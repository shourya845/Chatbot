"""Backend-owned privacy policy for model and retrieval providers."""
import os
from enum import Enum

from .config import load_environment

load_environment()


class PrivacyMode(str, Enum):
    CLOUD_ALLOWED = "cloud_allowed"
    LOCAL_ONLY = "local_only"


def get_privacy_mode() -> PrivacyMode:
    configured = os.getenv("PRIVACY_MODE", PrivacyMode.CLOUD_ALLOWED.value).strip().lower()
    try:
        return PrivacyMode(configured)
    except ValueError as error:
        allowed = ", ".join(mode.value for mode in PrivacyMode)
        raise ValueError(f"PRIVACY_MODE must be one of: {allowed}") from error


def external_services_allowed() -> bool:
    return get_privacy_mode() is PrivacyMode.CLOUD_ALLOWED
