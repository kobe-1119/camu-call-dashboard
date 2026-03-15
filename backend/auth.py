"""Authentication module — JWT-based session auth for HIPAA compliance."""
import os
import jwt
import bcrypt
import secrets
from datetime import datetime, timedelta
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Secret key for JWT signing — set via environment variable in production
JWT_SECRET = os.environ.get("JWT_SECRET", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.environ.get("JWT_EXPIRY_HOURS", "12"))

# Dashboard password — MUST be set via environment variable in production
# Generate a hash with: python -c "import bcrypt; print(bcrypt.hashpw(b'yourpassword', bcrypt.gensalt()).decode())"
DASHBOARD_PASSWORD_HASH = os.environ.get("DASHBOARD_PASSWORD_HASH", "")
DASHBOARD_PASSWORD_PLAIN = os.environ.get("DASHBOARD_PASSWORD", "")

security = HTTPBearer(auto_error=False)


def verify_password(password: str) -> bool:
    """Check password against stored hash or plaintext env var."""
    if DASHBOARD_PASSWORD_HASH:
        return bcrypt.checkpw(password.encode(), DASHBOARD_PASSWORD_HASH.encode())
    if DASHBOARD_PASSWORD_PLAIN:
        return secrets.compare_digest(password, DASHBOARD_PASSWORD_PLAIN)
    return False


def create_token(username: str = "user") -> str:
    """Create a JWT token."""
    payload = {
        "sub": username,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict:
    """Verify and decode a JWT token."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """FastAPI dependency — rejects unauthenticated requests."""
    # Check Authorization header
    if credentials:
        verify_token(credentials.credentials)
        return credentials.credentials

    # Check cookie fallback (for browser requests)
    token = request.cookies.get("token")
    if token:
        verify_token(token)
        return token

    raise HTTPException(status_code=401, detail="Not authenticated")
