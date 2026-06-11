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
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, jsonify)
from app.extensions import db
from app.models import OnlineDocument, User, DocVersion
from app.decorators import login_required, require_role
from app.utils import (add_log, get_pagination, check_visible,
                       append_extension, content_disposition)
from app.importers import uploaded_file_path, import_document_content

docs_bp = Blueprint('docs', __name__, url_prefix='/docs')


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
                           total=total,
                           published=published,
                           draft=draft,
                           user_role=user_role)


@docs_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_doc():
    """Create a new online document."""
    if request.method == 'POST':
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
    versions = DocVersion.query.filter_by(doc_id=doc_id).order_by(DocVersion.version_num.desc()).all()
    user_map = {u.id: u.username for u in User.query.all()}
    return render_template('docs/versions.html',
                           doc=doc, doc_versions=versions, users_dict=user_map)


@docs_bp.route('/<int:doc_id>/versions/<int:version_id>/restore', methods=['POST'])
@login_required
def restore_version(doc_id, version_id):
    """Restore a previous version of a document."""
    doc = OnlineDocument.query.get_or_404(doc_id)
    version = DocVersion.query.get_or_404(version_id)
    if version.doc_id != doc.id:
        flash('版本与文档不匹配', 'danger')
        return redirect(url_for('docs.view_doc', doc_id=doc.id))

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
