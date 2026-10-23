"""Local token authentication boundary; replace with verified corporate OIDC adapter."""

from dataclasses import dataclass
import secrets
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    subject: str
    role: str
    sources: tuple[str, ...] = ()


def principal(
    request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)
):
    config = request.app.state.config
    if credentials:
        for token, binding in config.tokens_json.items():
            if secrets.compare_digest(token, credentials.credentials):
                return Principal(
                    binding["subject"],
                    binding["role"],
                    tuple(
                        filter(
                            None, binding.get("sources", "maintenance,parts").split(",")
                        )
                    ),
                )
        raise HTTPException(401, "Invalid bearer token")
    if config.mode == "synthetic":
        return Principal("synthetic-anonymous", "viewer")
    raise HTTPException(401, "Authentication required")


def require_roles(*roles):
    def authorize(actor: Principal = Depends(principal)):
        if actor.role not in roles:
            raise HTTPException(403, "Role is not authorized for this operation")
        return actor

    return authorize
