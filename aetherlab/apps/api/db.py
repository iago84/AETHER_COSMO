from aetherlab.packages.aether_core.db import SessionLocal
from sqlalchemy.orm import Session
from contextlib import contextmanager

@contextmanager
def get_session() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
