from copy import deepcopy
import json
import pytest

from tests.test_corporate_handoff import document
from tests.test_esg_v2 import run_esg, table_page, records_of
from src.extraction.corporate_handoff import convert_document
from src.extraction.corporate_handoff import _source_bytes_checked
from src.extraction.corporate_review import identify, recover_headcounts
from src.extraction.quality_report import extraction_quality
from src.extraction.financial_context_v2 import scope_candidate, resolve_scope
from scripts.run_extract_batch import _table_cells, _card_literals, copy_previous_capture
from scripts.docling_page_worker import needs_ocr


def test_conflicting_units_cannot_normalize(document):
    r = document['output']['records'][1]
    r['payload']['unit_source_labels_raw'] = ['triệu đồng', 'tỷ đồng']
    source = deepcopy(r['field_sources']['/payload/unit'][0])
    source['raw_text'] = 'tỷ đồng'
    r['field_sources']['/payload/unit'].append(source)
    h = convert_document(document)
    assert h['records'][0]['value']['normalized_value'] is None
    assert 'conflicting_observed_scale_labels' in h['records'][0]['quality']['uncertainty']


def test_duplicate_native_ids_block(document):
    document['output']['records'].append(deepcopy(document['output']['records'][0]))
    with pytest.raises(ValueError, match='DUPLICATE_NATIVE'):
        convert_document(document)


def test_other_page_year_does_not_establish_column(document):
    document['coverage']['pages'].append({'pdf_page': 2, 'status': 'processed'})
    document['output']['reports'][0]['pdf_page_count'] = 2
    document['output']['records'][1]['field_sources']['/content_period'][0]['pdf_page'] = 2
    period = convert_document(document)['records'][0]['period']
    assert period['year_basis'] == 'unknown'
    assert period['observation_year'] is None


def test_plan_actual_and_currency_table(tmp_path):
    _, output = run_esg(tmp_path, [table_page([
        ['Chỉ tiêu', 'Đơn vị', 'Thực hiện 2024', 'Kế hoạch 2025'],
        ['Lợi nhuận sau thuế hợp nhất', 'Tỷ VND', '591', '1000']])])
    rows = records_of(output, 'measurement')
    assert [r['payload']['unit'] for r in rows] == ['Tỷ VND', 'Tỷ VND']
    assert [r['payload']['assertion_kind'] for r in rows] == ['reported_result', 'target']
    assert [r['content_period']['year'] for r in rows] == [2024, 2025]


def test_metrics_do_not_merge_totals_and_subtotals():
    assert identify('Tổng tài sản (270 = 100 + 200)') == 'total_assets'
    assert identify('Vốn chủ sở hữu') == 'owners_equity'
    assert identify('Tổng tài sản ngắn hạn') is None
    assert identify('Vốn góp của chủ sở hữu') is None


def test_quality_is_not_accuracy_and_retains_exclusion_ledger(document):
    h = convert_document(document)
    native = deepcopy(document['output'])
    native['records'].append({'record_id': 'unmapped', 'record_type': 'unsupported'})
    q = extraction_quality([h], [native])
    assert q['precision'] is None and q['recall'] is None
    assert q['documents'][0]['excluded_native_records'][0]['record_id'] == 'unmapped'
    assert q['documents'][0]['report_year'] == h['document']['report_year']
    assert q['documents'][0]['source_document_type'] == h['document']['source_document_type']
    assert sum(group['records_exported'] for group in q['documents'][0]['dimensions'].values()) == len(h['records'])


def test_no_bsr_entity_in_other_company_recovery():
    h = {'document': {'report_type': 'Financial', 'reporting_entity': 'Example Company',
                     'source': {'sha256': 'a'*64}, 'financial_scope': 'Consolidated'},
         'records': [], 'issue_log': []}
    native = {'source_blocks': [{
        'original_text': 'Tổng số nhân viên của Công ty tại ngày 31 tháng 12 năm 2024 là 123.',
        'source': {'pdf_page': 1, 'native_json_pointer': '/document/texts/0'}}]}
    recover_headcounts(h, native)
    assert h['records'][0]['boundary']['reporting_entity'] == 'Example Company'
    assert h['records'][0]['boundary']['consolidation'] == 'unknown'


def test_exact_ocr_income_statement_title_establishes_reviewable_scope():
    title = {'label': 'text', 'block_id': 'ocr-title', 'source': {'pdf_page': 9},
             'original_text': 'BÁO CÁO KT QUÅ HOAT DNG KINH DOANH HP NHÃT'}
    assert scope_candidate(title)['scope'] == 'consolidated'
    assert scope_candidate({**title, 'original_text': 'BÁO CÁO KT QUÅ HOAT DNG KINH DOANH HP NHT'})['scope'] == 'consolidated'
    assert scope_candidate({**title, 'original_text': 'BÁO CÁO KT QUÅ HOAT DÔNG KINH DOANH HP NHÃT'})['scope'] == 'consolidated'
    assert scope_candidate({**title, 'original_text': title['original_text'] + ' theo thuyết minh'}) is None


def test_unique_statement_page_resolves_scope_when_scan_cover_has_none():
    cover = {'kind': 'texts', 'label': 'text', 'block_id': 'cover',
             'source': {'pdf_page': 1}, 'original_text': 'Công ty ví dụ'}
    title = {'kind': 'texts', 'label': 'text', 'block_id': 'statement',
             'source': {'pdf_page': 9},
             'original_text': 'BÁO CÁO KT QUÅ HOAT DNG KINH DOANH HP NHÃT'}
    bundle = {'source_blocks': [cover, title]}
    assert resolve_scope(cover, bundle)['value'] == 'consolidated'
    conflicting = {**title, 'block_id': 'separate', 'original_text': 'Báo cáo tài chính riêng'}
    assert resolve_scope(cover, {'source_blocks': [cover, title, conflicting]})['status'] == 'ambiguous'


def test_handoff_exposes_fallback_and_ocr_review_flags(document):
    for method, flag in [('pymupdf_native_text_and_tables_fallback', 'native_fallback_layout_needs_review'),
                         ('isolated_configured_ocr_single_scanned_page', 'ocr_transcription_needs_review')]:
        document['page_methods'] = {'1': {'read_method': method}}
        record = convert_document(document)['records'][0]
        assert flag in record['quality']['uncertainty']
        assert method in record['quality']['parser_name']


def test_non_bsr_official_host_requires_exact_config_and_matching_bytes(tmp_path):
    from src.extraction.source_v2 import file_hash
    pdf = tmp_path / 'publisher.pdf'
    pdf.write_bytes(b'%PDF-1.7\nsource-byte-identity')
    digest = file_hash(pdf)
    info = {'url': 'https://example.org/reports/company.pdf',
            'official_domains': ['example.org'],
            'verification': {'method': 'windows_https_download_and_sha256_match',
                             'downloaded_pdf': str(pdf)}}
    assert _source_bytes_checked(info, digest)
    assert not _source_bytes_checked({**info, 'url': 'https://example.org.evil/reports.pdf'}, digest)
    assert not _source_bytes_checked({**info, 'official_domains': 'example.org.evil'}, digest)


def test_table_cell_comparison_detects_merged_unit_cell():
    docling = {'tables': [{'data': {'table_cells': [{'text': 'Profit / VND'}, {'text': '591'}]}}]}
    literal = {'tables': [{'data': {'table_cells': [{'text': 'Profit'}, {'text': 'VND'}, {'text': '591'}]}}]}
    assert _table_cells(literal) > _table_cells(docling)


def test_scanned_page_tiled_into_image_strips_still_requires_ocr():
    import pymupdf
    class Page:
        rect = pymupdf.Rect(0, 0, 100, 100)
        def get_images(self, full=True):
            return [(i,) for i in range(10)]
        def get_image_rects(self, i):
            return [pymupdf.Rect(0, i * 10, 100, (i + 1) * 10)]
    assert needs_ocr(Page(), 'selectable footer stamp on a scanned financial statement')


def test_merged_kpi_card_number_can_trigger_reviewable_fallback():
    docling = {'texts': [{'text': 'Lợi nhuận sau thuế đạt'}, {'text': '5.217 tỷ đồng'}]}
    literal = {'texts': [{'text': 'Lợi nhuận sau thuế đạt'}, {'text': '5.217'}, {'text': 'tỷ đồng'}]}
    assert _card_literals(literal)[1] > _card_literals(docling)[1]
    assert _card_literals(literal)[0] == 1


def test_reuse_keeps_page_checkpoints_without_mutating_previous_run(tmp_path):
    previous = tmp_path / 'previous'
    capture = previous / 'capture' / 'r_source' / 'p_profile'
    (capture / 'pages').mkdir(parents=True)
    config = {'company_id': 'BSR', 'documents': []}
    (previous / 'config_snapshot.json').write_text(json.dumps(config), encoding='utf-8')
    (capture / 'source.pdf').write_bytes(b'%PDF-1.7 source bytes')
    (capture / 'pages/0001.json').write_text('{"status":"processed"}', encoding='utf-8')
    (capture / '.writer.lock').write_text('stale', encoding='utf-8')
    (capture / 'canonical.json').write_text('old aggregate', encoding='utf-8')
    destination = tmp_path / 'next'
    destination.mkdir()
    copy_previous_capture(previous, destination, config)
    reused = destination / 'capture/r_source/p_profile'
    assert (reused / 'pages/0001.json').read_text(encoding='utf-8') == '{"status":"processed"}'
    assert not (reused / '.writer.lock').exists()
    assert not (reused / 'canonical.json').exists()
    (reused / 'pages/0001.json').write_text('new', encoding='utf-8')
    assert (capture / 'pages/0001.json').read_text(encoding='utf-8') == '{"status":"processed"}'


def test_reuse_rejects_different_config(tmp_path):
    previous = tmp_path / 'previous'
    (previous / 'capture').mkdir(parents=True)
    (previous / 'config_snapshot.json').write_text(json.dumps({'company_id': 'BSR'}), encoding='utf-8')
    with pytest.raises(ValueError, match='differs'):
        copy_previous_capture(previous, tmp_path / 'next', {'company_id': 'OTHER'})


def test_reused_processed_pages_skip_reader(tmp_path):
    import pymupdf
    from src.extraction.source_v2 import capture_pdf
    pdf = tmp_path / 'source.pdf'
    with pymupdf.open() as document:
        document.new_page().insert_text((40, 40), 'One')
        document.save(pdf)
    previous = tmp_path / 'previous'
    config = {'company_id': 'BSR', 'documents': []}
    previous.mkdir()
    (previous / 'config_snapshot.json').write_text(json.dumps(config), encoding='utf-8')

    def first_reader(_path, _page):
        return {'status': 'processed', 'document': {'texts': [{'text': 'One', 'label': 'text', 'prov': []}]}}

    profile = {'engine': 'reuse-test'}
    capture_pdf(pdf, previous / 'capture', company_id='BSR', profile=profile, page_reader=first_reader)
    next_run = tmp_path / 'next'
    next_run.mkdir()
    copy_previous_capture(previous, next_run, config)

    def no_read(_path, _page):
        raise AssertionError('already processed page was reread')

    work = capture_pdf(pdf, next_run / 'capture', company_id='BSR', profile=profile,
                       page_reader=no_read, persist_interval=10)
    assert json.loads((work / 'canonical.json').read_text(encoding='utf-8'))['coverage']['counts'] == {'processed': 1}
