"""PostgreSQL adapter; callers supply a trusted local user ID and autocommit connection."""

from pathlib import Path
import secrets

from psycopg.errors import UniqueViolation


def apply_identity_schema(connection) -> None:
    """Install additive OAuth tables after app.database.apply_schema."""
    connection.execute(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))


class PostgresIdentityStore:
    def __init__(self, connection):
        if not connection.autocommit:
            raise ValueError("OAuth storage requires an autocommit PostgreSQL connection")
        self.connection = connection

    def create_state(self, digest, user_id, purpose, verifier_ciphertext, expires_at):
        self.connection.execute("DELETE FROM oauth_pending_states WHERE expires_at <= now()")
        self.connection.execute(
            """INSERT INTO oauth_pending_states
               (state_digest, user_id, purpose, verifier_ciphertext, expires_at)
               VALUES (%s, %s, %s, %s, %s)""",
            (digest, user_id, purpose, verifier_ciphertext, expires_at),
        )

    def create_login_attempt(self, digest, browser_digest, verifier_ciphertext, expires_at):
        self.connection.execute("DELETE FROM oauth_login_attempts WHERE expires_at <= now()")
        self.connection.execute(
            """INSERT INTO oauth_login_attempts
               (state_digest, browser_digest, verifier_ciphertext, expires_at)
               VALUES (%s, %s, %s, %s)""",
            (digest, browser_digest, verifier_ciphertext, expires_at),
        )

    def consume_login_attempt(self, digest, browser_digest):
        row = self.connection.execute(
            """DELETE FROM oauth_login_attempts
               WHERE state_digest = %s AND browser_digest = %s AND expires_at > now()
               RETURNING verifier_ciphertext""",
            (digest, browser_digest),
        ).fetchone()
        return bytes(row[0]) if row else None

    def consume_state(self, digest, user_id, purpose):
        # DELETE is atomic: at most one concurrent callback receives the verifier.
        row = self.connection.execute(
            """DELETE FROM oauth_pending_states
               WHERE state_digest = %s AND user_id = %s AND purpose = %s
                 AND expires_at > now()
               RETURNING verifier_ciphertext""",
            (digest, user_id, purpose),
        ).fetchone()
        return bytes(row[0]) if row else None

    def save_verified_token(self, user_id, github_id, purpose, token_ciphertext,
                            refresh_ciphertext, scopes, expires_at, refresh_expires_at):
        # The unique users.github_id constraint prevents the same GitHub account
        # from silently binding to two local accounts. A mismatched link fails closed.
        try:
            with self.connection.transaction():
                row = self.connection.execute(
                    """UPDATE users SET github_id = %s
                       WHERE id = %s AND (github_id IS NULL OR github_id = %s)
                       RETURNING id""", (github_id, user_id, github_id)
                ).fetchone()
                if not row:
                    return False
                self.connection.execute(
                """INSERT INTO oauth_connections
                   (user_id, purpose, github_id, token_ciphertext, refresh_ciphertext,
                    scopes, expires_at, refresh_expires_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (user_id, purpose) DO UPDATE SET
                       github_id = EXCLUDED.github_id,
                       token_ciphertext = EXCLUDED.token_ciphertext,
                       refresh_ciphertext = EXCLUDED.refresh_ciphertext,
                       scopes = EXCLUDED.scopes,
                       expires_at = EXCLUDED.expires_at,
                       refresh_expires_at = EXCLUDED.refresh_expires_at,
                       updated_at = now()""",
                    (user_id, purpose, github_id, token_ciphertext, refresh_ciphertext,
                     list(scopes), expires_at, refresh_expires_at),
                )
        except UniqueViolation:
            return False
        return True

    def load_token(self, user_id, purpose):
        row = self.connection.execute(
            """SELECT c.github_id, c.token_ciphertext, c.refresh_ciphertext,
                      c.scopes, c.expires_at, c.refresh_expires_at
               FROM oauth_connections c JOIN users u ON u.id = c.user_id
               WHERE c.user_id = %s AND c.purpose = %s AND u.github_id = c.github_id""",
            (user_id, purpose),
        ).fetchone()
        if not row:
            return None
        return (row[0], bytes(row[1]), bytes(row[2]) if row[2] else None,
                frozenset(row[3]), row[4], row[5])

    def bootstrap_verified_login(self, github_id, token_ciphertext, refresh_ciphertext,
                                 scopes, expires_at, refresh_expires_at):
        """One GitHub ID maps to one local user under concurrent first logins."""
        try:
            with self.connection.transaction():
                row = self.connection.execute(
                    """INSERT INTO users(email, password_hash, github_id)
                       VALUES (%s, %s, %s)
                       ON CONFLICT (github_id) DO UPDATE SET github_id = EXCLUDED.github_id
                       RETURNING id""",
                    (f"github-{github_id}@ariadne.invalid",
                     "!oauth-disabled:" + secrets.token_hex(32), github_id),
                ).fetchone()
                user_id = str(row[0])
                self.connection.execute(
                    """INSERT INTO oauth_connections
                       (user_id, purpose, github_id, token_ciphertext, refresh_ciphertext,
                        scopes, expires_at, refresh_expires_at)
                       VALUES (%s, 'login', %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (user_id, purpose) DO UPDATE SET
                           token_ciphertext = EXCLUDED.token_ciphertext,
                           refresh_ciphertext = EXCLUDED.refresh_ciphertext,
                           scopes = EXCLUDED.scopes,
                           expires_at = EXCLUDED.expires_at,
                           refresh_expires_at = EXCLUDED.refresh_expires_at,
                           updated_at = now()""",
                    (user_id, github_id, token_ciphertext, refresh_ciphertext,
                     list(scopes), expires_at, refresh_expires_at),
                )
                return user_id
        except UniqueViolation:
            # A concurrent first login can hit users.email's unique index before
            # PostgreSQL selects the github_id conflict target. Retry only when
            # the verified GitHub ID now names the existing account; never
            # merge by the synthetic email itself.
            row = self.connection.execute(
                "SELECT id FROM users WHERE github_id = %s", (github_id,)
            ).fetchone()
            if row and self.save_verified_token(
                str(row[0]), github_id, "login", token_ciphertext,
                refresh_ciphertext, scopes, expires_at, refresh_expires_at
            ):
                return str(row[0])
            return None

    def replace_session(self, user_id, digest, expires_at, previous_digest=None):
        with self.connection.transaction():
            self.connection.execute("DELETE FROM oauth_sessions WHERE expires_at <= now()")
            if previous_digest is not None:
                self.connection.execute(
                    "DELETE FROM oauth_sessions WHERE session_digest = %s", (previous_digest,))
            self.connection.execute(
                """INSERT INTO oauth_sessions(session_digest, user_id, expires_at)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (user_id) DO UPDATE SET
                       session_digest = EXCLUDED.session_digest,
                       expires_at = EXCLUDED.expires_at""",
                (digest, user_id, expires_at),
            )

    def load_session(self, digest):
        row = self.connection.execute(
            """SELECT user_id::text FROM oauth_sessions
               WHERE session_digest = %s AND expires_at > now()""", (digest,)
        ).fetchone()
        return row[0] if row else None

    def delete_session(self, digest):
        self.connection.execute("DELETE FROM oauth_sessions WHERE session_digest = %s", (digest,))
