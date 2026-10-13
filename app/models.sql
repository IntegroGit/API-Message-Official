-- Criação das tabelas do Agro Zap em PostgreSQL + PostGIS.

CREATE TABLE messages (
    message_id TEXT PRIMARY KEY,
    sender TEXT NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    message_type TEXT NOT NULL,
    text_body TEXT NULL,
    payload JSONB NOT NULL
);

CREATE TABLE message_audio (
    message_id TEXT PRIMARY KEY,
    media_id TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    audio_data BYTEA NULL,
    download_status TEXT NOT NULL DEFAULT 'pending' 
    CHECK(download_status IN ('pending', 'downloaded', 'downloading', 'error')),
    download_started_at TIMESTAMPTZ NULL,
    transcription_text TEXT,
    transcription_status TEXT NOT NULL DEFAULT 'pending'
    CHECK(transcription_status IN ('pending', 'processing', 'completed', 'error', 'not_applicable')),
    transcription_started_at TIMESTAMPTZ NULL,
    CONSTRAINT fk_message FOREIGN KEY (message_id)
    REFERENCES messages(message_id)
);

CREATE TABLE message_interpretations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    message_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'processing'
    CHECK(status IN ('completed','error','processing')),
    source_text TEXT NOT NULL,
    model_name TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    result JSONB,
    error_message TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMPTZ,
    CONSTRAINT fk_message FOREIGN KEY (message_id)
    REFERENCES messages(message_id)
);

CREATE TABLE message_images (
    message_id TEXT PRIMARY KEY,
    media_id TEXT NOT NULL, 
    mime_type TEXT NOT NULL,
    image_converted BYTEA NULL,
    download_status TEXT NOT NULL DEFAULT 'pending'
    CHECK(download_status IN ('pending', 'downloading', 'downloaded', 'error')),
    download_started_at TIMESTAMPTZ,
    CONSTRAINT fk_message FOREIGN KEY (message_id)
    REFERENCES messages(message_id)
);