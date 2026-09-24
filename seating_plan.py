"""Assign students to 32 classroom seats and create one landscape PDF per room."""
import io
import re
import zipfile
from collections import Counter

import numpy as np
from scipy.optimize import milp, Bounds, LinearConstraint
from scipy.sparse import lil_matrix
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Table, TableStyle

from envelopes import _clean, _p, _register_fonts, _visual
from teacher_reports import _validate_room_labels


ROWS, COLUMNS = 4, 8
SEATS = [(row, column) for row in range(ROWS) for column in range(COLUMNS)]


def _category(unit):
    return '3' if _clean(unit) in ('3', '3א') else _clean(unit)


def _conflicts():
    pairs = set()
    for index, (row, column) in enumerate(SEATS):
        for other, (row2, column2) in enumerate(SEATS):
            if other <= index:
                continue
            beside = row == row2 and abs(column - column2) == 1
            diagonal = abs(row - row2) == 1 and abs(column - column2) == 1
            if beside or diagonal:
                pairs.add((index, other))
    return sorted(pairs)


CONFLICTS = _conflicts()


def arrange_room(students):
    if not students or len(students) > 32:
        raise ValueError('סידור מקומות ישיבה דורש בין תלמיד אחד ל־32 תלמידים בחדר.')
    count = len(students)
    variable_count = count * 32 + 16
    X = lambda student, seat: student * 32 + seat
    Y = lambda table: count * 32 + table
    constraints = []
    def add(values, low, high): constraints.append((values, low, high))

    for student in range(count):
        add({X(student, seat): 1 for seat in range(32)}, 1, 1)
        if students[student].get('problematic'):
            add({X(student, seat): 1 for seat, (row, _) in enumerate(SEATS) if row == 0}, 1, 1)
    for seat in range(32):
        add({X(student, seat): 1 for student in range(count)}, 0, 1)
    for table in range(16):
        row, pair = divmod(table, 4)
        seats = [row * 8 + pair * 2, row * 8 + pair * 2 + 1]
        occupancy = {X(student, seat): 1 for student in range(count) for seat in seats}
        add({**occupancy, Y(table): -2}, -np.inf, 0)
        add({**occupancy, Y(table): -1}, 0, np.inf)
    categories = sorted({_category(student.get('unit')) for student in students})
    for category in categories:
        members = [index for index, student in enumerate(students) if _category(student.get('unit')) == category]
        for left, right in CONFLICTS:
            values = {}
            for student in members:
                values[X(student, left)] = 1
                values[X(student, right)] = 1
            add(values, 0, 1)

    matrix = lil_matrix((len(constraints), variable_count)); lower=[]; upper=[]
    for row, (values, low, high) in enumerate(constraints):
        for column, value in values.items(): matrix[row, column] = value
        lower.append(low); upper.append(high)
    objective = np.zeros(variable_count)
    # First maximize occupied tables. Then prefer front tables and wall seats.
    for table in range(16):
        table_row, pair = divmod(table, 4)
        objective[Y(table)] = -100 + table_row * 2 + pair * .01
    for student in range(count):
        for seat, (row, column) in enumerate(SEATS):
            objective[X(student, seat)] = row * .03
            if column in (1, 6): objective[X(student, seat)] += .01
    result = milp(objective, integrality=np.ones(variable_count),
                  bounds=Bounds(np.zeros(variable_count), np.ones(variable_count)),
                  constraints=LinearConstraint(matrix.tocsr(), lower, upper),
                  options={'time_limit': 25, 'mip_rel_gap': 0})
    if result.x is None:
        raise ValueError('לא נמצא סידור מקומות שעומד בכל כללי ההפרדה בחדר.')
    values = np.rint(result.x).astype(int)
    arranged = [None] * 32
    for student in range(count):
        selected = next((seat for seat in range(32) if values[X(student, seat)]), None)
        if selected is None: raise ValueError('בדיקת סידור המקומות נכשלה.')
        arranged[selected] = students[student]
    _validate_arrangement(arranged, students)
    return arranged


def _validate_arrangement(arranged, students):
    placed = [student for student in arranged if student]
    if len(placed) != len(students) or len({student['row'] for student in placed}) != len(students):
        raise ValueError('בדיקת שלמות סידור המקומות נכשלה.')
    for index, student in enumerate(arranged):
        if student and student.get('problematic') and SEATS[index][0] != 0:
            raise ValueError('תלמיד המסומן לישיבה קדמית לא שובץ בשורה הראשונה.')
    for left, right in CONFLICTS:
        if arranged[left] and arranged[right] and _category(arranged[left]['unit']) == _category(arranged[right]['unit']):
            raise ValueError('בדיקת הפרדת יחידות בסידור המקומות נכשלה.')


def _seat_text(student, style):
    if not student: return _p('', style)
    return _p(f"{student.get('name', '')}\n{student.get('unit', '')} יח׳", style)


def _room_pdf(room, physical_room, arranged, font_base):
    _register_fonts(font_base)
    from reportlab.pdfgen.canvas import Canvas
    output = io.BytesIO();page = landscape(A4)
    canvas = Canvas(output, pagesize=page, pageCompression=1)
    canvas.setTitle(f'סידור מקומות ישיבה - חדר {room}')
    canvas.setAuthor('אסי וינברגר')
    width, height = page
    normal = ParagraphStyle('seat-normal', fontName='EnvelopeHebrew', fontSize=8.2,
                            leading=10, alignment=TA_CENTER)
    header = ParagraphStyle('seat-header', fontName='EnvelopeHebrewBold', fontSize=12,
                            leading=14, alignment=TA_CENTER)
    title = f'חדר {room}  |  חדר בחינה {physical_room}'
    teacher = Table([[_p(title, header)]], colWidths=[86 * mm], rowHeights=[15 * mm])
    teacher.setStyle(TableStyle([('GRID',(0,0),(-1,-1),1.2,colors.black),('VALIGN',(0,0),(-1,-1),'MIDDLE')]))
    tw, th = teacher.wrapOn(canvas, width, height)
    teacher.drawOn(canvas, (width - tw) / 2, height - 22 * mm - th)

    table_width = 61 * mm
    gap = 9 * mm
    left = (width - (4 * table_width + 3 * gap)) / 2
    top = height - 48 * mm
    seat_height = 22 * mm
    row_gap = 8 * mm
    # Display columns from right to left: 1 is the right wall and 8 the left wall.
    for row in range(ROWS):
        y = top - row * (seat_height + row_gap) - seat_height
        for pair in range(4):
            visual_pair = 3 - pair
            x = left + visual_pair * (table_width + gap)
            first = row * 8 + pair * 2
            data = [[_seat_text(arranged[first + 1], normal), _seat_text(arranged[first], normal)]]
            desk = Table(data, colWidths=[table_width / 2] * 2, rowHeights=[seat_height])
            desk.setStyle(TableStyle([('GRID',(0,0),(-1,-1),1,colors.HexColor('#222222')),
                                      ('VALIGN',(0,0),(-1,-1),'MIDDLE'),('ALIGN',(0,0),(-1,-1),'CENTER'),
                                      ('LEFTPADDING',(0,0),(-1,-1),2),('RIGHTPADDING',(0,0),(-1,-1),2)]))
            desk.wrapOn(canvas, table_width, seat_height);desk.drawOn(canvas, x, y)
    canvas.showPage();canvas.save()
    value = output.getvalue()
    if not value.startswith(b'%PDF-') or len(value) < 1000:
        raise ValueError(f'יצירת PDF לחדר {room} נכשלה.')
    return value


def create_seating_plans(book, result, room_labels, font_base):
    labels = _validate_room_labels(result, room_labels)
    assignments = result.get('assignments') or {}
    excluded = {'מצומצם 1', 'מצומצם 2', 'נפרד'}
    eligible = [room for room in result.get('rooms', []) if room.get('kind') not in excluded]
    if not eligible: raise ValueError('לא נמצאו חדרים רגילים להפקת סידור מקומות.')
    by_room = {int(room['room']): [] for room in eligible}
    for student in book.get('participants', []):
        room = assignments.get(student['row'])
        if room in by_room: by_room[int(room)].append(student)
    reports = {}
    details = []
    for room in sorted(by_room):
        arranged = arrange_room(by_room[room])
        safe_label = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', labels[room])[:40]
        filename = f'room_{room:02d}_{safe_label}.pdf'
        reports[filename] = _room_pdf(room, labels[room], arranged, font_base)
        details.append({'room': room, 'physicalRoom': labels[room], 'students': len(by_room[room]),
                        'units': dict(Counter(student['unit'] for student in by_room[room]))})
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as target:
        for filename, data in reports.items(): target.writestr(filename, data)
    return archive.getvalue(), reports, {'rooms': len(reports),
                                         'students': sum(len(items) for items in by_room.values()),
                                         'files': list(reports), 'details': details}
