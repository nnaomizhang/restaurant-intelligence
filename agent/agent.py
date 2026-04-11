"""
Restaurant Intelligence Agent
==============================
LangChain agent powered by OpenAI GPT-4o.
Uses 8 tools to answer questions about restaurants
in Shoreditch, Peckham and Hackney.
"""

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.prompts import ChatPromptTemplate

from config import OPENAI_API_KEY
from agent.tools import ALL_TOOLS
from agent.logger import log_query
from agent.validator import validate_response


SYSTEM_PROMPT = """You are a restaurant intelligence assistant for London neighbourhoods.
You have access to data about restaurants in Shoreditch, Peckham and Hackney.

Your data sources include:
- Google Places: ratings, reviews, coordinates, opening hours
- FSA: official hygiene ratings (0-5 scale)
- Companies House: business registration and financial health
- Deliveroo: menu items and prices
- ONS Census: demographic data about each neighbourhood

When answering questions:
1. Always use the available tools to retrieve real data
2. Cite your sources (e.g. "According to FSA data...")
3. Be specific with numbers and ratings
4. If asked to compare neighbourhoods use the compare_neighbourhoods tool
5. For semantic searches use the search_reviews tool
6. Never mention restaurant names that you haven't retrieved from the tools
7. If you cannot find specific data, say so clearly rather than making up examples
8. For cuisine-specific queries (Chinese, sushi, Indian etc.) use search_reviews tool with the cuisine as the query — NOT get_top_restaurants which filters by business_type not cuisine
9. When asked about "best X restaurant" always use search_reviews first to find cuisine matches, then get_hygiene_rating to enrich results

Target neighbourhoods: Shoreditch, Peckham, Hackney
"""


def get_agent():
    """Create and return the agent executor."""
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        api_key=OPENAI_API_KEY,
        temperature=0,
    )

    agent = create_react_agent(
        llm,
        ALL_TOOLS,
        prompt=SYSTEM_PROMPT,
    )

    return agent


def run_query(question: str, neighbourhood: str = None, history: list = None) -> dict:
    """
    Run a query through the agent with conversation history.
    Returns answer, tools used, and validation result.
    """
    import time
    start = time.time()

    if neighbourhood:
        question = f"[Focus on {neighbourhood}] {question}"

    agent = get_agent()

    # Build messages with history
    messages = []
    for msg in (history or []):
        if msg["role"] == "user":
            messages.append(("human", msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(("ai", msg["content"]))
    messages.append(("human", question))

    try:
        result = agent.invoke({"messages": messages})
        answer = result["messages"][-1].content
    except Exception as e:
        answer = f"Error: {str(e)}"

    latency_ms = int((time.time() - start) * 1000)
    validation = validate_response(answer)
    log_query(query=question, answer=answer, latency_ms=latency_ms, validation=validation)

    return {
        "answer": answer,
        "latency_ms": latency_ms,
        "validation": validation,
    }


if __name__ == "__main__":
    result = run_query("What are the top rated restaurants in Shoreditch?")
    print(f"\nAnswer: {result['answer']}")
    print(f"Latency: {result['latency_ms']}ms")