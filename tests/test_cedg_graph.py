"""Step 6 acceptance: accepted drafts land in the CEDG; cedg.json is written
with claims matching the section's claims and non-empty edges."""
import asyncio
import json
import os

from src.agents.data_analyzer.data_analyzer import AnalysisResult
from src.cedg.graph import CEDG, ClaimNode, EvidenceNode

from tests.conftest import make_tool_result

GOOD_DRAFT = (
    "公司 2024 年营收为 ⟨VAR:revenue_2024⟩ 亿元，表现稳健 [Source:E001]。\n"
    "公司总部位于北京 [Source:E002]。\n"
    "我们认为该趋势将延续。[INFER]\n"
)
BAD_DRAFT = "营收 123.4 亿元，表现强劲 [Source:E999]。"


def _prime(report_generator, memory):
    memory.add_data(make_tool_result('Income statement 2024'))          # E001
    memory.add_data(make_tool_result('Company profile'))                # E002
    memory.add_data(AnalysisResult(
        title='Margin analysis', content='plain text', image_save_dir='x',
    ))                                                                  # E003 (analysis)
    report_generator.var_registry['revenue_2024'] = {
        'value': 123.4, 'depends_on': ['E001'], 'code': 'float(...)',
    }
    report_generator._current_section_idx = 0


def _accept(report_generator, draft, section_idx=0):
    report_generator._current_section_idx = section_idx
    return asyncio.run(report_generator._handle_draft_action(draft))


def test_accepted_draft_populates_cedg(report_generator, memory):
    _prime(report_generator, memory)
    result = _accept(report_generator, GOOD_DRAFT)
    assert result['continue'] is False

    cedg = report_generator.cedg
    assert isinstance(cedg, CEDG)
    # claims count matches the section's claims (num + fact + infer = 3)
    assert len(cedg.claims) == 3
    types = {c.ctype for c in cedg.claims.values()}
    assert types == {'num', 'fact', 'infer'}
    # edges: sup from both cited eids + derive from the var's depends_on
    sup_edges = [e for e in cedg.edges if e[2] == 'sup']
    derive_edges = [e for e in cedg.edges if e[2] == 'derive']
    assert {e[0] for e in sup_edges} == {'E001', 'E002'}
    assert len(derive_edges) == 1 and derive_edges[0][0] == 'E001'
    # every claim defaults to pending with kappa 1.0
    assert all(c.nu == 'pending' for c in cedg.claims.values())
    assert all(c.kappa == 1.0 for c in cedg.claims.values())


def test_evidence_node_kinds(report_generator, memory):
    _prime(report_generator, memory)
    _accept(report_generator, GOOD_DRAFT)
    cedg = report_generator.cedg
    assert cedg.evidence['E001'].kind == 'tool_result'
    assert cedg.evidence['E002'].kind == 'tool_result'
    # uncited analysis evidence only lands if cited; cite it now
    _accept(report_generator, "分析报告认为毛利率稳定 [Source:E003]。", section_idx=1)
    assert cedg.evidence['E003'].kind == 'analysis'
    assert 'E003' in {e[0] for e in cedg.edges if e[2] == 'sup'}


def test_forced_draft_claims_marked_unresolved(report_generator, memory):
    _prime(report_generator, memory)
    for _ in range(3):
        result = _accept(report_generator, BAD_DRAFT)   # 2 bounces then force
    assert result['continue'] is False
    assert report_generator.cedg.claims
    assert all(c.nu == 'unresolved' for c in report_generator.cedg.claims.values())


def test_cids_unique_across_sections(report_generator, memory):
    _prime(report_generator, memory)
    _accept(report_generator, GOOD_DRAFT, section_idx=0)
    _accept(report_generator, "公司总部位于上海 [Source:E002]。", section_idx=1)
    cids = list(report_generator.cedg.claims.keys())
    assert len(cids) == len(set(cids))


def test_to_json_writes_loadable_graph(report_generator, memory, tmp_path):
    _prime(report_generator, memory)
    _accept(report_generator, GOOD_DRAFT)
    path = os.path.join(str(tmp_path), 'cedg.json')
    report_generator.cedg.to_json(path)

    assert os.path.exists(path)
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    assert len(data['claims']) == 3
    assert len(data['edges']) >= 3
    assert data['evidence']['E001']['kind'] == 'tool_result'
    assert data['claims'][list(data['claims'])[0]]['nu'] == 'pending'


def test_dataclass_defaults():
    e = EvidenceNode(eid='E001', kind='tool_result', ref_repr='r')
    c = ClaimNode(cid='C001', ctype='num', text='t')
    assert c.var_names == [] and c.kappa == 1.0 and c.nu == 'pending'
    g = CEDG()
    assert g.evidence == {} and g.claims == {} and g.edges == []
