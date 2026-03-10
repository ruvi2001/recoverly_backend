# services/causal_service/app/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router

# 🔹 ADD THESE TWO IMPORTS
from app.db.database import engine
from app.db.models import Base

app = FastAPI()

# 🔹 CREATE TABLES AUTOMATICALLY ON STARTUP
Base.metadata.create_all(bind=engine)

# Enable CORS (required for React frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")