from flask import Blueprint, render_template, redirect, url_for
from ..auth import get_current_user
from ..models import Coach

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    user = get_current_user()
    if user:
        if user.is_admin:
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('dashboard.index'))
        
    coaches = Coach.query.filter_by(is_active=True).all()
    return render_template('index.html', coaches=coaches)

@main_bp.route('/about')
def about():
    return render_template('index.html')
