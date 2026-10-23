PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS companies (
  company_id TEXT PRIMARY KEY, name TEXT NOT NULL, industry TEXT, country TEXT,
  is_demo_data INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS documents (
  document_id TEXT PRIMARY KEY, company_id TEXT NOT NULL, title TEXT NOT NULL,
  report_year INTEGER NOT NULL, document_type TEXT NOT NULL, source_file TEXT NOT NULL,
  source_path TEXT, page_count INTEGER, extraction_method TEXT, confidence REAL,
  is_demo_data INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(company_id) REFERENCES companies(company_id)
);
CREATE TABLE IF NOT EXISTS passages (
  passage_id TEXT PRIMARY KEY, document_id TEXT NOT NULL, report_year INTEGER NOT NULL,
  document_type TEXT NOT NULL, page_number INTEGER NOT NULL, source_text TEXT NOT NULL,
  extraction_method TEXT NOT NULL, confidence REAL NOT NULL, is_demo_data INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(document_id) REFERENCES documents(document_id)
);
CREATE TABLE IF NOT EXISTS source_artifacts (
  artifact_id TEXT PRIMARY KEY, document_id TEXT NOT NULL,
  artifact_type TEXT NOT NULL, source_path TEXT NOT NULL,
  content_text TEXT NOT NULL, sha256 TEXT NOT NULL,
  page_start INTEGER, page_end INTEGER, record_count INTEGER,
  report_year INTEGER NOT NULL, document_type TEXT NOT NULL,
  is_demo_data INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(document_id) REFERENCES documents(document_id)
);
CREATE TABLE IF NOT EXISTS claims (
  claim_id TEXT PRIMARY KEY, passage_id TEXT NOT NULL, document_id TEXT NOT NULL,
  report_year INTEGER NOT NULL, document_type TEXT NOT NULL, page_number INTEGER NOT NULL,
  source_text TEXT NOT NULL, extraction_method TEXT NOT NULL, confidence REAL NOT NULL,
  claim_type TEXT NOT NULL, pillar TEXT NOT NULL, topic_id TEXT NOT NULL, metric_code TEXT,
  actor TEXT, action TEXT, object TEXT, raw_value REAL, raw_unit TEXT, time_text TEXT,
  baseline_year INTEGER, target_year INTEGER, scope TEXT, boundary TEXT, qualifier TEXT,
  direction TEXT NOT NULL DEFAULT 'NEUTRAL', value_kind TEXT, denominator TEXT,
  is_demo_data INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(passage_id) REFERENCES passages(passage_id),
  FOREIGN KEY(document_id) REFERENCES documents(document_id)
);
CREATE TABLE IF NOT EXISTS metrics (
  metric_id TEXT PRIMARY KEY, passage_id TEXT NOT NULL, document_id TEXT NOT NULL,
  report_year INTEGER NOT NULL, document_type TEXT NOT NULL, page_number INTEGER NOT NULL,
  source_text TEXT NOT NULL, extraction_method TEXT NOT NULL, confidence REAL NOT NULL,
  metric_code TEXT NOT NULL, metric_name TEXT, raw_value REAL, raw_unit TEXT,
  normalized_value REAL, normalized_unit TEXT, metric_year INTEGER, scope TEXT, boundary TEXT,
  denominator TEXT, value_kind TEXT NOT NULL DEFAULT 'ABSOLUTE', methodology TEXT,
  assurance_status TEXT, financial_class TEXT, is_demo_data INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(passage_id) REFERENCES passages(passage_id),
  FOREIGN KEY(document_id) REFERENCES documents(document_id)
);
CREATE TABLE IF NOT EXISTS evidence_links (
  evidence_link_id TEXT PRIMARY KEY, claim_id TEXT NOT NULL, metric_id TEXT,
  relationship TEXT NOT NULL, candidate_score REAL, explanation TEXT NOT NULL,
  same_metric INTEGER, same_period INTEGER, same_unit INTEGER, unit_convertible INTEGER,
  same_scope INTEGER, same_boundary INTEGER, same_definition INTEGER, same_value_kind INTEGER,
  comparison_conditions TEXT, is_demo_data INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(claim_id) REFERENCES claims(claim_id),
  FOREIGN KEY(metric_id) REFERENCES metrics(metric_id)
);
CREATE TABLE IF NOT EXISTS rule_results (
  rule_result_id TEXT PRIMARY KEY, claim_id TEXT NOT NULL, evidence_link_id TEXT,
  rule_id TEXT NOT NULL, risk_type TEXT NOT NULL, severity INTEGER NOT NULL,
  risk_score REAL NOT NULL, explanation TEXT NOT NULL, evidence_summary TEXT,
  comparison_conditions TEXT, document_id TEXT NOT NULL, report_year INTEGER NOT NULL,
  page_number INTEGER NOT NULL, confidence REAL, is_demo_data INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(claim_id) REFERENCES claims(claim_id),
  FOREIGN KEY(evidence_link_id) REFERENCES evidence_links(evidence_link_id)
);
CREATE TABLE IF NOT EXISTS claim_scores (
  claim_id TEXT PRIMARY KEY, contradiction REAL, evidence_gap REAL, vagueness REAL,
  target_integrity REAL, temporal_consistency REAL, risk_score REAL NOT NULL,
  risk_level TEXT NOT NULL, evidence_coverage REAL NOT NULL, confidence REAL NOT NULL,
  is_demo_data INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(claim_id) REFERENCES claims(claim_id)
);
CREATE TABLE IF NOT EXISTS topic_scores (
  topic_score_id TEXT PRIMARY KEY, company_id TEXT NOT NULL, report_year INTEGER NOT NULL,
  pillar TEXT NOT NULL, topic_id TEXT NOT NULL, risk_score REAL NOT NULL, claim_count INTEGER,
  warning_count INTEGER, evidence_coverage REAL, confidence REAL, gri_reference TEXT,
  is_demo_data INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(company_id) REFERENCES companies(company_id)
);
CREATE INDEX IF NOT EXISTS idx_claims_year_topic ON claims(report_year, topic_id);
CREATE INDEX IF NOT EXISTS idx_metrics_code_year ON metrics(metric_code, metric_year);
CREATE INDEX IF NOT EXISTS idx_rules_claim ON rule_results(claim_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_document_type ON source_artifacts(document_id, artifact_type);
