from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FRIP_", env_file=".env", extra="ignore"
    )
    database_url: str = "sqlite:///./frip.db"
    mode: str = "synthetic"
    tokens_json: dict[str, dict[str, str]] = Field(default_factory=dict)
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @model_validator(mode="after")
    def safe_auth(self):
        if self.mode not in {"synthetic", "enterprise"}:
            raise ValueError("FRIP_MODE must be synthetic or enterprise")
        for value in self.tokens_json.values():
            if value.get("role") not in {
                "viewer",
                "analyst",
                "editor",
                "admin",
            } or not value.get("subject"):
                raise ValueError("Token bindings require subject and supported role")
        if self.mode == "enterprise" and not self.tokens_json:
            raise ValueError(
                "Enterprise mode requires configured authentication; anonymous access is disabled"
            )
        return self


@lru_cache
def settings():
    return Settings()
