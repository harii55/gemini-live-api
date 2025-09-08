# WebSocket API Specification for Real-Time Audio AI Communication

## Overview
Real-time bidirectional audio communication API with AI assistant. Send audio, receive AI responses and text transcriptions.

## Connection Details

**Endpoint**: `ws://localhost:8765`
**Protocol**: WebSocket (RFC 6455)

## Quick Start Flow

1. **Connect** to WebSocket endpoint
2. **Wait** for `{"type": "ready"}` message
3. **Send** raw PCM audio as binary frames
4. **Receive** AI audio responses as binary frames + text transcriptions as JSON
5. **Handle** control messages for turn management

## Audio Format Requirements

### Send Audio (Android → Server)
- **Format**: PCM 16-bit signed, little-endian
- **Sample Rate**: 16,000 Hz
- **Channels**: Mono
- **Frame Size**: 4096 samples (8192 bytes) recommended
- **Transmission**: Binary WebSocket frames (not JSON)

### Receive Audio (Server → Android)
- **Format**: PCM 16-bit signed
- **Sample Rate**: 24,000 Hz (typical)
- **Channels**: Mono
- **Transmission**: Binary WebSocket frames

## Message Protocol

### Binary Messages (Audio Data)
- **Client → Server**: Raw PCM audio bytes
- **Server → Client**: Raw PCM audio bytes
- **Detection**: `instanceof ArrayBuffer` or `instanceof Blob`

### JSON Messages (Control)
All control messages are JSON strings sent as text WebSocket frames.

#### Server → Client Control Messages

**Ready Signal**
```json
{"type": "ready"}
```
*Sent once after connection. Start sending audio after receiving this.*

**Text Transcription**
```json
{"type": "text", "data": "AI response text"}
```
*Real-time transcription of AI speech. Display to user.*

**Turn Complete**
```json
{"type": "turn_complete"}
```
*AI finished speaking. Re-enable user input.*

**Response Interrupted**
```json
{"type": "interrupted", "data": "Response interrupted by user input"}
```
*Stop audio playback immediately, clear queue.*

**Session ID** (Optional)
```json
{"type": "session_id", "data": "session_identifier"}
```
*Store for session management.*

#### Client → Server Control Messages

**End Turn Signal** (Optional)
```json
{"type": "end"}
```
*Indicate user finished speaking.*

**Text Input** (Optional)
```json
{"type": "text", "data": "user text"}
```
*Send text instead of audio.*

## Error Handling

### Connection Issues
- **Connection timeout**: 5 seconds, implement retry with exponential backoff
- **Disconnection**: Auto-reconnect on unexpected close codes
- **Max retries**: 3 attempts

### Message Handling
- **Unknown JSON message types**: Ignore gracefully
- **Invalid JSON**: Log error, continue processing
- **Binary data errors**: Display error to user

## Performance Notes

- **Bandwidth**: ~32KB/sec upload, ~48KB/sec download
- **Latency**: <100ms for real-time experience
- **Buffer size**: 4096 samples (256ms) for optimal performance
- **Memory**: Queue audio chunks for smooth playback

## Testing Checklist

✅ **Connection**: Receives ready message after connect  
✅ **Audio Send**: Can send 16kHz PCM as binary frames  
✅ **Audio Receive**: Can play 24kHz PCM from binary frames  
✅ **Text Display**: Shows real-time transcriptions  
✅ **Turn Management**: Handles turn_complete properly  
✅ **Interruption**: Stops playback on interrupted signal  
✅ **Reconnection**: Recovers from connection drops

## Sample Audio Test Data

**Input PCM**: 16-bit signed integers, -32768 to 32767 range  
**Output PCM**: 16-bit signed integers, decode directly to AudioTrack  
**Test chunk**: 8192 bytes = 4096 samples = 256ms at 16kHz

---

**API Version**: 1.0  
**Protocol**: Binary audio + JSON control messages  
**Transport**: WebSocket over TCP
