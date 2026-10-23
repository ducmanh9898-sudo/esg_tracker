import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def pointer_get(obj, pointer):
    value = obj
    for part in pointer.strip("/").split("/"):
        value = value[part]
    return value


def compare_overlapping_pvd_extracts():
    source_dir = ROOT / "data" / "extract" / "esg"
    full = read_json(source_dir / "PVD_2025_esg.json")
    partial = read_json(source_dir / "PVD_2025_esg_120_134.json")
    aliases = read_json(ROOT / "data" / "config" / "pvd_aliases.json")
    rows = []
    canonical = []

    for metric, unit, full_pointer, partial_pointer in aliases:
        full_series = pointer_get(full, full_pointer)
        partial_series = pointer_get(partial, partial_pointer)
        full_value = full_series.get("2025") if isinstance(full_series, dict) else None
        partial_value = partial_series.get("2025") if isinstance(partial_series, dict) else None
        rows.append({
            "metric_id": metric,
            "unit": unit,
            "canonical_source": "PVD_2025_esg.json",
            "duplicate_source": "PVD_2025_esg_120_134.json",
            "canonical_value": full_value,
            "duplicate_value": partial_value,
            "same_value": full_value == partial_value,
            "action": "keep_full_extract; retain_partial_as_provenance"
        })
        canonical.append({
            "metric_id": metric,
            "observation_year": 2025,
            "value": full_value,
            "unit": unit,
            "canonical_source": "PVD_2025_esg.json",
            "duplicate_evidence": [{
                "source_file": "PVD_2025_esg_120_134.json",
                "value": partial_value,
                "same_value": full_value == partial_value
            }]
        })

    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    (out / "pvd_deduplication_report.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out / "pvd_canonical_2025.json").write_text(
        json.dumps(canonical, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return rows


if __name__ == "__main__":
    rows = compare_overlapping_pvd_extracts()
    print(f"Đã kiểm tra {len(rows)} cặp dữ liệu PVD 2025 bị chồng lặp")
