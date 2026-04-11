from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.db.database import create_all_tables

app = FastAPI(title="AI Job Application Assistant API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Custom response headers are not readable from fetch() cross-origin unless exposed.
    expose_headers=["X-Resume-OCR-Status"],
)


@app.on_event("startup")
def on_startup() -> None:
    create_all_tables()


app.include_router(router)
