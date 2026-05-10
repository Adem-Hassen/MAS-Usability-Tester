# MAS Usability Tester — Comprehensive Technical Description

## Automated Multi-Agent Accessibility and Usability Evaluation Platform

---

**Abstract.** The MAS (Multi-Agent System) Usability Tester is an end-to-end automated platform for evaluating the accessibility and usability of HTML-based user interfaces. It orchestrates a swarm of simulated user personas that interact with web pages via real browser automation, detects usability and WCAG violations through both inline observation and post-hoc analysis, clusters findings, generates concrete source-level patches (HTML, CSS, JavaScript), and verifies their effectiveness through iterative correction loops. The system exposes a real-time dashboard built on Next.js that streams live agent actions, screenshots, and pipeline progress via Server-Sent Events. This document provides a comprehensive technical description of the system architecture, agent workflows, data models, and implementation details suitable for academic review.

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [System Architecture Overview](#2-system-architecture-overview)
3. [Backend Architecture](#3-backend-architecture)
4. [Multi-Agent System](#4-multi-agent-system)
5. [Frontend Architecture](#5-frontend-architecture)
6. [Real-Time Communication](#6-real-time-communication)
7. [Data Models and Schemas](#7-data-models-and-schemas)
8. [Configuration and Deployment](#8-configuration-and-deployment)
9. [End-to-End Workflow](#9-end-to-end-workflow)
10. [Key Design Decisions](#10-key-design-decisions)

---

## 1. Introduction

### 1.1 Motivation

Traditional accessibility and usability testing relies on manual audits, heuristic evaluations, or single-script automated checkers (e.g., axe-core, Lighthouse). These approaches suffer from three limitations: (1) they cannot simulate diverse user perspectives (e.g., screen-reader users, colorblind users, impatient mobile users); (2) they produce diagnostic reports without concrete remediation code; and (3) they do not verify whether proposed fixes actually resolve the detected issues.

The MAS Usability Tester addresses these gaps by employing a multi-agent architecture in which each agent embodies a distinct user persona with specific accessibility constraints, technical skill levels, and interaction styles. Personas navigate real browser instances, make autonomous decisions via large language models (LLMs), and report issues from their subjective perspectives. A separate recommender agent swarm generates concrete patches, and a verification loop validates patches by re-simulating failing personas on the corrected HTML.

### 1.2 Key Capabilities

- **Massively Parallel Persona Simulation:** Up to 100 personas can run concurrently across a bounded thread pool, each with an isolated browser context.
- **Concrete Patch Generation:** Patches are not suggestions but executable code snippets (HTML attributes, structural changes, CSS rules, JavaScript behaviors) that can be applied directly to the source.
- **Iterative Verification:** The system runs correction loops—re-simulating personas on patched HTML—to verify that fixes work before declaring success.
- **Real-Time Telemetry:** Every agent action, screenshot, and pipeline stage is streamed to the frontend via SSE, providing live visibility into the evaluation process.
- **Multi-Provider LLM Support:** The system supports Groq, OpenAI, Moonshot (Kimi), DeepSeek, Qwen, and OpenRouter through a unified routing layer.

### 1.3 Tech Stack

| Layer | Technology |
|-------|-----------|
| Orchestration | Python 3.10+, LangGraph |
| LLM Inference | Groq (default), OpenAI, Moonshot, DeepSeek, Qwen, OpenRouter |
| Backend API | FastAPI, Uvicorn |
| Browser Automation | Playwright (Chromium via CDP) |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`) |
| Clustering | HDBSCAN |
| Frontend | Next.js 14 (App Router), React 18, TypeScript, Tailwind CSS |
| Logging | structlog with EventBus bridge |
| Persistence | SQLite |
| PDF Reports | ReportLab / fpdf2 |

---

## 2. System Architecture Overview

### 2.1 High-Level Architecture

The system follows a three-tier architecture: (1) a **Frontend Dashboard** (Next.js) for user interaction and visualization; (2) a **Backend API** (FastAPI) that manages sessions, streams events, and serves static assets; and (3) an **Agent Execution Layer** (Python/LangGraph) that runs the evaluation pipeline.

```
┌─────────────────────────────────────────────────────────────┐
│                     FRONTEND (Next.js)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Upload Page  │  │  Dashboard   │  │  Report Viewer   │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
└─────────┼─────────────────┼───────────────────┼───────────┘
          │                 │                   │
          │  HTTP/SSE       │  HTTP/SSE         │  HTTP
          ▼                 ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│                   BACKEND (FastAPI)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  REST API    │  │  SSE Stream  │  │  Session Store   │  │
│  │  /api/v1/... │  │  /evaluate/  │  │  (SQLite)        │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
└─────────┼─────────────────┼───────────────────┼───────────┘
          │                 │                   │
          ▼                 ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│              PIPELINE RUNNER (pipeline_runner.py)            │
│              ┌─────────────────────────────┐                │
│              │   EventBus + structlog      │                │
│              └─────────────┬───────────────┘                │
│                            │                                 │
│  ┌─────────────────────────▼─────────────────────────────┐  │
│  │              LANGGRAPH PIPELINE (core/graph.py)        │  │
│  │  supervisor → fan_out → page_pipeline_node (×N pages) │  │
│  │     ↓                                                    │  │
│  │  personas → clustering → recommenders → conflict        │  │
│  │     ↓                                                    │  │
│  │  patch_applicator → verification → report_generator     │  │
│  └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Folder Structure

```
MAS-Usability-Tester/
├── backend/                    # FastAPI backend
│   ├── main.py                 # API endpoints
│   ├── pipeline_runner.py      # Pipeline orchestration
│   ├── session_store.py        # SQLite session & event store
│   ├── schemas.py              # Pydantic request/response models
│   └── sessions/               # Per-session input/output directories
├── core/                       # LangGraph pipeline
│   ├── graph.py                # Graph topology & node wiring
│   ├── state.py                # TypedDict state & PageContext dataclass
│   └── event_bus.py            # Thread-safe event pub/sub
├── agents/                     # Agent implementations
│   ├── supervisor/             # Supervisor, patch applicator, verifier, reporter
│   ├── persona/                # Persona agent, Playwright engine, validator
│   └── recommender/            # Recommender agent, conflict resolver
├── tools/                      # Utilities
│   ├── rate_limiter.py         # Provider-agnostic LLM client
│   ├── llm_router.py           # Per-role LLM router
│   ├── analysis/               # Cluster engine, audit engine, design token extractor
│   ├── reporting/              # Markdown & PDF exporters
│   └── html_preprocessor.py    # HTML sanitization
├── schemas/                    # Pydantic data models
│   ├── persona_schema.py
│   ├── issue_schema.py
│   ├── patch_schema.py
│   └── report_schema.py
├── prompts/                    # LLM system/user prompts
│   ├── supervisor_prompts.py
│   ├── persona_prompts.py
│   └── recommender_prompts.py
├── config/                     # Settings, logging, persona templates
│   ├── settings.py             # pydantic-settings config
│   ├── logging_config.py       # structlog + EventBus bridge
│   └── persona_templates.yaml  # Base persona library
├── frontend/                   # Next.js frontend
│   ├── src/
│   │   ├── app/                # Next.js App Router pages
│   │   ├── components/         # React components
│   │   ├── context/            # PipelineContext (global state)
│   │   ├── hooks/              # Custom React hooks
│   │   ├── lib/                # API client
│   │   └── types/              # TypeScript type definitions
│   └── tailwind.config.ts
└── monitoring/                 # Logging utilities
    └── logger.py
```

---

## 3. Backend Architecture

### 3.1 FastAPI Application (`backend/main.py`)

The FastAPI application exposes two API versions: **V1** (primary) and a **Legacy** API (backward-compatible). The V1 API is designed for the Next.js frontend and follows RESTful conventions.

#### V1 Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/evaluate` | Upload 1–5 HTML files (max 5 MB each), start evaluation pipeline |
| `GET` | `/api/v1/evaluate/{job_id}/stream` | SSE stream with `Last-Event-ID` support |
| `GET` | `/api/v1/evaluate/{job_id}/events` | Replay buffered events (for state recovery) |
| `GET` | `/api/v1/evaluate/{job_id}/issues` | Clustered issues JSON |
| `GET` | `/api/v1/evaluate/{job_id}/results` | Full results (pages, scores, reports) |
| `GET` | `/api/v1/evaluate/{job_id}/report` | PDF report download |
| `GET` | `/api/v1/evaluate/{job_id}/download` | ZIP of patched HTML files |
| `GET` | `/api/v1/evaluate/{job_id}/screenshots/{filename}` | Serve persona screenshots |
| `GET` | `/api/v1/history` | Past evaluation list |
| `GET` | `/api/v1/stats/*` | Aggregated statistics (overview, evaluations, personas, recommendations) |
| `GET` | `/api/v1/active-run` | Currently running job ID |
| `GET` | `/api/v1/health` | Health check |
| `DELETE`| `/api/v1/evaluate/{job_id}` | Cancel/delete session |

**Upload Validation:** The `/api/v1/evaluate` endpoint validates file extensions (`.html`), size limits, and count. It auto-cancels any previous running pipelines via `store.cancel_all()` before creating a new session.

**Results Endpoint (`/api/v1/evaluate/{job_id}/results`):** Returns `session.results` from the in-memory `SessionStore`. If the results are empty (e.g., due to a backend restart), it falls back to reading `results.json` from the session's output directory on disk.

### 3.2 Session Store (`backend/session_store.py`)

The `SessionStore` class is the backbone of session lifecycle management. It is **not** a pure in-memory store; it persists session metadata and events to SQLite, enabling recovery after backend restarts.

#### SQLite Schema

**`sessions` table:**
```sql
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    status TEXT,
    progress INTEGER,
    pages_done INTEGER,
    created_at TIMESTAMP,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    results TEXT,        -- JSON blob
    error TEXT
);
```

**`events` table:**
```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    event_id INTEGER,
    kind TEXT,
    ts TEXT,
    payload TEXT         -- JSON blob
);
```

#### Key Capabilities

- **Event Buffering with Auto-Incrementing IDs:** Events are stored with a per-session auto-incrementing `event_id`, enabling the frontend to request only events after a given ID (`after_id`). This supports SSE reconnection without duplicate events.
- **Async Queue Broadcasting:** `_queues` maps `session_id` to a list of `asyncio.Queue` objects. When an event is emitted, it is both written to SQLite and pushed to all subscriber queues via `loop.call_soon_threadsafe()`, ensuring thread-safe delivery from worker threads.
- **Task Tracking:** Running pipeline tasks are registered as `asyncio.Task` objects. `cancel_all()` cancels all tasks and shuts down the shared browser.
- **Results Persistence:** `save_results()` writes the `results` JSON blob to the SQLite `sessions` table when the pipeline completes.

### 3.3 Pipeline Runner (`backend/pipeline_runner.py`)

The `PipelineRunner` bridges the LangGraph pipeline to the SSE event stream. It is invoked by `run_pipeline_async(session, store)`.

#### Execution Flow

1. **Session Setup:** Creates input/output directories, emits `PIPELINE_START` and `PROGRESS` events.
2. **EventBus Subscription:** Subscribes a `_bus_handler` to the `EventBus` singleton. This handler maps internal log messages to structured SSE events.
3. **Pipeline Execution:** Calls `run_evaluation(pages)` from the LangGraph pipeline.
4. **Heartbeat Thread:** A daemon thread emits `PROGRESS` events every 20 seconds if no log events arrive, preventing frontend timeouts.
5. **Result Extraction:** After pipeline completion, iterates over `page_contexts` and `reports`, emits `ISSUE` and `PATCH` events, writes `results.json`, and generates a PDF report.
6. **Cleanup:** Unsubscribes from the EventBus and stops the heartbeat.

#### Event Mapping

The `_STEP_MAP` and `_FUNC_STEP_MAP` dictionaries map internal log prefixes (e.g., `"graph.supervisor_node.start"`) to frontend step IDs, statuses, progress values, and labels. For example:

```python
_STEP_MAP = {
    "graph.supervisor_node.start":  ("supervisor", "running", 5,  "Analysing UI..."),
    "persona.start":                ("personas",   "running", 18, "Persona started"),
    "recommender.proposal_complete":("recommender","running", 42, "Patch generated"),
    "patch_applicator":             ("applicator", "running", 50, "Applying patches..."),
}
```

#### Screenshot Handling

When a `persona.start` or `persona.action` log event contains a base64 screenshot, the runner decodes it, saves it as a JPEG file in the session's output directory, and rewrites the event payload to contain a URL like `/api/v1/evaluate/{job_id}/screenshots/{filename}`.

---

## 4. Multi-Agent System

### 4.1 LangGraph Pipeline (`core/graph.py`)

The pipeline is modeled as a **directed acyclic graph (DAG)** using LangGraph's `StateGraph`. The graph is compiled once as a module-level singleton (`_compiled_graph`).

#### Graph Topology

```
[supervisor_node] → _fan_out_pages
                          ↓
              Send("page_pipeline_node", ctx) per page
                          ↓
              [page_pipeline_node] (parallel, one per page)
                          ↓
        ┌─────────────────┼─────────────────┐
        ↓                 ↓                 ↓
   [personas]      [clustering]      [recommender]
        ↓                 ↓                 ↓
   [analysis]      [verified_issues]  [patch_proposals]
        ↓                 ↓                 ↓
        └─────────────────┼─────────────────┘
                          ↓
                  [conflict_resolver]
                          ↓
                  [patch_applicator]
                          ↓
                  [verification_node]
                          ↓
                  (if failed) → [correction_loop]
                          ↓
                  [report_generator]
```

#### Parallel-Write Safety

`GraphState` is a `TypedDict` with carefully chosen annotations:

- **`supervisor_output`**: Plain field (written once by a single node).
- **`current_page_context`**: Injected per-branch via `Send()`, never written back to shared state.
- **`page_contexts` and `reports`**: Annotated with `Annotated[list, operator.add]`, making concurrent appends safe.

This design allows `page_pipeline_node` to run in parallel for every uploaded page without write conflicts.

#### Correction Loop

If `verification_node` determines that patches did not resolve enough issues, the graph enters a correction loop:

1. `_prepare_correction` creates a temporary patched HTML file.
2. Resets the `PageContext` with the patched HTML.
3. Re-runs simulations for failing personas.
4. Re-runs analysis, clustering, recommenders, patch application, and verification.
5. Repeats up to `max_correction_loops` times (default: 0, configurable up to 5).

### 4.2 Supervisor Agent (`agents/supervisor/supervisor_agent.py`)

The supervisor agent is the entry point of the pipeline. It has three responsibilities:

#### UI Analysis (`supervisor_node`)

Calls an LLM with `UI_ANALYSIS_SYSTEM` and `UI_ANALYSIS_USER` prompts to infer:

- `ui_type`: The category of page (e.g., `auth`, `checkout`, `dashboard`).
- `critical_paths`: Sequences of interactions required to complete primary tasks.
- `interactive_elements`: List of clickable, focusable, or input elements.
- `detected_issues_hint`: Static accessibility observations from structural analysis.
- `accessibility_risk_level`: A score from 1–10 indicating how likely the page is to have severe issues.

**Fallback:** If the LLM call fails, `_stub_analysis()` generates a basic analysis from HTML tags.

#### Persona Generation (`supervisor_node`)

1. Reads `config/persona_templates.yaml`, a library of base persona profiles (e.g., "Screen Reader User", "Colorblind Mobile User").
2. Filters templates by `ui_type` relevance.
3. Calls an LLM to select diverse personas and assign task goals specific to the page.
4. Merges library base profiles with LLM-generated task specifics.

**Persona Budget:** `_persona_budget()` computes how many personas to spawn (1 to `max_num_personas`) based on element count, critical paths, and risk level.

#### Trace Verification (`analysis_node`)

A **rule-based** verification step (no LLM call) that filters invalid simulation traces:

- **Loop Detection:** Identical `(action_type, selector)` repeated in the last 3 steps.
- **Navigate Interception:** Traces that attempt external navigation.
- **Missing Selectors:** `click` or `type` actions with no target.
- **Network Errors:** `ERR_FILE_NOT_FOUND` or similar.
- **Unknown Selectors:** Selectors not present in the HTML or `UIAnalysis`.

Traces with >40% invalid steps are discarded entirely.

### 4.3 Persona Agent (`agents/persona/persona_agent.py`)

The persona agent simulates a single user interacting with the page. It is the most complex agent in the system.

#### PersonaRunner Architecture

```
┌─────────────────────────────────────────────┐
│           PersonaRunner                      │
│  ┌─────────────────────────────────────┐   │
│  │  WorkingMemory (Python-maintained)  │   │
│  │  - page_phase                       │   │
│  │  - fields_filled                    │   │
│  │  - fields_required                  │   │
│  │  - observe_count                    │   │
│  │  - steps_remaining                  │   │
│  └─────────────────────────────────────┘   │
│  ┌─────────────────────────────────────┐   │
│  │  Simulation Loop (up to N steps)    │   │
│  │  1. Get DOMState                    │   │
│  │  2. Scroll/Observe guards           │   │
│  │  3. LLM Decision (DECISION_USER)    │   │
│  │  4. Action Validation               │   │
│  │  5. Execute via PlaywrightEngine    │   │
│  │  6. Record step & update memory     │   │
│  │  7. Screenshot & issue detection    │   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

#### WorkingMemory

A `@dataclass` updated after every step. Key fields:

- `page_phase`: Tracks where the user is in the task flow (`FILLING_FORM`, `SUBMITTED`, `AWAITING_REDIRECT`, `SUCCESS`, `STUCK`).
- `observe_count`: Counts consecutive "observe" actions. If ≥3, the runner forces a `dead_end` or `goal_achieved` to prevent infinite observation loops.
- `steps_remaining`: A countdown that terminates the loop when exhausted.

WorkingMemory is **never modified by the LLM**; it is maintained entirely in Python and injected into every `DECISION_USER` prompt.

#### Action Guards

1. **Scroll Stagnation Guard:** Max 4 consecutive scrolls without Y-axis change.
2. **Repeat-Action Guard:** A sliding 3-step window prevents clicking the same selector repeatedly.
3. **Grounding Guard:** Before executing an action, the runner verifies that the selector exists in the DOM via `engine.selector_exists()`. This prevents LLM hallucinations.
4. **Navigate Interception:** External URLs (`http://`, `https://`) are blocked; the agent is redirected to use click-based navigation.
5. **Form-Filling Sequence:** The LLM is instructed to fill required fields before submitting, with WorkingMemory tracking progress.

#### Issue Detection

Issues are detected through **three parallel paths**:

1. **Inline Detection:** On every decision step, the LLM can report `issue_detected` (e.g., "missing label", "low contrast"). These are recorded immediately.
2. **Failure Analysis:** When an action fails (e.g., click timeout, invalid selector), the LLM is prompted with `ISSUE_DETECTION_SYSTEM` to analyze the root cause and generate `IssueReport` objects with WCAG criterion references.
3. **Post-Simulation Audit:** If a persona completes with zero issues, a dedicated LLM review of the full trace is triggered to catch missed accessibility problems (missing headings, alt text, etc.).

### 4.4 Playwright Engine (`agents/persona/playwright_engine.py`)

The `PlaywrightEngine` provides browser automation for each persona. It is designed for performance and isolation.

#### Performance Optimizations

- **_ThreadLocalPlaywright:** Caches one `sync_playwright().start()` per worker thread. With 8 threads and 100 personas, only 8 Playwright drivers are created.
- **_SharedBrowser:** Launches one Chromium process with `--remote-debugging-port=9222`. Each persona gets an isolated `BrowserContext` (cookies, localStorage, viewport) but shares the OS process.
- **Health Monitoring:** `check_health()` polls the CDP endpoint; if Chromium crashes, it auto-restarts.

#### DOM State Extraction (`get_page_state`)

Returns a `DOMState` object containing:

- `visible_text`: Extracted via `TreeWalker`, skipping hidden elements.
- `interactive_elements`: Up to 50 elements covering `a`, `button`, `input`, `select`, `textarea`, `[role="button"]`, `[tabindex]`. Each element includes computed styles, bounding boxes (`{x, y, width, height}`), ARIA roles/labels, and associated `<label>` elements.
- `hidden_sections`: Up to 10 `display:none` sections with inferred `activate_via` selectors.
- `has_modal`, `alert_text`, `scroll_position`, `focused_element_selector`.

#### Actions

| Action | Description |
|--------|-------------|
| `click` | Click element by selector |
| `type` | Click, then fill input with value |
| `scroll` | Scroll up/down by 300px |
| `navigate` | Blocked for external URLs; allowed for local sandbox |
| `observe` | Report current page state without interaction |
| `hover` | Move mouse over element |

After every action, the engine captures:
- A screenshot (JPEG base64 for SSE, PNG for internal use).
- The element's bounding box (`{x, y, width, height}`) for frontend overlay rendering.
- The new URL.
- Elapsed time.

#### Sandbox Setup (`agents/persona/agent_sandbox.py`)

HTML content is written to a temporary sandbox file. A `storage_seed` is injected via `add_init_script` to prevent auth-guard redirects (e.g., checking `localStorage.isLoggedIn`).

### 4.5 Clustering Engine (`tools/analysis/cluster_engine.py`)

After all personas finish, their issues are clustered to remove duplicates and group related findings.

#### Algorithm

1. **Embedding:** Uses `sentence-transformers` (`all-MiniLM-L6-v2`) to embed each issue. The text representation combines `title`, `description`, `wcag_criterion`, `category`, `affected_element`, and `UI_page`.
2. **Clustering:** HDBSCAN with dynamic `min_cluster_size = max(2, n_issues // 6)`. Noise points (-1) become singleton clusters.
3. **Fallback:** For ≤2 issues or embedding failures, falls back to category-based grouping.

#### Metadata Derivation

For each cluster:
- `dominant_severity`: By rank (critical > high > medium > low).
- `dominant_category`: Most frequent category.
- `affected_personas`: Union of all persona IDs.
- `affected_elements`: Union of all selectors.
- `representative_description`: The longest description in the cluster.

### 4.6 Recommender Agent (`agents/recommender/recommender_agent.py`)

For each cluster, one or more `RecommenderProfile` objects are generated, each spawning a recommender agent.

#### RecommenderProfile

Generated by the supervisor with:
- `focus`: accessibility, usability, navigation, form, clarity, mixed.
- `fix_strategy_hint`: Technology assignment (CSS for visual, JS for behavior, HTML for structure) with specific selectors.
- `num_recommenders`: 1–4 instances depending on issue count and diversity.
- `priority`: Ranked by severity and persona impact breadth.

#### Patch Proposal

The recommender calls an LLM with `RECOMMENDER_SYSTEM` and `RECOMMENDER_USER` prompts. The "Bold Directive" in the system prompt requires proactive design improvements beyond reactive fixes.

**Patch Types:**

| Type | Description |
|------|-------------|
| `html_attribute` | Add/modify attributes (aria-label, alt, role) |
| `html_structure` | Wrap elements, add fieldset/legend |
| `content` | Rewrite visible text |
| `remove_element` | Delete broken elements |
| `reorder_elements` | Fix DOM/tab order |
| `inline_style` | Add `style=""` directly |
| `css_rule` / `css_class` | New standalone CSS rules |
| `js_snippet` | Self-contained JavaScript wrapped in DOMContentLoaded |

**Snippet Recovery:** If `css_snippet` is empty but `after_snippet` looks like CSS, the system promotes it. Invalid JS patches are downgraded to HTML to avoid corruption.

#### Swarm Stigmergy

Recommender agents read `swarm_claims` (a snapshot at launch time) to detect overlapping selectors. If overlap is detected, the recommender notes it in `side_effects` but continues execution.

### 4.7 Conflict Resolver (`agents/recommender/conflict_resolver.py`)

After all recommenders finish, the conflict resolver detects and resolves overlapping patches.

#### Conflict Detection

- **Primary Method:** LLM-based detection with `CONFLICT_DETECTION_SYSTEM`.
- **Fallback Heuristic:** Two patches conflict if they share the same `target_element` AND the same type category (HTML/HTML, CSS/CSS, JS/JS). Cross-type patches (e.g., HTML + CSS on the same element) are orthogonal.

#### Negotiation

For each conflict, up to `conflict_max_negotiation_rounds` rounds are run:

1. **Argument Phase:** Each agent argues for its patch (`NEGOTIATION_ARGUMENT_SYSTEM`).
2. **Mediation Phase:** A mediator LLM decides: `chose_a`, `chose_b`, `merged`, or `unresolved` (`MEDIATOR_SYSTEM`).
3. **Resolution:** Builds `ResolvedPatch` objects. Merged patches combine snippets. Losers are dropped.

### 4.8 Patch Applicator (`agents/supervisor/patch_applicator.py`)

Applies the unified patch set to the original HTML.

#### Application Order

Patches are sorted by `(type_priority, cluster_id)` and applied in this order:
1. HTML patches (`html_attribute`, `html_structure`, `content`, `reorder_elements`).
2. CSS patches (`css_rule`, `css_class`, `inline_style`).
3. JavaScript patches (`js_snippet`).
4. `remove_element` patches (applied last to avoid breaking references).

#### HTML Replacement Strategies

1. **Exact Substring Match:** Direct string replacement.
2. **Whitespace-Normalized Regex:** Matches `before_snippet` with flexible whitespace.
3. **Attribute-Targeted Replace:** For `html_attribute` patches, injects attributes into the target tag using regex.

#### CSS Injection

Appends CSS inside the last `<style>` block, or creates a new `<style>` before `</head>`, or prepends before `<body>`.

#### JS Injection

Wraps snippets in `DOMContentLoaded` if missing, then injects before `</body>`.

#### Validation

After each HTML patch, `html.parser.HTMLParser` checks for malformed output. Invalid patches are logged and skipped.

### 4.9 Verification Loop (`agents/supervisor/verification_loop.py`)

Validates whether patches actually resolved the issues.

#### Per-Persona Verification

For each verified simulation result, the verifier LLM receives:
- The patched HTML snippet.
- The original issues.
- The applied patches.

It classifies each issue as `resolved`, `remaining`, or `new`.

#### Pass Criteria

- **Default:** ≥80% of critical+high issues must be resolved.
- **Fallback:** If no critical/high issues exist, ≥50% of all issues must be resolved.

If verification fails, the graph enters the correction loop (Section 4.1).

### 4.10 Report Generator (`agents/supervisor/report_generator.py`)

Compiles all data into a `DiagnosticReport`.

#### Score Calculation

Can be LLM-generated (with strict scoring rubric) or fallback to a deterministic formula based on:
- Resolved issue ratio.
- Critical/high issue counts.
- Task completion rate.

#### Output Formats

- **JSON:** Structured report (`report_file.json`).
- **Markdown:** Human-readable report.
- **PDF:** Generated via ReportLab (or fpdf2 fallback).

---

## 5. Frontend Architecture

### 5.1 Framework and State Management

The frontend is built with **Next.js 14** (App Router), **React 18**, **TypeScript**, and **Tailwind CSS**. Global state is managed via a single React Context (`PipelineContext`) rather than Redux or Zustand, as the state shape is relatively flat and events are the primary driver of updates.

#### PipelineState

```typescript
interface PipelineState {
  jobId: string | null;
  status: 'ready' | 'queued' | 'running' | 'done' | 'failed';
  connection: 'connecting' | 'connected' | 'reconnecting' | 'disconnected' | 'error';
  progress: number;
  progressLabel: string;
  steps: PipelineStep[];
  logs: { level: string; message: string; ts: string }[];
  issues: Issue[];
  patches: Patch[];
  results: SessionResults | null;
  livePreviews: Record<string, LivePreview>;
  notifications: Notification[];
  totalIssues: number;
  totalPatches: number;
}
```

#### applyEvent Reducer

The `applyEvent` function is a **pure reducer** that maps `StreamEvent` → `PipelineState` updates. It handles deduplication (by `issue_id` and `patch_id`) to prevent double-counting from correction loops.

Key reducer logic:
- `issue` events append to `issues[]` and increment `totalIssues`.
- `recommender_patch` events increment `totalPatches` live.
- `patch` events append to `patches[]` and use `Math.max()` to avoid overwriting live increments.
- `pipeline_complete` uses `Math.max(prev, ev.issues_found)` to preserve higher event-based counts.

### 5.2 API Client (`frontend/src/lib/api.ts`)

#### streamEvaluate

Manages `EventSource` lifecycle with:
- **Last-Event-ID tracking:** Browser-native reconnection uses the last seen event ID.
- **Manual reconnection:** On error, exponential backoff (1s, 2s, 4s, 8s, 16s) with `onReconnect` callback.
- **Terminal events:** `done`, `pipeline_complete`, and `error` close the stream automatically.

#### getResults

Fetches results from the v1 endpoint with legacy fallback:
```typescript
let res = await fetch(`${BASE}/v1/evaluate/${sessionId}/results`);
if (res.status === 404) {
  res = await fetch(`${BASE}/sessions/${sessionId}/results`);
}
```

### 5.3 Dashboard Layout (`frontend/src/app/evaluate/[job_id]/page.tsx`)

The evaluation dashboard uses a **three-panel layout**:

```
┌─────────────────┬──────────────────────────────┬─────────────────────┐
│  Pipeline Rail  │   Agent Stream & Live        │   Output Tabs       │
│  (left, 256px)  │   Preview (center, flex-1)   │   (right, 500px)   │
│                 │                              │                     │
│  - Stepper      │   - Live screenshots         │   - Issues          │
│  - Progress     │   - Action overlays          │   - Patches         │
│  - Stats        │   - Terminal logs            │   - Verify (diff)   │
│                 │                              │   - Export          │
└─────────────────┴──────────────────────────────┴─────────────────────┘
```

### 5.4 Live Preview Panel (`frontend/src/components/pipeline/LivePreviewPanel.tsx`)

Displays real-time screenshots from persona simulations.

#### Features
- **Grid Layout:** 1–3 columns depending on active persona count.
- **Focus Layout:** Full-width carousel with prev/next navigation.
- **Persona Color Assignment:** Deterministic 8-color palette (cyan, emerald, amber, rose, violet, orange, sky, lime) assigned by hashing `persona_id`.
- **Action Overlay:** Renders bounding boxes received from backend as colored rectangles with action badges (click, type, hover, etc.), corner markers, and click ripple animations.
- **Action HUD:** Always-visible bottom gradient showing action type and target selector.
- **Maximizable:** Toggle to fullscreen mode.

### 5.5 Diff Viewer (`frontend/src/components/diff/DiffViewer.tsx`)

A professional code comparison tool for reviewing patches.

#### Features
- **Myers Diff Algorithm:** Pure TypeScript LCS implementation.
- **Split View:** Side-by-side Original vs. Patched with synchronized scrolling.
- **Unified View:** Single column with left/right line numbers.
- **Syntax Highlighting:** Custom HTML tokenizer (tags in rose, attributes in amber, values in emerald).
- **Word-Level Diff:** Secondary LCS pass within changed lines to highlight specific words.
- **Context Folding:** Collapses unchanged lines with `···` indicators.
- **Fullscreen Support:** Browser fullscreen API integration.

### 5.6 Pipeline Rail (`frontend/src/components/pipeline/PipelineRail.tsx`)

Displays pipeline progress with:
- **Stepper:** Visual step indicators for supervisor → personas → clustering → recommender → resolver → applicator → verification → report.
- **Progress Bar:** Animated percentage indicator.
- **Live Counters:** Animated issue and patch counters with `useAnimatedNumber` hook.
- **Connection Status:** API status indicator.

---

## 6. Real-Time Communication

### 6.1 EventBus (`core/event_bus.py`)

A thread-safe singleton pub/sub system:
- `subscribe(handler)`: Add a callback.
- `emit(event_type, **payload)`: Broadcast to all handlers.
- Exceptions in handlers are swallowed to prevent cascading failures.

### 6.2 Logging Bridge (`config/logging_config.py`)

structlog is configured with an `_event_bus_processor` that emits every log event as `log_event` to the EventBus. This bridges Python backend logs to SSE without code changes in agents.

### 6.3 SSE Stream (`backend/main.py`)

The `stream_evaluate` endpoint:
1. Parses `Last-Event-ID` header for reconnection.
2. Replays buffered events from SQLite where `event_id > last_event_id`.
3. Subscribes to the live queue for new events.
4. Sends `: keepalive\n\n` every 15 seconds to prevent proxy timeouts.
5. Closes the stream on terminal events (`DONE`, `ERROR`, `PIPELINE_COMPLETE`).

### 6.4 Frontend Event Processing

1. **History Replay:** On connection, fetches past events via `getJobEvents()` and replays them through `applyEvent`.
2. **Live Streaming:** Opens `EventSource` and processes events in real time.
3. **Reconnection:** Exponential backoff with `Last-Event-ID` tracking.
4. **Auto-Recovery:** On page load, checks `/api/v1/active-run` and auto-connects if a pipeline is running.

### 6.5 Event Types

| Event | Direction | Payload |
|-------|-----------|---------|
| `pipeline_start` | Backend → Frontend | `job_id`, `file_count`, `model` |
| `persona_start` | Backend → Frontend | `persona_id`, `persona_name`, `screenshot` |
| `persona_action` | Backend → Frontend | `persona_id`, `action_type`, `selector`, `screenshot`, `bounding_box` |
| `issue` | Backend → Frontend | `issue_id`, `title`, `severity`, `category`, `description` |
| `patch` | Backend → Frontend | `patch_id`, `target`, `description`, `patch_type` |
| `recommender_patch` | Backend → Frontend | `status`, `message` |
| `patch_applied` | Backend → Frontend | `file_name`, `patch_count` |
| `pipeline_complete` | Backend → Frontend | `issues_found`, `patches_applied`, `report_url` |
| `error` | Backend → Frontend | `message`, `stage` |
| `progress` | Backend → Frontend | `value`, `label` |
| `step` | Backend → Frontend | `step`, `status`, `page` |

---

## 7. Data Models and Schemas

### 7.1 PageContext (`core/state.py`)

The central per-page state container:

```python
@dataclass
class PageContext:
    html_source_path: str
    original_html_path: str
    html_content: str
    ui_context: str
    storage_seed: dict
    ui_analysis: Optional[UIAnalysis]
    personas: list[PersonaProfile]
    simulation_results: list[PersonaSimulationResult]
    verified_issues: list[IssueReport]
    issue_clusters: list[IssueCluster]
    patch_proposals: list[PatchProposal]
    unified_patch_set: Optional[UnifiedPatchSet]
    patched_html_content: Optional[str]
    verification_results: list[VerificationResult]
    verification_passed: bool
    report: Optional[DiagnosticReport]
    total_patches_applied: int
```

### 7.2 IssueReport (`schemas/issue_schema.py`)

```python
class IssueReport(BaseModel):
    issue_id: str
    severity: IssueSeverity          # critical, high, medium, low
    category: IssueCategory          # accessibility, usability, navigation, form, visual, content
    wcag_criterion: Optional[str]    # e.g., "1.3.1", "2.1.1"
    title: str
    description: str
    affected_element: Optional[str]  # CSS selector
    reproduction_steps: str
    persona_impact: list[str]        # Which personas encountered this
```

### 7.3 PatchProposal (`schemas/patch_schema.py`)

```python
class PatchProposal(BaseModel):
    patch_id: str
    patch_type: PatchType
    target_element: Optional[str]
    before_snippet: Optional[str]
    after_snippet: Optional[str]
    css_snippet: Optional[str]
    js_snippet: Optional[str]
    confidence: float                # 0.0–1.0
    description: str
    side_effects: Optional[str]
```

### 7.4 DiagnosticReport (`schemas/report_schema.py`)

```python
class DiagnosticReport(BaseModel):
    overall_score: float             # 0.0–10.0
    severity_breakdown: dict         # count per severity
    total_issues_found: int
    total_patches_applied: int
    executive_summary: str
    top_recommendations: list[str]
    page_name: str
    personas_evaluated: int
    evaluation_duration_seconds: float
```

---

## 8. Configuration and Deployment

### 8.1 Settings (`config/settings.py`)

Uses `pydantic_settings.BaseSettings` with `.env` file loading.

#### Key Configuration Groups

| Category | Key Settings | Defaults |
|----------|-------------|----------|
| **Supervisor** | `supervisor_api_key`, `supervisor_llm_model`, `supervisor_temperature` | `llama-3.3-70b-versatile`, `0.2` |
| **Persona** | `persona_api_key`, `persona_llm_model`, `max_num_personas`, `persona_max_steps` | `llama-3.1-8b-instant`, `3`, `10` |
| **Recommender** | `recommender_api_key`, `recommender_llm_model` | `llama-3.3-70b-versatile` |
| **Rate Limiting** | `llm_max_concurrent_calls`, `llm_tpm_limit` | `5`, `0` |
| **Clustering** | `embedding_model`, `clustering_similarity_threshold` | `all-MiniLM-L6-v2`, `0.75` |
| **Verification** | `max_correction_loops`, `verification_resolution_threshold` | `0`, `0.8` |
| **Browser** | `persona_headless`, `persona_action_timeout_seconds` | `True`, `20.0` |

### 8.2 Rate Limiter (`tools/rate_limiter.py`)

- **Per-Key Semaphore:** Limits concurrent requests per API key (default 5).
- **Provider Routing:** Automatic base URL selection based on model prefix:
  - `gpt-*`, `o1-*`, `o3-*`, `o4-*` → OpenAI
  - `qwen*`, `qwq*` → Qwen MaaS
  - `kimi-*` → Moonshot (requires `temperature=1.0`)
  - `deepseek-*` → DeepSeek
  - Default → Groq
- **JSON Mode:** Conditionally sends `response_format={"type":"json_object"}` based on provider capabilities.
- **Retry Logic:** Exponential backoff with jitter, handling rate limits and 5xx errors.

### 8.3 LLM Router (`tools/llm_router.py`)

Provides per-role singletons:
- `get_persona_router()`
- `get_recommender_router()`
- `get_supervisor_router()`
- `get_resolver_router()`

Each router wraps `chat_completion` with role-specific configuration (model, temperature, max_tokens).

### 8.4 Deployment

**Backend:**
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

**Frontend:**
```bash
cd frontend && npm run dev
```

**Environment Variables:**
- `ALLOWED_ORIGINS`: CORS origins (default: `http://localhost:3000`).
- `ALLOW_SIMULATION_FALLBACK`: Enable demo mode when MAS core is unavailable.

---

## 9. End-to-End Workflow

### 9.1 User Upload

1. User visits the Next.js frontend and uploads 1–5 HTML files.
2. Frontend calls `POST /api/v1/evaluate`.
3. Backend creates a session, saves files to `backend/sessions/{job_id}/input/`, and starts the pipeline asynchronously.
4. Backend returns `{ job_id, file_count, status: "queued" }`.

### 9.2 Supervisor Analysis

1. Pipeline emits `PIPELINE_START`.
2. `supervisor_node` calls the supervisor LLM to analyze the HTML.
3. Generates `UIAnalysis` (page type, critical paths, risk level).
4. Generates `PersonaProfile` objects based on templates and page context.
5. Emits `SUPERVISOR_ANALYSIS` event.

### 9.3 Persona Simulation

1. `_fan_out_pages` creates one `page_pipeline_node` per page.
2. Each page pipeline spawns personas in parallel via `ThreadPoolExecutor`.
3. Each persona opens a browser context, navigates the sandbox, and runs the simulation loop.
4. Actions are logged, screenshots are captured, and issues are detected inline.
5. Frontend receives `PERSONA_START` and `PERSONA_ACTION` events with screenshots and bounding boxes.

### 9.4 Issue Detection and Clustering

1. Simulation results are collected.
2. Rule-based trace verification filters invalid traces.
3. Issues are embedded and clustered via HDBSCAN.
4. `CLUSTERING_COMPLETE` event is emitted with cluster count.

### 9.5 Recommendation and Patch Generation

1. The supervisor generates `RecommenderProfile` objects per cluster.
2. Recommender agents run in parallel, producing `PatchProposal` objects.
3. The conflict resolver detects overlapping patches and negotiates resolutions.
4. `UnifiedPatchSet` is produced and emitted as `PATCH` events.

### 9.6 Patch Application and Verification

1. `patch_applicator_node` applies patches to the original HTML.
2. `verification_node` re-simulates failing personas on the patched HTML.
3. If verification passes, proceed to reporting.
4. If verification fails and `max_correction_loops > 0`, enter correction loop.

### 9.7 Report Generation

1. `report_generator_node` compiles the `DiagnosticReport`.
2. Saves JSON, Markdown, and PDF to the session output directory.
3. Emits `PIPELINE_COMPLETE` with `issues_found`, `patches_applied`, `report_url`.

### 9.8 Frontend Real-Time Visualization

1. Frontend connects to SSE stream and receives live events.
2. `PipelineContext` updates state via `applyEvent` reducer.
3. Dashboard shows live previews, progress rail, issue/patch lists.
4. User clicks "Verify" tab to view the diff viewer.
5. User downloads the PDF report or patched HTML ZIP.

---

## 10. Key Design Decisions

### 10.1 Why LangGraph?

LangGraph was chosen over a simple linear pipeline because:
- **Parallel execution:** Pages run in parallel via `Send()`.
- **Stateful nodes:** Each node receives and returns a `PageContext`.
- **Correction loops:** Conditional edges enable iterative improvement.
- **Observability:** Built-in checkpointing and tracing.

### 10.2 Why ThreadPoolExecutor over AsyncIO?

Playwright's sync API is used because:
- Persona simulations involve blocking browser I/O (click, type, screenshot).
- A bounded thread pool (`max_num_personas`) caps concurrent browser contexts.
- Thread-local caching of Playwright drivers reduces process spawn overhead.

### 10.3 Why SQLite over Redis?

SQLite was chosen for the session store because:
- **Zero infrastructure:** No separate database service required.
- **Sufficient scale:** Each evaluation produces ~100–500 events; SQLite handles this easily.
- **Event replay:** Auto-incrementing `event_id` enables efficient replay.
- **Future migration:** The store interface abstracts persistence; Redis can be swapped in later.

### 10.4 Why Provider-Agnostic Rate Limiting?

The system supports multiple LLM providers because:
- **Reliability:** Rate limits on one provider can be mitigated by switching to another.
- **Cost optimization:** Different providers have different pricing models.
- **Model diversity:** Some tasks (e.g., persona decision) benefit from fast/cheap models, while others (e.g., patch generation) need strong reasoning models.

### 10.5 Why WorkingMemory in Python?

WorkingMemory is maintained in Python (not by the LLM) because:
- **Consistency:** Prevents the LLM from hallucinating or contradicting its own memory.
- **Enforcement:** Guards (observe spiral, scroll stagnation) are enforced in Python, not via prompt instructions.
- **Determinism:** Guarantees that the same trace always produces the same memory state.

### 10.6 Why Bounding Boxes for Action Highlighting?

Playwright's `element.bounding_box()` is captured after every action because:
- **Precision:** Exact pixel coordinates of the interacted element.
- **Visual clarity:** Frontend can draw overlays directly on screenshots.
- **Debugging:** Users can see exactly which element each persona targeted.

---

## Conclusion

The MAS Usability Tester represents a novel approach to automated accessibility and usability evaluation by combining multi-agent simulation, concrete patch generation, and iterative verification. Its architecture is designed for extensibility: new persona types, patch strategies, and LLM providers can be added with minimal changes. The real-time dashboard provides unprecedented visibility into the evaluation process, making it a powerful tool for both developers and researchers.

---

*Document generated from comprehensive codebase analysis of the MAS-Usability-Tester project.*
