# -*- coding: utf-8 -*-
"""
Online Spreadsheets blueprint.
Create, edit, view spreadsheets using x-spreadsheet with role-based permissions.
Export to CSV/Excel format.
"""
import json
import os
import html
from datetime import datetime
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, jsonify)
from app.extensions import db
from app.models import Spreadsheet, User, SheetVersion
from app.decorators import login_required
from app.utils import (add_log, get_pagination, check_visible,
                       append_extension, content_disposition)
from app.importers import uploaded_file_path, import_spreadsheet_rows, rows_to_xspreadsheet_data

sheets_bp = Blueprint('sheets', __name__, url_prefix='/sheets')


def _first_sheet_data(raw_data):
    """Return first x-spreadsheet sheet object from stored JSON."""
    try:
        data = json.loads(raw_data) if raw_data else {}
    except (json.JSONDecodeError, TypeError):
        return {}
    if isinstance(data, list):
        return data[0] if data else {}
    if isinstance(data, dict):
        return data
    return {}


def _has_sheet_content(data):
    """Return True when parsed x-spreadsheet data contains visible cell data."""
    if isinstance(data, list):
        return any(_has_sheet_content(item) for item in data)
    if not isinstance(data, dict):
        return False

    celldata = data.get('celldata')
    if isinstance(celldata, list) and len(celldata) > 0:
        return True

    rows = data.get('rows')
    if isinstance(rows, dict):
        for row in rows.values():
            if isinstance(row, dict):
                cells = row.get('cells')
                if isinstance(cells, dict) and cells:
                    return True
    return False


def _sheet_rows(raw_data):
    """Convert common x-spreadsheet data shapes into a row dictionary."""
    data = _first_sheet_data(raw_data)
    rows = {}

    celldata = data.get('celldata', []) if isinstance(data, dict) else []
    if celldata:
        for cell in celldata:
            r = cell.get('r', 0)
            c = cell.get('c', 0)
            value = cell.get('v', '')
            if isinstance(value, dict):
                value = value.get('text', value.get('v', ''))
            rows.setdefault(int(r), {})[int(c)] = '' if value is None else str(value)
        return rows

    row_data = data.get('rows', {}) if isinstance(data, dict) else {}
    if isinstance(row_data, dict):
        for r_key, row in row_data.items():
            if not isinstance(row, dict):
                continue
            cells = row.get('cells', {})
            if not isinstance(cells, dict):
                continue
            try:
                r = int(r_key)
            except (TypeError, ValueError):
                continue
            for c_key, cell in cells.items():
                try:
                    c = int(c_key)
                except (TypeError, ValueError):
                    continue
                value = cell.get('text', cell.get('v', '')) if isinstance(cell, dict) else cell
                rows.setdefault(r, {})[c] = '' if value is None else str(value)
    return rows


@sheets_bp.route('/')
@login_required
def list_sheets():
    """List spreadsheets."""
    page, per_page = get_pagination()
    user_role = session.get('role', '')
    user_id = session.get('user_id')

    keyword = request.args.get('keyword', '').strip()

    query = Spreadsheet.query.filter(Spreadsheet.is_active == 1)

    if user_role not in ('super_admin', 'dept_admin'):
        query = query.filter(
            db.or_(
                Spreadsheet.created_by == user_id,
                Spreadsheet.view_roles == 'all'
            )
        )

    if keyword:
        query = query.filter(Spreadsheet.name.like('%' + keyword + '%'))

    query = query.order_by(Spreadsheet.updated_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    sheets = pagination.items

    users_map = {u.id: u.username for u in User.query.all()}

    return render_template('sheets/list.html',
                           sheets=sheets,
                           pagination=pagination,
                           users_dict=users_map,
                           keyword=keyword,
                           user_role=user_role)


@sheets_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_sheet():
    """Create a new spreadsheet."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('表格名称不能为空', 'warning')
            return redirect(url_for('sheets.create_sheet'))

        view_roles = request.form.get('view_roles', 'all').strip()
        edit_roles = request.form.get('edit_roles', '["super_admin","dept_admin"]').strip()

        # Initialize with empty x-spreadsheet data
        default_data = '[]'

        sheet = Spreadsheet(
            name=name,
            sheet_data=request.form.get('sheet_data', default_data),
            status=request.form.get('status', 'draft').strip(),
            view_roles=view_roles,
            edit_roles=edit_roles,
            related_type=request.form.get('related_type', '').strip(),
            related_id=request.form.get('related_id', 0, type=int),
            created_by=session['user_id']
        )
        db.session.add(sheet)
        db.session.commit()

        add_log('create_sheet', 'spreadsheet', sheet.id, 'Created sheet: ' + name)
        flash('表格创建成功', 'success')
        return redirect(url_for('sheets.edit_sheet', sheet_id=sheet.id))

    return render_template('sheets/create.html')


@sheets_bp.route('/<int:sheet_id>')
@login_required
def view_sheet(sheet_id):
    """View a spreadsheet (read-only)."""
    sheet = Spreadsheet.query.get_or_404(sheet_id)
    user_role = session.get('role', '')

    if user_role not in ('super_admin', 'dept_admin') and not check_visible(sheet.view_roles, user_role):
        if sheet.created_by != session.get('user_id'):
            flash('无权查看此表格', 'danger')
            return redirect(url_for('sheets.list_sheets'))

    can_edit = check_visible(sheet.edit_roles, user_role) or (sheet.created_by == session.get('user_id'))

    return render_template('sheets/view.html', sheet=sheet, can_edit=can_edit)


@sheets_bp.route('/<int:sheet_id>/publish', methods=['POST'])
@login_required
def publish_sheet(sheet_id):
    """Publish a spreadsheet (AJAX)."""
    sheet = Spreadsheet.query.get_or_404(sheet_id)
    sheet.status = 'published'
    sheet.updated_at = datetime.utcnow()
    db.session.commit()
    add_log('publish_sheet', 'spreadsheet', sheet.id, 'Published sheet: ' + sheet.name)
    return jsonify({'success': True, 'message': '已发布'})


@sheets_bp.route('/<int:sheet_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_sheet(sheet_id):
    """Edit a spreadsheet."""
    sheet = Spreadsheet.query.get_or_404(sheet_id)
    user_role = session.get('role', '')

    if not check_visible(sheet.edit_roles, user_role) and sheet.created_by != session.get('user_id'):
        flash('无权编辑此表格', 'danger')
        return redirect(url_for('sheets.list_sheets'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('表格名称不能为空', 'warning')
            return redirect(url_for('sheets.edit_sheet', sheet_id=sheet_id))

        # Save version before updating
        max_ver = db.session.query(db.func.max(SheetVersion.version_num)).filter_by(sheet_id=sheet.id).scalar() or 0
        version = SheetVersion(
            sheet_id=sheet.id,
            sheet_data=sheet.sheet_data or '',
            name=sheet.name,
            version_num=max_ver + 1,
            change_summary=name + ' - update',
            created_by=session['user_id']
        )
        db.session.add(version)

        sheet.name = name
        sheet_data = request.form.get('sheet_data', '')
        if sheet_data:
            sheet.sheet_data = sheet_data
        sheet.view_roles = request.form.get('view_roles', sheet.view_roles).strip()
        sheet.edit_roles = request.form.get('edit_roles', sheet.edit_roles).strip()
        sheet.status = request.form.get('status', sheet.status).strip()
        sheet.updated_at = datetime.utcnow()
        db.session.commit()

        add_log('edit_sheet', 'spreadsheet', sheet.id, 'Edited sheet: ' + name)
        flash('表格已更新 (版本 {})'.format(max_ver + 1), 'success')
        return redirect(url_for('sheets.edit_sheet', sheet_id=sheet.id))

    return render_template('sheets/edit.html',
                           sheet=sheet, is_edit=True)


@sheets_bp.route('/<int:sheet_id>/save', methods=['POST'])
@login_required
def save_sheet_data(sheet_id):
    """AJAX save spreadsheet data."""
    sheet = Spreadsheet.query.get_or_404(sheet_id)
    user_role = session.get('role', '')

    if user_role not in ('super_admin', 'dept_admin'):
        if sheet.created_by != session.get('user_id'):
            return jsonify({'success': False, 'message': '权限不足'}), 403

    raw = request.get_data(as_text=True)
    if raw is None or raw == '':
        return jsonify({'success': False, 'message': '数据为空'}), 400

    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, (list, dict)):
            return jsonify({'success': False, 'message': '数据格式错误: 表格数据必须是对象或数组'}), 400
        try:
            existing_data = json.loads(sheet.sheet_data) if sheet.sheet_data else []
        except (json.JSONDecodeError, TypeError):
            existing_data = []
        if _has_sheet_content(existing_data) and not _has_sheet_content(parsed):
            return jsonify({'success': False, 'message': '保存内容为空，已保留原表格内容'}), 400
        sheet.sheet_data = raw
        sheet.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True, 'message': '保存成功'})
    except (json.JSONDecodeError, TypeError) as e:
        return jsonify({'success': False, 'message': '数据格式错误: ' + str(e)}), 400


@sheets_bp.route('/<int:sheet_id>/load')
@login_required
def load_sheet_data(sheet_id):
    """AJAX load spreadsheet data."""
    from flask import Response as Resp, make_response
    sheet = Spreadsheet.query.get_or_404(sheet_id)
    data = sheet.sheet_data if sheet.sheet_data and len(sheet.sheet_data) > 10 else '[]'
    resp = make_response(data)
    resp.headers['Content-Type'] = 'application/json; charset=utf-8'
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


@sheets_bp.route('/<int:sheet_id>/delete', methods=['POST'])
@login_required
def delete_sheet(sheet_id):
    """Soft-delete a spreadsheet."""
    sheet = Spreadsheet.query.get_or_404(sheet_id)
    user_role = session.get('role', '')

    if user_role not in ('super_admin', 'dept_admin'):
        if sheet.created_by != session.get('user_id'):
            flash('无权删除此表格', 'danger')
            return redirect(url_for('sheets.list_sheets'))

    sheet.is_active = 0
    db.session.commit()
    add_log('delete_sheet', 'spreadsheet', sheet_id, 'Deleted sheet: ' + sheet.name)
    flash('表格已删除', 'success')
    return redirect(url_for('sheets.list_sheets'))


@sheets_bp.route('/<int:sheet_id>/export/csv')
@login_required
def export_csv(sheet_id):
    """Backward-compatible old endpoint. Default export is XLS now."""
    return redirect(url_for('sheets.export_xls', sheet_id=sheet_id))


@sheets_bp.route('/<int:sheet_id>/export/xls')
@login_required
def export_xls(sheet_id):
    """Export spreadsheet data as Excel-compatible .xls HTML."""
    sheet = Spreadsheet.query.get_or_404(sheet_id)
    user_role = session.get('role', '')

    if user_role not in ('super_admin', 'dept_admin') and not check_visible(sheet.view_roles, user_role):
        if sheet.created_by != session.get('user_id'):
            flash('无权导出此表格', 'danger')
            return redirect(url_for('sheets.list_sheets'))

    from flask import make_response

    rows = _sheet_rows(sheet.sheet_data)
    table_rows = []
    if rows:
        max_col = max(max(cols.keys()) for cols in rows.values())
        for r in range(max(rows.keys()) + 1):
            row_data = rows.get(r, {})
            cells = []
            for c in range(max_col + 1):
                cells.append('<td style="mso-number-format:\\@;">{}</td>'.format(
                    html.escape(row_data.get(c, ''))
                ))
            table_rows.append('<tr>{}</tr>'.format(''.join(cells)))
    else:
        table_rows.append('<tr><td></td></tr>')

    xls_html = '''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
table {{ border-collapse: collapse; }}
td {{ border: 1px solid #999; padding: 4px; }}
</style>
</head>
<body>
<table>{}</table>
</body>
</html>'''.format(''.join(table_rows))
    response = make_response(xls_html)
    response.headers['Content-Type'] = 'application/vnd.ms-excel; charset=utf-8'
    response.headers['Content-Disposition'] = content_disposition(append_extension(sheet.name, 'xls'))
    return response


@sheets_bp.route('/api/list')
@login_required
def api_list():
    """JSON API for spreadsheet list."""
    sheets = Spreadsheet.query.filter_by(
        is_active=1, status='published'
    ).order_by(Spreadsheet.updated_at.desc()).limit(20).all()
    return jsonify([s.to_dict() for s in sheets])


@sheets_bp.route('/<int:sheet_id>/versions')
@login_required
def sheet_versions(sheet_id):
    """View version history for a spreadsheet."""
    sheet = Spreadsheet.query.get_or_404(sheet_id)
    versions = SheetVersion.query.filter_by(sheet_id=sheet_id).order_by(SheetVersion.version_num.desc()).all()
    user_map = {u.id: u.username for u in User.query.all()}
    return render_template('sheets/versions.html',
                           sheet=sheet, sheet_versions=versions, users_dict=user_map)


@sheets_bp.route('/<int:sheet_id>/versions/<int:version_id>/restore', methods=['POST'])
@login_required
def restore_sheet_version(sheet_id, version_id):
    """Restore a previous version of a spreadsheet."""
    sheet = Spreadsheet.query.get_or_404(sheet_id)
    version = SheetVersion.query.get_or_404(version_id)
    if version.sheet_id != sheet.id:
        flash('版本与表格不匹配', 'danger')
        return redirect(url_for('sheets.list_sheets'))

    # Save current as version first
    max_ver = db.session.query(db.func.max(SheetVersion.version_num)).filter_by(sheet_id=sheet.id).scalar() or 0
    curr_ver = SheetVersion(
        sheet_id=sheet.id,
        sheet_data=sheet.sheet_data or '',
        name=sheet.name,
        version_num=max_ver + 1,
        change_summary='回退前自动保存 v' + str(version.version_num),
        created_by=session['user_id']
    )
    db.session.add(curr_ver)

    sheet.sheet_data = version.sheet_data
    sheet.updated_at = datetime.utcnow()
    db.session.commit()

    add_log('restore_sheet_version', 'spreadsheet', sheet.id,
            'Restored sheet version {}'.format(version.version_num))
    flash('已回退到版本 {}'.format(version.version_num), 'success')
    return redirect(url_for('sheets.edit_sheet', sheet_id=sheet.id))


@sheets_bp.route('/import/<int:file_id>')
@login_required
def import_from_file(file_id):
    """Import an uploaded spreadsheet/text file as a new spreadsheet."""
    from app.models import File as FileModel
    from app.config import BASE_DIR

    file_record = FileModel.query.get_or_404(file_id)
    ext = file_record.file_type.lower() if file_record.file_type else ''
    full_path = uploaded_file_path(file_record, BASE_DIR)
    rows, imported, message = import_spreadsheet_rows(full_path, ext)
    if not imported:
        rows = [['导入提示'], [message or '未能解析源文件内容，请转换为 XLSX 或 CSV 后再导入']]
    sheet_data = json.dumps(rows_to_xspreadsheet_data(rows, file_record.original_name), ensure_ascii=False)

    sheet = Spreadsheet(
        name=file_record.original_name,
        sheet_data=sheet_data,
        status='draft',
        view_roles='all',
        edit_roles='["super_admin","dept_admin"]',
        related_type='file',
        related_id=file_id,
        created_by=session['user_id']
    )
    db.session.add(sheet)
    db.session.commit()
    add_log('import_sheet', 'spreadsheet', sheet.id, 'Imported from file: ' + file_record.original_name)
    if imported:
        flash('已导入表格内容，可继续编辑', 'success')
    else:
        flash('已创建在线表格，但源文件内容未能完整解析，请查看表格中的提示', 'warning')
    return redirect(url_for('sheets.edit_sheet', sheet_id=sheet.id))
