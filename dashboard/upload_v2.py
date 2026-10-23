"""Isolated upload orchestration for source capture + typed v2 parsers.

No database import, scoring, cross-run matching or verification is performed.
"""
import base64
import binascii
import json
from pathlib import Path
import re
import uuid
import unicodedata
from datetime import datetime, timezone, timedelta

from src.extraction.esg_v2 import extract_esg
from src.extraction.financial_v2 import extract_financial
from src.extraction.source_v2 import atomic_json, capture_pdf, file_hash, now, stable_id
from src.extraction.toolkit import build_document_spec, load_yaml


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def download_filename(result, *, timestamp=None, token=None):
    """Windows-safe descriptive name; naming never establishes verified metadata."""
    def slug(value, fallback='UNKNOWN'):
        text = unicodedata.normalize('NFKD', str(value or '').replace('đ', 'd').replace('Đ', 'D'))
        text = text.encode('ascii', 'ignore').decode().upper()
        return re.sub(r'[^A-Z0-9]+', '_', text).strip('_')[:32] or fallback

    def source_value(output, field, fallback=None):
        item = output.get('metadata', {}).get(field, {})
        return item.get('value') if item.get('status') == 'available' and item.get('value') is not None else fallback

    documents = result.get('documents', [])
    companies, types, years = set(), set(), set()
    for doc in documents:
        output = doc['output']
        report = output['reports'][0]
        companies.add(slug(source_value(output, 'ticker_from_pdf', report.get('company_id'))))
        kinds = {'financial_statements': 'BCTC', 'annual_report': 'BCTN', 'sustainability_report': 'ESG', 'ESG': 'ESG'}
        kind = source_value(output, 'report_type', report.get('report_type'))
        types.add(kinds.get(kind, slug(kind)))
        years.add(slug(source_value(output, 'reporting_year', report.get('reporting_year'))))
    def one(values, mixed):
        return next(iter(values)) if len(values) == 1 else mixed if values else 'UNKNOWN'
    parts = [one(companies, 'MULTI'), one(types, 'MIXED'), one(years, 'MULTI')]
    total = result.get('manifest', {}).get('document_count', len(documents))
    if len(documents) == 1 and total == 1 and parts[1] == 'BCTC':
        scope = source_value(documents[0]['output'], 'statement_scope')
        parts.append({'separate': 'RIENG', 'consolidated': 'HOPNHAT'}.get(scope, 'PHAMVI_UNKNOWN'))
    if total > 1:
        parts.append(f'BATCH{int(total):02d}')
    stamp = timestamp or datetime.now(timezone(timedelta(hours=7))).strftime('%Y%m%d_%H%M%S')
    suffix = slug(token or uuid.uuid4().hex[:8])[:8]
    return '_'.join(parts + ['extract_v2', slug(stamp), suffix]) + '.json'


def process_upload_v2(root, contents, filenames, company=None, year=None,
                      report_type=None, progress_callback=None, number_format='auto'):
    root = Path(root).resolve()
    if number_format not in ('auto', 'vi', 'en'):
        raise ValueError('Quy ước số không hợp lệ.')
    if not contents or not filenames or len(contents) != len(filenames):
        raise ValueError('Danh sách file tải lên không hợp lệ.')
    if len(contents) > 20:
        raise ValueError('Tối đa 20 file mỗi lần. Hãy chia thành nhiều lần tải.')
    if year is not None and (float(year) != int(year) or not 1900 <= int(year) <= 2100):
        raise ValueError('Năm báo cáo phải là số nguyên từ 1900 đến 2100.')
    config = load_yaml(root / 'config/extraction_toolkit.yml')
    parsed, total_bytes = [], 0
    batch = root / 'data/uploads' / uuid.uuid4().hex
    for index, (content, filename) in enumerate(zip(contents, filenames, strict=True)):
        name = str(filename).replace('\\', '/').split('/')[-1]
        if Path(name).suffix.lower() != '.pdf' or any(c in name for c in '<>:"|?*\x00') or re.match(r'^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])\.', name, re.I):
            raise ValueError('Tên file không hợp lệ; chỉ hỗ trợ PDF.')
        try:
            encoded = content.split(',', 1)[1]
            if len(encoded) > 140 * 1024 * 1024:
                raise ValueError(f'{name}: vượt quá 100 MB.')
            raw = base64.b64decode(encoded, validate=True)
        except (IndexError, AttributeError, binascii.Error) as exc:
            raise ValueError(f'{name}: dữ liệu tải lên không hợp lệ.') from exc
        total_bytes += len(raw)
        if len(raw) > 100 * 1024 * 1024 or total_bytes > 250 * 1024 * 1024:
            raise ValueError('Giới hạn 100 MB/file và 250 MB/lần tải.')
        if not raw.startswith(b'%PDF-'):
            raise ValueError(f'{name}: nội dung không phải PDF.')
        path = batch / str(index) / name
        try:
            spec = build_document_spec(path, config, company or None, int(year) if year else None, report_type or None)
        except ValueError as exc:
            raise ValueError(f'{name}: hãy nhập mã doanh nghiệp, năm và loại báo cáo. {exc}') from exc
        parsed.append((spec, raw))
    # All payloads/metadata validated before creating files. Each file has its
    # own output root, including separate/consolidated reports of the same year.
    batch.mkdir(parents=True)
    run = root / 'data/processed/uploads_v2' / batch.name
    run.mkdir(parents=True)
    documents, failures = [], []
    for index, (spec, raw) in enumerate(parsed):
        spec.source_path.parent.mkdir(parents=True)
        spec.source_path.write_bytes(raw)

        def emit(event):
            if progress_callback:
                progress_callback({**event, 'document_index': index + 1, 'document_total': len(parsed),
                                   'filename': spec.source_path.name})

        emit({'stage': 'document', 'completed_pages': 0, 'page_total': 0})
        workspace = None
        try:
            # Same PDF/profile/input metadata resumes across new upload jobs.
            # Scope is NOT inferred from filenames. Profile hash separates backends.
            cache_key = stable_id('input', spec.company_id, spec.report_type, spec.report_year)[-16:]
            capture_root = root / 'data/processed/capture_v2' / cache_key
            workspace = capture_pdf(spec.source_path, capture_root, company_id=spec.company_id,
                                    report_type=spec.report_type, report_year=spec.report_year,
                                    progress_callback=emit)
            bundle = read_json(workspace / 'canonical.json')
            coverage = bundle['coverage']
            emit({'stage': 'semantic_v2', 'completed_pages': coverage['counts'].get('processed', 0),
                  'page_total': coverage['total_pages']})
            if spec.report_type == 'financial_statements':
                output_path = extract_financial(workspace, number_format=number_format)
            else:
                output_path = extract_esg(workspace, number_format=number_format)
            output = read_json(output_path)
            documents.append({'document_index': index, 'filename': spec.source_path.name,
                              'workspace': str(workspace), 'output_path': str(output_path),
                              'capture_status': bundle['batch']['capture_status'],
                              'coverage': coverage, 'output': output})
        except Exception as exc:
            failures.append({'document_index': index, 'filename': spec.source_path.name,
                             'error': str(exc), 'workspace': str(workspace) if workspace else None})
        atomic_json(run / 'run_manifest.json', {'pipeline': 'source-typed-v2', 'created_at': now(),
                    'document_count': len(parsed), 'processed_documents': len(documents),
                    'documents': [{k: v for k, v in d.items() if k != 'output'} for d in documents],
                    'failures': failures, 'graph_ready': False})
    if progress_callback:
        progress_callback({'stage': 'export', 'document_index': len(parsed), 'document_total': len(parsed)})
    return {'status': 'completed', 'pipeline': 'source-typed-v2', 'run_directory': str(run),
            'manifest': read_json(run / 'run_manifest.json'), 'documents': documents,
            'graph_ready': False, 'semantic_status': 'partial'}


def export_result(result):
    """Portable native checkpoints keyed by artifact ID; source PDFs separately."""
    documents = []
    for document in result['documents']:
        work = Path(document['workspace']).resolve()
        output = document['output']
        native = {}
        for artifact in output['source_artifacts']:
            path = (work / artifact['path']).resolve()
            if not path.is_relative_to(work) or file_hash(path) != artifact['sha256']:
                raise ValueError('Nguồn đã thay đổi hoặc đường dẫn không an toàn. Hãy chạy lại.')
            if artifact['kind'] == 'page_checkpoint':
                native[artifact['artifact_id']] = read_json(path)
        documents.append({'document_index': document['document_index'], 'filename': document['filename'],
                          'capture_status': document['capture_status'], 'coverage': document['coverage'],
                          'output': output, 'native_artifacts': native})
    return {'schema_version': 'esg-upload/2.0.0', 'pipeline': 'source-typed-v2',
            'document_count': result['manifest']['document_count'], 'documents': documents,
            'failures': [{k: v for k, v in f.items() if k != 'workspace'} for f in result['manifest']['failures']],
            'graph_ready': False, 'semantic_status': 'partial',
            'source_note': 'PDFs downloaded separately; native_json_pointer resolves within native_artifacts[artifact_id]. No automatic verification or greenwashing verdict.'}


def record_rows(result):
    rows = []
    for doc in result['documents']:
        records = doc['output']['records']
        by_id = {r['record_id']: r for r in records}
        for record in records:
            payload = record['payload']
            metric = by_id.get(payload.get('metric_id') or payload.get('metric_record_id'), {})
            refs = list(record.get('field_sources', {}).values())
            sources = [source for group in refs for source in group]
            rows.append({'id': f"{doc['document_index']}:{record['record_id']}",
                         'file': doc['filename'], 'company': record.get('company_id'),
                         'type': record['record_type'],
                         'indicator': payload.get('row_label_raw') or payload.get('name_raw') or metric.get('original_text'),
                         'year': (record.get('content_period') or {}).get('year'),
                         'value': payload.get('value', payload.get('parsed_value')),
                         'unit': payload.get('unit'), 'page': sources[0].get('pdf_page') if sources else None,
                         'original_text': record['original_text'], 'status': record['review']['status']})
    return rows


def selected_source(result, row_id):
    for doc in result['documents']:
        for record in doc['output']['records']:
            if row_id == f"{doc['document_index']}:{record['record_id']}":
                anchors = set(record['source_refs'])
                return {'filename': doc['filename'], 'record': record,
                        'source_blocks': [b for b in doc['output']['source_blocks'] if b['block_id'] in anchors]}
    return None
