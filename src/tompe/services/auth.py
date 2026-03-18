"""Simple token-based authentication (v1)."""

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer(auto_error=False)


async def verify_token(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> dict:
    """Verify bearer token and return user info.

    v1: Simple token lookup. v2: OAuth/institutional SSO.
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authentication token")
    # TODO: implement token validation
    raise NotImplementedError
