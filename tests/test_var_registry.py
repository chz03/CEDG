"""Step 2 acceptance: derived-variable registry exposed to <execute> code."""
import asyncio


def test_var_registry_initialized_empty(report_generator):
    assert report_generator.var_registry == {}


def test_set_var_in_execute_registers(report_generator):
    async def _run():
        report_generator.current_task_data = {'task': 'test'}
        await report_generator._prepare_executor()
        return await report_generator.code_executor.execute(
            '_set_var("x", 42, depends_on=["E001"])'
        )

    result = asyncio.run(_run())
    assert result['error'] is False

    entry = report_generator.var_registry['x']
    assert entry['value'] == 42
    assert entry['depends_on'] == ['E001']


def test_set_var_latest_wins_and_records_code(report_generator):
    async def _run():
        report_generator.current_task_data = {'task': 'test'}
        await report_generator._prepare_executor()
        await report_generator.code_executor.execute(
            '_set_var("margin", 0.31, depends_on=["E001", "E002"], _code="(a-b)/a")'
        )
        return await report_generator.code_executor.execute(
            '_set_var("margin", 0.33, depends_on=["E001", "E002"], _code="(a2-b2)/a2")'
        )

    result = asyncio.run(_run())
    assert result['error'] is False
    entry = report_generator.var_registry['margin']
    assert entry['value'] == 0.33
    assert entry['code'] == '(a2-b2)/a2'
