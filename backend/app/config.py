from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "MAF Deterministic Job Card"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    data_dir: Path = Path("data")
    template_path: Path = Path("templates/job_card_template.xlsx")
    output_dir: Path = Path("data/output")
    upload_dir: Path = Path("data/uploads")
    frontend_dist: Path = Path("frontend/dist")

    max_pdf_bytes: int = 20 * 1024 * 1024
    pdf_chunk_chars: int = 1800
    pdf_chunk_overlap: int = 200
    search_top_k: int = 12
    max_reasoning_context_chars: int = 28_000
    strict_citations: bool = True
    template_task_capacity: int = 40
    reasoning_seed: int = 42

    azure_search_endpoint: str = Field(
        default="https://gptkb-q6f7jlnpp6tnk.search.windows.net",
        alias="AZURE_SEARCH_ENDPOINT"
        )
    
    azure_search_index_name: str = Field(
        default="job-card-reference",
        alias="AZURE_SEARCH_INDEX_NAME"
        )
    
    azure_search_api_key: SecretStr = Field(
        default="JIGLVyzZOsi7qMAayXJgIGd6wohbuOaLbt1x5VXwmtAzSeDJWbI3",
        alias="AZURE_SEARCH_API_KEY"
        )

    azure_openai_endpoint: str
    azure_openai_deployment: str
    azure_openai_api_version: str = "2025-04-01-preview"
    azure_openai_api_key: SecretStr | None = None

    model_config = SettingsConfigDict(
    env_file=str(ROOT / ".env"),
    extra="ignore",
    )

    @field_validator("azure_search_api_key", "azure_openai_api_key", mode="before")
    @classmethod
    def blank_secret_is_none(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value

    @field_validator("allowed_origins")
    @classmethod
    def normalize_origins(cls, value: str) -> str:
        return ",".join(part.strip() for part in value.split(",") if part.strip())

    @property
    def cors_origins(self) -> list[str]:
        return self.allowed_origins.split(",") if self.allowed_origins else []

    @property
    def registry_path(self) -> Path:
        return self.upload_dir / "manifest.json"

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

settings = Settings()

print("================================================")
print("CONFIG LOADED")
print("ENV FILE:", ROOT / ".env")
print("SEARCH:", settings.azure_search_endpoint)
print("INDEX:", settings.azure_search_index_name)
print("================================================")

def reveal(secret: SecretStr | None) -> str | None:
    return secret.get_secret_value() if secret is not None else None
