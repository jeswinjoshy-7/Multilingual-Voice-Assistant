import os
import io
import wave
import requests
import asyncio
from groq import Groq
from murf import Murf
from dotenv import load_dotenv
from urllib.parse import quote # Import for URL encoding

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse
from typing import IO

# --- Configuration & Initialization ---
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MURF_API_KEY = os.getenv("MURF_API_KEY")
MURF_VOICE_ID = os.getenv("MURF_VOICE_ID")

if not all([GROQ_API_KEY, MURF_API_KEY, MURF_VOICE_ID]):
    print("FATAL ERROR: Missing one or more API keys/Voice ID in .env file.")
    exit(1)

GROQ_LLM_MODEL = "llama-3.1-8b-instant" 
GROQ_STT_MODEL = "whisper-large-v3" 
RATE = 16000 

app = FastAPI(title="Stable Voice Agent Backend")
groq_client = Groq(api_key=GROQ_API_KEY)
murf_client = Murf(api_key=MURF_API_KEY)

# Set CORS to allow React frontend connection
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Diagnostic Function ---

def check_api_status():
    """Performs a minimal check on all APIs used to catch auth/ID errors on startup."""
    try:
        groq_client.models.list() 
        print("DEBUG: Groq API status: OK")
    except Exception as e:
        print(f"FATAL DEBUG: Groq API Failed to authenticate or list models. Error: {e}")
        raise RuntimeError("Groq API Authentication failed on startup.")

    try:
        murf_client.text_to_speech.generate(
            text="hello", voice_id=MURF_VOICE_ID, format="WAV"
        )
        print(f"DEBUG: Murf API status: OK (Voice ID: {MURF_VOICE_ID} is valid)")
    except Exception as e:
        print(f"FATAL DEBUG: Murf API Failed. Check MURF_VOICE_ID and MURF_API_KEY. Error: {e}")
        raise RuntimeError("Murf API/Voice Check failed on startup.")


@app.on_event("startup")
def startup_event():
    check_api_status()


# --- AI Pipeline Functions ---

def transcribe_audio(audio_file: IO[bytes]):
    """Transcribes audio using Groq's Whisper API."""
    try:
        audio_file.seek(0)
        transcript = groq_client.audio.transcriptions.create(
            model=GROQ_STT_MODEL,
            file=audio_file,
        )
        return transcript.text
    except Exception as e:
        print(f"STT Error: {e}")
        raise HTTPException(status_code=500, detail="Transcription failed. Groq API returned an error.")

def get_llm_response(text: str):
    """Gets LLM response from Groq (Hindi/English optimized)."""
    system_prompt = (
        "You are a highly accurate and professional voice agent. Your supported languages are English and Hindi. "
        "1. Analyze the user's input language. If it is Hindi, respond in Hindi. Otherwise, assume English. "
        "2. Keep responses concise (Max 40 words) and professional."
    )
    
    response = groq_client.chat.completions.create(
        model=GROQ_LLM_MODEL,
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": text}]
    )
    return response.choices[0].message.content

def generate_tts(text: str):
    """Generates Murf TTS audio and returns raw WAV bytes."""
    try:
        response = murf_client.text_to_speech.generate(
            text=text,
            voice_id=MURF_VOICE_ID, 
            format="WAV",
        )
        audio_url = response.audio_file
        
        audio_data = requests.get(audio_url).content
        return audio_data
    except Exception as e:
        print(f"TTS Error (Murf): {e}")
        raise HTTPException(status_code=500, detail="TTS generation failed.")

# --- FastAPI Endpoint ---

@app.post("/voice_turn")
async def handle_voice_turn(audio_file: UploadFile = File(...)):
    """Handles the full voice turn: STT -> LLM -> TTS."""
    
    # 1. Input Validation
    if audio_file.content_type not in ["audio/wav", "audio/webm"]: 
        raise HTTPException(status_code=400, detail=f"Invalid audio format. Expected audio/wav or audio/webm.")
        
    # 2. Read audio content
    audio_content = await audio_file.read()
    
    # 3. Transcribe
    audio_io = io.BytesIO(audio_content)
    audio_io.name = "input.wav"
    transcript = await asyncio.to_thread(transcribe_audio, audio_io)
    
    # CRITICAL FIX: Ensure no leading/trailing whitespace is passed to the LLM
    cleaned_transcript = transcript.strip() 

    if not cleaned_transcript:
        raise HTTPException(status_code=400, detail="No clear speech detected or transcribed.")

    # 4. Get LLM Response
    llm_response = await asyncio.to_thread(get_llm_response, cleaned_transcript)
    
    # 5. Generate TTS Audio
    llm_response_stripped = llm_response.strip() # Strip response before TTS and headers
    audio_bytes = await asyncio.to_thread(generate_tts, llm_response_stripped)
    
    # 6. Prepare Headers (CRITICAL FIX: Encoding)
    
    # Use URL encoding for the LLM response to guarantee ASCII safety in headers
    encoded_llm_response = quote(llm_response_stripped, safe='') 
    
    # Use ASCII-safe version of transcript for the header (and strip again for absolute safety)
    ascii_transcript = cleaned_transcript.encode('ascii', 'ignore').decode('ascii').strip()


    return StreamingResponse(
        io.BytesIO(audio_bytes),
        media_type="audio/wav",
        headers={
            "X-Transcript": ascii_transcript, 
            "X-Response-Text-Encoded": encoded_llm_response 
        }
    )

if __name__ == "__main__":
    import uvicorn
    # RUN COMMAND: uvicorn server:app --host 127.0.0.1 --port 8000 --reload
    uvicorn.run(app, host="127.0.0.1", port=8000)
