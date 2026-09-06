# -*- coding: utf-8 -*-
"""
Bulletin / information publishing blueprint (core module).
Tab + Column two-level navigation / content publishing /
pinned + expiration / role visibility / multi-filter search.
"""
import json
from datetime import datetime, date
from urllib.parse import urlsplit
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session)
from app.extensions import db
from app.models import (Tab, Column, Bulletin, BulletinCategory,
                        BulletinAttachment, User, ReadRecord, Comment)
from app.decorators import login_required, require_role
from app.utils import add_log, get_pagination, check_visible

bulletin_bp = Blueprint('bulletin', __name__)


def _optional_nextcloud_url():
    value = request.form.get('nextcloud_url', '').strip()[:2000]
    if not value:
        return ''
    parsed = urlsplit(value)
    return value if parsed.scheme in ('http', 'https') and parsed.netloc else ''


def _attachment_classification():
    category_id = request.form.get('attachment_category_id', 0, type=int)
    column_id = request.form.get('attachment_column_id', 0, type=int)
    column = Column.query.filter_by(id=column_id, is_active=1).first() if column_id else None
    if column:
        return column.category_id or category_id or None, column.id
    return category_id or None, None


def _mark_read(target_id):
    """Mark current bulletin as read for current user."""
    user_id = session.get('user_id')
    if not user_id:
        return
    exists = ReadRecord.query.filter_by(
        target_type='bulletin', target_id=target_id, user_id=user_id
    ).first()
    if not exists:
        db.session.add(ReadRecord(
            target_type='bulletin', target_id=target_id, user_id=user_id
        ))
        db.session.commit()


def _read_status_users(target_id):
    """Return read and unread active users for a bulletin."""
    read_user_ids = [
        r[0] for r in db.session.query(ReadRecord.user_id).filter_by(
            target_type='bulletin', target_id=target_id
        ).all()
    ]
    read_users = []
    if read_user_ids:
        read_users = User.query.filter(
            User.is_active == 1,
            User.id.in_(read_user_ids)
        ).order_by(User.department.asc(), User.real_name.asc()).all()

    query = User.query.filter(User.is_active == 1)
    if read_user_ids:
        query = query.filter(~User.id.in_(read_user_ids))
    unread_users = query.order_by(User.department.asc(), User.real_name.asc()).all()
    return read_users, unread_users


@bulletin_bp.route('/')
@login_required
def index():
    """Bulletin homepage - category filter with bulletin list and counts."""
    page, per_page = get_pagination()
    user_role = session['role']

    # Get active categories
    categories = BulletinCategory.query.filter_by(is_active=1).order_by(
        BulletinCategory.sort_order.asc()
    ).all()
    visible_cats = [c for c in categories if check_visible(c.visible_roles, user_role)]

    # Selected category filter
    filter_cat_id = request.args.get('category_id', 0, type=int)
    if filter_cat_id and filter_cat_id not in [c.id for c in visible_cats]:
        filter_cat_id = 0

    # Build bulletin query
    query = Bulletin.query.filter(Bulletin.status != 'archived')

    if filter_cat_id:
        query = query.filter(Bulletin.category_id == filter_cat_id)

    # Filter expired (keep pinned)
    today = date.today()
    query = query.filter(
        db.or_(
            Bulletin.expire_date == None,
            Bulletin.expire_date >= today,
            Bulletin.is_pinned == 1
        )
    )

    query = query.order_by(Bulletin.is_pinned.desc(), Bulletin.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    bulletins = pagination.items

    read_ids = [
        r[0] for r in db.session.query(ReadRecord.target_id).filter(
            ReadRecord.target_type == 'bulletin',
            ReadRecord.user_id == session['user_id'],
            ReadRecord.target_id.in_([b.id for b in bulletins] or [0])
        ).all()
    ]

    # Category counts (published, non-archived)
    cat_counts = {}
    for cat in visible_cats:
        cnt = Bulletin.query.filter(
            Bulletin.category_id == cat.id,
            Bulletin.status != 'archived'
        ).filter(
            db.or_(
                Bulletin.expire_date == None,
                Bulletin.expire_date >= today,
                Bulletin.is_pinned == 1
            )
        ).count()
        cat_counts[cat.id] = cnt

    return render_template('bulletin/index.html',
                           categories=visible_cats,
                           cat_counts=cat_counts,
                           filter_cat_id=filter_cat_id,
                           bulletins=bulletins,
                           read_ids=read_ids,
                           pagination=pagination)


@bulletin_bp.route('/column/<int:column_id>')
@login_required
def column_list(column_id):
    """Content list for a specific column."""
    page, per_page = get_pagination()
    user_role = session['role']

    col = Column.query.get_or_404(column_id)

    if not check_visible(col.visible_roles, user_role):
        flash('无权访问', 'danger')
        return redirect(url_for('bulletin.index'))

    # Get category for the column
    category = col.category

    keyword = request.args.get('keyword', '').strip()
    search_scope = request.args.get('search_scope', 'all').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    query = Bulletin.query.filter(
        Bulletin.column_id == column_id,
        Bulletin.status != 'archived'
    )

    if keyword:
        like = '%' + keyword + '%'
        if search_scope == 'title':
            query = query.filter(Bulletin.title.like(like))
        else:
            search_scope = 'all'
            query = query.filter(db.or_(Bulletin.title.like(like), Bulletin.content.like(like)))
    if date_from:
        try:
            query = query.filter(Bulletin.created_at >= datetime.strptime(date_from, '%Y-%m-%d'))
        except ValueError:
            pass
    if date_to:
        try:
            query = query.filter(Bulletin.created_at <= datetime.strptime(date_to + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
        except ValueError:
            pass

    # Filter expired (keep pinned)
    today = date.today()
    query = query.filter(
        db.or_(
            Bulletin.expire_date == None,
            Bulletin.expire_date >= today,
            Bulletin.is_pinned == 1
        )
    )

    query = query.order_by(Bulletin.is_pinned.desc(), Bulletin.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    bulletins = pagination.items

    # Get tabs for sidebar and columns in same category
    tabs = Tab.query.filter_by(is_active=1).order_by(Tab.sort_order.asc()).all()
    columns = Column.query.filter_by(category_id=col.category_id, is_active=1)\
        .order_by(Column.sort_order.asc()).all()

    return render_template('bulletin/list.html',
                           bulletins=bulletins,
                           pagination=pagination,
                           current_column=col,
                           current_category=category,
                           tabs=tabs,
                           columns=columns,
                           keyword=keyword,
                           search_scope=search_scope,
                           date_from=date_from,
                           date_to=date_to)


@bulletin_bp.route('/<int:bulletin_id>')
@login_required
def detail(bulletin_id):
    """Bulletin detail page."""
    bulletin = Bulletin.query.get_or_404(bulletin_id)
    user_role = session['role']
    col = Column.query.get(bulletin.column_id) if bulletin.column_id else None
    # Tab info: new path through category->tab, or None for legacy data
    tab = None
    if col:
        try:
            tab = col.category.tab if col.category and col.category.tab else None
        except Exception:
            tab = None

    if col and not check_visible(col.visible_roles, user_role):
        flash('无权访问', 'danger')
        return redirect(url_for('bulletin.index'))

    _mark_read(bulletin_id)

    comments = Comment.query.filter_by(
        target_type='bulletin', target_id=bulletin_id, is_deleted=0
    ).order_by(Comment.created_at.asc()).all()
    read_users = []
    unread_users = []
    if user_role in ('super_admin', 'dept_admin'):
        read_users, unread_users = _read_status_users(bulletin_id)

    # Related online documents and spreadsheets
    from app.models import OnlineDocument, Spreadsheet, CloudAttachment
    related_docs = OnlineDocument.query.filter_by(
        related_type='bulletin', related_id=bulletin_id, is_active=1
    ).order_by(OnlineDocument.updated_at.desc()).all()
    related_sheets = Spreadsheet.query.filter_by(
        related_type='bulletin', related_id=bulletin_id, is_active=1
    ).order_by(Spreadsheet.updated_at.desc()).all()
    cloud_attachments = CloudAttachment.query.filter_by(
        target_type='bulletin', target_id=bulletin_id).order_by(CloudAttachment.created_at.asc()).all()

    return render_template('bulletin/detail.html',
                           bulletin=bulletin,
                           column=col,
                           tab=tab,
                           comments=comments,
                           read_users=read_users,
                           unread_users=unread_users,
                           related_docs=related_docs,
                           related_sheets=related_sheets,
                           cloud_attachments=cloud_attachments)


@bulletin_bp.route('/<int:bulletin_id>/comments', methods=['POST'])
@login_required
def add_comment(bulletin_id):
    """Add a comment to a bulletin."""
    bulletin = Bulletin.query.get_or_404(bulletin_id)
    content = request.form.get('content', '').strip()
    if not content:
        flash('评论内容不能为空', 'warning')
        return redirect(url_for('bulletin.detail', bulletin_id=bulletin.id))

    comment = Comment(
        target_type='bulletin',
        target_id=bulletin.id,
        content=content,
        created_by=session['user_id']
    )
    db.session.add(comment)
    db.session.commit()
    add_log('comment_bulletin', 'bulletin', bulletin.id, 'Commented bulletin: ' + bulletin.title)
    flash('评论已发布', 'success')
    return redirect(url_for('bulletin.detail', bulletin_id=bulletin.id))


@bulletin_bp.route('/<int:bulletin_id>/comments/reply/<int:comment_id>', methods=['POST'])
@login_required
def reply_comment(bulletin_id, comment_id):
    """Reply to a comment on a bulletin."""
    parent = Comment.query.get_or_404(comment_id)
    content = request.form.get('content', '').strip()
    if not content:
        return jsonify({'success': False, 'message': '回复内容不能为空'}), 400

    reply = Comment(
        target_type='bulletin',
        target_id=bulletin_id,
        parent_id=parent.id,
        content=content,
        created_by=session['user_id']
    )
    db.session.add(reply)
    db.session.commit()
    return jsonify({'success': True, 'message': '回复成功'})


@bulletin_bp.route('/comments/<int:comment_id>/vote', methods=['POST'])
@login_required
def vote_comment(comment_id):
    """Like or dislike a comment on a bulletin."""
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
            if existing.vote == 1:
                comment.likes = max(0, (comment.likes or 0) - 1)
            else:
                comment.dislikes = max(0, (comment.dislikes or 0) - 1)
            db.session.delete(existing)
        else:
            if existing.vote == 1:
                comment.likes = max(0, (comment.likes or 0) - 1)
                comment.dislikes = (comment.dislikes or 0) + 1
            else:
                comment.dislikes = max(0, (comment.dislikes or 0) - 1)
                comment.likes = (comment.likes or 0) + 1
            existing.vote = vote_val
    else:
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


@bulletin_bp.route('/create', methods=['GET', 'POST'])
@login_required
@require_role('dept_admin')
def create():
    """Publish new bulletin content (category-level only, no column selection)."""
    from flask import jsonify
    user_role = session['role']
    user_id = session['user_id']
    import os
    from flask import current_app

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        nextcloud_url = _optional_nextcloud_url()
        attachment_category_id, attachment_column_id = _attachment_classification()
        is_pinned = int(request.form.get('is_pinned', 0))
        expire_date = request.form.get('expire_date', '').strip()
        quick_expire = request.form.get('quick_expire', '').strip()
        category_id = request.form.get('category_id', 0, type=int)
        column_id = request.form.get('column_id', 0, type=int)

        if not title:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': '请填写标题'})
            flash('请填写标题', 'warning')
            return redirect(url_for('bulletin.create'))

        if not category_id:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': '请选择业务类别'})
            flash('请选择业务类别', 'warning')
            return redirect(url_for('bulletin.create'))

        # Handle quick expire options
        if quick_expire:
            from datetime import timedelta
            today = date.today()
            if quick_expire == '1week':
                expire_date = (today + timedelta(days=7)).strftime('%Y-%m-%d')
            elif quick_expire == '1month':
                expire_date = (today + timedelta(days=30)).strftime('%Y-%m-%d')
            elif quick_expire == '1year':
                expire_date = (today + timedelta(days=365)).strftime('%Y-%m-%d')
            elif quick_expire == 'forever':
                expire_date = ''

        try:
            expire_date_obj = datetime.strptime(expire_date, '%Y-%m-%d').date() if expire_date else None
        except ValueError:
            expire_date_obj = None

        bulletin = Bulletin(
            category_id=category_id,
            column_id=column_id if column_id > 0 else None,
            title=title,
            content=content,
            nextcloud_url=nextcloud_url,
            is_pinned=is_pinned,
            expire_date=expire_date_obj,
            status='published',
            created_by=session['user_id']
        )
        db.session.add(bulletin)
        db.session.flush()

        # Handle file uploads
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'bulletins', str(bulletin.id))
        os.makedirs(upload_folder, exist_ok=True)

        uploaded_files = request.files.getlist('attachments')
        for f in uploaded_files:
            if f and f.filename:
                filename = f.filename
                safe_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                file_path = os.path.join(upload_folder, safe_name)
                f.save(file_path)

                attachment = BulletinAttachment(
                    bulletin_id=bulletin.id,
                    filename=safe_name,
                    original_name=filename,
                    file_path=f'/static/uploads/bulletins/{bulletin.id}/{safe_name}',
                    file_size=os.path.getsize(file_path),
                    file_type=filename.split('.')[-1].lower() if '.' in filename else '',
                    category_id=attachment_category_id,
                    column_id=attachment_column_id,
                    uploaded_by=user_id
                )
                db.session.add(attachment)
                from app.nextcloud import mirror_attachment
                mirror_attachment('bulletin', bulletin.id, file_path, filename, user_id,
                                  category_id=attachment_category_id, column_id=attachment_column_id)

        # Link selected online docs/sheets to this bulletin
        from app.models import OnlineDocument, Spreadsheet
        linked_doc_ids = request.form.getlist('linked_doc_ids')
        linked_sheet_ids = request.form.getlist('linked_sheet_ids')
        for did in linked_doc_ids:
            doc = OnlineDocument.query.get(int(did))
            if doc:
                doc.related_type = 'bulletin'
                doc.related_id = bulletin.id
        for sid in linked_sheet_ids:
            sheet = Spreadsheet.query.get(int(sid))
            if sheet:
                sheet.related_type = 'bulletin'
                sheet.related_id = bulletin.id

        db.session.commit()

        add_log('create_bulletin', 'bulletin', bulletin.id, 'Published: ' + title)

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': '内容发布成功', 'redirect': url_for('bulletin.detail', bulletin_id=bulletin.id)})

        flash('内容发布成功', 'success')
        return redirect(url_for('bulletin.detail', bulletin_id=bulletin.id))

    # Load visible categories for the selector (no columns needed)
    categories = BulletinCategory.query.filter_by(is_active=1).order_by(
        BulletinCategory.sort_order.asc()
    ).all()

    visible_categories = []
    for cat in categories:
        if check_visible(cat.visible_roles, user_role):
            visible_categories.append({
                'id': cat.id,
                'name': cat.name,
                'icon': cat.icon,
                'color': cat.color,
            })

    all_columns = Column.query.filter_by(is_active=1).order_by(Column.sort_order.asc()).all()
    cols_by_cat = {}
    for col in all_columns:
        cols_by_cat.setdefault(col.category_id or 0, []).append(col)
    from app.nextcloud import cloud_home_url

    return render_template('bulletin/create.html',
                           categories=visible_categories,
                           cols_by_cat=cols_by_cat,
                           nextcloud_url=cloud_home_url())


@bulletin_bp.route('/<int:bulletin_id>/edit', methods=['GET', 'POST'])
@login_required
@require_role('dept_admin')
def edit(bulletin_id):
    """Edit bulletin content."""
    bulletin = Bulletin.query.get_or_404(bulletin_id)
    user_role = session['role']
    user_id = session['user_id']
    import os
    from flask import current_app

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        nextcloud_url = _optional_nextcloud_url()
        attachment_category_id, attachment_column_id = _attachment_classification()
        is_pinned = int(request.form.get('is_pinned', 0))
        expire_date = request.form.get('expire_date', '').strip()
        quick_expire = request.form.get('quick_expire', '').strip()
        delete_attachments = request.form.get('delete_attachments', '')
        category_id = request.form.get('category_id', 0, type=int)
        column_id = request.form.get('column_id', 0, type=int)

        if not title:
            flash('标题不能为空', 'warning')
            return redirect(url_for('bulletin.edit', bulletin_id=bulletin_id))

        # Handle quick expire options
        if quick_expire:
            from datetime import timedelta
            today = date.today()
            if quick_expire == '1week':
                expire_date = (today + timedelta(days=7)).strftime('%Y-%m-%d')
            elif quick_expire == '1month':
                expire_date = (today + timedelta(days=30)).strftime('%Y-%m-%d')
            elif quick_expire == '1year':
                expire_date = (today + timedelta(days=365)).strftime('%Y-%m-%d')
            elif quick_expire == 'forever':
                expire_date = ''

        bulletin.title = title
        bulletin.content = content
        bulletin.nextcloud_url = nextcloud_url
        bulletin.is_pinned = is_pinned
        if category_id:
            bulletin.category_id = category_id
        bulletin.column_id = column_id if column_id > 0 else None

        try:
            bulletin.expire_date = datetime.strptime(expire_date, '%Y-%m-%d').date() if expire_date else None
        except ValueError:
            bulletin.expire_date = None

        bulletin.updated_at = datetime.utcnow()

        # Delete attachments marked for removal
        if delete_attachments:
            ids_to_delete = [int(x) for x in delete_attachments.split(',') if x.isdigit()]
            for att_id in ids_to_delete:
                att = BulletinAttachment.query.get(att_id)
                if att and att.bulletin_id == bulletin.id:
                    # Delete physical file
                    file_full_path = os.path.join(current_app.root_path, 'static', att.file_path.lstrip('/'))
                    if os.path.exists(file_full_path):
                        os.remove(file_full_path)
                    db.session.delete(att)

        # Handle new file uploads
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'bulletins', str(bulletin.id))
        os.makedirs(upload_folder, exist_ok=True)

        uploaded_files = request.files.getlist('attachments')
        for f in uploaded_files:
            if f and f.filename:
                filename = f.filename
                safe_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                file_path = os.path.join(upload_folder, safe_name)
                f.save(file_path)

                attachment = BulletinAttachment(
                    bulletin_id=bulletin.id,
                    filename=safe_name,
                    original_name=filename,
                    file_path=f'/static/uploads/bulletins/{bulletin.id}/{safe_name}',
                    file_size=os.path.getsize(file_path),
                    file_type=filename.split('.')[-1].lower() if '.' in filename else '',
                    category_id=attachment_category_id,
                    column_id=attachment_column_id,
                    uploaded_by=user_id
                )
                db.session.add(attachment)
                from app.nextcloud import mirror_attachment
                mirror_attachment('bulletin', bulletin.id, file_path, filename, user_id,
                                  category_id=attachment_category_id, column_id=attachment_column_id)

        # Link/update linked docs/sheets
        from app.models import OnlineDocument, Spreadsheet
        linked_doc_ids = request.form.getlist('linked_doc_ids')
        linked_sheet_ids = request.form.getlist('linked_sheet_ids')
        # Clear old links for this bulletin
        OnlineDocument.query.filter_by(related_type='bulletin', related_id=bulletin.id).update(
            {OnlineDocument.related_type: '', OnlineDocument.related_id: 0}
        )
        Spreadsheet.query.filter_by(related_type='bulletin', related_id=bulletin.id).update(
            {Spreadsheet.related_type: '', Spreadsheet.related_id: 0}
        )
        for did in linked_doc_ids:
            doc = OnlineDocument.query.get(int(did))
            if doc:
                doc.related_type = 'bulletin'
                doc.related_id = bulletin.id
        for sid in linked_sheet_ids:
            sheet = Spreadsheet.query.get(int(sid))
            if sheet:
                sheet.related_type = 'bulletin'
                sheet.related_id = bulletin.id

        db.session.commit()
        add_log('edit_bulletin', 'bulletin', bulletin.id, 'Edited: ' + title)
        flash('内容更新成功', 'success')
        return redirect(url_for('bulletin.detail', bulletin_id=bulletin_id))

    # Load categories for the picker
    categories = BulletinCategory.query.filter_by(is_active=1).order_by(
        BulletinCategory.sort_order.asc()
    ).all()
    visible_categories = [c for c in categories if check_visible(c.visible_roles, user_role)]

    from app.models import OnlineDocument, Spreadsheet
    all_columns = Column.query.filter_by(is_active=1).order_by(Column.sort_order.asc()).all()
    cols_by_cat = {}
    for col in all_columns:
        cols_by_cat.setdefault(col.category_id or 0, []).append(col)
    available_docs = OnlineDocument.query.filter_by(is_active=1).order_by(OnlineDocument.updated_at.desc()).all()
    available_sheets = Spreadsheet.query.filter_by(is_active=1).order_by(Spreadsheet.updated_at.desc()).all()
    # Find already-linked IDs
    linked_doc_ids = [d.id for d in OnlineDocument.query.filter_by(related_type='bulletin', related_id=bulletin.id)]
    linked_sheet_ids = [s.id for s in Spreadsheet.query.filter_by(related_type='bulletin', related_id=bulletin.id)]

    from app.nextcloud import cloud_home_url
    return render_template('bulletin/edit.html',
                           bulletin=bulletin,
                           categories=visible_categories,
                           cols_by_cat=cols_by_cat,
                           available_docs=available_docs,
                           available_sheets=available_sheets,
                           linked_doc_ids=linked_doc_ids,
                           linked_sheet_ids=linked_sheet_ids,
                           nextcloud_url=cloud_home_url())


@bulletin_bp.route('/<int:bulletin_id>/archive', methods=['POST'])
@login_required
@require_role('dept_admin')
def archive(bulletin_id):
    """Archive a bulletin."""
    bulletin = Bulletin.query.get_or_404(bulletin_id)
    bulletin.status = 'archived'
    bulletin.updated_at = datetime.utcnow()
    db.session.commit()
    add_log('archive_bulletin', 'bulletin', bulletin.id, 'Archived: ' + bulletin.title)
    flash('内容已归档', 'success')
    next_url = request.form.get('next') or request.args.get('next')
    if next_url and next_url.startswith('/'):
        return redirect(next_url)
    if request.args.get('next') == 'manage':
        return redirect(url_for('bulletin.manage'))
    if bulletin.column_id:
        return redirect(url_for('bulletin.column_list', column_id=bulletin.column_id))
    return redirect(url_for('bulletin.index', category_id=bulletin.category_id))


@bulletin_bp.route('/<int:bulletin_id>/restore', methods=['POST'])
@login_required
@require_role('dept_admin')
def restore(bulletin_id):
    """Restore an archived bulletin to published status."""
    bulletin = Bulletin.query.get_or_404(bulletin_id)
    bulletin.status = 'published'
    bulletin.updated_at = datetime.utcnow()
    db.session.commit()
    add_log('restore_bulletin', 'bulletin', bulletin.id, 'Restored: ' + bulletin.title)
    flash('内容已恢复发布', 'success')
    return redirect(url_for('bulletin.manage', status='archived'))


@bulletin_bp.route('/<int:bulletin_id>/delete', methods=['POST'])
@login_required
@require_role('dept_admin')
def delete(bulletin_id):
    """Delete a bulletin."""
    bulletin = Bulletin.query.get_or_404(bulletin_id)
    col_id = bulletin.column_id
    cat_id = bulletin.category_id
    title = bulletin.title
    db.session.delete(bulletin)
    db.session.commit()
    add_log('delete_bulletin', 'bulletin', bulletin_id, 'Deleted: ' + title)
    flash('内容已删除', 'success')
    if col_id:
        return redirect(url_for('bulletin.column_list', column_id=col_id))
    return redirect(url_for('bulletin.index', category_id=cat_id))


@bulletin_bp.route('/manage')
@login_required
@require_role('dept_admin')
def manage():
    """Content management page (includes archived)."""
    page, per_page = get_pagination()
    user_role = session['role']
    user_dept = session['department']
    status = request.args.get('status', 'all').strip()
    category_id = request.args.get('category_id', '', type=int)

    query = Bulletin.query

    if user_role == 'dept_admin':
        query = query.join(User, Bulletin.created_by == User.id)\
            .filter(User.department == user_dept)

    if status != 'all':
        query = query.filter(Bulletin.status == status)
    if category_id:
        query = query.filter(Bulletin.category_id == category_id)

    from sqlalchemy import case as sa_case
    archived_last = sa_case((Bulletin.status == 'archived', 1), else_=0)
    query = query.order_by(archived_last, Bulletin.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    bulletins = pagination.items

    # Bulletin statistics
    stats_query = Bulletin.query
    if user_role == 'dept_admin':
        stats_query = stats_query.join(User, Bulletin.created_by == User.id)\
            .filter(User.department == user_dept)

    published_count = stats_query.filter(Bulletin.status == 'published').count()
    archived_count = stats_query.filter(Bulletin.status == 'archived').count()
    total_count = published_count + archived_count

    # Build category list for filter
    categories = BulletinCategory.query.filter_by(is_active=1).order_by(BulletinCategory.sort_order.asc()).all()
    visible_categories = [c for c in categories if check_visible(c.visible_roles, user_role)]

    return render_template('bulletin/manage.html',
                           bulletins=bulletins,
                           pagination=pagination,
                           categories=visible_categories,
                           status=status,
                           category_id=category_id,
                           total_count=total_count,
                           published_count=published_count,
                           archived_count=archived_count)


@bulletin_bp.route('/batch-archive', methods=['POST'])
@login_required
@require_role('dept_admin')
def batch_archive():
    """Batch archive multiple bulletins."""
    from flask import jsonify
    user_role = session['role']

    try:
        ids = json.loads(request.form.get('ids', '[]'))
    except:
        return jsonify({'success': False, 'message': '参数错误'}), 400

    if not ids:
        return jsonify({'success': False, 'message': '请选择内容'}), 400

    count = 0
    for bulletin_id in ids:
        bulletin = Bulletin.query.get(bulletin_id)
        if bulletin:
            bulletin.status = 'archived'
            bulletin.updated_at = datetime.utcnow()
            count += 1

    db.session.commit()
    add_log('batch_archive_bulletins', 'bulletin', 0, 'Archived {} bulletins'.format(count))

    return jsonify({'success': True, 'message': '已归档 {} 个内容'.format(count)})


@bulletin_bp.route('/batch-restore', methods=['POST'])
@login_required
@require_role('dept_admin')
def batch_restore():
    """Batch restore archived bulletins."""
    from flask import jsonify

    try:
        ids = json.loads(request.form.get('ids', '[]'))
    except:
        return jsonify({'success': False, 'message': '参数错误'}), 400

    if not ids:
        return jsonify({'success': False, 'message': '请选择内容'}), 400

    count = 0
    for bulletin_id in ids:
        bulletin = Bulletin.query.get(bulletin_id)
        if bulletin and bulletin.status == 'archived':
            bulletin.status = 'published'
            bulletin.updated_at = datetime.utcnow()
            count += 1

    db.session.commit()
    add_log('batch_restore_bulletins', 'bulletin', 0, 'Restored {} bulletins'.format(count))

    return jsonify({'success': True, 'message': '已恢复 {} 个内容'.format(count)})


@bulletin_bp.route('/batch-delete', methods=['POST'])
@login_required
@require_role('dept_admin')
def batch_delete():
    """Batch delete multiple bulletins."""
    from flask import jsonify
    user_role = session['role']

    if user_role == 'user':
        return jsonify({'success': False, 'message': '权限不足'}), 403

    try:
        ids = json.loads(request.form.get('ids', '[]'))
    except:
        return jsonify({'success': False, 'message': '参数错误'}), 400

    if not ids:
        return jsonify({'success': False, 'message': '请选择内容'}), 400

    count = 0
    for bulletin_id in ids:
        bulletin = Bulletin.query.get(bulletin_id)
        if bulletin:
            db.session.delete(bulletin)
            count += 1

    db.session.commit()
    add_log('batch_delete_bulletins', 'bulletin', 0, 'Deleted {} bulletins'.format(count))

    return jsonify({'success': True, 'message': '已删除 {} 个内容'.format(count)})
