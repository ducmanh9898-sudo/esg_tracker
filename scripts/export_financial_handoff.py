"""Portable one-JSON-per-BCTC handoff with source checkpoints and batch manifest."""
import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.extraction.financial_v2 import extract_financial, validate_financial
from src.extraction.source_v2 import atomic_json, file_hash, now


def summary(output):
    measurements = [r for r in output['records'] if r['record_type'] == 'measurement']
    return {'counts': output['counts'],
            'capture_pages': output['source_capture_coverage']['counts'],
            'semantic_status': output['semantic_status'],
            'measurement_nulls': dict(Counter(key for r in measurements for key, value in (
                ('period', r['content_period']), ('unit', r['payload']['unit']),
                ('parsed_value', r['payload']['parsed_value']), ('statement_scope', r['payload']['statement_scope'])) if value is None)),
            'issue_counts': dict(Counter(i['code'] for i in output['issues'])),
            'arithmetic_checks': dict(Counter(c['status'] for c in output.get('arithmetic_checks', [])))}


def export(workspaces, destination, number_format='auto', baseline=None):
    destination = Path(destination).resolve()
    # Refuse to overwrite a prior delivery or user-supplied data.
    destination.mkdir(parents=True, exist_ok=False)
    entries = []
    for workspace in workspaces:
        work = Path(workspace).resolve()
        parsed = extract_financial(work, number_format=number_format)
        output = json.loads(parsed.read_text(encoding='utf-8'))
        report = output['reports'][0]
        folder = destination / report['report_version_id']
        folder.mkdir()
        for artifact in output['source_artifacts']:
            path = Path(artifact['path'])
            target = (folder / path).resolve()
            if path.is_absolute() or not target.is_relative_to(folder):
                raise ValueError('Unsafe source artifact path')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(work / path, target)
            if file_hash(target) != artifact['sha256']:
                raise ValueError('Copied source artifact hash mismatch')
        for name in ('canonical.json', 'profile.json', 'inventory.json'):
            shutil.copyfile(work / name, folder / name)
        filename = Path(report['source_filename']).stem + '.json'
        atomic_json(folder / filename, output)
        integrity = validate_financial(output, folder)
        if integrity or not output['validation']['valid']:
            raise ValueError('Export validation failed: ' + '; '.join(integrity))
        result = summary(output)
        result['validation'] = output['validation']
        atomic_json(folder / 'validation_summary.json', result)
        entries.append({'report_version_id': report['report_version_id'],
            'company_from_pdf': output['metadata']['company_name'],
            'ticker_from_pdf': output['metadata']['ticker_from_pdf'],
            'report_type': output['metadata']['report_type'],
            'statement_scope': output['metadata']['statement_scope'],
            'period_start': output['metadata']['period_start'], 'period_end': output['metadata']['period_end'],
            'presentation_currency': output['metadata']['presentation_currency'],
            'supplied_metadata': output['metadata']['supplied_metadata'],
            'json_path': (folder / filename).relative_to(destination).as_posix(),
            'json_sha256': file_hash(folder / filename),
            'source_pdf_path': (folder / 'source.pdf').relative_to(destination).as_posix(),
            'source_pdf_filename': report['source_filename'], 'source_pdf_sha256': report['source_sha256'],
            'pdf_page_count': report['pdf_page_count'], 'capture_status': 'completed' if result['capture_pages'].get('processed') == report['pdf_page_count'] else 'partial',
            'semantic_status': output['semantic_status'], 'summary': result})
    manifest = {'schema_version': 'financial-handoff/1.0', 'created_at': now(),
        'purpose': 'Analytical support and source review; not an audit or greenwashing accusation.',
        'documents': entries}
    atomic_json(destination / 'manifest.json', manifest)
    if baseline:
        previous = json.loads(Path(baseline).read_text(encoding='utf-8'))
        old = [summary(d['output']) for d in previous.get('documents', [])]
        atomic_json(destination / 'baseline_comparison.json', {'baseline_filename': Path(baseline).name,
            'baseline_sha256': file_hash(baseline), 'before': old, 'after': [e['summary'] for e in entries],
            'id_policy': 'Source/record IDs are stable within identical PDF/profile/native anchors. New OCR segmentation changes IDs; baseline JSON remains untouched. Report SHA links versions.'})
    shutil.copyfile(ROOT / 'contracts/financial_v2.schema.json', destination / 'financial.schema.json')
    # This generated README describes the actual manifest; never asserts full semantics.
    readme = '''# Bàn giao trích xuất BCTC

- `manifest.json`: danh mục báo cáo, kỳ/phạm vi có dẫn nguồn, đường dẫn và SHA-256.
- Mỗi thư mục `report_<sha>` chứa một JSON BCTC, `source.pdf` nguyên bản,
  `canonical.json`, cấu hình và `pages/*.json` (OCR, bố cục, bảng/cell gốc).
- `validation_summary.json`: số lượng, trường null, lỗi cần rà soát, kiểm tra cộng tổng.
- `baseline_comparison.json`: so sánh bản upload cũ nếu được cung cấp.
- `financial.schema.json`: hợp đồng cấu trúc; validation không xác nhận số liệu đúng.

## Cách đọc JSON

`metadata` phân biệt chứng cứ PDF với thông tin đầu vào chưa kiểm chứng.
`records` gồm metric (hàng), measurement (ô số) và financial_context (đoạn thuyết minh).
`field_sources` có trang PDF 1-based, trang in nếu đọc được, bbox, SHA và JSON pointer
trong checkpoint. `original_text`/`raw_value` giữ nguyên OCR, không phải bản chép tay
đã được xác nhận. `parsed_value` là chuỗi decimal chính xác; null/dấu gạch không là 0.
`normalized_value` = parsed_value × scale khi đã xác định được đơn vị.
`content_period` phân biệt thời điểm với khoảng thời gian; các kỳ tương đối phải
có bằng chứng ngày/kỳ từ PDF, không mặc định theo năm nhập vào.

`semantic_coverage.pages/tables/notes` và `unmapped_numeric_cells` cho biết phần chưa
ánh xạ. Một bảng không có measurement vẫn được giữ trong source_blocks/checkpoint.
Bảng mục lục không được chuyển thành số liệu tài chính. Bảng được phục hồi theo
tọa độ OCR có `layout_recovery` trong checkpoint và vẫn cần rà soát.

`semantic_status: partial`, `graph_ready: false`, `needs_review` là chủ ý.
Đọc đủ trang KHÔNG đồng nghĩa trích xuất đúng/đủ mọi trường. Các ô bị thiếu, mã số
OCR hỏng, bảng nhiều tầng/đa kỳ chưa phân giải và các quan hệ chưa xác nhận vẫn
được ghi nhận; không tự bù số. Ngày ký không được dùng thay ngày công bố.
Phạm vi BCTC riêng/hợp nhất không tự xác nhận included_entities/excluded_entities
cho từng KPI. Chưa xác minh thì boundary vẫn null và missing_fields đồng bộ.

Kiểm tra số học chỉ so các số cùng kỳ, đơn vị, scale, scope khi toán hạng được
nhận dạng; sai lệch chỉ tạo issue, không sửa nguồn. `not_checked` không là pass.
ESG-related là kết quả tìm ứng viên từ đoạn/nhãn có từ khóa cụ thể, không kết luận
doanh nghiệp không có một hoạt động khi không tìm thấy trong phần đã kiểm tra.
Không có kết luận kiểm toán hoặc buộc tội greenwashing; không tạo ESG giả.

## Chạy lại từ thư mục dự án (PowerShell, mỗi lệnh một dòng)

```powershell
.\\.venv\\Scripts\\python.exe scripts\\setup_vietnamese_ocr.py
.\\.venv\\Scripts\\python.exe scripts\\extract_source_v2.py "C:\\duong-dan\\BCTC.pdf" --output-dir data/processed/source_v2 --company BSR --report-type financial_statements --report-year 2024
.\\.venv\\Scripts\\python.exe scripts\\export_financial_handoff.py "<thư mục chứa canonical.json>" --output-dir outputs/financial_handoff_new --number-format vi
```

Tesseract phải được cài riêng. `vi` là lựa chọn dấu phân cách đã kiểm tra cho báo
cáo này, không suy từ VND cho mọi báo cáo. Với tài liệu khác có thể dùng `auto` để
giữ trường hợp mơ hồ. Không dùng đường dẫn ví dụ nếu chưa thay bằng đường dẫn thật.
Không ghi đè gói bàn giao cũ: chọn output-dir mới.
'''
    (destination / 'README.md').write_text(readme, encoding='utf-8')
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workspaces', nargs='+', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--number-format', choices=['auto', 'vi', 'en'], default='auto')
    parser.add_argument('--baseline', type=Path)
    args = parser.parse_args()
    print(export(args.workspaces, args.output_dir, args.number_format, args.baseline))


if __name__ == '__main__':
    main()
