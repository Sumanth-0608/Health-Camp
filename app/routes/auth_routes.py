from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for, flash, g
from sqlalchemy.exc import SQLAlchemyError
from ..models import db, User, ParticipantProfile, ensure_primary_coach
from ..auth import login_user, logout_user, get_current_user, login_required, initialize_participant_records
from ..utils import UploadStorageError, save_uploaded_file, allowed_file
from flask import current_app

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    # If already logged in, redirect to dashboard
    if get_current_user():
        return redirect(url_for('dashboard.index'))
        
    try:
        primary_coach = ensure_primary_coach()
    except (SQLAlchemyError, ValueError):
        db.session.rollback()
        current_app.logger.exception("Could not load the registration coach.")
        return render_template(
            'auth/register.html',
            coaches=[],
            coach_error=True,
            today_str=date.today().strftime('%Y-%m-%d'),
            form=request.form if request.method == 'POST' else {}
        ), 503

    coaches = [primary_coach] if primary_coach else []
    
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        mobile = request.form.get('mobile', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        coach_id = request.form.get('coach_id', '').strip()
        start_date_str = request.form.get('start_date', '').strip()
        goal_90_day = request.form.get('goal_90_day', '').strip()
        reason_why = request.form.get('reason_why', '').strip()
        session_day_time = request.form.get('session_day_time', '').strip()
        root_cause_1 = request.form.get('root_cause_1', '').strip()
        root_cause_2 = request.form.get('root_cause_2', '').strip()
        
        # Validations
        errors = []
        if not full_name:
            errors.append("Full Name is required.")
        if not email or '@' not in email:
            errors.append("A valid email address is required.")
        if not mobile:
            errors.append("Mobile number is required.")
        if not password or len(password) < 6:
            errors.append("Password must be at least 6 characters long.")
        if password != confirm_password:
            errors.append("Passwords do not match.")
        if not start_date_str:
            errors.append("Program start date is required.")
        if not goal_90_day:
            errors.append("Personal 90-day wellness goal is required.")
        if not reason_why:
            errors.append("Reason for joining (your 'why') is required.")
        if not session_day_time:
            errors.append("Session day and preferred time are required.")
        if not root_cause_1 or not root_cause_2:
            errors.append("Both primary root causes/challenges are required.")
        if not primary_coach or coach_id != str(primary_coach.id):
            errors.append("Please select the available NutriLife coach.")
            
        # Check existing user
        if User.query.filter_by(email=email).first():
            errors.append("An account with this email address already exists. Please log in.")
            
        start_date_val = None
        try:
            start_date_val = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except Exception:
            errors.append("Invalid start date format. Please select a valid date.")
            
        if errors:
            for err in errors:
                flash(err, "danger")
            return render_template('auth/register.html', coaches=coaches, form=request.form)
            
        # Handle optional profile photo
        profile_photo_path = None
        if 'profile_photo' in request.files:
            file = request.files['profile_photo']
            if file and file.filename:
                if allowed_file(file.filename, current_app.config['ALLOWED_IMAGE_EXTENSIONS']):
                    try:
                        profile_photo_path = save_uploaded_file(
                            file,
                            'profiles',
                            current_app.config['ALLOWED_IMAGE_EXTENSIONS']
                        )
                    except UploadStorageError:
                        flash(
                            "Profile photo upload failed. You can upload it later from your profile.",
                            "warning"
                        )
                else:
                    flash("Invalid image format for profile photo. Allowed: JPG, PNG, WEBP.", "warning")
                    
        # Determine coach
        # Create user (Strictly participant role)
        user = User(
            email=email,
            full_name=full_name,
            mobile=mobile,
            role='participant',
            profile_photo=profile_photo_path,
            is_active=True
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush() # get user.id
        
        # Create participant profile
        profile = ParticipantProfile(
            user_id=user.id,
            coach_id=primary_coach.id,
            coach_name=primary_coach.name,
            start_date=start_date_val,
            goal_90_day=goal_90_day,
            reason_why=reason_why,
            session_day_time=session_day_time,
            root_cause_1=root_cause_1,
            root_cause_2=root_cause_2
        )
        db.session.add(profile)
        db.session.commit()
        
        # Initialize tracking records (food, water, habits, measurements, blood reports, weekly scores)
        initialize_participant_records(user, start_date_val)
        
        # Automatically login participant
        login_user(user)
        flash(f"Welcome to Dr. Girija's NutriLife, {user.full_name}! Your personal tracker is ready.", "success")
        return redirect(url_for('dashboard.index'))
        
    today_str = date.today().strftime('%Y-%m-%d')
    return render_template('auth/register.html', coaches=coaches, today_str=today_str, form={})

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if get_current_user():
        user = get_current_user()
        if user.is_admin:
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('dashboard.index'))
        
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'
        
        if not email or not password:
            flash("Please enter both email and password.", "danger")
            return render_template('auth/login.html')
            
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash("Invalid email or password. Please try again.", "danger")
            return render_template('auth/login.html')
            
        if not user.is_active:
            flash("Your account has been deactivated. Please contact support.", "danger")
            return render_template('auth/login.html')
            
        login_user(user)
        flash(f"Welcome back, {user.full_name}!", "success")
        
        next_page = request.args.get('next')
        if next_page and next_page.startswith('/'):
            return redirect(next_page)
            
        if user.is_admin:
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('dashboard.index'))
        
    return render_template('auth/login.html')

@auth_bp.route('/logout')
def logout():
    logout_user()
    flash("You have been securely logged out.", "info")
    return redirect(url_for('main.index'))

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        new_password = request.form.get('new_password', '')
        confirm_new = request.form.get('confirm_new_password', '')
        
        user = User.query.filter_by(email=email).first()
        if not user:
            # Consistent feedback
            flash("If that email exists in our system, the password has been updated.", "info")
            return redirect(url_for('auth.login'))
            
        if not new_password or len(new_password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return render_template('auth/forgot_password.html')
            
        if new_password != confirm_new:
            flash("Passwords do not match.", "danger")
            return render_template('auth/forgot_password.html')
            
        user.set_password(new_password)
        db.session.commit()
        flash("Password successfully reset! You can now log in with your new password.", "success")
        return redirect(url_for('auth.login'))
        
    return render_template('auth/forgot_password.html')
