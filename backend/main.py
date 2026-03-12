"""
ACCA AA AI Marker - Backend Entry Point
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
from backend.api import upload


# Load environment variables
load_dotenv()

# Create FastAPI app
app = FastAPI(
    title="ACCA AA AI Marker API",
    description="API for marking ACCA AA exam answers",
    version="0.1.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "message": "ACCA AA AI Marker API",
        "status": "running",
        "version": "0.1.0"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Import and include routers (we'll add these later)
app.include_router(upload.router)
# app.include_router(upload.router, prefix="/api/v1/upload", tags=["upload"])
# app.include_router(mark.router, prefix="/api/v1/mark", tags=["mark"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)