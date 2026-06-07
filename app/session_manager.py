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

def cleanup_old_sessions():
    now = datetime.now()
    to_delete = [
        sid for sid, sess in sessions.items()
        if (now - sess["created_at"]).total_seconds() > 3600  # ← fix bug .seconds
    ]
    for sid in to_delete:
        del sessions[sid]