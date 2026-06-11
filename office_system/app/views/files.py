# -*- coding: utf-8 -*-
"""
File management blueprint.
Upload / download / delete / association binding.
"""
import os
import uuid
from datetime import datetime
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, send_file, jsonify)
from app.extensions import db
from app.models import (File, FileRelation, User, BulletinCategory, Task,
                        TaskAssignee, Bulletin, Memo)
from app.decorators import login_required, require_role
from app.utils import (add_log, get_pagination, format_file_size,
                       clean_original_filename, get_file_extension,
                       content_disposition, check_visible)

files_bp = Blueprint('files', __name__)


def infer_category_id(related_type, related_id, category_id=0):
    """Use explicit category, or infer from related task/bulletin."""
    if category_id:
        return category_id
    if related_type == 'task' and related_id:
        task = Task.query.get(related_id)
        return task.category_id if task else None
    if related_type == 'bulletin' and related_id:
        bulletin = Bulletin.query.get(related_id)
        return bulletin.category_id if bulletin else None
    return None


def infer_category_from_relations(relations, category_id=0):
    """Use explicit category, or infer from the first related task/bulletin."""
    if category_id:
        return category_id
    for target_type, target_id in relations:
        inferred = infer_category_id(target_type, target_id)
        if inferred:
            return inferred
    return None


def parse_relation_values(values):
    """Parse relation select values like task:12 into unique tuples."""
    parsed = []
    seen = set()
    for value in values:
        if not value or ':' not in value:
            continue
        target_type, raw_id = value.split(':', 1)
        target_type = target_type.strip()
        if target_type not in ('task', 'bulletin', 'memo'):
            continue
        try:
            target_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if target_id <= 0:
            continue
        key = (target_type, target_id)
        if key not in seen:
            seen.add(key)
            parsed.append(key)
    return parsed


def parse_request_relations():
    """Read relation selections, keeping old related_type/related_id posts compatible."""
    relations = parse_relation_values(request.form.getlist('relations'))
    if relations:
        return relations
    legacy_type = request.form.get('related_type', '').strip()
    legacy_id = request.form.get('related_id', 0, type=int)
    if legacy_type in ('task', 'bulletin', 'memo') and legacy_id:
        return [(legacy_type, legacy_id)]
    return []


def sync_file_relations(file_record, relations):
    """Replace relation rows and keep legacy single relation fields in sync."""
    FileRelation.query.filter_by(file_id=file_record.id).delete()
    for target_type, target_id in relations:
        db.session.add(FileRelation(
            file_id=file_record.id,
            target_type=target_type,
            target_id=target_id
        ))
    if relations:
        file_record.related_type, file_record.related_id = relations[0]
    else:
        file_record.related_type = ''
        file_record.related_id = 0


def relation_title(target_type, target_id):
    """Return a human label for a relation target."""
    label_map = {'task': '任务', 'bulletin': '公示', 'memo': '备忘'}
    model_map = {'task': Task, 'bulletin': Bulletin, 'memo': Memo}
    model = model_map.get(target_type)
    obj = model.query.get(target_id) if model else None
    title = getattr(obj, 'title', '') if obj else ''
    return label_map.get(target_type, '事项') + '：' + (title or ('#' + str(target_id)))


def relation_labels_for(file_records):
    """Build display labels for file relations."""
    labels = {}
    file_ids = [f.id for f in file_records]
    if not file_ids:
        return labels
    rows = FileRelation.query.filter(FileRelation.file_id.in_(file_ids)).order_by(FileRelation.id.asc()).all()
    for rel in rows:
        labels.setdefault(rel.file_id, []).append(relation_title(rel.target_type, rel.target_id))
    for file_record in file_records:
        if file_record.id not in labels and file_record.related_type and file_record.related_id:
            labels[file_record.id] = [relation_title(file_record.related_type, file_record.related_id)]
    return labels


def relation_choices(user_role, user_id, user_dept):
    """Return selectable relation targets for the current user."""
    task_query = Task.query
    if user_role == 'dept_admin':
        task_query = task_query.filter(Task.department == user_dept)
    elif user_role == 'user':
        task_query = task_query.filter(db.or_(
            Task.creator_id == user_id,
            Task.assignee_id == user_id,
            Task.assignee_links.any(TaskAssignee.user_id == user_id)
        ))
    tasks = task_query.order_by(Task.updated_at.desc()).limit(80).all()

    bulletins = Bulletin.query.filter(
        Bulletin.status == 'published',
        Bulletin.is_active == 1
    ).order_by(Bulletin.created_at.desc()).limit(80).all()
    bulletins = [
        b for b in bulletins
        if (b.column and check_visible(b.column.visible_roles, user_role))
        or (b.category and check_visible(b.category.visible_roles, user_role))
        or (not b.column and not b.category)
    ]

    memo_query = Memo.query.filter(Memo.is_archived == 0)
    if user_role != 'super_admin':
        memo_query = memo_query.filter(db.or_(
            db.and_(Memo.memo_type == 'private', Memo.created_by == user_id),
            Memo.memo_type == 'public'
        ))
    memos = memo_query.order_by(Memo.updated_at.desc()).limit(80).all()
    memos = [
        m for m in memos
        if user_role == 'super_admin'
        or (m.memo_type == 'private' and m.created_by == user_id)
        or (m.memo_type == 'public' and check_visible(m.visible_roles, user_role))
    ]

    return {'tasks': tasks, 'bulletins': bulletins, 'memos': memos}


def allowed_file(filename):
    """Allow any ordinary file name in the intranet file manager."""
    return bool(filename and filename.strip())


def get_upload_dir():
    """Get upload directory for today (organized by date)."""
    from app.config import Config
    base = Config.UPLOAD_FOLDER
    today = datetime.utcnow().strftime('%Y-%m')
    upload_dir = os.path.join(base, today)
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)
    return upload_dir


@files_bp.route('/')
@login_required
def list_files():
    """File list with filters."""
    page, per_page = get_pagination()
    user_id = session['user_id']
    user_role = session['role']
    user_dept = session['department']

    related_type = request.args.get('related_type', '').strip()
    related_id = request.args.get('related_id', '', type=int)
    file_type = request.args.get('file_type', '').strip()
    category_id = request.args.get('category_id', '', type=int)
    keyword = request.args.get('keyword', '').strip()

    query = File.query.filter(File.is_deleted == 0)

    # Role-based filtering
    if user_role == 'super_admin':
        pass
    elif user_role == 'dept_admin':
        # Dept admin sees files uploaded by users in same department
        dept_user_ids = [u.id for u in User.query.filter_by(department=user_dept).all()]
        query = query.filter(File.uploaded_by.in_(dept_user_ids))
    else:
        query = query.filter(File.uploaded_by == user_id)

    if related_type:
        query = query.filter(db.or_(
            File.related_type == related_type,
            File.relation_links.any(FileRelation.target_type == related_type)
        ))
    if related_id:
        query = query.filter(db.or_(
            File.related_id == related_id,
            File.relation_links.any(FileRelation.target_id == related_id)
        ))
    if file_type:
        query = query.filter(File.file_type == file_type)
    if category_id:
        query = query.filter(File.category_id == category_id)
    if keyword:
        query = query.filter(File.original_name.like('%' + keyword + '%'))

    query = query.order_by(File.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    file_list = pagination.items

    # File statistics
    stats_query = File.query.filter(File.is_deleted == 0)
    if user_role == 'super_admin':
        pass
    elif user_role == 'dept_admin':
        dept_user_ids = [u.id for u in User.query.filter_by(department=user_dept).all()]
        stats_query = stats_query.filter(File.uploaded_by.in_(dept_user_ids))
    else:
        stats_query = stats_query.filter(File.uploaded_by == user_id)

    total_files = stats_query.count()
    total_size = sum(f.file_size or 0 for f in stats_query.all())
    task_files = stats_query.filter(db.or_(
        File.related_type == 'task',
        File.relation_links.any(FileRelation.target_type == 'task')
    )).count()
    bulletin_files = stats_query.filter(db.or_(
        File.related_type == 'bulletin',
        File.relation_links.any(FileRelation.target_type == 'bulletin')
    )).count()

    users_map = {u.id: u.username for u in User.query.all()}
    categories = BulletinCategory.query.filter_by(is_active=1).order_by(BulletinCategory.sort_order.asc()).all()

    return render_template('files/list.html',
                           files=file_list,
                           pagination=pagination,
                           users_dict=users_map,
                           related_type=related_type,
                           related_id=related_id,
                           file_type=file_type,
                           category_id=category_id,
                           categories=categories,
                           relation_choices=relation_choices(user_role, user_id, user_dept),
                           relation_labels=relation_labels_for(file_list),
                           keyword=keyword,
                           total_files=total_files,
                           total_size=total_size,
                           task_files=task_files,
                           bulletin_files=bulletin_files)


@files_bp.route('/upload', methods=['POST'])
@login_required
def upload():
    """Upload a file."""
    if 'file' not in request.files:
        flash('未选择文件', 'warning')
        return redirect(request.referrer or url_for('files.list_files'))

    file_obj = request.files['file']
    if not file_obj or file_obj.filename == '':
        flash('未选择文件', 'warning')
        return redirect(request.referrer or url_for('files.list_files'))

    if not allowed_file(file_obj.filename):
        flash('不支持的文件类型', 'danger')
        return redirect(request.referrer or url_for('files.list_files'))

    # Keep readable original name, but store a UUID filename with original extension.
    original_name = clean_original_filename(file_obj.filename)
    ext = get_file_extension(original_name)
    unique_name = str(uuid.uuid4()).replace('-', '')[:16]
    if ext:
        unique_name = unique_name + '.' + ext

    upload_dir = get_upload_dir()
    save_path = os.path.join(upload_dir, unique_name)

    try:
        file_obj.save(save_path)
        file_size = os.path.getsize(save_path)
    except Exception as e:
        flash('上传失败: ' + str(e), 'danger')
        return redirect(request.referrer or url_for('files.list_files'))

    relations = parse_request_relations()
    category_id = infer_category_from_relations(
        relations,
        request.form.get('category_id', 0, type=int)
    )

    # Determine file type category
    file_type = ext

    file_record = File(
        filename=unique_name,
        original_name=original_name,
        file_path=os.path.relpath(save_path, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        file_size=file_size,
        file_type=file_type,
        category_id=category_id,
        related_type='',
        related_id=0,
        uploaded_by=session['user_id']
    )
    db.session.add(file_record)
    db.session.flush()
    sync_file_relations(file_record, relations)
    db.session.commit()

    add_log('upload_file', 'file', file_record.id,
            'Uploaded: ' + original_name)
    flash('文件上传成功', 'success')
    return redirect(request.referrer or url_for('files.list_files'))


@files_bp.route('/<int:file_id>/download')
@login_required
def download(file_id):
    """Download a file."""
    file_record = File.query.get_or_404(file_id)
    user_role = session['role']
    user_id = session['user_id']

    # Permission check
    if user_role not in ('super_admin', 'dept_admin'):
        if file_record.uploaded_by != user_id:
            flash('无权执行此操作', 'danger')
            return redirect(url_for('files.list_files'))

    from app.config import Config, BASE_DIR
    # file_path is stored as relative path from BASE_DIR, e.g. "data/uploads/2026-06/xxx.ext"
    full_path = os.path.join(BASE_DIR, file_record.file_path.replace('/', os.sep))

    if not os.path.exists(full_path):
        flash('文件不存在', 'danger')
        return redirect(url_for('files.list_files'))

    add_log('download_file', 'file', file_id,
            'Downloaded: ' + file_record.original_name)

    response = send_file(full_path, as_attachment=True)
    response.headers['Content-Disposition'] = content_disposition(file_record.original_name)
    return response


@files_bp.route('/<int:file_id>/preview')
@login_required
def preview(file_id):
    """Preview a file inline (images, PDF, text)."""
    file_record = File.query.get_or_404(file_id)
    user_role = session['role']
    user_id = session['user_id']

    if user_role not in ('super_admin', 'dept_admin'):
        if file_record.uploaded_by != user_id:
            flash('无权执行此操作', 'danger')
            return redirect(url_for('files.list_files'))

    from app.config import Config, BASE_DIR
    full_path = os.path.join(BASE_DIR, file_record.file_path.replace('/', os.sep))

    if not os.path.exists(full_path):
        return jsonify({'success': False, 'message': '文件不存在'}), 404

    ext = file_record.file_type.lower() if file_record.file_type else ''

    # Images: serve directly for inline viewing
    if ext in ('jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp'):
        return send_file(full_path, mimetype='image/' + ext)

    # PDF
    if ext == 'pdf':
        return send_file(full_path, mimetype='application/pdf')

    # Text files: read and return as plain text
    if ext in ('txt', 'csv', 'log', 'md', 'json', 'xml', 'yaml', 'yml'):
        try:
            with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            return render_template('files/preview.html',
                                   file=file_record,
                                   relation_labels=relation_labels_for([file_record]).get(file_record.id, []),
                                   content=content,
                                   preview_type='text')
        except Exception as e:
            return jsonify({'success': False, 'message': '无法读取文件: ' + str(e)}), 500

    # Office documents: show info page
    if ext in ('doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'):
        return render_template('files/preview.html',
                               file=file_record,
                               relation_labels=relation_labels_for([file_record]).get(file_record.id, []),
                               content='',
                               preview_type='office')

    return render_template('files/preview.html',
                           file=file_record,
                           relation_labels=relation_labels_for([file_record]).get(file_record.id, []),
                           content='',
                           preview_type='unknown')


@files_bp.route('/<int:file_id>/save-text', methods=['POST'])
@login_required
def save_text(file_id):
    """Save edited text content back to file (AJAX)."""
    file_record = File.query.get_or_404(file_id)
    from app.config import Config, BASE_DIR
    full_path = os.path.join(BASE_DIR, file_record.file_path.replace('/', os.sep))
    if not os.path.exists(full_path):
        return jsonify({'success': False, 'message': '文件不存在'}), 404
    content = request.form.get('content', '')
    try:
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({'success': True, 'message': '保存成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@files_bp.route('/<int:file_id>/delete', methods=['POST'])
@login_required
def delete_file(file_id):
    """Soft-delete a file."""
    file_record = File.query.get_or_404(file_id)
    user_role = session['role']
    user_id = session['user_id']

    # Permission: owner, dept_admin, or super_admin
    if user_role == 'user' and file_record.uploaded_by != user_id:
        flash('无权执行此操作', 'danger')
        return redirect(url_for('files.list_files'))

    if user_role == 'dept_admin':
        uploader = User.query.get(file_record.uploaded_by)
        if uploader and uploader.department != session['department']:
            flash('无权执行此操作', 'danger')
            return redirect(url_for('files.list_files'))

    file_record.is_deleted = 1
    db.session.commit()

    add_log('delete_file', 'file', file_id,
            'Deleted: ' + file_record.original_name)
    flash('文件已删除', 'success')
    return redirect(request.referrer or url_for('files.list_files'))


@files_bp.route('/api/upload', methods=['POST'])
@login_required
def api_upload():
    """AJAX upload endpoint for KindEditor and other editors."""
    if 'file' not in request.files:
        return jsonify({'error': 1, 'message': 'No file'})

    file_obj = request.files['file']
    if not file_obj or file_obj.filename == '':
        return jsonify({'error': 1, 'message': 'No file'})

    if not allowed_file(file_obj.filename):
        return jsonify({'error': 1, 'message': '不支持的文件类型'})

    original_name = clean_original_filename(file_obj.filename)
    ext = get_file_extension(original_name)
    unique_name = str(uuid.uuid4()).replace('-', '')[:16]
    if ext:
        unique_name = unique_name + '.' + ext

    upload_dir = get_upload_dir()
    save_path = os.path.join(upload_dir, unique_name)

    try:
        file_obj.save(save_path)
        file_size = os.path.getsize(save_path)
    except Exception as e:
        return jsonify({'error': 1, 'message': str(e)})

    relations = parse_request_relations()
    file_record = File(
        filename=unique_name,
        original_name=original_name,
        file_path=os.path.relpath(save_path, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        file_size=file_size,
        file_type=ext,
        category_id=infer_category_from_relations(
            relations,
            request.form.get('category_id', 0, type=int)
        ),
        related_type='',
        related_id=0,
        uploaded_by=session['user_id']
    )
    db.session.add(file_record)
    db.session.flush()
    sync_file_relations(file_record, relations)
    db.session.commit()

    # Return URL for editor
    file_url = url_for('files.download', file_id=file_record.id)
    return jsonify({'error': 0, 'url': file_url})
