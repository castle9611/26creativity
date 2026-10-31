"""Render stored spreadsheet formatting without Office or network services."""
import colorsys
import html
import math
import posixpath
import re
from xml.etree import ElementTree as ET

from xlrd.formatting import excel_default_palette_b8, std_format_strings
from app.importers import _column_index

S = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
BORDER_STYLES = {
    'thin': '1px solid', 'medium': '2px solid', 'thick': '3px solid',
    'double': '3px double', 'dotted': '1px dotted', 'hair': '1px dotted',
    'dashed': '1px dashed', 'mediumDashed': '2px dashed',
    'dashDot': '1px dashed', 'mediumDashDot': '2px dashed',
    'dashDotDot': '1px dashed', 'mediumDashDotDot': '2px dashed',
    'slantDashDot': '2px dashed',
}


def esc(value):
    return html.escape(str(value if value is not None else ''), quote=True)


def font_family(name):
    # Font names become CSS, not markup; exclude CSS delimiters and URLs.
    return '"{}", sans-serif'.format(re.sub(r'[^\w\s.,-]', '', name or 'Arial'))


def column_pixels(width):
    width = max(0, min(float(width), 500))
    return math.floor(width * 12 + .5) if width < 1 else math.floor(width * 7 + .5) + 5


def number_text(value, code='General', datemode=0):
    """Display common Excel numeric/date masks, using cached formula values."""
    try:
        numeric = float(value)
    except (ValueError, TypeError):
        return str(value)
    if not math.isfinite(numeric):
        return str(value)
    sections = re.split(r';(?=(?:[^"]*"[^"]*")*[^"]*$)', code or 'General')
    section = sections[1] if numeric < 0 and len(sections) > 1 else sections[2] if numeric == 0 and len(sections) > 2 else sections[0]
    if not section:
        return ''
    clean = re.sub(r'"[^"]*"|\\.|_.|\*.', '', section)
    if re.search(r'(?i)[ymdhs]', re.sub(r'\[[^]]*\]', '', clean)) and not re.search('[#0?]', clean):
        from xlrd import xldate_as_datetime
        try:
            date = xldate_as_datetime(numeric, datemode)
            tokens = re.findall(r'"[^"]*"|\\.|AM/PM|am/pm|\[[hmsHMS]+\]|[ymdhsYMDHS]+|.', section)
            output = []
            for index, token in enumerate(tokens):
                lower = token.lower()
                if token.startswith('"'):
                    output.append(token[1:-1])
                elif token.startswith('\\'):
                    output.append(token[1:])
                elif lower == 'am/pm':
                    output.append('AM' if date.hour < 12 else 'PM')
                elif re.fullmatch(r'\[[hms]+\]', lower):
                    output.append(str(int(numeric * {'h': 24, 'm': 1440, 's': 86400}[lower[1]])))
                elif re.fullmatch('[ymdhs]+', lower):
                    if lower[0] == 'm':
                        before = ''.join(tokens[:index]).lower()
                        after = ''.join(tokens[index + 1:]).lower()
                        minute = bool(re.search(r'h+[^ymdhs]*$', before) or re.match(r'[^ymdhs]*s', after))
                        if not minute and len(lower) >= 3:
                            output.append(date.strftime('%B' if len(lower) >= 4 else '%b'))
                            continue
                        number = date.minute if minute else date.month
                    elif lower[0] == 'y':
                        number = date.year if len(lower) >= 4 else date.year % 100
                    elif lower[0] == 'd' and len(lower) >= 3:
                        output.append(date.strftime('%A' if len(lower) >= 4 else '%a'))
                        continue
                    else:
                        number = {'d': date.day, 'h': date.hour, 's': date.second}[lower[0]]
                        if lower[0] == 'h' and 'am/pm' in section.lower():
                            number = number % 12 or 12
                    output.append(str(number).zfill(len(lower) if len(lower) <= 2 or lower[0] == 'y' else 1))
                elif not token.startswith('['):
                    output.append(token)
            return ''.join(output)
        except (ValueError, OverflowError):
            return str(value)
    if section.lower() in ('general', '@'):
        return format(numeric, '.15g')
    section = re.sub(r'\[\$([^\]-]*)[^]]*\]', lambda m: m.group(1), section)
    section = re.sub(r'\[[^]]*\]|_.|\*.', '', section)
    match = re.search(r'[#0?,]+(?:\.[#0?]+)?(?:[eE][+-]?0+)?%?', section)
    literal = lambda text: re.sub(r'"([^"]*)"|\\(.)', lambda m: m.group(1) if m.group(1) is not None else m.group(2), text)
    if not match:
        return literal(section)
    mask = match.group()
    magnitude = abs(numeric) if numeric < 0 and len(sections) > 1 else numeric
    if '%' in mask:
        magnitude *= 100
    trailing = re.search(r',+$', mask.split('.')[0])
    if trailing:
        magnitude /= 1000 ** len(trailing.group())
    fraction = re.search(r'\.([#0?]+)', mask)
    decimals = min(30, len(fraction.group(1))) if fraction else 0
    if re.search('[eE]', mask):
        text = format(magnitude, '.{}E'.format(decimals))
    else:
        text = format(magnitude, '{}.{}f'.format(',' if ',' in mask.rstrip(',') else '', decimals))
        if fraction and '#' in fraction.group(1):
            optional = len(fraction.group(1)) - len(fraction.group(1).rstrip('#'))
            for unused in range(optional):
                if text.endswith('0'):
                    text = text[:-1]
            text = text.rstrip('.')
        if not fraction and ',' not in mask and re.fullmatch('0+', mask):
            text = text.zfill(len(mask))
    return literal(section[:match.start()]) + text + ('%' if '%' in mask else '') + literal(section[match.end():])


def xlsx_colors(archive):
    palette = list(excel_default_palette_b8[:8]) + list(excel_default_palette_b8)
    theme = ['FFFFFF', '000000', 'EEECE1', '1F497D', '4F81BD', 'C0504D', '9BBB59', '8064A2', '4BACC6', 'F79646']
    if 'xl/theme/theme1.xml' in archive.namelist():
        scheme = ET.fromstring(archive.read('xl/theme/theme1.xml')).find('.//' + A + 'clrScheme')
        if scheme is not None:
            for index, name in enumerate(('lt1', 'dk1', 'lt2', 'dk2', 'accent1', 'accent2', 'accent3', 'accent4', 'accent5', 'accent6')):
                node = scheme.find(A + name)
                if node is not None and len(node):
                    theme[index] = node[0].get('lastClr') or node[0].get('val', theme[index])

    def color(node, default='#000000'):
        if node is None:
            return default
        value = node.get('rgb', '')[-6:]
        if node.get('theme') is not None:
            index = int(node.get('theme'))
            value = theme[index] if index < len(theme) else ''
        elif node.get('indexed') is not None:
            index = int(node.get('indexed'))
            value = '%02X%02X%02X' % palette[index] if index < len(palette) else ''
        if not re.fullmatch('[a-fA-F0-9]{6}', value):
            return default
        tint = max(-1, min(1, float(node.get('tint', '0'))))
        if tint:
            rgb = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
            hue, light, saturation = colorsys.rgb_to_hls(*rgb)
            light = light * (1 + tint) if tint < 0 else light * (1 - tint) + tint
            value = '%02X%02X%02X' % tuple(round(c * 255) for c in colorsys.hls_to_rgb(hue, light, saturation))
        return '#' + value
    return color


def xml_font(node, color):
    if node is None:
        return ''
    css = []
    name = node.find(S + 'name')
    if name is None:
        name = node.find(S + 'rFont')
    if name is not None:
        css.append('font-family:' + font_family(name.get('val')))
    size = node.find(S + 'sz')
    if size is not None:
        css.append('font-size:{}pt'.format(max(1, min(200, float(size.get('val', '11'))))))
    for tag, rule in [('b', 'font-weight:bold'), ('i', 'font-style:italic'), ('strike', 'text-decoration:line-through')]:
        item = node.find(S + tag)
        if item is not None and item.get('val') not in ('0', 'false'):
            css.append(rule)
    underline = node.find(S + 'u')
    if underline is not None and underline.get('val') != 'none':
        css.append('text-decoration:underline')
    font_color = node.find(S + 'color')
    if font_color is not None:
        css.append('color:' + color(font_color))
    return ';'.join(css)


def xlsx_html(archive):
    color = xlsx_colors(archive)
    style_root = ET.fromstring(archive.read('xl/styles.xml')) if 'xl/styles.xml' in archive.namelist() else ET.Element('styles')
    fonts = style_root.findall(S + 'fonts/' + S + 'font')
    fills = style_root.findall(S + 'fills/' + S + 'fill')
    borders = style_root.findall(S + 'borders/' + S + 'border')
    formats = dict(std_format_strings)
    formats.update((int(n.get('numFmtId')), n.get('formatCode')) for n in style_root.findall(S + 'numFmts/' + S + 'numFmt'))
    base_styles = style_root.findall(S + 'cellStyleXfs/' + S + 'xf')
    styles = []
    for xf in style_root.findall(S + 'cellXfs/' + S + 'xf'):
        base_id = int(xf.get('xfId', '0'))
        base = base_styles[base_id] if base_id < len(base_styles) else ET.Element('xf')
        def component(name):
            key = name + 'Id'
            return int(base.get(key, '0') if xf.get('apply' + name.capitalize()) == '0' else xf.get(key, base.get(key, '0')))
        font_id, fill_id, border_id = component('font'), component('fill'), component('border')
        css = [xml_font(fonts[font_id], color)] if font_id < len(fonts) else []
        if fill_id < len(fills):
            fill = fills[fill_id].find(S + 'patternFill')
            if fill is not None and fill.get('patternType') == 'solid':
                css.append('background-color:' + color(fill.find(S + 'fgColor'), '#ffffff'))
        edges = {}
        if border_id < len(borders):
            for side in ('left', 'right', 'top', 'bottom'):
                edge = borders[border_id].find(S + side)
                if edge is not None and edge.get('style') in BORDER_STYLES:
                    edges[side] = BORDER_STYLES[edge.get('style')] + ' ' + color(edge.find(S + 'color'))
        align = xf.find(S + 'alignment')
        if align is None or xf.get('applyAlignment') == '0':
            align = base.find(S + 'alignment')
        align = align.attrib if align is not None else {}
        horizontal = align.get('horizontal', 'general')
        if horizontal in ('left', 'right', 'center', 'justify', 'distributed', 'centerContinuous'):
            css.append('text-align:' + {'distributed': 'justify', 'centerContinuous': 'center'}.get(horizontal, horizontal))
        css.append('vertical-align:' + {'center': 'middle', 'justify': 'middle', 'distributed': 'middle'}.get(align.get('vertical'), align.get('vertical', 'bottom')))
        indent = min(30, int(align.get('indent', '0')))
        if indent:
            css.append('padding-left:{}px'.format(indent * 9))
        format_id = int(xf.get('numFmtId', base.get('numFmtId', '0')))
        styles.append({'css': ';'.join(css), 'edges': edges, 'wrap': align.get('wrapText') in ('1', 'true'),
                       'rotation': int(align.get('textRotation', '0')), 'format': formats.get(format_id, 'General'),
                       'horizontal': horizontal})
    if not styles:
        styles.append({'css': 'font-family:Arial;font-size:11pt;vertical-align:bottom', 'edges': {}, 'wrap': False, 'rotation': 0, 'format': 'General', 'horizontal': 'general'})

    def rich_text(node):
        parts = []
        for child in node:
            if child.tag == S + 't':
                parts.append(esc(child.text))
            elif child.tag == S + 'r':
                parts.append('<span style="{}">{}</span>'.format(esc(xml_font(child.find(S + 'rPr'), color)), esc(child.findtext(S + 't', ''))))
        return ''.join(parts)
    shared = []
    if 'xl/sharedStrings.xml' in archive.namelist():
        shared = [rich_text(item) for item in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
    workbook = ET.fromstring(archive.read('xl/workbook.xml'))
    props = workbook.find(S + 'workbookPr')
    datemode = int(props is not None and props.get('date1904') in ('1', 'true'))
    relationships = {r.get('Id'): r.get('Target') for r in ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))}
    output = []
    for sheet in workbook.findall(S + 'sheets/' + S + 'sheet'):
        if sheet.get('state', 'visible') != 'visible':
            continue
        target = relationships.get(sheet.get(R + 'id'), '')
        path = posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/' + target)
        if not path.startswith('xl/') or path not in archive.namelist():
            continue
        root = ET.fromstring(archive.read(path))
        row_nodes = {int(row.get('r', '1')) - 1: row for row in root.findall(S + 'sheetData/' + S + 'row')}
        cells = {}
        for y, row in row_nodes.items():
            for index, cell in enumerate(row.findall(S + 'c')):
                cells[(y, _column_index(cell.get('r')) if cell.get('r') else index)] = cell
        merges = []
        for node in root.findall(S + 'mergeCells/' + S + 'mergeCell'):
            start, end = node.get('ref').split(':')
            merges.append((int(re.sub(r'\D', '', start)) - 1, int(re.sub(r'\D', '', end)), _column_index(start), _column_index(end) + 1))
        nrows = max([y + 1 for y, x in cells] + [m[1] for m in merges] + [1])
        ncols = max([x + 1 for y, x in cells] + [m[3] for m in merges] + [1])
        if ncols > 1024 or nrows > 10000 or nrows * ncols > 100000:
            raise ValueError('Sheet exceeds offline preview size limit')
        defaults = root.find(S + 'sheetFormatPr')
        default_height = float(defaults.get('defaultRowHeight', '15')) if defaults is not None else 15
        default_width = float(defaults.get('defaultColWidth', '8.43')) if defaults is not None else 8.43
        columns = {}
        for node in root.findall(S + 'cols/' + S + 'col'):
            for x in range(max(0, int(node.get('min')) - 1), min(ncols, int(node.get('max')))):
                columns[x] = node.attrib
        widths = [0 if columns.get(x, {}).get('hidden') in ('1', 'true') else column_pixels(columns.get(x, {}).get('width', default_width)) for x in range(ncols)]
        heights = []
        for y in range(nrows):
            row = row_nodes.get(y)
            heights.append(0 if row is not None and row.get('hidden') in ('1', 'true') else max(0, min(1000, float(row.get('ht', default_height)) if row is not None else default_height)) * 4 / 3)

        def cell_style(y, x):
            cell = cells.get((y, x))
            row = row_nodes.get(y)
            fallback = row.get('s', columns.get(x, {}).get('style', '0')) if row is not None else columns.get(x, {}).get('style', '0')
            index = int(cell.get('s', fallback)) if cell is not None else int(fallback)
            return styles[index] if 0 <= index < len(styles) else styles[0]

        def cell_value(y, x, style):
            cell = cells.get((y, x))
            if cell is None:
                return '', False
            kind = cell.get('t', 'n')
            value = cell.findtext(S + 'v', '')
            if kind == 's':
                return shared[int(value)], False
            if kind == 'inlineStr':
                node = cell.find(S + 'is')
                return rich_text(node) if node is not None else '', False
            if kind == 'b':
                return 'TRUE' if value == '1' else 'FALSE', False
            if kind in ('str', 'e', 'd'):
                return esc(value), False
            # Never evaluate formulas or follow external references.
            return esc(number_text(value, style['format'], datemode)) if value else '', bool(value)

        view = root.find(S + 'sheetViews/' + S + 'sheetView')
        gridlines = view is None or view.get('showGridLines') not in ('0', 'false')
        output.append(render_sheet(sheet.get('name', ''), widths, heights, merges, cell_style, cell_value, gridlines))
    return ''.join(output)


def render_sheet(name, widths, heights, merges, cell_style, cell_value, gridlines=True):
    """Use a fixed geometry so browser content cannot stretch narrow columns."""
    anchors, covered = {}, set()
    for y1, y2, x1, x2 in merges:
        if y1 < 0 or x1 < 0 or y2 > len(heights) or x2 > len(widths) or (y2 - y1) * (x2 - x1) > 100000:
            raise ValueError('Invalid merged range')
        anchors[(y1, x1)] = (y2, x2)
        covered.update((y, x) for y in range(y1, y2) for x in range(x1, x2) if (y, x) != (y1, x1))
    rows = []
    for y, height in enumerate(heights):
        if not height:
            continue
        cells = []
        for x, width in enumerate(widths):
            if not width or (y, x) in covered:
                continue
            y2, x2 = anchors.get((y, x), (y + 1, x + 1))
            style = cell_style(y, x)
            edges = dict(style['edges'])
            if (y, x) in anchors:
                for side, cy, cx in [('right', y, x2 - 1), ('bottom', y2 - 1, x), ('right', y2 - 1, x2 - 1), ('bottom', y2 - 1, x2 - 1)]:
                    edge = cell_style(cy, cx)['edges'].get(side)
                    if edge:
                        edges[side] = edge
            css = [style['css']] + ['border-{}:{}'.format(side, edge) for side, edge in edges.items()]
            value, numeric = cell_value(y, x, style)
            if style['horizontal'] == 'general':
                css.append('text-align:' + ('right' if numeric else 'left'))
            inner = ['height:{}px'.format(max(0, sum(heights[y:y2]) - 2)),
                     'white-space:' + ('pre-wrap' if style['wrap'] else 'pre')]
            vertical = re.search(r'vertical-align:(top|middle|bottom)', style['css'])
            vertical = vertical.group(1) if vertical else 'bottom'
            text_position = {'top': 'top:0', 'middle': 'top:50%;transform:translateY(-50%)', 'bottom': 'bottom:0'}[vertical]
            if style['wrap']:
                inner.append('word-wrap:break-word')
            rotation = style['rotation']
            if rotation == 255:
                value = '<span class="sheet-stacked">{}</span>'.format(value)
            elif rotation:
                degrees = rotation if rotation <= 90 else 90 - rotation
                value = '<span style="display:inline-block;transform:rotate({}deg)">{}</span>'.format(-degrees, value)
            cells.append('<td rowspan="{}" colspan="{}" style="{}"><div class="sheet-cell-content" style="{}"><span class="sheet-cell-text" style="{}">{}</span></div></td>'.format(
                sum(h > 0 for h in heights[y:y2]), sum(w > 0 for w in widths[x:x2]), esc(';'.join(css)), esc(';'.join(inner)), text_position, value))
        rows.append('<tr style="height:{}px">{}</tr>'.format(height, ''.join(cells)))
    columns = ''.join('<col style="width:{}px">'.format(width) for width in widths if width)
    return '<section class="sheet-preview"><h2 class="sheet-name">{}</h2><table class="office-sheet{}" style="width:{}px"><colgroup>{}</colgroup><tbody>{}</tbody></table></section>'.format(esc(name), ' sheet-gridlines' if gridlines else '', sum(widths), columns, ''.join(rows))


def xls_html(path):
    import xlrd
    book = xlrd.open_workbook(path, on_demand=True, formatting_info=True)
    try:
        color = lambda index, default='#000000': '#%02X%02X%02X' % book.colour_map[index] if book.colour_map.get(index) else default
        styles = []
        line_styles = ['none', 'thin', 'medium', 'dashed', 'dotted', 'thick', 'double', 'hair', 'mediumDashed', 'dashDot', 'mediumDashDot', 'dashDotDot', 'mediumDashDotDot', 'slantDashDot']
        for xf in book.xf_list:
            font = book.font_list[xf.font_index]
            align = xf.alignment
            horizontal = {0: 'general', 1: 'left', 2: 'center', 3: 'right', 5: 'justify', 6: 'center', 7: 'justify'}.get(align.hor_align, 'general')
            css = ['font-family:' + font_family(font.name), 'font-size:{}pt'.format(font.height / 20),
                   'color:' + color(font.colour_index), 'font-weight:' + ('bold' if font.bold else 'normal'),
                   'font-style:' + ('italic' if font.italic else 'normal'),
                   'vertical-align:' + {0: 'top', 1: 'middle', 2: 'bottom', 3: 'middle', 4: 'middle'}.get(align.vert_align, 'bottom')]
            if horizontal != 'general':
                css.append('text-align:' + horizontal)
            if font.underlined:
                css.append('text-decoration:underline')
            if xf.background.fill_pattern == 1:
                css.append('background-color:' + color(xf.background.pattern_colour_index, '#ffffff'))
            edges = {}
            for side in ('left', 'right', 'top', 'bottom'):
                line = getattr(xf.border, side + '_line_style')
                if 0 < line < len(line_styles):
                    edges[side] = BORDER_STYLES[line_styles[line]] + ' ' + color(getattr(xf.border, side + '_colour_index'))
            fmt = book.format_map.get(xf.format_key)
            styles.append({'css': ';'.join(css), 'edges': edges, 'wrap': bool(align.text_wrapped),
                           'horizontal': horizontal, 'rotation': align.rotation,
                           'format': fmt.format_str if fmt else 'General'})
        output = []
        for sheet in book.sheets():
            if sheet.visibility:
                continue
            if sheet.nrows * sheet.ncols > 100000:
                raise ValueError('Sheet exceeds offline preview size limit')
            widths = [0 if sheet.colinfo_map.get(x) and sheet.colinfo_map[x].hidden else column_pixels(sheet.computed_column_width(x) / 256) for x in range(sheet.ncols)]
            heights = [(0 if info and info.hidden else (info.height if info else sheet.default_row_height or 300) / 15)
                       for info in (sheet.rowinfo_map.get(y) for y in range(sheet.nrows))]
            def cell_style(y, x):
                return styles[sheet.cell_xf_index(y, x)]
            def cell_value(y, x, style):
                cell = sheet.cell(y, x)
                if cell.ctype in (xlrd.XL_CELL_NUMBER, xlrd.XL_CELL_DATE):
                    return esc(number_text(cell.value, style['format'], book.datemode)), True
                if cell.ctype == xlrd.XL_CELL_BOOLEAN:
                    return 'TRUE' if cell.value else 'FALSE', False
                if cell.ctype == xlrd.XL_CELL_ERROR:
                    return esc(xlrd.error_text_from_code.get(cell.value, '#ERROR')), False
                return esc(cell.value), False
            output.append(render_sheet(sheet.name, widths, heights, sheet.merged_cells, cell_style, cell_value, bool(sheet.show_grid_lines)))
        return ''.join(output)
    finally:
        book.release_resources()
