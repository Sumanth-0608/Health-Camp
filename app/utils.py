import os
import uuid
from pathlib import Path
from flask import current_app
from werkzeug.utils import secure_filename
from PIL import Image

def allowed_file(filename, allowed_extensions):
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in allowed_extensions

def save_uploaded_file(file_storage, subfolder, allowed_extensions=None, optimize_image=True):
    """
    Saves an uploaded file into the specified subfolder inside UPLOAD_FOLDER.
    Returns relative path like 'meals/uuid_name.jpg' or None on failure.
    """
    if not file_storage or not file_storage.filename:
        return None
        
    filename = secure_filename(file_storage.filename)
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    
    if allowed_extensions and ext not in allowed_extensions:
        return None
        
    target_dir = Path(current_app.config['UPLOAD_FOLDER']) / subfolder
    target_dir.mkdir(parents=True, exist_ok=True)
    
    unique_name = f"{uuid.uuid4().hex[:12]}_{filename}"
    file_path = target_dir / unique_name
    
    # If image, optionally resize/optimize with Pillow
    if optimize_image and ext in {'jpg', 'jpeg', 'png', 'webp'}:
        try:
            image = Image.open(file_storage)
            # Convert RGBA to RGB for JPEG if needed
            if image.mode in ('RGBA', 'P') and ext in ('jpg', 'jpeg'):
                image = image.convert('RGB')
            # Resize if unnecessarily large (e.g. > 1600px width/height)
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            image.save(file_path, quality=85, optimize=True)
            return f"{subfolder}/{unique_name}"
        except Exception:
            file_storage.seek(0)
            file_storage.save(file_path)
            return f"{subfolder}/{unique_name}"
    else:
        file_storage.save(file_path)
        return f"{subfolder}/{unique_name}"

def delete_uploaded_file(relative_path):
    if not relative_path:
        return
    try:
        full_path = Path(current_app.config['UPLOAD_FOLDER']) / relative_path
        if full_path.exists() and full_path.is_file():
            full_path.unlink()
    except Exception:
        pass
