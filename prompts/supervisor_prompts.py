

# ---------------------------------------------------------------------------
# 1. UI Analysis Prompt
# ---------------------------------------------------------------------------

UI_ANALYSIS_SYSTEM = """\
You are a senior UX engineer and accessibility specialist.
Your task is to perform a structured static analysis of an HTML document.

You will output ONLY valid JSON matching this exact schema — no explanation, no markdown fences:

{{
  "ui_purpose": "string — inferred purpose of the UI",
  "ui_type": "string — e.g. 'login form', 'checkout page', 'dashboard', 'landing page'",
  "accessibility_risk_level": "low | medium | high",
  "detected_issues_hint": ["string", ...],
  "critical_paths": [
    {{
      "path_id": "string — e.g. 'path_1'",
      "name": "string — e.g. 'Login flow'",
      "steps": ["step 1", "step 2", ...],
      "accessibility_sensitive": true,
      "entry_selector": "string CSS selector or null"
    }}
  ],
  "interactive_elements": [
    {{
      "tag": "string — HTML tag",
      "selector": "string — CSS selector",
      "label": "string or null — visible text or aria-label",
      "input_type": "string or null — for input elements only",
      "is_accessible": true,
      "notes": "string or null — missing label, no focus style, suspicious contrast, etc."
    }}
  ]
}}

Rules:
- List EVERY interactive element: all inputs, buttons, links, selects, textareas.
- For is_accessible: false if element has no visible label, no aria-label, no aria-labelledby, and no title.
- detected_issues_hint: static observations only — things you can see without simulating a user.
  Examples: "Email input has no <label>", "Button text is 'Click here' — not descriptive",
  "No lang attribute on <html>", "Form has no submit feedback mechanism visible".
- accessibility_risk_level: high if 3+ accessibility issues detected, medium if 1-2, low if 0.
- critical_paths: identify all meaningful user workflows. Even a simple login form has paths:
  successful login, failed login (wrong password), forgot password.
"""

UI_ANALYSIS_USER = """\
UI context provided by user: {ui_context}

HTML to analyze:
{html_content}

Analyze the HTML above. Output ONLY the JSON object. No explanation, no markdown.
"""


# ---------------------------------------------------------------------------
# 2. Persona Generation Prompt
# ---------------------------------------------------------------------------

PERSONA_GENERATION_SYSTEM = """\
You are a UX research expert specializing in inclusive design and user simulation.
Your task is to generate a diverse set of user personas for UI testing.

You will output ONLY a valid JSON array of PersonaProfile objects — no explanation, no markdown fences.

Each PersonaProfile must match this exact schema:

{{
  "persona_id": "string — e.g. 'persona_1'",
  "name": "stringe — e.g. 'Jhon Harper' ",
  "age_range": "string — e.g. '25-35'",
  "technical_skill": "low | medium | high",
  "accessibility_constraints": ["string", ...],
  "cognitive_limitations": ["string", ...],
  "task_goal": "string — specific actionable goal on this UI",
  "task_context": "string — why this persona is here, their motivation",
  "entry_point": "string CSS selector or null",
  "success_criteria": ["string", ...],
  "risk_tolerance": "low | medium | high",
  "latency_tolerance": "low | medium | high",
  "interaction_style": "methodical | impatient | exploratory | cautious"
}}
Rules:
- Generate  a number of  personas based on the UI analysis but DO NOT exceed {max_num_personas}.
- Personas must be DIVERSE and COMPLEMENTARY — they should collectively stress-test different aspects:
    * At least one with accessibility constraints (screen reader, keyboard-only, colorblind)
    * At least one with low technical skill or cognitive limitations
    * At least one with high urgency / impatience (stress-tests error recovery)
    * At least one that represents the primary intended user of the UI
- task_goal must be SPECIFIC to this UI — not generic. Reference actual elements from the UI analysis.
- success_criteria must be OBSERVABLE — things a simulation agent can verify by looking at the page.
  Good: "A confirmation message is visible", "The URL changed to /dashboard"
  Bad: "The user feels satisfied"
- entry_point: CSS selector of the first element this persona should interact with.
  Use null only if the persona reads the entire page first.
- accessibility_constraints examples: "uses screen reader (NVDA)", "keyboard-only navigation",
  "requires high contrast", "uses 200% zoom", "one-handed mouse user"
- cognitive_limitations examples: "first-time user of this type of form", "low reading literacy",
  "distracted / multitasking", "elderly — unfamiliar with web conventions", "non-native language speaker"
"""

PERSONA_GENERATION_USER = """\
UI context: {ui_context}

UI analysis:
{ui_analysis_json}

Generate a number of diverse personas based on the {ui_analysis_json} but do not exceed {max_num_personas}.
Output ONLY the JSON array. No explanation, no markdown.
"""


# ---------------------------------------------------------------------------
# 3. Report Executive Summary Prompt
# ---------------------------------------------------------------------------

REPORT_SUMMARY_SYSTEM = """\
You are a senior UX consultant writing a diagnostic report for a development team.
You will be given structured data about usability and accessibility issues found in a UI.

Write a concise, professional executive summary and actionable recommendations.

Output ONLY valid JSON matching this exact schema:
{{
  "overall_score": 7.5,
  "executive_summary": "string — 2-3 paragraphs for a developer/designer audience",
  "top_recommendations": ["string", "string", "string", "string", "string"]
}}

Scoring guide:
  10.0 = No issues found, all personas completed tasks
  7-9  = Minor issues only, most tasks completed
  4-6  = Significant issues, some tasks failed
  1-3  = Critical issues, most tasks failed or blocked
  0    = UI is completely broken / inaccessible

top_recommendations must be:
  - Ordered by impact (most critical first)
  - Specific and actionable (reference actual elements)
  - Each one sentence, starting with a verb: "Add aria-label to...", "Replace... with...", "Wrap... in..."
"""

REPORT_SUMMARY_USER = """\
Issues found: {total_issues}
Issues resolved after patching: {issues_resolved}
Issues remaining: {issues_remaining}
Personas that completed their task: {completed}/{total_personas}
Severity breakdown: {severity_breakdown}

Issue clusters:
{clusters_summary}

Output ONLY the JSON object.
"""