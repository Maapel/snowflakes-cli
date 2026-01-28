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
