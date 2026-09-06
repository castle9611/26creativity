# -*- coding: utf-8 -*-
"""Nextcloud + ONLYOFFICE unified entry."""
from flask import Blueprint, render_template, request

from app.decorators import login_required
from app.nextcloud import cloud_home_url, connection_status, is_nextcloud_configured, search_files


cloud_bp = Blueprint('cloud', __name__, url_prefix='/cloud-office')


@cloud_bp.route('/')
@login_required
def index():
    keyword = request.args.get('q', '').strip()
    results = []
    error = ''
    if keyword and is_nextcloud_configured():
        try:
            results = search_files(keyword, 30)
        except Exception as exc:
            error = '云盘 搜索失败：' + str(exc).replace('Nextcloud', '云盘')
    return render_template('cloud/index.html', keyword=keyword, results=results, error=error,
                           configured=is_nextcloud_configured(), cloud_url=cloud_home_url())


@cloud_bp.route('/status')
@login_required
def status():
    ok, message = connection_status()
    return {'success': ok, 'message': message}
