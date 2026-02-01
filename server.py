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

from main import create_ticket_logic, list_tickets_logic, move_ticket_logic, edit_ticket_logic

# ... imports ...

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

# run_cli_command removed

@app.get("/api/tickets")
async def get_tickets():
    """Get all tickets via direct DB call."""
    return list_tickets_logic(all=True)

@app.post("/api/tickets")
async def create_ticket(ticket: TicketCreate):
    """Create a new ticket via direct DB call."""
    new_ticket = create_ticket_logic(
        title=ticket.title,
        desc=ticket.description,
        type=ticket.type,
        assign=ticket.assignee,
        prio=ticket.priority,
        points=ticket.points,
        sprint=ticket.sprint
    )
    return {"status": "success", "ticket_id": new_ticket.id}

class TicketMove(BaseModel):
    status: str



@app.post("/api/tickets/{ticket_id}/move")
async def move_ticket(ticket_id: int, move: TicketMove):
    """Move a ticket to a new status via direct DB call."""
    try:
        move_ticket_logic(ticket_id, move.status)
        return {"status": "success", "ticket_id": ticket_id}
    except ValueError:
        raise HTTPException(status_code=404, detail="Ticket not found")

class TicketUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    priority: Optional[str] = None

@app.post("/api/tickets/{ticket_id}/update")
async def update_ticket(ticket_id: int, update: TicketUpdate):
    """Update a ticket via direct DB call."""
    try:
        edit_ticket_logic(
            ticket_id, 
            title=update.title, 
            desc=update.description, 
            type=update.type, 
            prio=update.priority
        )
        return {"status": "success", "ticket_id": ticket_id}
    except ValueError:
        raise HTTPException(status_code=404, detail="Ticket not found")

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
