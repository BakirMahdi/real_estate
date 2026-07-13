from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
import bcrypt
import secrets
from .db import db_cursor
import os

# How long an emailed verification code stays valid, and how many wrong guesses
# are allowed before the code is burned (online brute-force protection; the
# /auth/verify-email endpoint is also rate limited).
VERIFICATION_TTL_MINUTES = 10
MAX_VERIFICATION_ATTEMPTS = 5

# JWT settings
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-this-in-production")
ALGORITHM = "HS256"
# Login session lifetime in minutes. Defaults to 30 days when unset - long
# enough that a user effectively "stays logged in", but bounded so a raw
# token that ever leaks outside its httponly cookie (a proxy/server log
# line, a MITM'd network) doesn't stay valid forever with no way to revoke
# it. Set ACCESS_TOKEN_EXPIRE_MINUTES explicitly for a stricter value.
_DEFAULT_EXPIRE_MINUTES = 30 * 24 * 60  # 30 days
_expire_env = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "").strip()
ACCESS_TOKEN_EXPIRE_MINUTES = int(_expire_env) if _expire_env.isdigit() and int(_expire_env) > 0 else _DEFAULT_EXPIRE_MINUTES


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta is not None:
        to_encode.update({"exp": datetime.utcnow() + expires_delta})
    else:
        to_encode.update({"exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        return payload
    except JWTError:
        return None


def is_admin(token: str) -> bool:
    """Check if the token belongs to an admin user."""
    payload = verify_token(token)
    if not payload:
        return False
    return payload.get("role") == "admin"


def _generate_verification_code() -> str:
    """A 6-digit numeric code, zero-padded (secrets = cryptographically random)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def register_local_user(email: str, password: str) -> tuple[str, Optional[str]]:
    """Create (or refresh) an unverified local account and return its code.

    Returns (status, code):
      - ("exists", None)   -> a verified account already uses this email
      - ("created", code)  -> new account; caller should email the code
      - ("refreshed", code)-> account existed but was never verified; the
                              password and code are updated and a fresh code
                              is returned (covers "I didn't get the email")
      - ("error", None)    -> unexpected failure
    """
    try:
        with db_cursor(commit=True) as cur:
            cur.execute(
                "SELECT id, email_verified FROM users WHERE username = %s", (email,)
            )
            row = cur.fetchone()

            code = _generate_verification_code()
            expires = datetime.now(timezone.utc) + timedelta(minutes=VERIFICATION_TTL_MINUTES)
            password_hash = get_password_hash(password)

            if row:
                _, email_verified = row
                if email_verified:
                    return ("exists", None)
                # Unverified account re-registering: reset its password/code so a
                # stale or intercepted earlier code can't be used.
                cur.execute(
                    """
                    UPDATE users
                    SET password_hash = %s, verification_code = %s,
                        verification_expires_at = %s, verification_attempts = 0
                    WHERE username = %s
                    """,
                    (password_hash, code, expires, email),
                )
                status = "refreshed"
            else:
                cur.execute(
                    """
                    INSERT INTO users (username, password_hash, role, email_verified,
                                       verification_code, verification_expires_at)
                    VALUES (%s, %s, 'user', FALSE, %s, %s)
                    """,
                    (email, password_hash, code, expires),
                )
                status = "created"

            return (status, code)
    except Exception as e:
        print(f"Error registering user: {e}")
        return ("error", None)


def refresh_verification_code(email: str) -> Optional[str]:
    """Issue a fresh code for an existing UNVERIFIED account (password untouched).

    Returns the new code, or None if the account doesn't exist or is already
    verified. Used by the "resend code" flow.
    """
    try:
        with db_cursor(commit=True) as cur:
            cur.execute(
                "SELECT id, email_verified FROM users WHERE username = %s", (email,)
            )
            row = cur.fetchone()
            if not row or row[1]:
                return None

            code = _generate_verification_code()
            expires = datetime.now(timezone.utc) + timedelta(minutes=VERIFICATION_TTL_MINUTES)
            cur.execute(
                """
                UPDATE users
                SET verification_code = %s, verification_expires_at = %s,
                    verification_attempts = 0
                WHERE id = %s
                """,
                (code, expires, row[0]),
            )
            return code
    except Exception as e:
        print(f"Error refreshing verification code: {e}")
        return None


def verify_email_code(email: str, code: str) -> Optional[dict]:
    """Confirm the emailed code, mark the account verified, and return it.

    Returns the user dict on success, or None if the code is wrong/expired/
    exhausted. Wrong guesses increment an attempt counter that burns the code
    once MAX_VERIFICATION_ATTEMPTS is reached.
    """
    try:
        with db_cursor(commit=True) as cur:
            cur.execute(
                """
                SELECT id, username, role, verification_code,
                       verification_expires_at, verification_attempts, email_verified
                FROM users WHERE username = %s
                """,
                (email,),
            )
            row = cur.fetchone()
            if not row:
                return None

            user_id, username, role, stored_code, expires_at, attempts, email_verified = row

            if email_verified:
                return {"id": user_id, "username": username, "role": role}

            expired = expires_at is None or datetime.now(timezone.utc) > expires_at
            exhausted = attempts is not None and attempts >= MAX_VERIFICATION_ATTEMPTS
            if not stored_code or expired or exhausted:
                return None

            if not secrets.compare_digest(str(stored_code), str(code)):
                cur.execute(
                    "UPDATE users SET verification_attempts = verification_attempts + 1 WHERE id = %s",
                    (user_id,),
                )
                return None

            # Correct code: mark verified and clear the one-time fields.
            cur.execute(
                """
                UPDATE users
                SET email_verified = TRUE, verification_code = NULL,
                    verification_expires_at = NULL, verification_attempts = 0
                WHERE id = %s
                """,
                (user_id,),
            )
            return {"id": user_id, "username": username, "role": role}
    except Exception as e:
        print(f"Error verifying email code: {e}")
        return None


def authenticate_user(username: str, password: str) -> Optional[dict]:
    try:
        with db_cursor() as cur:
            cur.execute(
                "SELECT id, username, password_hash, role, email_verified FROM users WHERE username = %s",
                (username,)
            )
            user = cur.fetchone()

        if not user:
            return None

        user_id, user_username, password_hash, role, email_verified = user

        # Google-authenticated accounts have no local password.
        if not password_hash:
            return None
        if not verify_password(password, password_hash):
            return None

        return {
            "id": user_id,
            "username": user_username,
            "role": role,
            "email_verified": bool(email_verified),
        }
    except Exception as e:
        print(f"Error authenticating user: {e}")
        return None


GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")


def verify_google_credential(credential: str) -> Optional[dict]:
    """Verify a Google ID token (from Sign in with Google) and return its claims.

    Returns the decoded token info ({sub, email, name, ...}) when valid and
    issued for our client, or None otherwise. Requires GOOGLE_CLIENT_ID to be
    configured.
    """
    if not GOOGLE_CLIENT_ID:
        return None
    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests

        # clock_skew_in_seconds tolerates the intermittent clock drift of the
        # Docker/WSL2 VM (it falls behind after the host sleeps), which would
        # otherwise reject a freshly issued token as "used too early".
        info = id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
            clock_skew_in_seconds=300,
        )
        if not info.get("email_verified", False):
            return None
        return info
    except Exception as e:
        print(f"Error verifying Google credential: {e}")
        return None


def get_or_create_google_user(email: str) -> Optional[dict]:
    """Find or create a passwordless user keyed by their Google email."""
    try:
        with db_cursor(commit=True) as cur:
            # Google has already verified this email, so the account is verified
            # outright. If a matching local account existed but was never verified,
            # signing in through Google confirms ownership and marks it verified.
            #
            # Security: an unverified row's password_hash cannot be trusted — anyone
            # can /register that email with a password of their choosing, since the
            # verification code (sent to the real owner) is never entered. If we
            # only flipped email_verified here, that attacker-chosen password would
            # become valid for the real owner's account the moment they signed in
            # with Google. So on conflict we also null out password_hash, but only
            # when the row wasn't already verified — a legitimate user who already
            # verified their own local password keeps it.
            cur.execute(
                """
                INSERT INTO users (username, password_hash, role, email_verified)
                VALUES (%s, NULL, 'user', TRUE)
                ON CONFLICT (username) DO UPDATE
                SET email_verified = TRUE,
                    password_hash = CASE
                        WHEN users.email_verified THEN users.password_hash
                        ELSE NULL
                    END
                RETURNING id, username, role
                """,
                (email,),
            )
            row = cur.fetchone()
        return {"id": row[0], "username": row[1], "role": row[2]}
    except Exception as e:
        print(f"Error creating Google user: {e}")
        return None
