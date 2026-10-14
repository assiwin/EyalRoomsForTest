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


def _column_number(name):
    value = 0
    for char in name:
        value = value * 26 + ord(char) - 64
    return value


def _teacher_from_header(header):
    text = _norm(header)
    if 'מתמטיקה' not in text:
        return None
    details = text.replace('מתמטיקה', '', 1).strip()
    unit = ''
    if re.search(r'מב["״\']?ר', details):
        unit = '3א'
        details = re.sub(r'מב["״\']?ר', '', details).strip()
    else:
        match = re.search(r'(?<!\d)([345])\s*יח(?:ידות)?\b', details)
        if match:
            unit = match.group(1)
            details = details[:match.start()] + ' ' + details[match.end():]
    class_match = re.search(r'(?<!\w)(י|יא|יב)\s*(\d+)(?:\s*[-–]\s*(?:י|יא|יב)?\s*\d+)?', details)
    grade7 = ''
    if class_match:
        grade, number = class_match.group(1), class_match.group(2)
        if number == '7':
            grade7 = grade + '7'
            if not unit:
                unit = '3'
        details = details[:class_match.start()] + ' ' + details[class_match.end():]
    details = re.sub(r'\[\s*\d+\s*\]', '', details)
    teacher = re.sub(r'\s+', ' ', details).strip(' -–')
    if not unit:
        return {'teacher': teacher, 'unit': '', 'grade7': grade7}
    return {'teacher': teacher, 'unit': unit, 'grade7': grade7}


def parse_teacher_workbook(data):
    """Read the school's student matrix: row 3 headers, student data from row 4."""
    _, files = _files(data)
    shared = _strings(files)
    sheets = _sheet_paths(files)
    if not sheets:
        raise ValueError('לא נמצאו גיליונות בקובץ נתוני התלמידים.')
    students = []
    seen = {}
    for sheet_name, path in sheets:
        if path not in files:
            continue
        rows = _read_sheet(files[path], shared)
        headers = rows.get(3, {})
        math_columns = {column: _teacher_from_header(header) for column, header in headers.items()}
        math_columns = {column: info for column, info in math_columns.items() if info is not None}
        legacy_unit = _norm(rows.get(1, {}).get('A'))
        legacy_teacher = _norm(rows.get(1, {}).get('B'))
        legacy = not math_columns and legacy_unit in ('3', '3א', '4', '5') and bool(legacy_teacher)
        special_grade_teachers = {
            info['teacher']: info['grade7']
            for info in math_columns.values()
            if info['teacher'] and info['grade7'] and any(
                other['teacher'] == info['teacher'] and not other['grade7']
                for other in math_columns.values())
        }
        for row_number in sorted(n for n in rows if n >= 4):
            row = rows[row_number]
            student_id = _norm(row.get('B'))
            if not student_id:
                continue
            name = ' '.join(value for value in (_norm(row.get('C')), _norm(row.get('D')))
                             if value) if legacy else _norm(row.get('C'))
            class_name = (_norm(row.get('E')) + _norm(row.get('F'))) if legacy else (_norm(row.get('F')) + _norm(row.get('E')))
            if not name or not class_name:
                raise ValueError(f'גיליון „{sheet_name}”, שורה {row_number}: חסרים שם תלמיד או כיתה.')
            if student_id in seen:
                raise ValueError(f'תעודת זהות {student_id} מופיעה פעמיים בקובץ נתוני התלמידים.')
            marked = ([{'teacher': legacy_teacher, 'unit': legacy_unit, 'grade7': ''}] if legacy else
                      [info.copy() for column, info in math_columns.items()
                       if _norm(row.get(column)).upper() == 'X'])
            # If the same teacher teaches both a special seventh-grade class and
            # another math class, distinguish the teacher in the seventh-grade group.
            for item in marked:
                if item['grade7'] and item['teacher'] in special_grade_teachers:
                    item['teacher'] += item['grade7']
            assignments = marked or [{'teacher': '', 'unit': '', 'grade7': ''}]
            for assignment in assignments:
                students.append({'id': student_id, 'name': name, 'class': class_name,
                                 'teacher': assignment['teacher'], 'unit': assignment['unit'],
                                 'source': f'{sheet_name} שורה {row_number}'})
            seen[student_id] = f'{sheet_name} שורה {row_number}'
    if not students:
        raise ValueError('לא נמצאו תלמידים בקובץ נתוני התלמידים החל משורה 4.')
    return students, len(sheets)


def parse_accommodations_workbook(data):
    """Return student accommodations keyed by ID from the accommodation matrix."""
    _, files = _files(data)
    shared = _strings(files)
    result = {}
    has_students = False
    for sheet_name, path in _sheet_paths(files):
        if path not in files:
            continue
        rows = _read_sheet(files[path], shared)
        headers = rows.get(3, {})
        columns = {}
        for col, label in headers.items():
            if _column_number(col) < 6:
                continue
            label = _norm(label)
            if 'תוספת זמן' in label:
                percent_match = re.search(r'(?<!\d)(50|33|25)\s*%', label)
                percent = percent_match.group(1) if percent_match else ''
                if percent:
                    columns[col] = ('D', percent)
            if 'הגדלת שאלון בחינה' in label:
                columns[col] = ('E', 'כן')
            if 'מתמטיקה והקראה' in label:
                columns[col] = ('F', 'כן')
            if 'חדר מצומצם' in label:
                columns[col] = ('L', '1')
            if 'חדר נפרד' in label:
                columns[col] = ('M', '1')
        for row_number in sorted(n for n in rows if n >= 4):
            row = rows[row_number]
            student_id = _norm(row.get('B'))
            if not student_id:
                continue
            has_students = True
            values = result.setdefault(student_id, {})
            for col, (target, value) in columns.items():
                if _norm(row.get(col)):
                    # Prefer the largest extra-time value if multiple columns are marked.
                    if target == 'D' and target in values:
                        values[target] = str(max(int(values[target]), int(value)))
                    else:
                        values[target] = value
    if not has_students:
        raise ValueError('לא נמצאו תלמידים בקובץ ההתאמות החל משורה 4.')
    return {student_id: values for student_id, values in result.items() if values}, len(_sheet_paths(files))


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
    sheet_pairs = _sheet_paths(files)
    paths = dict(sheet_pairs)
    path = paths.get(name)
    if path is None:
        path = next((candidate for sheet_name, candidate in sheet_pairs if sheet_name.casefold() == name.casefold()), None)
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
                   f'<worksheet xmlns="{MAIN_NS}"><dimension ref="A1:E{max(1, len(rows))}"/>'
                   '<sheetViews><sheetView rightToLeft="1" workbookViewId="0"/></sheetViews>'
                   '<sheetFormatPr defaultRowHeight="18"/>'
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


def _dbase_records(rows):
    """Index every student row by ID, regardless of its participant marker in J."""
    records = {}
    for number, row in sorted(rows.items()):
        if number < 2:
            continue
        student_id = _norm(row.get('A'))
        if not student_id:
            if any(_norm(row.get(column)) for column in ('B', 'C', 'G', 'H')):
                raise ValueError(f'גיליון dbase, שורה {number}: חסרה תעודת זהות בעמודה A. לא ניתן לעדכן רשומה זו.')
            continue
        if student_id in records:
            raise ValueError(f'גיליון dbase: תעודת זהות כפולה בשורות {records[student_id][0]} ו־{number}.')
        records[student_id] = (number, row)
    return records


def import_database(base_data, student_data, accommodation_data, mode, base_filename):
    if mode not in ('new', 'update'):
        raise ValueError('יש לבחור טעינת קובץ חדש או עדכון קובץ קיים.')
    infos, files = _files(base_data)
    dbase_path = _classlist(files, base_filename)
    students, sheets = parse_teacher_workbook(student_data) if student_data else ([], 0)
    accommodations, accommodation_sheets = parse_accommodations_workbook(accommodation_data) if accommodation_data else ({}, 0)
    if not student_data and not accommodation_data:
        raise ValueError('יש לבחור לפחות קובץ נתוני תלמידים או קובץ התאמות.')
    shared = _strings(files)
    xml = files[dbase_path].decode('utf-8')
    log_rows = [['תאריך', 'פעולה', 'תעודת זהות', 'שם תלמיד', 'פירוט']]
    changes = 0
    now = datetime.now().strftime('%d/%m/%Y %H:%M')
    if mode == 'new':
        if students:
            xml = _replace_dbase_new(xml, students)
            changes = len(students)
        existing_rows = _read_sheet(xml.encode('utf-8'), shared)
        existing = _dbase_records(existing_rows)
        for student in students:
            if not student['teacher'] or not student['unit']:
                log_rows.append([now, 'חסר שיבוץ מתמטיקה', student['id'], student['name'],
                                 'לא נמצא סימון X בעמודת מתמטיקה; יש לבדוק שיוך, מורה ויחידות.'])
    else:
        existing_rows = _read_sheet(files[dbase_path], _strings(files))
        existing = _dbase_records(existing_rows)
        if students:
            incoming = {}
            nonparticipants = {student_id for student_id, (_, row) in existing.items() if _norm(row.get('J')) != '1'}
            matched_nonparticipants = 0
            updated_nonparticipants = 0
            for student in students:
                incoming.setdefault(student['id'], []).append(student)
            found = set()
            labels = {'B': 'שם תלמיד', 'C': 'כיתה', 'G': 'מורה', 'H': 'יחידות'}
            keys = {'B': 'name', 'C': 'class', 'G': 'teacher', 'H': 'unit'}
            for student_id, candidates in incoming.items():
                if student_id not in existing:
                    student = candidates[0]
                    log_rows.append([now, 'לבדיקה - תלמיד חדש', student_id, student['name'],
                                     f"כיתה {student['class']}, מורה {student['teacher'] or 'לא נמצאה מתמטיקה'}, {student['unit'] or 'יחידות לא ידועות'}"])
                    continue
                found.add(student_id)
                if student_id in nonparticipants:
                    matched_nonparticipants += 1
                row_number, old = existing[student_id]
                # A student may be marked in more than one math column; preserve each
                # marked teacher/group as a separate row in the new-load path. Updates
                # use the first marked assignment for the existing classlist row.
                student = candidates[0]
                if not student['teacher'] or not student['unit']:
                    log_rows.append([now, 'חסר שיבוץ מתמטיקה', student_id, student['name'],
                                     'לא נמצא סימון X בעמודת מתמטיקה; פרטי המורה והיחידות הקיימים נשמרו לבדיקה.'])
                    continue
                details = []
                for column in ('B', 'C', 'G', 'H'):
                    after = student[keys[column]]
                    before = _norm(old.get(column))
                    if before != after:
                        xml = _set_cell(xml, f'{column}{row_number}', after)
                        details.append(f'{labels[column]}: „{before}” ← „{after}”')
                if details:
                    log_rows.append([now, 'עדכון נתוני תלמיד', student_id, student['name'], '; '.join(details)])
                    changes += 1
                    if student_id in nonparticipants:
                        updated_nonparticipants += 1
            for student_id, (row_number, old) in existing.items():
                if student_id not in found and student_id not in incoming:
                    log_rows.append([now, 'לבדיקה - תלמיד לא נמצא בקלט', student_id,
                                     _norm(old.get('B')), 'יש לבדוק אם התלמיד עזב; לא בוצעה מחיקה אוטומטית.'])
        # Re-read the updated XML, then apply accommodation data by ID.
        current_rows = _read_sheet(xml.encode('utf-8'), shared)
        existing = _dbase_records(current_rows)
    # Apply accommodations in both new and update modes. Missing IDs are reported,
    # and no dbase rows are created implicitly.
    if accommodations:
        rows_now = _read_sheet(xml.encode('utf-8'), shared) if mode == 'new' else _read_sheet(xml.encode('utf-8'), shared)
        records = _dbase_records(rows_now)
        matched = set()
        for student_id, values in accommodations.items():
            record = records.get(student_id)
            if not record:
                log_rows.append([now, 'לבדיקה - התאמות ללא תלמיד ב־dbase', student_id, '',
                                 'לא נמצאה תעודת זהות זו בגיליון dbase; לא נוצרה רשומה.'])
                continue
            matched.add(student_id)
            row_number, old = record
            details = []
            for column, value in values.items():
                before = _norm(old.get(column))
                if before != value:
                    xml = _set_cell(xml, f'{column}{row_number}', value)
                    details.append(f'{column}: „{before}” ← „{value}”')
            if details:
                log_rows.append([now, 'עדכון התאמות', student_id, _norm(old.get('B')), '; '.join(details)])
                changes += 1
        if mode == 'update':
            unmatched = len(set(accommodations) - matched)
            # Keep a count for the UI; detailed rows are already in LOG.
        else:
            unmatched = len(set(accommodations) - matched)
    else:
        unmatched = 0
    if mode == 'new' or mode == 'update':
        _add_or_replace_sheet(files, 'LOG', log_rows)
    files[dbase_path] = xml.encode('utf-8')
    value = _write(infos, files)
    meta = {'mode': mode, 'students': len(students), 'sheets': sheets,
            'accommodationStudents': len(accommodations), 'accommodationSheets': accommodation_sheets,
            'changes': changes, 'logEntries': max(0, len(log_rows) - 1),
            'unmatchedAccommodations': unmatched,
            'studentFileLoaded': bool(student_data), 'accommodationFileLoaded': bool(accommodation_data)}
    if mode == 'update':
        meta.update(dbaseRecords=len(existing), dbaseNonParticipants=sum(1 for _, row in existing.values() if _norm(row.get('J')) != '1'))
        if students:
            meta.update(matchedNonParticipants=matched_nonparticipants,
                        updatedNonParticipants=updated_nonparticipants,
                        unmatchedRecords=len(set(existing) - set(incoming)),
                        unmatchedNonParticipants=sum(1 for student_id in set(existing) - set(incoming) if student_id in nonparticipants))
    return value, meta
