"""
MCP Server
==========
Exposes restaurant intelligence tools via Model Context Protocol.

Tools:
  - restaurant_query    : search restaurants by neighbourhood/rating
  - review_search       : semantic search across reviews
  - market_analysis     : compare neighbourhoods
"""

import asyncio
import json
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from agent.tools import search_restaurants, search_reviews, compare_neighbourhoods

app = Server("restaurant-intelligence")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="restaurant_query",
            description="Search for restaurants by neighbourhood and minimum rating",
            inputSchema={
                "type": "object",
                "properties": {
                    "neighbourhood": {
                        "type": "string",
                        "description": "Shoreditch, Peckham or Hackney"
                    },
                    "min_rating": {
                        "type": "number",
                        "description": "Minimum Google rating (0-5)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of results"
                    }
                }
            }
        ),
        Tool(
            name="review_search",
            description="Semantically search restaurant reviews",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query"
                    },
                    "neighbourhood": {
                        "type": "string",
                        "description": "Optional neighbourhood filter"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="market_analysis",
            description="Compare restaurant markets across neighbourhoods",
            inputSchema={
                "type": "object",
                "properties": {
                    "metric": {
                        "type": "string",
                        "description": "restaurants, hygiene, demographics or menu_prices",
                        "enum": ["restaurants", "hygiene", "demographics", "menu_prices"]
                    }
                },
                "required": ["metric"]
            }
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "restaurant_query":
        result = search_restaurants.invoke(arguments)
        return [TextContent(type="text", text=result)]

    elif name == "review_search":
        result = search_reviews.invoke(arguments)
        return [TextContent(type="text", text=result)]

    elif name == "market_analysis":
        result = compare_neighbourhoods.invoke(arguments)
        return [TextContent(type="text", text=result)]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())