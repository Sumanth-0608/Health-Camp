import argparse
from getpass import getpass
from app import create_app
from app.models import (
    db, User, Coach, ParticipantProfile,
    PRIMARY_COACH_NAME, PRIMARY_COACH_SPECIALTY, PRIMARY_COACH_EMAIL
)
NUTRILIFE_ADMIN_USERNAME = "drgirijasnutrilife.com"

def seed_coaches():
    coaches = Coach.query.order_by(Coach.id).all()
    primary_coach = next(
        (coach for coach in coaches if coach.name == PRIMARY_COACH_NAME),
        None
    )
    if not primary_coach:
        primary_coach = Coach.query.filter_by(email=PRIMARY_COACH_EMAIL).first()
    if not primary_coach:
        primary_coach = Coach(
            name=PRIMARY_COACH_NAME,
            email=PRIMARY_COACH_EMAIL,
            specialty=PRIMARY_COACH_SPECIALTY,
            is_active=True
        )
        db.session.add(primary_coach)
        db.session.flush()

    retired_coach_names = {
        coach.name for coach in coaches if coach.id != primary_coach.id
    }
    for profile in ParticipantProfile.query.all():
        if profile.coach_id is not None or profile.coach_name in retired_coach_names:
            profile.coach_id = primary_coach.id
            profile.coach_name = PRIMARY_COACH_NAME

    for coach in coaches:
        coach.is_active = coach.id == primary_coach.id

    primary_coach.name = PRIMARY_COACH_NAME
    primary_coach.specialty = PRIMARY_COACH_SPECIALTY
    primary_coach.is_active = True
    db.session.commit()
    print(f"-> Ensured active coach: {PRIMARY_COACH_NAME}")

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


def configure_nutrilife_admin(password, full_name=None, mobile=None):
    if not password:
        raise ValueError("Administrator password must not be empty.")

    admin = User.query.filter_by(email=NUTRILIFE_ADMIN_USERNAME).first()
    if admin and not admin.is_admin:
        raise ValueError(
            "The NutriLife admin username belongs to a non-admin account; "
            "no account was changed."
        )

    if admin:
        admin.set_password(password)
        admin.is_active = True
        db.session.commit()
        print("-> NutriLife administrator credentials updated.")
        return

    if not full_name or not mobile:
        raise ValueError("Administrator name and mobile are required for a new account.")

    admin = User(
        email=NUTRILIFE_ADMIN_USERNAME,
        full_name=full_name,
        mobile=mobile,
        role='admin',
        is_active=True
    )
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    print("-> NutriLife administrator account created.")


def main():
    parser = argparse.ArgumentParser(description="Initialize Dr. Girija's NutriLife database")
    parser.add_argument('--create-admin', action='store_true', help="Interactively create an administrator account")
    parser.add_argument('--admin-email', help="Email for the new administrator")
    parser.add_argument(
        '--configure-nutrilife-admin',
        action='store_true',
        help="Create or update the Dr. Girija's NutriLife administrator account"
    )

    args = parser.parse_args()
    if args.create_admin and args.configure_nutrilife_admin:
        parser.error("Choose either --create-admin or --configure-nutrilife-admin.")
    if args.admin_email and not args.create_admin:
        parser.error("--admin-email can only be used with --create-admin.")

    app = create_app()
    admin_details = None
    nutrilife_admin_details = None
    with app.app_context():
        print("Creating any missing database tables...")
        db.create_all()

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

        if args.configure_nutrilife_admin:
            existing_admin = User.query.filter_by(email=NUTRILIFE_ADMIN_USERNAME).first()
            if existing_admin and not existing_admin.is_admin:
                parser.error(
                    "The NutriLife admin username belongs to a non-admin account."
                )
            full_name = existing_admin.full_name if existing_admin else input(
                "Administrator name: "
            ).strip()
            mobile = existing_admin.mobile if existing_admin else input(
                "Administrator mobile: "
            ).strip()
            password = getpass("Administrator password: ")
            confirmation = getpass("Confirm administrator password: ")
            if not password:
                parser.error("Administrator password must not be empty.")
            if password != confirmation:
                parser.error("Administrator passwords do not match.")
            nutrilife_admin_details = (password, full_name, mobile)

        print("Ensuring the primary NutriLife coach...")
        seed_coaches()
        
        if admin_details:
            create_admin(*admin_details)
        if nutrilife_admin_details:
            configure_nutrilife_admin(*nutrilife_admin_details)
            
        print("\nDatabase initialization complete! Database is ready.")

if __name__ == '__main__':
    main()
