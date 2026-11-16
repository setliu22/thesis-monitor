export type Company = {
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
export type Job = {
  id: number;
  kind: string;
  status: string;
  attempts: number;
  error: string | null;
  created_at: string;
  finished_at: string | null;
};
export type Analysis = {
  id: number;
  filing_id: number;
  thesis_id: number;
  model: string;
  prompt_version: string;
  created_at: string;
  result: {
    scope: string;
    observations: { summary: string; quote: string; assessment: string }[];
    rejected_count: number;
  };
};
export type Detail = {
  company: Company;
  thesis: { id: number; body: string; version: number } | null;
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
