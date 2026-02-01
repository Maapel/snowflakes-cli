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
