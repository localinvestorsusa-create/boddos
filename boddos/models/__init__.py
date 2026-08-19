"""Local model providers and the pluggable 'Assistant' registry."""
from .base import ModelProvider, ChatMessage
from .ollama_adapter import OllamaProvider

__all__ = ["ModelProvider", "ChatMessage", "OllamaProvider"]
