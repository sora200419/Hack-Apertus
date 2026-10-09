"""OriginPass evaluation harness (E1 HS classification, E2 origin engine, E3 dossier, E4 cost).

Run from src/api (locally, with PYTHONPATH pointing at src) or from /app in Docker:
    python -m eval.run_all
"""

import sys
from pathlib import Path

# Local checkout: src/eval sits next to src/api, which holds the `originpass` package.
_API_DIR = Path(__file__).resolve().parent.parent / "api"
if (_API_DIR / "originpass").is_dir() and str(_API_DIR) not in sys.path:
    sys.path.append(str(_API_DIR))
