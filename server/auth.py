"""
Awakener - Authentication Module
==================================
Provides simple password-based authentication for the web management console.

Security model:
- Single admin password (no user accounts needed)
- Password stored as bcrypt hash in data/auth.json
- JWT tokens issued on successful login (stored in browser localStorage)
- All API routes (except /api/setup and /api/login) require a valid token

First-time setup flow:
    1. User visits the web console for the first time
    2. No auth.json exists -> frontend shows "Set Password" page
    3. User sets a password via POST /api/setup
    4. Password is hashed and saved to data/auth.json
    5. JWT token returned, user enters the console

Subsequent visits:
    1. auth.json exists -> frontend shows login page
    2. User enters password via POST /api/login
    3. Password verified against stored hash
    4. JWT token returned on success
"""

import os
import json
import bcrypt
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


# JWT configuration
# The secret key is generated on first setup and stored alongside the password hash.
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# Security scheme for FastAPI dependency injection
security = HTTPBearer(auto_error=False)


class AuthManager:
    """
    Manages password authentication and JWT token lifecycle.

    Attributes:
        auth_file: Path to the JSON file storing the password hash and JWT secret.
    """

    def __init__(self, data_dir: str):
        """
        Initialize the auth manager.

        Args:
            data_dir: Absolute path to the data/ directory where auth.json is stored.
        """
        self.auth_file = os.path.join(data_dir, "auth.json")

    def is_configured(self) -> bool:
        """
        Check if a password has been set (first-time setup completed).

        Returns:
            True if auth.json exists and contains a valid password hash.
        """
        if not os.path.exists(self.auth_file):
            return False
        try:
            data = self._load()
            return "password_hash" in data
        except (json.JSONDecodeError, OSError):
            return False

    def setup_password(self, password: str, force: bool = False) -> str:
        """
        Set the admin password.

        On first-time setup, generates a new bcrypt hash and a random JWT secret.
        When force=True, allows overwriting an existing password (used for
        password changes from the web console).

        Args:
            password: The plaintext password to set.
            force:    If True, allow overwriting existing password.

        Returns:
            A JWT token for immediate use after setup.

        Raises:
            ValueError: If password is empty or too short.
            RuntimeError: If a password is already set and force is False.
        """
        if self.is_configured() and not force:
            raise RuntimeError("Password already configured. Use force=True to overwrite.")

        if not password or len(password) < 4:
            raise ValueError("Password must be at least 4 characters.")

        # Generate password hash
        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

        # Keep existing JWT secret if available, otherwise generate new
        jwt_secret = None
        if force and os.path.exists(self.auth_file):
            try:
                existing = self._load()
                jwt_secret = existing.get("jwt_secret")
            except (json.JSONDecodeError, OSError):
                pass

        if not jwt_secret:
            jwt_secret = bcrypt.gensalt().decode("utf-8")

        # Save to auth.json
        data = {
            "password_hash": password_hash.decode("utf-8"),
            "jwt_secret": jwt_secret,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save(data)

        # Return a token so the user is immediately logged in after setup
        return self._create_token(jwt_secret)

    def verify_password(self, password: str) -> str | None:
        """
        Verify a password and return a JWT token if correct.

        Args:
            password: The plaintext password to verify.

        Returns:
            A JWT token string if password is correct, None otherwise.
        """
        if not self.is_configured():
            return None

        data = self._load()
        stored_hash = data["password_hash"].encode("utf-8")

        if bcrypt.checkpw(password.encode("utf-8"), stored_hash):
            return self._create_token(data["jwt_secret"])

        return None

    def verify_token(self, token: str) -> bool:
        """
        Verify a JWT token is valid and not expired.

        Args:
            token: The JWT token string to verify.

        Returns:
            True if the token is valid, False otherwise.
        """
        if not self.is_configured():
            return False

        data = self._load()
        try:
            payload = jwt.decode(
                token,
                data["jwt_secret"],
                algorithms=[JWT_ALGORITHM],
            )
            return True
        except JWTError:
            return False

    def change_password(self, old_password: str, new_password: str) -> bool:
        """
        Change the admin password.

        Args:
            old_password: Current password for verification.
            new_password: New password to set.

        Returns:
            True if password was changed successfully, False if old_password is wrong.

        Raises:
            ValueError: If new_password is empty or too short.
        """
        if not new_password or len(new_password) < 4:
            raise ValueError("New password must be at least 4 characters.")

        data = self._load()
        stored_hash = data["password_hash"].encode("utf-8")

        if not bcrypt.checkpw(old_password.encode("utf-8"), stored_hash):
            return False

        # Update password hash, keep the same JWT secret
        new_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt())
        data["password_hash"] = new_hash.decode("utf-8")
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save(data)

        return True

    # -- Internal helpers ------------------------------------------------------

    def _create_token(self, secret: str) -> str:
        """Generate a JWT token with expiration."""
        payload = {
            "sub": "admin",
            "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS),
            "iat": datetime.now(timezone.utc),
        }
        return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)

    def _load(self) -> dict:
        """Load auth.json from disk."""
        with open(self.auth_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, data: dict) -> None:
        """Save data to auth.json."""
        os.makedirs(os.path.dirname(self.auth_file), exist_ok=True)
        with open(self.auth_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


def require_auth(auth_manager: AuthManager):
    """
    Create a FastAPI dependency that enforces authentication.

    Usage in routes:
        @router.get("/api/config", dependencies=[Depends(require_auth(auth_mgr))])
        async def get_config(): ...

    Args:
        auth_manager: The AuthManager instance to use for token verification.

    Returns:
        A FastAPI dependency function.
    """
    async def _verify(
        credentials: HTTPAuthorizationCredentials | None = Depends(security),
    ):
        # If no password is set yet, allow access (first-time setup)
        if not auth_manager.is_configured():
            return True

        if credentials is None:
            raise HTTPException(status_code=401, detail="Authentication required")

        if not auth_manager.verify_token(credentials.credentials):
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        return True

    return _verify
