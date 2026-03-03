# Notes SQLite Schema (Notemaster)

This SQLite database is designed for a notes app with optional tags and fast searching.

## Tables

### `notes`
- `id` (TEXT, PK)
- `title` (TEXT, not null)
- `content` (TEXT, not null)
- `created_at` (TEXT, ISO-ish UTC string)
- `updated_at` (TEXT, ISO-ish UTC string)

Indexes:
- `idx_notes_created_at`
- `idx_notes_updated_at`

### `tags`
- `id` (TEXT, PK)
- `name` (TEXT, not null, UNIQUE)
- `color` (TEXT, optional)
- `created_at` (TEXT)

Indexes:
- `idx_tags_name`

### `note_tags` (join table)
- `note_id` (TEXT, FK -> notes.id, ON DELETE CASCADE)
- `tag_id` (TEXT, FK -> tags.id, ON DELETE CASCADE)
- `created_at` (TEXT)
- PRIMARY KEY (`note_id`, `tag_id`)

Indexes:
- `idx_note_tags_note_id`
- `idx_note_tags_tag_id`

### `notes_fts` (optional, if SQLite has FTS5)
FTS5 virtual table used for full-text search:
- `note_id` (UNINDEXED)
- `title`
- `content`

Sync triggers:
- `notes_ai` (after insert)
- `notes_au` (after update)
- `notes_ad` (after delete)

## Common queries

### List notes with tags
```sql
SELECT
  n.id, n.title, n.content, n.created_at, n.updated_at,
  GROUP_CONCAT(t.name, ',') AS tags
FROM notes n
LEFT JOIN note_tags nt ON nt.note_id = n.id
LEFT JOIN tags t ON t.id = nt.tag_id
GROUP BY n.id
ORDER BY n.updated_at DESC;
```

### Filter notes by a tag name
```sql
SELECT n.*
FROM notes n
JOIN note_tags nt ON nt.note_id = n.id
JOIN tags t ON t.id = nt.tag_id
WHERE t.name = 'work'
ORDER BY n.updated_at DESC;
```

### Search notes (FTS5)
If `notes_fts` exists:
```sql
SELECT n.*
FROM notes n
JOIN notes_fts f ON f.note_id = n.id
WHERE notes_fts MATCH 'retro* OR search'
ORDER BY n.updated_at DESC;
```

If `notes_fts` does not exist (fallback):
```sql
SELECT *
FROM notes
WHERE title LIKE '%retro%' OR content LIKE '%retro%'
ORDER BY updated_at DESC;
```
