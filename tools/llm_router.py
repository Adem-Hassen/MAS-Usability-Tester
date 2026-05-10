
from __future__ import annotations

import asyncio
import functools
import random
from typing import Optional, List, Dict

from config.settings import settings
from monitoring.logger import get_logger
from tools.rate_limiter import chat_completion

logger = get_logger(__name__)


class LLMRouter:
    """
    Thread-safe / async-safe LLM router.

    Args:
        api_key:          Comma-separated API keys (rotated per retry)
        model:            Primary model name
        temperature:      Sampling temperature
        max_tokens:       Max output tokens
        role:             Label for logging (e.g. "persona", "recommender")
        max_concurrent:   Global asyncio semaphore cap for achat_completion
        fallback_model:   Model to switch to on hard rate limits
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        temperature: float = 0.7,
        max_completion_tokens: int = 4096,
        role: str = "agent",
        max_concurrent: int = 5,
        fallback_model: str = "llama-3.1-8b-instant",
    ):
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_completion_tokens = max_completion_tokens
        self.role = role
        self.fallback_model = fallback_model

        # Async concurrency guard — shared across all async callers using this router
        self._sem = asyncio.Semaphore(max_concurrent)

    # ------------------------------------------------------------------
    # Sync API
    # ------------------------------------------------------------------

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        task: str,
        temperature: Optional[float] = None,
        max_completion_tokens: Optional[int] = None,
        model: Optional[str] = None,
    ) -> tuple[str, Optional[str]]:
        """
        Synchronous LLM call.
        Delegates directly to chat_completion so all existing
        rate-limit logic (semaphore, TPM tracker, backoff event) is reused.
        """
        use_model = model or self.model
        use_temp = temperature if temperature is not None else self.temperature
        use_max_tokens = max_completion_tokens if max_completion_tokens is not None else self.max_completion_tokens

        logger.debug(f"router.{self.role}.sync_request",
                     task=task, model=use_model)

        return chat_completion(
            api_key=self.api_key,
            model=use_model,
            messages=messages,
            temperature=use_temp,
            max_completion_tokens=use_max_tokens,
            task=f"{self.role}.{task}",
        )

    # ------------------------------------------------------------------
    # Async API
    # ------------------------------------------------------------------

    async def achat_completion(
        self,
        messages: List[Dict[str, str]],
        task: str,
        temperature: Optional[float] = None,
        max_completion_tokens: Optional[int] = None,
        model: Optional[str] = None,
    ) -> tuple[str, Optional[str]]:
        """
        Asynchronous LLM call with global concurrency cap.

        Runs the underlying sync chat_completion() in a thread-pool
        so that the existing rate_limiter Semaphore + TPM tracker still
        coordinate correctly across both sync and async callers.
        """
        use_model = model or self.model
        use_temp = temperature if temperature is not None else self.temperature
        use_max_tokens = max_completion_tokens if max_completion_tokens is not None else self.max_completion_tokens

        async with self._sem:
            loop = asyncio.get_running_loop()
            fn = functools.partial(
                chat_completion,
                api_key=self.api_key,
                model=use_model,
                messages=messages,
                temperature=use_temp,
                max_completion_tokens=use_max_tokens,
                task=f"{self.role}.{task}",
            )
            # Run sync rate-limited call in a thread so we don't block the event loop
            return await loop.run_in_executor(None, fn)


# ---------------------------------------------------------------------------
# Singleton instances per agent role  (import these directly)
# ---------------------------------------------------------------------------

_persona_router: Optional[LLMRouter] = None
_recommender_router: Optional[LLMRouter] = None
_supervisor_router: Optional[LLMRouter] = None
_resolver_router: Optional[LLMRouter] = None


def get_persona_router() -> LLMRouter:
    global _persona_router
    if _persona_router is None:
        _persona_router = LLMRouter(
            api_key=settings.persona_api_key,
            model=settings.persona_llm_model,
            temperature=settings.persona_temperature,
            max_completion_tokens=getattr(settings, "persona_max_tokens", settings.llm_max_output_tokens),
            role="persona",
            max_concurrent=getattr(settings, "llm_max_concurrent_calls", 5),
        )
    return _persona_router


def get_recommender_router() -> LLMRouter:
    global _recommender_router
    if _recommender_router is None:
        _recommender_router = LLMRouter(
            api_key=settings.recommender_api_key,
            model=settings.recommender_llm_model,
            temperature=settings.recommender_temperature,
            max_completion_tokens=getattr(settings, "recommender_max_tokens", settings.llm_max_output_tokens),
            role="recommender",
            max_concurrent=getattr(settings, "llm_max_concurrent_calls", 5),
        )
    return _recommender_router


def get_supervisor_router() -> LLMRouter:
    global _supervisor_router
    if _supervisor_router is None:
        _supervisor_router = LLMRouter(
            api_key=settings.supervisor_api_key,
            model=settings.supervisor_llm_model,
            temperature=getattr(settings, "supervisor_temperature", 0.3),
            max_completion_tokens=getattr(settings, "supervisor_max_tokens", settings.llm_max_output_tokens),
            role="supervisor",
            max_concurrent=getattr(settings, "llm_max_concurrent_calls", 5),
        )
    return _supervisor_router


def get_resolver_router() -> LLMRouter:
    global _resolver_router
    if _resolver_router is None:
        _resolver_router = LLMRouter(
            api_key=settings.resolver_api_key,
            model=settings.resolver_llm_model,
            temperature=settings.resolver_temperature,
            max_completion_tokens=getattr(settings, "resolver_max_tokens", settings.llm_max_output_tokens),
            role="resolver",
            max_concurrent=getattr(settings, "llm_max_concurrent_calls", 5),
        )
    return _resolver_router


# Convenience re-export for generic use
llm_router = get_persona_router()
