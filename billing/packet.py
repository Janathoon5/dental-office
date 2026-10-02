"""Builds a single appeal-packet PDF for a claim denial: the letter on the
office letterhead, a claim summary, selected clinical notes and X-rays, and a
copy of the insurer's letter — everything the insurer needs in one file."""
import io
import re
from html import escape
from pathlib import Path

from PIL import Image as PILImage
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter as LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable, Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from clinical.teeth import parse_teeth
from imaging.models import DentalImage
from dental_office.templatetags.office import money

NAVY = colors.HexColor('#1a3a5c')
STYLES = {
    'office': ParagraphStyle('office', fontName='Times-Bold', fontSize=18, leading=22, textColor=NAVY),
    'office_details': ParagraphStyle('office_details', fontName='Times-Roman', fontSize=9.5, leading=12, textColor=colors.HexColor('#444444')),
    'body': ParagraphStyle('body', fontName='Times-Roman', fontSize=11.5, leading=15.5, spaceAfter=9),
    'h1': ParagraphStyle('h1', fontName='Helvetica-Bold', fontSize=15, leading=19, textColor=NAVY, spaceAfter=10),
    'h2': ParagraphStyle('h2', fontName='Helvetica-Bold', fontSize=11.5, leading=15, spaceBefore=8, spaceAfter=4),
    'small': ParagraphStyle('small', fontName='Helvetica', fontSize=9.5, leading=13),
    'cell': ParagraphStyle('cell', fontName='Helvetica', fontSize=9, leading=11.5),
}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
CLOSING_RE = re.compile(r'^(sincerely|respectfully|regards|best regards|kind regards|thank you)[^\n]{0,20},$', re.I)


def _p(text, style='body'):
    """Paragraph from plain text: escaped, newlines kept, and characters the
    built-in PDF fonts can't draw swapped for '?' rather than blank boxes."""
    text = (text or '').encode('cp1252', errors='replace').decode('cp1252')
    return Paragraph(escape(text).replace('\n', '<br/>'), STYLES[style])


def packet_options(denial):
    """Clinical records and images staff can include. Items that match the
    denied teeth or dates of service start out ticked."""
    invoice = denial.invoice
    patient = invoice.patient
    teeth, dates = set(), set()
    for line in invoice.line_items.all():
        teeth |= parse_teeth(line.tooth_number)
        dates.add(line.service_date)
    if invoice.appointment:
        dates.add(invoice.appointment.date)
    linked = getattr(invoice.appointment, 'treatment_record', None) if invoice.appointment else None

    records = []
    for r in patient.treatment_records.select_related('dentist').order_by('-date')[:50]:
        matches = bool(parse_teeth(r.tooth_number) & teeth) or r.date in dates or (linked and r.pk == linked.pk)
        records.append({'obj': r, 'selected': matches})

    images = []
    for img in DentalImage.objects.filter(patient=patient).order_by('-captured_date')[:50]:
        images.append({'obj': img, 'selected': bool(parse_teeth(img.tooth_number) & teeth)})
    return records, images


def _letter_section(denial, office):
    story = [
        _p(office.office_name or '[OFFICE NAME]', 'office'),
        _p('\n'.join(filter(None, [
            office.address or '[OFFICE ADDRESS]',
            ' · '.join(filter(None, [f'Phone: {office.phone}' if office.phone else '', office.email])),
            ' · '.join(filter(None, [f'NPI: {office.npi}' if office.npi else '', f'TIN: {office.tax_id}' if office.tax_id else ''])),
        ])), 'office_details'),
        Spacer(1, 4),
        HRFlowable(width='100%', thickness=1.5, color=NAVY, spaceAfter=16),
    ]
    # Paragraphs are separated by blank lines; extra blank lines (e.g. room
    # left for a signature) become extra space instead of being collapsed.
    parts = re.split(r'(\n[ \t]*\n(?:[ \t]*\n)*)', (denial.appeal_letter or '').replace('\r\n', '\n').strip())
    after_closing = False
    for i, part in enumerate(parts):
        if i % 2:  # separator
            extra_blank_lines = part.count('\n') - 2
            if extra_blank_lines > 0 and not after_closing:
                story.append(Spacer(1, extra_blank_lines * 12))
            continue
        lines = part.strip('\n').split('\n')
        after_closing = bool(CLOSING_RE.match(lines[0].strip()))
        if after_closing:
            # "Sincerely," always gets room for a signature before the name.
            story += [_p(lines[0]), Spacer(1, 0.45 * inch)]
            lines = lines[1:]
        if any(line.strip() for line in lines):
            story.append(_p('\n'.join(lines)))
    return story


def _table(rows, col_widths, header=True):
    data = [[_p(str(c), 'cell') for c in row] for row in rows]
    table = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#999999')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]
    if header:
        style.append(('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e9eef4')))
    else:
        style.append(('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e9eef4')))
    table.setStyle(TableStyle(style))
    return table


def _summary_section(denial):
    invoice, patient = denial.invoice, denial.invoice.patient
    story = [_p('Claim Summary', 'h1'), _table([
        ['Patient', patient.full_name()],
        ['Date of birth', patient.date_of_birth.strftime('%m/%d/%Y')],
        ['Insurance', patient.insurance_provider or '—'],
        ['Member ID', patient.insurance_id or '—'],
        ['Insurer on denial', denial.insurer_name or '—'],
        ['Claim number', denial.claim_number or '—'],
        ['Denial codes', denial.denial_codes or '—'],
        ['Amount denied', money(denial.amount_denied) if denial.amount_denied is not None else '—'],
    ], [1.8 * inch, 4.9 * inch], header=False)]

    lines = list(invoice.line_items.all())
    story.append(_p('Procedures', 'h2'))
    if lines:
        rows = [['Date', 'Code', 'Tooth', 'Surf.', 'Description', 'Fee']]
        rows += [[l.service_date.strftime('%m/%d/%Y'), l.cdt_code, l.tooth_number or '—', l.surfaces or '—',
                  l.description, money(l.fee)] for l in lines]
        story.append(_table(rows, [0.9 * inch, 0.65 * inch, 0.55 * inch, 0.55 * inch, 3.15 * inch, 0.9 * inch]))
    else:
        story.append(_p(f'Total billed: {money(invoice.subtotal)}', 'small'))
    return story


def _notes_section(records):
    story = [_p('Clinical Notes', 'h1')]
    for r in records:
        heading = f'{r.date.strftime("%m/%d/%Y")} — {r.procedure}'
        if r.tooth_number:
            heading += f', tooth {r.tooth_number}'
        byline = f'Treating dentist: {r.dentist.get_full_name()}' if r.dentist else ''
        story.append(KeepTogether([
            _p(heading, 'h2'),
            *([_p(byline, 'small')] if byline else []),
            Spacer(1, 3),
            _p(r.notes or 'No notes recorded.'),
        ]))
    return story


def _image_flowable(data, max_w=7 * inch, max_h=7.6 * inch):
    with PILImage.open(io.BytesIO(data)) as im:
        w, h = im.size
        if im.format not in ('JPEG', 'PNG'):  # e.g. WEBP/GIF: re-encode for the PDF
            buf = io.BytesIO()
            im.convert('RGB').save(buf, 'PNG')
            data = buf.getvalue()
    scale = min(max_w / w, max_h / h)  # fill the page area, keeping proportions
    return Image(io.BytesIO(data), width=w * scale, height=h * scale)


def _image_page(title, data, subtitle=''):
    story = [_p(title, 'h1')]
    if subtitle:
        story.append(_p(subtitle, 'small'))
        story.append(Spacer(1, 6))
    try:
        story.append(_image_flowable(data))
    except Exception:
        story.append(_p('This image could not be added to the PDF. Please attach it separately.', 'small'))
    return story


def _read_file(field_file):
    with field_file.open('rb') as f:
        return f.read()


def build_packet(denial, office, records, images, include_summary=True, include_original=True):
    """Returns the packet as PDF bytes."""
    patient = denial.invoice.patient
    footer = f'{patient.full_name()} · DOB {patient.date_of_birth.strftime("%m/%d/%Y")}'
    if denial.claim_number:
        footer += f' · Claim {denial.claim_number}'

    original_pdf = None
    original_image = None
    original_note = ''
    if include_original:
        ext = Path(denial.letter.name).suffix.lower()
        try:
            data = _read_file(denial.letter)
            if ext == '.pdf':
                original_pdf = PdfReader(io.BytesIO(data))
                len(original_pdf.pages)  # fail now, not after the rest is built
            elif ext in IMAGE_EXTENSIONS:
                original_image = data
        except Exception:
            original_pdf = original_image = None
            original_note = "The insurer's original letter could not be added. Please attach a copy separately."

    story = _letter_section(denial, office)
    if include_summary:
        story += [PageBreak(), *_summary_section(denial)]
    if records:
        story += [PageBreak(), *_notes_section(records)]
    for img in images:
        subtitle = ', '.join(filter(None, [
            f'Tooth {img.tooth_number}' if img.tooth_number else '',
            f'Taken {img.captured_date.strftime("%m/%d/%Y")}',
        ]))
        if img.caption:
            subtitle += f'. {img.caption}'
        try:
            data = _read_file(img.image)
        except Exception:
            data = b''
        story += [PageBreak(), *_image_page(img.get_image_type_display(), data, subtitle)]
    if original_image:
        story += [PageBreak(), *_image_page("Copy of Insurer's Letter", original_image)]
    if original_note:
        story += [PageBreak(), _p("Copy of Insurer's Letter", 'h1'), _p(original_note)]

    def draw_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#666666'))
        canvas.drawString(0.75 * inch, 0.5 * inch, footer.encode('cp1252', errors='replace').decode('cp1252'))
        canvas.drawRightString(LETTER[0] - 0.75 * inch, 0.5 * inch, f'Page {doc.page}')
        canvas.restoreState()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=LETTER, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                            topMargin=0.75 * inch, bottomMargin=0.85 * inch,
                            title=f'Appeal packet — {patient.full_name()}')
    doc.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)

    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(buffer.getvalue())))
    if original_pdf is not None:
        writer.append(original_pdf)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
