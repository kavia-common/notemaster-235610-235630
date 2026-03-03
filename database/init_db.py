#!/usr/bin/env python3
"""Initialize SQLite database for the notes application.

This script creates a notes-focused schema that supports:
- Notes CRUD
- Optional tags (many-to-many relationship)
- Indexes for fast tag filtering
- Full-text search via FTS5 when available (with a safe fallback when not)

It also writes connection helper files:
- db_connection.txt
- db_visualizer/sqlite.env
"""

import os
import sqlite3
from typing import Optional

DB_NAME = "myapp.db"

print("Starting SQLite setup (notes schema)...")

# Check if database already exists
db_exists = os.path.exists(DB_NAME)
if db_exists:
    print(f"SQLite database already exists at {DB_NAME}")
    # Verify it's accessible
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.execute("SELECT 1")
        conn.close()
        print("Database is accessible and working.")
    except Exception as e:
        print(f"Warning: Database exists but may be corrupted: {e}")
else:
    print("Creating new SQLite database...")

conn = sqlite3.connect(DB_NAME)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Enable foreign keys and set pragmatic defaults
cursor.execute("PRAGMA foreign_keys = ON")
cursor.execute("PRAGMA journal_mode = WAL")
cursor.execute("PRAGMA synchronous = NORMAL")

# --- Schema: notes + optional tags ---

# Core notes table
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS notes (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )
"""
)

# Tags: unique name, optional color
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS tags (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        color TEXT,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )
"""
)

# Many-to-many join table
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS note_tags (
        note_id TEXT NOT NULL,
        tag_id TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        PRIMARY KEY (note_id, tag_id),
        FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE,
        FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
    )
"""
)

# Helpful indexes for filtering/sorting
cursor.execute("CREATE INDEX IF NOT EXISTS idx_notes_created_at ON notes(created_at)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_notes_updated_at ON notes(updated_at)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_note_tags_note_id ON note_tags(note_id)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_note_tags_tag_id ON note_tags(tag_id)")

# --- Full-text search (optional via FTS5) ---
# We try to create an FTS5 virtual table and keep it synchronized with triggers.
# If the SQLite build doesn't include FTS5, we continue without it.
fts_enabled = False
try:
    cursor.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts
        USING fts5(
            note_id UNINDEXED,
            title,
            content,
            tokenize = 'unicode61'
        )
    """
    )

    # Initial backfill to ensure existing notes are searchable
    cursor.execute(
        """
        INSERT INTO notes_fts(note_id, title, content)
        SELECT id, title, content
        FROM notes
        WHERE id NOT IN (SELECT note_id FROM notes_fts)
    """
    )

    # Triggers to keep FTS in sync
    cursor.execute(
        """
        CREATE TRIGGER IF NOT EXISTS notes_ai
        AFTER INSERT ON notes
        BEGIN
            INSERT INTO notes_fts(note_id, title, content)
            VALUES (new.id, new.title, new.content);
        END;
    """
    )
    cursor.execute(
        """
        CREATE TRIGGER IF NOT EXISTS notes_au
        AFTER UPDATE ON notes
        BEGIN
            UPDATE notes_fts
            SET title = new.title, content = new.content
            WHERE note_id = new.id;
        END;
    """
    )
    cursor.execute(
        """
        CREATE TRIGGER IF NOT EXISTS notes_ad
        AFTER DELETE ON notes
        BEGIN
            DELETE FROM notes_fts WHERE note_id = old.id;
        END;
    """
    )
    fts_enabled = True
    print("✓ FTS5 enabled: notes_fts virtual table created.")
except sqlite3.OperationalError as e:
    # FTS5 may not be compiled in; treat as optional.
    print(f"ℹ FTS5 not available; continuing without FTS search. Details: {e}")

# --- Minimal meta table for diagnostics (kept small and relevant) ---
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS app_info (
        key TEXT PRIMARY KEY,
        value TEXT,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )
"""
)
cursor.execute(
    "INSERT OR REPLACE INTO app_info (key, value) VALUES (?, ?)",
    ("project_name", "notemaster (notes app)"),
)
cursor.execute(
    "INSERT OR REPLACE INTO app_info (key, value) VALUES (?, ?)",
    ("schema_version", "1"),
)
cursor.execute(
    "INSERT OR REPLACE INTO app_info (key, value) VALUES (?, ?)",
    ("fts_enabled", "true" if fts_enabled else "false"),
)

# --- Seed data (idempotent) ---
# Seed a few tags and notes; uses deterministic IDs so re-running is safe.
seed_tags = [
    ("tag-inbox", "inbox", "#60A5FA"),
    ("tag-work", "work", "#34D399"),
    ("tag-personal", "personal", "#F472B6"),
]
for tag_id, name, color in seed_tags:
    cursor.execute(
        """
        INSERT OR IGNORE INTO tags (id, name, color)
        VALUES (?, ?, ?)
        """,
        (tag_id, name, color),
    )

seed_notes = [
    (
        "note-welcome",
        "Welcome to Notemaster",
        "This is your first note. Try editing, tagging, and searching!",
    ),
    (
        "note-shortcuts",
        "Retro tips",
        "Use search to quickly find notes. Tags help you filter.",
    ),
]
for note_id, title, content in seed_notes:
    cursor.execute(
        """
        INSERT OR IGNORE INTO notes (id, title, content)
        VALUES (?, ?, ?)
        """,
        (note_id, title, content),
    )
    # Ensure updated_at reflects any changes if the seed content changes over time
    cursor.execute(
        """
        UPDATE notes
        SET title = ?, content = ?, updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        WHERE id = ?
        """,
        (title, content, note_id),
    )

# Seed note-tag relationships
seed_note_tags = [
    ("note-welcome", "tag-inbox"),
    ("note-shortcuts", "tag-personal"),
]
for note_id, tag_id in seed_note_tags:
    cursor.execute(
        """
        INSERT OR IGNORE INTO note_tags (note_id, tag_id)
        VALUES (?, ?)
        """,
        (note_id, tag_id),
    )

conn.commit()

# Update FTS rows for seeded content (if enabled)
if fts_enabled:
    cursor.execute(
        """
        INSERT INTO notes_fts(note_id, title, content)
        SELECT id, title, content FROM notes
        WHERE id NOT IN (SELECT note_id FROM notes_fts)
    """
    )
    cursor.execute(
        """
        UPDATE notes_fts
        SET title = (SELECT title FROM notes WHERE notes.id = notes_fts.note_id),
            content = (SELECT content FROM notes WHERE notes.id = notes_fts.note_id)
        WHERE note_id IN (SELECT id FROM notes)
    """
    )
    conn.commit()

# Stats
cursor.execute(
    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
)
table_count = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM notes")
notes_count = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM tags")
tags_count = cursor.fetchone()[0]

conn.close()

# Save connection information to a file
current_dir = os.getcwd()
connection_string = f"sqlite:///{current_dir}/{DB_NAME}"

try:
    with open("db_connection.txt", "w", encoding="utf-8") as f:
        f.write("# SQLite connection methods:\n")
        f.write(f"# Python: sqlite3.connect('{DB_NAME}')\n")
        f.write(f"# Connection string: {connection_string}\n")
        f.write(f"# File path: {current_dir}/{DB_NAME}\n")
    print("✓ Connection information saved to db_connection.txt")
except Exception as e:
    print(f"Warning: Could not save connection info: {e}")

# Create environment variables file for Node.js viewer
db_path = os.path.abspath(DB_NAME)
if not os.path.exists("db_visualizer"):
    os.makedirs("db_visualizer", exist_ok=True)
    print("Created db_visualizer directory")

try:
    with open("db_visualizer/sqlite.env", "w", encoding="utf-8") as f:
        f.write(f'export SQLITE_DB="{db_path}"\n')
    print("✓ Environment variables saved to db_visualizer/sqlite.env")
except Exception as e:
    print(f"Warning: Could not save environment variables: {e}")

print("\nSQLite setup complete!")
print(f"Database: {DB_NAME}")
print(f"Location: {current_dir}/{DB_NAME}")
print("")
print("Database statistics:")
print(f"  Tables: {table_count}")
print(f"  Notes: {notes_count}")
print(f"  Tags: {tags_count}")
print(f"  FTS enabled: {'yes' if fts_enabled else 'no'}")

# If sqlite3 CLI is available, show how to use it
try:
    import subprocess

    result = subprocess.run(["which", "sqlite3"], capture_output=True, text=True)
    if result.returncode == 0:
        print("")
        print("SQLite CLI is available. You can also use:")
        print(f"  sqlite3 {DB_NAME}")
except Exception:
    pass

print("\nScript completed successfully.")
