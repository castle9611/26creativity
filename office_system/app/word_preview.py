"""Offline DOCX layout, using document styles rather than portal defaults."""
import base64
import html
import posixpath
import re
from xml.etree import ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'


def esc(value):
    return html.escape(str(value if value is not None else ''), quote=True)


def scalar(value, default=0):
    try:
        return max(-100000, min(100000, float(value)))
    except (TypeError, ValueError):
        return default


def props(nodes):
    result = {}
    for node in nodes:
        if node is not None:
            for child in node:
                name = child.tag.rsplit('}', 1)[-1]
                if name == 'rFonts':
                    for key in ('ascii', 'hAnsi', 'eastAsia', 'cs'):
                        if W + key in child.attrib and W + key + 'Theme' not in child.attrib:
                            result.setdefault(name, {}).pop(key + 'Theme', None)
                result.setdefault(name, {}).update((key.rsplit('}', 1)[-1], value) for key, value in child.attrib.items())
    return result


def font_css(values):
    css = []
    fonts = values.get('rFonts', {})
    names = [fonts.get(key) for key in ('ascii', 'eastAsia', 'hAnsi', 'cs') if fonts.get(key)]
    if names:
        css.append('font-family:' + ','.join('"' + re.sub(r'[^\w\s.,-]', '', name) + '"' for name in dict.fromkeys(names)))
    if 'sz' in values:
        css.append('font-size:{}pt'.format(max(1, scalar(values['sz'].get('val'), 24) / 2)))
    for tag, key, enabled, disabled in [('b', 'font-weight', 'bold', 'normal'), ('i', 'font-style', 'italic', 'normal')]:
        if tag in values:
            css.append(key + ':' + (disabled if values[tag].get('val') in ('0', 'false', 'off') else enabled))
    decorations = []
    if 'u' in values and values['u'].get('val') not in ('none', '0', 'false'):
        decorations.append('underline')
    if 'strike' in values and values['strike'].get('val') not in ('0', 'false'):
        decorations.append('line-through')
    if decorations:
        css.append('text-decoration:' + ' '.join(decorations))
    color = values.get('color', {}).get('val', '')
    if re.fullmatch('[A-Fa-f0-9]{6}', color):
        css.append('color:#' + color)
    fill = values.get('shd', {}).get('fill', '')
    if re.fullmatch('[A-Fa-f0-9]{6}', fill):
        css.append('background-color:#' + fill)
    highlight = values.get('highlight', {}).get('val')
    if highlight in ('yellow', 'cyan', 'green', 'magenta', 'red', 'blue', 'black', 'white'):
        css.append('background-color:' + highlight)
    spacing = values.get('spacing', {}).get('val')
    if spacing:
        css.append('letter-spacing:{}pt'.format(scalar(spacing) / 20))
    vertical = values.get('vertAlign', {}).get('val')
    if vertical in ('superscript', 'subscript'):
        css.extend(['vertical-align:' + ('super' if vertical == 'superscript' else 'sub'), 'font-size:smaller'])
    return ';'.join(css)


def border_css(node):
    if node is None:
        return 'none'
    kind = node.get(W + 'val', 'single')
    if kind in ('nil', 'none'):
        return 'none'
    width = max(.5, scalar(node.get(W + 'sz'), 4) / 8)
    color = node.get(W + 'color', '000000')
    color = '#' + color if re.fullmatch('[a-fA-F0-9]{6}', color) else '#000000'
    line = {'double': 'double', 'dotted': 'dotted', 'dashed': 'dashed', 'dashSmallGap': 'dashed'}.get(kind, 'solid')
    return '{}pt {} {}'.format(max(2.25, width) if line == 'double' else width, line, color)


def docx_html(archive):
    root = ET.fromstring(archive.read('word/document.xml'))
    body = root.find(W + 'body')
    if body is None:
        return ''
    style_root = ET.fromstring(archive.read('word/styles.xml')) if 'word/styles.xml' in archive.namelist() else ET.Element('styles')
    styles = {node.get(W + 'styleId'): node for node in style_root.findall(W + 'style')}
    normal = next((key for key, node in styles.items() if node.get(W + 'type') == 'paragraph' and node.get(W + 'default') == '1'), 'Normal')
    default_p = style_root.find(W + 'docDefaults/' + W + 'pPrDefault/' + W + 'pPr')
    default_r = style_root.find(W + 'docDefaults/' + W + 'rPrDefault/' + W + 'rPr')
    theme_fonts = {}
    if 'word/theme/theme1.xml' in archive.namelist():
        theme = ET.fromstring(archive.read('word/theme/theme1.xml'))
        drawing = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
        for group in ('major', 'minor'):
            node = theme.find('.//' + drawing + group + 'Font')
            if node is not None:
                for suffix, tag in [('HAnsi', 'latin'), ('Ascii', 'latin'), ('EastAsia', 'ea'), ('Bidi', 'cs')]:
                    face = node.find(drawing + tag)
                    name = face.get('typeface', '') if face is not None else ''
                    if not name and tag == 'ea':
                        face = next((item for item in node.findall(drawing + 'font') if item.get('script') == 'Hans'), None)
                        name = face.get('typeface', '') if face is not None else ''
                    if name:
                        theme_fonts[group + suffix] = name
    relationships = {}
    numbering, counters = {}, {}
    if 'word/numbering.xml' in archive.namelist():
        numbering_root = ET.fromstring(archive.read('word/numbering.xml'))
        abstracts = {node.get(W + 'abstractNumId'): {int(level.get(W + 'ilvl', '0')): level for level in node.findall(W + 'lvl')}
                     for node in numbering_root.findall(W + 'abstractNum')}
        for node in numbering_root.findall(W + 'num'):
            abstract = node.find(W + 'abstractNumId')
            levels = dict(abstracts.get(abstract.get(W + 'val'), {})) if abstract is not None else {}
            overrides = {}
            for override in node.findall(W + 'lvlOverride'):
                index = int(override.get(W + 'ilvl', '0'))
                level = override.find(W + 'lvl')
                if level is not None:
                    levels[index] = level
                start = override.find(W + 'startOverride')
                if start is not None:
                    overrides[index] = int(start.get(W + 'val', '1'))
            numbering[node.get(W + 'numId')] = (levels, overrides)
    if 'word/_rels/document.xml.rels' in archive.namelist():
        for rel in ET.fromstring(archive.read('word/_rels/document.xml.rels')):
            path = posixpath.normpath('word/' + rel.get('Target', ''))
            if rel.get('TargetMode') != 'External' and path.startswith('word/'):
                relationships[rel.get('Id')] = path

    def style_nodes(style_id, kind):
        chain, seen = [], set()
        while style_id in styles and style_id not in seen and len(seen) < 30:
            seen.add(style_id)
            node = styles[style_id]
            chain.insert(0, node.find(W + kind))
            parent = node.find(W + 'basedOn')
            style_id = parent.get(W + 'val') if parent is not None else None
        return chain

    def run_props(nodes):
        values = props(nodes)
        fonts = values.get('rFonts', {})
        for key in ('ascii', 'hAnsi', 'eastAsia', 'cs'):
            theme_name = fonts.get(key + 'Theme') or (fonts.get('cstheme') if key == 'cs' else None)
            if theme_name in theme_fonts:
                fonts[key] = theme_fonts[theme_name]
        return values

    def paragraph(node):
        direct = node.find(W + 'pPr')
        pstyle = node.find(W + 'pPr/' + W + 'pStyle')
        style_id = pstyle.get(W + 'val') if pstyle is not None else normal
        paragraph_nodes = [default_p] + style_nodes(style_id, 'pPr') + [direct]
        num_props = next((item.find(W + 'numPr') for item in reversed(paragraph_nodes) if item is not None and item.find(W + 'numPr') is not None), None)
        level, marker = None, ''
        if num_props is not None:
            num_id, ilvl = num_props.find(W + 'numId'), num_props.find(W + 'ilvl')
            num_id = num_id.get(W + 'val') if num_id is not None else '0'
            index = max(0, min(8, int(ilvl.get(W + 'val', '0')))) if ilvl is not None else 0
            levels, overrides = numbering.get(num_id, ({}, {}))
            level = levels.get(index)
            if level is not None:
                start = level.find(W + 'start')
                start = overrides.get(index, int(start.get(W + 'val', '1')) if start is not None else 1)
                counts = counters.setdefault(num_id, {})
                counts[index] = counts.get(index, start - 1) + 1
                for deeper in list(counts):
                    if deeper > index:
                        del counts[deeper]
                label = level.find(W + 'lvlText')
                marker = label.get(W + 'val', '%{}.'.format(index + 1)) if label is not None else ''
                def replace_number(match):
                    target = int(match.group(1)) - 1
                    value = counts.get(target, 1)
                    fmt = levels.get(target)
                    fmt = fmt.find(W + 'numFmt') if fmt is not None else None
                    fmt = fmt.get(W + 'val', 'decimal') if fmt is not None else 'decimal'
                    if fmt in ('lowerLetter', 'upperLetter') and 1 <= value <= 26:
                        return chr((97 if fmt == 'lowerLetter' else 65) + value - 1)
                    if fmt == 'decimalEnclosedCircle' and 1 <= value <= 20:
                        return chr(0x2460 + value - 1)
                    if fmt in ('lowerRoman', 'upperRoman') and 0 < value < 4000:
                        roman, remaining = '', value
                        for magnitude, letter in [(1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'), (100, 'C'), (90, 'XC'), (50, 'L'), (40, 'XL'), (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')]:
                            roman += letter * (remaining // magnitude)
                            remaining %= magnitude
                        return roman.lower() if fmt == 'lowerRoman' else roman
                    if fmt == 'chineseCounting' and 0 < value < 10000:
                        digits, units, result = '\u96f6\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d', ['', '\u5341', '\u767e', '\u5343'], ''
                        text = str(value)
                        for position, digit in enumerate(text):
                            if digit != '0':
                                result += digits[int(digit)] + units[len(text) - position - 1]
                            elif result and not result.endswith(digits[0]) and any(char != '0' for char in text[position + 1:]):
                                result += digits[0]
                        return result[1:] if result.startswith('\u4e00\u5341') else result
                    return str(value)
                marker = re.sub(r'%([1-9])', replace_number, marker)
                marker = re.sub(r'[\uf000-\uf8ff]', '\u2022', marker)
                paragraph_nodes.insert(-1, level.find(W + 'pPr'))
        values = props(paragraph_nodes)
        run_defaults = [default_r] + style_nodes(style_id, 'rPr')
        defaults = run_props(run_defaults)
        css = [font_css(defaults), 'margin:0']
        alignment = values.get('jc', {}).get('val', 'left')
        css.append('text-align:' + {'both': 'justify', 'distribute': 'justify'}.get(alignment, alignment if alignment in ('left', 'right', 'center', 'justify') else 'left'))
        spacing = values.get('spacing', {})
        for key, side in [('before', 'top'), ('after', 'bottom')]:
            if key in spacing:
                css.append('margin-{}:{}pt'.format(side, max(0, scalar(spacing[key])) / 20))
        if 'line' in spacing:
            if spacing.get('lineRule') in ('exact', 'atLeast'):
                line_height = max(1, scalar(spacing['line'])) / 20
                if spacing.get('lineRule') == 'atLeast':
                    sizes = [scalar(defaults.get('sz', {}).get('val'), 24) / 2]
                    sizes.extend(scalar(item.get(W + 'val'), 24) / 2 for item in node.findall('.//' + W + 'rPr/' + W + 'sz'))
                    line_height = max(line_height, max(sizes) * 1.2)
                css.append('line-height:{}pt'.format(line_height))
            else:
                css.append('line-height:' + str(max(.1, scalar(spacing['line']) / 240)))
        indent = values.get('ind', {})
        for key, fallback, side in [('left', 'start', 'left'), ('right', 'end', 'right')]:
            if key in indent or fallback in indent:
                css.append('margin-{}:{}pt'.format(side, scalar(indent.get(key, indent.get(fallback))) / 20))
        if 'firstLine' in indent or 'hanging' in indent:
            css.append('text-indent:{}pt'.format((scalar(indent.get('firstLine')) - scalar(indent.get('hanging'))) / 20))
        if values.get('pageBreakBefore', {}).get('val', '1') not in ('0', 'false') and 'pageBreakBefore' in values:
            css.append('page-break-before:always;border-top:1px dashed #d1d5db;padding-top:12pt')
        if 'keepNext' in values:
            css.append('page-break-after:avoid')
        parts = []
        if marker:
            marker_width = max(0, scalar(values.get('ind', {}).get('hanging'), 360) / 20)
            parts.append('<span class="word-list-marker" style="display:inline-block;text-indent:0;min-width:{}pt">{}</span>'.format(marker_width, esc(marker)))
        for run in node.iter(W + 'r'):
            rstyle = run.find(W + 'rPr/' + W + 'rStyle')
            character = style_nodes(rstyle.get(W + 'val'), 'rPr') if rstyle is not None else []
            run_values = run_props(run_defaults + character + [run.find(W + 'rPr')])
            text = []
            for child in run.iter():
                if child.tag == W + 't':
                    east_asia = run_values.get('rFonts', {}).get('eastAsia')
                    if east_asia:
                        family = re.sub(r'[^\w\s.,-]', '', east_asia)
                        text.append(''.join('<span style="font-family:{}">{}</span>'.format(esc('"' + family + '"'), esc(part)) if re.match(r'[\u2e80-\u9fff\uff00-\uffef]', part) else esc(part)
                                            for part in re.split(r'([\u2e80-\u9fff\uff00-\uffef]+)', child.text or '')))
                    else:
                        text.append(esc(child.text))
                elif child.tag in (W + 'br', W + 'cr'):
                    text.append('<br class="word-page-break">' if child.get(W + 'type') == 'page' else '<br>')
                elif child.tag == W + 'tab':
                    text.append('&#9;')
                elif child.tag.endswith('}blip'):
                    path = relationships.get(child.get(R + 'embed'), '')
                    extension = path.rsplit('.', 1)[-1].lower()
                    if extension in ('png', 'jpg', 'jpeg', 'gif', 'bmp') and path in archive.namelist():
                        extent = next((item for item in run.iter() if item.tag.endswith('}extent') and item.get('cx')), None)
                        size = ''
                        if extent is not None:
                            size = 'width:{}pt;height:{}pt'.format(min(3000, max(1, float(extent.get('cx', 12700)) / 12700)), min(3000, max(1, float(extent.get('cy', 12700)) / 12700)))
                        data = base64.b64encode(archive.read(path)).decode('ascii')
                        text.append('<img style="{}" src="data:image/{};base64,{}" alt="">'.format(size, 'jpeg' if extension == 'jpg' else extension, data))
            parts.append('<span style="{}">{}</span>'.format(esc(font_css(run_values)), ''.join(text)))
        return '<p style="{}">{}</p>'.format(esc(';'.join(css)), ''.join(parts) or '<br>')

    def table(node):
        direct = node.find(W + 'tblPr')
        selected = node.find(W + 'tblPr/' + W + 'tblStyle')
        table_props = style_nodes(selected.get(W + 'val'), 'tblPr') if selected is not None else []
        table_props.append(direct)
        values = props(table_props)
        borders, margins = {}, {}
        for source in table_props:
            if source is not None:
                group = source.find(W + 'tblBorders')
                if group is not None:
                    borders.update((edge.tag.rsplit('}', 1)[-1], edge) for edge in group)
                group = source.find(W + 'tblCellMar')
                if group is not None:
                    margins.update((edge.tag.rsplit('}', 1)[-1], edge) for edge in group)
        grid = [max(0, scalar(item.get(W + 'w')) / 20) for item in node.findall(W + 'tblGrid/' + W + 'gridCol')]
        css = ['table-layout:' + ('fixed' if grid else 'auto')]
        width = values.get('tblW', {})
        if width.get('type') == 'dxa' and scalar(width.get('w')) > 0:
            css.append('width:{}pt'.format(scalar(width['w']) / 20))
        elif width.get('type') == 'pct':
            css.append('width:{}%'.format(scalar(width.get('w')) / 50))
        elif grid:
            css.append('width:{}pt'.format(sum(grid)))
        alignment = values.get('jc', {}).get('val')
        if alignment == 'center':
            css.append('margin-left:auto;margin-right:auto')
        elif alignment == 'right':
            css.append('margin-left:auto;margin-right:0')
        indent = values.get('tblInd', {})
        if indent.get('type') == 'dxa':
            css.append('margin-left:{}pt'.format(scalar(indent.get('w')) / 20))
        rows, active = [], {}
        for y, row in enumerate(node.findall(W + 'tr')):
            entries, next_active = [], {}
            before = row.find(W + 'trPr/' + W + 'gridBefore')
            x = int(scalar(before.get(W + 'val'))) if before is not None else 0
            for cell in row.findall(W + 'tc'):
                span = cell.find(W + 'tcPr/' + W + 'gridSpan')
                span = max(1, min(128, int(scalar(span.get(W + 'val'), 1)))) if span is not None else 1
                merge = cell.find(W + 'tcPr/' + W + 'vMerge')
                if merge is not None and merge.get(W + 'val') != 'restart' and x in active and active[x]['span'] == span:
                    active[x]['rowspan'] += 1
                    next_active[x] = active[x]
                else:
                    entry = {'node': cell, 'x': x, 'span': span, 'rowspan': 1}
                    entries.append(entry)
                    if merge is not None:
                        next_active[x] = entry
                x += span
            rows.append((row, entries, x))
            active = next_active
        rendered = []
        for y, (row, entries, total) in enumerate(rows):
            cells = []
            height = row.find(W + 'trPr/' + W + 'trHeight')
            row_css = 'height:{}pt'.format(max(0, scalar(height.get(W + 'val'))) / 20) if height is not None else ''
            for entry in entries:
                cell = entry['node']
                cell_props = cell.find(W + 'tcPr')
                cell_values = props([cell_props])
                cell_css = []
                width = cell_values.get('tcW', {})
                if width.get('type') == 'dxa' and scalar(width.get('w')) > 0:
                    cell_css.append('width:{}pt'.format(scalar(width['w']) / 20))
                for side in ('top', 'bottom', 'left', 'right'):
                    outer = (side == 'top' and y == 0) or (side == 'bottom' and y + entry['rowspan'] == len(rows)) or (side == 'left' and entry['x'] == 0) or (side == 'right' and entry['x'] + entry['span'] == total)
                    edge = borders.get(side if outer else 'insideH' if side in ('top', 'bottom') else 'insideV')
                    override = cell.find(W + 'tcPr/' + W + 'tcBorders/' + W + side)
                    cell_css.append('border-{}:{}'.format(side, border_css(override if override is not None else edge)))
                    padding = cell.find(W + 'tcPr/' + W + 'tcMar/' + W + side)
                    padding = padding if padding is not None else margins.get(side)
                    cell_css.append('padding-{}:{}pt'.format(side, max(0, scalar(padding.get(W + 'w'))) / 20 if padding is not None else 0 if side in ('top', 'bottom') else 5.4))
                valign = cell_values.get('vAlign', {}).get('val', 'top')
                cell_css.append('vertical-align:' + {'center': 'middle', 'bottom': 'bottom'}.get(valign, 'top'))
                fill = cell_values.get('shd', {}).get('fill', '')
                if re.fullmatch('[a-fA-F0-9]{6}', fill):
                    cell_css.append('background-color:#' + fill)
                cells.append('<td colspan="{}" rowspan="{}" style="{}">{}</td>'.format(entry['span'], entry['rowspan'], esc(';'.join(cell_css)), blocks(cell)))
            rendered.append('<tr style="{}">{}</tr>'.format(row_css, ''.join(cells)))
        columns = ''.join('<col style="width:{}pt">'.format(width) for width in grid)
        return '<table class="word-table" style="{}"><colgroup>{}</colgroup>{}</table>'.format(esc(';'.join(css)), columns, ''.join(rendered))

    def blocks(node):
        return ''.join(paragraph(child) if child.tag == W + 'p' else table(child) if child.tag == W + 'tbl' else '' for child in node)

    section = body.find(W + 'sectPr')
    page = section.find(W + 'pgSz') if section is not None else None
    margins = section.find(W + 'pgMar') if section is not None else None
    css = ['width:{}pt'.format(max(100, scalar(page.get(W + 'w'), 11906) / 20) if page is not None else 595.3),
           'min-height:{}pt'.format(max(100, scalar(page.get(W + 'h'), 16838) / 20) if page is not None else 841.9)]
    for side in ('top', 'right', 'bottom', 'left'):
        css.append('padding-{}:{}pt'.format(side, max(0, scalar(margins.get(W + side), 1440)) / 20 if margins is not None else 72))
    css.append(font_css(run_props([default_r] + style_nodes(normal, 'rPr'))))
    return '<article class="word-page" style="{}">{}</article>'.format(esc(';'.join(css)), blocks(body))
