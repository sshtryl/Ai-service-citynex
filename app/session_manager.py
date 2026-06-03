from typing import Dict
from datetime import datetime

sessions = {}

def get_session(session_id: str):
    return sessions.get(session_id)

def create_session(session_id: str):
    sessions[session_id] = {
        "step": "initial",
        "collected_data": {},
        "history": [],
        "created_at": datetime.now()
    }
    return sessions[session_id]

def update_session(session_id: str, data: dict):
    if session_id in sessions:
        sessions[session_id].update(data)

def delete_session(session_id: str):
    if session_id in sessions:
        del sessions[session_id]

# Cleanup session lama (lebih dari 1 jam)
def cleanup_old_sessions():
    now = datetime.now()
    to_delete = []
    for sid, sess in sessions.items():
        if (now - sess['created_at']).seconds > 3600:
            to_delete.append(sid)
    for sid in to_delete:
        del sessions[sid]