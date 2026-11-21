"""Guard schema migrations so development processes cannot change remote DBs."""

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


def is_local_migration_target(url: str) -> bool:
    """Return whether a database URL points at an approved local dev database."""
    try:
        parsed = make_url(url)
    except (ArgumentError, TypeError, ValueError):
        return False

    if parsed.drivername.startswith("sqlite"):
        return True
    if not parsed.drivername.startswith(("postgres", "postgresql")):
        return False

    host = (parsed.host or "").lower().rstrip(".")
    port = parsed.port if parsed.port is not None else 5432
    return host in {"localhost", "127.0.0.1", "::1", "db"} and port == 5432


def assert_remote_migrations_allowed(url: str, allow_remote: bool) -> None:
    """Refuse non-local migrations unless explicitly enabled."""
    if not is_local_migration_target(url) and not allow_remote:
        raise RuntimeError(
            "Refusing to migrate a remote database without explicit opt-in. Database URL and credentials are not shown."
        )
