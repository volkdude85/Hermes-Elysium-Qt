"""Sessions manager for Hermes Elysium — reads/writes from the real Hermes state.db.
Storage: ~/.hermes/state.db (shared with Hermes Agent CLI)"""
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import List, Dict, Optional, Any

STATE_DB = Path.home() / ".hermes" / "state.db"


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(STATE_DB))
    conn.row_factory = sqlite3.Row
    return conn


def create_session(title: str = "Untitled") -> Dict[str, Any]:
    sid = f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    ts = time.time()
    with _db() as conn:
        conn.execute(
            "INSERT INTO sessions (id, title, source, started_at, message_count) VALUES (?, ?, ?, ?, ?)",
            (sid, title, "qt_shell", ts, 0),
        )
        conn.commit()
    return {
        "id": sid,
        "title": title,
        "created_at": ts,
        "updated_at": ts,
        "messages": [],
        "source": "qt_shell",
    }


def load_session(sid: str) -> Optional[Dict[str, Any]]:
    with _db() as conn:
        row = conn.execute(
            "SELECT id, title, started_at, message_count, model, billing_provider FROM sessions WHERE id=?", (sid,)
        ).fetchone()
        if not row:
            return None
        msgs = conn.execute(
            "SELECT role, content, timestamp FROM messages WHERE session_id=? ORDER BY timestamp",
            (sid,),
        ).fetchall()
        # auto-title from first user message if no title
        title = row["title"]
        if not title:
            for m in msgs:
                if m["role"] == "user":
                    title = m["content"][:50]
                    if len(m["content"]) > 50:
                        title += "…"
                    break
        if not title:
            title = row["id"][:8]
    return {
        "id": row["id"],
        "title": title,
        "created_at": row["started_at"],
        "updated_at": row["started_at"],
        "message_count": row["message_count"] or 0,
        "model": row["model"] if row["model"] else "",
        "billing_provider": row["billing_provider"] if row["billing_provider"] else "",
        "messages": [{"role": m["role"], "content": m["content"], "timestamp": m["timestamp"]} for m in msgs],
    }


def save_session(session: Dict[str, Any]) -> bool:
    sid = session.get("id")
    title = session.get("title", "Untitled")
    count = len(session.get("messages", []))
    with _db() as conn:
        conn.execute(
            "UPDATE sessions SET title=?, message_count=? WHERE id=?",
            (title, count, sid),
        )
        conn.commit()
    return True


def append_message(sid: str, role: str, content: str) -> bool:
    ts = time.time()
    with _db() as conn:
        conn.execute(
            "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (sid, role, content, ts),
        )
        conn.execute(
            "UPDATE sessions SET message_count = message_count + 1 WHERE id=?",
            (sid,),
        )
        conn.commit()
    return True


def list_sessions() -> List[Dict[str, Any]]:
    if not STATE_DB.exists():
        return []
    with _db() as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.title, s.started_at, s.message_count, s.source, s.model, s.billing_provider,
                   (SELECT content FROM messages WHERE session_id=s.id AND role='user' ORDER BY timestamp LIMIT 1) AS first_user_msg
            FROM sessions s
            ORDER BY s.started_at DESC LIMIT 100
            """
        ).fetchall()
    result = []
    for r in rows:
        title = r["title"]
        if not title:
            fu = r["first_user_msg"] or ""
            if fu:
                title = fu[:50] + ("…" if len(fu) > 50 else "")
            else:
                title = r["id"][:8]
        result.append({
            "id": r["id"],
            "title": title,
            "created_at": r["started_at"],
            "updated_at": r["started_at"],
            "message_count": r["message_count"] or 0,
            "source": r["source"] or "unknown",
            "model": r["model"] if r["model"] else "",
            "billing_provider": r["billing_provider"] if r["billing_provider"] else "",
        })
    return result


def delete_session(sid: str) -> bool:
    with _db() as conn:
        conn.execute("DELETE FROM messages WHERE session_id=?", (sid,))
        conn.execute("DELETE FROM sessions WHERE id=?", (sid,))
        conn.commit()
    return True
