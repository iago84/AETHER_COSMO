from typing import Optional
from datetime import datetime
from sqlalchemy.orm import declarative_base, relationship, Mapped, mapped_column
from sqlalchemy import String, Integer, ForeignKey, DateTime, func, Text

Base = declarative_base()

class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    experiments: Mapped[list["Experiment"]] = relationship(back_populates="project", cascade="all, delete-orphan")

class Experiment(Base):
    __tablename__ = "experiments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    project: Mapped["Project"] = relationship(back_populates="experiments")
    runs: Mapped[list["SimulationRun"]] = relationship(back_populates="experiment", cascade="all, delete-orphan")

class SimulationRun(Base):
    __tablename__ = "simulation_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="created")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    snapshot_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    job_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    experiment: Mapped["Experiment"] = relationship(back_populates="runs")
