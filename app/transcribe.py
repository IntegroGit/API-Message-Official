"""Transcrição local de áudios com faster-whisper.

Estrutura inicial; implementação pendente.
"""
import logging
from faster_whisper import WhisperModel
from tempfile import TemporaryDirectory
from pathlib import Path
from app.interpret import run_interpretation_background
from app.retry_policy import MAX_TRANSCRIPTION_ATTEMPTS, TRANSCRIPTION_RETRY_DELAY_SECONDS
from app.database import (claim_transcription, 
                          get_audio_data, 
                          mark_transcription_completed, 
                          mark_transcription_error,
                          transcription_task_lock,)

logger = logging.getLogger("uvicorn.error")

model = WhisperModel("large-v3", device="cpu", compute_type="int8")

def transcribe_audio(file_path):

    segments, info = model.transcribe(file_path, language="pt")

    text_parts = []

    for segment in segments:
        text_parts.append(segment.text)

    text = " ".join(text_parts).strip()

    return text

def process_transcription(message_id):

    
    should_interpret = False   

    with transcription_task_lock(message_id) as acquire:
        
        if acquire is False:
            return
        
        claim_token = claim_transcription(message_id, MAX_TRANSCRIPTION_ATTEMPTS)
        
        if claim_token == None:
            return 
    
        try:
        
            audio_record = get_audio_data(message_id)
            if audio_record is None:
                raise RuntimeError("Registro de áudio não encontrado")
            
            audio_data, mime_type = audio_record
            if not audio_data:
                raise RuntimeError("O áudio não tem conteúdo armazenado no banco")

            base_mime_type = mime_type.split(";", 1)[0].strip().lower()
            extensions = {
                    "audio/ogg":".ogg",
                    "audio/mpeg":".mp3",
                    "audio/mp4":".m4a"
                }

            extension = extensions.get(base_mime_type)

            if extension is None:
                raise RuntimeError(f"Tipo de áudio {base_mime_type} não suportado")

            with TemporaryDirectory() as temp_dir:
                file_path = Path(temp_dir) / f"audio{extension}"
                file_path.write_bytes(audio_data)
                logger.info(f"Arquivo temporário criado: {file_path}")

                text = transcribe_audio(str(file_path))
            
                if not isinstance(text, str):
                    raise ValueError("A transcrição não é um texto")
            
                if not text.strip():
                    raise ValueError("Não foi produzido a transcrição")

            logger.info(f"Arquivo temporário existe após a transcrição: {file_path.exists()}")
        
        except Exception:
            logger.exception(f"A transcrição do áudio falhou")
            mk_tr_err = mark_transcription_error(message_id, TRANSCRIPTION_RETRY_DELAY_SECONDS, claim_token)
        
            if mk_tr_err is False:
                logger.warning(f"A reserva de {message_id} já não pertence à tentativa")        

        else: 
            mk_tr_comp = mark_transcription_completed(message_id, text, claim_token)

            if mk_tr_comp is True:
                should_interpret = mk_tr_comp
        
            else:
                logger.warning(f"A reserva de {message_id} nao pertence a essa tentativa")

    if should_interpret is True:
        run_interpretation_background(message_id, text)