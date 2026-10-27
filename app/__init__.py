
from datetime import datetime, date
from urllib.parse import urlparse

from flask import Flask, g, url_for
from .config import Config
from .models import db, User, SupportConversation
from .auth import get_current_user


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize database
    db.init_app(app)

    # Register blueprints
    from .routes.main import main_bp
    from .routes.auth_routes import auth_bp
    from .routes.participant import participant_bp
    from .routes.trackers import trackers_bp
    from .routes.support import support_bp
    from .routes.admin import admin_bp
    from .routes.uploads import uploads_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(participant_bp)
    app.register_blueprint(trackers_bp)
    app.register_blueprint(support_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(uploads_bp)

    # Global variables available in templates
    @app.context_processor
    def inject_globals():
        user = get_current_user()
        unread_support = 0

        if user:
            if user.is_admin:
                unread_support = SupportConversation.query.filter_by(
                    status="Open"
                ).count()
            else:
                unread_support = SupportConversation.query.filter_by(
                    participant_id=user.id,
                    status="Replied"
                ).count()

        return {
            "current_user": user,
            "current_year": datetime.utcnow().year,
            "today_date": date.today(),
            "unread_support": unread_support,
        }

    # Helper for Cloudinary URLs and legacy local uploads
    @app.context_processor
    def inject_upload_helpers():
        def upload_url(folder, stored_path):
            if folder not in {"profiles", "meals", "reports"} or not stored_path:
                return ""

            parsed = urlparse(stored_path)

            # Blood reports always pass through the authenticated route.
            if folder in {"profiles", "meals"} and (
                parsed.scheme == "https"
                and parsed.hostname == "res.cloudinary.com"
            ):
                return stored_path

            if folder == "reports" and (parsed.scheme or parsed.netloc):
                return ""

            # Older uploads use the existing local upload route.
            filename = stored_path.replace("\\", "/").lstrip("/")
            if folder != "reports" and (parsed.scheme or parsed.netloc):
                return ""
            if filename.startswith(f"{folder}/"):
                filename = filename[len(folder) + 1:]
            if not filename or any(part in {".", ".."} for part in filename.split("/")):
                return ""

            return url_for(
                "uploads.serve_file",
                folder=folder,
                filename=filename,
            )

        return {"upload_url": upload_url}

    # Date formatting filter
    @app.template_filter("format_date")
    def format_date(value, format="%b %d, %Y"):
        if not value:
            return ""

        if isinstance(value, str):
            try:
                value = datetime.strptime(value, "%Y-%m-%d").date()
            except Exception:
                return value

        return value.strftime(format)

    return app
