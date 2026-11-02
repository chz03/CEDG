"""Step 4 acceptance: _prepare_init_prompt shows evidence under E-IDs."""
import asyncio

from src.agents.data_analyzer.data_analyzer import AnalysisResult

from tests.conftest import make_tool_result


def test_init_prompt_lists_evidence_with_eids(report_generator, memory):
    memory.add_data(make_tool_result('Income statement 2024'))
    memory.add_data(make_tool_result('Balance sheet 2024'))
    memory.add_data(AnalysisResult(
        title='Revenue analysis',
        content='plain analysis text without imports',
        image_save_dir='unused',
    ))

    async def _run():
        # async_run normally sets this before preparing the prompt
        report_generator.enable_chart = True
        return await report_generator._prepare_init_prompt(
            {'task': 'test task', 'section_outline': 'some outline'}
        )

    messages = asyncio.run(_run())
    content = messages[0]['content']

    assert '**Evidence [E001] (data_id=0):**' in content
    assert '**Evidence [E002] (data_id=1):**' in content
    # Analysis results share the same E-ID series (assigned by add_data in step 1)
    assert '**Evidence [E003] (analysis_id=0):**' in content
    # The old bare "Data ID" header must be gone
    assert '**Data ID 0:**' not in content
