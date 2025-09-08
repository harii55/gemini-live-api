import asyncio
import json
import base64
import os
from google import genai
from google.genai import types
from google.genai.types import (
    LiveConnectConfig,
    SpeechConfig,
    VoiceConfig,
    PrebuiltVoiceConfig,
)
# Common components
from common import (
    BaseWebSocketServer,
    logger,
    SYSTEM_INSTRUCTION,
)

MODEL = "gemini-live-2.5-flash-preview"
VOICE_NAME = "Puck"
SEND_SAMPLE_RATE = 16000

# API key (AI Studio)
api_key = os.getenv("GOOGLE_API_KEY")
if api_key:
    client = genai.Client(api_key=api_key)
    logger.info(f"Using AI Studio key (...{api_key[-6:]}, model={MODEL})")

# LiveAPI Configuration
logger.info(f"System instruction being sent to Gemini (Scholar):\n{SYSTEM_INSTRUCTION}")
config = LiveConnectConfig(
    response_modalities=["AUDIO"],
    output_audio_transcription=types.AudioTranscriptionConfig(),
    input_audio_transcription=types.AudioTranscriptionConfig(),
    speech_config=SpeechConfig(
        voice_config=VoiceConfig(
            prebuilt_voice_config=PrebuiltVoiceConfig(voice_name=VOICE_NAME)
        )
    ),
    system_instruction=SYSTEM_INSTRUCTION,
)

class LiveAPIWebSocketServer(BaseWebSocketServer):
    """WebSocket server for Scholar using Gemini LiveAPI (via API key)."""

    async def process_audio(self, websocket, client_id):
        # Store reference to client
        self.active_clients[client_id] = websocket

        logger.info(f"Starting audio processing for client {client_id}")

        # Connect to Gemini using LiveAPI
        async with client.aio.live.connect(model=MODEL, config=config) as session:
            async with asyncio.TaskGroup() as tg:
                # Create a queue for audio data from the client
                audio_queue = asyncio.Queue()

                # Task to process incoming WebSocket messages
                async def handle_websocket_messages():
                    async for message in websocket:
                        try:
                            # Check if message is binary (audio data) or text (control messages)
                            if isinstance(message, bytes):
                                # Handle binary audio data directly
                                await audio_queue.put(message)
                            else:
                                # Handle JSON control messages
                                data = json.loads(message)
                                if data.get("type") == "end":
                                    # Client is done sending audio for this turn
                                    logger.info("Received end signal from client")
                                elif data.get("type") == "text":
                                    # Handle text messages (not implemented in this simple version)
                                    logger.info(f"Received text: {data.get('data')}")
                        except json.JSONDecodeError:
                            logger.error("Invalid JSON message received")
                        except Exception as e:
                            logger.error(f"Error processing message: {e}")

                # Task to process and send audio to Gemini
                async def process_and_send_audio():
                    while True:
                        data = await audio_queue.get()

                        # Send the audio data to Gemini
                        await session.send_realtime_input(
                            media={
                                "data": data,
                                "mime_type": f"audio/pcm;rate={SEND_SAMPLE_RATE}",
                            }
                        )

                        audio_queue.task_done()

                # Task to receive and play responses
                async def receive_and_play():
                    while True:
                        input_transcriptions = []
                        output_transcriptions = []

                        async for response in session.receive():
                            # Get session resumption update if available
                            if response.session_resumption_update:
                                update = response.session_resumption_update
                                if update.resumable and update.new_handle:
                                    session_id = update.new_handle
                                    logger.info(f"New SESSION: {session_id}")
                                    # Send session ID to client
                                    session_id_msg = json.dumps({
                                        "type": "session_id",
                                        "data": session_id
                                    })
                                    await websocket.send(session_id_msg)

                            # Check if connection will be terminated soon
                            if response.go_away is not None:
                                logger.info(f"Session will terminate in: {response.go_away.time_left}")

                            server_content = response.server_content

                            # Handle interruption
                            if (hasattr(server_content, "interrupted") and server_content.interrupted):
                                logger.info("🤐 INTERRUPTION DETECTED")
                                # Just notify the client - no need to handle audio on server side
                                await websocket.send(json.dumps({
                                    "type": "interrupted",
                                    "data": "Response interrupted by user input"
                                }))

                            # Process model response
                            if server_content and server_content.model_turn:
                                for part in server_content.model_turn.parts:
                                    if part.inline_data:
                                        # Send raw PCM audio data directly as binary
                                        await websocket.send(part.inline_data.data)

                            # Handle turn completion
                            if server_content and server_content.turn_complete:
                                logger.info("✅ Gemini done talking")
                                await websocket.send(json.dumps({
                                    "type": "turn_complete"
                                }))

                            # Handle transcriptions
                            output_transcription = getattr(response.server_content, "output_transcription", None)
                            if output_transcription and output_transcription.text:
                                output_transcriptions.append(output_transcription.text)
                                # Send text to client
                                await websocket.send(json.dumps({
                                    "type": "text",
                                    "data": output_transcription.text
                                }))

                            input_transcription = getattr(response.server_content, "input_transcription", None)
                            if input_transcription and input_transcription.text:
                                input_transcriptions.append(input_transcription.text)

                        logger.info(f"Output transcription: {''.join(output_transcriptions)}")
                        logger.info(f"Input transcription: {''.join(input_transcriptions)}")

                # Start all tasks
                tg.create_task(handle_websocket_messages())
                tg.create_task(process_and_send_audio())
                tg.create_task(receive_and_play())

async def main():
    """Main function to start the server"""
    server = LiveAPIWebSocketServer()
    await server.start()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Exiting application via KeyboardInterrupt...")
    except Exception as e:
        logger.error(f"Unhandled exception in main: {e}")
        import traceback
        traceback.print_exc()
