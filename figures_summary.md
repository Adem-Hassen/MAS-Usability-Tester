# Thesis Figures — Complete Guide with AI Generation Prompts

This document provides **AI image generator prompts** for every figure placeholder in the *VerSimUX* thesis. Each prompt is designed for tools like DALL-E, Midjourney, Mermaid, draw.io, or Excalidraw.

> **Style Guide for all figures:**
> - Clean, vector-style, professional academic diagram
> - White background, no decorative elements
> - Use a consistent colour palette: **#1E3A5F** (dark navy) for primary elements, **#3B82F6** (blue) for VerSimUX, **#EF4444** (red) for baselines/issues, **#22C55E** (green) for positive outcomes, **#F59E0B** (amber) for warnings
> - Sans-serif font (Inter, Helvetica, or similar)
> - All text must be legible at print resolution (300 DPI, A4 page)
> - No AI-generated "artistic" flourishes — strict technical diagram style

---

## Chapter 1: Introduction

### Figure 1.1 — Three Gaps Venn Diagram
**Label:** `fig:three-gaps`
**Caption:** The three gaps in automated web accessibility evaluation.

**AI Prompt:**
```
Create a clean, academic Venn diagram on a white background with three overlapping circles arranged in a triangular layout.

Circle 1 (top-left, light blue #DBEAFE): "Static Checkers" with subtitle "(axe-core, Lighthouse, WAVE)".
Circle 2 (top-right, light red #FEE2E2): "Manual Expert Audits" with subtitle "(WCAG walkthroughs)".
Circle 3 (bottom-center, light yellow #FEF3C7): "User Testing" with subtitle "(real participants)".

In the gap between Circle 1 and Circle 3, place a red label: "Gap 1: No Persona Simulation".
In the gap between Circle 1 and Circle 2, place a red label: "Gap 2: No Code-Level Patches".
In the gap between Circle 2 and Circle 3, place a red label: "Gap 3: No Closed-Loop Verification".

At the exact center where all three circles overlap, place a bold blue (#3B82F6) hexagon or shield badge labeled "VerSimUX" with three checkmarks below it: "✓ Simulation  ✓ Patches  ✓ Verification".

Style: flat vector, no gradients, no shadows, professional academic figure. Sans-serif font. White background. 300 DPI.
```

---

### Figure 1.2 — Pipeline Overview
**Label:** `fig:pipeline-overview`
**Caption:** High-level overview of the VerSimUX pipeline.

**AI Prompt:**
```
Create a horizontal pipeline flowchart on a white background, reading left to right. Use rounded rectangle boxes connected by arrows.

Box 1 (grey): "HTML Upload" with a document icon.
Box 2 (navy #1E3A5F, white text): "Supervisor Analysis" — subtitle: "UI parsing, persona generation".
Box 3 (blue #3B82F6, white text): "Persona Simulation Swarm" — show 3 small persona icons inside the box.
Box 4 (navy): "Issue Clustering" — subtitle: "HDBSCAN + embeddings".
Box 5 (navy): "Patch Synthesis" — subtitle: "HTML, CSS, JS patches".
Box 6 (navy): "Conflict Resolution" — subtitle: "Multi-agent negotiation".
Box 7 (amber #F59E0B, dark text): "Verification Loop" — subtitle: "Re-simulate failing personas".
Box 8 (green #22C55E, white text): "Diagnostic Report" with a checkmark icon.

Draw a dashed curved arrow looping BACK from Box 7 to Box 3, labeled "Correction Loop (up to N iterations)" in red (#EF4444).

All arrows are solid dark grey. Each box is the same height. The loop arrow goes above the main pipeline.
Style: clean flat vector, academic diagram, sans-serif font, white background, 300 DPI. No decorative elements.
```

---

## Chapter 2: Background and Related Work

### Figure 2.1 — Gap-to-Domain Matrix
**Label:** `fig:bg-gaps-mapping`
**Caption:** Mapping of related research domains to the three identified gaps.

**AI Prompt:**
```
Create a clean academic heatmap/matrix table on a white background.

Rows (6 research domains, left-aligned labels):
1. "Accessibility Checkers (axe-core, WAVE)"
2. "Simulated User Testing"
3. "Multi-Agent Systems"
4. "Grounded AI Agents"
5. "Automated Program Repair"
6. "Developer Tooling & CI/CD"

Columns (3 gaps, top-aligned labels):
1. "Gap 1: Persona Simulation"
2. "Gap 2: Code-Level Patches"
3. "Gap 3: Closed-Loop Verification"

Fill cells as follows:
- Accessibility Checkers: ✗ (red), ✗ (red), ✗ (red)
- Simulated Users: ✓ (green), ✗ (red), ✗ (red)
- Multi-Agent Systems: ◐ partial (amber), ✗ (red), ✗ (red)
- Grounded AI: ◐ partial (amber), ✗ (red), ✗ (red)
- Program Repair: ✗ (red), ✓ (green), ✗ (red)
- Developer Tooling: ✗ (red), ◐ partial (amber), ✗ (red)

Add a final row at the bottom with bold text: "VerSimUX (Ours)" with ✓ (green) in all three columns.

Use light cell background colours: green cells #DCFCE7, red cells #FEE2E2, amber cells #FEF3C7.
Style: flat, clean table with thin grey borders. Sans-serif font. White background. Academic style.
```

---

## Chapter 3: System Overview

### Figure 3.1 — Three-Tier Architecture
**Label:** `fig:system-architecture`
**Caption:** Overall three-tier system architecture.

**AI Prompt:**
```
Create a three-tier architecture diagram on a white background, arranged as three horizontal layers stacked vertically.

TOP LAYER (light blue #EFF6FF, labeled "Tier 1 — Client"):
  - Box: "Next.js 'Nexus' Dashboard" containing three sub-items: "Layout Upload", "Real-Time Telemetry Feed", "Report Viewer".

MIDDLE LAYER (light grey #F3F4F6, labeled "Tier 2 — API Server"):
  - Three boxes side by side: "FastAPI Backend" (with REST + SSE endpoints), "SQLite Database" (with "WAL mode" subtitle), "EventBus Singleton" (with "Thread-safe pub/sub" subtitle).

BOTTOM LAYER (light navy #1E3A5F with white text, labeled "Tier 3 — Core Pipeline"):
  - Large box: "LangGraph Multi-Agent Orchestrator" containing 5 small labeled nodes inside: "Supervisor", "Persona Agents", "Recommenders", "Conflict Resolver", "Verifier".

ARROWS between layers:
  - Downward arrow from Dashboard to FastAPI labeled "REST API (upload, config)".
  - Upward arrow from EventBus to Dashboard labeled "SSE Stream (events, logs, screenshots)".
  - Bidirectional arrow between FastAPI and LangGraph labeled "Graph State / Pipeline Runner".
  - Arrow from LangGraph nodes to EventBus labeled "emit(event)".
  - Arrow from EventBus to SQLite labeled "persist".

Style: flat vector, clean boxes with rounded corners, sans-serif labels, no shadows, 300 DPI, A4 width.
```

---

### Figure 3.2 — Pipeline Sequence
**Label:** `fig:pipeline-sequence`
**Caption:** The twelve-stage pipeline sequence.

**AI Prompt:**
```
Create a horizontal numbered timeline diagram on a white background showing 12 sequential stages.

Each stage is a small rounded rectangle with a number (1-12) and a short label.

Stage labels in order:
1. HTML Upload
2. DOM Sanitization
3. UI Analysis
4. Persona Generation
5. Persona Simulation
6. Trace Verification
7. Issue Extraction
8. HDBSCAN Clustering
9. Recommender Profiles
10. Patch Synthesis & Conflict Resolution
11. Patch Application
12. Report Generation

Group the stages into three colour-coded phases with background bands:
- Stages 1-7: "Diagnostic Phase" (light blue #DBEAFE background band)
- Stages 8-10: "Remediation Phase" (light amber #FEF3C7 background band)
- Stages 11-12: "Verification & Report Phase" (light green #DCFCE7 background band)

Draw a bold dashed red (#EF4444) curved arrow from Stage 11 looping back to Stage 5, labeled "Correction Loop".

Style: flat, vector, horizontal timeline, thin connecting arrows between sequential stages, sans-serif font, white background, 300 DPI.
```

---

## Chapter 4: System Architecture and Implementation

### Figure 4.1 — LangGraph Topology
**Label:** `fig:langgraph-topology`
**Caption:** LangGraph state graph topology for multi-page evaluation.

**AI Prompt:**
```
Create a directed acyclic graph (DAG) diagram on a white background.

Nodes (rounded rectangles):
  - "START" (small green circle, top)
  - "supervisor_node" (navy #1E3A5F box, white text) — connected from START
  - Diamond shape: "_fan_out_pages" (conditional edge, amber #F59E0B)
  - Three parallel "page_pipeline_node" boxes (blue #3B82F6, white text), labeled "Page 1", "Page 2", "Page N" — fanning out from the diamond
  - "END" (small red circle, bottom) — all three page nodes merge into END

Arrows:
  - START → supervisor_node (solid black)
  - supervisor_node → _fan_out_pages diamond (solid black)
  - _fan_out_pages → Page 1, Page 2, Page N (three parallel arrows, labeled "Send()" in small italic text)
  - Page 1, Page 2, Page N → END (three arrows merging)

Add a small annotation box near the parallel arrows: "Annotated[list, operator.add] ensures write-safe parallel merging"

Style: clean DAG, flat vector, no shadows, sans-serif font, white background, 300 DPI. Use dotted lines for the "..." between Page 2 and Page N.
```

---

### Figure 4.2 — PageContext Data Flow
**Label:** `fig:pagecontext-flow`
**Caption:** PageContext data flow and state adapter mapping.

**AI Prompt:**
```
Create a horizontal data flow diagram on a white background showing the adapter pattern.

LEFT: Large rounded box labeled "PageContext (nested)" containing nested attributes: "audit_results: list", "verified_issues: list", "unified_patch_set: UnifiedPatchSet", "personas: list[PersonaProfile]".

MIDDLE-LEFT: Small box labeled "_ctx_to_flat()" with a right-pointing arrow — converts nested PageContext into a flat dictionary.

CENTER: Box labeled "Flat Dict" showing key-value pairs: "{'audit_results': [...], 'verified_issues': [...], ...}".

CENTER: Arrow into a processing box labeled "Agent Node Execution" (blue #3B82F6 background).

MIDDLE-RIGHT: Small box labeled "_flat_to_ctx()" with a right-pointing arrow — merges flat dict updates back into PageContext.

RIGHT: Large rounded box labeled "Updated PageContext (nested)" — same structure as left but with highlighted modified fields.

Style: horizontal flow, flat vector, thin grey arrows, sans-serif font, white background, 300 DPI. Use light blue (#EFF6FF) for the PageContext boxes and light grey for the flat dict.
```

---

### Figure 4.3 — Persona Cognitive Loop
**Label:** `fig:persona-loop`
**Caption:** Flowchart of the six-phase cognitive pipeline.

**AI Prompt:**
```
Create a circular/ring flowchart on a white background showing 6 phases of a cognitive loop.

Arrange 6 rounded rectangle nodes in a hexagonal ring pattern, connected by clockwise arrows:

1. "Perceive DOM" (top, light blue) — subtitle: "Sanitise HTML, extract numbered elements"
2. "Plan" (top-right, light blue) — subtitle: "Strategic next-step reasoning"
3. "Decide" (right, blue #3B82F6, white text) — subtitle: "Select element by [index]"
4. "Execute" (bottom-right, navy #1E3A5F, white text) — subtitle: "Playwright action"
5. "Evaluate" (bottom-left, light blue) — subtitle: "Assess outcome, detect issues"
6. "Reflect" (left, light blue) — subtitle: "Progress check, revise strategy"

Between nodes 3 and 4, insert a gate/barrier box labeled "5 Grounding Guards" (amber #F59E0B) with 5 small bullet items: "Scroll stagnation", "Observe spiral", "Repeat-action", "DOM grounding", "Navigate interception".

An arrow from Reflect loops back to Perceive DOM (completing the cycle).
Add a break-out arrow from Reflect labeled "Goal achieved / Max steps" pointing to an "END" node outside the ring.

Style: clean hexagonal ring, flat vector, clockwise arrows, sans-serif font, white background, 300 DPI.
```

---

### Figure 4.4 — PagePhase State Machine
**Label:** `fig:pagephase-state`
**Caption:** PagePhase state machine transition diagram.

**AI Prompt:**
```
Create a simple finite state machine diagram on a white background with 3 states.

Three circles/ovals:
  - "page_understanding" (light blue, left) — initial state, with a small arrow pointing to it from a filled black dot
  - "simulating" (blue #3B82F6, center, larger) — main state
  - "complete" (green #22C55E, right) — terminal state, double-bordered

Transitions (labeled arrows):
  - page_understanding → simulating: "Plan generated"
  - simulating → simulating (self-loop arrow on top): "Next step / Execute action"
  - simulating → complete: "Goal achieved OR step budget exhausted"

Style: standard UML state machine notation, flat vector, minimal, sans-serif labels, white background, 300 DPI.
```

---

### Figure 4.5 — Shared Browser Architecture
**Label:** `fig:shared-browser`
**Caption:** Process-sharing and isolation architecture.

**AI Prompt:**
```
Create a hierarchical process diagram on a white background.

TOP: Large rounded box labeled "Chromium Process (Singleton)" in navy #1E3A5F with white text.

INSIDE the Chromium box, show 4 isolated compartments side by side:
  - "BrowserContext 1" (light blue box with "Cookies, Storage, Cache" subtitle)
  - "BrowserContext 2" (light blue box)
  - "BrowserContext 3" (light blue box)
  - "BrowserContext N" (light blue box, with "..." between 3 and N)

BELOW: A row of 4 boxes labeled "Thread 1", "Thread 2", "Thread 3", "Thread N" (light grey).

Dashed lines connecting each Thread to its corresponding BrowserContext (1:1 mapping).

BELOW threads: A container box labeled "ThreadPoolExecutor (max_workers=N)" in grey.

Add a small annotation: "If Chromium crashes → auto-restart, reconnect active sessions"

Style: hierarchical, flat vector, containment boxes, sans-serif font, white background, 300 DPI.
```

---

### Figure 4.6 — Clustering Pipeline
**Label:** `fig:clustering-pipeline`
**Caption:** Flow diagram of the semantic issue clustering pipeline.

**AI Prompt:**
```
Create a horizontal data pipeline diagram on a white background, left to right.

INPUT (left): Stack of document icons labeled "Verified Issues (N issues)" with example: "title | description | WCAG | category | element | page".

STAGE 1: Box labeled "Sentence-Transformers" with subtitle "all-MiniLM-L6-v2" and "→ 384-dim vectors". Show an arrow with "encode()" label.

STAGE 2: Box labeled "HDBSCAN Clustering" with parameters listed below:
  - "min_cluster_size = max(2, ⌊N/6⌋)"
  - "min_samples = 1"
  - "metric = euclidean"
  - "selection = eom"
Add a small branch: "N ≤ 2 → Category Fallback" (dashed arrow to a grey box).

STAGE 3: Box labeled "Metadata Derivation" with subtitle "Dominant severity, category, affected personas, representative description".

STAGE 4: Box labeled "Noise Handling" with subtitle "label = -1 → singleton clusters".

OUTPUT (right): Stack of document icons labeled "IssueCluster[]" with example clusters.

Style: horizontal pipeline, flat vector, rounded boxes connected by arrows, sans-serif font, white background, 300 DPI.
```

---

### Figure 4.7 — Conflict Resolution Workflow
**Label:** `fig:conflict-workflow`
**Caption:** Workflow of the multi-agent conflict detection and negotiation protocol.

**AI Prompt:**
```
Create a swimlane/sequence diagram on a white background with 4 vertical swimlanes.

Swimlanes (left to right):
  1. "Conflict Detector" (grey)
  2. "Agent A" (blue #3B82F6)
  3. "Agent B" (blue #60A5FA)
  4. "Mediator/Resolver" (navy #1E3A5F)

Flow (top to bottom):
  1. Conflict Detector: "Detect overlapping CSS selectors" → outputs "ConflictRecord"
  2. Arrow to Agent A: "Submit argument for Patch A"
  3. Arrow to Agent B: "Submit argument for Patch B"
  4. Both arguments flow into Mediator
  5. Mediator: "Evaluate arguments" → decision diamond
  6. Four possible outputs from diamond:
     - "Chose A" (green) → keep Patch A
     - "Chose B" (green) → keep Patch B
     - "Merged" (amber) → combined patch
     - "Fallback" (red) → severity-based tiebreak

Add a loop annotation: "Up to max_negotiation_rounds iterations"

Style: UML-style swimlane diagram, flat vector, sans-serif font, white background, 300 DPI.
```

---

### Figure 4.8 — Verification Loop
**Label:** `fig:verification-loop`
**Caption:** Closed-loop patch application, verification, and correction loop.

**AI Prompt:**
```
Create a flowchart diagram on a white background showing the verification and correction loop.

START: Box "Resolved Patch Set" (input, grey).

STEP 1: Box "Patch Applicator" (navy) — subtitle: "Apply HTML → CSS → JS in dependency order".

STEP 2: Box "Verifier Node" (blue #3B82F6) — subtitle: "Re-simulate failing personas on patched HTML".

STEP 3: Diamond decision block "All critical/high issues resolved? (≥80% threshold)".

YES path (right): Arrow to green box "Compile Final Diagnostic Report" → END.

NO path (down): Arrow to box "Increment correction_count" (red border).

Sub-decision: Diamond "correction_count < max_correction_loops?".
  YES: Arrow looping back UP to "Recommender Profile Generation" (which feeds back into Patch Synthesis → Conflict Resolution → Patch Applicator cycle).
  NO: Arrow to amber box "Generate Report with Remaining Issues" → END.

Style: standard flowchart with diamonds for decisions, rounded rectangles for processes, flat vector, sans-serif font, white background, 300 DPI.
```

---

## Chapter 5: AI Agent Design

### Figure 5.1 — Prompt Structure
**Label:** `fig:cognitive-prompt-structure`
**Caption:** Prompt structure and token architecture.

**AI Prompt:**
```
Create a vertical stacked block diagram on a white background showing the composition of an LLM prompt.

Show a tall vertical rectangle divided into 5 horizontal segments, like a stacked bar chart. Each segment is a different colour and labeled:

TOP (navy #1E3A5F, white text): "System Prompt" — subtitle: "Persona demographics, disability constraints, ARIA interaction rules, output JSON schema"
Labels: "STATIC — same for entire session"

SECOND (blue #3B82F6, white text): "Goal & Context Block" — subtitle: "task_goal, task_context, success_criteria, entry_point"
Label: "STATIC — injected once per persona"

THIRD (amber #F59E0B, dark text): "Working Memory Block" — subtitle: "page_phase, fields_filled, steps_remaining, action_history[], issues_found[]"
Label: "DYNAMIC — updated every step in Python"

FOURTH (light blue #DBEAFE, dark text): "Sanitized DOM State" — subtitle: "Numbered interactive elements: [1] button.submit 'Login' [2] input#email ..."
Label: "DYNAMIC — re-extracted every step from live DOM"

BOTTOM (light grey #F3F4F6): "Format Rules" — subtitle: "Strict JSON output schema, allowed action types, constraint reminders"
Label: "STATIC"

Add a side annotation with arrows: "Python-maintained state (not LLM self-tracked) → Prevents context drift and hallucination"

Style: vertical stacked blocks, flat vector, clear segment boundaries, sans-serif font, white background, 300 DPI.
```

---

### Figure 5.2 — Model Routing Tree
**Label:** `fig:model-routing-tree`
**Caption:** Decision tree and rate-limiting flow of the model routing layer.

**AI Prompt:**
```
Create a top-down decision tree / flowchart on a white background.

START: "LLM Request (agent_role, model_prefix)" (top, grey box).

LEVEL 1 — Diamond: "Route by model prefix?"
  Branch "gpt-*" → Box "OpenAI Provider" (green)
  Branch "kimi-*" → Box "Moonshot Provider" (purple)
  Branch "llama-*" (default) → Box "Groq Provider" (blue #3B82F6)

Each provider box flows down to:

LEVEL 2: Box "Parameter Normalization" — subtitle: "Temperature clamp, JSON mode toggle, max_tokens per agent role"

LEVEL 3: Box "Semaphore Acquire" (amber) — subtitle: "asyncio.Semaphore(max_concurrent_calls=5) per API key"

LEVEL 4: Box "TPM Budget Check" (amber) — subtitle: "Sliding-window tokens-per-minute tracker"

LEVEL 5: Box "API Call" (navy) → two outcomes:
  SUCCESS → Green box "Return response"
  FAILURE → Red diamond "RateLimitError / 500?"
    YES → "Exponential backoff (base=5s, max_retries=5)" → loop back to "Semaphore Acquire"
    NO → Red box "Raise exception"

Style: top-down tree/flowchart, flat vector, diamond decisions, rounded boxes, sans-serif font, white background, 300 DPI.
```

---

## Chapter 6: Infrastructure and Observability

### Figure 6.1 — Telemetry Infrastructure
**Label:** `fig:telemetry-infrastructure`
**Caption:** Telemetry event streaming and pub/sub architecture.

**AI Prompt:**
```
Create a system architecture diagram on a white background showing the two-path event dispatch.

LEFT SIDE: Multiple boxes labeled "Agent Thread 1", "Agent Thread 2", "Agent Thread N" (blue #3B82F6) — these represent LangGraph state nodes running in ThreadPoolExecutor.

CENTER: Large rounded box "EventBus Singleton" (navy #1E3A5F, white text) — with "emit(event_type, payload)" method call shown.

Two arrows fan out from EventBus to the right:

PATH 1 (down-right): Arrow labeled "Persist" → Box "SQLite Database" (grey) containing two table icons: "events table (auto-increment ID)" and "sessions table (status, metadata)".

PATH 2 (up-right): Arrow labeled "loop.call_soon_threadsafe(q.put_nowait, event)" → Box "asyncio.Queue (per subscriber)" (amber #F59E0B) → Arrow to Box "FastAPI StreamingResponse" (navy) → Arrow labeled "text/event-stream (SSE)" → Box "Next.js Dashboard" (light blue) with "EventSource API" subtitle.

Add a small annotation near the asyncio.Queue: "Thread-safe bridge: sync agent threads → async FastAPI event loop"

Style: horizontal system diagram, flat vector, rounded boxes, labelled arrows, sans-serif font, white background, 300 DPI.
```

---

### Figure 6.2 — Reconnection Flow
**Label:** `fig:reconnection-flow`
**Caption:** Reconnection sequence with Last-Event-ID.

**AI Prompt:**
```
Create a UML sequence diagram on a white background with 3 participants.

Participants (vertical lifelines):
  - "Next.js Client" (left, light blue box)
  - "FastAPI SSE Endpoint" (center, navy box)
  - "SQLite Database" (right, grey box)

Sequence of messages (top to bottom):

1. FastAPI → Client: "event: log, id: 13, data: {...}" (solid arrow)
2. FastAPI → Client: "event: log, id: 14, data: {...}" (solid arrow)
3. FastAPI → Client: "event: log, id: 15, data: {...}" (solid arrow)

4. RED DASHED LINE across all lifelines labeled "⚡ Connection Dropped"

5. Client → FastAPI: "GET /api/sessions/{id}/stream" with header "Last-Event-ID: 15" (solid arrow, labeled)

6. FastAPI → SQLite: "SELECT * FROM events WHERE id > 15 AND session_id = ?" (dashed arrow)

7. SQLite → FastAPI: "Return events 16, 17" (dashed arrow)

8. FastAPI → Client: "event: log, id: 16, data: {...}" (solid arrow, green — catch-up)
9. FastAPI → Client: "event: log, id: 17, data: {...}" (solid arrow, green — catch-up)

10. BLUE DASHED LINE labeled "✓ Seamless Resume — Live Events"

11. FastAPI → Client: "event: log, id: 18, data: {...}" (solid arrow — live)

Style: standard UML sequence diagram, flat vector, alternating message colours, sans-serif font, white background, 300 DPI.
```

---

### Figure 6.3 — Nexus Dashboard Layout
**Label:** `fig:frontend-dashboard`
**Caption:** The Next.js dashboard interface showing the three-panel layout, the live preview grid with bounding box overlays, and real-time execution logs.

**Source of Image:**
Take a screenshot of the actual Next.js application during an active evaluation run showing the three columns/panels (Pipeline Rail on the left, Live Preview cards in the center, and the tabbed outputs on the right). Save this image as `static/ch06_dashboard.png` in the thesis directory.

---

### Figure 6.4 — Interactive Code-Diff Viewer
**Label:** `fig:frontend-diff`
**Caption:** The interactive side-by-side diff viewer highlighting code remediation patches and conflict resolution changes.

**Source of Image:**
Take a screenshot of the Next.js application highlighting a patch recommendation in the Diff Viewer tab of the right panel, showing the side-by-side or unified Myers diff with line additions (green) and deletions (red). Save this image as `static/ch06_diff_viewer.png` in the thesis directory.

---

## Chapter 7: Evaluation

### Figure 7.1 — F₁-Score Comparison
**Label:** `fig:precision-recall-comparison`
**Caption:** F₁-score comparison under ISO 9241-110 and Nielsen's heuristics.

**AI Prompt:**
```
Create a grouped bar chart on a white background.

X-axis: Two groups: "ISO 9241-110" and "Nielsen's Heuristics".
Y-axis: "F₁-Score" ranging from 0.0 to 1.0.

Each group has 2 bars:
  - "Single-Agent Baseline" (light red #FCA5A5): ISO = 0.81, Nielsen = 0.84
  - "VerSimUX (Ours)" (blue #3B82F6): ISO = 0.88, Nielsen = 0.94

Add value labels on top of each bar.
Add delta annotations: "+7 pts" between the ISO bars, "+10 pts" between the Nielsen bars (with small arrow indicators).

Add a horizontal dashed reference line at 0.85 labeled "Good threshold".

Legend at top-right: red square = Baseline, blue square = VerSimUX.

Style: clean academic bar chart, flat colours, thin axis lines, sans-serif labels, white background, 300 DPI.
```

---

### Figure 7.2 — Persona Fidelity Comparison
**Label:** `fig:action-failure-timeline`
**Caption:** Persona inconsistency and hallucination rate comparison.

**AI Prompt:**
```
Create a side-by-side bar chart on a white background.

X-axis: Two metric groups: "Persona Inconsistency Rate" and "Hallucination Rate".
Y-axis: "Rate (%)" ranging from 0% to 50%.

Each group has 2 bars:
  - "Single-Agent Baseline" (light red #FCA5A5): both at 45%
  - "VerSimUX (Ours)" (blue #3B82F6): 0.8% and 0.9% respectively

Add value labels on top of each bar.
Add a large downward arrow annotation between each pair of bars labeled "−98.2%" and "−98.0%" in bold green text.

Since the VerSimUX bars are very small compared to baseline, make sure they are still visible (minimum bar height with value label).

Legend at top-right.

Style: clean academic bar chart, flat colours, sans-serif labels, white background, 300 DPI.
```

---

### Figure 7.3 — Developer Survey Results
**Label:** `fig:developer-feedback-chart`
**Caption:** Developer survey feedback metrics comparison.

**AI Prompt:**
```
Create a horizontal grouped bar chart on a white background.

Y-axis (categories, top to bottom):
  1. "Trust (1–7 Likert)" — Baseline: 4, VerSimUX: 5
  2. "NASA-TLX Workload (0–100)" — Baseline: 50, VerSimUX: 35 (note: lower = better)
  3. "Utility (1–5 Likert)" — Baseline: 3, VerSimUX: 4
  4. "Fix Correctness (1–5)" — Baseline: 3, VerSimUX: 4
  5. "ACCEPT Rate (%)" — Baseline: 45%, VerSimUX: 65%

X-axis: Scale appropriate for each metric (normalize bars proportionally).

Each category has 2 horizontal bars:
  - "Baseline" (light red #FCA5A5)
  - "VerSimUX" (blue #3B82F6)

Add value labels at the end of each bar.
For NASA-TLX, add a small "(↓ lower = better)" annotation.
For ACCEPT Rate, highlight the "+20pp" improvement in green.

Legend at top-right: red = Baseline, blue = VerSimUX.

Style: clean academic horizontal bar chart, flat colours, sans-serif labels, white background, 300 DPI.
```

---

## Appendix D: Example Pipeline Output

### Figure D.1 — Example Input Page
**Label:** `fig:example-input`

**AI Prompt:**
```
Create a screenshot mockup of a simple login page with intentional accessibility violations.

The page should have a white/light grey background and contain:
- A centered login card (white, subtle shadow, rounded corners)
- A title "Welcome Back" (no <h1> tag — just styled text)
- An email input field WITH NO VISIBLE LABEL (just a placeholder "Email")
- A password input field WITH NO VISIBLE LABEL (just a placeholder "Password")
- A blue "Sign In" button with LOW CONTRAST (light blue #93C5FD text on blue #3B82F6 background)
- A "Forgot password?" link below the button
- NO lang attribute indicator (show a red annotation: "Missing lang attribute")
- Red annotation arrows pointing to: missing labels, low contrast button, no error feedback region

Style: realistic web page mockup with academic annotation overlays (red arrows and labels), 300 DPI.
```

---

### Figure D.2 — Supervisor UIAnalysis Output
**Label:** `fig:example-uianalysis`

**AI Prompt:**
```
Create a formatted JSON code block display on a white background, styled like a code editor.

Show a JSON object with syntax highlighting:
{
  "ui_purpose": "User authentication login form",
  "ui_type": "login form",
  "accessibility_risk_level": "high",
  "detected_issues_hint": [
    "Input #email has no <label> and no aria-label",
    "Input #password has no <label> and no aria-label",
    "<html> tag missing lang attribute",
    "Form #loginForm has no aria-live region for errors",
    "Button .btn-login has insufficient colour contrast"
  ],
  "critical_paths": [{
    "path_id": "path_1",
    "name": "Login flow",
    "steps": ["Enter email", "Enter password", "Click Sign In"],
    "accessibility_sensitive": true
  }],
  "interactive_elements": [
    {"tag": "input", "selector": "#email", "is_accessible": false},
    {"tag": "input", "selector": "#password", "is_accessible": false},
    {"tag": "button", "selector": ".btn-login", "is_accessible": true},
    {"tag": "a", "selector": ".forgot-link", "is_accessible": true}
  ]
}

Style: code editor appearance with line numbers, dark-on-light syntax highlighting, monospace font, white background, 300 DPI.
```

---

### Figures D.3 through D.7

**Note:** Figures D.3–D.7 follow the same pattern as D.2 — formatted JSON code block displays showing:
- **D.3:** An 8-step action trace table/JSON with step_number, action_type, target_selector, reasoning, success, issue_triggered fields
- **D.4:** 3 IssueCluster objects with cluster_id, cluster_label, dominant_severity, issue_count, affected_personas
- **D.5:** 3 PatchProposal objects + 1 ConflictRecord + NegotiationSession JSON
- **D.6:** 2 VerificationResult objects with issues_before/resolved/remaining counts
- **D.7:** DiagnosticReport summary JSON with overall_score, totals, executive_summary excerpt

These are best rendered as **actual formatted JSON in LaTeX lstlisting blocks** rather than AI-generated images. Use the `\begin{lstlisting}[style=jsonstyle]` environment with syntax highlighting.

---

## Summary

| Chapter | Figures | Recommended Tool |
|---|---|---|
| Ch 1 | 2 | AI image generator (conceptual diagrams) |
| Ch 2 | 1 | Spreadsheet / draw.io (matrix table) |
| Ch 3 | 2 | draw.io / Excalidraw (architecture diagrams) |
| Ch 4 | 8 | draw.io / Mermaid (flowcharts, DAGs, swimlanes) |
| Ch 5 | 2 | draw.io / Excalidraw (block diagrams, trees) |
| Ch 6 | 4 | 2x draw.io/Mermaid (architecture, sequence), 2x Real Screenshots |
| Ch 7 | 3 | Python matplotlib / seaborn (charts with real data) |
| App D | 7 | LaTeX lstlisting (formatted JSON code blocks) |
| **Total** | **29** | |
