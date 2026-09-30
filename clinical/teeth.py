"""Tooth chart data: names, SVG geometry, and per-tooth history for the
32 adult teeth in Universal numbering (1 = upper right third molar, going
across the top to 16, then 17 = lower left third molar back around to 32)."""
import re

from .models import ToothCondition

# Order from the back of the mouth to the front, for teeth 1-8 and 17-24.
# Teeth 9-16 and 25-32 are the same list mirrored.
_QUADRANT = [
    ('molar', 'third molar'), ('molar', 'second molar'), ('molar', 'first molar'),
    ('premolar', 'second premolar'), ('premolar', 'first premolar'),
    ('canine', 'canine'), ('incisor', 'lateral incisor'), ('incisor', 'central incisor'),
]
_WIDTHS = {'molar': 44, 'premolar': 36, 'canine': 32, 'incisor': 30}
_GAP = 4
_MARGIN = 12
TOOTH_HEIGHT = 90
UPPER_Y = 8
LOWER_Y = 156
CHART_HEIGHT = 252

CONDITION_COLORS = {
    'decay': '#e5484d',
    'filling': '#3e7bfa',
    'crown': '#e0a526',
    'root_canal': '#ffffff',
    'implant': '#cfd6de',
    'bridge': '#8e6cd8',
    'missing': 'none',
    'watch': '#ffffff',
}


def tooth_info(number):
    """(kind, full name) for a Universal tooth number."""
    if number <= 8:
        kind, name = _QUADRANT[number - 1]
        side = 'Upper right'
    elif number <= 16:
        kind, name = _QUADRANT[16 - number]
        side = 'Upper left'
    elif number <= 24:
        kind, name = _QUADRANT[number - 17]
        side = 'Lower left'
    else:
        kind, name = _QUADRANT[32 - number]
        side = 'Lower right'
    return kind, f'{side} {name}'


def parse_teeth(text):
    """Tooth numbers mentioned in a free-text tooth field, e.g. "14",
    "#3, #4", or "18-20". Anything outside 1-32 is ignored."""
    numbers = set()
    text = text or ''
    for start, end in re.findall(r'(\d+)\s*-\s*(\d+)', text):
        start, end = int(start), int(end)
        if start <= end and end - start < 32:
            numbers.update(range(start, end + 1))
    numbers.update(int(n) for n in re.findall(r'\d+', text))
    return {n for n in numbers if 1 <= n <= 32}


def _geometry(kind, x, upper):
    """SVG path/shape coordinates for one tooth. Drawn roots-up for the top
    row; the bottom row is the same shape mirrored vertically."""
    w = _WIDTHS[kind]
    y0 = UPPER_Y if upper else LOWER_Y

    def fy(v):  # v runs 0 (root tip) -> 90 (biting edge) for an upper tooth
        return round(y0 + v if upper else y0 + TOOTH_HEIGHT - v, 1)

    def px(f):
        return round(x + f * w, 1)

    if kind == 'molar':
        root = (f'M{px(.12)},{fy(50)} Q{px(.18)},{fy(6)} {px(.3)},{fy(4)} '
                f'Q{px(.42)},{fy(20)} {px(.5)},{fy(28)} Q{px(.58)},{fy(20)} {px(.7)},{fy(4)} '
                f'Q{px(.82)},{fy(6)} {px(.88)},{fy(50)} Z')
    else:
        root = (f'M{px(.22)},{fy(50)} Q{px(.3)},{fy(4)} {px(.5)},{fy(2)} '
                f'Q{px(.7)},{fy(4)} {px(.78)},{fy(50)} Z')
    crown_top, crown_bottom = sorted([fy(44), fy(90)])
    return {
        'x': x, 'w': w, 'x2': x + w,
        'root_path': root,
        'crown_y': crown_top,
        'crown_h': round(crown_bottom - crown_top, 1),
        'crown_y2': crown_bottom,
        'crown_rx': 7 if kind == 'molar' else 10,
        'cx': px(.5),
        'canal_y1': fy(10), 'canal_y2': fy(52),
        'label_y': 118 if upper else 148,
        'planned_cy': 114 if upper else 144,
        'hit_y': 4 if upper else 136,
    }


def chart_width():
    return _MARGIN * 2 + sum(_WIDTHS[k] for k, _ in _QUADRANT) * 2 + _GAP * 15


def build_chart(patient):
    """Everything the chart template needs, one dict per tooth, plus the two
    rows in display order (upper 1-16, lower 32-17 so teeth line up)."""
    from .models import TreatmentPlanItem

    conditions = {c.tooth_number: c for c in ToothCondition.objects.filter(patient=patient)}

    records = {}
    for record in patient.treatment_records.select_related('dentist').order_by('-date'):
        for n in parse_teeth(record.tooth_number):
            records.setdefault(n, []).append(record)

    planned = {}
    for item in TreatmentPlanItem.objects.filter(
        plan__patient=patient, plan__is_active=True, status='pending',
    ).exclude(plan__status='completed').select_related('plan'):
        for n in parse_teeth(item.tooth_number):
            planned.setdefault(n, []).append(item)

    teeth = {}
    for row, numbers in (('upper', range(1, 17)), ('lower', range(32, 16, -1))):
        x = _MARGIN
        for n in numbers:
            kind, name = tooth_info(n)
            geo = _geometry(kind, x, upper=(row == 'upper'))
            x += geo['w'] + _GAP
            condition = conditions.get(n)
            teeth[n] = {
                'number': n,
                'name': name,
                'condition': condition,
                'code': condition.condition if condition else 'healthy',
                'fill': CONDITION_COLORS[condition.condition] if condition else '#ffffff',
                'records': records.get(n, []),
                'planned': planned.get(n, []),
                **geo,
            }

    return {
        'upper': [teeth[n] for n in range(1, 17)],
        'lower': [teeth[n] for n in range(32, 16, -1)],
        'all': [teeth[n] for n in range(1, 33)],
        'width': chart_width(),
        'height': CHART_HEIGHT,
        'midline_x': teeth[8]['x'] + teeth[8]['w'] + _GAP / 2,
        'counts': {
            'charted': len(conditions),
            'planned': len(planned),
        },
    }
