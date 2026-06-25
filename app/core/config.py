"""Application configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Myntra Fetcher"
    debug: bool = False
    myntra_base_url: str = "https://www.myntra.com"
    request_timeout_seconds: float = 30.0
    max_concurrent_requests: int = 3
    request_delay_seconds: float = 0.8
    max_retries: int = 3
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    enable_delivery_check: bool = True
    delivery_pincodes: dict[str, str] = {
        "Mumbai": "400072",
        "Bangalore": "560001",
        "Delhi": "110006",
        "Ahmedabad": "380054",
        "Kolkata": "700001",
    }


settings = Settings()
