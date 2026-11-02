"""Step 8 acceptance (integration): verify stage runs between reference and
render; marking mode appends [待核实] and decays kappa; strict mode rewrites
the failing section once."""
import asyncio

from src.agents.report_generator.report_class import Report

from tests.conftest import make_tool_result

DRAFT = "公司 2024 年营收为 ⟨VAR:rev⟩ 亿元，表现稳健 [Source:E001]。"


def _setup(report_generator, memory, code, value):
    memory.add_data(make_tool_result('Income statement 2024'))   # E001
    report_generator.var_registry['rev'] = {
        'value': value, 'depends_on': ['E001'], 'code': code,
    }
    report_generator._current_section_idx = 0
    result = asyncio.run(report_generator._handle_draft_action(DRAFT))
    assert result['continue'] is False

    report_generator.enable_chart = False          # skip image machinery
    report_generator.add_introduction = False      # title only (llm mocked)
    report_generator.add_reference_section = True
    return Report("# 测试报告\n\n## 正文\n\nbody")


async def _mocked_post(report_generator, report, monkeypatch):
    async def fake_generate(messages, **kwargs):
        return "新标题"

    monkeypatch.setattr(report_generator.llm, 'generate', fake_generate)

    rendered = []

    async def fake_render(input_data, rep):
        rendered.append(rep)
        return rep

    monkeypatch.setattr(report_generator, '_render_report', fake_render)
    report_generator._post_stage = 0
    report = await report_generator.post_process_report(
        {'target_type': 'general', 'task': 't', 'max_iterations': 5}, report
    )
    return report, rendered


def test_marking_mode_marks_failed_claims(report_generator, memory, monkeypatch):
    # registered value 100.0 but the expression recomputes to 99 → failed
    report = _setup(report_generator, memory, code='99.0', value=100.0)
    report.sections[0].set_content(DRAFT)

    report, rendered = asyncio.run(
        _mocked_post(report_generator, report, monkeypatch)
    )
    content = report.sections[0].content
    assert '[待核实]' in content
    assert '⟨VAR:rev⟩' in content          # placeholder survives for step 9
    # kappa decayed, nu recorded on the graph
    claim = report_generator.cedg.claims['S01-C001']
    assert claim.nu == 'failed'
    assert claim.kappa == 0.5
    # render ran after verification
    assert len(rendered) == 1
    assert report_generator._post_stage == 6


def test_marking_mode_clean_claims_unmarked(report_generator, memory, monkeypatch):
    report = _setup(report_generator, memory, code='100.0', value=100.0)
    report.sections[0].set_content(DRAFT)

    report, _ = asyncio.run(_mocked_post(report_generator, report, monkeypatch))
    assert '[待核实]' not in report.sections[0].content
    assert report_generator.cedg.claims['S01-C001'].nu == 'verified'
    assert report_generator.cedg.claims['S01-C001'].kappa == 1.0


def test_strict_mode_rewrites_failed_section_once(report_generator, memory, monkeypatch):
    report_generator.config.config['verify_mode'] = 'strict'
    report = _setup(report_generator, memory, code='99.0', value=100.0)
    report.sections[0].set_content(DRAFT)

    calls = []

    async def fake_write_section(idx, section, section_input_data, **kwargs):
        calls.append(idx)
        # simulate a successful rewrite: fix the registry, re-run the gate,
        # and replace the section content
        report_generator.var_registry['rev']['value'] = 99.0
        await report_generator._handle_draft_action(DRAFT)
        section.set_content(DRAFT)
        return DRAFT

    monkeypatch.setattr(report_generator, '_write_section', fake_write_section)

    report, _ = asyncio.run(_mocked_post(report_generator, report, monkeypatch))
    assert calls == [0]                       # section 1 rewritten exactly once
    assert '[待核实]' not in report.sections[0].content
    claim = report_generator.cedg.claims['S01-C001']
    assert claim.nu == 'verified'             # re-verified after the rewrite
