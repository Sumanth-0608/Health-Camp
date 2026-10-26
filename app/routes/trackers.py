from datetime import date, datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, g, jsonify, current_app
from ..models import (
    db, User, ParticipantProfile, DailyLog, Meal, WaterLog, 
    WaterGoal, MovementEntry, HabitWeek, HabitDay, Measurement, 
    BloodReport, WeeklyScore
)
from ..auth import login_required
from ..utils import save_uploaded_file, delete_uploaded_file, allowed_file

trackers_bp = Blueprint('trackers', __name__, url_prefix='/trackers')

def parse_target_date(profile, date_str=None, day_str=None):
    """
    Parses and returns (target_date, program_day).
    Ensures safe fallbacks to today.
    """
    if day_str and day_str.isdigit():
        day_num = int(day_str)
        target_date = profile.start_date + timedelta(days=day_num - 1)
        return target_date, day_num
        
    if date_str:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            day_num = profile.get_program_day(target_date)
            return target_date, day_num
        except Exception:
            pass
            
    today = date.today()
    return today, profile.get_program_day(today)

# ----------------- 1. DAILY TASKS OVERVIEW -----------------
@trackers_bp.route('/daily')
@login_required
def daily():
    user = g.current_user
    profile = user.profile
    target_date, program_day = parse_target_date(profile, request.args.get('date'), request.args.get('day'))
    
    # Get or create daily log
    daily_log = DailyLog.query.filter_by(participant_id=user.id, date=target_date).first()
    
    # Meals for date
    meals = Meal.query.filter_by(participant_id=user.id, date=target_date).all()
    meals_by_slot = {m.meal_slot: m for m in meals}
    
    # Water for date
    water_entries = WaterLog.query.filter_by(participant_id=user.id, date=target_date).order_by(WaterLog.logged_at.desc()).all()
    water_total_ml = sum(w.amount_ml for w in water_entries)
    water_goal_obj = WaterGoal.query.filter_by(participant_id=user.id).first()
    water_goal_ml = water_goal_obj.daily_goal_ml if water_goal_obj else 3000
    
    # Movement for date
    movement = MovementEntry.query.filter_by(participant_id=user.id, date=target_date).first()
    
    # Current week habits
    week_num = max(1, min(12, ((program_day - 1) // 7) + 1)) if program_day >= 1 else 1
    habit_week = HabitWeek.query.filter_by(participant_id=user.id, week_number=week_num).first()
    habit_days = HabitDay.query.filter_by(participant_id=user.id, week_number=week_num).order_by(HabitDay.step_index.asc()).all()

    prev_date = target_date - timedelta(days=1)
    next_date = target_date + timedelta(days=1)

    return render_template(
        'trackers/daily.html',
        user=user,
        profile=profile,
        target_date=target_date,
        program_day=program_day,
        prev_date=prev_date,
        next_date=next_date,
        daily_log=daily_log,
        meals_by_slot=meals_by_slot,
        meal_slots=Meal.MEAL_SLOTS,
        water_entries=water_entries,
        water_total_ml=water_total_ml,
        water_goal_ml=water_goal_ml,
        movement=movement,
        week_num=week_num,
        habit_week=habit_week,
        habit_days=habit_days
    )

# ----------------- 2. FOOD TRACKER -----------------
@trackers_bp.route('/food', methods=['GET', 'POST'])
@login_required
def food():
    user = g.current_user
    profile = user.profile
    target_date, program_day = parse_target_date(profile, request.args.get('date'), request.args.get('day'))
    
    # Ensure DailyLog exists
    daily_log = DailyLog.query.filter_by(participant_id=user.id, date=target_date).first()
    if not daily_log:
        daily_log = DailyLog(
            participant_id=user.id,
            date=target_date,
            program_day=program_day,
            water_glasses=0
        )
        db.session.add(daily_log)
        db.session.commit()
        
    if request.method == 'POST':
        action = request.form.get('action')
        
        # Save a meal slot
        if action == 'save_meal':
            slot = request.form.get('meal_slot')
            meal_time = request.form.get('meal_time', '').strip()
            food_description = request.form.get('food_description', '').strip()
            notes = request.form.get('notes', '').strip()
            remove_photo = request.form.get('remove_photo') == 'true'
            
            meal = Meal.query.filter_by(participant_id=user.id, date=target_date, meal_slot=slot).first()
            if not meal:
                meal = Meal(
                    participant_id=user.id,
                    daily_log_id=daily_log.id,
                    date=target_date,
                    meal_slot=slot
                )
                db.session.add(meal)
                
            meal.meal_time = meal_time
            meal.food_description = food_description
            meal.notes = notes
            
            if remove_photo and meal.photo_path:
                delete_uploaded_file(meal.photo_path)
                meal.photo_path = None
                
            # Optional photo upload
            photo_file = request.files.get(f'photo_{slot}') or request.files.get('meal_photo')
            if photo_file and photo_file.filename:
                if allowed_file(photo_file.filename, current_app.config['ALLOWED_IMAGE_EXTENSIONS']):
                    if meal.photo_path:
                        delete_uploaded_file(meal.photo_path)
                    saved_path = save_uploaded_file(photo_file, 'meals', current_app.config['ALLOWED_IMAGE_EXTENSIONS'])
                    meal.photo_path = saved_path
                else:
                    flash("Invalid image format for meal photo. Allowed: JPG, PNG, WEBP.", "warning")
                    
            db.session.commit()
            flash(f"{dict(Meal.MEAL_SLOTS).get(slot, 'Meal')} details saved successfully.", "success")
            return redirect(url_for('trackers.food', date=target_date.strftime('%Y-%m-%d')))
            
        # Save daily notes / cravings / water glasses
        elif action == 'save_daily_notes':
            craving_notes = request.form.get('craving_notes', '').strip()
            water_glasses = request.form.get('water_glasses', '0').strip()
            
            daily_log.craving_notes = craving_notes
            try:
                daily_log.water_glasses = max(0, int(water_glasses))
            except ValueError:
                daily_log.water_glasses = 0
                
            db.session.commit()
            flash("Cravings & notes saved successfully.", "success")
            return redirect(url_for('trackers.food', date=target_date.strftime('%Y-%m-%d')))

    # Fetch all meals for this date
    existing_meals = Meal.query.filter_by(participant_id=user.id, date=target_date).all()
    meals_by_slot = {m.meal_slot: m for m in existing_meals}
    
    # 90-day history overview list
    history_logs = DailyLog.query.filter_by(participant_id=user.id).order_by(DailyLog.date.asc()).all()

    prev_date = target_date - timedelta(days=1)
    next_date = target_date + timedelta(days=1)

    return render_template(
        'trackers/food.html',
        user=user,
        profile=profile,
        target_date=target_date,
        program_day=program_day,
        prev_date=prev_date,
        next_date=next_date,
        daily_log=daily_log,
        meals_by_slot=meals_by_slot,
        meal_slots=Meal.MEAL_SLOTS,
        history_logs=history_logs
    )

# ----------------- 3. WATER TRACKER -----------------
@trackers_bp.route('/water', methods=['GET', 'POST'])
@login_required
def water():
    user = g.current_user
    profile = user.profile
    target_date, program_day = parse_target_date(profile, request.args.get('date'), request.args.get('day'))
    
    goal_obj = WaterGoal.query.filter_by(participant_id=user.id).first()
    if not goal_obj:
        goal_obj = WaterGoal(participant_id=user.id, daily_goal_ml=3000)
        db.session.add(goal_obj)
        db.session.commit()
        
    if request.method == 'POST':
        action = request.form.get('action')
        
        # Add water intake entry
        if action == 'add_intake':
            amount_val = request.form.get('amount', '').strip()
            unit = request.form.get('unit', 'ml')  # 'ml', 'l', 'glass'
            notes = request.form.get('notes', '').strip()
            
            try:
                raw_amt = float(amount_val)
                if unit == 'l':
                    amount_ml = int(raw_amt * 1000)
                elif unit == 'glass':
                    amount_ml = int(raw_amt * 250)
                else:
                    amount_ml = int(raw_amt)
                    
                if amount_ml <= 0:
                    flash("Please enter an intake amount greater than zero.", "danger")
                else:
                    entry = WaterLog(
                        participant_id=user.id,
                        date=target_date,
                        amount_ml=amount_ml,
                        notes=notes if notes else f"+{amount_ml}ml",
                        logged_at=datetime.utcnow()
                    )
                    db.session.add(entry)
                    db.session.commit()
                    flash(f"Logged {amount_ml} ml of water!", "success")
            except ValueError:
                flash("Invalid amount entered. Please enter a valid number.", "danger")
                
            return redirect(url_for('trackers.water', date=target_date.strftime('%Y-%m-%d')))
            
        # Delete water entry
        elif action == 'delete_intake':
            entry_id = request.form.get('entry_id')
            entry = WaterLog.query.filter_by(id=entry_id, participant_id=user.id).first()
            if entry:
                db.session.delete(entry)
                db.session.commit()
                flash("Water entry deleted.", "info")
            return redirect(url_for('trackers.water', date=target_date.strftime('%Y-%m-%d')))
            
        # Update daily water goal
        elif action == 'update_goal':
            new_goal_ml = request.form.get('daily_goal_ml', '').strip()
            try:
                goal_val = int(new_goal_ml)
                if goal_val >= 500:
                    goal_obj.daily_goal_ml = goal_val
                    db.session.commit()
                    flash(f"Daily water goal updated to {goal_val} ml.", "success")
                else:
                    flash("Water goal should be at least 500 ml.", "warning")
            except ValueError:
                flash("Invalid goal value.", "danger")
            return redirect(url_for('trackers.water', date=target_date.strftime('%Y-%m-%d')))

    # Fetch entries for target date
    entries = WaterLog.query.filter_by(participant_id=user.id, date=target_date).order_by(WaterLog.logged_at.desc()).all()
    total_ml = sum(e.amount_ml for e in entries)
    goal_ml = goal_obj.daily_goal_ml
    remaining_ml = max(0, goal_ml - total_ml)
    pct_complete = min(100, int((total_ml / goal_ml) * 100)) if goal_ml > 0 else 0
    
    prev_date = target_date - timedelta(days=1)
    next_date = target_date + timedelta(days=1)

    return render_template(
        'trackers/water.html',
        user=user,
        profile=profile,
        target_date=target_date,
        program_day=program_day,
        prev_date=prev_date,
        next_date=next_date,
        entries=entries,
        total_ml=total_ml,
        goal_ml=goal_ml,
        remaining_ml=remaining_ml,
        pct_complete=pct_complete
    )

# ----------------- 4. MOVEMENT TRACKER -----------------
@trackers_bp.route('/movement', methods=['GET', 'POST'])
@login_required
def movement():
    user = g.current_user
    profile = user.profile
    target_date, program_day = parse_target_date(profile, request.args.get('date'), request.args.get('day'))
    
    entry = MovementEntry.query.filter_by(participant_id=user.id, date=target_date).first()
    
    if request.method == 'POST':
        steps_val = request.form.get('steps', '').strip()
        morning_activity = request.form.get('morning_activity', '').strip()
        morning_mins = request.form.get('morning_mins', '').strip()
        evening_activity = request.form.get('evening_activity', '').strip()
        evening_mins = request.form.get('evening_mins', '').strip()
        other_activity = request.form.get('other_activity', '').strip()
        other_mins = request.form.get('other_mins', '').strip()
        how_i_felt = request.form.get('how_i_felt', '').strip()
        
        if not entry:
            entry = MovementEntry(
                participant_id=user.id,
                date=target_date,
                program_day=program_day
            )
            db.session.add(entry)
            
        # Parse fields
        entry.steps = int(steps_val) if steps_val.isdigit() else None
        entry.morning_activity = morning_activity or None
        entry.morning_mins = int(morning_mins) if morning_mins.isdigit() else None
        entry.evening_activity = evening_activity or None
        entry.evening_mins = int(evening_mins) if evening_mins.isdigit() else None
        entry.other_activity = other_activity or None
        entry.other_mins = int(other_mins) if other_mins.isdigit() else None
        
        # Calculate Total active mins (formula: Morning mins + Evening mins + Other mins)
        entry.total_active_mins = entry.calculate_total_active_mins()
        entry.how_i_felt = how_i_felt or None
        
        db.session.commit()
        flash("Movement entry recorded successfully!", "success")
        return redirect(url_for('trackers.movement', date=target_date.strftime('%Y-%m-%d')))
        
    # Excel averages calculation across all 90 days:
    all_movement = MovementEntry.query.filter_by(participant_id=user.id).all()
    # Days filled = COUNT(D10:D99)
    valid_step_entries = [m.steps for m in all_movement if m.steps is not None]
    valid_mins_entries = [m.total_active_mins for m in all_movement if m.total_active_mins is not None]
    
    days_filled = len(valid_step_entries)
    avg_steps = round(sum(valid_step_entries) / len(valid_step_entries)) if valid_step_entries else 0
    avg_active_mins = round(sum(valid_mins_entries) / len(valid_mins_entries)) if valid_mins_entries else 0
    
    # 90-day history records list
    history_records = MovementEntry.query.filter_by(participant_id=user.id).order_by(MovementEntry.program_day.asc()).all()
    
    prev_date = target_date - timedelta(days=1)
    next_date = target_date + timedelta(days=1)

    return render_template(
        'trackers/movement.html',
        user=user,
        profile=profile,
        target_date=target_date,
        program_day=program_day,
        prev_date=prev_date,
        next_date=next_date,
        entry=entry,
        days_filled=days_filled,
        avg_steps=avg_steps,
        avg_active_mins=avg_active_mins,
        history_records=history_records
    )

# ----------------- 5. HABIT TRACKER -----------------
@trackers_bp.route('/habits', methods=['GET', 'POST'])
@login_required
def habits():
    user = g.current_user
    profile = user.profile
    
    # Week selection (1 to 12)
    selected_week = request.args.get('week', type=int)
    if not selected_week or not (1 <= selected_week <= 12):
        # Determine based on current program day
        p_day = profile.get_program_day()
        selected_week = max(1, min(12, ((p_day - 1) // 7) + 1)) if p_day >= 1 else 1

    habit_week = HabitWeek.query.filter_by(participant_id=user.id, week_number=selected_week).first()
    if not habit_week:
        w_start = profile.start_date + timedelta(days=(selected_week - 1) * 7)
        w_end = w_start + timedelta(days=6)
        habit_week = HabitWeek(
            participant_id=user.id,
            week_number=selected_week,
            date_range_label=f"{w_start.strftime('%b %d')} - {w_end.strftime('%b %d')}"
        )
        db.session.add(habit_week)
        db.session.commit()

    # Ensure 3 habit days exist for this week
    for s_idx in [1, 2, 3]:
        hd = HabitDay.query.filter_by(participant_id=user.id, week_number=selected_week, step_index=s_idx).first()
        if not hd:
            hd = HabitDay(participant_id=user.id, week_number=selected_week, step_index=s_idx)
            db.session.add(hd)
    db.session.commit()

    if request.method == 'POST':
        action = request.form.get('action')
        
        # Participant saving their Mon-Sun check ticks
        if action == 'save_ticks':
            for s_idx in [1, 2, 3]:
                hd = HabitDay.query.filter_by(participant_id=user.id, week_number=selected_week, step_index=s_idx).first()
                if hd:
                    hd.mon = request.form.get(f'step_{s_idx}_mon') == 'on'
                    hd.tue = request.form.get(f'step_{s_idx}_tue') == 'on'
                    hd.wed = request.form.get(f'step_{s_idx}_wed') == 'on'
                    hd.thu = request.form.get(f'step_{s_idx}_thu') == 'on'
                    hd.fri = request.form.get(f'step_{s_idx}_fri') == 'on'
                    hd.sat = request.form.get(f'step_{s_idx}_sat') == 'on'
                    hd.sun = request.form.get(f'step_{s_idx}_sun') == 'on'
            db.session.commit()
            flash(f"Week {selected_week} action step check-ins saved!", "success")
            return redirect(url_for('trackers.habits', week=selected_week))

    habit_days = HabitDay.query.filter_by(participant_id=user.id, week_number=selected_week).order_by(HabitDay.step_index.asc()).all()
    
    # Calculate Excel week score: SUM(J7:J9) and J10/21
    total_days_done = sum(hd.days_done for hd in habit_days)
    week_score_pct = round((total_days_done / 21.0) * 100, 1)

    # All 12 weeks overview
    all_weeks_summary = []
    for w in range(1, 13):
        w_days = HabitDay.query.filter_by(participant_id=user.id, week_number=w).all()
        w_done = sum(d.days_done for d in w_days)
        w_pct = round((w_done / 21.0) * 100, 1) if w_days else 0
        all_weeks_summary.append({
            'week': w,
            'days_done': w_done,
            'pct': w_pct
        })

    return render_template(
        'trackers/habits.html',
        user=user,
        profile=profile,
        selected_week=selected_week,
        habit_week=habit_week,
        habit_days=habit_days,
        total_days_done=total_days_done,
        week_score_pct=week_score_pct,
        all_weeks_summary=all_weeks_summary
    )

# ----------------- 6. MEASUREMENTS TRACKER -----------------
@trackers_bp.route('/measurements', methods=['GET', 'POST'])
@login_required
def measurements():
    user = g.current_user
    profile = user.profile
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'save_entry':
            week_number = request.form.get('week_number', type=int)
            date_str = request.form.get('date', '').strip()
            weight = request.form.get('weight_kg', '').strip()
            waist = request.form.get('waist_cm', '').strip()
            hips = request.form.get('hips_cm', '').strip()
            chest = request.form.get('chest_cm', '').strip()
            upper_arm = request.form.get('upper_arm_cm', '').strip()
            thigh = request.form.get('thigh_cm', '').strip()
            notes = request.form.get('notes', '').strip()
            
            entry = Measurement.query.filter_by(participant_id=user.id, week_number=week_number).first()
            if not entry:
                entry = Measurement(
                    participant_id=user.id,
                    week_number=week_number,
                    week_label="Start (day 1)" if week_number == 0 else f"Week {week_number}"
                )
                db.session.add(entry)
                
            try:
                entry.date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else None
            except Exception:
                pass
                
            entry.weight_kg = float(weight) if weight else None
            entry.waist_cm = float(waist) if waist else None
            entry.hips_cm = float(hips) if hips else None
            entry.chest_cm = float(chest) if chest else None
            entry.upper_arm_cm = float(upper_arm) if upper_arm else None
            entry.thigh_cm = float(thigh) if thigh else None
            entry.notes = notes or None
            
            db.session.commit()
            flash(f"Measurements for {entry.week_label} saved successfully!", "success")
            return redirect(url_for('trackers.measurements'))

    # Fetch all measurements 0 to 12
    records = Measurement.query.filter_by(participant_id=user.id).order_by(Measurement.week_number.asc()).all()
    
    # Calculate Change so far: Latest minus Start (LOOKUP(9.99E+307, range) - Start)
    start_rec = next((r for r in records if r.week_number == 0), None)
    
    # Latest valid record
    latest_rec = None
    for r in reversed(records):
        if r.week_number > 0 and any([r.weight_kg, r.waist_cm, r.hips_cm, r.chest_cm, r.upper_arm_cm, r.thigh_cm]):
            latest_rec = r
            break
            
    changes = {}
    for col in ['weight_kg', 'waist_cm', 'hips_cm', 'chest_cm', 'upper_arm_cm', 'thigh_cm']:
        if start_rec and latest_rec:
            s_val = getattr(start_rec, col)
            l_val = getattr(latest_rec, col)
            if s_val is not None and l_val is not None:
                changes[col] = round(l_val - s_val, 1)
            else:
                changes[col] = None
        else:
            changes[col] = None

    # Chart datasets
    chart_labels = []
    chart_weights = []
    chart_waists = []
    for r in records:
        if r.weight_kg is not None or r.waist_cm is not None:
            chart_labels.append(r.week_label)
            chart_weights.append(r.weight_kg if r.weight_kg is not None else None)
            chart_waists.append(r.waist_cm if r.waist_cm is not None else None)

    return render_template(
        'trackers/measurements.html',
        user=user,
        profile=profile,
        records=records,
        start_rec=start_rec,
        latest_rec=latest_rec,
        changes=changes,
        chart_labels=chart_labels,
        chart_weights=chart_weights,
        chart_waists=chart_waists
    )

# ----------------- 7. BLOOD REPORTS TRACKER -----------------
@trackers_bp.route('/reports', methods=['GET', 'POST'])
@login_required
def reports():
    user = g.current_user
    profile = user.profile
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        # Update existing test result
        if action == 'save_test':
            report_id = request.form.get('report_id', type=int)
            test_report = BloodReport.query.filter_by(id=report_id, participant_id=user.id).first()
            if test_report:
                b_date = request.form.get('before_date', '').strip()
                b_res = request.form.get('before_result', '').strip()
                d_date = request.form.get('day90_date', '').strip()
                d_res = request.form.get('day90_result', '').strip()
                ideal = request.form.get('ideal_range', '').strip()
                notes = request.form.get('notes', '').strip()
                
                try:
                    test_report.before_date = datetime.strptime(b_date, '%Y-%m-%d').date() if b_date else None
                except Exception:
                    pass
                try:
                    test_report.day90_date = datetime.strptime(d_date, '%Y-%m-%d').date() if d_date else None
                except Exception:
                    pass
                    
                test_report.before_result = b_res or None
                test_report.day90_result = d_res or None
                test_report.ideal_range = ideal or None
                test_report.notes = notes or None
                
                # Check optional file upload for this test
                if 'report_file' in request.files:
                    f = request.files['report_file']
                    if f and f.filename and allowed_file(f.filename, current_app.config['ALLOWED_REPORT_EXTENSIONS']):
                        if test_report.report_file_path:
                            delete_uploaded_file(test_report.report_file_path)
                        path = save_uploaded_file(f, 'reports', current_app.config['ALLOWED_REPORT_EXTENSIONS'], optimize_image=False)
                        test_report.report_file_path = path
                        
                db.session.commit()
                flash(f"Updated results for {test_report.test_name}.", "success")
                return redirect(url_for('trackers.reports'))
                
        # Add custom lab test
        elif action == 'add_custom_test':
            test_name = request.form.get('test_name', '').strip()
            if not test_name:
                flash("Test name cannot be blank.", "danger")
            else:
                custom_test = BloodReport(
                    participant_id=user.id,
                    test_name=test_name,
                    is_custom=True
                )
                db.session.add(custom_test)
                db.session.commit()
                flash(f"Custom test '{test_name}' added.", "success")
            return redirect(url_for('trackers.reports'))

    # Fetch all test reports
    standard_reports = BloodReport.query.filter_by(participant_id=user.id, is_custom=False).order_by(BloodReport.id.asc()).all()
    custom_reports = BloodReport.query.filter_by(participant_id=user.id, is_custom=True).order_by(BloodReport.id.asc()).all()

    return render_template(
        'trackers/reports.html',
        user=user,
        profile=profile,
        standard_reports=standard_reports,
        custom_reports=custom_reports
    )

# ----------------- 8. WEEKLY SCORE TRACKER -----------------
@trackers_bp.route('/weekly-scores', methods=['GET', 'POST'])
@login_required
def weekly_scores():
    user = g.current_user
    profile = user.profile
    
    if request.method == 'POST':
        week_num = request.form.get('week_number', type=int)
        energy = request.form.get('energy', '').strip()
        sleep = request.form.get('sleep', '').strip()
        digestion = request.form.get('digestion', '').strip()
        mood = request.form.get('mood', '').strip()
        cravings = request.form.get('cravings', '').strip()
        notes = request.form.get('notes', '').strip()
        
        ws = WeeklyScore.query.filter_by(participant_id=user.id, week_number=week_num).first()
        if not ws:
            ws = WeeklyScore(participant_id=user.id, week_number=week_num)
            db.session.add(ws)
            
        def clean_score(val):
            if val and val.isdigit():
                num = int(val)
                if 1 <= num <= 10:
                    return num
            return None
            
        ws.energy = clean_score(energy)
        ws.sleep = clean_score(sleep)
        ws.digestion = clean_score(digestion)
        ws.mood = clean_score(mood)
        ws.cravings = clean_score(cravings)
        ws.notes = notes or None
        
        # Excel formula: ROUND(AVERAGE(C6:G6), 1)
        ws.week_average = ws.calculate_average()
        
        db.session.commit()
        flash(f"Week {week_num} score saved! Average: {ws.week_average if ws.week_average else 'Incomplete'}", "success")
        return redirect(url_for('trackers.weekly_scores'))

    scores = WeeklyScore.query.filter_by(participant_id=user.id).order_by(WeeklyScore.week_number.asc()).all()
    
    # Calculate Change, week 1 to latest (Excel formula: IFERROR(IF(COUNT(H6:H17)<2,"",LOOKUP(9.99E+307,H6:H17)-H6),""))
    week_1 = next((s for s in scores if s.week_number == 1 and s.week_average is not None), None)
    latest_score = None
    for s in reversed(scores):
        if s.week_average is not None:
            latest_score = s
            break
            
    change_score = None
    if week_1 and latest_score and latest_score.week_number > 1:
        change_score = round(latest_score.week_average - week_1.week_average, 1)

    # Chart data
    chart_weeks = [f"Week {s.week_number}" for s in scores]
    chart_averages = [s.week_average for s in scores]
    chart_energy = [s.energy for s in scores]
    chart_sleep = [s.sleep for s in scores]
    chart_digestion = [s.digestion for s in scores]
    chart_mood = [s.mood for s in scores]
    chart_cravings = [s.cravings for s in scores]

    return render_template(
        'trackers/weekly_scores.html',
        user=user,
        profile=profile,
        scores=scores,
        change_score=change_score,
        latest_score=latest_score,
        chart_weeks=chart_weeks,
        chart_averages=chart_averages,
        chart_energy=chart_energy,
        chart_sleep=chart_sleep,
        chart_digestion=chart_digestion,
        chart_mood=chart_mood,
        chart_cravings=chart_cravings
    )
