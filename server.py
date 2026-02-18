import subprocess
import json
import logging
import sys
import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

# Determine if running in frozen mode (PyInstaller)
if getattr(sys, 'frozen', False):
    # PyInstaller creates a temp folder at _MEIPASS
    base_dir = sys._MEIPASS
    # In frozen mode, sys.executable is the binary itself
    CLI_CMD_BASE = [sys.executable]
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    # In dev mode, use python main.py
    CLI_CMD_BASE = [sys.executable, "main.py"]

app = FastAPI()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TicketCreate(BaseModel):
    title: str
    description: Optional[str] = None
    type: Optional[str] = "TASK"
    assignee: Optional[str] = "me"
    priority: Optional[str] = "MEDIUM"
    points: Optional[int] = 0
    sprint: Optional[str] = "Backlog"

from main import create_ticket_logic, list_tickets_logic, move_ticket_logic, edit_ticket_logic, list_comments_logic, create_comment_logic

# ... imports ...

app = FastAPI()

# ...

class CommentCreate(BaseModel):
    content: str
    author: Optional[str] = "me"

@app.get("/api/tickets/{ticket_id}/comments")
async def get_comments(ticket_id: int):
    """Get all comments for a ticket."""
    return list_comments_logic(ticket_id)

@app.post("/api/tickets/{ticket_id}/comments")
async def create_comment(ticket_id: int, comment: CommentCreate):
    """Add a comment to a ticket."""
    try:
        new_comment = create_comment_logic(ticket_id, comment.content, comment.author)
        return {"status": "success", "comment_id": new_comment.id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# Mount static files at root
static_dir = os.environ.get("SNOWFLAKES_STATIC_DIR")
if not static_dir or not os.path.exists(static_dir):
    # Fallback for dev mode
    static_dir = os.path.join(base_dir, "static")
    if not os.path.exists(static_dir):
        static_dir = "static"

app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
