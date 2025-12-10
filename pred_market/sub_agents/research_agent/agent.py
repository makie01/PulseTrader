import os

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

# Optional: read key from env (recommended)
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
if not PERPLEXITY_API_KEY:
    raise RuntimeError("PERPLEXITY_API_KEY is not set in the environment")

perplexity_news_research_agent = LlmAgent(
    model="gemini-2.0-flash",
    name="perplexity_news_research_agent",
    instruction=(
        "You are a prediction-market research assistant. "
        "Use the Perplexity MCP tools to gather recent news, "
        "summaries, and deep research for markets the user cares about."
    ),
    tools=[
        McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command="/usr/local/bin/npx", # This is the path to the npx command on my machine
                    args=[
                        "-y",
                        "@perplexity-ai/mcp-server",
                    ],
                    env={
                        "PERPLEXITY_API_KEY": PERPLEXITY_API_KEY,
                        "PERPLEXITY_TIMEOUT_MS": "60000000",
                    },
                ),
            ),
            # Optional: only expose some of the MCP tools to the agent
            # tool_filter=["perplexity_search", "perplexity_research"]
        )
    ],
)




