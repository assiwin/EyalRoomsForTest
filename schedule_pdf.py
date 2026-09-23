"""Create a clean one-page PDF of the editable exam-time calculator."""
import io
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, Table, TableStyle

from envelopes import _p, _register_fonts, _visual


LEVELS = ('3a', '3', '4', '5')
EXTRAS = (0, 25, 33, 50)


def _validate_schedule(schedule):
    if not isinstance(schedule, dict):
        raise ValueError('נתוני זמני הבחינה אינם תקינים.')
    cleaned = {}
    for level in LEVELS:
        item = schedule.get(level)
        if not isinstance(item, dict):
            raise ValueError('חסרים נתוני זמן עבור אחת מרמות הלימוד.')
        start = item.get('start')
        duration = item.get('duration')
        if not isinstance(start, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', start):
            raise ValueError('שעת התחלה אינה תקינה.')
        if type(duration) is not int or not 1 <= duration <= 600:
            raise ValueError('משך הבחינה אינו תקין.')
        cleaned[level] = {'start': start, 'duration': duration}
    return cleaned


def _end_time(start, duration, extra):
    hours, minutes = (int(value) for value in start.split(':'))
    total = hours * 60 + minutes + duration + duration * extra // 100
    return f'{total // 60 % 24:02d}:{total % 60:02d}'


def create_schedule_pdf(schedule, font_base):
    """Return (pdf_bytes, metadata) for the current calculator values."""
    schedule = _validate_schedule(schedule)
    _register_fonts(font_base)
    output = io.BytesIO()
    canvas = Canvas(output, pagesize=A4, pageCompression=1)
    canvas.setTitle('חישובי זמני הבחינה')
    width, height = A4

    canvas.setFillColor(colors.HexColor('#17324d'))
    canvas.setFont('EnvelopeHebrewBold', 19)
    canvas.drawRightString(width - 22 * mm, height - 28 * mm, _visual('חישובי זמני הבחינה'))
    canvas.setFillColor(colors.HexColor('#60768b'))
    canvas.setFont('EnvelopeHebrew', 9.5)
    canvas.drawRightString(width - 22 * mm, height - 36 * mm, _visual('שעות סיום לפי רמת לימוד ותוספת זמן'))

    normal = ParagraphStyle('schedule-normal', fontName='EnvelopeHebrew', fontSize=10,
                            leading=12, alignment=TA_CENTER, textColor=colors.HexColor('#193149'))
    bold = ParagraphStyle('schedule-bold', parent=normal, fontName='EnvelopeHebrewBold')
    level_order = ('5', '4', '3', '3a')
    data = [[_p(label, bold) for label in ('5 יחידות', '4 יחידות', '3 יחידות', 'א3', 'נתון')]]
    data.append([schedule[level]['start'] for level in level_order] + [_p('שעת התחלה', bold)])
    data.append([str(schedule[level]['duration']) for level in level_order] + [_p('משך בדקות', bold)])
    labels = {0: 'סיום ללא תוספת', 25: 'תוספת 25%', 33: 'תוספת 33%', 50: 'תוספת 50%'}
    for extra in EXTRAS:
        data.append([_end_time(schedule[level]['start'], schedule[level]['duration'], extra)
                     for level in level_order] + [_p(labels[extra], bold)])

    col_widths = [27 * mm] * 4 + [38 * mm]
    row_heights = [11 * mm] + [10 * mm] * (len(data) - 1)
    table = Table(data, colWidths=col_widths, rowHeights=row_heights)
    table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.65, colors.HexColor('#9eb3c4')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#c9dff0')),
        ('BACKGROUND', (-1, 1), (-1, -1), colors.HexColor('#f5f8fb')),
        ('BACKGROUND', (0, 1), (-2, 2), colors.HexColor('#fbfdff')),
        ('BACKGROUND', (0, 4), (-2, 4), colors.HexColor('#f8fbfd')),
        ('BACKGROUND', (0, 6), (-2, 6), colors.HexColor('#f8fbfd')),
        ('FONTNAME', (0, 0), (-1, 0), 'EnvelopeHebrewBold'),
        ('FONTNAME', (0, 1), (-1, -1), 'EnvelopeHebrewBold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#17324d')),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#193149')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    table_width = sum(col_widths)
    _, table_height = table.wrapOn(canvas, table_width, height)
    table.drawOn(canvas, (width - table_width) / 2, height - 54 * mm - table_height)

    canvas.setStrokeColor(colors.HexColor('#dce6ef'))
    canvas.line(22 * mm, 18 * mm, width - 22 * mm, 18 * mm)
    canvas.save()
    value = output.getvalue()
    if not value.startswith(b'%PDF-') or len(value) < 1000:
        raise ValueError('יצירת קובץ זמני הבחינה נכשלה.')
    return value, {'levels': 4, 'rows': len(data), 'pages': 1}
