from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

# Load .env into os.environ too (some modules read os.getenv directly)
load_dotenv()


class Settings(BaseSettings):
    """
    All secrets are required and come from the environment / .env.
    Never add default values for secrets here: anything in this file ends up in git.
    See .env.example for the full list.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Supabase client (optional, not used by the API yet) ---
    SUPABASE_URL: str | None = None
    SUPABASE_ANON_KEY: str | None = None

    # --- Database ---
    DB_HOST: str
    DB_PORT: int
    DB_NAME: str
    DB_USER: str
    DB_PASS: str

    # --- Tokens ---
    JWT_SECRET: str  # signs access tokens
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    SECRET_KEY: str  # signs refresh tokens
    ALGORITHM: str = "HS256"
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # --- Rate limiting (per company, falls back to per IP) ---
    RATE_LIMIT: str = "60/minute"

    # --- Logging ---
    LOG_LEVEL: str = "INFO"

    # --- Voice checks (tune per environment) ---
    CHALLENGE_TTL: int = 120  # seconds a challenge phrase stays valid
    MATCH_THRESHOLD: float = 0.8  # min transcript/challenge text similarity (liveness)
    SPOOF_THRESHOLD: float = 0.30  # max AASIST spoof probability accepted
    SIMILARITY_THRESHOLD: float = 0.65  # min voiceprint cosine similarity (identity)

    # --- External services ---
    OPENAI_API_KEY: str
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    S3_BUCKET_NAME: str
    AWS_REGION: str = "us-east-1"

    @property
    def DATABASE_URL(self) -> str:
        # URL.create escapes special characters (@, :, / ...) in the password
        return URL.create(
            "postgresql",
            username=self.DB_USER,
            password=self.DB_PASS,
            host=self.DB_HOST,
            port=self.DB_PORT,
            database=self.DB_NAME,
        ).render_as_string(hide_password=False)


settings = Settings()
