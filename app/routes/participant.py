from datetime import date, datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, g, current_app, jsonify
from ..models import (
    db, User, ParticipantProfile, Coach, DailyLog, Meal, WaterLog, 
    WaterGoal, MovementEntry, HabitWeek, HabitDay, Measurement, 
    BloodReport, WeeklyScore, SupportConversation
)
from ..auth import login_required, get_current_user
from ..utils import save_uploaded_file, delete_uploaded_file, allowed_file

participant_bp = Blueprint('dashboard', __name__)

@participant_bp.route('/dashboard')
@login_required
def index():
    user = g.current_user
    if user.is_admin:
        return redirect(url_for('admin.dashboard'))
        
    profile = user.profile
    if not profile:
        flash("Profile not found. Please contact support.", "danger")
        return redirect(url_for('auth.logout'))
        
    # Calculate real program day based on start_date and current date
    today = date.today()
    program_day = profile.get_program_day(today)
    days_completed = profile.get_days_completed()
    days_remaining = profile.get_days_remaining()
    
    # 1. Today's Daily Log and Meals
    today_meals = Meal.query.filter_by(participant_id=user.id, date=today).all()
    today_meals_by_slot = {m.meal_slot: m for m in today_meals}
    meals_logged_count = len(today_meals)
    
    # 2. Today's Water
    today_water_entries = WaterLog.query.filter_by(participant_id=user.id, date=today).order_by(WaterLog.logged_at.desc()).all()
    today_water_ml = sum(w.amount_ml for w in today_water_entries)
    water_goal_obj = WaterGoal.query.filter_by(participant_id=user.id).first()
    daily_water_goal_ml = water_goal_obj.daily_goal_ml if water_goal_obj else 3000
    water_percent = min(100, int((today_water_ml / daily_water_goal_ml) * 100)) if daily_water_goal_ml > 0 else 0
    
    # 3. Today's Movement
    today_movement = MovementEntry.query.filter_by(participant_id=user.id, date=today).first()
    
    # 4. Movement Averages overall (Excel exact formulas: COUNT(D10:D99), AVERAGE(D10:D99), AVERAGE(J10:J99))
    all_movement = MovementEntry.query.filter_by(participant_id=user.id).all()
    steps_list = [m.steps for m in all_movement if m.steps is not None]
    active_mins_list = [m.total_active_mins for m in all_movement if m.total_active_mins is not None]
    
    movement_days_filled = len(steps_list)
    avg_steps = round(sum(steps_list) / len(steps_list)) if steps_list else 0
    avg_active_mins = round(sum(active_mins_list) / len(active_mins_list)) if active_mins_list else 0
    
    # 5. Current Week's Habits
    # Determine current week number 1 to 12
    current_week_num = max(1, min(12, ((program_day - 1) // 7) + 1)) if program_day >= 1 else 1
    current_habit_week = HabitWeek.query.filter_by(participant_id=user.id, week_number=current_week_num).first()
    current_habit_days = HabitDay.query.filter_by(participant_id=user.id, week_number=current_week_num).order_by(HabitDay.step_index.asc()).all()
    
    # Calculate habit score for current week
    total_days_done = sum(h.days_done for h in current_habit_days)
    habit_week_pct = round((total_days_done / 21.0) * 100, 1) if current_habit_days else 0
    
    # 6. Latest Measurement and Progress
    all_measurements = Measurement.query.filter_by(participant_id=user.id).order_by(Measurement.week_number.asc()).all()
    start_measurement = next((m for m in all_measurements if m.week_number == 0), None)
    
    # Find latest measurement with recorded values
    latest_measurement = None
    for m in reversed(all_measurements):
        if m.weight_kg is not None or m.waist_cm is not None:
            latest_measurement = m
            break
            
    # Calculate Change so far: Latest minus Start (Excel formula: LOOKUP(9.99E+307, range) - Start)
    changes = {}
    if start_measurement and latest_measurement and latest_measurement.week_number > 0:
        for field in ['weight_kg', 'waist_cm', 'hips_cm', 'chest_cm', 'upper_arm_cm', 'thigh_cm']:
            start_val = getattr(start_measurement, field)
            latest_val = getattr(latest_measurement, field)
            if start_val is not None and latest_val is not None:
                changes[field] = round(latest_val - start_val, 1)
            else:
                changes[field] = None
    else:
        changes = {f: None for f in ['weight_kg', 'waist_cm', 'hips_cm', 'chest_cm', 'upper_arm_cm', 'thigh_cm']}
        
    # 7. Latest Weekly Score & trend
    weekly_scores = WeeklyScore.query.filter_by(participant_id=user.id).order_by(WeeklyScore.week_number.asc()).all()
    latest_score_obj = None
    for ws in reversed(weekly_scores):
        if ws.week_average is not None:
            latest_score_obj = ws
            break
            
    # 8. Daily Task Completion Status (4 key pillars today: Food, Water, Movement, Habits)
    tasks = [
        {
            'name': 'Log Meals (Food Tracker)',
            'status': 'Completed' if meals_logged_count >= 3 else ('In Progress' if meals_logged_count > 0 else 'Pending'),
            'done': meals_logged_count >= 3,
            'details': f"{meals_logged_count}/7 meal slots recorded today",
            'link': url_for('trackers.food', date=today.strftime('%Y-%m-%d'))
        },
        {
            'name': 'Hydration Goal (Water Tracker)',
            'status': 'Completed' if today_water_ml >= daily_water_goal_ml else ('In Progress' if today_water_ml > 0 else 'Pending'),
            'done': today_water_ml >= daily_water_goal_ml,
            'details': f"{today_water_ml} ml / {daily_water_goal_ml} ml ({water_percent}%)",
            'link': url_for('trackers.water', date=today.strftime('%Y-%m-%d'))
        },
        {
            'name': 'Record Movement & Steps',
            'status': 'Completed' if (today_movement and (today_movement.steps or today_movement.total_active_mins)) else 'Pending',
            'done': bool(today_movement and (today_movement.steps or today_movement.total_active_mins)),
            'details': f"{today_movement.steps if today_movement and today_movement.steps else 0} steps, {today_movement.total_active_mins if today_movement and today_movement.total_active_mins else 0} active mins",
            'link': url_for('trackers.movement', date=today.strftime('%Y-%m-%d'))
        },
        {
            'name': f"Weekly Action Steps (Week {current_week_num})",
            'status': 'Completed' if habit_week_pct >= 70 else ('In Progress' if habit_week_pct > 0 else 'Pending'),
            'done': habit_week_pct >= 70,
            'details': f"{habit_week_pct}% achieved this week",
            'link': url_for('trackers.habits', week=current_week_num)
        }
    ]
    
    completed_tasks_count = sum(1 for t in tasks if t['done'])
    daily_completion_pct = int((completed_tasks_count / len(tasks)) * 100)
    
    # 9. Support queries status
    open_tickets = SupportConversation.query.filter_by(participant_id=user.id, status='Replied').count()
    
    # Prepare charts data (Weight & Waist history, Weekly Score history)
    chart_weeks = []
    chart_weights = []
    chart_waists = []
    for m in all_measurements:
        if m.weight_kg is not None or m.waist_cm is not None:
            chart_weeks.append(m.week_label)
            chart_weights.append(m.weight_kg if m.weight_kg is not None else None)
            chart_waists.append(m.waist_cm if m.waist_cm is not None else None)
            
    chart_score_weeks = []
    chart_score_averages = []
    for ws in weekly_scores:
        if ws.week_average is not None:
            chart_score_weeks.append(f"Wk {ws.week_number}")
            chart_score_averages.append(ws.week_average)

    return render_template(
        'dashboard/index.html',
        user=user,
        profile=profile,
        today=today,
        program_day=program_day,
        days_completed=days_completed,
        days_remaining=days_remaining,
        tasks=tasks,
        daily_completion_pct=daily_completion_pct,
        today_meals_by_slot=today_meals_by_slot,
        today_water_ml=today_water_ml,
        daily_water_goal_ml=daily_water_goal_ml,
        water_percent=water_percent,
        today_movement=today_movement,
        movement_days_filled=movement_days_filled,
        avg_steps=avg_steps,
        avg_active_mins=avg_active_mins,
        current_week_num=current_week_num,
        current_habit_week=current_habit_week,
        current_habit_days=current_habit_days,
        habit_week_pct=habit_week_pct,
        latest_measurement=latest_measurement,
        start_measurement=start_measurement,
        changes=changes,
        latest_score_obj=latest_score_obj,
        open_tickets=open_tickets,
        chart_weeks=chart_weeks,
        chart_weights=chart_weights,
        chart_waists=chart_waists,
        chart_score_weeks=chart_score_weeks,
        chart_score_averages=chart_score_averages
    )

@participant_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = g.current_user
    profile = user.profile
    coaches = Coach.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        # 1. Update Profile Information (Name, Mobile, Coach, Root Causes, Session Day)
        if action == 'update_info':
            full_name = request.form.get('full_name', '').strip()
            mobile = request.form.get('mobile', '').strip()
            coach_id = request.form.get('coach_id', '').strip()
            coach_name = request.form.get('coach_name', '').strip()
            goal_90_day = request.form.get('goal_90_day', '').strip()
            reason_why = request.form.get('reason_why', '').strip()
            session_day_time = request.form.get('session_day_time', '').strip()
            root_cause_1 = request.form.get('root_cause_1', '').strip()
            root_cause_2 = request.form.get('root_cause_2', '').strip()
            
            if not full_name:
                flash("Full name cannot be blank.", "danger")
                return redirect(url_for('dashboard.profile'))
            if not mobile:
                flash("Mobile number cannot be blank.", "danger")
                return redirect(url_for('dashboard.profile'))
                
            user.full_name = full_name
            user.mobile = mobile
            
            if profile:
                if coach_id and coach_id.isdigit():
                    coach = db.session.get(Coach, int(coach_id))
                    if coach:
                        profile.coach_id = coach.id
                        profile.coach_name = coach.name
                elif coach_name:
                    profile.coach_name = coach_name
                    
                profile.goal_90_day = goal_90_day
                profile.reason_why = reason_why
                profile.session_day_time = session_day_time
                profile.root_cause_1 = root_cause_1
                profile.root_cause_2 = root_cause_2
                
            db.session.commit()
            flash("Your profile information has been successfully updated.", "success")
            return redirect(url_for('dashboard.profile'))
            
        # 2. Update Profile Photo
        elif action == 'update_photo':
            if 'profile_photo' in request.files:
                file = request.files['profile_photo']
                if file and file.filename:
                    if allowed_file(file.filename, current_app.config['ALLOWED_IMAGE_EXTENSIONS']):
                        # Delete old photo if existed
                        if user.profile_photo:
                            delete_uploaded_file(user.profile_photo)
                        new_path = save_uploaded_file(file, 'profiles', current_app.config['ALLOWED_IMAGE_EXTENSIONS'])
                        user.profile_photo = new_path
                        db.session.commit()
                        flash("Profile photo updated successfully!", "success")
                    else:
                        flash("Invalid image format. Supported formats: JPG, PNG, WEBP.", "danger")
                else:
                    flash("Please select a valid image file to upload.", "warning")
            return redirect(url_for('dashboard.profile'))
            
        # 3. Remove Profile Photo
        elif action == 'remove_photo':
            if user.profile_photo:
                delete_uploaded_file(user.profile_photo)
                user.profile_photo = None
                db.session.commit()
                flash("Profile photo removed.", "info")
            return redirect(url_for('dashboard.profile'))
            
        # 4. Change Password
        elif action == 'change_password':
            curr_pass = request.form.get('current_password', '')
            new_pass = request.form.get('new_password', '')
            confirm_pass = request.form.get('confirm_password', '')
            
            if not user.check_password(curr_pass):
                flash("Current password incorrect.", "danger")
                return redirect(url_for('dashboard.profile'))
            if not new_pass or len(new_pass) < 6:
                flash("New password must be at least 6 characters long.", "danger")
                return redirect(url_for('dashboard.profile'))
            if new_pass != confirm_pass:
                flash("New passwords do not match.", "danger")
                return redirect(url_for('dashboard.profile'))
                
            user.set_password(new_pass)
            db.session.commit()
            flash("Your password has been changed successfully.", "success")
            return redirect(url_for('dashboard.profile'))

    return render_template('dashboard/profile.html', user=user, profile=profile, coaches=coaches)
