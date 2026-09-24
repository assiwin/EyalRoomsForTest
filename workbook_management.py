"""Read and update the application's management worksheet without losing VBA."""
import html
import io
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET

SHEET_NAME = 'ניהול'
MAIN_NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def _worksheet_path(files):
    root = ET.fromstring(files['xl/workbook.xml'])
    relroot = ET.fromstring(files['xl/_rels/workbook.xml.rels'])
    targets = {rel.attrib['Id']: rel.attrib['Target'] for rel in relroot}
    sheet = next((item for item in root.findall(f'{{{MAIN_NS}}}sheets/{{{MAIN_NS}}}sheet')
                  if item.attrib.get('name') == SHEET_NAME), None)
    if sheet is None:
        return None
    target = targets[sheet.attrib[f'{{{REL_NS}}}id']]
    return posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/' + target)


def _shared_strings(files):
    if 'xl/sharedStrings.xml' not in files:
        return []
    root = ET.fromstring(files['xl/sharedStrings.xml'])
    return [''.join(t.text or '' for t in item.iter(f'{{{MAIN_NS}}}t')) for item in root]


def _cell_value(root, ref, strings):
    cell = next((c for c in root.iter(f'{{{MAIN_NS}}}c') if c.attrib.get('r') == ref), None)
    if cell is None:
        return ''
    value = cell.find(f'{{{MAIN_NS}}}v')
    raw = value.text if value is not None else ''
    if cell.attrib.get('t') == 's' and raw:
        return strings[int(raw)]
    if cell.attrib.get('t') == 'inlineStr':
        return ''.join(t.text or '' for t in cell.iter(f'{{{MAIN_NS}}}t'))
    return raw or ''


def read_management(data):
    with zipfile.ZipFile(io.BytesIO(data)) as src:
        files = {item.filename: src.read(item.filename) for item in src.infolist()}
    path = _worksheet_path(files)
    if not path or path not in files:
        return {'roomLabels': {}}
    root = ET.fromstring(files[path])
    strings = _shared_strings(files)
    labels = {}
    for row in range(2, 27):
        room = str(_cell_value(root, f'A{row}', strings)).strip()
        label = str(_cell_value(root, f'B{row}', strings)).strip()
        if room and label:
            try:
                labels[int(float(room))] = label
            except ValueError:
                continue
    return {'roomLabels': labels}


def _inline_cell(ref, value, style=''):
    clean = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', str(value))
    style_attr = f' s="{style}"' if style else ''
    return f'<c r="{ref}"{style_attr} t="inlineStr"><is><t>{html.escape(clean)}</t></is></c>'


def _column_number(ref):
    value = 0
    for char in re.match(r'[A-Z]+', ref).group():
        value = value * 26 + ord(char) - 64
    return value


def _set_cell(xml, ref, value):
    pattern = r'<c\b(?=[^>]*\br="' + re.escape(ref) + r'")(?:[^>]*/>|[^>]*>.*?</c>)'
    match = re.search(pattern, xml, re.S)
    if match:
        style_match = re.search(r'\bs="([^"]+)"', match.group())
        replacement = _inline_cell(ref, value, style_match.group(1) if style_match else '')
        return xml[:match.start()] + replacement + xml[match.end():]
    replacement = _inline_cell(ref, value)
    row_number = int(re.search(r'\d+', ref).group())
    row_match = re.search(r'(<row\b[^>]*\br="' + str(row_number) + r'"[^>]*>)(.*?)(</row>)', xml, re.S)
    if row_match:
        inner = row_match.group(2)
        insert_at = len(inner)
        new_column = _column_number(ref)
        for cell in re.finditer(r'<c\b[^>]*\br="([A-Z]+\d+)"', inner):
            if _column_number(cell.group(1)) > new_column:
                insert_at = cell.start()
                break
        inner = inner[:insert_at] + replacement + inner[insert_at:]
        return xml[:row_match.start(2)] + inner + xml[row_match.end(2):]
    sheet_data_end = xml.find('</sheetData>')
    if sheet_data_end < 0:
        raise ValueError('מבנה גיליון ניהול אינו נתמך.')
    row_xml = f'<row r="{row_number}">{replacement}</row>'
    return xml[:sheet_data_end] + row_xml + xml[sheet_data_end:]


def _delete_cell(xml, ref):
    pattern = r'<c\b(?=[^>]*\br="' + re.escape(ref) + r'")(?:[^>]*/>|[^>]*>.*?</c>)'
    return re.sub(pattern, '', xml, count=1, flags=re.S)


def _refresh_dimension(xml):
    match = re.search(r'<dimension\b[^>]*\bref="([^"]+)"[^>]*/>', xml)
    if not match:
        return xml
    refs = re.findall(r'<c\b[^>]*\br="([A-Z]+\d+)"', xml)
    if not refs:
        new_ref = 'A1'
        return xml[:match.start()] + match.group().replace(match.group(1), new_ref) + xml[match.end():]
    last_row = max(int(re.search(r'\d+', ref).group()) for ref in refs)
    last_column = max(_column_number(ref) for ref in refs)
    column = ''
    while last_column:
        last_column, remainder = divmod(last_column - 1, 26)
        column = chr(65 + remainder) + column
    replacement = match.group().replace(match.group(1), f'A1:{column}{last_row}')
    return xml[:match.start()] + replacement + xml[match.end():]


def _new_sheet(files):
    numbers = [int(match.group(1)) for name in files
               if (match := re.fullmatch(r'xl/worksheets/sheet(\d+)\.xml', name))]
    number = max(numbers, default=0) + 1
    path = f'xl/worksheets/sheet{number}.xml'
    workbook = files['xl/workbook.xml'].decode('utf-8')
    rels = files['xl/_rels/workbook.xml.rels'].decode('utf-8')
    rid_number = max([int(value) for value in re.findall(r'\bId="rId(\d+)"', rels)], default=0) + 1
    sheet_id = max([int(value) for value in re.findall(r'\bsheetId="(\d+)"', workbook)], default=0) + 1
    rid = f'rId{rid_number}'
    workbook = workbook.replace('</sheets>', f'<sheet name="{SHEET_NAME}" sheetId="{sheet_id}" r:id="{rid}"/></sheets>', 1)
    relationship = (f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                    f'Target="worksheets/sheet{number}.xml"/>')
    rels = rels.replace('</Relationships>', relationship + '</Relationships>', 1)
    types = files['[Content_Types].xml'].decode('utf-8')
    override = (f'<Override PartName="/{path}" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
    files['xl/workbook.xml'] = workbook.encode('utf-8')
    files['xl/_rels/workbook.xml.rels'] = rels.encode('utf-8')
    files['[Content_Types].xml'] = types.replace('</Types>', override + '</Types>', 1).encode('utf-8')
    files[path] = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   f'<worksheet xmlns="{MAIN_NS}"><sheetViews><sheetView rightToLeft="1" workbookViewId="0"/></sheetViews>'
                   '<sheetFormatPr defaultRowHeight="18"/><sheetData></sheetData>'
                   '<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/></worksheet>').encode('utf-8')
    return path


def update_management(data, room_labels=None):
    with zipfile.ZipFile(io.BytesIO(data)) as src:
        infos = {item.filename: item for item in src.infolist()}
        files = {item.filename: src.read(item.filename) for item in src.infolist()}
    path = _worksheet_path(files)
    if path is None:
        if room_labels is None:
            return data
        path = _new_sheet(files)
    xml = files[path].decode('utf-8')
    xml = _set_cell(xml, 'A1', 'חדר מספר')
    xml = _set_cell(xml, 'B1', 'חדר בחינה')
    if room_labels is not None:
        cleaned = {int(key): str(value).strip() for key, value in room_labels.items()}
        for index, room in enumerate(range(1, 26), 2):
            xml = _set_cell(xml, f'A{index}', room)
            xml = _set_cell(xml, f'B{index}', cleaned.get(room, ''))
    # Version 12 no longer has a locking mechanism. Remove legacy lock cells
    # from workbooks created by earlier builds while preserving all other data.
    xml = _delete_cell(_delete_cell(xml, 'E1'), 'E2')
    xml = _refresh_dimension(xml)
    files[path] = xml.encode('utf-8')
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as dst:
        for name, content in files.items():
            dst.writestr(infos.get(name, name), content)
    value = output.getvalue()
    with zipfile.ZipFile(io.BytesIO(value)) as check:
        ET.fromstring(check.read(path))
        if any(name.endswith('vbaProject.bin') for name in infos):
            original = next(name for name in infos if name.endswith('vbaProject.bin'))
            assert check.read(original) == files[original]
    return value
