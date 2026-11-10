-- Conversations that start from a digest item and wander through the article store.

ALTER TABLE evidence_versions
    ADD COLUMN IF NOT EXISTS search_vector tsvector
    GENERATED ALWAYS AS (to_tsvector('english', left(coalesce(raw_content, ''), 40000))) STORED;

CREATE INDEX IF NOT EXISTS evidence_versions_search_idx ON evidence_versions USING GIN (search_vector);

CREATE TABLE IF NOT EXISTS riff_threads (
    thread_id TEXT PRIMARY KEY,
    digest_id TEXT REFERENCES digests(digest_id) ON DELETE SET NULL,
    kind TEXT NOT NULL CHECK (kind IN ('collision', 'idea', 'theme', 'free')),
    title TEXT NOT NULL,
    seed JSONB NOT NULL DEFAULT '{}'::jsonb,
    shelf JSONB NOT NULL DEFAULT '{}'::jsonb,
    sketch TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS riff_messages (
    message_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES riff_threads(thread_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('you', 'riff')),
    content TEXT NOT NULL,
    sources JSONB NOT NULL DEFAULT '[]'::jsonb,
    tangents JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS riff_messages_thread_idx ON riff_messages (thread_id, message_id);
CREATE INDEX IF NOT EXISTS riff_threads_updated_idx ON riff_threads (updated_at DESC);
