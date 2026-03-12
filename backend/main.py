"""
ACCA AA AI Marker - backend entrypoint.
"""

from __future__ import annotations

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api import knowledge, upload
from backend.api import mark


load_dotenv()

app = FastAPI(
    title="ACCA AA AI Marker API",
    description="API for marking ACCA AA exam answers",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"message": "ACCA AA AI Marker API", "status": "running", "version": "0.1.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}

app.include_router(mark.router)
app.include_router(upload.router)
app.include_router(knowledge.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
