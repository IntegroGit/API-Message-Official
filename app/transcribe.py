"""Transcrição local de áudios com faster-whisper.

Estrutura inicial; implementação pendente.
"""
import logging
from faster_whisper import WhisperModel
from tempfile import TemporaryDirectory
from pathlib import Path
from app.interpret import run_interpretation_background
from app.database import claim_transcription, get_audio_data, mark_transcription_completed, mark_transcription_error

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

    audio_record = get_audio_data(message_id)

    if audio_record is None:
        logger.error("Registro não encontrado")
        mark_transcription_error(message_id)
        return

    audio_data, mime_type = audio_record

    if not audio_data:
        logger.error("O áudio não tem conteúdo armazenado no banco")
        mark_transcription_error(message_id)
        return

    try:

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

        logger.info(f"Arquivo temporário existe após a transcrição: {file_path.exists()}")
        
    except Exception:
        logger.exception(f"A transcrição do áudio falhou")
        mark_transcription_error(message_id)

    else: 
        mark_transcription_completed(message_id, text)

        if text.strip():
            run_interpretation_background(message_id, text)
