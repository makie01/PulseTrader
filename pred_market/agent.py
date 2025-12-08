from google.adk.agents import Agent
from google.adk.tools import AgentTool
from .prompt import ROOT_AGENT_PROMPT
from .sub_agents.get_events_agent import event_finder_agent
from .sub_agents.research_agent import research_agent
from .sub_agents.trade_agent import execution_agent

root_agent = Agent(
    name='pred_market_agent',
    model='gemini-2.5-pro',
    description="Main agent to trade a prediction market event that has been chosen by the user.",
    instruction= ROOT_AGENT_PROMPT,
    tools=[
        AgentTool(event_finder_agent),
        AgentTool(research_agent),
        AgentTool(execution_agent),
    ],
)

