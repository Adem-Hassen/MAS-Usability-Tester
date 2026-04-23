// src/types/index.ts

export type SessionStatus = 'ready' | 'queued' | 'running' | 'done' | 'failed';

// V1 structured event types
export type SSEEventType =
  | 'pipeline_start'
  | 'supervisor_analysis'
  | 'persona_start'
  | 'persona_action'
  | 'persona_complete'
  | 'clustering_start'
  | 'clustering_complete'
  | 'recommender_start'
  | 'recommender_patch'
  | 'conflict_detected'
  | 'conflict_resolved'
  | 'patch_applied'
  | 'pipeline_complete'
  | 'error'
  // Legacy event types
  | 'log'
  | 'progress'
  | 'step'
  | 'issue'
  | 'patch'
  | 'done';

export type Severity = 'critical' | 'high' | 'medium' | 'low';

export type StepStatus = 'idle' | 'running' | 'done' | 'error';

export type ConnectionStatus = 'connecting' | 'connected' | 'reconnecting' | 'disconnected' | 'error';

// Unified SSE event — discriminated union via `kind`
export interface StreamEvent {
  id?:     number;
  kind:    SSEEventType;
  ts:      string;
  // pipeline_start
  job_id?: string;
  file_count?: number;
  model?: string;
  tokens_remaining?: number;
  // supervisor_analysis
  summary?: string;
  structural_issues_found?: number;
  // persona_start / persona_complete
  persona_id?: string;
  persona_name?: string;
  persona_type?: string;
  issues_found?: number;
  // persona_action
  action_type?: string;
  selector?: string;
  result?: string;
  // clustering
  raw_issue_count?: number;
  cluster_count?: number;
  duplicate_count?: number;
  // recommender
  recommender_id?: string;
  cluster_ids?: string[];
  component?: string;
  before_snippet?: string;
  after_snippet?: string;
  // conflict
  components_affected?: string[];
  strategy?: string;
  resolution_strategy?: string;
  // patch_applied
  file_name?: string;
  patch_count?: number;
  // pipeline_complete
  report_url?: string;
  download_url?: string;
  // progress (legacy)
  value?:  number;
  label?:  string;
  // step (legacy)
  step?:   string;
  status?: StepStatus;
  page?:   string;
  page_num?: number;
  pages_total?: number;
  // log
  level?:  'info' | 'warning' | 'error';
  message?: string;
  // issue (legacy)
  issue_id?:    string;
  title?:       string;
  severity?:    Severity;
  category?:    string;
  description?: string;
  // patch (legacy)
  patch_id?:    string;
  target?:      string;
  patch_type?:  string;
  // done (legacy)
  pages_done?: number;
  has_pdf?:    boolean;
  // error
  stage?: string;
  traceback?: string;
  // pipeline_complete extras
  patches_applied?: number;
  duplicates_removed?: number;
}

export interface PipelineStep {
  id:      string;
  label:   string;
  status:  StepStatus;
  page?:   string;
  elapsed?: number;  // seconds
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
