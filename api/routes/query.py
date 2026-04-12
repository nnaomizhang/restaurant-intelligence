"""
Query endpoint — natural language questions to the agent.
"""

import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from api.schemas import QueryRequest, QueryResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/query", response_model=QueryResponse)
async def query_agent(body: QueryRequest):
    """
    Send a natural language question to the agent.
    Returns answer with validation, sources and latency.
    Supports conversation history for multi-turn dialogue.
    """
    try:
        from agent.agent import run_query
        result = run_query(
            question=body.question,
            neighbourhood=body.neighbourhood,
            history=body.history or [],
        )
        return QueryResponse(
            answer=result["answer"],
            latency_ms=result["latency_ms"],
            validation=result["validation"],
            sources=result["validation"].get("verified_restaurants", []),
        )
    except Exception as e:
        logger.error(f"Agent query error: {e}")
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")


@router.post("/query/stream")
async def stream_query(body: QueryRequest):
    """
    Stream agent response token by token using Server-Sent Events (SSE).
    Streamlit consumes this for real-time chat output.
    """
    async def generate():
        try:
            from agent.agent import run_query
            result = run_query(
                question=body.question,
                neighbourhood=body.neighbourhood,
                history=body.history or [],
            )
            words = result["answer"].split()
            for word in words:
                yield f"data: {word} \n\n"
            # Send validation metadata at end
            import json
            yield f"data: [VALIDATION]{json.dumps(result['validation'])}\n\n"
            yield f"data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: [ERROR]{str(e)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )