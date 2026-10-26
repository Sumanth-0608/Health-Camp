from datetime import datetime, date, timezone
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

def utc_now():
    return datetime.now(timezone.utc)


class Coach(db.Model):
    __tablename__ = 'coaches'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    specialty = db.Column(db.String(200), default="Holistic Wellness & Habit Coaching")
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utc_now)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'specialty': self.specialty
        }

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='participant', nullable=False)  # 'participant' or 'admin'
    full_name = db.Column(db.String(120), nullable=False)
    mobile = db.Column(db.String(30), nullable=False)
    profile_photo = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    
    # Relationships
    profile = db.relationship('ParticipantProfile', backref='user', uselist=False, cascade='all, delete-orphan')
    water_logs = db.relationship('WaterLog', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    water_goal = db.relationship('WaterGoal', backref='user', uselist=False, cascade='all, delete-orphan')
    daily_logs = db.relationship('DailyLog', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    meals = db.relationship('Meal', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    movement_entries = db.relationship('MovementEntry', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    habit_weeks = db.relationship('HabitWeek', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    habit_days = db.relationship('HabitDay', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    measurements = db.relationship('Measurement', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    blood_reports = db.relationship('BloodReport', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    weekly_scores = db.relationship('WeeklyScore', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    support_conversations = db.relationship('SupportConversation', backref='participant', lazy='dynamic', cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == 'admin'

class ParticipantProfile(db.Model):
    __tablename__ = 'participant_profiles'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False)
    coach_id = db.Column(db.Integer, db.ForeignKey('coaches.id', ondelete='SET NULL'), nullable=True)
    coach_name = db.Column(db.String(100), nullable=True)
    start_date = db.Column(db.Date, nullable=False, default=date.today)
    goal_90_day = db.Column(db.Text, nullable=True)
    reason_why = db.Column(db.Text, nullable=True)
    session_day_time = db.Column(db.String(100), nullable=True)
    root_cause_1 = db.Column(db.String(255), nullable=True)
    root_cause_2 = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    
    coach = db.relationship('Coach', backref='assigned_participants')

    def get_program_day(self, target_date=None):
        if not target_date:
            target_date = date.today()
        elif isinstance(target_date, str):
            target_date = datetime.strptime(target_date, '%Y-%m-%d').date()
            
        diff = (target_date - self.start_date).days
        day_num = diff + 1
        return day_num

    def get_days_completed(self):
        # Program days passed up to today, capped at 90
        curr_day = self.get_program_day()
        if curr_day < 1:
            return 0
        return min(curr_day, 90)

    def get_days_remaining(self):
        completed = self.get_days_completed()
        return max(0, 90 - completed)

class DailyLog(db.Model):
    __tablename__ = 'daily_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    program_day = db.Column(db.Integer, nullable=False)
    water_glasses = db.Column(db.Integer, default=0)
    craving_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    
    __table_args__ = (
        db.UniqueConstraint('participant_id', 'date', name='uq_participant_daily_date'),
    )

class Meal(db.Model):
    __tablename__ = 'meals'
    
    MEAL_SLOTS = [
        ('early_morning', 'Early Morning'),
        ('breakfast', 'Breakfast'),
        ('mid_morning', 'Mid-morning'),
        ('lunch', 'Lunch'),
        ('evening_snack', 'Evening snack'),
        ('dinner', 'Dinner'),
        ('after_dinner', 'After dinner')
    ]
    
    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    daily_log_id = db.Column(db.Integer, db.ForeignKey('daily_logs.id', ondelete='SET NULL'), nullable=True)
    date = db.Column(db.Date, nullable=False, index=True)
    meal_slot = db.Column(db.String(30), nullable=False)
    meal_time = db.Column(db.String(20), nullable=True)
    food_description = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    photo_path = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    
    __table_args__ = (
        db.UniqueConstraint('participant_id', 'date', 'meal_slot', name='uq_participant_date_meal_slot'),
    )

class WaterGoal(db.Model):
    __tablename__ = 'water_goals'
    
    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False)
    daily_goal_ml = db.Column(db.Integer, default=3000, nullable=False)  # 3000 ml default
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

class WaterLog(db.Model):
    __tablename__ = 'water_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    amount_ml = db.Column(db.Integer, nullable=False)
    logged_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    notes = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now)

class MovementEntry(db.Model):
    __tablename__ = 'movement_entries'
    
    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    daily_log_id = db.Column(db.Integer, db.ForeignKey('daily_logs.id', ondelete='SET NULL'), nullable=True)
    date = db.Column(db.Date, nullable=False, index=True)
    program_day = db.Column(db.Integer, nullable=False)
    steps = db.Column(db.Integer, nullable=True)
    morning_activity = db.Column(db.String(200), nullable=True)
    morning_mins = db.Column(db.Integer, nullable=True)
    evening_activity = db.Column(db.String(200), nullable=True)
    evening_mins = db.Column(db.Integer, nullable=True)
    other_activity = db.Column(db.String(255), nullable=True)
    other_mins = db.Column(db.Integer, nullable=True)
    total_active_mins = db.Column(db.Integer, nullable=True)
    how_i_felt = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    
    __table_args__ = (
        db.UniqueConstraint('participant_id', 'date', name='uq_participant_movement_date'),
    )

    def calculate_total_active_mins(self):
        parts = [self.morning_mins, self.evening_mins, self.other_mins]
        valid_parts = [p for p in parts if p is not None]
        if not valid_parts:
            return None
        return sum(valid_parts)

class HabitWeek(db.Model):
    __tablename__ = 'habit_weeks'
    
    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    week_number = db.Column(db.Integer, nullable=False)  # 1 to 12
    date_range_label = db.Column(db.String(100), nullable=True)
    step_1 = db.Column(db.String(255), default="Drink 3L water throughout the day")
    step_2 = db.Column(db.String(255), default="30 minutes brisk morning walk")
    step_3 = db.Column(db.String(255), default="No screen time 30 mins before sleep")
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    
    __table_args__ = (
        db.UniqueConstraint('participant_id', 'week_number', name='uq_participant_habit_week'),
    )

class HabitDay(db.Model):
    __tablename__ = 'habit_days'
    
    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    week_number = db.Column(db.Integer, nullable=False)  # 1 to 12
    step_index = db.Column(db.Integer, nullable=False)   # 1, 2, or 3
    mon = db.Column(db.Boolean, default=False)
    tue = db.Column(db.Boolean, default=False)
    wed = db.Column(db.Boolean, default=False)
    thu = db.Column(db.Boolean, default=False)
    fri = db.Column(db.Boolean, default=False)
    sat = db.Column(db.Boolean, default=False)
    sun = db.Column(db.Boolean, default=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    
    __table_args__ = (
        db.UniqueConstraint('participant_id', 'week_number', 'step_index', name='uq_participant_habit_day'),
    )

    @property
    def days_done(self):
        return sum([1 for d in [self.mon, self.tue, self.wed, self.thu, self.fri, self.sat, self.sun] if d])

    @property
    def percent_done(self):
        return round((self.days_done / 7.0) * 100, 1)

class Measurement(db.Model):
    __tablename__ = 'measurements'
    
    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    week_number = db.Column(db.Integer, nullable=False)  # 0 for Start (Day 1), 1 to 12
    week_label = db.Column(db.String(50), nullable=False)
    date = db.Column(db.Date, nullable=True)
    weight_kg = db.Column(db.Float, nullable=True)
    waist_cm = db.Column(db.Float, nullable=True)
    hips_cm = db.Column(db.Float, nullable=True)
    chest_cm = db.Column(db.Float, nullable=True)
    upper_arm_cm = db.Column(db.Float, nullable=True)
    thigh_cm = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    
    __table_args__ = (
        db.UniqueConstraint('participant_id', 'week_number', name='uq_participant_measurement_week'),
    )

class BloodReport(db.Model):
    __tablename__ = 'blood_reports'
    
    STANDARD_TESTS = [
        "Vitamin D",
        "Vitamin B12",
        "Fasting blood sugar",
        "HbA1c",
        "Haemoglobin",
        "Thyroid - TSH",
        "Total cholesterol",
        "Triglycerides",
        "HDL",
        "LDL",
        "SGPT / ALT",
        "Serum creatinine",
        "Uric acid",
        "Ferritin / iron",
        "Insulin (fasting)"
    ]
    
    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    test_name = db.Column(db.String(150), nullable=False)
    is_custom = db.Column(db.Boolean, default=False)
    before_date = db.Column(db.Date, nullable=True)
    before_result = db.Column(db.String(100), nullable=True)
    day90_date = db.Column(db.Date, nullable=True)
    day90_result = db.Column(db.String(100), nullable=True)
    ideal_range = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    report_file_path = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

class WeeklyScore(db.Model):
    __tablename__ = 'weekly_scores'
    
    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    week_number = db.Column(db.Integer, nullable=False)  # 1 to 12
    energy = db.Column(db.Integer, nullable=True)        # 1-10
    sleep = db.Column(db.Integer, nullable=True)         # 1-10
    digestion = db.Column(db.Integer, nullable=True)     # 1-10
    mood = db.Column(db.Integer, nullable=True)          # 1-10
    cravings = db.Column(db.Integer, nullable=True)      # 1-10
    week_average = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    
    __table_args__ = (
        db.UniqueConstraint('participant_id', 'week_number', name='uq_participant_weekly_score'),
    )

    def calculate_average(self):
        scores = [self.energy, self.sleep, self.digestion, self.mood, self.cravings]
        valid_scores = [s for s in scores if s is not None and 1 <= s <= 10]
        if not valid_scores:
            return None
        return round(sum(valid_scores) / len(valid_scores), 1)

class SupportConversation(db.Model):
    __tablename__ = 'support_conversations'
    
    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    subject = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(30), default='Open', nullable=False)  # 'Open', 'Replied', 'Resolved'
    last_message_at = db.Column(db.DateTime, default=utc_now)
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    
    messages = db.relationship('SupportMessage', backref='conversation', lazy='dynamic', cascade='all, delete-orphan', order_by='SupportMessage.created_at.asc()')

class SupportMessage(db.Model):
    __tablename__ = 'support_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('support_conversations.id', ondelete='CASCADE'), nullable=False, index=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_admin_reply = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=utc_now)
    
    sender = db.relationship('User', foreign_keys=[sender_id])
