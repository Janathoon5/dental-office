"""The [BRACKETED] gaps the AI leaves in a letter for the dental team to fill,
e.g. "[DENTIST TO CONFIRM: pocket depths on #3]" or "[ATTACH: bitewing X-ray]".

Each one is sorted into who has to deal with it:
  dentist - clinical facts only a dentist may state to an insurer
  staff   - administrative details the front desk can verify
  attach  - documents to enclose (or drop if unavailable)
"""
import re

from django.utils.html import escape
from django.utils.safestring import mark_safe

PLACEHOLDER_RE = re.compile(r'\[([^\]\n]{2,})\]')

CATEGORY_LABELS = {
    'dentist': 'Dentist to confirm',
    'staff': 'Staff to verify',
    'attach': 'Attachments',
}


def categorize(inner):
    """(category, question) for the text inside the brackets."""
    head, sep, rest = inner.partition(':')
    head = head.upper() if sep else inner.upper()
    if 'DENTIST' in head:
        category = 'dentist'
    elif head.startswith('ATTACH'):
        category = 'attach'
    else:
        category = 'staff'
    return category, (rest if sep else inner).strip()


def find_placeholders(letter):
    """Unique placeholders in the order they first appear."""
    items, seen = [], set()
    for match in PLACEHOLDER_RE.finditer(letter or ''):
        text = match.group(0)
        if text in seen:
            continue
        seen.add(text)
        category, question = categorize(match.group(1))
        items.append({'placeholder': text, 'category': category, 'question': question})
    return items


def count_by_category(letter):
    counts = {key: 0 for key in CATEGORY_LABELS}
    for item in find_placeholders(letter):
        counts[item['category']] += 1
    return counts


def highlight(letter):
    """HTML-escaped letter with each placeholder wrapped in a color-coded <mark>."""
    letter = letter or ''
    parts, pos = [], 0
    for match in PLACEHOLDER_RE.finditer(letter):
        category, _ = categorize(match.group(1))
        parts.append(escape(letter[pos:match.start()]))
        parts.append(f'<mark class="ph ph-{category}">{escape(match.group(0))}</mark>')
        pos = match.end()
    parts.append(escape(letter[pos:]))
    return mark_safe(''.join(parts))
