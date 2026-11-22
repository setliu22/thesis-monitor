export type Company = {
  invested?: boolean;
  earnings_schedule?: { date?: string; status?: string; source?: string; error?: string | null };
  id: number;
  ticker: string;
  name: string;
  data_status: string;
  last_success: string | null;
  last_attempt?: string | null;
  last_error?: string | null;
  stale?: boolean;
};
export type Source = {
  mapping_note?: string;
  tag: string;
  value: string;
  filed: string;
  accn: string;
  start?: string;
  end: string;
  url?: string;
};
export type Observation = {
  identity: string;
  metric: string;
  value: string | null;
  unit: string;
  start: string | null;
  end: string;
  kind: string;
  derivation: string;
  unavailable_reason: string | null;
  sources: Source[];
};
export type Rule = {
  id: number;
  group_key: string;
  version: number;
  name: string;
  metric: string;
  operator: string;
  threshold: string;
  period_kind: string;
  enabled: boolean;
};
export type Alert = {
  id: number;
  title: string;
  created_at: string;
  acknowledged_at: string | null;
  evidence: Observation & {
    threshold: string;
    operator: string;
    rule_version: number;
    rule_name: string;
  };
};
export type Filing = {
  id: number;
  form: string;
  filed: string;
  report_date: string;
  accession: string;
  url: string | null;
};
export type ThesisVersion = {
  id: number;
  version: number;
  body: string;
  created_at: string;
};
export type Job = {
  id: number;
  kind: string;
  status: string;
  attempts: number;
  error: string | null;
  created_at: string;
  finished_at: string | null;
  available_at?: string;
  payload?: {
    waiting_for?: 'groq';
    wait_kind?: string;
    last_attempt_at?: string;
    summary_analysis_id?: number;
    summary_policy?: string;
    filing_id?: number;
    thesis_id?: number;
    review_id?: number;
    progress?: { phase: string; completed_batches: number; total_batches: number };
  };
};
export type Analysis = {
  id: number;
  filing_id: number;
  thesis_id: number;
  model: string;
  prompt_version: string;
  created_at: string;
  review_id?: number | null;
  result: {
    claims?: ThesisClaim[];
    claim_assessments?: ClaimAssessment[];
    no_testable_claims?: boolean;
    summary_policy?: string;
    summary_eligible?: boolean;
    summary?: {
      policy: string;
      sections: { claim_id: string; direction: 'supports' | 'challenges'; text: string; citations: string[] }[];
    };
    evidence?: ReviewEvidence[];
    coverage?: {
      filing?: { selective?: boolean; selected_blocks?: number; total_blocks?: number };
      call?: { selective?: boolean; selected_blocks?: number; total_blocks?: number };
    };
    call?: { status: string; reason?: string; next_attempt?: string | null; deadline?: string };
    stage?: string;
    thesis_version?: number;
    transcript?: {
      status: string;
      quarter?: string;
      reason?: string;
      source_url?: string;
      coverage?: { full_transcript?: boolean; passages_classified: number; batches: number };
      observations?: {
        summary: string;
        quote: string;
        thesis_quote?: string;
        assessment: string;
        speaker: string;
        title?: string;
        turn?: number;
      }[];
    };
    scope: string;
    source_url?: string;
    selection_method?: string;
    review_status?: string;
    review_notes?: string[];
    observations: { summary: string; quote: string; thesis_quote?: string; assessment: string }[];
    rejected_count: number;
  };
};
export type Detail = {
  review?: ReviewStatus;
  recent_reviews?: ReviewStatus[];
  company: Company;
  thesis: ThesisVersion | null;
  rules: Rule[];
  observations: Observation[];
  filings: Filing[];
  alerts: Alert[];
  jobs: Job[];
  analyses: Analysis[];
};
export type Settings = {
  sec_configured: boolean;
  llm_configured: boolean;
  refresh_seconds: number;
  metrics: Record<string, string>;
};

export type ThesisClaim = { id: string; text: string; driver?: string };
export type ReviewEvidence = {
  id: string;
  claim_id: string;
  claim_ids?: string[];
  quote: string;
  direction: string;
  source_type: string;
  source_url: string;
  period?: string;
  speaker?: string;
  role?: string;
  heading?: string;
  context?: unknown;
  context_clipped?: boolean;
  prior_review_id?: number;
};
export type ClaimAssessment = {
  claim_id: string;
  assessment: 'supports' | 'challenges' | 'mixed' | 'insufficient evidence';
  finding: string;
  why_it_matters: string;
  uncertainty: string;
  citations: string[];
  assertions?: { text: string; citations: string[] }[];
  temporal_comparison?: boolean;
  coverage?: { available_evidence: number; reviewed_evidence: number; prior_incomplete?: boolean };
};
export type ReviewStatus = {
  status: string;
  review_id?: number;
  filing_id?: number | null;
  thesis_id?: number | null;
  thesis_version?: number | null;
  reason?: string;
  next_attempt?: string | null;
  completion_estimate?: { at: string; scope: 'filing' | 'filing and call' } | null;
  last_error?: string | null;
  progress?: { phase: string; completed_batches: number; total_batches: number } | null;
  call_status?: { status: string; reason?: string; next_attempt?: string | null };
  filing_status?: string;
  discovery_cadence_hours?: number;
  discovery_note?: string;
  discovery_next_attempt?: string;
};
