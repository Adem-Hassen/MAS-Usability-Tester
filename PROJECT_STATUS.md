# MAS-Usability-Tester: Project Status & Root Cause Analysis 

## 1. Current Architecture
The system consists of three main pillars:
*   **Core MAS (Multi-Agent System):** A Python-based agentic evaluation engine driven by LangGraph. It features specific modules (Supervisor, Personas, Recommender, Conflict Resolver, and Patch Applicator) that load Playwright locally to evaluate UI files and propose structural patches.
*   **FastAPI Backend (`backend/`):** A RESTful and SSE API built with FastAPI that wraps the system. It handles uploaded HTML sessions via `session_store.py` and runs the evaluation in a background thread via `pipeline_runner.py`.
*   **Next.js Frontend (`frontend/`):** Provides a visual dashboard to review issues, see live agent actions (via Server-Sent Events), and download patched HTML files and PDF reports.

## 2. Recent Progress
We have made substantial functional upgrades to the Cognitive Agents:
*   **Anti-Hallucination Framework:** Enforced an "Evidence-First" reasoning protocol, integrated Trace-to-State heuristic grounding, and implemented post-mortem loop detection inside the Supervisor node.
*   **Recommender Agent Upgrade:** Expanded agent context to inject global CSS/Design tokens (`_extract_global_styles`), and enforced a "Bold Directive" to rewrite components architecturally rather than applying superficial `aria-label` patches.

## 3. Unresolved Bugs & Root Cause Analysis

**The Symptoms:** 
The WebApp returns identically repetitive results (same issues, same fake patches), regardless of the submitted UI. The outputted fixed HTML files apply zero real code changes, except adding a single standard HTML comment inside the `<head>` tag. However, the CLI environment functions normally.

**The Root Cause (Identified):**
The FastAPI application is silently degrading into a mocked **Simulation Mode**.

In `backend/pipeline_runner.py`, the import logic defines a `try...except ImportError:` block to wrap the core MAS engine (`from core.graph import run_evaluation`). 
If *any* module inside the underlying graph fails to import (due to environment variable pathing issues, or missing packages like `openai` which was recently highlighted), the WebApp catches the `ImportError`, swallows it without logging, and sets `MAS_AVAILABLE = False`.

When `MAS_AVAILABLE` is false, `_run_simulation()` assumes control. It:
1. Iterates through the files while pausing randomly (`time.sleep`).
2. Pulls randomly from a hardcoded list of `FAKE_ISSUES` (e.g., "Missing form label", "Insufficient color contrast").
3. Emits fake patches.
4. Performs a string replacement on `<head>` to `<head>\n<!-- Nexus Accessibility Fixes Applied -->` (which is why you only see one line added to the patched HTML).

The CLI (`main.py`) does not contain this silent fallback mechanism, which is why it runs the real LangGraph logic (or fails conspicuously if it cannot).

## 4. Next Steps & Proposed Fix
1.  **Remove the Silent Mock:** We need to update `backend/pipeline_runner.py` to stop silently swallowing the `ImportError`. If the import fails, it should log the `traceback` explicitly. We should either disable `MAS_AVAILABLE = False` for production, or strictly control when simulation mode is active (e.g. via an environment variable).
2.  **Fix Venv / Python Paths:** Ensure that the command running the WebApp (`uvicorn backend.main:app`) executes in the exact same virtual environment context as the CLI, and resolving any missing dependencies (like `openai`).
