# Validation Protocol v0.1

Validation is reported in six independent layers. A pass at one layer does not
waive an error or pending review at another layer.

1. **Input** — required identity, company, report/observation period, value,
   unit, scope and evidence fields; missing values remain distinct from absent
   records.
2. **Evidence linkage** — every finding must trace to all input claims,
   evidence records, reports, pages and JSON pointers supplied by Extract.
3. **Standard mapping** — only verified crosswalk entries appear in the graph;
   mapping context never creates a compliance or violation conclusion.
4. **Rule** — rule inputs and applicability guards are checked independently;
   an absent record does not create InsufficientEvidence or Contradicted.
5. **Temporal comparison** — company, metric, unit, period, scope and reporting
   boundary must align, or an explicit change explanation is required. Numeric
   change alone is not Temporal Inconsistency.
6. **Company aggregation** — finding IDs are unique, exact duplicates are
   removed, paraphrase equivalence remains unverified, and synthetic financial
   fixtures are excluded from real-company summaries.

Synthetic cases define deterministic expected behavior. Real cases that have
not been manually checked against their PDF source are labelled
`pending_adjudication`; they are not a confirmed gold set.
