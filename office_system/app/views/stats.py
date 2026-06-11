# -*- coding: utf-8 -*-
"""
Statistics dashboard blueprint.
"""
from flask import Blueprint, render_template, session
from app.extensions import db
from app.decorators import login_required
from app.models import Task, Bulletin, Memo, User, Column, Tab
from sqlalchemy import func, and_
from datetime import datetime, timedelta

stats_bp = Blueprint('stats', __name__)


@stats_bp.route('/stats')
@stats_bp.route('/tasks/stats')
@login_required
def index():
    """Statistics dashboard."""
    user_id = session.get('user_id')
    user_role = session.get('role', '')
    user_dept = session.get('department', '')

    today = datetime.utcnow().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    # Task statistics
    task_base = Task.query
    if user_role == 'user':
        task_base = task_base.filter(Task.assignee_id == user_id)
    elif user_role == 'dept_admin':
        task_base = task_base.filter(Task.department == user_dept)

    task_stats = {
        'total': task_base.count(),
        'pending': task_base.filter(Task.status == 'pending').count(),
        'processing': task_base.filter(Task.status == 'processing').count(),
        'completed': task_base.filter(Task.status == 'completed').count(),
        'overdue': task_base.filter(
            and_(Task.deadline < today, Task.status.in_(['pending', 'processing']))
        ).count(),
        'week_new': task_base.filter(Task.created_at >= week_ago).count(),
    }

    # Bulletin statistics
    bulletin_stats = {
        'total': Bulletin.query.filter(Bulletin.status == 'published').count(),
        'pinned': Bulletin.query.filter(
            Bulletin.status == 'published',
            Bulletin.is_pinned == 1
        ).count(),
        'week_new': Bulletin.query.filter(
            Bulletin.created_at >= week_ago
        ).count(),
    }

    # Memo statistics
    memo_base = Memo.query.filter(Memo.is_archived == 0)
    memo_stats = {
        'total': memo_base.count(),
        'my_memos': memo_base.filter(Memo.created_by == user_id).count(),
        'public': memo_base.filter(Memo.memo_type == 'public').count(),
    }

    # User statistics (admin only)
    user_stats = {}
    if user_role == 'super_admin':
        user_stats = {
            'total': User.query.count(),
            'active': User.query.filter(User.is_active == 1).count(),
            'admins': User.query.filter(User.role.in_(['super_admin', 'dept_admin'])).count(),
            'users': User.query.filter(User.role == 'user').count(),
        }

    # Tab/Column statistics
    tab_stats = {
        'tabs': Tab.query.filter(Tab.is_active == 1, Tab.tab_type == 'bulletin').count(),
        'columns': Column.query.filter(Column.is_active == 1).count(),
    }

    # Recent activity (latest tasks)
    recent_tasks = Task.query.order_by(Task.updated_at.desc()).limit(5).all()

    return render_template('stats/index.html',
                          task_stats=task_stats,
                          bulletin_stats=bulletin_stats,
                          memo_stats=memo_stats,
                          user_stats=user_stats,
                          tab_stats=tab_stats,
                          recent_tasks=recent_tasks,
                          current_date=today,
                          user_role=user_role)


@stats_bp.route('/stats/story')
@login_required
def story():
    """Scrollytelling data story: bulletin + task analysis."""
    from app.models import BulletinCategory, Column as Col

    today = datetime.utcnow().date()
    month_ago = today - timedelta(days=30)

    # === Scene 1: Overview ===
    total_tasks = Task.query.count()
    completed_tasks = Task.query.filter(Task.status == 'completed').count()
    completion_rate = round(completed_tasks / total_tasks * 100) if total_tasks else 0
    total_bulletins = Bulletin.query.filter(Bulletin.status == 'published').count()

    # === Scene 2: Task flow analysis ===
    status_labels = ['pending', 'processing', 'transferring', 'completed', 'rejected', 'archived']
    status_names = {'pending': '待接受', 'processing': '处理中', 'transferring': '待交接',
                    'completed': '已完成', 'rejected': '已驳回', 'archived': '已归档'}
    status_colors = {'pending': '#f59e0b', 'processing': '#3b82f6', 'transferring': '#8b5cf6',
                     'completed': '#10b981', 'rejected': '#ef4444', 'archived': '#9ca3af'}
    task_status_data = []
    for s in status_labels:
        cnt = Task.query.filter(Task.status == s).count()
        pct = round(cnt / total_tasks * 100) if total_tasks else 0
        task_status_data.append({'key': s, 'label': status_names[s], 'count': cnt, 'pct': pct, 'color': status_colors[s]})

    overdue = Task.query.filter(
        Task.deadline < today,
        Task.status.in_(['pending', 'processing'])
    ).count()

    # === Scene 3: Bulletin analysis ===
    bulletin_cats = BulletinCategory.query.filter_by(is_active=1).order_by(BulletinCategory.sort_order).all()
    bulletin_cat_data = []
    for cat in bulletin_cats:
        cnt = Bulletin.query.filter(Bulletin.category_id == cat.id, Bulletin.status == 'published').count()
        if cnt > 0:
            bulletin_cat_data.append({'name': cat.name, 'icon': cat.icon, 'color': cat.color, 'count': cnt})

    # Weekly bulletin trend
    weekly_bulletins = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        cnt = Bulletin.query.filter(
            Bulletin.created_at >= day,
            Bulletin.created_at < day + timedelta(days=1)
        ).count()
        weekly_bulletins.append({'day': day.strftime('%m/%d'), 'count': cnt})
    max_weekly = max((w['count'] for w in weekly_bulletins), default=1)

    # Monthly task trend
    monthly_tasks = []
    for i in range(5, -1, -1):
        start = today.replace(day=1) - timedelta(days=30*i)
        end = (start + timedelta(days=32)).replace(day=1)
        cnt = Task.query.filter(Task.created_at >= start, Task.created_at < end).count()
        monthly_tasks.append({'month': start.strftime('%m月'), 'count': cnt})
    max_monthly = max((m['count'] for m in monthly_tasks), default=1)

    # Max bulletin category count for chart scaling
    max_bulletin_cat = max((c['count'] for c in bulletin_cat_data), default=1) if bulletin_cat_data else 1

    return render_template('stats/story.html',
                          completion_rate=completion_rate,
                          total_tasks=total_tasks,
                          completed_tasks=completed_tasks,
                          total_bulletins=total_bulletins,
                          task_status_data=task_status_data,
                          overdue=overdue,
                          bulletin_cat_data=bulletin_cat_data,
                          weekly_bulletins=weekly_bulletins,
                          monthly_tasks=monthly_tasks,
                          max_weekly=max_weekly,
                          max_monthly=max_monthly,
                          max_bulletin_cat=max_bulletin_cat)
