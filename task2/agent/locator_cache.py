from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from urllib.parse import urlsplit

LOCATOR_CACHE_TABLE = "locator_cache"

# Column-name + SQLite-type set, in canonical order. Used both to CREATE the table
# and to drop+recreate when an existing file's schema does not match.
_EXPECTED_COLUMNS: tuple[tuple[str, str], ...] = (
    ("origin", "TEXT"),
    ("intent", "TEXT"),
    ("role", "TEXT"),
    ("name", "TEXT"),
    ("selector", "TEXT"),
    ("ax_fingerprint", "TEXT"),
    ("confidence", "REAL"),
    ("tier", "TEXT"),
    ("coords_x", "INTEGER"),
    ("coords_y", "INTEGER"),
    ("written_at_utc", "TEXT"),
)

_COLUMN_NAMES: tuple[str, ...] = tuple(name for name, _ in _EXPECTED_COLUMNS)
_INSERT_PLACEHOLDERS = ", ".join("?" for _ in _COLUMN_NAMES)
_INSERT_COLUMN_LIST = ", ".join(_COLUMN_NAMES)
_SELECT_SQL = (
    f"SELECT {_INSERT_COLUMN_LIST} FROM {LOCATOR_CACHE_TABLE} "
    "WHERE origin = ? AND intent = ? LIMIT 1"
)
_UPSERT_SQL = (
    f"INSERT OR REPLACE INTO {LOCATOR_CACHE_TABLE} "
    f"({_INSERT_COLUMN_LIST}) VALUES ({_INSERT_PLACEHOLDERS})"
)
_DELETE_SQL = f"DELETE FROM {LOCATOR_CACHE_TABLE} WHERE origin = ? AND intent = ?"


@dataclass(frozen=True)
class CacheEntry:
    origin: str
    intent: str
    role: str
    name: str | None
    selector: str
    ax_fingerprint: str
    confidence: float
    tier: str
    coords: tuple[int, int] | None
    written_at_utc: str


def _origin_from_url(url: str) -> str:
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    if scheme == "http" and (port is None or port == 80):
        return f"http://{host}"
    if scheme == "https" and (port is None or port == 443):
        return f"https://{host}"
    if port is None:
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def _build_create_sql() -> str:
    column_defs: list[str] = []
    for col_name, col_type in _EXPECTED_COLUMNS:
        if col_name in ("origin", "intent", "role", "selector", "ax_fingerprint", "tier"):
            column_defs.append(f"{col_name} {col_type} NOT NULL")
        elif col_name in ("confidence", "written_at_utc"):
            column_defs.append(f"{col_name} {col_type} NOT NULL")
        else:
            column_defs.append(f"{col_name} {col_type}")
    column_defs.append("PRIMARY KEY (origin, intent)")
    body = ",\n    ".join(column_defs)
    return f"CREATE TABLE {LOCATOR_CACHE_TABLE} (\n    {body}\n)"


def _row_to_entry(row: tuple) -> CacheEntry:
    (
        origin,
        intent,
        role,
        name,
        selector,
        ax_fingerprint,
        confidence,
        tier,
        coords_x,
        coords_y,
        written_at_utc,
    ) = row
    coords: tuple[int, int] | None
    if coords_x is None or coords_y is None:
        coords = None
    else:
        coords = (int(coords_x), int(coords_y))
    return CacheEntry(
        origin=origin,
        intent=intent,
        role=role,
        name=name,
        selector=selector,
        ax_fingerprint=ax_fingerprint,
        confidence=float(confidence),
        tier=tier,
        coords=coords,
        written_at_utc=written_at_utc,
    )


def _entry_to_row(entry: CacheEntry) -> tuple:
    coords_x: int | None
    coords_y: int | None
    if entry.coords is None:
        coords_x = None
        coords_y = None
    else:
        coords_x, coords_y = entry.coords
    return (
        entry.origin,
        entry.intent,
        entry.role,
        entry.name,
        entry.selector,
        entry.ax_fingerprint,
        float(entry.confidence),
        entry.tier,
        coords_x,
        coords_y,
        entry.written_at_utc,
    )


class LocatorCache:
    def __init__(self, *, path: str = ":memory:") -> None:
        self._conn: sqlite3.Connection | None = sqlite3.connect(path)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        assert self._conn is not None
        existing = list(self._conn.execute(f"PRAGMA table_info({LOCATOR_CACHE_TABLE})"))
        existing_set = {(row[1], row[2].upper()) for row in existing}
        expected_set = {(name, dtype.upper()) for name, dtype in _EXPECTED_COLUMNS}
        if existing_set != expected_set:
            self._conn.execute(f"DROP TABLE IF EXISTS {LOCATOR_CACHE_TABLE}")
            self._conn.execute(_build_create_sql())
            self._conn.commit()

    def get(self, *, origin: str, intent: str) -> CacheEntry | None:
        if self._conn is None:
            raise sqlite3.ProgrammingError("Cannot operate on a closed LocatorCache.")
        cur = self._conn.execute(_SELECT_SQL, (origin, intent))
        row = cur.fetchone()
        if row is None:
            return None
        return _row_to_entry(row)

    def put(self, entry: CacheEntry) -> None:
        if self._conn is None:
            raise sqlite3.ProgrammingError("Cannot operate on a closed LocatorCache.")
        self._conn.execute(_UPSERT_SQL, _entry_to_row(entry))
        self._conn.commit()

    def invalidate(self, *, origin: str, intent: str) -> None:
        if self._conn is None:
            raise sqlite3.ProgrammingError("Cannot operate on a closed LocatorCache.")
        self._conn.execute(_DELETE_SQL, (origin, intent))
        self._conn.commit()

    def close(self) -> None:
        if self._conn is None:
            return
        self._conn.close()
        self._conn = None

    def __enter__(self) -> LocatorCache:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
