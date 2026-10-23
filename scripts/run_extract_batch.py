"""Sequential, configurable PDF extraction; no LLM/API or external Graph ingestion."""
import argparse
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.extraction.source_v2 import capture_pdf, atomic_json, file_hash, default_profile, now
from src.extraction.isolated_page_reader import IsolatedPageReader
from src.extraction.native_pdf_fallback import read_native_page
from src.extraction.esg_v2 import extract_esg
from src.extraction.financial_v2 import extract_financial
from src.extraction.corporate_handoff import build_delivery
from src.extraction.corporate_review import identify


def _table_cells(document):
    return sum(len(table.get('data', {}).get('table_cells', []))
               for table in document.get('tables', []))


def _card_literals(document):
    lines = [(item.get('text') or '').strip() for item in document.get('texts', [])]
    labels = sum(identify(line) in {'profit_after_tax', 'profit_before_tax',
                                    'total_assets', 'owners_equity'} for line in lines)
    numbers = sum(bool(re.fullmatch(r'[0-9][0-9.,]*', line)) for line in lines)
    return labels, numbers


def copy_previous_capture(previous_run, destination, config):
    """Reuse page checkpoints from an identical prior batch in a new output folder."""
    previous_run = Path(previous_run).resolve()
    old_config = previous_run / 'config_snapshot.json'
    old_capture = previous_run / 'capture'
    if not old_config.is_file() or not old_capture.is_dir():
        raise ValueError('reuse source has no config snapshot or capture directory')
    if json.loads(old_config.read_text(encoding='utf-8')) != config:
        raise ValueError('reuse source config differs from this batch')
    if any(path.is_symlink() for path in old_capture.rglob('*')):
        raise ValueError('reuse source contains symlinks')
    if destination.is_relative_to(previous_run) or previous_run.is_relative_to(destination):
        raise ValueError('reuse source and destination must be separate runs')

    def ignore(_folder, names):
        return {name for name in names if name in {'page_workers', 'workers', '.writer.lock',
                                                     '.capture.guard', 'canonical.json', 'validation.json'}
                or name.endswith('.tmp')}

    shutil.copytree(old_capture, destination / 'capture', ignore=ignore)


def run(config_path, destination, engine='docling', fallback=False, timeout=120,
        checkpoint_interval=10, reuse_checkpoints_from=None):
    config_path, destination = Path(config_path).resolve(), Path(destination).resolve()
    config = json.loads(config_path.read_text(encoding='utf-8'))
    if destination.exists():
        raise ValueError('Choose a new output folder; existing runs are immutable.')
    if (engine not in ('docling', 'native') or timeout <= 0 or
            type(checkpoint_interval) is not int or checkpoint_interval < 1):
        raise ValueError('Invalid engine/timeout')
    if reuse_checkpoints_from is not None:
        previous = Path(reuse_checkpoints_from).resolve()
        if (not (previous / 'config_snapshot.json').is_file() or
                json.loads((previous / 'config_snapshot.json').read_text(encoding='utf-8')) != config):
            raise ValueError('reuse source config differs from this batch')
    destination.mkdir(parents=True)
    atomic_json(destination / 'config_snapshot.json', config)
    if reuse_checkpoints_from is not None:
        copy_previous_capture(reuse_checkpoints_from, destination, config)
    documents, failures, page_events = [], [], []
    profile = default_profile()
    profile.update(batch_extractor_version=1, requested_engine=engine,
                   native_fallback_allowed=fallback, page_timeout_seconds=timeout)
    sources = {}
    for entry in config['documents']:
        source = (config_path.parent / entry['pdf']).resolve()
        reader = None
        try:
            digest = file_hash(source)
            if digest != entry['sha256']:
                raise ValueError('SOURCE_SHA256_MISMATCH')
            if entry['report_type'] not in ('ESG', 'annual_report', 'financial_statements'):
                raise ValueError('Unsupported source report_type')
            sources[digest] = {'url': entry.get('url'), 'downloaded_at_utc': entry.get('downloaded_at_utc'),
                               'official_domains': entry.get('official_domains'),
                               'verification': entry.get('verification')}
            if engine == 'docling':
                reader = IsolatedPageReader(destination / 'workers', profile['ocr'],
                                            timeout=timeout, startup_timeout=timeout, mode='native_auto')

            def read(path, number):
                if engine == 'native':
                    result = read_native_page(path, number)
                else:
                    try:
                        result = reader(path, number)
                        if fallback and result['status'] == 'processed':
                            # Docling may produce prose while omitting a table
                            # found by the literal local parser. Keep the full
                            # Docling result in the checkpoint for comparison.
                            try:
                                literal = read_native_page(path, number)
                            except ValueError:
                                literal = None
                            card_labels, card_numbers = _card_literals(literal['document']) if literal else (0, 0)
                            _, docling_numbers = _card_literals(result['document'])
                            missed_cards = bool(card_labels and card_numbers > docling_numbers)
                            if (literal is not None and
                                    (missed_cards or len(literal['document'].get('tables', [])) >
                                     len(result['document'].get('tables', [])) or
                                     _table_cells(literal['document']) > _table_cells(result['document']))):
                                literal['docling_comparison'] = {
                                    'read_method': result.get('read_method'),
                                    'table_count': len(result['document'].get('tables', [])),
                                    'table_cell_count': _table_cells(result['document']),
                                    'standalone_card_numbers': docling_numbers,
                                    'document': result['document']}
                                literal['fallback_reason'] = ('docling_merged_card_values_detected_by_literal_parser'
                                                              if missed_cards else 'docling_missed_table_or_cells_detected_by_literal_parser')
                                result = literal
                    except Exception as exc:
                        if not fallback:
                            raise
                        result = read_native_page(path, number)
                        result['docling_failure'] = {'type': type(exc).__name__, 'message': str(exc)}
                page_events.append({'source_sha256': digest, 'physical_page': number,
                                    'status': result['status'], 'read_method': result.get('read_method'),
                                    'docling_failure': result.get('docling_failure'),
                                    'fallback_reason': result.get('fallback_reason'),
                                    'docling_table_count': result.get('docling_comparison', {}).get('table_count'),
                                    'docling_table_cell_count': result.get('docling_comparison', {}).get('table_cell_count'),
                                    'docling_standalone_card_numbers': result.get('docling_comparison', {}).get('standalone_card_numbers'),
                                    'selected_table_cell_count': _table_cells(result.get('document', {})),
                                    'selected_table_count': len(result.get('document', {}).get('tables', []))})
                atomic_json(destination / 'page_events.json', page_events)
                print(json.dumps(page_events[-1], ensure_ascii=True), flush=True)
                return result

            pages = entry.get('pages')
            if pages is not None and (not pages or any(type(p) is not int or p < 1 for p in pages)):
                raise ValueError('pages must be positive physical PDF page numbers')
            # Missing pages list explicitly means all physical pages.
            work = capture_pdf(source, destination / 'capture', company_id=config['company_id'],
                               report_type=entry['report_type'], report_year=entry['report_year'],
                               profile=profile, page_reader=read, retries=0,
                               selected_pages=pages, persist_interval=checkpoint_interval,
                               expected_sha256=digest)
            parse = extract_financial if entry['report_type'] == 'financial_statements' else extract_esg
            output_path = parse(work, number_format=entry.get('number_format', 'auto'))
            output = json.loads(output_path.read_text(encoding='utf-8'))
            bundle = json.loads((work / 'canonical.json').read_text(encoding='utf-8'))
            page_methods = {}
            for selected_page in pages or range(1, bundle['coverage']['total_pages'] + 1):
                checkpoint = work / 'pages' / f'{selected_page:04d}.json'
                if checkpoint.exists():
                    saved = json.loads(checkpoint.read_text(encoding='utf-8'))
                    page_methods[str(selected_page)] = {
                        'read_method': saved.get('read_method'),
                        'fallback_reason': saved.get('fallback_reason'),
                        'docling_failure': saved.get('docling_failure'),
                    }
            documents.append({'filename': source.name, 'workspace': str(work),
                              'output_path': str(output_path), 'coverage': bundle['coverage'],
                              'page_methods': page_methods, 'output': output})
        except Exception as exc:
            failures.append({'pdf': str(source), 'error_type': type(exc).__name__, 'message': str(exc)})
        finally:
            if reader:
                reader.close()
            atomic_json(destination / 'result.json', {'status': 'partial', 'documents': documents,
                        'failures': failures, 'graph_ready': False, 'created_at': now()})
    result = {'status': 'partial', 'documents': len(documents), 'failures': failures,
              'page_events': len(page_events), 'engine': engine, 'semantic_status': 'pending_human_review',
              'graph_ingested': False}
    if documents:
        try:
            result['delivery'] = build_delivery({'documents': documents}, destination / 'delivery',
                                                source_info=sources)
        except Exception as exc:
            result['delivery_error'] = {'type': type(exc).__name__, 'message': str(exc)}
    if not documents:
        result['status'] = 'failed'
    atomic_json(destination / 'run_report.json', result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--engine', choices=['docling', 'native'], default='docling')
    p.add_argument('--allow-native-fallback', action='store_true')
    p.add_argument('--page-timeout', type=float, default=120)
    p.add_argument('--checkpoint-interval', type=int, default=10,
                   help='Persist the growing canonical bundle every N pages; page checkpoints remain immediate')
    p.add_argument('--reuse-checkpoints-from', type=Path,
                   help='Copy verified capture checkpoints from an earlier run with identical config')
    a = p.parse_args()
    report = run(a.config, a.output, a.engine, a.allow_native_fallback,
                 a.page_timeout, a.checkpoint_interval, a.reuse_checkpoints_from)
    print(json.dumps(report, ensure_ascii=True))
    return 1 if report['status'] == 'failed' or report.get('delivery_error') or report['failures'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
