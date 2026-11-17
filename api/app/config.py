"""Runtime settings. Values come from the process environment."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    mongodb_uri: str = "mongodb://10.30.30.10:27017"
    mongodb_db: str = "fleettrace"
    mongo_timeout_ms: int = 2000
    freshness_threshold_seconds: float = 10.0
    api_host: str = "10.20.20.10"
    api_port: int = 8443
    log_level: str = "INFO"

    @property
    def freshness_threshold_ms(self) -> int:
        return int(self.freshness_threshold_seconds * 1000)
