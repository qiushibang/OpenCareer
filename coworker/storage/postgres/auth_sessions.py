"""PostgreSQL-backed mapping from OpenID identities to browser sessions."""

from __future__ import annotations

import hashlib
import secrets
from uuid import uuid4

from coworker.server.auth import (
    AuthSession,
    IdentityClaims,
    IssuedAuthSession,
)
from coworker.server.identity import Principal


def _token_sha256(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _identity_lock_key(issuer: str, subject: str) -> int:
    """Return a collision-resistant PostgreSQL advisory-lock key for one identity.

    PostgreSQL text parameters cannot contain a NUL byte.  Hash the two parts
    with their byte lengths instead of concatenating them with a delimiter.
    """
    digest = hashlib.sha256()
    for value in (issuer, subject):
        encoded = value.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return int.from_bytes(digest.digest()[:8], "big", signed=True)


class PostgresAuthSessionStore:
    def __init__(self, database) -> None:
        self.database = database

    def issue(
        self,
        claims: IdentityClaims,
        *,
        ttl_seconds: int,
    ) -> IssuedAuthSession:
        if ttl_seconds <= 0:
            raise ValueError("auth session lifetime must be positive")
        with self.database.shared_transaction() as connection:
            connection.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                (_identity_lock_key(claims.issuer, claims.subject),),
            )
            row = connection.execute(
                """
                SELECT user_id
                FROM identity.external_identities
                WHERE issuer = %s AND subject = %s
                """,
                (claims.issuer, claims.subject),
            ).fetchone()
            if row is None:
                user_id = f"usr_{uuid4().hex}"
                connection.execute(
                    "INSERT INTO identity.users(id) VALUES (%s)",
                    (user_id,),
                )
                connection.execute(
                    """
                    INSERT INTO identity.external_identities(
                        id, user_id, issuer, subject, email,
                        email_verified, display_name
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(uuid4()),
                        user_id,
                        claims.issuer,
                        claims.subject,
                        claims.email,
                        claims.email_verified,
                        claims.display_name,
                    ),
                )
            else:
                user_id = str(row[0])
                connection.execute(
                    """
                    UPDATE identity.external_identities
                    SET email = %s,
                        email_verified = %s,
                        display_name = %s,
                        updated_at = now()
                    WHERE issuer = %s AND subject = %s
                    """,
                    (
                        claims.email,
                        claims.email_verified,
                        claims.display_name,
                        claims.issuer,
                        claims.subject,
                    ),
                )

            raw_token = secrets.token_urlsafe(48)
            token_hash = _token_sha256(raw_token)
            connection.execute(
                """
                INSERT INTO identity.auth_sessions(
                    user_id, token_sha256, id, expires_at
                ) VALUES (
                    %s, %s, %s,
                    now() + (%s * interval '1 second')
                )
                """,
                (user_id, token_hash, str(uuid4()), ttl_seconds),
            )

        session = AuthSession(
            principal=Principal(user_id, "oidc-session"),
            email=claims.email,
            display_name=claims.display_name,
        )
        return IssuedAuthSession(raw_token=raw_token, session=session)

    def resolve(self, raw_token: str | None) -> AuthSession | None:
        if not raw_token:
            return None
        token_hash = _token_sha256(raw_token)
        with self.database.shared_transaction() as connection:
            row = connection.execute(
                """
                SELECT s.user_id, profile.email, profile.display_name
                FROM identity.auth_sessions AS s
                LEFT JOIN LATERAL (
                    SELECT email, display_name
                    FROM identity.external_identities
                    WHERE user_id = s.user_id
                    ORDER BY updated_at DESC
                    LIMIT 1
                ) AS profile ON TRUE
                WHERE s.token_sha256 = %s
                  AND s.revoked_at IS NULL
                  AND s.expires_at > now()
                """,
                (token_hash,),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE identity.auth_sessions
                SET last_seen_at = now()
                WHERE token_sha256 = %s
                """,
                (token_hash,),
            )
        return AuthSession(
            principal=Principal(str(row[0]), "oidc-session"),
            email=str(row[1]) if row[1] is not None else None,
            display_name=str(row[2]) if row[2] is not None else None,
        )

    def revoke(self, raw_token: str | None) -> None:
        if not raw_token:
            return
        with self.database.shared_transaction() as connection:
            connection.execute(
                """
                UPDATE identity.auth_sessions
                SET revoked_at = COALESCE(revoked_at, now())
                WHERE token_sha256 = %s
                """,
                (_token_sha256(raw_token),),
            )
