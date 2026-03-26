# tools/rate_limiter.py
"""
Parallel-safe Groq rate limiter.

Architecture: Semaphore + Shared Backoff Event
-----------------------------------------------

                    ┌─────────────────────────────────┐
  Persona thread 1  │                                 │
  Persona thread 2  │  groq_chat_completion()         │
  Persona thread 3  │                                 │
  Recommender thr 1 │   1. Wait on shared backoff     │
  Recommender thr 2 │      event (pauses ALL callers  │
        ...         │      when a 429 is in flight)   │
                    │                                 │
                    │   2. Acquire per-key semaphore  │
                    │      (limits concurrent calls)  │
                    │                                 │
                    │   3. Make LLM call              │
                    │                                 │
                    │   4a. Success  → release sem    │
                    │                                 │
                    │   4b. 429      → set backoff    │
                    │                   event         │
                    │                → sleep Retry-   │
                    │                   After + jitter│
                    │                → clear event    │
                    │                → retry          │
                    └─────────────────────────────────┘

Key properties
--------------
  - True parallelism is preserved — no sequential forcing.
  - The semaphore sets a ceiling on concurrent in-flight requests
    per API key, keeping burst rate below Groq's 30 RPM limit.
  - When one caller hits 429, the shared backoff Event is set,
    causing ALL other callers to pause at step 1 instead of
    pile-driving Groq with retries (thundering-herd prevention).
  - Once the backoff period ends, all paused callers resume
    simultaneously and re-enter the semaphore queue — natural
    spreading because they contend for semaphore slots.
  - Jitter on every sleep prevents synchronized retry bursts.
  - The sliding-window token tracker ensures TPM is also respected.

Configuration (via settings / .env)
-------------------------------------
  LLM_MAX_CONCURRENT_CALLS      int   default 5
      Max simultaneous in-flight calls per API key.
      Groq 30 RPM ≈ 0.5 req/s.  5 concurrent calls with ~10s avg
      latency = 0.5 req/s steady state — exactly at the limit.
      Lower this if you still hit 429s.

  LLM_INTER_REQUEST_DELAY_SECONDS  float  default 0.0
      Optional fixed delay injected AFTER acquiring the semaphore,
      before making the call.  Adds breathing room beyond concurrency
      control.  Set > 0 if TPM limits are the bottleneck.

  LLM_MAX_RETRIES                 int   default 5
  LLM_RETRY_DELAY_SECONDS         float default 5.0
      Base for exponential backoff when Retry-After is missing.
"""

from __future__ import annotations

import random
import threading
import time
from collections import deque
from typing import Optional

from openai import OpenAI, RateLimitError, APIStatusError
from monitoring.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Groq base URL
# ---------------------------------------------------------------------------
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


def _base_url_for(model: str) -> Optional[str]:
    """Route model to correct endpoint."""
    if model.startswith(("gpt-", "o1-", "o3-", "o4-","o3", "o4")):
        return None                            # OpenAI default
    if "/" in model:
        return "https://openrouter.ai/api/v1"  # OpenRouter
    return GROQ_BASE_URL                       # Groq


# ---------------------------------------------------------------------------
# Per-key shared state
# ---------------------------------------------------------------------------

class _KeyState:
    """
    All concurrency-control objects for one API key.
    Created once per key and cached in _KEY_STATES.
    """

    def __init__(self, max_concurrent: int, tpm_limit: int):
        # Semaphore: limits how many threads can be inside _make_call() at once
        self.semaphore = threading.Semaphore(max_concurrent)

        # Backoff event: SET means "Groq returned 429, everyone pause"
        #                CLEAR means "normal operation, proceed"
        # We use it inverted: threads wait until the event is CLEAR.
        self._backoff_event = threading.Event()
        self._backoff_event.set()   # set = "clear to proceed"
        self._backoff_lock = threading.Lock()

        # Sliding-window TPM tracker
        self._tpm_limit    = tpm_limit
        self._token_window: deque = deque()   # deque of (timestamp, tokens)
        self._tpm_lock     = threading.Lock()

    # ── Backoff control ───────────────────────────────────────────────────

    def wait_for_backoff_clear(self) -> None:
        """Block until no 429 backoff is in progress."""
        self._backoff_event.wait()

    def enter_backoff(self, duration: float) -> None:
        """
        Called by the thread that received 429.
        Clears the event (pausing all waiters), sleeps, then sets it again.
        Other threads that call wait_for_backoff_clear() will block until
        this completes.
        """
        with self._backoff_lock:
            if self._backoff_event.is_set():
                # Only one thread should drive the backoff
                self._backoff_event.clear()
                logger.info("rate_limiter.backoff_start",
                            duration=round(duration, 1))
                time.sleep(duration)
                self._backoff_event.set()
                logger.info("rate_limiter.backoff_end")

    # ── TPM tracking ──────────────────────────────────────────────────────

    def wait_for_tpm_budget(self, estimated_tokens: int) -> None:
        """
        Block until the sliding 60-second window has room for
        estimated_tokens more tokens.  If the window is full, sleep
        until the oldest entry expires.

        Thread-safety note
        ------------------
        All reads AND the final append happen inside _tpm_lock.
        sleep_for is computed inside the lock then used outside it —
        safe because it is a local variable.
        The deque emptiness check before reading [0] prevents the
        IndexError that occurs when a concurrent thread evicts the
        last entry while we are inside the lock.
        """
        if self._tpm_limit <= 0:
            return

        while True:
            sleep_for = 0.0
            now = time.monotonic()

            with self._tpm_lock:
                # Evict entries older than 60 s
                while self._token_window and now - self._token_window[0][0] >= 60:
                    self._token_window.popleft()

                used = sum(t for _, t in self._token_window)

                if used + estimated_tokens <= self._tpm_limit:
                    # Budget available — reserve it and return immediately
                    self._token_window.append((now, estimated_tokens))
                    return

                # Window is full — compute sleep duration inside the lock
                # Guard: deque may be empty if all entries just expired above
                if self._token_window:
                    oldest_ts = self._token_window[0][0]
                    sleep_for = max(0.1, 60.0 - (now - oldest_ts) + random.uniform(0, 0.5))
                else:
                    # All entries expired during eviction — loop back immediately
                    sleep_for = 0.0

            if sleep_for > 0:
                logger.debug("rate_limiter.tpm_wait", sleep_s=round(sleep_for, 2))
                time.sleep(sleep_for)
            # else: loop back without sleeping — will find budget on next iteration


# Global registry of per-key state objects
_KEY_STATES: dict[str, _KeyState] = {}
_REGISTRY_LOCK = threading.Lock()


def _get_key_state(api_key: str, max_concurrent: int, tpm_limit: int) -> _KeyState:
    with _REGISTRY_LOCK:
        if api_key not in _KEY_STATES:
            _KEY_STATES[api_key] = _KeyState(max_concurrent, tpm_limit)
        return _KEY_STATES[api_key]


# ---------------------------------------------------------------------------
# Settings helper (lazy import to avoid circular deps)
# ---------------------------------------------------------------------------

def _settings():
    from config.settings import settings
    return settings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def groq_chat_completion(
    api_key:          str,
    model:            str,
    messages:         list[dict],
    temperature:      float,
    max_tokens:       int,
    task:             str,
    inter_call_delay: float = 0.0,
) -> tuple[str, Optional[str]]:
    """
    Thread-safe, parallel-safe LLM call with Groq rate-limit handling.

    Designed to be called from many threads simultaneously — the internal
    semaphore and backoff event coordinate them safely without forcing
    sequential execution at the application level.

    Args:
        api_key          : Groq API key (used to scope semaphore + backoff)
        model            : Groq model name
        messages         : OpenAI-format message list
        temperature      : sampling temperature
        max_tokens       : max output tokens
        task             : short label for logging (e.g. "persona_decision")
        inter_call_delay : optional extra delay after acquiring semaphore
                           (use when TPM is the bottleneck, not RPM)

    Returns:
        (raw_json_string, error_message)
        error_message is None on success.
    """
    s           = _settings()
    max_concurrent = getattr(s, "llm_max_concurrent_calls",       5)
    tpm_limit      = getattr(s, "llm_tpm_limit",                  6000)
    max_retries    = getattr(s, "llm_max_retries",                 5)
    base_delay     = getattr(s, "llm_retry_delay_seconds",         5.0)
    fixed_delay    = inter_call_delay or getattr(s, "llm_inter_request_delay_seconds", 0.0)

    key_state = _get_key_state(api_key, max_concurrent, tpm_limit)
    base_url  = _base_url_for(model)
    client    = OpenAI(api_key=api_key, base_url=base_url)

    # Estimate tokens conservatively: ~4 chars/token for English text
    estimated_tokens = sum(len(m.get("content", "")) // 4 for m in messages) + max_tokens

    for attempt in range(1, max_retries + 1):

        # ── Step 1: Wait for any active 429 backoff to clear ─────────────
        key_state.wait_for_backoff_clear()

        # ── Step 2: Wait for TPM budget ───────────────────────────────────
        key_state.wait_for_tpm_budget(estimated_tokens)

        # ── Step 3: Acquire concurrency slot ─────────────────────────────
        key_state.semaphore.acquire()

        try:
            # Optional fixed delay inside the semaphore
            if fixed_delay > 0:
                time.sleep(fixed_delay + random.uniform(0, 0.1))

            logger.debug(f"llm.{task}.attempt",
                         model=model, attempt=attempt)

            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )

            # Guard against empty choices (Groq returns choices=[] on
            # context-length exceeded or soft content refusals)
            if not response.choices:
                finish = getattr(response, "finish_reason", "unknown")
                logger.warning(f"llm.{task}.empty_choices",
                               finish_reason=finish, attempt=attempt)
                if attempt < max_retries:
                    time.sleep(base_delay)
                    continue
                return "", f"Empty choices in response ({task}) — possible context limit"

            raw = response.choices[0].message.content or ""
            raw = raw.strip()
            if raw.startswith("```"):
                lines = raw.splitlines()
                raw   = "\n".join(
                    l for l in lines if not l.strip().startswith("```")
                ).strip()

            logger.debug(f"llm.{task}.ok", chars=len(raw))
            return raw, None

        except RateLimitError as e:
            retry_after = _parse_retry_after(e)
            jitter      = random.uniform(1.0, 3.0)
            backoff     = (retry_after + jitter) if retry_after else min(
                base_delay * (2 ** (attempt - 1)) + jitter, 60.0
            )
            logger.warning(f"llm.{task}.rate_limit",
                           attempt=attempt,
                           retry_after=retry_after,
                           backoff=round(backoff, 1))

            if attempt < max_retries:
                # Drive the shared backoff — all other threads will pause
                key_state.enter_backoff(backoff)
            else:
                return "", f"Rate limit — {max_retries} retries exhausted ({task})"

        except APIStatusError as e:
            if e.status_code == 503:
                sleep_s = min(base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1), 60.0)
                logger.warning(f"llm.{task}.overload",
                               attempt=attempt, sleep_s=round(sleep_s, 1))
                if attempt < max_retries:
                    time.sleep(sleep_s)
                    continue
            return "", f"API {e.status_code} ({task}): {e.message}"

        except Exception as e:
            sleep_s = min(base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5), 60.0)
            logger.warning(f"llm.{task}.error",
                           attempt=attempt, error=str(e), sleep_s=round(sleep_s, 1))
            if attempt < max_retries:
                time.sleep(sleep_s)
            else:
                return "", f"Failed after {max_retries} retries ({task}): {e}"

        finally:
            # Always release the semaphore slot, even on exception
            key_state.semaphore.release()

    return "", f"All {max_retries} retries exhausted ({task})"


# ---------------------------------------------------------------------------
# Retry-After header parser
# ---------------------------------------------------------------------------

def _parse_retry_after(exc: RateLimitError) -> Optional[float]:
    """
    Extract Retry-After seconds from a Groq RateLimitError.
    Groq always includes this — either in response headers or the message body.
    """
    try:
        headers = getattr(getattr(exc, "response", None), "headers", {}) or {}
        val = headers.get("retry-after") or headers.get("Retry-After")
        if val:
            return float(val)
        import re
        m = re.search(r"(?:retry.?after|please wait)\s+(\d+\.?\d*)\s*s",
                      str(exc), re.IGNORECASE)
        if m:
            return float(m.group(1))
    except Exception:
        pass
    return None