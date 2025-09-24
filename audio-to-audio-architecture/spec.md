
# Backend WebSocket API (backend-only)

Endpoint: ws://localhost:8765

Purpose: This file documents only what the backend expects from a client and what the backend will send back. Use this as the single-source protocol reference for Android or other frontends.

---

## 1) Handshake
- Connect to: ws://localhost:8765
- Immediately after connection the server sends a text JSON message:

	{"type": "ready"}

- Wait for this message before sending any audio.

## 2) What the backend expects (client → server)

- Audio (binary WebSocket frames):
	- Encoding: PCM 16-bit signed little-endian (PCM16LE)
	- Channels: mono
	- Sample rate: 16000 Hz (16 kHz)
	- Transport: raw bytes in binary WebSocket frames (no JSON wrapper, no base64)
	- Recommended chunk size: several thousand samples per frame (example: 4096 samples / 8192 bytes) for low latency

- Control (text JSON frames):
	- {"type": "end"}
		- Sent by client to indicate end of the user's audio for the current turn (e.g., PTT release or VAD end).
	- Optional: {"type":"text","data":"..."}
		- Send only if you want to provide a text-only user input (not required for audio-only flows).

## 3) What the backend sends (server → client)

- Binary frames:
	- Raw PCM16LE audio bytes produced by the model.
	- Sample rate: 24000 Hz (24 kHz)
	- Channels: mono

- Text frames (JSON events):
	- {"type":"ready"} — initial ready message
	- {"type":"text","data":"..."} — streaming transcription or transcript updates
	- {"type":"turn_complete"} — model finished responding for current turn
	- {"type":"interrupted","data":"<reason>"} — response interrupted; discard pending playback
	- {"type":"session_id","data":"<id>"} — optional session/resumption id

Notes: treat any binary frame as audio; treat any text frame as JSON control and parse by the `type` field.

## 4) Frontend responsibilities (must implement)

- Wait for the initial {"type":"ready"} message before sending audio.
- Capture audio and ensure it matches backend expectations:
	- Produce PCM16LE, mono, resampled to 16000 Hz before sending.
	- If device records at a different sample rate, downsample client-side to 16 kHz.
- Send captured audio as binary WebSocket frames (raw bytes). Do NOT base64-encode or JSON-wrap audio data.
- When the user finishes speaking (PTT release or VAD end) send {"type":"end"} as a text JSON frame.
- Receive and handle server frames:
	- Binary frames: queue/play as PCM16LE @ 24 kHz.
	- Text frames: parse JSON and handle by `type` (ready, text, turn_complete, interrupted, session_id).
- Playback:
	- Configure playback path for PCM16LE @ 24000 Hz, mono (e.g., Android AudioTrack sampleRate=24000)
	- Use a small FIFO/jitter buffer to smooth incoming audio before playback.
	- On {"type":"interrupted"}: stop playback and clear the buffer immediately.
- Transcription UI:
	- Accept multiple {"type":"text"} partial updates; show or concatenate partials per your UI design.
- Session & reconnection:
	- Persist session_id if provided (optional)
	- Implement reconnect with exponential backoff; server will clean up on disconnect.

## 5) Example minimal flows

- Typical push-to-talk (PTT):
	1. Connect → wait for {"type":"ready"}
	2. PTT press → start capture → resample to 16 kHz → send PCM16LE binary frames
	3. PTT release → stop capture → send {"type":"end"}
	4. Receive server binary audio → play as PCM16LE @ 24 kHz
	5. On {"type":"turn_complete"} re-enable PTT

- Interrupt:
	- Server sends {"type":"interrupted","data":"<reason>"} → clear playback queue and stop current playback immediately.

## 6) Edge cases & recommendations

- Always confirm server readiness with {"type":"ready"} before streaming audio.
- Treat binary frames strictly as audio bytes; do not attempt to parse them as JSON.
- If you require a different audio format, update backend; current implementation expects PCM16LE only.
- Implement a maximum size for incoming audio buffer to avoid unbounded memory growth on long responses.

---

If you want a compact Kotlin example for capture → resample → WebSocket send and playback with AudioTrack, tell me and I will add it as a separate file (example client code).

