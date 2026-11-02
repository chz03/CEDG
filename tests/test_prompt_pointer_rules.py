"""Step 3 acceptance: pointer-writing rules present in every prompt variant,
and templates still format with the kwargs report_generator actually passes."""
import os

import yaml

PROMPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'src', 'agents', 'report_generator', 'prompts',
)

# kwargs _prepare_init_prompt passes to section templates
SECTION_KWARGS = dict(
    task='t', report_theme='t', section_description='s', data_api='d',
    data_info='i', max_iterations=5, target_language='Chinese (中文)',
)
# kwargs _final_polish passes
POLISH_KWARGS = dict(
    draft_report='d', reference_image='r', target_language='Chinese (中文)',
)

POINTER_MARKERS = ('[Source:E012]', '⟨VAR:', '[INFER]')


def _load(filename):
    with open(os.path.join(PROMPTS_DIR, filename), encoding='utf-8') as f:
        return yaml.safe_load(f)


def test_financial_company_and_industry_section_templates_format_and_carry_rules():
    for filename in ('financial_company_prompts.yaml', 'financial_industry_prompts.yaml'):
        prompts = _load(filename)
        # Both variants must format cleanly and contain the pointer rules.
        for key in ('section_writing', 'section_writing_wo_chart'):
            rendered = prompts[key].format(**SECTION_KWARGS)
            for marker in POINTER_MARKERS:
                assert marker in rendered, f'{filename}:{key} missing {marker}'


def test_financial_final_polish_preserves_pointer_tokens():
    for filename in ('financial_company_prompts.yaml', 'financial_industry_prompts.yaml'):
        prompts = _load(filename)
        rendered = prompts['final_polish'].format(**POLISH_KWARGS)
        assert 'Pointer-token preservation' in rendered
        for marker in ('⟨VAR:', '[Source:E…]'):
            assert marker in rendered


def test_general_macro_governance_carry_pointer_rules():
    # These templates reference {reference_data}/{reference_analysis} placeholders
    # that _prepare_init_prompt/_final_polish never supply (pre-existing upstream
    # quirk), so only check rule presence, not .format().
    for filename in ('general_prompts.yaml', 'financial_macro_prompts.yaml',
                     'governance_prompts.yaml'):
        prompts = _load(filename)
        combined = '\n'.join(
            prompts[key] for key in ('section_writing', 'section_writing_wo_chart',
                                     'final_polish') if prompts.get(key)
        )
        assert '[Source:E012]' in combined, f'{filename} missing E-ID citation rule'
        assert '⟨VAR:' in combined, f'{filename} missing VAR placeholder rule'
        assert '[INFER]' in combined, f'{filename} missing INFER rule'
        assert 'Pointer-token preservation' in combined, f'{filename} missing polish preservation rule'


def test_data_api_documents_set_var():
    for filename in ('financial_company_prompts.yaml', 'financial_industry_prompts.yaml',
                     'general_prompts.yaml'):
        prompts = _load(filename)
        assert '_set_var' in prompts['data_api'], f'{filename}: data_api lacks _set_var docs'
