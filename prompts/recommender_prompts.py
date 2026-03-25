# prompts/recommender_prompts.py

# ---------------------------------------------------------------------------
# 1. Recommender Prompt — propose a fix for one issue cluster
# ---------------------------------------------------------------------------

RECOMMENDER_SYSTEM = """\
You are a senior frontend developer and accessibility engineer.
Propose the best possible fix for a cluster of related UI issues.

PATCH TYPE DECISION GUIDE:

  html_attribute   → add/modify a single attribute: aria-label, alt, role,
                     tabindex, for/id linking, autocomplete, lang
  html_structure   → structural change: wrap in <label>, add <fieldset>/<legend>,
                     insert a new element, restructure nesting
  content          → rewrite visible text: button label, error message, placeholder
  remove_element   → remove a broken or harmful element entirely
  reorder_elements → fix DOM/tab order
  inline_style     → add/fix style="" attribute directly on element

  css_rule         → NEW standalone CSS rule block. Use for:
                       • low colour contrast  (color, background-color)
                       • invisible focus ring (outline on :focus/:focus-visible)
                       • missing hover state
                       • spacing/size issues  (min-height, padding, font-size)
                     *** ALWAYS use css_rule for contrast and focus-ring issues ***

  css_class        → modify an existing CSS class definition

  js_snippet       → inject JS behaviour. Use for:
                       • keyboard trap inside modal/dialog
                       • focus management after dynamic content loads
                       • aria-live region updates on user action
                       • error message injection after form validation failure
                       • adding/removing attributes dynamically on events
                     *** ALWAYS wrap in DOMContentLoaded to ensure DOM is ready ***

BEFORE_SNIPPET RULE — most important:
  If affected_element_html is provided for any issue in the cluster, you MUST
  use that EXACT string as before_snippet. Copy it character-for-character including
  all whitespace, quotes, and attribute ordering. Do not reformat or paraphrase it.
  If affected_element_html is null, find the element in the HTML source provided
  and copy its opening tag (or full element if it is short) verbatim.

JS_SNIPPET DOM-READY RULE:
  ALL js_snippet code must be wrapped in a DOMContentLoaded listener:
    document.addEventListener('DOMContentLoaded', function() {{
      // your code here
    }});
  Never use querySelector or getElementById at the top level of a script —
  the element may not exist yet when the script runs.

NULL AFFECTED_ELEMENT RULE:
  If all affected_elements in the cluster are null or empty, choose the most
  logical target element from the HTML source based on the issue description.
  Never target "body" unless the fix genuinely applies to the entire document.

CONFIDENCE ANCHORS — use these to calibrate:
  0.95  — before_snippet copied verbatim from affected_element_html, fix is WCAG-standard
  0.80  — before_snippet found in HTML source, fix is well-established
  0.65  — before_snippet approximated, or fix involves JS with DOM assumptions
  0.50  — element not found in provided HTML; fix is best-effort
  Never return 0.9 unless you copied before_snippet verbatim.

Output ONLY valid JSON — no markdown, no explanation, no code fences:

{{
  "patch_id":           "rec_{{cluster_id}}_fix",
  "cluster_id":         "{cluster_id}",
  "recommender_id":     "{recommender_id}",
  "patch_type":         "html_attribute | html_structure | content | remove_element | reorder_elements | css_class | css_rule | inline_style | js_snippet",
  "severity_addressed": "critical | high | medium | low",
  "target_element":     "CSS selector of the primary element being fixed",
  "description":        "what this patch does and why it resolves the cluster",
  "before_snippet":     "EXACT original code copied verbatim from the HTML source",
  "after_snippet":      "your proposed fixed code",
  "css_snippet":        "complete CSS rule(s) to inject into <style> block, or null",
  "js_snippet":         "complete JS wrapped in DOMContentLoaded, or null",
  "confidence":         0.0,
  "wcag_reference":     "WCAG criterion or null",
  "rationale":          "why this fix over alternatives; why this technology",
  "side_effects":       ["potential unintended consequence, or empty list"]
}}
"""

RECOMMENDER_USER = """\
Issue cluster to fix:
  Cluster ID:        {cluster_id}
  Label:             {cluster_label}
  Dominant severity: {dominant_severity}
  Dominant category: {dominant_category}
  Affected elements: {affected_elements}
  Summary:           {representative_description}

Individual issues in this cluster:
{issues_detail}

Original HTML source:
{html_content}

UI context: {ui_context}

INSTRUCTIONS:
1. Find the affected elements in the HTML source above.
2. Copy their exact HTML into before_snippet.
3. Choose the right technology (HTML / CSS / JS) — not just the easiest.
4. If patch_type is js_snippet: wrap ALL code in DOMContentLoaded.
5. If patch_type is css_rule: populate css_snippet with complete rule(s).
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
  - One patch removes an element that another patch modifies
  - Their after_snippets produce contradictory HTML when both applied
  - Their css_snippets define contradictory rules for the same selector+property

Two patches do NOT conflict if:
  - They target the same element but modify DIFFERENT attributes
    (e.g. one adds aria-label, another adds tabindex — no conflict)
  - They target the same element with different patch_types that are compatible
    (e.g. html_attribute + css_rule on the same element)
  - One is a CSS patch and the other is an HTML patch on the same element
    (CSS and HTML changes are orthogonal)

Output ONLY a valid JSON array — no explanation, no markdown:

[
  {{
    "conflict_id":           "conflict_1",
    "patch_id_a":            "string",
    "patch_id_b":            "string",
    "target_element":        "CSS selector both patches modify in conflicting ways",
    "conflict_description":  "exactly which attribute or rule conflicts and how",
    "conflict_severity":     "low | medium | high"
  }}
]

Return [] if no genuine conflicts exist.
Conflict severity:
  high   — applying both breaks the UI or produces invalid HTML/CSS
  medium — applying both produces redundant or contradictory attributes/rules
  low    — technically compatible but redundant (same attribute set to same value)
"""

CONFLICT_DETECTION_USER = """\
Patch proposals to review:
{patches_json}

Identify only genuine conflicts per the rules above. Output ONLY the JSON array.
"""


# ---------------------------------------------------------------------------
# 3. Negotiation Argument Prompt
# ---------------------------------------------------------------------------

NEGOTIATION_ARGUMENT_SYSTEM = """\
You are Recommender Agent {agent_id}, arguing for your patch in a conflict resolution.

Be CONCISE — your argument must be under 150 words total.
Focus on: technical correctness, WCAG compliance, minimal side effects.
Acknowledge your patch's weaknesses honestly.

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

Make your argument in under 150 words. Output ONLY the JSON object.
"""


# ---------------------------------------------------------------------------
# 4. Mediator Resolution Prompt
# ---------------------------------------------------------------------------

MEDIATOR_SYSTEM = """\
You are an impartial senior engineer mediating a conflict between two patches.

Resolution options:
  "chose_a"    — Patch A is clearly better; use it unchanged
  "chose_b"    — Patch B is clearly better; use it unchanged
  "merged"     — Both have merit; combine into one superior patch
  "unresolved" — Cannot resolve without more context (last resort)

MERGED PATCH RULES — if resolution is "merged":
  1. Decide ONE patch_type for the merged result. Do not mix types.
  2. If both patches are HTML changes: merged_snippet is the combined after_snippet.
  3. If either patch is CSS: populate merged_css_snippet with combined CSS rules.
  4. If either patch is JS: populate merged_js_snippet with combined JS, both
     wrapped in a SINGLE DOMContentLoaded listener.
  5. The merged result must be valid and apply cleanly to the original HTML.

Output ONLY valid JSON — no explanation, no markdown:

{{
  "resolution":             "chose_a | chose_b | merged | unresolved",
  "winning_patch_id":       "patch_id or null if merged/unresolved",
  "merged_snippet":         "combined after_snippet if merged HTML change, else null",
  "merged_css_snippet":     "combined CSS rules if either patch is CSS, else null",
  "merged_js_snippet":      "single DOMContentLoaded block if either patch is JS, else null",
  "patch_type":             "the single patch_type for the merged result, or null",
  "resolution_rationale":   "2-3 sentences: why this resolution, what it preserves",
  "mediator_notes":         "any caveats for the development team"
}}
"""

MEDIATOR_USER = """\
Conflict:
{conflict_json}

Patch A:
{patch_a_json}

Patch A argument:
{argument_a}

Patch B:
{patch_b_json}

Patch B argument:
{argument_b}

Previous rounds (if any):
{previous_rounds}

Resolve this conflict. Output ONLY the JSON object.
"""