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
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS schema_migrations (
                            id TEXT PRIMARY KEY,
                            applied_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
                        )
                        """
                    )
                )
                conn.commit()

                def _sqlite_cols(table: str) -> set[str]:
                    rows = conn.execute(text(f"PRAGMA table_info('{table}')")).all()
                    return {r[1] for r in rows}

                def _sqlite_add_col(table: str, col: str, ddl: str):
                    cols = _sqlite_cols(table)
                    if col in cols:
                        return
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))

                applied = {r[0] for r in conn.execute(text("SELECT id FROM schema_migrations")).all()}
                migrations = []

                def m_job_id():
                    _sqlite_add_col("simulation_runs", "job_id", "job_id VARCHAR(100) NULL")

                def m_modelrun_metrics():
                    _sqlite_add_col("model_runs", "metrics_json", "metrics_json TEXT NULL")

                def m_modelrun_params():
                    _sqlite_add_col("model_runs", "params_json", "params_json TEXT NULL")

                migrations.extend(
                    [
                        ("2026_03_12_simulation_runs_job_id", m_job_id),
                        ("2026_03_12_model_runs_params_json", m_modelrun_params),
                        ("2026_03_12_model_runs_metrics_json", m_modelrun_metrics),
                    ]
                )
                for mid, fn in migrations:
                    if mid in applied:
                        continue
                    fn()
                    conn.execute(text("INSERT INTO schema_migrations (id) VALUES (:id)"), {"id": mid})
                    conn.commit()

            elif dialect in ("postgresql", "postgres"):
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS schema_migrations (
                            id TEXT PRIMARY KEY,
                            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )
                        """
                    )
                )
                conn.commit()
                applied = {r[0] for r in conn.execute(text("SELECT id FROM schema_migrations")).all()}

                migrations: list[tuple[str, list[str]]] = [
                    (
                        "2026_03_12_simulation_runs_job_id",
                        [
                            "ALTER TABLE IF EXISTS simulation_runs ADD COLUMN IF NOT EXISTS job_id VARCHAR(100)",
                        ],
                    ),
                    (
                        "2026_03_12_model_runs_params_json",
                        [
                            "ALTER TABLE IF EXISTS model_runs ADD COLUMN IF NOT EXISTS params_json TEXT",
                        ],
                    ),
                    (
                        "2026_03_12_model_runs_metrics_json",
                        [
                            "ALTER TABLE IF EXISTS model_runs ADD COLUMN IF NOT EXISTS metrics_json TEXT",
                        ],
                    ),
                ]
                for mid, stmts in migrations:
                    if mid in applied:
                        continue
                    for stmt in stmts:
                        conn.execute(text(stmt))
                    conn.execute(text("INSERT INTO schema_migrations (id) VALUES (:id)"), {"id": mid})
                    conn.commit()
    except Exception:
        pass
