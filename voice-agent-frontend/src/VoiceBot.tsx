import React, { useState, useRef, useEffect, useCallback } from 'react';
import styles from './VoiceBot.module.css';

// --- Configuration Constants ---
const BACKEND_URL = "http://127.0.0.1:8000/voice_turn"; 
const MAX_RECORD_TIME = 10000;
const SAMPLE_RATE = 44100; 
const BUFFER_SIZE = 1024; // WARNING FIX: Retained because it's used in createScriptProcessor

// --- TypeScript Definitions ---
interface LogEntry {
    type: 'user' | 'agent' | 'system' | 'error';
    message: string;
    timestamp: string;
}

type CanvasRefType = HTMLCanvasElement | null;

declare global {
    interface Window { webkitAudioContext: typeof AudioContext; }
}
const AudioContextClass = window.AudioContext || window.webkitAudioContext;


// --- Helper Function: Local Volume Analyzer ---
const getVolumeLevel = (analyser: AnalyserNode, dataArray: Uint8Array): number => {
    analyser.getByteFrequencyData(dataArray);
    const average = dataArray.reduce((a, b) => a + b) / dataArray.length;
    return Math.min(1, average / 128); 
};


// --- React Component ---
const VoiceBot: React.FC = () => {
    const [status, setStatus] = useState("Ready, click to record."); 
    const [isRecording, setIsRecording] = useState(false);
    const [logEntries, setLogEntries] = useState<LogEntry[]>([]);
    const [volume, setVolume] = useState(0);

    // Refs for persistent objects
    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const audioChunksRef = useRef<Blob[]>([]);
    const audioPlayerRef = useRef<HTMLAudioElement | null>(null);
    
    // Refs for local audio analysis
    const audioContextRef = useRef<AudioContext | null>(null);
    const analyserRef = useRef<AnalyserNode | null>(null);
    const canvasRef = useRef<CanvasRefType>(null); // Main canvas ref
    // FIX: Initialized with null and correctly typed
    const visualizationIntervalRef = useRef<number | null>(null); 

    // --- Utility Functions ---

    const addLog = useCallback((type: LogEntry['type'], message: string) => {
        setLogEntries(prev => [...prev, { type, message, timestamp: new Date().toLocaleTimeString() }]);
    }, []);

    // Setup the audio player on mount
    useEffect(() => {
        audioPlayerRef.current = new Audio();
        audioPlayerRef.current.crossOrigin = "anonymous";
        return () => {
            cleanupAudioProcessor(); // Ensure cleanup happens on unmount
        };
    }, []);

    // --- Audio Processor Cleanup ---
    const cleanupAudioProcessor = useCallback(() => {
        // FIX: Casting interval to number before clearing
        if (visualizationIntervalRef.current !== null) {
            clearInterval(visualizationIntervalRef.current as unknown as number);
            visualizationIntervalRef.current = null;
        }
        if (audioContextRef.current) {
            audioContextRef.current.close().catch(console.error);
            audioContextRef.current = null;
        }
        setVolume(0);
    }, []);


    // --- Visualization Drawing Loop (FIXED) ---
    const drawVisualizer = useCallback(() => {
        // FIX: Use the existing canvasRef.current, do not call useRef() here!
        const canvas = canvasRef.current;
        if (!canvas) return; 

        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        
        const centerX = canvas.width / 2;
        const centerY = canvas.height / 2;
        const scale = 1 + (volume * 0.05); 

        ctx.clearRect(0, 0, canvas.width, canvas.height);
        
        ctx.beginPath();
        ctx.strokeStyle = `rgba(255, 255, 255, ${isRecording ? 0.4 : 0.1})`;
        ctx.lineWidth = 4;
        ctx.arc(centerX, centerY, 90 * scale, 0, 2 * Math.PI);
        ctx.stroke();

        ctx.beginPath();
        ctx.fillStyle = isRecording 
            ? `rgba(0, 255, 204, ${0.1 + volume * 0.2})`
            : 'rgba(0, 123, 255, 0.1)'; 
        ctx.arc(centerX, centerY, 80, 0, 2 * Math.PI);
        ctx.fill();

        requestAnimationFrame(drawVisualizer);
    }, [isRecording, volume]);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (canvas) {
            canvas.width = 200;
            canvas.height = 200;
        }
        
        // Final Fix for visualization drawing loop
        const animationId = requestAnimationFrame(drawVisualizer);

        return () => {
            cancelAnimationFrame(animationId);
        };
    }, [drawVisualizer]);


    const startRecording = async () => {
        try {
            // 1. Get Microphone Stream
            const stream = await navigator.mediaDevices.getUserMedia({ 
                audio: { sampleRate: SAMPLE_RATE, channelCount: 1 } 
            });
            
            // 2. Setup Local Audio Processor for Visualization
            audioContextRef.current = new AudioContextClass({ sampleRate: SAMPLE_RATE });
            analyserRef.current = audioContextRef.current.createAnalyser();
            const source = audioContextRef.current.createMediaStreamSource(stream);
            
            source.connect(analyserRef.current);
            analyserRef.current.fftSize = 256;
            const bufferLength = analyserRef.current.frequencyBinCount;
            const dataArray = new Uint8Array(bufferLength);

            // 3. Start Volume Monitoring Loop (for the pulse effect)
            const updateVolume = () => {
                if (analyserRef.current) {
                    const level = getVolumeLevel(analyserRef.current, dataArray);
                    setVolume(level);
                }
            };
            // FIX: Explicitly cast the result of setInterval to 'number'
            visualizationIntervalRef.current = setInterval(updateVolume, 50) as unknown as number; 
            

            // 4. Initialize MediaRecorder
            const recorder = new MediaRecorder(stream, { mimeType: 'audio/wav' }); 
            
            recorder.ondataavailable = (event) => {
                audioChunksRef.current.push(event.data);
            };

            recorder.onstop = () => {
                processAudio();
                stream.getTracks().forEach(track => track.stop());
                cleanupAudioProcessor();
            };

            mediaRecorderRef.current = recorder;
            recorder.start();
            
            setIsRecording(true);
            setStatus("Listening... Speak clearly.");
            addLog('system', 'Recording started.');

            // Set a safety timeout
            setTimeout(() => {
                if (recorder.state === 'recording') {
                    recorder.stop();
                }
            }, MAX_RECORD_TIME); 

        } catch (error) {
            console.error("Microphone access failed:", error);
            setStatus("ERROR: Microphone Access Denied.");
            addLog('error', 'Microphone access denied. Ensure you are using HTTPS (via ngrok) or localhost.');
        }
    };

    const stopRecording = () => {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
            mediaRecorderRef.current.stop();
        }
        setIsRecording(false);
    };

    const processAudio = async () => {
        setStatus("Processing...");
        
        if (audioChunksRef.current.length === 0) {
            addLog('error', 'No audio recorded.');
            setStatus("Ready, click to record.");
            return;
        }

        // 1. Prepare Payload
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/wav' });
        const formData = new FormData();
        formData.append('audio_file', audioBlob, 'input.wav'); 

        try {
            const response = await fetch(BACKEND_URL, {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                 const errorDetail = await response.json().catch(() => ({detail: 'Unknown server error'}));
                 throw new Error(`HTTP Error: ${response.status} - ${errorDetail.detail}`);
            }

            // 2. Extract and log response information
            const transcript = response.headers.get('X-Transcript') || 'Transcription N/A.';
            const encodedResponseText = response.headers.get('X-Response-Text-Encoded') || '';
            const responseText = decodeURIComponent(encodedResponseText); 

            addLog('user', transcript);
            addLog('agent', responseText);

            // 3. Play the returned WAV audio data
            const audioBlobResponse = await response.blob();
            const audioUrl = URL.createObjectURL(audioBlobResponse);
            
            if (audioPlayerRef.current) {
                audioPlayerRef.current.src = audioUrl;
                audioPlayerRef.current.play();
                audioPlayerRef.current.onended = () => {
                    URL.revokeObjectURL(audioUrl);
                    setStatus("Ready, click to record.");
                };
            }

        } catch (error) {
            console.error("API Call Failed:", error);
            addLog('error', `Agent Communication Error: ${error instanceof Error ? error.message : String(error)}`);
            setStatus("API Error");
        }
    };

    const handleButtonClick = () => {
        if (isRecording) {
            stopRecording();
        } else if (!status.includes("Processing")) {
            startRecording();
        }
    };
    
    const buttonText = isRecording ? "Stop & Process" : (status.includes("Processing") ? "Processing..." : "Start Conversation");

    return (
        <div className={styles.voiceContainer}>
            <h1>Agentic Voice Assistant</h1>
            
            <div className={styles.visualizerWrapper}>
                {/* FIX: Use the canvasRef directly */}
                <canvas ref={canvasRef} 
                    // Dynamic scaling based on local volume or processing state
                    style={{ transform: `scale(${isRecording ? (1 + volume * 0.05) : 1})` }}
                    // Apply visual styling based on state
                    className={`${styles.canvasVisualizer} ${isRecording ? styles.pulsate : ''} ${status.includes("Processing") ? styles.spinner : ''}`} 
                /> 
                
                <button 
                    onClick={handleButtonClick}
                    // Button disabled when processing is active or error state
                    disabled={status.includes("Processing") || status.includes("Error")}
                    // Apply the pulse class to the button when actively recording
                    className={`${styles.circleButton} ${isRecording ? styles.pulse : ''}`}
                    style={{ 
                        // Enhance visual scale based on input volume
                        transform: isRecording ? `scale(${1 + volume * 0.1})` : 'scale(1)',
                    }}
                >
                    {buttonText}
                </button>
            </div>
            
            <p className={styles.statusText}>Status: {status}</p>

            <div className={styles.transcriptLog}>
                {logEntries.map((entry, index) => (
                    <p key={index} className={styles[`${entry.type}Message`]}>
                        <strong>[{entry.timestamp}] {entry.type.toUpperCase()}:</strong> {entry.message}
                    </p>
                ))}
            </div>
            <audio ref={audioPlayerRef} style={{ display: 'none' }} />
        </div>
    );
};

export default VoiceBot;
