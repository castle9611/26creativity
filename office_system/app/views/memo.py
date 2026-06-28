# -*- coding: utf-8 -*-
"""
Memo management blueprint.
Personal private memos + public shared memos.
"""
import json
from datetime import datetime
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session)
from app.extensions import db
from app.models import Memo, User, MemoGroup, File
from app.decorators import login_required, require_role
from app.utils import add_log, get_pagination, check_visible

memo_bp = Blueprint('memo', __name__)


@memo_bp.route('/')
@login_required
def list_memos():
    """Memo list - private + visible public memos."""
    page, per_page = get_pagination()
    user_id = session['user_id']
    user_role = session['role']

    memo_type = request.args.get('type', 'all').strip()
    keyword = request.args.get('keyword', '').strip()
    group_id = request.args.get('group_id', 0, type=int)

    # Build query: private memos (own) + public memos (visible)
    query = Memo.query.filter(Memo.is_archived == 0)

    if memo_type == 'private':
        query = query.filter(Memo.memo_type == 'private', Memo.created_by == user_id)
    elif memo_type == 'public':
        query = query.filter(Memo.memo_type == 'public')
    else:
        # 'all': own private + visible public
        query = query.filter(
            db.or_(
                db.and_(Memo.memo_type == 'private', Memo.created_by == user_id),
                Memo.memo_type == 'public'
            )
        )

    if keyword:
        query = query.filter(
            db.or_(
                Memo.title.like('%' + keyword + '%'),
                Memo.content.like('%' + keyword + '%')
            )
        )

    if group_id:
        query = query.filter(Memo.group_id == group_id)

    memos = query.order_by(Memo.created_at.desc()).all()

    # Filter public memos by visibility before slicing pages.
    filtered_memos = []
    for m in memos:
        if m.memo_type == 'private' and m.created_by == user_id:
            filtered_memos.append(m)
        elif m.memo_type == 'public' and check_visible(m.visible_roles, user_role):
            filtered_memos.append(m)

    # Rebuild simple pagination info
    total = len(filtered_memos)
    start = (page - 1) * per_page
    end = start + per_page
    page_memos = filtered_memos[start:end]

    has_prev = page > 1
    has_next = end < total

    # Memo statistics
    private_count = Memo.query.filter(Memo.memo_type == 'private', Memo.created_by == user_id, Memo.is_archived == 0).count()
    public_count = sum(
        1 for memo in Memo.query.filter(Memo.memo_type == 'public', Memo.is_archived == 0).all()
        if check_visible(memo.visible_roles, user_role)
    )
    memo_total_count = private_count + public_count
    groups = MemoGroup.query.filter(
        MemoGroup.is_active == 1,
        db.or_(MemoGroup.created_by == user_id, MemoGroup.memo_type == 'public')
    ).order_by(MemoGroup.memo_type.asc(), MemoGroup.sort_order.asc(), MemoGroup.name.asc()).all()

    # Build memo links data for all displayed memos
    from app.models import OnlineDocument, Spreadsheet
    memo_ids = [m.id for m in page_memos]
    memo_links = {}
    if memo_ids:
        all_docs = OnlineDocument.query.filter(
            OnlineDocument.related_type == 'memo',
            OnlineDocument.related_id.in_(memo_ids),
            OnlineDocument.is_active == 1
        ).all()
        all_sheets = Spreadsheet.query.filter(
            Spreadsheet.related_type == 'memo',
            Spreadsheet.related_id.in_(memo_ids),
            Spreadsheet.is_active == 1
        ).all()
        for mid in memo_ids:
            memo_links[mid] = {
                'docs': [{'id': d.id, 'title': d.title, 'url': url_for('docs.view_doc', doc_id=d.id)} for d in all_docs if d.related_id == mid],
                'sheets': [{'id': s.id, 'name': s.name, 'url': url_for('sheets.edit_sheet', sheet_id=s.id)} for s in all_sheets if s.related_id == mid],
            }

    # AJAX partial rendering for no-flash filtering
    if request.args.get('partial') == '1':
        html = render_template('memo/_list_content.html',
                               memos=page_memos,
                               groups=groups,
                               group_id=group_id,
                               page=page,
                               per_page=per_page,
                               total=total,
                               has_prev=has_prev,
                               has_next=has_next,
                               memo_type=memo_type,
                               keyword=keyword,
                               private_count=private_count,
                               public_count=public_count,
                               memo_total_count=memo_total_count,
                               memo_links=memo_links)
        return html

    return render_template('memo/list.html',
                           memos=page_memos,
                           groups=groups,
                           group_id=group_id,
                           page=page,
                           per_page=per_page,
                           total=total,
                           has_prev=has_prev,
                           has_next=has_next,
                           memo_type=memo_type,
                           keyword=keyword,
                           private_count=private_count,
                           public_count=public_count,
                           memo_total_count=memo_total_count,
                           memo_links=memo_links)


@memo_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_memo():
    """Create a new memo."""
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        memo_type = request.form.get('memo_type', 'private').strip()
        visible_roles = request.form.get('visible_roles', 'all').strip()
        group_id = request.form.get('group_id', 0, type=int)

        if not title:
            flash('备忘标题不能为空', 'warning')
            return redirect(url_for('memo.create_memo'))

        memo = Memo(
            title=title,
            content=content,
            memo_type=memo_type,
            group_id=group_id if group_id > 0 else None,
            visible_roles=visible_roles,
            created_by=session['user_id']
        )
        db.session.add(memo)
        db.session.flush()

        _save_memo_attachments(memo.id)

        # Link selected online docs/sheets
        from app.models import OnlineDocument, Spreadsheet
        linked_doc_ids = request.form.getlist('linked_doc_ids')
        linked_sheet_ids = request.form.getlist('linked_sheet_ids')
        for did in linked_doc_ids:
            doc = OnlineDocument.query.get(int(did))
            if doc:
                doc.related_type = 'memo'
                doc.related_id = memo.id
        for sid in linked_sheet_ids:
            sheet = Spreadsheet.query.get(int(sid))
            if sheet:
                sheet.related_type = 'memo'
                sheet.related_id = memo.id

        db.session.commit()

        add_log('create_memo', 'memo', memo.id, 'Created memo: ' + title)
        flash('备忘创建成功', 'success')
        return redirect(url_for('memo.list_memos'))

    groups = _visible_groups()
    from app.models import OnlineDocument, Spreadsheet
    available_docs = OnlineDocument.query.filter_by(is_active=1).order_by(OnlineDocument.updated_at.desc()).all()
    available_sheets = Spreadsheet.query.filter_by(is_active=1).order_by(Spreadsheet.updated_at.desc()).all()
    return render_template('memo/edit.html', memo=None, is_edit=False, groups=groups,
                           available_docs=available_docs, available_sheets=available_sheets)


@memo_bp.route('/<int:memo_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_memo(memo_id):
    """Edit a memo."""
    memo = Memo.query.get_or_404(memo_id)
    user_id = session['user_id']
    user_role = session['role']

    # Only creator or super_admin can edit
    if memo.created_by != user_id and user_role != 'super_admin':
        flash('无权执行此操作', 'danger')
        return redirect(url_for('memo.list_memos'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('标题不能为空', 'warning')
            return render_template('memo/edit.html', memo=memo, is_edit=True)

        memo.title = title
        memo.content = request.form.get('content', '').strip()
        memo.memo_type = request.form.get('memo_type', memo.memo_type).strip()
        group_id = request.form.get('group_id', 0, type=int)
        memo.group_id = group_id if group_id > 0 else None
        memo.visible_roles = request.form.get('visible_roles', memo.visible_roles).strip()
        memo.updated_at = datetime.utcnow()

        _delete_memo_attachments(memo.id, request.form.get('delete_attachments', ''))
        _save_memo_attachments(memo.id)

        # Update linked docs/sheets
        from app.models import OnlineDocument, Spreadsheet
        OnlineDocument.query.filter_by(related_type='memo', related_id=memo.id).update(
            {OnlineDocument.related_type: '', OnlineDocument.related_id: 0}
        )
        Spreadsheet.query.filter_by(related_type='memo', related_id=memo.id).update(
            {Spreadsheet.related_type: '', Spreadsheet.related_id: 0}
        )
        linked_doc_ids = request.form.getlist('linked_doc_ids')
        linked_sheet_ids = request.form.getlist('linked_sheet_ids')
        for did in linked_doc_ids:
            doc = OnlineDocument.query.get(int(did))
            if doc:
                doc.related_type = 'memo'
                doc.related_id = memo.id
        for sid in linked_sheet_ids:
            sheet = Spreadsheet.query.get(int(sid))
            if sheet:
                sheet.related_type = 'memo'
                sheet.related_id = memo.id

        db.session.commit()
        add_log('edit_memo', 'memo', memo.id, 'Edited memo: ' + title)
        flash('备忘更新成功', 'success')
        return redirect(url_for('memo.list_memos'))

    groups = _visible_groups()
    from app.models import OnlineDocument, Spreadsheet
    available_docs = OnlineDocument.query.filter_by(is_active=1).order_by(OnlineDocument.updated_at.desc()).all()
    available_sheets = Spreadsheet.query.filter_by(is_active=1).order_by(Spreadsheet.updated_at.desc()).all()
    linked_doc_ids = [d.id for d in OnlineDocument.query.filter_by(related_type='memo', related_id=memo.id)]
    linked_sheet_ids = [s.id for s in Spreadsheet.query.filter_by(related_type='memo', related_id=memo.id)]
    memo_attachments = File.query.filter_by(
        related_type='memo', related_id=memo.id, is_deleted=0
    ).order_by(File.created_at.asc()).all()
    return render_template('memo/edit.html', memo=memo, is_edit=True, groups=groups,
                           available_docs=available_docs, available_sheets=available_sheets,
                           linked_doc_ids=linked_doc_ids, linked_sheet_ids=linked_sheet_ids,
                           memo_attachments=memo_attachments)


def _save_memo_attachments(memo_id):
    """Save uploaded files as memo attachments."""
    import os
    from flask import current_app
    upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'memos', str(memo_id))
    os.makedirs(upload_folder, exist_ok=True)
    for f in request.files.getlist('attachments'):
        if not f or not f.filename:
            continue
        original = f.filename
        safe_name = datetime.now().strftime('%Y%m%d%H%M%S%f') + '_' + original
        file_path = os.path.join(upload_folder, safe_name)
        f.save(file_path)
        db.session.add(File(
            filename=safe_name,
            original_name=original,
            file_path='/static/uploads/memos/{}/{}'.format(memo_id, safe_name),
            file_size=os.path.getsize(file_path),
            file_type=original.rsplit('.', 1)[-1].lower() if '.' in original else '',
            related_type='memo',
            related_id=memo_id,
            uploaded_by=session['user_id']
        ))


def _delete_memo_attachments(memo_id, raw_ids):
    """Soft-delete memo attachment rows and remove files when requested."""
    if not raw_ids:
        return
    import os
    from flask import current_app
    ids_to_delete = [int(x) for x in raw_ids.split(',') if x.isdigit()]
    if not ids_to_delete:
        return
    files = File.query.filter(
        File.related_type == 'memo',
        File.related_id == memo_id,
        File.id.in_(ids_to_delete)
    ).all()
    for f in files:
        f.is_deleted = 1
        rel_path = f.file_path.lstrip('/').replace('/', os.sep)
        full_path = os.path.join(current_app.root_path, rel_path[7:] if rel_path.startswith('static' + os.sep) else rel_path)
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
            except OSError:
                pass


def _visible_groups():
    """Groups current user can use."""
    user_id = session['user_id']
    return MemoGroup.query.filter(
        MemoGroup.is_active == 1,
        db.or_(MemoGroup.created_by == user_id, MemoGroup.memo_type == 'public')
    ).order_by(MemoGroup.memo_type.asc(), MemoGroup.sort_order.asc(), MemoGroup.name.asc()).all()


@memo_bp.route('/groups/add', methods=['POST'])
@login_required
def add_group():
    """Create memo group."""
    name = request.form.get('name', '').strip()
    memo_type = request.form.get('memo_type', 'private').strip()
    if memo_type not in ('private', 'public'):
        memo_type = 'private'
    if not name:
        flash('分组名称不能为空', 'warning')
        return redirect(url_for('memo.list_memos'))
    if memo_type == 'public' and session.get('role') not in ('super_admin', 'dept_admin'):
        flash('只有管理员可以创建公共分组', 'danger')
        return redirect(url_for('memo.list_memos'))

    group = MemoGroup(name=name, memo_type=memo_type, created_by=session['user_id'])
    db.session.add(group)
    db.session.commit()
    add_log('create_memo_group', 'memo_group', group.id, 'Created memo group: ' + name)
    flash('备忘分组已创建', 'success')
    return redirect(url_for('memo.list_memos', type=memo_type, group_id=group.id))


@memo_bp.route('/<int:memo_id>/archive', methods=['POST'])
@login_required
def archive_memo(memo_id):
    """Archive a memo."""
    memo = Memo.query.get_or_404(memo_id)
    user_id = session['user_id']
    user_role = session['role']

    if memo.created_by != user_id and user_role != 'super_admin':
        flash('无权执行此操作', 'danger')
        return redirect(url_for('memo.list_memos'))

    memo.is_archived = 1
    memo.updated_at = datetime.utcnow()
    db.session.commit()

    add_log('archive_memo', 'memo', memo.id, 'Archived memo: ' + memo.title)
    flash('备忘已归档', 'success')
    return redirect(url_for('memo.list_memos'))


@memo_bp.route('/<int:memo_id>/restore', methods=['POST'])
@login_required
def restore_memo(memo_id):
    """Restore an archived memo."""
    memo = Memo.query.get_or_404(memo_id)
    user_id = session['user_id']
    user_role = session['role']

    if memo.created_by != user_id and user_role != 'super_admin':
        flash('无权执行此操作', 'danger')
        return redirect(url_for('memo.archived'))

    memo.is_archived = 0
    memo.updated_at = datetime.utcnow()
    db.session.commit()
    add_log('restore_memo', 'memo', memo.id, 'Restored memo: ' + memo.title)
    flash('备忘已恢复', 'success')
    return redirect(url_for('memo.archived'))


@memo_bp.route('/<int:memo_id>/delete', methods=['POST'])
@login_required
def delete_memo(memo_id):
    """Delete a memo."""
    memo = Memo.query.get_or_404(memo_id)
    user_id = session['user_id']
    user_role = session['role']

    if memo.created_by != user_id and user_role != 'super_admin':
        flash('无权执行此操作', 'danger')
        return redirect(url_for('memo.list_memos'))

    title = memo.title
    db.session.delete(memo)
    db.session.commit()

    add_log('delete_memo', 'memo', memo_id, 'Deleted memo: ' + title)
    flash('备忘已删除', 'success')
    return redirect(url_for('memo.list_memos'))


@memo_bp.route('/archived')
@login_required
def archived():
    """View archived memos."""
    page, per_page = get_pagination()
    user_id = session['user_id']
    user_role = session['role']

    query = Memo.query.filter(Memo.is_archived == 1)
    if user_role != 'super_admin':
        query = query.filter(Memo.created_by == user_id)
    query = query.order_by(Memo.updated_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return render_template('memo/list.html',
                           memos=pagination.items,
                           groups=_visible_groups(),
                           group_id=0,
                           page=page,
                           per_page=per_page,
                           total=pagination.total,
                           has_prev=pagination.has_prev,
                           has_next=pagination.has_next,
                           memo_type='archived',
                           keyword='',
                           memo_links={},
                           private_count=Memo.query.filter(Memo.memo_type == 'private', Memo.created_by == user_id, Memo.is_archived == 0).count(),
                           public_count=sum(
                               1 for memo in Memo.query.filter(Memo.memo_type == 'public', Memo.is_archived == 0).all()
                               if check_visible(memo.visible_roles, user_role)
                           ),
                           memo_total_count=(
                               Memo.query.filter(Memo.memo_type == 'private', Memo.created_by == user_id, Memo.is_archived == 0).count()
                               + sum(
                                   1 for memo in Memo.query.filter(Memo.memo_type == 'public', Memo.is_archived == 0).all()
                                   if check_visible(memo.visible_roles, user_role)
                               )
                           ))


@memo_bp.route('/batch-restore', methods=['POST'])
@login_required
def batch_restore():
    """Batch restore archived memos."""
    from flask import jsonify
    try:
        if request.content_type and 'json' in request.content_type:
            ids = request.get_json().get('ids', [])
        else:
            ids = json.loads(request.form.get('ids', '[]'))
    except:
        return jsonify({'success': False, 'message': '参数错误'}), 400

    if not ids:
        return jsonify({'success': False, 'message': '请选择备忘'}), 400

    user_id = session['user_id']
    user_role = session['role']
    count = 0
    for mid in ids:
        memo = Memo.query.get(mid)
        if memo and memo.is_archived == 1 and (memo.created_by == user_id or user_role == 'super_admin'):
            memo.is_archived = 0
            memo.updated_at = datetime.utcnow()
            count += 1

    db.session.commit()
    return jsonify({'success': True, 'message': '已恢复 {} 个备忘'.format(count)})


@memo_bp.route('/batch-archive', methods=['POST'])
@login_required
def batch_archive():
    """Batch archive memos."""
    from flask import jsonify
    try:
        if request.content_type and 'json' in request.content_type:
            ids = request.get_json().get('ids', [])
        else:
            ids = json.loads(request.form.get('ids', '[]'))
    except:
        return jsonify({'success': False, 'message': '参数错误'}), 400

    if not ids:
        return jsonify({'success': False, 'message': '请选择备忘'}), 400

    user_id = session['user_id']
    user_role = session['role']
    count = 0
    for mid in ids:
        memo = Memo.query.get(mid)
        if memo and (memo.created_by == user_id or user_role == 'super_admin'):
            memo.is_archived = 1
            memo.updated_at = datetime.utcnow()
            count += 1

    db.session.commit()
    return jsonify({'success': True, 'message': '已归档 {} 个备忘'.format(count)})


@memo_bp.route('/batch-delete', methods=['POST'])
@login_required
def batch_delete():
    """Batch delete memos."""
    from flask import jsonify
    try:
        if request.content_type and 'json' in request.content_type:
            ids = request.get_json().get('ids', [])
        else:
            ids = json.loads(request.form.get('ids', '[]'))
    except:
        return jsonify({'success': False, 'message': '参数错误'}), 400

    if not ids:
        return jsonify({'success': False, 'message': '请选择备忘'}), 400

    user_id = session['user_id']
    user_role = session['role']
    count = 0
    for mid in ids:
        memo = Memo.query.get(mid)
        if memo and (memo.created_by == user_id or user_role == 'super_admin'):
            db.session.delete(memo)
            count += 1

    db.session.commit()
    return jsonify({'success': True, 'message': '已删除 {} 个备忘'.format(count)})
