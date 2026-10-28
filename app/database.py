#Connection of the database in API
import os, psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb
from datetime import timedelta
from contextlib import contextmanager
from uuid import uuid4
from app.grouping import get_or_create_session

load_dotenv()

host = os.getenv("POSTGRES_HOST")
port = os.getenv("POSTGRES_PORT")
dbname = os.getenv("POSTGRES_DB")
user = os.getenv("POSTGRES_USER")
password = os.getenv("POSTGRES_PASSWORD")

#Conection in database
def get_connection():
    return psycopg.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password
    )

#Save the message into database
def save_message(message_id, sender, sent_at, message_type, text_body, payload):

    sql = """INSERT INTO agrozap_messages (message_id, sender, sent_at, message_type, text_body, payload)
                VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (message_id) DO NOTHING
                RETURNING message_id"""

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (message_id, sender, sent_at, message_type, text_body, Jsonb(payload)))
            row = cursor.fetchone()

            if row is None:
                return

            session_id = get_or_create_session(conn, sender, sent_at)

            cursor.execute("""UPDATE agrozap_messages
                            SET session_id = %s
                            WHERE message_id = %s
                            """, (session_id, message_id))

#Save the message and audio into database
def save_audio_message(message_id, sender, sent_at, media_id, mime_type, payload):

    sql_messages = """INSERT INTO agrozap_messages (message_id, sender, sent_at, message_type, text_body, payload)
                        VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (message_id) DO NOTHING
                        RETURNING message_id"""

    sql_media = """INSERT INTO agrozap_message_audio (message_id, media_id, mime_type)
                    VALUES (%s, %s, %s) ON CONFLICT (message_id) DO NOTHING"""

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql_messages, (message_id, sender, sent_at, "audio", None, Jsonb(payload)))
            row = cursor.fetchone()

            if row is None:
                return

            session_id = get_or_create_session(conn, sender, sent_at)

            cursor.execute("""UPDATE agrozap_messages
                            SET session_id = %s
                            WHERE message_id = %s
                            """, (session_id, message_id))
            
            cursor.execute(sql_media, (message_id, media_id, mime_type))

def save_image_message(message_id, sender, sent_at, media_id, mime_type, caption, payload):

    sql_messages = """INSERT INTO agrozap_messages (message_id, sender, sent_at, message_type, text_body, payload)
                        VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (message_id) DO NOTHING
                        RETURNING message_id"""

    sql_media = """INSERT INTO agrozap_message_images (message_id, media_id, mime_type)
                    VALUES (%s, %s, %s) ON CONFLICT (message_id) DO NOTHING"""

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql_messages, (message_id, sender, sent_at, 'image', caption, Jsonb(payload)))
            row = cursor.fetchone()

            if row is None:
                return

            session_id = get_or_create_session(conn, sender, sent_at)

            cursor.execute("""UPDATE agrozap_messages
                            SET session_id = %s
                            WHERE message_id = %s
                            """, (session_id, message_id))

            cursor.execute(sql_media, (message_id, media_id, mime_type))

def save_location_message(message_id, sender, sent_at, latitude, longitude, name, address, payload):

    sql_messages = """INSERT INTO agrozap_messages (message_id, sender, sent_at, message_type, text_body, payload)
                        VALUES (%s, %s, %s, %s , %s, %s) ON CONFLICT (message_id) DO NOTHING
                        RETURNING message_id"""

    sql_location = """INSERT INTO agrozap_message_locations (message_id, latitude, longitude, name, address)
                        VALUES (%s, %s, %s, %s, %s) ON CONFLICT (message_id) DO NOTHING"""

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql_messages, (message_id, sender, sent_at, 'location', None, Jsonb(payload)))
            row = cursor.fetchone()

            if row is None:
                return

            session_id = get_or_create_session(conn, sender, sent_at)
            
            cursor.execute("""UPDATE agrozap_messages
                            SET session_id = %s
                            WHERE message_id = %s
                            """, (session_id, message_id))

            cursor.execute(sql_location, (message_id, latitude, longitude, name, address))

def save_session_report(conn, session_id, report_html, report_pdf, source_manifest, template_version):

    sql_status = """SELECT status
            FROM agrozap_field_sessions
            WHERE id = %s
            FOR UPDATE
            """

    sql_report = """SELECT id, version, template_version, source_manifest
                    FROM agrozap_session_reports
                    WHERE session_id = %s
                    ORDER BY version DESC
                    LIMIT 1
                    """
    
    sql_vesion = """SELECT COALESCE (MAX(version), 0) + 1
                    FROM agrozap_session_reports
                    WHERE session_id = %s
                    """

    sql = """ INSERT INTO agrozap_session_reports (session_id, version, template_version, html_content, pdf_data, source_manifest)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, version
            """
    
    with conn.cursor() as cursor:
        cursor.execute(sql_status, (session_id,))
        row = cursor.fetchone()

        if row is None:
            raise ValueError("Registro da sessão não encotrado")

        if row[0] != 'closed':
            raise ValueError("Sessão ainda não foi fechada")

        cursor.execute(sql_report, (session_id,))
        row = cursor.fetchone()

        if row and row[2] == template_version and row[3] == source_manifest:
            return row[0], row[1]

        cursor.execute(sql_vesion, (session_id,))
        row = cursor.fetchone()
        next_version = row[0]

        cursor.execute(sql, (session_id, next_version, template_version, report_html, report_pdf, Jsonb(source_manifest)))
        row = cursor.fetchone()

    return row
        

def mark_image_downloaded(message_id, image_data, claim_token):

    sql = """UPDATE agrozap_message_images 
            SET image_converted = %s, 
                download_status = 'downloaded', 
                download_next_retry_at = NULL, 
                download_claim_token = NULL
            WHERE message_id = %s AND download_status = 'downloading' AND download_claim_token = %s
            RETURNING message_id
            """

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (image_data, message_id, claim_token))
            row = cursor.fetchone()
            
    return row is not None 

def mark_image_error(message_id, retry_delay_seconds, claim_token):

    sql = """UPDATE agrozap_message_images
            SET download_status = 'error', 
                download_next_retry_at = CURRENT_TIMESTAMP + %s, 
                download_claim_token = NULL
            WHERE message_id = %s AND download_status = 'downloading' AND download_claim_token = %s
            RETURNING message_id
            """

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (timedelta(seconds=retry_delay_seconds), message_id, claim_token))
            row = cursor.fetchone()
    
    return row is not None

#If the audio is downloaded, this function will be executed
def mark_audio_downloaded(message_id, audio_data, claim_token):

    sql = """UPDATE agrozap_message_audio
            SET audio_data = %s, 
                download_status = 'downloaded', 
                download_next_retry_at = NULL,
                download_claim_token = NULL
            WHERE message_id = %s AND download_status = 'downloading' AND download_claim_token = %s
            RETURNING message_id 
            """

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (audio_data, message_id, claim_token))
            row = cursor.fetchone()
            
    return row is not None

#If the download fails, `download_status` will change to 'error'.
def mark_audio_error(message_id, retry_delay_seconds, claim_token):

    sql = """UPDATE agrozap_message_audio
            SET download_status = 'error', 
                download_next_retry_at = CURRENT_TIMESTAMP + %s, 
                download_claim_token = NULL
            WHERE message_id = %s 
                AND download_status = 'downloading' 
                AND download_claim_token = %s
            RETURNING message_id
            """

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (timedelta(seconds=retry_delay_seconds), message_id, claim_token))
            row = cursor.fetchone()
            
    return row is not None

def get_image_download_status(message_id):

    sql = """SELECT download_status
            FROM agrozap_message_images
            WHERE message_id = %s
            """

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (message_id,))
            row = cursor.fetchone()

    if row is None:
        return None

    return row[0]
    

#Check the status of file. It could be: 'downloaded', 'pending' or 'error' 
def get_audio_download_status(message_id):

    sql = """SELECT download_status
            FROM agrozap_message_audio
            WHERE message_id = %s
            """

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (message_id,))
            row = cursor.fetchone()

    if row is None:
        return None
    
    return row[0]

def get_audio_data(message_id):

    sql = """SELECT audio_data, mime_type
            FROM agrozap_message_audio
            WHERE message_id = %s 
            """

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (message_id,))
            row = cursor.fetchone()

    if row is None:
        return None

    return row

#This function prevents a single message from being executed twice.
#The download only starts after this function return True
def claim_audio_download(message_id, max_attempts):

    sql = """UPDATE agrozap_message_audio
            SET download_status = 'downloading', 
                download_started_at = CURRENT_TIMESTAMP, 
                download_attempts = download_attempts + 1,
                download_claim_token = %s
            WHERE message_id = %s 
                AND download_status IN ('pending', 'error') 
                AND download_attempts < %s 
                AND (download_next_retry_at IS NULL OR download_next_retry_at <= CURRENT_TIMESTAMP)
            RETURNING download_claim_token
            """
    claim_token = uuid4()
    
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (claim_token, message_id, max_attempts)) 
            row = cursor.fetchone()

            if row is None:
                return None
    
    return row[0]


#This function updates the database to record the audio transcribed into text.
def mark_transcription_completed(message_id, text, claim_token):

    sql = """UPDATE agrozap_message_audio
            SET transcription_text = %s, 
                transcription_status = 'completed',
                transcription_claim_token = NULL,
                transcription_next_retry_at = NULL
            WHERE message_id = %s
                AND transcription_status = 'processing'
                AND transcription_claim_token = %s
            RETURNING message_id
            """

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (text, message_id, claim_token))
            row = cursor.fetchone()
            
    return row is not None

def mark_transcription_error(message_id, retry_delay_seconds, claim_token):

    sql = """UPDATE agrozap_message_audio
            SET transcription_status = 'error',
                transcription_claim_token = NULL,
                transcription_next_retry_at = CURRENT_TIMESTAMP + %s
            WHERE message_id = %s 
                AND transcription_status = 'processing'
                AND transcription_claim_token = %s
            RETURNING message_id
            """
    
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (timedelta(seconds=retry_delay_seconds), message_id, claim_token))
            row = cursor.fetchone()
            
    return row is not None

#This function prevents a single message from being executed twice.
def claim_transcription(message_id, max_attempts):

    sql = """UPDATE agrozap_message_audio
            SET transcription_status = 'processing', 
                transcription_started_at = CURRENT_TIMESTAMP,
                transcription_attempts = transcription_attempts + 1,
                transcription_claim_token = %s
            WHERE message_id = %s 
                AND transcription_status IN ('pending', 'error') 
                AND download_status = 'downloaded'
                AND transcription_attempts < %s
                AND (transcription_next_retry_at IS NULL OR transcription_next_retry_at <= CURRENT_TIMESTAMP)
            RETURNING transcription_claim_token
            """
    claim_token = uuid4()

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (claim_token, message_id, max_attempts))
            row = cursor.fetchone()
            
            if row is None:
                return None

    return row[0]

def claim_image_download(message_id, max_attempts):

    sql = """UPDATE agrozap_message_images
            SET download_status = 'downloading', 
                download_started_at = CURRENT_TIMESTAMP, 
                download_attempts = download_attempts + 1,
                download_claim_token = %s
            WHERE message_id = %s 
                AND download_status IN ('pending', 'error') 
                AND download_attempts < %s 
                AND (download_next_retry_at IS NULL OR download_next_retry_at <= CURRENT_TIMESTAMP)
            RETURNING download_claim_token
            """
    claim_token = uuid4()

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (claim_token, message_id, max_attempts))
            row = cursor.fetchone()
            
            if row is None:
                return None

    return row[0] 

#Recording of the interpretation of the text
def start_interpretation(message_id, source_text, model_name, prompt_version, schema_version, max_attempts, retry_delay_seconds):

    sql_lock = """SELECT message_id
                    FROM agrozap_messages
                    WHERE message_id = %s
                    FOR UPDATE
                    """
    sql_select = """SELECT message_id
                    FROM agrozap_message_interpretations
                    WHERE message_id = %s
                        AND source_text = %s
                        AND model_name = %s
                        AND prompt_version = %s
                        AND schema_version = %s
                        AND status IN ('processing','completed')
                    LIMIT 1
                    """

    sql = """INSERT INTO agrozap_message_interpretations (message_id, source_text, model_name, prompt_version, schema_version)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """
            
    sql_history = """SELECT COUNT(*), COALESCE(MAX(COALESCE(finished_at, started_at)) + %s > CURRENT_TIMESTAMP, FALSE)
                    FROM agrozap_message_interpretations
                    WHERE message_id = %s
                        AND source_text = %s 
                        AND model_name = %s
                        AND prompt_version = %s
                        AND schema_version = %s
                    """
    
    interpretation_params = (
        message_id,
        source_text,
        model_name,
        prompt_version,
        schema_version,
    )

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql_lock, (message_id,))
            message_row = cursor.fetchone()
            if message_row is None:
                raise ValueError("A mensagem não existe")

            cursor.execute(sql_select, interpretation_params)
            message_interpretation_row = cursor.fetchone()

            if message_interpretation_row is not None:
                return None
            
            cursor.execute(sql_history, (timedelta(seconds=retry_delay_seconds), *interpretation_params))
            attempts, must_wait = cursor.fetchone()
            
            if attempts >= max_attempts or must_wait:
                return None
                
            cursor.execute(sql, interpretation_params)
            row = cursor.fetchone()

    return row[0]

#Marks the interpretation as complete
def mark_interpretation_completed(interpretation_id, result):

    sql = """UPDATE agrozap_message_interpretations 
            SET result = %s, status = 'completed', finished_at = CURRENT_TIMESTAMP, error_message = NULL
            WHERE id = %s AND status = 'processing'
            RETURNING id 
            """

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (Jsonb(result), interpretation_id))
            row = cursor.fetchone()

    return row is not None

#Marks the interpretation as an error
def mark_interpretation_error(interpretation_id, error_message):

    sql = """UPDATE agrozap_message_interpretations
            SET status = 'error', error_message = %s, finished_at = CURRENT_TIMESTAMP, result = NULL
            WHERE id = %s AND status = 'processing'
            RETURNING id
            """

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (error_message, interpretation_id))
            row = cursor.fetchone()

    return row is not None

def get_sessions_without_report():

    sql = """SELECT afs.id
            FROM agrozap_field_sessions afs
            WHERE status = 'closed' AND NOT EXISTS (
                SELECT 1
                FROM agrozap_session_reports asr
                WHERE asr.session_id = afs.id
                )
            ORDER BY last_message_at, id
            """

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            rows = cursor.fetchall()

    return [row[0] for row in rows]

def get_retryable_image_downloads(max_attempts):

    sql = """SELECT message_id, media_id, mime_type
            FROM agrozap_message_images
            WHERE download_status IN ('pending','error') 
                AND download_attempts < %s
                AND (download_next_retry_at IS NULL OR download_next_retry_at <= CURRENT_TIMESTAMP)
            ORDER BY message_id
            """

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (max_attempts,))
            rows = cursor.fetchall()

    return rows

def get_retryable_audio_downloads(max_attempts):

    sql = """SELECT message_id, media_id, mime_type
            FROM agrozap_message_audio
            WHERE download_status IN ('pending','error') 
                AND download_attempts < %s
                AND (download_next_retry_at IS NULL OR download_next_retry_at <= CURRENT_TIMESTAMP)
            ORDER BY message_id
            """
    
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (max_attempts,))
            rows = cursor.fetchall()
    
    return rows

@contextmanager
def download_task_lock(message_id):
    
    text_key = f"agrozap:download:{message_id}"
    
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_xact_lock(hashtextextended(%s, 0))", (text_key,))
            acquired = cursor.fetchone()[0]
            
        yield acquired
        
def get_stale_image_downloads(stale_after_seconds):

    sql = """SELECT message_id, download_claim_token, download_started_at
            FROM agrozap_message_images
            WHERE download_status = 'downloading' 
                AND (download_started_at IS NULL OR download_started_at <= CURRENT_TIMESTAMP - %s)
            ORDER BY download_started_at NULLS FIRST, message_id
            """
            
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (timedelta(seconds=stale_after_seconds),))
            row = cursor.fetchall()
            
    return row


def get_stale_audio_downloads(stale_after_seconds):  
     
    sql = """SELECT message_id, download_claim_token, download_started_at
            FROM agrozap_message_audio
            WHERE download_status = 'downloading' 
                AND (download_started_at IS NULL OR download_started_at <= CURRENT_TIMESTAMP - %s)
            ORDER BY download_started_at NULLS FIRST, message_id
            """
            
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (timedelta(seconds=stale_after_seconds),))
            rows = cursor.fetchall()
            
    return rows

def release_stale_image_download(message_id, expected_token, expected_started_at, stale_after_seconds, retry_delay_seconds):
    
    with download_task_lock(message_id) as acquire:
        if not acquire:
            return False
    
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""UPDATE agrozap_message_images
                                SET download_status = 'error', 
                                    download_claim_token = NULL, 
                                    download_next_retry_at = CURRENT_TIMESTAMP + %s
                                WHERE message_id = %s 
                                    AND download_status = 'downloading'
                                    AND download_claim_token IS NOT DISTINCT FROM %s
                                    AND download_started_at IS NOT DISTINCT FROM %s
                                    AND (download_started_at IS NULL OR download_started_at <= CURRENT_TIMESTAMP - %s)
                                    RETURNING message_id
                                """, (timedelta(seconds=retry_delay_seconds), 
                                        message_id, 
                                        expected_token, 
                                        expected_started_at, 
                                        timedelta(seconds=stale_after_seconds)))
                row = cursor.fetchone()
            
    return row is not None

def release_stale_audio_download(message_id, expected_token, expected_started_at, stale_after_seconds, retry_delay_seconds):
    
    with download_task_lock(message_id) as acquire:
        if not acquire:
            return False
        
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""UPDATE agrozap_message_audio
                                SET download_status = 'error', 
                                    download_claim_token = NULL, 
                                    download_next_retry_at = CURRENT_TIMESTAMP + %s
                                WHERE message_id = %s 
                                    AND download_status = 'downloading'
                                    AND download_claim_token IS NOT DISTINCT FROM %s
                                    AND download_started_at IS NOT DISTINCT FROM %s
                                    AND (download_started_at IS NULL OR download_started_at <= CURRENT_TIMESTAMP - %s)
                                    RETURNING message_id
                               """, (timedelta(seconds=retry_delay_seconds), 
                                        message_id, 
                                        expected_token, 
                                        expected_started_at, 
                                        timedelta(seconds=stale_after_seconds)))
                row = cursor.fetchone()
                
    return row is not None

@contextmanager
def transcription_task_lock(message_id):
    
    text_key = f"agrozap:transcription:{message_id}"
        
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_xact_lock(hashtextextended(%s, 0))", (text_key,))
            acquired = cursor.fetchone()[0]
                
        yield acquired
        
def get_retryable_transcriptions(max_attempts):
    
    sql = """SELECT message_id
            FROM agrozap_message_audio
            WHERE download_status = 'downloaded'
                AND transcription_status IN ('pending', 'error')
                AND transcription_attempts < %s
                AND (transcription_next_retry_at IS NULL OR transcription_next_retry_at <= CURRENT_TIMESTAMP)
            ORDER BY message_id
            """
            
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (max_attempts,))
            rows = cursor.fetchall()
            
    return [row[0] for row in rows] 

def get_stale_transcriptions(stale_after_seconds):
    
    sql = """SELECT message_id, transcription_claim_token, transcription_started_at
            FROM agrozap_message_audio
            WHERE transcription_status = 'processing'
                AND (transcription_started_at IS NULL OR transcription_started_at <= CURRENT_TIMESTAMP - %s)
            ORDER BY transcription_started_at NULLS FIRST, message_id
            """
            
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (timedelta(seconds=stale_after_seconds),))
            rows = cursor.fetchall()
            
    return rows

def release_stale_transcription(message_id, expected_token, expected_started_at, stale_after_seconds, retry_delay_seconds):
    
    with transcription_task_lock(message_id) as acquired:
        if not acquired:
            return False
        
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""UPDATE agrozap_message_audio
                                SET transcription_status = 'error',
                                    transcription_claim_token = NULL,
                                    transcription_next_retry_at = CURRENT_TIMESTAMP + %s
                                WHERE message_id = %s
                                    AND transcription_status = 'processing'
                                    AND transcription_claim_token IS NOT DISTINCT FROM %s
                                    AND transcription_started_at IS NOT DISTINCT FROM %s
                                    AND (transcription_started_at IS NULL OR transcription_started_at <= CURRENT_TIMESTAMP - %s)
                                RETURNING message_id
                                """, (timedelta(seconds=retry_delay_seconds),
                                      message_id,
                                      expected_token,
                                      expected_started_at,
                                      timedelta(seconds=stale_after_seconds)))
                row = cursor.fetchone()
                
    return row is not None

@contextmanager
def interpretation_task_lock(message_id):
    
    text_key = f"agrozap:interpretation:{message_id}"
    
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_xact_lock(hashtextextended(%s, 0))", (text_key,))
            acquired = cursor.fetchone()[0]
                    
        yield acquired
        
def get_stale_interpretations(stale_after_seconds):
    
    sql = """SELECT id, message_id, started_at
            FROM agrozap_message_interpretations
            WHERE status = 'processing'
                AND (started_at IS NULL OR started_at <= CURRENT_TIMESTAMP - %s)
            ORDER BY started_at NULLS FIRST, id
            """
    
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (timedelta(seconds=stale_after_seconds),))
            rows = cursor.fetchall()
            
    return rows
            
            
def release_stale_interpretation(interpretation_id, message_id, expected_started_at, stale_after_seconds):
    
    with interpretation_task_lock(message_id) as acquire:
        if not acquire:
            return False
        
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""UPDATE agrozap_message_interpretations
                                SET status = 'error',
                                    error_message = 'Tentativa interrompida; reserva abandonada recuperada',
                                    finished_at = CURRENT_TIMESTAMP,
                                    result = NULL
                                WHERE id = %s
                                    AND message_id = %s
                                    AND status = 'processing'
                                    AND started_at IS NOT DISTINCT FROM %s
                                    AND (started_at IS NULL OR started_at <= CURRENT_TIMESTAMP - %s)
                                RETURNING id
                               """, (interpretation_id, message_id, expected_started_at, timedelta(seconds=stale_after_seconds)))
                row = cursor.fetchone()
                
    return row is not None

def get_retryable_interpretations(model_name, prompt_version, schema_version, max_attempts, retry_delay_seconds):
    
    sql = """SELECT am.message_id, am.text_body 
            FROM agrozap_messages am 
            WHERE am.message_type = 'text'
            UNION ALL
            SELECT ama.message_id, ama.transcription_text 
            FROM agrozap_message_audio ama
            INNER JOIN agrozap_messages am ON ama.message_id = am.message_id
            WHERE am.message_type = 'audio'
                AND ama.download_status = 'downloaded'
                AND ama.transcription_status = 'completed'
            ORDER BY message_id
            """
    sql_history = """SELECT COUNT(*), 
                        COALESCE(BOOL_OR(status IN ('processing', 'completed')), FALSE),
                        COALESCE(MAX(COALESCE(finished_at, started_at)) + %s > CURRENT_TIMESTAMP, FALSE) 
                    FROM agrozap_message_interpretations
                    WHERE message_id = %s
                        AND source_text = %s
                        AND model_name = %s
                        AND prompt_version = %s
                        AND schema_version = %s
                    """
                    
    retryable_interpretations = []
            
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            rows = cursor.fetchall()
            
            for message_id, source_text in rows:
                
                if not isinstance(source_text, str):
                   continue
                
                source_text = source_text.strip()
                
                if not source_text:
                    continue
                
                cursor.execute(sql_history, (timedelta(seconds=retry_delay_seconds),
                                             message_id,
                                             source_text,
                                             model_name,
                                             prompt_version,
                                             schema_version))
                
                attempts, has_active_or_completed, must_wait = (
                    cursor.fetchone()
                )
                
                if attempts >= max_attempts:
                    continue
                
                if has_active_or_completed or must_wait:
                    continue
                
                retryable_interpretations.append((message_id, source_text))
                
    return retryable_interpretations
                
                                    