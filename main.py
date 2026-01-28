import typer
import json
from typing import Optional, List
from sqlmodel import select
from rich.console import Console
from rich.table import Table
from rich import print as rprint
from rich.columns import Columns
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt

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
    title: Optional[str] = typer.Argument(None), 
    desc: Optional[str] = typer.Option(None, help="Description of the ticket"), 
    type: Optional[str] = typer.Option(None, help="Type: STORY, TASK, BUG"),
    assign: Optional[str] = typer.Option(None, help="Assignee (e.g., me, ai, name)"), 
    prio: Optional[str] = typer.Option(None, help="Priority: LOW, MEDIUM, HIGH"),
    points: Optional[int] = typer.Option(None, help="Story Points"),
    sprint: Optional[str] = typer.Option(None, help="Sprint name"),
    interactive: bool = typer.Option(True, help="Enable interactive prompts if args missing")
):
    """Create a new ticket. Interactive by default if arguments are missing."""
    
    # Interactive Mode
    if interactive and not title:
        rprint("[bold cyan]❄️  New Ticket Wizard[/bold cyan]")
        title = Prompt.ask("Title")
        
        if not type:
            type = Prompt.ask("Type", choices=["STORY", "TASK", "BUG"], default="TASK")
        
        if not points:
             points = IntPrompt.ask("Points", default=0)
             
        if not assign:
             assign = Prompt.ask("Assignee", default="me")
             
        if not sprint:
             sprint = Prompt.ask("Sprint", default="Backlog")
        
        if not prio:
             prio = Prompt.ask("Priority", choices=["LOW", "MEDIUM", "HIGH"], default="MEDIUM")

    # Defaults if non-interactive and missing
    if not title:
        rprint("[red]Title is required.[/red]")
        raise typer.Exit(code=1)
        
    type = type or "TASK"
    assign = assign or "me"
    prio = prio or "MEDIUM"
    points = points or 0
    sprint = sprint or "Backlog"

    with get_session() as session:
        ticket = Ticket(
            title=title, 
            description=desc, 
            type=type.upper(),
            assignee=assign.lower(), 
            priority=prio.upper(),
            points=points,
            sprint=sprint
        )
        session.add(ticket)
        session.commit()
        session.refresh(ticket)
    
    rprint(f"[green]✓ Created {ticket.type} #{ticket.id}:[/green] {title}")

@app.command("list")
def list_tickets(
    all: bool = False, 
    sprint: Optional[str] = None,
    assignee: Optional[str] = typer.Option(None, "--assignee", "-u", help="Filter by user")
):
    """List open tickets. Options: --all, --sprint, --assignee."""
    with get_session() as session:
        query = select(Ticket)
        if not all:
            query = query.where(Ticket.status != "DONE")
        if sprint:
            query = query.where(Ticket.sprint == sprint)
        if assignee:
            # Simple substring match or exact match? Exact is safer for "me" vs "men"
            query = query.where(Ticket.assignee == assignee.lower())
            
        tickets = session.exec(query).all()

    if not tickets:
        rprint("[yellow]No tickets found.[/yellow]")
        return

    table = Table(title=f"Snowflakes ❄️  ({sprint if sprint else 'All Sprints'})")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Type", style="bold")
    table.add_column("Status", style="magenta")
    table.add_column("Sprint")
    table.add_column("Pts")
    table.add_column("Assignee")
    table.add_column("Title")

    for t in tickets:
        assignee_style = "bold purple" if t.assignee == "ai" else "blue"
        # Removed EPIC icon, added simple mapping
        type_icon = "🐞" if t.type == "BUG" else "📝" if t.type == "STORY" else "🔨"
        
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
def board(
    sprint: str = "Backlog",
    assignee: Optional[str] = typer.Option(None, "--assignee", "-u", help="Filter by user")
):
    """View the project as a Kanban Board."""
    with get_session() as session:
        query = select(Ticket)
        if sprint != "ALL":
             query = query.where(Ticket.sprint == sprint)
        
        if assignee:
            query = query.where(Ticket.assignee == assignee.lower())
            
        tickets = session.exec(query).all()

    # Buckets
    todo_panels = []
    prog_panels = []
    done_panels = []
    review_panels = [] 

    for t in tickets:
        # Visual cues
        color = "cyan" if t.type == "STORY" else "red" if t.type == "BUG" else "green"
        icon = "🐞" if t.type == "BUG" else "📝" if t.type == "STORY" else "🔨"
        
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

@app.command("close-sprint")
def close_sprint(
    current_sprint: str, 
    next_sprint: str = typer.Option("Backlog", help="Where to move unfinished tickets")
):
    """Close a sprint: Move unfinished tickets to the next sprint (or Backlog)."""
    with get_session() as session:
        # Find unfinished tickets in current sprint
        statement = select(Ticket).where(
            (Ticket.sprint == current_sprint) & 
            (Ticket.status != "DONE")
        )
        tickets = session.exec(statement).all()
        
        if not tickets:
            rprint(f"[green]Sprint {current_sprint} is clear! No open tickets to move.[/green]")
            return

        for t in tickets:
            t.sprint = next_sprint
            session.add(t)
        
        session.commit()
        
    rprint(f"[green]✓ Closed Sprint '{current_sprint}'. Moved {len(tickets)} unfinished tickets to '{next_sprint}'.[/green]")

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
