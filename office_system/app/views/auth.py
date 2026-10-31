# -*- coding: utf-8 -*-
"""
Authentication blueprint: login / logout / change password.
"""
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session)
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db
from app.models import User, RegistrationRequest
from app.decorators import login_required
from app.utils import add_log, add_login_log

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Accept a named account application without creating a usable user."""
    import re
    import secrets
    from flask import abort
    from sqlalchemy.exc import IntegrityError
    if session.get('user_id'):
        return redirect(url_for('index_bp.workbench'))
    if 'registration_token' not in session:
        session['registration_token'] = secrets.token_hex(24)
    if request.method == 'POST':
        if not secrets.compare_digest(request.form.get('registration_token', '').encode('utf-8'), session['registration_token'].encode('utf-8')):
            abort(400)
        username = request.form.get('username', '').strip()
        real_name = request.form.get('real_name', '').strip()
        department = request.form.get('department', '').strip()
        password = request.form.get('password', '').strip()
        confirm = request.form.get('confirm_password', '').strip()
        note = request.form.get('application_note', '').strip()
        if not re.fullmatch(r'[A-Za-z0-9_]{3,50}', username):
            flash('\u7528\u6237\u540d\u9700\u4e3a3\u81f350\u4f4d\u5b57\u6bcd\u3001\u6570\u5b57\u6216\u4e0b\u5212\u7ebf', 'warning')
        elif not real_name or len(real_name) > 50 or not department or len(department) > 100:
            flash('\u8bf7\u586b\u5199\u771f\u5b9e\u59d3\u540d\uff0850\u5b57\u4ee5\u5185\uff09\u548c\u90e8\u95e8\uff08100\u5b57\u4ee5\u5185\uff09', 'warning')
        elif not 6 <= len(password) <= 128 or password != confirm:
            flash('\u5bc6\u7801\u9700\u4e3a6\u81f3128\u4f4d\uff0c\u4e24\u6b21\u8f93\u5165\u987b\u4e00\u81f4', 'warning')
        elif len(note) > 500:
            flash('\u7533\u8bf7\u8bf4\u660e\u4e0d\u80fd\u8d85\u8fc7500\u5b57', 'warning')
        elif User.query.filter_by(username=username).first() or RegistrationRequest.query.filter_by(username=username).first():
            flash('\u8be5\u7528\u6237\u540d\u5df2\u88ab\u4f7f\u7528\u6216\u5df2\u63d0\u4ea4\u7533\u8bf7\uff0c\u8bf7\u8054\u7cfb\u7ba1\u7406\u5458', 'warning')
        else:
            application = RegistrationRequest(username=username, real_name=real_name, department=department,
                                              password_hash=generate_password_hash(password), application_note=note)
            db.session.add(application)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash('\u8be5\u7528\u6237\u540d\u5df2\u63d0\u4ea4\u7533\u8bf7\uff0c\u8bf7\u52ff\u91cd\u590d\u63d0\u4ea4', 'warning')
            else:
                add_log('request_registration', 'registration_request', application.id, 'Registration requested: ' + username)
                flash('\u6ce8\u518c\u7533\u8bf7\u5df2\u63d0\u4ea4\uff0c\u8bf7\u7b49\u5f85\u7ba1\u7406\u5458\u5ba1\u6838\u901a\u8fc7\u540e\u518d\u767b\u5f55', 'success')
                return redirect(url_for('auth.login'))
    return render_template('register.html', registration_token=session['registration_token'])


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and handler."""
    if 'user_id' in session:
        return redirect(url_for('index_bp.workbench'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            flash('请输入用户名和密码', 'warning')
            return render_template('login.html')

        user = User.query.filter_by(username=username).first()

        if not user:
            application = RegistrationRequest.query.filter_by(username=username).first()
            if application and check_password_hash(application.password_hash, password):
                if application.status == 'pending':
                    flash('\u6ce8\u518c\u7533\u8bf7\u5f85\u5ba1\u6838\uff0c\u901a\u8fc7\u540e\u624d\u80fd\u767b\u5f55', 'warning')
                elif application.status == 'rejected':
                    flash('\u6ce8\u518c\u7533\u8bf7\u672a\u901a\u8fc7\uff1a' + (application.review_note or '\u8bf7\u8054\u7cfb\u7ba1\u7406\u5458'), 'warning')
                else:
                    flash('\u8d26\u53f7\u4e0d\u5b58\u5728\uff0c\u8bf7\u8054\u7cfb\u7ba1\u7406\u5458', 'warning')
            else:
                flash('用户名或密码错误', 'danger')
            return render_template('login.html')

        if not user.is_active:
            flash('账号已被禁用，请联系管理员', 'danger')
            return render_template('login.html')

        if not check_password_hash(user.password_hash, password):
            flash('用户名或密码错误', 'danger')
            return render_template('login.html')

        # Set session
        session['user_id'] = user.id
        session['username'] = user.username
        session['real_name'] = user.real_name or user.username
        session['role'] = user.role
        session['department'] = user.department or ''
        session['avatar'] = user.avatar or ''

        add_login_log(user.id)
        add_log('login', 'user', user.id, 'User login: ' + user.username)

        flash('登录成功，欢迎 ' + (user.real_name or user.username), 'success')

        next_url = request.args.get('next', '')
        if next_url:
            return redirect(next_url)
        return redirect(url_for('index_bp.workbench'))

    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    """Logout and clear session."""
    if 'user_id' in session:
        add_log('logout', 'user', session['user_id'],
                'User logout: ' + session.get('username', ''))
    session.clear()
    flash('已安全退出', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/api/users')
@login_required
def list_users():
    """Return list of active users for user switcher (JSON)."""
    from flask import jsonify
    users = User.query.filter_by(is_active=1).order_by(User.id.asc()).all()
    return jsonify([{
        'id': u.id,
        'username': u.username,
        'real_name': u.real_name or u.username,
        'role': u.role,
        'department': u.department or ''
    } for u in users])


@auth_bp.route('/api/switch', methods=['GET', 'POST'])
@login_required
def switch_user():
    """Switch to another user account - super_admin only."""
    from flask import jsonify, request
    target_id = request.values.get('user_id', type=int)
    if not target_id:
        return jsonify({'success': False, 'message': '无效的用户'}), 400

    current_role = session.get('role', '')
    current_user_id = session.get('user_id')

    # Only super_admin can switch users
    if current_role != 'super_admin':
        return jsonify({'success': False, 'message': '权限不足'}), 403

    target = User.query.get(target_id)
    if not target:
        return jsonify({'success': False, 'message': '用户不存在'}), 404
    if not target.is_active:
        return jsonify({'success': False, 'message': '用户已被禁用'}), 403

    # Cannot switch to same user or other super_admin
    if target_id == current_user_id:
        return jsonify({'success': False, 'message': '不能切换到自己'}), 400
    if target.role == 'super_admin':
        return jsonify({'success': False, 'message': '不能切换到其他超级管理员'}), 403

    # Log the switch
    add_log('switch_user', 'user', session['user_id'],
            'Switched from ' + session.get('username', '') + ' to ' + target.username)

    # Update session
    session['user_id'] = target.id
    session['username'] = target.username
    session['real_name'] = target.real_name or target.username
    session['role'] = target.role
    session['department'] = target.department or ''

    return jsonify({'success': True})


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """User profile and password change."""
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        action = request.form.get('action', '')

        if action == 'update_info':
            real_name = request.form.get('real_name', '').strip()
            if real_name:
                user.real_name = real_name
                session['real_name'] = real_name
            db.session.commit()
            add_log('update_profile', 'user', user.id,
                    '个人信息已更新: ' + user.username)
            flash('个人信息已更新', 'success')

        elif action == 'upload_avatar':
            if 'avatar' in request.files:
                f = request.files['avatar']
                if f and f.filename:
                    ext = f.filename.rsplit('.', 1)[1].lower() if '.' in f.filename else 'png'
                    if ext not in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
                        flash('不支持的头像格式', 'danger')
                        return redirect(url_for('auth.profile'))
                    import uuid, os
                    from flask import current_app
                    avatar_dir = os.path.join(current_app.root_path, 'static', 'avatars')
                    if not os.path.exists(avatar_dir):
                        os.makedirs(avatar_dir)
                    avatar_name = 'user_' + str(user.id) + '.' + ext
                    avatar_path = os.path.join(avatar_dir, avatar_name)
                    f.save(avatar_path)
                    user.avatar = '/static/avatars/' + avatar_name
                    db.session.commit()
                    session['avatar'] = user.avatar
                    flash('头像已更新', 'success')
            return redirect(url_for('auth.profile'))

        elif action == 'change_password':
            old_pw = request.form.get('old_password', '').strip()
            new_pw = request.form.get('new_password', '').strip()
            confirm_pw = request.form.get('confirm_password', '').strip()

            if not old_pw or not new_pw:
                flash('请填写完整的密码信息', 'warning')
                return render_template('profile.html', user=user)

            if not check_password_hash(user.password_hash, old_pw):
                flash('原密码错误', 'danger')
                return render_template('profile.html', user=user)

            if len(new_pw) < 6:
                flash('密码长度不能少于6位', 'warning')
                return render_template('profile.html', user=user)

            if new_pw != confirm_pw:
                flash('两次输入的密码不一致', 'warning')
                return render_template('profile.html', user=user)

            user.password_hash = generate_password_hash(new_pw)
            db.session.commit()
            add_log('change_password', 'user', user.id,
                    'Password changed: ' + user.username)
            flash('密码修改成功，请重新登录', 'success')
            session.clear()
            return redirect(url_for('auth.login'))

        return redirect(url_for('auth.profile'))

    return render_template('profile.html', user=user)
