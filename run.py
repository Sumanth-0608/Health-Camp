import os
from app import create_app
from app.models import db, Coach, User

app = create_app()

if __name__ == '__main__':
    with app.app_context():
        # Ensure database tables exist
        db.create_all()
        # Seed coaches if none exist
        if Coach.query.count() == 0:
            from init_db import seed_coaches
            seed_coaches()
            
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '127.0.0.1')
    debug = os.environ.get('DEBUG', 'True').lower() in ('true', '1', 't')
    
    print("=" * 65)
    print("  90-DAY WELLNESS TRACKER WEB APPLICATION")
    print(f"  Server running at: http://{host}:{port}/")
    print(f"  Admin portal at:   http://{host}:{port}/admin")
    print("=" * 65)
    
    app.run(host=host, port=port, debug=debug)
