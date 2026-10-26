from functools import wraps
from flask import session, redirect, url_for, flash, request, g, abort
from .models import (
    db, User, ParticipantProfile, WaterGoal, Measurement, 
    BloodReport, HabitWeek, HabitDay, WeeklyScore
)
from datetime import timedelta

def get_current_user():
    if 'user_id' not in session:
        return None
    user_id = session.get('user_id')
    user = db.session.get(User, user_id)
    if not user or not user.is_active:
        session.pop('user_id', None)
        return None
    return user

def login_user(user):
    session['user_id'] = user.id
    session.permanent = True

def logout_user():
    session.pop('user_id', None)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('auth.login', next=request.url))
        g.current_user = user
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            flash("Please log in with administrator privileges.", "warning")
            return redirect(url_for('auth.login', next=request.url))
        if not user.is_admin:
            flash("Access denied. Administrator privileges are required.", "danger")
            return redirect(url_for('dashboard.index'))
        g.current_user = user
        return f(*args, **kwargs)
    return decorated_function

def initialize_participant_records(user, start_date):
    """
    Initializes standard Excel-matched records for a newly registered participant:
    - Water goal (3000ml)
    - Measurements rows (Start / Week 1 to 12)
    - 15 Standard Blood Reports
    - 12 Habit Weeks and Habit Day slots (3 steps/week)
    - 12 Weekly Score rows
    """
    # 1. Water goal
    existing_wg = WaterGoal.query.filter_by(participant_id=user.id).first()
    if not existing_wg:
        wg = WaterGoal(participant_id=user.id, daily_goal_ml=3000)
        db.session.add(wg)
        
    # 2. Measurements (0 = Start (day 1), 1..12 = Week 1..12)
    existing_m = Measurement.query.filter_by(participant_id=user.id).count()
    if existing_m == 0:
        labels = [
            (0, "Start (day 1)"),
            (1, "Week 1"), (2, "Week 2"), (3, "Week 3"), (4, "Week 4"),
            (5, "Week 5"), (6, "Week 6"), (7, "Week 7"), (8, "Week 8"),
            (9, "Week 9"), (10, "Week 10"), (11, "Week 11"), (12, "Week 12")
        ]
        for w_num, label in labels:
            expected_date = start_date + timedelta(days=w_num * 7) if w_num > 0 else start_date
            m = Measurement(
                participant_id=user.id,
                week_number=w_num,
                week_label=label,
                date=expected_date
            )
            db.session.add(m)
            
    # 3. Standard Blood Reports (15 tests from Excel worksheet)
    existing_br = BloodReport.query.filter_by(participant_id=user.id).count()
    if existing_br == 0:
        for test in BloodReport.STANDARD_TESTS:
            br = BloodReport(
                participant_id=user.id,
                test_name=test,
                is_custom=False
            )
            db.session.add(br)
            
    # 4. Habit Weeks (12 weeks, 3 action steps each)
    existing_hw = HabitWeek.query.filter_by(participant_id=user.id).count()
    if existing_hw == 0:
        for w in range(1, 13):
            w_start = start_date + timedelta(days=(w - 1) * 7)
            w_end = w_start + timedelta(days=6)
            date_label = f"{w_start.strftime('%b %d')} - {w_end.strftime('%b %d')}"
            
            hw = HabitWeek(
                participant_id=user.id,
                week_number=w,
                date_range_label=date_label,
                step_1="Drink 3 liters of water throughout the day",
                step_2="30 minutes brisk morning walk",
                step_3="Consistent sleep schedule with 30m screen-off routine"
            )
            db.session.add(hw)
            
            # Create corresponding 3 habit day tracking rows
            for step_idx in [1, 2, 3]:
                hd = HabitDay(
                    participant_id=user.id,
                    week_number=w,
                    step_index=step_idx
                )
                db.session.add(hd)

    # 5. Weekly Scores (12 weeks)
    existing_ws = WeeklyScore.query.filter_by(participant_id=user.id).count()
    if existing_ws == 0:
        for w in range(1, 13):
            ws = WeeklyScore(
                participant_id=user.id,
                week_number=w
            )
            db.session.add(ws)

    db.session.commit()
