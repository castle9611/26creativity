# -*- coding: utf-8 -*-
"""
Utility functions: logging, IP detection, pagination helpers.
"""
import json
import os
import re
import unicodedata
from urllib.parse import quote
from flask import request, session
from werkzeug.utils import secure_filename
from app.extensions import db
from app.models import OperationLog, LoginLog
from datetime import datetime


def get_client_ip():
    """Get client IP address from request."""
    if request.headers.get('X-Forwarded-For'):
        ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        ip = request.headers.get('X-Real-IP').strip()
    else:
        ip = request.remote_addr or '127.0.0.1'
    return ip


def add_log(action, target_type='', target_id=0, content=''):
    """
    Write operation log entry.
    """
    try:
        user_id = session.get('user_id', 0)
        ip = get_client_ip()
        log_entry = OperationLog(
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            content=content,
            ip_address=ip
        )
        db.session.add(log_entry)
        db.session.commit()
    except Exception:
        db.session.rollback()


def add_login_log(user_id):
    """Write login log entry."""
    try:
        ip = get_client_ip()
        log_entry = LoginLog(user_id=user_id, ip_address=ip)
        db.session.add(log_entry)
        db.session.commit()
    except Exception:
        db.session.rollback()


def parse_visible_roles(visible_roles_str):
    """
    Parse visible_roles field.
    Returns 'all' or a list like ['super_admin', 'dept_admin'].
    """
    if not visible_roles_str or visible_roles_str == 'all':
        return 'all'
    try:
        return json.loads(visible_roles_str)
    except (json.JSONDecodeError, TypeError):
        return 'all'


def check_visible(visible_roles_str, user_role):
    """Check if a user role can see content with given visible_roles."""
    if user_role == 'super_admin':
        return True
    roles = parse_visible_roles(visible_roles_str)
    if roles == 'all':
        return True
    return user_role in roles


def get_pagination(page_param=None, per_page=10):
    """Extract pagination params from request args."""
    if page_param is None:
        page_param = request.args.get('page', 1)
    requested_per_page = request.args.get('per_page', per_page)
    try:
        page = int(page_param)
    except (ValueError, TypeError):
        page = 1
    if page < 1:
        page = 1
    try:
        requested_per_page = int(requested_per_page)
    except (ValueError, TypeError):
        requested_per_page = per_page
    if requested_per_page not in (10, 20, 50, 100):
        requested_per_page = 10
    per_page = requested_per_page
    return page, per_page


def format_file_size(size_bytes):
    """Format byte size to human-readable string."""
    if size_bytes < 1024:
        return str(size_bytes) + ' B'
    elif size_bytes < 1024 * 1024:
        return '{:.1f} KB'.format(size_bytes / 1024.0)
    elif size_bytes < 1024 * 1024 * 1024:
        return '{:.1f} MB'.format(size_bytes / (1024.0 * 1024.0))
    else:
        return '{:.1f} GB'.format(size_bytes / (1024.0 * 1024.0 * 1024.0))


def clean_original_filename(filename, fallback='file'):
    """Keep a readable original filename while removing path/control chars."""
    filename = filename or fallback
    filename = os.path.basename(filename.replace('\\', '/')).strip()
    filename = unicodedata.normalize('NFKC', filename)
    filename = re.sub(r'[\x00-\x1f<>:"/\\|?*]+', '_', filename)
    filename = filename.strip(' ._')
    if not filename:
        filename = fallback
    return filename[:240]


def get_file_extension(filename):
    """Return lowercase extension without dot, preserving multi-byte filenames."""
    filename = clean_original_filename(filename)
    if '.' not in filename:
        return ''
    return filename.rsplit('.', 1)[1].lower()


def append_extension(filename, ext):
    """Ensure filename ends with the requested extension."""
    filename = clean_original_filename(filename)
    ext = (ext or '').lstrip('.').lower()
    if not ext:
        return filename
    if filename.lower().endswith('.' + ext):
        return filename
    if '.' in filename:
        filename = filename.rsplit('.', 1)[0]
    filename = filename.strip(' ._') or 'file'
    return filename + '.' + ext


def ascii_download_fallback(filename):
    """Build an ASCII fallback filename for older browsers."""
    fallback = secure_filename(filename) or 'download'
    return fallback.replace('"', '')


def content_disposition(filename):
    """Attachment header with RFC 5987 filename* for Chinese filenames."""
    filename = clean_original_filename(filename, 'download')
    fallback = ascii_download_fallback(filename)
    return "attachment; filename=\"{}\"; filename*=UTF-8''{}".format(
        fallback,
        quote(filename.encode('utf-8'))
    )


def get_status_label(status):
    """Map status code to display label."""
    labels = {
        'pending': 'Pending',
        'accepted': 'In Progress',
        'processing': 'In Progress',
        'transferring': 'Transferring',
        'completed': 'Completed',
        'rejected': 'Rejected',
        'archived': 'Archived',
        'approved': 'Approved',
        'published': 'Published',
        'expired': 'Expired',
        'high': 'High',
        'medium': 'Medium',
        'low': 'Low'
    }
    return labels.get(status, status)
