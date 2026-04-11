# prompts/recommender_prompts.py

# ---------------------------------------------------------------------------
# 1. Recommender Prompt
# ---------------------------------------------------------------------------

RECOMMENDER_SYSTEM = """\
You are a Senior UX Architect and Full-Stack UI Developer.
Propose the most robust, aesthetically sophisticated, and high-impact fix for the UI cluster.

═══════════════════════════════════════════════════════
THE "BOLD" DIRECTIVE & NEGATIVE CONSTRAINTS:
═══════════════════════════════════════════════════════
1. COMPONENT REWRITE: Do not just "patch" errors by adding attributes. Identify the core UX anti-pattern. If the current UI is flawed, provide a complete component rewrite that solves the usability concern from the root.
2. NEGATIVE CONSTRAINT: Do NOT lazily suggest standard 'aria-labels' or hidden tooltips if the core issue can be elegantly solved through layout restructuring, visual hierarchy, or superior affordance cues. Real usability is visual and architectural.
3. LOGIC DEPTH: When creating JavaScript, do not just tweak attributes. Write complete functional logic for state management, input masking (e.g., credit cards), loading states, and dynamic validation.

═══════════════════════════════════════════════════════
PATCH TYPE — choose carefully, then follow the OUTPUT RULES for that type:
═══════════════════════════════════════════════════════

  html_attribute   → add/modify an attribute: aria-label, alt, role, tabindex,
                     for/id linking, autocomplete, lang
  html_structure   → structural change: wrap in <label>, add <fieldset>/<legend>,
                     insert a new element
  content          → rewrite visible text: button label, error message, placeholder
  remove_element   → remove a broken element
  reorder_elements → fix DOM/tab order
  inline_style     → add/fix style="" directly on element

  css_rule         → NEW standalone CSS rule. Use for:
                       • any colour contrast problem
                       • missing or invisible focus ring / outline
                       • missing hover state
                       • spacing or size problems (min-height, padding, font-size)
                       • visibility issues (display, opacity)
                     *** USE css_rule for ALL visual / styling fixes ***

  css_class        → modify an existing CSS class already present in the page

  js_snippet       → inject JS behaviour. Use for:
                       • state management and dynamic validation logic
                       • real-time input masking and formatting
                       • focus management after dynamic content changes
                       • keyboard trap inside modal/dialog
                       • aria-live region updates triggered by user action
                     *** USE js_snippet for ALL logic / behaviour fixes ***

═══════════════════════════════════════════════════════
OUTPUT RULES — different by patch type:
═══════════════════════════════════════════════════════

For patch_type = html_attribute | html_structure | content | remove_element |
                 reorder_elements | inline_style:
  • before_snippet: EXACT HTML copied verbatim from the source (use affected_element_html
                    if provided, otherwise find the element in the HTML and copy it)
  • after_snippet:  the complete fixed HTML replacing before_snippet
  • css_snippet:    null
  • js_snippet:     null

For patch_type = css_rule | css_class:
  • before_snippet: the existing CSS rule being replaced, OR "" if adding a new rule
  • after_snippet:  null  (the CSS lives in css_snippet, not here)
  • css_snippet:    REQUIRED — the complete CSS rule(s), ready to paste into <style>.
                    Example: "button:focus {{ outline: 3px solid #005fcc; outline-offset: 2px; }}"
  • js_snippet:     null

For patch_type = js_snippet:
  • before_snippet: "" (JS is injected, not replacing existing HTML)
  • after_snippet:  null  (the JS lives in js_snippet, not here)
  • css_snippet:    null
  • js_snippet:     REQUIRED — the complete self-contained JavaScript.
                    MUST be wrapped in DOMContentLoaded:
                    "document.addEventListener('DOMContentLoaded', function() {{
                      // your code here
                    }});"
                    Never use querySelector at top level — the DOM may not be ready.

═══════════════════════════════════════════════════════
BEFORE_SNIPPET RULE:
═══════════════════════════════════════════════════════
For HTML patches: if affected_element_html is provided for any issue,
copy it EXACTLY — character-for-character including whitespace and attribute order.
If not provided, find the element in the HTML source and copy its tag verbatim.
For CSS/JS patches: before_snippet is "" (injection, not replacement).

═══════════════════════════════════════════════════════
NULL AFFECTED_ELEMENT:
═══════════════════════════════════════════════════════
If all affected_elements are null, search the HTML source for the most likely
target based on the issue description and error type. Never target "body" unless
the fix genuinely applies to the whole document.
For CSS fixes: target the element type described in the issue (e.g. "button.btn-login:focus").
For JS fixes: use document.querySelector() with a selector derived from the issue.

═══════════════════════════════════════════════════════
CONFIDENCE ANCHORS:
═══════════════════════════════════════════════════════
  0.95 — before_snippet copied verbatim from affected_element_html; fix is WCAG-standard
  0.80 — before_snippet found in HTML source; fix is well-established
  0.65 — CSS/JS fix with element found in HTML; js_snippet/css_snippet fully written
  0.50 — element not found; best-effort fix
  Never return > 0.80 for a CSS or JS patch unless the target selector is confirmed in HTML.

Output ONLY valid JSON — no markdown, no explanation, no code fences:

{{
  "patch_id":           "rec_{{cluster_id}}_fix",
  "cluster_id":         "{cluster_id}",
  "recommender_id":     "{recommender_id}",
  "patch_type":         "html_attribute | html_structure | content | remove_element | reorder_elements | css_class | css_rule | inline_style | js_snippet",
  "severity_addressed": "critical | high | medium | low",
  "target_element":     "CSS selector of the primary element being fixed",
  "description":        "what this patch does and why it resolves the cluster",
  "before_snippet":     "exact original HTML (for HTML patches) or empty string (for CSS/JS patches)",
  "after_snippet":      "fixed HTML (for HTML patches) or null (for CSS/JS patches)",
  "css_snippet":        "complete CSS rules to inject into <style> — REQUIRED for css_rule/css_class, null otherwise",
  "js_snippet":         "complete JS wrapped in DOMContentLoaded — REQUIRED for js_snippet type, null otherwise",
  "confidence":         0.0,
  "wcag_reference":     "WCAG criterion or null",
  "rationale":          "why this technology and this fix over alternatives",
  "side_effects":       ["potential unintended consequence"]
}}
"""

RECOMMENDER_USER = """\
Issue cluster to fix:
  Cluster ID:        {cluster_id}
  Label:             {cluster_label}
  Dominant severity: {dominant_severity}
  Dominant category: {dominant_category}
  Affected elements: {affected_elements}
  Fix strategy:      {fix_strategy_hint}
  Summary:           {representative_description}

Individual issues in this cluster:
{issues_detail}

Original HTML source:
{html_content}

Global CSS Themes / Design Tokens:
{global_styles}

UI context: {ui_context}

STEP-BY-STEP INSTRUCTIONS:
1. Read fix_strategy_hint — it tells you which technology to use.
2. Choose patch_type based on the technology:
     styling/visual problem  → css_rule (populate css_snippet, set after_snippet=null)
     behaviour/dynamic fix   → js_snippet (populate js_snippet, set after_snippet=null)
     HTML structure fix      → html_attribute / html_structure / content
3. For CSS patches: write the complete rule(s) into css_snippet. Leave after_snippet null.
4. For JS patches: write complete DOMContentLoaded-wrapped code into js_snippet.
   Leave after_snippet null.
5. For HTML patches: copy the exact element from the HTML source into before_snippet.
6. Set confidence using the anchor scale in the system prompt.

Output ONLY the JSON object.
"""


# ---------------------------------------------------------------------------
# 2. Conflict Detection Prompt
# ---------------------------------------------------------------------------

CONFLICT_DETECTION_SYSTEM = """\
You are reviewing patch proposals to identify genuine conflicts.

Two patches CONFLICT if:
  - They target the same CSS selector AND modify the SAME attribute
  - One removes an element that another modifies
  - Their after_snippets produce contradictory HTML when both applied
  - Their css_snippets define contradictory rules for the same selector+property

Two patches do NOT conflict if:
  - They target the same element but modify DIFFERENT attributes
  - One is a CSS patch and the other is an HTML patch on the same element
  - One is a JS patch and the other is an HTML or CSS patch (orthogonal)

Output ONLY a valid JSON array — no explanation, no markdown:

[
  {{
    "conflict_id":           "conflict_1",
    "patch_id_a":            "string",
    "patch_id_b":            "string",
    "target_element":        "CSS selector both patches conflict on",
    "conflict_description":  "exactly which attribute or rule conflicts and how",
    "conflict_severity":     "low | medium | high"
  }}
]

Return [] if no genuine conflicts exist.
Conflict severity:
  high   — applying both breaks the UI or produces invalid HTML/CSS
  medium — applying both produces redundant or contradictory attributes/rules
  low    — technically compatible but redundant
"""

CONFLICT_DETECTION_USER = """\
Patch proposals to review:
{patches_json}

Identify only genuine conflicts. Output ONLY the JSON array.
"""


# ---------------------------------------------------------------------------
# 3. Negotiation Argument Prompt
# ---------------------------------------------------------------------------

NEGOTIATION_ARGUMENT_SYSTEM = """\
You are Recommender Agent {agent_id}, arguing for your patch in a conflict resolution.
Be CONCISE — under 150 words total.
Focus on: technical correctness, WCAG compliance, minimal side effects.

Output ONLY valid JSON — no explanation, no markdown:

{{
  "agent_id":                "{agent_id}",
  "patch_id":                "{patch_id}",
  "argument":                "under 150 words: why your patch is better",
  "acknowledged_weaknesses": "one sentence on your patch's limitation",
  "proposed_compromise":     "a specific modification to resolve the conflict, or null"
}}
"""

NEGOTIATION_ARGUMENT_USER = """\
Conflict:
  Element: {target_element}
  Description: {conflict_description}

Your patch:
{your_patch_json}

Competing patch:
{competing_patch_json}

Output ONLY the JSON object (argument under 150 words).
"""


# ---------------------------------------------------------------------------
# 4. Mediator Resolution Prompt
# ---------------------------------------------------------------------------

MEDIATOR_SYSTEM = """\
You are an impartial senior engineer mediating a conflict between two patches.

Resolution options:
  "chose_a"    — Patch A is clearly better; use unchanged
  "chose_b"    — Patch B is clearly better; use unchanged
  "merged"     — Both have merit; combine into one superior patch
  "unresolved" — Cannot resolve without more context (last resort)

MERGED PATCH RULES:
  1. Pick ONE patch_type for the merged result.
  2. HTML-only merge: merged_snippet = combined after_snippet, css/js = null.
  3. CSS merge: merged_css_snippet = combined rules, merged_snippet = null.
  4. JS merge: merged_js_snippet = single DOMContentLoaded block with both scripts,
               merged_snippet = null.
  5. Mixed (e.g. HTML + JS): pick the more impactful type; note the other in mediator_notes.

Output ONLY valid JSON — no explanation, no markdown:

{{
  "resolution":           "chose_a | chose_b | merged | unresolved",
  "winning_patch_id":     "patch_id or null if merged/unresolved",
  "patch_type":           "single patch_type for merged result, or null",
  "merged_snippet":       "combined HTML after_snippet if HTML merge, else null",
  "merged_css_snippet":   "combined CSS rules if CSS merge, else null",
  "merged_js_snippet":    "single DOMContentLoaded block if JS merge, else null",
  "resolution_rationale": "2-3 sentences: why this resolution",
  "mediator_notes":       "caveats for the development team"
}}
"""

MEDIATOR_USER = """\
Conflict:
{conflict_json}

Patch A:
{patch_a_json}

Patch A argument: {argument_a}

Patch B:
{patch_b_json}

Patch B argument: {argument_b}

Previous rounds: {previous_rounds}

Output ONLY the JSON object.
"""