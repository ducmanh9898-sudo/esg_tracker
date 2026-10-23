"""Read-only source identity checks for incoming legacy Graph handoffs."""
import hashlib
import json
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def file_digest(path):
    sha = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def inside_root(relative):
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("path_outside_repository")
    return path


def checked_source(registry_path, source_id):
    entries = [s for s in read_json(registry_path)["sources"] if s["source_id"] == source_id]
    if len(entries) != 1:
        raise ValueError("source_id_missing_or_duplicate")
    entry = entries[0]
    path = inside_root(entry["path"])
    with path.open("rb") as stream:
        if stream.read(5) != b"%PDF-":
            raise ValueError("source_is_not_pdf")
    with fitz.open(path) as pdf:
        page_count = len(pdf)
    if file_digest(path) != entry["sha256"] or page_count != entry["page_count"]:
        raise ValueError("source_pdf_hash_or_page_count_mismatch")
    return entry
