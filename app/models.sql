-- Criação das tabelas do Agro Zap em PostgreSQL + PostGIS.

CREATE TABLE agrozap_field_sessions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sender TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    last_message_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
    CHECK (status IN ('open', 'closed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE agrozap_messages (
    message_id TEXT PRIMARY KEY,
    session_id BIGINT NULL,
    sender TEXT NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    message_type TEXT NOT NULL,
    text_body TEXT NULL,
    payload JSONB NOT NULL,
    CONSTRAINT fk_message FOREIGN KEY (session_id)
    REFERENCES agrozap_field_sessions(id)
);

CREATE TABLE agrozap_message_audio (
    message_id TEXT PRIMARY KEY,
    media_id TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    audio_data BYTEA NULL,
    download_status TEXT NOT NULL DEFAULT 'pending' 
    CHECK(download_status IN ('pending', 'downloaded', 'downloading', 'error')),
    download_attempts INTEGER NOT NULL DEFAULT 0 CHECK (download_attempts >= 0),
    download_next_retry_at TIMESTAMPTZ NULL,
    download_claim_token UUID NULL,
    download_started_at TIMESTAMPTZ NULL,
    transcription_text TEXT,
    transcription_status TEXT NOT NULL DEFAULT 'pending'
    CHECK(transcription_status IN ('pending', 'processing', 'completed', 'error', 'not_applicable')),
    transcription_attempts INTEGER NOT NULL DEFAULT 0 CHECK (transcription_attempts >= 0),
    transcription_next_retry_at TIMESTAMPTZ NULL,
    transcription_claim_token UUID NULL,
    transcription_started_at TIMESTAMPTZ NULL,
    CONSTRAINT fk_message FOREIGN KEY (message_id)
    REFERENCES agrozap_messages(message_id)
);

CREATE TABLE agrozap_message_interpretations (
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
    REFERENCES agrozap_messages(message_id)
);

CREATE TABLE agrozap_message_images (
    message_id TEXT PRIMARY KEY,
    media_id TEXT NOT NULL, 
    mime_type TEXT NOT NULL,
    image_converted BYTEA NULL,
    download_status TEXT NOT NULL DEFAULT 'pending'
    CHECK(download_status IN ('pending', 'downloading', 'downloaded', 'error')),
    download_attempts INTEGER NOT NULL DEFAULT 0 CHECK (download_attempts >= 0),
    download_next_retry_at TIMESTAMPTZ NULL,
    download_claim_token UUID NULL,
    download_started_at TIMESTAMPTZ,
    CONSTRAINT fk_message FOREIGN KEY (message_id)
    REFERENCES agrozap_messages(message_id)
);

CREATE TABLE agrozap_message_locations (
    message_id TEXT PRIMARY KEY,
    latitude DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    name TEXT NULL,
    address TEXT NULL,
    CONSTRAINT fk_message FOREIGN KEY (message_id)
    REFERENCES agrozap_messages(message_id)
);

CREATE TABLE agrozap_session_reports (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id BIGINT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    template_version TEXT NOT NULL,
    html_content TEXT NOT NULL,
    pdf_data BYTEA NOT NULL,
    source_manifest JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_session FOREIGN key (session_id)
    REFERENCES agrozap_field_sessions(id),

    UNIQUE (session_id, version)
);
