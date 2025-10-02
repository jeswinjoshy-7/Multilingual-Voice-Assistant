import requests
import time
import os
import subprocess
import json

# --- Configuration ---
# NOTE: This URL must match your FastAPI server's host and port
BACKEND_URL = "http://127.0.0.1:8000/voice_turn"
AUDIO_FILENAME = "cli_input.wav"
RECORD_DURATION = 5 # seconds (Adjust as needed)

# --- Functions ---

def record_audio(duration: int, filename: str):
    """Records audio using the SoX command-line utility."""
    print(f"\n--- Recording {duration} seconds of audio... Speak now! ---")
    
    # SoX command: records from default microphone, 1 channel, 16000Hz, 16-bit encoding
    cmd = ['rec', '-r', '16000', '-c', '1', '-b', '16', filename, 'trim', '0', str(duration)]
    
    try:
        # Run SoX command and check the return code
        subprocess.run(cmd, check=True)
        print("--- Recording finished. Processing... ---")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] SoX recording failed. Check microphone configuration/permissions. {e}")
        return False
    except FileNotFoundError:
        print("\n[FATAL ERROR] 'rec' command (SoX) not found. Please install SoX: 'sudo apt install sox libsox-fmt-all'")
        return False

def send_to_fastapi(filename: str):
    """Sends the recorded WAV file to the FastAPI endpoint."""
    
    # Check if the audio file is empty (SoX failed to capture voice)
    if os.path.getsize(filename) < 1024: # Check size > 1KB as a minimal safety
        print("\n[WARNING] Recorded file is nearly empty. Skipping API call.")
        return

    try:
        # Open the file for binary upload
        with open(filename, 'rb') as f:
            # Prepare the multipart/form-data payload
            files = {'audio_file': (filename, f, 'audio/wav')}
            
            # Send the request to your running FastAPI server
            response = requests.post(BACKEND_URL, files=files, timeout=60)
            
            if response.status_code == 200:
                # Success: Get transcription and response text from headers
                transcript = response.headers.get('X-Transcript', 'N/A')
                responseText = response.headers.get('X-Response-Text', 'N/A')
                
                print("\n[SUCCESS] AI Turn Completed.")
                print("-" * 30)
                print(f"  > **Transcription:** {transcript}")
                print(f"  > **AI Response:** {responseText}")
                
                # Optional: Save the returned audio for manual verification
                with open("agent_response.wav", 'wb') as out_f:
                    out_f.write(response.content)
                print("\n  > Agent audio saved to agent_response.wav")

            else:
                print(f"\n[HTTP ERROR] Status: {response.status_code}")
                try:
                    # Attempt to parse the error message sent from FastAPI
                    error_detail = response.json().get('detail', 'Unknown error.')
                    print(f"  > Detail: {error_detail}")
                except json.JSONDecodeError:
                    print(f"  > Raw Response: {response.text}")

    except requests.exceptions.ConnectionError:
        print(f"\n[CONNECTION ERROR] Could not connect to {BACKEND_URL}. Is your FastAPI server running?")
    except Exception as e:
        print(f"\n[GENERAL ERROR] Failed to process request: {e}")
        
    finally:
        # Clean up the recorded audio file
        if os.path.exists(filename):
            os.remove(filename)

# --- Main Execution ---
if __name__ == "__main__":
    # Ensure the virtual environment is active before running this script!
    if record_audio(RECORD_DURATION, AUDIO_FILENAME):
        send_to_fastapi(AUDIO_FILENAME)
