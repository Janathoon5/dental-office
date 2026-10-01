"""Generated files for the demo practice: X-ray-looking images and insurer
denial letters (EOBs). Everything is drawn from scratch, so no real patient
image or document is ever involved."""
import io
import random

from PIL import Image, ImageDraw, ImageFilter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas


def _tooth(draw, x, y, w, h, upper, rng, filling=False, crown=False, canal=False):
    """A crown plus root(s); upper teeth have roots pointing up."""
    crown_h = h * 0.42
    shade = rng.randint(175, 205)
    if upper:
        crown_box = (x, y + h - crown_h, x + w, y + h)
        root_top, root_bottom = y, y + h - crown_h + 6
    else:
        crown_box = (x, y, x + w, y + crown_h)
        root_top, root_bottom = y + crown_h - 6, y + h
    roots = 2 if w > 60 else 1
    for i in range(roots):
        rx = x + w * (0.3 + 0.4 * i if roots == 2 else 0.5)
        tip = root_top if upper else root_bottom
        base = root_bottom if upper else root_top
        draw.polygon([(rx - w * 0.16, base), (rx + w * 0.16, base), (rx + w * 0.04, tip), (rx - w * 0.04, tip)],
                     fill=shade - 35)
        if canal:
            draw.line([(rx, base), (rx, tip + (8 if upper else -8))], fill=250, width=4)
    draw.rounded_rectangle(crown_box, radius=w * 0.25, fill=shade)
    if crown:
        draw.rounded_rectangle(crown_box, radius=w * 0.25, fill=248)
    elif filling:
        cx0, cy0, cx1, cy1 = crown_box
        draw.ellipse((cx0 + w * 0.25, cy0 + crown_h * 0.25, cx1 - w * 0.25, cy1 - crown_h * 0.25), fill=250)


def make_xray(kind='pa', seed=0, crown=False, filling=False, canal=False):
    """PNG bytes of a fake radiograph: 'pa' (periapical), 'bw' (bitewing) or 'pano'."""
    rng = random.Random(seed)
    size = {'pa': (480, 640), 'bw': (720, 520), 'pano': (1400, 640)}[kind]
    img = Image.new('L', size, 18)
    draw = ImageDraw.Draw(img)
    w, h = size
    if kind == 'pa':
        _tooth(draw, w * 0.3, h * 0.12, w * 0.4, h * 0.75, upper=rng.random() < 0.5, rng=rng,
               crown=crown, filling=filling, canal=canal)
        _tooth(draw, w * 0.02, h * 0.15, w * 0.24, h * 0.7, upper=False, rng=rng)
        _tooth(draw, w * 0.74, h * 0.15, w * 0.24, h * 0.7, upper=False, rng=rng)
    elif kind == 'bw':
        for i in range(4):
            x = 20 + i * (w - 40) / 4
            _tooth(draw, x + 6, 10, (w - 40) / 4 - 12, h * 0.48, upper=True, rng=rng,
                   filling=filling and i == 1, crown=crown and i == 2)
            _tooth(draw, x + 6, h * 0.52, (w - 40) / 4 - 12, h * 0.46, upper=False, rng=rng)
    else:
        for row, upper in ((0, True), (1, False)):
            for i in range(14):
                tw = (w - 120) / 14
                x = 60 + i * tw
                curve = abs(i - 6.5) * 6
                y = (40 + curve) if upper else (h / 2 + 10 - curve * 0.4)
                if not (row == 1 and i == 11):  # leave a gap: a missing lower molar
                    _tooth(draw, x + 4, y, tw - 8, h * 0.42, upper=upper, rng=rng)
    noise = Image.effect_noise(size, 18).point(lambda v: v // 6)
    img = Image.blend(img.filter(ImageFilter.GaussianBlur(2.2)), noise, 0.18)
    buf = io.BytesIO()
    img.save(buf, 'PNG')
    return buf.getvalue()


def make_eob(insurer, insurer_address, letter_date, office, patient, member_id, group, claim_number,
             received, lines, remarks, amount_denied, closing):
    """PDF bytes of an insurer's Explanation of Benefits / denial notice."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    width, height = letter
    left, y = 0.8 * inch, height - 0.8 * inch

    c.setFillColor(colors.HexColor('#0b4a7a'))
    c.setFont('Helvetica-Bold', 17)
    c.drawString(left, y, insurer.upper())
    c.setFillColor(colors.HexColor('#555555'))
    c.setFont('Helvetica', 8.5)
    c.drawString(left, y - 13, insurer_address)
    c.setFillColor(colors.black)

    y -= 44
    c.setFont('Helvetica', 10.5)
    for text in [letter_date.strftime('%B %d, %Y'), '', office.office_name, *office.address.splitlines()]:
        c.drawString(left, y, text)
        y -= 14

    y -= 10
    c.setFont('Helvetica-Bold', 12.5)
    c.drawString(left, y, 'EXPLANATION OF BENEFITS - CLAIM DENIAL')
    y -= 22
    c.setFont('Helvetica', 10.5)
    c.drawString(left, y, f'Subscriber/Patient: {patient.full_name()}    DOB: {patient.date_of_birth:%m/%d/%Y}')
    c.drawString(left, y - 14, f'Member ID: {member_id}    Group: {group}')
    c.drawString(left, y - 28, f'Claim Number: {claim_number}    Date Received: {received:%m/%d/%Y}')

    y -= 54
    headers = ['Date', 'Code', 'Tooth', 'Description', 'Billed', 'Paid', 'Remark']
    xs = [left, left + 70, left + 120, left + 165, left + 345, left + 405, left + 450]
    c.setFillColor(colors.HexColor('#e9eef4'))
    c.rect(left - 4, y - 5, width - 2 * left + 8, 17, fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.setFont('Helvetica-Bold', 9)
    for x, t in zip(xs, headers):
        c.drawString(x, y, t)
    c.setFont('Helvetica', 9)
    for dos, code, tooth, desc, billed, remark in lines:
        y -= 17
        for x, t in zip(xs, [dos.strftime('%m/%d/%Y'), code, tooth or '-', desc[:32], f'${billed:,.2f}', '$0.00', remark]):
            c.drawString(x, y, t)

    y -= 30
    c.setFont('Helvetica', 10)
    text = c.beginText(left, y)
    text.setLeading(13.5)
    for paragraph in [*remarks, f'Amount denied: ${amount_denied:,.2f} (plan benefit).', closing]:
        line = ''
        for word in paragraph.split():
            if c.stringWidth(line + ' ' + word, 'Helvetica', 10) > width - 2 * left:
                text.textLine(line)
                line = word
            else:
                line = f'{line} {word}'.strip()
        text.textLine(line)
        text.textLine('')
    c.drawText(text)

    c.setFont('Helvetica', 7.5)
    c.setFillColor(colors.HexColor('#888888'))
    c.drawString(left, 0.6 * inch, 'SAMPLE DOCUMENT FOR SOFTWARE DEMONSTRATION - FICTIONAL PATIENT AND INSURER.')
    c.showPage()
    c.save()
    return buf.getvalue()
