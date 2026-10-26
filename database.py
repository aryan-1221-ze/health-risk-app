import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name     TEXT NOT NULL CHECK (length(trim(full_name)) > 0),
    date_of_birth TEXT NOT NULL,                 -- stored as yyyy-mm-dd
    email         TEXT NOT NULL,
    glucose       REAL NOT NULL CHECK (glucose > 0),
    haemoglobin   REAL NOT NULL CHECK (haemoglobin > 0),
    cholesterol   REAL NOT NULL CHECK (cholesterol > 0),
    remarks       TEXT,                          -- NULL until the AI service returns a result
    ai_error      TEXT,                          -- why remarks are missing, if they are
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# A record is a possible duplicate when another record has the same name,
# date of birth and email. A matching name alone is not enough.
LIST_SQL = """
SELECT p.*,
       (SELECT COUNT(*) FROM patients d
         WHERE d.id != p.id
           AND lower(d.full_name) = lower(p.full_name)
           AND d.date_of_birth = p.date_of_birth
           AND lower(d.email) = lower(p.email)) AS duplicate_count
  FROM patients p
 ORDER BY p.id
"""


@contextmanager
def connect(db_path):
    """Open a connection, commit on success, roll back on any error, always close."""
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db(db_path):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as connection:
        connection.executescript(SCHEMA)


def _values(data):
    return (
        data["full_name"],
        data["date_of_birth"].isoformat(),
        data["email"],
        data["glucose"],
        data["haemoglobin"],
        data["cholesterol"],
    )


def add_patient(db_path, data):
    with connect(db_path) as connection:
        cursor = connection.execute(
            "INSERT INTO patients (full_name, date_of_birth, email, glucose, haemoglobin, cholesterol)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            _values(data),
        )
        return cursor.lastrowid


def list_patients(db_path):
    with connect(db_path) as connection:
        return connection.execute(LIST_SQL).fetchall()


def get_patient(db_path, patient_id):
    with connect(db_path) as connection:
        return connection.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()


def find_duplicate_ids(db_path, data):
    with connect(db_path) as connection:
        rows = connection.execute(
            "SELECT id FROM patients"
            " WHERE lower(full_name) = lower(?) AND date_of_birth = ? AND lower(email) = lower(?)"
            " ORDER BY id",
            (data["full_name"], data["date_of_birth"].isoformat(), data["email"]),
        ).fetchall()
        return [row["id"] for row in rows]


def update_patient(db_path, patient_id, data):
    with connect(db_path) as connection:
        cursor = connection.execute(
            "UPDATE patients SET full_name = ?, date_of_birth = ?, email = ?, glucose = ?,"
            " haemoglobin = ?, cholesterol = ?, updated_at = datetime('now') WHERE id = ?",
            _values(data) + (patient_id,),
        )
        return cursor.rowcount > 0


def set_remarks(db_path, patient_id, remarks, ai_error):
    with connect(db_path) as connection:
        connection.execute(
            "UPDATE patients SET remarks = ?, ai_error = ?, updated_at = datetime('now') WHERE id = ?",
            (remarks, ai_error, patient_id),
        )


def delete_patient(db_path, patient_id):
    with connect(db_path) as connection:
        cursor = connection.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
        return cursor.rowcount > 0
