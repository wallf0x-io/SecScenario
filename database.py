import sqlite3
from contextlib import contextmanager
from config import Config


SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    original_name TEXT NOT NULL,
    file_type TEXT,
    size_bytes INTEGER,
    extracted_text TEXT,
    uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'uploaded'
);

CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL,
    title TEXT,
    vuln_type TEXT,
    severity TEXT,
    cve TEXT,
    affected_component TEXT,
    summary TEXT,
    root_cause TEXT,
    exploitation_steps TEXT,
    raw_json TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (report_id) REFERENCES reports(id)
);

CREATE TABLE IF NOT EXISTS challenges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    difficulty TEXT,
    category TEXT,
    flag TEXT,
    folder_path TEXT,
    port INTEGER,
    status TEXT DEFAULT 'generated',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (analysis_id) REFERENCES analyses(id)
);
"""


def init_db():
    Config.ensure_dirs()
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        conn.commit()


@contextmanager
def get_conn():
    conn = sqlite3.connect(Config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
    finally:
        conn.close()


def insert_report(filename, original_name, file_type, size_bytes, extracted_text):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO reports (filename, original_name, file_type, size_bytes, extracted_text)
               VALUES (?, ?, ?, ?, ?)""",
            (filename, original_name, file_type, size_bytes, extracted_text),
        )
        conn.commit()
        return cur.lastrowid


def list_reports():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM reports ORDER BY uploaded_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_report(report_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM reports WHERE id = ?", (report_id,)
        ).fetchone()
        return dict(row) if row else None


def update_report_status(report_id, status):
    with get_conn() as conn:
        conn.execute(
            "UPDATE reports SET status = ? WHERE id = ?", (status, report_id)
        )
        conn.commit()


def insert_analysis(report_id, data, raw_json):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO analyses (report_id, title, vuln_type, severity, cve,
                                     affected_component, summary, root_cause,
                                     exploitation_steps, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                report_id,
                data.get("title"),
                data.get("vuln_type"),
                data.get("severity"),
                data.get("cve"),
                data.get("affected_component"),
                data.get("summary"),
                data.get("root_cause"),
                data.get("exploitation_steps"),
                raw_json,
            ),
        )
        conn.commit()
        return cur.lastrowid


def get_analysis(analysis_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM analyses WHERE id = ?", (analysis_id,)
        ).fetchone()
        return dict(row) if row else None


def get_analysis_by_report(report_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM analyses WHERE report_id = ? ORDER BY created_at DESC LIMIT 1",
            (report_id,),
        ).fetchone()
        return dict(row) if row else None


def insert_challenge(analysis_id, name, description, difficulty, category, flag, folder_path, port):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO challenges (analysis_id, name, description, difficulty,
                                       category, flag, folder_path, port)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (analysis_id, name, description, difficulty, category, flag, folder_path, port),
        )
        conn.commit()
        return cur.lastrowid


def list_challenges():
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT c.*, a.vuln_type, a.severity, r.original_name
               FROM challenges c
               JOIN analyses a ON c.analysis_id = a.id
               JOIN reports r ON a.report_id = r.id
               ORDER BY c.created_at DESC"""
        ).fetchall()
        return [dict(r) for r in rows]


def get_challenge(challenge_id):
    with get_conn() as conn:
        row = conn.execute(
            """SELECT c.*, a.vuln_type, a.severity, a.summary, a.exploitation_steps,
                      r.original_name
               FROM challenges c
               JOIN analyses a ON c.analysis_id = a.id
               JOIN reports r ON a.report_id = r.id
               WHERE c.id = ?""",
            (challenge_id,),
        ).fetchone()
        return dict(row) if row else None


def update_challenge_status(challenge_id, status):
    with get_conn() as conn:
        conn.execute(
            "UPDATE challenges SET status = ? WHERE id = ?", (status, challenge_id)
        )
        conn.commit()


def get_challenges_by_report(report_id):
    """All challenges whose analysis belongs to a given report."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT c.* FROM challenges c
               JOIN analyses a ON c.analysis_id = a.id
               WHERE a.report_id = ?""",
            (report_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def delete_challenge(challenge_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM challenges WHERE id = ?", (challenge_id,))
        conn.commit()


def delete_report_cascade(report_id):
    """Delete report + its analyses + all child challenges (DB rows only)."""
    with get_conn() as conn:
        conn.execute(
            """DELETE FROM challenges
               WHERE analysis_id IN (SELECT id FROM analyses WHERE report_id = ?)""",
            (report_id,),
        )
        conn.execute("DELETE FROM analyses WHERE report_id = ?", (report_id,))
        conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))
        conn.commit()
