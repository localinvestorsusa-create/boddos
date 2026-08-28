"""External-world services: weather, translation, calling, drone control."""
from .weather import get_forecast
from .translate import translate_to_english
from .drone import DroneAdapter
from .calling import CallingAdapter
from .notify import Notifier
from .push import PushManager
from .routing import geocode, route, directions

__all__ = [
    "get_forecast",
    "translate_to_english",
    "DroneAdapter",
    "CallingAdapter",
    "Notifier",
    "PushManager",
    "geocode",
    "route",
    "directions",
]
