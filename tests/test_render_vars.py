"""Step 9 acceptance (renderer): placeholders become real values only at
render time, with centralized formatting."""
from src.cedg.renderer import format_value, render_vars


def _reg(**kwargs):
    return {k: {'value': v, 'depends_on': [], 'code': ''} for k, v in kwargs.items()}


def test_int_gets_thousands_separator():
    assert format_value('store_count', 1234567) == '1,234,567'
    assert format_value('rev', 99) == '99'


def test_float_money_two_decimals():
    assert format_value('rev', 1234.5678) == '1,234.57'
    assert format_value('rev', 99.0) == '99.00'


def test_ratio_fractions_render_as_percent():
    assert format_value('gross_margin', 0.31) == '31.0%'
    assert format_value('net_profit_margin', 0.125) == '12.5%'
    assert format_value('market_share', 0.07) == '7.0%'


def test_explicit_percent_names_suffix_without_scaling():
    assert format_value('revenue_growth_pct', 25.3) == '25.3%'
    assert format_value('market_share_pct', 7) == '7.0%'


def test_non_percent_names_never_get_percent_sign():
    # 汇率 matches the fraction-marker 率 but is >1 and not an explicit percent
    # name, so it renders as a plain number.
    assert format_value('exchange_rate', 7.24) == '7.24'
    assert format_value('leverage', 1.2) == '1.20'


def test_string_value_passthrough():
    assert format_value('verdict', '稳健') == '稳健'


def test_render_vars_replaces_all_placeholders():
    registry = _reg(revenue_2024=1234.5678, gross_margin=0.31, verdict='向好')
    text = "营收 ⟨VAR:revenue_2024⟩ 亿元，毛利率 ⟨VAR:gross_margin⟩，展望 ⟨VAR:verdict⟩。"
    out = render_vars(text, registry)
    assert out == "营收 1,234.57 亿元，毛利率 31.0%，展望 向好。"


def test_render_vars_leaves_unknown_placeholder_visible():
    registry = _reg(known=1)
    out = render_vars("未知 ⟨VAR:unknown_var⟩ 保持可见", registry)
    assert '⟨VAR:unknown_var⟩' in out


def test_render_vars_keeps_markers_and_citations():
    registry = _reg(x=1.0)
    text = "数值 ⟨VAR:x⟩ [待核实] 引用 [1] 保留。"
    assert render_vars(text, registry) == "数值 1.00 [待核实] 引用 [1] 保留。"
