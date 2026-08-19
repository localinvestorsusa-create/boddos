"""External-world services: weather, translation, calling, drone control."""
from .weather import get_forecast
from .translate import translate_to_english
from .drone import DroneAdapter
from .calling import CallingAdapter

__all__ = [
    "get_forecast",
    "translate_to_english",
    "DroneAdapter",
    "CallingAdapter",
]
