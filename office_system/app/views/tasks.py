# -*- coding: utf-8 -*-
"""
Task management blueprint.
Task CRUD / status workflow / transfer & approval / multi-filter search.
"""
import json
from datetime import datetime, date
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, jsonify)
from werkzeug.security import check_password_hash
from app.extensions import db
from app.models import (Task, TaskTransfer, TaskAssignee, User, File, BulletinCategory,
                        ReadRecord, Comment, Memo, MemoGroup)
from app.decorators import login_required, require_role
from app.utils import add_log, get_pagination

tasks_bp = Blueprint('tasks', __name__)


def _assignee_clause(user_id):
    return db.or_(
        Task.assignee_id == user_id,
        Task.assignee_links.any(TaskAssignee.user_id == user_id)
    )


def _task_assignee_ids(task):
    ids = task.assignee_ids
    return [int(uid) for uid in ids if uid]


def _is_task_assignee(task, user_id):
    return int(user_id or 0) in _task_assignee_ids(task)


def _parse_assignee_ids():
    ids = []
    for value in request.form.getlist('assignee_ids'):
        try:
            uid = int(value)
        except (TypeError, ValueError):
            continue
        if uid > 0 and uid not in ids:
            ids.append(uid)
    if not ids:
        fallback = request.form.get('assignee_id', 0, type=int)
        if fallback > 0:
            ids.append(fallback)
    return ids


def _sync_task_assignees(task, assignee_ids):
    assignee_ids = [uid for uid in assignee_ids if uid]
    task.assignee_id = assignee_ids[0] if assignee_ids else None
    TaskAssignee.query.filter_by(task_id=task.id).delete(synchronize_session=False)
    for uid in assignee_ids:
        db.session.add(TaskAssignee(task_id=task.id, user_id=uid))


def _mark_task_read(task_id):
    """Mark current task as read for current user."""
    user_id = session.get('user_id')
    if not user_id:
        return
    exists = ReadRecord.query.filter_by(
        target_type='task', target_id=task_id, user_id=user_id
    ).first()
    if not exists:
        db.session.add(ReadRecord(target_type='task', target_id=task_id, user_id=user_id))
        db.session.commit()


@tasks_bp.route('/')
@login_required
def list_tasks():
    """Task list with multi-condition filter."""
    page, per_page = get_pagination()
    user_id = session['user_id']
    user_role = session['role']
    user_dept = session['department']

    status = request.args.get('status', '').strip()
    priority = request.args.get('priority', '').strip()
    department = request.args.get('department', '').strip()
    assignee_id = request.args.get('assignee_id', '', type=int)
    keyword = request.args.get('keyword', '').strip()
    search_scope = request.args.get('search_scope', 'all').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    query = Task.query

    # Role-based data filtering
    if user_role == 'super_admin':
        pass
    elif user_role == 'dept_admin':
        query = query.filter(Task.department == user_dept)
    else:
        query = query.filter(
            db.or_(_assignee_clause(user_id), Task.creator_id == user_id)
        )

    if status == 'overdue':
        today = datetime.utcnow().date()
        query = query.filter(
            Task.deadline < today,
            Task.status.in_(['pending', 'processing'])
        )
    elif status:
        query = query.filter(Task.status == status)
    if priority:
        query = query.filter(Task.priority == priority)
    if department:
        query = query.filter(Task.department == department)
    if assignee_id:
        query = query.filter(_assignee_clause(assignee_id))
    if keyword:
        like = '%' + keyword + '%'
        if search_scope == 'title':
            query = query.filter(Task.title.like(like))
        else:
            search_scope = 'all'
            query = query.filter(db.or_(Task.title.like(like), Task.content.like(like)))
    if date_from:
        try:
            query = query.filter(Task.created_at >= datetime.strptime(date_from, '%Y-%m-%d'))
        except ValueError:
            pass
    if date_to:
        try:
            query = query.filter(Task.created_at <= datetime.strptime(date_to + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
        except ValueError:
            pass

    # Apply category filter BEFORE pagination
    category_filter = request.args.get('category_id', '', type=int)
    if category_filter:
        query = query.filter(Task.category_id == category_filter)

    from sqlalchemy import case as sa_case
    archived_last = sa_case((Task.status == 'archived', 1), else_=0)
    query = query.order_by(archived_last, Task.status.asc(), Task.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    tasks_list = pagination.items

    read_ids = [
        r[0] for r in db.session.query(ReadRecord.target_id).filter(
            ReadRecord.target_type == 'task',
            ReadRecord.user_id == user_id,
            ReadRecord.target_id.in_([t.id for t in tasks_list] or [0])
        ).all()
    ]

    users = User.query.filter_by(is_active=1).all()
    depts = db.session.query(Task.department).filter(Task.department != '').distinct().all()
    dept_list = [d[0] for d in depts]
    categories = BulletinCategory.query.filter_by(is_active=1).order_by(BulletinCategory.sort_order).all()

    # Task statistics
    stats_query = Task.query
    if user_role == 'super_admin':
        pass
    elif user_role == 'dept_admin':
        stats_query = stats_query.filter(Task.department == user_dept)
    else:
        stats_query = stats_query.filter(db.or_(_assignee_clause(user_id), Task.creator_id == user_id))

    total_count = stats_query.count()
    pending_count = stats_query.filter(Task.status == 'pending').count()
    processing_count = stats_query.filter(Task.status == 'processing').count()
    transferring_count = stats_query.filter(Task.status == 'transferring').count()
    completed_count = stats_query.filter(Task.status == 'completed').count()
    archived_count = stats_query.filter(Task.status == 'archived').count()
    rejected_count = stats_query.filter(Task.status == 'rejected').count()
    today = datetime.utcnow().date()
    overdue_count = stats_query.filter(
        Task.deadline < today,
        Task.status.in_(['pending', 'processing'])
    ).count()

    # AJAX partial rendering for no-flash filtering
    if request.args.get('partial') == '1':
        html = render_template('tasks/_list_content.html',
                               tasks=tasks_list,
                               pagination=pagination,
                               read_ids=read_ids,
                               status=status,
                               priority=priority,
                               department=department,
                               assignee_id=assignee_id,
                               category_filter=category_filter,
                               keyword=keyword,
                               search_scope=search_scope,
                               date_from=date_from,
                               date_to=date_to,
                               total_count=total_count,
                               pending_count=pending_count,
                               processing_count=processing_count,
                               transferring_count=transferring_count,
                               completed_count=completed_count,
                               archived_count=archived_count,
                               rejected_count=rejected_count,
                               overdue_count=overdue_count,
                               today=today)
        return html

    return render_template('tasks/list.html',
                           tasks=tasks_list,
                           pagination=pagination,
                           users=users,
                           departments=dept_list,
                           categories=categories,
                           read_ids=read_ids,
                           status=status,
                           priority=priority,
                           department=department,
                           assignee_id=assignee_id,
                           category_filter=category_filter,
                           keyword=keyword,
                           search_scope=search_scope,
                           date_from=date_from,
                           date_to=date_to,
                           total_count=total_count,
                           pending_count=pending_count,
                           processing_count=processing_count,
                           transferring_count=transferring_count,
                           completed_count=completed_count,
                           archived_count=archived_count,
                           rejected_count=rejected_count,
                           overdue_count=overdue_count,
                           today=today)


@tasks_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_task():
    """Create a new task (dept_admin and above)."""
    if session['role'] == 'user':
        flash('没有创建任务的权限', 'danger')
        return redirect(url_for('tasks.list_tasks'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        priority = request.form.get('priority', 'normal').strip()
        department = request.form.get('department', '').strip()
        category_id = request.form.get('category_id', 0, type=int)
        assignee_ids = _parse_assignee_ids()
        deadline = request.form.get('deadline', '').strip()

        if not title:
            flash('任务标题不能为空', 'warning')
            return redirect(url_for('tasks.create_task'))

        task = Task(
            title=title,
            content=content,
            priority=priority,
            department=department,
            category_id=category_id if category_id > 0 else None,
            assignee_id=assignee_ids[0] if assignee_ids else None,
            creator_id=session['user_id'],
            deadline=datetime.strptime(deadline, '%Y-%m-%d').date() if deadline else None,
            status='pending'
        )
        db.session.add(task)
        db.session.flush()
        _sync_task_assignees(task, assignee_ids)

        # Handle file uploads
        import os
        from flask import current_app
        uploaded_files = request.files.getlist('attachments')
        attachment_list = []
        if uploaded_files:
            upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'tasks', str(task.id))
            os.makedirs(upload_folder, exist_ok=True)
            for f in uploaded_files:
                if f and f.filename:
                    safe_name = datetime.now().strftime('%Y%m%d%H%M%S') + '_' + f.filename
                    f.save(os.path.join(upload_folder, safe_name))
                    attachment_list.append({
                        'name': safe_name,
                        'original': f.filename,
                        'path': '/static/uploads/tasks/' + str(task.id) + '/' + safe_name,
                        'size': os.path.getsize(os.path.join(upload_folder, safe_name)),
                    })
        if attachment_list:
            task.attachments = json.dumps(attachment_list)

        # Link selected online docs/sheets to this task
        from app.models import OnlineDocument, Spreadsheet
        linked_doc_ids = request.form.getlist('linked_doc_ids')
        linked_sheet_ids = request.form.getlist('linked_sheet_ids')
        doc_edit_role = request.form.get('doc_edit_role', '["super_admin","dept_admin","user"]').strip()

        for did in linked_doc_ids:
            doc = OnlineDocument.query.get(int(did))
            if doc:
                doc.related_type = 'task'
                doc.related_id = task.id
                doc.edit_roles = doc_edit_role
        for sid in linked_sheet_ids:
            sheet = Spreadsheet.query.get(int(sid))
            if sheet:
                sheet.related_type = 'task'
                sheet.related_id = task.id
                sheet.edit_roles = doc_edit_role

        db.session.commit()

        add_log('create_task', 'task', task.id, 'Created task: ' + title)
        flash('任务创建成功', 'success')
        return redirect(url_for('tasks.detail_task', task_id=task.id))

    users = User.query.filter(User.is_active == 1).order_by(User.department, User.real_name).all()
    depts = db.session.query(Task.department).filter(Task.department != '').distinct().all()
    departments = [d[0] for d in depts]
    categories = BulletinCategory.query.filter_by(is_active=1).order_by(BulletinCategory.sort_order).all()

    # Load columns grouped by category
    from app.models import Column as ColModel, OnlineDocument, Spreadsheet
    all_columns = ColModel.query.filter_by(is_active=1).order_by(ColModel.sort_order.asc()).all()
    cols_by_cat = {}
    for col in all_columns:
        cid = col.category_id or 0
        if cid not in cols_by_cat:
            cols_by_cat[cid] = []
        cols_by_cat[cid].append(col)

    # Available online docs/sheets for linking
    available_docs = OnlineDocument.query.filter_by(is_active=1).order_by(OnlineDocument.updated_at.desc()).all()
    available_sheets = Spreadsheet.query.filter_by(is_active=1).order_by(Spreadsheet.updated_at.desc()).all()

    return render_template('tasks/create.html',
                           users=users,
                           departments=departments,
                           categories=categories,
                           cols_by_cat=cols_by_cat,
                           available_docs=available_docs,
                           available_sheets=available_sheets,
                           selected_assignee_ids=[])


@tasks_bp.route('/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    """Edit a task (super_admin or dept_admin)."""
    task = Task.query.get_or_404(task_id)
    user_role = session['role']

    if user_role not in ('super_admin', 'dept_admin'):
        flash('没有编辑任务的权限', 'danger')
        return redirect(url_for('tasks.detail_task', task_id=task_id))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        priority = request.form.get('priority', 'normal').strip()
        department = request.form.get('department', '').strip()
        category_id = request.form.get('category_id', 0, type=int)
        assignee_ids = _parse_assignee_ids()
        deadline = request.form.get('deadline', '').strip()
        status = request.form.get('status', '').strip()

        if not title:
            flash('任务标题不能为空', 'warning')
            return redirect(url_for('tasks.edit_task', task_id=task_id))

        old_assignee_ids = _task_assignee_ids(task)
        task.title = title
        task.content = content
        task.priority = priority
        task.department = department
        task.category_id = category_id if category_id > 0 else None
        _sync_task_assignees(task, assignee_ids)
        task.deadline = datetime.strptime(deadline, '%Y-%m-%d').date() if deadline else None
        if status and status in ('pending', 'processing', 'completed', 'rejected', 'archived'):
            task.status = status
        if old_assignee_ids != assignee_ids:
            task.reminder_seen_at = None
        task.updated_at = datetime.utcnow()

        # Handle file uploads
        import os
        from flask import current_app
        uploaded_files = request.files.getlist('attachments')
        if uploaded_files:
            existing = json.loads(task.attachments) if task.attachments else []
            upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'tasks', str(task.id))
            os.makedirs(upload_folder, exist_ok=True)
            for f in uploaded_files:
                if f and f.filename:
                    safe_name = datetime.now().strftime('%Y%m%d%H%M%S') + '_' + f.filename
                    f.save(os.path.join(upload_folder, safe_name))
                    existing.append({
                        'name': safe_name,
                        'original': f.filename,
                        'path': '/static/uploads/tasks/' + str(task.id) + '/' + safe_name,
                        'size': os.path.getsize(os.path.join(upload_folder, safe_name)),
                    })
            task.attachments = json.dumps(existing)

        # Update linked docs/sheets
        from app.models import OnlineDocument, Spreadsheet
        OnlineDocument.query.filter_by(related_type='task', related_id=task.id).update(
            {OnlineDocument.related_type: '', OnlineDocument.related_id: 0}
        )
        Spreadsheet.query.filter_by(related_type='task', related_id=task.id).update(
            {Spreadsheet.related_type: '', Spreadsheet.related_id: 0}
        )
        for did in request.form.getlist('linked_doc_ids'):
            doc = OnlineDocument.query.get(int(did))
            if doc:
                doc.related_type = 'task'
                doc.related_id = task.id
        for sid in request.form.getlist('linked_sheet_ids'):
            sheet = Spreadsheet.query.get(int(sid))
            if sheet:
                sheet.related_type = 'task'
                sheet.related_id = task.id

        db.session.commit()
        add_log('edit_task', 'task', task.id, 'Edited task: ' + title)
        flash('任务更新成功', 'success')
        return redirect(url_for('tasks.detail_task', task_id=task_id))

    users = User.query.filter(User.is_active == 1).order_by(User.department, User.real_name).all()
    depts = db.session.query(Task.department).filter(Task.department != '').distinct().all()
    departments = [d[0] for d in depts]
    categories = BulletinCategory.query.filter_by(is_active=1).order_by(BulletinCategory.sort_order).all()
    statuses = ['pending', 'processing', 'completed', 'rejected', 'archived']

    from app.models import Column as ColModel, OnlineDocument, Spreadsheet
    all_columns = ColModel.query.filter_by(is_active=1).order_by(ColModel.sort_order.asc()).all()
    cols_by_cat = {}
    for col in all_columns:
        cid = col.category_id or 0
        if cid not in cols_by_cat:
            cols_by_cat[cid] = []
        cols_by_cat[cid].append(col)

    available_docs = OnlineDocument.query.filter_by(is_active=1).order_by(OnlineDocument.updated_at.desc()).all()
    available_sheets = Spreadsheet.query.filter_by(is_active=1).order_by(Spreadsheet.updated_at.desc()).all()
    linked_doc_ids = [d.id for d in OnlineDocument.query.filter_by(related_type='task', related_id=task.id)]
    linked_sheet_ids = [s.id for s in Spreadsheet.query.filter_by(related_type='task', related_id=task.id)]

    return render_template('tasks/create.html',
                           task=task, users=users,
                           departments=departments,
                           categories=categories,
                           statuses=statuses,
                           cols_by_cat=cols_by_cat,
                           is_edit=True,
                           available_docs=available_docs,
                           available_sheets=available_sheets,
                           linked_doc_ids=linked_doc_ids,
                           linked_sheet_ids=linked_sheet_ids,
                           selected_assignee_ids=_task_assignee_ids(task))


@tasks_bp.route('/<int:task_id>')
@login_required
def detail_task(task_id):
    """Task detail view."""
    task = Task.query.get_or_404(task_id)

    user_role = session['role']
    user_id = session['user_id']
    user_dept = session['department']

    # Permission check
    if user_role != 'super_admin':
        if user_role == 'dept_admin' and task.department != user_dept:
            flash('无权访问', 'danger')
            return redirect(url_for('tasks.list_tasks'))
        if user_role == 'user' and not _is_task_assignee(task, user_id) and task.creator_id != user_id:
            flash('无权访问', 'danger')
            return redirect(url_for('tasks.list_tasks'))

    _mark_task_read(task_id)

    transfers = TaskTransfer.query.filter_by(task_id=task_id)\
        .order_by(TaskTransfer.created_at.desc()).all()

    files = File.query.filter_by(related_type='task', related_id=task_id,
                                  is_deleted=0).all()

    users = User.query.filter(User.is_active == 1, User.id != task.assignee_id)\
        .order_by(User.department, User.real_name).all()

    # Parse task attachments from JSON
    task_attachments = []
    if task.attachments:
        try:
            task_attachments = json.loads(task.attachments)
        except:
            task_attachments = []

    comments = Comment.query.filter_by(
        target_type='task', target_id=task_id, is_deleted=0
    ).order_by(Comment.created_at.asc()).all()

    unread_users = []
    read_users = []
    if user_role in ('super_admin', 'dept_admin'):
        candidate_ids = []
        candidate_ids.extend(_task_assignee_ids(task))
        if task.creator_id:
            candidate_ids.append(task.creator_id)
        candidate_ids = list(dict.fromkeys(candidate_ids))
        read_user_ids = [
            r[0] for r in db.session.query(ReadRecord.user_id).filter_by(
                target_type='task', target_id=task_id
            ).all()
        ]
        unread_ids = [uid for uid in candidate_ids if uid not in read_user_ids]
        if unread_ids:
            unread_users = User.query.filter(User.id.in_(unread_ids)).all()
        read_ids = [uid for uid in candidate_ids if uid in read_user_ids]
        if read_ids:
            read_users = User.query.filter(User.id.in_(read_ids)).all()

    # Related online documents and spreadsheets
    from app.models import OnlineDocument, Spreadsheet
    related_docs = OnlineDocument.query.filter_by(
        related_type='task', related_id=task_id, is_active=1
    ).order_by(OnlineDocument.updated_at.desc()).all()
    related_sheets = Spreadsheet.query.filter_by(
        related_type='task', related_id=task_id, is_active=1
    ).order_by(Spreadsheet.updated_at.desc()).all()

    return render_template('tasks/detail.html',
                           task=task,
                           transfers=transfers,
                           files=files,
                           users=users,
                           task_attachments=task_attachments,
                           comments=comments,
                           read_users=read_users,
                           unread_users=unread_users,
                           related_docs=related_docs,
                           related_sheets=related_sheets,
                           is_current_assignee=_is_task_assignee(task, user_id))


@tasks_bp.route('/<int:task_id>/comments', methods=['POST'])
@login_required
def add_comment(task_id):
    """Add a comment to a task."""
    task = Task.query.get_or_404(task_id)
    content = request.form.get('content', '').strip()
    if not content:
        flash('评论内容不能为空', 'warning')
        return redirect(url_for('tasks.detail_task', task_id=task.id))

    db.session.add(Comment(
        target_type='task',
        target_id=task.id,
        content=content,
        created_by=session['user_id']
    ))
    db.session.commit()
    add_log('comment_task', 'task', task.id, 'Commented task: ' + task.title)
    flash('评论已发布', 'success')
    return redirect(url_for('tasks.detail_task', task_id=task.id))


@tasks_bp.route('/<int:task_id>/comments/reply/<int:comment_id>', methods=['POST'])
@login_required
def reply_comment(task_id, comment_id):
    """Reply to a comment on a task."""
    task = Task.query.get_or_404(task_id)
    parent = Comment.query.get_or_404(comment_id)
    content = request.form.get('content', '').strip()
    if not content:
        return jsonify({'success': False, 'message': '回复内容不能为空'}), 400

    reply = Comment(
        target_type='task',
        target_id=task.id,
        parent_id=parent.id,
        content=content,
        created_by=session['user_id']
    )
    db.session.add(reply)
    db.session.commit()
    return jsonify({'success': True, 'message': '回复成功'})


@tasks_bp.route('/comments/<int:comment_id>/vote', methods=['POST'])
@login_required
def vote_comment(comment_id):
    """Like or dislike a comment (AJAX)."""
    from flask import jsonify
    comment = Comment.query.get_or_404(comment_id)
    vote_type = request.form.get('vote', 'like').strip()
    vote_val = 1 if vote_type == 'like' else -1
    user_id = session['user_id']

    existing = CommentVote.query.filter_by(
        comment_id=comment.id, user_id=user_id
    ).first()

    if existing:
        if existing.vote == vote_val:
            # Remove vote (toggle off)
            if existing.vote == 1:
                comment.likes = max(0, (comment.likes or 0) - 1)
            else:
                comment.dislikes = max(0, (comment.dislikes or 0) - 1)
            db.session.delete(existing)
        else:
            # Switch vote
            if existing.vote == 1:
                comment.likes = max(0, (comment.likes or 0) - 1)
                comment.dislikes = (comment.dislikes or 0) + 1
            else:
                comment.dislikes = max(0, (comment.dislikes or 0) - 1)
                comment.likes = (comment.likes or 0) + 1
            existing.vote = vote_val
    else:
        # New vote
        if vote_val == 1:
            comment.likes = (comment.likes or 0) + 1
        else:
            comment.dislikes = (comment.dislikes or 0) + 1
        db.session.add(CommentVote(
            comment_id=comment.id, user_id=user_id, vote=vote_val
        ))

    db.session.commit()
    return jsonify({
        'success': True,
        'likes': comment.likes or 0,
        'dislikes': comment.dislikes or 0
    })


@tasks_bp.route('/<int:task_id>/to-memo', methods=['POST'])
@login_required
def task_to_memo(task_id):
    """Convert a task into a private memo for current user."""
    task = Task.query.get_or_404(task_id)
    user_id = session['user_id']
    user_role = session['role']
    if user_role == 'user' and not _is_task_assignee(task, user_id) and task.creator_id != user_id:
        flash('无权转换此任务', 'danger')
        return redirect(url_for('tasks.detail_task', task_id=task.id))

    group = MemoGroup.query.filter_by(
        name='任务转备忘', memo_type='private', created_by=user_id, is_active=1
    ).first()
    if not group:
        group = MemoGroup(name='任务转备忘', memo_type='private', created_by=user_id)
        db.session.add(group)
        db.session.flush()

    content = '<p><b>来源任务：</b>{}</p><p><b>状态：</b>{}</p><hr>{}'.format(
        task.title, task.status, task.content or ''
    )
    memo = Memo(
        title='任务备忘：' + task.title,
        content=content,
        memo_type='private',
        group_id=group.id,
        visible_roles='all',
        created_by=user_id
    )
    db.session.add(memo)
    db.session.commit()
    add_log('task_to_memo', 'task', task.id, 'Converted task to memo: ' + task.title)
    flash('已转为个人备忘', 'success')
    return redirect(url_for('memo.list_memos', type='private', group_id=group.id))


@tasks_bp.route('/alerts')
@login_required
def task_alerts():
    """Pending task alerts for current assignee."""
    tasks = Task.query.filter(
        _assignee_clause(session['user_id']),
        Task.status == 'pending',
        Task.reminder_seen_at == None
    ).order_by(Task.created_at.desc()).limit(5).all()
    return jsonify({
        'tasks': [{'id': t.id, 'title': t.title} for t in tasks]
    })


@tasks_bp.route('/alerts/ack', methods=['POST'])
@login_required
def ack_task_alerts():
    """Acknowledge pending task alert popup."""
    Task.query.filter(
        _assignee_clause(session['user_id']),
        Task.status == 'pending',
        Task.reminder_seen_at == None
    ).update({'reminder_seen_at': datetime.utcnow()}, synchronize_session=False)
    db.session.commit()
    return jsonify({'success': True})


@tasks_bp.route('/<int:task_id>/status', methods=['POST'])
@login_required
def update_status(task_id):
    """Update task status."""
    task = Task.query.get_or_404(task_id)
    user_id = session['user_id']
    user_role = session['role']
    action = request.form.get('action', '').strip()

    status_map = {
        'accept': 'processing',
        'complete': 'completed',
        'reject': 'rejected',
        'archive': 'archived',
        'reactivate': 'pending',
    }

    if action not in status_map:
        flash('无效的操作', 'danger')
        return redirect(url_for('tasks.detail_task', task_id=task_id))

    new_status = status_map[action]

    # Permission validation
    if action == 'accept':
        if not _is_task_assignee(task, user_id) and user_role == 'user':
            flash('无权执行此操作', 'danger')
            return redirect(url_for('tasks.detail_task', task_id=task_id))
    elif action in ('reject', 'archive'):
        if user_role not in ('super_admin', 'dept_admin'):
            flash('需要管理员权限', 'danger')
            return redirect(url_for('tasks.detail_task', task_id=task_id))

    task.status = new_status
    task.updated_at = datetime.utcnow()
    db.session.commit()

    add_log('update_task_status', 'task', task.id,
            'Task status: {} -> {}'.format(task.title, new_status))
    flash('任务状态已更新为: ' + new_status, 'success')
    return redirect(url_for('tasks.detail_task', task_id=task_id))


@tasks_bp.route('/<int:task_id>/transfer', methods=['GET', 'POST'])
@login_required
def transfer_task(task_id):
    """Initiate task transfer / handover."""
    task = Task.query.get_or_404(task_id)
    user_id = session['user_id']
    user_role = session['role']

    if user_role == 'user' and not _is_task_assignee(task, user_id):
        flash('无权执行此操作', 'danger')
        return redirect(url_for('tasks.detail_task', task_id=task_id))

    if request.method == 'POST':
        to_user_id = request.form.get('to_user_id', 0, type=int)
        reason = request.form.get('reason', '').strip()

        if not to_user_id:
            flash('请选择接交人', 'warning')
            return redirect(url_for('tasks.transfer_task', task_id=task_id))

        if to_user_id == task.assignee_id:
            flash('不能交接给自己', 'warning')
            return redirect(url_for('tasks.transfer_task', task_id=task_id))

        # Dept admin + super admin auto-approve
        is_auto = user_role in ('super_admin', 'dept_admin')
        tx_status = 'approved' if is_auto else 'pending'

        transfer = TaskTransfer(
            task_id=task_id,
            from_user_id=task.assignee_id or user_id,
            to_user_id=to_user_id,
            reason=reason,
            status=tx_status,
            reviewed_by=user_id if is_auto else None,
            reviewed_at=datetime.utcnow() if is_auto else None
        )
        db.session.add(transfer)

        if is_auto:
            _sync_task_assignees(task, [to_user_id])
            task.status = 'processing'
            task.reminder_seen_at = None
        else:
            task.status = 'transferring'
        task.updated_at = datetime.utcnow()

        db.session.commit()

        add_log('transfer_task', 'task', task.id,
                'Task transfer: {} -> user#{}'.format(task.title, to_user_id))
        msg = '交接已完成' if is_auto else '交接申请已提交，等待审批'
        flash(msg, 'success')
        return redirect(url_for('tasks.detail_task', task_id=task_id))

    users = User.query.filter(User.is_active == 1, User.id != task.assignee_id)\
        .order_by(User.department, User.real_name).all()
    return render_template('tasks/transfer.html', task=task, users=users)


@tasks_bp.route('/transfer/<int:transfer_id>/review', methods=['POST'])
@login_required
@require_role('dept_admin')
def review_transfer(transfer_id):
    """Approve or reject a transfer request."""
    transfer = TaskTransfer.query.get_or_404(transfer_id)
    action = request.form.get('action', '').strip()
    comment = request.form.get('comment', '').strip()

    if action not in ('approve', 'reject'):
        flash('无效的操作', 'danger')
        return redirect(url_for('tasks.detail_task', task_id=transfer.task_id))

    task = Task.query.get(transfer.task_id)

    if action == 'approve':
        transfer.status = 'approved'
        transfer.reviewed_by = session['user_id']
        transfer.reviewed_at = datetime.utcnow()
        transfer.review_comment = comment
        _sync_task_assignees(task, [transfer.to_user_id])
        task.status = 'processing'
        add_log('approve_transfer', 'task_transfer', transfer.id,
                'Approved transfer: task#{} -> user#{}'.format(transfer.task_id, transfer.to_user_id))
        flash('流转审批已通过，任务已交接', 'success')
    else:
        transfer.status = 'rejected'
        transfer.reviewed_by = session['user_id']
        transfer.reviewed_at = datetime.utcnow()
        transfer.review_comment = comment
        task.status = 'processing'
        add_log('reject_transfer', 'task_transfer', transfer.id,
                'Rejected transfer: task#{}'.format(transfer.task_id))
        flash('流转申请已驳回', 'info')

    task.updated_at = datetime.utcnow()
    db.session.commit()
    return redirect(url_for('tasks.detail_task', task_id=transfer.task_id))


@tasks_bp.route('/<int:task_id>/delete', methods=['POST'])
@login_required
@require_role('dept_admin')
def delete_task(task_id):
    """Delete a task."""
    task = Task.query.get_or_404(task_id)

    if session['role'] == 'dept_admin' and task.department != session['department']:
        flash('无权执行此操作', 'danger')
        return redirect(url_for('tasks.list_tasks'))

    title = task.title
    db.session.delete(task)
    db.session.commit()
    add_log('delete_task', 'task', task_id, 'Deleted task: ' + title)
    flash('Task deleted', 'success')
    return redirect(url_for('tasks.list_tasks'))


@tasks_bp.route('/<int:task_id>/reassign', methods=['POST'])
@login_required
@require_role('dept_admin')
def reassign_task(task_id):
    """Force reassign a task to another user (admin override)."""
    task = Task.query.get_or_404(task_id)
    user_id = session['user_id']
    user_role = session['role']

    if user_role == 'dept_admin' and task.department != session['department']:
        flash('无权跨部门操作此任务', 'danger')
        return redirect(url_for('tasks.detail_task', task_id=task_id))

    to_user_id = request.form.get('to_user_id', 0, type=int)
    password = request.form.get('password', '').strip()

    if not to_user_id:
        flash('请选择被分配人', 'warning')
        return redirect(url_for('tasks.detail_task', task_id=task_id))
    if to_user_id == task.assignee_id:
        flash('任务已在该用户名下', 'warning')
        return redirect(url_for('tasks.detail_task', task_id=task_id))

    target = User.query.get_or_404(to_user_id)
    if not target.is_active:
        flash('被分配人账号已被禁用', 'warning')
        return redirect(url_for('tasks.detail_task', task_id=task_id))

    operator = User.query.get(user_id)
    if not operator or not check_password_hash(operator.password_hash, password):
        flash('操作人密码验证失败，请重试', 'danger')
        return redirect(url_for('tasks.detail_task', task_id=task_id))

    old_primary = task.assignee_id
    _sync_task_assignees(task, [target.id])
    if task.status in ('transferring', 'rejected'):
        task.status = 'processing'
    task.reminder_seen_at = None
    task.updated_at = datetime.utcnow()
    db.session.commit()

    add_log('reassign_task', 'task', task.id,
            'Reassigned task#{} from user#{} to user#{} by user#{}'.format(
                task.id, old_primary, target.id, user_id))
    flash('任务已强制分配给 {}'.format(target.real_name or target.username), 'success')
    return redirect(url_for('tasks.detail_task', task_id=task_id))


@tasks_bp.route('/<int:task_id>/progress', methods=['POST'])
@login_required
def update_progress(task_id):
    """Update task progress (assignee only, processing status)."""
    task = Task.query.get_or_404(task_id)
    user_id = session['user_id']
    user_role = session['role']

    # Allow assignee or admin to update progress
    if user_role == 'user' and not _is_task_assignee(task, user_id):
        return jsonify({'success': False, 'message': '无权操作'}), 403

    try:
        progress = int(request.form.get('progress', 0))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': '无效的进度值'}), 400

    # Clamp to 0-100, round to nearest 10
    progress = max(0, min(100, round(progress / 10) * 10))
    task.progress = progress
    task.updated_at = datetime.utcnow()

    # Auto-complete at 100%
    if progress == 100 and task.status == 'processing':
        task.status = 'completed'

    db.session.commit()
    return jsonify({'success': True, 'progress': progress, 'status': task.status})


@tasks_bp.route('/batch-archive', methods=['POST'])
@login_required
def batch_archive():
    """Batch archive multiple tasks."""
    from flask import jsonify
    user_role = session['role']

    if user_role not in ('super_admin', 'dept_admin'):
        return jsonify({'success': False, 'message': '权限不足'}), 403

    try:
        ids = json.loads(request.form.get('ids', '[]'))
    except:
        return jsonify({'success': False, 'message': '参数错误'}), 400

    if not ids:
        return jsonify({'success': False, 'message': '请选择任务'}), 400

    count = 0
    for task_id in ids:
        task = Task.query.get(task_id)
        if task:
            task.status = 'archived'
            task.updated_at = datetime.utcnow()
            count += 1

    db.session.commit()
    add_log('batch_archive_tasks', 'task', 0, 'Archived {} tasks'.format(count))

    return jsonify({'success': True, 'message': '已归档 {} 个任务'.format(count)})


@tasks_bp.route('/batch-delete', methods=['POST'])
@login_required
def batch_delete():
    """Batch delete multiple tasks."""
    from flask import jsonify
    user_role = session['role']

    if user_role != 'super_admin':
        return jsonify({'success': False, 'message': '只有超级管理员可以批量删除'}), 403

    try:
        ids = json.loads(request.form.get('ids', '[]'))
    except:
        return jsonify({'success': False, 'message': '参数错误'}), 400

    if not ids:
        return jsonify({'success': False, 'message': '请选择任务'}), 400

    count = 0
    for task_id in ids:
        task = Task.query.get(task_id)
        if task:
            db.session.delete(task)
            count += 1

    db.session.commit()
    add_log('batch_delete_tasks', 'task', 0, 'Deleted {} tasks'.format(count))

    return jsonify({'success': True, 'message': '已删除 {} 个任务'.format(count)})
