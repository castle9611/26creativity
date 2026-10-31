# -*- coding: utf-8 -*-
"""
Admin blueprint (super_admin only).
User management / Tab management / Column management / Shared folders /
Operation logs / System config.
"""
import json
from datetime import datetime
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, jsonify)
from werkzeug.security import generate_password_hash
from app.extensions import db
from app.models import (User, Tab, Column, BulletinCategory,
                        OperationLog, SharedFolder, SystemConfig, QuickLink, RegistrationRequest)
from app.decorators import login_required, require_super_admin, require_admin
from app.utils import add_log, get_pagination

admin_bp = Blueprint('admin', __name__)


def _redirect(location):
    """Redirect with no-cache headers to prevent stale data after mutations."""
    resp = redirect(location)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    return resp


def _valid_link_url(link_url):
    return link_url.startswith('http://') or link_url.startswith('https://')


# ==================== User Management ====================

@admin_bp.route('/registrations')
@login_required
@require_super_admin
def registrations():
    """Review account applications using the existing user-management permission."""
    import secrets
    status = request.args.get('status', 'pending')
    if status not in ('pending', 'approved', 'rejected'):
        status = 'pending'
    if 'registration_token' not in session:
        session['registration_token'] = secrets.token_hex(24)
    page, per_page = get_pagination()
    applications = RegistrationRequest.query.filter_by(status=status).order_by(
        RegistrationRequest.created_at.desc(), RegistrationRequest.id.desc()).paginate(
            page=page, per_page=per_page, error_out=False)
    return render_template('admin/registrations.html', applications=applications, status=status,
                           registration_token=session['registration_token'])


@admin_bp.route('/registrations/<int:application_id>/review', methods=['POST'])
@login_required
@require_super_admin
def review_registration(application_id):
    """Atomically approve an application and create an ordinary account, or reject it."""
    import secrets
    from flask import abort
    from sqlalchemy.exc import IntegrityError
    if not secrets.compare_digest(request.form.get('registration_token', '').encode('utf-8'), (session.get('registration_token', '') or 'missing').encode('utf-8')):
        abort(400)
    application = RegistrationRequest.query.get_or_404(application_id)
    action = request.form.get('action', '')
    note = request.form.get('review_note', '').strip()
    if action not in ('approve', 'reject') or len(note) > 500 or (action == 'reject' and not note):
        flash('\u8bf7\u9009\u62e9\u6709\u6548\u64cd\u4f5c\uff0c\u9a73\u56de\u65f6\u9700\u586b\u5199\u539f\u56e0\uff08500\u5b57\u4ee5\u5185\uff09', 'warning')
        return _redirect(url_for('admin.registrations'))
    changed = RegistrationRequest.query.filter_by(id=application_id, status='pending').update({
        'status': 'approved' if action == 'approve' else 'rejected', 'reviewed_at': datetime.utcnow(),
        'reviewed_by': session['user_id'], 'review_note': note}, synchronize_session=False)
    if not changed:
        db.session.rollback()
        flash('\u8be5\u7533\u8bf7\u5df2\u5ba1\u6838\uff0c\u8bf7\u52ff\u91cd\u590d\u64cd\u4f5c', 'warning')
        return _redirect(url_for('admin.registrations'))
    if action == 'approve':
        db.session.add(User(username=application.username, real_name=application.real_name,
                            department=application.department, password_hash=application.password_hash,
                            role='user', is_active=1))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash('\u8be5\u7528\u6237\u540d\u5df2\u5b58\u5728\uff0c\u672a\u901a\u8fc7\u7533\u8bf7\uff0c\u8bf7\u6838\u5bf9\u540e\u5904\u7406', 'warning')
        return _redirect(url_for('admin.registrations'))
    add_log('approve_registration' if action == 'approve' else 'reject_registration',
            'registration_request', application_id, 'Registration reviewed: ' + application.username)
    flash('\u5df2\u901a\u8fc7\u6ce8\u518c\u7533\u8bf7\uff0c\u7533\u8bf7\u4eba\u73b0\u53ef\u767b\u5f55' if action == 'approve' else '\u5df2\u9a73\u56de\u6ce8\u518c\u7533\u8bf7', 'success')
    return _redirect(url_for('admin.registrations'))

@admin_bp.route('/users')
@login_required
@require_super_admin
def users():
    """User list with search and role filter."""
    page, per_page = get_pagination()
    search = request.args.get('search', '').strip()
    role_filter = request.args.get('role', '').strip()

    query = User.query
    if search:
        query = query.filter(
            db.or_(
                User.username.like('%' + search + '%'),
                User.real_name.like('%' + search + '%'),
                User.department.like('%' + search + '%')
            )
        )
    if role_filter:
        query = query.filter(User.role == role_filter)

    query = query.order_by(User.role.asc(), User.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    users_list = pagination.items

    # User statistics
    total_users = User.query.filter(User.is_active == 1).count()
    super_admin_count = User.query.filter(User.role == 'super_admin', User.is_active == 1).count()
    dept_admin_count = User.query.filter(User.role == 'dept_admin', User.is_active == 1).count()
    normal_user_count = User.query.filter(User.role == 'user', User.is_active == 1).count()

    return render_template('admin/users.html',
                           users=users_list,
                           pagination=pagination,
                           search=search,
                           role_filter=role_filter,
                           total_users=total_users,
                           super_admin_count=super_admin_count,
                           dept_admin_count=dept_admin_count,
                           normal_user_count=normal_user_count)


@admin_bp.route('/users/export')
@login_required
@require_super_admin
def users_export():
    """Export filtered user information as an Excel-compatible UTF-8 CSV."""
    import csv
    import io
    from flask import make_response

    search = request.args.get('search', '').strip()
    role_filter = request.args.get('role', '').strip()
    query = User.query
    if search:
        query = query.filter(db.or_(
            User.username.like('%' + search + '%'),
            User.real_name.like('%' + search + '%'),
            User.department.like('%' + search + '%')
        ))
    if role_filter:
        query = query.filter(User.role == role_filter)

    role_labels = {'super_admin': '超级管理员', 'dept_admin': '部门管理员', 'user': '普通用户'}
    output = io.StringIO()
    writer = csv.writer(output, lineterminator='\r\n')
    writer.writerow(['用户ID', '用户名', '姓名', '角色', '部门', '状态', '创建时间', '更新时间'])
    rows = query.order_by(User.role.asc(), User.created_at.desc()).all()
    for user in rows:
        writer.writerow([
            user.id, user.username, user.real_name or '', role_labels.get(user.role, user.role),
            user.department or '', '启用' if user.is_active else '禁用',
            user.created_at.strftime('%Y-%m-%d %H:%M:%S') if user.created_at else '',
            user.updated_at.strftime('%Y-%m-%d %H:%M:%S') if user.updated_at else '',
        ])
    add_log('export_users', 'user', 0, 'Exported {} users'.format(len(rows)))
    response = make_response('\ufeff' + output.getvalue())
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = 'attachment; filename=users_{}.csv'.format(
        datetime.now().strftime('%Y%m%d_%H%M%S'))
    return response


@admin_bp.route('/users/add', methods=['POST'])
@login_required
@require_super_admin
def user_add():
    """Add a new user."""
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    real_name = request.form.get('real_name', '').strip()
    role = request.form.get('role', 'user').strip()
    department = request.form.get('department', '').strip()

    if not username or not password:
        flash('用户名和密码不能为空', 'warning')
        return _redirect(url_for('admin.users'))

    if User.query.filter_by(username=username).first():
        flash('用户名已存在', 'danger')
        return _redirect(url_for('admin.users'))

    if len(password) < 6:
        flash('密码长度不能少于6位', 'warning')
        return _redirect(url_for('admin.users'))

    user = User(
        username=username,
        password_hash=generate_password_hash(password),
        real_name=real_name or username,
        role=role,
        department=department
    )
    db.session.add(user)
    db.session.commit()

    add_log('create_user', 'user', user.id,
            'Created user: ' + username + ' role: ' + role)
    flash('用户创建成功', 'success')
    resp = redirect(url_for('admin.users'))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    return resp


@admin_bp.route('/users/<int:user_id>/edit', methods=['POST'])
@login_required
@require_super_admin
def user_edit(user_id):
    """Edit user details."""
    user = User.query.get_or_404(user_id)
    username = request.form.get('username', user.username).strip() or user.username

    if user.username == 'admin' and username != 'admin':
        flash('不允许修改默认超级管理员的用户名', 'danger')
        return _redirect(url_for('admin.users'))

    if username != user.username and User.query.filter(User.username == username, User.id != user.id).first():
        flash('用户名已存在', 'danger')
        return _redirect(url_for('admin.users'))

    user.username = username
    user.real_name = request.form.get('real_name', user.real_name).strip()
    user.role = request.form.get('role', user.role).strip()
    user.department = request.form.get('department', user.department).strip()

    new_password = request.form.get('password', '').strip()
    if new_password:
        if len(new_password) < 6:
            flash('密码长度不能少于6位', 'warning')
            return _redirect(url_for('admin.users'))
        user.password_hash = generate_password_hash(new_password)

    db.session.commit()
    add_log('edit_user', 'user', user.id, 'Edited user: ' + user.username)
    flash('用户信息已更新', 'success')
    return _redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@login_required
@require_super_admin
def user_toggle(user_id):
    """Enable or disable a user."""
    user = User.query.get_or_404(user_id)
    if user.username == 'admin':
        flash('不允许禁用默认超级管理员', 'danger')
        return _redirect(url_for('admin.users'))

    user.is_active = 1 if user.is_active == 0 else 0
    db.session.commit()
    label = 'enabled' if user.is_active else 'disabled'
    add_log('toggle_user', 'user', user.id, label + ' user: ' + user.username)
    flash('User ' + label, 'success')
    return _redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@require_super_admin
def user_delete(user_id):
    """Delete a user."""
    user = User.query.get_or_404(user_id)
    if user.username == 'admin':
        flash('不允许删除默认超级管理员', 'danger')
        return _redirect(url_for('admin.users'))

    username = user.username
    db.session.delete(user)
    db.session.commit()
    add_log('delete_user', 'user', user_id, 'Deleted user: ' + username)
    flash('用户已删除', 'success')
    return _redirect(url_for('admin.users'))


@admin_bp.route('/users/import', methods=['POST'])
@login_required
@require_super_admin
def users_import():
    """Bulk import users from CSV data."""
    import_data = request.form.get('import_data', '')
    if not import_data:
        return jsonify({'success': False, 'message': '没有导入数据'})

    lines = import_data.strip().split('\n')
    if len(lines) < 2:
        return jsonify({'success': False, 'message': 'CSV文件至少需要包含表头和一行数据'})

    role_map = {'1': 'super_admin', '2': 'dept_admin', '3': 'user',
                'super_admin': 'super_admin', 'dept_admin': 'dept_admin', 'user': 'user'}

    success_count = 0
    error_msgs = []
    skip_count = 0

    for i, line in enumerate(lines[1:], start=2):  # Skip header
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        # Parse CSV line (handle quoted fields)
        cols = []
        current = ''
        in_quote = False
        for char in line:
            if char == '"' and not in_quote:
                in_quote = True
            elif char == '"' and in_quote:
                in_quote = False
            elif char == ',' and not in_quote:
                cols.append(current.strip())
                current = ''
            else:
                current += char
        cols.append(current.strip())

        if len(cols) < 2:
            error_msgs.append(f'行{i}: 格式错误')
            continue

        username = cols[0]
        real_name = cols[1] if len(cols) > 1 else username
        password = cols[2] if len(cols) > 2 else ''
        role_str = cols[3] if len(cols) > 3 else 'user'
        department = cols[4] if len(cols) > 4 else ''
        status_str = cols[5] if len(cols) > 5 else '1'

        if not username:
            error_msgs.append(f'行{i}: 用户名为空')
            continue

        if not password or len(password) < 6:
            error_msgs.append(f'行{i}: 密码长度不足6位')
            continue

        # Check if user exists
        if User.query.filter_by(username=username).first():
            error_msgs.append(f'行{i}: 用户名 {username} 已存在')
            skip_count += 1
            continue

        role = role_map.get(role_str, 'user')
        is_active = 1 if status_str == '1' else 0

        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            real_name=real_name,
            role=role,
            department=department,
            is_active=is_active
        )
        db.session.add(user)
        success_count += 1

    if success_count > 0:
        db.session.commit()
        add_log('bulk_import', 'user', 0, f'Bulk imported {success_count} users')
        return jsonify({'success': True, 'count': success_count, 'skip': skip_count})

    return jsonify({'success': False, 'message': '没有导入任何用户'})


# ==================== Tab Management ====================

# ==================== Column Management ====================

@admin_bp.route('/columns')
@login_required
@require_admin
def columns():
    """Column list grouped by category — click category to drill in."""
    category_id = request.args.get('category_id', 0, type=int)
    categories_list = BulletinCategory.query.filter_by(is_active=1).order_by(BulletinCategory.sort_order.asc()).all()

    # Auto-select first category if none selected
    if not category_id and categories_list:
        category_id = categories_list[0].id

    # Count columns per category
    from sqlalchemy import func
    cat_counts = dict(db.session.query(Column.category_id, func.count(Column.id))
                      .filter(Column.category_id.isnot(None)).group_by(Column.category_id).all())

    # Get columns for selected category
    columns_list = []
    current_category = None
    if category_id:
        current_category = BulletinCategory.query.get(category_id)
        columns_list = Column.query.filter_by(category_id=category_id).order_by(
            Column.sort_order.asc(), Column.id.asc()).all()

    return render_template('admin/columns.html',
                           columns=columns_list,
                           categories=categories_list,
                           current_category=current_category,
                           current_category_id=category_id,
                           cat_counts=cat_counts)


@admin_bp.route('/columns/add', methods=['POST'])
@login_required
@require_admin
def column_add():
    """Add a new column."""
    category_id = request.form.get('category_id', 0, type=int)
    name = request.form.get('name', '').strip()

    if not category_id or not name:
        flash('请选择业务类别并填写栏目名称', 'warning')
        return redirect(url_for('admin.columns'))

    col = Column(
        category_id=category_id,
        name=name,
        description=request.form.get('description', '').strip(),
        sort_order=request.form.get('sort_order', 0, type=int),
        is_active=int(request.form.get('is_active', 1)),
        visible_roles=request.form.get('visible_roles', 'all').strip(),
        created_by=session['user_id']
    )
    db.session.add(col)
    db.session.commit()

    from app.nextcloud import ensure_business_folder
    ensure_business_folder(col.category, col)

    add_log('create_column', 'column', col.id, 'Created column: ' + name)
    flash('栏目创建成功', 'success')
    return redirect(url_for('admin.columns', category_id=category_id))


@admin_bp.route('/columns/<int:column_id>/edit', methods=['POST'])
@login_required
@require_admin
def column_edit(column_id):
    """Edit a column."""
    col = Column.query.get_or_404(column_id)
    name = request.form.get('name', '').strip()
    if name:
        col.name = name
    col.category_id = request.form.get('category_id', col.category_id, type=int)
    col.description = request.form.get('description', '').strip()
    col.sort_order = int(request.form.get('sort_order', col.sort_order))
    col.is_active = int(request.form.get('is_active', col.is_active))
    col.visible_roles = request.form.get('visible_roles', col.visible_roles).strip()

    db.session.commit()
    from app.nextcloud import ensure_business_folder
    ensure_business_folder(col.category, col)
    add_log('edit_column', 'column', col.id, 'Edited column: ' + col.name)
    flash('栏目更新成功', 'success')
    return redirect(url_for('admin.columns', category_id=col.category_id))


@admin_bp.route('/columns/<int:column_id>/delete', methods=['POST'])
@login_required
@require_admin
def column_delete(column_id):
    """Delete a column."""
    col = Column.query.get_or_404(column_id)
    category_id = col.category_id
    name = col.name
    db.session.delete(col)
    db.session.commit()
    add_log('delete_column', 'column', column_id, 'Deleted column: ' + name)
    flash('栏目已删除', 'success')
    return redirect(url_for('admin.columns', category_id=category_id))


@admin_bp.route('/columns/batch-delete', methods=['POST'])
@login_required
@require_admin
def batch_delete_columns():
    """Batch delete columns."""
    try:
        if request.content_type and 'json' in request.content_type:
            ids = request.get_json().get('ids', [])
        else:
            ids = json.loads(request.form.get('ids', '[]'))
    except Exception as e:
        return jsonify({'success': False, 'message': '参数错误: ' + str(e)}), 400

    if not ids:
        return jsonify({'success': False, 'message': '请选择栏目'}), 400

    count = 0
    for col_id in ids:
        col = Column.query.get(int(col_id))
        if col:
            db.session.delete(col)
            count += 1

    db.session.commit()
    return jsonify({'success': True, 'message': '已删除 {} 个栏目'.format(count)})



# ==================== Shared Folders ====================

@admin_bp.route('/shares')
@login_required
@require_super_admin
def shares():
    """Shared folder list."""
    folders = SharedFolder.query.order_by(SharedFolder.sort_order.asc()).all()
    return render_template('admin/shares.html', folders=folders)


@admin_bp.route('/shares/add', methods=['POST'])
@login_required
@require_super_admin
def share_add():
    """Add a shared folder."""
    name = request.form.get('name', '').strip()
    folder_path = request.form.get('folder_path', '').strip()

    if not name or not folder_path:
        flash('名称和路径不能为空', 'warning')
        return redirect(url_for('admin.shares'))

    folder = SharedFolder(
        name=name,
        folder_path=folder_path,
        sort_order=request.form.get('sort_order', 0, type=int),
        is_active=int(request.form.get('is_active', 1)),
        visible_roles=request.form.get('visible_roles', 'all').strip(),
        created_by=session['user_id']
    )
    db.session.add(folder)
    db.session.commit()

    add_log('create_share', 'shared_folder', folder.id,
            'Created shared folder: ' + name)
    flash('共享文件夹添加成功', 'success')
    return redirect(url_for('admin.shares'))


@admin_bp.route('/shares/<int:folder_id>/edit', methods=['POST'])
@login_required
@require_super_admin
def share_edit(folder_id):
    """Edit a shared folder."""
    folder = SharedFolder.query.get_or_404(folder_id)
    name = request.form.get('name', '').strip()
    fpath = request.form.get('folder_path', '').strip()
    if name:
        folder.name = name
    if fpath:
        folder.folder_path = fpath
    folder.sort_order = int(request.form.get('sort_order', folder.sort_order))
    folder.is_active = int(request.form.get('is_active', folder.is_active))
    folder.visible_roles = request.form.get('visible_roles', folder.visible_roles).strip()

    db.session.commit()
    add_log('edit_share', 'shared_folder', folder.id,
            'Edited shared folder: ' + folder.name)
    flash('共享文件夹更新成功', 'success')
    return redirect(url_for('admin.shares'))


@admin_bp.route('/shares/<int:folder_id>/delete', methods=['POST'])
@login_required
@require_super_admin
def share_delete(folder_id):
    """Delete a shared folder."""
    folder = SharedFolder.query.get_or_404(folder_id)
    name = folder.name
    db.session.delete(folder)
    db.session.commit()
    add_log('delete_share', 'shared_folder', folder_id,
            'Deleted shared folder: ' + name)
    flash('共享文件夹已删除', 'success')
    return redirect(url_for('admin.shares'))


@admin_bp.route('/shares/batch-delete', methods=['POST'])
@login_required
@require_super_admin
def batch_delete_shares():
    """Batch delete shared folders."""
    try:
        if request.content_type and 'json' in request.content_type:
            ids = request.get_json().get('ids', [])
        else:
            ids = json.loads(request.form.get('ids', '[]'))
    except:
        return jsonify({'success': False, 'message': '参数错误'}), 400

    if not ids:
        return jsonify({'success': False, 'message': '请选择共享文件夹'}), 400

    count = 0
    for fid in ids:
        folder = SharedFolder.query.get(int(fid))
        if folder:
            db.session.delete(folder)
            count += 1

    db.session.commit()
    return jsonify({'success': True, 'message': '已删除 {} 个共享文件夹'.format(count)})


# ==================== Public Quick Links ====================

@admin_bp.route('/quick-links')
@login_required
@require_super_admin
def quick_links():
    """Manage public portal quick links."""
    links = QuickLink.query.filter_by(scope='public').order_by(
        QuickLink.sort_order.asc(), QuickLink.id.asc()
    ).all()
    return render_template('admin/quick_links.html', links=links)


@admin_bp.route('/quick-links/add', methods=['POST'])
@login_required
@require_super_admin
def quick_link_add():
    """Add a public portal quick link."""
    name = request.form.get('name', '').strip()
    link_url = request.form.get('url', '').strip()
    if not name or not link_url:
        flash('名称和链接不能为空', 'warning')
        return redirect(url_for('admin.quick_links'))
    if not _valid_link_url(link_url):
        flash('链接必须以 http:// 或 https:// 开头', 'warning')
        return redirect(url_for('admin.quick_links'))

    link = QuickLink(
        scope='public',
        name=name,
        url=link_url,
        icon=request.form.get('icon', 'gen-link').strip() or 'gen-link',
        sort_order=request.form.get('sort_order', 0, type=int),
        is_active=1 if request.form.get('is_active') else 0,
        created_by=session.get('user_id')
    )
    db.session.add(link)
    db.session.commit()
    add_log('create_quick_link', 'quick_link', link.id, 'Created public quick link: ' + name)
    flash('首页快捷链接已添加', 'success')
    return redirect(url_for('admin.quick_links'))


@admin_bp.route('/quick-links/<int:link_id>/edit', methods=['POST'])
@login_required
@require_super_admin
def quick_link_edit(link_id):
    """Edit a public portal quick link."""
    link = QuickLink.query.filter_by(id=link_id, scope='public').first_or_404()
    name = request.form.get('name', '').strip()
    link_url = request.form.get('url', '').strip()
    if not name or not link_url:
        flash('名称和链接不能为空', 'warning')
        return redirect(url_for('admin.quick_links'))
    if not _valid_link_url(link_url):
        flash('链接必须以 http:// 或 https:// 开头', 'warning')
        return redirect(url_for('admin.quick_links'))

    link.name = name
    link.url = link_url
    link.icon = request.form.get('icon', link.icon).strip() or 'gen-link'
    link.sort_order = request.form.get('sort_order', link.sort_order, type=int)
    link.is_active = int(request.form.get('is_active', link.is_active))
    db.session.commit()
    add_log('edit_quick_link', 'quick_link', link.id, 'Edited public quick link: ' + link.name)
    flash('首页快捷链接已更新', 'success')
    return redirect(url_for('admin.quick_links'))


@admin_bp.route('/quick-links/<int:link_id>/delete', methods=['POST'])
@login_required
@require_super_admin
def quick_link_delete(link_id):
    """Delete a public portal quick link."""
    link = QuickLink.query.filter_by(id=link_id, scope='public').first_or_404()
    name = link.name
    db.session.delete(link)
    db.session.commit()
    add_log('delete_quick_link', 'quick_link', link_id, 'Deleted public quick link: ' + name)
    flash('首页快捷链接已删除', 'success')
    return redirect(url_for('admin.quick_links'))



# ==================== Logs ====================

@admin_bp.route('/logs')
@login_required
@require_super_admin
def logs():
    """Operation log viewer."""
    page, per_page = get_pagination()
    action = request.args.get('action', '').strip()
    uid = request.args.get('user_id', '', type=int)
    target_type = request.args.get('target_type', '').strip()
    keyword = request.args.get('keyword', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    query = OperationLog.query
    if action:
        query = query.filter(OperationLog.action.like('%' + action + '%'))
    if uid:
        query = query.filter(OperationLog.user_id == uid)
    if target_type:
        query = query.filter(OperationLog.target_type == target_type)
    if keyword:
        like = '%' + keyword + '%'
        query = query.filter(db.or_(
            OperationLog.content.like(like),
            OperationLog.ip_address.like(like),
            OperationLog.action.like(like),
            OperationLog.target_type.like(like)
        ))
    if date_from:
        try:
            query = query.filter(OperationLog.created_at >= datetime.strptime(date_from, '%Y-%m-%d'))
        except ValueError:
            pass
    if date_to:
        try:
            query = query.filter(OperationLog.created_at <= datetime.strptime(date_to + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
        except ValueError:
            pass

    query = query.order_by(OperationLog.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    logs_list = pagination.items

    # Build username lookup
    users = User.query.order_by(User.username.asc()).all()
    users_map = {u.id: (u.real_name or u.username) for u in users}
    actions = [r[0] for r in db.session.query(OperationLog.action).distinct().order_by(OperationLog.action.asc()).all()]
    target_types = [r[0] for r in db.session.query(OperationLog.target_type).filter(OperationLog.target_type != '').distinct().order_by(OperationLog.target_type.asc()).all()]

    return render_template('admin/logs.html',
                           logs=logs_list,
                           pagination=pagination,
                           users_dict=users_map,
                           users=users,
                           actions=actions,
                           target_types=target_types,
                           action=action,
                           user_id=uid,
                           target_type=target_type,
                           keyword=keyword,
                           date_from=date_from,
                           date_to=date_to)


@admin_bp.route('/logs/batch-delete', methods=['POST'])
@login_required
@require_super_admin
def batch_delete_logs():
    """Batch delete operation logs."""
    try:
        ids = json.loads(request.form.get('ids', '[]'))
    except:
        return jsonify({'success': False, 'message': '参数错误'}), 400

    ids = [int(i) for i in ids if str(i).isdigit()]
    if not ids:
        return jsonify({'success': False, 'message': '请选择日志'}), 400

    count = OperationLog.query.filter(OperationLog.id.in_(ids)).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({'success': True, 'message': '已删除 {} 条日志'.format(count)})


# ==================== System Config ====================

UI_DEFAULTS = {
    'public_ui_version': '2.0',
    'public_color_scheme': 'navy_portal',
    'public_quick_link_icons': '0',
    'public_quick_link_display': 'hover',
    'public_show_overview': '1',
    'public_slideshow_show': '0',
    'public_slideshow_position': 'bottom',
    'public_slideshow_background_transparency': '100',
    'public_slideshow_images': '[]',
    'public_video_autoplay': '0',
    'public_home_layout': 'classic',
    'public_item_row_height': '50',
    'public_brand_height': '78',
    'public_nav_height': '54',
    'public_search_width': '460',
    'public_page_gutter': '20',
    'public_card_gap': '18',
    'public_card_radius': '9',
    'public_card_padding': '20',
    'public_brand_color': '#071d50',
    'public_page_color': '#F5F7FA'
}
UI_RANGES = {
    'public_slideshow_background_transparency': (0, 100),
    'public_item_row_height': (40, 80),
    'public_brand_height': (72, 100),
    'public_nav_height': (48, 72),
    'public_search_width': (360, 560),
    'public_page_gutter': (12, 48),
    'public_card_gap': (8, 32),
    'public_card_radius': (4, 20),
    'public_card_padding': (16, 32)
}
UI_COLORS = {
    'public_brand_color': ('#071d50', '#123b6f', '#18395b'),
    'public_page_color': ('#F5F7FA', '#F1F5F9', '#FAFBFD')
}


@admin_bp.route('/ui-settings', methods=['GET', 'POST'])
@login_required
@require_super_admin
def ui_settings():
    """Manage public homepage appearance without changing system settings."""
    font_defaults = {'public_font_tab': '16', 'public_font_content': '17'}
    if request.method == 'POST':
        values = {}
        ui_version = request.form.get('config_public_ui_version', UI_DEFAULTS['public_ui_version']).strip()
        if ui_version not in ('1.0', '2.0'):
            flash('请选择有效的 UI 版本', 'warning')
            return redirect(url_for('admin.ui_settings'))
        values['public_ui_version'] = ui_version
        for key, default in font_defaults.items():
            value = request.form.get('config_' + key, default)
            if not value.isdigit() or not 12 <= int(value) <= 32:
                flash('\u5b57\u53f7\u5e94\u4e3a12\u81f332\u50cf\u7d20', 'warning')
                return redirect(url_for('admin.ui_settings'))
            values[key] = value
        scheme = request.form.get('config_public_color_scheme', '').strip()
        if scheme not in ('light', 'navy_portal'):
            flash('请选择有效的首页配色方案', 'warning')
            return redirect(url_for('admin.ui_settings'))
        values['public_color_scheme'] = scheme
        quick_link_icons = request.form.get('config_public_quick_link_icons', '').strip()
        if quick_link_icons not in ('0', '1'):
            flash('请选择是否显示快捷链接图标', 'warning')
            return redirect(url_for('admin.ui_settings'))
        values['public_quick_link_icons'] = quick_link_icons
        for key, choices in (
                ('public_quick_link_display', ('hover', 'always')),
                ('public_slideshow_show', ('0', '1')),
                ('public_slideshow_position', ('middle', 'bottom')),
                ('public_video_autoplay', ('0', '1')),
                ('public_show_overview', ('0', '1'))):
            value = request.form.get('config_' + key, UI_DEFAULTS[key]).strip()
            if value not in choices:
                flash('请选择有效的首页区域显示设置', 'warning')
                return redirect(url_for('admin.ui_settings'))
            values[key] = value
        layout = request.form.get('config_public_home_layout', '').strip()
        if layout not in ('classic', 'columns', 'content_tabs'):
            flash('请选择有效的首页内容布局', 'warning')
            return redirect(url_for('admin.ui_settings'))
        values['public_home_layout'] = layout
        for key, limits in UI_RANGES.items():
            value = request.form.get('config_' + key, UI_DEFAULTS[key]).strip()
            if not value.isdigit() or not limits[0] <= int(value) <= limits[1]:
                flash('UI 参数超出允许范围', 'warning')
                return redirect(url_for('admin.ui_settings'))
            values[key] = value
        for key, choices in UI_COLORS.items():
            value = request.form.get('config_' + key, '').strip()
            if value not in choices:
                flash('请选择有效的配色方案', 'warning')
                return redirect(url_for('admin.ui_settings'))
            values[key] = value
        from app.slideshow import load_slides, store_images
        images_row = SystemConfig.query.filter_by(config_key='public_slideshow_images').first()
        slides = load_slides(images_row.config_value if images_row else '[]')
        removed = request.form.getlist('remove_slide')
        slides = [item for item in slides if item['path'] not in removed]
        uploads = [upload for upload in request.files.getlist('slideshow_images') if upload.filename]
        try:
            new_slides = store_images(uploads)
        except ValueError as exc:
            flash('图片“{}”无法识别，请使用 JPG、PNG、GIF、BMP 或 WebP 图片'.format(str(exc)), 'warning')
            return redirect(url_for('admin.ui_settings'))
        slides.extend(new_slides)
        values['public_slideshow_images'] = json.dumps(slides, ensure_ascii=False)
        for key, value in values.items():
            cfg = SystemConfig.query.filter_by(config_key=key).first()
            if cfg:
                cfg.config_value = value
            else:
                db.session.add(SystemConfig(config_key=key, config_value=value))
        db.session.commit()
        add_log('update_config', 'system_config', 0, 'UI settings updated')
        flash('UI 设置已保存', 'success')
        return redirect(url_for('admin.ui_settings'))
    configs = dict(UI_DEFAULTS)
    configs.update(font_defaults)
    configs.update({item.config_key: item.config_value for item in
                    SystemConfig.query.filter(SystemConfig.config_key.in_(configs)).all()})
    from app.slideshow import load_slides
    return render_template('admin/ui_settings.html', configs=configs,
                           slideshow_images=load_slides(configs['public_slideshow_images']))

@admin_bp.route('/slideshow', methods=['GET', 'POST'])
@login_required
@require_super_admin
def slideshow():
    """Manage image uploads and paginated ordering independently of UI settings."""
    import hashlib
    from app.slideshow import load_slides, store_images
    row = SystemConfig.query.filter_by(config_key='public_slideshow_images').first()
    stored = row.config_value if row else '[]'
    images = load_slides(stored)
    revision = hashlib.sha256(stored.encode('utf-8')).hexdigest()
    page = max(1, request.values.get('page', 1, type=int))
    per_page = 12
    page = min(page, max(1, (len(images) + per_page - 1) // per_page))
    offset = (page - 1) * per_page
    if request.method == 'POST':
        action = request.form.get('action', '')
        if action != 'upload' and request.form.get('revision') != revision:
            flash('图片列表已发生变化，请刷新后重新操作', 'warning')
            return redirect(url_for('admin.slideshow', page=page))
        if action == 'upload':
            errors = []
            try:
                additions = store_images(request.files.getlist('slideshow_images'), errors=errors)
            except OSError:
                from flask import current_app
                current_app.logger.exception('Slideshow image storage failed')
                flash('图片保存失败，请检查上传目录是否可写及磁盘剩余空间', 'warning')
                return redirect(url_for('admin.slideshow', page=page))
            if errors:
                flash('已添加 {} 张图片；{} 张无法识别：{}。支持 JPG、PNG、GIF、BMP、WebP。'.format(
                    len(additions), len(errors), '、'.join(errors[:3])), 'warning')
            if not additions:
                if not errors:
                    flash('请先选择需要添加的图片', 'warning')
                return redirect(url_for('admin.slideshow', page=page))
            images.extend(additions)
            page = max(1, (len(images) + per_page - 1) // per_page)
        elif action == 'remove':
            removed = set(request.form.getlist('selected'))
            if not removed:
                flash('请先勾选需要移除的图片', 'warning')
                return redirect(url_for('admin.slideshow', page=page))
            images = [image for image in images if image['path'] not in removed]
        elif action == 'reorder':
            try:
                order = json.loads(request.form.get('order', '[]'))
            except ValueError:
                order = []
            current = images[offset:offset + per_page]
            by_path = {image['path']: image for image in current}
            if not isinstance(order, list) or not all(isinstance(path, str) for path in order) or len(order) != len(current) or set(order) != set(by_path):
                flash('排序信息无效，请刷新后重试', 'warning')
                return redirect(url_for('admin.slideshow', page=page))
            images[offset:offset + per_page] = [by_path[path] for path in order]
        else:
            return jsonify({'success': False, 'message': '操作无效'}), 400
        if row is None:
            row = SystemConfig(config_key='public_slideshow_images')
            db.session.add(row)
        row.config_value = json.dumps(images, ensure_ascii=False)
        db.session.commit()
        add_log('update_slideshow', 'system_config', row.id, 'Slideshow images: ' + action)
        return redirect(url_for('admin.slideshow', page=page))
    return render_template('admin/slideshow.html', images=images[offset:offset + per_page],
                           total=len(images), page=page, pages=max(1, (len(images) + per_page - 1) // per_page),
                           offset=offset, revision=revision)


@admin_bp.route('/config', methods=['GET', 'POST'])
@login_required
@require_super_admin
def config():
    """System configuration page."""
    if request.method == 'POST':
        load_groups = request.form.get('load_groups') == '1'
        share_groups = request.form.getlist('config_nextcloud_share_groups')
        file_share_groups = request.form.getlist('config_nextcloud_file_share_groups')
        nextcloud_url = request.form.get('config_nextcloud_url', '').strip().rstrip('/')
        if nextcloud_url and not (nextcloud_url.startswith('http://') or nextcloud_url.startswith('https://')):
            flash('Nextcloud 地址必须以 http:// 或 https:// 开头', 'warning')
            return redirect(url_for('admin.config'))
        for key, value in request.form.items():
            if key.startswith('config_'):
                cfg_key = key[7:]
                if cfg_key in UI_DEFAULTS:
                    continue
                if cfg_key in ('nextcloud_share_groups', 'nextcloud_file_share_groups'):
                    continue
                if cfg_key == 'nextcloud_app_password' and not value.strip():
                    continue
                if cfg_key == 'nextcloud_url':
                    value = nextcloud_url
                cfg = SystemConfig.query.filter_by(config_key=cfg_key).first()
                if cfg:
                    cfg.config_value = value.strip()
                else:
                    cfg = SystemConfig(config_key=cfg_key,
                                       config_value=value.strip())
                    db.session.add(cfg)

        groups_value = json.dumps(share_groups, ensure_ascii=False)
        groups_cfg = SystemConfig.query.filter_by(config_key='nextcloud_share_groups').first()
        if groups_cfg:
            groups_cfg.config_value = groups_value
        else:
            db.session.add(SystemConfig(config_key='nextcloud_share_groups',
                                        config_value=groups_value))
        file_groups_value = json.dumps(file_share_groups, ensure_ascii=False)
        file_groups_cfg = SystemConfig.query.filter_by(
            config_key='nextcloud_file_share_groups').first()
        if file_groups_cfg:
            file_groups_cfg.config_value = file_groups_value
        else:
            db.session.add(SystemConfig(config_key='nextcloud_file_share_groups',
                                        config_value=file_groups_value))

        db.session.commit()
        add_log('update_config', 'system_config', 0, 'System config updated')
        if load_groups:
            # The group picker must use the credentials currently visible in
            # the form, including a newly entered application password.
            return redirect(url_for('admin.config', load_groups=1))
        flash('系统配置已保存', 'success')
        return redirect(url_for('admin.config'))

    configs_list = SystemConfig.query.all()
    config_dict = {c.config_key: c.config_value for c in configs_list}

    try:
        selected_share_groups = json.loads(config_dict.get('nextcloud_share_groups', '[]'))
    except (TypeError, ValueError):
        selected_share_groups = []
    try:
        selected_file_share_groups = json.loads(
            config_dict.get('nextcloud_file_share_groups', '[]'))
    except (TypeError, ValueError):
        selected_file_share_groups = []
    nextcloud_groups = []
    nextcloud_groups_error = ''
    if request.args.get('load_groups') == '1':
        from app.nextcloud import list_share_groups
        nextcloud_groups, nextcloud_groups_error = list_share_groups()
    nextcloud_groups = sorted(set(
        nextcloud_groups + selected_share_groups + selected_file_share_groups))

    from app.models import File
    from app.models import CloudAttachment
    stats = {
        'user_count': User.query.count(),
        'tab_count': Tab.query.count(),
        'column_count': Column.query.count(),
        'log_count': OperationLog.query.count(),
        'file_count': File.query.filter_by(is_deleted=0).count(),
        'cloud_synced': CloudAttachment.query.filter_by(sync_status='synced').count(),
        'cloud_pending': CloudAttachment.query.filter(
            CloudAttachment.sync_status.in_(('pending', 'failed'))).count(),
        'cloud_file_synced': CloudAttachment.query.filter_by(
            target_type='file', sync_status='synced').count(),
        'cloud_file_pending': CloudAttachment.query.filter(
            CloudAttachment.target_type == 'file',
            CloudAttachment.sync_status.in_(('pending', 'failed'))).count()
    }

    return render_template('admin/config.html',
                           configs=config_dict,
                           stats=stats,
                           nextcloud_groups=nextcloud_groups,
                           selected_share_groups=selected_share_groups,
                           selected_file_share_groups=selected_file_share_groups,
                           nextcloud_groups_error=nextcloud_groups_error)


@admin_bp.route('/config/nextcloud/retry', methods=['POST'])
@login_required
@require_super_admin
def retry_nextcloud_attachments():
    """Retry pending/failed attachment mirrors without blocking normal OA work."""
    from app.models import CloudAttachment
    from app.nextcloud import sync_attachment
    records = CloudAttachment.query.filter(
        CloudAttachment.sync_status.in_(('pending', 'failed'))
    ).order_by(CloudAttachment.created_at.asc()).limit(100).all()
    synced = 0
    sync_context = {'folder_cache': set(), 'share_cache': set()}
    for record in records:
        if sync_attachment(record, sync_context):
            synced += 1
    db.session.commit()
    add_log('retry_nextcloud_sync', 'cloud_attachment', 0,
            'Retried {} cloud attachments, {} synced'.format(len(records), synced))
    flash('已重试 {} 个附件，成功同步 {} 个'.format(len(records), synced),
          'success' if synced == len(records) else 'warning')
    return redirect(url_for('admin.config'))


@admin_bp.route('/config/nextcloud/queue-history', methods=['POST'])
@login_required
@require_super_admin
def queue_nextcloud_history():
    """Queue existing task, bulletin and memo attachments for controlled migration."""
    import os
    from flask import current_app
    from app.models import Task, BulletinAttachment, File, CloudAttachment
    from app.nextcloud import queue_attachment

    before = CloudAttachment.query.count()
    root = current_app.root_path

    def static_path(value):
        relative = (value or '').lstrip('/').replace('/', os.sep)
        if relative.startswith('static' + os.sep):
            relative = relative[len('static' + os.sep):]
        return os.path.abspath(os.path.join(root, 'static', relative))

    for task in Task.query.filter(Task.attachments != '').all():
        try:
            attachments = json.loads(task.attachments or '[]')
        except Exception:
            attachments = []
        for item in attachments:
            path = static_path(item.get('path', ''))
            if os.path.isfile(path):
                queue_attachment('task', task.id, path,
                                 item.get('original') or item.get('name') or os.path.basename(path),
                                 task.creator_id)

    for item in BulletinAttachment.query.all():
        path = static_path(item.file_path)
        if os.path.isfile(path):
            queue_attachment('bulletin', item.bulletin_id, path, item.original_name, item.uploaded_by)

    for item in File.query.filter(File.related_type == 'memo', File.is_deleted == 0).all():
        path = static_path(item.file_path)
        if os.path.isfile(path):
            queue_attachment('memo', item.related_id, path, item.original_name, item.uploaded_by)

    db.session.commit()
    added = CloudAttachment.query.count() - before
    add_log('queue_nextcloud_history', 'cloud_attachment', 0,
            'Queued {} historical attachments'.format(added))
    flash('已新增 {} 个历史附件到待同步队列，请点击“重试待同步附件”分批上传'.format(added), 'success')
    return redirect(url_for('admin.config'))


@admin_bp.route('/config/nextcloud/sync-folders', methods=['POST'])
@login_required
@require_super_admin
def sync_nextcloud_folders():
    """Create all missing category/column folders; deliberately never delete extras."""
    from app.nextcloud import sync_business_folders
    try:
        count, error = sync_business_folders()
        if error:
            flash(error, 'warning')
        else:
            add_log('sync_nextcloud_folders', 'system_config', 0,
                    'Ensured {} Nextcloud folders'.format(count))
            flash('已检查并补齐 {} 个分类/栏目目录；云端冗余内容未作任何删除'.format(count), 'success')
    except Exception as exc:
        flash('Nextcloud 目录同步失败：' + str(exc), 'warning')
    return redirect(url_for('admin.config'))


@admin_bp.route('/config/nextcloud/sync-files', methods=['POST'])
@login_required
@require_super_admin
def sync_nextcloud_files():
    """Queue all active file-manager content and upload a controlled batch."""
    import os
    from app.config import BASE_DIR
    from app.models import File, CloudAttachment
    from app.nextcloud import (queue_attachment, sync_attachment,
                               sync_managed_file_shares, managed_file_cloud_path)

    sync_context = {'folder_cache': set(), 'share_cache': set()}
    try:
        share_roots = sync_managed_file_shares(sync_context)
    except Exception as exc:
        flash('文件资料分组分享补齐失败：' + str(exc), 'warning')
        return redirect(url_for('admin.config'))

    queued = 0
    skipped = 0
    missing = 0
    for item in File.query.filter_by(is_deleted=0).order_by(File.id.asc()).all():
        relative = (item.file_path or '').replace('/', os.sep)
        local_path = os.path.realpath(os.path.join(BASE_DIR, relative))
        if (os.path.commonpath([os.path.realpath(BASE_DIR), local_path]) != os.path.realpath(BASE_DIR)
                or not os.path.isfile(local_path)):
            missing += 1
            continue
        record = queue_attachment('file', item.id, local_path, item.original_name, item.uploaded_by)
        expected_path = managed_file_cloud_path(item)
        if record.sync_status == 'synced' and record.cloud_path == expected_path:
            skipped += 1
        else:
            record.sync_status = 'pending'
            record.sync_error = ''
            queued += 1
    db.session.commit()

    records = CloudAttachment.query.filter_by(
        target_type='file', sync_status='pending').order_by(CloudAttachment.id.asc()).limit(20).all()
    synced = 0
    for record in records:
        if sync_attachment(record, sync_context):
            synced += 1
        db.session.commit()
    remaining = CloudAttachment.query.filter(
        CloudAttachment.target_type == 'file',
        CloudAttachment.sync_status.in_(('pending', 'failed'))).count()
    add_log('sync_nextcloud_files', 'cloud_attachment', 0,
            'Ensured {} share roots, queued {}, skipped {}, synced {}, remaining {}, missing {}'.format(
                share_roots, queued, skipped, synced, remaining, missing))
    flash('已检查 {} 个分享目录；新增/变化 {} 个，跳过未变化 {} 个，本批同步成功 {} 个，剩余/失败 {} 个，本地缺失 {} 个'.format(
        share_roots, queued, skipped, synced, remaining, missing),
        'success' if remaining == 0 else 'warning')
    return redirect(url_for('admin.config'))


def _parse_ids():
    """Extract IDs from request (supports JSON body and form-encoded)."""
    if request.content_type and 'json' in request.content_type:
        return request.get_json().get('ids', [])
    return json.loads(request.form.get('ids', '[]'))


# ==================== Batch User Operations ====================

@admin_bp.route('/users/batch-delete', methods=['POST'])
@login_required
@require_super_admin
def batch_delete_users():
    """Batch delete users."""
    from flask import jsonify

    try:
        ids = _parse_ids()
    except:
        return jsonify({'success': False, 'message': '参数错误'}), 400

    if not ids:
        return jsonify({'success': False, 'message': '请选择用户'}), 400

    # Prevent deleting admin user
    admin_user = User.query.filter_by(username='admin').first()
    if admin_user and admin_user.id in ids:
        ids.remove(admin_user.id)
        if not ids:
            return jsonify({'success': False, 'message': '不能删除admin用户'}), 400

    count = 0
    for user_id in ids:
        user = User.query.get(int(user_id))
        if user and user.username != 'admin':
            db.session.delete(user)
            count += 1

    db.session.commit()
    add_log('batch_delete_users', 'user', 0, 'Deleted {} users'.format(count))

    return jsonify({'success': True, 'message': '已删除 {} 个用户'.format(count)})


@admin_bp.route('/users/batch-update-role', methods=['POST'])
@login_required
@require_super_admin
def batch_update_role():
    """Batch update user roles."""
    from flask import jsonify

    try:
        ids = _parse_ids()
    except:
        return jsonify({'success': False, 'message': '参数错误'}), 400

    new_role = request.form.get('role', '').strip()
    if request.content_type and 'json' in request.content_type:
        new_role = request.get_json().get('role', '').strip()
    if new_role not in ('super_admin', 'dept_admin', 'user'):
        return jsonify({'success': False, 'message': '无效的角色'}), 400

    if not ids:
        return jsonify({'success': False, 'message': '请选择用户'}), 400

    # Prevent changing admin user role
    admin_user = User.query.filter_by(username='admin').first()
    if admin_user and admin_user.id in ids:
        ids.remove(admin_user.id)
        if not ids:
            return jsonify({'success': False, 'message': '不能修改admin用户角色'}), 400

    count = 0
    for user_id in ids:
        user = User.query.get(int(user_id))
        if user and user.username != 'admin':
            user.role = new_role
            count += 1

    db.session.commit()
    add_log('batch_update_role', 'user', 0, 'Updated {} users to role: {}'.format(count, new_role))

    return jsonify({'success': True, 'message': '已修改 {} 个用户的角色'.format(count)})


@admin_bp.route('/users/batch-toggle-status', methods=['POST'])
@login_required
@require_super_admin
def batch_toggle_status():
    """Batch toggle user status (enabled/disabled)."""
    from flask import jsonify

    try:
        ids = _parse_ids()
    except:
        return jsonify({'success': False, 'message': '参数错误'}), 400

    if not ids:
        return jsonify({'success': False, 'message': '请选择用户'}), 400

    # Prevent toggling admin user status
    admin_user = User.query.filter_by(username='admin').first()
    if admin_user and admin_user.id in ids:
        ids.remove(admin_user.id)
        if not ids:
            return jsonify({'success': False, 'message': '不能修改admin用户状态'}), 400

    count = 0
    for user_id in ids:
        user = User.query.get(int(user_id))
        if user and user.username != 'admin':
            user.is_active = 0 if user.is_active else 1
            count += 1

    db.session.commit()
    add_log('batch_toggle_status', 'user', 0, 'Toggled status for {} users'.format(count))

    return jsonify({'success': True, 'message': '已切换 {} 个用户的状态'.format(count)})
