"""Step 5 acceptance (gate half): bad drafts bounce with feedback, good drafts
pass and store claims; reject cap forces acceptance; <report> drafts are gated
too; polish that mutates pointers is discarded."""
import asyncio

from tests.conftest import make_tool_result

GOOD_DRAFT = (
    "公司 2024 年营收为 ⟨VAR:revenue_2024⟩ 亿元，表现稳健 [Source:E001]。\n"
    "我们认为该趋势将延续。[INFER]\n"
)
BAD_DRAFT = "营收 123.4 亿元，表现强劲 [Source:E999]。"


def _prime(report_generator, memory):
    memory.add_data(make_tool_result('Income statement 2024'))
    report_generator.var_registry['revenue_2024'] = {
        'value': 123.4, 'depends_on': ['E001'], 'code': 'float(...)',
    }
    report_generator._current_section_idx = 0


def test_checklist_acceptance_bad_draft_bounced(report_generator, memory):
    _prime(report_generator, memory)
    result = asyncio.run(report_generator._handle_draft_action(BAD_DRAFT))
    assert result['continue'] is True
    assert 'REJECTED' in result['result']
    assert any('123.4' in line for line in result['result'].splitlines())
    assert any('E999' in line for line in result['result'].splitlines())


def test_good_draft_accepted_and_claims_stored(report_generator, memory):
    _prime(report_generator, memory)
    result = asyncio.run(report_generator._handle_draft_action(GOOD_DRAFT))
    assert result['continue'] is False
    assert result['result'] == GOOD_DRAFT
    claims = report_generator.section_claims[0]
    assert {c.ctype for c in claims} == {'num', 'infer'}
    assert not getattr(report_generator, '_last_draft_forced', False)


def test_reject_cap_forces_acceptance_after_two_bounces(report_generator, memory):
    _prime(report_generator, memory)
    r1 = asyncio.run(report_generator._handle_draft_action(BAD_DRAFT))
    r2 = asyncio.run(report_generator._handle_draft_action(BAD_DRAFT))
    assert r1['continue'] is True and r2['continue'] is True
    # third bad draft: over the cap → forced acceptance to avoid burning tokens
    r3 = asyncio.run(report_generator._handle_draft_action(BAD_DRAFT))
    assert r3['continue'] is False
    assert getattr(report_generator, '_last_draft_forced', False) is True
    # claims are still recorded for the CEDG build (flagged unresolved in step 6)
    assert 0 in report_generator.section_claims


def test_report_action_draft_is_gated_too(report_generator, memory):
    _prime(report_generator, memory)
    result = asyncio.run(report_generator._handle_report_action(BAD_DRAFT))
    assert result['continue'] is True
    assert 'REJECTED' in result['result']


def test_final_polish_discards_pointer_mutations(report_generator, memory, monkeypatch):
    _prime(report_generator, memory)

    async def fake_generate(messages, **kwargs):
        # polish that silently drops the VAR placeholder and invents a number
        return "公司 2024 年营收为 999 亿元，表现稳健 [Source:E001]。"

    monkeypatch.setattr(report_generator.llm, 'generate', fake_generate)
    polished = asyncio.run(
        report_generator._final_polish({'task': 't'}, GOOD_DRAFT)
    )
    # polish lost ⟨VAR:revenue_2024⟩ → pointer set not preserved → draft wins
    assert polished == GOOD_DRAFT


def test_final_polish_keeps_clean_polish(report_generator, memory, monkeypatch):
    _prime(report_generator, memory)

    async def fake_generate(messages, **kwargs):
        return ("公司 2024 年营收为 ⟨VAR:revenue_2024⟩ 亿元，表现稳健且结构优异 [Source:E001]。\n"
                "我们认为该趋势将延续。[INFER]\n")

    monkeypatch.setattr(report_generator.llm, 'generate', fake_generate)
    polished = asyncio.run(report_generator._final_polish({'task': 't'}, GOOD_DRAFT))
    assert '结构优异' in polished          # polish applied
    assert '⟨VAR:revenue_2024⟩' in polished  # pointer intact
