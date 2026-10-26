import argparse
from getpass import getpass
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
        raise ValueError("A user with this email already exists; no account was changed.")

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
    print("-> Administrator account created.")

def main():
    parser = argparse.ArgumentParser(description="Initialize 90-Day Wellness Tracker Database")
    parser.add_argument('--create-admin', action='store_true', help="Interactively create an administrator account")
    parser.add_argument('--admin-email', help="Email for the new administrator")
    
    args = parser.parse_args()

    admin_details = None
    if args.create_admin:
        if not args.admin_email:
            parser.error("--admin-email is required with --create-admin.")
        full_name = input("Administrator name: ").strip()
        mobile = input("Administrator mobile: ").strip()
        password = getpass("Administrator password: ")
        confirmation = getpass("Confirm administrator password: ")
        if not full_name or not mobile or not password:
            parser.error("Administrator name, mobile, and password must not be empty.")
        if password != confirmation:
            parser.error("Administrator passwords do not match.")
        admin_details = (args.admin_email, password, full_name, mobile)

    with app.app_context():
        print("Creating any missing database tables...")
        db.create_all()
        print("Seeding default wellness coaches...")
        seed_coaches()
        
        if admin_details:
            create_admin(*admin_details)
            
        print("\nDatabase initialization complete! Database is ready.")

if __name__ == '__main__':
    main()
