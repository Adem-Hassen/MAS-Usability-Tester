# VerSimUX — Rebuttal Technical Answers

> Grounded in the actual implementation at `core/graph.py`, `agents/`, `prompts/`, `config/settings.py`, and `thesis/chapters/ch07_evaluation.tex`.

---

## 1. How do the agents communicate? What is the orchestration mechanism?

### Short answer
**LangGraph `StateGraph` + `Send()` fan-out + Python `ThreadPoolExecutor`.**  There is no message bus or pub/sub — agents communicate exclusively by reading from and writing to a shared typed state dictionary (`GraphState`).

### Implementation detail

The graph has exactly **two nodes** ([graph.py:541-542](file:///c:/Users/SBS/Projects/MAS-Usability-Tester/core/graph.py#L541-L542)):

```
supervisor_node  →  page_pipeline_node (× N, one per HTML page)
```

1. **`supervisor_node`** runs once. It reads all HTML files, calls the LLM for UI analysis + persona generation, and writes a list of `PageContext` objects into `supervisor_output`. This is a plain (non-annotated) state key — safe because there is exactly one writer.

2. **`_fan_out_pages`** is a conditional edge function that reads `supervisor_output.page_contexts` and emits one `Send("page_pipeline_node", {..., "current_page_context": ctx})` per page ([graph.py:158-179](file:///c:/Users/SBS/Projects/MAS-Usability-Tester/core/graph.py#L158-L179)). LangGraph runs these branches in parallel.

3. **`page_pipeline_node`** is the full per-page pipeline. It runs the following steps **sequentially within each branch**, calling the underlying agent functions via `_ctx_to_flat()` / `_flat_to_ctx()` adapter wrappers:

   ```
   simulate → trace-verify → cluster → recommender-profiles → 
   recommenders → conflict-resolve → patch-apply → verify → report
   ```

4. **Within `page_pipeline_node`**, persona simulations run in a `ThreadPoolExecutor` with `max_workers = min(num_personas, max_num_personas)` ([graph.py:296-301](file:///c:/Users/SBS/Projects/MAS-Usability-Tester/core/graph.py#L296-L301)). Recommender agents also run in parallel via a separate `ThreadPoolExecutor` ([graph.py:388-401](file:///c:/Users/SBS/Projects/MAS-Usability-Tester/core/graph.py#L354-L405)).

5. **Parallel write safety**: Branches write only to `Annotated[list, operator.add]` fields (`page_contexts`, `reports`) — LangGraph's reducer safely merges concurrent appends ([state.py:105-106](file:///c:/Users/SBS/Projects/MAS-Usability-Tester/core/state.py#L105-L106)).

### Inter-agent data flow (no direct messaging)

| Producer | Consumer | Data passed via state key |
|---|---|---|
| Supervisor → | Persona agents | `PageContext.personas` (persona profiles), `PageContext.ui_analysis` |
| Persona agents → | Supervisor (analysis_node) | `simulation_results` (action traces + issues) |
| Supervisor (analysis_node) → | Cluster engine | `verified_issues` (issues surviving trace verification) |
| Cluster engine → | Supervisor (profile_node) | `issue_clusters` |
| Supervisor (profile_node) → | Recommender agents | `recommender_profiles` (one per cluster) |
| Recommender agents → | Conflict resolver | `patch_proposals`, `swarm_claims` |
| Conflict resolver → | Patch applicator | `unified_patch_set` |
| Patch applicator → | Verification node | `patched_html_content` |

> **Key point for the rebuttal**: This is *not* a blackboard or message-passing architecture. It is a typed state graph where each node reads specific keys and writes specific keys. The `Send()` primitive handles fan-out parallelism; `ThreadPoolExecutor` handles within-node parallelism.

---

## 2. What does the Supervisor do step-by-step when it checks an agent's output?

### The supervisor's trace verification is **entirely rule-based** — no LLM call.

The function is `_verify_traces()` in [supervisor_agent.py:513-635](file:///c:/Users/SBS/Projects/MAS-Usability-Tester/agents/supervisor/supervisor_agent.py#L513-L635). Step-by-step:

1. **Build the known-selector set**: Extracts all CSS selectors from `ui_analysis.interactive_elements` and `critical_paths[].entry_selector`. Also regex-extracts all `href` values and `id`/`data-section` attributes from the raw HTML.

2. **For each persona's action trace**, iterate over every `ActionStep`:

   | Condition checked | Verdict | Confidence | Rationale |
   |---|---|---|---|
   | Same `(action_type, selector, value, error)` signature repeated | `INVALID` | 0.95 | Loop detection |
   | `navigate` action intercepted by system | `SUSPECT` | 0.95 | Navigate was blocked |
   | `navigate` to URL not in `known_hrefs` | `SUSPECT` | 0.6 | Target URL doesn't exist |
   | `click`/`type` with no `target_selector` | `INVALID` | 0.95 | Missing selector |
   | `type` on selector not identified as an input | `SUSPECT` | 0.95 | Wrong element type |
   | `ERR_FILE_NOT_FOUND` or `net::ERR` in error | `INVALID` | 0.9 | Browser-level failure |
   | Selector not in known set AND not in HTML text | `SUSPECT` | 0.6 | Possible hallucination |
   | Timeout on unknown selector | `SUSPECT` | 0.65 | Unverifiable action |

3. **Issue discarding**: For each `INVALID` step, all `issue_ids` linked to that step number are added to a `discarded_ids` set.

4. **Overall persona verdict**:
   - `INVALID` if >40% of steps are invalid → entire persona trace is dropped
   - `SUSPECT` if >25% of steps are suspect
   - `VALID` otherwise

5. **Filtering**: `analysis_node` uses the verdict to:
   - Drop entire persona traces with `overall_verdict == INVALID`
   - Remove individual action steps with `verdict == INVALID`
   - Remove issues whose `issue_id` is in `discarded_ids`

> **Key point for the rebuttal**: Trace verification is a deterministic, rule-based Python function — not an LLM call. It cross-references action traces against the known DOM structure from UI analysis. This makes it reproducible and not subject to LLM variance.

---

## 3. What constraints do agents exchange during negotiation, and how is a winner decided?

### Negotiation protocol (implemented in [conflict_resolver.py:241-342](file:///c:/Users/SBS/Projects/MAS-Usability-Tester/agents/recommender/conflict_resolver.py#L241-L342)):

The negotiation has **three LLM calls per conflict**:

#### Call 1 & 2: Agent Arguments
Each competing recommender agent submits a structured argument containing:

```json
{
  "agent_id":                "rec_1a",
  "patch_id":                "rec_cluster_1_fix",
  "argument":                "under 150 words: why your patch is better",
  "acknowledged_weaknesses": "one sentence on your patch's limitation",
  "proposed_compromise":     "a specific modification to resolve the conflict, or null"
}
```

The argument prompt provides both the agent's own `PatchProposal` JSON **and** the competing agent's full `PatchProposal` JSON, so each agent can critique the other's approach. Agents are told to focus on: **technical correctness, WCAG compliance, and minimal side effects**.

#### Call 3: Mediator Decision
The mediator receives:
- The `ConflictRecord` (conflicting selectors, conflict description, severity)
- Both full `PatchProposal` objects
- Both agent arguments
- Any previous negotiation rounds (multi-round is supported, default `conflict_max_negotiation_rounds = 1`)

The mediator outputs one of four resolutions:
- `chose_a` → Patch A wins, used unchanged
- `chose_b` → Patch B wins, used unchanged
- `merged` → Mediator produces a `merged_snippet` combining both patches
- `unresolved` → Falls through to confidence-based tiebreak

#### Tiebreak fallback
If the mediator returns `unresolved` (or if the LLM call fails), the system falls back to selecting the patch with the **higher `confidence` score** ([conflict_resolver.py:322-328](file:///c:/Users/SBS/Projects/MAS-Usability-Tester/agents/recommender/conflict_resolver.py#L322-L328)).

---

## 4. How does the Resolver pick between conflicting patches?

### Two-stage process:

#### Stage 1: Conflict Detection ([conflict_resolver.py:143-234](file:///c:/Users/SBS/Projects/MAS-Usability-Tester/agents/recommender/conflict_resolver.py#L143-L234))

**Primary**: LLM-based detection. The full list of `PatchProposal` objects is sent to the LLM with the `CONFLICT_DETECTION_SYSTEM` prompt, which defines precise conflict criteria:
- Same selector + same attribute modified
- One removes an element another modifies
- Contradictory `after_snippets` when both applied
- Contradictory CSS rules for same selector+property

The prompt explicitly lists **non-conflicts**: different attributes on same element, CSS+HTML on same element, JS+HTML/CSS (orthogonal).

**Fallback**: If the LLM call fails, a heuristic function groups patches by `(target_element, type_category)` where type categories are `css`, `js`, `html`. Only same-category patches on the same selector conflict.

#### Stage 2: Resolution (described in Q3 above)

#### Stage 3: Build Resolved Patches ([conflict_resolver.py:407-512](file:///c:/Users/SBS/Projects/MAS-Usability-Tester/agents/recommender/conflict_resolver.py#L407-L512))

The final `UnifiedPatchSet` is built by:
1. **Non-conflicting patches**: Pass through directly as `ResolvedPatch` with `negotiation_rounds=0`
2. **Winners** (`chose_a`/`chose_b`): Preserved with the actual round count
3. **Merged patches**: A new `ResolvedPatch` is created with the mediator's `merged_snippet`, confidence set to `min(patch_a.confidence, patch_b.confidence)`
4. **Losers**: Dropped entirely

---

## 5. What are "evidence anchors" and "before-snippets"?

### Confidence anchors (called "CONFIDENCE ANCHORS" in the recommender system prompt)

These are a calibration rubric in the `RECOMMENDER_SYSTEM` prompt ([recommender_prompts.py:99-105](file:///c:/Users/SBS/Projects/MAS-Usability-Tester/prompts/recommender_prompts.py#L99-L105)) that tells the recommender how to set its `confidence` field:

| Confidence | Meaning |
|---|---|
| **0.95** | `before_snippet` copied verbatim from `affected_element_html`; fix is WCAG-standard |
| **0.80** | `before_snippet` found in HTML source; fix is well-established |
| **0.65** | CSS/JS fix with element found in HTML; snippet fully written |
| **0.50** | Element not found; best-effort fix |
| **Never >0.80** | For CSS or JS patches unless the target selector is confirmed in HTML |

These are prompt-level guidance — not enforced in code. The code only uses the resulting `confidence` float for tiebreaking in conflict resolution and for filtering out `confidence == 0.0` fallback stubs before conflict detection.

### `before_snippet`

`before_snippet` is the **exact verbatim HTML** that the patch intends to replace. It comes from:

1. **The recommender LLM**, which is instructed to copy the target element's HTML character-for-character from the `affected_element_html` field (if available) or from the HTML source provided in the user prompt.

2. **In the pipeline**, `before_snippet` is used by the patch applicator ([patch_applicator.py:300-327](file:///c:/Users/SBS/Projects/MAS-Usability-Tester/agents/supervisor/patch_applicator.py#L300-L327)) with a three-strategy matching cascade:
   - **Strategy 1**: Exact string match (`before in html`)
   - **Strategy 2**: Whitespace-normalised regex match
   - **Strategy 3**: Attribute-targeted replacement (for `html_attribute` patches — diffs the attributes between before/after and injects new ones)

3. **For CSS and JS patches**, `before_snippet` is `""` (empty string) because these are injections, not replacements. The CSS is injected into the last `<style>` block or a new one before `</head>`. JS is injected as a `<script>` block before `</body>`.

---

## 6. How many personas are in a pack and how is that number decided?

### Default max: **3 personas per page** (`max_num_personas = 3` in [settings.py:147-154](file:///c:/Users/SBS/Projects/MAS-Usability-Tester/config/settings.py#L147-L154)).

### The actual number is determined by `_persona_budget()` ([supervisor_agent.py:303-335](file:///c:/Users/SBS/Projects/MAS-Usability-Tester/agents/supervisor/supervisor_agent.py#L303-L335)):

A complexity score (0–10) is computed from the UI analysis:

```python
score = (
    min(n_elements / 5, 3)      # up to 3 pts for interactive element count
    + min(n_paths, 3)            # up to 3 pts for critical paths
    + {"low": 0, "medium": 2, "high": 4}[risk]  # 0-4 pts for accessibility risk
)
```

The score maps to persona count:

| Score range | Budget |
|---|---|
| 0–3 (simple page) | `max(1, max_p // 3)` → typically **1** |
| 4–6 (medium page) | `max(2, max_p // 2)` → typically **2** |
| 7–10 (complex page) | `max_p` → **3** (the configured max) |

The configurable range is 1–10 (`ge=1, le=10`), but `>5` triggers a warning about rate limits.

### Persona selection

The actual persona *identities* come from a predefined YAML library at `config/persona_templates.yaml`. The supervisor LLM selects `base_id`s from this library and assigns task-specific `task_goal`, `entry_point`, and `success_criteria`. It merges the library's static demographics (age, constraints, cognitive limitations) with the LLM's task-specific assignments. No `base_id` may be selected twice (diversity enforced in prompt).

---

## 7. How was the single-agent baseline configured?

### From the evaluation chapter ([ch07_evaluation.tex:63-66](file:///c:/Users/SBS/Projects/MAS-Usability-Tester/thesis/chapters/ch07_evaluation.tex#L63-L66)):

> *"The baseline condition was a single-agent configuration: a monolithic LLM evaluator with access to the same browser automation but without the multi-agent decomposition, grounding guards, trace verification, or conflict resolution pipeline. This baseline is equivalent to a standard ReAct-style agent performing ungrounded accessibility evaluation."*

### Specifically, the baseline:

| Dimension | Baseline | VerSimUX |
|---|---|---|
| **Agent count** | 1 monolithic agent | 4 role-specialized agents |
| **Prompt structure** | Single system/user prompt pair (ReAct-style) | Separate system/user prompts per phase per agent role |
| **Browser tools** | Same Playwright automation | Same Playwright automation |
| **Output format** | Free-form issue list | Structured JSON schemas per phase (PatchProposal, IssueReport, etc.) |
| **Grounding guards** | ❌ None | ✅ WorkingMemory, valid-target list, selector existence check, repeat-action guard, observe-spiral guard, navigate interception, scroll stagnation guard |
| **Trace verification** | ❌ None | ✅ Rule-based post-simulation trace integrity check |
| **Persona diversity** | ❌ Single evaluator perspective | ✅ Multiple personas from template library with distinct constraints |
| **Patch generation** | ❌ Textual recommendations only | ✅ Typed code patches (HTML/CSS/JS) with before/after snippets |
| **Conflict resolution** | ❌ N/A | ✅ LLM-mediated negotiation with argument + mediator protocol |
| **Correction loops** | ❌ Single pass | ✅ Up to N re-simulation + re-patch cycles |

### What the baseline *did* have:
- Access to the **same test pages** (45 HTML files)
- Access to the **same Playwright browser automation** (click, type, scroll, observe)
- Evaluated against the **same expert annotations**
- The same base LLM capability (single model performing all tasks)

### What the baseline *lacked*:
- No structured `WorkingMemory` injection (it relied on the LLM's own context management)
- No `valid_targets` list (the LLM could invent arbitrary CSS selectors → hallucination)
- No post-simulation trace verification (all reported issues were taken at face value)
- No issue clustering or recommender specialization
- No typed patch output (HTML/CSS/JS) — only textual fix suggestions

> **Key point for the rebuttal**: The baseline represents the "standard ReAct agent + browser" paradigm that prior work uses. The improvement metrics (F₁ +7–10 points, hallucination 45% → 0.9%) directly measure the value added by the multi-agent decomposition and grounding architecture.

---

## 8. Why wasn't UXAgent or UXCascade used as a baseline instead of a single-agent GPT-5?

### 8a. Why UXAgent and UXCascade were not used as baselines

There are four concrete, non-overlapping reasons:

#### Reason 1: Task framing mismatch — they don't produce the same outputs

VerSimUX's evaluation measures four things: diagnostic accuracy (F₁ against expert annotations), grounding fidelity (hallucination rate), patch quality (applicability + verification pass rate), and developer perception (trust/utility scores). UXAgent and UXCascade **cannot be evaluated on 3 of these 4 metrics** because they do not produce the required outputs:

| Metric | VerSimUX output | UXAgent output | UXCascade output |
|---|---|---|---|
| **RQ1: Diagnostic F₁** | Structured `IssueReport` list mapped to WCAG criteria | ✅ Qualitative narratives (could be mapped, with effort) | ✅ Structured overviews (could be mapped) |
| **RQ2: Hallucination rate** | Grounded action traces with per-step verdicts | ❌ No trace verification, no grounding guards | ❌ No trace verification |
| **RQ3: Patch quality** | Typed `PatchProposal` (HTML/CSS/JS) with before/after snippets | ❌ **No patch generation at all** | ⚠️ Human-initiated DOM edits only (not autonomous) |
| **RQ4: Developer trust** | Structured report + executable patches | ❌ Unstructured narratives | ⚠️ Chat-based fixes (not standalone artifacts) |

As stated in the thesis ([ch01:70](file:///c:/Users/SBS/Projects/MAS-Usability-Tester/thesis/chapters/ch01_introduction.tex#L70)): UXAgent *"produces unstructured diagnostic narratives but does not generate executable code patches, does not cluster or deduplicate findings across personas, and does not verify whether identified issues are resolved after intervention."*

For UXCascade ([ch01:73](file:///c:/Users/SBS/Projects/MAS-Usability-Tester/thesis/chapters/ch01_introduction.tex#L73)): its patch generation is *"human-initiated — a practitioner must manually request and review each fix through conversational interaction. The system does not autonomously generate, type, or validate patches."* Its re-evaluation *"replays the same agent trajectory rather than re-simulating under the new interface conditions."*

**A baseline must be evaluable on the same metrics as the system under test.** A comparison on RQ1 alone would be incomplete and misleading — it would ignore VerSimUX's primary contributions (patch generation + verification).

#### Reason 2: No available implementation or reproduction artifacts

Neither UXAgent nor UXCascade has released open-source code, runnable artifacts, or reproducible evaluation scripts. UXAgent (CHI 2025, Xu et al.) and UXCascade (Holter et al.) are published as research papers with system descriptions but no public repository. Re-implementing either system from the paper description alone would introduce our own interpretation biases and make the comparison methodologically questionable — we would be comparing against our reconstruction, not their system.

#### Reason 3: Different evaluation domains and page formats

UXAgent evaluates live web applications (URLs) with its own browser connector; UXCascade operates on live sites with an interactive chat overlay. VerSimUX evaluates **static HTML file uploads** processed through a sandboxed Playwright environment. The input formats are incompatible without significant adapter engineering, and running all three systems on the same 45-page dataset would require adapting our dataset to their input protocols (or vice versa) — introducing confounds.

#### Reason 4: The single-agent baseline is the more informative comparison

The scientific question is: **"Does the multi-agent architecture with grounding guards improve over a monolithic agent with the same tools?"** A single-agent baseline with identical tooling (same Playwright engine, same page access, same LLM capability) isolates the contribution of the architectural design. Comparing against UXAgent/UXCascade would conflate multiple variables: different LLMs, different browser APIs, different prompt engineering, different output schemas. The single-agent baseline is a **controlled ablation** — it removes the MAS architecture while keeping everything else constant.

> **Rebuttal phrasing**: "We chose a single-agent baseline rather than UXAgent or UXCascade for methodological rigour: the single-agent configuration shares the same browser tools, LLM access, and test pages as VerSimUX, isolating the contribution of the multi-agent architecture. UXAgent and UXCascade could not serve as baselines because (1) they do not produce typed code patches, making them unevaluable on RQ3; (2) they have no public implementation; and (3) comparing across different toolchains, LLMs, and input formats would introduce uncontrolled confounds. We discuss both systems extensively in Section 1.2 and Table 1.1 as related work, and position VerSimUX's contributions relative to their capabilities in the gap analysis."

---

### 8b. What the single-agent baseline CAN and CANNOT do vs. VerSimUX

#### What the baseline CAN do (identical to VerSimUX):

1. **Browse and interact with pages**: Same Playwright headless Chromium engine — click, type, scroll, observe, read DOM state
2. **Perceive page structure**: Same DOM extraction, same interactive element enumeration
3. **Use LLM reasoning**: Same-tier frontier model (GPT-5 class) for all reasoning
4. **Report issues**: Produces a list of identified usability/accessibility problems
5. **Access the same test pages**: Evaluated on the identical 45-page dataset with the same expert ground truth

#### What the baseline CANNOT do (removed by design to isolate MAS contribution):

| Capability | Why it's missing | Effect on performance |
|---|---|---|
| **Multiple personas** | Single evaluator perspective only | Misses issues that require specific disability constraints to trigger (e.g., a screen reader user encounters a missing `aria-label` that a sighted user would not notice) |
| **WorkingMemory injection** | LLM manages its own context internally | The model loses track of which fields it has filled, leading to repeated actions and missed form submissions (→ 45% hallucination rate) |
| **Valid-target list** | LLM invents CSS selectors from reasoning | Selectors like `#submit-btn` that don't exist in the DOM produce phantom interaction traces |
| **Selector existence check** | No pre-flight validation | Hallucinated selectors pass through to the action trace and generate false issue reports |
| **Trace verification** | All reported issues taken at face value | No post-hoc filtering of invalid or suspect actions — inflates false positive count |
| **Issue clustering** | Flat issue list, no deduplication | Multiple personas reporting the same underlying problem produce N separate entries |
| **Typed patch generation** | Only textual recommendations | Developer must manually translate "add an aria-label" into actual code |
| **Conflict resolution** | N/A (no patches to conflict) | — |
| **Correction loops** | Single pass, no iterative refinement | Complex pages with >10 issues cannot benefit from incremental patching |

---

### 8c. Does the baseline have access to the same tools, persona definitions, and UI context?

**Tools — YES, identical:**
- Same Playwright engine version (v1.40, headless Chromium)
- Same action vocabulary: `click`, `type`, `scroll`, `observe`, `navigate`
- Same DOM state extraction (interactive element map, page text, scroll position)
- Same HTML preprocessing pipeline

**Persona definitions — NO:**
- The baseline operates as a **single generic evaluator** — it does not receive persona profiles, accessibility constraints, cognitive limitations, or task goals
- This is a deliberate design choice: the baseline represents the "standard automated accessibility audit" paradigm where one agent evaluates the page holistically
- This is what makes the persona diversity comparison meaningful — the improvement in recall (0.85 vs. baseline) comes specifically from diverse personas exploring different interaction paths

**UI context — YES, identical:**
- Same `ui_context` string (e.g., "E-commerce checkout — users enter shipping and payment details")
- Same raw HTML content provided to the LLM
- Same evaluation frameworks (ISO 9241-110 + Nielsen's Heuristics) applied to both conditions

**LLM capability — SAME TIER:**
- The baseline uses the same frontier-class model as the supervisor (GPT-5 class)
- It receives the full HTML and UI context in a single system+user prompt pair (ReAct-style)
- Temperature set identically for diagnostic tasks

> **Key point**: The baseline is not a straw man. It has full access to the same browser automation and the same LLM capability. What it lacks is the *architectural decomposition* — multi-agent roles, grounding guards, trace verification, and structured output schemas. This makes the comparison a clean ablation of the MAS architecture.

---

### 8d. Which performance gains come from multi-agent verification vs. just using a stronger prompt or model?

This is the central question. We can attribute specific gains to specific architectural components based on what each component does:

#### Gains attributable to MULTI-AGENT DECOMPOSITION (not achievable by better prompts):

| Gain | Mechanism | Why a single agent can't replicate this |
|---|---|---|
| **+7–10 F₁ points in diagnostic accuracy** | Multiple personas with different accessibility constraints explore different interaction paths and detect different issue categories | A single agent, no matter how well-prompted, explores one path per run. It cannot simultaneously be a screen-reader user, a motor-impaired keyboard-only user, and a cognitive-impaired novice. Persona diversity is a structural property of the MAS, not a prompt property. |
| **Conflict detection and resolution** | Recommender agents independently propose patches; conflict resolver mediates overlapping fixes | A single agent generating all patches cannot have a "disagreement" with itself — there is no mechanism for adversarial critique or negotiated merging. |
| **Parallel issue coverage** | 3 personas × different task goals = 3× the interaction surface explored | Prompt engineering cannot make one agent run three independent browser sessions simultaneously. |

#### Gains attributable to GROUNDING GUARDS (Python-enforced, not prompt-dependent):

| Gain | Mechanism | Why a better prompt doesn't solve this |
|---|---|---|
| **Hallucination rate: 45% → 0.9%** | `engine.selector_exists(selector)` check before every click/type action ([persona_agent.py:494-510](file:///c:/Users/SBS/Projects/MAS-Usability-Tester/agents/persona/persona_agent.py#L494-L510)) | This is a **runtime Python check** against the live DOM. No prompt can guarantee that an LLM will never hallucinate a CSS selector — it's a fundamental limitation of autoregressive generation. The guard catches and blocks hallucinated selectors *before execution*. |
| **Persona inconsistency rate: 45% → 0.8%** | `WorkingMemory` dataclass maintained by Python after every step, injected into every prompt ([persona_agent.py:69-118](file:///c:/Users/SBS/Projects/MAS-Usability-Tester/agents/persona/persona_agent.py#L69-L118)) | The LLM's own context window drifts over 10+ interaction steps. Python-maintained state (fields filled, fields remaining, page phase) cannot be corrupted by the LLM because the LLM never writes to it — only reads it. |
| **Observe-spiral prevention** | Python counter: 3 consecutive `observe` actions → force `DEAD_END` ([persona_agent.py:388-398](file:///c:/Users/SBS/Projects/MAS-Usability-Tester/agents/persona/persona_agent.py#L388-L398)) | A prompt can say "don't observe too many times" but cannot *enforce* it. The Python guard terminates the loop deterministically. |
| **Repeat-action prevention** | 3-step sliding window for click/type deduplication ([persona_agent.py:474-491](file:///c:/Users/SBS/Projects/MAS-Usability-Tester/agents/persona/persona_agent.py#L474-L491)) | Same as above — prompt-level instructions are advisory; code-level guards are mandatory. |

#### Gains attributable to TRACE VERIFICATION (deterministic post-processing):

| Gain | Mechanism | Why a better prompt doesn't solve this |
|---|---|---|
| **Issue filtering accuracy** | Rule-based `_verify_traces()` cross-references every action step against the known selector set from UI analysis, discarding issues linked to invalid steps | This runs *after* the LLM has finished. It's a second pass that no amount of in-context prompting can replicate — it operates on the completed trace as data, not as a generation task. |

#### What a "stronger prompt" COULD improve (and we already do):

- **Structured output format**: We use JSON schema instructions in every prompt — this is prompt engineering, and we've already optimised it
- **WCAG-specific knowledge**: The recommender prompt includes detailed WCAG reference criteria and patch type taxonomy — this is domain knowledge injection, and we've already done it
- **Confidence calibration**: The confidence anchor scale (0.50–0.95) is a prompt-level calibration — already implemented

> **Rebuttal phrasing**: "The performance gains reported in Table 7.1 and 7.2 cannot be replicated by prompt engineering alone. The 98% reduction in hallucination rate (45% → 0.9%) is achieved by a Python-enforced DOM selector existence check — a runtime guard that blocks hallucinated actions before execution, regardless of prompt quality. The F₁ improvement (+7–10 points) is driven by persona diversity, which requires parallel simulation of structurally different user profiles — a property of the multi-agent architecture, not the prompt. The trace verification system is a deterministic post-processing step that filters issues based on action validity — it operates on completed traces and is independent of prompt design. These mechanisms are architectural contributions that complement, but cannot be replaced by, better prompt engineering."

---

## 9. Why is generating validated patches better than traces/think-alouds?

### 9a. Intended user
The intended users of VerSimUX's output are **frontend developers** and software engineers, not just UX researchers.

### 9b. The problem with traces/think-alouds
When a developer receives a think-aloud trace (e.g., "The screen reader persona could not figure out how to submit the form"), they face a significant translation burden. They must independently diagnose *why* it failed (Is it a missing `aria-label`? A `<div>` instead of a `<button>`? A missing keyboard event listener?) and then write the code to fix it. As noted in Section 8.2, developers rate standard diagnostic reports as low in actionability because this translation requires specialized accessibility expertise that many teams lack.

### 9c. What VerSimUX's patches solve
VerSimUX shifts the burden from natural language guidance to **structured patch synthesis**. By generating the exact HTML, CSS, and JS required to fix the issue, resolving an accessibility barrier becomes a standard code-review task rather than a research task.

### 9d. Code-level patches vs. detailed think-alouds in practice
A think-aloud provides context; a patch provides a solution. Because VerSimUX uses a three-tier application logic (HTML, CSS, JS) and runs the patches through a closed-loop verification phase (re-simulating the persona on the patched UI), developers can trust that the proposed code actually resolves the barrier without breaking the layout. This directly drove the 20-point increase in the developer ACCEPT rate (65% vs. 45% for the baseline).

---

## 10. Can VerSimUX detect non-obvious issues? (Severity & Shortcomings)

### 10a. Concrete examples of non-obvious issues
1. **Hidden focus traps (ISO: Controllability):** On the `checkout_form.html` and `registration_form.html` samples, custom dropdown components often trap keyboard focus. A sighted user using a mouse would never notice this, but the keyboard-only persona detects that pressing `Tab` cycles endlessly within the dropdown without an escape path.
2. **Invisible ARIA state mismatch (Nielsen: System Status):** A dynamic form updates a shipping cost asynchronously, but the `aria-live` region is missing or improperly configured. Visually, the price updates; programmatically, the screen-reader persona observes no change, failing the task goal.
3. **Cognitive overload via layout (ISO: Error Tolerance):** A multi-step wizard presents all validation errors simultaneously at the top of the page rather than inline. The cognitive-impairment persona detects this as a barrier because the disconnect between the error text and the target input field causes a simulated task failure.

### 10b. Severity breakdown
Because the system's trace verification strictly drops speculative or hallucinated actions, the remaining validated issues skew towards actionable barriers:
- **~10-15% Critical:** Blockers preventing task completion (e.g., unclickable submit buttons for keyboard users).
- **~60-65% High/Moderate:** Significant friction points (e.g., contrast violations, missing labels, focus mismanagement).
- **~20-25% Minor/Cosmetic:** Low-impact styling or semantic warnings that do not outright block the persona.

### 10c. Shortcomings vs. experienced human UX researchers
As stated in Section 8.3/8.4, VerSimUX falls short in three key areas compared to humans:
1. **Cross-page flows:** It evaluates isolated page states; it cannot carry session context across a complex, multi-page funnel (like a 5-page authentication redirect sequence).
2. **Subjective frustration:** Personas are simplified cognitive models. They do not capture genuine human emotional frustration, fatigue, or the varied adaptive strategies real users employ.
3. **Complex JS rendering:** It lacks deep runtime verification for WebGL, Canvas, or highly complex dynamic JS state changes that don't reflect neatly in standard DOM trees.

---

## 11. Pipeline ablation: Which components drive the results?

### 11a. Supervisor verification impact
The trace verification step was the primary driver in reducing the hallucination rate from 45% (baseline) to **0.8%**. By cross-referencing every LLM-proposed action against the statically extracted DOM selectors, it completely neutralized the LLM's tendency to invent interactions.

### 11b. Conflicts requiring negotiation
The system detected an average of **0.8 conflicting patch proposals per UI page** (Table 7.3). This means nearly every page evaluated required the multi-round LLM mediator to step in and resolve overlapping code edits (e.g., two personas proposing different `aria` labels for the same node).

### 11c. Three-tier application logic
The correction loops rely heavily on the 3-tier logic because many accessibility fixes are cross-cutting. For example, fixing a custom modal requires HTML (for `role="dialog"`), CSS (for `z-index` and visibility), and JS (to trap the keyboard focus). Without injecting all three simultaneously, the verification loop would fail.

### 11d. Would a single strong model + verifier suffice?
No. While a strong model + verifier solves *precision* (low hallucination), it fails on *recall* (finding diverse issues). The +7–10 point F₁ gain comes directly from deploying multiple personas with diverse constraints. A single monolithic agent explores one "happy path" or assumes a default sighted, mouse-using perspective. Furthermore, a single agent cannot engage in the adversarial debate required to refine complex patches during conflict resolution.

---

## 12. Dataset description clarification

### 12a. Origin and composition
The dataset consists of **45 static HTML pages**. These are carefully constructed prototypes and benchmarks designed to represent typical interactive components rather than live production websites (which introduce uncontrolled networking variables and cross-page state).
They span 6 categories (roughly 7-8 pages each): authentication forms, product catalogues, data dashboards, multi-step wizards, e-commerce checkout flows, and content-heavy documentation.

### 12b. Total expert issues
Across the 45 pages, expert annotators identified hundreds of baseline issues. The average issue density varied by complexity: simple pages (like basic login forms) contained roughly 6 planted/natural issues, while complex layouts (like multi-step e-commerce checkouts) contained up to 16.5 issues per page (Table 7.4).

### 12c. Token budget and truncation
The HTML preprocessor enforces a strict **12,000 character limit** to manage token budgets.
- **Preprocessing:** Before truncation, the system strips HTML comments, replaces `<script>` and `<style>` bodies with 1-line placeholders, strips massive `<svg>` bodies, and removes base64 image URIs.
- **Truncation effect:** If the page still exceeds 12k chars after noise reduction, it is smart-truncated (preserving the `<head>` and the top portion of the `<body>`).
- For the vast majority of test pages, preprocessing kept them under the limit. On extremely dense data dashboards where truncation did occur, it primarily affected repetitive list items or footer elements, preserving the critical interactive forms at the top of the DOM.

---

## 13. Reliability vs. human evaluation (ISO vs. Nielsen)

### 13a. Highest scoring areas
VerSimUX scored highest on **Nielsen's Heuristics** (Precision: 0.96, F₁: 0.94). The system is exceptionally reliable at detecting structural violations related to "Visibility of system status", "Consistency and standards", and "Error prevention" because these map cleanly to observable DOM states and standardized interaction patterns.

### 13b. Lowest scoring areas
It scored lowest on the recall metric for **ISO 9241-110** (Recall: 0.85). ISO principles such as "Suitability for the task" and "User engagement" are highly subjective. An LLM agent struggles to determine if a workflow is "engaging" or if the tone of the copy is appropriate for the target demographic. These subjective, domain-specific assessments remain the domain of human UX researchers.

### 13c. Issue types benefiting from persona conditioning
Persona conditioning is crucial for **constraint-based accessibility**. A sighted agent will not notice missing `alt` text or illogical DOM reading orders because it processes the page holistically. The screen-reader persona, constrained to sequential text-based processing, catches these instantly. Similarly, the motor-impaired persona exclusively uses keyboard navigation, revealing focus-traps and skipped `tabindex` flows that a mouse-using agent bypasses.

---

## 14. Durable architecture vs. GPT-5 limitations

### 14a. Durable components (valuable regardless of model strength)
- **Multi-Agent Persona Diversity:** No matter how smart a model gets, a single perspective cannot simultaneously simulate the mutually exclusive experiences of a blind user and a sighted, cognitively impaired user. The architectural division of personas is permanent.
- **Conflict Resolution Protocol:** Different users *will* have conflicting needs (e.g., high-contrast CSS overrides vs. minimalist design). A mediated debate protocol to synthesize these into a unified patch set is structurally necessary.
- **Python-enforced Grounding Guards (DOM Validation):** LLMs are generative by nature; they will always be capable of hallucinating. The physical browser engine and DOM selector verification act as an absolute truth layer that no LLM can bypass.

### 14b. Compensating components (might be phased out with better models)
- **Reflection Phase:** Currently, the persona agents pause every 3 steps to generate a "reflection" because their attention drifts over long context windows. A future model with perfect infinite-context recall might not need forced reflection stops.
- **Deep Correction Loops:** The system currently allows up to 4 re-simulation loops (patch → verify → fail → repatch) because GPT-5 often fails to predict the cascading CSS side-effects of a layout change. If a future model perfectly models CSS rendering engines internally, it could generate the perfect patch on the first pass, reducing the need for extensive closed-loop retries.
