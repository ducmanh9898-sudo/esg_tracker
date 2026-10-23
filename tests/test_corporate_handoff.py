from copy import deepcopy
import json
from pathlib import Path

import pymupdf
import pytest

from src.extraction.corporate_handoff import build_delivery, convert_document, validator_module, CONTRACT, zip_delivery
from src.extraction.source_v2 import atomic_json, file_hash


@pytest.fixture
def document(tmp_path):
    work = tmp_path / 'native'
    work.mkdir()
    with pymupdf.open() as pdf:
        pdf.new_page()
        pdf.save(work / 'source.pdf')
    digest = file_hash(work / 'source.pdf')
    def ref(text, col):
        return {'artifact_id': 'page1', 'pdf_page': 1, 'raw_text': text,
                'row_index': 1, 'column_index': col, 'native_json_pointer': '/document/tables/0/data/table_cells/' + str(col)}
    metric = {'record_id': 'row-revenue', 'record_type': 'metric', 'original_text': 'Doanh thu thuần',
              'field_sources': {'/payload/original_name': [ref('Doanh thu thuần', 0)]}}
    measurement = {'record_id': 'revenue-2024-in-2025', 'record_type': 'measurement', 'domain': 'financial',
                   'original_text': '123', 'data_status': 'available', 'reported_entity': None,
                   'payload': {'metric_record_id': metric['record_id'], 'raw_value': '123', 'parsed_value': '123',
                               'unit': 'VND', 'scale': '1000000', 'unit_source_labels_raw': ['triệu đồng'],
                               'statement_scope': 'separate', 'statement_type': 'income_statement'},
                   'content_period': {'year': 2024, 'start_date': '2024-01-01', 'end_date': '2024-12-31', 'period_type': 'duration'},
                   'field_sources': {'/payload/raw_value': [ref('123', 2)], '/content_period': [ref('2024', 2)],
                                     '/payload/unit': [ref('triệu đồng', None)]},
                   'source_refs': [], 'interpretation_notes': []}
    report = {'report_version_id': 'report_' + digest, 'source_sha256': digest, 'reporting_year': 2025,
              'company_id': 'BSR', 'pdf_page_count': 1, 'report_type': 'financial_statements'}
    output = {'schema_version': 'esg-financial-candidates/2.3.0', 'reports': [report], 'source_blocks': [],
              'records': [metric, measurement], 'issues': [],
              'source_artifacts': [{'kind': 'pdf', 'path': 'source.pdf', 'sha256': digest}],
              'metadata': {'statement_scope': {'status': 'available', 'value': 'separate'}}}
    return {'filename': 'BSR_2025.pdf', 'workspace': str(work), 'output': output,
            'coverage': {'pages': [{'pdf_page': 1, 'status': 'processed'}], 'total_pages': 1}}


def test_financial_contract_comparative_year_unit_and_pending_review(document, tmp_path):
    h = convert_document(document)
    r = h['records'][0]
    assert h['document']['report_year'] == 2025
    assert r['period']['observation_year'] == 2024
    assert r['period']['year_basis'] == 'table_header'
    assert r['value']['normalized_value'] == 123000000
    assert r['value']['normalization_factor'] == 1000000
    assert r['value']['original_unit'] == 'triệu đồng'
    assert r['record_type'] == 'financial_measurement' and r['dimension'] == 'X'
    assert r['metric_id'] is None and r['metric_definition'] is None
    assert r['quality']['review_status'] == 'pending_human_review'
    assert r['boundary']['verified'] is False and r['boundary']['reporting_entity'] is None
    assert r['restatement']['status'] == 'unknown'
    path = tmp_path / 'h.json'
    atomic_json(path, h)
    v = validator_module()
    _, errors = v.validate_handoff(path, v.load_json(CONTRACT / 'schema.json'))
    assert errors == []


def test_missing_scope_is_blocked_not_invented(document):
    document['output']['metadata'] = {}
    with pytest.raises(ValueError, match='FINANCIAL_SCOPE_UNRESOLVED'):
        convert_document(document)


def test_attachment_lists_do_not_conflict_with_actual_pdf_scope(document):
    from src.extraction.financial_context_v2 import scope_candidate
    assert scope_candidate({'label': 'list_item', 'original_text': 'Báo cáo tài chính hợp nhất đã kiểm toán'}) is None
    output = document['output']
    output['metadata'] = {}
    output['source_blocks'] = [
        {'block_id': 'attached', 'kind': 'texts', 'label': 'list_item',
         'original_text': 'Báo cáo tài chính hợp nhất đã kiểm toán', 'source': {'pdf_page': 1}},
        {'block_id': 'actual-cover', 'kind': 'texts', 'label': 'section_header',
         'original_text': 'BÁO CÁO TÀI CHÍNH RIÊNG ĐÃ ĐƯỢC KIỂM TOÁN', 'source': {'pdf_page': 1}}]
    assert convert_document(document)['document']['financial_scope'] == 'Separate'


def test_unknown_units_missing_values_and_precision_are_not_faked(document):
    m = document['output']['records'][1]
    m['payload']['unit'] = None
    r = convert_document(document)['records'][0]
    # Remove the observed scale too; no base-unit default.
    m['payload']['unit_source_labels_raw'] = []
    r = convert_document(document)['records'][0]
    assert r['value']['normalized_value'] is None and r['value']['status'] == 'unknown'
    m['payload'].update(raw_value='-', parsed_value=None)
    m['original_text'] = '-'
    m['field_sources']['/payload/raw_value'][0]['raw_text'] = '-'
    assert convert_document(document)['records'][0]['value']['normalized_value'] is None
    m['payload'].update(raw_value='0.1234567890123456789', parsed_value='0.1234567890123456789', unit='VND', scale='1')
    m['original_text'] = m['payload']['raw_value']
    m['field_sources']['/payload/raw_value'][0]['raw_text'] = m['original_text']
    m['field_sources']['/payload/unit'] = [dict(m['field_sources']['/payload/unit'][0], raw_text='VND')]
    r = convert_document(document)['records'][0]
    assert r['value']['status'] == 'ambiguous' and r['value']['normalized_value'] is None


def test_context_year_is_not_marked_human_reviewed_and_no_restatement_assumption(document):
    m = document['output']['records'][1]
    m['field_sources']['/content_period'][0]['raw_text'] = 'Năm trước'
    m['payload']['restatement_status'] = 'not_labelled'
    r = convert_document(document)['records'][0]
    assert r['period']['year_basis'] == 'unknown'
    assert r['restatement']['status'] == 'unknown'


def test_interpretation_cannot_be_laundered_into_source_quote(document):
    document['output']['records'][1]['original_text'] = 'A generated interpretation not present in the source cell'
    h = convert_document(document)
    assert not h['records']
    assert any(i['code'] == 'QUOTE_NOT_IN_SOURCE_ANCHOR' for i in h['issue_log'])


def test_parsed_amount_must_match_literal_source_before_normalization(document):
    document['output']['records'][1]['payload']['parsed_value'] = '999'
    r = convert_document(document)['records'][0]
    assert r['value']['status'] == 'ambiguous'
    assert r['value']['normalized_value'] is None and r['value']['original_value'] == '123'


def test_adjustment_column_is_not_automatically_restatement(document):
    m = document['output']['records'][1]
    m['field_sources']['/content_period'][0]['raw_text'] = '2024 Điều chỉnh'
    assert convert_document(document)['records'][0]['restatement']['status'] == 'ambiguous'
    m['field_sources']['/content_period'][0]['raw_text'] = '2024 Trình bày lại'
    assert convert_document(document)['records'][0]['restatement']['status'] == 'restated'


def test_dividend_reference_year_and_wrong_column_do_not_become_observation_header(document):
    m = document['output']['records'][1]
    m['payload']['row_label_raw'] = 'Chia cổ tức năm 2022'
    m['content_period']['year'] = 2022
    m['field_sources']['/content_period'][0].update(raw_text='Chia cổ tức năm 2022', column_index=0)
    r = convert_document(document)['records'][0]
    assert r['period']['observation_year'] is None
    assert r['period']['observation_start'] is None
    assert r['period']['year_basis'] == 'unknown'


def test_esg_units_types_unknown_dimensions_and_no_metric_alias_join(document):
    out = document['output']
    out.update(schema_version='esg-candidates/2.1.0', metadata={})
    out['reports'][0]['report_type'] = 'ESG'
    m = out['records'][1]
    m.update(domain='esg', classification={'pillar': 'E', 'topic_candidates': []})
    m['payload'].update(unit='kgCO2e', scale='1', unit_source_labels_raw=[])
    m['field_sources']['/payload/unit'][0]['raw_text'] = 'kgCO2e'
    r = convert_document(document)['records'][0]
    assert r['value']['normalized_value'] == .123
    assert r['value']['normalized_unit'] == 'tCO2e'
    assert r['boundary']['consolidation'] == 'unknown'
    m['classification']['pillar'] = 'unknown'
    assert convert_document(document)['records'] == []


def test_delivery_checks_pdf_hash_manifest_nine_slots_and_zip(document, tmp_path):
    result = {'documents': [document, deepcopy(document)]}
    folder = tmp_path / 'delivery'
    summary = build_delivery(result, folder, expected_bsr=True)
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    assert len(manifest['files']) == 9
    assert summary['unavailable_slots'] == 8 and summary['partial_documents'] == 1
    assert summary['mechanical_valid'] and not summary['complete_handoff']
    assert len(list((folder / 'json').glob('*.json'))) == 1
    v = validator_module()
    assert v.main(['--manifest', str(folder / 'manifest.json'), '--pdf-dir', str(folder / 'pdf')]) == 0
    assert zip_delivery(folder).is_file()
    with pytest.raises(FileExistsError):
        build_delivery(result, folder)
    (folder / 'pdf' / document['filename']).write_bytes(b'corrupt')
    assert v.main(['--manifest', str(folder / 'manifest.json'), '--pdf-dir', str(folder / 'pdf')]) == 1


def test_blocked_documents_are_not_falsely_delivered(document, tmp_path):
    document['output']['metadata'] = {}
    summary = build_delivery({'documents': [document]}, tmp_path / 'blocked', expected_bsr=True)
    assert summary['blocked_documents'] == 1 and summary['unavailable_slots'] == 9
    assert not list((tmp_path / 'blocked/json').glob('*.json'))


def test_official_source_flag_requires_https_host_and_recomputed_file_hash(document):
    from src.extraction.corporate_handoff import _source_bytes_checked
    digest = document['output']['reports'][0]['source_sha256']
    info = {'url': 'https://bsr.com.vn/example.pdf', 'verification': {
        'method': 'windows_https_download_and_sha256_match',
        'downloaded_pdf': str(Path(document['workspace']) / 'source.pdf')}}
    assert _source_bytes_checked(info, digest)
    assert not _source_bytes_checked(info, 'f'*64)
    info['url'] = 'https://bsr.com.vn.evil.example/example.pdf'
    assert not _source_bytes_checked(info, digest)


def test_delivery_slot_uses_pdf_year_not_old_supplied_report_year(document):
    from scripts.export_corporate_handoff import bsr_slot
    output = document['output']
    output['reports'][0]['reporting_year'] = 2024
    output['metadata']['reporting_year'] = {'status': 'available', 'value': 2025}
    assert bsr_slot(document) == ('BSR', 2025, 'Financial', 'separate')
