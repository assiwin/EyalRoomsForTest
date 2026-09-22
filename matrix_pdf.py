"""Create a printable Hebrew teachers-by-rooms matrix PDF."""
import io

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Table, TableStyle

from envelopes import _clean, _p, _register_fonts, _visual


def create_matrix_pdf(result, font_base):
    """Return (pdf_bytes, metadata) for an approved assignment result."""
    matrix = result.get('matrix') or {}
    rooms = matrix.get('rooms') or []
    rows = matrix.get('rows') or []
    room_totals = matrix.get('roomTotals') or []
    participants = result.get('participants')

    if not rooms or not rows or participants is None:
        raise ValueError('אין מטריצת שיבוץ תקינה שממנה ניתן להפיק PDF.')
    if len(room_totals) != len(rooms):
        raise ValueError('נתוני סיכום החדרים במטריצה אינם תקינים.')
    if sum(room_totals) != participants:
        raise ValueError('סיכום התלמידים בחדרים אינו תואם לתוצאת השיבוץ.')
    for item in rows:
        counts = item.get('counts') or []
        if len(counts) != len(rooms) or sum(counts) != item.get('total'):
            raise ValueError('אחת משורות המורים במטריצה אינה תקינה.')

    _register_fonts(font_base)
    output = io.BytesIO()
    from reportlab.pdfgen.canvas import Canvas
    page_size = landscape(A4)
    canvas = Canvas(output, pagesize=page_size, pageCompression=1)
    canvas.setTitle('מטריצת מורים וחדרים')
    canvas.setAuthor('אסי וינברגר')
    width, height = page_size

    normal = ParagraphStyle(
        'matrix-normal-he', fontName='EnvelopeHebrew', fontSize=7.2,
        leading=8.2, alignment=TA_CENTER, textColor=colors.HexColor('#20364b'))
    header = ParagraphStyle(
        'matrix-header-he', parent=normal, fontName='EnvelopeHebrewBold',
        fontSize=7.4, leading=8.5, alignment=TA_CENTER)
    teacher_style = ParagraphStyle(
        'matrix-teacher-he', parent=normal, fontSize=7.6,
        leading=8.6, alignment=TA_RIGHT)

    left = 10 * mm
    right = width - 10 * mm
    usable = right - left
    top = height - 11 * mm
    bottom = 10 * mm
    title_block = 25 * mm
    row_height = 7.3 * mm
    header_height = 8.5 * mm
    max_rows = max(1, int((top - bottom - title_block - header_height) // row_height) - 1)
    chunks = [rows[i:i + max_rows] for i in range(0, len(rows), max_rows)]

    name_width = 37 * mm
    unit_width = 15 * mm
    total_width = 17 * mm
    room_width = min(12 * mm, (usable - name_width - unit_width - total_width) / len(rooms))
    col_widths = [room_width] * len(rooms) + [total_width, unit_width, name_width]
    table_width = sum(col_widths)

    descending_rooms = list(reversed(rooms))
    descending_totals = list(reversed(room_totals))
    header_row = [str(room) for room in descending_rooms] + [
        _p('סה״כ', header), _p('יחידות', header), _p('שם מורה', header)]

    for page_index, chunk in enumerate(chunks):
        canvas.setFont('EnvelopeHebrewBold', 16)
        canvas.setFillColor(colors.HexColor('#223b56'))
        canvas.drawRightString(right, top, _visual('מטריצת מורים וחדרים'))
        canvas.setFont('EnvelopeHebrew', 9)
        canvas.setFillColor(colors.HexColor('#5b6f82'))
        subtitle = 'בכל תא מוצג מספר התלמידים של המורה ורמת הלימוד ששובצו לחדר'
        if page_index:
            subtitle += ' - המשך'
        canvas.drawRightString(right, top - 7 * mm, _visual(subtitle))

        data = [header_row]
        for item in chunk:
            counts = list(reversed(item['counts']))
            data.append([
                *[str(value) if value else '' for value in counts],
                str(item['total']),
                _p(_clean(item.get('unit')), normal),
                _p(_clean(item.get('teacher')), teacher_style),
            ])
        if page_index == len(chunks) - 1:
            data.append([
                *[str(value) for value in descending_totals],
                str(participants), '', _p('סה״כ', header)])

        table = Table(data, colWidths=col_widths,
                      rowHeights=[header_height] + [row_height] * (len(data) - 1))
        last_col = len(col_widths) - 1
        total_col = len(rooms)
        table_style = [
            ('GRID', (0, 0), (-1, -1), 0.55, colors.HexColor('#8798a8')),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#c9dff0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#17324d')),
            ('FONTNAME', (0, 0), (-1, 0), 'EnvelopeHebrewBold'),
            ('FONTNAME', (0, 1), (-1, -1), 'EnvelopeHebrew'),
            ('FONTNAME', (total_col, 1), (total_col, -1), 'EnvelopeHebrewBold'),
            ('BACKGROUND', (total_col, 1), (total_col, -1), colors.HexColor('#fff200')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (last_col, 1), (last_col, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ]
        if page_index == len(chunks) - 1:
            last_row = len(data) - 1
            table_style.extend([
                ('BACKGROUND', (0, last_row), (-1, last_row), colors.HexColor('#fff200')),
                ('FONTNAME', (0, last_row), (-1, last_row), 'EnvelopeHebrewBold')])
        table.setStyle(TableStyle(table_style))
        _, table_height = table.wrapOn(canvas, table_width, height)
        table.drawOn(canvas, right - table_width, top - title_block - table_height)
        canvas.showPage()

    canvas.save()
    value = output.getvalue()
    if not value.startswith(b'%PDF-') or len(value) < 1000:
        raise ValueError('יצירת קובץ מטריצת המורים והחדרים נכשלה.')
    return value, {'rooms': len(rooms), 'teachers': len(rows),
                   'students': participants, 'pages': len(chunks)}
