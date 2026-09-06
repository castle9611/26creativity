# -*- coding: utf-8 -*-
"""
Settings blueprint - System configuration and category management.
"""
from flask import Blueprint, render_template, request, session, redirect, url_for, flash, jsonify
from app.extensions import db
from app.decorators import login_required
from app.models import BulletinCategory, Tab, Column

settings_bp = Blueprint('settings', __name__)


@settings_bp.route('/settings')
@login_required
def index():
    """Settings overview page."""
    user_role = session.get('role', '')
    if user_role not in ('super_admin', 'dept_admin'):
        flash('您没有权限访问系统设置', 'error')
        return redirect(url_for('index_bp.workbench'))

    return render_template('settings/index.html')


@settings_bp.route('/settings/task-categories')
@login_required
def task_categories():
    """Business category management (shared by tasks and bulletins)."""
    user_role = session.get('role', '')
    if user_role not in ('super_admin', 'dept_admin'):
        flash('您没有权限管理业务类别', 'error')
        return redirect(url_for('index_bp.workbench'))

    return_url = request.args.get('next', '')
    categories = BulletinCategory.query.order_by(BulletinCategory.sort_order.asc(), BulletinCategory.id.asc()).all()
    # Get all tabs for dropdown selection
    tabs = Tab.query.filter_by(tab_type='bulletin').order_by(Tab.sort_order.asc()).all()
    return render_template('settings/task_categories.html', categories=categories, tabs=tabs, return_url=return_url)


@settings_bp.route('/settings/task-categories/create', methods=['POST'])
@login_required
def create_task_category():
    """Create a new business category (shared by tasks and bulletins)."""
    user_role = session.get('role', '')
    if user_role not in ('super_admin', 'dept_admin'):
        return jsonify({'success': False, 'message': '权限不足'}), 403

    name = request.form.get('name', '').strip()
    icon = request.form.get('icon', 'cat-production').strip()
    color = request.form.get('color', '#3b82f6').strip()
    tab_id = request.form.get('tab_id', type=int)
    visible_roles = request.form.get('visible_roles', 'all').strip()

    if not name:
        return jsonify({'success': False, 'message': '类别名称不能为空'}), 400

    # Check duplicate
    existing = BulletinCategory.query.filter(BulletinCategory.name == name).first()
    if existing:
        return jsonify({'success': False, 'message': '该类别已存在'}), 400

    # Get max sort order
    max_order = db.session.query(db.func.max(BulletinCategory.sort_order)).scalar() or 0

    category = BulletinCategory(
        name=name,
        icon=icon,
        color=color,
        tab_id=tab_id,
        visible_roles=visible_roles,
        sort_order=max_order + 1,
        created_by=session.get('user_id')
    )
    db.session.add(category)
    db.session.commit()

    from app.nextcloud import ensure_business_folder
    ensure_business_folder(category)

    return jsonify({'success': True, 'message': '创建成功', 'category': category.to_dict()})


@settings_bp.route('/settings/task-categories/<int:cat_id>/edit', methods=['POST'])
@login_required
def edit_task_category(cat_id):
    """Edit a business category."""
    user_role = session.get('role', '')
    if user_role not in ('super_admin', 'dept_admin'):
        return jsonify({'success': False, 'message': '权限不足'}), 403

    category = BulletinCategory.query.get_or_404(cat_id)

    name = request.form.get('name', '').strip()
    icon = request.form.get('icon', 'cat-production').strip()
    color = request.form.get('color', '#3b82f6').strip()
    tab_id = request.form.get('tab_id', type=int)
    visible_roles = request.form.get('visible_roles', 'all').strip()
    is_active = request.form.get('is_active', type=int, default=1)

    if not name:
        return jsonify({'success': False, 'message': '类别名称不能为空'}), 400

    # Check duplicate (exclude self)
    existing = BulletinCategory.query.filter(
        BulletinCategory.name == name,
        BulletinCategory.id != cat_id
    ).first()
    if existing:
        return jsonify({'success': False, 'message': '该类别已存在'}), 400

    category.name = name
    category.icon = icon
    category.color = color
    category.tab_id = tab_id
    category.visible_roles = visible_roles
    category.is_active = is_active
    db.session.commit()

    from app.nextcloud import ensure_business_folder
    ensure_business_folder(category)

    return jsonify({'success': True, 'message': '更新成功', 'category': category.to_dict()})


@settings_bp.route('/settings/task-categories/<int:cat_id>/delete', methods=['POST'])
@login_required
def delete_task_category(cat_id):
    """Delete a business category."""
    user_role = session.get('role', '')
    if user_role not in ('super_admin', 'dept_admin'):
        return jsonify({'success': False, 'message': '权限不足'}), 403

    category = BulletinCategory.query.get_or_404(cat_id)

    # Clear related tasks' category reference first (to avoid FK constraint issues)
    from app.models import Task
    Task.query.filter_by(category_id=cat_id).update({'category_id': None})

    db.session.delete(category)
    db.session.commit()

    return jsonify({'success': True, 'message': '删除成功'})


@settings_bp.route('/settings/task-categories/reorder', methods=['POST'])
@login_required
def reorder_task_categories():
    """Reorder business categories."""
    user_role = session.get('role', '')
    if user_role not in ('super_admin', 'dept_admin'):
        return jsonify({'success': False, 'message': '权限不足'}), 403

    order_ids = request.form.getlist('order_ids')
    for i, cat_id in enumerate(order_ids):
        cat = BulletinCategory.query.get(int(cat_id))
        if cat:
            cat.sort_order = i

    db.session.commit()
    return jsonify({'success': True, 'message': '排序已更新'})


@settings_bp.route('/settings/task-categories/batch-delete', methods=['POST'])
@login_required
def batch_delete_task_categories():
    """Batch delete business categories."""
    from flask import jsonify
    user_role = session.get('role', '')
    if user_role not in ('super_admin', 'dept_admin'):
        return jsonify({'success': False, 'message': '权限不足'}), 403

    try:
        ids = json.loads(request.form.get('ids', '[]'))
    except:
        return jsonify({'success': False, 'message': '参数错误'}), 400

    if not ids:
        return jsonify({'success': False, 'message': '请选择类别'}), 400

    from app.models import Task
    count = 0
    for cat_id in ids:
        cat = BulletinCategory.query.get(int(cat_id))
        if cat:
            # Clear related tasks first
            Task.query.filter_by(category_id=int(cat_id)).update({'category_id': None})
            db.session.delete(cat)
            count += 1

    db.session.commit()
    return jsonify({'success': True, 'message': '已删除 {} 个类别'.format(count)})


# Redirect bulletin_categories to task_categories (they share the same data)
@settings_bp.route('/settings/bulletin-categories')
@login_required
def bulletin_categories():
    """Redirect to task categories (same data)."""
    return redirect(url_for('settings.task_categories'))


@settings_bp.route('/settings/bulletin-categories/create', methods=['POST'])
@login_required
def create_bulletin_category():
    """Create bulletin category - redirects to task category creation."""
    return redirect(url_for('settings.task_categories'))


@settings_bp.route('/settings/bulletin-categories/<int:cat_id>/edit', methods=['POST'])
@login_required
def edit_bulletin_category(cat_id):
    """Edit a bulletin category."""
    user_role = session.get('role', '')
    if user_role not in ('super_admin', 'dept_admin'):
        return jsonify({'success': False, 'message': '权限不足'}), 403

    category = BulletinCategory.query.get_or_404(cat_id)

    name = request.form.get('name', '').strip()
    icon = request.form.get('icon', 'cat-notice').strip()
    color = request.form.get('color', '#10b981').strip()
    tab_id = request.form.get('tab_id', type=int)
    visible_roles = request.form.get('visible_roles', 'all')

    if not name:
        return jsonify({'success': False, 'message': '类别名称不能为空'}), 400

    # Check duplicate (exclude self)
    existing = BulletinCategory.query.filter(
        BulletinCategory.name == name,
        BulletinCategory.id != cat_id
    ).first()
    if existing:
        return jsonify({'success': False, 'message': '该类别已存在'}), 400

    category.name = name
    category.icon = icon
    category.color = color
    category.tab_id = tab_id
    category.visible_roles = visible_roles
    db.session.commit()

    return jsonify({'success': True, 'message': '更新成功', 'category': category.to_dict()})


@settings_bp.route('/settings/bulletin-categories/<int:cat_id>/delete', methods=['POST'])
@login_required
def delete_bulletin_category(cat_id):
    """Delete a bulletin category."""
    user_role = session.get('role', '')
    if user_role not in ('super_admin', 'dept_admin'):
        return jsonify({'success': False, 'message': '权限不足'}), 403

    category = BulletinCategory.query.get_or_404(cat_id)
    db.session.delete(category)
    db.session.commit()

    return jsonify({'success': True, 'message': '删除成功'})


@settings_bp.route('/settings/bulletin-categories/reorder', methods=['POST'])
@login_required
def reorder_bulletin_categories():
    """Reorder bulletin categories."""
    user_role = session.get('role', '')
    if user_role not in ('super_admin', 'dept_admin'):
        return jsonify({'success': False, 'message': '权限不足'}), 403

    order_ids = request.form.getlist('order_ids')
    for i, cat_id in enumerate(order_ids):
        cat = BulletinCategory.query.get(int(cat_id))
        if cat:
            cat.sort_order = i

    db.session.commit()
    return jsonify({'success': True, 'message': '排序已更新'})


# API endpoints for AJAX
@settings_bp.route('/api/task-categories')
@login_required
def api_task_categories():
    """Get all task categories as JSON."""
    categories = BulletinCategory.query.filter(BulletinCategory.is_active == 1).order_by(BulletinCategory.sort_order.asc()).all()
    return jsonify([c.to_dict() for c in categories])


@settings_bp.route('/api/bulletin-categories')
@login_required
def api_bulletin_categories():
    """Get all bulletin categories as JSON (alias for task categories)."""
    categories = BulletinCategory.query.filter(BulletinCategory.is_active == 1).order_by(BulletinCategory.sort_order.asc()).all()
    return jsonify([c.to_dict() for c in categories])


@settings_bp.route('/settings/bulletin-categories/<int:cat_id>/api')
@login_required
def get_bulletin_category(cat_id):
    """Get single bulletin category as JSON."""
    category = BulletinCategory.query.get_or_404(cat_id)
    return jsonify({'success': True, 'category': category.to_dict()})
