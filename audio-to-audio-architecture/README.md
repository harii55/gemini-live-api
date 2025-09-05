# Audio-to-Audio Architecture

This folder contains a complete bidirectional audio-to-audio communication system using Google's Gemini Live API. The system enables real-time voice conversations with AI through (smart glasses or) any web client.

## Architecture Overview

- **Backend**: Python WebSocket server (`server.py`) that connects to Gemini Live API
- **Frontend**: JavaScript audio client (`audio-client.js`) with HTML interface
- **Communication**: Real-time bidirectional audio streaming via WebSocket

## Files

### Core Files (focus on server.py)
- `server.py` - **Main WebSocket server** for Scholar AI assistant
- `audio-client.js` - Frontend audio client class for recording/playback
- `index_for_server.html` - Web interface for testing
- `common.py` - Shared utilities and base classes
- `requirements.txt` - Python dependencies (minimal, server.py focused)


- `archive/` - Contains alternative implementations and unused files

## Features

- Real-time audio recording and streaming
- Bidirectional communication (speak and listen)
- WebSocket-based architecture
- Browser-based client interface

## Setup

### Prerequisites
- Python 3.8+ 
- Google API Key for Gemini Live API

### Installation

1. **Clone and navigate to project:**
   ```bash
   git clone <repository-url>
   cd audio-to-audio-architecture
   ```

2. **Create virtual environment (recommended):**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
   
   **Note:** Virtual environments (`venv/`, `.venv/`) are excluded from git via `.gitignore` as they're platform-specific and recreatable.

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set API key:**
   ```bash
   export GOOGLE_API_KEY="your_api_key_here"
   ```

5. **Run server:**
   ```bash
   python server.py
   ```

6. **Open frontend:**
   Open `index_for_server.html` in your browser and start recording!

## Usage

1. Set your `GOOGLE_API_KEY` environment variable
2. Install dependencies: `pip install -r requirements.txt`
3. Run server: `python server.py`
4. Open `index_for_server.html` in browser
5. Start recording and speak with Scholar
