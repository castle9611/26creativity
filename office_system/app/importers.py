# -*- coding: utf-8 -*-
"""
Offline file import helpers.

The portable Win7 package should not depend on Office, WPS, pandas, openpyxl,
or python-docx, so DOCX/XLSX are parsed through their zipped XML structure.
"""
import csv
import html
import os
import re
import zipfile
from html.parser import HTMLParser
from xml.etree import ElementTree as ET


TEXT_EXTS = {'txt', 'log', 'md', 'json', 'xml', 'yaml', 'yml'}


def uploaded_file_path(file_record, base_dir):
    """Return an absolute path for an uploaded File model row."""
    return os.path.join(base_dir, file_record.file_path.replace('/', os.sep))


def read_text_file(path):
    """Read a text-like file with common Chinese/Office encodings."""
    encodings = ('utf-8-sig', 'utf-8', 'gb18030', 'utf-16', 'big5')
    for encoding in encodings:
        try:
            with open(path, 'r', encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()


def text_to_paragraph_html(text):
    """Convert plain text into simple document HTML."""
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    out = []
    for line in lines:
        if line.strip():
            out.append('<p>{}</p>'.format(html.escape(line)))
        else:
            out.append('<p><br></p>')
    return ''.join(out) or '<p><br></p>'


def table_rows_to_html(rows):
    if not rows:
        return ''
    body = []
    for row in rows:
        cells = ['<td>{}</td>'.format(html.escape(str(cell or ''))) for cell in row]
        body.append('<tr>{}</tr>'.format(''.join(cells)))
    return '<table>{}</table>'.format(''.join(body))


def _local_name(tag):
    return tag.rsplit('}', 1)[-1] if '}' in tag else tag


def _docx_text_from_node(node):
    parts = []
    for child in node.iter():
        name = _local_name(child.tag)
        if name == 't' and child.text:
            parts.append(child.text)
        elif name in ('tab',):
            parts.append('\t')
        elif name in ('br', 'cr'):
            parts.append('\n')
    return ''.join(parts)


def import_docx_as_html(path):
    """Extract paragraphs and tables from a DOCX file."""
    with zipfile.ZipFile(path) as zf:
        xml_bytes = zf.read('word/document.xml')
    root = ET.fromstring(xml_bytes)
    body = None
    for node in root.iter():
        if _local_name(node.tag) == 'body':
            body = node
            break
    if body is None:
        return ''

    blocks = []
    for child in list(body):
        name = _local_name(child.tag)
        if name == 'p':
            text = _docx_text_from_node(child)
            if text.strip():
                blocks.append('<p>{}</p>'.format(html.escape(text).replace('\n', '<br>')))
        elif name == 'tbl':
            rows = []
            for tr in child:
                if _local_name(tr.tag) != 'tr':
                    continue
                row = []
                for tc in tr:
                    if _local_name(tc.tag) == 'tc':
                        row.append(_docx_text_from_node(tc).strip())
                if row:
                    rows.append(row)
            if rows:
                blocks.append(table_rows_to_html(rows))
    return ''.join(blocks)


def _body_inner_html(text):
    match = re.search(r'<body[^>]*>([\s\S]*?)</body>', text, re.I)
    if match:
        return match.group(1)
    return text


def import_document_content(path, ext):
    """Return HTML content for an uploaded document-like file."""
    ext = (ext or '').lower()
    if not os.path.exists(path):
        return '<p>（源文件不存在，无法导入内容）</p>', False

    try:
        if ext == 'docx':
            content = import_docx_as_html(path)
            return (content or '<p>（未从 DOCX 中读取到文字内容）</p>'), bool(content)
        if ext in TEXT_EXTS:
            return text_to_paragraph_html(read_text_file(path)), True
        if ext == 'csv':
            rows = import_csv_rows(path)
            return table_rows_to_html(rows) or '<p>（CSV 文件为空）</p>', bool(rows)
        if ext in ('html', 'htm', 'doc'):
            text = read_text_file(path)
            if '<html' in text.lower() or '<body' in text.lower():
                return _body_inner_html(text), True
            if ext == 'doc':
                return '<p>（老式二进制 DOC 暂无法离线解析，请另存为 DOCX 后再导入。）</p>', False
            return text_to_paragraph_html(text), True
        if ext == 'rtf':
            text = read_text_file(path)
            text = re.sub(r'\\[a-zA-Z]+\d* ?', '', text)
            text = re.sub(r'[{}]', '', text)
            return text_to_paragraph_html(text), True
    except Exception as exc:
        return '<p>（导入失败：{}）</p>'.format(html.escape(str(exc))), False

    return '<p>（该文件类型暂不支持直接导入内容，请转换为 DOCX、XLSX、CSV 或 TXT 后再试。）</p>', False


def import_csv_rows(path):
    text = read_text_file(path)
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=',\t;')
    except Exception:
        dialect = csv.excel
    return [[cell for cell in row] for row in csv.reader(text.splitlines(), dialect)]


def _xlsx_shared_strings(zf):
    try:
        root = ET.fromstring(zf.read('xl/sharedStrings.xml'))
    except KeyError:
        return []
    strings = []
    for si in root:
        parts = []
        for node in si.iter():
            if _local_name(node.tag) == 't' and node.text:
                parts.append(node.text)
        strings.append(''.join(parts))
    return strings


def _column_index(cell_ref):
    letters = re.sub(r'[^A-Z]', '', (cell_ref or '').upper())
    value = 0
    for ch in letters:
        value = value * 26 + (ord(ch) - ord('A') + 1)
    return max(value - 1, 0)


def import_xlsx_rows(path):
    with zipfile.ZipFile(path) as zf:
        shared = _xlsx_shared_strings(zf)
        sheet_names = [n for n in zf.namelist() if re.match(r'xl/worksheets/sheet\d+\.xml$', n)]
        if not sheet_names:
            return []
        root = ET.fromstring(zf.read(sorted(sheet_names)[0]))

    rows = []
    for row_node in root.iter():
        if _local_name(row_node.tag) != 'row':
            continue
        row = []
        for c_node in row_node:
            if _local_name(c_node.tag) != 'c':
                continue
            col = _column_index(c_node.attrib.get('r', ''))
            while len(row) <= col:
                row.append('')
            cell_type = c_node.attrib.get('t', '')
            value = ''
            if cell_type == 'inlineStr':
                value = _docx_text_from_node(c_node)
            else:
                for v_node in c_node:
                    if _local_name(v_node.tag) == 'v' and v_node.text is not None:
                        value = v_node.text
                        break
                if cell_type == 's':
                    try:
                        value = shared[int(value)]
                    except Exception:
                        pass
            row[col] = value
        rows.append(row)
    return rows


class _TableParser(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)
        self.rows = []
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == 'tr':
            self._row = []
        elif tag in ('td', 'th') and self._row is not None:
            self._cell = []

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ('td', 'th') and self._row is not None and self._cell is not None:
            self._row.append(''.join(self._cell).strip())
            self._cell = None
        elif tag == 'tr' and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def import_html_table_rows(path):
    parser = _TableParser()
    parser.feed(read_text_file(path))
    return parser.rows


def import_spreadsheet_rows(path, ext):
    """Return a 2D rows list for an uploaded spreadsheet-like file."""
    ext = (ext or '').lower()
    if not os.path.exists(path):
        return [], False, '源文件不存在，无法导入内容'
    try:
        if ext == 'xlsx':
            rows = import_xlsx_rows(path)
            return rows, bool(rows), ''
        if ext in ('csv', 'txt'):
            rows = import_csv_rows(path)
            return rows, bool(rows), ''
        if ext in ('xls', 'html', 'htm'):
            rows = import_html_table_rows(path)
            if rows:
                return rows, True, ''
            if ext == 'xls':
                return [], False, '老式二进制 XLS 暂无法离线解析，请另存为 XLSX 或 CSV 后再导入'
    except Exception as exc:
        return [], False, str(exc)
    return [], False, '该文件类型暂不支持直接导入为在线表格'


def rows_to_xspreadsheet_data(rows, sheet_name='Sheet1'):
    """Convert a 2D list into x-spreadsheet's rows/cells format."""
    row_map = {}
    max_col = 0
    for r, row in enumerate(rows or []):
        cells = {}
        for c, value in enumerate(row):
            text = '' if value is None else str(value)
            if text != '':
                cells[str(c)] = {'text': text}
                max_col = max(max_col, c)
        if cells:
            row_map[str(r)] = {'cells': cells}
    return [{
        'name': sheet_name or 'Sheet1',
        'rows': row_map,
        'cols': {'len': max(max_col + 1, 26)}
    }]
