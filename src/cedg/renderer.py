"""Render-time variable substitution (step 9): «generation decoupled from
rendering» — numbers enter the text only here, formatting centralized in one
place. The draft carried ⟨VAR:name⟩ placeholders; nothing numeric was
generated.
"""
import re

VAR_RENDER_RE = re.compile(r'⟨VAR:([A-Za-z_][\w]*)⟩')

# Names implying a fraction in [0,1] that should be shown as a percentage.
RATIO_FRACTION_MARKERS = (
    'margin', 'pct', 'percent', 'ratio', 'share', 'yield', 'growth',
    '增速', '毛利率', '净利率', '利润率', '占有率', '占比', '比率',
)
# Names explicitly declaring a percentage already on the 0–100 scale.
PERCENT_SUFFIX_MARKERS = ('pct', 'percent', '占比', '百分比')


def _is_ratio_fraction(name: str) -> bool:
    lowered = name.lower()
    return any(m in lowered or m in name for m in RATIO_FRACTION_MARKERS)


def _is_percent_scaled(name: str) -> bool:
    lowered = name.lower()
    return any(m in lowered or m in name for m in PERCENT_SUFFIX_MARKERS)


def format_value(name: str, value) -> str:
    """Centralized value formatting.

    - explicit percent names (pct/percent/占比): 1 decimal + %
    - fraction-like values (|v| ≤ 1) on ratio-flavoured names: ×100, 1 decimal + %
    - ints: thousands separators, no decimals
    - floats: thousands separators, 2 decimals (money convention)
    - strings: as-is
    """
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return str(value)
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)

    # name-based percent rendering wins over plain numeric formatting
    if _is_percent_scaled(name):
        return f'{num:.1f}%'
    if _is_ratio_fraction(name) and abs(num) <= 1:
        return f'{num * 100:.1f}%'
    if isinstance(value, int):
        return f'{value:,}'
    return f'{num:,.2f}'


def render_vars(text: str, registry: dict) -> str:
    """Replace every ⟨VAR:name⟩ placeholder with its formatted value.

    Unknown placeholders are left visible in the text (an auditable anomaly,
    not a silently dropped number).
    """
    def _sub(match: re.Match) -> str:
        name = match.group(1)
        entry = registry.get(name)
        if entry is None or 'value' not in entry:
            return match.group(0)
        return format_value(name, entry['value'])

    return VAR_RENDER_RE.sub(_sub, text)
