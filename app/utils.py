
import os
import re
import time
import uuid
from pathlib import Path
from urllib.parse import unquote, urlparse

import cloudinary
import cloudinary.exceptions
import cloudinary.uploader
import cloudinary.utils
from flask import current_app
from werkzeug.utils import secure_filename


REPORT_PREFIX = "cloudinary_private:"
PRIVATE_URL_TTL_SECONDS = 300


class UploadStorageError(RuntimeError):
    """Raised when an upload or delete operation cannot be completed."""


def configure_cloudinary():
    """Configure Cloudinary from environment variables."""
    cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME", "").strip()
    api_key = os.environ.get("CLOUDINARY_API_KEY", "").strip()
    api_secret = os.environ.get("CLOUDINARY_API_SECRET", "").strip()

    if not all([cloud_name, api_key, api_secret]):
        return False

    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=True,
    )
    return True


def allowed_file(filename, allowed_extensions):
    if not filename or "." not in filename:
        return False
    return filename.rsplit(".", 1)[1].lower() in allowed_extensions


def save_uploaded_file(
    file_storage,
    subfolder,
    allowed_extensions=None,
    optimize_image=True,
):
    """Store files in Cloudinary; reports use authenticated delivery."""
    if not file_storage or not file_storage.filename:
        return None

    filename = secure_filename(file_storage.filename)
    extension = filename.rsplit(".", 1)[1].lower() if "." in filename else ""

    if not filename or (
        allowed_extensions and extension not in allowed_extensions
    ):
        return None

    if not configure_cloudinary():
        current_app.logger.error("Cloudinary credentials are not configured.")
        raise UploadStorageError("Cloudinary is not configured.")

    is_image = extension in {"jpg", "jpeg", "png", "webp"}
    is_report = subfolder == "reports"

    if subfolder not in {"profiles", "meals", "reports"}:
        raise UploadStorageError("Upload destination is invalid.")

    public_id = f"nutrilife/{subfolder}/{uuid.uuid4().hex}"

    options = {
        "public_id": public_id,
        "overwrite": False,
        "resource_type": "image" if is_image else "raw",
        "filename": filename,
    }

    if is_report:
        # Authenticated assets require a signed delivery URL.
        options["type"] = "authenticated"
    else:
        options["folder"] = f"nutrilife/{subfolder}"
        options.pop("public_id", None)
        options["public_id"] = f"{uuid.uuid4().hex}_{Path(filename).stem}"

    if is_image and optimize_image and not is_report:
        options["transformation"] = [
            {"width": 1600, "height": 1600, "crop": "limit"},
            {"quality": "auto"},
            {"fetch_format": "auto"},
        ]

    try:
        result = cloudinary.uploader.upload(file_storage, **options)
    except cloudinary.exceptions.Error as error:
        current_app.logger.error(
            "Cloudinary upload failed (%s).",
            type(error).__name__,
        )
        raise UploadStorageError("Cloudinary upload failed.") from None

    if not isinstance(result, dict):
        current_app.logger.error("Cloudinary upload returned an invalid response.")
        raise UploadStorageError("Cloudinary upload returned an invalid response.")

    public_id = result.get("public_id")
    if not public_id:
        current_app.logger.error("Cloudinary upload returned no public ID.")
        raise UploadStorageError("Cloudinary upload returned an invalid response.")

    if is_report:
        resource_type = result.get("resource_type")
        if resource_type != options["resource_type"]:
            current_app.logger.error(
                "Cloudinary report upload returned an invalid resource type."
            )
            raise UploadStorageError("Cloudinary report upload returned an invalid response.")
        return (
            f"{REPORT_PREFIX}{resource_type}:{extension}:"
            f"{public_id}"
        )

    secure_url = result.get("secure_url")
    parsed_url = urlparse(secure_url or "")
    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname != "res.cloudinary.com"
        or result.get("resource_type") != "image"
    ):
        current_app.logger.error("Cloudinary upload returned an invalid delivery URL.")
        raise UploadStorageError("Cloudinary upload returned an invalid response.")
    return secure_url


def get_private_report_url(stored_path):
    """Create a short-lived URL after the route checks report ownership."""
    if not stored_path or not stored_path.startswith(REPORT_PREFIX):
        return None

    if not configure_cloudinary():
        current_app.logger.error("Cloudinary credentials are not configured.")
        return None

    try:
        parts = stored_path[len(REPORT_PREFIX):].split(":", 2)
        if len(parts) == 3:
            resource_type, file_format, public_id = parts
        elif len(parts) == 2:
            resource_type, public_id = parts
            file_format = "pdf" if resource_type == "raw" else "jpg"
        else:
            return None

        if (
            resource_type not in {"image", "raw"}
            or not re.fullmatch(r"[a-zA-Z0-9]{1,10}", file_format)
            or not public_id
        ):
            return None

        return cloudinary.utils.private_download_url(
            public_id,
            file_format,
            resource_type=resource_type,
            type="authenticated",
            expires_at=int(time.time()) + PRIVATE_URL_TTL_SECONDS,
        )
    except cloudinary.exceptions.Error as error:
        current_app.logger.error(
            "Could not create a private report URL (%s).",
            type(error).__name__,
        )
        return None


def delete_uploaded_file(stored_path):
    """Delete Cloudinary assets or legacy local files without unsafe path access."""
    if not stored_path:
        return

    if stored_path.startswith(REPORT_PREFIX):
        parts = stored_path[len(REPORT_PREFIX):].split(":", 2)
        if len(parts) == 3:
            resource_type, _, public_id = parts
        elif len(parts) == 2:
            resource_type, public_id = parts
        else:
            raise UploadStorageError("Stored private report identifier is invalid.")
        access_type = "authenticated"
    else:
        parsed = urlparse(stored_path)
        if parsed.scheme or parsed.netloc:
            if parsed.scheme != "https" or parsed.hostname != "res.cloudinary.com":
                raise UploadStorageError("Stored Cloudinary URL is invalid.")

            parts = unquote(parsed.path).strip("/").split("/")
            try:
                upload_index = parts.index("upload")
            except ValueError:
                raise UploadStorageError("Stored Cloudinary URL is invalid.") from None

            resource_type = parts[upload_index - 1] if upload_index else ""
            if resource_type not in {"image", "raw"}:
                raise UploadStorageError("Stored Cloudinary resource type is invalid.")

            asset_parts = parts[upload_index + 1:]
            version_index = next(
                (
                    index for index, part in enumerate(asset_parts)
                    if re.fullmatch(r"v\d+", part)
                ),
                None,
            )
            if version_index is not None:
                asset_parts = asset_parts[version_index + 1:]
            if not asset_parts:
                raise UploadStorageError("Stored Cloudinary public ID is missing.")

            public_id = "/".join(asset_parts)
            if resource_type == "image":
                public_id = public_id.rsplit(".", 1)[0]
            access_type = "upload"
        else:
            upload_root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
            local_path = (upload_root / stored_path).resolve()
            if upload_root not in local_path.parents:
                raise UploadStorageError("Stored upload path is invalid.")
            if not local_path.exists():
                return
            try:
                local_path.unlink()
            except OSError as error:
                current_app.logger.error(
                    "Could not delete legacy local upload (%s).",
                    type(error).__name__,
                )
                raise UploadStorageError("Legacy local upload could not be deleted.") from None
            return

    if resource_type not in {"image", "raw"} or not public_id:
        raise UploadStorageError("Stored Cloudinary asset identifier is invalid.")

    if not configure_cloudinary():
        current_app.logger.error("Cloudinary credentials are not configured for deletion.")
        raise UploadStorageError("Cloudinary is not configured.")

    try:
        result = cloudinary.uploader.destroy(
            public_id,
            resource_type=resource_type,
            type=access_type,
            invalidate=True,
        )
    except cloudinary.exceptions.Error as error:
        current_app.logger.error(
            "Cloudinary deletion failed (%s).",
            type(error).__name__,
        )
        raise UploadStorageError("Cloudinary deletion failed.") from None

    if not isinstance(result, dict):
        current_app.logger.error("Cloudinary deletion returned an invalid response.")
        raise UploadStorageError("Cloudinary deletion failed.")

    if result.get("result") not in {"ok", "not found"}:
        current_app.logger.error("Cloudinary deletion returned an unsuccessful result.")
        raise UploadStorageError("Cloudinary deletion failed.")
