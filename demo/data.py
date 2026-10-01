"""The demo practice: a fictional office with about 20 patients, a full
schedule, charts, plans, invoices, X-rays, messages and analyzed insurance
denials, all dated relative to today so the demo always looks current.

reset_demo_practice() wipes every patient and the clinical/billing data
around them, then rebuilds it. It only runs when DEMO_MODE is on (or when
forced), because on a real practice it would destroy patient records.
"""
import datetime
import random
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from appointments.models import Appointment, AppointmentRequest, RecallNotice, ReminderLog
from billing.models import ClaimDenial, Invoice, InvoiceLineItem, OfficeSettings, Payment
from clinical.models import ToothCondition, TreatmentPlan, TreatmentPlanItem, TreatmentRecord
from imaging.models import DentalImage
from inventory.models import SupplyItem
from messaging.models import Conversation, Message
from patients.models import MedicalAlert, Patient
from staff.models import StaffProfile

from .files import make_eob, make_xray

# Demo logins, keyed by the role shown on the login page.
DEMO_USERS = {
    'dentist': ('demo-dentist', 'Elena', 'Park', 'dentist'),
    'hygienist': ('demo-hygienist', 'Marcus', 'Reed', 'hygienist'),
    'frontdesk': ('demo-frontdesk', 'Sofia', 'Alvarez', 'receptionist'),
    'patient': ('demo-patient', 'Maria', 'Lopez', None),
}

INSURERS = {
    'sunrise': ('Sunrise Dental Insurance', 'P.O. Box 4410, Tempe, AZ 85280 · Provider Services 1-800-555-0142'),
    'harbor': ('Harborview Dental PPO', 'P.O. Box 7720, Columbus, OH 43215 · Provider Line 1-800-555-0168'),
    'summit': ('Summit Benefit Dental', 'P.O. Box 3301, Denver, CO 80202 · Claims 1-800-555-0191'),
    'keystone': ('Keystone Dental Plan', 'P.O. Box 9050, Harrisburg, PA 17105 · Claims 1-800-555-0117'),
}

# first, last, date of birth, insurer key, member ID, recall months
PATIENTS = [
    ('Maria', 'Lopez', '1985-03-02', 'sunrise', 'SDI-448812', 6),
    ('James', 'Carter', '1971-07-19', 'harbor', 'HDP-200471', 3),
    ('Priya', 'Shah', '1992-11-08', 'summit', 'SBD-77310', 6),
    ('David', 'Kim', '1964-02-27', 'keystone', 'KDP-551902', 6),
    ('Emily', 'Johnson', '2010-05-14', 'sunrise', 'SDI-660124', 6),
    ('Robert', 'Brown', '1958-09-03', 'harbor', 'HDP-118830', 6),
    ('Aisha', 'Mohammed', '1988-01-22', 'summit', 'SBD-40218', 6),
    ('Carlos', 'Rivera', '1979-12-11', 'keystone', 'KDP-308817', 6),
    ('Linda', 'Nguyen', '1966-06-30', 'sunrise', 'SDI-902216', 6),
    ('Tom', 'Becker', '1990-04-04', 'harbor', 'HDP-733001', 6),
    ('Grace', 'Chen', '1983-08-17', 'summit', 'SBD-61904', 6),
    ('Michael', 'Ross', '1975-10-25', 'keystone', 'KDP-420661', 6),
    ('Hannah', 'Lee', '1996-02-09', 'sunrise', 'SDI-310558', 6),
    ('Owen', 'Patel', '2014-09-21', 'harbor', 'HDP-559120', 6),
    ('Zoe', 'Martinez', '2001-12-30', 'summit', 'SBD-88207', 6),
    ('Ben', 'Wright', '1969-03-15', 'keystone', 'KDP-116045', 6),
    ('Nora', 'Kelly', '1954-07-07', 'sunrise', 'SDI-771930', 4),
    ('Lucas', 'Silva', '1987-05-28', 'harbor', 'HDP-402276', 6),
    ('Ava', 'Thompson', '1999-01-12', 'summit', 'SBD-25541', 6),
    ('Ethan', 'Cole', '1981-11-03', 'keystone', 'KDP-690388', 12),
]

# Days since each patient's last completed cleaning (None = never), which
# drives the Recalls page: overdue, due soon, and on track.
LAST_CLEANING = {
    'Maria': 160, 'James': 125, 'Priya': 60, 'David': 95, 'Emily': 170, 'Robert': 40,
    'Aisha': 110, 'Carlos': 200, 'Linda': 245, 'Tom': None, 'Grace': 30, 'Michael': 175,
    'Hannah': 168, 'Owen': 80, 'Zoe': 210, 'Ben': 230, 'Nora': 100, 'Lucas': 45, 'Ava': 15, 'Ethan': 300,
}

ALERTS = {
    'Maria': [('condition', 'medium', 'Bruxism (grinds teeth at night)')],
    'James': [('condition', 'high', 'Type 2 diabetes'), ('medication', 'medium', 'Metformin 1000 mg daily')],
    'Robert': [('allergy', 'high', 'Penicillin: hives and swelling'), ('medication', 'high', 'Warfarin (blood thinner)')],
    'Aisha': [('condition', 'medium', 'Pregnant, second trimester')],
    'Nora': [('condition', 'medium', 'Heart murmur; check with physician before invasive work'),
             ('medication', 'medium', 'Lisinopril (blood pressure)')],
    'Carlos': [('allergy', 'low', 'Latex: mild skin irritation')],
}

TOOTH_CHARTS = {
    'Maria': [(14, 'crown', 'Porcelain crown, seated after cusp fracture'), (3, 'filling', 'MO composite'),
              (19, 'root_canal', 'RCT 2022, crowned elsewhere'), (30, 'filling', 'DO amalgam'), (1, 'missing', ''),
              (16, 'missing', ''), (17, 'missing', ''), (32, 'missing', '')],
    'James': [(2, 'watch', '5-6 mm pockets'), (3, 'watch', '5 mm pockets, bleeding on probing'), (14, 'watch', '5 mm pockets'),
              (18, 'filling', 'Occlusal composite'), (31, 'crown', 'PFM crown')],
    'Priya': [(30, 'filling', 'MO composite (new)'), (19, 'decay', 'Small occlusal lesion, monitor or restore')],
    'David': [(19, 'missing', 'Extracted 2025; implant planned'), (30, 'implant', 'Implant crown 2021'),
              (3, 'crown', 'Gold crown'), (14, 'crown', 'PFM crown'), (2, 'filling', 'MOD amalgam')],
    'Robert': [(30, 'root_canal', 'RCT needed, see plan'), (31, 'crown', 'PFM'), (18, 'crown', 'PFM'),
               (8, 'filling', 'Facial composite'), (9, 'filling', 'Mesial composite'), (1, 'missing', ''), (16, 'missing', '')],
    'Linda': [(12, 'bridge', '3-unit bridge 11-13'), (11, 'bridge', 'Bridge abutment'), (13, 'bridge', 'Bridge abutment'),
              (20, 'decay', 'Distal decay')],
    'Michael': [(15, 'decay', 'Mesial lesion on bitewings'), (4, 'watch', 'Craze lines')],
}


def _days(n):
    return timezone.localdate() + datetime.timedelta(days=n)


def _time(h, m=0):
    return datetime.time(h, m)


def wipe():
    """Delete all patients and the records around them, demo logins, and
    patient-portal accounts. Staff and admin accounts are kept. Returns the
    stored files that belonged to the deleted records, for deleting once the
    whole reset has committed."""
    old_files = [(img.image.storage, img.image.name) for img in DentalImage.all_objects.all() if img.image]
    old_files += [(d.letter.storage, d.letter.name) for d in ClaimDenial.all_objects.all() if d.letter]
    # Queryset deletes are real deletes (soft delete only overrides
    # instance.delete()), and cascade through everything tied to a patient.
    Patient.all_objects.all().delete()
    AppointmentRequest.objects.all().delete()
    SupplyItem.objects.all().delete()
    demo_names = [u[0] for u in DEMO_USERS.values()]
    User.objects.filter(username__in=demo_names).delete()
    User.objects.filter(groups__name='Patient', is_superuser=False, is_staff=False,
                        staff_profile__isnull=True).delete()
    return old_files


def _create_users():
    users = {}
    for role, (username, first, last, staff_role) in DEMO_USERS.items():
        user = User.objects.create(username=username, first_name=first, last_name=last,
                                   email=f'{username}@example.com')
        user.set_unusable_password()  # demo logins only work through the demo buttons
        user.save()
        if staff_role:
            StaffProfile.objects.create(user=user, role=staff_role)
        else:
            user.groups.add(Group.objects.get_or_create(name='Patient')[0])
        users[role] = user
    return users


def _office():
    office = OfficeSettings.load()
    office.office_name = 'Bright Smiles Dental'
    office.address = '123 Main St\nSpringfield, IL 62701'
    office.phone = '(555) 010-4567'
    office.email = 'office@example.com'
    office.dentist_name = 'Dr. Elena Park, DDS'
    office.npi = '0000000000'
    office.tax_id = '00-0000000'
    office.save()
    return office


def _image(patient, kind, days_ago, tooth, caption, uploader, seed, **drawing):
    data = make_xray(kind, seed=seed, **drawing)
    return DentalImage.objects.create(
        patient=patient, image_type='xray', captured_date=_days(-days_ago), tooth_number=tooth,
        caption=caption, uploaded_by=uploader,
        image=ContentFile(data, name=f'demo-{patient.last_name.lower()}-{kind}-{seed}.png'),
    )


def _invoice(patient, appt, lines, insurance, status='pending', paid=None, notes=''):
    invoice = Invoice.objects.create(patient=patient, appointment=appt, subtotal=0,
                                     insurance_amount=Decimal(insurance), status=status, notes=notes)
    Invoice.all_objects.filter(pk=invoice.pk).update(date_issued=appt.date)
    for code, desc, tooth, surfaces, fee in lines:
        InvoiceLineItem.objects.create(invoice=invoice, service_date=appt.date, cdt_code=code, description=desc,
                                       tooth_number=tooth, surfaces=surfaces, fee=Decimal(fee))
    invoice.recalculate_subtotal()
    if paid:
        Payment.objects.create(invoice=invoice, amount=Decimal(paid), method='card')
    return invoice


@transaction.atomic
def build():
    """Create the demo practice. Assumes wipe() has run."""
    rng = random.Random(2026)
    users = _create_users()
    dr, hyg, desk = users['dentist'], users['hygienist'], users['frontdesk']
    office = _office()

    patients = {}
    for first, last, dob, insurer, member_id, recall in PATIENTS:
        patients[first] = Patient.objects.create(
            first_name=first, last_name=last, date_of_birth=datetime.date.fromisoformat(dob),
            phone=f'(555) 01{rng.randint(0, 9)}-{rng.randint(1000, 9999)}',
            email=f'{first.lower()}.{last.lower()}@example.com',
            address=f'{rng.randint(100, 999)} {rng.choice(["Oak", "Maple", "Cedar", "Elm", "Pine"])} St\nSpringfield, IL 62701',
            insurance_provider=INSURERS[insurer][0], insurance_id=member_id, recall_interval_months=recall,
        )
    maria = patients['Maria']
    maria.user = users['patient']
    maria.save(update_fields=['user'])

    for name, alerts in ALERTS.items():
        for alert_type, severity, description in alerts:
            MedicalAlert.objects.create(patient=patients[name], alert_type=alert_type, severity=severity,
                                        description=description)
    for name, chart in TOOTH_CHARTS.items():
        for tooth, condition, notes in chart:
            ToothCondition.objects.create(patient=patients[name], tooth_number=tooth, condition=condition,
                                          notes=notes, updated_by=dr)

    # Cleaning history: drives the Recalls page.
    for name, days_ago in LAST_CLEANING.items():
        if days_ago is None:
            continue
        for back in (days_ago + 182, days_ago):
            appt = Appointment.objects.create(patient=patients[name], dentist=hyg, date=_days(-back),
                                              start_time=_time(9 + rng.randint(0, 6)), duration_minutes=60,
                                              appointment_type='cleaning', status='completed')
            TreatmentRecord.objects.create(patient=patients[name], appointment=appt, dentist=hyg, date=appt.date,
                                           procedure='Adult cleaning (prophylaxis)',
                                           notes=rng.choice([
                                               'Light calculus, good home care. Reviewed flossing.',
                                               'Moderate plaque lower anteriors. OHI given.',
                                               'Healthy tissue, no bleeding on probing.',
                                           ]))

    # Today's schedule and the next two weeks.
    today_plan = [
        (8, 0, 'Grace', 'checkup', dr, 'scheduled'), (9, 0, 'Maria', 'consultation', dr, 'completed'),
        (9, 0, 'Zoe', 'cleaning', hyg, 'completed'), (10, 30, 'Carlos', 'other', dr, 'scheduled'),
        (11, 0, 'Emily', 'cleaning', hyg, 'scheduled'), (13, 0, 'David', 'consultation', dr, 'scheduled'),
        (14, 0, 'Michael', 'filling', dr, 'scheduled'), (14, 30, 'Hannah', 'cleaning', hyg, 'scheduled'),
        (15, 30, 'Owen', 'checkup', dr, 'scheduled'),
    ]
    for h, m, name, kind, provider, status in today_plan:
        Appointment.objects.create(patient=patients[name], dentist=provider, date=_days(0), start_time=_time(h, m),
                                   duration_minutes=60 if kind != 'other' else 30, appointment_type=kind,
                                   status=status, notes='Toothache, upper right' if name == 'Carlos' else '')
    upcoming = [
        (1, 9, 'Nora', 'cleaning', hyg), (1, 10, 'Robert', 'consultation', dr), (1, 14, 'Ben', 'cleaning', hyg),
        (2, 8, 'Tom', 'consultation', dr), (2, 11, 'Aisha', 'cleaning', hyg), (3, 9, 'James', 'other', hyg),
        (3, 13, 'Priya', 'filling', dr), (6, 15, 'Lucas', 'checkup', dr),
        (7, 9, 'Ethan', 'cleaning', hyg), (8, 14, 'David', 'other', dr), (9, 11, 'Ava', 'checkup', dr),
        (13, 9, 'Maria', 'other', dr),
    ]
    for days, h, name, kind, provider in upcoming:
        Appointment.objects.create(patient=patients[name], dentist=provider, date=_days(days), start_time=_time(h),
                                   duration_minutes=60, appointment_type=kind, status='scheduled',
                                   notes={('David', 'other'): 'Implant placement #19',
                                          ('Maria', 'other'): 'Night guard delivery',
                                          ('James', 'other'): 'SRP lower left and lower right',
                                          ('Tom', 'consultation'): 'New patient exam and X-rays'}.get((name, kind), ''))
    Appointment.objects.create(patient=patients['Lucas'], dentist=dr, date=_days(-6), start_time=_time(10),
                               appointment_type='checkup', status='no_show')
    Appointment.objects.create(patient=patients['Zoe'], dentist=dr, date=_days(-3), start_time=_time(15),
                               appointment_type='consultation', status='cancelled')

    # --- Maria Lopez: crown on #14, denied as "not medically necessary" ---
    crown_visit = Appointment.objects.create(patient=maria, dentist=dr, date=_days(-34), start_time=_time(9),
                                             duration_minutes=90, appointment_type='other', status='completed',
                                             notes='Crown prep #14')
    TreatmentRecord.objects.create(
        patient=maria, appointment=crown_visit, dentist=dr, date=crown_visit.date, procedure='Porcelain crown prep',
        tooth_number='14', notes='Fractured mesiolingual cusp on #14 to the gumline with recurrent decay under a large '
                                 'MOD amalgam. About 50% of coronal structure missing after decay removal. Crown '
                                 'indicated. Patient reports grinding; night guard recommended.')
    _image(maria, 'pa', 48, '14', 'PA #14 pre-op: recurrent decay under distal margin of MOD amalgam', dr, 1, filling=True)
    _image(maria, 'bw', 150, '', 'Bitewings, right and left', hyg, 2, filling=True)
    maria_invoice = _invoice(maria, crown_visit, [
        ('D2740', 'Crown, porcelain/ceramic', '14', '', '1500.00'),
        ('D2950', 'Core buildup', '14', '', '250.00'),
    ], insurance='1150.00', notes='Crown #14, insurance denied; appeal in progress')
    plan = TreatmentPlan.objects.create(patient=maria, title='Restore #14 and protect from grinding', status='in_progress')
    TreatmentPlanItem.objects.create(plan=plan, procedure='Crown, porcelain/ceramic', tooth_number='14',
                                     estimated_cost=Decimal('1500'), status='completed')
    TreatmentPlanItem.objects.create(plan=plan, procedure='Night guard, hard, full arch', tooth_number='',
                                     estimated_cost=Decimal('450'), status='pending')

    # --- James Carter: gum disease, deep cleaning denied ---
    srp_visit = Appointment.objects.create(patient=patients['James'], dentist=hyg, date=_days(-27), start_time=_time(13),
                                           duration_minutes=90, appointment_type='other', status='completed',
                                           notes='SRP upper right and upper left')
    TreatmentRecord.objects.create(
        patient=patients['James'], appointment=srp_visit, dentist=hyg, date=srp_visit.date,
        procedure='Scaling and root planing, UR and UL', tooth_number='2-5, 12-15',
        notes='Generalized 5-6 mm pockets with bleeding on probing in UR and UL, subgingival calculus. Local '
              'anesthetic. Patient is diabetic (A1c 7.9 per physician). Re-evaluate in 6 weeks.')
    _image(patients['James'], 'bw', 40, '', 'Bitewings: horizontal bone loss, subgingival calculus', hyg, 3)
    james_invoice = _invoice(patients['James'], srp_visit, [
        ('D4342', 'Scaling and root planing, 1-3 teeth per quadrant', '2-5', '', '240.00'),
        ('D4342', 'Scaling and root planing, 1-3 teeth per quadrant', '12-15', '', '240.00'),
    ], insurance='384.00')
    perio = TreatmentPlan.objects.create(patient=patients['James'], title='Periodontal therapy', status='in_progress')
    for item, teeth, cost, status in [('Scaling and root planing, UR', '2-5', 240, 'completed'),
                                      ('Scaling and root planing, UL', '12-15', 240, 'completed'),
                                      ('Scaling and root planing, LL', '18-20', 240, 'pending'),
                                      ('Scaling and root planing, LR', '29-31', 240, 'pending')]:
        TreatmentPlanItem.objects.create(plan=perio, procedure=item, tooth_number=teeth,
                                         estimated_cost=Decimal(cost), status=status)

    # --- Priya Shah: filling denied for a missing tooth number ---
    filling_visit = Appointment.objects.create(patient=patients['Priya'], dentist=dr, date=_days(-41), start_time=_time(11),
                                               appointment_type='filling', status='completed')
    TreatmentRecord.objects.create(patient=patients['Priya'], appointment=filling_visit, dentist=dr,
                                   date=filling_visit.date, procedure='Composite filling, MO', tooth_number='30',
                                   notes='Mesial and occlusal decay into dentin on #30. Composite MO placed, '
                                         'occlusion checked. Monitor small occlusal lesion on #19.')
    priya_invoice = _invoice(patients['Priya'], filling_visit, [
        ('D2392', 'Composite filling, back tooth, two surfaces', '30', 'MO', '225.00'),
    ], insurance='180.00', notes='Original claim went out without tooth/surface')

    # --- Robert Brown: root canal and crown planned; earlier denial won on appeal ---
    rb_visit = Appointment.objects.create(patient=patients['Robert'], dentist=dr, date=_days(-75), start_time=_time(10),
                                          appointment_type='extraction', status='completed')
    TreatmentRecord.objects.create(patient=patients['Robert'], appointment=rb_visit, dentist=dr, date=rb_visit.date,
                                   procedure='Surgical extraction', tooth_number='17',
                                   notes='Partially impacted #17, recurrent pericoronitis. INR checked (2.4) with '
                                         'physician clearance. Sutures placed, hemostasis achieved.')
    robert_invoice = _invoice(patients['Robert'], rb_visit, [
        ('D7210', 'Surgical extraction', '17', '', '395.00'),
    ], insurance='316.00', status='paid', paid='79.00')
    _image(patients['Robert'], 'pa', 20, '30', 'PA #30: periapical radiolucency', dr, 4, canal=False)
    rplan = TreatmentPlan.objects.create(patient=patients['Robert'], title='Save #30', status='proposed')
    TreatmentPlanItem.objects.create(plan=rplan, procedure='Root canal, molar', tooth_number='30',
                                     estimated_cost=Decimal('1150'))
    TreatmentPlanItem.objects.create(plan=rplan, procedure='Crown, porcelain/ceramic', tooth_number='30',
                                     estimated_cost=Decimal('1500'))

    # --- David Kim: implant ---
    dplan = TreatmentPlan.objects.create(patient=patients['David'], title='Implant to replace #19', status='accepted')
    for item, cost in [('Implant placement', 3200), ('Implant abutment', 650), ('Implant crown', 1700)]:
        TreatmentPlanItem.objects.create(plan=dplan, procedure=item, tooth_number='19', estimated_cost=Decimal(cost))
    _image(patients['David'], 'pano', 95, '', 'Panoramic: edentulous space #19, adequate bone height', dr, 5)

    # --- Other billing: a few paid and partly paid cleanings and exams ---
    for name, paid_status in [('Grace', 'paid'), ('Ava', 'partial'), ('Lucas', 'pending'), ('Robert', 'paid')]:
        appt = Appointment.objects.filter(patient=patients[name], appointment_type='cleaning',
                                          status='completed').order_by('-date').first()
        if appt and not hasattr(appt, 'invoice'):
            inv = _invoice(patients[name], appt, [
                ('D1110', 'Cleaning, adult', '', '', '125.00'),
                ('D0120', 'Periodic oral exam', '', '', '65.00'),
                ('D0274', 'Bitewing X-rays, four images', '', '', '85.00'),
            ], insurance='220.00', status=paid_status,
                paid={'paid': '55.00', 'partial': '25.00'}.get(paid_status))

    _build_denials(office, maria_invoice, james_invoice, priya_invoice, robert_invoice, dr, desk)

    # Messages between patients and the office.
    for patient, thread in [
        (maria, [(maria.user, 'Hi, I got a letter from my insurance saying my crown was denied. Do I owe the full amount now?', 49),
                 (desk, "Hi Maria, don't worry. We're appealing it with your X-ray and Dr. Park's notes. "
                        "We'll hold your bill until the insurance decides.", 47),
                 (maria.user, "Thank you! Also, can I bring my night guard question to the next visit?", 30)]),
        (patients['Emily'], [(desk, 'Reminder: Emily is due for sealants. Want to add them to her cleaning?', 26)]),
    ]:
        conversation = Conversation.get_or_start_for(patient)
        for sender, body, hours_ago in thread:
            msg = Message.objects.create(conversation=conversation, sender=sender, body=body)
            Message.all_objects.filter(pk=msg.pk).update(sent_at=timezone.now() - datetime.timedelta(hours=hours_ago))

    for first, last, days, hour, kind, note in [
        ('Olivia', 'Grant', 2, 10, 'consultation', 'Chipped front tooth, would like it fixed before a wedding.'),
        ('Henry', 'Walsh', 4, 15, 'checkup', 'New to the area, looking for a family dentist.'),
    ]:
        AppointmentRequest.objects.create(first_name=first, last_name=last, phone='(555) 010-2233',
                                          email=f'{first.lower()}@example.com', preferred_date=_days(days),
                                          preferred_time=_time(hour), appointment_type=kind, message=note)

    for name, category, qty, unit, minimum in [
        ('Lidocaine 2% with epi', 'anesthetics', 4, 'boxes', 5), ('Articaine 4%', 'anesthetics', 9, 'boxes', 4),
        ('Nitrile gloves, medium', 'ppe', 18, 'boxes', 10), ('Nitrile gloves, small', 'ppe', 3, 'boxes', 8),
        ('Level 3 masks', 'ppe', 22, 'boxes', 10), ('Prophy paste, medium grit', 'materials', 6, 'tubs', 3),
        ('Composite A2 syringes', 'materials', 2, 'packs', 4), ('Bonding agent', 'materials', 5, 'bottles', 2),
        ('Saliva ejectors', 'disposables', 30, 'bags', 10), ('Patient bibs', 'disposables', 12, 'cases', 4),
        ('Fluoride varnish', 'medications', 40, 'units', 20), ('Explorers', 'instruments', 14, 'units', 6),
        ('Printer paper', 'office', 7, 'reams', 3),
    ]:
        SupplyItem.objects.create(name=name, category=category, quantity=qty, unit=unit, min_quantity=minimum)

    return {'patients': len(patients), 'users': users}


CROWN_LETTER = """{today}

Sunrise Dental Insurance
Attn: Appeals Department
P.O. Box 4410
Tempe, AZ 85280

RE: Request for Review of Claim Denial
Patient: Maria Lopez
Date of Birth: 03/02/1985
Member ID: [STAFF TO VERIFY: the EOB shows SDI-448821 but our records show SDI-448812; which is correct?]
Claim Number: SDI-26-0918-3321
Date of Service: {dos}
Procedures: D2740 Crown, porcelain/ceramic, tooth #14; D2950 Core buildup, tooth #14

To the Claims Review Department:

I am writing to request a review of the denial of the above claim under remark codes N30 (not medically necessary) and 96 (pre-operative radiograph and narrative not received). This letter serves as my narrative as the treating dentist, and the pre-operative radiograph is enclosed.

Clinical findings: Ms. Lopez presented with a fractured mesiolingual cusp on tooth #14 extending to the gumline, with recurrent decay beneath a large existing MOD amalgam. After the failing restoration and decay were removed, approximately 50% of the coronal tooth structure was missing. [DENTIST TO CONFIRM: were the remaining cusp walls thin or undermined?] [DENTIST TO CONFIRM: did the patient report pain on biting or cold sensitivity on #14?]

Medical necessity: With a fractured cusp and half of the coronal structure lost, the remaining tooth could not be predictably restored with a direct filling. The patient's documented bruxism places heavy forces on the first molars and further raises the risk of fracture. [DENTIST TO CONFIRM: were wear facets or other signs of bruxism observed on #14 or the opposing teeth?] Full cuspal coverage was the appropriate standard of care to protect the tooth.

Enclosures:
1. Pre-operative periapical radiograph of #14
2. Clinical notes from {dos}
3. [ATTACH: intraoral photo of #14 showing the fractured cusp]
4. Copy of your Explanation of Benefits

I respectfully request that you reverse the denial and process the plan benefit for this claim.

Sincerely,



Dr. Elena Park, DDS
NPI: 0000000000
Bright Smiles Dental
(555) 010-4567"""

SRP_LETTER = """{today}

Harborview Dental PPO
Attn: Appeals
P.O. Box 7720
Columbus, OH 43215

RE: Appeal of Denied Periodontal Treatment
Patient: James Carter
Date of Birth: 07/19/1971
Member ID: HDP-200471
Claim Number: HDP-26-8810-0042
Date of Service: {dos}
Procedures: D4342 Scaling and root planing, 1-3 teeth, UR (#2-5) and UL (#12-15)

Dear Appeals Reviewer:

I am appealing the denial of scaling and root planing for Mr. Carter, which was denied because periodontal charting was not submitted (remark N180).

Mr. Carter presented with generalized 5-6 mm pockets with bleeding on probing in the upper right and upper left quadrants, with subgingival calculus confirmed on bitewing radiographs, which also show horizontal bone loss. [DENTIST TO CONFIRM: list the deepest pocket depths for teeth #2-5 and #12-15 from the periodontal chart.]

Mr. Carter has type 2 diabetes. Untreated periodontitis worsens blood sugar control, and treatment is a recognized part of managing patients with diabetes, which makes timely therapy medically necessary.

Enclosed are the bitewing radiographs, the clinical notes from the date of service, and [ATTACH: full periodontal charting with pocket depths]. [STAFF TO VERIFY: was the original claim sent before the periodontal chart was finalized?]

Please reprocess this claim for payment.

Sincerely,



Dr. Elena Park, DDS
NPI: 0000000000
Bright Smiles Dental
(555) 010-4567"""

FILLING_LETTER = """{today}

Summit Benefit Dental
Attn: Claims Department
P.O. Box 3301
Denver, CO 80202

RE: Corrected Claim
Patient: Priya Shah
Date of Birth: 11/08/1992
Member ID: SBD-77310
Original Claim Number: SBD-26-0731-5562
Date of Service: {dos}
Procedure: D2392 Resin composite, two surfaces, posterior

To the Claims Department:

Please find enclosed a corrected claim for the above service, which was denied under remark codes 16 and N37 because the tooth number and surfaces were missing.

The correct tooth number is #30 and the surfaces are mesial and occlusal (MO), as documented in the clinical notes from the date of service. No other information on the claim has changed.

Please process the corrected claim for payment.

Sincerely,



Dr. Elena Park, DDS
Bright Smiles Dental
(555) 010-4567"""


def _build_denials(office, maria_inv, james_inv, priya_inv, robert_inv, dr, desk):
    today_str = timezone.localdate().strftime('%B %d, %Y')

    def eob(invoice, insurer_key, days_ago, claim, group, lines, remarks, amount, closing):
        name, address = INSURERS[insurer_key]
        patient = invoice.patient
        return ContentFile(make_eob(
            name, address, _days(-days_ago), office, patient, patient.insurance_id, group, claim,
            _days(-days_ago - 12), lines, remarks, amount, closing,
        ), name=f'demo-eob-{patient.last_name.lower()}.pdf')

    crown_dos = maria_inv.appointment.date
    ClaimDenial.objects.create(
        invoice=maria_inv, created_by=desk, ai_status='done', ai_task='analyze', status='denied',
        letter=eob(maria_inv, 'sunrise', 9, 'SDI-26-0918-3321', '20771',
                   [(crown_dos, 'D2740', '14', 'Crown - porcelain/ceramic', 1500, 'N30, 96'),
                    (crown_dos, 'D2950', '14', 'Core buildup', 250, 'N30')],
                   ['Remark N30: Services not medically necessary. The documentation submitted does not demonstrate '
                    'sufficient loss of tooth structure to support a full-coverage restoration.',
                    'Remark 96: Pre-operative radiograph and narrative not received.'],
                   1150, 'Your appeal rights: written appeals must be received within 60 days of the date of this '
                         'notice and should include radiographs and a narrative from the treating dentist.'),
        insurer_name='Sunrise Dental Insurance', claim_number='SDI-26-0918-3321', denial_codes='N30, 96',
        amount_denied=Decimal('1150.00'), appeal_deadline=_days(51),
        summary="Sunrise denied Maria's crown and buildup on tooth #14 ($1,150). They say it wasn't medically "
                "necessary because nothing showed how much tooth was lost, and they never got an X-ray or a "
                "dentist's narrative. Our chart documents a broken cusp and about half the tooth missing, and we "
                "have the pre-op X-ray, so this is a strong appeal.",
        denial_reason='N30: not medically necessary (insufficient documented loss of tooth structure). '
                      '96: pre-operative radiograph and narrative not received.',
        recommendation='appeal',
        recommendation_reason="This is a judgment call by the insurer that our records can contest. The clinical "
                              "notes document a cusp fracture and roughly 50% structure loss, the standard "
                              "indications for a crown, and the missing X-ray and narrative are things we can send "
                              "now. Her bruxism adds a further reason a filling would not hold.",
        checklist=[
            {'item': 'Pre-operative periapical X-ray of #14', 'why': 'Answers remark 96 and shows the decay under the old filling.', 'on_file': True},
            {'item': 'Clinical notes from the crown prep visit', 'why': 'Documents the fractured cusp and 50% structure loss.', 'on_file': True},
            {'item': 'Intraoral photo of #14', 'why': 'Shows the fracture more directly than an X-ray.', 'on_file': False},
            {'item': 'Copy of the EOB', 'why': 'Lets the reviewer match the appeal to the claim.', 'on_file': True},
        ],
        warnings=['Member ID mismatch: the EOB shows SDI-448821 but our records show SDI-448812 (two digits swapped). '
                  'Check the insurance card before sending.',
                  'The appeal must be received within 60 days of the notice. Send it with tracking.'],
        appeal_letter=CROWN_LETTER.format(today=today_str, dos=crown_dos.strftime('%m/%d/%Y')),
    )

    srp_dos = james_inv.appointment.date
    ClaimDenial.objects.create(
        invoice=james_inv, created_by=desk, ai_status='done', ai_task='analyze', status='denied',
        letter=eob(james_inv, 'harbor', 14, 'HDP-26-8810-0042', '5512',
                   [(srp_dos, 'D4342', '2-5', 'Scaling/root planing 1-3 teeth', 240, 'N180'),
                    (srp_dos, 'D4342', '12-15', 'Scaling/root planing 1-3 teeth', 240, 'N180')],
                   ['Remark N180: This item or service does not meet the criteria for the category under which it '
                    'was billed. Periodontal charting documenting pocket depths of 4 mm or greater is required.'],
                   384, 'Appeals must be received within 30 days of the date of this notice.'),
        insurer_name='Harborview Dental PPO', claim_number='HDP-26-8810-0042', denial_codes='N180',
        amount_denied=Decimal('384.00'), appeal_deadline=_days(16),
        summary="Harborview denied James's deep cleaning on the upper right and upper left ($384) because the "
                "claim didn't include a periodontal chart showing pocket depths. Our notes record 5-6 mm pockets, "
                "so sending the chart should get this paid.",
        denial_reason='N180: periodontal charting with pocket depths of 4 mm or more was not submitted.',
        recommendation='appeal',
        recommendation_reason="The treatment clearly meets the plan's criteria (pockets of 5-6 mm are documented), "
                              "the claim was just missing the chart. His diabetes strengthens the case for timely "
                              "treatment.",
        checklist=[
            {'item': 'Full periodontal chart with pocket depths', 'why': 'This is exactly what the denial says was missing.', 'on_file': False},
            {'item': 'Bitewing X-rays showing bone loss', 'why': 'Shows calculus and horizontal bone loss.', 'on_file': True},
            {'item': 'Clinical notes from the SRP visit', 'why': 'Documents pocket depths and bleeding.', 'on_file': True},
        ],
        warnings=['Only 30 days to appeal from the notice date. The deadline is coming up soon.',
                  'The periodontal chart is not in the app. Print it from your charting software or upload it.'],
        appeal_letter=SRP_LETTER.format(today=today_str, dos=srp_dos.strftime('%m/%d/%Y')),
    )

    filling_dos = priya_inv.appointment.date
    ClaimDenial.objects.create(
        invoice=priya_inv, created_by=desk, ai_status='done', ai_task='analyze', status='resubmitted',
        letter=eob(priya_inv, 'summit', 21, 'SBD-26-0731-5562', '3040',
                   [(filling_dos, 'D2392', '', 'Resin composite 2 surf post', 225, '16, N37')],
                   ['Remark 16: Claim lacks information which is needed for adjudication.',
                    'Remark N37: Missing or invalid tooth number and surface(s).'],
                   180, 'Submit a corrected claim with the tooth number and surfaces within 90 days.'),
        insurer_name='Summit Benefit Dental', claim_number='SBD-26-0731-5562', denial_codes='16, N37',
        amount_denied=Decimal('180.00'), appeal_deadline=_days(69),
        summary="Summit didn't actually deny Priya's filling on its merits. The claim was missing the tooth number "
                "and surfaces. Our records show it was tooth #30, surfaces MO, so we just need to send a corrected "
                "claim.",
        denial_reason='16 / N37: the claim was missing the tooth number and surfaces.',
        recommendation='resubmit',
        recommendation_reason='This is a paperwork error, not a coverage decision. A corrected claim is faster than an appeal.',
        checklist=[{'item': 'Corrected claim form with tooth #30, surfaces MO', 'why': 'Fixes exactly what was missing.', 'on_file': False}],
        warnings=[],
        appeal_letter=FILLING_LETTER.format(today=today_str, dos=filling_dos.strftime('%m/%d/%Y')),
    )

    ClaimDenial.objects.create(
        invoice=robert_inv, created_by=desk, ai_status='done', ai_task='analyze', status='approved',
        letter=eob(robert_inv, 'harbor', 60, 'HDP-26-6120-0310', '5512',
                   [(robert_inv.appointment.date, 'D7210', '17', 'Surgical extraction', 395, 'N30')],
                   ['Remark N30: Narrative required to support surgical extraction.'],
                   316, 'Appeals must be received within 30 days of the date of this notice.'),
        insurer_name='Harborview Dental PPO', claim_number='HDP-26-6120-0310', denial_codes='N30',
        amount_denied=Decimal('316.00'),
        summary="Harborview asked for a narrative to support the surgical extraction of #17. We sent one with the "
                "X-ray and the claim was paid.",
        denial_reason='N30: narrative required for surgical extraction.', recommendation='appeal',
        recommendation_reason='The extraction was clearly surgical (partially impacted tooth).',
        checklist=[], warnings=[],
        appeal_letter='(Appeal sent and approved. Claim paid in full.)',
    )


def _delete_files(files):
    for storage, name in files:
        try:
            storage.delete(name)
        except Exception:
            pass  # an orphaned demo image is harmless


def reset_demo_practice():
    """Wipe and rebuild the demo in one transaction, so a reset that's cut
    off halfway leaves the old demo intact. The caller must have checked
    DEMO_MODE."""
    from auditlog.context import disable_auditlog
    with disable_auditlog(), transaction.atomic():
        old_files = wipe()
        result = build()
        transaction.on_commit(lambda: _delete_files(old_files))
    return result
