"""Local token authentication boundary; replace with verified corporate OIDC adapter."""

from dataclasses import dataclass
import secrets
from typing import Protocol
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    subject: str
    role: str
    sources: tuple[str, ...] = ()
    equipment: tuple[str, ...] = ()
    collections: tuple[str, ...] = ()
    export_allowed: bool = False
    anonymous_demo: bool = False


class PrincipalProvider(Protocol):
    """Internal SSO adapter must verify signatures, issuer, audience and expiry.

    Only a server-installed provider can produce this principal. Request headers
    asserting a role, source or equipment scope are never trusted.
    """

    def verify_bearer(self, token: str) -> Principal: ...


def _scopes(binding: dict[str, str], name: str, default: str = "") -> tuple[str, ...]:
    return tuple(x.strip() for x in binding.get(name, default).split(",") if x.strip())


def principal(
    request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)
):
    config = request.app.state.config
    if credentials:
        provider = getattr(request.app.state, "authentication_provider", None)
        if provider is not None:
            try:
                actor = provider.verify_bearer(credentials.credentials)
                if (
                    not isinstance(actor, Principal)
                    or not actor.subject
                    or actor.anonymous_demo
                    or actor.role not in {"viewer", "analyst", "editor", "admin"}
                ):
                    raise ValueError("Invalid verified identity")
                return actor
            except Exception:
                raise HTTPException(401, "Bearer authentication failed") from None
        for token, binding in config.tokens_json.items():
            if secrets.compare_digest(token, credentials.credentials):
                return Principal(
                    binding["subject"],
                    binding["role"],
                    _scopes(binding, "sources", "maintenance,parts"),
                    _scopes(binding, "equipment"),
                    _scopes(binding, "collections"),
                    binding.get("export", "false").lower() == "true",
                )
        raise HTTPException(401, "Invalid bearer token")
    if config.mode == "synthetic":
        return Principal("synthetic-anonymous", "viewer", anonymous_demo=True)
    raise HTTPException(401, "Authentication required")


def require_roles(*roles):
    def authorize(actor: Principal = Depends(principal)):
        if actor.role not in roles:
            raise HTTPException(403, "Role is not authorized for this operation")
        return actor

    return authorize


def require_export(request: Request, actor: Principal = Depends(principal)):
    if (
        request.app.state.config.mode != "synthetic"
        and not actor.export_allowed
        and actor.role != "admin"
    ):
        raise HTTPException(403, "Export permission is required")
    return actor
