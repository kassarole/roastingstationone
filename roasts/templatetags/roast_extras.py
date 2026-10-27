import json
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def jsonify(value):
    return mark_safe(json.dumps(value))


@register.filter
def fmt_time(seconds):
    if seconds is None:
        return "-"
    seconds = float(seconds)
    m, s = divmod(seconds, 60)
    return f"{int(m)}:{s:04.1f}"

@register.filter
def to_f(val, mode):
    if val is None:
        return "-"
    if mode == "F":
        return (val * 9.0 / 5.0) + 32
    return val
