from contextlib import contextmanager

from sqlalchemy.orm import Session

from aetherlab.packages.aether_core.db import SessionLocal


@contextmanager
def get_session() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
