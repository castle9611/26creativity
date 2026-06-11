# -*- coding: utf-8 -*-
"""
Blueprint auto-registration.
"""
from app.views.auth import auth_bp
from app.views.admin import admin_bp
from app.views.tasks import tasks_bp
from app.views.bulletin import bulletin_bp
from app.views.memo import memo_bp
from app.views.files import files_bp
from app.views.contacts import contacts_bp
from app.views.stats import stats_bp
from app.views.settings import settings_bp
from app.views.docs import docs_bp
from app.views.sheets import sheets_bp


def register_blueprints(app):
    """Register all application blueprints."""
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(tasks_bp, url_prefix='/tasks')
    app.register_blueprint(bulletin_bp, url_prefix='/bulletin')
    app.register_blueprint(memo_bp, url_prefix='/memo')
    app.register_blueprint(files_bp, url_prefix='/files')
    app.register_blueprint(contacts_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(docs_bp)
    app.register_blueprint(sheets_bp)

    from flask import session, g
    from app.models import Column, Tab, User
    from app.utils import check_visible

    @app.before_request
    def load_tabs():
        """Load tabs and columns for sidebar (app-wide)."""
        if 'user_id' not in session:
            return
        user_role = session.get('role', '')
        # Load categories with columns for bulletin sidebar
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
        g.visible_categories = visible_categories

    @app.context_processor
    def inject_tabs():
        visible_categories = getattr(g, 'visible_categories', [])
        sidebar_tabs = []
        return dict(visible_categories=visible_categories, sidebar_tabs=sidebar_tabs)

    @app.context_processor
    def inject_user_lists():
        try:
            su = User.query.filter_by(role='super_admin', is_active=1).order_by(User.id.asc()).all()
            da = User.query.filter_by(role='dept_admin', is_active=1).order_by(User.id.asc()).all()
            nu = User.query.filter_by(role='user', is_active=1).order_by(User.id.asc()).all()
        except Exception:
            su = da = nu = []
        return {
            'super_admins': su,
            'dept_admins': da,
            'normal_users': nu,
        }

    # Index / dashboard routes
    from flask import Blueprint, render_template, jsonify, session, request, url_for, redirect, flash
    from app.extensions import db
    from app.decorators import login_required
    from app.models import Task, TaskAssignee, Bulletin, Memo, User, File, OnlineDocument, Spreadsheet, Column, BulletinCategory, QuickLink
    from app.utils import check_visible
    from sqlalchemy.orm import joinedload
    from datetime import datetime, timedelta

    index_bp = Blueprint('index_bp', __name__)

    def _valid_link_url(url):
        return url.startswith('http://') or url.startswith('https://')

    def _assignee_clause(user_id):
        return db.or_(
            Task.assignee_id == user_id,
            Task.assignee_links.any(TaskAssignee.user_id == user_id)
        )

    @index_bp.route('/')
    def index():
        """Public category portal."""
        from datetime import date

        categories = BulletinCategory.query.filter_by(is_active=1).order_by(
            BulletinCategory.sort_order.asc(), BulletinCategory.id.asc()
        ).all()
        selected_id = request.args.get('category_id', type=int)
        active_category = next((c for c in categories if c.id == selected_id), None) if selected_id else None

        active_statuses = ['pending', 'processing', 'transferring']
        task_query = Task.query
        bulletin_query = Bulletin.query.filter(
            Bulletin.status == 'published',
            Bulletin.is_active == 1
        )
        file_query = File.query.filter(File.is_deleted == 0)
        if active_category:
            task_query = task_query.filter(Task.category_id == active_category.id)
            bulletin_query = bulletin_query.filter(Bulletin.category_id == active_category.id)
            file_query = file_query.filter(File.category_id == active_category.id)

        pending_tasks = task_query.filter(Task.status.in_(active_statuses)).order_by(
            Task.deadline.asc().nullslast(), Task.created_at.desc()
        ).limit(8).all()
        tracking_tasks = task_query.order_by(Task.updated_at.desc()).limit(8).all()
        reminders = bulletin_query.filter(
            Bulletin.expire_date == None
        ).order_by(Bulletin.created_at.desc()).limit(8).all()
        public_files = file_query.order_by(File.created_at.desc()).limit(8).all()
        public_memos = Memo.query.filter(
            Memo.memo_type == 'public',
            Memo.is_archived == 0
        ).order_by(Memo.updated_at.desc()).limit(6).all()
        public_quick_links = QuickLink.query.filter_by(
            scope='public',
            is_active=1
        ).order_by(QuickLink.sort_order.asc(), QuickLink.id.asc()).limit(10).all()

        portal_stats = {
            'pending': task_query.filter(Task.status.in_(active_statuses)).count(),
            'tracking': task_query.count(),
            'reminders': len(reminders),
            'files': file_query.count(),
        }

        return render_template('public_home.html',
                               categories=categories,
                               active_category=active_category,
                               pending_tasks=pending_tasks,
                               tracking_tasks=tracking_tasks,
                               reminders=reminders,
                               public_files=public_files,
                               public_memos=public_memos,
                               public_quick_links=public_quick_links,
                               portal_stats=portal_stats)

    @index_bp.route('/public/file/<int:file_id>/download')
    def public_file_download(file_id):
        """Public download for files shown on the portal."""
        from flask import send_file
        import os
        from app.config import BASE_DIR
        from app.utils import content_disposition

        file_record = File.query.filter_by(id=file_id, is_deleted=0).first_or_404()
        full_path = os.path.join(BASE_DIR, file_record.file_path.replace('/', os.sep))
        if not os.path.exists(full_path):
            return render_template('errors/404.html'), 404
        response = send_file(full_path, as_attachment=True)
        response.headers['Content-Disposition'] = content_disposition(file_record.original_name)
        return response

    @index_bp.route('/workbench')
    @login_required
    def workbench():
        """Main dashboard."""
        user_id = session.get('user_id')
        user_role = session.get('role', '')
        user_dept = session.get('department', '')
        search = session.get('_last_dashboard_search', '')

        active_statuses = ['pending', 'processing', 'transferring']

        # Task statistics
        if user_role == 'super_admin':
            pending_count = Task.query.filter(Task.status.in_(active_statuses)).count()
            total_tasks = Task.query.count()
            completed_count = Task.query.filter(Task.status == 'completed').count()
            processing_count = Task.query.filter(Task.status == 'processing').count()
        elif user_role == 'dept_admin':
            pending_count = Task.query.filter(Task.department == user_dept, Task.status.in_(active_statuses)).count()
            total_tasks = Task.query.filter(Task.department == user_dept).count()
            completed_count = Task.query.filter(Task.department == user_dept, Task.status == 'completed').count()
            processing_count = Task.query.filter(Task.department == user_dept, Task.status == 'processing').count()
        else:
            pending_count = Task.query.filter(_assignee_clause(user_id), Task.status.in_(active_statuses)).count()
            total_tasks = Task.query.filter(_assignee_clause(user_id)).count()
            completed_count = Task.query.filter(_assignee_clause(user_id), Task.status == 'completed').count()
            processing_count = Task.query.filter(_assignee_clause(user_id), Task.status == 'processing').count()

        # Overdue count
        from datetime import date
        today = date.today()
        overdue_count = Task.query.filter(
            Task.deadline < today,
            Task.status.in_(['pending', 'processing'])
        ).count() if user_role == 'super_admin' else 0
        if user_role == 'dept_admin':
            overdue_count = Task.query.filter(
                Task.department == user_dept,
                Task.deadline < today,
                Task.status.in_(['pending', 'processing'])
            ).count()
        elif user_role == 'user':
            overdue_count = Task.query.filter(
                _assignee_clause(user_id),
                Task.deadline < today,
                Task.status.in_(['pending', 'processing'])
            ).count()

        week_ago = datetime.utcnow() - timedelta(days=7)
        if user_role == 'super_admin':
            week_new_tasks = Task.query.filter(Task.created_at >= week_ago).count()
        elif user_role == 'dept_admin':
            week_new_tasks = Task.query.filter(Task.department == user_dept, Task.created_at >= week_ago).count()
        else:
            week_new_tasks = Task.query.filter(_assignee_clause(user_id), Task.created_at >= week_ago).count()

        # Bulletin statistics
        total_bulletins = Bulletin.query.filter(Bulletin.status == 'published').count()

        # Memo statistics
        my_memos = Memo.query.filter(Memo.created_by == user_id, Memo.is_archived == 0).count()
        public_memos = Memo.query.filter(Memo.memo_type == 'public', Memo.is_archived == 0).count()

        # User count (for admin)
        total_users = User.query.filter(User.is_active == 1).count() if user_role == 'super_admin' else 0
        active_users = User.query.filter(User.is_active == 1).count() if user_role == 'super_admin' else 0
        total_files = File.query.filter(File.is_deleted == 0).count()
        total_docs = OnlineDocument.query.filter(OnlineDocument.is_active == 1).count()
        total_sheets = Spreadsheet.query.filter(Spreadsheet.is_active == 1).count()
        total_columns = Column.query.filter(Column.is_active == 1).count() if user_role in ('super_admin', 'dept_admin') else 0

        # Latest bulletins
        today_year = datetime.utcnow().year
        latest_bulletins = Bulletin.query.options(
            joinedload(Bulletin.column), joinedload(Bulletin.category)
        ).filter(
            Bulletin.status == 'published',
            Bulletin.is_active == 1
        ).order_by(Bulletin.created_at.desc()).limit(5).all()

        visible_bulletins = [
            b for b in latest_bulletins
            if (b.column and check_visible(b.column.visible_roles, user_role))
            or (b.category and check_visible(b.category.visible_roles, user_role))
        ]

        # User lists for switcher
        super_admins = User.query.filter_by(role='super_admin', is_active=1).order_by(User.id.asc()).all()
        dept_admins = User.query.filter_by(role='dept_admin', is_active=1).order_by(User.id.asc()).all()
        normal_users = User.query.filter_by(role='user', is_active=1).order_by(User.id.asc()).all()

        assigned_alerts = Task.query.filter(
            _assignee_clause(user_id),
            Task.status == 'pending',
            Task.reminder_seen_at == None
        ).order_by(Task.created_at.desc()).limit(5).all()
        quick_links = QuickLink.query.filter_by(
            scope='user',
            user_id=user_id,
            is_active=1
        ).order_by(QuickLink.sort_order.asc(), QuickLink.id.asc()).limit(10).all()

        return render_template('index.html',
                               pending_count=pending_count,
                               total_tasks=total_tasks,
                               completed_count=completed_count,
                               processing_count=processing_count,
                               overdue_count=overdue_count,
                               week_new_tasks=week_new_tasks,
                               total_bulletins=total_bulletins,
                               my_memos=my_memos,
                               public_memos=public_memos,
                               total_users=total_users,
                               active_users=active_users,
                               total_files=total_files,
                               total_docs=total_docs,
                               total_sheets=total_sheets,
                               total_columns=total_columns,
                               latest_bulletins=visible_bulletins[:5],
                               assigned_alerts=assigned_alerts,
                               quick_links=quick_links,
                               search=search,
                               super_admins=super_admins,
                               dept_admins=dept_admins,
                               normal_users=normal_users)

    @index_bp.route('/quick-links')
    @login_required
    def quick_links():
        """Manage current user's workbench quick links."""
        user_id = session.get('user_id')
        links = QuickLink.query.filter_by(scope='user', user_id=user_id).order_by(
            QuickLink.sort_order.asc(), QuickLink.id.asc()
        ).all()
        return render_template('quick_links.html', links=links, max_links=10)

    @index_bp.route('/quick-links/add', methods=['POST'])
    @login_required
    def quick_link_add():
        """Add a personal workbench quick link."""
        user_id = session.get('user_id')
        count = QuickLink.query.filter_by(scope='user', user_id=user_id).count()
        if count >= 10:
            flash('个人快捷链接最多只能添加 10 个', 'warning')
            return redirect(url_for('index_bp.quick_links'))

        name = request.form.get('name', '').strip()
        link_url = request.form.get('url', '').strip()
        if not name or not link_url:
            flash('名称和链接不能为空', 'warning')
            return redirect(url_for('index_bp.quick_links'))
        if not _valid_link_url(link_url):
            flash('链接必须以 http:// 或 https:// 开头', 'warning')
            return redirect(url_for('index_bp.quick_links'))

        link = QuickLink(
            scope='user',
            user_id=user_id,
            name=name,
            url=link_url,
            icon=request.form.get('icon', 'gen-link').strip() or 'gen-link',
            sort_order=request.form.get('sort_order', 0, type=int),
            is_active=1 if request.form.get('is_active') else 0,
            created_by=user_id
        )
        db.session.add(link)
        db.session.commit()
        flash('快捷链接已添加', 'success')
        return redirect(url_for('index_bp.quick_links'))

    @index_bp.route('/quick-links/<int:link_id>/edit', methods=['POST'])
    @login_required
    def quick_link_edit(link_id):
        """Edit a personal workbench quick link."""
        user_id = session.get('user_id')
        link = QuickLink.query.filter_by(id=link_id, scope='user', user_id=user_id).first_or_404()
        name = request.form.get('name', '').strip()
        link_url = request.form.get('url', '').strip()
        if not name or not link_url:
            flash('名称和链接不能为空', 'warning')
            return redirect(url_for('index_bp.quick_links'))
        if not _valid_link_url(link_url):
            flash('链接必须以 http:// 或 https:// 开头', 'warning')
            return redirect(url_for('index_bp.quick_links'))

        link.name = name
        link.url = link_url
        link.icon = request.form.get('icon', link.icon).strip() or 'gen-link'
        link.sort_order = request.form.get('sort_order', link.sort_order, type=int)
        link.is_active = int(request.form.get('is_active', link.is_active))
        db.session.commit()
        flash('快捷链接已更新', 'success')
        return redirect(url_for('index_bp.quick_links'))

    @index_bp.route('/quick-links/<int:link_id>/delete', methods=['POST'])
    @login_required
    def quick_link_delete(link_id):
        """Delete a personal workbench quick link."""
        user_id = session.get('user_id')
        link = QuickLink.query.filter_by(id=link_id, scope='user', user_id=user_id).first_or_404()
        db.session.delete(link)
        db.session.commit()
        flash('快捷链接已删除', 'success')
        return redirect(url_for('index_bp.quick_links'))

    @index_bp.route('/public/task/<int:task_id>')
    def public_task_detail(task_id):
        """Public read-only task detail."""
        task = Task.query.get_or_404(task_id)
        return render_template('public_detail.html',
                               detail_type='task',
                               item=task,
                               back_url=url_for('index_bp.index', category_id=task.category_id) if task.category_id else url_for('index_bp.index'))

    @index_bp.route('/public/bulletin/<int:bulletin_id>')
    def public_bulletin_detail(bulletin_id):
        """Public read-only bulletin detail."""
        bulletin = Bulletin.query.filter(
            Bulletin.id == bulletin_id,
            Bulletin.status == 'published',
            Bulletin.is_active == 1
        ).first_or_404()
        return render_template('public_detail.html',
                               detail_type='bulletin',
                               item=bulletin,
                               back_url=url_for('index_bp.index', category_id=bulletin.category_id) if bulletin.category_id else url_for('index_bp.index'))

    @index_bp.route('/public/memo/<int:memo_id>')
    def public_memo_detail(memo_id):
        """Public read-only memo detail."""
        memo = Memo.query.filter(
            Memo.id == memo_id,
            Memo.memo_type == 'public',
            Memo.is_archived == 0
        ).first_or_404()
        return render_template('public_detail.html',
                               detail_type='memo',
                               item=memo,
                               back_url=url_for('index_bp.index'))

    @index_bp.route('/search')
    @login_required
    def dashboard_search():
        """Simple dashboard search across tasks, bulletins and memos."""
        keyword = request.args.get('q', '').strip()
        search_scope = request.args.get('scope', 'all').strip()
        if search_scope not in ('title', 'all'):
            search_scope = 'all'
        session['_last_dashboard_search'] = keyword
        user_id = session.get('user_id')
        user_role = session.get('role', '')
        user_dept = session.get('department', '')

        task_query = Task.query
        if user_role == 'dept_admin':
            task_query = task_query.filter(Task.department == user_dept)
        elif user_role == 'user':
            task_query = task_query.filter(db.or_(_assignee_clause(user_id), Task.creator_id == user_id))

        bulletin_query = Bulletin.query.filter(Bulletin.status == 'published', Bulletin.is_active == 1)
        memo_query = Memo.query.filter(Memo.is_archived == 0)
        memo_query = memo_query.filter(db.or_(
            db.and_(Memo.memo_type == 'private', Memo.created_by == user_id),
            Memo.memo_type == 'public'
        ))

        results = {'tasks': [], 'bulletins': [], 'memos': []}
        if keyword:
            like = '%' + keyword + '%'
            if search_scope == 'title':
                results['tasks'] = task_query.filter(Task.title.like(like)).limit(8).all()
                results['bulletins'] = bulletin_query.filter(Bulletin.title.like(like)).limit(8).all()
                results['memos'] = memo_query.filter(Memo.title.like(like)).limit(8).all()
            else:
                results['tasks'] = task_query.filter(db.or_(Task.title.like(like), Task.content.like(like))).limit(8).all()
                results['bulletins'] = bulletin_query.filter(db.or_(Bulletin.title.like(like), Bulletin.content.like(like))).limit(8).all()
                results['memos'] = memo_query.filter(db.or_(Memo.title.like(like), Memo.content.like(like))).limit(8).all()

        return render_template('search.html', keyword=keyword, search_scope=search_scope, results=results)

    @index_bp.route('/help')
    @login_required
    def help_page():
        """Help guide page."""
        return render_template('help.html')

    @index_bp.route('/health')
    def health_check():
        """Health check endpoint for monitoring."""
        import os

        health = {
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'components': {}
        }

        # Check database
        try:
            from app.extensions import db
            db.session.execute(db.text('SELECT 1'))
            health['components']['database'] = 'ok'
        except Exception as e:
            health['components']['database'] = f'error: {str(e)}'
            health['status'] = 'unhealthy'

        # Check upload directory
        try:
            from app.config import Config
            upload_dir = Config.UPLOAD_FOLDER
            if os.path.exists(upload_dir):
                health['components']['uploads'] = 'ok'
            else:
                health['components']['uploads'] = 'missing'
                os.makedirs(upload_dir, exist_ok=True)
        except Exception as e:
            health['components']['uploads'] = f'error: {str(e)}'

        status_code = 200 if health['status'] == 'healthy' else 503
        return jsonify(health), status_code

    app.register_blueprint(index_bp)
