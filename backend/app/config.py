from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    persistence_enabled: bool = False
    cosmos_endpoint: str = ""
    cosmos_key: str = ""
    cosmos_database_name: str = "jobassist"
    cosmos_container_name: str = "results"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    max_upload_bytes: int = 5 * 1024 * 1024
    enable_pdf_ocr_fallback: bool = True
    tesseract_cmd: str = ""

    model_config = SettingsConfigDict(env_file=PROJECT_ROOT_ENV_FILE, extra="ignore")


settings = Settings()
