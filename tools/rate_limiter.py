# tools/rate_limiter.py
"""
Provider-agnostic LLM rate limiter with resilient retry logic.

Architecture: Per-key Semaphore + Per-thread Retry
--------------------------------------------------

                    ┌─────────────────────────────────┐
  Persona thread 1  │                                 │
  Persona thread 2  │  chat_completion()              │
  Persona thread 3  │                                 │
  Recommender thr 1 │   1. Acquire per-key semaphore  │
  Recommender thr 2 │      (limits concurrent calls)  │
        ...         │                                 │
                     │   2. Make LLM call              │
                     │                                 │
                     │   3a. Success  → release sem    │
                     │                                 │
                     │   3b. Error    → release sem    │
                     │                → backoff sleep  │
                     │                → retry (goto 1) │
                     └─────────────────────────────────┘

Key properties
--------------
  - Per-key semaphore limits concurrent in-flight requests per API key.
  - Each thread retries independently with exponential backoff + jitter.
  - No global pauses — one thread's rate limit does not block others.
  - TPM tracker is optional (disabled when LLM_TPM_LIMIT=0).
  - response_format is sent only for providers that support it.

Configuration (via settings / .env)
-------------------------------------
  LLM_MAX_CONCURRENT_CALLS      int   default 5
      Max simultaneous in-flight calls per API key.

  LLM_TPM_LIMIT                 int   default 0
      Tokens-per-minute sliding-window limit. 0 = disabled.
      Enable only if your provider enforces TPM limits.

  LLM_MAX_RETRIES               int   default 5
  LLM_RETRY_DELAY_SECONDS       float default 5.0
      Base for exponential backoff when Retry-After is missing.

  LLM_INTER_REQUEST_DELAY_SECONDS  float  default 0.0
      Optional fixed delay injected AFTER acquiring the semaphore,
      before making the call.
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
# Provider base URLs
# ---------------------------------------------------------------------------
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
MOONSHOT_BASE_URL = "https://api.moonshot.ai/v1"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
QWEN_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"


def _base_url_for(model: str) -> Optional[str]:
    """Route model name to the correct API base URL.

    Routing table (checked in order):
      OpenAI native   gpt-* | o1-* | o3-* | o4-*  → None (OpenAI SDK default)
      Qwen            qwen* | qwq*                 → Qwen MaaS
      Moonshot / Kimi kimi-*                        → api.moonshot.ai/v1
      DeepSeek        deepseek-*                    → DeepSeek
      OpenRouter      any model containing "/"      → openrouter.ai/api/v1
      Default         everything else               → Groq
    """
    if model.startswith(("gpt-", "o1-", "o3-", "o4-")):
        return None        # OpenAI — use SDK default base URL

    if model.startswith(("qwen", "qwq")):
        return QWEN_BASE_URL

    if model.startswith("kimi-") or model == "moonshot":
        return MOONSHOT_BASE_URL

    if model.startswith("deepseek-"):
        return DEEPSEEK_BASE_URL

    if "/" in model:
        return "https://openrouter.ai/api/v1"

    return GROQ_BASE_URL


def _supports_json_mode(base_url: Optional[str] = None, model: str = "") -> bool:
    """
    Return True if the provider supports response_format={"type": "json_object"}.

    Detection order:
      1. Model name prefix (most reliable — covers custom URLs)
      2. Base URL fallback (legacy)

    Known unsupported / flaky:
      - Qwen / QwQ (Alibaba) → 500 error
      - DeepSeek → may error
      - Moonshot / Kimi → returns empty content with json_object
    """
    if model:
        if model.startswith(("qwen", "qwq")):
            return False
        # Kimi and DeepSeek now support JSON mode via OpenAI-compatible endpoints
        if model.startswith("deepseek-"):
            return True
        if model.startswith("kimi") or model == "moonshot":
            return True
        if model.startswith(("gpt-", "o1-", "o3-", "o4-")):
            return True
    if base_url is None:
        return True
    if QWEN_BASE_URL in (base_url or ""):
        return False
    # Standard OpenAI-compatible JSON mode detection
    return True    


def _normalize_provider_params(model: str, temperature: float, max_tokens: int) -> tuple[float, int]:
    """
    Normalize LLM parameters for provider-specific quirks.

    Known constraints:
      - Moonshot / Kimi: temperature MUST be exactly 1.0
      - DeepSeek: temperature range 0-2, no special constraints
    """
    original_temp = temperature
    if model.startswith("kimi") or model == "moonshot":
        temperature = 1.0
        if original_temp != 1.0:
            logger.info("rate_limiter.kimi_temp_adjusted",
                        original=original_temp, normalized=1.0, model=model)


    # Clamp to safe ranges
    temperature = max(0.0, min(2.0, temperature))
    max_tokens = max(1, min(8192, max_tokens))

    return temperature, max_tokens


# ---------------------------------------------------------------------------
# Per-key shared state
# ---------------------------------------------------------------------------

class _KeyState:
    """
    Concurrency-control objects for one API key.
    Created once per key and cached in _KEY_STATES.
    """

    def __init__(self, max_concurrent: int, tpm_limit: int):
        # Semaphore: limits how many threads can be inside the call at once
        self.semaphore = threading.Semaphore(max_concurrent)

        # Sliding-window TPM tracker (optional — disabled when tpm_limit <= 0)
        self._tpm_limit = tpm_limit
        self._token_window: deque = deque()   # deque of (timestamp, tokens)
        self._tpm_lock = threading.Lock()

    # ── TPM tracking ──────────────────────────────────────────────────────

    def wait_for_tpm_budget(self, estimated_tokens: int) -> None:
        """
        Block until the sliding 60-second window has room for
        estimated_tokens more tokens.  If the window is full, sleep
        until the oldest entry expires.

        Disabled when tpm_limit <= 0.
        """
        if self._tpm_limit <= 0:
            return

        # Safety guard: if a single request is larger than the entire TPM limit,
        # we must not loop forever. Cap it to the limit.
        if estimated_tokens >= self._tpm_limit:
            logger.warning("rate_limiter.tpm_cap_triggered",
                           requested=estimated_tokens, limit=self._tpm_limit)
            estimated_tokens = self._tpm_limit - 1

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
                if self._token_window:
                    oldest_ts = self._token_window[0][0]
                    sleep_for = max(0.5, 60.0 - (now - oldest_ts) + random.uniform(0.1, 0.5))
                else:
                    sleep_for = 0.0

            if sleep_for > 0:
                logger.debug("rate_limiter.tpm_wait", sleep_s=round(sleep_for, 2))
                time.sleep(sleep_for)


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

def chat_completion(
    api_key:          str,
    model:            str,
    messages:         list[dict],
    temperature:      float,
    max_completion_tokens:       int,
    task:             str,
    inter_call_delay: float = 0.0,
) -> tuple[str, Optional[str]]:
    """
    Thread-safe, parallel-safe LLM call with resilient retry logic.

    Works with any OpenAI-compatible provider (Groq, Moonshot, DeepSeek,
    Qwen, OpenRouter, OpenAI, etc.).

    Args:
        api_key          : API key (used to scope semaphore)
        model            : Model name
        messages         : OpenAI-format message list
        temperature      : sampling temperature
        max_completion_tokens : max output tokens
        task             : short label for logging (e.g. "persona_decision")
        inter_call_delay : optional extra delay after acquiring semaphore

    Returns:
        (raw_json_string, error_message)
        error_message is None on success.
    """
    s = _settings()
    max_concurrent = getattr(s, "llm_max_concurrent_calls", 5)
    tpm_limit      = getattr(s, "llm_tpm_limit", 0)
    max_retries    = getattr(s, "llm_max_retries", 5)
    base_delay     = getattr(s, "llm_retry_delay_seconds", 5.0)
    fixed_delay    = inter_call_delay or getattr(s, "llm_inter_request_delay_seconds", 0.0)

    keys = [k.strip() for k in api_key.split(",") if k.strip()]
    if not keys:
        return "", "No valid API keys provided."

    # Estimate tokens conservatively: ~4 chars/token for English text
    estimated_tokens = sum(len(m.get("content", "")) // 4 for m in messages) + max_completion_tokens

    current_model = model

    for attempt in range(1, max_retries + 1):
        active_key = keys[(attempt - 1) % len(keys)]
        key_state = _get_key_state(active_key, max_concurrent, tpm_limit)
        base_url = _base_url_for(current_model)
        client = OpenAI(api_key=active_key, base_url=base_url)
        use_json_mode = _supports_json_mode(base_url=base_url, model=current_model)

        # Normalize provider-specific parameters
        use_temp, use_max_tokens = _normalize_provider_params(current_model, temperature, max_completion_tokens)

        # ── Step 1: Wait for TPM budget (optional) ────────────────────────
        key_state.wait_for_tpm_budget(estimated_tokens)

        # ── Step 2: Acquire concurrency slot ─────────────────────────────
        key_state.semaphore.acquire()

        try:
            # Optional fixed delay inside the semaphore
            if fixed_delay > 0:
                time.sleep(fixed_delay + random.uniform(0, 0.1))

            prompt_chars = sum(len(m.get("content", "")) for m in messages)
            logger.debug(f"llm.{task}.attempt",
                         model=current_model, key_idx=(attempt - 1) % len(keys), attempt=attempt,
                         json_mode=use_json_mode, temperature=use_temp, max_completion_tokens=use_max_tokens,
                         prompt_chars=prompt_chars, estimated_tokens=estimated_tokens)

            call_kwargs = dict(
                model=current_model,
                messages=messages,
                temperature=use_temp,
                max_completion_tokens=use_max_tokens,
            )
            if use_json_mode:
                call_kwargs["response_format"] = {"type": "json_object"}

            response = client.chat.completions.create(**call_kwargs)

            # Guard against empty choices
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

            if not raw:
                finish = getattr(response.choices[0], "finish_reason", "unknown")
                refusal = getattr(response.choices[0].message, "refusal", None)
                logger.warning(f"llm.{task}.empty_content",
                               model=current_model, finish_reason=finish,
                               refusal=refusal, attempt=attempt,
                               prompt_chars=prompt_chars, max_tokens=use_max_tokens)

                if finish == "length":
                    # Prompt may be too large for the output budget.
                    # On first attempt, try with doubled max_tokens (up to 4096).
                    if attempt == 1 and use_max_tokens < 4096:
                        new_max = min(4096, use_max_tokens * 2)
                        logger.info("llm.{task}.length_retry_doubling",
                                    old_max=use_max_tokens, new_max=new_max,
                                    prompt_chars=prompt_chars)
                        max_tokens = new_max  # carry forward to next loop iteration
                        time.sleep(0.5)
                        continue
                    return "", f"Empty content from LLM ({task}) — finish_reason=length (prompt too long or max_tokens too small)"

                if attempt < max_retries:
                    time.sleep(base_delay)
                    continue
                return "", f"Empty content from LLM ({task}) — finish_reason={finish}"

            if raw.startswith("```"):
                lines = raw.splitlines()
                raw = "\n".join(
                    l for l in lines if not l.strip().startswith("```")
                ).strip()

            logger.debug(f"llm.{task}.ok", chars=len(raw))
            return raw, None

        except RateLimitError as e:
            retry_after = _parse_retry_after(e)

            jitter = random.uniform(1.0, 3.0)
            backoff = (retry_after + jitter) if retry_after else min(
                base_delay * (2 ** (attempt - 1)) + jitter, 60.0
            )
            logger.warning(f"llm.{task}.rate_limit",
                           attempt=attempt,
                           retry_after=retry_after,
                           backoff=round(backoff, 1))

            if attempt < max_retries:
                time.sleep(backoff)
            else:
                return "", f"Rate limit — {max_retries} retries exhausted ({task})"

        except APIStatusError as e:
            if e.status_code == 500 and use_json_mode and attempt < max_retries:
                # Some providers return 500 when response_format is not supported.
                # Retry once without it.
                logger.warning(f"llm.{task}.provider_500_json_mode",
                               attempt=attempt,
                               message=f"{e.message[:120]}..." if len(e.message) > 120 else e.message)
                use_json_mode = False
                time.sleep(random.uniform(0.5, 1.5))
                continue
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


# Backward-compatible alias — all existing imports still work
groq_chat_completion = chat_completion


# ---------------------------------------------------------------------------
# Retry-After header parser
# ---------------------------------------------------------------------------

def _parse_retry_after(exc: RateLimitError) -> Optional[float]:
    """
    Extract Retry-After seconds from a RateLimitError.
    Checks response headers first, then falls back to message body regex.
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
