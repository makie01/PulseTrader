from google.adk.agents import Agent
from google.adk.tools import google_search
from .prompt import RESEARCH_AGENT_PROMPT


research_agent = Agent(
    name='research_agent',
    model='gemini-2.5-pro',
    description="Researches specific Kalshi markets and explains how they work, including settlement criteria and market mechanics.",
    instruction=RESEARCH_AGENT_PROMPT,
    tools=[google_search],
)

