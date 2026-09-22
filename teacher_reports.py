"""Create one student-to-physical-room PDF per teacher."""
import io
import re
import zipfile
from collections import defaultdict

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Table, TableStyle

from envelopes import _clean, _p, _register_fonts, _visual


def _safe_filename(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', _clean(value))
    value = re.sub(r'\s+', ' ', value).strip(' .')
    return value[:80] or 'מורה'


def _unit_key(value):
    return {'3': 0, '3א': 1, '4': 2, '5': 3}.get(value, 9)


def _validate_room_labels(result, room_labels):
    rooms = set(result.get('matrix', {}).get('rooms') or [])
    if not isinstance(room_labels, dict) or set(room_labels) != rooms:
        raise ValueError('יש להזין מספר חדר בחינה לכל החדרים בשיבוץ.')
    cleaned = {}
    for room in sorted(rooms):
        label = _clean(room_labels.get(room))
        if not label:
            raise ValueError(f'חסר מספר חדר בחינה עבור חדר {room}.')
        if len(label) > 40:
            raise ValueError(f'מספר חדר הבחינה עבור חדר {room} ארוך מדי.')
        cleaned[room] = label
    if len(set(cleaned.values())) != len(cleaned):
        raise ValueError('כל מספר חדר בחינה חייב להיות ייחודי.')
    return cleaned


def _teacher_pdf(teacher, students, room_labels, font_base):
    _register_fonts(font_base)
    output = io.BytesIO()
    from reportlab.pdfgen.canvas import Canvas
    canvas = Canvas(output, pagesize=A4, pageCompression=1)
    canvas.setTitle(f'שיבוץ תלמידים - {teacher}')
    canvas.setAuthor('אסי וינברגר')
    width, height = A4
    left, right = 16 * mm, width - 16 * mm
    top, bottom = height - 15 * mm, 15 * mm
    usable = right - left

    normal = ParagraphStyle('teacher-normal-he', fontName='EnvelopeHebrew',
                            fontSize=10, leading=12, alignment=TA_RIGHT)
    header = ParagraphStyle('teacher-header-he', parent=normal,
                            fontName='EnvelopeHebrewBold', fontSize=10.5,
                            leading=12, alignment=TA_CENTER)
    room_style = ParagraphStyle('teacher-room-he', parent=normal,
                                fontSize=10, alignment=TA_CENTER)

    units = sorted({s.get('unit', '') for s in students}, key=_unit_key)
    units_text = ' ו־'.join(units)
    title_text = f'שיבוץ חדרים לתלמידי {units_text} יחידות, מורה {teacher}'
    rows_per_page = 27
    chunks = [students[i:i + rows_per_page] for i in range(0, len(students), rows_per_page)]

    for page_index, chunk in enumerate(chunks):
        canvas.setFillColor(colors.HexColor('#111111'))
        canvas.setFont('EnvelopeHebrewBold', 15)
        canvas.drawRightString(right, top, _visual(title_text))
        if page_index:
            canvas.setFont('EnvelopeHebrew', 9)
            canvas.drawRightString(right, top - 6 * mm, _visual('המשך'))

        data = [[_p('חדר בחינה', header), _p('שם תלמיד', header)]]
        for student in chunk:
            internal_room = int(student['assigned_room'])
            data.append([
                _p(room_labels[internal_room], room_style),
                _p(student.get('name', ''), normal),
            ])
        table = Table(data, colWidths=[52 * mm, usable - 52 * mm],
                      rowHeights=[11 * mm] + [8.5 * mm] * len(chunk))
        table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.7, colors.HexColor('#333333')),
            ('FONTNAME', (0, 0), (-1, 0), 'EnvelopeHebrewBold'),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        _, table_height = table.wrapOn(canvas, usable, height)
        table.drawOn(canvas, left, top - 15 * mm - table_height)
        canvas.showPage()

    canvas.save()
    value = output.getvalue()
    if not value.startswith(b'%PDF-') or len(value) < 1000:
        raise ValueError(f'יצירת הדוח עבור המורה {teacher} נכשלה.')
    return value


def create_teacher_reports(book, result, room_labels, font_base):
    """Return (zip_bytes, reports, metadata), with one PDF in reports per teacher."""
    labels = _validate_room_labels(result, room_labels)
    assignments = result.get('assignments') or {}
    by_teacher = defaultdict(list)
    for student in book.get('participants', []):
        room = assignments.get(student['row'])
        if room is None:
            raise ValueError(f"שורה {student['row']}: המשתתף לא שובץ לחדר.")
        item = dict(student)
        item['assigned_room'] = int(room)
        by_teacher[student['teacher']].append(item)
    if not by_teacher:
        raise ValueError('לא נמצאו תלמידים להפקת דוחות מורים.')

    reports = {}
    for index, teacher in enumerate(sorted(by_teacher), 1):
        students = sorted(by_teacher[teacher],
                          key=lambda s: (_unit_key(s.get('unit')), labels[s['assigned_room']], s.get('name', '')))
        filename = f'{index:02d}_{_safe_filename(teacher)}.pdf'
        reports[filename] = _teacher_pdf(teacher, students, labels, font_base)

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for filename, data in reports.items():
            zf.writestr(filename, data)
    return archive.getvalue(), reports, {
        'teachers': len(reports),
        'students': sum(len(v) for v in by_teacher.values()),
        'files': list(reports),
    }
