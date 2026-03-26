// src/types/index.ts

export type SessionStatus = 'ready' | 'running' | 'done' | 'failed';

export type EventKind = 'log' | 'progress' | 'step' | 'issue' | 'patch' | 'done' | 'error';

export type Severity = 'critical' | 'high' | 'medium' | 'low';

export type StepStatus = 'idle' | 'running' | 'done' | 'error';

export interface StreamEvent {
  kind:    EventKind;
  ts:      string;
  // progress
  value?:  number;
  label?:  string;
  // step
  step?:   string;
  status?: StepStatus;
  page?:   string;
  page_num?: number;
  pages_total?: number;
  // log
  level?:  'info' | 'warning' | 'error';
  message?: string;
  // issue
  issue_id?:    string;
  title?:       string;
  severity?:    Severity;
  category?:    string;
  description?: string;
  // patch
  patch_id?:    string;
  target?:      string;
  patch_type?:  string;
  // done
  pages_done?: number;
  has_pdf?:    boolean;
}

export interface PipelineStep {
  id:      string;
  label:   string;
  status:  StepStatus;
  page?:   string;
}

export interface Issue {
  issue_id:    string;
  title:       string;
  severity:    Severity;
  category:    string;
  description: string;
  page:        string;
}

export interface Patch {
  patch_id:    string;
  target:      string;
  description: string;
  patch_type:  string;
  page:        string;
}

export interface PageResult {
  page:            string;
  fixed_file?:     string;
  report_file?:    string;
  overall_score?:  number;
  total_issues?:   number;
  patches_applied?: number;
  summary?:        string;
  recommendations?: string[];
  error?:          string;
}

export interface SessionResults {
  session_id:   string;
  pages_total:  number;
  pages_done:   number;
  pages:        PageResult[];
  finished_at?: string;
}
