# -*- coding: utf-8 -*-
"""
Common query helpers to reduce code duplication and improve performance.
[DEPRECATED] Moved from app/queries.py on 2026-06-09.
This file is preserved for reference — the functions were never imported
by any view or template. Inline equivalents exist in the respective views.
"""
from app.extensions import db
from app.models import User, Task, Bulletin, Column, Tab, Memo, File, SharedFolder
from app.utils import check_visible
from flask import session
from datetime import date


def get_user_role_scope():
    """
    Get current user's role-based query scope.
    Returns a dict with user context for permission filtering.
    """
    user_id = session.get('user_id')
    user_role = session.get('role', '')
    user_dept = session.get('department', '')

    return {
        'user_id': user_id,
        'role': user_role,
        'department': user_dept,
        'is_super_admin': user_role == 'super_admin',
        'is_dept_admin': user_role == 'dept_admin',
        'is_user': user_role == 'user'
    }


def get_visible_tabs(user_role=None):
    """
    Get active tabs visible to user role.

    Args:
        user_role: Role string. If None, gets from session.

    Returns:
        List of Tab objects.
    """
    if user_role is None:
        user_role = session.get('role', '')

    tabs = Tab.query.filter_by(is_active=1).order_by(
        Tab.is_pinned.desc(), Tab.sort_order.asc()
    ).all()

    return [t for t in tabs if check_visible(t.visible_roles, user_role)]


def get_visible_columns(category_id, user_role=None):
    """
    Get active columns for category visible to user role.

    Args:
        category_id: BulletinCategory ID.
        user_role: Role string. If None, gets from session.

    Returns:
        List of Column objects.
    """
    if user_role is None:
        user_role = session.get('role', '')

    columns = Column.query.filter_by(
        category_id=category_id, is_active=1
    ).order_by(Column.sort_order.asc()).all()

    return [c for c in columns if check_visible(c.visible_roles, user_role)]


def build_tabs_columns(user_role=None):
    """
    Build tabs with columns structure for templates.

    Args:
        user_role: Role string. If None, gets from session.

    Returns:
        List of dicts with 'tab' and 'columns' keys.
    """
    if user_role is None:
        user_role = session.get('role', '')

    tabs = get_visible_tabs(user_role)
    return [
        {'tab': tab, 'columns': get_visible_columns(tab.id, user_role)}
        for tab in tabs
    ]


def get_department_user_ids(department):
    """
    Get all user IDs in a department.

    Args:
        department: Department name.

    Returns:
        List of user IDs.
    """
    return [u.id for u in User.query.filter_by(department=department).all()]


def filter_tasks_by_role(query, user_role=None, user_id=None, user_dept=None):
    """
    Apply role-based filtering to Task query.

    Args:
        query: SQLAlchemy query object.
        user_role: Role string. If None, gets from session.
        user_id: User ID. If None, gets from session.
        user_dept: Department. If None, gets from session.

    Returns:
        Filtered query object.
    """
    if user_role is None:
        user_role = session.get('role', '')
    if user_id is None:
        user_id = session.get('user_id')
    if user_dept is None:
        user_dept = session.get('department', '')

    if user_role == 'super_admin':
        pass  # No filter
    elif user_role == 'dept_admin':
        query = query.filter(Task.department == user_dept)
    else:
        query = query.filter(
            db.or_(Task.assignee_id == user_id, Task.creator_id == user_id)
        )

    return query


def filter_files_by_role(query, user_role=None, user_id=None, user_dept=None):
    """
    Apply role-based filtering to File query.

    Args:
        query: SQLAlchemy query object.
        user_role: Role string. If None, gets from session.
        user_id: User ID. If None, gets from session.
        user_dept: Department. If None, gets from session.

    Returns:
        Filtered query object.
    """
    if user_role is None:
        user_role = session.get('role', '')
    if user_id is None:
        user_id = session.get('user_id')
    if user_dept is None:
        user_dept = session.get('department', '')

    if user_role == 'super_admin':
        pass  # No filter
    elif user_role == 'dept_admin':
        dept_user_ids = get_department_user_ids(user_dept)
        query = query.filter(File.uploaded_by.in_(dept_user_ids))
    else:
        query = query.filter(File.uploaded_by == user_id)

    return query


def get_active_bulletins(column_id, user_role=None, limit=None):
    """
    Get active (non-expired) bulletins for a column.

    Args:
        column_id: Column ID.
        user_role: Role string. If None, gets from session.
        limit: Optional limit.

    Returns:
        List of Bulletin objects.
    """
    if user_role is None:
        user_role = session.get('role', '')

    query = Bulletin.query.filter(
        Bulletin.column_id == column_id,
        Bulletin.status != 'archived',
        db.or_(
            Bulletin.expire_date == None,
            Bulletin.expire_date >= date.today(),
            Bulletin.is_pinned == 1
        )
    )

    if limit:
        query = query.limit(limit)

    return query.order_by(
        Bulletin.is_pinned.desc(), Bulletin.created_at.desc()
    ).all()


def get_user_stats(user_id=None):
    """
    Get statistics for a user (for dashboard).

    Args:
        user_id: User ID. If None, gets from session.

    Returns:
        Dict with counts.
    """
    if user_id is None:
        user_id = session.get('user_id')

    user_role = session.get('role', '')
    user_dept = session.get('department', '')

    # Active task statuses
    active_statuses = ['pending', 'processing', 'transferring']

    if user_role == 'super_admin':
        pending_count = Task.query.filter(
            Task.status.in_(active_statuses)
        ).count()
    elif user_role == 'dept_admin':
        pending_count = Task.query.filter(
            Task.department == user_dept,
            Task.status.in_(active_statuses)
        ).count()
    else:
        pending_count = Task.query.filter(
            Task.assignee_id == user_id,
            Task.status.in_(active_statuses)
        ).count()

    # My memos count
    my_memos = Memo.query.filter(
        Memo.created_by == user_id,
        Memo.is_archived == 0
    ).count()

    # My files count
    my_files = File.query.filter(
        File.uploaded_by == user_id,
        File.is_deleted == 0
    ).count()

    return {
        'pending_tasks': pending_count,
        'my_memos': my_memos,
        'my_files': my_files
    }


def get_quick_links(user_role=None):
    """
    Get quick links based on user role.

    Args:
        user_role: Role string. If None, gets from session.

    Returns:
        List of dicts with link info.
    """
    if user_role is None:
        user_role = session.get('role', '')

    links = [
        {'url': '/bulletin/', 'icon': 'layui-icon-read', 'text': '信息公示', 'show': True},
        {'url': '/files/', 'icon': 'layui-icon-file', 'text': '文件管理', 'show': True},
    ]

    if user_role in ('super_admin', 'dept_admin'):
        links.insert(0, {'url': '/bulletin/create', 'icon': 'layui-icon-add-1', 'text': '发布内容', 'show': True, 'primary': True})

    if user_role in ('super_admin', 'dept_admin'):
        links.insert(1, {'url': '/tasks/create', 'icon': 'layui-icon-edit', 'text': '创建任务', 'show': True, 'primary': True})

    if user_role == 'super_admin':
        links.append({'url': '/admin/users', 'icon': 'layui-icon-user', 'text': '用户管理', 'show': True})

    return links
