import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import uvicorn

sys.path.insert(0, str(Path(__file__).parent))

if __name__ == "__main__":
    print("Starting Recommendation Service")

    uvicorn.run(
        "api.routes:app",
        host="0.0.0.0",
        port=8003,
        reload=True,
        log_level="info",
    )