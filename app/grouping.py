"""Agrupamento de mensagens em ocorrências de campo.

Estrutura inicial; implementação pendente.
"""
from datetime import timedelta

def get_or_create_session(conn, sender, sent_at):

    with conn.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))', (sender,))

        cursor.execute("""SELECT id, started_at, last_message_at
                        FROM agrozap_field_sessions
                        WHERE sender = %s AND status = 'open'
                        ORDER BY last_message_at DESC, id DESC
                        LIMIT 1""", (sender,))

        session = cursor.fetchone()

        if session is None:
            cursor.execute("""INSERT INTO agrozap_field_sessions (sender, started_at, last_message_at)
                            VALUES (%s, %s, %s)
                            RETURNING id""", (sender, sent_at, sent_at))
            row = cursor.fetchone()

            return row[0]

        session_id, started_at, last_message_at = session

        interval = sent_at - last_message_at

        if interval >= timedelta(minutes=5):

            cursor.execute("""UPDATE agrozap_field_sessions
                            SET status = 'closed'
                            WHERE id = %s""", (session_id,))

            cursor.execute("""INSERT INTO agrozap_field_sessions (sender, started_at, last_message_at)
                            VALUES (%s, %s, %s)
                            RETURNING id""", (sender, sent_at, sent_at))
            row = cursor.fetchone()
            
            return row[0]

        cursor.execute("""UPDATE agrozap_field_sessions
                        SET started_at = LEAST(started_at, %s), 
                            last_message_at = GREATEST(last_message_at, %s)
                        WHERE id = %s""", (sent_at, sent_at, session_id))

        return session_id

def close_inactive_sessions(conn, now):

    cutoff = now - timedelta(minutes=5)

    closed_session_ids = []

    with conn.cursor() as cursor:
        cursor.execute("""SELECT id, sender
                        FROM agrozap_field_sessions
                        WHERE status = 'open' AND last_message_at <= %s
                        ORDER BY sender, id
                        """, (cutoff,))

        sessions = cursor.fetchall()

        for session_id, sender in sessions:
        
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (sender,))

            cursor.execute("""UPDATE agrozap_field_sessions
                            SET status = 'closed'
                            WHERE id = %s AND status = 'open' AND last_message_at <= %s
                            RETURNING id 
                            """, (session_id, cutoff))
            
            row = cursor.fetchone()

            if row is not None:
                closed_session_ids.append(row[0])

    return closed_session_ids