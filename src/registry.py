from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models import BaseProvider

PROVIDER_REGISTRY: dict[str, type[BaseProvider]] = {}


def register_provider(name: str):
    """Class decorator that registers a provider under a lowercase key."""
    def decorator(cls: type[BaseProvider]) -> type[BaseProvider]:
        PROVIDER_REGISTRY[name.lower()] = cls
        return cls
    return decorator
