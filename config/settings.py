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

    supervisor_api_key: str = Field(
        ...,
        description="API key for the Supervisor agent. Set SUPERVISOR_API_KEY in .env."
    )
    supervisor_llm_model: str = Field(
        "gpt-4.1",
        description="LLM model for the Supervisor agent. Any provider string accepted."
    )
    supervisor_temperature: float = Field(
        0.2,
        ge=0.0, le=2.0,
        description=(
            "Temperature for the Supervisor agent. "
            "Low (0.1-0.3) keeps JSON output deterministic and schema-conformant."
        )
    )

    persona_api_key: str = Field(
        ...,
        description="API key for Persona agents. Set PERSONA_API_KEY in .env."
    )
    persona_llm_model: str = Field(
        "meta-llama/llama-4-scout-17b-16e-instruct",
        description=(
            "LLM model for Persona agents. "
            "Lighter/faster model recommended — this is the highest-volume agent."
        )
    )
    persona_temperature: float = Field(
        0.4,
        ge=0.0, le=2.0,
        description=(
            "Temperature for Persona agents. "
            "Slightly higher than other agents to allow varied interaction patterns "
            "across personas, while still staying grounded."
        )
    )

    recommender_api_key: str = Field(
        ...,
        description="API key for Recommender agents. Set RECOMMENDER_API_KEY in .env."
    )
    recommender_llm_model: str = Field(
        "gemini-2.5-flash",
        description="LLM model for Recommender agents."
    )
    recommender_temperature: float = Field(
        0.1,
        ge=0.0, le=2.0,
        description=(
            "Temperature for Recommender agents. "
            "Very low — patch generation must be precise and not hallucinate HTML."
        )
    )

   
    resolver_api_key: str = Field(
        ...,
        description="API key for the Resolver agent. Set RESOLVER_API_KEY in .env."
    )
    resolver_llm_model: str = Field(
        "gemini-2.5-flash",
        description="LLM model for the Resolver agent."
    )
    resolver_temperature: float = Field(
        0.3,
        ge=0.0, le=2.0,
        description=(
            "Temperature for the Resolver agent. "
            "Moderate — needs some flexibility to reason about trade-offs, "
            "but not so high that mediation becomes inconsistent."
        )
    )

    llm_max_output_tokens: int = Field(
        4096,
        ge=256, le=8192,
        description="Max output tokens per LLM response. Shared across all agents."
    )
    llm_max_retries: int = Field(
        3,
        ge=1, le=10,
        description="Retry attempts on LLM API errors before failing."
    )
    llm_retry_delay_seconds: float = Field(
        2.0,
        ge=0.5,
        description="Base delay (seconds) between retries. Exponential backoff applied on top."
    )

 
    max_num_personas: int = Field(
        5,
        ge=1, le=10,
        description="Number of persona agents to run in parallel per evaluation."
    )
    use_persona_library: bool = Field(
        False,
        description=(
            "If True, supplement LLM-generated personas with pre-built templates "
            "from config/persona_library.yaml matching the detected UI type."
        )
    )
    persona_library_path: str = Field(
        "config/persona_library.yaml",
        description="Path to the pre-built persona templates YAML file."
    )


    persona_max_steps: int = Field(
        15,
        ge=5, le=50,
        description="Maximum Playwright actions a persona can take before forced stop."
    )
    persona_action_timeout_seconds: float = Field(
        10.0,
        ge=1.0,
        description="Playwright timeout per action (click, type, scroll) in seconds."
    )
    persona_page_load_timeout_seconds: float = Field(
        30.0,
        ge=5.0,
        description="Playwright timeout for full page load in seconds."
    )
    persona_headless: bool = Field(
        True,
        description="Run Playwright browser headless. Set False to watch while debugging."
    )

    hdbscan_min_cluster_size: int = Field(
        2,
        ge=2, le=20,
        description="Minimum issues to form a cluster. Singletons get their own cluster."
    )
    hdbscan_min_samples: int = Field(
        1,
        ge=1,
        description="HDBSCAN min_samples. Lower = more clusters, fewer noise points."
    )
    embedding_model: str = Field(
        "all-MiniLM-L6-v2",
        description="sentence-transformers model name for issue text embeddings."
    )
    clustering_similarity_threshold: float = Field(
        0.75,
        ge=0.0, le=1.0,
        description=(
            "Cosine similarity threshold for deduplicating near-identical issues "
            "before clustering. Issues above this threshold are merged."
        )
    )

   
    conflict_strategy: Literal["llm"] = Field(
        "llm",
        description="Conflict resolution strategy. Currently only 'llm' is supported."
    )
    conflict_max_negotiation_rounds: int = Field(
        3,
        ge=1, le=10,
        description="Max debate rounds per conflict before the mediator makes a final call."
    )

    
    max_correction_loops: int = Field(
        3,
        ge=1, le=10,
        description="Max fix→verify cycles before accepting any remaining issues."
    )
    verification_resolution_threshold: float = Field(
        0.8,
        ge=0.0, le=1.0,
        description=(
            "Fraction of critical+high issues that must be resolved to pass "
            "verification and skip further correction loops. 0.8 = 80%."
        )
    )

    
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
        description="console = colored human-readable. json = structured for log ingestion."
    )
    save_action_traces: bool = Field(
        True,
        description="Write each persona's full action trace JSON to output_dir."
    )
    save_patched_html: bool = Field(
        True,
        description="Write the patched HTML file to output_dir after verification."
    )

 
    @field_validator("max_num_personas")
    @classmethod
    def warn_high_persona_count(cls, v: int) -> int:
        if v > 5:
            import warnings
            warnings.warn(
                f"num_personas={v} will make {v} parallel LLM calls per simulation step. "
                "Free-tier accounts may hit rate limits. Consider ≤ 5.",
                UserWarning,
                stacklevel=2,
            )
        return v

    @field_validator("output_dir")
    @classmethod
    def ensure_output_dir_exists(cls, v: str) -> str:
        Path(v).mkdir(parents=True, exist_ok=True)
        return v

   
    @computed_field
    @property
    def playwright_file_url_prefix(self) -> str:
        return "file://"

    @computed_field
    @property
    def is_debug_mode(self) -> bool:
        return self.log_level == "DEBUG"


settings = Settings()