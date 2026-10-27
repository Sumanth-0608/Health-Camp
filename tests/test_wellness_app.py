import os
import io
import time
import unittest
from unittest.mock import patch
from datetime import date, timedelta, datetime
from sqlalchemy.exc import OperationalError
from werkzeug.datastructures import FileStorage
from app import create_app
from app.models import (
    db, User, ParticipantProfile, Coach, DailyLog, Meal, 
    WaterLog, MovementEntry, HabitDay, Measurement, BloodReport, 
    WeeklyScore, SupportConversation, SupportMessage, ensure_primary_coach,
    PRIMARY_COACH_NAME, PRIMARY_COACH_SPECIALTY
)
from app.config import Config, _database_uri, _secret_key
from init_db import (
    NUTRILIFE_ADMIN_USERNAME, configure_nutrilife_admin, seed_coaches
)
from app.utils import (
    PRIVATE_URL_TTL_SECONDS,
    REPORT_PREFIX,
    UploadStorageError,
    delete_uploaded_file,
    get_private_report_url,
    save_uploaded_file,
)

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret-key-12345"


class DatabaseConfigTests(unittest.TestCase):
    def test_local_database_defaults_to_sqlite(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(_database_uri().startswith("sqlite:///"))

    def test_production_requires_database_url(self):
        with patch.dict(os.environ, {"VERCEL": "1"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL is required"):
                _database_uri()

    def test_production_rejects_sqlite(self):
        with patch.dict(os.environ, {"APP_ENV": "production", "DATABASE_URL": "sqlite:///local.db"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "must use a PostgreSQL URL"):
                _database_uri()

    def test_production_rejects_malformed_database_url(self):
        with patch.dict(os.environ, {"VERCEL": "1", "DATABASE_URL": "postgresql://"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "include the PostgreSQL host"):
                _database_uri()

    def test_postgres_url_uses_psycopg_driver(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgres://db.invalid/wellness"}, clear=True):
            self.assertEqual(
                _database_uri(),
                "postgresql+psycopg://db.invalid/wellness",
            )

    def test_production_requires_secret_key(self):
        with patch.dict(os.environ, {"APP_ENV": "production"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "SECRET_KEY must be set"):
                _secret_key()

    def test_development_secret_is_generated_when_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            first_secret = _secret_key()
            second_secret = _secret_key()
        self.assertGreaterEqual(len(first_secret), 32)
        self.assertNotEqual(first_secret, second_secret)


class WellnessTrackerTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        
        # Seed the only supported coach
        self.coach = Coach(
            name=PRIMARY_COACH_NAME,
            email="dr.girija.pashikanti@nutrilife.invalid",
            specialty=PRIMARY_COACH_SPECIALTY
        )
        db.session.add(self.coach)
        
        # Seed test admin
        self.admin = User(
            email="admin@testwellness.com",
            full_name="Lead Administrator",
            mobile="+15550001111",
            role="admin",
            is_active=True
        )
        self.admin.set_password("AdminPass123!")
        db.session.add(self.admin)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def create_dummy_image(self, filename="test.jpg"):
        from PIL import Image
        img = Image.new('RGB', (100, 100), color='green')
        buf = io.BytesIO()
        img.save(buf, format='JPEG')
        buf.seek(0)
        return (buf, filename)

    # 1. New participant registration
    def test_01_participant_registration(self):
        registration_page = self.client.get('/register').get_data(as_text=True)
        self.assertEqual(registration_page.count("<option"), 1)
        self.assertIn(
            f"{PRIMARY_COACH_NAME} — {PRIMARY_COACH_SPECIALTY}",
            registration_page
        )

        start_date_str = (date.today() - timedelta(days=5)).strftime('%Y-%m-%d')
        response = self.client.post('/register', data={
            'full_name': 'Alice Participant',
            'email': 'alice@example.com',
            'mobile': '+15551234567',
            'password': 'password123',
            'confirm_password': 'password123',
            'coach_id': str(self.coach.id),
            'start_date': start_date_str,
            'goal_90_day': 'Drop 5kg and build morning energy',
            'reason_why': 'To feel healthy and vibrant',
            'session_day_time': 'Wednesdays at 7 PM',
            'root_cause_1': 'Late snacking',
            'root_cause_2': 'Sedentary work'
        }, follow_redirects=True)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Welcome to Dr. Girija&#39;s NutriLife", response.data)
        
        user = User.query.filter_by(email='alice@example.com').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.role, 'participant')
        self.assertIsNotNone(user.profile)
        self.assertEqual(user.profile.coach_id, self.coach.id)
        self.assertEqual(user.profile.coach_name, PRIMARY_COACH_NAME)
        
        # Check that standard records were initialized
        self.assertEqual(Measurement.query.filter_by(participant_id=user.id).count(), 13)
        self.assertEqual(BloodReport.query.filter_by(participant_id=user.id).count(), 15)
        self.assertEqual(WeeklyScore.query.filter_by(participant_id=user.id).count(), 12)

        self.client.get('/logout')
        login_response = self.client.post('/login', data={
            'email': 'alice@example.com',
            'password': 'password123'
        }, follow_redirects=True)
        self.assertEqual(login_response.status_code, 200)
        db.session.expire_all()
        persisted_profile = User.query.filter_by(email='alice@example.com').first().profile
        self.assertEqual(persisted_profile.coach_name, PRIMARY_COACH_NAME)
        self.assertEqual(persisted_profile.coach_id, self.coach.id)

    def test_registration_rejects_another_active_coach_id(self):
        other_coach = Coach(
            name="Unexpected Coach",
            email="unexpected-coach@example.com",
            specialty="Not selectable"
        )
        db.session.add(other_coach)
        db.session.commit()

        response = self.client.post('/register', data={
            'full_name': 'Invalid Coach Participant',
            'email': 'invalid-coach@example.com',
            'mobile': '12345',
            'password': 'password123',
            'confirm_password': 'password123',
            'coach_id': str(other_coach.id),
            'start_date': date.today().strftime('%Y-%m-%d'),
            'goal_90_day': 'Build healthier routines',
            'reason_why': 'Feel better every day',
            'session_day_time': 'Wednesdays at 7 PM',
            'root_cause_1': 'Late nights',
            'root_cause_2': 'Inactivity'
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Please select the available NutriLife coach.", response.data)
        self.assertIsNone(User.query.filter_by(email='invalid-coach@example.com').first())

    def test_registration_creates_missing_coach_and_persists_assignment(self):
        db.session.delete(self.coach)
        db.session.commit()

        page = self.client.get('/register')
        coach = Coach.query.filter_by(name=PRIMARY_COACH_NAME, is_active=True).one()
        page_text = page.get_data(as_text=True)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page_text.count("<option"), 1)
        self.assertIn(
            f'<option value="{coach.id}">{PRIMARY_COACH_NAME} — '
            f'{PRIMARY_COACH_SPECIALTY}</option>',
            page_text
        )

        response = self.client.post('/register', data={
            'full_name': 'Coach Migration Participant',
            'email': 'coach-migration@example.com',
            'mobile': '12345',
            'password': 'password123',
            'confirm_password': 'password123',
            'coach_id': str(coach.id),
            'start_date': date.today().strftime('%Y-%m-%d'),
            'goal_90_day': 'Build healthier routines',
            'reason_why': 'Feel better every day',
            'session_day_time': 'Wednesdays at 7 PM',
            'root_cause_1': 'Late nights',
            'root_cause_2': 'Inactivity'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        participant = User.query.filter_by(
            email='coach-migration@example.com'
        ).one()
        self.assertEqual(participant.profile.coach_id, coach.id)
        self.assertEqual(participant.profile.coach_name, PRIMARY_COACH_NAME)

        self.client.get('/logout')
        self.client.post('/login', data={
            'email': participant.email,
            'password': 'password123'
        }, follow_redirects=True)
        db.session.expire_all()
        persisted = User.query.filter_by(email=participant.email).one()
        self.assertEqual(persisted.profile.coach_id, coach.id)
        self.assertEqual(persisted.profile.coach_name, PRIMARY_COACH_NAME)

    def test_registration_displays_database_coach_load_failure(self):
        with patch(
            'app.routes.auth_routes.ensure_primary_coach',
            side_effect=OperationalError(
                "SELECT coach", {}, Exception("database unavailable")
            )
        ):
            response = self.client.get('/register')

        page_text = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 503)
        self.assertIn("Coach information is temporarily unavailable.", page_text)
        self.assertIn("We could not load coach information.", page_text)
        self.assertIn('name="coach_id" required disabled', page_text)
        self.assertIn('type="submit" disabled', page_text)

    def test_coach_initialization_preserves_profiles_and_deactivates_old_coaches(self):
        legacy_coaches = [
            Coach(name="Legacy Coach One", email="legacy-one@example.com"),
            Coach(name="Legacy Coach Two", email="legacy-two@example.com")
        ]
        participant = User(
            email="legacy-participant@example.com",
            full_name="Legacy Participant",
            mobile="12345",
            role="participant"
        )
        participant.set_password("Secret123!")
        db.session.add_all([*legacy_coaches, participant])
        db.session.flush()
        db.session.add(ParticipantProfile(
            user_id=participant.id,
            coach_id=legacy_coaches[0].id,
            coach_name=legacy_coaches[0].name,
            start_date=date.today()
        ))
        db.session.commit()

        seed_coaches()
        seed_coaches()

        db.session.expire_all()
        profile = ParticipantProfile.query.filter_by(user_id=participant.id).one()
        self.assertEqual(profile.coach_id, self.coach.id)
        self.assertEqual(profile.coach_name, PRIMARY_COACH_NAME)
        self.assertEqual(Coach.query.filter_by(is_active=True).count(), 1)
        self.assertEqual(Coach.query.count(), 3)
        self.assertEqual(User.query.filter_by(email=participant.email).count(), 1)

    def test_configured_admin_login_hashing_and_invalid_credentials(self):
        password = "LocalTestPassword123!"
        configure_nutrilife_admin(
            password,
            full_name="Dr. Girija Pashikanti",
            mobile="12345"
        )
        configure_nutrilife_admin(password)

        admin = User.query.filter_by(email=NUTRILIFE_ADMIN_USERNAME).one()
        self.assertTrue(admin.is_admin)
        self.assertNotEqual(admin.password_hash, password)
        self.assertTrue(admin.check_password(password))

        response = self.client.post('/login', data={
            'email': NUTRILIFE_ADMIN_USERNAME,
            'password': password
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Dr. Girija's NutriLife Admin Dashboard", response.data)

        self.client.get('/logout')
        invalid_response = self.client.post('/login', data={
            'email': NUTRILIFE_ADMIN_USERNAME,
            'password': 'incorrect-password'
        }, follow_redirects=True)
        self.assertEqual(invalid_response.status_code, 200)
        self.assertIn(b"Invalid email or password", invalid_response.data)
        self.assertNotIn(b"Protected Administration Portal", invalid_response.data)

    # 2. Returning participant login
    def test_02_participant_login(self):
        # Register user
        user = User(email='bob@example.com', full_name='Bob Smith', mobile='12345', role='participant')
        user.set_password('Secret123!')
        db.session.add(user)
        db.session.flush()
        profile = ParticipantProfile(user_id=user.id, start_date=date.today())
        db.session.add(profile)
        db.session.commit()
        
        # Attempt login
        resp = self.client.post('/login', data={
            'email': 'bob@example.com',
            'password': 'Secret123!'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Welcome back, Bob Smith!", resp.data)
        self.assertIn(b"Dashboard", resp.data)

    # 3. Participant profile photo upload and update
    def test_03_profile_photo_upload(self):
        user = User(email='charlie@example.com', full_name='Charlie', mobile='12345', role='participant')
        user.set_password('pass123')
        db.session.add(user)
        db.session.flush()
        db.session.add(ParticipantProfile(user_id=user.id, start_date=date.today()))
        db.session.commit()
        
        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id
            
        img_buf, img_name = self.create_dummy_image("charlie_avatar.jpg")
        with patch('app.utils.configure_cloudinary', return_value=True), patch(
            'app.utils.cloudinary.uploader.upload',
            return_value={
                'public_id': 'nutrilife/profiles/profile-id',
                'resource_type': 'image',
                'secure_url': 'https://res.cloudinary.com/test/image/upload/profile.jpg',
            },
        ) as cloudinary_upload:
            resp = self.client.post('/profile', data={
                'action': 'update_photo',
                'profile_photo': (img_buf, img_name)
            }, content_type='multipart/form-data', follow_redirects=True)
        
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Profile photo updated successfully!", resp.data)
        
        updated_user = db.session.get(User, user.id)
        self.assertIsNotNone(updated_user.profile_photo)
        self.assertEqual(
            updated_user.profile_photo,
            'https://res.cloudinary.com/test/image/upload/profile.jpg'
        )
        self.assertIn(
            b'https://res.cloudinary.com/test/image/upload/profile.jpg',
            resp.data,
        )
        self.assertEqual(cloudinary_upload.call_count, 1)
        self.assertEqual(
            cloudinary_upload.call_args.kwargs['filename'],
            img_name,
        )

    def test_profile_photo_upload_handles_missing_cloudinary_credentials(self):
        user = User(
            email='profile-upload-error@example.com',
            full_name='Profile Upload Error',
            mobile='12345',
            role='participant',
        )
        user.set_password('pass123')
        db.session.add(user)
        db.session.flush()
        db.session.add(ParticipantProfile(user_id=user.id, start_date=date.today()))
        db.session.commit()

        with self.client.session_transaction() as session:
            session['user_id'] = user.id

        image, filename = self.create_dummy_image('profile.jpg')
        with patch.dict(os.environ, {}, clear=True):
            response = self.client.post(
                '/profile',
                data={
                    'action': 'update_photo',
                    'profile_photo': (image, filename),
                },
                content_type='multipart/form-data',
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Profile photo upload failed.', response.data)
        self.assertIsNone(db.session.get(User, user.id).profile_photo)

    def test_cloudinary_storage_uses_private_report_delivery_and_correct_deletes(self):
        report = FileStorage(stream=io.BytesIO(b"report"), filename="report.pdf")
        with patch("app.utils.configure_cloudinary", return_value=True), patch(
            "app.utils.cloudinary.uploader.upload",
            return_value={
                "public_id": "nutrilife/reports/report-id",
                "resource_type": "raw",
            },
        ) as upload:
            stored_path = save_uploaded_file(
                report,
                "reports",
                allowed_extensions={"jpg", "pdf"},
            )

        self.assertEqual(
            stored_path,
            f"{REPORT_PREFIX}raw:pdf:nutrilife/reports/report-id",
        )
        self.assertEqual(upload.call_args.kwargs["resource_type"], "raw")
        self.assertEqual(upload.call_args.kwargs["type"], "authenticated")
        self.assertEqual(upload.call_args.kwargs["filename"], "report.pdf")

        before = int(time.time())
        with patch("app.utils.configure_cloudinary", return_value=True), patch(
            "app.utils.cloudinary.utils.private_download_url",
            return_value="https://res.cloudinary.com/test/private",
        ) as private_url:
            self.assertEqual(get_private_report_url(stored_path),
                             "https://res.cloudinary.com/test/private")
        options = private_url.call_args.kwargs
        self.assertEqual(options["resource_type"], "raw")
        self.assertEqual(options["type"], "authenticated")
        self.assertEqual(private_url.call_args.args[1], "pdf")
        self.assertGreaterEqual(
            options["expires_at"],
            before + PRIVATE_URL_TTL_SECONDS,
        )

        with patch("app.utils.configure_cloudinary", return_value=True), patch(
            "app.utils.cloudinary.uploader.destroy",
            return_value={"result": "ok"},
        ) as destroy:
            delete_uploaded_file(stored_path)
        destroy.assert_called_once_with(
            "nutrilife/reports/report-id",
            resource_type="raw",
            type="authenticated",
            invalidate=True,
        )

    def test_upload_without_cloudinary_credentials_raises_safe_storage_error(self):
        image = FileStorage(stream=io.BytesIO(b"image"), filename="meal.jpg")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                UploadStorageError,
                "Cloudinary is not configured",
            ):
                save_uploaded_file(
                    image,
                    "meals",
                    allowed_extensions={"jpg"},
                )

    def test_cloudinary_public_meal_and_private_image_report(self):
        meal_photo = FileStorage(stream=io.BytesIO(b"image"), filename="meal.webp")
        with patch("app.utils.configure_cloudinary", return_value=True), patch(
            "app.utils.cloudinary.uploader.upload",
            return_value={
                "public_id": "meal-id",
                "resource_type": "image",
                "secure_url": "https://res.cloudinary.com/test/image/upload/meal-id.webp",
            },
        ) as upload:
            meal_path = save_uploaded_file(
                meal_photo,
                "meals",
                allowed_extensions={"webp"},
            )

        self.assertEqual(
            meal_path,
            "https://res.cloudinary.com/test/image/upload/meal-id.webp",
        )
        self.assertEqual(upload.call_args.kwargs["resource_type"], "image")
        self.assertEqual(upload.call_args.kwargs["folder"], "nutrilife/meals")
        self.assertEqual(upload.call_args.kwargs["filename"], "meal.webp")
        self.assertNotIn("type", upload.call_args.kwargs)

        report_image = FileStorage(stream=io.BytesIO(b"image"), filename="scan.png")
        with patch("app.utils.configure_cloudinary", return_value=True), patch(
            "app.utils.cloudinary.uploader.upload",
            return_value={
                "public_id": "nutrilife/reports/scan-id",
                "resource_type": "image",
            },
        ) as upload:
            report_path = save_uploaded_file(
                report_image,
                "reports",
                allowed_extensions={"png"},
            )

        self.assertEqual(
            report_path,
            f"{REPORT_PREFIX}image:png:nutrilife/reports/scan-id",
        )
        self.assertEqual(upload.call_args.kwargs["resource_type"], "image")
        self.assertEqual(upload.call_args.kwargs["type"], "authenticated")
        self.assertEqual(upload.call_args.kwargs["filename"], "scan.png")

        with patch("app.utils.configure_cloudinary", return_value=True), patch(
            "app.utils.cloudinary.utils.private_download_url",
            return_value="https://res.cloudinary.com/test/private-image",
        ) as private_url:
            self.assertEqual(
                get_private_report_url(report_path),
                "https://res.cloudinary.com/test/private-image",
            )
        self.assertEqual(private_url.call_args.args[1], "png")
        self.assertEqual(private_url.call_args.kwargs["resource_type"], "image")
        self.assertEqual(private_url.call_args.kwargs["type"], "authenticated")

    def test_private_report_route_requires_owner_or_admin(self):
        participant = User(
            email="report-owner@example.com",
            full_name="Report Owner",
            mobile="12345",
            role="participant",
        )
        participant.set_password("Secret123!")
        other_participant = User(
            email="other-owner@example.com",
            full_name="Other Owner",
            mobile="12346",
            role="participant",
        )
        other_participant.set_password("Secret123!")
        db.session.add_all([participant, other_participant])
        db.session.flush()
        stored_path = f"{REPORT_PREFIX}raw:pdf:reports/report-id"
        db.session.add(BloodReport(
            participant_id=participant.id,
            test_name="Lab report",
            report_file_path=stored_path,
        ))
        db.session.commit()
        report_url = f"/uploads/reports/{stored_path}"

        self.assertEqual(self.client.get(report_url).status_code, 401)

        with patch(
            "app.routes.uploads.get_private_report_url",
            return_value="https://res.cloudinary.com/test/temporary",
        ) as private_url:
            with self.client.session_transaction() as session:
                session["user_id"] = other_participant.id
            self.assertEqual(self.client.get(report_url).status_code, 404)

            with self.client.session_transaction() as session:
                session["user_id"] = participant.id
            owner_response = self.client.get(report_url)
            self.assertEqual(owner_response.status_code, 302)
            self.assertEqual(
                owner_response.headers["Location"],
                "https://res.cloudinary.com/test/temporary",
            )
            self.assertEqual(owner_response.headers["Cache-Control"], "private, no-store")
            self.assertEqual(
                owner_response.headers["Referrer-Policy"],
                "no-referrer",
            )

            with self.client.session_transaction() as session:
                session["user_id"] = self.admin.id
            self.assertEqual(self.client.get(report_url).status_code, 302)
            self.assertEqual(private_url.call_count, 2)

    def test_upload_url_helper_routes_private_reports_and_keeps_public_images(self):
        public_image = "https://res.cloudinary.com/test/image/upload/meal.jpg"
        private_report = f"{REPORT_PREFIX}raw:pdf:reports/report-id"
        with self.app.test_request_context():
            context = {}
            self.app.update_template_context(context)
            upload_url = context["upload_url"]

            self.assertEqual(upload_url("meals", public_image), public_image)
            self.assertEqual(
                upload_url("profiles", "profiles/legacy-photo.jpg"),
                "/uploads/profiles/legacy-photo.jpg",
            )
            self.assertEqual(
                upload_url("reports", private_report),
                "/uploads/reports/cloudinary_private:raw:pdf:reports/report-id",
            )
            self.assertEqual(
                upload_url(
                    "reports",
                    "https://res.cloudinary.com/test/raw/upload/public-report.pdf",
                ),
                "",
            )

    def test_dashboard_renders_profile_photo_url_without_changing_layout(self):
        image_url = "https://res.cloudinary.com/test/image/upload/profile.jpg"
        user = User(
            email="dashboard-photo@example.com",
            full_name="Dashboard Participant",
            mobile="12345",
            role="participant",
            profile_photo=image_url,
        )
        user.set_password("Secret123!")
        db.session.add(user)
        db.session.flush()
        db.session.add(ParticipantProfile(
            user_id=user.id,
            start_date=date.today(),
            coach_name=PRIMARY_COACH_NAME,
        ))
        db.session.add(Measurement(
            participant_id=user.id,
            week_number=0,
            week_label="Start",
            weight_kg=72.0,
        ))
        db.session.commit()

        with self.client.session_transaction() as session:
            session["user_id"] = user.id

        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn(image_url.encode(), response.data)
        self.assertIn(b'id="measurementsChart"', response.data)
        self.assertIn(b"Hydration Progress", response.data)

    # 4. Save a meal without a photo
    def test_04_save_meal_without_photo(self):
        user = User(email='david@example.com', full_name='David', mobile='12345', role='participant')
        user.set_password('pass123')
        db.session.add(user)
        db.session.flush()
        db.session.add(ParticipantProfile(user_id=user.id, start_date=date.today()))
        db.session.commit()
        
        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id
            
        today_str = date.today().strftime('%Y-%m-%d')
        resp = self.client.post(f'/trackers/food?date={today_str}', data={
            'action': 'save_meal',
            'meal_slot': 'breakfast',
            'meal_time': '8:15 AM',
            'food_description': 'Steel-cut oats with chia seeds and almond butter',
            'notes': 'High satiety, steady energy'
        }, follow_redirects=True)
        
        self.assertEqual(resp.status_code, 200)
        meal = Meal.query.filter_by(participant_id=user.id, meal_slot='breakfast').first()
        self.assertIsNotNone(meal)
        self.assertEqual(meal.food_description, 'Steel-cut oats with chia seeds and almond butter')
        self.assertIsNone(meal.photo_path)

    # 5. Save a meal with a photo
    def test_05_save_meal_with_photo(self):
        user = User(email='eve@example.com', full_name='Eve', mobile='12345', role='participant')
        user.set_password('pass123')
        db.session.add(user)
        db.session.flush()
        db.session.add(ParticipantProfile(user_id=user.id, start_date=date.today()))
        db.session.commit()
        
        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id
            
        img_buf, img_name = self.create_dummy_image("lunch_salad.jpg")
        today_str = date.today().strftime('%Y-%m-%d')
        with patch('app.utils.configure_cloudinary', return_value=True), patch(
            'app.utils.cloudinary.uploader.upload',
            return_value={
                'public_id': 'nutrilife/meals/meal-id',
                'resource_type': 'image',
                'secure_url': 'https://res.cloudinary.com/test/image/upload/meal.jpg',
            },
        ) as cloudinary_upload:
            resp = self.client.post(f'/trackers/food?date={today_str}', data={
                'action': 'save_meal',
                'meal_slot': 'lunch',
                'meal_time': '1:00 PM',
                'food_description': 'Grilled salmon with asparagus and quinoa',
                'meal_photo': (img_buf, img_name)
            }, content_type='multipart/form-data', follow_redirects=True)
        
        self.assertEqual(resp.status_code, 200)
        meal = Meal.query.filter_by(participant_id=user.id, meal_slot='lunch').first()
        self.assertIsNotNone(meal)
        self.assertIsNotNone(meal.photo_path)
        self.assertEqual(
            meal.photo_path,
            'https://res.cloudinary.com/test/image/upload/meal.jpg'
        )
        self.assertIn(
            b'https://res.cloudinary.com/test/image/upload/meal.jpg',
            resp.data,
        )
        self.assertEqual(cloudinary_upload.call_count, 1)
        self.assertEqual(
            cloudinary_upload.call_args.kwargs['filename'],
            img_name,
        )

    # 6. Meal records and photos remain available after re-login
    def test_06_meal_persistence_after_relogin(self):
        user = User(email='frank@example.com', full_name='Frank', mobile='12345', role='participant')
        user.set_password('FrankPass123')
        db.session.add(user)
        db.session.flush()
        db.session.add(ParticipantProfile(user_id=user.id, start_date=date.today()))
        
        meal = Meal(
            participant_id=user.id,
            date=date.today(),
            meal_slot='dinner',
            food_description='Lentil curry with brown rice',
            photo_path='meals/sample_frank_dinner.jpg'
        )
        db.session.add(meal)
        db.session.commit()
        
        # Log out
        self.client.get('/logout')
        
        # Log back in
        self.client.post('/login', data={'email': 'frank@example.com', 'password': 'FrankPass123'})
        
        # Fetch food page
        today_str = date.today().strftime('%Y-%m-%d')
        resp = self.client.get(f'/trackers/food?date={today_str}')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Lentil curry with brown rice", resp.data)
        self.assertIn(b"sample_frank_dinner.jpg", resp.data)

    # 7. Water entries calculate correctly
    def test_07_water_calculations(self):
        user = User(email='grace@example.com', full_name='Grace', mobile='12345', role='participant')
        user.set_password('pass123')
        db.session.add(user)
        db.session.flush()
        db.session.add(ParticipantProfile(user_id=user.id, start_date=date.today()))
        db.session.commit()
        
        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id
            
        today_str = date.today().strftime('%Y-%m-%d')
        # Add 250ml
        self.client.post(f'/trackers/water?date={today_str}', data={'action': 'add_intake', 'amount': '250', 'unit': 'ml'})
        # Add 500ml
        self.client.post(f'/trackers/water?date={today_str}', data={'action': 'add_intake', 'amount': '500', 'unit': 'ml'})
        # Add 1 Liter (1000ml)
        self.client.post(f'/trackers/water?date={today_str}', data={'action': 'add_intake', 'amount': '1', 'unit': 'l'})
        
        entries = WaterLog.query.filter_by(participant_id=user.id, date=date.today()).all()
        self.assertEqual(len(entries), 3)
        total_water = sum(e.amount_ml for e in entries)
        self.assertEqual(total_water, 1750) # 250 + 500 + 1000
        
        # Delete one entry
        del_id = entries[0].id
        del_amt = entries[0].amount_ml
        self.client.post(f'/trackers/water?date={today_str}', data={'action': 'delete_intake', 'entry_id': str(del_id)})
        
        remaining_entries = WaterLog.query.filter_by(participant_id=user.id, date=date.today()).all()
        self.assertEqual(sum(e.amount_ml for e in remaining_entries), 1750 - del_amt)

    # 8. Movement totals and averages calculate correctly
    def test_08_movement_totals_and_averages(self):
        user = User(email='harry@example.com', full_name='Harry', mobile='12345', role='participant')
        user.set_password('pass123')
        db.session.add(user)
        db.session.flush()
        db.session.add(ParticipantProfile(user_id=user.id, start_date=date.today() - timedelta(days=2)))
        db.session.commit()
        
        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id
            
        # Day 1 movement
        d1 = date.today() - timedelta(days=2)
        m1 = MovementEntry(
            participant_id=user.id,
            date=d1,
            program_day=1,
            steps=10000,
            morning_mins=30,
            evening_mins=20,
            other_mins=10
        )
        m1.total_active_mins = m1.calculate_total_active_mins() # 60
        db.session.add(m1)
        
        # Day 2 movement
        d2 = date.today() - timedelta(days=1)
        m2 = MovementEntry(
            participant_id=user.id,
            date=d2,
            program_day=2,
            steps=6000,
            morning_mins=20,
            evening_mins=20,
            other_mins=0
        )
        m2.total_active_mins = m2.calculate_total_active_mins() # 40
        db.session.add(m2)
        db.session.commit()
        
        # Verify sum and averages
        self.assertEqual(m1.total_active_mins, 60)
        self.assertEqual(m2.total_active_mins, 40)
        
        all_m = MovementEntry.query.filter_by(participant_id=user.id).all()
        valid_steps = [m.steps for m in all_m if m.steps is not None]
        valid_mins = [m.total_active_mins for m in all_m if m.total_active_mins is not None]
        
        days_filled = len(valid_steps)
        avg_steps = round(sum(valid_steps) / len(valid_steps))
        avg_mins = round(sum(valid_mins) / len(valid_mins))
        
        self.assertEqual(days_filled, 2)
        self.assertEqual(avg_steps, 8000) # (10000 + 6000) / 2
        self.assertEqual(avg_mins, 50)    # (60 + 40) / 2

    # 9. Habits, measurements, blood reports, and weekly scores
    def test_09_trackers_saving(self):
        user = User(email='isla@example.com', full_name='Isla', mobile='12345', role='participant')
        user.set_password('pass123')
        db.session.add(user)
        db.session.flush()
        db.session.add(ParticipantProfile(user_id=user.id, start_date=date.today()))
        db.session.commit()
        
        from app.auth import initialize_participant_records
        initialize_participant_records(user, date.today())
        
        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id
            
        # 1. Habits
        self.client.post('/trackers/habits?week=1', data={
            'action': 'save_ticks',
            'step_1_mon': 'on', 'step_1_tue': 'on', 'step_1_wed': 'on', 'step_1_thu': 'on', 'step_1_fri': 'on',
            'step_2_mon': 'on', 'step_2_tue': 'on'
        })
        hd1 = HabitDay.query.filter_by(participant_id=user.id, week_number=1, step_index=1).first()
        self.assertEqual(hd1.days_done, 5)
        self.assertEqual(hd1.percent_done, 71.4)
        
        # 2. Measurements
        # Start Day 1
        self.client.post('/trackers/measurements', data={
            'action': 'save_entry',
            'week_number': '0',
            'weight_kg': '78.4',
            'waist_cm': '88.0'
        })
        # Week 4
        self.client.post('/trackers/measurements', data={
            'action': 'save_entry',
            'week_number': '4',
            'weight_kg': '75.6',
            'waist_cm': '85.2'
        })
        m_start = Measurement.query.filter_by(participant_id=user.id, week_number=0).first()
        m_w4 = Measurement.query.filter_by(participant_id=user.id, week_number=4).first()
        self.assertEqual(round(m_w4.weight_kg - m_start.weight_kg, 1), -2.8)
        self.assertEqual(round(m_w4.waist_cm - m_start.waist_cm, 1), -2.8)
        
        # 3. Weekly Score
        self.client.post('/trackers/weekly-scores', data={
            'week_number': '1',
            'energy': '8',
            'sleep': '7',
            'digestion': '9',
            'mood': '8',
            'cravings': '8'
        })
        ws1 = WeeklyScore.query.filter_by(participant_id=user.id, week_number=1).first()
        self.assertEqual(ws1.week_average, 8.0) # (8+7+9+8+8)/5

    # 10 & 11. Admin portal reviews participant
    def test_10_and_11_admin_portal_review(self):
        user = User(email='jack@example.com', full_name='Jack Sparrow', mobile='99999', role='participant')
        user.set_password('pass123')
        db.session.add(user)
        db.session.flush()
        db.session.add(ParticipantProfile(user_id=user.id, start_date=date.today(), goal_90_day="Win treasure"))
        db.session.commit()
        
        # Login as Admin
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin.id
            
        resp = self.client.get('/admin/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Jack Sparrow", resp.data)
        
        # Inspect participant detail
        detail_resp = self.client.get(f'/admin/participants/{user.id}')
        self.assertEqual(detail_resp.status_code, 200)
        self.assertIn(b"Win treasure", detail_resp.data)

    # 12. Participant submits query and receives admin reply
    def test_12_support_ticket_and_reply(self):
        user = User(email='karen@example.com', full_name='Karen', mobile='12345', role='participant')
        user.set_password('pass123')
        db.session.add(user)
        db.session.commit()
        
        # Participant creates query
        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id
            
        resp = self.client.post('/support/new', data={
            'subject': 'Electrolyte timing',
            'message': 'Should I drink electrolytes before or after my morning run?'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        
        convo = SupportConversation.query.filter_by(participant_id=user.id).first()
        self.assertIsNotNone(convo)
        self.assertEqual(convo.status, 'Open')
        
        # Admin replies
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin.id
            
        resp_reply = self.client.post(f'/support/{convo.id}', data={
            'message': 'Take half before your run and sip the rest during your cool down!'
        }, follow_redirects=True)
        self.assertEqual(resp_reply.status_code, 200)
        
        updated_convo = db.session.get(SupportConversation, convo.id)
        self.assertEqual(updated_convo.status, 'Replied')
        self.assertEqual(updated_convo.messages.count(), 2)

    # 13. Privacy check: Participant cannot access another participant's private records
    def test_13_record_privacy(self):
        user1 = User(email='user1@example.com', full_name='User One', mobile='1', role='participant')
        user1.set_password('p1')
        user2 = User(email='user2@example.com', full_name='User Two', mobile='2', role='participant')
        user2.set_password('p2')
        db.session.add_all([user1, user2])
        db.session.commit()
        
        convo1 = SupportConversation(participant_id=user1.id, subject="Private issue")
        db.session.add(convo1)
        db.session.commit()
        
        # Login as User 2
        with self.client.session_transaction() as sess:
            sess['user_id'] = user2.id
            
        # Try to view User 1's conversation
        resp = self.client.get(f'/support/{convo1.id}')
        self.assertEqual(resp.status_code, 403)

    # 14. Participant cannot access protected admin functions
    def test_14_admin_access_protection(self):
        user = User(email='regular@example.com', full_name='Regular User', mobile='1', role='participant')
        user.set_password('p')
        db.session.add(user)
        db.session.flush()
        db.session.add(ParticipantProfile(user_id=user.id, start_date=date.today()))
        db.session.commit()
        
        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id
            
        resp = self.client.get('/admin/', follow_redirects=True)
        self.assertIn(b"Access denied. Administrator privileges are required.", resp.data)

    # 15. Main navigation endpoints return 200
    def test_15_navigation_endpoints(self):
        user = User(email='nav@example.com', full_name='Nav User', mobile='1', role='participant')
        user.set_password('p')
        db.session.add(user)
        db.session.flush()
        db.session.add(ParticipantProfile(user_id=user.id, start_date=date.today()))
        db.session.commit()
        
        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id
            
        endpoints = [
            '/dashboard',
            '/profile',
            '/trackers/daily',
            '/trackers/food',
            '/trackers/water',
            '/trackers/movement',
            '/trackers/habits',
            '/trackers/measurements',
            '/trackers/reports',
            '/trackers/weekly-scores',
            '/support/'
        ]
        for ep in endpoints:
            resp = self.client.get(ep)
            self.assertEqual(resp.status_code, 200, f"Endpoint {ep} failed with {resp.status_code}")

    # 16. Program day calculation uses real saved dates
    def test_16_program_day_calculation(self):
        user = User(email='date@example.com', full_name='Date Tester', mobile='1', role='participant')
        user.set_password('p')
        db.session.add(user)
        db.session.flush()
        
        # Start date exactly 10 days ago -> today is Day 11
        p = ParticipantProfile(user_id=user.id, start_date=date.today() - timedelta(days=10))
        db.session.add(p)
        db.session.commit()
        
        self.assertEqual(p.get_program_day(), 11)
        self.assertEqual(p.get_days_completed(), 11)
        self.assertEqual(p.get_days_remaining(), 79)

if __name__ == '__main__':
    unittest.main()
