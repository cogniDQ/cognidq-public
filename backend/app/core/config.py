"""
Application configuration
"""

from pydantic import model_validator
from pydantic_settings import BaseSettings

# Placeholder values that must never reach production.
_INSECURE_PLACEHOLDER_SECRETS = frozenset(
    {
        "",
        "dev-only-change-in-prod",
        "your-secret-key-here-change-in-production",
        "your-jwt-secret-key-here-change-in-production",
        "change-me",
        "changeme",
        "secret",
    }
)


class Settings(BaseSettings):
    """Application settings"""

    # Application
    APP_NAME: str = "DataQuality.AI"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "dev-only-change-in-prod"  # gitleaks:allow

    # API
    API_V1_PREFIX: str = "/api/v1"
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Database
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_TTL: int = 3600

    # OpenAI
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_TEMPERATURE: float = 0.0
    OPENAI_MAX_TOKENS: int = 2000

    # NL Rule Parser — subtype clarification behaviour
    # When confidence is below this threshold, the parser will ask a
    # clarifying question to disambiguate the check subtype even if the LLM
    # picked one. (0.0 disables, 1.0 always asks.)
    NL_PARSER_CONFIDENCE_THRESHOLD: float = 0.80
    # When True, the parser ALWAYS asks the user to confirm the check subtype
    # (and required-field values) regardless of confidence. Useful for
    # workspaces that prefer maximum explicitness over speed.
    NL_PARSER_ALWAYS_ASK_SUBTYPE: bool = False

    # Embedding
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    VECTOR_STORE_PATH: str = "./data/chroma_db"

    # Execution Limits
    MAX_EXECUTION_TIME_SECONDS: int = 60
    MAX_ROWS_RETURNED: int = 10000
    QUERY_TIMEOUT_SECONDS: int = 30

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # File Upload
    UPLOAD_DIR: str = "/tmp/dq_uploads"
    MAX_UPLOAD_SIZE_MB: int = 100

    # MinIO Storage
    STORAGE_TYPE: str = "minio"  # Options: local, minio
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"  # gitleaks:allow
    MINIO_SECRET_KEY: str = "minioadmin"  # gitleaks:allow — dev default; override via env
    MINIO_BUCKET: str = "dq-data-assets"
    MINIO_SECURE: bool = False

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/app.log"

    # Security
    JWT_SECRET_KEY: str = "dev-only-change-in-prod"  # gitleaks:allow
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str | None = None  # When set, the 'iss' claim in every F001 JWT is validated
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 100
    RATE_LIMIT_PER_HOUR: int = 1000

    # Onboarding / registration gating
    # SECURITY: Public `POST /api/v1/auth/register` is disabled by default.
    # Set ALLOW_PUBLIC_REGISTRATION=true only in development / demo sandboxes.
    # When disabled, registration requires a valid invitation_token.
    ALLOW_PUBLIC_REGISTRATION: bool = False

    # When set, activation / invitation emails are composed against this URL.
    APP_PUBLIC_URL: str = "http://localhost:5173"

    # LangGraph Flow Builder Settings
    ENABLE_COMPLEX_FLOW_BUILDER: bool = True
    COMPLEX_FLOW_BUILDER_MAX_INSTRUCTIONS: int = 10
    COMPLEX_FLOW_BUILDER_TIMEOUT: int = 30
    REQUEST_CLASSIFIER_THRESHOLD: int = 3

    # Performance settings for flow builder
    FLOW_BUILDER_CACHE_TTL: int = 300  # 5 minutes
    FLOW_BUILDER_MAX_RETRIES: int = 3
    ENABLE_FLOW_BUILDER_CACHE: bool = True

    # LLM Cost & Performance Settings
    LLM_SIMPLE_MODEL: str = "gpt-3.5-turbo"
    LLM_COMPLEX_MODEL: str = "gpt-4o"
    LLM_MAX_TOKENS_PER_MINUTE: int = 100000

    # Retry & Circuit Breaker Settings
    LLM_RETRY_MAX_ATTEMPTS: int = 3
    LLM_RETRY_INITIAL_DELAY: float = 2.0
    LLM_RETRY_MAX_DELAY: float = 10.0
    LLM_CIRCUIT_BREAKER_THRESHOLD: int = 5
    LLM_CIRCUIT_BREAKER_TIMEOUT: float = 60.0

    # Rate Limiting for Flow Builder
    FLOW_BUILDER_REQUESTS_PER_MINUTE: int = 10
    FLOW_BUILDER_REQUESTS_PER_HOUR: int = 100

    # F-CONN-RBAC — Tenant Connections / Workspace Data Sources lockdown.
    # When True, workspace data-source WRITE endpoints (create / update /
    # archive / restore / test) require the actor to be a tenant admin for
    # the workspace's tenant. Workspace users see data sources read-only;
    # all create/update happens at the tenant level (F130). Default False
    # keeps the legacy F004 behaviour for backwards compatibility.
    WORKSPACE_DATA_SOURCE_TENANT_ADMIN_ONLY: bool = False

    @model_validator(mode="after")
    def _enforce_production_safety(self) -> "Settings":
        """Fail closed: refuse to start production with insecure defaults."""
        if self.ENVIRONMENT.strip().lower() not in {"production", "prod"}:
            return self
        problems = []
        if self.SECRET_KEY in _INSECURE_PLACEHOLDER_SECRETS or len(self.SECRET_KEY) < 32:
            problems.append("SECRET_KEY must be a unique random value of at least 32 characters")
        if self.JWT_SECRET_KEY in _INSECURE_PLACEHOLDER_SECRETS or len(self.JWT_SECRET_KEY) < 32:
            problems.append(
                "JWT_SECRET_KEY must be a unique random value of at least 32 characters"
            )
        if "minioadmin" in (self.MINIO_ACCESS_KEY, self.MINIO_SECRET_KEY):
            problems.append("MINIO_ACCESS_KEY / MINIO_SECRET_KEY must not use the dev defaults")
        if self.DEBUG:
            problems.append("DEBUG must be False")
        if problems:
            raise ValueError(
                "Refusing to start with insecure production configuration "
                "(set ENVIRONMENT=development for local runs):\n- " + "\n- ".join(problems)
            )
        return self

    class Config:
        env_file = ".env"
        case_sensitive = True


# Create settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings."""
    return settings
