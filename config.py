import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-only-change-me")
    HOST = os.getenv("FLASK_HOST", "127.0.0.1")
    PORT = int(os.getenv("FLASK_PORT", "5000"))
    DEBUG = os.getenv("FLASK_DEBUG", "1") == "1"

    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

    BASE_DIR = BASE_DIR
    UPLOAD_DIR = BASE_DIR / "uploads"
    CHALLENGES_DIR = BASE_DIR / "challenges"
    INSTANCE_DIR = BASE_DIR / "instance"
    DB_PATH = INSTANCE_DIR / "secscenario.db"

    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100 MB
    ALLOWED_EXTENSIONS = {
        "pdf", "txt", "md", "markdown", "html", "htm",
        "json", "zip", "log", "rst",
    }

    @classmethod
    def ensure_dirs(cls):
        for d in (cls.UPLOAD_DIR, cls.CHALLENGES_DIR, cls.INSTANCE_DIR):
            d.mkdir(parents=True, exist_ok=True)
