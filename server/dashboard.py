"""
AVA Dashboard — Web App
Shows people you've met, transcripts, and live audio status.
Runs on port 5014.
"""
import json
import asyncio
import websockets
from pathlib import Path
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
import threading
import os

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

# In-memory state (will persist to Neo4j/JSON later)
people_db = {
    "people": [],
    "conversations": [],
    "transcripts": []
}

PEOPLE_JSON = Path(__file__).parent / "people.json"

def load_people():
    if PEOPLE_JSON.exists():
        with open(PEOPLE_JSON) as f:
            data = json.load(f)
            people_db.update(data)

def save_people():
    with open(PEOPLE_JSON, "w") as f:
        json.dump(people_db, f, indent=2)

load_people()

class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self):
        if self.path == "/api/people":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(people_db).encode())
        elif self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "server": "online",
                "people_count": len(people_db["people"]),
                "conversations_count": len(people_db["conversations"]),
                "last_updated": datetime.now().isoformat()
            }).encode())
        elif self.path == "/" or self.path == "/index.html":
            self.path = "/index.html"
            return super().do_GET()
        else:
            return super().do_GET()

    def do_POST(self):
        if self.path == "/api/people":
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            try:
                person = json.loads(body)
                person["id"] = len(people_db["people"]) + 1
                person["added"] = datetime.now().isoformat()
                people_db["people"].append(person)
                save_people()
                self.send_response(201)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "person": person}).encode())
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())

def run_dashboard(host="0.0.0.0", port=5014):
    server = HTTPServer((host, port), DashboardHandler)
    print(f"[Dashboard] http://{host}:{port}")
    server.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=run_dashboard, daemon=True).start()
    asyncio.get_event_loop().run_forever()
