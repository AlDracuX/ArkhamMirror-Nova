"""Entity linking and coreference resolution."""

from .coreference import CoreferenceResolver
from .entity_linker import EntityLinker

__all__ = [
    "EntityLinker",
    "CoreferenceResolver",
]
