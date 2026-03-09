from sqlalchemy.orm import Session

from aetherlab.packages.aether_core.db import SessionLocal


def get_session() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
