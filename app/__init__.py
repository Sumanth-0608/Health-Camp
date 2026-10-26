from datetime import datetime, date
from flask import Flask, g
from .config import Config
from .models import db, User, SupportConversation
from .auth import get_current_user

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize DB
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
    
    # Context processor for global template variables
    @app.context_processor
    def inject_globals():
        user = get_current_user()
        unread_support = 0
        if user:
            if user.is_admin:
                unread_support = SupportConversation.query.filter_by(status='Open').count()
            else:
                unread_support = SupportConversation.query.filter_by(participant_id=user.id, status='Replied').count()
        return {
            'current_user': user,
            'current_year': datetime.utcnow().year,
            'today_date': date.today(),
            'unread_support': unread_support
        }
        
    # Custom template filters
    @app.template_filter('format_date')
    def format_date(value, format='%b %d, %Y'):
        if not value:
            return ''
        if isinstance(value, str):
            try:
                value = datetime.strptime(value, '%Y-%m-%d').date()
            except Exception:
                return value
        return value.strftime(format)

    return app
