"""Build or update a classlist workbook from teacher worksheets while preserving VBA."""
import io
import html
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime

MAIN_NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
RID = f'{{{REL_NS}}}id'


def _norm(value):
    value = str(value or '').strip()
    if re.fullmatch(r'\d+\.0', value):
        value = value[:-2]
    return value


def _files(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as src:
            if sum(item.file_size for item in src.infolist()) > 120_000_000:
                raise ValueError('הקובץ גדול מדי לאחר פתיחה.')
            infos = {item.filename: item for item in src.infolist()}
            files = {item.filename: src.read(item.filename) for item in src.infolist()}
        ET.fromstring(files['xl/workbook.xml'])
        return infos, files
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise ValueError('נדרש קובץ Excel תקין מסוג XLSX או XLSM, ללא סיסמה.') from exc


def _sheet_paths(files):
    workbook = ET.fromstring(files['xl/workbook.xml'])
    rels = ET.fromstring(files['xl/_rels/workbook.xml.rels'])
    targets = {rel.attrib['Id']: rel.attrib['Target'] for rel in rels}
    result = []
    for sheet in workbook.findall(f'{{{MAIN_NS}}}sheets/{{{MAIN_NS}}}sheet'):
        target = targets[sheet.attrib[RID]]
        path = posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/' + target)
        result.append((sheet.attrib.get('name', ''), path))
    return result


def _strings(files):
    if 'xl/sharedStrings.xml' not in files:
        return []
    root = ET.fromstring(files['xl/sharedStrings.xml'])
    return [''.join(t.text or '' for t in item.iter(f'{{{MAIN_NS}}}t')) for item in root]


def _read_sheet(xml, shared):
    root = ET.fromstring(xml)
    rows = {}
    for row in root.findall(f'{{{MAIN_NS}}}sheetData/{{{MAIN_NS}}}row'):
        number = int(row.attrib.get('r', '0'))
        values = {}
        for cell in row.findall(f'{{{MAIN_NS}}}c'):
            ref = cell.attrib.get('r', '')
            column = re.sub(r'\d', '', ref)
            value_node = cell.find(f'{{{MAIN_NS}}}v')
            value = value_node.text if value_node is not None else ''
            if cell.attrib.get('t') == 's' and value:
                value = shared[int(value)]
            elif cell.attrib.get('t') == 'inlineStr':
                value = ''.join(t.text or '' for t in cell.iter(f'{{{MAIN_NS}}}t'))
            values[column] = _norm(value)
        rows[number] = values
    return rows


def parse_teacher_workbook(data):
    _, files = _files(data)
    shared = _strings(files)
    students = []
    seen = {}
    sheet_count = 0
    for sheet_name, path in _sheet_paths(files):
        if path not in files:
            continue
        rows = _read_sheet(files[path], shared)
        title = _norm(rows.get(1, {}).get('A'))
        match = re.fullmatch(r'(.+?)\s+(3א|3|4|5)', title)
        if not match:
            raise ValueError(f'גיליון „{sheet_name}”: תא A1 חייב להכיל שם מורה ולאחריו 3, 3א, 4 או 5.')
        teacher, unit = match.group(1).strip(), match.group(2)
        sheet_count += 1
        for row_number in sorted(number for number in rows if number >= 3):
            row = rows[row_number]
            student_id = _norm(row.get('B'))
            if not student_id:
                continue
            surname, first = _norm(row.get('C')), _norm(row.get('D'))
            class_name = _norm(row.get('E')) + _norm(row.get('F'))
            name = ' '.join(value for value in (surname, first) if value)
            if not name or not class_name:
                raise ValueError(f'גיליון „{sheet_name}”, שורה {row_number}: חסרים שם תלמיד או כיתה.')
            if student_id in seen:
                previous = seen[student_id]
                raise ValueError(f'תעודת הזהות {student_id} מופיעה פעמיים: {previous} וגם {sheet_name} שורה {row_number}.')
            seen[student_id] = f'{sheet_name} שורה {row_number}'
            students.append({'id': student_id, 'name': name, 'class': class_name,
                             'teacher': teacher, 'unit': unit, 'source': seen[student_id]})
    if not sheet_count:
        raise ValueError('לא נמצאו גיליונות מורים בקובץ הקלט.')
    if not students:
        raise ValueError('לא נמצאו תלמידים בקובץ הקלט החל משורה 3.')
    return students, sheet_count


def _classlist(files, filename):
    if not re.match(r'^classlist', filename or '', re.I):
        raise ValueError('שם קובץ בסיס הנתונים חייב להתחיל ב־classlist.')
    names = {name for name, _ in _sheet_paths(files)}
    if 'dbase' not in names or 'ניהול' not in names:
        raise ValueError('קובץ classlist חייב להכיל את הגיליונות dbase ו־ניהול.')
    return dict(_sheet_paths(files))['dbase']


def _style_map(row_xml):
    styles = {}
    for cell in re.finditer(r'<c\b[^>]*\br="([A-Z]+)\d+"[^>]*>', row_xml):
        style = re.search(r'\bs="([^"]+)"', cell.group())
        styles[cell.group(1)] = style.group(1) if style else ''
    return styles


def _cell(column, row, value, style=''):
    style_text = f' s="{style}"' if style else ''
    clean = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', str(value or ''))
    if clean == '':
        return f'<c r="{column}{row}"{style_text}/>'
    return f'<c r="{column}{row}"{style_text} t="inlineStr"><is><t>{html.escape(clean)}</t></is></c>'


def _student_row(number, student, styles):
    values = {'A': student['id'], 'B': student['name'], 'C': student['class'],
              'G': student['teacher'], 'H': student['unit'], 'J': '1'}
    cells = ''.join(_cell(column, number, values.get(column, ''), styles.get(column, ''))
                    for column in 'ABCDEFGHIJKLMN')
    return f'<row r="{number}" spans="1:14">{cells}</row>'


def _refresh_dimension(xml, last_row, last_column='N'):
    return re.sub(r'(<dimension\b[^>]*\bref=")[^"]+("[^>]*/>)',
                  rf'\g<1>A1:{last_column}{max(1, last_row)}\2', xml, count=1)


def _replace_dbase_new(xml, students):
    sheet_match = re.search(r'<sheetData>(.*?)</sheetData>', xml, re.S)
    if not sheet_match:
        raise ValueError('מבנה גיליון dbase אינו נתמך.')
    rows = re.findall(r'<row\b[^>]*>.*?</row>', sheet_match.group(1), re.S)
    if not rows:
        raise ValueError('בגיליון dbase חסרה שורת כותרת.')
    header = next((row for row in rows if re.search(r'\br="1"', row)), rows[0])
    template = next((row for row in rows if re.search(r'\br="2"', row)), rows[-1])
    styles = _style_map(template)
    body = header + ''.join(_student_row(index, student, styles)
                            for index, student in enumerate(students, 2))
    xml = xml[:sheet_match.start(1)] + body + xml[sheet_match.end(1):]
    return _refresh_dimension(xml, len(students) + 1)


def _set_cell(xml, ref, value):
    pattern = r'<c\b(?=[^>]*\br="' + re.escape(ref) + r'")(?:[^>]*/>|[^>]*>.*?</c>)'
    match = re.search(pattern, xml, re.S)
    column = re.sub(r'\d', '', ref)
    row = int(re.sub(r'\D', '', ref))
    if match:
        style = re.search(r'\bs="([^"]+)"', match.group())
        replacement = _cell(column, row, value, style.group(1) if style else '')
        return xml[:match.start()] + replacement + xml[match.end():]
    row_match = re.search(r'(<row\b[^>]*\br="' + str(row) + r'"[^>]*>)(.*?)(</row>)', xml, re.S)
    if not row_match:
        raise ValueError(f'לא ניתן לעדכן את התא {ref}.')
    inner = row_match.group(2)
    order = lambda name: sum((ord(char) - 64) * 26 ** index for index, char in enumerate(reversed(name)))
    at = len(inner)
    for found in re.finditer(r'<c\b[^>]*\br="([A-Z]+)\d+"', inner):
        if order(found.group(1)) > order(column):
            at = found.start(); break
    updated = inner[:at] + _cell(column, row, value) + inner[at:]
    return xml[:row_match.start(2)] + updated + xml[row_match.end(2):]


def _add_or_replace_sheet(files, name, rows):
    paths = dict(_sheet_paths(files))
    path = paths.get(name)
    if path is None:
        numbers = [int(match.group(1)) for filename in files
                   if (match := re.fullmatch(r'xl/worksheets/sheet(\d+)\.xml', filename))]
        number = max(numbers, default=0) + 1
        path = f'xl/worksheets/sheet{number}.xml'
        workbook = files['xl/workbook.xml'].decode('utf-8')
        rels = files['xl/_rels/workbook.xml.rels'].decode('utf-8')
        rid_number = max([int(value) for value in re.findall(r'\bId="rId(\d+)"', rels)], default=0) + 1
        sheet_id = max([int(value) for value in re.findall(r'\bsheetId="(\d+)"', workbook)], default=0) + 1
        rid = f'rId{rid_number}'
        workbook = workbook.replace('</sheets>', f'<sheet name="{html.escape(name)}" sheetId="{sheet_id}" r:id="{rid}"/></sheets>', 1)
        relationship = (f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                        f'Target="worksheets/sheet{number}.xml"/>')
        rels = rels.replace('</Relationships>', relationship + '</Relationships>', 1)
        types = files['[Content_Types].xml'].decode('utf-8')
        override = (f'<Override PartName="/{path}" '
                    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
        files['xl/workbook.xml'] = workbook.encode('utf-8')
        files['xl/_rels/workbook.xml.rels'] = rels.encode('utf-8')
        files['[Content_Types].xml'] = types.replace('</Types>', override + '</Types>', 1).encode('utf-8')
    sheet_rows = []
    for number, values in enumerate(rows, 1):
        cells = ''.join(_cell(chr(65 + index), number, value) for index, value in enumerate(values))
        sheet_rows.append(f'<row r="{number}">{cells}</row>')
    files[path] = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   f'<worksheet xmlns="{MAIN_NS}"><sheetViews><sheetView rightToLeft="1" workbookViewId="0"/></sheetViews>'
                   f'<dimension ref="A1:E{max(1, len(rows))}"/><sheetFormatPr defaultRowHeight="18"/>'
                   '<cols><col min="1" max="1" width="19" customWidth="1"/><col min="2" max="5" width="28" customWidth="1"/></cols>'
                   f'<sheetData>{"".join(sheet_rows)}</sheetData><pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/></worksheet>').encode('utf-8')


def _write(infos, files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as dst:
        for name, content in files.items():
            dst.writestr(infos.get(name, name), content)
    value = output.getvalue()
    with zipfile.ZipFile(io.BytesIO(value)) as check:
        ET.fromstring(check.read('xl/workbook.xml'))
        for name in check.namelist():
            if name.startswith('xl/worksheets/') and name.endswith('.xml'):
                ET.fromstring(check.read(name))
        for name in infos:
            if name.endswith('vbaProject.bin'):
                assert check.read(name) == files[name]
    return value


def import_database(base_data, input_data, mode, base_filename):
    if mode not in ('new', 'update'):
        raise ValueError('יש לבחור טעינת קובץ חדש או עדכון קובץ קיים.')
    infos, files = _files(base_data)
    dbase_path = _classlist(files, base_filename)
    students, sheets = parse_teacher_workbook(input_data)
    xml = files[dbase_path].decode('utf-8')
    log_rows = [['תאריך', 'פעולה', 'תעודת זהות', 'שם תלמיד', 'פירוט']]
    changes = 0
    if mode == 'new':
        xml = _replace_dbase_new(xml, students)
        changes = len(students)
    else:
        existing_rows = _read_sheet(files[dbase_path], _strings(files))
        existing = {_norm(row.get('A')): (number, row) for number, row in existing_rows.items()
                    if number >= 2 and _norm(row.get('A'))}
        incoming = {student['id']: student for student in students}
        labels = {'B': 'שם תלמיד', 'C': 'כיתה', 'G': 'מורה', 'H': 'יחידות'}
        keys = {'B': 'name', 'C': 'class', 'G': 'teacher', 'H': 'unit'}
        now = datetime.now().strftime('%d/%m/%Y %H:%M')
        for student_id in sorted(set(existing) & set(incoming)):
            row_number, old = existing[student_id]
            student = incoming[student_id]
            for column in ('B', 'C', 'G', 'H'):
                before, after = _norm(old.get(column)), student[keys[column]]
                if before != after:
                    xml = _set_cell(xml, f'{column}{row_number}', after)
                    log_rows.append([now, 'עדכון', student_id, student['name'],
                                     f'{labels[column]}: „{before}” ← „{after}”'])
                    changes += 1
        for student_id in sorted(set(existing) - set(incoming)):
            _, old = existing[student_id]
            log_rows.append([now, 'לבדיקה - תלמיד לא נמצא בקלט', student_id,
                             _norm(old.get('B')), 'יש לבדוק אם התלמיד עזב ויש למחוק אותו ידנית.'])
        for student_id in sorted(set(incoming) - set(existing)):
            student = incoming[student_id]
            detail = f"כיתה {student['class']}, מורה {student['teacher']}, {student['unit']} יחידות"
            log_rows.append([now, 'לבדיקה - תלמיד חדש', student_id, student['name'], detail])
        _add_or_replace_sheet(files, 'log', log_rows)
    files[dbase_path] = xml.encode('utf-8')
    value = _write(infos, files)
    return value, {'mode': mode, 'students': len(students), 'sheets': sheets,
                   'changes': changes, 'logEntries': max(0, len(log_rows) - 1) if mode == 'update' else 0}
