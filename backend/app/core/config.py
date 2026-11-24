from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    redis_url: str
    api_key: str
    gemini_api_key: str = ''
    llm_model: str = 'gemini-3.5-flash-lite'
    llm_min_interval: float = 5.0  # seconds between calls: 60 divided by the requests per minute you may use
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
