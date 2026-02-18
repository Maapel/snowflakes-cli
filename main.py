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
from models import Ticket, Comment
from database import init_db, get_session
import sys
import os
import signal
import subprocess
import webbrowser
import time
import shutil

HOME_DIR = os.path.expanduser("~/.snowflakes")
PID_FILE = os.path.join(HOME_DIR, "server.pid")

def get_pid():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                return int(f.read().strip())
        except:
            return None
    return None

def save_pid(pid):
    os.makedirs(HOME_DIR, exist_ok=True)
    with open(PID_FILE, "w") as f:
        f.write(str(pid))

def remove_pid():
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)

# Add logic functions for comments
def create_comment_logic(ticket_id: int, content: str, author: str = "me"):
    with get_session() as session:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            raise ValueError(f"Ticket #{ticket_id} not found")
        
        comment = Comment(
            ticket_id=ticket_id,
            content=content,
            author=author
        )
        session.add(comment)
        session.commit()
        session.refresh(comment)
        return comment

def list_comments_logic(ticket_id: int):
    with get_session() as session:
        statement = select(Comment).where(Comment.ticket_id == ticket_id).order_by(Comment.created_at)
        return session.exec(statement).all()

app = typer.Typer(add_completion=False)
console = Console()

@app.command()
def view(ticket_id: int):
    """View ticket details and conversation."""
    with get_session() as session:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            rprint(f"[red]Ticket #{ticket_id} not found.[/red]")
            raise typer.Exit(code=1)
        
        comments = list_comments_logic(ticket_id)

    # Render Ticket Info
    rprint(Panel(
        f"[bold cyan]{ticket.title}[/bold cyan]\n"
        f"[dim]{ticket.description or 'No description'}[/dim]\n\n"
        f"Status: [magenta]{ticket.status}[/magenta] | Prio: {ticket.priority} | Pts: {ticket.points}\n"
        f"Assignee: [purple]{ticket.assignee}[/purple] | Sprint: {ticket.sprint}",
        title=f"Ticket #{ticket.id} [{ticket.type}]",
        expand=False
    ))

    if ticket.resolution_notes:
        rprint(Panel(f"[green]{ticket.resolution_notes}[/green]", title="Resolution Notes", expand=False))

    # Render Conversation
    if comments:
        rprint("\n[bold]Conversation:[/bold]")
        for c in comments:
            author_style = "bold purple" if c.author == "ai" else "bold blue"
            rprint(f"[{author_style}]{c.author}[/{author_style}] [dim]({c.created_at.strftime('%Y-%m-%d %H:%M')})[/dim]")
            rprint(f"  {c.content}\n")
    else:
        rprint("\n[dim]No comments yet.[/dim]")

@app.command()
def comment(
    ticket_id: int, 
    content: str = typer.Argument(..., help="Comment text"),
    author: str = typer.Option("me", help="Author of the comment")
):
    """Add a comment to a ticket."""
    try:
        create_comment_logic(ticket_id, content, author)
        rprint(f"[green]✓ Added comment to Ticket #{ticket_id}[/green]")
    except ValueError as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(code=1)

@app.callback(invoke_without_command=True)
def callback(
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Path to project root. Defaults to CWD."),
    agent_help: bool = typer.Option(False, "--agent-help", help="Print instructions for AI agents and exit.")
):
    """
    Snowflakes: A local-first Project Management System.
    """
    if agent_help:
        rprint("""[bold cyan]❄️ Snowflakes AI Protocol[/bold cyan]

[bold]1. Overview[/bold]
Snowflakes is a local-first PM system. Data is in `snowflakes.db`.
Use `sw --project <path>` if the DB is not in the current directory.

[bold]2. Core Loop[/bold]
1. [green]SCAN[/green]: `sw agent-read` -> Get assigned OPEN tickets + full conversation history.
2. [yellow]SIGNAL[/yellow]: `sw move <ID> IN_PROGRESS` -> Let others know you are working.
3. [magenta]COMMUNICATE[/magenta]: 
   - If blocked: `sw comment <ID> "Missing API key for X" --author ai`
   - If update needed: `sw comment <ID> "Refactored the auth logic" --author ai`
4. [blue]RESOLVE[/blue]: `sw resolve <ID> --notes "Fixed in commit a1b2c3"` -> Close ticket.

[bold]3. Commands for Agents[/bold]
- `sw agent-read`: JSON dump of AI-assigned tickets including all comments.
- `sw comment <ID> <TEXT> --author ai`: Add to the ticket conversation.
- `sw view <ID>`: See full ticket details and human-readable conversation.
- `sw move <ID> <STATUS>`: Update status (TODO, IN_PROGRESS, REVIEW, DONE).
- `sw groom-read`: Find backlog tasks needing description or estimation.

[bold]4. System Prompt Hint[/bold]
"You are a software engineer agent. Use `sw agent-read` to find your tasks. 
Always signal progress with `sw move` and use `sw comment --author ai` 
to report blockers or provide technical notes during the task lifecycle."
""")
        raise typer.Exit()

    if project:
        os.environ["SNOWFLAKES_ROOT"] = os.path.abspath(project)
        
    # Initialize DB in project folder (or current folder) on every run
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
        
        if not desc:
            desc = Prompt.ask("Description", default="")
        
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

    ticket = create_ticket_logic(title, desc, type, assign, prio, points, sprint)
    rprint(f"[green]✓ Created {ticket.type} #{ticket.id}:[/green] {title}")

def create_ticket_logic(title, desc, type, assign, prio, points, sprint):
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
        return ticket

@app.command("list")
def list_tickets(
    all: bool = False, 
    sprint: Optional[str] = None,
    assignee: Optional[str] = typer.Option(None, "--assignee", "-u", help="Filter by user"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """List open tickets. Options: --all, --sprint, --assignee, --json."""
    tickets = list_tickets_logic(all, sprint, assignee)

    if json_output:
        data = [t.model_dump(mode='json') for t in tickets]
        print(json.dumps(data, indent=2))
        return

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

def list_tickets_logic(all: bool = False, sprint: Optional[str] = None, assignee: Optional[str] = None):
    with get_session() as session:
        query = select(Ticket)
        if not all:
            query = query.where(Ticket.status != "DONE")
        if sprint:
            query = query.where(Ticket.sprint == sprint)
        if assignee:
            # Simple substring match or exact match? Exact is safer for "me" vs "men"
            query = query.where(Ticket.assignee == assignee.lower())
            
        return session.exec(query).all()

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
        
        move_ticket_logic(ticket_id, status)
        
    rprint(f"[green]✓ Moved Ticket #{ticket_id} to {status.upper()}[/green]")

def move_ticket_logic(ticket_id: int, status: str):
    """
    Moves a ticket to a new status.
    Raises ValueError if ticket not found.
    """
    with get_session() as session:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            raise ValueError(f"Ticket {ticket_id} not found")
            
        ticket.status = status.upper()
        session.add(ticket)
        session.commit()
        session.refresh(ticket)
        return ticket

@app.command()
def edit(
    ticket_id: int,
    title: Optional[str] = typer.Option(None, help="New title"),
    desc: Optional[str] = typer.Option(None, help="New description"),
    type: Optional[str] = typer.Option(None, help="New type"),
    prio: Optional[str] = typer.Option(None, help="New priority"),
):
    """Edit an existing ticket's details."""
    try:
        updated = edit_ticket_logic(ticket_id, title, desc, type, prio)
        rprint(f"[green]✓ Updated Ticket #{ticket_id}:[/green] {updated.title}")
    except ValueError as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(code=1)

def edit_ticket_logic(ticket_id: int, title=None, desc=None, type=None, prio=None):
    with get_session() as session:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            raise ValueError(f"Ticket #{ticket_id} not found")
        
        if title: ticket.title = title
        if desc: ticket.description = desc
        if type: ticket.type = type.upper()
        if prio: ticket.priority = prio.upper()
        
        session.add(ticket)
        session.commit()
        session.refresh(ticket)
        return ticket

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
    """Output OPEN tickets assigned to AI as JSON (Machine Readable). Includes conversation history."""
    with get_session() as session:
        statement = select(Ticket).where(Ticket.assignee == "ai").where(Ticket.status != "DONE")
        tickets = session.exec(statement).all()
        
    data = []
    for t in tickets:
        ticket_data = t.model_dump(mode='json')
        comments = list_comments_logic(t.id)
        ticket_data["comments"] = [c.model_dump(mode='json') for c in comments]
        data.append(ticket_data)
        
    print(json.dumps(data, indent=2))

@app.command("internal-server", hidden=True)
def internal_server(
    port: int = 8000,
    host: str = "0.0.0.0",
    reload: bool = False
):
    """Run the uvicorn server directly (blocking). Used internally."""
    import uvicorn
    # Import app inside function to avoid startup cost for CLI commands
    from server import app as fast_app
    
    # Check if we are frozen (PyInstaller)
    if getattr(sys, 'frozen', False):
        # When frozen, reload must be False
        uvicorn.run(fast_app, host=host, port=port, reload=False)
    else:
        uvicorn.run("server:app", host=host, port=port, reload=reload)

@app.command("start")
def start_server(
    port: int = typer.Option(8000, help="Port to run the UI on"),
    host: str = typer.Option("0.0.0.0", help="Host to run the UI on")
):
    """Start the Snowflakes UI in the background."""
    pid = get_pid()
    if pid:
        # Check if process is actually running
        try:
            os.kill(pid, 0)
            rprint(f"[yellow]❄️  Snowflakes is already running (PID: {pid}). Opening browser...[/yellow]")
            webbrowser.open(f"http://{host}:{port}")
            return
        except OSError:
            # Process doesn't exist, clean up PID file
            remove_pid()

    rprint(f"[green]❄️  Starting Snowflakes UI at http://{host}:{port}...[/green]")
    
    # Construct command to run 'internal-server'
    if getattr(sys, 'frozen', False):
        cmd = [sys.executable, "internal-server", "--port", str(port), "--host", host]
        
        # Extract static files to persistent location
        static_src = os.path.join(sys._MEIPASS, "static")
        static_dst = os.path.join(HOME_DIR, "static")
        if os.path.exists(static_src):
            # Clean update of static files
            shutil.copytree(static_src, static_dst, dirs_exist_ok=True)
            
    else:
        cmd = [sys.executable, "main.py", "internal-server", "--port", str(port), "--host", host]
        
    # Sanitize environment for PyInstaller background process
    env = os.environ.copy()
    
    # Set static dir for server
    env["SNOWFLAKES_STATIC_DIR"] = os.path.join(HOME_DIR, "static")

    if getattr(sys, 'frozen', False):
        # Prevent child from inheriting 'LD_LIBRARY_PATH' pointing to parent's temp dir
        # which will be deleted when parent exits.
        env.pop('LD_LIBRARY_PATH', None)
        env.pop('LD_LIBRARY_PATH_ORIG', None)
        env.pop('_MEIPASS2', None)
        
    # Spawn background process
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=env
    )
    
    save_pid(proc.pid)
    
    # Wait a moment for server to likely come up
    time.sleep(1)
    
    # Suppress output to prevent "Broken pipe" from browser
    with open(os.devnull, 'w') as devnull:
        saved_stdout = sys.stdout
        saved_stderr = sys.stderr
        try:
            sys.stdout = devnull
            sys.stderr = devnull
            webbrowser.open(f"http://{host}:{port}")
        finally:
            sys.stdout = saved_stdout
            sys.stderr = saved_stderr

@app.command("stop")
def stop_server():
    """Stop the running Snowflakes UI."""
    pid = get_pid()
    if not pid:
        rprint("[red]❄️  No active Snowflakes server found.[/red]")
        return
        
    try:
        os.kill(pid, signal.SIGTERM)
        rprint(f"[green]✓ Stopped Snowflakes server (PID: {pid})[/green]")
    except OSError:
        rprint(f"[yellow]Process {pid} not found. Cleaning up lock file.[/yellow]")
        
    remove_pid()

if __name__ == "__main__":
    app()
