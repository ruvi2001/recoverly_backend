"""
Entry Point for Social Service

"""
import uvicorn
import sys
from pathlib import Path

#Add current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

if __name__ == "__main__":
    print("Starting Social Service")
    print("Port: 8002")

    uvicorn.run(
        "api.routes:app",    # Points to app object in api/routes.py
        host="0.0.0.0",
        port=8002,
        reload=True,
        log_level="info" 
    )
