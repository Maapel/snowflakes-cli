import os
import sys
import logging
from contextlib import contextmanager
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from sqlmodel import select, Session

from database import (
    get_session, get_registry_session, get_project_session,
    get_project_engine, init_registry_db, DB_NAME
)
from models import Ticket, Comment, Project
from main import (
    create_ticket_logic, list_tickets_logic, move_ticket_logic,
    edit_ticket_logic, list_comments_logic, create_comment_logic
)

# Determine if running in frozen mode (PyInstaller)
if getattr(sys, 'frozen', False):
    base_dir = sys._MEIPASS
    CLI_CMD_BASE = [sys.executable]
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    CLI_CMD_BASE = [sys.executable, "main.py"]

app = FastAPI()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Pydantic Models ---

class TicketCreate(BaseModel):
    title: str
    description: Optional[str] = None
    type: Optional[str] = "TASK"
    assignee: Optional[str] = "me"
    priority: Optional[str] = "MEDIUM"
    points: Optional[int] = 0
    sprint: Optional[str] = "Backlog"

class TicketUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    priority: Optional[str] = None
    assignee: Optional[str] = None
    points: Optional[int] = None

class TicketMove(BaseModel):
    status: str

class CommentCreate(BaseModel):
    content: str
    author: Optional[str] = "me"

# --- Legacy per-project endpoints (backward compatible) ---

@app.get("/api/tickets")
async def get_tickets():
    return list_tickets_logic(all=True)

@app.post("/api/tickets")
async def create_ticket(ticket: TicketCreate):
    try:
        t = create_ticket_logic(
            ticket.title, ticket.description, ticket.type or "TASK",
            ticket.assignee or "me", ticket.priority or "MEDIUM",
            ticket.points or 0, ticket.sprint or "Backlog"
        )
        return {"status": "success", "id": t.id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/tickets/{ticket_id}/move")
async def move_ticket(ticket_id: int, move: TicketMove):
    try:
        move_ticket_logic(ticket_id, move.status)
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.post("/api/tickets/{ticket_id}/update")
async def update_ticket(ticket_id: int, update: TicketUpdate):
    try:
        edit_ticket_logic(ticket_id, update.title, update.description, update.type, update.priority, update.assignee, update.points)
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.get("/api/tickets/{ticket_id}/comments")
async def get_comments(ticket_id: int):
    return list_comments_logic(ticket_id)

@app.post("/api/tickets/{ticket_id}/comments")
async def create_comment(ticket_id: int, comment: CommentCreate):
    try:
        new_comment = create_comment_logic(ticket_id, comment.content, comment.author)
        return {"status": "success", "comment_id": new_comment.id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# --- Project Registry Helpers ---

@contextmanager
def project_context(project_id: int):
    """Temporarily switch SNOWFLAKES_ROOT to a registered project."""
    with get_registry_session() as session:
        project = session.get(Project, project_id)
        if not project:
            raise HTTPException(404, "Project not found")
        path = project.path
    old = os.environ.get("SNOWFLAKES_ROOT")
    os.environ["SNOWFLAKES_ROOT"] = path
    try:
        yield path
    finally:
        if old:
            os.environ["SNOWFLAKES_ROOT"] = old
        else:
            os.environ.pop("SNOWFLAKES_ROOT", None)

# --- Project-Scoped API Endpoints ---

@app.get("/api/projects")
async def list_projects():
    """List all registered projects with ticket stats and agent activity."""
    init_registry_db()
    with get_registry_session() as reg_session:
        projects = reg_session.exec(select(Project).order_by(Project.last_accessed.desc())).all()

    results = []
    for proj in projects:
        db_path = os.path.join(proj.path, DB_NAME)
        stats = {"todo": 0, "in_progress": 0, "review": 0, "done": 0, "agent_active": 0, "agent_tickets": []}

        if os.path.exists(db_path):
            try:
                engine = get_project_engine(proj.path)
                with Session(engine) as session:
                    tickets = session.exec(select(Ticket)).all()
                    for t in tickets:
                        status_key = t.status.lower()
                        if status_key in stats:
                            stats[status_key] += 1
                        if t.assignee == "ai" and t.status in ("TODO", "IN_PROGRESS", "REVIEW"):
                            stats["agent_tickets"].append({"id": t.id, "title": t.title, "status": t.status})
                    stats["agent_active"] = len(stats["agent_tickets"])
            except Exception as e:
                logger.warning(f"Failed to read project DB at {proj.path}: {e}")

        results.append({
            "id": proj.id,
            "name": proj.name,
            "path": proj.path,
            "last_accessed": proj.last_accessed.isoformat() if proj.last_accessed else None,
            "stats": stats
        })

    return results

@app.get("/api/projects/{project_id}/tickets")
async def get_project_tickets(project_id: int):
    with project_context(project_id):
        return list_tickets_logic(all=True)

@app.post("/api/projects/{project_id}/tickets")
async def create_project_ticket(project_id: int, ticket: TicketCreate):
    with project_context(project_id):
        try:
            t = create_ticket_logic(
                ticket.title, ticket.description, ticket.type or "TASK",
                ticket.assignee or "me", ticket.priority or "MEDIUM",
                ticket.points or 0, ticket.sprint or "Backlog"
            )
            return {"status": "success", "id": t.id}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/projects/{project_id}/tickets/{ticket_id}/move")
async def move_project_ticket(project_id: int, ticket_id: int, move: TicketMove):
    with project_context(project_id):
        try:
            move_ticket_logic(ticket_id, move.status)
            return {"status": "success"}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

@app.post("/api/projects/{project_id}/tickets/{ticket_id}/update")
async def update_project_ticket(project_id: int, ticket_id: int, update: TicketUpdate):
    with project_context(project_id):
        try:
            edit_ticket_logic(ticket_id, update.title, update.description, update.type, update.priority, update.assignee, update.points)
            return {"status": "success"}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

@app.get("/api/projects/{project_id}/tickets/{ticket_id}/comments")
async def get_project_comments(project_id: int, ticket_id: int):
    with project_context(project_id):
        return list_comments_logic(ticket_id)

@app.post("/api/projects/{project_id}/tickets/{ticket_id}/comments")
async def create_project_comment(project_id: int, ticket_id: int, comment: CommentCreate):
    with project_context(project_id):
        try:
            new_comment = create_comment_logic(ticket_id, comment.content, comment.author)
            return {"status": "success", "comment_id": new_comment.id}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

# --- Static Files (must be last) ---

static_dir = os.environ.get("SNOWFLAKES_STATIC_DIR")
if not static_dir or not os.path.exists(static_dir):
    static_dir = os.path.join(base_dir, "static")
    if not os.path.exists(static_dir):
        static_dir = "static"

app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
