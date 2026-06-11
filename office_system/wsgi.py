# -*- coding: utf-8 -*-
"""
PythonAnywhere WSGI entry point.
"""
import sys
import os

# --- PythonAnywhere will replace this path ---
# Set this to your PA home directory + /office_system
PROJECT_PATH = '/home/YOUR_USERNAME/office_system'

if PROJECT_PATH not in sys.path:
    sys.path.insert(0, PROJECT_PATH)

# Ensure data directories exist on first run
data_dir = os.path.join(PROJECT_PATH, 'data')
upload_dir = os.path.join(data_dir, 'uploads')
for d in [data_dir, upload_dir]:
    if not os.path.exists(d):
        os.makedirs(d)

# Initialize database on first run if needed
db_path = os.path.join(PROJECT_PATH, 'data', 'database.db')
if not os.path.exists(db_path):
    from app.database import init_database
    init_database()
else:
    try:
        from migrate import migrate
        migrate()
    except Exception as e:
        print('[WARN] Migration skipped:', str(e))

from app import create_app
application = create_app()
