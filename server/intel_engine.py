"""
AVA Intelligence Engine — CIA-Level Analysis
Relationship mapping, commitment tracking, pattern detection, threat/opportunity scoring.

SQLite-backed (Neo4j blocked pending password). 
Works with local Ollama for deep extraction.
"""
import json, sqlite3, re, time, hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass, asdict
from collections import defaultdict

DB_PATH = Path(__file__).parent / "intel.db"

# ─── Schema ─────────────────────────────────────────────────
def init_db():
    db = sqlite3.connect(str(DB_PATH))
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
        -- Core entities
        CREATE TABLE IF NOT EXISTS persons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            aliases TEXT,               -- comma-separated
            first_seen TIMESTAMP,
            last_seen TIMESTAMP,
            meeting_count INTEGER DEFAULT 0,
            influence_score REAL DEFAULT 0.0,
            threat_level REAL DEFAULT 0.0,
            opportunity_score REAL DEFAULT 0.0,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_a TEXT NOT NULL,
            person_b TEXT NOT NULL,
            rel_type TEXT,              -- 'colleague', 'boss', 'client', 'friend', 'family'
            strength REAL DEFAULT 0.0,  -- 0-1 based on frequency + sentiment
            first_observed TIMESTAMP,
            last_observed TIMESTAMP,
            mentions INTEGER DEFAULT 0,
            sentiment_avg REAL DEFAULT 0.0,
            evidence TEXT               -- JSON array of transcript IDs
        );

        CREATE TABLE IF NOT EXISTS meetings (
            id TEXT PRIMARY KEY,
            person TEXT,
            timestamp TIMESTAMP,
            transcript TEXT,
            summary TEXT,
            topics TEXT,                -- JSON array
            sentiment REAL,             -- -1 to 1
            duration_words INTEGER
        );

        CREATE TABLE IF NOT EXISTS commitments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person TEXT NOT NULL,
            meeting_id TEXT,
            description TEXT,
            deadline TEXT,
            status TEXT DEFAULT 'pending',  -- pending, completed, broken
            created TIMESTAMP,
            completed TIMESTAMP,
            priority TEXT DEFAULT 'medium'   -- low, medium, high, critical
        );

        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            first_seen TIMESTAMP,
            count INTEGER DEFAULT 0,
            related_persons TEXT         -- JSON array
        );

        CREATE TABLE IF NOT EXISTS intelligence_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            signal_type TEXT,            -- 'new_person', 'commitment_made', 'commitment_due',
                                         -- 'relationship_discovered', 'sentiment_shift',
                                         -- 'high_value_meeting', 'anomaly', 'opportunity',
                                         -- 'reconnection'
            person TEXT,
            meeting_id TEXT,
            description TEXT,
            priority TEXT DEFAULT 'low',  -- low, medium, high, critical
            acknowledged INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS conversation_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person TEXT,
            pattern_type TEXT,           -- 'frequent_topics', 'time_of_day', 'avg_duration',
                                         -- 'response_style', 'emotional_range'
            pattern_data TEXT             -- JSON
        );

        -- Indexes
        CREATE INDEX IF NOT EXISTS idx_meetings_person ON meetings(person);
        CREATE INDEX IF NOT EXISTS idx_meetings_ts ON meetings(timestamp);
        CREATE INDEX IF NOT EXISTS idx_commitments_status ON commitments(status);
        CREATE INDEX IF NOT EXISTS idx_commitments_person ON commitments(person);
        CREATE INDEX IF NOT EXISTS idx_signals_priority ON intelligence_signals(priority);
        CREATE INDEX IF NOT EXISTS idx_signals_ack ON intelligence_signals(acknowledged);
        CREATE INDEX IF NOT EXISTS idx_relationships_ab ON relationships(person_a, person_b);
    """)
    db.commit()
    return db

init_db()

# ─── Intelligence Extraction ─────────────────────────────────

COMMITMENT_PATTERNS = [
    # "I'll [verb] by [time]"
    (r"(?:i'll|i will|i'm going to|i am going to|let me)\s+([\w\s]+?)(?:by|before|on|next|tomorrow|tonight|today)(?:\s+the)?\s+([\w\s\d]+?)(?:\.|,|$)", "high"),
    # "we need to [verb]"
    (r"(?:we need to|we should|we have to|we gotta)\s+([\w\s]+?)(?:by|before|on|next|tomorrow|today)?(?:\s+the)?\s*([\w\s\d]*?)(?:\.|,|$)", "medium"),
    # "remind me to [verb]"
    (r"(?:remind me to|don't let me forget to)\s+([\w\s]+?)(?:\.|,|$)", "high"),
    # "I owe [person] [thing]"
    (r"(?:i owe|i need to pay|i need to send|i need to give)\s+(\w+)\s+([\w\s]+?)(?:\.|,|$)", "medium"),
]

RELATIONSHIP_PATTERNS = [
    # "my [role] [name]"
    (r"(?:my|our)\s+(boss|manager|partner|client|coworker|friend|brother|sister|dad|mom|father|mother|son|daughter|wife|husband)\s+(?:is|named)?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", 0.8),
    # "[name] is my [role]"
    (r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+is\s+(?:my|our)\s+(boss|manager|partner|client|coworker|friend|brother|sister|dad|mom|father|mother)", 0.9),
    # "[name] works with [name]"
    (r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:works? with|reports to|manages)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", 0.7),
]

TOPIC_KEYWORDS = {
    "money": ["money", "cash", "payment", "salary", "budget", "cost", "expensive", "cheap", "invest", "price", "deal", "revenue", "profit", "loss"],
    "power": ["promotion", "fired", "hired", "boss", "manager", "leadership", "decision", "authority", "control", "in charge"],
    "conflict": ["angry", "upset", "fight", "argument", "problem", "issue", "disagree", "wrong", "blame", "sorry", "apologize"],
    "opportunity": ["opportunity", "chance", "open", "possible", "potential", "growth", "expand", "new project", "launch"],
    "risk": ["risk", "danger", "careful", "warning", "threat", "lose", "failure", "worried", "concern", "problematic"],
    "family": ["mom", "dad", "brother", "sister", "wife", "husband", "son", "daughter", "parent", "family", "home"],
    "tech": ["code", "software", "app", "server", "computer", "AI", "data", "system", "build", "develop", "launch"],
    "health": ["sick", "doctor", "hospital", "medicine", "tired", "sleep", "exercise", "diet", "pain"],
}

def extract_commitments(transcript: str, meeting_id: str) -> list:
    """Extract commitments from transcript."""
    found = []
    for pattern, priority in COMMITMENT_PATTERNS:
        for m in re.finditer(pattern, transcript, re.IGNORECASE):
            action = m.group(1).strip()
            deadline = m.group(2).strip() if m.lastindex >= 2 else None
            if len(action) > 3:
                found.append({
                    "action": action,
                    "deadline": deadline,
                    "priority": priority,
                    "source_pattern": pattern[:30]
                })
    return found

def extract_relationships(transcript: str) -> list:
    """Extract person-to-person relationships."""
    found = []
    for pattern, confidence in RELATIONSHIP_PATTERNS:
        for m in re.finditer(pattern, transcript, re.IGNORECASE):
            if m.lastindex >= 2:
                a, b = m.group(1).strip(), m.group(2).strip()
                if a and b and a.lower() != b.lower() and len(a) > 1 and len(b) > 1:
                    found.append({"person_a": a, "person_b": b, "confidence": confidence})
    return found

def extract_topics(transcript: str) -> list:
    """Extract conversation topics by keyword matching."""
    text = transcript.lower()
    scores = {}
    for topic, keywords in TOPIC_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[topic] = score
    return sorted(scores.keys(), key=lambda k: scores[k], reverse=True)[:5]

def sentiment_score(transcript: str) -> float:
    """Basic sentiment: positive vs negative word ratio."""
    positive = len(re.findall(r'\b(great|good|awesome|amazing|excellent|happy|love|wonderful|fantastic|yes|agree|perfect|thank|thanks|excited|opportunity)\b', transcript, re.IGNORECASE))
    negative = len(re.findall(r'\b(bad|terrible|awful|hate|angry|upset|wrong|no|don\'t|never|problem|issue|fail|worried|scared|difficult|hard)\b', transcript, re.IGNORECASE))
    total = positive + negative
    return (positive - negative) / max(total, 1)

def analyze_power_dynamics(person: str, db: sqlite3.Connection) -> dict:
    """Analyze power/influence signals for a person."""
    cur = db.execute("""
        SELECT transcript FROM meetings WHERE person = ?
    """, (person,))
    transcripts = [r[0] for r in cur.fetchall() if r[0]]

    total_words = sum(len(t.split()) for t in transcripts)
    # Who mentions them
    cur = db.execute("""
        SELECT COUNT(*) FROM meetings WHERE transcript LIKE ?
    """, (f"%{person}%",))
    mention_count = cur.fetchone()[0]

    # Commitment completion rate
    cur = db.execute("""
        SELECT COUNT(*), SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END)
        FROM commitments WHERE person = ?
    """, (person,))
    total_comm, completed_comm = cur.fetchone()
    completion_rate = completed_comm / max(total_comm, 1)

    # Meeting frequency
    cur = db.execute("SELECT COUNT(*) FROM meetings WHERE person = ?", (person,))
    meeting_count = cur.fetchone()[0]

    return {
        "total_words_spoken": total_words,
        "mention_count": mention_count,
        "commitment_completion": completion_rate,
        "meeting_count": meeting_count,
        "influence_score": min(1.0, (meeting_count * 0.1 + completion_rate * 0.4 + min(mention_count / 20, 1) * 0.5))
    }

# ─── Ingestion Pipeline ─────────────────────────────────────
def ingest_intelligence(meeting_id: str, person: str, transcript: str):
    """Full intelligence pipeline on new transcript."""
    db = sqlite3.connect(str(DB_PATH))

    # Store meeting
    ts = datetime.now().isoformat()
    topics = extract_topics(transcript)
    sentiment = sentiment_score(transcript)
    db.execute("""
        INSERT OR IGNORE INTO meetings (id, person, timestamp, transcript, topics, sentiment, duration_words)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (meeting_id, person, ts, transcript, json.dumps(topics), sentiment, len(transcript.split())))

    # Update person
    cur = db.execute("SELECT meeting_count FROM persons WHERE name = ?", (person,))
    row = cur.fetchone()
    if row:
        db.execute("UPDATE persons SET last_seen = ?, meeting_count = meeting_count + 1 WHERE name = ?", (ts, person))
    else:
        db.execute("INSERT INTO persons (name, first_seen, last_seen, meeting_count) VALUES (?, ?, ?, 1)", (person, ts, ts))

    # Extract commitments
    commitments = extract_commitments(transcript, meeting_id)
    for c in commitments:
        db.execute("""
            INSERT INTO commitments (person, meeting_id, description, deadline, priority, created, status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
        """, (person, meeting_id, c["action"], c.get("deadline"), c["priority"], ts))

        # Signal
        db.execute("""
            INSERT INTO intelligence_signals (signal_type, person, meeting_id, description, priority)
            VALUES ('commitment_made', ?, ?, ?, ?)
        """, (person, meeting_id, f"Committed to: {c['action'][:100]}", c["priority"]))

    # Extract relationships
    relationships = extract_relationships(transcript)
    for rel in relationships:
        a, b = sorted([rel["person_a"], rel["person_b"]])
        cur = db.execute("SELECT id FROM relationships WHERE person_a = ? AND person_b = ?", (a, b))
        if cur.fetchone():
            db.execute("UPDATE relationships SET strength = MIN(strength + ?, 1.0), last_observed = ?, mentions = mentions + 1 WHERE person_a = ? AND person_b = ?",
                       (rel["confidence"] * 0.1, ts, a, b))
        else:
            db.execute("""
                INSERT INTO relationships (person_a, person_b, strength, first_observed, last_observed, mentions)
                VALUES (?, ?, ?, ?, ?, 1)
            """, (a, b, rel["confidence"] * 0.1, ts, ts))

        db.execute("""
            INSERT INTO intelligence_signals (signal_type, person, description, priority)
            VALUES ('relationship_discovered', ?, ?, 'medium')
        """, (person, f"Connection: {a} ↔ {b} ({rel['person_a']} knows {rel['person_b']})"))

    # Track topics
    for topic in topics:
        db.execute("""
            INSERT INTO topics (name, first_seen, count)
            VALUES (?, ?, 1)
            ON CONFLICT(name) DO UPDATE SET count = count + 1
        """, (topic, ts))

    # Run power analysis
    power = analyze_power_dynamics(person, db)
    db.execute("UPDATE persons SET influence_score = ? WHERE name = ?", (power["influence_score"], person))

    # Detect anomalies / high-value signals
    cur = db.execute("SELECT COUNT(*) FROM meetings WHERE person = ?", (person,))
    total_meetings = cur.fetchone()[0]

    if total_meetings == 1:
        db.execute("""
            INSERT INTO intelligence_signals (signal_type, person, description, priority)
            VALUES ('new_person', ?, ?, 'medium')
        """, (person, f"First encounter with {person}"))

    if sentiment < -0.3:
        db.execute("""
            INSERT INTO intelligence_signals (signal_type, person, description, priority)
            VALUES ('sentiment_shift', ?, ?, 'high')
        """, (person, f"Negative sentiment detected with {person}"))

    if sentiment > 0.5:
        db.execute("""
            INSERT INTO intelligence_signals (signal_type, person, meeting_id, description, priority)
            VALUES ('opportunity', ?, ?, ?, 'medium')
        """, (person, meeting_id, f"Positive high-value conversation with {person}"))

    db.commit()
    db.close()

    return {
        "commitments_found": len(commitments),
        "relationships_found": len(relationships),
        "topics": topics,
        "sentiment": round(sentiment, 2),
        "power": power
    }

# ─── Intelligence Queries ───────────────────────────────────
def get_intel_briefing(db_path: str = str(DB_PATH)) -> dict:
    """Generate a CIA-style intelligence briefing."""
    db = sqlite3.connect(db_path)

    # Top people by influence
    top_people = db.execute("""
        SELECT name, meeting_count, influence_score FROM persons
        WHERE meeting_count > 0 ORDER BY influence_score DESC LIMIT 10
    """).fetchall()

    # Pending commitments
    pending = db.execute("""
        SELECT person, description, deadline, priority, created
        FROM commitments WHERE status = 'pending'
        ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END
        LIMIT 20
    """).fetchall()

    # Recent signals
    signals = db.execute("""
        SELECT timestamp, signal_type, person, description, priority
        FROM intelligence_signals WHERE acknowledged = 0
        ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                 timestamp DESC
        LIMIT 20
    """).fetchall()

    # Relationship graph
    rels = db.execute("""
        SELECT person_a, person_b, rel_type, strength, mentions FROM relationships
        ORDER BY strength DESC LIMIT 30
    """).fetchall()

    # Topic trends
    topics = db.execute("""
        SELECT name, count FROM topics ORDER BY count DESC LIMIT 10
    """).fetchall()

    # Stats
    stats = {
        "total_people": db.execute("SELECT COUNT(*) FROM persons").fetchone()[0],
        "total_meetings": db.execute("SELECT COUNT(*) FROM meetings").fetchone()[0],
        "total_commitments": db.execute("SELECT COUNT(*) FROM commitments").fetchone()[0],
        "pending_commitments": db.execute("SELECT COUNT(*) FROM commitments WHERE status='pending'").fetchone()[0],
        "broken_commitments": db.execute("SELECT COUNT(*) FROM commitments WHERE status='broken'").fetchone()[0],
        "total_relationships": db.execute("SELECT COUNT(*) FROM relationships").fetchone()[0],
        "unacknowledged_signals": db.execute("SELECT COUNT(*) FROM intelligence_signals WHERE acknowledged=0").fetchone()[0],
    }

    db.close()
    return {
        "timestamp": datetime.now().isoformat(),
        "stats": stats,
        "top_people": [{"name": p[0], "meetings": p[1], "influence": round(p[2], 2)} for p in top_people],
        "pending_commitments": [{"person": p[0], "description": p[1], "deadline": p[2], "priority": p[3], "created": p[4]} for p in pending],
        "signals": [{"timestamp": s[0], "type": s[1], "person": s[2], "description": s[3], "priority": s[4]} for s in signals],
        "relationships": [{"a": r[0], "b": r[1], "type": r[2], "strength": round(r[3], 2), "mentions": r[4]} for r in rels],
        "topic_trends": [{"topic": t[0], "count": t[1]} for t in topics]
    }

def search_intel(query: str, db_path: str = str(DB_PATH)) -> dict:
    """Search across all intelligence data."""
    db = sqlite3.connect(db_path)
    q = f"%{query}%"

    people = [r[0] for r in db.execute("SELECT name FROM persons WHERE name LIKE ? OR notes LIKE ?", (q, q)).fetchall()]
    meetings = [{"id": r[0], "person": r[1], "text": r[2][:200]} for r in
                db.execute("SELECT id, person, transcript FROM meetings WHERE transcript LIKE ? LIMIT 10", (q,)).fetchall()]
    commitments = [{"person": r[0], "description": r[1], "status": r[2]} for r in
                   db.execute("SELECT person, description, status FROM commitments WHERE description LIKE ? LIMIT 10", (q,)).fetchall()]
    signals = [{"type": r[0], "person": r[1], "description": r[2]} for r in
               db.execute("SELECT signal_type, person, description FROM intelligence_signals WHERE description LIKE ? LIMIT 10", (q,)).fetchall()]

    db.close()
    return {"query": query, "people": people, "meetings": meetings, "commitments": commitments, "signals": signals}

def ack_signal(signal_id: int, db_path: str = str(DB_PATH)):
    """Acknowledge an intelligence signal."""
    db = sqlite3.connect(db_path)
    db.execute("UPDATE intelligence_signals SET acknowledged = 1 WHERE id = ?", (signal_id,))
    db.commit()
    db.close()

# ─── CLI ─────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "briefing":
        print(json.dumps(get_intel_briefing(), indent=2))
    elif len(sys.argv) > 1 and sys.argv[1] == "search" and len(sys.argv) > 2:
        print(json.dumps(search_intel(sys.argv[2]), indent=2))
    elif len(sys.argv) > 1 and sys.argv[1] == "init":
        init_db()
        print("Intel DB initialized")
    else:
        print("Usage: python intel_engine.py [briefing|search <query>|init]")
