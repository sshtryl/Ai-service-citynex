from pydantic import BaseModel
from typing import Optional, List


class Message(BaseModel):
    role: str
    content: str

class UserInput(BaseModel):
    session_id: str
    message: str

class AIResponse(BaseModel):
    session_id: str
    message: str
    is_complete: bool = False
    report_data: Optional[dict] = None

class ReportOutput(BaseModel):
    category: str
    location: str
    severity: str
    description: str
    priority: str
    summary: str
    fake_score: int
    priority_score: int