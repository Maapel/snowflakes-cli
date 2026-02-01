# Snowflakes

A local-first Project Management System bundled as a single binary. It combines a CLI, a Kanban board, and a JSON-protocol for AI agents into one tool.

The data lives in a `snowflakes.db` SQLite file in your project root. No cloud, no login, no setup.

## Installation

### Method 1: Single Binary (Recommended)

Build it once, put it in your path, and use it anywhere.

```bash
# 1. Clone and install dependencies
git clone https://github.com/Maapel/snowflakes-cli.git
cd snowflakes-cli
pip install -r requirements.txt

# 2. Compile to binary
python build.py

# 3. Move to path (Linux/Mac example)
mv dist/snowflakes /usr/local/bin/sw

```

### Method 2: Python

```bash
pip install -r requirements.txt
alias sw="python main.py"

```

## Usage

Snowflakes is designed to be fast. Initialize a board in any directory by running a command.

### CLI Workflow

```bash
# Interactive wizard to create tickets
sw new

# One-line creation (Title is required)
sw new "Fix auth middleware" --type BUG --prio HIGH --assign ai

# List all open tickets
sw list

# View terminal Kanban board
sw board
sw board --sprint "Sprint-1"

```

### Management

```bash
# Start work
sw move 1 IN_PROGRESS

# Assign story points (Fibonacci: 1, 2, 3, 5, 8...)
sw estimate 1 5

# Add to sprint
sw sprint "Sprint-1" 1 2 3

# Close a sprint (moves unfinished tasks to next sprint)
sw close-sprint "Sprint-1" --next-sprint "Sprint-2"

```

### Web UI

Includes a local web interface for drag-and-drop management.

```bash
sw start
# Opens http://127.0.0.1:8000
sw stop
# Stops the running UI
```

## AI Integration

Snowflakes exposes project state as machine-readable JSON. This allows AI agents (Cursor, Windsurf, generic scripts) to read the board, pick up tasks, and report progress without hallucinating ticket IDs.

### The Protocol

**1. Reading State (`agent-read`)**
Agents should run this to find assigned work. It returns only `OPEN` tickets assigned to `ai`.

```bash
sw agent-read

```

*Output:*

```json
[
  {
    "id": 1,
    "title": "Refactor auth middleware",
    "description": "Switch to JWT...",
    "type": "TASK",
    "status": "TODO"
  }
]

```

**2. Grooming Backlog (`groom-read`)**
Agents can run this to find tasks that need estimation or details (0 points or missing description).

```bash
sw groom-read

```

**3. Execution Loop**
A standard agent workflow looks like this:

1. `sw agent-read` -> Agent parses JSON.
2. `sw move <ID> IN_PROGRESS` -> Agent signals start.
3. [Agent writes code]
4. `sw resolve <ID> --notes "Fixed via PR #12"` -> Agent closes ticket.

## Command Reference

| Command | Description | Options |
| :--- | :--- | :--- |
| `new` | Create a new ticket. Interactive by default. | `--type`, `--prio`, `--assign` |
| `list` | List open tickets. | `--all`, `--sprint`, `--assignee`, `--json` |
| `board` | View the Kanban Board. | `--sprint` |
| `close-sprint` | Close a sprint and migrate tickets. | `--next-sprint` (required) |
| `resolve` | Mark a ticket as DONE. | `--notes` (required) |
| `estimate` | Assign complexity points. | `ID POINTS` |
| `sprint` | Bulk assign tickets to a sprint. | `NAME ID...` |
| `move` | Move a ticket to a new status. | `ID STATUS` |
| `groom-read` | JSON output of unestimated backlog tickets. | |
| `agent-read` | JSON output of AI-assigned OPEN tickets. | |
| `start` | Start the Snowflakes Web UI. | |
| `stop` | Stop the running Snowflakes Web UI. | |

## Configuration

| Env Variable | Description | Default |
| :--- | :--- | :--- |
| `SNOWFLAKES_ROOT` | Path to the database file. | Current Working Directory |
