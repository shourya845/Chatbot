"""Shared project paths and environment loading."""

from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RUNTIME_DATA_DIR = DATA_DIR / "runtime"
EVALUATIONS_DIR = DATA_DIR / "evaluations"
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
ENV_FILE = PROJECT_ROOT / ".env"


def load_environment() -> None:
    """Load root settings without replacing variables already set by the shell."""
    load_dotenv(ENV_FILE)
