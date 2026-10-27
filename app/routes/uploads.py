
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    make_response,
    send_from_directory,
)

from ..auth import get_current_user
from ..models import BloodReport, Meal
from ..utils import REPORT_PREFIX, get_private_report_url


uploads_bp = Blueprint("uploads", __name__)


@uploads_bp.route("/uploads/<folder>/<path:filename>")
def serve_file(folder, filename):
    if folder not in {"profiles", "meals", "reports"}:
        abort(404)

    user = get_current_user()

    # All meal photos and blood reports require login.
    if folder in {"meals", "reports"} and not user:
        abort(401)

    # Private Cloudinary blood report: check ownership before redirecting.
    if folder == "reports" and filename.startswith(REPORT_PREFIX):
        report_query = BloodReport.query.filter_by(
            report_file_path=filename
        )

        if user.is_admin:
            report = report_query.first()
        else:
            report = report_query.filter_by(
                participant_id=user.id
            ).first()

        if not report:
            abort(404)

        signed_url = get_private_report_url(filename)
        if not signed_url:
            abort(503)

        response = make_response(redirect(signed_url))
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    # Never serve a persisted public Cloudinary report URL directly.
    if folder == "reports" and filename.startswith(("https://", "http://")):
        abort(404)

    # Cloudinary image URLs can be displayed directly.
    # This route handles only local/legacy uploads and private reports.
    upload_root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    upload_dir = (upload_root / folder).resolve()

    if upload_root not in upload_dir.parents:
        abort(404)

    file_path = (upload_dir / filename).resolve()

    if upload_dir not in file_path.parents:
        abort(404)

    if not file_path.is_file():
        abort(404)

    # Profile photos are not private records.
    if folder == "profiles":
        return send_from_directory(upload_dir, filename)

    # Verify that the requested legacy file belongs to the user.
    relative_path = f"{folder}/{filename}"

    if folder == "meals":
        query = Meal.query.filter_by(photo_path=relative_path)
    else:
        query = BloodReport.query.filter_by(
            report_file_path=relative_path
        )

    if user.is_admin:
        record = query.first()
    else:
        record = query.filter_by(participant_id=user.id).first()

    if not record:
        abort(404)

    return send_from_directory(upload_dir, filename)
