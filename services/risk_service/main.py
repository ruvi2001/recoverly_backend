import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
    
import uvicorn
import sys
from pathlib import Path

# Add current directory to Python path (same pattern as social_service)
sys.path.insert(0, str(Path(__file__).parent))

if __name__ == "__main__":
    print("Starting Risk Service")

    uvicorn.run(
        "api.routes:app",   # app object inside api/routes.py
        host="0.0.0.0",
        port=8001,          # uses .env in api/routes.py too, but keep this stable like social_service
        reload=True,
        log_level="info",
    )