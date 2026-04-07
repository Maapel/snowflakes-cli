import os
import sys
import logging
from contextlib import contextmanager
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from sqlmodel import select, Session, or_

from database import (
    get_session, get_registry_session, get_project_session,
    get_project_engine, init_registry_db, DB_NAME
)
from models import Ticket, Comment, Project, Agent
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

class AgentRegister(BaseModel):
    name: str
    role: Optional[str] = "agent"
    capabilities: Optional[str] = None

class AgentHeartbeat(BaseModel):
    name: str
    status: Optional[str] = "WORKING"

# --- Legacy per-project endpoints (backward compatible) ---

@app.get("/api/tickets")
async def get_tickets(
    assignee: Optional[str] = None,
):
    """List tickets with optional agent filter."""
    with get_session() as session:
        q = select(Ticket).where(Ticket.status != "DONE")
        if assignee:
            q = q.where(Ticket.assignee == assignee.lower())
        tickets = session.exec(q).all()
    result = []
    for t in tickets:
        d = t.model_dump(mode='json')
        comments = list_comments_logic(t.id)
        d['comment_count'] = len(comments)
        result.append(d)
    return result

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
                    agent_tickets = {}
                    for t in tickets:
                        status_key = t.status.lower()
                        if status_key in stats:
                            stats[status_key] += 1
                        if t.assignee not in ("me",):
                            if t.assignee not in agent_tickets:
                                agent_tickets[t.assignee] = []
                            if t.status in ("TODO", "IN_PROGRESS", "REVIEW"):
                                agent_tickets[t.assignee].append({"id": t.id, "title": t.title, "status": t.status, "priority": t.priority})
                    # Legacy key (backward compat)
                    all_agent = [at for ats in agent_tickets.values() for at in ats]
                    stats["agent_tickets"] = all_agent
                    stats["agent_active"] = len(all_agent)
                    stats["agents"] = {name: {"active": len(ts), "tickets": ts} for name, ts in agent_tickets.items()}
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
        tickets = list_tickets_logic(all=True)
        result = []
        for t in tickets:
            d = t.model_dump(mode='json')
            comments = list_comments_logic(t.id)
            d['comment_count'] = len(comments)
            result.append(d)
        return result

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

# --- Agent API Endpoints ---

def get_project_agent_session(project_id: int, project_path: str):
    """Create a session for a specific project's DB and return engine+session."""
    engine = get_project_engine(project_path)
    session = Session(engine)
    return engine, session

@app.get("/api/agents")
async def list_agents(project_id: Optional[int] = None):
    """List all registered agents for a project (or all projects)."""
    with get_session() as session:
        q = select(Agent).order_by(Agent.name)
        agents = session.exec(q).all()
    return [a.model_dump(mode='json') for a in agents]

@app.post("/api/agents/register")
async def register_agent(agent: AgentRegister):
    """Register or update an agent in the project DB."""
    with get_session() as session:
        q = select(Agent).where(Agent.name == agent.name.lower())
        existing = session.exec(q).first()
        if existing:
            existing.role = agent.role or existing.role
            existing.status = "IDLE"
            existing.last_heartbeat = datetime.now()
            existing.capabilities = agent.capabilities or existing.capabilities
            session.add(existing)
        else:
            session.add(Agent(
                name=agent.name.lower(),
                role=agent.role,
                capabilities=agent.capabilities,
            ))
        session.commit()
    return {"status": "success", "name": agent.name.lower()}

@app.post("/api/agents/{agent_name}/heartbeat")
async def agent_heartbeat(agent_name: str, heartbeat: AgentHeartbeat):
    """Update agent heartbeat status."""
    with get_session() as session:
        q = select(Agent).where(Agent.name == agent_name.lower())
        agent = session.exec(q).first()
        if not agent:
            session.add(Agent(name=agent_name.lower(), role="agent", status=heartbeat.status.upper()))
        else:
            agent.status = heartbeat.status.upper()
            agent.last_heartbeat = datetime.now()
            session.add(agent)
        session.commit()
    return {"status": "success", "agent": agent_name, "status": heartbeat.status.upper()}

@app.get("/api/agents/{agent_name}/poll")
async def agent_poll(agent_name: str, status: Optional[str] = "WORKING"):
    """Poll for tickets assigned to an agent, with unreplied message detection."""
    with get_session() as session:
        q = select(Agent).where(Agent.name == agent_name.lower())
        agent = session.exec(q).first()
        if agent:
            agent.last_heartbeat = datetime.now()
            if status:
                agent.status = status.upper()
            session.add(agent)
            session.commit()

        tickets = session.exec(
            select(Ticket).where(Ticket.assignee == agent_name.lower()).where(Ticket.status != "DONE")
        ).all()

    data = []
    for t in tickets:
        ticket_data = t.model_dump(mode='json')
        comments = list_comments_logic(t.id)
        comment_list = [c.model_dump(mode='json') for c in comments]
        ticket_data["comments"] = comment_list

        unreplied = []
        last_agent_idx = -1
        for i, c in enumerate(comment_list):
            if c["author"] == agent_name.lower():
                last_agent_idx = i
        for c in comment_list[last_agent_idx + 1:]:
            if c["author"] != agent_name.lower():
                unreplied.append(c)

        ticket_data["has_unreplied"] = len(unreplied) > 0
        ticket_data["unreplied_messages"] = unreplied
        data.append(ticket_data)

    return {
        "agent": agent_name.lower(),
        "status": agent.status.upper() if agent else "UNKNOWN",
        "active_tickets": len(data),
        "tickets": data,
    }

@app.get("/api/agents/{agent_name}")
async def get_agent(agent_name: str):
    """Get a single agent's details."""
    with get_session() as session:
        q = select(Agent).where(Agent.name == agent_name.lower())
        agent = session.exec(q).first()
    if not agent:
        raise HTTPException(404, f"Agent '{agent_name}' not found")
    return agent.model_dump(mode='json')

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
