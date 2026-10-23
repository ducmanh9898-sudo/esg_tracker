"""Download and register annual PDFs without changing an existing source version."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import subprocess

import fitz
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from kg.text_normalize import normalized_label


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inspect_pdf(path, year, company, visual_cover_sha256=None):
    with path.open("rb") as stream:
        magic = stream.read(5)
    if magic != b"%PDF-":
        raise ValueError("response_is_not_pdf")
    with fitz.open(path) as pdf:
        if pdf.page_count < 2:
            raise ValueError("pdf_has_too_few_pages")
        opening = " ".join(pdf[i].get_text() for i in range(min(8, pdf.page_count))).lower()
        folded = " ".join(opening.split())
        text_identity = str(company).lower() in folded
        title_identity = ("bao cao thuong nien" in normalized_label(opening) or
                          "annual report" in normalized_label(opening))
        visual_identity = (visual_cover_sha256 is not None and
                           file_hash(path) == visual_cover_sha256)
        if str(year) not in folded or not ((text_identity and title_identity) or visual_identity):
            raise ValueError("annual_report_identity_not_established_in_opening_pages")
        return pdf.page_count, ("pdf_text" if text_identity else "visual_cover_sha256")


def download(session, url, path):
    try:
        with path.open("wb") as stream:
            with session.get(url, stream=True, timeout=(20, 120),
                             headers={"User-Agent": "ESG-Research/1.0"}) as response:
                response.raise_for_status()
                for block in response.iter_content(chunk_size=1024 * 1024):
                    if block:
                        stream.write(block)
    except requests.exceptions.SSLError:
        # Windows curl uses the OS certificate store. Never disable TLS verification.
        subprocess.run(["curl.exe", "--location", "--fail", "--retry", "2",
                        "--connect-timeout", "20", "--max-time", "180",
                        "--output", str(path), url], check=True, capture_output=True)


def fetch(profile_path, output):
    profile = json.loads(Path(profile_path).read_text(encoding="utf-8"))
    company = profile["company_id"]
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    registry_path = output / "registry.json"
    if registry_path.exists():
        raise ValueError("registry_exists_choose_new_output")
    session = requests.Session()
    retry = Retry(total=2, connect=2, read=2, backoff_factor=2,
                  status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    registry = {"schema_version": "annual-source-registry-1.0", "company_id": company,
                "sources": []}
    for item in profile["sources"]:
        year, url = item["report_year"], item["url"]
        target = output / f"{company}_annual_{year}.pdf"
        temporary = None
        downloaded = False
        try:
            if not target.exists():
                with tempfile.NamedTemporaryFile(prefix=f"annual_{year}_", suffix=".part",
                                                 dir=output, delete=False) as stream:
                    temporary = Path(stream.name)
                download(session, url, temporary)
                inspect_pdf(temporary, year, company, item.get("visual_cover_sha256"))
                os.replace(temporary, target)
                downloaded = True
            pages, identity_method = inspect_pdf(target, year, company,
                                                 item.get("visual_cover_sha256"))
            source_hash = file_hash(target)
            registry["sources"].append({"source_id": f"{company}-ANNUAL-{year}-{source_hash[:12]}",
                                        "report_year": year, "source_document_type": "annual_report",
                                        "url": url, "path": str(target.resolve()), "sha256": source_hash,
                                        "page_count": pages, "page_system": "physical_pdf_page_1_based",
                                        "downloaded_at_utc": (datetime.now(timezone.utc).isoformat() if downloaded else
                                                              datetime.fromtimestamp(target.stat().st_mtime, timezone.utc).isoformat()),
                                        "downloaded_at_basis": "current_run" if downloaded else "existing_file_mtime",
                                        "identity_method": identity_method,
                                        "identity_review_status": "pending_human_review" if identity_method == "visual_cover_sha256" else "text_checked",
                                        "status": "available"})
        except (requests.RequestException, subprocess.CalledProcessError, OSError, ValueError, RuntimeError) as exc:
            registry["sources"].append({"report_year": year, "url": url,
                                        "status": "failed", "reason": str(exc)})
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    with tempfile.NamedTemporaryFile("w", prefix="registry_", suffix=".part", dir=output,
                                     encoding="utf-8", delete=False) as stream:
        json.dump(registry, stream, ensure_ascii=False, indent=2)
        temp_registry = Path(stream.name)
    os.replace(temp_registry, registry_path)
    return registry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    registry = fetch(args.profile, args.output_dir)
    print(json.dumps(registry, ensure_ascii=False, indent=2))
    return 0 if all(s["status"] == "available" for s in registry["sources"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
