"""Step 5 acceptance (parser half): parse_draft catches dangling pointers,
bare numbers, malformed citations; splits claims by type."""
import pytest

from src.cedg.draft_parser import (
    Claim,
    ParsedDraft,
    SOURCE_RE,
    VAR_RE,
    parse_draft,
)

VALID_EIDS = {"E001", "E002", "E003"}
VALID_VARS = {"revenue_2024", "gross_margin"}


def test_clean_draft_produces_no_errors():
    text = (
        "### 2.1 盈利能力分析\n\n"
        "公司 2024 年营收为 ⟨VAR:revenue_2024⟩ 亿元，同比增长稳健 [Source:E001]。\n\n"
        "公司总部位于北京 [Source:E002]。\n\n"
        "管理层预计该趋势仍将延续。[INFER]\n"
    )
    parsed = parse_draft(text, VALID_EIDS, VALID_VARS)
    assert parsed.errors == []
    assert parsed.warnings == []
    types = {c.ctype for c in parsed.claims}
    assert "num" in types and "fact" in types and "infer" in types


def test_checklist_acceptance_case_bare_number_and_dangling_source():
    text = "营收 123.4 亿元，表现强劲 [Source:E999]。"
    parsed = parse_draft(text, VALID_EIDS, VALID_VARS)
    assert len(parsed.errors) == 2
    assert any("123.4" in e for e in parsed.errors)
    assert any("E999" in e for e in parsed.errors)


def test_dangling_var_pointer_is_error():
    text = "营收为 ⟨VAR:unknown_var⟩ 亿元 [Source:E001]。"
    parsed = parse_draft(text, VALID_EIDS, VALID_VARS)
    assert len(parsed.errors) == 1
    assert "unknown_var" in parsed.errors[0]


def test_years_and_section_numbers_are_whitelisted():
    text = "### 2.1 历史回顾\n\n在 2023 年至 2024 年间，业务结构持续优化 [Source:E001]。"
    parsed = parse_draft(text, VALID_EIDS, VALID_VARS)
    assert parsed.errors == []


def test_percentages_and_counts_are_bare_numbers():
    parsed = parse_draft("毛利率高达45%。", VALID_EIDS, VALID_VARS)
    assert any("45%" in e for e in parsed.errors)
    parsed = parse_draft("门店数量达到1,234家。", VALID_EIDS, VALID_VARS)
    assert any("1,234" in e for e in parsed.errors)


def test_cjk_glued_numbers_are_caught():
    # No space before the digits — common in Chinese prose
    parsed = parse_draft("营收123.4亿元。", VALID_EIDS, VALID_VARS)
    assert any("123.4" in e for e in parsed.errors)


def test_source_by_name_is_malformed():
    parsed = parse_draft("营收增长强劲 [Source: Wind资讯]。", VALID_EIDS, VALID_VARS)
    assert parsed.errors, "named source must be rejected"
    assert any("E-ID" in e or "E0" in e for e in parsed.errors)


def test_import_and_images_do_not_trigger_bare_numbers():
    text = (
        '@import "revenue_breakdown_2023.png"\n\n'
        "营收见下图 [Source:E001]。\n\n"
        "![chart](media/fig_2024_v2.png)\n"
    )
    parsed = parse_draft(text, VALID_EIDS, VALID_VARS)
    assert parsed.errors == []


def test_claim_split_types_and_pointers():
    text = (
        "营收为 ⟨VAR:revenue_2024⟩ 亿元 [Source:E001]。\n"
        "公司总部位于北京 [Source:E002]。\n"
        "我们认为该业务前景广阔 [INFER]。\n"
        "这句话完全没有任何标记。\n"
    )
    parsed = parse_draft(text, VALID_EIDS, VALID_VARS)
    assert parsed.errors == []
    assert len(parsed.claims) == 4
    by_type = {c.ctype: c for c in parsed.claims}
    assert by_type["num"].var_names == ["revenue_2024"]
    assert by_type["num"].source_eids == ["E001"]
    assert by_type["fact"].source_eids == ["E002"]
    assert by_type["infer"].ctype == "infer"


def test_unsourced_judgement_is_warning_not_error():
    parsed = parse_draft("公司盈利能力持续恶化。", VALID_EIDS, VALID_VARS)
    assert parsed.errors == []
    assert len(parsed.warnings) >= 1


def test_headings_and_placeholders_are_not_claims():
    text = "### 盈利能力分析\n\n@import \"fig.png\"\n"
    parsed = parse_draft(text, VALID_EIDS, VALID_VARS)
    assert parsed.claims == []


def test_claim_dataclass_defaults():
    c = Claim(cid="C001", ctype="num", text="x")
    assert c.source_eids == [] and c.var_names == []
    p = ParsedDraft(claims=[], errors=[], warnings=[])
    assert p.claims == []
