# -*- coding: utf-8 -*-
"""
Flask application factory (following pear-admin-flask pattern).
"""
import os
import sys
from flask import Flask

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.config import Config
from app.extensions import db


def create_app(config_class=Config):
    """Create and configure the Flask application."""
    app = Flask(__name__,
                template_folder='templates',
                static_folder='static',
                static_url_path='/static')

    app.config.from_object(config_class)

    # Ensure data directories exist
    data_dir = os.path.join(BASE_DIR, 'data')
    upload_dir = os.path.join(data_dir, 'uploads')
    for d in [data_dir, upload_dir]:
        if not os.path.exists(d):
            os.makedirs(d)

    # Initialize extensions
    db.init_app(app)

    # Register blueprints
    from app.views import register_blueprints
    register_blueprints(app)

    # Register error handlers and context processors
    register_error_handlers(app)
    register_context_processors(app)
    register_theme_injector(app)
    ensure_runtime_tables(app)

    return app


def ensure_runtime_tables(app):
    """Create newly added tables in existing SQLite deployments."""
    with app.app_context():
        from app.models import QuickLink, Task, TaskAssignee, File, FileRelation
        db.create_all()
        inspector = db.inspect(db.engine)
        file_columns = [col['name'] for col in inspector.get_columns('files')]
        if 'category_id' not in file_columns:
            db.session.execute(db.text('ALTER TABLE files ADD COLUMN category_id INTEGER'))
            db.session.execute(db.text('CREATE INDEX IF NOT EXISTS ix_files_category_id ON files(category_id)'))
            db.session.commit()
        changed = False
        legacy_tasks = Task.query.filter(Task.assignee_id.isnot(None)).all()
        for task in legacy_tasks:
            if not TaskAssignee.query.filter_by(task_id=task.id, user_id=task.assignee_id).first():
                db.session.add(TaskAssignee(task_id=task.id, user_id=task.assignee_id))
                changed = True
        if changed:
            db.session.commit()
        changed = False
        legacy_files = File.query.filter(
            File.related_type != '',
            File.related_id.isnot(None),
            File.related_id != 0
        ).all()
        for file_record in legacy_files:
            exists = FileRelation.query.filter_by(
                file_id=file_record.id,
                target_type=file_record.related_type,
                target_id=file_record.related_id
            ).first()
            if not exists:
                db.session.add(FileRelation(
                    file_id=file_record.id,
                    target_type=file_record.related_type,
                    target_id=file_record.related_id
                ))
                changed = True
        if changed:
            db.session.commit()


def register_theme_injector(app):
    """Inject theme switcher script into HTML pages that use the main CSS."""

    @app.after_request
    def inject_theme_script(response):
        content_type = response.headers.get('Content-Type', '')
        if response.direct_passthrough or 'text/html' not in content_type:
            return response
        try:
            html_text = response.get_data(as_text=True)
        except Exception:
            return response
        if 'css/app.css' not in html_text or 'js/theme.js' in html_text or '</head>' not in html_text:
            return response
        script = '<script src="/static/js/theme.js"></script>\n'
        html_text = html_text.replace('</head>', script + '</head>', 1)
        response.set_data(html_text)
        response.headers['Content-Length'] = str(len(response.get_data()))
        return response


def register_error_handlers(app):
    """Register global HTTP error handlers."""

    @app.errorhandler(403)
    def forbidden(e):
        from flask import render_template
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def page_not_found(e):
        from flask import render_template
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(e):
        from flask import render_template
        return render_template('errors/500.html'), 500


def register_context_processors(app):
    """Register Jinja2 context processors and custom filters."""
    icon_aliases = {
        '📋': 'task', '📝': 'memo', '📁': 'folder', '📢': 'bulletin',
        '📊': 'chart', '📌': 'pin', '⚡': 'gen-light', '👥': 'users',
        '⚖': 'cat-discipline', '🔒': 'lock', '📂': 'archive',
        '': 'category', None: 'category'
    }

    @app.context_processor
    def inject_global_vars():
        from flask import session
        return {
            'app_name': '内网OA办公系统',
            'app_version': '1.0.0',
            'current_year': '2026',
            'session': session
        }

    @app.context_processor
    def inject_sidebar_tabs():
        """Inject sidebar tabs from database for dynamic navigation."""
        from flask import session, g
        from app.models import Tab, Column
        from app.utils import check_visible

        user_role = session.get('role', '')

        # Query sidebar tabs (link type tabs visible to current user)
        sidebar_tabs = Tab.query.filter(
            Tab.is_active == 1,
            Tab.tab_type == 'link'
        ).order_by(Tab.sort_order.asc()).all()
        sidebar_tabs = [t for t in sidebar_tabs if check_visible(t.visible_roles, user_role)]

        # Get visible categories with columns for bulletin navigation
        from app.models import BulletinCategory
        categories = BulletinCategory.query.filter_by(is_active=1).order_by(
            BulletinCategory.sort_order.asc()
        ).all()
        visible_categories = []
        for cat in categories:
            if check_visible(cat.visible_roles, user_role):
                cols = Column.query.filter(
                    Column.category_id == cat.id,
                    Column.is_active == 1
                ).order_by(Column.sort_order.asc()).all()
                visible_cols = [c for c in cols if check_visible(c.visible_roles, user_role)]
                visible_categories.append({
                    'id': cat.id, 'name': cat.name, 'icon': cat.icon,
                    'color': cat.color, 'columns': visible_cols
                })

        # sidebar_tabs already loaded above (link type only for shortcuts)

        return {'sidebar_tabs': sidebar_tabs, 'visible_categories': visible_categories}

    @app.template_filter('status_label')
    def status_label_filter(status):
        labels = {
            'pending': '待接收',
            'accepted': '处理中',
            'processing': '处理中',
            'transferring': '待交接',
            'completed': '已完成',
            'rejected': '已驳回',
            'archived': '已归档',
            'approved': '已通过',
            'published': '已发布',
            'expired': '已过期',
            'high': '高',
            'medium': '中',
            'low': '低'
        }
        return labels.get(status, status)

    @app.template_filter('role_label')
    def role_label_filter(role):
        labels = {
            'super_admin': '超级管理员',
            'dept_admin': '监区管理员',
            'user': '干警'
        }
        return labels.get(role, role)

    @app.template_filter('icon_id')
    def icon_id_filter(value, default='category'):
        """Normalize legacy emoji category icons to stored SVG icon ids."""
        if value in icon_aliases:
            return icon_aliases[value]
        if isinstance(value, str) and value.strip():
            return value.strip()
        return default

    @app.template_filter('localtime')
    def localtime_filter(value, fmt='%Y-%m-%d %H:%M'):
        """Display stored UTC datetimes as Beijing local time."""
        if not value:
            return ''
        try:
            from datetime import timezone, timedelta
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            local_value = value.astimezone(timezone(timedelta(hours=8)))
            return local_value.strftime(fmt)
        except Exception:
            try:
                return value.strftime(fmt)
            except Exception:
                return ''

    @app.template_filter('strip_html')
    def strip_html_filter(text):
        """Remove HTML tags from text for plain preview."""
        import re
        if not text:
            return ''
        text = re.sub(r'<[^>]+>', '', text)
        text = text.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>')
        text = text.replace('&amp;', '&').replace('&quot;', '"').replace('&#39;', "'")
        return text.strip()
