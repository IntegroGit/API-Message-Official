"""Recepção de eventos e validação do webhook da Meta.

Estrutura inicial; implementação pendente.
"""
import os, hmac, hashlib, logging
from json import JSONDecodeError
from dotenv import load_dotenv
from typing import Annotated
from app.database import save_message, save_audio_message, save_image_message, save_location_message
from app.interpret import run_interpretation_background
from app.media import process_audio_download, process_image_download
from datetime import timezone, datetime
from fastapi.responses import PlainTextResponse
from starlette.concurrency import run_in_threadpool
from fastapi import APIRouter, Query, HTTPException, Request, BackgroundTasks



load_dotenv()

VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN")
APP_SECRET = os.getenv("META_APP_SECRET")

if not APP_SECRET:
    raise RuntimeError("META_APP_SECRET não configurado")
if not VERIFY_TOKEN:
    raise RuntimeError("META_VERIFY_TOKEN não configurado")

router = APIRouter()
logger = logging.getLogger("uvicorn.error")

#Validating webhook authentication
@router.get("/webhook", response_class=PlainTextResponse)
async def verify_webhook(hub_mode: Annotated[str, Query(alias="hub.mode")],      #Indicates the operation
                         hub_verify_token: Annotated[str, Query(alias="hub.verify_token")],       #Token to be compared
                         hub_challenge: Annotated[str, Query(alias="hub.challenge")]):      #Challenge that we will return after validating the request.
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:    
        return PlainTextResponse(hub_challenge)

    raise HTTPException(status_code=403, detail="Verificação inválida")


@router.post("/webhook")
async def receive_webhook(request: Request, background_task: BackgroundTasks):

    #Calculation of the expected signature
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    expected_signature = "sha256=" + hmac.new(APP_SECRET.encode("utf-8") ,body, hashlib.sha256).hexdigest()
    
    if not signature or not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=403, detail="Assinatura inválida")

    #Interpretation of the request body as JSON
    try: 
        payload = await request.json() #Checking if the body is in JSON format

    except JSONDecodeError:
        raise HTTPException(status_code=400, detail="JSON inválido") 

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="O corpo deve ser o objeto JSON")

    #Checking if the event belongs to the Whatsapp Business account
    if payload.get("object") != "whatsapp_business_account":
        raise HTTPException(status_code=400, detail="Objeto do webhook não suportado")

    entries = payload.get("entry") #Getting the entry of the JSON 
    if not isinstance(entries, list):
        raise HTTPException(status_code=400, detail="O campo entry deve ser uma lista")

    for entry in entries:    #Checking if each element of the list entry is a dict
        if not isinstance(entry, dict): 
            raise HTTPException(status_code=400, detail="Cada item de entry deve ser um objeto JSON")

        #Checking if the element changes is a list
        changes = entry.get("changes")
        if not isinstance(changes, list):
            raise HTTPException(status_code=400, detail="O campo changes deve ser uma lista")
      
        for change in changes:   #Checking if each element of the list change is a dict
            if not isinstance(change, dict):
                raise HTTPException(status_code=400, detail="Cada item de changes deve ser um objeto JSON")

            if change.get("field") != "messages": 
                continue

            #Checking if the element value is a dict    
            value = change.get("value") #Getting the value of the JSON 
            if not isinstance(value, dict):  
                raise HTTPException(status_code=400, detail="O campo value deve ser um objeto JSON")

            messages = value.get("messages", []) #Getting the message of the JSON 
            if not isinstance(messages, list):
                raise HTTPException(status_code=400, detail="O campo messsages deve ser um lista")

            for message in messages:   #Cheking if each elemente of the list messages is a dict
                if not isinstance(message, dict):
                    raise HTTPException(status_code=400, detail="Cada item de mensagens dever ser um objeto JSON")

                #The variables that catch the values from JSON elements
                message_id = message.get("id") #Getting the id of the JSON 
                sender = message.get("from") #Getting the from of the JSON 
                message_type = message.get("type") #Getting the type of the JSON 
                message_timestamp = message.get("timestamp") #Getting the timestamp of the JSON 

                if message_type not in ("text", "audio", "image", "location"):
                    continue

                #Checking if the element id is a string
                if not isinstance(message_id, str) or not message_id:
                    raise HTTPException(status_code=400, detail="O campo id deve ser uma string") 
                
                #Checking if the element from is a string
                if not isinstance(sender, str) or not sender:
                    raise HTTPException(status_code=400, detail="O campo from deve ser uma string") 

                #Converting the element timestamp into a UTC date
                try: 
                    sent_at = datetime.fromtimestamp(int(message_timestamp), timezone.utc)

                except (TypeError, ValueError, OverflowError, OSError):
                    raise HTTPException(status_code=400, detail="Timestamp da mensagem inválido")

                if message_type == "text":
                
                    #Getting the text of the JSON 
                    text_data = message.get("text")

                    #Checking if the element text is a dict
                    if not isinstance(text_data, dict):
                        raise HTTPException(status_code=400, detail="O campo text deve ser um objeto JSON")

                    #Getting the body of the JSON
                    message_text = text_data.get("body")

                    #Checking if the element body is a string
                    if not isinstance(message_text, str):
                        raise HTTPException(status_code=400, detail="O campo text.body deve ser uma string")

                    #Passing the variables that store the values of the JSON elements to the save_message function
                    await run_in_threadpool(save_message, message_id, sender, sent_at, message_type, message_text, payload)

                    background_task.add_task(run_interpretation_background, message_id, message_text)

                    logger.info("Mensagem de texto recebida")

                elif message_type == "audio":
                    audio_data = message.get("audio")

                    #Checking if the element audio is a dict
                    if not isinstance(audio_data, dict):
                        raise HTTPException(status_code=400, detail="O campo de audio deve ser um objeto JSON")

                    media_id = audio_data.get("id")

                    #Checking if the element id is a str
                    if not isinstance(media_id, str) or not media_id:
                        raise HTTPException(status_code=400, detail="O campo audio.id deve ser uma string não vazia")

                    mime_type = audio_data.get("mime_type")

                    if not isinstance(mime_type, str) or not mime_type:
                        raise HTTPException(status_code=400, detail="O campo audio.mime_type deve ser uma string não vazia")

                    await run_in_threadpool(save_audio_message, message_id, sender, sent_at, media_id, mime_type, payload)

                    background_task.add_task(process_audio_download, message_id, media_id, mime_type)

                elif message_type == "image":
                    image_data = message.get("image")

                    #Check if the element image is a dict
                    if not isinstance(image_data, dict):
                        raise HTTPException(status_code=400, detail="O campo image deve ser um objeto JSON")

                    media_id = image_data.get("id")

                    if not isinstance(media_id, str) or not media_id:
                        raise HTTPException(status_code=400, detail="O campo image.id deve ser uma string")

                    mime_type = image_data.get("mime_type")

                    if not isinstance(mime_type, str) or not mime_type:
                        raise HTTPException(status_code=400, detail="O campo image.mime_type deve ser uma string")

                    caption = image_data.get("caption")

                    if caption is not None:
                        if not isinstance(caption, str):
                            raise HTTPException(status_code=400, detail="O campo image.caption deve ser uma string")

                    await run_in_threadpool(save_image_message, message_id, sender, sent_at, media_id, mime_type, caption, payload)

                    background_task.add_task(process_image_download, message_id, media_id, mime_type)

                elif message_type == "location":

                    location_data = message.get("location")

                    if not isinstance(location_data, dict):
                        raise HTTPException(status_code=400, detail="O campo deve ser um objeto JSON")

                    latitude = location_data.get("latitude")
                    longitude = location_data.get("longitude")

                    for field_name, value in (("latitude", latitude), ("longitude", longitude)):
                        if isinstance (value, bool) or not isinstance(value, (int, float)):
                            raise HTTPException(status_code=400, detail=f"O campo {field_name} deve ser um números")

                    if not (-90 <= latitude <= 90):
                        raise HTTPException(status_code=400, detail="A coordenada da latitude está incorreta")

                    if not (-180 <= longitude <= 180):
                        raise HTTPException(status_code=400, detail="A coordenada da longitude está incorreta")

                    name = location_data.get("name")

                    if name is not None:
                        if not isinstance(name, str):
                            raise HTTPException(status_code=400, detail="o campo name deve ser uma string")

                    address = location_data.get("address")

                    if address is not None:
                        if not isinstance(address, str):
                            raise HTTPException(status_code=400, detail="O campo address deve ser uma string")

                    await run_in_threadpool(save_location_message, message_id, sender, sent_at, latitude, longitude, name, address, payload)
            
    return PlainTextResponse("EVENT_RECEIVED", status_code=200)