import os
from app import create_app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '127.0.0.1')
    debug = os.environ.get('DEBUG', 'True').lower() in ('true', '1', 't')
    
    print("=" * 65)
    print("  DR. GIRIJA'S NUTRILIFE WEB APPLICATION")
    print(f"  Server running at: http://{host}:{port}/")
    print(f"  Admin portal at:   http://{host}:{port}/admin")
    print("=" * 65)
    
    app.run(host=host, port=port, debug=debug)
