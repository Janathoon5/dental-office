import re

from django.core.exceptions import ValidationError

# Area codes used on claims instead of single teeth: quadrants and arches.
AREAS = {'UR', 'UL', 'LR', 'LL', 'UA', 'LA', 'FM'}
_TOKEN = re.compile(r'#?(\d{1,2})(?:-#?(\d{1,2}))?$')


def validate_tooth_list(value):
    """Tooth numbers as staff write them: "14", "#3, #4", "2-5, 12-15",
    "A" to "T" for baby teeth, or an area such as "UR" or "LA". Adult teeth
    use Universal numbering, 1 to 32."""
    text = re.sub(r'\s*-\s*', '-', (value or '').strip())
    if not text:
        return
    for token in re.split(r'[\s,;/&]+|\band\b', text):
        if not token:
            continue
        if token.upper() in AREAS or re.fullmatch(r'[A-Ta-t]', token):
            continue
        match = _TOKEN.match(token)
        if match:
            start = int(match.group(1))
            end = int(match.group(2) or start)
            if 1 <= start <= end <= 32:
                continue
        raise ValidationError(
            f'"{token}" isn\'t a tooth number. Use 1-32 (or A-T for baby teeth), '
            f'for example 14, 3-5, or 2, 3.'
        )
