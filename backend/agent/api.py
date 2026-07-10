"""
DRIVEWISE — Agent API Service
Exposes a FastAPI endpoint on port 8766 to process natural language queries.
"""
import sys
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add backend directory to python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.nl_query_agent import NLQueryAgent

app = FastAPI(
    title="DRIVEWISE GenAI Query Agent API",
    description="Natural language to SQL interface for multi-drive telemetry data.",
    version="1.0.0"
)

# Enable CORS for the React frontend (Vite defaults to port 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for local dev simplicity
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instantiate the query agent
agent = NLQueryAgent()

class QueryRequest(BaseModel):
    question: str

class QueryResponse(BaseModel):
    question: str
    sql: str
    chart_type: str
    data: list
    answer: str

@app.get("/health")
def health_check():
    """Verify service and DB connectivity."""
    try:
        from persistence.db import get_engine, get_dialect
        from sqlalchemy import text
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "db_dialect": get_dialect(),
            "anthropic_configured": "ANTHROPIC_API_KEY" in os.environ
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection unhealthy: {str(e)}")

@app.post("/agent/query", response_model=QueryResponse)
async def ask_agent(req: QueryRequest):
    """
    POST endpoint to query the drivewise historian database using natural language.
    """
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
        
    try:
        result = agent.query(req.question)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    # Allow port to be configurable via env
    port = int(os.environ.get("AGENT_PORT", 8766))
    uvicorn.run("api:app", host="0.0.0.0", port=port, reload=True)
