from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import settings

app = FastAPI(title="AI Job Application Assistant API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    # Custom response headers are not readable from fetch() cross-origin unless exposed.
    expose_headers=["X-Resume-OCR-Status"],
)

app.include_router(router)
