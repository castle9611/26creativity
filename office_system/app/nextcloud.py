# -*- coding: utf-8 -*-
"""Small Nextcloud WebDAV client used by the OA search and cloud-office page."""
import base64
import hashlib
import json
import os
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from flask import current_app


DAV = '{DAV:}'
OC = '{http://owncloud.org/ns}'
LARGE_UPLOAD_THRESHOLD = 100 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 20 * 1024 * 1024
MAX_SYNC_FILE_SIZE = 50 * 1024 * 1024 * 1024


def _db_settings():
    """Load administrator-managed values without making DB config mandatory."""
    try:
        from app.models import SystemConfig
        keys = (
            'nextcloud_enabled', 'nextcloud_url', 'nextcloud_username',
            'nextcloud_app_password', 'nextcloud_root_path',
            'nextcloud_verify_ssl', 'nextcloud_timeout',
            'nextcloud_share_groups', 'nextcloud_file_share_groups')
        rows = SystemConfig.query.filter(SystemConfig.config_key.in_(keys)).all()
        return {row.config_key: row.config_value for row in rows}
    except Exception:
        return {}


def _bool_value(value, default=False):
    if value is None or value == '':
        return default
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def is_nextcloud_configured():
    cfg = _config()
    return bool(cfg['enabled'] and cfg['url'] and cfg['username'] and cfg['password'])


def _config():
    cfg = current_app.config
    saved = _db_settings()
    timeout_value = saved.get('nextcloud_timeout', cfg.get('NEXTCLOUD_TIMEOUT', 8))
    try:
        timeout_value = max(2, int(timeout_value))
    except (TypeError, ValueError):
        timeout_value = 8
    return {
        'enabled': _bool_value(saved.get('nextcloud_enabled'), cfg.get('NEXTCLOUD_ENABLED', False)),
        'url': saved.get('nextcloud_url', cfg.get('NEXTCLOUD_URL', '')).strip().rstrip('/'),
        'username': saved.get('nextcloud_username', cfg.get('NEXTCLOUD_USERNAME', '')).strip(),
        'password': saved.get('nextcloud_app_password', cfg.get('NEXTCLOUD_APP_PASSWORD', '')),
        'root': saved.get('nextcloud_root_path', cfg.get('NEXTCLOUD_ROOT_PATH', '')).strip('/'),
        'verify': _bool_value(saved.get('nextcloud_verify_ssl'), cfg.get('NEXTCLOUD_VERIFY_SSL', True)),
        'timeout': timeout_value,
        'share_groups': saved.get('nextcloud_share_groups', '[]'),
        'file_share_groups': saved.get('nextcloud_file_share_groups', '[]'),
    }


def _selected_share_groups(cfg=None, setting='share_groups'):
    cfg = cfg or _config()
    value = cfg.get(setting) or '[]'
    try:
        groups = json.loads(value)
    except (TypeError, ValueError):
        groups = [item.strip() for item in str(value).split(',')]
    return [str(item).strip() for item in groups if str(item).strip()]


def cloud_home_url():
    cfg = _config()
    if not cfg['url']:
        return ''
    folder = '/' + cfg['root'] if cfg['root'] else '/'
    return cfg['url'] + '/index.php/apps/files/?dir=' + quote(folder, safe='/')


def _request(cfg, url, method='GET', data=None, headers=None, timeout=None):
    request_headers = dict(headers or {})
    credentials = (cfg['username'] + ':' + cfg['password']).encode('utf-8')
    request_headers['Authorization'] = 'Basic ' + base64.b64encode(credentials).decode('ascii')
    req = Request(url, data=data, headers=request_headers)
    req.get_method = lambda: method
    context = None
    if url.lower().startswith('https://') and not cfg['verify']:
        context = ssl._create_unverified_context()
    response = urlopen(req, timeout=timeout or cfg['timeout'], context=context)
    try:
        return response.read(), response.getcode()
    finally:
        response.close()


def _ocs_json(cfg, path, method='GET', fields=None):
    """Call an OCS endpoint and enforce its application-level status code."""
    fields = fields or {}
    url = cfg['url'] + path
    data = None
    if method == 'GET' and fields:
        url += ('&' if '?' in path else '?') + urlencode(fields)
    elif fields:
        data = urlencode(fields).encode('utf-8')
    body, status = _request(cfg, url, method=method, data=data, headers={
        'OCS-APIRequest': 'true',
        'Accept': 'application/json',
        'Content-Type': 'application/x-www-form-urlencoded; charset=utf-8',
    })
    result = json.loads(body.decode('utf-8'))
    ocs = result.get('ocs', {})
    meta = ocs.get('meta', {})
    if int(meta.get('statuscode', 100)) not in (100, 200):
        raise RuntimeError(meta.get('message') or 'Nextcloud OCS 请求失败')
    return ocs.get('data', {})


def list_share_groups():
    """Return group IDs visible to the configured sharing account."""
    if not is_nextcloud_configured():
        return [], '请先完整配置 Nextcloud 账号和应用密码'
    cfg = _config()
    try:
        data = _ocs_json(cfg, '/ocs/v2.php/cloud/groups', fields={
            'format': 'json', 'limit': 500,
        })
        groups = data.get('groups', []) if isinstance(data, dict) else []
        return sorted(set(str(item) for item in groups)), ''
    except Exception as exc:
        current_app.logger.warning('Nextcloud group list failed: %s', exc)
        return [], '无法读取 Nextcloud 分组，请确认专用账号具有查看分组的权限'


def _load_group_share_state(cfg):
    """Load all group shares once so a batch can skip completed folders."""
    endpoint = '/ocs/v2.php/apps/files_sharing/api/v1/shares'
    data = _ocs_json(cfg, endpoint, fields={'format': 'json'})
    state = set()
    for item in data if isinstance(data, list) else []:
        if str(item.get('share_type', '')) != '1':
            continue
        path = str(item.get('path') or item.get('file_target') or '').strip('/')
        group_id = str(item.get('share_with') or '')
        if path and group_id:
            state.add((path, group_id))
    return state


def _group_shares_complete(cfg, relative_folder, setting, state):
    selected = _selected_share_groups(cfg, setting)
    path = relative_folder.strip('/')
    return bool(selected) and all((path, group_id) in state for group_id in selected)


def _ensure_group_shares(cfg, relative_folder, setting='share_groups', cache=None,
                         share_state=None):
    """Add selected group shares only. Existing and deselected shares are untouched."""
    cache_key = setting + ':' + relative_folder.strip('/')
    if cache is not None and cache_key in cache:
        return 0
    selected = _selected_share_groups(cfg, setting)
    if not selected:
        if cache is not None:
            cache.add(cache_key)
        return 0
    normalized_path = relative_folder.strip('/')
    share_path = '/' + normalized_path
    endpoint = '/ocs/v2.php/apps/files_sharing/api/v1/shares'
    if share_state is None:
        data = _ocs_json(cfg, endpoint, fields={
            'format': 'json', 'path': share_path, 'reshares': 'true',
        })
        shares = data if isinstance(data, list) else []
        existing = set()
        for item in shares:
            if str(item.get('share_type', '')) == '1':
                existing.add(str(item.get('share_with', '')))
    else:
        existing = set(group_id for path, group_id in share_state
                       if path == normalized_path)
    created = 0
    for group_id in selected:
        if group_id in existing:
            continue
        _ocs_json(cfg, endpoint + '?format=json', method='POST', fields={
            'path': share_path, 'shareType': '1', 'shareWith': group_id,
            'permissions': '15',
        })
        if share_state is not None:
            share_state.add((normalized_path, group_id))
        created += 1
    if cache is not None:
        cache.add(cache_key)
    return created


def _managed_file_parts(item):
    """Resolve one file-manager record to its category/column/type cloud folders."""
    from app.models import Bulletin, FileRelation
    category = item.category
    column = None
    relation = FileRelation.query.filter_by(
        file_id=item.id, target_type='bulletin').order_by(FileRelation.id.asc()).first()
    bulletin_id = relation.target_id if relation else (
        item.related_id if item.related_type == 'bulletin' else 0)
    bulletin = Bulletin.query.get(bulletin_id) if bulletin_id else None
    if bulletin:
        category = bulletin.category or category
        column = bulletin.column
    parts = []
    if category:
        parts.append(safe_cloud_name(category.name))
        if column:
            parts.append(safe_cloud_name(column.name))
        parts.append('文件资料')
    else:
        parts.append('未分类文件')
    extension = (item.file_type or '').lower()
    if extension in ('doc', 'docx', 'odt', 'txt', 'md', 'pdf'):
        parts.append('文档')
    elif extension in ('xls', 'xlsx', 'ods', 'csv'):
        parts.append('表格')
    elif extension in ('ppt', 'pptx', 'odp'):
        parts.append('演示')
    elif extension in ('jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'):
        parts.append('图片')
    elif extension in ('mp3', 'wav', 'm4a', 'aac', 'ogg', 'flac'):
        parts.append('音频')
    elif extension in ('mp4', 'webm', 'ogv', 'mov', 'm4v'):
        parts.append('视频')
    else:
        parts.append('其他')
    return parts


def managed_file_cloud_path(item, cfg=None):
    """Return the deterministic target path used to skip unchanged uploads."""
    cfg = cfg or _config()
    parts = _managed_file_parts(item)
    parts.append('文件-{}'.format(item.id))
    folder = '/'.join([value for value in [cfg['root']] + parts if value])
    return folder + '/' + safe_cloud_name(item.original_name, '未命名文件')


def _managed_file_share_parts(parts):
    """Share category parents, avoiding duplicate File Materials mounts."""
    if parts and parts[0] == '未分类文件':
        return parts[:1]
    return parts[:1]


def sync_managed_file_shares(context=None):
    """Backfill selected shares even when the corresponding files already synced."""
    from app.models import File
    if not is_nextcloud_configured():
        return 0
    cfg = _config()
    context = context or {}
    folder_cache = context.setdefault('folder_cache', set())
    share_cache = context.setdefault('share_cache', set())
    if not context.get('folders_loaded'):
        folder_cache.update(_load_existing_folders(cfg))
        context['folders_loaded'] = True
    share_state = context.get('share_state')
    if share_state is None:
        share_state = _load_group_share_state(cfg)
        context['share_state'] = share_state
    roots = []
    for item in File.query.filter_by(is_deleted=0).order_by(File.id.asc()).all():
        parts = _managed_file_parts(item)
        share_parts = _managed_file_share_parts(parts)
        share_root = '/'.join([value for value in [cfg['root']] + share_parts if value])
        roots.append(share_root)
    unique_roots = list(dict.fromkeys(roots))
    for share_root in unique_roots:
        if _group_shares_complete(cfg, share_root, 'file_share_groups', share_state):
            share_cache.add('file_share_groups:' + share_root.strip('/'))
            continue
        _ensure_cloud_folders(cfg, share_root, folder_cache)
        _ensure_group_shares(cfg, share_root, setting='file_share_groups',
                             cache=share_cache, share_state=share_state)
    return len(unique_roots)


def _file_url(cfg, file_id, path):
    if file_id:
        return cfg['url'] + '/index.php/f/' + quote(str(file_id))
    folder = '/' + '/'.join(path.split('/')[:-1])
    return cfg['url'] + '/index.php/apps/files/?dir=' + quote(folder or '/', safe='/')


def _folder_url(cfg, path):
    return cfg['url'] + '/index.php/apps/files/?dir=' + quote('/' + path.strip('/'), safe='/')


def safe_cloud_name(value, fallback='未命名'):
    """Keep business labels readable while preventing accidental path nesting."""
    cleaned = ''.join('_' if ch in '/\\\x00' or ord(ch) < 32 else ch for ch in (value or '').strip())
    cleaned = cleaned.rstrip('. ')
    return cleaned or fallback


def _dav_file_url(cfg, relative_path):
    parts = [quote(part, safe='') for part in relative_path.strip('/').split('/') if part]
    return cfg['url'] + '/remote.php/dav/files/' + quote(cfg['username'], safe='') + '/' + '/'.join(parts)


def _dav_upload_url(cfg, upload_id, name=''):
    url = (cfg['url'] + '/remote.php/dav/uploads/' +
           quote(cfg['username'], safe='') + '/' + quote(upload_id, safe=''))
    if name:
        url += '/' + quote(name, safe='')
    return url


def _existing_upload_chunks(cfg, upload_id):
    """Return chunk names and sizes so interrupted uploads can resume."""
    body = (b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:">'
            b'<d:prop><d:getcontentlength/><d:displayname/></d:prop></d:propfind>')
    try:
        response_body, status = _request(
            cfg, _dav_upload_url(cfg, upload_id), method='PROPFIND', data=body,
            headers={'Depth': '1', 'Content-Type': 'text/xml; charset=utf-8'},
            timeout=max(cfg['timeout'], 60))
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    root = ElementTree.fromstring(response_body)
    chunks = {}
    for item in root.findall(DAV + 'response'):
        prop = item.find('.//' + DAV + 'prop')
        if prop is None:
            continue
        name = prop.findtext(DAV + 'displayname') or ''
        if name.isdigit():
            chunks[name] = int(prop.findtext(DAV + 'getcontentlength') or 0)
    return chunks


def _chunked_upload(cfg, local_path, relative_path):
    """Upload through Nextcloud chunking v2 without loading the file into memory."""
    total_size = os.path.getsize(local_path)
    stat = os.stat(local_path)
    fingerprint = '{}|{}|{}'.format(relative_path, total_size, int(stat.st_mtime))
    upload_id = 'oa-' + hashlib.sha1(fingerprint.encode('utf-8')).hexdigest()
    destination = _dav_file_url(cfg, relative_path)
    common_headers = {
        'Destination': destination,
        'OC-Total-Length': str(total_size),
    }
    existing = _existing_upload_chunks(cfg, upload_id)
    if existing is None:
        _request(cfg, _dav_upload_url(cfg, upload_id), method='MKCOL',
                 headers={'Destination': destination}, timeout=max(cfg['timeout'], 60))
        existing = {}
    with open(local_path, 'rb') as source:
        index = 1
        while True:
            content = source.read(UPLOAD_CHUNK_SIZE)
            if not content:
                break
            chunk_name = '{:05d}'.format(index)
            if existing.get(chunk_name) != len(content):
                _request(cfg, _dav_upload_url(cfg, upload_id, chunk_name), method='PUT',
                         data=content, headers=common_headers,
                         timeout=max(cfg['timeout'], 300))
            index += 1
    move_headers = dict(common_headers)
    move_headers['X-OC-Mtime'] = str(int(stat.st_mtime))
    move_headers['Overwrite'] = 'T'
    _request(cfg, _dav_upload_url(cfg, upload_id, '.file'), method='MOVE',
             headers=move_headers, timeout=max(cfg['timeout'], 1800))


def _load_existing_folders(cfg):
    """Fetch the folder tree once; fall back to MKCOL checks if unsupported."""
    body = (b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:">'
            b'<d:prop><d:resourcetype/></d:prop></d:propfind>')
    try:
        response_body, status = _request(
            cfg, _dav_file_url(cfg, cfg['root']), method='PROPFIND', data=body,
            headers={'Depth': 'infinity', 'Content-Type': 'text/xml; charset=utf-8'})
        root = ElementTree.fromstring(response_body)
        prefix = '/remote.php/dav/files/' + cfg['username'] + '/'
        folders = set()
        for item in root.findall(DAV + 'response'):
            resource_type = item.find('.//' + DAV + 'resourcetype')
            if resource_type is None or resource_type.find(DAV + 'collection') is None:
                continue
            href = unquote(item.findtext(DAV + 'href') or '')
            path = urlparse(href).path
            relative = path.split(prefix, 1)[-1] if prefix in path else ''
            relative = relative.strip('/')
            if relative:
                folders.add(relative)
        return folders
    except Exception as exc:
        current_app.logger.warning('Nextcloud folder preload failed, using MKCOL checks: %s', exc)
        return set()


def _ensure_cloud_folders(cfg, relative_folder, cache=None):
    current = ''
    for part in [item for item in relative_folder.strip('/').split('/') if item]:
        current = current + '/' + part
        cache_key = current.strip('/')
        if cache is not None and cache_key in cache:
            continue
        try:
            _request(cfg, _dav_file_url(cfg, current), method='MKCOL')
        except HTTPError as exc:
            # 405 means the collection already exists.  A 409 is a real
            # parent/path conflict and must be reported instead of hidden.
            if exc.code != 405:
                raise
        if cache is not None:
            cache.add(cache_key)


def sync_business_folders():
    """Create missing category/column folders. Never move or delete cloud content."""
    from app.models import BulletinCategory, Column
    if not is_nextcloud_configured():
        return 0, 'Nextcloud 尚未完整配置'
    cfg = _config()
    folder_paths = []
    categories = BulletinCategory.query.order_by(BulletinCategory.id.asc()).all()
    columns = Column.query.order_by(Column.id.asc()).all()
    columns_by_category = {}
    for column in columns:
        columns_by_category.setdefault(column.category_id, []).append(column)
    for category in categories:
        category_path = '/'.join(item for item in (cfg['root'], safe_cloud_name(category.name)) if item)
        folder_paths.append(category_path)
        for column in columns_by_category.get(category.id, []):
            folder_paths.append(category_path + '/' + safe_cloud_name(column.name))
    unique_paths = list(dict.fromkeys(folder_paths))
    folder_cache = _load_existing_folders(cfg)
    share_cache = set()
    share_state = _load_group_share_state(cfg)
    for path in unique_paths:
        _ensure_cloud_folders(cfg, path, folder_cache)
    for category in categories:
        category_path = '/'.join(item for item in (cfg['root'], safe_cloud_name(category.name)) if item)
        _ensure_group_shares(cfg, category_path, cache=share_cache,
                             share_state=share_state)
    return len(unique_paths), ''


def ensure_business_folder(category, column=None):
    """Best-effort creation after one category/column save; no deletion counterpart exists."""
    if not is_nextcloud_configured() or not category:
        return False
    cfg = _config()
    path = '/'.join(item for item in (cfg['root'], safe_cloud_name(category.name)) if item)
    if column:
        path += '/' + safe_cloud_name(column.name)
    try:
        _ensure_cloud_folders(cfg, path)
        category_path = '/'.join(item for item in (cfg['root'], safe_cloud_name(category.name)) if item)
        _ensure_group_shares(cfg, category_path)
        return True
    except Exception as exc:
        current_app.logger.warning('Nextcloud folder ensure failed for %s: %s', path, exc)
        return False


def _lookup_file_id(cfg, relative_path):
    body = b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns"><d:prop><oc:fileid/></d:prop></d:propfind>'
    response_body, status = _request(cfg, _dav_file_url(cfg, relative_path), method='PROPFIND', data=body,
                                     headers={'Depth': '0', 'Content-Type': 'text/xml; charset=utf-8'})
    root = ElementTree.fromstring(response_body)
    return root.findtext('.//' + OC + 'fileid') or ''


def sync_attachment(record, context=None):
    """Upload one CloudAttachment. Errors are stored and do not abort OA saves."""
    import os
    from datetime import datetime
    from app.extensions import db

    if not is_nextcloud_configured():
        record.sync_status = 'pending'
        record.sync_error = 'Nextcloud 尚未配置专用账号或应用密码'
        return False
    cfg = _config()
    context = context or {}
    folder_cache = context.setdefault('folder_cache', set())
    share_cache = context.setdefault('share_cache', set())
    share_state = context.get('share_state')
    labels = {'task': '任务', 'bulletin': '公示', 'memo': '备忘'}
    business_parts = []
    managed_file = None
    try:
        if record.category_id:
            from app.models import BulletinCategory, Column
            category = BulletinCategory.query.get(record.category_id)
            column = Column.query.get(record.column_id) if record.column_id else None
            if category:
                business_parts.append(safe_cloud_name(category.name))
            if column:
                business_parts.append(safe_cloud_name(column.name))
        elif record.target_type == 'bulletin':
            from app.models import Bulletin
            item = Bulletin.query.get(record.target_id)
            if item and item.category:
                business_parts.append(safe_cloud_name(item.category.name))
            if item and item.column:
                business_parts.append(safe_cloud_name(item.column.name))
        elif record.target_type == 'task':
            from app.models import Task
            item = Task.query.get(record.target_id)
            if item and item.category:
                business_parts.append(safe_cloud_name(item.category.name))
        elif record.target_type == 'memo':
            from app.models import Memo
            item = Memo.query.get(record.target_id)
            business_parts.append('备忘')
            if item and item.group:
                business_parts.append(safe_cloud_name(item.group.name))
        elif record.target_type == 'file':
            from app.models import File
            managed_file = File.query.get(record.target_id)
            if managed_file:
                business_parts = _managed_file_parts(managed_file)
    except Exception:
        business_parts = []
    if record.target_type == 'file':
        if not business_parts:
            business_parts = ['未分类文件', '其他']
        # Keep duplicate original names isolated without changing the visible filename.
        business_parts.append('文件-{}'.format(record.target_id))
    else:
        business_parts.append('{}-{}'.format(labels.get(record.target_type, record.target_type), record.target_id))
    folder = '/'.join([item for item in [cfg['root']] + business_parts if item])
    safe_name = safe_cloud_name(record.original_name, '未命名文件')
    relative_path = folder + '/' + safe_name
    try:
        if not os.path.isfile(record.local_path):
            raise IOError('本地附件不存在')
        file_size = os.path.getsize(record.local_path)
        if file_size > MAX_SYNC_FILE_SIZE:
            raise ValueError('单个文件不能超过 50GB')
        _ensure_cloud_folders(cfg, folder, folder_cache)
        if record.target_type == 'file':
            share_parts = _managed_file_share_parts(business_parts)
            _ensure_group_shares(cfg, '/'.join(
                item for item in [cfg['root']] + share_parts if item),
                                 setting='file_share_groups', cache=share_cache)
        if file_size >= LARGE_UPLOAD_THRESHOLD:
            _chunked_upload(cfg, record.local_path, relative_path)
        else:
            with open(record.local_path, 'rb') as source:
                content = source.read()
            _request(cfg, _dav_file_url(cfg, relative_path), method='PUT', data=content,
                     headers={'Content-Type': 'application/octet-stream'},
                     timeout=max(cfg['timeout'], 300))
        file_id = _lookup_file_id(cfg, relative_path)
        record.cloud_path = relative_path
        record.cloud_file_id = file_id
        record.cloud_url = _file_url(cfg, file_id, relative_path)
        record.sync_status = 'synced'
        record.sync_error = ''
        record.synced_at = datetime.utcnow()
        return True
    except Exception as exc:
        record.sync_status = 'failed'
        record.sync_error = str(exc)[:1000]
        return False


def queue_attachment(target_type, target_id, local_path, original_name, user_id,
                     category_id=None, column_id=None):
    """Create a durable pending mirror record without contacting Nextcloud."""
    import os
    from app.extensions import db
    from app.models import CloudAttachment
    absolute_path = os.path.abspath(local_path)
    record = CloudAttachment.query.filter_by(
        target_type=target_type, target_id=target_id, local_path=absolute_path).first()
    if not record:
        record = CloudAttachment(target_type=target_type, target_id=target_id,
                                 local_path=absolute_path, original_name=original_name,
                                 uploaded_by=user_id, sync_status='pending',
                                 category_id=category_id, column_id=column_id)
        db.session.add(record)
    else:
        record.category_id = category_id
        record.column_id = column_id
    return record


def mirror_attachment(target_type, target_id, local_path, original_name, user_id,
                      category_id=None, column_id=None):
    """Create/update a mirror record and attempt upload immediately."""
    record = queue_attachment(target_type, target_id, local_path, original_name, user_id,
                              category_id=category_id, column_id=column_id)
    sync_attachment(record)
    return record


def search_files(keyword, limit=12):
    """Search Nextcloud filenames with RFC 5323 WebDAV SEARCH."""
    if not is_nextcloud_configured() or not keyword:
        return []
    cfg = _config()
    scope = '/files/' + cfg['username']
    if cfg['root']:
        scope += '/' + cfg['root']
    literal = ('%' + keyword + '%').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    body = '''<?xml version="1.0" encoding="UTF-8"?>
<d:searchrequest xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">
 <d:basicsearch><d:select><d:prop><oc:fileid/><d:displayname/><d:getcontenttype/><d:resourcetype/>
 <d:getcontentlength/><d:getlastmodified/></d:prop></d:select>
 <d:from><d:scope><d:href>{scope}</d:href><d:depth>infinity</d:depth></d:scope></d:from>
 <d:where><d:like><d:prop><d:displayname/></d:prop><d:literal>{literal}</d:literal></d:like></d:where>
 <d:orderby><d:order><d:prop><d:getlastmodified/></d:prop><d:descending/></d:order></d:orderby>
 </d:basicsearch></d:searchrequest>'''.format(scope=scope, literal=literal)
    response_body, status = _request(
        cfg, cfg['url'] + '/remote.php/dav/', method='SEARCH', data=body.encode('utf-8'),
        headers={'Content-Type': 'text/xml; charset=utf-8'})
    root = ElementTree.fromstring(response_body)
    prefix = '/remote.php/dav/files/' + cfg['username'] + '/'
    results = []
    for item in root.findall(DAV + 'response'):
        href = unquote(item.findtext(DAV + 'href') or '')
        prop = item.find('.//' + DAV + 'prop')
        if prop is None:
            continue
        content_type = prop.findtext(DAV + 'getcontenttype') or ''
        resource_type = prop.find(DAV + 'resourcetype')
        is_folder = (content_type == 'httpd/unix-directory' or
                     (resource_type is not None and resource_type.find(DAV + 'collection') is not None))
        name = prop.findtext(DAV + 'displayname') or href.rstrip('/').split('/')[-1]
        path = href.split(prefix, 1)[-1] if prefix in href else urlparse(href).path
        file_id = prop.findtext(OC + 'fileid') or ''
        results.append({
            'name': name, 'path': path, 'file_id': file_id,
            'content_type': content_type, 'is_folder': is_folder,
            'size': int(prop.findtext(DAV + 'getcontentlength') or 0),
            'modified': prop.findtext(DAV + 'getlastmodified') or '',
            'url': _folder_url(cfg, path) if is_folder else _file_url(cfg, file_id, path),
        })
        if len(results) >= limit:
            break
    return results


def connection_status():
    if not is_nextcloud_configured():
        return False, '尚未配置 Nextcloud'
    cfg = _config()
    try:
        _request(cfg, cfg['url'] + '/status.php')
        return True, '连接正常'
    except Exception as exc:
        return False, str(exc)
