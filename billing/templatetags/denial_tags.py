from django import template

from billing.placeholders import highlight

register = template.Library()


@register.filter
def highlight_placeholders(letter):
    return highlight(letter)
