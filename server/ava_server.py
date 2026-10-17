#!/usr/bin/env python3
"""
AVA Server — Phase 1
Receives PCM audio from ESP32-S3 via WebSocket, runs VAD + Whisper for transcription.
Architecture: Audio Stream → VAD → Whisper → Context → Memory (Neo4j / Obsidian)
"""

import asyncio
import json
import wave
import struct
import tempfile
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import websockets
import numpy as np

# ─── Config ─────────────────────────────────────────────────────────────────
WS_HOST = "0.0.0.0"
WS_PORT = 5013
RECORDINGS_DIR = Path(__file__).parent / "recordings"
RECORDINGS_DIR.mkdir(exist_ok=True)

# Audio params (must match firmware)
SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit

# VAD: simple energy-based (replace with Silero VAD later)
VAD_THRESHOLD_DB = -40.0
VAD_MIN_MS = 500       # minimum speech duration
VAD_MAX_SILENCE_MS = 800

# ─── State ──────────────────────────────────────────────────────────────────
clients = {}  # ws -> { "buffer": bytearray, "last_voice_ms": float, "speaking": bool }


# ─── Audio Utils ────────────────────────────────────────────────────────────
def pcm_to_numpy(pcm_bytes: bytes) -> np.ndarray:
    """Convert raw PCM s16le to float32 numpy array, normalized [-1, 1]."""
    samples = struct.unpack(f"<{len(pcm_bytes)//2}h", pcm_bytes)
    return np.array(samples, dtype=np.float32) / 32768.0


def rms_db(audio: np.ndarray) -> float:
    """Root-mean-square in dBFS."""
    rms = np.sqrt(np.mean(audio ** 2))
    return 20 * np.log10(max(rms, 1e-10))


# ─── Whisper (lazy load) ────────────────────────────────────────────────────
_whisper_model = None

def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        import whisper
        print("[Whisper] Loading model...")
        _whisper_model = whisper.load_model("base")  # ~74MB, works on CPU
        print("[Whisper] Model loaded.")
    return _whisper_model


def transcribe(path: Path) -> str:
    model = get_whisper_model()
    result = model.transcribe(str(path), language="en", fp16=False)
    return result["text"].strip()


# ─── Session Handling ───────────────────────────────────────────────────────
class AudioSession:
    def __init__(self, client_id: str):
        self.client_id = client_id
        self.buffer = bytearray()
        self.speaking = False
        self.last_voice_ms: Optional[float] = None
        self.session_start = time.time()

    def ingest(self, pcm_chunk: bytes) -> Optional[Path]:
        """Ingest audio chunk. Returns Path to saved WAV if utterance complete."""
        self.buffer.extend(pcm_chunk)
        audio = pcm_to_numpy(pcm_chunk)
        db = rms_db(audio)

        if db > VAD_THRESHOLD_DB:
            self.speaking = True
            self.last_voice_ms = time.time()
        else:
            if self.speaking and self.last_voice_ms:
                silence_ms = (time.time() - self.last_voice_ms) * 1000
                if silence_ms > VAD_MAX_SILENCE_MS and len(self.buffer) > (SAMPLE_RATE * SAMPLE_WIDTH * VAD_MIN_MS // 1000):
                    # Utterance complete
                    return self.flush_buffer()
        return None

    def flush_buffer(self) -> Path:
        """Save buffered audio to WAV and reset."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        path = RECORDINGS_DIR / f"ava_{self.client_id}_{ts}.wav"
        with wave.open(str(path), "wb") as w:
            w.setnchannels(CHANNELS)
            w.setsampwidth(SAMPLE_WIDTH)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(self.buffer)
        self.buffer.clear()
        self.speaking = False
        self.last_voice_ms = None
        print(f"[AUDIO] Saved {path.name} ({path.stat().st_size} bytes)")
        return path

    def force_flush(self) -> Optional[Path]:
        if len(self.buffer) > (SAMPLE_RATE * SAMPLE_WIDTH * 200 // 1000):  # 200ms min
            return self.flush_buffer()
        return None


# ─── WebSocket Handler ──────────────────────────────────────────────────────
async def handle_client(websocket):
    client_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
    session = AudioSession(client_id)
    clients[websocket] = session
    print(f"[CONN] {client_id} connected. Clients: {len(clients)}")

    try:
        async for message in websocket:
            if isinstance(message, bytes):
                # Audio chunk
                result = session.ingest(message)
                if result:
                    await process_utterance(websocket, result)
            else:
                # JSON control message
                try:
                    data = json.loads(message)
                    msg_type = data.get("type", "unknown")
                    if msg_type == "device_hello":
                        print(f"[HELLO] Device: {data.get('device', 'unknown')}")
                    elif msg_type == "gesture":
                        print(f"[GESTURE] {data.get('gesture')} from {client_id}")
                        await websocket.send(json.dumps({"type": "ack", "gesture": data.get("gesture")}))
                    elif msg_type == "status":
                        print(f"[STATUS] heap={data.get('heap')} rssi={data.get('rssi')}")
                except json.JSONDecodeError:
                    pass

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        # Flush any remaining audio
        remaining = session.force_flush()
        if remaining:
            await process_utterance(websocket, remaining)
        del clients[websocket]
        print(f"[CONN] {client_id} disconnected. Clients: {len(clients)}")


async def process_utterance(websocket, wav_path: Path):
    """Transcribe speech and optionally route to downstream pipeline."""
    print(f"[PROC] Transcribing {wav_path.name}...")
    try:
        text = transcribe(wav_path)
        print(f"[TRANSCRIPT] \"{text}\"")

        response = {
            "type": "transcript",
            "text": text,
            "timestamp": datetime.now().isoformat(),
            "audio_file": str(wav_path.name)
        }
        await websocket.send(json.dumps(response))

        # TODO: Feed into context engine → Neo4j / Obsidian
        # TODO: If wake phrase detected, set flag for proactive mode

    except Exception as e:
        print(f"[ERROR] Transcription failed: {e}")


# ─── Main ───────────────────────────────────────────────────────────────────
async def main():
    print(f"╔══════════════════════════════════════════════╗")
    print(f"║     AVA Server  —  Phase 1                   ║")
    print(f"║     WebSocket: ws://{WS_HOST}:{WS_PORT:<15}  ║")
    print(f"╚══════════════════════════════════════════════╝")
    async with websockets.serve(handle_client, WS_HOST, WS_PORT):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] AVA server stopped.")