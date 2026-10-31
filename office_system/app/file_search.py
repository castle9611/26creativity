# -*- coding: utf-8 -*-
"""Extract searchable text from local office files without external services."""
import html
import os
import re
import zipfile
from datetime import datetime
from xml.etree import ElementTree as ET


SUPPORTED_EXTS = set(('txt', 'csv', 'log', 'md', 'json', 'xml', 'yaml', 'yml',
                      'html', 'htm', 'rtf', 'doc', 'docx', 'xls', 'xlsx', 'pptx', 'pdf'))
MAX_INDEX_CHARS = 4000000


def _clean(value):
    value = html.unescape(re.sub(r'<[^>]+>', ' ', value or ''))
    return re.sub(r'\s+', ' ', value).strip()[:MAX_INDEX_CHARS]


def _xml_text(path, members):
    parts = []
    with zipfile.ZipFile(path) as archive:
        for member in members(archive.namelist()):
            root = ET.fromstring(archive.read(member))
            parts.extend(node.text for node in root.iter() if node.text)
    return _clean(' '.join(parts))


def _legacy_doc_text(path):
    import olefile
    chunks = []
    with olefile.OleFileIO(path) as ole:
        for stream in ole.listdir():
            data = ole.openstream(stream).read()
            chunks.extend(item.decode('utf-16le', 'ignore') for item in re.findall(b'(?:[\x20-\x7e\x80-\xff]\x00){3,}', data))
            chunks.extend(item.decode('gb18030', 'ignore') for item in re.findall(b'[\x20-\x7e\x81-\xfe]{4,}', data))
    return _clean(' '.join(chunks))


def extract_file_text(path, ext):
    ext = (ext or '').lower()
    if ext not in SUPPORTED_EXTS or not os.path.isfile(path):
        return '', 'unsupported'
    try:
        if ext in ('txt', 'csv', 'log', 'md', 'json', 'xml', 'yaml', 'yml', 'html', 'htm', 'rtf'):
            from app.importers import read_text_file
            return _clean(read_text_file(path)), 'ready'
        if ext == 'docx':
            return _xml_text(path, lambda names: [n for n in names if n == 'word/document.xml']), 'ready'
        if ext == 'pptx':
            return _xml_text(path, lambda names: sorted(n for n in names if re.match(r'ppt/slides/slide\d+\.xml$', n))), 'ready'
        if ext == 'xlsx':
            from app.importers import import_xlsx_rows
            return _clean(' '.join(str(cell or '') for row in import_xlsx_rows(path) for cell in row)), 'ready'
        if ext == 'xls':
            import xlrd
            book = xlrd.open_workbook(path, on_demand=True)
            text = ' '.join(str(cell.value) for sheet in book.sheets() for row in sheet.get_rows() for cell in row)
            book.release_resources()
            return _clean(text), 'ready'
        if ext == 'pdf':
            from pypdf import PdfReader
            return _clean(' '.join(page.extract_text() or '' for page in PdfReader(path).pages)), 'ready'
        if ext == 'doc':
            return _legacy_doc_text(path), 'ready'
    except Exception:
        return '', 'failed'
    return '', 'unsupported'


def index_file(file_record):
    from app.config import BASE_DIR
    from app.extensions import db
    from app.models import FileSearchText
    path = os.path.realpath(os.path.join(BASE_DIR, (file_record.file_path or '').replace('/', os.sep)))
    ext = (file_record.file_type or '').lower().lstrip('.')
    if ext not in SUPPORTED_EXTS:
        ext = os.path.splitext(file_record.original_name or '')[1].lower().lstrip('.')
    text, status = extract_file_text(path, ext)
    row = FileSearchText.query.get(file_record.id) or FileSearchText(file_id=file_record.id)
    row.content, row.status, row.updated_at = text, status, datetime.utcnow()
    db.session.add(row)
    return row


def index_missing_files(files):
    from app.models import FileSearchText
    indexed = dict(FileSearchText.query.with_entities(FileSearchText.file_id, FileSearchText.status).all())
    count = 0
    for file_record in files:
        ext = os.path.splitext(file_record.original_name or '')[1].lower().lstrip('.')
        if file_record.id not in indexed or (indexed[file_record.id] == 'unsupported' and ext in SUPPORTED_EXTS):
            index_file(file_record)
            count += 1
    return count
