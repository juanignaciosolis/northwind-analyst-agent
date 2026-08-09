from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    """Configuración validada de la aplicación."""

    model_config = SettingsConfigDict(
        extra="ignore",
        case_sensitive=False,
        env_file_encoding="utf-8",
        env_file = BASE_DIR / ".env"
    )

    app_env: Literal["development", "testing", "production"] = "development"
    gemini_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    gemini_default_model: str = "gemini-3.1-flash-lite"
    openai_default_model: str = "gpt-4o-mini"
    default_provider: str = "GEMINI"

    db_user: str = "postgres"
    db_password: SecretStr | None = None
    db_name: str = "Northwind"
    db_port: int = 5432
    db_host: str = "localhost"

    request_timeout_seconds: float = Field(default=20.0, gt=0)
    max_retries: int = Field(default=2, ge=0, le=8)
    retry_base_delay_seconds: float = Field(default=0.25, ge=0)
    max_concurrency: int = Field(default=3, ge=1, le=32)
    history_max_turns: int = Field(default=6, ge=1, le=50)

    budget: float = Field(default=1.27, ge=0, lt=5)
    gemini_input_usd_per_million: float = Field(default=0.25, ge=0)
    gemini_output_usd_per_million: float = Field(default=1.50, ge=0)
    openai_input_usd_per_million: float = Field(default=0.15, ge=0)
    opneai_output_usd_per_million: float = Field(default=0.6, ge=0)

    @model_validator(mode="after")
    def validate_provider(self):
        """Impide activar un llm sin configurar una provider valido."""
        if self.default_provider not in ("GEMINI","OPENAI"):
            raise ValueError("requiere PROVIDER")
        return self

    @model_validator(mode="after")
    def validate_db_credentials(self):
        """Verifica credenciales de la base de datos."""
        if not self.db_host:
            raise ValueError("requiere HOST")
        if not self.db_user:
            raise ValueError("requiere USER")
        if not self.db_password:
            raise ValueError("requiere PASSWORD")
        if not self.db_name:
            raise ValueError("requiere DB NAME")
        if not self.db_port:
            raise ValueError("requiere DB PORT")
        return self

    @model_validator(mode="after")
    def validate_live_mode(self):
        """Impide activar un llm sin configurar una credencial."""
        if self.default_provider == "GEMINI" and self.gemini_api_key is None:
            raise ValueError("PROVIDER=GEMINI requiere GEMINI_API_KEY")
        elif self.default_provider == "OPNEAI" and self.openai_api_key is None:
            raise ValueError("PROVIDER=OPENAI requiere OPENAI_API_KEY")
        return self

    @classmethod
    def from_env(cls, env_path: str | Path | None = None):
        path = Path(env_path) if env_path is not None else None
        values = {"_env_file": path} if path is not None and path.exists() else {}
        return cls(**values)

    def api_key_value(self) -> str | None:
        if self.default_provider == "GEMINI":
            return self.gemini_api_key.get_secret_value() if self.gemini_api_key else None
        elif self.default_provider == "OPENAI":
             return self.openai_api_key.get_secret_value() if self.openai_api_key else None     
        else:
            return None  

    def get_db_password(self) -> str | None:
        if self.db_password:
            return self.db_password.get_secret_value() if self.db_password else None    

    def safe_dict(self) -> dict:
        """Devuelve configuración apta para logs, sin revelar keys ni passwords."""
        data = self.model_dump(exclude={"gemini_api_key","openai_api_key","db_password"})
        data["gemini_api_key"] = "***configurada***" if self.gemini_api_key else None
        data["openai_api_key"] = "***configurada***" if self.openai_api_key else None
        data["db_password"] = "***configurada***" if self.db_password else None

        return data

settings = Settings()

if __name__ == "__main__":

    print(settings.db_user)
    print(settings.gemini_api_key)
    print(settings.safe_dict())
    print(settings.api_key_value())
    print(settings.get_db_password())