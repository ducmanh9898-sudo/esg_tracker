# Corporate Extract — source-bound partial handoff

This is an analytical extraction package, not an audit, assurance opinion or
greenwashing verdict. All exported records await human source review. Read
`validation/report.json`, `notes/blocked_documents.json`, coverage and issue_log
before using any values. Mechanical validity does not mean semantic completeness.

## Contents

- `manifest.json`: strict corporate-extract-manifest-1.0, relative paths and hashes.
- `pdf/`: original PDF bytes, not OCR-rewritten replacements.
- `json/`: one corporate-extract-1.0 JSON per exported source PDF.
- `notes/native/<PDF_SHA256>.json`: original internal semantic output, including
  unmapped records. This is deliberately not mixed into strict contract JSON.
- `notes/native/<PDF_SHA256>/pages/`: parser page checkpoints. Resolve original
  native JSON pointers against the corresponding page artifact here. Native
  artifact hashes remain in the original internal output. The PDF artifact in
  that output resolves instead to `pdf/` via manifest; its old relative path is
  not an instruction to look outside the delivery.
- `notes/source_provenance.json`: supplied source URLs, keyed by PDF hash. A URL
  being supplied does not prove official-publication byte identity.
- `validation/`: supplied schemas, mechanical validator, dependency list and report.
- `notes/demo_review_queue.json`: source-linked candidates for emissions, workforce,
  board and environmental financial notes; a review queue, not comparison findings.

## Verify

From the extracted package root:

```text
python -m pip install -r validation/requirements.txt
python validation/validate.py --manifest manifest.json --pdf-dir pdf
```

An all-unavailable manifest has no JSON to validate; it is not a completed handoff.
`unavailable` means no contract-ready source/result was supplied for that slot,
not a conclusion that the company failed to publish a report. A supplied PDF
whose export was blocked remains in pdf/, with its problem described in notes.

## Interpretation safeguards

- Missing/ambiguous values stay null, never zero. Base values have already had
  normalization_factor applied exactly once; do not multiply them again.
- Metric identity/definition remains null unless established, not guessed from
  name similarity. Native row IDs are not shared metric IDs.
- Document year is not observation year. Context-derived periods are not human-
  reviewed context. Unknown KPI boundaries are not copied from document scope.
- `not_labelled` is not converted to absence of restatement. Unlinked footnotes
  remain pending review, not fabricated. Unsupported compound units remain unknown.
- Search outcomes stay not_searched where no defensible topic-search record is
  available. Successful OCR pages do not certify complete topic coverage.
- The adapter preserves record IDs and quotes from existing OCR output. These
  are OCR observations, not certified verbatim transcriptions. Check the PDF.
- No record is automatically reviewed, no boundary verified and no comparison
  classified Contradicted. Reviewer adjudication is still required.

For the BSR nine-slot export, missing years/scopes are explicit manifest rows.
For a single-session export, the manifest covers that session only.

The supplied manifest schema forbids extra URL fields. Official URLs therefore
live in each document.source and notes/source_provenance.json, not as an
undeclared manifest property. Where the report says source_pdf_bytes_verified,
the downloaded reference file SHA-256 was recomputed at export; this verifies
byte identity/provenance, not the factual accuracy of the company's disclosures.
PDF source-version changes are recorded separately; earlier local files/history
are never overwritten to make an official URL appear to match.
