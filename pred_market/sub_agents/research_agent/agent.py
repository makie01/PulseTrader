import os
import dotenv
from perplexity import Perplexity
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters
from .prompt import RESEARCH_AGENT_PROMPT

dotenv.load_dotenv()
PERPLEXITY_API_KEY_ID = os.getenv("PERPLEXITY_API_KEY_ID")
print("PERPLEXITY_API_KEY_ID: ", PERPLEXITY_API_KEY_ID)
if not PERPLEXITY_API_KEY_ID:
    raise RuntimeError("PERPLEXITY_API_KEY_ID is not set in the environment")

# Initialize Perplexity client
_perplexity_client = None

def get_perplexity_client():
    """Get the Perplexity client."""
    perplexity_client = Perplexity(api_key=PERPLEXITY_API_KEY_ID)
    return perplexity_client

def query_sonar_pro(message: str) -> str:
    """
    Query Perplexity Sonar Pro model with a message and return the response.
    
    Args:
        message: The message/query to send to Sonar Pro
        
    Returns:
        The response content from Sonar Pro
    """
    client = get_perplexity_client()
    completion = client.chat.completions.create(
        model="sonar-pro",
        messages=[
            {"role": "user", "content": message}
        ]
    )
    return completion.choices[0].message.content

# Create the tool for the agent
sonar_pro_tool = FunctionTool(
    func=query_sonar_pro,
    name="query_sonar_pro",
    description="Query Perplexity Sonar Pro model for comprehensive research and analysis. Use this tool to get in-depth research, analysis, and context on prediction markets and related topics."
)

# mcp_true = False
# if mcp_true:
#     perplexity_mcp = McpToolset(
#             connection_params=StdioConnectionParams(
#                 server_params=StdioServerParameters(
#                     command="/usr/local/bin/npx", # This is the path to the npx command on my machine
#                     args=[
#                         "-y",
#                         "@perplexity-ai/mcp-server",
#                     ],
#                     env={
#                         "PERPLEXITY_API_KEY": PERPLEXITY_API_KEY_ID,
#                         # "PERPLEXITY_TIMEOUT_MS": "600000",
#                     },
#                 ),
#                 timeout=720,
#             ),
#             # Optional: only expose some of the MCP tools to the agent
#             tool_filter=["perplexity_research"] # ["perplexity_search",
#         )

perplexity_news_research_agent = LlmAgent(
    model="gemini-2.0-flash",
    name="perplexity_news_research_agent",
    instruction=RESEARCH_AGENT_PROMPT,
    tools=[
        sonar_pro_tool,
    ],
)




