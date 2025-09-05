import asyncio
import json
import base64
import os

# Google Generative AI
from google import genai
from google.genai import types
from google.genai.types import (
    LiveConnectConfig,
    SpeechConfig,
    VoiceConfig,
    PrebuiltVoiceConfig,
)

# Common components (assuming these exist in your project)
from common import (
    BaseWebSocketServer,
    logger,
    SYSTEM_INSTRUCTION,
)

# ---- Config -----------------------------------------------------------------

# Prefer API key (AI Studio); fall back to Vertex (needs region)
api_key = os.getenv("GOOGLE_API_KEY")
PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID", "My First Project")
LOCATION = os.getenv("GOOGLE_VERTEX_LOCATION", "us-central1")  # Vertex needs regional endpoint
MODEL = "gemini-live-2.5-flash-preview"
VOICE_NAME = "Puck"

# Default input rate (we’ll use the browser’s actual rate if it tells us)
INPUT_SAMPLE_RATE_DEFAULT = 16000  # 16-bit PCM, mono

# ---- Client init ------------------------------------------------------------

if api_key:
    client = genai.Client(api_key=api_key)
    logger.info(f"Using AI Studio key (...{api_key[-6:]}, model={MODEL})")
else:
    client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
    logger.info(f"Using Vertex AI with ADC (project={PROJECT_ID}, location={LOCATION}, model={MODEL})")

# ---- Live API configuration -------------------------------------------------

logger.info(f"System instruction being sent to Gemini:\n{SYSTEM_INSTRUCTION}")

config = LiveConnectConfig(
    response_modalities=["AUDIO"],
    # Use explicit config objects (not raw dicts)
    output_audio_transcription=types.AudioTranscriptionConfig(),
    input_audio_transcription=types.AudioTranscriptionConfig(),
    speech_config=SpeechConfig(
        voice_config=VoiceConfig(
            prebuilt_voice_config=PrebuiltVoiceConfig(voice_name=VOICE_NAME)
        ),
        # language_code="en-US",  # uncomment to force a language
    ),
    system_instruction=SYSTEM_INSTRUCTION,
)

# ---- Server -----------------------------------------------------------------

class LiveAPIWebSocketServer(BaseWebSocketServer):
    """WebSocket server bridging browser audio <-> Gemini Live Native Audio."""

    async def process_audio(self, websocket, client_id):
        logger.info(f"[{client_id}] process_audio: START")
        self.active_clients[client_id] = websocket

        # Per-connection state
        audio_queue = asyncio.Queue(maxsize=8)
        client_sample_rate = INPUT_SAMPLE_RATE_DEFAULT

        try:
            logger.info(f"[{client_id}] Connecting to Gemini (model={MODEL})")
            async with client.aio.live.connect(model=MODEL, config=config) as session:
                logger.info(f"[{client_id}] Connected to Gemini")
                # Tell the client that both WS and Gemini are ready
                try:
                    await websocket.send(json.dumps({"type": "connected", "model": MODEL}))
                except Exception:
                    pass

                # ---------- Task 1: WebSocket -> Queues/Session (reader) ----------
                async def ws_reader():
                    logger.info(f"[{client_id}] WS reader: START")
                    try:
                        async for message in websocket:
                            try:
                                data = json.loads(message)
                            except json.JSONDecodeError:
                                logger.error(f"[{client_id}] Invalid JSON message")
                                continue

                            mtype = data.get("type")
                            if mtype == "audio":
                                payload = data.get("data", "")
                                if not payload:
                                    continue
                                audio_bytes = base64.b64decode(payload)
                                sr = int(data.get("rate") or client_sample_rate)
                                client_sample_rate = sr
                                # enqueue chunk (backpressure via maxsize)
                                await audio_queue.put((audio_bytes, sr))

                            elif mtype == "end":
                                # Signal end-of-turn for audio. We use a sentinel to ensure commit
                                # happens *after* all enqueued chunks have been sent.
                                logger.info(f"[{client_id}] Received end-of-input from client")
                                await audio_queue.put(None)

                            elif mtype == "text":
                                text = data.get("data", "")
                                if text:
                                    # Text turns can be sent directly with end_of_turn=True
                                    await session.send(input=text, end_of_turn=True)
                                    logger.info(f"[{client_id}] Forwarded text turn to model")

                            elif mtype == "close":
                                logger.info(f"[{client_id}] Client requested close")
                                try:
                                    await websocket.close()
                                finally:
                                    break

                            else:
                                logger.debug(f"[{client_id}] Unknown message type: {mtype}")

                    except Exception as e:
                        logger.error(f"[{client_id}] WS reader error: {e}")
                    finally:
                        logger.info(f"[{client_id}] WS reader: END")

                # ---------- Task 2: Audio queue -> Gemini (sender) ----------
                async def audio_sender():
                    logger.info(f"[{client_id}] Audio sender: START")
                    try:
                        while True:
                            item = await audio_queue.get()
                            try:
                                # Sentinel: commit the turn (after prior chunks are sent)
                                if item is None:
                                    try:
                                        await session.send(end_of_turn=True)
                                        logger.info(f"[{client_id}] Audio turn committed")
                                    finally:
                                        audio_queue.task_done()
                                    continue

                                chunk, sr = item
                                try:
                                    await session.send_realtime_input(
                                        audio=types.Blob(
                                            data=chunk,
                                            mime_type=f"audio/pcm;rate={int(sr)};channels=1",
                                        )
                                    )
                                except Exception as e:
                                    logger.error(f"[{client_id}] Failed sending audio: {e}")
                                finally:
                                    audio_queue.task_done()

                            except asyncio.CancelledError:
                                # Attempt to flush outstanding items before exit (optional)
                                raise
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        logger.error(f"[{client_id}] Audio sender error: {e}")
                    finally:
                        logger.info(f"[{client_id}] Audio sender: END")

                # ---------- Task 3: Gemini -> WebSocket (receiver) ----------
                async def model_receiver():
                    logger.info(f"[{client_id}] Model receiver: START")
                    try:
                        async for response in session.receive():
                            # Stream synthesized audio back
                            if response.data is not None:
                                try:
                                    b64 = base64.b64encode(response.data).decode("utf-8")
                                    await websocket.send(json.dumps({"type": "audio", "data": b64}))
                                except Exception as e:
                                    logger.error(f"[{client_id}] Error forwarding audio: {e}")

                            sc = response.server_content

                            # Live transcript (optional)
                            if sc and getattr(sc, "output_transcription", None):
                                text = sc.output_transcription.text
                                if text:
                                    await websocket.send(json.dumps({"type": "text", "data": text}))

                            # Turn boundary + readiness cue
                            if sc and getattr(sc, "turn_complete", False):
                                await websocket.send(json.dumps({"type": "turn_complete"}))
                                await websocket.send(json.dumps({"type": "ready_for_input"}))

                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        logger.error(f"[{client_id}] Model receiver error: {e}")
                    finally:
                        logger.info(f"[{client_id}] Model receiver: END")

                # ---------- Start tasks & supervise ----------
                ws_task = asyncio.create_task(ws_reader(), name=f"ws_reader:{client_id}")
                send_task = asyncio.create_task(audio_sender(), name=f"audio_sender:{client_id}")
                recv_task = asyncio.create_task(model_receiver(), name=f"model_receiver:{client_id}")

                # Wait until either the websocket closes OR the Gemini stream ends.
                done, pending = await asyncio.wait(
                    [ws_task, recv_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # Cancel remaining tasks and drain
                for t in (ws_task, send_task, recv_task):
                    if not t.done():
                        t.cancel()
                await asyncio.gather(ws_task, send_task, recv_task, return_exceptions=True)

                logger.info(f"[{client_id}] Conversation cleanup completed")

        except Exception as e:
            logger.error(f"[{client_id}] process_audio error: {e}")
        finally:
            logger.info(f"[{client_id}] process_audio: END")


async def main():
    server = LiveAPIWebSocketServer()
    await server.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Exiting via KeyboardInterrupt...")
    except Exception as e:
        logger.error(f"Unhandled exception in main: {e}")
        import traceback
        traceback.print_exc()
