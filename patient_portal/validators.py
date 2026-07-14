from datetime import time

from django.core.exceptions import ValidationError

# Office hours by weekday (0=Monday … 6=Sunday). Missing key = closed.
OFFICE_HOURS = {
    0: (time(8, 0), time(17, 0)),
    1: (time(8, 0), time(17, 0)),
    2: (time(8, 0), time(17, 0)),
    3: (time(8, 0), time(17, 0)),
    4: (time(8, 0), time(17, 0)),
    5: (time(8, 0), time(13, 0)),
}
_DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def _fmt(t):
    return t.strftime('%I:%M %p').lstrip('0')


def validate_office_hours(preferred_date, preferred_time):
    """Shared by the web AppointmentRequestForm and the mobile API serializer
    so the office-hours business rule only lives in one place."""
    if not preferred_date or not preferred_time:
        return

    weekday = preferred_date.weekday()
    day_name = _DAY_NAMES[weekday]
    hours = OFFICE_HOURS.get(weekday)

    if hours is None:
        raise ValidationError({
            'preferred_date': f'The office is closed on {day_name}s. '
                              f'Please choose a weekday or Saturday.',
        })

    open_t, close_t = hours
    if not (open_t <= preferred_time < close_t):
        raise ValidationError({
            'preferred_time': f'On {day_name}s, office hours are {_fmt(open_t)} – {_fmt(close_t)}. '
                              f'Please pick a time within those hours.',
        })
