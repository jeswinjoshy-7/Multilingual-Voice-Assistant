import os
import time
import pyaudio
import wave
import numpy as np
import requests
from groq import Groq
from murf import Murf
from dotenv import load_dotenv

# --- Configuration & Initialization ---

# 1. Load API keys from .env file
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MURF_API_KEY = os.getenv("MURF_API_KEY")
MURF_VOICE_ID = os.getenv("MURF_VOICE_ID")

# LLM Model for fast reasoning (Llama 3 is a solid choice for speed)
GROQ_LLM_MODEL = "llama-3.3-70b-versatile" 
GROQ_STT_MODEL = "whisper-large-v3" 

# Audio I/O settings
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000 
MIN_RECORD_SECONDS = 1.0 # Minimum audio required to process
SILENCE_THRESHOLD = 500  # Amplitude level below which audio is considered silence (adjust this!)
SILENCE_CHUNKS = int(RATE / CHUNK * 0.5) # Wait 0.5 seconds of silence before ending input
NO_SPEECH_TIMEOUT = 5 # Stop listening after 5 seconds if no voice is heard

WAVE_INPUT_FILENAME = "user_input.wav"
WAVE_OUTPUT_FILENAME = "murf_output.wav"

# 2. Client Initialization and Error Check
if not MURF_VOICE_ID or not GROQ_API_KEY or not MURF_API_KEY:
    print("FATAL ERROR: One or more critical API keys/Voice ID are missing or null.")
    print("Please ensure GROQ_API_KEY, MURF_API_KEY, and MURF_VOICE_ID are correctly set in your .env file.")
    exit()

try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    murf_client = Murf(api_key=MURF_API_KEY)
    p_audio = pyaudio.PyAudio()
except Exception as e:
    print(f"ERROR: Failed to initialize clients. Check your API keys and internet connection: {e}")
    exit()

# --- Core Utility Functions ---

def record_audio_to_file():
    """Records audio using silence detection to improve latency."""
    stream_mic = p_audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
    print("Agent: Listening... (Hindi/English only. Stop speaking to end turn)")
    
    frames = []
    silent_chunks_count = 0
    speaking_time = 0.0
    
    # Pre-record loop (runs until silence or timeout)
    while speaking_time < NO_SPEECH_TIMEOUT:
        data = stream_mic.read(CHUNK, exception_on_overflow=False)
        frames.append(data)
        
        # Convert audio data chunk to numpy array for volume check
        numpy_data = np.frombuffer(data, dtype=np.int16)
        volume = np.abs(numpy_data).max()
        
        if volume < SILENCE_THRESHOLD:
            silent_chunks_count += 1
            if silent_chunks_count > SILENCE_CHUNKS and speaking_time > MIN_RECORD_SECONDS:
                break # Silence detected and minimum speaking time passed
        else:
            silent_chunks_count = 0 # Reset silence counter if noise is detected
        
        speaking_time += CHUNK / RATE # Increment total time

    print("Agent: Done listening. Processing...")
    stream_mic.stop_stream()
    stream_mic.close()

    # Save audio to file only if some substantial audio was recorded
    if len(frames) * CHUNK / RATE < MIN_RECORD_SECONDS:
        print("Warning: Insufficient speech detected.")
        return None

    wf = wave.open(WAVE_INPUT_FILENAME, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(p_audio.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()
    return WAVE_INPUT_FILENAME

def play_wav_file(file_path):
    """Plays the generated audio file locally using PyAudio."""
    try:
        wf = wave.open(file_path, 'rb')
        stream_out = p_audio.open(format=p_audio.get_format_from_width(wf.getsampwidth()),
                                  channels=wf.getnchannels(),
                                  rate=wf.getframerate(),
                                  output=True)

        data = wf.readframes(CHUNK)
        while data:
            stream_out.write(data)
            data = wf.readframes(CHUNK)

        stream_out.stop_stream()
        stream_out.close()
        wf.close()
    except Exception as e:
        print(f"AUDIO PLAYBACK ERROR: Could not play file {file_path}. {e}")

# --- AI Pipeline Functions ---

def speech_to_text(audio_file):
    """Uses Groq's Whisper API endpoint for high-speed transcription."""
    try:
        with open(audio_file, "rb") as audio:
            transcript = groq_client.audio.transcriptions.create(
                model=GROQ_STT_MODEL,
                file=audio,
            )
            return transcript.text
    except Exception as e:
        print(f"STT Error (Groq): {e}")
        return "" 

def get_llm_response(text):
    """
    Uses the ultra-fast Groq LLM for multi-lingual reasoning.
    Prompt is now highly specialized for English and Hindi ONLY.
    """
    system_prompt = (
        "You are a highly accurate and professional voice agent. "
        "Your supported languages are **English (en)** and **Hindi (hi)**. "
        "**Marathi (mr) is NOT supported.** "
        "1. **STRICT ANALYSIS**: Analyze the user's input language. If it is Hindi, respond in Hindi. Otherwise, assume English and respond in English. "
        "2. **IDENTICAL RESPONSE**: Respond *naturally* and *fluently* **ONLY** in the determined language. "
        "3. **CODE-SWITCHING**: If the user mixes Hindi and English words, respond in the language that has the most words. "
        "4. Keep responses concise (Max 40 words) and professional. Do not add any extra commentary or apologies."
    )
    
    response = groq_client.chat.completions.create(
        model=GROQ_LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ]
    )
    return response.choices[0].message.content

def text_to_speech_and_play(text):
    """Uses Murf API for speech synthesis, downloads the audio, and plays it."""
    print(f"Agent Response (Text): {text}")
    print("Agent: Generating high-quality Murf audio...")
    
    try:
        response = murf_client.text_to_speech.generate(
            text=text,
            voice_id=MURF_VOICE_ID, 
            format="WAV", 
        )

        audio_url = response.audio_file
        audio_data = requests.get(audio_url).content
        
        with open(WAVE_OUTPUT_FILENAME, 'wb') as f:
            f.write(audio_data)

        print("Agent: Speaking...")
        play_wav_file(WAVE_OUTPUT_FILENAME)
        
        os.remove(WAVE_OUTPUT_FILENAME)

    except requests.exceptions.HTTPError as e:
        error_info = e.response.json()
        error_message = error_info.get('errorMessage', 'Unknown API Error')
        print(f"TTS Error (Murf): Status {e.response.status_code}. {error_message}")
        print(f"HINT: Check your Murf account status and ensure the text is not too long.")
        pass 
    except Exception as e:
        print(f"TTS Error (Murf): Failed to generate or play speech. Check network. {e}")
        pass 

# --- Main Application Loop ---

def run_agent_loop():
    print(f"--- 🎙️ AI Voice Agent (Groq + Murf AI) ---")
    print(f"LLM: {GROQ_LLM_MODEL} | Voice ID: {MURF_VOICE_ID}")
    print("Agent is ready. Speak after the 'Listening...' prompt. Press Ctrl+C to exit.")

    while True:
        try:
            # 1. Capture User Audio (Low-latency turn detection)
            audio_file = record_audio_to_file()
            
            if audio_file is None:
                print("No clear speech detected. Trying again.")
                continue

            # 2. Transcribe (STT)
            user_text = speech_to_text(audio_file)
            
            # Clean up input file
            if os.path.exists(audio_file):
                os.remove(audio_file)
            
            if not user_text.strip():
                print("Transcribed text was empty. Trying again.")
                continue
                
            print(f"You (Transcribed): {user_text}")

            if user_text.strip().lower() in ["quit", "exit", "stop"]:
                break
            
            # 3. LLM Reasoning (Groq)
            llm_response = get_llm_response(user_text)
            
            # 4. Synthesize and Speak (Murf)
            text_to_speech_and_play(llm_response)

        except KeyboardInterrupt:
            print("\nShutting down agent...")
            break
        except Exception as e:
            print(f"An unexpected error occurred in the main loop: {e}")
            time.sleep(2)

    p_audio.terminate()

if __name__ == "__main__":
    run_agent_loop()
