"""Transcrição local de áudios com faster-whisper.

Estrutura inicial; implementação pendente.
"""
import logging
from faster_whisper import WhisperModel
from app.interpret import run_interpretation_background
from app.database import claim_transcription, get_audio_file_path, mark_transcription_completed, mark_transcription_error

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

    if claim_transcription(message_id) == False:
        return

    file_path = get_audio_file_path(message_id)

    if not file_path:
        logger.error("O áudio não tem caminho registrado")
        mark_transcription_error(message_id)
        return

    try:
        text = transcribe_audio(file_path)

    except Exception:
        logger.exception(f"A transcrição do áudio falhou")
        mark_transcription_error(message_id)

    else: 
        mark_transcription_completed(message_id, text)

        if text.strip():
            run_interpretation_background(message_id, text)
