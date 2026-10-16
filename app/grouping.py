"""Agrupamento de mensagens em ocorrências de campo.

Estrutura inicial; implementação pendente.
"""
from datetime import timedelta

def get_or_create_session(conn, sender, sent_at):

    with conn.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))', (sender,))

        cursor.execute("""SELECT id, started_at, last_message_at
                        FROM field_sessions
                        WHERE sender = %s AND status = 'open'
                        ORDER BY last_message_at DESC, id DESC
                        LIMIT 1""", (sender,))

        session = cursor.fetchone()

        if session is None:
            cursor.execute("""INSERT INTO field_sessions (sender, started_at, last_message_at)
                            VALUES (%s, %s, %s)
                            RETURNING id""", (sender, sent_at, sent_at))
            row = cursor.fetchone()

            return row[0]

        session_id, started_at, last_message_at = session

        interval = sent_at - last_message_at

        if interval >= timedelta(minutes=15):

            cursor.execute("""UPDATE field_sessions
                            SET status = 'closed'
                            WHERE id = %s""", (session_id,))

            cursor.execute("""INSERT INTO field_sessions (sender, started_at, last_message_at)
                            VALUES (%s, %s, %s)
                            RETURNING id""", (sender, sent_at, sent_at))
            row = cursor.fetchone()
            
            return row[0]

        cursor.execute("""UPDATE field_sessions
                        SET started_at = LEAST(started_at, %s), 
                            last_message_at = GREATEST(last_message_at, %s)
                        WHERE id = %s""", (sent_at, sent_at, session_id))

        return session_id

    #Testando a transferência