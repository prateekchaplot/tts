-- Schema v1 for the local tts library database.
-- Applied once on first run; the DAL sets PRAGMA user_version = 1 afterwards.

CREATE TABLE generations (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('queued', 'running', 'cancelling', 'succeeded', 'failed', 'cancelled')
    ),
    source_type TEXT NOT NULL CHECK (source_type IN ('text', 'file')),
    input_text TEXT NOT NULL,
    input_filename TEXT,
    voice_id TEXT NOT NULL,
    voice_name TEXT NOT NULL,
    rate REAL NOT NULL,
    volume REAL NOT NULL,
    duration_seconds REAL,
    sample_rate INTEGER,
    audio_path TEXT,
    word_timings_json TEXT,
    cues_json TEXT,
    aligned_word_ratio REAL,
    error_code TEXT,
    error_message TEXT
);

CREATE INDEX idx_generations_created ON generations (created_at DESC);

CREATE TABLE app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
