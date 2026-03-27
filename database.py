import os
from sqlmodel import SQLModel, create_engine, Session

# Name of the DB file that will appear in your project folders
DB_NAME = "snowflakes.db"

def get_db_path():
    """Returns the path to the DB. Respects SNOWFLAKES_ROOT if set."""
    root = os.environ.get("SNOWFLAKES_ROOT", os.getcwd())
    return os.path.join(root, DB_NAME)

def get_engine():
    """Creates the engine connecting to the local DB file."""
    db_url = f"sqlite:///{get_db_path()}"
    return create_engine(db_url)

def init_db():
    """Creates the tables if they don't exist."""
    engine = get_engine()
    SQLModel.metadata.create_all(engine)

def get_session():
    """Returns a new session for database operations."""
    engine = get_engine()
    return Session(engine)

# --- Central Registry ---
REGISTRY_DIR = os.path.join(os.path.expanduser("~"), ".snowflakes")
REGISTRY_DB = os.path.join(REGISTRY_DIR, "registry.db")

def get_registry_engine():
    os.makedirs(REGISTRY_DIR, exist_ok=True)
    return create_engine(f"sqlite:///{REGISTRY_DB}")

def init_registry_db():
    from models import Project
    engine = get_registry_engine()
    SQLModel.metadata.create_all(engine)

def get_registry_session():
    return Session(get_registry_engine())

def get_project_engine(project_path: str):
    """Engine for a specific project's snowflakes.db"""
    db_path = os.path.join(project_path, DB_NAME)
    return create_engine(f"sqlite:///{db_path}")

def get_project_session(project_path: str):
    return Session(get_project_engine(project_path))
