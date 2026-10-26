from pathlib import Path
from flask import Blueprint, send_from_directory, abort, current_app, g
from ..auth import login_required, get_current_user
from ..models import Meal, BloodReport, User

uploads_bp = Blueprint('uploads', __name__)

@uploads_bp.route('/uploads/<folder>/<filename>')
def serve_file(folder, filename):
    # Only allow known subfolders
    if folder not in {'profiles', 'meals', 'reports'}:
        abort(404)
        
    upload_dir = Path(current_app.config['UPLOAD_FOLDER']) / folder
    file_path = upload_dir / filename
    if not file_path.is_file():
        abort(404)
        
    rel_path = f"{folder}/{filename}"
    
    # Check permissions based on folder
    user = get_current_user()
    
    # Profiles can be viewed by authenticated users (or anyone for default coach/demo badges)
    if folder == 'profiles':
        return send_from_directory(upload_dir, filename)
        
    # Meals and Reports require authentication and strict ownership verification
    if not user:
        abort(401)
        
    if user.is_admin:
        # Admins can view participants' meals and reports for coaching review
        return send_from_directory(upload_dir, filename)
        
    if folder == 'meals':
        # Check if the meal belongs to the current user
        meal = Meal.query.filter_by(participant_id=user.id, photo_path=rel_path).first()
        if not meal:
            abort(403)
        return send_from_directory(upload_dir, filename)
        
    if folder == 'reports':
        # Check if report belongs to current user
        report = BloodReport.query.filter_by(participant_id=user.id, report_file_path=rel_path).first()
        if not report:
            abort(403)
        return send_from_directory(upload_dir, filename)
        
    abort(403)
