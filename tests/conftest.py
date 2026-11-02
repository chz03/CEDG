"""Shared fixtures for CEDG renovation tests (offline, no network)."""
import sys
import types

# --- Stub heavy optional deps before any `src` import -----------------------
# crawl4ai pulls in a full playwright/browser stack; web_crawler.py only
# references these names inside method bodies, so class definitions work with
# inert placeholders. Unit tests never crawl.
if 'crawl4ai' not in sys.modules:
    _crawl4ai_stub = types.ModuleType('crawl4ai')

    class _Dummy:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    _crawl4ai_stub.AsyncWebCrawler = _Dummy
    _crawl4ai_stub.BrowserConfig = _Dummy
    _crawl4ai_stub.CrawlerRunConfig = _Dummy

    class _CacheMode:
        BYPASS = "bypass"

    _crawl4ai_stub.CacheMode = _CacheMode
    sys.modules['crawl4ai'] = _crawl4ai_stub

import pytest

from src.config import Config
from src.memory.variable_memory import Memory
from src.tools.base import ToolResult

# Env vars referenced by src/config/default_config.yaml via ${...} placeholders.
_DUMMY_ENV = {
    'DS_MODEL_NAME': 'test-chat-model',
    'DS_API_KEY': 'test-key',
    'DS_BASE_URL': 'http://localhost:9/v1',
    'EMBEDDING_MODEL_NAME': 'test-embed-model',
    'EMBEDDING_API_KEY': 'test-key',
    'EMBEDDING_BASE_URL': 'http://localhost:9/v1',
    'VLM_MODEL_NAME': 'test-vlm-model',
    'VLM_API_KEY': 'test-key',
    'VLM_BASE_URL': 'http://localhost:9/v1',
}


@pytest.fixture
def dummy_env(monkeypatch):
    for key, value in _DUMMY_ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def make_config(tmp_path, dummy_env):
    def _make(target_type: str = 'financial_company') -> Config:
        return Config(config_dict={
            'output_dir': str(tmp_path / 'outputs'),
            'target_name': 'pytest_target',
            'target_type': target_type,
            'reference_doc_path': 'src/template/report_template.docx',
            # Offline LLM entries; generation is never called in unit tests.
            'llm_config_list': [
                {
                    'model_name': 'deepseek-chat',
                    'api_key': 'test-key',
                    'base_url': 'http://localhost:9/v1',
                    'generation_params': {},
                },
                {
                    'model_name': 'qwen3-embedding',
                    'api_key': 'test-key',
                    'base_url': 'http://localhost:9/v1',
                },
            ],
        })
    return _make


@pytest.fixture
def memory(make_config):
    return Memory(make_config())


class _FakeTool:
    """Stand-in tool so BaseAgent skips DeepSearchAgent instantiation."""
    id = 'tool_fake_1'


@pytest.fixture
def make_report_generator(make_config, memory):
    from src.agents.report_generator.report_generator import ReportGenerator

    def _make(target_type: str = 'financial_company') -> ReportGenerator:
        return ReportGenerator(
            config=make_config(target_type),
            tools=[_FakeTool()],
            use_llm_name='deepseek-chat',
            enable_code=True,
            memory=memory,
        )

    return _make


@pytest.fixture
def report_generator(make_report_generator):
    return make_report_generator()


def make_tool_result(name: str, value=None) -> ToolResult:
    return ToolResult(
        name=name,
        description=f"description of {name}",
        data={"value": value if value is not None else 1},
        source="unit-test",
    )
