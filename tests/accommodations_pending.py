"""Regression coverage for accommodation headings awaiting approval."""
import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import database_import as importer

MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG_REL = 'http://schemas.openxmlformats.org/package/2006/relationships'


def workbook(sheets):
    """Build a minimal xlsx package from (name, rows) pairs."""
    sheet_nodes = ''.join(
        f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>'
        for i, (name, _) in enumerate(sheets, 1)
    )
    rel_nodes = ''.join(
        f'<Relationship Id="rId{i}" Type="{REL}/worksheet" Target="worksheets/sheet{i}.xml"/>'
        for i in range(1, len(sheets) + 1)
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('xl/workbook.xml',
                         f'<workbook xmlns="{MAIN}" xmlns:r="{REL}"><sheets>{sheet_nodes}</sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels',
                         f'<Relationships xmlns="{PKG_REL}">{rel_nodes}</Relationships>')
        overrides = ''.join(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(1, len(sheets) + 1)
        )
        archive.writestr('[Content_Types].xml',
                         '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                         '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                         '<Default Extension="xml" ContentType="application/xml"/>'
                         '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                         f'{overrides}</Types>')
        for index, (_, rows) in enumerate(sheets, 1):
            row_xml = []
            for row_number, values in rows.items():
                cells = ''.join(
                    f'<c r="{col}{row_number}" t="inlineStr"><is><t>{value}</t></is></c>'
                    for col, value in values.items()
                )
                row_xml.append(f'<row r="{row_number}">{cells}</row>')
            archive.writestr(f'xl/worksheets/sheet{index}.xml',
                             f'<worksheet xmlns="{MAIN}"><sheetData>{"".join(row_xml)}</sheetData></worksheet>')
    return out.getvalue()


def classlist():
    headers = dict(zip('ABCDEFGHIJKLMN',
                       ['ת.ז', 'שם', 'כיתה', 'תוספת זמן', 'הגדלה', 'הקראה',
                        'מורה', 'יחידות', 'חדר בחינה', 'משתתף', 'בר אילן',
                        'מצומצם 10 נוסף', 'נפרד 1', 'סידור']))
    return workbook([('dbase', {1: headers, 2: {}}), ('ניהול', {1: {}})])


def main():
    teacher_data = workbook([('מורה בדיקה', {
        3: {'B': 'ת.ז', 'C': 'שם', 'D': 'שם פרטי', 'E': 'שכבה', 'F': 'כיתה',
            'K': 'מתמטיקה 3 יח מורה בדיקה'},
        4: {'B': '123456789', 'C': 'כהן', 'D': 'דנה', 'E': 'י', 'F': '1', 'K': 'X'},
        5: {'B': '987654321', 'C': 'לוי', 'D': 'עדי', 'E': 'י', 'F': '1', 'K': 'X'},
    })])
    accommodation_data = workbook([('התאמות', {
        3: {'A': 'מס', 'B': 'ת.ז', 'F': 'תוספת זמן 25%',
            'G': 'תוספת זמן 33% טרם אושר', 'H': 'תוספת זמן 50% טרם אושר',
            'I': 'הגדלת שאלון הבחינה טרם אושר',
            'J': 'הקראת שאלון במתמטיקה - טרם אושר',
            'K': 'כיתה מצומצמת', 'L': 'חדר נפרד טרם אושר'},
        4: {'B': '123456789', 'G': 'X', 'H': 'X', 'I': 'X', 'J': 'X', 'K': 'X', 'L': 'X'},
        5: {'B': '987654321', 'F': 'X', 'G': 'X', 'H': 'X'},
    })])

    parsed, _, fields = importer.parse_accommodations_workbook(accommodation_data)
    assert fields == {'D', 'L'}, fields
    assert parsed['123456789'] == {'L': '1'}, parsed['123456789']
    assert parsed['987654321'] == {'D': '25'}, parsed['987654321']

    new_data, _ = importer.import_database(classlist(), teacher_data, accommodation_data,
                                           'new', 'classlist12.xlsx')
    infos, files = importer._files(new_data)
    rows = importer._read_sheet(files[importer._classlist(files, 'classlist12.xlsx')],
                                importer._strings(files))
    records = importer._dbase_records(rows)
    pending = records['123456789'][1]
    assert pending.get('D', '') == ''
    assert pending.get('E', '') == ''
    assert pending.get('F', '') == ''
    assert pending.get('L', '') == '1'
    approved = records['987654321'][1]
    assert approved.get('D') == '25'

    updated, _ = importer.import_database(new_data, teacher_data, accommodation_data,
                                          'update', 'classlist12.xlsx')
    _, updated_files = importer._files(updated)
    updated_rows = importer._read_sheet(
        updated_files[importer._classlist(updated_files, 'classlist12.xlsx')],
        importer._strings(updated_files))
    updated_records = importer._dbase_records(updated_rows)
    assert updated_records['123456789'][1].get('D', '') != '33'
    assert updated_records['123456789'][1].get('D', '') != '50'
    assert updated_records['987654321'][1].get('D') == '25'
    print('Pending-approval accommodation columns ignored in new and update modes')


if __name__ == '__main__':
    main()
