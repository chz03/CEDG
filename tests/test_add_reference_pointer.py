"""Step 7 acceptance: citation backfill becomes direct E-ID translation in
pointer mode; legacy mode (the ablation switch) still generates references."""
import asyncio

from src.agents.report_generator.report_class import Report
from src.tools.web.web_crawler import ClickResult

from tests.conftest import make_tool_result

BODY = (
    "公司 2024 年营收为 ⟨VAR:revenue_2024⟩ 亿元，表现稳健 [Source:E001]。\n\n"
    "网络资料显示业务持续扩张 [Source:E002]。\n\n"
    "营收再次被引用 [Source:E001]。"
)


def _prime(report_generator, memory):
    memory.add_data(make_tool_result('Income statement 2024'))   # E001
    memory.add_data(ClickResult(
        name='News page', description='company news',
        data='page text', link='https://example.com/news', source='Example',
    ))                                                             # E002
    report_generator.var_registry['revenue_2024'] = {
        'value': 123.4, 'depends_on': ['E001'], 'code': 'x',
    }


def _report():
    report = Report("# 测试报告\n\n## 正文\n\nbody")
    report.sections[0].set_content(BODY)
    return report


def test_pointer_mode_translates_eids_directly(report_generator, memory):
    _prime(report_generator, memory)
    assert report_generator.config.config.get('citation_mode') == 'pointer'

    report = asyncio.run(report_generator._add_reference(_report()))
    content = report.sections[0].content

    assert '[Source:' not in content
    assert '[1]' in content and '[2]' in content
    # repeated citation reuses the same number
    assert content.count('[1]') == 2
    # reference section appended with both entries, web entry carries the link
    assert report.sections[-1].title == 'Reference Data Sources'
    ref = report.sections[-1].content
    assert 'Income statement 2024' in ref
    assert 'https://example.com/news' in ref


def test_pointer_mode_missing_evidence_gets_audit_marker(report_generator, memory):
    _prime(report_generator, memory)
    report = Report("# 测试报告\n\n## 正文\n\nbody")
    report.sections[0].set_content("悬空引用 [Source:E999]。")

    report = asyncio.run(report_generator._add_reference(report))
    assert '[1]' in report.sections[0].content
    assert '<missing evidence E999>' in report.sections[-1].content


def test_legacy_mode_still_generates_references(report_generator, memory, monkeypatch):
    _prime(report_generator, memory)
    report_generator.config.config['citation_mode'] = 'legacy'

    # stub the embedding index; legacy logic itself stays upstream-verbatim
    import src.agents.report_generator.report_generator as rg_mod

    class _StubIndex:
        def __init__(self, config=None, embedding_model=None, working_dir=None):
            self.corpus = []

        async def _build_index(self, corpus):
            self.corpus = list(corpus)

        async def search(self, query, top_k=5):
            for i, doc in enumerate(self.corpus):
                if query in doc or doc in query:
                    return [{'id': i, 'score': 0.9}]
            return [{'id': 0, 'score': 0.9}]

    monkeypatch.setattr(rg_mod, 'IndexBuilder', _StubIndex)

    report = Report("# 测试报告\n\n## 正文\n\nbody")
    report.sections[0].set_content("营收增长 [Source: Income statement 2024]。")

    report = asyncio.run(report_generator._add_reference(report))
    assert '[1]' in report.sections[0].content
    assert report.sections[-1].title == 'Reference Data Sources'
    # legacy display entries use item.source (upstream behavior)
    assert '1. ' in report.sections[-1].content


def test_default_config_declares_modes(make_config, dummy_env):
    config = make_config()
    assert config.config.get('citation_mode') in ('pointer', 'legacy')
    assert config.config.get('citation_mode') == 'pointer'
    assert config.config.get('verify_mode') in ('strict', 'marking')
    assert config.config.get('verify_mode') == 'marking'
