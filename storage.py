"""
SQLite storage — jobs, runs, and job status tracking.
Schema is migrated automatically on startup (non-destructive).
"""

import sqlite3
import logging
from datetime import datetime

from scrapers.base import Job

logger = logging.getLogger(__name__)

VALID_STATUSES = {"none", "saved", "applied", "rejected"}


class JobStorage:
    def __init__(self, db_path: str = "jobs.db"):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id          TEXT PRIMARY KEY,
                    title       TEXT NOT NULL,
                    url         TEXT,
                    company     TEXT NOT NULL,
                    location    TEXT,
                    department  TEXT,
                    seen_at     TEXT NOT NULL,
                    status      TEXT NOT NULL DEFAULT 'none',
                    is_remote   INTEGER NOT NULL DEFAULT 0,
                    notified    INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    ran_at      TEXT NOT NULL,
                    companies   INTEGER,
                    new_jobs    INTEGER
                )
            """)
            # Non-destructive migrations for existing DBs
            self._migrate(conn)
            conn.commit()
        logger.debug(f"Storage ready at {self.db_path}")

    def _migrate(self, conn):
        """Add new columns to existing tables without breaking old data."""
        existing = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
        migrations = {
            "status":    "ALTER TABLE jobs ADD COLUMN status TEXT NOT NULL DEFAULT 'none'",
            "is_remote": "ALTER TABLE jobs ADD COLUMN is_remote INTEGER NOT NULL DEFAULT 0",
            "notified":  "ALTER TABLE jobs ADD COLUMN notified INTEGER NOT NULL DEFAULT 0",
        }
        for col, sql in migrations.items():
            if col not in existing:
                conn.execute(sql)
                logger.info(f"DB migrated: added column '{col}'")

    # ── Write ──────────────────────────────────────────────────────────────────

    def save_jobs(self, jobs: list[Job]):
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR IGNORE INTO jobs
                    (id, title, url, company, location, department, seen_at, status, is_remote, notified)
                VALUES
                    (:id, :title, :url, :company, :location, :department, :seen_at, 'none', :is_remote, 0)
                """,
                [{
                    **j.to_dict(),
                    "seen_at":   now,
                    "is_remote": 1 if _is_remote(j.location) else 0,
                } for j in jobs],
            )
            conn.commit()
        logger.info(f"Saved {len(jobs)} new jobs")

    def log_run(self, companies_checked: int, new_jobs: int):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO runs (ran_at, companies, new_jobs) VALUES (?, ?, ?)",
                (datetime.utcnow().isoformat(), companies_checked, new_jobs),
            )
            conn.commit()

    def set_status(self, job_id: str, status: str) -> bool:
        """Update the application status of a job. Returns True if found."""
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}. Must be one of {VALID_STATUSES}")
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE jobs SET status = ? WHERE id = ?", (status, job_id)
            )
            conn.commit()
        return cur.rowcount > 0

    def mark_notified(self, job_ids: list[str]):
        """Mark jobs as included in a digest notification."""
        if not job_ids:
            return
        with self._connect() as conn:
            conn.executemany(
                "UPDATE jobs SET notified = 1 WHERE id = ?",
                [(jid,) for jid in job_ids]
            )
            conn.commit()

    # ── Read ───────────────────────────────────────────────────────────────────

    def get_all_ids(self) -> set[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id FROM jobs").fetchall()
        return {row["id"] for row in rows}

    def get_recent_jobs(self, limit: int = 500) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY seen_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_unnotified_jobs(self) -> list[dict]:
        """Return jobs not yet included in a digest."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE notified = 0 ORDER BY seen_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_jobs_by_status(self, status: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY seen_at DESC", (status,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        with self._connect() as conn:
            total    = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            companies= conn.execute("SELECT COUNT(DISTINCT company) FROM jobs").fetchone()[0]
            runs     = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            saved    = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='saved'").fetchone()[0]
            applied  = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='applied'").fetchone()[0]
            rejected = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='rejected'").fetchone()[0]
            remote   = conn.execute("SELECT COUNT(*) FROM jobs WHERE is_remote=1").fetchone()[0]
        return {
            "total_jobs": total,
            "companies_tracked": companies,
            "total_runs": runs,
            "saved": saved,
            "applied": applied,
            "rejected": rejected,
            "remote_jobs": remote,
        }


def _is_remote(location: str) -> bool:
    if not location:
        return False
    loc = location.lower()
    return any(kw in loc for kw in ["remote", "anywhere", "worldwide", "distributed", "work from home", "wfh"])
