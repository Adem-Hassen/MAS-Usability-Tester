from __future__ import annotations

import asyncio
import random
import threading
import time
from typing import Optional, Tuple, List, Dict

from openai import AsyncOpenAI, RateLimitError, APIStatusError

from config.settings import settings
from monitoring.logger import get_logger
from tools.rate_limiter import _base_url_for, _parse_retry_after

logger = get_logger(__name__)


class ProviderKey:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.backoff_until = 0.0


class PersonaAsyncRequestPool:
    """
    Shared async request pool exclusively for the Persona agent swarm.
    Manages multiple API keys, respects rate limits, and uses asyncio
    to handle hundreds of concurrent LLM requests.
    """
    def __init__(self, keys: List[str], max_concurrent_per_key: int = 5):
        valid_keys = [k.strip() for k in keys if k.strip()]
        if not valid_keys:
            valid_keys = [settings.persona_api_key.strip()]
        
        self.keys = [ProviderKey(k) for k in valid_keys]
        self.max_concurrent_per_key = max_concurrent_per_key
        
        # Limit total in-flight requests across all keys
        self.semaphore = asyncio.Semaphore(len(self.keys) * max_concurrent_per_key)
        
        self.clients = {k.api_key: AsyncOpenAI(api_key=k.api_key) for k in self.keys}
        
        # Dedicated event loop for async LLM requests
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def stop(self):
        """Cleanly shut down the background event loop."""
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join()

    def chat_completion_sync(
        self,
        model: str,
        messages: List[Dict],
        temperature: float,
        max_tokens: int,
        task: str,
    ) -> Tuple[str, Optional[str]]:
        """Synchronous wrapper for the async pool, to be called from persona threads."""
        future = asyncio.run_coroutine_threadsafe(
            self.chat_completion_async(model, messages, temperature, max_tokens, task),
            self.loop
        )
        return future.result()

    async def chat_completion_async(
        self,
        model: str,
        messages: List[Dict],
        temperature: float,
        max_tokens: int,
        task: str,
    ) -> Tuple[str, Optional[str]]:
        max_retries = getattr(settings, "llm_max_retries", 5)
        base_delay = getattr(settings, "llm_retry_delay_seconds", 5.0)
        current_model = model
        fallback_model = "llama-3.1-8b-instant"

        for attempt in range(1, max_retries + 1):
            if attempt >= max_retries - 1 and "70b" in current_model.lower():
                logger.info("persona.pool.fallback_model", original=current_model, fallback=fallback_model)
                current_model = fallback_model

            now = time.monotonic()
            available_keys = [k for k in self.keys if k.backoff_until <= now]
            
            if available_keys:
                key_obj = random.choice(available_keys)
            else:
                key_obj = min(self.keys, key=lambda k: k.backoff_until)
                wait_time = key_obj.backoff_until - now
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
            
            client = self.clients[key_obj.api_key]
            # Override base URL per model (for Moonshot/OpenRouter support)
            client.base_url = _base_url_for(current_model) or client.base_url

            async with self.semaphore:
                try:
                    logger.debug(f"llm.{task}.attempt", model=current_model, attempt=attempt)
                    response = await client.chat.completions.create(
                        model=current_model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        response_format={"type": "json_object"},
                    )

                    if not response.choices:
                        finish = getattr(response, "finish_reason", "unknown")
                        logger.warning(f"llm.{task}.empty_choices", finish_reason=finish, attempt=attempt)
                        if attempt < max_retries:
                            await asyncio.sleep(base_delay)
                            continue
                        return "", f"Empty choices in response ({task})"

                    raw = response.choices[0].message.content or ""
                    raw = raw.strip()
                    if raw.startswith("```"):
                        lines = raw.splitlines()
                        raw = "\n".join(l for l in lines if not l.strip().startswith("```")).strip()

                    return raw, None

                except RateLimitError as e:
                    retry_after = _parse_retry_after(e)
                    
                    if retry_after and retry_after > 60.0 and "70b" in current_model.lower() and attempt < max_retries:
                        logger.warning("persona.pool.hard_limit", retry_after=retry_after, model=current_model)
                        current_model = fallback_model
                        await asyncio.sleep(random.uniform(1.0, 3.0))
                        continue

                    jitter = random.uniform(1.0, 3.0)
                    backoff = (retry_after + jitter) if retry_after else min(base_delay * (2 ** (attempt - 1)) + jitter, 60.0)
                    logger.warning(f"llm.{task}.rate_limit", attempt=attempt, retry_after=retry_after, backoff=round(backoff, 1))

                    if attempt < max_retries:
                        key_obj.backoff_until = time.monotonic() + backoff
                        await asyncio.sleep(backoff)
                    else:
                        return "", f"Rate limit — {max_retries} retries exhausted ({task})"

                except APIStatusError as e:
                    if e.status_code == 503:
                        sleep_s = min(base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1), 60.0)
                        if attempt < max_retries:
                            await asyncio.sleep(sleep_s)
                            continue
                    return "", f"API {e.status_code} ({task}): {e.message}"
                except Exception as e:
                    sleep_s = min(base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5), 60.0)
                    if attempt < max_retries:
                        await asyncio.sleep(sleep_s)
                    else:
                        return "", f"Failed after {max_retries} retries ({task}): {e}"

        return "", f"All {max_retries} retries exhausted ({task})"
