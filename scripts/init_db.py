import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aetherlab.packages.aether_core.db import ENGINE
from aetherlab.packages.aether_core.models_db import Base

if __name__ == "__main__":
    Base.metadata.create_all(bind=ENGINE)
    print("OK")
