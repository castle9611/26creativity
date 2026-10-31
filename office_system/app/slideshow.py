"""Homepage slideshow metadata and offline image upload validation."""
import imghdr
import json
import re
import os
import uuid
from datetime import datetime

def load_slides(value):
    try:
        items = json.loads(value or '[]')
    except (TypeError, ValueError):
        return []
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict) and
            isinstance(item.get('path'), str) and re.fullmatch(
                r'data/uploads/\d{4}-\d{2}/[a-f0-9]{32}\.(jpg|png|gif|bmp|webp)', item['path']) and
            isinstance(item.get('name'), str)]


def validate_images(uploads, errors=None):
    """Validate all streams before writing any image or changing configuration."""
    checked = []
    for upload in uploads:
        if not upload.filename:
            continue
        upload.stream.seek(0, 2)
        size = upload.stream.tell()
        upload.stream.seek(0)
        header = upload.stream.read(32)
        kind = 'jpeg' if header.startswith(b'\xff\xd8\xff') else imghdr.what(None, header)
        upload.stream.seek(0)
        if size <= 0 or kind not in ('jpeg', 'png', 'gif', 'bmp', 'webp'):
            name = upload.filename.replace('\\', '/').rsplit('/', 1)[-1][:100]
            if errors is None:
                raise ValueError(name)
            errors.append(name)
            continue
        checked.append((upload, 'jpg' if kind == 'jpeg' else kind))
    return checked


def store_images(uploads, errors=None):
    from app.config import BASE_DIR
    checked = validate_images(uploads, errors=errors)
    images = []
    month = datetime.now().strftime('%Y-%m')
    for upload, extension in checked:
        relative = 'data/uploads/{}/{}.{}'.format(month, uuid.uuid4().hex, extension)
        full_path = os.path.join(BASE_DIR, *relative.split('/'))
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        upload.save(full_path)
        images.append({'path': relative, 'name': upload.filename.replace('\\', '/').rsplit('/', 1)[-1][:200]})
    return images
