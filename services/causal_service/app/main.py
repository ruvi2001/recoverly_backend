from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as main_router
from app.api.auth_routes import router as auth_router

from app.core.config import CORS_ALLOW_ORIGINS
from app.db.database import engine
from app.db.models import Base

app = FastAPI()


@app.on_event("startup")
def startup():
    # DB connection test
    with engine.connect() as conn:
        conn.exec_driver_sql("SELECT 1;")

    # Create tables
    Base.metadata.create_all(bind=engine)


app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# auth first
app.include_router(auth_router, prefix="/api")
# main routes
app.include_router(main_router, prefix="/api")