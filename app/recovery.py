# Tratamento automático de falhas

from app.transcribe import process_transcription
from app.database import (get_retryable_audio_downloads, 
                          get_retryable_image_downloads,
                          get_stale_audio_downloads, 
                          get_stale_image_downloads,
                          release_stale_audio_download,
                          release_stale_image_download,
                          get_retryable_transcriptions,
                          get_stale_transcriptions,
                          release_stale_transcription,
                          get_stale_interpretations,
                          release_stale_interpretation,
                          get_retryable_interpretations)
from app.interpret import (process_interpretation, 
                           model_name,
                           PROMPT_VERSION,
                           SCHEMA_VERSION)
from app.media import process_audio_download, process_image_download
from app.retry_policy import (MAX_DOWNLOAD_ATTEMPTS, 
                              DOWNLOAD_RETRY_DELAY_SECONDS, 
                              DOWNLOAD_STALE_AFTER_SECONDS,
                              MAX_TRANSCRIPTION_ATTEMPTS,
                              TRANSCRIPTION_RETRY_DELAY_SECONDS,
                              TRANSCRIPTION_STALE_AFTER_SECONDS,
                              INTERPRETATION_STALE_AFTER_SECONDS,
                              MAX_INTERPRETATION_ATTEMPTS,
                              INTERPRETATION_RETRY_DELAY_SECONDS)
import logging

logger = logging.getLogger("uvicorn.error")

def recover_image_downloads():

    images = get_retryable_image_downloads(MAX_DOWNLOAD_ATTEMPTS)

    for image in images:

        message_id, media_id, mime_type = image

        try:

            process_image_download(message_id, media_id, mime_type)

        except Exception:

            logger.exception(f"Falha na recuperação do {message_id}")

def recover_audio_downloads():

    audios = get_retryable_audio_downloads(MAX_DOWNLOAD_ATTEMPTS)

    for audio in audios:

        message_id, media_id, mime_type = audio

        try:

            process_audio_download(message_id, media_id, mime_type)

        except Exception:

            logger.exception(f"Falha na recuperação do {message_id}")
            
def recover_stale_image_downloads():
    
    stale_images = get_stale_image_downloads(DOWNLOAD_STALE_AFTER_SECONDS)
    
    for stale_image in stale_images:
        message_id, expected_token, expected_started_at = stale_image   
        
        try:
            
            rel_st_img = release_stale_image_download(message_id, expected_token, expected_started_at, DOWNLOAD_STALE_AFTER_SECONDS, DOWNLOAD_RETRY_DELAY_SECONDS) 
            if rel_st_img is True:
                logger.info(f"Reserva abandonada liberada em {message_id}")
                
            else: 
                continue
        
        except Exception:
            
            logger.exception(f"Reserva não liberada em {message_id}") 
        
        
def recover_stale_audio_downloads():
    
    stale_audios = get_stale_audio_downloads(DOWNLOAD_STALE_AFTER_SECONDS)
    
    for stale_audio in stale_audios:
        message_id, expected_token, expected_started_at = stale_audio
        
        try:
            
            rel_st_aud = release_stale_audio_download(message_id, expected_token, expected_started_at, DOWNLOAD_STALE_AFTER_SECONDS, DOWNLOAD_RETRY_DELAY_SECONDS)
            if rel_st_aud is True:
                logger.info(f"Reserva abandonada liberada em {message_id}")
            
            else:
                continue
        
        except Exception:
            
            logger.exception(f"Reserva não liberada em {message_id}")
            
            
def recover_stale_transcriptions():
    
    stale_transcriptions = get_stale_transcriptions(TRANSCRIPTION_STALE_AFTER_SECONDS)
    
    for stale_transcription in stale_transcriptions:
        message_id, expected_token, expected_started_at = stale_transcription
        
        try:
            
            rel_st_tr = release_stale_transcription(message_id, expected_token, expected_started_at, TRANSCRIPTION_STALE_AFTER_SECONDS, TRANSCRIPTION_RETRY_DELAY_SECONDS)
            if rel_st_tr is True:
                logger.info(f"Reserva abandonada liberada em {message_id}")
                
            else:
                continue
            
        except Exception:
            logger.exception(f"Reserva não liberada em {message_id}")
            
def recover_transcriptions():
    
    transcriptions_id = get_retryable_transcriptions(MAX_TRANSCRIPTION_ATTEMPTS)
    
    for transcription_id in transcriptions_id:
        
        try:
            process_transcription(transcription_id)
            
        except Exception:
            logger.exception(f"Falha na recuperação da transcrição do {transcription_id}")

def recover_stale_interpretations():
    
    stale_interpretations = get_stale_interpretations(INTERPRETATION_STALE_AFTER_SECONDS)
    
    for stale_interpretation in stale_interpretations:
        interpretation_id, message_id, expected_started_at = stale_interpretation
        
        try:
            
            rel_st_int = release_stale_interpretation(interpretation_id, message_id, expected_started_at, INTERPRETATION_STALE_AFTER_SECONDS)
            if rel_st_int is True:
                logger.info(f"Reserva abandonada liberada em {interpretation_id} de {message_id}")
                
            else:
                continue
                
        except Exception:
            logger.exception(f"Reserva não liberada em {interpretation_id} de {message_id}")
            
def recover_interpretations():
    
    interpretations = get_retryable_interpretations(model_name, 
                                                    PROMPT_VERSION, 
                                                    SCHEMA_VERSION, 
                                                    MAX_INTERPRETATION_ATTEMPTS, 
                                                    INTERPRETATION_RETRY_DELAY_SECONDS)
    
    for message_id, source_text in interpretations:
        
        try:
            
            process_interpretation(message_id, source_text)
            
        except Exception:
            logger.exception(f"Falha na recuperação da interpretação do {message_id}")