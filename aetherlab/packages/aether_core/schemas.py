from typing import Optional, Literal, List, Dict
        from pydantic import BaseModel, Field

        class SimulationConfig(BaseModel):
            dt: float = 0.01
            steps: int = 1000
            nx: int = 128
            ny: int = 128
            boundary: Literal["periodic", "fixed", "absorbing"] = "periodic"
            seed: Optional[int] = None

        class EventConfig(BaseModel):
            kind: Literal["supernova", "black_hole_merger", "pulse", "stochastic", "periodic", "dataset"] = "pulse"
            intensity: float = 1.0
            x: float = 0.5
            y: float = 0.5
            duration: float = 1.0
            frequency: Optional[float] = None

        class AetherFieldConfig(BaseModel):
            lambda_: float = Field(1.0, alias="lambda")
            diffusion: float = 0.1
            noise: float = 0.0

        class DatasetConfig(BaseModel):
            name: str
            path: str
            meta: Dict[str, str] = {}

        class ExperimentConfig(BaseModel):
            project: str
            name: str
            tags: List[str] = []

        class TrainingConfig(BaseModel):
            method: Literal["iforest", "pca", "dbscan", "autoencoder", "cae", "transformer"] = "iforest"
            params: Dict[str, float] = {}

        class ReportConfig(BaseModel):
            title: str = "AETHERLAB Report"
            include_figures: bool = True
