import ast
import json
from pathlib import Path
from types import SimpleNamespace

from test_saved_news import ASOF, artifacts, item
from saved_news import apply_saved_news_metadata, attach_saved_news_context, saved_news_status


def test_actual_post_metadata_assignment_preserves_supplied_source():
    source = Path(__file__).with_name('mvp_three.py')
    assignments = [node for node in ast.walk(ast.parse(source.read_text('utf-8'))) if isinstance(node, ast.Assign) and any(isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == 'result' and target.attr == 'data_sources' for target in node.targets)]
    assert len(assignments) == 1
    prepared = attach_saved_news_context(artifacts(), {'SYNTHETIC': [item()]}, ASOF)
    result = SimpleNamespace(data_sources='original source', raw_response='original raw')
    apply_saved_news_metadata(result, prepared.enhanced_context)
    compiled = compile(ast.fix_missing_locations(ast.Module(body=assignments, type_ignores=[])), str(source), 'exec')
    exec(compiled, dict(result=result, NOTICE='SYNTHETIC NOTICE'))
    assert prepared.enhanced_context['news_source_note'] in result.data_sources
    assert 'original source' in result.data_sources
    assert result.search_performed is False and result.raw_response == 'original raw'


def test_status_parent_serialization_and_legacy_state(tmp_path):
    attached = attach_saved_news_context(artifacts(), {'SYNTHETIC': [item()]}, ASOF)
    empty = attach_saved_news_context(artifacts(), {'SYNTHETIC': []}, ASOF)
    cases = [(attached.enhanced_context, 'saved_evidence_attached_not_searched'), (empty.enhanced_context, 'saved_evidence_empty_or_rejected_not_searched'), ({}, 'not_configured')]
    for index, (context, expected) in enumerate(cases):
        row = dict(symbol='SYNTHETIC', news=saved_news_status(context), real_POSTs=0)
        status = tmp_path / f'STATUS-{index}.json'
        status.write_text(json.dumps(row), encoding='utf-8')
        parent = dict(symbols=[json.loads(status.read_text('utf-8'))])
        assert json.loads(json.dumps(parent))['symbols'][0]['news'] == expected
    source = Path(__file__).with_name('mvp_three.py').read_text('utf-8')
    assert "'news':saved_news_status(contexts[-1])" in source
    assert "save(out/'STATUS.json',status)" in source and "rows.append(row)" in source


def test_missing_ticker_and_explicit_empty_are_audited_distinctly():
    missing = attach_saved_news_context(artifacts(), {}, ASOF).enhanced_context
    empty = attach_saved_news_context(artifacts(), {'SYNTHETIC': []}, ASOF).enhanced_context
    assert missing['saved_news_audit']['ticker_entry_present'] is False
    assert missing['saved_news_audit']['rejected'] == [dict(index=None, reason='ticker_entry_missing')]
    assert empty['saved_news_audit']['ticker_entry_present'] is True
    assert empty['saved_news_audit']['rejected'] == []
    assert saved_news_status(missing) == saved_news_status(empty)
    assert '事件风险未知' in missing['news_source_note']
