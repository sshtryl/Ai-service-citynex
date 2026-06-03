# ai-service/app/main.py
import json
import asyncio
import logging 
import httpx
import os 
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .models import UserInput, AIResponse
from .session_manager import get_session, create_session, update_session
from .ai_agent import chat_with_ai, extract_report_json
from .db import save_report

NODE_BACKEND_URL = os.getenv("NODE_BACKEND_URL", "http://localhost:3001")

# 🔥 TAMBAHKAN LOGGING
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GREETING = (
    "Halo selamat datang di citynex silahkan melaporkan masalah yang anda temui di kota anda"
)

@app.post("/api/ai/chat", response_model=AIResponse)
async def chat(user_input: UserInput):
    session = get_session(user_input.session_id)

    if not session:
        session = create_session(user_input.session_id)
        session["history"].append({"role": "assistant", "content": GREETING})
        logger.info(f"🆕 New session created: {user_input.session_id}")

    messages = [
        *session["history"],
        {"role": "user", "content": user_input.message},
    ]

    ai_response = chat_with_ai(messages, session["collected_data"])

    session["history"].append({"role": "user", "content": user_input.message})
    session["history"].append({"role": "assistant", "content": ai_response})
    update_session(user_input.session_id, session)

    report_data = extract_report_json(ai_response)
    is_complete = report_data is not None

    clean_message = ai_response.split("###REPORT_JSON###")[0].strip() if is_complete else ai_response

    return AIResponse(
        session_id=user_input.session_id,
        message=clean_message,
        is_complete=is_complete,
        report_data=report_data,
    )

@app.get("/api/ai/start/{session_id}")
async def start_session(session_id: str):
    session = get_session(session_id)
    if not session:
        session = create_session(session_id)
        session["history"].append({"role": "assistant", "content": GREETING})
        update_session(session_id, session)
        logger.info(f"🆕 Session started: {session_id}")
    return {"session_id": session_id, "message": GREETING}

@app.get("/api/ai/health")
async def health():
    return {"status": "ok"}