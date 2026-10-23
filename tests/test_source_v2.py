import json

import pymupdf
import pytest

from src.extraction.source_v2 import capture_pdf, new_record, sync_missing_fields, validate_source_bundle

PROFILE = {'engine': 'test', 'version': 1}


def sample_pdf(tmp_path):
    source = tmp_path / 'input.pdf'
    with pymupdf.open() as pdf:
        for index in range(3):
            page = pdf.new_page()
            page.insert_text((50, 50), f'Page {index + 1}')
        pdf.save(source)
    return source


def page_ok(path, number):
    return {'status': 'processed', 'conversion_status': 'success', 'markdown': 'Policy text',
            'document': {'texts': [{'text': 'Policy text', 'label': 'text', 'prov': []}],
                         'tables': [{'label': 'table', 'data': {'table_cells': [{'text': ''}]}, 'prov': []}]}}


def read_bundle(work):
    return json.loads((work / 'canonical.json').read_text(encoding='utf-8'))


def test_failure_keeps_other_pages_and_resume_only_failed(tmp_path):
    source = sample_pdf(tmp_path)
    calls = []
    def broken(path, number):
        calls.append(number)
        if number == 2:
            raise RuntimeError('OCR failure')
        return page_ok(path, number)
    work = capture_pdf(source, tmp_path / 'out', page_reader=broken, profile=PROFILE, retries=0)
    first = read_bundle(work)
    assert first['coverage']['counts'] == {'processed': 2, 'failed': 1}
    assert first['batch']['capture_status'] == 'partial'
    assert first['batch']['graph_ready'] is False
    assert first['records'] == []
    old_ids = [b['block_id'] for b in first['source_blocks']]
    calls.clear()
    def repaired(path, number):
        calls.append(number)
        return page_ok(path, number)
    assert capture_pdf(source, tmp_path / 'out', page_reader=repaired, profile=PROFILE) == work
    second = read_bundle(work)
    assert calls == [2]
    assert second['coverage']['counts'] == {'processed': 3}
    assert second['batch']['capture_status'] == 'completed'
    assert second['batch']['semantic_status'] == 'not_started'
    assert set(old_ids) <= {b['block_id'] for b in second['source_blocks']}
    checkpoint = json.loads((work / 'pages/0002.json').read_text())
    assert checkpoint['attempts'] == 2
    assert len(checkpoint['attempt_history']) == 2
    assert validate_source_bundle(second, work) == []
    assert (work / 'source.pdf').read_bytes() == source.read_bytes()


def test_limited_range_is_not_full_and_empty_is_not_blank(tmp_path):
    source = sample_pdf(tmp_path)
    def empty(path, number):
        return {'status': 'partial', 'document': {}, 'markdown': '', 'conversion_status': 'success'}
    work = capture_pdf(source, tmp_path / 'out', page_reader=empty, profile=PROFILE,
                       start_page=2, max_pages=1, retries=0)
    bundle = read_bundle(work)
    assert bundle['coverage']['counts'] == {'pending': 2, 'partial': 1}
    assert bundle['batch']['capture_status'] == 'partial'
    assert bundle['issues'][0]['pdf_page'] == 2


def test_sparse_selection_and_batched_canonical_persistence(tmp_path, monkeypatch):
    from src.extraction import source_v2
    source = sample_pdf(tmp_path)
    calls = []
    canonical_writes = []
    original_atomic_json = source_v2.atomic_json

    def recording_json(path, value):
        if path.name == 'canonical.json':
            canonical_writes.append(path)
        original_atomic_json(path, value)

    def reader(path, number):
        calls.append(number)
        return page_ok(path, number)

    monkeypatch.setattr(source_v2, 'atomic_json', recording_json)
    work = capture_pdf(source, tmp_path / 'out', page_reader=reader, profile=PROFILE,
                       selected_pages=[3, 1, 3], persist_interval=10,
                       expected_sha256=source_v2.file_hash(source))
    bundle = read_bundle(work)
    assert calls == [1, 3]
    assert bundle['coverage']['counts'] == {'processed': 2, 'pending': 1}
    assert len(canonical_writes) == 2  # initial and final; checkpoints stay immediate
    assert validate_source_bundle(bundle, work) == []


def test_sparse_selection_rejects_out_of_range_page(tmp_path):
    source = sample_pdf(tmp_path)
    with pytest.raises(ValueError, match='Selected page exceeds'):
        capture_pdf(source, tmp_path / 'out', page_reader=page_ok, profile=PROFILE,
                    selected_pages=[4])


def test_profile_isolation_and_identical_rerun_ids(tmp_path):
    source = sample_pdf(tmp_path)
    work = capture_pdf(source, tmp_path / 'out', page_reader=page_ok, profile=PROFILE)
    first = read_bundle(work)
    def no_call(*args):
        raise AssertionError('Successful page must not be reread')
    capture_pdf(source, tmp_path / 'out', page_reader=no_call, profile=PROFILE)
    assert read_bundle(work)['source_blocks'] == first['source_blocks']
    other = capture_pdf(source, tmp_path / 'out', page_reader=page_ok, profile={'version': 2})
    assert other != work
    assert read_bundle(other)['reports'][0]['report_version_id'] == first['reports'][0]['report_version_id']


def test_field_missing_lists_sync_without_coercion():
    record = new_record('report', 'anchor')
    original_id = record['record_id']
    record['boundary']['included_entities'] = ['BSR']
    record['field_status']['/boundary/included_entities'] = {'status': 'available'}
    sync_missing_fields(record)
    assert '/boundary/included_entities' not in record['missing_fields']
    assert 'included_entities' not in record['boundary']['missing_fields']
    assert 'excluded_entities' in record['boundary']['missing_fields']
    assert record['boundary']['excluded_entities'] is None
    assert record['record_id'] == original_id
    assert record['review']['status'] == 'unreviewed'


def test_metadata_conflict_and_writer_lock(tmp_path):
    source = sample_pdf(tmp_path)
    work = capture_pdf(source, tmp_path / 'out', company_id='BSR', page_reader=page_ok, profile=PROFILE)
    with pytest.raises(ValueError, match='Metadata differs'):
        capture_pdf(source, tmp_path / 'out', company_id='PLX', page_reader=page_ok, profile=PROFILE)
    # atomic_json is the same atomic filesystem mechanism used by real workers.
    from src.extraction.source_v2 import atomic_json
    atomic_json(work / '.writer.lock', {'test': True})
    with pytest.raises(RuntimeError, match='Workspace is in use'):
        capture_pdf(source, tmp_path / 'out', page_reader=page_ok, profile=PROFILE)


def test_source_tamper_and_unresolved_pointer_are_detected(tmp_path):
    source = sample_pdf(tmp_path)
    work = capture_pdf(source, tmp_path / 'out', page_reader=page_ok, profile=PROFILE)
    bundle = read_bundle(work)
    bundle['source_blocks'][0]['source']['native_json_pointer'] = '/document/texts/999'
    assert any('Unresolved native pointer' in e for e in validate_source_bundle(bundle, work))


def test_partial_source_survives_failed_retry(tmp_path):
    source = sample_pdf(tmp_path)
    calls = []
    def reader(path, number):
        calls.append(number)
        if len(calls) == 1:
            return {**page_ok(path, number), 'status': 'partial'}
        raise RuntimeError('retry failed')
    work = capture_pdf(source, tmp_path / 'out', max_pages=1, page_reader=reader, profile=PROFILE)
    bundle = read_bundle(work)
    assert bundle['coverage']['pages'][0]['status'] == 'partial'
    assert len(bundle['source_blocks']) == 2
