# -*- coding: utf-8 -*-
"""
Permission decorators (3-level role system).
super_admin > dept_admin > user
"""
from functools import wraps
from flask import session, redirect, url_for, flash, request


def login_required(f):
    """Require user to be logged in."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                from flask import jsonify
                return jsonify({'code': -1, 'msg': 'Please login first'}), 401
            flash('Please login first', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def require_role(role_name):
    """
    Role-based access control factory.
    super_admin has all permissions automatically.
    :param role_name: 'super_admin' | 'dept_admin' | 'user'
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    from flask import jsonify
                    return jsonify({'code': -1, 'msg': 'Please login first'}), 401
                flash('Please login first', 'warning')
                return redirect(url_for('auth.login'))

            user_role = session.get('role', '')

            # super_admin bypasses all checks
            if user_role == 'super_admin':
                return f(*args, **kwargs)

            if role_name == 'super_admin' and user_role != 'super_admin':
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    from flask import jsonify
                    return jsonify({'code': -1, 'msg': 'Super admin required'}), 403
                flash('Super admin permission required', 'danger')
                return redirect(url_for('index_bp.workbench'))

            if role_name == 'dept_admin' and user_role not in ('super_admin', 'dept_admin'):
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    from flask import jsonify
                    return jsonify({'code': -1, 'msg': 'Dept admin or above required'}), 403
                flash('Dept admin or above permission required', 'danger')
                return redirect(url_for('index_bp.workbench'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_super_admin(f):
    """Shortcut for require_role('super_admin')"""
    return require_role('super_admin')(f)


def require_dept_admin(f):
    """Shortcut for require_role('dept_admin')"""
    return require_role('dept_admin')(f)


def require_admin(f):
    """Shortcut for require_role('dept_admin') - allows super_admin and dept_admin"""
    return require_role('dept_admin')(f)
