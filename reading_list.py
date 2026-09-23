"""Create the A4 reading-accommodation list PDF."""
import io
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Table, TableStyle
from envelopes import _clean, _p, _register_fonts, _visual


def create_reading_list_pdf(book, result, room_labels, font_base):
    _register_fonts(font_base)
    assignments = result.get('assignments') or {}
    students = []
    for student in book.get('participants', []):
        if _clean(student.get('reading')).lower() != 'כן':
            continue
        room = assignments.get(student['row'])
        if room is None or int(room) not in room_labels:
            raise ValueError(f"שורה {student['row']}: חסר שיבוץ מלא עבור רשימת ההקראה.")
        students.append((student.get('name', ''), int(room), room_labels[int(room)]))
    students.sort(key=lambda item: (item[1], item[0]))

    from reportlab.pdfgen.canvas import Canvas
    output = io.BytesIO(); canvas = Canvas(output, pagesize=A4, pageCompression=1)
    canvas.setTitle('רשימת הקראה'); canvas.setAuthor('אסי וינברגר')
    width, height = A4; left, right = 16*mm, width-16*mm; top = height-16*mm; usable = right-left
    normal = ParagraphStyle('reading-normal', fontName='EnvelopeHebrew', fontSize=10.5, leading=13, alignment=TA_RIGHT)
    center = ParagraphStyle('reading-center', parent=normal, alignment=TA_CENTER)
    header = ParagraphStyle('reading-header', parent=center, fontName='EnvelopeHebrewBold', fontSize=11)
    chunks = [students[i:i+27] for i in range(0, len(students), 27)] or [[]]
    for page_index, chunk in enumerate(chunks):
        canvas.setFont('EnvelopeHebrewBold', 17); canvas.drawRightString(right, top, _visual('רשימת הקראה'))
        if page_index: canvas.setFont('EnvelopeHebrew', 9); canvas.drawRightString(right, top-6*mm, _visual('המשך'))
        data = [[_p('חדר בחינה', header), _p('חדר מספר', header), _p('שם תלמיד', header)]]
        data += [[_p(label, center), _p(str(room), center), _p(name, normal)] for name, room, label in chunk]
        table = Table(data, colWidths=[52*mm, 34*mm, usable-86*mm], rowHeights=[11*mm]+[8.5*mm]*len(chunk))
        table.setStyle(TableStyle([
            ('GRID',(0,0),(-1,-1),0.7,colors.HexColor('#333333')),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#D9EAF7')),
            ('VALIGN',(0,0),(-1,-1),'MIDDLE'),('ALIGN',(0,0),(1,-1),'CENTER'),('ALIGN',(2,0),(2,-1),'RIGHT'),
            ('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),2),
        ]))
        _, table_height = table.wrapOn(canvas, usable, height); table.drawOn(canvas, left, top-14*mm-table_height); canvas.showPage()
    canvas.save(); value = output.getvalue()
    if not value.startswith(b'%PDF-') or len(value) < 1000: raise ValueError('יצירת רשימת ההקראה נכשלה.')
    return value, {'readingStudents': len(students), 'readingPages': len(chunks)}
