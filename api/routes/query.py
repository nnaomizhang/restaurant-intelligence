"""
Query endpoint — natural language questions to the agent.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from api.schemas import QueryRequest, QueryResponse
import json

router = APIRouter()


@router.post("/query")
async def query_agent(body: QueryRequest):
    """
    Send a natural language question to the agent.
    Returns a JSON response with the answer.
    Agent will be wired in Phase 6.
    """
    # Placeholder until agent is built in Phase 6
    return QueryResponse(
        answer=f"Agent not yet configured. Question received: {body.question}",
        sources=[]
    )


@router.post("/query/stream")
async def stream_query(body: QueryRequest):
    """
    Stream agent response token by token using SSE.
    """
    async def generate():
        # Placeholder until agent is built in Phase 6
        response = f"Streaming agent not yet configured. Question: {body.question}"
        for word in response.split():
            yield f"data: {word} \n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream"
    )