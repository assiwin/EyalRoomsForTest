"""Synthetic regression for the student matrix, accommodation import, and all-row updates."""
import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from database_import import _files, _read_sheet, _strings, import_database, parse_teacher_workbook

MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'


def cell(ref, value):
    if value is None:
        return ''
    return f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>'


def row(number, values):
    return f'<row r="{number}">' + ''.join(cell(f'{col}{number}', value) for col, value in values.items()) + '</row>'


def workbook(sheets):
    names = ''.join(f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>'
                    for i, (name, _) in enumerate(sheets, 1))
    links = ''.join(f'<Relationship Id="rId{i}" Type="{REL}/worksheet" Target="worksheets/sheet{i}.xml"/>'
                    for i in range(1, len(sheets) + 1))
    overrides = ''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
                        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                        for i in range(1, len(sheets) + 1))
    data = {
        'xl/workbook.xml': f'<workbook xmlns="{MAIN}" xmlns:r="{REL}"><sheets>{names}</sheets></workbook>',
        'xl/_rels/workbook.xml.rels': f'<Relationships xmlns="{PKG}">{links}</Relationships>',
        '[Content_Types].xml': f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">{overrides}</Types>',
    }
    for i, (_, rows) in enumerate(sheets, 1):
        data[f'xl/worksheets/sheet{i}.xml'] = f'<worksheet xmlns="{MAIN}"><sheetData>{rows}</sheetData></worksheet>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, content in data.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def classlist(rows):
    header = row(1, {'A': 'תעודת זהות', 'B': 'שם תלמיד', 'C': 'כיתה', 'D': 'תוספת זמן',
                     'E': 'הגדלה', 'F': 'הקראה', 'G': 'מורה', 'H': 'יחידות', 'J': 'משתתף'})
    return workbook([('dbase', header + rows), ('ניהול', row(1, {'A': 'ניהול'}))])


def student_matrix(records):
    header = row(3, {'CT': 'מתמטיקה 4 יח יב1-יב10 מורה בדיקה [42]'})
    content = ''.join(row(i + 4, {'B': sid, 'C': name, 'E': 'י', 'F': '1', 'CT': mark})
                      for i, (sid, name, mark) in enumerate(records))
    return workbook([('נתוני תלמידים', header + content)])


def accommodations(records, enlargement_header='הגדלת שאלון הבחינה', reading_header='הקראת שאלון במתמטיקה'):
    header = row(3, {'B': 'תעודת זהות', 'F': 'תוספת זמן 25%', 'G': enlargement_header,
                     'H': reading_header, 'I': 'כיתה מצומצמת', 'J': 'חדר נפרד'})
    content = ''.join(row(i + 4, {'B': sid, **values}) for i, (sid, values) in enumerate(records))
    return workbook([('התאמות', header + content)])


# Initial import omits students without a math X and reports them in LOG.
base_blank = classlist('')
student_file = student_matrix([('101', 'כהן א', 'X'), ('102', 'לוי ב', '')])
accommodation_file = accommodations([('101', {'F': 'X', 'G': 'X', 'H': 'X', 'I': 'X', 'J': 'X'})])
created, meta = import_database(base_blank, student_file, accommodation_file, 'new', 'classlist.xlsx')
_, files = _files(created)
rows = _read_sheet(files['xl/worksheets/sheet1.xml'], _strings(files))
assert [rows[i]['A'] for i in (2,)] == ['101']
assert rows[2]['G'] == 'מורה בדיקה' and rows[2]['H'] == '4' and rows[2]['J'] == '1'
assert rows[2]['C'] == 'י1'
assert rows[2]['D'] == '25' and rows[2]['E'] == rows[2]['F'] == 'כן'
assert rows[2]['L'] == rows[2]['M'] == '1'
assert meta['logEntries'] == 1 and meta['students'] == 2
log = _read_sheet(files['xl/worksheets/sheet3.xml'], _strings(files))
assert log[2]['C'] == '102'  # successful accommodations are not listed on initial load

# Accommodation columns use the exact corrected header wording.
old_header_output, _ = import_database(
    base_blank, student_matrix([('111', 'בדיקה', 'X')]),
    accommodations([('111', {'G': 'X', 'H': 'X'})], 'הגדלת שאלון בחינה', 'מתמטיקה והקראה'),
    'new', 'classlist.xlsx')
_, files = _files(old_header_output)
old_header_rows = _read_sheet(files['xl/worksheets/sheet1.xml'], _strings(files))
assert old_header_rows[2].get('E', '') == old_header_rows[2].get('F', '') == ''
new_header_rows = rows
assert new_header_rows[2]['E'] == new_header_rows[2]['F'] == 'כן'

# During an update, blank accommodation cells clear stale values from dbase and are logged.
stale_base = classlist(row(2, {'A': '115', 'B': 'תלמיד בדיקה', 'D': '25', 'E': 'כן', 'F': 'כן',
                              'G': 'מורה', 'H': '4', 'J': '1', 'L': '1', 'M': '1'}))
cleared, clear_meta = import_database(stale_base, b'', accommodations([('115', {})]), 'update', 'classlist.xlsx')
_, files = _files(cleared)
clear_rows = _read_sheet(files['xl/worksheets/sheet1.xml'], _strings(files))
assert all(clear_rows[2].get(column, '') == '' for column in ('D', 'E', 'F', 'L', 'M'))
clear_log = _read_sheet(files['xl/worksheets/sheet3.xml'], _strings(files))
assert clear_meta['logEntries'] == 1 and clear_log[2]['B'] == 'עדכון התאמות'
assert 'בוטל/הוסר' in clear_log[2]['E']

# Initial load sorts by teacher, study units, then student name.
multi_headers = row(3, {'CT': 'מתמטיקה 5 יח יב1 מורה ב', 'CU': 'מתמטיקה 3 יח יב1 מורה א',
                        'CV': 'מתמטיקה 4 יח יב1 מורה א'})
multi_students = ''.join([
    row(4, {'B': '203', 'C': 'זד', 'E': 'י', 'F': '1', 'CT': 'X'}),
    row(5, {'B': '202', 'C': 'בית', 'E': 'י', 'F': '1', 'CU': 'X'}),
    row(6, {'B': '201', 'C': 'אלף', 'E': 'י', 'F': '1', 'CV': 'X'}),
])
sorted_file, _ = import_database(base_blank, workbook([('נתוני תלמידים', multi_headers + multi_students)]), b'', 'new', 'classlist.xlsx')
_, files = _files(sorted_file)
sorted_rows = _read_sheet(files['xl/worksheets/sheet1.xml'], _strings(files))
assert [sorted_rows[i]['A'] for i in (2, 3, 4)] == ['202', '201', '203']

# A single student may be assigned to multiple teachers within the same math
# level (co-taught 3א groups). Keep one dbase row and retain both teacher names.
co_taught_headers = row(3, {'CT': 'מתמטיקה 3 יח יב1 מורה א', 'CU': 'מתמטיקה 3 יח יב1 מורה ב'})
co_taught_row = row(4, {'B': '301', 'C': 'תלמיד משותף', 'E': 'י', 'F': '1', 'CT': 'X', 'CU': 'X'})
co_taught_output, co_taught_meta = import_database(
    base_blank, workbook([('נתוני תלמידים', co_taught_headers + co_taught_row)]), b'', 'new', 'classlist.xlsx')
_, files = _files(co_taught_output)
co_taught_rows = _read_sheet(files['xl/worksheets/sheet1.xml'], _strings(files))
assert co_taught_meta['students'] == 1
assert co_taught_rows[2]['A'] == '301' and co_taught_rows.get(3, {}).get('A', '') == ''
assert co_taught_rows[2]['G'] == 'מורה א / מורה ב' and co_taught_rows[2]['H'] == '3'

# One student cannot be loaded into two different study levels as one dbase row.
mixed_levels = row(3, {'CT': 'מתמטיקה 3 יח יב1 מורה א', 'CU': 'מתמטיקה 4 יח יב1 מורה ב'})
mixed_student = row(4, {'B': '302', 'C': 'תלמיד בדיקה', 'E': 'י', 'F': '1', 'CT': 'X', 'CU': 'X'})
try:
    import_database(base_blank, workbook([('נתוני תלמידים', mixed_levels + mixed_student)]), b'', 'new', 'classlist.xlsx')
except ValueError as error:
    assert 'כמה רמות מתמטיקה' in str(error) and '302' in str(error)
else:
    raise AssertionError('A student marked in two math levels was silently assigned twice')

# A grade-7 teacher name gets a suffix only when that teacher also teaches a 3-unit class.
headers = row(3, {'CT': 'מתמטיקה 3 יח י7 מורה א [1]', 'CU': 'מתמטיקה 4 יח יב3 מורה א [2]'})
marked = row(4, {'B': '201', 'C': 'תלמיד', 'E': 'י', 'F': '7', 'CT': 'X'})
parsed, _ = parse_teacher_workbook(workbook([('matrix', headers + marked)]))
assert parsed[0]['teacher'] == 'מורה א' and parsed[0]['class'] == 'י7'
headers = row(3, {'CT': 'מתמטיקה 3 יח י7 מורה א [1]', 'CU': 'מתמטיקה 3 יח יב3 מורה א [2]'})
parsed, _ = parse_teacher_workbook(workbook([('matrix', headers + marked)]))
assert parsed[0]['teacher'] == 'מורה אי7'

# Update every record including blank/zero J; preserve J and report unmatched rows.
base = classlist(
    row(2, {'A': '101', 'B': 'שם ישן', 'C': 'י1', 'G': 'מורה ישן', 'H': '3', 'J': '1'})
    + row(3, {'A': '102', 'B': 'כהן ב', 'C': 'י1', 'G': 'מורה ישן', 'H': '3'})
    + row(4, {'A': '103', 'B': 'כהן ג', 'C': 'י1', 'G': 'מורה ישן', 'H': '3', 'J': '0', 'L': '1'})
    + row(5, {'A': '104', 'B': 'ישן ד', 'C': 'י1', 'G': 'מורה ישן', 'H': '3'}))

# A teacherless update preserves an existing assignment and is logged without an accommodation duplicate.
teacherless_update, _ = import_database(base, student_matrix([('101', 'כהן א', '')]),
                                        accommodations([('999', {'F': 'X'})]), 'update', 'classlist.xlsx')
_, files = _files(teacherless_update)
updated_rows = _read_sheet(files['xl/worksheets/sheet1.xml'], _strings(files))
assert updated_rows[2]['G'] == 'מורה ישן'
log_rows = _read_sheet(files['xl/worksheets/sheet3.xml'], _strings(files))
assert log_rows[2]['C'] == '101' and log_rows[2]['B'] == 'חסר שיבוץ מתמטיקה'
updated, update_meta = import_database(
    base, student_matrix([('101', 'כהן א', 'X'), ('102', 'כהן ב', 'X'), ('103', 'כהן ג', 'X'), ('105', 'חדש ה', 'X')]),
    accommodations([('103', {'F': 'X'})]), 'update', 'classlist.xlsx')
_, files = _files(updated)
rows = _read_sheet(files['xl/worksheets/sheet1.xml'], _strings(files))
assert [rows[i]['A'] for i in range(2, 6)] == ['101', '102', '103', '104']
assert rows[2]['G'] == rows[3]['G'] == rows[4]['G'] == 'מורה בדיקה'
assert [rows[i].get('J', '') for i in (2, 3, 4, 5)] == ['1', '', '0', '']
assert rows[5]['B'] == 'ישן ד' and rows[4].get('L', '') == ''
assert update_meta['dbaseRecords'] == 4 and update_meta['dbaseNonParticipants'] == 3
assert update_meta['matchedNonParticipants'] == 2 and update_meta['updatedNonParticipants'] == 2
assert update_meta['unmatchedRecords'] == 1 and update_meta['unmatchedNonParticipants'] == 1
assert 'xl/worksheets/sheet3.xml' in files  # a fresh LOG sheet was added

# An accommodations-only update works even when the source contains no checked accommodations.
empty_accommodation_file = accommodations([('102', {})])
only_accommodations, only_meta = import_database(base, b'', empty_accommodation_file, 'update', 'classlist.xlsx')
assert only_meta['studentFileLoaded'] is False and only_meta['accommodationFileLoaded'] is True
assert only_meta['accommodationStudents'] == 0

# Bad dbase rows must still be rejected instead of silently skipped or collapsed.
bad = classlist(row(2, {'B': 'תלמיד בלי מזהה', 'J': '0'}))
try:
    import_database(bad, student_matrix([('101', 'כהן א', 'X')]), b'', 'update', 'classlist.xlsx')
except ValueError as error:
    assert 'שורה 2' in str(error) and 'תעודת זהות' in str(error)
else:
    raise AssertionError('A dbase student without an ID was silently omitted')

duplicate = classlist(row(2, {'A': '101', 'B': 'תלמיד ראשון'}) + row(3, {'A': '101', 'B': 'תלמיד נוסף', 'J': '0'}))
try:
    import_database(duplicate, student_matrix([('101', 'כהן א', 'X')]), b'', 'update', 'classlist.xlsx')
except ValueError as error:
    assert 'כפולה' in str(error) and '2' in str(error) and '3' in str(error)
else:
    raise AssertionError('Duplicate dbase IDs were silently collapsed')

print('Synthetic import/update checks passed: all dbase rows, J preservation, accommodations, and LOG entries.')
