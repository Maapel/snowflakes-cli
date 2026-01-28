import typer
import json
from typing import Optional, List
from sqlmodel import select
from rich.console import Console
from rich.table import Table
from rich import print as rprint
from rich.columns import Columns
from rich.panel import Panel

# Import our local modules
from models import Ticket
from database import init_db, get_session

app = typer.Typer(add_completion=False)
console = Console()

@app.callback()
def callback():
    """
    Snowflakes: A local-first Project Management System.
    """
    # Initialize DB in current folder on every run
    init_db()

@app.command()
def new(
    title: str, 
    desc: Optional[str] = None, 
    type: str = "TASK",
    assign: str = "me", 
    prio: str = "MEDIUM",
    points: int = 0,
    sprint: str = "Backlog",
    parent: Optional[int] = None
):
    """Create a new ticket."""
    with get_session() as session:
        ticket = Ticket(
            title=title, 
            description=desc, 
            type=type.upper(),
            assignee=assign.lower(), 
            priority=prio.upper(),
            points=points,
            sprint=sprint,
            parent_id=parent
        )
        session.add(ticket)
        session.commit()
        session.refresh(ticket)
    
    rprint(f"[green]✓ Created {ticket.type} #{ticket.id}:[/green] {title}")

@app.command("list")
def list_tickets(all: bool = False, sprint: Optional[str] = None):
    """List open tickets (or all with --all). Filter by sprint with --sprint."""
    with get_session() as session:
        query = select(Ticket)
        if not all:
            query = query.where(Ticket.status != "DONE")
        if sprint:
            query = query.where(Ticket.sprint == sprint)
        tickets = session.exec(query).all()

    if not tickets:
        rprint("[yellow]No tickets found in this directory.[/yellow]")
        return

    table = Table(title="Snowflakes ❄️")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Type", style="bold")
    table.add_column("Status", style="magenta")
    table.add_column("Sprint")
    table.add_column("Pts")
    table.add_column("Assignee")
    table.add_column("Title")

    for t in tickets:
        # Highlight AI tasks
        assignee_style = "bold purple" if t.assignee == "ai" else "blue"
        type_icon = "🚀" if t.type == "EPIC" else "🐞" if t.type == "BUG" else "📝" if t.type == "STORY" else "🔨"
        table.add_row(
            str(t.id), 
            f"{type_icon} {t.type}",
            t.status, 
            t.sprint,
            str(t.points),
            f"[{assignee_style}]{t.assignee}[/{assignee_style}]", 
            t.title
        )

    console.print(table)

@app.command()
def board(sprint: str = "Backlog"):
    """View the project as a Kanban Board."""
    with get_session() as session:
        # Fetch only relevant sprint tickets
        # Use simple string matching or if sprint is 'all', show everything? 
        # Plan says "accept optional --sprint (default to all active)" 
        # But code implementation in plan snippet used sprint arg directly. 
        # I'll stick to the snippet logic but allow fetching all if user passes "ALL" maybe?
        # User request said: "accept an optional --sprint argument (default to all active)."
        # But the snippet provided: `def board(sprint: str = "Backlog"):`
        # I will modify to follow the prompt's intent better if I can, or just stick to snippet.
        # Snippet is safer. I'll stick to snippet but maybe make sprint Optional to mean "all active"?
        # Let's stick to the user's snippet exactly for the core part, but maybe improve the fetching.
        
        query = select(Ticket)
        if sprint != "ALL":
             query = query.where(Ticket.sprint == sprint)
        
        tickets = session.exec(query).all()

    # Buckets
    todo_panels = []
    prog_panels = []
    done_panels = []
    review_panels = [] 

    for t in tickets:
        # Visual cues
        color = "cyan" if t.type == "STORY" else "red" if t.type == "BUG" else "purple" if t.type == "EPIC" else "green"
        icon = "🚀" if t.type == "EPIC" else "🐞" if t.type == "BUG" else "📝" if t.type == "STORY" else "🔨"
        
        # The Card
        info = f"{icon} #{t.id} [bold]{t.title}[/bold]\npts: {t.points} | @{t.assignee}"
        panel = Panel(info, border_style=color)

        if t.status == "TODO": todo_panels.append(panel)
        elif t.status == "IN_PROGRESS": prog_panels.append(panel)
        elif t.status == "REVIEW": review_panels.append(panel)
        elif t.status == "DONE": done_panels.append(panel)

    # Render Board
    console.rule(f"[bold]Sprint: {sprint}[/bold]")
    console.print(Columns(todo_panels, title="TODO", expand=True))
    console.print(Columns(prog_panels, title="IN PROGRESS", expand=True))
    if review_panels:
        console.print(Columns(review_panels, title="REVIEW", expand=True))
    console.print(Columns(done_panels, title="DONE", expand=True))

@app.command()
def resolve(ticket_id: int, notes: str = typer.Option(..., "--notes", "-n", help="How was this fixed?")):
    """Mark a ticket as DONE with resolution notes."""
    with get_session() as session:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            rprint(f"[red]Ticket #{ticket_id} not found.[/red]")
            raise typer.Exit(code=1)
        
        ticket.status = "DONE"
        ticket.resolution_notes = notes
        session.add(ticket)
        session.commit()
    
    rprint(f"[green]✓ Resolved Ticket #{ticket_id}[/green]")

@app.command()
def estimate(ticket_id: int, points: int):
    """Assign complexity points to a ticket."""
    with get_session() as session:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            rprint(f"[red]Ticket #{ticket_id} not found.[/red]")
            raise typer.Exit(code=1)
        
        ticket.points = points
        session.add(ticket)
        session.commit()
        
    rprint(f"[green]✓ SET POINTS: Ticket #{ticket_id} -> {points}[/green]")

@app.command("sprint")
def set_sprint(sprint_name: str, ticket_ids: List[int]):
    """Bulk assign tickets to a sprint."""
    with get_session() as session:
        for tid in ticket_ids:
            ticket = session.get(Ticket, tid)
            if ticket:
                ticket.sprint = sprint_name
                session.add(ticket)
        session.commit()
    
    rprint(f"[green]✓ Moved {len(ticket_ids)} tickets to sprint: {sprint_name}[/green]")

@app.command()
def move(ticket_id: int, status: str):
    """Move a ticket to a new status (TODO, IN_PROGRESS, REVIEW, DONE)."""
    valid_statuses = ["TODO", "IN_PROGRESS", "REVIEW", "DONE"]
    if status.upper() not in valid_statuses:
         rprint(f"[red]Invalid status. Options: {', '.join(valid_statuses)}[/red]")
         raise typer.Exit(code=1)

    with get_session() as session:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            rprint(f"[red]Ticket #{ticket_id} not found.[/red]")
            raise typer.Exit(code=1)
        
        ticket.status = status.upper()
        session.add(ticket)
        session.commit()
    rprint(f"[green]✓ Moved Ticket #{ticket_id} to {status.upper()}[/green]")

@app.command("groom-read")
def groom_read():
    """Output unestimated backlog tickets as JSON for AI grooming."""
    with get_session() as session:
        # Find tickets in Backlog that have 0 points OR missing description
        statement = select(Ticket).where(
            (Ticket.sprint == "Backlog") & 
            ((Ticket.points == 0) | (Ticket.description == None)) &
            (Ticket.status != "DONE")
        )
        tickets = session.exec(statement).all()
        
    data = [t.model_dump(mode='json') for t in tickets]
    print(json.dumps(data, indent=2))

@app.command("agent-read")
def agent_read():
    """Output OPEN tickets assigned to AI as JSON (Machine Readable)."""
    with get_session() as session:
        statement = select(Ticket).where(Ticket.assignee == "ai").where(Ticket.status != "DONE")
        tickets = session.exec(statement).all()
        
    # Convert to dict manually for clean JSON output
    data = [t.model_dump(mode='json') for t in tickets]
    print(json.dumps(data, indent=2))

if __name__ == "__main__":
    app()
