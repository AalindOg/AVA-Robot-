"""
AVA Server v2.0 — 6-Layer Architecture
Audio → VAD → Whisper → Storage → Obsidian → Dashboard
(File-based storage pending Neo4j auth fix)
"""
import asyncio, re, os, json
from datetime import datetime
from pathlib import Path
from typing import Optional
import wave
import numpy as np
import websockets

# Import AVA intelligence engine
from intel_engine import ingest_intelligence, get_intel_briefing, search_intel

# ─── Config ─────────────────────────────────────────────────
WS_HOST, WS_PORT = "0.0.0.0", 5013
INTEL_DB = Path(__file__).parent / "intel.db"
OBSIDIAN_VAULT = Path.home() / "Documents" / "AVA_Vault"
OBSIDIAN_VAULT.mkdir(parents=True, exist_ok=True)
RECORDINGS_DIR = Path(__file__).parent / "recordings"
RECORDINGS_DIR.mkdir(exist_ok=True)
DB_PATH = Path(__file__).parent / "ava_graph.json"

SAMPLE_RATE, CHANNELS, SAMPLE_WIDTH = 16000, 1, 2
VAD_THRESHOLD_DB = -35.0
VAD_MIN_MS, VAD_MAX_SILENCE_MS = 400, 700

# ─── Graph DB (JSON → Neo4j later) ─────────────────────────
def load_db():
    if DB_PATH.exists():
        return json.loads(DB_PATH.read_text())
    return {"people": {}, "meetings": [], "transcripts": []}

def save_db(db):
    DB_PATH.write_text(json.dumps(db, indent=2, default=str))

graph = load_db()

def get_or_create_person(name: str) -> dict:
    if name not in graph["people"]:
        graph["people"][name] = {
            "name": name, "first_seen": datetime.now().isoformat(),
            "meeting_count": 0, "last_seen": None
        }
    return graph["people"][name]

def record_meeting(person_name: str, transcript: str) -> str:
    mid = datetime.now().strftime("%Y%m%d%H%M%S")
    ts = datetime.now().isoformat()
    p = get_or_create_person(person_name)
    p["meeting_count"] += 1
    p["last_seen"] = ts
    meeting = {"id": mid, "person": person_name, "timestamp": ts, "transcript": transcript[:2000]}
    graph["meetings"].append(meeting)
    graph["transcripts"].append({"id": mid, "text": transcript, "ts": ts, "person": person_name})
    save_db(graph)
    # Obsidian note
    filename = OBSIDIAN_VAULT / f"Meeting_{ts[:10]}_{person_name.replace(' ', '_')}.md"
    content = f"""---
date: {ts}
person: {person_name}
meeting_id: {mid}
---
# Meeting: {person_name}

**Date:** {ts[:10]}

## Transcript
{transcript}

## Auto-Notes
- Meeting #{p['meeting_count']} with {person_name}
- Duration: {len(transcript.split())} words
"""
    filename.write_text(content)
    return mid

# ─── Whisper ─────────────────────────────────────────────────
_whisper = None
def get_whisper():
    global _whisper
    if _whisper is None:
        import whisper
        _whisper = whisper.load_model("tiny.en")
    return _whisper

# ─── Audio Utils ────────────────────────────────────────────
def pcm_to_numpy(pcm): return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
def rms_db(audio): return 20 * np.log10(max(np.sqrt(np.mean(audio**2)), 1e-10))

# ─── NLP ─────────────────────────────────────────────────────
def extract_person(transcript: str) -> Optional[str]:
    text = transcript.strip()
    for pattern in [
        r"(?:this is|meet)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        r"(?:my name is|i'm|i am)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        r"(?:hi|hey|hello)[,.]?\s*(?:i'm|i am)\s+([A-Z][a-z]+)",
    ]:
        m = re.search(pattern, text)
        if m: return m.group(1).strip()
    return None

# ─── Audio Session ──────────────────────────────────────────
class AudioSession:
    def __init__(self, cid):
        self.cid = cid; self.buf = bytearray()
        self.speaking = False; self.last_voice = None
    def ingest(self, chunk):
        self.buf.extend(chunk)
        db = rms_db(pcm_to_numpy(chunk))
        if db > VAD_THRESHOLD_DB:
            self.speaking = True; self.last_voice = time.time()
        elif self.speaking and self.last_voice:
            silence = (time.time() - self.last_voice) * 1000
            if silence > VAD_MAX_SILENCE_MS and len(self.buf) > (SAMPLE_RATE*SAMPLE_WIDTH*VAD_MIN_MS//1000):
                return self.flush()
    def flush(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = RECORDINGS_DIR / f"ava_{ts}.wav"
        with wave.open(str(path), "wb") as w:
            w.setnchannels(CHANNELS); w.setsampwidth(SAMPLE_WIDTH)
            w.setframerate(SAMPLE_RATE); w.writeframes(self.buf)
        size = path.stat().st_size
        self.buf.clear(); self.speaking = False; self.last_voice = None
        print(f"[AUDIO] {path.name} ({size}B)")
        return path

# ─── WebSocket ───────────────────────────────────────────────
async def handle(ws):
    session = AudioSession(str(ws.remote_address[1]))
    print(f"[+] AVA {session.cid}")
    await ws.send(json.dumps({"type":"server_hello","version":"2.0"}))
    try:
        async for msg in ws:
            if isinstance(msg, bytes):
                result = session.ingest(msg)
                if result: await process(ws, result)
            else:
                try:
                    data = json.loads(msg)
                    t = data.get("type","")
                    if t == "device_hello": print(f"[BOARD] {data.get('device')}")
                    elif t == "gesture": await ws.send(json.dumps({"type":"ack","gesture":"tap"}))
                except: pass
    except websockets.exceptions.ConnectionClosed:
        pass
    print(f"[-] AVA {session.cid}")

async def process(ws, wav_path):
    try:
        w = get_whisper()
        result = w.transcribe(str(wav_path), fp16=False)
        text = result["text"].strip()
        if not text or len(text) < 3: return
        print(f"[→] \"{text}\"")
        await ws.send(json.dumps({"type":"transcript","text":text}))

        person = extract_person(text)
        if person:
            mid = record_meeting(person, text)
            await ws.send(json.dumps({"type":"person_detected","name":person,"meeting_id":mid,
                                       "count":graph['people'][person]['meeting_count']}))
            print(f"[PERSON] {person} (meeting #{graph['people'][person]['meeting_count']})")
        else:
            # Unknown speaker
            ts = datetime.now().isoformat()
            graph["transcripts"].append({"id": ts, "text": text, "ts": ts, "person": "unknown"})
            save_db(graph)

        # Sync to dashboard people.json
        sync_people_json()

    except Exception as e:
        print(f"[ERR] {e}")

def sync_people_json():
    """Export people data for dashboard API"""
    people = []
    for name, p in graph["people"].items():
        people.append({
            "name": name, "role": p.get("role", ""),
            "met_at": p.get("first_seen", ""),
            "meetings": p.get("meeting_count", 0),
            "notes": f"Met {p['meeting_count']} times, last seen {p.get('last_seen', 'N/A')[:10]}"
        })
    with open(Path(__file__).parent / "people.json", "w") as f:
        json.dump({"people": people, "conversations": [], "transcripts": []}, f)

async def main():
    print(f"╔══════════════════════════════════════════════╗")
    print(f"║   AVA v2.0  —  6-Layer Architecture           ║")
    print(f"║   WS: {WS_HOST}:{WS_PORT}     Obsidian: {OBSIDIAN_VAULT.name}")
    print(f"╚══════════════════════════════════════════════╝")
    async with websockets.serve(handle, WS_HOST, WS_PORT):
        await asyncio.Future()

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: print("\n[DONE]")
