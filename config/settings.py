from __future__ import annotations
from pydantic import Field, field_validator, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",          
        case_sensitive=False,  
        extra="ignore",         
    )

    # -------------------------------------------------------------------------
    # LLM
    # -------------------------------------------------------------------------
    gemini_api_key: str = Field(
        ...,
        description="Google Gemini API key. Required. Set via GEMINI_API_KEY env var."
    )
    gemini_model: Literal[
        "gemini-2.5-flash",       # recommended — best balance for prototype
        "gemini-2.5-flash-lite",  # highest free quota (1000 req/day)
        "gemini-2.5-pro",         # best reasoning, very limited (100 req/day)
] =    Field(
    "gemini-2.5-flash",
    description="Gemini model. Free tier."
    )
    gemini_temperature: float = Field(
        0.2,
        ge=0.0, le=2.0,
        description="LLM temperature. Low = deterministic structured output. Keep ≤ 0.4 for agents."
    )
    gemini_max_output_tokens: int = Field(
        4096,
        ge=256, le=8192,
        description="Max tokens per Gemini response."
    )
    gemini_max_retries: int = Field(
        3,
        ge=1, le=10,
        description="Number of retry attempts on Gemini API errors before failing."
    )
    gemini_retry_delay_seconds: float = Field(
        2.0,
        ge=0.5,
        description="Base delay between Gemini retries (exponential backoff applied)."
    )

    # -------------------------------------------------------------------------
    # Personas
    # -------------------------------------------------------------------------
    max_num_personas: int = Field(
        5,
        ge=1, le=10,
        description="Maximum number of persona agents to run in parallel per evaluation."
    )
    use_persona_library: bool = Field(
        False,
        description=(
            "If True, supplement LLM-generated personas with pre-built personas "
            "from config/persona_library.yaml that match the UI type."
        )
    )
    persona_library_path: str = Field(
        "config/persona_library.yaml",
        description="Path to the YAML file containing pre-built persona templates."
    )

    # -------------------------------------------------------------------------
    # Persona simulation loop
    # -------------------------------------------------------------------------
    persona_max_steps: int = Field(
        15,
        ge=5, le=50,
        description="Maximum number of actions a persona agent can take before forced stop."
    )
    persona_action_timeout_seconds: float = Field(
        10.0,
        ge=1.0,
        description="Playwright timeout per action (click, type, etc.) in seconds."
    )
    persona_page_load_timeout_seconds: float = Field(
        30.0,
        ge=5.0,
        description="Playwright timeout for full page load in seconds."
    )
    persona_headless: bool = Field(
        True,
        description="Run Playwright browser in headless mode. Set False for debugging."
    )

    # -------------------------------------------------------------------------
    # Clustering
    # -------------------------------------------------------------------------
    hdbscan_min_cluster_size: int = Field(
        2,
        ge=2, le=20,
        description=(
            "Minimum number of issues to form a cluster. "
            "Issues below this threshold become singleton clusters."
        )
    )
    hdbscan_min_samples: int = Field(
        1,
        ge=1,
        description="HDBSCAN min_samples parameter. Lower = more clusters, fewer noise points."
    )
    embedding_model: str = Field(
        "all-MiniLM-L6-v2",
        description="sentence-transformers model for issue embedding. Tradeoff: speed vs quality."
    )
    clustering_similarity_threshold: float = Field(
        0.75,
        ge=0.0, le=1.0,
        description=(
            "Cosine similarity threshold for merging near-duplicate issues before clustering. "
            "Issues with similarity > threshold are considered duplicates."
        )
    )

    # -------------------------------------------------------------------------
    # Conflict resolution
    # -------------------------------------------------------------------------
    conflict_strategy: Literal["llm"] = Field(
        "llm",
        description="Conflict resolution strategy. Currently only 'llm' (LLM-based negotiation)."
    )
    conflict_max_negotiation_rounds: int = Field(
        3,
        ge=1, le=10,
        description="Maximum negotiation rounds per conflict before escalating to mediator."
    )

    # -------------------------------------------------------------------------
    # Verification loop
    # -------------------------------------------------------------------------
    max_correction_loops: int = Field(
        3,
        ge=1, le=10,
        description=(
            "Maximum number of fix → verify cycles before accepting remaining issues. "
            "After this limit, the system reports what it has."
        )
    )
    verification_resolution_threshold: float = Field(
        0.8,
        ge=0.0, le=1.0,
        description=(
            "Fraction of critical+high issues that must be resolved to consider "
            "verification passed and skip further correction loops."
        )
    )

    # -------------------------------------------------------------------------
    # Output and logging
    # -------------------------------------------------------------------------
    output_dir: str = Field(
        "outputs",
        description="Directory where JSON reports and artifacts are written."
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        "INFO",
        description="Logging verbosity."
    )
    log_format: Literal["console", "json"] = Field(
        "console",
        description="console = human-readable dev output. json = structured for log ingestion."
    )
    save_action_traces: bool = Field(
        True,
        description="If True, write each persona's full action trace JSON to output_dir."
    )
    save_patched_html: bool = Field(
        True,
        description="If True, write the patched HTML file to output_dir after verification."
    )

    # -------------------------------------------------------------------------
    # Validators
    # -------------------------------------------------------------------------
    @field_validator("max_num_personas")
    @classmethod
    def warn_high_persona_count(cls, v: int) -> int:
        if v > 5:
            import warnings
            warnings.warn(
                f"num_personas={v} will make {v} parallel Gemini calls. "
                ,
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
        """Prefix for loading local HTML files in Playwright."""
        return "file://"

    @computed_field
    @property
    def is_debug_mode(self) -> bool:
        """True if log level is DEBUG — enables extra verbose output."""
        return self.log_level == "DEBUG"


settings = Settings()

