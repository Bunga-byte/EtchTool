"""Internal-only extension points. No external service is configured here."""

from dataclasses import dataclass, field
from typing import Protocol

from .contracts import AuthorizationContext, ConnectionConfig, SourceScope


@dataclass(frozen=True)
class ServiceCredentials:
    """Opaque provider result; never serialize credentials into records or logs."""

    identity: str
    headers: dict[str, str] = field(default_factory=dict, repr=False)


class SecretProvider(Protocol):
    def credentials_for(self, reference: str, source_id: str) -> ServiceCredentials: ...


class CorporateServiceAuthentication(Protocol):
    def authorize(
        self, config: ConnectionConfig, requested_scope: SourceScope
    ) -> AuthorizationContext: ...


class RetentionPolicy(Protocol):
    """Data owner must approve legal holds before any source deletion task."""

    def may_purge(
        self, source_id: str, classification: str, record_id: str
    ) -> bool: ...
