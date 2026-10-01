"""Regression: database updates must consider all dbase rows, independent of J."""
import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from database_import import _files, _read_sheet, _strings, import_database

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


header = row(1, {'A': 'תעודת זהות', 'B': 'שם תלמיד', 'C': 'כיתה', 'G': 'מורה', 'H': 'יחידות', 'J': 'משתתף'})
base = workbook([
    ('dbase', header
     + row(2, {'A': '101', 'B': 'ישן א', 'C': 'י1', 'G': 'מורה ישן', 'H': '4', 'J': '1'})
     + row(3, {'A': '102', 'B': 'ישן ב', 'C': 'י1', 'G': 'מורה ישן', 'H': '4'})
     + row(4, {'A': '103', 'B': 'ישן ג', 'C': 'י1', 'G': 'מורה ישן', 'H': '4', 'J': '0', 'L': '1'})
     + row(5, {'A': '104', 'B': 'ישן ד', 'C': 'י1', 'G': 'מורה ישן', 'H': '4'})),
    ('ניהול', row(1, {'A': 'ניהול'})),
])
teacher = workbook([
    ('מורה', row(1, {'A': '4', 'B': 'מורה חדשה'})
     + row(4, {'B': '101', 'C': 'כהן', 'D': 'א', 'E': 'י', 'F': '1'})
     + row(5, {'B': '102', 'C': 'כהן', 'D': 'ב', 'E': 'י', 'F': '1'})
     + row(6, {'B': '103', 'C': 'כהן', 'D': 'ג', 'E': 'י', 'F': '1'})),
])

output, meta = import_database(base, teacher, 'update', 'classlist.xlsm')
_, files = _files(output)
rows = _read_sheet(files['xl/worksheets/sheet1.xml'], _strings(files))
assert [rows[i]['A'] for i in range(2, 6)] == ['101', '102', '103', '104']
assert [rows[i]['J'] for i in (2, 4)] == ['1', '0']
assert rows[3].get('J', '') == '' and rows[5].get('J', '') == ''
assert rows[4]['L'] == '1'
assert all(rows[i]['G'] == 'מורה חדשה' for i in (2, 3, 4))
assert rows[3]['B'] == 'כהן ב' and rows[4]['B'] == 'כהן ג'
assert rows[5]['B'] == 'ישן ד'
assert meta['dbaseRecords'] == 4 and meta['dbaseNonParticipants'] == 3
assert meta['matchedNonParticipants'] == 2 and meta['updatedNonParticipants'] == 2
assert meta['unmatchedRecords'] == 1 and meta['unmatchedNonParticipants'] == 1
assert meta['changes'] == 3 and meta['logEntries'] == 4

# A populated row without an ID must be reported instead of silently skipped.
bad = workbook([('dbase', header + row(2, {'B': 'תלמיד בלי מזהה', 'J': '0'})),
                ('ניהול', row(1, {'A': 'ניהול'}))])
try:
    import_database(bad, teacher, 'update', 'classlist.xlsm')
except ValueError as error:
    assert 'שורה 2' in str(error) and 'תעודת זהות' in str(error)
else:
    raise AssertionError('A dbase student without an ID was silently omitted')

duplicate = workbook([('dbase', header
                       + row(2, {'A': '101', 'B': 'תלמיד ראשון'})
                       + row(3, {'A': '101', 'B': 'תלמיד נוסף', 'J': '0'})),
                      ('ניהול', row(1, {'A': 'ניהול'}))])
try:
    import_database(duplicate, teacher, 'update', 'classlist.xlsm')
except ValueError as error:
    assert 'כפולה' in str(error) and '2' in str(error) and '3' in str(error)
else:
    raise AssertionError('Duplicate dbase IDs were silently collapsed')

print('Database update reads active and inactive dbase records, preserves J, and reports missing IDs.')
