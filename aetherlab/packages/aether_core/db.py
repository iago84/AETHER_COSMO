import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def default_sqlite_url(root: str | None = None) -> str:
    if root is None:
        root = str(Path(__file__).resolve().parents[3])
    db_path = Path(root) / "aetherlab" / "data" / "outputs" / "aetherlab.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+pysqlite:///{db_path.as_posix()}"


def make_engine():
    url = os.environ.get("AETHERLAB_DB_URL") or default_sqlite_url()
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
        if ":memory:" in url:
            return create_engine(url, future=True, connect_args=connect_args, poolclass=StaticPool)
        return create_engine(url, future=True, connect_args=connect_args)
    return create_engine(url, future=True)


ENGINE = make_engine()
SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False, future=True)


def ensure_schema():
    try:
        with ENGINE.connect() as conn:
            dialect = conn.engine.dialect.name
            if dialect == "sqlite":
                rows = conn.execute(text("PRAGMA table_info('simulation_runs')")).all()
                cols = {r[1] for r in rows}
                if "job_id" not in cols:
                    conn.execute(text("ALTER TABLE simulation_runs ADD COLUMN job_id VARCHAR(100) NULL"))
                    conn.commit()
            elif dialect in ("postgresql", "postgres"):
                conn.execute(text("ALTER TABLE IF EXISTS simulation_runs ADD COLUMN IF NOT EXISTS job_id VARCHAR(100)"))
                conn.commit()
    except Exception:
        pass
