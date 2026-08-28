"""OS agent: run allowlisted tasks on THIS machine, and fetch/parse the web."""
from .os_agent import OSAgent, AgentResult
from .screen_agent import ScreenAgent, ScreenResult
from .web import fetch_url

__all__ = ["OSAgent", "AgentResult", "ScreenAgent", "ScreenResult", "fetch_url"]
