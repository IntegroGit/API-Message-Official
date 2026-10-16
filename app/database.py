#Connection of the database in API
import os, psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb
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

    sql = """INSERT INTO messages (message_id, sender, sent_at, message_type, text_body, payload)
                VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (message_id) DO NOTHING
                RETURNING message_id"""

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (message_id, sender, sent_at, message_type, text_body, Jsonb(payload)))
            row = cursor.fetchone()

            if row is None:
                return

            session_id = get_or_create_session(conn, sender, sent_at)

            cursor.execute("""UPDATE messages
                            SET session_id = %s
                            WHERE message_id = %s
                            """, (session_id, message_id))

#Save the message and audio into database
def save_audio_message(message_id, sender, sent_at, media_id, mime_type, payload):

    sql_messages = """INSERT INTO messages (message_id, sender, sent_at, message_type, text_body, payload)
                        VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (message_id) DO NOTHING
                        RETURNING message_id"""

    sql_media = """INSERT INTO message_audio (message_id, media_id, mime_type)
                    VALUES (%s, %s, %s) ON CONFLICT (message_id) DO NOTHING"""

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql_messages, (message_id, sender, sent_at, "audio", None, Jsonb(payload)))
            row = cursor.fetchone()

            if row is None:
                return

            session_id = get_or_create_session(conn, sender, sent_at)

            cursor.execute("""UPDATE messages
                            SET session_id = %s
                            WHERE message_id = %s
                            """, (session_id, message_id))
            
            cursor.execute(sql_media, (message_id, media_id, mime_type))

def save_image_message(message_id, sender, sent_at, media_id, mime_type, caption, payload):

    sql_messages = """INSERT INTO messages (message_id, sender, sent_at, message_type, text_body, payload)
                        VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (message_id) DO NOTHING
                        RETURNING message_id"""

    sql_media = """INSERT INTO message_images (message_id, media_id, mime_type)
                    VALUES (%s, %s, %s) ON CONFLICT (message_id) DO NOTHING"""

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql_messages, (message_id, sender, sent_at, 'image', caption, Jsonb(payload)))
            row = cursor.fetchone()

            if row is None:
                return

            session_id = get_or_create_session(conn, sender, sent_at)

            cursor.execute("""UPDATE messages
                            SET session_id = %s
                            WHERE message_id = %s
                            """, (session_id, message_id))

            cursor.execute(sql_media, (message_id, media_id, mime_type))

def save_location_message(message_id, sender, sent_at, latitude, longitude, name, address, payload):

    sql_messages = """INSERT INTO messages (message_id, sender, sent_at, message_type, text_body, payload)
                        VALUES (%s, %s, %s, %s , %s, %s) ON CONFLICT (message_id) DO NOTHING
                        RETURNING message_id"""

    sql_location = """INSERT INTO message_locations (message_id, latitude, longitude, name, address)
                        VALUES (%s, %s, %s, %s, %s) ON CONFLICT (message_id) DO NOTHING"""

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql_messages, (message_id, sender, sent_at, 'location', None, Jsonb(payload)))
            row = cursor.fetchone()

            if row is None:
                return

            session_id = get_or_create_session(conn, sender, sent_at)
            
            cursor.execute("""UPDATE messages
                            SET session_id = %s
                            WHERE message_id = %s
                            """, (session_id, message_id))

            cursor.execute(sql_location, (message_id, latitude, longitude, name, address))

def mark_image_downloaded(message_id, image_data):

    sql = """UPDATE message_images 
            SET image_converted = %s, download_status = 'downloaded'
            WHERE message_id = %s
            """

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (image_data, message_id))

def mark_image_error(message_id):

    sql = """UPDATE message_images
            SET download_status = 'error'
            WHERE message_id = %s AND download_status <> 'downloaded'
            """

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (message_id,))

#If the audio is downloaded, this function will be executed
def mark_audio_downloaded(message_id, audio_data):

    sql = """UPDATE message_audio
            SET audio_data = %s, download_status = 'downloaded'
            WHERE message_id = %s 
            """

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (audio_data, message_id))

#If the download fails, `download_status` will change to 'error'.
def mark_audio_error(message_id):

    sql = """UPDATE message_audio
            SET download_status = 'error'
            WHERE message_id = %s AND download_status <> 'downloaded'
            """

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (message_id,))

def get_image_download_status(message_id):

    sql = """SELECT download_status
            FROM message_images
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
            FROM message_audio
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
            FROM message_audio
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
def claim_audio_download(message_id):

    sql = """UPDATE message_audio
            SET download_status = 'downloading', download_started_at = CURRENT_TIMESTAMP
            WHERE message_id = %s AND download_status IN ('pending', 'error')
            RETURNING message_id
            """

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (message_id,)) 
            row = cursor.fetchone()

    return row is not None


#This function updates the database to record the audio transcribed into text.
def mark_transcription_completed(message_id, text):

    sql = """UPDATE message_audio
            SET transcription_text = %s, transcription_status = 'completed'
            WHERE message_id = %s
            """

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (text, message_id))

def mark_transcription_error(message_id):

    sql = """UPDATE message_audio
            SET transcription_status = 'error'
            WHERE message_id = %s AND transcription_status <> 'completed'
            """
    
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (message_id,))

#This function prevents a single message from being executed twice.
def claim_transcription(message_id):

    sql = """UPDATE message_audio
            SET transcription_status = 'processing', transcription_started_at = CURRENT_TIMESTAMP
            WHERE message_id = %s AND transcription_status IN ('pending', 'error') AND download_status = 'downloaded'
            RETURNING message_id
            """

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (message_id,))
            row = cursor.fetchone()

    return row is not None

def claim_image_download(message_id):

    sql = """UPDATE message_images
            SET download_status = 'downloading', download_started_at = CURRENT_TIMESTAMP
            WHERE message_id = %s AND download_status IN ('pending', 'error')
            RETURNING message_id
            """

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (message_id,))
            row = cursor.fetchone()

    return row is not None

#Recording of the interpretation of the text
def start_interpretation(message_id, source_text, model_name, prompt_version, schema_version):

    sql_lock = """SELECT message_id
                    FROM messages
                    WHERE message_id = %s
                    FOR UPDATE
                    """
    sql_select = """SELECT message_id
                    FROM message_interpretations
                    WHERE message_id = %s
                        AND source_text = %s
                        AND model_name = %s
                        AND prompt_version = %s
                        AND schema_version = %s
                        AND status IN ('processing','completed')
                    LIMIT 1
                    """

    sql = """INSERT INTO message_interpretations (message_id, source_text, model_name, prompt_version, schema_version)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql_lock, (message_id,))
            message_row = cursor.fetchone()
            if message_row is None:
                raise ValueError("A mensagem não existe")

            cursor.execute(sql_select, (message_id, source_text, model_name, prompt_version, schema_version))
            message_interpretation_row = cursor.fetchone()

            if message_interpretation_row is not None:
                return None
                
            cursor.execute(sql, (message_id, source_text, model_name, prompt_version, schema_version))
            row = cursor.fetchone()

    return row[0]

#Marks the interpretation as complete
def mark_interpretation_completed(interpretation_id, result):

    sql = """UPDATE message_interpretations 
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

    sql = """UPDATE message_interpretations
            SET status = 'error', error_message = %s, finished_at = CURRENT_TIMESTAMP, result = NULL
            WHERE id = %s AND status = 'processing'
            RETURNING id
            """

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (error_message, interpretation_id))
            row = cursor.fetchone()

    return row is not None