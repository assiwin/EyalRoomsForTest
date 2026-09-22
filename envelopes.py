"""Create printable Hebrew PDF envelope sheets from an approved assignment."""
import io
import os
import re
from collections import Counter
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, Table, TableStyle


_HEBREW = re.compile(r'[\u0590-\u05ff]')
_CONTROL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')


def _clean(value):
    return _CONTROL.sub('', str(value or '').strip())


def _visual(value):
    """Return a practical visual-order string for ReportLab's non-bidi canvas."""
    value = _clean(value)
    if not _HEBREW.search(value):
        return value
    words = value.split()
    def word_visual(word):
        return word[::-1] if _HEBREW.search(word) else word
    return ' '.join(word_visual(word) for word in reversed(words))


def _font_paths(base):
    base = Path(base)
    regular = base / 'assets' / 'DejaVuSans.ttf'
    bold = base / 'assets' / 'DejaVuSans-Bold.ttf'
    if regular.exists() and bold.exists():
        return regular, bold
    # Windows includes Hebrew-capable fonts. This fallback keeps the GitHub
    # build small while still embedding a local font in every generated PDF.
    windows_fonts = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts'
    for regular_name, bold_name in [('arial.ttf', 'arialbd.ttf'), ('segoeui.ttf', 'segoeuib.ttf')]:
        system_regular = windows_fonts / regular_name
        system_bold = windows_fonts / bold_name
        if system_regular.exists() and system_bold.exists():
            return system_regular, system_bold
    raise ValueError('לא נמצא גופן עברי מתאים. יש להתקין מחדש את האפליקציה.')


def _register_fonts(base):
    regular, bold = _font_paths(base)
    if 'EnvelopeHebrew' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('EnvelopeHebrew', str(regular)))
    if 'EnvelopeHebrewBold' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('EnvelopeHebrewBold', str(bold)))


def _p(text, style):
    lines=[]
    for line in _clean(text).splitlines() or ['']:
        lines.append(_visual(line).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))
    escaped='<br/>'.join(lines)
    return Paragraph(escaped or ' ', style)


def _room_pages(members, per_page=32):
    return [members[i:i + per_page] for i in range(0, len(members), per_page)] or [[]]


def create_envelopes_pdf(book, result, grade, notes, font_base):
    """Return (pdf_bytes, metadata). Does not modify the workbook or result."""
    if grade not in ('י׳', 'י״א', 'י״ב'):
        raise ValueError('יש לבחור שכבת מבחן: י׳, י״א או י״ב.')
    if not isinstance(notes, list) or len(notes) > 2:
        raise ValueError('ניתן להזין עד שתי הערות לחדרים.')
    assignments = result.get('assignments') or {}
    if not assignments:
        raise ValueError('אין שיבוץ תקין שממנו ניתן להפיק מעטפות.')
    rooms = {int(r['room']) for r in result.get('rooms', [])}
    cleaned_notes = {}
    for item in notes:
        if not isinstance(item, dict):
            raise ValueError('מבנה ההערה אינו תקין.')
        try:
            room = int(item.get('room'))
        except (TypeError, ValueError):
            raise ValueError('יש לבחור מספר חדר לכל הערה.')
        text = _clean(item.get('text'))
        if room not in rooms:
            raise ValueError(f'חדר {room} אינו קיים בשיבוץ הנוכחי.')
        if not text:
            raise ValueError('יש להזין תוכן להערה או להסיר את שורת ההערה.')
        if len(text) > 120:
            raise ValueError('אורך הערה מוגבל ל־120 תווים.')
        cleaned_notes.setdefault(room, []).append(text)

    by_room = {}
    for student in book['participants']:
        room = assignments.get(student['row'])
        if room is None:
            raise ValueError(f"שורה {student['row']}: המשתתף לא שובץ לחדר.")
        by_room.setdefault(int(room), []).append(student)
    expected = result.get('participants')
    if sum(map(len, by_room.values())) != expected:
        raise ValueError('מספר המשתתפים בדפי המעטפות אינו תואם לתוצאת השיבוץ.')

    _register_fonts(font_base)
    output = io.BytesIO()
    from reportlab.pdfgen.canvas import Canvas
    canvas = Canvas(output, pagesize=A4, pageCompression=1)
    canvas.setTitle('דפי מעטפות לחדרי בחינה')
    canvas.setAuthor('אסי וינברגר')
    width, height = A4

    normal = ParagraphStyle('normal-he', fontName='EnvelopeHebrew', fontSize=8.2,
                            leading=10, alignment=TA_RIGHT, textColor=colors.HexColor('#111111'))
    header = ParagraphStyle('header-he', parent=normal, fontName='EnvelopeHebrewBold',
                            fontSize=8.2, alignment=TA_CENTER)
    title = ParagraphStyle('title-he', parent=header, fontSize=15, leading=18)
    box = ParagraphStyle('box-he', parent=header, fontSize=11, leading=14)
    note_style = ParagraphStyle('note-he', parent=normal, fontSize=9, leading=11,
                                alignment=TA_RIGHT)

    page_specs = []
    for room in sorted(by_room):
        chunks = _room_pages(by_room[room])
        for index, chunk in enumerate(chunks, 1):
            page_specs.append((room, index, len(chunks), chunk, by_room[room]))
    total_pages = len(page_specs)

    for page_number, (room, part, room_parts, members, all_members) in enumerate(page_specs, 1):
        right = width - 18 * mm
        left = 18 * mm
        usable = right - left
        top = height - 16 * mm

        continuation = ' — המשך' if room_parts > 1 and part > 1 else ''
        canvas.setFont('EnvelopeHebrewBold', 15)
        canvas.drawRightString(right, top, _visual(f'חדר בחינה {room}{continuation}'))

        # Header boxes: room, exam grade and up to two room-specific notes.
        header_y = top - 8 * mm
        note_text = '\n'.join(cleaned_notes.get(room, []))
        top_data = [[
            _p(note_text, note_style),
            _p(f'מבחן שכבה\n{grade}', box),
            _p('', box),
        ]]
        top_table = Table(top_data, colWidths=[usable - 80 * mm, 38 * mm, 42 * mm], rowHeights=[26 * mm])
        top_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (1, 0), (2, 0), colors.HexColor('#f2f2f2')),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ]))
        tw, th = top_table.wrapOn(canvas, usable, 22 * mm)
        top_table.drawOn(canvas, left, header_y - th)

        # Full-width invigilation roster. The rightmost slot starts with hour 1.
        supervision_top = header_y - th - 4 * mm
        supervision_data = [
            [_p('השגחה', header)] + [''] * 5,
            [_p(f'שעה {hour}', header) for hour in range(6, 0, -1)],
            [_p('', normal) for _ in range(6)],
        ]
        supervision = Table(
            supervision_data,
            colWidths=[usable / 6] * 6,
            rowHeights=[7 * mm, 7 * mm, 11 * mm],
        )
        supervision.setStyle(TableStyle([
            ('SPAN', (0, 0), (-1, 0)),
            ('GRID', (0, 0), (-1, -1), 0.7, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#d9d9d9')),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f2f2f2')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ]))
        _, supervision_height = supervision.wrapOn(canvas, usable, 26 * mm)
        supervision.drawOn(canvas, left, supervision_top - supervision_height)

        table_top = supervision_top - supervision_height - 5 * mm
        columns = [
            ('הקראה', 15), ('הגדלה', 15), ('תוספת זמן', 20), ('הגשה', 15),
            ('נוכחות', 17), ('מורה', 28), ('יחידות', 17), ('שם', 48),
        ]
        col_widths = [w * mm for _, w in columns]
        # Scale exactly into the printable width.
        scale = usable / sum(col_widths)
        col_widths = [w * scale for w in col_widths]
        data = [[_p(label, header) for label, _ in columns]]
        for student in members:
            data.append([
                _p(student.get('reading', ''), normal),
                _p(student.get('enlargement', ''), normal),
                _p(student.get('extra_time', ''), normal),
                _p('', normal), _p('', normal),
                _p(student.get('teacher', ''), normal),
                _p(student.get('unit', ''), header),
                _p(student.get('name', ''), normal),
            ])
        while len(data) < 33:
            data.append([_p('', normal) for _ in columns])
        row_height = 14.1
        student_table = Table(data, colWidths=col_widths,
                              rowHeights=[20] + [row_height] * (len(data) - 1), repeatRows=1)
        student_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.55, colors.HexColor('#222222')),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#d9d9d9')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ]))
        sw, sh = student_table.wrapOn(canvas, usable, table_top - 34 * mm)
        table_y = table_top - sh
        student_table.drawOn(canvas, left, table_y)

        counts = Counter(s.get('unit', '') for s in all_members)
        order = ['3', '3א', '4', '5']
        summary = '   '.join(f'{counts[u]} נבחנים {u} יח׳' for u in order if counts[u])
        canvas.setFont('EnvelopeHebrewBold', 9.5)
        canvas.drawRightString(right, table_y - 7 * mm, _visual(summary))
        canvas.showPage()

    canvas.save()
    value = output.getvalue()
    if not value.startswith(b'%PDF-') or len(value) < 1000:
        raise ValueError('יצירת קובץ ה־PDF נכשלה.')
    return value, {'rooms': len(by_room), 'pages': total_pages, 'students': expected}
