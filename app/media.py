"""Download e armazenamento das 
    mídias originais.
"""

import os, httpx, logging
from dotenv import load_dotenv
from app.transcribe import process_transcription
from app.retry_policy import MAX_DOWNLOAD_ATTEMPTS, DOWNLOAD_RETRY_DELAY_SECONDS
from app.database import (mark_audio_downloaded, 
                          mark_audio_error, 
                          get_audio_download_status, 
                          claim_audio_download, 
                          get_image_download_status, 
                          claim_image_download, 
                          mark_image_downloaded, 
                          mark_image_error, download_task_lock)


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


def log_download_http_error(exc, message_id): 

    logger.error(f"Status HTTP do download da mensagem {message_id}: {exc.response.status_code}")
    
    try:
        error_body = exc.response.json()

    except ValueError:
        logger.warning(f"Resposta de erro sem JSON para a mensagem {message_id}")
        return

    else:
        if not isinstance(error_body, dict) or not isinstance(error_body.get('error'), dict):
            logger.warning(f"Resposta sem detalhes estruturados do erro para a mensagem {message_id}")
            return
        
    error_info = error_body['error']
    logger.error(f"Erro na API para a mensagem {message_id}:"
                 f"code = {error_info.get('code')}, "
                 f"error_subcode = {error_info.get('error_subcode')}, "
                 f"message = {error_info.get('message')}")
                                                     

"""The two function below processes the image and audio download, respectively:
   - mark_media_error if the download does not occur
   - mark_media_downloaded if the file downloaded, it will be store in the database
   - process_transcription for the file downloaded, it will transcribe the audio to text
"""

def process_image_download(message_id, media_id, mime_type): 
    
    with download_task_lock(message_id) as acquired:
        
        if acquired is False:
            return

        download_status = get_image_download_status(message_id)

        if download_status == 'downloaded':
            return

        if download_status is None:
            logger.error(f"Registro da imagem não encontrado para mensagem: {message_id}")
            return

        claim_token = claim_image_download(message_id, MAX_DOWNLOAD_ATTEMPTS)
    
        if claim_token is None:
            return

        try:
            image_data = download_image(media_id, mime_type)

        except (httpx.HTTPError, OSError, RuntimeError, ValueError) as exc:
            logger.error(f"Falha do download da mensagem: {message_id} - {type(exc).__name__}")
        
            if isinstance(exc, httpx.HTTPStatusError): 
                log_download_http_error(exc, message_id)
            
            mark_img_e = mark_image_error(message_id, DOWNLOAD_RETRY_DELAY_SECONDS, claim_token)
        
            if mark_img_e is False:
                logger.warning(f"A reserva já não pertence àquela tentativa em {message_id}") 

        else:
            mark_img_d = mark_image_downloaded(message_id, image_data, claim_token)
        
            if mark_img_d is True:
                logger.info(f"Download concluído para a mensagem: {message_id}")
        
            else:
                logger.warning(f"A reserva já não pertence àquela tentativa {message_id}") 



def process_audio_download(message_id, media_id, mime_type):

    normalized_mime = mime_type.split(";", 1)[0].strip().lower()
    is_audio = normalized_mime.startswith("audio/")
    should_transcribe = False
    
    with download_task_lock(message_id) as acquired:
        
        if acquired is False:
            return
        
        download_status = get_audio_download_status(message_id)
            

        if download_status is None:
            logger.error(f"Registro de mídia não encontrado para a mensagem: {message_id}")
            return
        
        elif download_status == 'downloaded':
            should_transcribe = is_audio
            
        else: 
    
            claim_token = claim_audio_download(message_id, MAX_DOWNLOAD_ATTEMPTS)
            if not claim_token:
                return

            try:
                audio_data = download_audio(media_id, mime_type)

            except (httpx.HTTPError, OSError, RuntimeError, ValueError) as exc:
                logger.error(f"Falha no download do áudio {message_id}: {type(exc).__name__}")  
        
                if isinstance(exc, httpx.HTTPStatusError):
                    log_download_http_error(exc, message_id)
              
                mark_aud_e = mark_audio_error(message_id, DOWNLOAD_RETRY_DELAY_SECONDS, claim_token)
        
                if mark_aud_e is False:
                    logger.warning(f"A reserva já não pertence àquela tentativa em {message_id}")

            else:
                mark_aud_d = mark_audio_downloaded(message_id, audio_data, claim_token)
        
                if mark_aud_d is True:
                    logger.info(f"Download concluído para a mensagem: {message_id}")
            
                    should_transcribe = is_audio
            
                else:
                    logger.warning(f"A reserva já não pertence àquela tentativa {message_id}")
                    
    if should_transcribe is True:
        
        process_transcription(message_id)
            