from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel

class Ticket(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    description: Optional[str] = None

    # PM Features
    type: str = Field(default="TASK")   # STORY, TASK, BUG
    status: str = Field(default="TODO") # TODO, IN_PROGRESS, REVIEW, DONE
    points: int = Field(default=0)      # Fibonacci: 1, 2, 3, 5, 8
    sprint: str = Field(default="Backlog")
    assignee: str = Field(default="me")

    priority: str = Field(default="MEDIUM")
    created_at: datetime = Field(default_factory=datetime.now)
    resolution_notes: Optional[str] = None
    last_activity: datetime = Field(default_factory=datetime.now)

class Comment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    ticket_id: int = Field(foreign_key="ticket.id")
    author: str = Field(default="me")
    content: str
    created_at: datetime = Field(default_factory=datetime.now)

class Project(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    path: str = Field(unique=True)
    last_accessed: datetime = Field(default_factory=datetime.now)

class Agent(SQLModel, table=True):
    """Registry of AI agents working on this project."""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)     # e.g., "bahubali", "virus"
    role: str = Field(default="agent")              # e.g., "Tech Lead", "Backend Engineer"
    status: str = Field(default="IDLE")             # IDLE, WORKING, BLOCKED, DONE
    current_ticket: Optional[int] = Field(default=None)
    last_heartbeat: datetime = Field(default_factory=datetime.now)
    capabilities: Optional[str] = Field(default=None)  # JSON array of capabilities
    agent_meta: Optional[str] = Field(default=None)      # JSON metadata
