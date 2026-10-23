# Data inventory and retention (2026-10-09)

Graph v2 reads selected JSON paths from `data/config/corpus_config.json`. The selected files are also registered with SHA-256 in `data/extract/manifest.json`. No PDF is stored in this repository; PDF names in Extract JSON are provenance locators, not local PDF copies.

| Former location | Contents and role | Current location / decision |
| --- | --- | --- |
| `esg/` | Ten structured ESG JSON files for BSR, PLX and PVD (2023–2025); PVD 2023/2024 are partial ranges, and PVD 2025 has both full and partial extracts. Ten human summaries are distinct Markdown documents. | JSON → `data/extract/esg/`; Markdown → `docs/extract-summaries/`. The PVD 2025 partial JSON remains as an unselected overlap with its own coverage and provenance. |
| `data/raw/financial_reports/BSR/` and the former root BSR separate file | Three historical consolidated financial extracts and one separate 2025 full OCR extract. The separate report includes four structured rows with 2024 comparatives. | `data/extract/financial/`; Separate and Consolidated remain distinct. |
| `json/` | Ten PDF page-text JSON files with source PDF metadata. These are retained source surrogates because the PDFs are absent. The PVD 2025 pages 120–134 JSON is an exact page-object subset of the full PVD 2025 JSON with the same PDF metadata. | Nine retained files → `data/source/page_text/`. The redundant PVD subset is represented by the full page JSON plus the separate partial ESG extract and batch manifest coverage. |
| `chunks/` | 147 chunk JSON files and 10 chunk manifests, covering the same page objects as the ten page-text JSON files. All 581 chunk page objects were checked against their page-text JSON counterparts with zero mismatch or missing page. | Removed after consumers switched to page-text JSON. The unused chunk regeneration utility was archived during the Graph-only cleanup; retained page-text JSON remains the source context. |
| `data/` root | Corpus/selection/rules/crosswalk/review-sample configuration, derived legacy JSON products, and separate review handoffs. | Ten configuration/sample files → `data/config/`. Derived `financial_disclosures_bsr.json`, `pilot_readiness_inventory.json`, `integration_gap_status.json` and `data/handoff/` remain at their old paths because legacy tools/tests or review provenance use them. They are not Graph v2 raw input. |

The preserved page JSON, ESG JSON, financial JSON and human summaries were copied byte-for-byte and SHA-256 checked before the old copies were removed. The source JSON contents, record IDs, numerical values, review status and source PDF names were not rewritten. `identity_path` in corpus config retains the original ESG path for stable generated claim/evidence IDs; `source_extract_path` now points to the actual new file.

| Company / period | ESG Extract JSON | Preserved page text | Financial Extract JSON / boundary |
| --- | --- | --- | --- |
| BSR 2023, 2024, 2025 | One selected JSON per year; reporting boundary remains unverified for many claims. | One page JSON per year. | Consolidated files for all three years; 2025 also has a separate-parent file with four 2024 comparative measurements. The 2025 consolidated extract does not verify every metric boundary. |
| PLX 2023, 2024, 2025 | One selected JSON per year; boundary is not inferred from file name. | One page JSON per year. | None in repository. |
| PVD 2023, 2024, 2025 | Partial pages 101–120 (2023), partial pages 120–144 (2024), full 2025 selected plus pages 120–134 retained as a distinct overlapping Extract snapshot. | 2023 and 2024 partial page JSON; one full 2025 page JSON covers the historical 120–134 subset. | None in repository. |

`data/config/` holds the corpus selector, BSR selection/rules, PVD alias mapping, rule catalogue, standards crosswalk, validation cases and demonstration candidate/temporal files. Graph consumers read the canonical paths. The unused `build_dataset.ps1` was archived during the Graph-only cleanup; its `pages_*.ps1` inputs were already absent. Available original PDFs and preserved historical page-text JSON remain in `data/source/`.

The current historical batch has 14 Extract JSON files: nine selected ESG files, one unselected PVD 2025 overlap, and four selected BSR financial files. Its batch manifest is `data/extract/manifest.json`. One future report/entity/boundary should be handed off as one adapter-supported JSON plus a shared batch manifest; page chunks and Markdown are optional internal artifacts, not handoff requirements. See `docs/extract-graph-contract.md`.
