import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load .env file
load_dotenv()

class Settings(BaseSettings):
    # --- Supabase Client Connection ---
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str

    # --- Direct Database Connection (Optional, but often needed for ORMs/Migrations) ---
    # These map to the standard Supabase connection string details.
    DB_HOST: str
    DB_PORT: int
    DB_NAME: str
    DB_USER: str
    DB_PASS: str

    # --- Existing Variables ---
    JWT_SECRET: str = "supersecretkey"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    OPENAI_API_KEY: str
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    S3_BUCKET_NAME: str
    AWS_REGION: str = "us-east-1"
    SECRET_KEY: str = "fbfabfec4de24aca3cfa63855ca0038ca4e238d03d7aad9f2bd9196c707b9984"
    ALGORITHM: str = "HS256"
    FERNET_KEY: str = "ORkXLF5tZlUH-owwdK0SbjVEt5HOQGdVLT8aRCtjG64="
    # DATABASE_URL: str

    @property
    def DATABASE_URL(self):
        # This property still works for direct SQLAlchemy connection
        # return f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        return f"postgresql://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        # return "postgresql://postgres.hfnabbkfqxhclxmewdds:zg88U!sxruDNs.z@aws-1-eu-west-2.pooler.supabase.com:5432/postgres"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()

# Debug: verify keys loaded
print("🔑 OpenAI Key Loaded:", settings.OPENAI_API_KEY[:8], "...")
print("🚀 Supabase URL Loaded:", settings.SUPABASE_URL[:30], "...")