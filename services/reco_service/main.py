import sys
from pathlib import Path
from fastapi import FastAPI
import uvicorn

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

sys.path.insert(0, str(Path(__file__).parent))

from api.routes import router, public_router

app = FastAPI(title="Recoverly Recommendation Service")

app.include_router(public_router)
app.include_router(router)

@app.get("/")
async def root():
    return {"service": "reco_service", "status": "running"}

if __name__ == "__main__":
    print("Starting Recommendation Service")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8003,
        reload=True,
        log_level="info",
    )