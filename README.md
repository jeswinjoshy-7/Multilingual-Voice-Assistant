Multilingual Voice Assistant: Low-Latency Conversational AI
<img width="594" height="480" alt="Screenshot from 2025-10-02 21-19-57" src="https://github.com/user-attachments/assets/1fa8377d-a598-49ed-8e80-eaf912cdee99" />

A full-stack conversational AI agent engineered for stable, low-latency interactions in English and Hindi. The system uses an asynchronous REST architecture with high-performance inference services to deliver consistent performance under concurrent load.

Key features
- Low-latency LLM inference via Groq Llama 3.1 for responsive conversations.
- High-fidelity multilingual TTS using Murf AI for production-grade audio output.
- Robust HTTP POST workflow for the voice pipeline (STT → LLM → TTS) to prioritize stability over raw streaming.
- Interactive React frontend with Web Audio API for local input level visualization and playback.

Architecture
The backend orchestrates a sequential pipeline to ensure deterministic behavior and straightforward error handling. Blocking operations are isolated from the main event loop to preserve responsiveness under concurrency.
- Input audio is uploaded via multipart form data.
- STT transcribes speech to text.
- LLM generates the assistant response.
- TTS synthesizes the final audio reply.

Technology stack

| Component | Technology | Role |
| :-- | :-- | :-- |
| Backend / Orchestration | Python (FastAPI) | Handles REST endpoints, file uploads, pipeline orchestration, and concurrency control |
| Inference (LLM) | Groq Llama 3.1 8B Instant | Low-latency response generation with multilingual handling |
| STT | Groq Whisper Large V3 | High-accuracy transcription for English and Hindi |
| TTS | Murf AI | High-fidelity, human-like synthesis for the final audio |
| Frontend / UI | React, Web Audio API | Microphone control, local level analysis, visualization, and playback |

Architectural insights
- Stable HTTP POST interface selected over WebSocket streaming for the MVP to avoid head-of-line blocking and brittle client state during network jitter.
- Blocking tasks, such as external API calls and file I/O, are offloaded to worker threads to keep the event loop responsive.
- Non ASCII header values are safely encoded server-side to prevent Unicode errors for multilingual content.
- Development uses an HTTPS tunnel to satisfy browser security requirements for microphone access on non local origins.

Prerequisites
- Node.js and npm
- Python 3.10 or newer
- API keys for Groq and Murf AI
- Optional: ngrok for HTTPS tunneling during development

Repository setup

Clone and prepare the backend
```bash
git clone https://github.com/jeswinjoshy-7/Multilingual-Voice-Assistant.git
cd Multilingual_Voice_Assistant/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create backend environment file
```bash
# backend/.env
GROQ_API_KEY="gsk_..."
MURF_API_KEY="your_murf_key"

# Model selection
LLM_MODEL="llama-3.1-8b-instant"
STT_MODEL="whisper-large-v3"

# Voices and language defaults
TTS_VOICE_EN="en-US-default"    # replace with a valid Murf voice
TTS_VOICE_HI="hi-IN-kabir"      # replace with a valid Murf voice
DEFAULT_LANG="en"

# Server and security
PORT=8000
LOG_LEVEL="info"
CORS_ORIGINS="http://localhost:3000"
MAX_AUDIO_SECONDS=30
```

Install and prepare the frontend
```bash
cd ../frontend
npm install
# If using a build-time config, optionally create frontend/.env:
# VITE_API_BASE_URL="http://localhost:8000"
# VITE_API_TIMEOUT_MS="30000"
# VITE_ENABLE_LEVEL_METER="true"
```

### Running locally

Start the backend
```bash
cd backend
source venv/bin/activate
uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```

Start the frontend
```bash
cd frontend
npm start
```

Enable HTTPS for browser mic access in development
```bash
# from your ngrok directory
./ngrok http 3000
# Open the forwarded https URL in a browser to test the app
```
API reference

Base URL
- http://localhost:8000

Health
- GET /health  
  - 200: {"status":"ok","time":"<iso-8601>"}

End to end voice
- POST /api/v1/voice/complete  
  - Purpose: Accepts audio, runs STT → LLM → TTS, returns synthesized audio or JSON.
  - Request (multipart/form-data):
    - audio: file (wav mp3 webm)
    - lang: "en" or "hi" optional
    - session_id: string optional
    - format: "audio" optional query param to stream audio
  - Responses:
    - 200 application json:
      - {"transcript": string, "text": string, "lang": string, "duration_ms": number, "trace_id": string}
    - 200 audio mpeg:
      - binary stream with headers x-transcript and x-trace-id

STT only
- POST /api/v1/stt/transcribe  
  - Request: multipart/form-data with audio file and optional lang
  - Response 200: {"transcript": string, "lang": string, "trace_id": string}

LLM only
- POST /api/v1/llm/generate  
  - Request: {"prompt": string, "system": string optional, "lang": "en" or "hi" optional, "max_tokens": number optional}
  - Response 200: {"text": string, "usage": {"prompt_tokens": number, "completion_tokens": number}, "trace_id": string}

TTS only
- POST /api/v1/tts/synthesize  
  - Request: {"text": string, "lang": "en" or "hi", "voice_id": string optional}
  - Response 200: audio mpeg stream with x-trace-id header

Error format
- {"error": {"code": string, "message": string, "trace_id": string}}
- Common statuses: 400, 401, 413, 415, 429, 500

### Example requests

Health
```bash
curl -s http://localhost:8000/health
```

Voice end to end JSON
```bash
curl -s -X POST "http://localhost:8000/api/v1/voice/complete" \
  -F "audio=@sample.wav" -F "lang=en"
```

Voice end to end audio stream
```bash
curl -s -X POST "http://localhost:8000/api/v1/voice/complete?format=audio" \
  -F "audio=@sample.wav" --output reply.mp3
```

STT only
```bash
curl -s -X POST "http://localhost:8000/api/v1/stt/transcribe" \
  -F "audio=@sample.wav"
```

TTS only
```bash
curl -s -X POST "http://localhost:8000/api/v1/tts/synthesize" \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello there","lang":"en"}' --output tts.mp3
```

### Directory structure
```text
Multilingual_Voice_Assistant/
├── backend/
│   ├── server.py                # FastAPI app entrypoint (app = FastAPI)
│   ├── routers/                 # API routers (voice stt tts llm health)
│   ├── services/                # groq stt llm murf tts helpers
│   ├── core/                    # config logging middleware errors
│   ├── tests/                   # API and unit tests
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── src/
    │   ├── App.tsx
    │   ├── components/          # Recorder meter player
    │   └── lib/                 # API client utils
    ├── public/
    ├── package.json
    └── .env.example
```

Production notes
- Serve the backend with a production server such as Gunicorn with Uvicorn workers and tune worker count to CPU cores.
- Enforce request size limits, connection timeouts, and per IP rate limits at the ASGI or proxy layer.
- Emit structured logs with a correlation id across STT, LLM, and TTS calls to simplify debugging and latency analysis.
- Keep secrets out of the frontend and use a secrets manager for deployment environments.

Troubleshooting
- Unicode header errors in multilingual flows: ensure header values are properly encoded on the server before sending.
- Microphone blocked in browser: use HTTPS for the frontend origin during development and production.
- 413 Payload Too Large: reduce audio duration or increase server request size limits within safe bounds.
- 415 Unsupported Media Type: ensure the request uses multipart form data for file uploads.
- CORS errors: align backend allowed origins with the frontend URL and avoid wildcard credentials.

Roadmap
- Add streaming via WebSockets or server sent events for partial transcripts and incremental TTS.
- Integrate voice activity detection for smarter segmentation and lower latency.
- Expand language coverage and voice selection with dynamic locale routing.
- Add observability for traces and latency histograms with a hosted monitoring stack.
- Provide Docker and docker compose files for one command development and deployment.
