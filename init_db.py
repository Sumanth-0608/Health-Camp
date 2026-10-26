import sys
import argparse
from app import create_app
from app.models import db, User, Coach

app = create_app()

def seed_coaches():
    coaches_data = [
        {
            "name": "Sarah Jenkins",
            "email": "sarah.coach@90daywellness.com",
            "specialty": "Nutrition Patterns, Habits & Lifestyle Architecture"
        },
        {
            "name": "Dr. Michael Chen",
            "email": "chen.coach@90daywellness.com",
            "specialty": "Movement, Functional Strength & Metabolic Health"
        },
        {
            "name": "Priya Sharma",
            "email": "priya.coach@90daywellness.com",
            "specialty": "Stress Reduction, Circadian Sleep & Craving Control"
        },
        {
            "name": "David Miller",
            "email": "david.coach@90daywellness.com",
            "specialty": "Cardiorespiratory Fitness & Endurance Transformation"
        }
    ]
    
    for c_data in coaches_data:
        existing = Coach.query.filter_by(email=c_data["email"]).first()
        if not existing:
            coach = Coach(
                name=c_data["name"],
                email=c_data["email"],
                specialty=c_data["specialty"],
                is_active=True
            )
            db.session.add(coach)
            print(f"-> Created coach: {c_data['name']}")
    db.session.commit()

def create_admin(email, password, full_name, mobile):
    existing = User.query.filter_by(email=email).first()
    if existing:
        existing.role = 'admin'
        existing.set_password(password)
        existing.full_name = full_name
        existing.mobile = mobile
        existing.is_active = True
        db.session.commit()
        print(f"-> Updated existing user '{email}' to administrator role.")
    else:
        admin = User(
            email=email,
            full_name=full_name,
            mobile=mobile,
            role='admin',
            is_active=True
        )
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        print(f"-> Successfully created administrator account: {email}")

def main():
    parser = argparse.ArgumentParser(description="Initialize 90-Day Wellness Tracker Database")
    parser.add_argument('--create-admin', action='store_true', help="Create default admin account")
    parser.add_argument('--admin-email', default="admin@90daywellness.com", help="Admin email")
    parser.add_argument('--admin-password', default="AdminWellness@2026", help="Admin password")
    parser.add_argument('--admin-name', default="Lead Program Director", help="Admin name")
    parser.add_argument('--admin-mobile', default="+1 (555) 019-2831", help="Admin mobile")
    
    args = parser.parse_args()

    with app.app_context():
        print("Creating all database tables...")
        db.create_all()
        print("Seeding default wellness coaches...")
        seed_coaches()
        
        # Always create default admin if requested or if no admin exists
        admin_count = User.query.filter_by(role='admin').count()
        if args.create_admin or admin_count == 0:
            create_admin(args.admin_email, args.admin_password, args.admin_name, args.admin_mobile)
            
        print("\nDatabase initialization complete! Database is ready.")

if __name__ == '__main__':
    main()
