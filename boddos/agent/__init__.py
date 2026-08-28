"""OS agent: run allowlisted tasks on THIS machine, and fetch/parse the web."""
from .os_agent import OSAgent, AgentResult
from .web import fetch_url

__all__ = ["OSAgent", "AgentResult", "fetch_url"]
