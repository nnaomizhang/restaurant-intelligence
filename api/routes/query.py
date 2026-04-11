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
    try:
        from agent.agent import run_query
        result = run_query(
            question=body.question,
            neighbourhood=body.neighbourhood,
            history=body.history or [],
        )
        return {
            "answer": result["answer"],
            "latency_ms": result["latency_ms"],
            "validation": result["validation"],
            "sources": result["validation"].get("verified_restaurants", []),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query/stream")
async def stream_query(body: QueryRequest):
    """
    Stream agent response token by token using SSE.
    """
    async def generate():
        try:
            from agent.agent import run_query
            result = run_query(
                question=body.question,
                neighbourhood=body.neighbourhood,
            )
            words = result["answer"].split()
            for word in words:
                yield f"data: {word} \n\n"
            yield f"data: [DONE]\n\n"
        except Exception as e:
            yield f"data: Error: {str(e)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream"
    )