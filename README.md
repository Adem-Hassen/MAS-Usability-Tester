#MAS Usability Tester

A full-stack web application that wraps the MAS-Usability-Tester pipeline behind
a FastAPI backend and Next.js frontend, providing real-time evaluation feedback,
issue detection, patch previews, and PDF report download.

---

## Architecture

```

MAS-Usability-Tester/
    ├── backend/
    │     ├── main.py            ← FastAPI app + all REST/SSE endpoints
    │     ├── session_store.py   ← In-memory session store with SSE pub/sub queues
    │     ├── pipeline_runner.py ← Bridges sessions to MAS pipeline (simulation fallback)
    │     └── requirements.txt
    └── frontend/
      ├── src/
    │     ├── app/
    │     │   ├── layout.tsx    ← Root layout
    │     │   ├── page.tsx      ← Main dashboard (upload + live view + results)
    │     │   └── globals.css   ← Design tokens + global styles
    │     ├── hooks/
    │     │   └── usePipeline.ts ← Central state machine + SSE consumer
    │     ├── lib/
    │     │   └── api.ts        ← Typed API client
    │     └── types/
    │       └── index.ts      ← Shared TypeScript types
        ├── next.config.js
        ├── tailwind.config.js
        └── package.json
    ├── agents/
    │   ├── persona/
    │   │   ├── agent_sandbox.py
    │   │   ├── persona_agent.py
    │   │   └── playwright_engine.py
    │   └── supervisor/
    │       └── supervisor_agent.py
    |       └── patch_applicator.py
    |       └── report_generator.py
    |       └── verficiation_loop.py
    │   └── recommender/
    │       └──recommender_agent.py
    |       └── conflict_resolver.py       
    ├── cofig/
    │   ├── logging_config.py
    │   ├── persona_templates.yaml
    │   └── settings.py
    ├── core/
    │   └── state.py
    │   └── graph.py
    ├── monitoring/
    │   └── logger.py
    ├── prompts/
    │   ├── persona_prompts.py
    │   ├── recommender_prompts.py
    │   └── supervisor_prompts.py
    ├── schemas/
    │   ├── issue_schema.py
    │   ├── patch_schema.py
    │   ├── persona_schema.py
    │   └── report_schema.py
    ├── tools/
    │   └── analysis/
    │       └── cluster_engine.py
    |   └── rate_limiter.py
    ├── .env
    ├── .gitignore
    ├── main.py
    └── requirements.txt
```

### Data flow

```
User uploads HTML files
        │
        ▼
POST /api/sessions          → session created, files saved to disk
POST /api/sessions/{id}/run → pipeline triggered in background thread
GET  /api/sessions/{id}/stream → SSE: progress / step / issue / patch / done events
GET  /api/sessions/{id}/results → final JSON results
GET  /api/sessions/{id}/files/{name} → download fixed HTML
GET  /api/sessions/{id}/report.pdf   → download PDF report
```

### SSE event types

| kind       | key fields                                        |
|------------|---------------------------------------------------|
| `progress` | `value` (0–100), `label`                          |
| `step`     | `step`, `status`, `page`, `page_num`, `label`     |
| `log`      | `level`, `message`                                |
| `issue`    | `issue_id`, `title`, `severity`, `category`, `description`, `page` |
| `patch`    | `patch_id`, `target`, `description`, `patch_type`, `page` |
| `done`     | `pages_done`, `has_pdf`                           |
| `error`    | `message`, `trace`                                |

---

## Quick Start

### 1. Backend

```bash

# Create virtual env (recommended)
python -m venv venv
# Linux/MacOS:source venv/bin/activate          # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run
uvicorn backend.main:app --reload
# → API available at http://localhost:8000
# → Swagger docs at http://localhost:8000/api/docs
```

The backend auto-detects whether the MAS pipeline is installed.
If not, it runs a **simulation mode** that produces realistic fake events
and writes placeholder fixed HTML — useful for frontend development.



### 2. Frontend

```bash
cd frontend

npm install
npm run dev
# → UI available at http://localhost:3000
```

The Next.js config proxies all `/api/*` requests to `http://localhost:8000`.

---

## API Reference

### `POST /api/sessions`
Upload files and create a session.

**Request:** `multipart/form-data` with field `files[]` (1–5 `.html` files, max 5 MB each)

**Response:**
```json
{ "session_id": "abc123", "files": ["login.html"], "created_at": "…" }
```

---

### `POST /api/sessions/{id}/run`
Trigger pipeline evaluation.

**Response:** `202 Accepted` → `{ "session_id": "…", "status": "running" }`

---

### `GET /api/sessions/{id}/stream`
Server-Sent Events stream. Connect with `EventSource`. Each event is JSON.

---

### `GET /api/sessions/{id}/status`
Quick status poll (no SSE needed).

```json
{
  "status": "running",
  "progress": 45,
  "pages_total": 3,
  "pages_done": 1,
  "started_at": "…",
  "finished_at": null
}
```

---

### `GET /api/sessions/{id}/results`
Full results JSON (only available when `status == "done"`).

---

### `GET /api/sessions/{id}/files/{filename}`
Download a fixed HTML file (e.g. `login_fixed.html`).

---

### `GET /api/sessions/{id}/report.pdf`
Download the PDF report.

---



