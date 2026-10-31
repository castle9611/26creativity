"""Small, offline, read-only Office renderer. Never execute embedded content."""
import html
import os
import zipfile

from app.importers import read_text_file



def escape(value):
    return html.escape(str(value if value is not None else ''), quote=True)


def docx_html(archive):
    from app.word_preview import docx_html as render_docx
    return render_docx(archive)


def xlsx_html(archive):
    from app.excel_preview import xlsx_html as render_xlsx
    return render_xlsx(archive)


def office_html(path, ext):
    """Return trusted generated markup, or None for unsupported legacy formats."""
    if ext in ('docx', 'xlsx'):
        with zipfile.ZipFile(path) as archive:
            if sum(item.file_size for item in archive.infolist()) > 40 * 1024 * 1024:
                raise ValueError('Document exceeds offline preview size limit')
            return docx_html(archive) if ext == 'docx' else xlsx_html(archive)
    if ext == 'xls':
        from app.excel_preview import xls_html
        return xls_html(path)
    if ext in ('txt', 'csv', 'log', 'md', 'json', 'xml', 'yaml', 'yml'):
        if os.path.getsize(path) > 4 * 1024 * 1024:
            raise ValueError('Text exceeds offline preview size limit')
        return '<pre>{}</pre>'.format(escape(read_text_file(path)))
    return None


def render_preview(path, name, download_url, stream_url):
    from flask import render_template
    ext = name.rsplit('.', 1)[-1].lower()
    from app.views.files import IMAGE_EXTENSIONS, AUDIO_EXTENSIONS, VIDEO_EXTENSIONS
    kind = 'document'
    content = None
    if ext in IMAGE_EXTENSIONS:
        kind = 'image'
    elif ext in VIDEO_EXTENSIONS:
        kind = 'video'
    elif ext in AUDIO_EXTENSIONS:
        kind = 'audio'
    elif ext == 'pdf':
        kind = 'pdf'
    else:
        try:
            content = office_html(path, ext)
        except Exception:
            from flask import current_app
            current_app.logger.warning('Offline preview could not render %s', ext)
            content = None
    return render_template('readonly_preview.html', name=name, kind=kind,
                           content=content, download_url=download_url, stream_url=stream_url)
