# -*- coding: utf-8 -*-
"""
Global configuration for internal network office system.
All paths relative to project root. No .env file needed.
Python 3.8.10 64-bit portable + Flask 2.0.1 + SQLite3.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Portable Python directory
PYTHON_DIR = os.path.join(BASE_DIR, 'python')


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


class Config:
    """Flask application configuration"""
    # Flask secret key (internal network, static value is fine)
    SECRET_KEY = 'office-system-win7-secret-key-2024-internal'

    # SQLite single-file database
    DB_PATH = os.path.join(BASE_DIR, 'data', 'database.db')
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + DB_PATH.replace('\\', '/')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False

    # File upload
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'data', 'uploads')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB

    # ONLYOFFICE Docs (all deployment-specific values come from environment)
    ONLYOFFICE_ENABLED = env_bool('ONLYOFFICE_ENABLED', False)
    ONLYOFFICE_SERVER_URL = os.environ.get('ONLYOFFICE_SERVER_URL', '').strip().rstrip('/')
    ONLYOFFICE_JWT_ENABLED = env_bool('ONLYOFFICE_JWT_ENABLED', True)
    ONLYOFFICE_JWT_SECRET = os.environ.get('ONLYOFFICE_JWT_SECRET', '')
    APP_PUBLIC_URL = os.environ.get('APP_PUBLIC_URL', '').strip().rstrip('/')
    DOCUMENT_STORAGE_FOLDER = os.path.abspath(os.environ.get(
        'DOCUMENT_STORAGE_FOLDER', os.path.join(BASE_DIR, 'data', 'online_documents')))
    DOCUMENT_VERSION_FOLDER = os.path.abspath(os.environ.get(
        'DOCUMENT_VERSION_FOLDER', os.path.join(BASE_DIR, 'data', 'document_versions')))
    DOCUMENT_MAX_UPLOAD_MB = max(1, int(os.environ.get('DOCUMENT_MAX_UPLOAD_MB', '50')))
    DOCUMENT_URL_TOKEN_MAX_AGE = max(60, int(os.environ.get('DOCUMENT_URL_TOKEN_MAX_AGE', '600')))
    ONLYOFFICE_DOWNLOAD_HOSTS = tuple(
        item.strip().lower() for item in os.environ.get('ONLYOFFICE_DOWNLOAD_HOSTS', '').split(',')
        if item.strip())
    ALLOWED_EXTENSIONS = {
        'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
        'pdf', 'txt', 'csv', 'rtf',
        'jpg', 'jpeg', 'png', 'gif', 'bmp',
        'zip', 'rar', '7z',
        'mp4', 'avi', 'wmv', 'mp3', 'wav'
    }

    # Session
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 28800  # 8 hours

    # Pagination
    ITEMS_PER_PAGE = 15

    # Max tabs limit
    MAX_TABS = 10

    # Logging
    LOG_LEVEL = 'INFO'

    # Server
    HOST = '0.0.0.0'
    PORT = 5000
    DEBUG = False

    # Default accounts (first-time init only)
    DEFAULT_ADMIN = {
        'username': 'admin',
        'password': 'admin123',
        'real_name': '系统管理员',
        'role': 'super_admin',
        'department': '信息技术科'
    }
    DEFAULT_DEPT_ADMIN = {
        'username': 'dept_admin',
        'password': 'admin123',
        'real_name': '监区管理员',
        'role': 'dept_admin',
        'department': '一监区'
    }
    DEFAULT_USER = {
        'username': 'user',
        'password': 'admin123',
        'real_name': '监区民警',
        'role': 'user',
        'department': '一监区'
    }
