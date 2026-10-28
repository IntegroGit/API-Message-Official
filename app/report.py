"""Geração de relatórios HTML e PDF.

Estrutura inicial; implementação pendente.
"""
from app.interpret import MessageInterpretation, validate_evidence, SCHEMA_VERSION
from app.database import get_connection, save_session_report
from pathlib import Path
from zoneinfo import ZoneInfo
from jinja2 import Environment, FileSystemLoader, select_autoescape
from base64 import b64encode
from weasyprint import HTML


TEMPLATE_VERSION = "v1"


class ReportNotReadyError(RuntimeError):
    pass

def get_session_report_data(conn, session_id):

    with conn.cursor() as cursor:
        cursor.execute("""SELECT id, sender, started_at, last_message_at, status
                        FROM agrozap_field_sessions
                        WHERE id = %s
                        """, (session_id,))

        session = cursor.fetchone()

        if session is None:
            raise ValueError("Sessão não encontrada")

        stored_session_id, sender, started_at, last_message_at, status = session

        if status != 'closed':
            raise ValueError("A sessão ainda está aberta")

        cursor.execute("""SELECT message_id, message_type, sent_at, received_at, text_body
                        FROM agrozap_messages
                        WHERE session_id = %s
                        ORDER BY sent_at, received_at, message_id
                        """, (stored_session_id,))
        
        messages = cursor.fetchall()

        if not messages:
            raise ValueError("A sessão não possui mensagens")

        report_data = {
            'session':{
                'id':stored_session_id,
                'sender':sender,
                'started_at':started_at,
                'last_message_at':last_message_at,
                'status':status
            },

            'messages':[]
        }

        for message in messages:

            message_id, message_type, sent_at, received_at, text_body = message

            message_data = {
                'message_id':message_id,
                'message_type':message_type,
                'sent_at':sent_at,
                'received_at':received_at,
                'text_body':text_body,
                'audio':None,
                'image':None,
                'location':None,
                'interpretation':None
            }

            if message_type == 'audio':

                cursor.execute("""SELECT mime_type, download_status, transcription_status, transcription_text
                                FROM agrozap_message_audio
                                WHERE message_id = %s
                                """, (message_id,))

                audio = cursor.fetchone()

                if audio is None:
                    raise ValueError("Registro de áudio não encontrado")

                mime_type, download_status, transcription_status, transcription_text = audio

                if download_status == 'error' or transcription_status == 'error':
                    raise RuntimeError("Falha no processamento do áudio")
                
                if download_status != 'downloaded' or transcription_status != 'completed':
                    raise ReportNotReadyError("Áudio ainda em processamento")

                if not isinstance(transcription_text, str) or not transcription_text.strip():
                    raise ValueError("Áudio concluído sem texto de transcrição")

                message_data['audio'] = {
                    'mime_type':mime_type,
                    'download_status':download_status,
                    'transcription_status':transcription_status,
                    'transcription_text':transcription_text
                }

            elif message_type == 'image':
              
                cursor.execute("""SELECT mime_type, download_status, image_converted
                                FROM agrozap_message_images
                                WHERE message_id = %s
                                """, (message_id,))

                image = cursor.fetchone()

                if image is None:
                    raise ValueError("Registro de imagem não encontrado")

                mime_type, download_status, image_converted = image

                if download_status == 'error':
                    raise RuntimeError("Falha no processamento da imagem")

                if download_status != 'downloaded':
                    raise ReportNotReadyError("Imagem ainda em processamento")

                if not image_converted:
                    raise ValueError("Imagem sem conteúdo armazenado")

                message_data['image'] = {
                    'mime_type':mime_type,
                    'download_status':download_status,
                    'image_converted':image_converted
                }

            elif message_type == 'location':

                cursor.execute("""SELECT latitude, longitude, name, address
                                FROM agrozap_message_locations
                                WHERE message_id = %s
                                """, (message_id,))

                location = cursor.fetchone()

                if location is None:
                    raise ValueError("Registro de localização não encontrado")

                latitude, longitude, name, address = location

                message_data['location'] = {
                    'latitude':latitude,
                    'longitude':longitude,
                    'name':name,
                    'address':address
                }

            if message_type in ('text','audio'):

                if message_type == 'text':
                    source_text = text_body

                if message_type == 'audio':
                    source_text = transcription_text

                if isinstance(source_text, str) and source_text.strip():

                    cursor.execute("""SELECT id, status, result, model_name, prompt_version, schema_version
                                    FROM agrozap_message_interpretations
                                    WHERE message_id = %s AND source_text = %s
                                    ORDER BY id DESC
                                    LIMIT 1
                                    """, (message_id, source_text.strip()))

                    interpretation = cursor.fetchone()

                    if interpretation is None:
                        raise ReportNotReadyError("Interpretação ainda não disponível")
                    
                    interpretation_id, interpretation_status, result, model_name, prompt_version, schema_version = interpretation

                    if interpretation_status == 'error':
                        raise RuntimeError("Falha na interpretação")

                    if interpretation_status != 'completed':
                        raise ReportNotReadyError("Interpretação ainda em processamento")

                    if schema_version != SCHEMA_VERSION:
                        raise ValueError("Versão do esquema de interpretação incompatível")

                    validate_interpretation = MessageInterpretation.model_validate(result)

                    validate_evidence(source_text.strip(), validate_interpretation)

                    message_data['interpretation'] = {
                        'id':interpretation_id,
                        'status':interpretation_status,
                        'source_text':source_text.strip(),
                        'result':validate_interpretation.model_dump(),
                        'model_name':model_name,
                        'prompt_version':prompt_version,
                        'schema_version':schema_version
                    }

            report_data['messages'].append(message_data)

    return report_data

def image_to_data_uri(image_data, mime_type):

    encode_image = b64encode(image_data).decode("ascii")

    return f"data:{mime_type};base64,{encode_image}"

def format_report_datetime(value):

    value = value.astimezone(ZoneInfo("America/Sao_Paulo"))

    return value.strftime("%d/%m/%Y %H:%M:%S %z")

def render_session_report_html(report_data):

    templates_dir = Path(__file__).resolve().parent.parent / "templates"

    env = Environment(loader=FileSystemLoader(str(templates_dir)),
                        autoescape=select_autoescape(["html", "xml"]))

    env.filters["image_data_uri"] = image_to_data_uri
    env.filters["report_datetime"] = format_report_datetime

    template = env.get_template("report.html")

    return template.render(session = report_data["session"],
                           messages = report_data["messages"])

def render_session_report_pdf(report_html):

    document = HTML(string=report_html)

    return document.write_pdf()

def build_report_source_manifest(report_data):

    sources = []

    for message in report_data['messages']:

        interpretation = message['interpretation']

        sources.append(
            {
                'message_id':message['message_id'],
                'interpretation_id':interpretation['id'] if interpretation else None
            }
        )

    return {
        'session_id':report_data['session']['id'],
        'messages':sources
    }

def generate_session_report(session_id):

    with get_connection() as conn:

        report_data = get_session_report_data(conn, session_id)

        report_html = render_session_report_html(report_data)

        report_pdf = render_session_report_pdf(report_html)

        source_manifest = build_report_source_manifest(report_data)

        save_report = save_session_report(conn, session_id, report_html, report_pdf, source_manifest, TEMPLATE_VERSION)

    return save_report