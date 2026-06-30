# -*- coding: utf-8 -*-
"""
Online Documents blueprint.
Create, edit, view online documents with role-based permissions.
"""
import json
import html
import os
import re
from datetime import datetime
from flask import (Blueprint, render_template, request, redirect, url_for, flash,
                   session, jsonify, current_app, abort, send_file)
from app.extensions import db
from app.models import OnlineDocument, User, DocVersion
from app.decorators import login_required, require_role
from app.utils import (add_log, get_pagination, check_visible,
                       append_extension, content_disposition)
from app.importers import uploaded_file_path, import_document_content
from app.onlyoffice import (MIME_TYPES, build_document_key, build_editor_config,
    build_content_token, create_blank_office_file, is_onlyoffice_configured,
    office_type_from_extension, restore_file_version, safe_document_path,
    save_callback_file, validate_office_file, verify_callback_token,
    verify_content_token, checksum_file)
from app.utils import clean_original_filename, content_disposition, format_file_size
import tempfile
import uuid

docs_bp = Blueprint('docs', __name__, url_prefix='/docs')


def can_view_doc(doc):
    role = session.get('role', '')
    return role in ('super_admin', 'dept_admin') or doc.created_by == session.get('user_id') or check_visible(doc.view_roles, role)


def can_edit_doc(doc):
    return doc.created_by == session.get('user_id') or check_visible(doc.edit_roles, session.get('role', ''))


def require_doc_permission(doc, edit=False):
    if not (can_edit_doc(doc) if edit else can_view_doc(doc)):
        abort(403)


def normalize_doc_images_for_word(content):
    """Keep exported DOC images inside the printable page width."""
    if not content:
        return content

    def repl(match):
        tag = match.group(0)
        tag = re.sub(r'\s(width|height)\s*=\s*(".*?"|\'.*?\'|[^\s>]+)', '', tag, flags=re.I)
        style_match = re.search(r'\sstyle\s*=\s*("|\')(.*?)\1', tag, flags=re.I | re.S)
        fit_style = 'width:15.2cm;max-width:15.2cm;height:auto;'
        if style_match:
            style_text = style_match.group(2)
            style_text = re.sub(r'(^|;)\s*(width|height|max-width)\s*:[^;]*', '', style_text, flags=re.I)
            new_style = (style_text.rstrip(';') + ';' + fit_style).lstrip(';')
            start, end = style_match.span()
            tag = tag[:start] + ' style="' + new_style + '"' + tag[end:]
        else:
            insert_at = -2 if tag.endswith('/>') else -1
            tag = tag[:insert_at] + ' style="' + fit_style + '"' + tag[insert_at:]
        insert_at = -2 if tag.endswith('/>') else -1
        return tag[:insert_at] + ' width="575"' + tag[insert_at:]

    return re.sub(r'<img\b[^>]*>', repl, content, flags=re.I | re.S)


def normalize_doc_image_sources(content):
    """Keep common local image URLs displayable in online documents."""
    if not content:
        return content

    def repl(match):
        quote = match.group(1)
        src = match.group(2).strip()
        if src.startswith(('data:image/', 'http://', 'https://', '/static/')):
            return match.group(0)
        if src.startswith('static/'):
            src = '/' + src
        elif src.startswith('app/static/'):
            src = '/' + src[len('app/'):]
        return 'src={}{}{}'.format(quote, src, quote)

    return re.sub(r'src\s*=\s*([\"\'])(.*?)\1', repl, content, flags=re.I | re.S)


@docs_bp.route('/')
@login_required
def list_docs():
    """List online documents with filters."""
    page, per_page = get_pagination()
    user_role = session.get('role', '')
    user_id = session.get('user_id')

    status = request.args.get('status', '').strip()
    keyword = request.args.get('keyword', '').strip()
    file_type = request.args.get('file_type', '').strip().lower()

    query = OnlineDocument.query.filter(OnlineDocument.is_active == 1)

    # Role-based filter: users see docs they can view or own
    if user_role not in ('super_admin', 'dept_admin'):
        query = query.filter(
            db.or_(
                OnlineDocument.created_by == user_id,
                OnlineDocument.view_roles == 'all'
            )
        )

    if status:
        query = query.filter(OnlineDocument.status == status)

    if keyword:
        query = query.filter(OnlineDocument.title.like('%' + keyword + '%'))
    if file_type == 'legacy_html':
        query = query.filter(OnlineDocument.editor_kind == 'legacy_html')
    elif file_type in ('docx', 'xlsx', 'pptx'):
        query = query.filter(OnlineDocument.file_ext == file_type)

    query = query.order_by(OnlineDocument.updated_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    docs = pagination.items

    # Counts
    total = query.count()
    published = query.filter(OnlineDocument.status == 'published').count()
    draft = query.filter(OnlineDocument.status == 'draft').count()

    users_map = {u.id: u.username for u in User.query.all()}

    return render_template('docs/list.html',
                           docs=docs,
                           pagination=pagination,
                           users_dict=users_map,
                           status=status,
                           keyword=keyword,
                           file_type=file_type, format_file_size=format_file_size,
                           total=total,
                           published=published,
                           draft=draft,
                           user_role=user_role)


@docs_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_doc():
    """Create a new online document."""
    if request.method == 'POST':
        if session.get('role') not in ('super_admin', 'dept_admin'):
            abort(403)
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        view_roles = request.form.get('view_roles', 'all').strip()

        if not title:
            flash('文档标题不能为空', 'warning')
            return redirect(url_for('docs.create_doc'))

        doc = OnlineDocument(
            title=title,
            content=normalize_doc_image_sources(content),
            doc_type=request.form.get('doc_type', 'rich').strip(),
            status=request.form.get('status', 'draft').strip(),
            view_roles=view_roles,
            edit_roles=request.form.get('edit_roles', '["super_admin","dept_admin"]').strip(),
            related_type=request.form.get('related_type', '').strip(),
            related_id=request.form.get('related_id', 0, type=int),
            created_by=session['user_id']
        )
        db.session.add(doc)
        db.session.commit()

        add_log('create_doc', 'online_document', doc.id, 'Created doc: ' + title)
        flash('文档创建成功', 'success')
        return redirect(url_for('docs.view_doc', doc_id=doc.id))

    return render_template('docs/edit.html',
                           doc=None, is_edit=False)


@docs_bp.route('/<int:doc_id>')
@login_required
def view_doc(doc_id):
    """View an online document."""
    doc = OnlineDocument.query.get_or_404(doc_id)
    user_role = session.get('role', '')
    require_doc_permission(doc)
    if (doc.editor_kind or 'legacy_html') == 'onlyoffice':
        return redirect(url_for('docs.view_office_doc', doc_id=doc.id))

    # Permission check
    if user_role not in ('super_admin', 'dept_admin') and not check_visible(doc.view_roles, user_role):
        if doc.created_by != session.get('user_id'):
            flash('无权查看此文档', 'danger')
            return redirect(url_for('docs.list_docs'))

    can_edit = check_visible(doc.edit_roles, user_role) or (doc.created_by == session.get('user_id'))

    versions = DocVersion.query.filter_by(doc_id=doc_id).order_by(DocVersion.version_num.desc()).limit(20).all()
    return render_template('docs/view.html',
                           doc=doc, doc_content=normalize_doc_image_sources(doc.content or ''),
                           can_edit=can_edit, versions=versions)


@docs_bp.route('/<int:doc_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_doc(doc_id):
    """Edit an online document."""
    doc = OnlineDocument.query.get_or_404(doc_id)
    user_role = session.get('role', '')
    if (doc.editor_kind or 'legacy_html') == 'onlyoffice':
        require_doc_permission(doc)
        return redirect(url_for('docs.office_editor', doc_id=doc.id))

    # Permission check
    if not check_visible(doc.edit_roles, user_role) and doc.created_by != session.get('user_id'):
        flash('无权编辑此文档', 'danger')
        return redirect(url_for('docs.list_docs'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('文档标题不能为空', 'warning')
            return redirect(url_for('docs.edit_doc', doc_id=doc_id))

        # Save version before updating
        max_ver = db.session.query(db.func.max(DocVersion.version_num)).filter_by(doc_id=doc.id).scalar() or 0
        version = DocVersion(
            doc_id=doc.id,
            content=doc.content or '',
            title=doc.title,
            version_num=max_ver + 1,
            change_summary=title + ' - update',
            created_by=session['user_id']
        )
        db.session.add(version)

        doc.title = title
        doc.content = normalize_doc_image_sources(request.form.get('content', '').strip())
        doc.doc_type = request.form.get('doc_type', doc.doc_type).strip()
        doc.status = request.form.get('status', doc.status).strip()
        doc.view_roles = request.form.get('view_roles', doc.view_roles).strip()
        doc.edit_roles = request.form.get('edit_roles', doc.edit_roles).strip()
        doc.updated_at = datetime.utcnow()

        db.session.commit()
        add_log('edit_doc', 'online_document', doc.id, 'Edited doc: ' + title)
        flash('文档已更新 (版本 {})'.format(max_ver + 1), 'success')
        return redirect(url_for('docs.view_doc', doc_id=doc.id))

    can_edit = True
    return render_template('docs/edit.html',
                           doc=doc, doc_content=normalize_doc_image_sources(doc.content or ''), is_edit=True)


@docs_bp.route('/<int:doc_id>/delete', methods=['POST'])
@login_required
def delete_doc(doc_id):
    """Soft-delete an online document."""
    doc = OnlineDocument.query.get_or_404(doc_id)
    user_role = session.get('role', '')

    if user_role not in ('super_admin', 'dept_admin'):
        if doc.created_by != session.get('user_id'):
            flash('无权删除此文档', 'danger')
            return redirect(url_for('docs.list_docs'))

    doc.is_active = 0
    db.session.commit()
    add_log('delete_doc', 'online_document', doc_id, 'Deleted doc: ' + doc.title)
    flash('文档已删除', 'success')
    return redirect(url_for('docs.list_docs'))


@docs_bp.route('/<int:doc_id>/download')
@login_required
def download_doc(doc_id):
    """Download a document as Word-compatible .doc."""
    doc = OnlineDocument.query.get_or_404(doc_id)
    user_role = session.get('role', '')
    require_doc_permission(doc)
    if (doc.editor_kind or 'legacy_html') == 'onlyoffice':
        try:
            path = safe_document_path(doc.storage_relpath)
        except ValueError:
            abort(404)
        if not os.path.isfile(path): abort(404)
        response = send_file(path, mimetype=doc.mime_type or MIME_TYPES.get(doc.file_ext), conditional=True)
        response.headers['Content-Disposition'] = content_disposition(doc.original_filename or doc.title + '.' + doc.file_ext)
        return response

    if user_role not in ('super_admin', 'dept_admin') and not check_visible(doc.view_roles, user_role):
        if doc.created_by != session.get('user_id'):
            flash('无权下载此文档', 'danger')
            return redirect(url_for('docs.list_docs'))

    from flask import make_response
    content = normalize_doc_images_for_word(normalize_doc_image_sources(doc.content or '(空文档)'))
    doc_html = '''<!DOCTYPE html>
<html xmlns:o="urn:schemas-microsoft-com:office:office"
      xmlns:w="urn:schemas-microsoft-com:office:word"
      xmlns="http://www.w3.org/TR/REC-html40">
<head>
<meta charset="utf-8">
<title>{}</title>
<!--[if gte mso 9]>
<xml>
  <w:WordDocument>
    <w:View>Print</w:View>
    <w:Zoom>100</w:Zoom>
    <w:DoNotOptimizeForBrowser/>
  </w:WordDocument>
</xml>
<![endif]-->
<style>
@page Section1 {{ size: 21cm 29.7cm; margin: 2.54cm 3.18cm 2.54cm 3.18cm; }}
div.Section1 {{ page: Section1; }}
body {{ font-family: SimSun, "Microsoft YaHei", serif; font-size: 12pt; line-height: 1.8; }}
p {{ margin: 0 0 8pt 0; }}
table {{ border-collapse: collapse; width: 100%; }}
td, th {{ border: 1px solid #666; padding: 6px; }}
img {{ width: 15.2cm !important; max-width: 15.2cm !important; height: auto !important; }}
</style>
</head>
<body><div class="Section1">{}</div></body>
</html>'''.format(html.escape(doc.title), content)
    response = make_response(doc_html)
    response.headers['Content-Type'] = 'application/msword; charset=utf-8'
    response.headers['Content-Disposition'] = content_disposition(append_extension(doc.title, 'doc'))
    return response


@docs_bp.route('/api/list')
@login_required
def api_list():
    """JSON API for document list (used in task/bulletin integration)."""
    docs = OnlineDocument.query.filter_by(
        is_active=1, status='published'
    ).order_by(OnlineDocument.updated_at.desc()).limit(20).all()
    return jsonify([d.to_dict() for d in docs])


@docs_bp.route('/<int:doc_id>/versions')
@login_required
def doc_versions(doc_id):
    """View version history for a document."""
    doc = OnlineDocument.query.get_or_404(doc_id)
    require_doc_permission(doc)
    versions = DocVersion.query.filter_by(doc_id=doc_id).order_by(DocVersion.version_num.desc()).all()
    user_map = {u.id: u.username for u in User.query.all()}
    return render_template('docs/versions.html',
                           doc=doc, doc_versions=versions, users_dict=user_map)


@docs_bp.route('/<int:doc_id>/versions/<int:version_id>/restore', methods=['POST'])
@login_required
def restore_version(doc_id, version_id):
    """Restore a previous version of a document."""
    doc = OnlineDocument.query.get_or_404(doc_id)
    require_doc_permission(doc, edit=True)
    version = DocVersion.query.get_or_404(version_id)
    if version.doc_id != doc.id:
        flash('版本与文档不匹配', 'danger')
        return redirect(url_for('docs.view_doc', doc_id=doc.id))
    if (doc.editor_kind or 'legacy_html') == 'onlyoffice':
        try:
            restore_file_version(doc, version, session['user_id'])
            db.session.commit()
            add_log('restore_doc_version', 'online_document', doc.id, 'Restored Office version {}'.format(version.version_num))
            flash('已恢复 Office 历史版本', 'success')
        except (IOError, ValueError) as exc:
            db.session.rollback()
            flash(str(exc), 'danger')
        return redirect(url_for('docs.doc_versions', doc_id=doc.id))

    # Save current as a version first
    max_ver = db.session.query(db.func.max(DocVersion.version_num)).filter_by(doc_id=doc.id).scalar() or 0
    curr_version = DocVersion(
        doc_id=doc.id,
        content=doc.content or '',
        title=doc.title,
        version_num=max_ver + 1,
        change_summary='回退前自动保存 v' + str(version.version_num),
        created_by=session['user_id']
    )
    db.session.add(curr_version)

    # Restore old version
    doc.content = version.content
    doc.updated_at = datetime.utcnow()
    db.session.commit()

    add_log('restore_doc_version', 'online_document', doc.id,
            'Restored doc version {}'.format(version.version_num))
    flash('已回退到版本 {}'.format(version.version_num), 'success')
    return redirect(url_for('docs.view_doc', doc_id=doc.id))


@docs_bp.route('/import/<int:file_id>')
@login_required
def import_from_file(file_id):
    """Import an uploaded file as a new online document."""
    from app.models import File as FileModel
    from app.config import BASE_DIR

    file_record = FileModel.query.get_or_404(file_id)
    full_path = uploaded_file_path(file_record, BASE_DIR)
    ext = file_record.file_type.lower() if file_record.file_type else ''
    content, imported = import_document_content(full_path, ext)

    doc = OnlineDocument(
        title=file_record.original_name,
        content=content,
        doc_type='rich',
        status='draft',
        view_roles='all',
        edit_roles='["super_admin","dept_admin"]',
        related_type='file',
        related_id=file_id,
        created_by=session['user_id']
    )
    db.session.add(doc)
    db.session.commit()
    add_log('import_doc', 'online_document', doc.id, 'Imported from file: ' + file_record.original_name)
    if imported:
        flash('已导入文件内容，可继续编辑', 'success')
    else:
        flash('已创建在线文档，但源文件内容未能完整解析，请查看文档中的提示', 'warning')
    return redirect(url_for('docs.edit_doc', doc_id=doc.id))


@docs_bp.route('/create-office', methods=['POST'])
@login_required
@require_role('dept_admin')
def create_office_doc():
    ext = request.form.get('file_ext', '').lower().lstrip('.')
    office_type = office_type_from_extension(ext)
    if not office_type:
        flash('仅支持新建 Word、Excel 和 PowerPoint 文档', 'danger')
        return redirect(url_for('docs.list_docs'))
    title = request.form.get('title', '').strip() or {'docx': '新建 Word 文档', 'xlsx': '新建 Excel 表格', 'pptx': '新建 PowerPoint 演示文稿'}[ext]
    stored = uuid.uuid4().hex + '.' + ext
    relpath = datetime.utcnow().strftime('%Y-%m') + '/' + stored
    path = safe_document_path(relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        size, checksum = create_blank_office_file(path, ext)
        doc = OnlineDocument(title=title, content='', editor_kind='onlyoffice', office_type=office_type,
            file_ext=ext, original_filename=title + '.' + ext, stored_filename=stored,
            storage_relpath=relpath, mime_type=MIME_TYPES[ext], file_size=size,
            file_version=1, checksum=checksum, status='draft', view_roles='all',
            edit_roles='["super_admin","dept_admin"]', created_by=session['user_id'])
        db.session.add(doc); db.session.flush()
        doc.document_key = build_document_key(doc.id, 1, checksum)
        db.session.commit()
        add_log('create_office_doc', 'online_document', doc.id, 'Created Office document: ' + ext)
        return redirect(url_for('docs.edit_doc', doc_id=doc.id))
    except Exception:
        db.session.rollback()
        if os.path.exists(path): os.remove(path)
        current_app.logger.exception('Failed to create Office document')
        flash('创建 Office 文档失败', 'danger')
        return redirect(url_for('docs.list_docs'))


@docs_bp.route('/upload', methods=['POST'])
@login_required
@require_role('dept_admin')
def upload_office_doc():
    uploaded = request.files.get('file')
    original = clean_original_filename(uploaded.filename if uploaded else '', 'document')
    ext = original.rsplit('.', 1)[-1].lower() if '.' in original else ''
    if not uploaded or not office_type_from_extension(ext):
        flash('请选择 docx、xlsx 或 pptx 文件；旧格式请先转换', 'danger')
        return redirect(url_for('docs.list_docs'))
    fd, temporary = tempfile.mkstemp(suffix='.' + ext)
    os.close(fd)
    path = None
    try:
        uploaded.save(temporary)
        size, checksum = validate_office_file(temporary, ext)
        stored = uuid.uuid4().hex + '.' + ext
        relpath = datetime.utcnow().strftime('%Y-%m') + '/' + stored
        path = safe_document_path(relpath); os.makedirs(os.path.dirname(path), exist_ok=True)
        os.replace(temporary, path)
        title = original.rsplit('.', 1)[0]
        doc = OnlineDocument(title=title, content='', editor_kind='onlyoffice',
            office_type=office_type_from_extension(ext), file_ext=ext, original_filename=original,
            stored_filename=stored, storage_relpath=relpath, mime_type=MIME_TYPES[ext],
            file_size=size, file_version=1, checksum=checksum, status='draft', view_roles='all',
            edit_roles='["super_admin","dept_admin"]', created_by=session['user_id'])
        db.session.add(doc); db.session.flush(); doc.document_key = build_document_key(doc.id, 1, checksum)
        db.session.commit(); add_log('upload_office_doc', 'online_document', doc.id, 'Uploaded Office document: ' + ext)
        flash('Office 文档上传成功', 'success')
        return redirect(url_for('docs.edit_doc', doc_id=doc.id))
    except ValueError as exc:
        db.session.rollback()
        if path and os.path.exists(path): os.remove(path)
        flash(str(exc), 'danger')
    except Exception:
        db.session.rollback(); current_app.logger.exception('Office upload failed')
        if path and os.path.exists(path): os.remove(path)
        flash('上传失败，请检查文件', 'danger')
    finally:
        if os.path.exists(temporary): os.remove(temporary)
    return redirect(url_for('docs.list_docs'))


def render_office(doc, requested_edit):
    require_doc_permission(doc)
    can_edit = requested_edit and can_edit_doc(doc)
    user = User.query.get(session['user_id'])
    configured = is_onlyoffice_configured()
    config = build_editor_config(doc, user, can_edit) if configured else None
    return render_template('docs/onlyoffice_editor.html', doc=doc, editor_config=config,
        configured=configured, can_edit=can_edit,
        server_url=current_app.config.get('ONLYOFFICE_SERVER_URL', ''))


@docs_bp.route('/<int:doc_id>/view')
@login_required
def view_office_doc(doc_id):
    doc = OnlineDocument.query.get_or_404(doc_id)
    if (doc.editor_kind or 'legacy_html') != 'onlyoffice':
        return redirect(url_for('docs.view_doc', doc_id=doc.id))
    return render_office(doc, False)


@docs_bp.route('/<int:doc_id>/office-editor')
@login_required
def office_editor(doc_id):
    doc = OnlineDocument.query.get_or_404(doc_id)
    if (doc.editor_kind or 'legacy_html') != 'onlyoffice':
        return redirect(url_for('docs.edit_doc', doc_id=doc.id))
    return render_office(doc, True)


@docs_bp.route('/<int:doc_id>/content')
def document_content(doc_id):
    doc = OnlineDocument.query.get_or_404(doc_id)
    if doc.editor_kind != 'onlyoffice' or not verify_content_token(request.args.get('token'), doc_id, 'content'):
        abort(403)
    try: path = safe_document_path(doc.storage_relpath)
    except ValueError: abort(403)
    if not os.path.isfile(path): abort(404)
    return send_file(path, mimetype=doc.mime_type or MIME_TYPES.get(doc.file_ext), conditional=True)


@docs_bp.route('/<int:doc_id>/callback', methods=['POST'])
def onlyoffice_callback(doc_id):
    doc = OnlineDocument.query.get_or_404(doc_id)
    if doc.editor_kind != 'onlyoffice' or not verify_content_token(request.args.get('callback_token'), doc_id, 'callback'):
        return jsonify(error=1), 403
    payload = request.get_json(silent=True) or {}
    auth = request.headers.get('Authorization', '')
    token = auth[7:].strip() if auth.lower().startswith('bearer ') else payload.get('token', '')
    try:
        decoded = verify_callback_token(token)
        if decoded is not None and isinstance(decoded, dict):
            payload = decoded.get('payload', decoded)
        status = int(payload.get('status', 0))
        if status in (3, 7):
            current_app.logger.error('ONLYOFFICE reported save error for document %s status %s', doc_id, status)
            return jsonify(error=1)
        if status not in (2, 6): return jsonify(error=0)
        users = payload.get('users') or []
        editor_id = int(users[0]) if users and str(users[0]).isdigit() else (doc.last_editor_id or doc.created_by)
        save_callback_file(doc, payload.get('url'), editor_id, final_save=(status == 2))
        db.session.commit()
        add_log('onlyoffice_save', 'online_document', doc.id, 'ONLYOFFICE callback status {}'.format(status))
        return jsonify(error=0)
    except Exception:
        db.session.rollback(); current_app.logger.exception('ONLYOFFICE callback rejected for document %s', doc_id)
        return jsonify(error=1), 403


@docs_bp.route('/<int:doc_id>/rename', methods=['POST'])
@login_required
def rename_doc(doc_id):
    doc = OnlineDocument.query.get_or_404(doc_id); require_doc_permission(doc, edit=True)
    title = request.form.get('title', '').strip()
    if not title: flash('文档标题不能为空', 'warning')
    else:
        doc.title = title
        if doc.editor_kind == 'onlyoffice': doc.original_filename = title + '.' + doc.file_ext
        db.session.commit(); add_log('rename_doc', 'online_document', doc.id, 'Renamed document')
        flash('文档已重命名', 'success')
    return redirect(url_for('docs.list_docs'))


@docs_bp.route('/onlyoffice/status')
@login_required
@require_role('dept_admin')
def onlyoffice_status():
    cfg = current_app.config; health = False; detail = '未配置或未启用'
    if cfg.get('ONLYOFFICE_ENABLED') and cfg.get('ONLYOFFICE_SERVER_URL'):
        try:
            response = __import__('requests').get(cfg['ONLYOFFICE_SERVER_URL'] + '/healthcheck', timeout=(3, 5))
            health = response.ok and 'true' in response.text.lower(); detail = '正常' if health else '响应异常'
        except Exception: detail = 'Flask 无法连接 Document Server'
    writable = os.access(cfg['DOCUMENT_STORAGE_FOLDER'], os.W_OK)
    return jsonify(enabled=bool(cfg.get('ONLYOFFICE_ENABLED')), server_configured=bool(cfg.get('ONLYOFFICE_SERVER_URL')),
        jwt_enabled=bool(cfg.get('ONLYOFFICE_JWT_ENABLED')), document_server_reachable=health,
        health_detail=detail, storage_writable=writable,
        public_content_test='请在 Document Server 主机测试 APP_PUBLIC_URL/docs/<id>/content?token=<短时令牌>')
