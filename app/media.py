"""Download e armazenamento das 
    mídias originais.
"""

import os, httpx, logging
from dotenv import load_dotenv
from app.transcribe import process_transcription
from app.database import (mark_audio_downloaded, 
                          mark_audio_error, 
                          get_audio_download_status, 
                          claim_audio_download, 
                          get_image_download_status, 
                          claim_image_download, 
                          mark_image_downloaded, 
                          mark_image_error)


load_dotenv()

ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
GRAPH_VERSION = os.getenv("META_GRAPH_VERSION")

if not ACCESS_TOKEN: 
    raise RuntimeError("META_ACCESS_TOKEN não configurado")
if not GRAPH_VERSION:
    raise RuntimeError("META_GRAPH_VERSION não foi configurado")

logger = logging.getLogger("uvicorn.error")

#This fuction will be get the address of the audio
def get_media_url(media_id):

    headers = {"Authorization":f"Bearer {ACCESS_TOKEN}"}
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{media_id}"

    #Querying the URL 
    response = httpx.get(url, headers=headers, timeout=30.0)
    response.raise_for_status() #If the query status does not indicate success, this method throws an exception.

    media_data = response.json()

    if not isinstance(media_data, dict):
        raise RuntimeError("Resposta da Meta deve ser um objeto JSON")

    download_url = media_data.get("url")

    if not isinstance(download_url, str) or not download_url:
        raise RuntimeError("URL de download ausente ou inválida na resposta da Meta")
   
    return download_url

#This fuction download the audio
def download_audio(media_id, mime_type):
    
    download_url = get_media_url(media_id)


    base_mime_type = mime_type.split(";", 1)[0].strip().lower()

    extensions = {
        "audio/ogg":".ogg",
        "audio/mpeg":".mp3",
        "audio/mp4":".m4a"
    }

    extension = extensions.get(base_mime_type)

    if extension is None:
        raise RuntimeError(f"Tipo de áudio não suportado: {base_mime_type}")


    headers = {"Authorization":f"Bearer {ACCESS_TOKEN}"}

    response = httpx.get(download_url, headers=headers, timeout=30.0)
    response.raise_for_status()

    if not response.content:
        raise RuntimeError("O arquivo de áudio recebido está vazio")

    return response.content #Return the binary content

def download_image(media_id, mime_type):

    normalized_mime = mime_type.split(";", 1)[0].strip().lower()
    
    if normalized_mime not in ("image/jpeg", "image/png"):
        raise RuntimeError("O formato não corresponde a de uma imagem")

    headers = {"Authorization":f"Bearer {ACCESS_TOKEN}"}
    image_url = get_media_url(media_id)

    response = httpx.get(image_url, headers=headers, timeout=30.0)
    response.raise_for_status()

    if not response.content:
        raise RuntimeError("O conteúdo está vazio")

    return response.content

"""The two function below processes the image and audio download, respectively:
   - mark_media_error if the download does not occur
   - mark_media_downloaded if the file downloaded, it will be store in the database
   - process_transcription for the file downloaded, it will transcribe the audio to text
"""

def process_image_download(message_id, media_id, mime_type): 

    download_status = get_image_download_status(message_id)

    if download_status == 'downloaded':
        return

    if download_status is None:
        logger.error(f"Registro da imagem não encontrado para mensagem: {message_id}")
        return

    claimed = claim_image_download(message_id)
    if not claimed:
        return

    try:
        image_data = download_image(media_id, mime_type)

    except (httpx.HTTPError, OSError, RuntimeError, ValueError) as exc:
        logger.error(f"Falha do download da mensagem: {message_id} - {type(exc).__name__}")
        if isinstance(exc, httpx.HTTPStatusError): 
            logger.error(f"Status HTTP do download: {exc.response.status_code}")
        mark_image_error(message_id)

    else:
        mark_image_downloaded(message_id, image_data)
        logger.info(f"Download concluído para a mensagem: {message_id}")


def process_audio_download(message_id, media_id, mime_type):

    download_status = get_audio_download_status(message_id)
    normalized_mime = mime_type.split(";", 1)[0].strip().lower()
    is_audio = normalized_mime.startswith("audio/")

    if download_status == 'downloaded':
        if is_audio:
            process_transcription(message_id)
        return 

    if download_status is None:
        logger.error(f"Registro de mídia não encontrado para a mensagem: {message_id}")
        return
    
    claimed = claim_audio_download(message_id)
    if not claimed:
        return

    try:
        audio_data = download_audio(media_id, mime_type)

    except (httpx.HTTPError, OSError, RuntimeError, ValueError) as exc:
        logger.error(f"Falha do download da mensagem: {message_id} - {type(exc).__name__}")
        if isinstance(exc, httpx.HTTPStatusError):
            logger.error(f"Status HTTP do download: {exc.response.status_code}")
        mark_audio_error(message_id)

    else:
        mark_audio_downloaded(message_id, audio_data)
        logger.info(f"Download concluído para a mensagem: {message_id}")
        if is_audio:
            process_transcription(message_id)
