"""Provider routing for the Sentrix Kernel.

The router decides *which* AI provider should handle a given request based on
declared provider capabilities and the request's requirements. It operates on
capability descriptors rather than concrete SDKs, keeping the kernel
provider-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from app.kernel.prompt_builder import Prompt


class KernelError(Exception):
    """Base error for kernel-level failures."""


class NoProviderAvailableError(KernelError):
    """Raised when no configured provider can satisfy a request."""


class Capability(str, Enum):
    """Capabilities a provider profile can advertise."""

    GENERAL = "general"
    SECURITY = "security"
    CODE = "code"
    REASONING = "reasoning"
    LONG_CONTEXT = "long_context"


@dataclass(frozen=True)
class KernelRequest:
    """A provider-agnostic request to the kernel."""

    prompt: Prompt
    capabilities: tuple[Capability, ...] = ()
    preferred_provider: str | None = None
    max_tokens: int | None = None


@dataclass(frozen=True)
class Route:
    """The outcome of routing a request to a provider."""

    provider: str
    capabilities: tuple[Capability, ...] = ()


@dataclass(frozen=True)
class ProviderProfile:
    """Static description of a provider's capabilities."""

    name: str
    capabilities: tuple[Capability, ...] = field(default_factory=tuple)
    priority: int = 0


class Router(Protocol):
    """Interface for providers that decide where a request should go."""

    def route(self, request: KernelRequest) -> Route:
        """Return the route for a request, or raise if none is suitable."""
        ...


class DefaultProviderRouter:
    """Routes requests to the best available provider.

    Selection strategy:

    1. If ``request.preferred_provider`` names a registered provider, use it.
    2. Filter providers whose capabilities satisfy the request requirements.
    3. Among eligible providers, choose the highest ``priority`` (ties broken
       by registration order).
    4. Fall back to a ``GENERAL`` provider only when no capabilities are
       required.
    """

    def __init__(self, profiles: list[ProviderProfile] | None = None) -> None:
        self._profiles: list[ProviderProfile] = list(profiles or [])

    @property
    def profiles(self) -> tuple[ProviderProfile, ...]:
        """Registered provider profiles, in registration order."""
        return tuple(self._profiles)

    def register(self, profile: ProviderProfile) -> None:
        """Register (or replace) a provider profile."""
        for index, existing in enumerate(self._profiles):
            if existing.name == profile.name:
                self._profiles[index] = profile
                return
        self._profiles.append(profile)

    def route(self, request: KernelRequest) -> Route:
        """Select the provider for ``request`` based on its requirements."""
        required = request.capabilities

        # 1. Explicit preference wins when the provider is registered.
        if request.preferred_provider is not None:
            for profile in self._profiles:
                if profile.name == request.preferred_provider:
                    return Route(
                        provider=profile.name,
                        capabilities=profile.capabilities,
                    )
            raise NoProviderAvailableError(
                f"Preferred provider '{request.preferred_provider}' is not registered."
            )

        # 2. Eligible providers must satisfy every required capability.
        eligible = [
            profile
            for profile in self._profiles
            if set(required).issubset(set(profile.capabilities))
        ]

        # 3. Highest priority first; ties preserve registration order.
        if eligible:
            best = max(eligible, key=lambda profile: profile.priority)
            return Route(provider=best.name, capabilities=best.capabilities)

        # 4. When no capabilities are required, a general-purpose provider is
        # an acceptable fallback.
        if not required:
            for profile in self._profiles:
                if Capability.GENERAL in profile.capabilities:
                    return Route(provider=profile.name, capabilities=profile.capabilities)

        raise NoProviderAvailableError("No configured provider can satisfy the request.")


__all__ = [
    "Capability",
    "DefaultProviderRouter",
    "KernelError",
    "KernelRequest",
    "NoProviderAvailableError",
    "ProviderProfile",
    "Route",
    "Router",
]
