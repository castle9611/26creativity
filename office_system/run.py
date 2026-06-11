# -*- coding: utf-8 -*-
"""
Main entry point for the OA system.
Handles database initialization and server startup.
"""
import sys
import os

# Add project root to path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Ensure data directories
for d in [os.path.join(BASE_DIR, 'data'), os.path.join(BASE_DIR, 'data', 'uploads')]:
    if not os.path.exists(d):
        os.makedirs(d)

# Initialize database on first run, migrate if already exists
db_path = os.path.join(BASE_DIR, 'data', 'database.db')
if not os.path.exists(db_path):
    print('[INFO] First run - creating database...')
    from app.database import init_database
    init_database()
    print('[OK] Database created with default data')
else:
    print('[INFO] Database exists - running migration if needed...')
    try:
        from migrate import migrate
        migrate()
    except Exception as e:
        print('[WARN] Migration skipped:', str(e))

# Start server
from app import create_app
from app.config import Config

app = create_app()
print('[INFO] Starting server on http://0.0.0.0:5000')
app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
