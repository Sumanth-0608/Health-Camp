import io
import csv
from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, g, make_response, abort
from ..models import (
    db, User, ParticipantProfile, Coach, DailyLog, Meal, WaterLog, 
    MovementEntry, HabitWeek, HabitDay, Measurement, BloodReport, 
    WeeklyScore, SupportConversation, SupportMessage
)
from ..auth import admin_required

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/')
@admin_required
def dashboard():
    today = date.today()
    
    # Participant counts
    total_participants = User.query.filter_by(role='participant').count()
    active_participants = User.query.filter_by(role='participant', is_active=True).count()
    
    # Recent registrations (last 10)
    recent_users = User.query.filter_by(role='participant').order_by(User.created_at.desc()).limit(10).all()
    
    # Pending help queries
    pending_support = SupportConversation.query.filter(SupportConversation.status.in_(['Open'])).count()
    
    # Participants by program day grouping
    all_profiles = ParticipantProfile.query.all()
    day_brackets = {
        'Day 1-30': 0,
        'Day 31-60': 0,
        'Day 61-90': 0,
        'Day 90+': 0
    }
    
    participants_summary = []
    for p in all_profiles:
        p_day = p.get_program_day(today)
        if 1 <= p_day <= 30:
            day_brackets['Day 1-30'] += 1
        elif 31 <= p_day <= 60:
            day_brackets['Day 31-60'] += 1
        elif 61 <= p_day <= 90:
            day_brackets['Day 61-90'] += 1
        else:
            day_brackets['Day 90+'] += 1
            
        # Check today's completion
        meals_today = Meal.query.filter_by(participant_id=p.user_id, date=today).count()
        movement_today = MovementEntry.query.filter_by(participant_id=p.user_id, date=today).first()
        water_today = WaterLog.query.filter_by(participant_id=p.user_id, date=today).count()
        
        has_today_entry = (meals_today > 0) or (movement_today is not None) or (water_today > 0)
        
        participants_summary.append({
            'user': p.user,
            'profile': p,
            'program_day': p_day,
            'has_today_entry': has_today_entry,
            'meals_today': meals_today
        })

    incomplete_today_count = sum(1 for item in participants_summary if not item['has_today_entry'])

    return render_template(
        'admin/dashboard.html',
        total_participants=total_participants,
        active_participants=active_participants,
        recent_users=recent_users,
        pending_support=pending_support,
        day_brackets=day_brackets,
        participants_summary=participants_summary,
        incomplete_today_count=incomplete_today_count,
        today=today
    )

@admin_bp.route('/participants')
@admin_required
def participants():
    search = request.args.get('search', '').strip()
    coach_filter = request.args.get('coach', '').strip()
    status_filter = request.args.get('status', '').strip()
    
    query = User.query.filter_by(role='participant')
    
    if search:
        query = query.filter(
            (User.full_name.ilike(f"%{search}%")) |
            (User.email.ilike(f"%{search}%")) |
            (User.mobile.ilike(f"%{search}%"))
        )
        
    users = query.order_by(User.created_at.desc()).all()
    coaches = Coach.query.filter_by(is_active=True).all()
    
    # Filter in memory if coach_filter or status_filter
    filtered_users = []
    for u in users:
        if not u.profile:
            continue
        if coach_filter and coach_filter != 'all':
            if u.profile.coach_name != coach_filter:
                continue
        if status_filter == 'active' and not u.is_active:
            continue
        if status_filter == 'inactive' and u.is_active:
            continue
        filtered_users.append(u)

    return render_template(
        'admin/participants.html',
        participants=filtered_users,
        coaches=coaches,
        search=search,
        coach_filter=coach_filter,
        status_filter=status_filter
    )

@admin_bp.route('/participants/<int:user_id>')
@admin_required
def participant_detail(user_id):
    participant = User.query.filter_by(id=user_id, role='participant').first_or_404()
    profile = participant.profile
    coaches = Coach.query.filter_by(is_active=True).all()
    today = date.today()
    program_day = profile.get_program_day(today) if profile else 0
    
    # Load all participant records
    daily_logs = DailyLog.query.filter_by(participant_id=user_id).order_by(DailyLog.date.desc()).all()
    meals = Meal.query.filter_by(participant_id=user_id).order_by(Meal.date.desc()).all()
    water_logs = WaterLog.query.filter_by(participant_id=user_id).order_by(WaterLog.logged_at.desc()).limit(50).all()
    
    movement_entries = MovementEntry.query.filter_by(participant_id=user_id).order_by(MovementEntry.program_day.desc()).all()
    valid_steps = [m.steps for m in movement_entries if m.steps is not None]
    valid_mins = [m.total_active_mins for m in movement_entries if m.total_active_mins is not None]
    avg_steps = round(sum(valid_steps) / len(valid_steps)) if valid_steps else 0
    avg_mins = round(sum(valid_mins) / len(valid_mins)) if valid_mins else 0
    
    measurements = Measurement.query.filter_by(participant_id=user_id).order_by(Measurement.week_number.asc()).all()
    blood_reports = BloodReport.query.filter_by(participant_id=user_id).order_by(BloodReport.id.asc()).all()
    weekly_scores = WeeklyScore.query.filter_by(participant_id=user_id).order_by(WeeklyScore.week_number.asc()).all()
    
    habit_weeks = HabitWeek.query.filter_by(participant_id=user_id).order_by(HabitWeek.week_number.asc()).all()
    habit_days = HabitDay.query.filter_by(participant_id=user_id).all()
    
    support_convos = SupportConversation.query.filter_by(participant_id=user_id).order_by(SupportConversation.last_message_at.desc()).all()

    return render_template(
        'admin/participant_detail.html',
        participant=participant,
        profile=profile,
        coaches=coaches,
        program_day=program_day,
        daily_logs=daily_logs,
        meals=meals,
        water_logs=water_logs,
        movement_entries=movement_entries,
        avg_steps=avg_steps,
        avg_mins=avg_mins,
        measurements=measurements,
        blood_reports=blood_reports,
        weekly_scores=weekly_scores,
        habit_weeks=habit_weeks,
        habit_days=habit_days,
        support_convos=support_convos
    )

@admin_bp.route('/participants/<int:user_id>/update-coach', methods=['POST'])
@admin_required
def update_coach(user_id):
    participant = User.query.filter_by(id=user_id, role='participant').first_or_404()
    coach_id = request.form.get('coach_id')
    coach = db.session.get(Coach, int(coach_id)) if coach_id and coach_id.isdigit() else None
    if coach and participant.profile:
        participant.profile.coach_id = coach.id
        participant.profile.coach_name = coach.name
        db.session.commit()
        flash(f"Assigned coach {coach.name} to {participant.full_name}.", "success")
    else:
        flash("Could not assign coach.", "danger")
    return redirect(url_for('admin.participant_detail', user_id=user_id))

@admin_bp.route('/participants/<int:user_id>/habits-config', methods=['GET', 'POST'])
@admin_required
def habits_config(user_id):
    participant = User.query.filter_by(id=user_id, role='participant').first_or_404()
    profile = participant.profile
    week_num = request.args.get('week', 1, type=int)
    
    habit_week = HabitWeek.query.filter_by(participant_id=user_id, week_number=week_num).first()
    
    if request.method == 'POST':
        step_1 = request.form.get('step_1', '').strip()
        step_2 = request.form.get('step_2', '').strip()
        step_3 = request.form.get('step_3', '').strip()
        date_label = request.form.get('date_range_label', '').strip()
        
        if not habit_week:
            habit_week = HabitWeek(
                participant_id=user_id,
                week_number=week_num
            )
            db.session.add(habit_week)
            
        habit_week.step_1 = step_1 or habit_week.step_1
        habit_week.step_2 = step_2 or habit_week.step_2
        habit_week.step_3 = step_3 or habit_week.step_3
        habit_week.date_range_label = date_label or habit_week.date_range_label
        
        db.session.commit()
        flash(f"Updated action steps for Week {week_num} for {participant.full_name}.", "success")
        return redirect(url_for('admin.habits_config', user_id=user_id, week=week_num))

    return render_template(
        'admin/habits_config.html',
        participant=participant,
        profile=profile,
        week_num=week_num,
        habit_week=habit_week
    )

# ----------------- ADMIN SUPPORT INBOX -----------------
@admin_bp.route('/support-inbox')
@admin_required
def support_inbox():
    status_filter = request.args.get('status', 'all')
    
    query = SupportConversation.query
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
        
    conversations = query.order_by(SupportConversation.last_message_at.desc()).all()
    open_count = SupportConversation.query.filter_by(status='Open').count()
    replied_count = SupportConversation.query.filter_by(status='Replied').count()
    resolved_count = SupportConversation.query.filter_by(status='Resolved').count()

    return render_template(
        'admin/support_inbox.html',
        conversations=conversations,
        status_filter=status_filter,
        open_count=open_count,
        replied_count=replied_count,
        resolved_count=resolved_count
    )

@admin_bp.route('/support-inbox/<int:convo_id>/status', methods=['POST'])
@admin_required
def update_support_status(convo_id):
    convo = SupportConversation.query.get_or_404(convo_id)
    new_status = request.form.get('status')
    if new_status in {'Open', 'Replied', 'Resolved'}:
        convo.status = new_status
        db.session.commit()
        flash(f"Support ticket status updated to {new_status}.", "success")
    return redirect(request.referrer or url_for('admin.support_inbox'))

# ----------------- CSV EXPORT -----------------
@admin_bp.route('/export/participants.csv')
@admin_required
def export_participants():
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow([
        'Participant ID', 'Full Name', 'Email', 'Mobile', 'Coach Name', 
        'Start Date', 'Goal (90 Day)', 'Why', 'Session Schedule', 
        'Root Cause 1', 'Root Cause 2', 'Registered Date'
    ])
    
    users = User.query.filter_by(role='participant').all()
    for u in users:
        p = u.profile
        writer.writerow([
            u.id,
            u.full_name,
            u.email,
            u.mobile,
            p.coach_name if p else '',
            p.start_date.strftime('%Y-%m-%d') if p and p.start_date else '',
            p.goal_90_day if p else '',
            p.reason_why if p else '',
            p.session_day_time if p else '',
            p.root_cause_1 if p else '',
            p.root_cause_2 if p else '',
            u.created_at.strftime('%Y-%m-%d %H:%M:%S')
        ])
        
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = f"attachment; filename=wellness_participants_{date.today()}.csv"
    response.headers['Content-Type'] = 'text/csv'
    return response

@admin_bp.route('/export/participant/<int:user_id>/movement.csv')
@admin_required
def export_participant_movement(user_id):
    participant = User.query.get_or_404(user_id)
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['Day', 'Date', 'Steps', 'Morning Activity', 'Morning Mins', 'Evening Activity', 'Evening Mins', 'Other Activity', 'Other Mins', 'Total Active Mins', 'How I Felt'])
    
    entries = MovementEntry.query.filter_by(participant_id=user_id).order_by(MovementEntry.program_day.asc()).all()
    for e in entries:
        writer.writerow([
            e.program_day,
            e.date.strftime('%Y-%m-%d'),
            e.steps or '',
            e.morning_activity or '',
            e.morning_mins or '',
            e.evening_activity or '',
            e.evening_mins or '',
            e.other_activity or '',
            e.other_mins or '',
            e.total_active_mins or '',
            e.how_i_felt or ''
        ])
        
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = f"attachment; filename={participant.full_name.replace(' ', '_')}_movement_{date.today()}.csv"
    response.headers['Content-Type'] = 'text/csv'
    return response
