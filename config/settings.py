#config/settings.py

from __future__ import annotations
from typing import Literal
from pathlib import Path

from pydantic import Field, field_validator, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Supervisor agent ──────────────────────────────────────────────────────
    supervisor_api_key: str = Field(
        ...,
        description="API key for the Supervisor agent. Set SUPERVISOR_API_KEY in .env."
    )
    supervisor_llm_model: str = Field(
        "llama-3.3-70b-versatile",
        description="LLM model for the Supervisor agent."
    )
    supervisor_temperature: float = Field(
        0.2, ge=0.0, le=2.0,
        description="Low temperature keeps JSON output deterministic and schema-conformant."
    )

    # ── Persona agents ────────────────────────────────────────────────────────
    persona_api_key: str = Field(
        ...,
        description="API key for Persona agents. Set PERSONA_API_KEY in .env."
    )
    persona_llm_model: str = Field(
        "llama-3.1-8b-instant",
        description="LLM model for Persona agents. Fastest/cheapest — highest call volume."
    )
    persona_temperature: float = Field(
        0.4, ge=0.0, le=2.0,
        description="Slightly higher temperature for varied persona interaction patterns."
    )

    # ── Recommender agents ────────────────────────────────────────────────────
    recommender_api_key: str = Field(
        ...,
        description="API key for Recommender agents. Set RECOMMENDER_API_KEY in .env."
    )
    recommender_llm_model: str = Field(
        "llama-3.3-70b-versatile",
        description="LLM model for Recommender agents."
    )
    recommender_temperature: float = Field(
        0.1, ge=0.0, le=2.0,
        description="Very low — patch generation must be precise and not hallucinate HTML."
    )

    # ── Resolver / Mediator agent ─────────────────────────────────────────────
    resolver_api_key: str = Field(
        ...,
        description="API key for the Resolver agent. Set RESOLVER_API_KEY in .env."
    )
    resolver_llm_model: str = Field(
        "llama-3.1-70b-versatile",
        description="LLM model for the Resolver / Mediator agent."
    )
    resolver_temperature: float = Field(
        0.3, ge=0.0, le=2.0,
        description="Moderate — needs flexibility to reason about trade-offs."
    )

    # ── Per-agent output token limits ─────────────────────────────────────────
    # Tight per-agent caps reduce Groq response time significantly.
    # Persona decisions are short JSON (~200 tokens); larger budgets waste latency.
    supervisor_max_tokens: int = Field(
        2048, ge=256, le=8192,
        description=(
            "Max output tokens for supervisor LLM calls "
            "(batch analysis, persona generation, recommender profiles)."
        )
    )
    persona_max_tokens: int = Field(
        512, ge=64, le=2048,
        description=(
            "Max output tokens per persona decide/act step. "
            "Keep small — each step produces a single short JSON action. "
            "Smaller limit = faster Groq response."
        )
    )
    recommender_max_tokens: int = Field(
        1024, ge=256, le=4096,
        description="Max output tokens for recommender patch proposals."
    )
    resolver_max_tokens: int = Field(
        1024, ge=256, le=4096,
        description="Max output tokens for conflict resolver / mediator responses."
    )
    verifier_max_tokens: int = Field(
        1024, ge=256, le=4096,
        description="Max output tokens for verification node responses."
    )
    llm_max_output_tokens: int = Field(
        1024, ge=64, le=8192,
        description="Global fallback token limit used by any agent without a specific override."
    )

    # ── LLM retry / backoff ───────────────────────────────────────────────────
    llm_max_retries: int = Field(
        5, ge=1, le=10,
        description="Retry attempts on LLM API errors before failing."
    )
    llm_retry_delay_seconds: float = Field(
        5.0, ge=0.5,
        description="Base delay (seconds) between retries. Exponential backoff applied."
    )

    # ── Parallel rate-limit control (semaphore + shared backoff) ─────────────
    llm_max_concurrent_calls: int = Field(
        5, ge=1, le=30,
        description=(
            "Max simultaneous in-flight LLM calls per API key. "
            "Groq free tier: 30 RPM. At ~10s avg latency, 5 concurrent = 0.5 req/s. "
            "Lower to 3 if you still hit 429s."
        )
    )
    llm_tpm_limit: int = Field(
        6000, ge=0,
        description=(
            "Tokens-per-minute limit for the sliding-window TPM tracker. "
            "Groq free tier: 6000 TPM for most models. Set 0 to disable."
        )
    )
    llm_inter_request_delay_seconds: float = Field(
        0.0, ge=0.0,
        description=(
            "Optional fixed delay after acquiring the semaphore slot. "
            "Use when TPM (not RPM) is the bottleneck. 0.0 = semaphore only."
        )
    )

    # ── Persona count and simulation loop ─────────────────────────────────────
    max_num_personas: int = Field(
        3, ge=1, le=10,
        description=(
            "Max personas generated per page. "
            "Total run time scales linearly — keep ≤ 3 on Groq free tier. "
            "Use 5 only for thorough evaluations."
        )
    )
    use_persona_library: bool = Field(
        False,
        description=(
            "If True, supplement LLM-generated personas with pre-built templates "
            "from config/persona_library.yaml."
        )
    )
    persona_library_path: str = Field(
        "config/persona_library.yaml",
        description="Path to the pre-built persona templates YAML file."
    )
    persona_max_steps: int = Field(
        10, ge=3, le=50,
        description=(
            "Maximum Playwright actions a persona can take before forced stop. "
            "Each step = 1 LLM call (~3-8s on Groq). "
            "Use 6 for quick tests, 10 for balanced, 15 for thorough."
        )
    )
    persona_action_timeout_seconds: float = Field(
        10.0, ge=1.0,
        description="Playwright timeout per action (click, type, scroll) in seconds."
    )
    persona_page_load_timeout_seconds: float = Field(
        30.0, ge=5.0,
        description="Playwright timeout for full page load in seconds."
    )
    persona_headless: bool = Field(
        True,
        description="Run Playwright browser headless. Set False to watch while debugging."
    )
    persona_inter_simulation_delay_seconds: float = Field(
        0.0, ge=0.0,
        description=(
            "Extra delay between persona simulations. "
            "0.0 = rely on semaphore alone. "
            "Set 0.5-1.0 only if you still see 429s after lowering concurrency."
        )
    )

    # ── Issue clustering ──────────────────────────────────────────────────────
    hdbscan_min_cluster_size: int = Field(
        2, ge=2, le=20,
        description="Minimum issues to form a cluster. Singletons get their own cluster."
    )
    hdbscan_min_samples: int = Field(
        1, ge=1,
        description="HDBSCAN min_samples. Lower = more clusters, fewer noise points."
    )
    embedding_model: str = Field(
        "all-MiniLM-L6-v2",
        description="sentence-transformers model for issue text embeddings."
    )
    clustering_similarity_threshold: float = Field(
        0.75, ge=0.0, le=1.0,
        description=(
            "Cosine similarity threshold for deduplicating near-identical issues "
            "before clustering."
        )
    )

    # ── Conflict resolution ───────────────────────────────────────────────────
    conflict_strategy: Literal["llm"] = Field(
        "llm",
        description="Conflict resolution strategy. Currently only 'llm' is supported."
    )
    conflict_max_negotiation_rounds: int = Field(
        1, ge=1, le=10,
        description=(
            "Max debate rounds per conflict before the mediator decides. "
            "1 round is sufficient for most conflicts and minimises LLM calls."
        )
    )

    # ── Verification / correction loop ────────────────────────────────────────
    max_correction_loops: int = Field(
        0, ge=0, le=5,
        description=(
            "Max fix→verify cycles after initial patching. "
            "0 = apply patches once and report (fastest). "
            "1 = one correction pass if verification fails. "
            "Set ≥ 1 only for thorough evaluations."
        )
    )
    verification_resolution_threshold: float = Field(
        0.8, ge=0.0, le=1.0,
        description=(
            "Fraction of critical+high issues that must be resolved to pass "
            "verification. 0.8 = 80%."
        )
    )

    # ── Output and logging ────────────────────────────────────────────────────
    output_dir: str = Field(
        "outputs",
        description="Directory where JSON reports and patched HTML are written."
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        "INFO",
        description="Logging verbosity level."
    )
    log_format: Literal["console", "json"] = Field(
        "console",
        description="console = coloured human-readable. json = structured for log ingestion."
    )
    save_action_traces: bool = Field(
        True,
        description="Write each persona's full action trace JSON to output_dir."
    )
    save_patched_html: bool = Field(
        True,
        description="Write the patched HTML file to output_dir after verification."
    )

    # ── Validators ────────────────────────────────────────────────────────────
    @field_validator("max_num_personas")
    @classmethod
    def warn_high_persona_count(cls, v: int) -> int:
        if v > 5:
            import warnings
            warnings.warn(
                f"max_num_personas={v} will generate {v} parallel LLM call streams. "
                "Groq free-tier accounts may hit rate limits. Consider ≤ 5.",
                UserWarning,
                stacklevel=2,
            )
        return v

    @field_validator("output_dir")
    @classmethod
    def ensure_output_dir_exists(cls, v: str) -> str:
        Path(v).mkdir(parents=True, exist_ok=True)
        return v

    # ── Computed fields ───────────────────────────────────────────────────────
    @computed_field
    @property
    def playwright_file_url_prefix(self) -> str:
        return "file://"

    @computed_field
    @property
    def is_debug_mode(self) -> bool:
        return self.log_level == "DEBUG"


settings = Settings()