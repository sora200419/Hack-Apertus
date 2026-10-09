// TypeScript mirror of src/api/originpass/models.py and the API response shapes in main.py.
// Keep in sync with the pydantic models.

// ---------------------------------------------------------------- input

export interface BomLine {
  line_id: string;
  description: string;
  hs6: string | null;
  origin_country: string;
  value_chf: number;
  supplier: string | null;
  originating_override: boolean | null;
}

export interface Shipment {
  destination: "CN" | "CH";
  transit_countries: string[];
  transshipment_or_storage_in_transit: boolean;
  order_quantity: number;
}

export interface Product {
  product_id: string;
  name: string;
  description: string;
  hs6: string | null;
  ex_works_chf: number;
  exporter_country: "CH" | "CN";
  processing: string[];
  bom: BomLine[];
  shipment: Shipment;
}

// ---------------------------------------------------------------- rule pack

export type CriterionKind = "WO" | "CC" | "CTH" | "CTSH" | "MAXNOM" | "SPECIFIC";

export interface Criterion {
  kind: CriterionKind;
  max_nom_pct: number | null;
  except_from: string[];
  note: string | null;
}

export interface Rule {
  rule_id: string;
  hs_scope: string[];
  alternatives: Criterion[][];
  text: string;
  text_zh: string | null;
  source: string;
  verified: boolean;
}

export interface GeneralProvisions {
  tolerance_pct: number;
  tolerance_applies_to: CriterionKind[];
  tolerance_text: string;
  insufficient_operations: string[];
  insufficient_operations_text: string;
  cumulation_parties: string[];
  direct_transport_text: string;
  max_items_per_certificate: number | null;
  source: string;
  verified: boolean;
}

export interface RulePack {
  pack_id: string;
  agreement: string;
  version_note: string;
  general: GeneralProvisions;
  rules: Rule[];
}

// ---------------------------------------------------------------- verdict

export type VerdictStatus = "PASS" | "FAIL" | "UNSURE";

export interface CheckResult {
  name: string;
  passed: boolean | null;
  detail: string;
  line_ids: string[];
}

export interface AlternativeResult {
  criteria: Criterion[];
  met: boolean | null;
  checks: CheckResult[];
}

export interface LineAssessment {
  line_id: string;
  originating: boolean;
  reason: string;
  hs6: string | null;
  value_chf: number;
  shift_ok: boolean | null;
}

export interface Verdict {
  product_id: string;
  status: VerdictStatus;
  hs6: string | null;
  rule: Rule | null;
  rule_verified: boolean;
  alternatives: AlternativeResult[];
  general_checks: CheckResult[];
  lines: LineAssessment[];
  nom_value_chf: number;
  nom_pct: number;
  threshold_pct: number | null;
  margin_pct: number | null;
  tolerance_used: boolean;
  reasons: string[];
  fixes: string[];
}

// ---------------------------------------------------------------- HS classification

export interface HSCandidate {
  hs6: string;
  description: string;
  score: number;
  source: "bm25" | "tfidf" | "fused";
}

export interface HSSuggestion {
  query: string;
  candidates: HSCandidate[];
  chosen: string | null;
  confidence: number;
  rationale: string;
  abstained: boolean;
  method: "llm" | "retrieval_only" | "fallback";
  llm_source: "live" | "replay" | "none";
}

// ---------------------------------------------------------------- dossier

export interface FactCheck {
  fact: string;
  expected: string;
  found: boolean;
}

export interface DossierText {
  lang: string;
  text: string;
  llm_source: "live" | "replay" | "template";
  fact_checks: FactCheck[];
  attempts: number;
}

export interface DutyEstimate {
  hs6: string;
  mfn_rate_pct: number | null;
  fta_rate_pct: number | null;
  order_value_chf: number;
  duty_saved_chf: number | null;
  source: string;
}

export interface Dossier {
  product_id: string;
  verdict_status: VerdictStatus;
  explanation_en: DossierText;
  explanation_de: DossierText;
  letter_zh: DossierText;
  back_translation_en: DossierText;
  checklist: string[];
  duty: DutyEstimate | null;
}

// ---------------------------------------------------------------- API responses

export type LlmMode = "replay" | "record" | "live";

export interface Health {
  status: string;
  mode: LlmMode;
  llm_name: string;
  llm_name_small: string;
  base_url_host: string | null;
  rulepack: { pack_id: string; rules: number; verified_rules: number };
  replay_entries: number;
}

export interface ProductSummary {
  product_id: string;
  name: string;
  description: string;
  hs6: string | null;
}

export interface EvaluateResponse {
  verdict: Verdict;
  duty: DutyEstimate | null;
}

export interface ClassifyBomResponse {
  suggestions: Record<string, HSSuggestion>;
}

export interface BomParseRequest {
  csv: string;
  name: string;
  ex_works_chf: number;
  hs6?: string;
  description?: string;
}

export interface ModelCost {
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  cost_chf: number;
  latency_p50_s: number | null;
  latency_p95_s: number | null;
}

export interface CostStats {
  usd_to_chf: number;
  prices_usd_per_m: Record<string, [number, number]>;
  by_model: Record<string, ModelCost>;
}

/** /api/eval/results is free-form JSON written by `make eval`; rendered generically. */
export type EvalResults = Record<string, unknown>;
