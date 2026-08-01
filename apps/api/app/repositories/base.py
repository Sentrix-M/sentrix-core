"""Base repository interfaces.

The repository layer is defined as abstract base classes (interfaces) so the
service layer depends only on contracts. Concrete implementations (in-memory
for development/tests, PostgreSQL for production) live alongside their
interface and are wired through the dependency-injection container.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class Repository(ABC):
    """Common contract for all repositories."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Return whether the backing store is reachable."""
        raise NotImplementedError

