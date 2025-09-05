# main.py
# Run either:
#   python main.py
# or
#   uvicorn main:app --host 0.0.0.0 --port 8000
#
# Env needed:
#   export GOOGLE_API_KEY="YOUR_AI_STUDIO_OR_VERTEX_KEY"
# Optional:
#   export GEMINI_MODEL="gemini-live-2.5-flash-preview"
#   export VOICE_NAME="Kore"
#   export LANGUAGE_CODE="en-IN"

import os
import asyncio
import logging
import json
from typing import Optional, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
import uvicorn

from google import genai
from google.genai import types

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scholar-live")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
if not GOOGLE_API_KEY:
    logger.warning("GOOGLE_API_KEY not set; Gemini connection will fail.")

MODEL = os.getenv("GEMINI_MODEL", "gemini-live-2.5-flash-preview")
VOICE_NAME = os.getenv("VOICE_NAME", "Puck")
LANGUAGE_CODE = os.getenv("LANGUAGE_CODE", "en-IN")

SYSTEM_INSTRUCTION = (
    "You are ScholAR, an AI assistant integrated into smart glasses designed for learning and "
    "knowledge acquisition. Your primary purpose is education and deep understanding. You excel "
    "at teaching complex concepts by breaking them down into understandable parts, providing "
    "detailed explanations, examples, and step-by-step guidance. Make learning engaging, "
    "interactive, and comprehensive. Encourage curiosity and deeper exploration."
)

# Google GenAI client (reads GOOGLE_API_KEY from env)
if api_key := os.getenv("GOOGLE_API_KEY"):
    client = genai.Client(api_key=api_key)
    logger.info(f"Using AI Studio key (...{api_key[-6:]}, model={MODEL})")

app = FastAPI(title="scholAR Live (2 files)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], allow_credentials=True
)

@app.get("/", response_class=HTMLResponse)
async def index():
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/healthz", response_class=PlainTextResponse)
async def healthz():
    return "ok"


# WebSocket endpoint for real-time audio streaming
@app.websocket("/ws/voice")
async def voice_ws(
    ws: WebSocket,
    voice: Optional[str] = Query(default=VOICE_NAME),
    lang: Optional[str] = Query(default=LANGUAGE_CODE),
    model: Optional[str] = Query(default=MODEL),
):
    await ws.accept()
    logger.info("Client connected")

    config = {
        "response_modalities": ["AUDIO"],
        "system_instruction": SYSTEM_INSTRUCTION,
        "speech_config": {
            "voice_config": {"prebuilt_voice_config": {"voice_name": voice}},
            "language_code": lang,
        },
    }

    async with client.aio.live.connect(model=model, config=config) as session:
        logger.info(f"Successfully connected to Gemini model: {model}")
        logger.info(f"Session object: {session}")
        logger.info(f"Using AI Studio key (...{api_key[-6:]}, model={MODEL})")

        
        async def pump_gemini_to_client():
            logger.info("pump_gemini_to_client started and waiting for Gemini messages.")
            message_count = 0
            try:
               async for msg in session.receive():
                    message_count += 1
                    logger.info(f"pump_gemini_to_client received message #{message_count} from Gemini: {type(msg)}")
                    
                    # Log all attributes of the message for debugging
                    logger.info(f"Message attributes: {dir(msg)}")
                    
                    if hasattr(msg, 'data') and msg.data is not None:
                        data_length = len(msg.data)
                        first_data_bytes = msg.data[:16] if data_length >= 16 else msg.data
                        logger.info(f"Received audio from Gemini: {data_length} bytes. First 16 bytes: {first_data_bytes}")
                        await ws.send_bytes(msg.data)
                    
                    if hasattr(msg, 'server_content'):
                        sc = msg.server_content
                        logger.info(f"Server content: {sc}")
                        if sc:
                            if hasattr(sc, 'input_transcription') and sc.input_transcription and sc.input_transcription.text:
                                logger.info(f"Gemini input transcript: {sc.input_transcription.text}")
                                await ws.send_json({"type":"input_transcript","text":sc.input_transcription.text})
                            if hasattr(sc, 'output_transcription') and sc.output_transcription and sc.output_transcription.text:
                                logger.info(f"Gemini output transcript: {sc.output_transcription.text}")
                                await ws.send_json({"type":"output_transcript","text":sc.output_transcription.text})
                    
                    # Log any other message content
                    if hasattr(msg, '__dict__'):
                        logger.info(f"Full message content: {msg.__dict__}")
            except Exception as e:
                logger.exception("Gemini->Client loop error: %s", e)
                try: await ws.close()
                except Exception: pass

        async def pump_client_to_gemini():
            logger.info("pump_client_to_gemini started and waiting for client messages.")
            try:
                while True:
                    message = await ws.receive()
                    logger.info(f"pump_client_to_gemini received a message from client: {message}")
                    if message["type"] == "websocket.disconnect":
                        break
                    if "bytes" in message and message["bytes"] is not None:
                        audio_length = len(message["bytes"])
                        first_bytes = message["bytes"][:16] if audio_length >= 16 else message["bytes"]
                        logger.info(f"Received audio from client: {audio_length} bytes. First 16 bytes: {first_bytes}")
                        logger.info("Preparing to send audio blob to Gemini with mime_type: audio/pcm;rate=16000")
                        audio_blob = types.Blob(data=message["bytes"], mime_type="audio/pcm;rate=16000")
                        blob_length = len(audio_blob.data) if audio_blob.data is not None else 0
                        first_blob_bytes = audio_blob.data[:16] if blob_length >= 16 else audio_blob.data
                        logger.info(f"Audio blob created. Length: {blob_length} bytes. Mime type: {audio_blob.mime_type}. First 16 bytes: {first_blob_bytes}")
                        try:
                            await session.send_realtime_input(audio=audio_blob)
                            logger.info("Audio successfully sent to Gemini session.")
                        except Exception as e:
                            logger.error(f"Error sending audio to Gemini: {e}")
                    elif "text" in message and message["text"] is not None:
                        try:
                            text_data = json.loads(message["text"])
                            if text_data.get("type") == "end":
                                logger.info("Received end-of-turn signal from client.")
                                # You can handle end-of-turn logic here if needed
                            elif text_data.get("type") == "text":
                                logger.info(f"Received text message: {text_data.get('data', '')}")
                                # Handle text messages if needed
                            else:
                                logger.info(f"Received control message: {text_data}")
                        except json.JSONDecodeError:
                            logger.warning(f"Received non-JSON text message: {message['text'][:100]}")
                        except Exception as e:
                            logger.warning(f"Error processing text message: {e}")
            except WebSocketDisconnect:
                logger.info("Client disconnected")
            except Exception as e:
                logger.exception("Client->Gemini loop error: %s", e)

        await asyncio.gather(pump_gemini_to_client(), pump_client_to_gemini())
    logger.info("Session closed")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8765, reload=False)
