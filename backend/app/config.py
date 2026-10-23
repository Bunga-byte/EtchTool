from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FRIP_", env_file=".env", extra="ignore"
    )
    database_url: str = "sqlite:///./frip.db"
    mode: str = "synthetic"
    auth_backend: str = "local_tokens"
    tokens_json: dict[str, dict[str, str]] = Field(default_factory=dict)
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @model_validator(mode="after")
    def safe_auth(self):
        if self.mode not in {"synthetic", "enterprise"}:
            raise ValueError("FRIP_MODE must be synthetic or enterprise")
        for token, value in self.tokens_json.items():
            if not token.strip():
                raise ValueError("Empty token bindings are not allowed")
            if value.get("role") not in {
                "viewer",
                "analyst",
                "editor",
                "admin",
            } or not value.get("subject"):
                raise ValueError("Token bindings require subject and supported role")
            for field in ("sources", "equipment", "collections"):
                if "*" in {entry.strip() for entry in value.get(field, "").split(",")}:
                    raise ValueError(
                        "Explicit authorization scopes are required; wildcard scopes are not allowed"
                    )
        if self.auth_backend not in {"local_tokens", "external_provider"}:
            raise ValueError("Unsupported authentication backend")
        if (
            self.mode == "enterprise"
            and self.auth_backend == "local_tokens"
            and not self.tokens_json
        ):
            raise ValueError(
                "Enterprise mode requires configured authentication; anonymous access is disabled"
            )
        return self


@lru_cache
def settings():
    return Settings()
