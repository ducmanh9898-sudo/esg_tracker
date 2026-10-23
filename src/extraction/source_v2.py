"""Versioned source capture, not semantic ESG/financial extraction.

Checkpoints preserve successful pages and make failures resumable. IDs are stable
within the same PDF and extraction profile, not across segmentation changes.
"""
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import shutil
import tempfile
import subprocess
import time
from contextlib import contextmanager, ExitStack

import pymupdf

SCHEMA_VERSION = 'esg-source/2.0.0'
DATA_STATUSES = {'available', 'missing', 'ambiguous', 'not_applicable', 'unknown', 'extraction_failure'}


def now():
    return datetime.now(timezone.utc).isoformat()


def stable_id(kind, *parts):
    encoded = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return f'{kind}_{sha256(encoded.encode()).hexdigest()}'


def file_hash(path):
    digest = sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        for attempt in range(7):
            try:
                os.replace(temporary, path)
                break
            except PermissionError as exc:
                # Windows readers/virus scanners may briefly deny replacement.
                # Keep atomic semantics; never truncate the existing checkpoint.
                if os.name != 'nt' or getattr(exc, 'winerror', None) not in (5, 32, 33) or attempt == 6:
                    raise
                time.sleep(.02 * (2 ** attempt))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def default_profile():
    from src.extraction.docling_backend import ocr_profile
    packages = {}
    for name in ('docling', 'docling-core', 'docling-parse', 'pypdfium2', 'rapidocr', 'torch'):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    return {'engine': 'docling', 'packages': packages, 'capture_version': 1, 'statement_layout_recovery_version': 1,
            'native_fallback_version': 2,
            'pdf_backend': 'pypdfium2',
            'ocr': ocr_profile(),
            'table_mode': 'accurate', 'cell_matching': True,
            'page_worker_protocol_version': 1, 'page_timeout_seconds': 180}


def _docling_page(path, number, converter):
    result = converter.convert(str(path), page_range=(number, number), raises_on_error=True)
    status = getattr(result.status, 'value', str(result.status)).lower()
    native = result.document.export_to_dict()
    text = result.document.export_to_markdown()
    # Successful conversion can still miss content. Empty is NOT confirmed blank.
    complete = status == 'success' and bool(text.strip() or native.get('tables'))
    return {'status': 'processed' if complete else 'partial', 'conversion_status': status,
            'document': native, 'markdown': text}


def _ocr_docling_page(path, number, converter, ocr):
    """Tesseract language OCR -> searchable page -> Docling layout/tables.

    No blind OSD rotation. Render orientation follows the PDF. The searchable
    page is fitted back to the exact original page size before table inference.
    Original PDF/checkpoints from other profiles remain untouched.
    """
    with tempfile.TemporaryDirectory(prefix='esg_ocr_') as folder:
        folder = Path(folder)
        with pymupdf.open(path) as original:
            page = original[number - 1]
            rect = page.rect
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(ocr['scale'], ocr['scale']), alpha=False)
            pixmap.set_dpi(round(72 * ocr['scale']), round(72 * ocr['scale']))
            image_path = folder / 'page.png'
            pixmap.save(image_path)
        stem = folder / 'ocr'
        subprocess.run([ocr['tesseract_cmd'], str(image_path), str(stem), '--tessdata-dir', ocr['path'],
                        '-l', '+'.join(ocr['lang']), '--psm', '3', 'pdf'], check=True, capture_output=True, timeout=180)
        fitted_path = folder / 'source_page.pdf'
        with pymupdf.open(stem.with_suffix('.pdf')) as search, pymupdf.open() as fitted:
            target = fitted.new_page(width=rect.width, height=rect.height)
            target.show_pdf_page(target.rect, search, 0)
            fitted.save(fitted_path)
        captured = _docling_page(fitted_path, 1, converter)
        from src.extraction.financial_layout_recovery import recover_statement_table
        with pymupdf.open(fitted_path) as searchable:
            recovered = recover_statement_table(captured['document'], searchable[0].get_text('words'), rect.height)
        captured['statement_layout_recovery'] = recovered
        captured['preprocessing'] = {'method': 'tesseract_pdf_then_docling', 'pdf_page': number,
            'source_sha256': file_hash(path), 'ocr_profile': ocr, 'original_page_size': [rect.width, rect.height],
            'orientation_policy': 'PDF render; no automatic OSD rotation; rotated scan content requires review.'}
        return captured


def source_blocks(report_id, profile_id, page_number, native, artifact_id, artifact_hash):
    blocks = []
    for collection in ('texts', 'tables', 'pictures', 'key_value_items', 'form_items'):
        for index, item in enumerate(native.get(collection, [])):
            pointer = f'/{collection}/{index}'
            anchor_id = stable_id('anchor', report_id, profile_id, page_number, pointer)
            blocks.append({'block_id': anchor_id, 'report_version_id': report_id,
                           'kind': collection, 'label': item.get('label'),
                           'original_text': item.get('text'),
                           'original_cells': item.get('data', {}).get('table_cells') if collection == 'tables' else None,
                           'source': {'artifact_id': artifact_id, 'artifact_sha256': artifact_hash,
                                      'native_json_pointer': '/document' + pointer,
                                      'pdf_page': page_number, 'printed_page': None,
                                      'native_provenance': item.get('prov', [])},
                           'disposition': 'pending_semantic_extraction'})
    return blocks


def new_record(report_id, anchor_id, record_type='unknown', slot='0'):
    """Foundation envelope; semantic parsers populate fields in a later phase."""
    record = {'record_id': stable_id('record', report_id, anchor_id, record_type, slot),
              'report_version_id': report_id, 'record_type': record_type,
              'company_id': None, 'reported_entity': None, 'domain': 'unknown',
              'original_text': None, 'original_cells': None, 'source_refs': [anchor_id],
              'interpretation_notes': [], 'content_period': None,
              'classification': {'pillar': 'unknown', 'topic_candidates': []},
              'boundary': {'included_entities': None, 'excluded_entities': None,
                           'consolidation_method': None, 'missing_fields': []},
              'payload': {}, 'data_status': 'unknown',
              'field_status': {}, 'missing_fields': [],
              'review': {'status': 'unreviewed', 'verified_fields': []}}
    for pointer in ('/company_id', '/reported_entity', '/content_period',
                    '/boundary/included_entities', '/boundary/excluded_entities',
                    '/boundary/consolidation_method'):
        record['field_status'][pointer] = {'status': 'unknown', 'reason': 'Not yet extracted from source.'}
    sync_missing_fields(record)
    return record


def sync_missing_fields(record):
    """Derive both lists from field statuses and values; never coerce null to zero."""
    missing = []
    for pointer, state in record['field_status'].items():
        if state['status'] not in DATA_STATUSES:
            raise ValueError(f'Unknown data status: {state["status"]}')
        value = record
        for token in pointer.lstrip('/').split('/'):
            value = value[token.replace('~1', '/').replace('~0', '~')]
        if value is None and state['status'] != 'not_applicable':
            missing.append(pointer)
    record['missing_fields'] = sorted(missing)
    record['boundary']['missing_fields'] = sorted(p.rsplit('/', 1)[-1] for p in missing if p.startswith('/boundary/'))


@contextmanager
def workspace_lock(work):
    """OS-held lock releases on native crash; legacy ownerless locks stay intact."""
    marker = work / '.writer.lock'
    guard = (work / '.capture.guard').open('a+b')
    locked = False
    try:
        guard.seek(0, os.SEEK_END)
        if guard.tell() == 0:
            guard.write(b'0')
            guard.flush()
        guard.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(guard.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(guard.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as exc:
            raise RuntimeError(f'Workspace is in use: {work}') from exc
        if marker.exists():
            try:
                previous = json.loads(marker.read_text(encoding='utf-8'))
            except (ValueError, OSError):
                previous = {}
            if previous.get('lock_protocol') != 'os_guard_v1':
                raise RuntimeError(f'Workspace is in use: {marker}. Legacy lock requires explicit owner verification.')
            # Acquired OS guard proves no new-protocol writer still holds it.
        atomic_json(marker, {'lock_protocol': 'os_guard_v1', 'pid': os.getpid(), 'started_at': now()})
        try:
            yield
        finally:
            marker.unlink(missing_ok=True)
    finally:
        if locked:
            guard.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(guard.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(guard.fileno(), fcntl.LOCK_UN)
        guard.close()


def capture_pdf(source, output_root, *, company_id=None, report_type=None, report_year=None,
                max_pages=None, start_page=1, retries=1, progress_callback=None,
                page_reader=None, profile=None, selected_pages=None,
                persist_interval=1, expected_sha256=None):
    """Capture selected pages; default full PDF. Reuse successful checkpoints.

    page_reader/profile injection is for deterministic tests. Never mark semantic
    extraction complete here. This is a single-writer workspace guarded by a lock.
    """
    source = Path(source).resolve()
    if (retries < 0 or start_page < 1 or (max_pages is not None and max_pages < 1)
            or type(persist_interval) is not int or persist_interval < 1):
        raise ValueError('Invalid page range or retry count.')
    if selected_pages is not None:
        selected_pages = tuple(selected_pages)
        if (start_page != 1 or max_pages is not None or not selected_pages or
                any(type(page) is not int or page < 1 for page in selected_pages)):
            raise ValueError('selected_pages must be positive PDF page numbers and cannot be combined with a range.')
    if expected_sha256 is not None and (not isinstance(expected_sha256, str) or
                                        len(expected_sha256) != 64 or
                                        any(ch not in '0123456789abcdef' for ch in expected_sha256)):
        raise ValueError('expected_sha256 must be a lowercase SHA-256 digest.')
    # The caller may have just hashed the source. The copied PDF is still hashed
    # below, so changing bytes between the two operations cannot enter capture.
    digest = expected_sha256 or file_hash(source)
    report_id = 'report_' + digest
    profile = profile or default_profile()
    profile_id = stable_id('profile', profile)
    root = Path(output_root).resolve()
    legacy = root / report_id / profile_id
    # Compact storage names only; full source/profile IDs remain in artifacts.
    # Preserve existing checkpoints and reject any shortened-key collision.
    work = legacy if legacy.exists() else root / ('r_' + digest[:24]) / ('p_' + profile_id.split('_', 1)[1][:24])
    if (work / 'profile.json').exists() and json.loads((work / 'profile.json').read_text(encoding='utf-8')) != profile:
        raise ValueError('Profile storage collision; refusing checkpoint overwrite.')
    work.mkdir(parents=True, exist_ok=True)
    with workspace_lock(work), ExitStack() as cleanup:
        return _capture(source, work, digest, report_id, profile, profile_id,
                        company_id, report_type, report_year, max_pages, start_page,
                        retries, progress_callback, page_reader, cleanup,
                        selected_pages, persist_interval)


def _capture(source, work, digest, report_id, profile, profile_id, company_id,
             report_type, report_year, max_pages, start_page, retries, callback, reader, cleanup,
             selected_pages, persist_interval):
    original = work / 'source.pdf'
    if not original.exists():
        shutil.copyfile(source, original)
    if file_hash(original) != digest:
        raise ValueError('Source snapshot hash mismatch; use a clean output workspace.')
    with pymupdf.open(original) as pdf:
        total = len(pdf)
    if start_page > total:
        raise ValueError('Start page exceeds PDF page count.')
    if selected_pages is not None:
        if max(selected_pages) > total:
            raise ValueError('Selected page exceeds PDF page count.')
        selected = set(selected_pages)
    else:
        selected = set(range(start_page, min(total + 1, start_page + max_pages) if max_pages else total + 1))
    inventory_path = work / 'inventory.json'
    inventory = {'report_version_id': report_id, 'source_filename': source.name,
                 'source_sha256': digest, 'source_access': 'source.pdf',
                 'company_id': company_id, 'report_type': report_type, 'reporting_year': report_year,
                 'metadata_origin': 'user_supplied_or_unknown', 'report_scope': None,
                 'publication_date': None, 'pdf_page_count': total}
    if inventory_path.exists():
        stored = json.loads(inventory_path.read_text(encoding='utf-8'))
        for field in ('company_id', 'report_type', 'reporting_year'):
            if inventory[field] is not None and inventory[field] != stored.get(field):
                raise ValueError(f'Metadata differs from checkpoint inventory: {field}')
        inventory = stored
    else:
        atomic_json(inventory_path, inventory)
    atomic_json(work / 'profile.json', profile)
    isolated = None
    ledger = []
    issues = []
    artifacts = [{'artifact_id': stable_id('artifact', report_id, 'pdf'),
                  'path': 'source.pdf', 'sha256': digest, 'kind': 'pdf'}]
    coverage = []
    attempt_id = stable_id('attempt', now(), os.urandom(8).hex())

    def persist():
        counts = dict(Counter(p['status'] for p in coverage))
        capture_complete = len(coverage) == total and counts.get('processed', 0) == total
        batch = {'schema_version': SCHEMA_VERSION, 'capture_status': 'completed' if capture_complete else 'partial',
                 'semantic_status': 'not_started', 'graph_ready': False,
                 'profile_id': profile_id, 'attempt_id': attempt_id, 'updated_at': now(),
                 'record_count': 0, 'block_count': len(ledger), 'issue_count': len(issues)}
        bundle = {'batch': batch, 'companies': [], 'reports': [inventory],
                  'source_artifacts': artifacts, 'source_blocks': ledger, 'records': [],
                  'evidence': [], 'links': [], 'coverage': {'total_pages': total, 'counts': counts, 'pages': coverage},
                  'issues': issues}
        atomic_json(work / 'canonical.json', bundle)
        return bundle

    # Coverage includes all pages even for a limited smoke test or an interrupted run.
    for number in range(1, total + 1):
        coverage.append({'pdf_page': number, 'status': 'pending', 'attempts': 0})
    persist()
    for number in range(1, total + 1):
        checkpoint = work / 'pages' / f'{number:04d}.json'
        saved = json.loads(checkpoint.read_text(encoding='utf-8')) if checkpoint.exists() else None
        if saved and (saved['report_version_id'] != report_id or saved['profile_id'] != profile_id
                      or saved['pdf_page'] != number):
            raise ValueError(f'Checkpoint identity mismatch: {checkpoint}')
        if number in selected and (not saved or saved['status'] != 'processed'):
            attempts = saved.get('attempts', 0) if saved else 0
            history = saved.get('attempt_history', []) if saved else []
            partial_result = saved if saved and saved['status'] == 'partial' else None
            for _ in range(retries + 1):
                attempts += 1
                if callback:
                    callback({'stage': 'source_v2', 'page': number, 'page_total': total,
                              'completed_pages': sum(p['status'] == 'processed' for p in coverage)})
                try:
                    if reader:
                        result = reader(original, number)
                    else:
                        if isolated is None:
                            from src.extraction.isolated_page_reader import IsolatedPageReader
                            isolated = IsolatedPageReader(work / 'page_workers', profile.get('ocr', {}),
                                                          timeout=profile.get('page_timeout_seconds', 180))
                            cleanup.callback(isolated.close)
                        result = isolated(original, number)
                    if result['status'] not in ('processed', 'partial'):
                        raise ValueError('Invalid page reader status.')
                    saved = dict(result)
                    if saved['status'] == 'partial':
                        partial_result = saved.copy()
                    error = None
                except Exception as exc:
                    error = {'type': type(exc).__name__, 'message': str(exc)}
                    saved = {**partial_result, 'last_retry_error': error} if partial_result else {'status': 'failed', 'error': error}
                history.append({'attempt_id': attempt_id, 'at': now(), 'status': saved['status'], 'error': error})
                saved.update({'report_version_id': report_id, 'profile_id': profile_id, 'pdf_page': number,
                              'attempts': attempts, 'attempt_history': history})
                atomic_json(checkpoint, saved)
                if saved['status'] == 'processed':
                    break
        row = coverage[number - 1]
        if saved:
            row.update({'status': saved['status'], 'attempts': saved['attempts']})
            artifact_id = stable_id('artifact', report_id, profile_id, number)
            artifact_digest = file_hash(checkpoint)
            artifacts.append({'artifact_id': artifact_id, 'path': checkpoint.relative_to(work).as_posix(),
                              'sha256': artifact_digest, 'kind': 'page_checkpoint'})
            ledger.extend(source_blocks(report_id, profile_id, number, saved.get('document', {}),
                                        artifact_id, artifact_digest))
            if saved['status'] != 'processed':
                issues.append({'issue_id': stable_id('issue', report_id, profile_id, number, 'page'),
                               'record_id': None, 'pdf_page': number, 'field': '/coverage',
                               'code': 'PAGE_FAILURE' if saved['status'] == 'failed' else 'PAGE_PARTIAL',
                               'status': 'open', 'details': saved.get('error') or 'Empty/partial conversion; not confirmed blank.'})
        # Page checkpoints are written atomically immediately. Rebuilding the
        # growing canonical bundle on every page has quadratic serialization
        # cost; the final bundle is always persisted and validated below.
        if number % persist_interval == 0:
            persist()
        if callback:
            callback({'stage': 'source_v2', 'page': number, 'page_total': total,
                      'completed_pages': sum(p['status'] == 'processed' for p in coverage),
                      'finished_pages': sum(p['status'] != 'pending' for p in coverage),
                      'page_status': row['status']})
    bundle = persist()
    schema = Path(__file__).resolve().parents[2] / 'contracts' / 'source_v2.schema.json'
    from jsonschema import Draft202012Validator
    errors = [e.message for e in Draft202012Validator(json.loads(schema.read_text(encoding='utf-8'))).iter_errors(bundle)]
    errors.extend(validate_source_bundle(bundle, work))
    atomic_json(work / 'validation.json', {'schema_version': SCHEMA_VERSION, 'schema_valid': not errors,
                                         'errors': errors, 'semantic_validation': 'not_started', 'graph_ready': False})
    if errors:
        raise ValueError('Source capture contract validation failed: ' + '; '.join(errors))
    return work


def validate_source_bundle(bundle, work):
    """Checks JSON Schema cannot express: references, counts and source hashes."""
    errors = []
    coverage = bundle['coverage']
    pages = coverage['pages']
    if [p['pdf_page'] for p in pages] != list(range(1, coverage['total_pages'] + 1)):
        errors.append('Coverage must contain each PDF page exactly once.')
    if dict(Counter(p['status'] for p in pages)) != coverage['counts']:
        errors.append('Coverage counts mismatch.')
    artifacts = {a['artifact_id']: a for a in bundle['source_artifacts']}
    ids = [a['artifact_id'] for a in bundle['source_artifacts']] + [b['block_id'] for b in bundle['source_blocks']]
    if len(ids) != len(set(ids)):
        errors.append('Duplicate source IDs.')
    loaded = {}
    for artifact_id, artifact in artifacts.items():
        path = (work / artifact['path']).resolve()
        if not path.is_relative_to(work.resolve()) or not path.is_file():
            errors.append(f'Missing or unsafe source artifact: {artifact_id}')
        elif file_hash(path) != artifact['sha256']:
            errors.append(f'Source hash mismatch: {artifact_id}')
        elif artifact['kind'] == 'page_checkpoint':
            loaded[artifact_id] = json.loads(path.read_text(encoding='utf-8'))
    for block in bundle['source_blocks']:
        source = block['source']
        artifact = artifacts.get(source['artifact_id'])
        if not artifact or artifact['sha256'] != source['artifact_sha256']:
            errors.append(f'Broken source reference: {block["block_id"]}')
            continue
        try:
            target = loaded[source['artifact_id']]
            for token in source['native_json_pointer'].lstrip('/').split('/'):
                token = token.replace('~1', '/').replace('~0', '~')
                target = target[int(token)] if isinstance(target, list) else target[token]
            if source['pdf_page'] != loaded[source['artifact_id']]['pdf_page']:
                errors.append('Source page mismatch.')
            if block['original_text'] != target.get('text'):
                errors.append('Source text mismatch.')
            if block['original_cells'] is not None and block['original_cells'] != target.get('data', {}).get('table_cells'):
                errors.append('Source table cells mismatch.')
        except (KeyError, IndexError, ValueError, TypeError):
            errors.append(f'Unresolved native pointer: {block["block_id"]}')
    for field, actual in (('record_count', len(bundle['records'])), ('block_count', len(bundle['source_blocks'])), ('issue_count', len(bundle['issues']))):
        if bundle['batch'][field] != actual:
            errors.append(f'{field} mismatch.')
    return errors
