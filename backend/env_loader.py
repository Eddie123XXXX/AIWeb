import os

from dotenv import load_dotenv


def load_backend_env() -> str | None:
    """Load backend env vars from AIWEB_ENV_FILE, .env, or .env.production."""
    explicit_path = os.getenv("AIWEB_ENV_FILE")
    if explicit_path:
        load_dotenv(explicit_path, override=False)
        return explicit_path

    if os.path.exists(".env"):
        load_dotenv(".env", override=False)
        return ".env"

    if os.path.exists(".env.production"):
        load_dotenv(".env.production", override=False)
        return ".env.production"

    load_dotenv(override=False)
    return None
