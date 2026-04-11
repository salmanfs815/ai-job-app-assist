from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://app:app@db:5432/jobassist"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    max_upload_bytes: int = 5 * 1024 * 1024
    enable_pdf_ocr_fallback: bool = True
    tesseract_cmd: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
