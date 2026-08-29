"""TP-Link Kasa smart home control — lights and plugs on your own LAN,
discovered by broadcast, not a cloud account. Reads (discover) are safe by
default; on/off/brightness/color writes go through the same tool-calling
path as everything else, so a misheard voice command is still bounded to
"toggle a light on your own network," not something with real stakes.

Needs `pip install 'boddos[smarthome]'` (python-kasa) and devices on the
same LAN/subnet as this node — Kasa's discovery is a UDP broadcast, so it
doesn't cross routers/VLANs.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..config import SmartHomeCfg

try:
    from kasa import Discover, Module
except ImportError:  # pragma: no cover - exercised via the ok=False path
    Discover = None
    Module = None


@dataclass
class DeviceInfo:
    ip: str
    alias: str
    model: str
    is_on: bool
    device_type: str
    is_dimmable: bool = False
    brightness: int | None = None
    is_color: bool = False
    hsv: tuple[int, int, int] | None = None

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class DiscoverResult:
    ok: bool
    error: str = ""
    devices: list[DeviceInfo] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "error": self.error, "devices": [d.to_dict() for d in self.devices]}


@dataclass
class ControlResult:
    ok: bool
    error: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


class SmartHomeManager:
    def __init__(self, cfg: SmartHomeCfg):
        self.cfg = cfg

    async def discover(self) -> DiscoverResult:
        if not self.cfg.enabled:
            return DiscoverResult(ok=False, error="smart home control disabled on this node (set services.smarthome.enabled: true)")
        if Discover is None:
            return DiscoverResult(ok=False, error="python-kasa not installed (pip install 'boddos[smarthome]')")
        try:
            found = await Discover.discover(discovery_timeout=self.cfg.discovery_timeout_s)
        except Exception as e:
            return DiscoverResult(ok=False, error=f"discovery failed: {e}")

        devices: list[DeviceInfo] = []
        for ip, dev in found.items():
            try:
                await dev.update()
            except Exception:
                continue
            light = dev.modules.get(Module.Light) if hasattr(dev, "modules") else None
            is_dimmable = bool(light and light.has_feature("brightness"))
            is_color = bool(light and light.has_feature("hsv"))
            devices.append(DeviceInfo(
                ip=ip, alias=dev.alias, model=dev.model, is_on=dev.is_on,
                device_type=dev.device_type.name if hasattr(dev, "device_type") else "unknown",
                is_dimmable=is_dimmable, brightness=light.brightness if is_dimmable else None,
                is_color=is_color, hsv=tuple(light.hsv) if is_color else None,
            ))
        return DiscoverResult(ok=True, devices=devices)

    async def _device(self, ip: str):
        return await Discover.discover_single(ip, discovery_timeout=self.cfg.discovery_timeout_s)

    async def turn_on(self, ip: str) -> ControlResult:
        return await self._toggle(ip, True)

    async def turn_off(self, ip: str) -> ControlResult:
        return await self._toggle(ip, False)

    async def _toggle(self, ip: str, on: bool) -> ControlResult:
        if not self.cfg.enabled:
            return ControlResult(ok=False, error="smart home control disabled on this node")
        if Discover is None:
            return ControlResult(ok=False, error="python-kasa not installed (pip install 'boddos[smarthome]')")
        try:
            dev = await self._device(ip)
            if dev is None:
                return ControlResult(ok=False, error=f"no device found at {ip}")
            await dev.update()
            await (dev.turn_on() if on else dev.turn_off())
            return ControlResult(ok=True)
        except Exception as e:
            return ControlResult(ok=False, error=f"couldn't reach {ip}: {e}")

    async def set_brightness(self, ip: str, level: int) -> ControlResult:
        if not self.cfg.enabled:
            return ControlResult(ok=False, error="smart home control disabled on this node")
        if Discover is None:
            return ControlResult(ok=False, error="python-kasa not installed (pip install 'boddos[smarthome]')")
        level = max(0, min(100, level))
        try:
            dev = await self._device(ip)
            if dev is None:
                return ControlResult(ok=False, error=f"no device found at {ip}")
            await dev.update()
            light = dev.modules.get(Module.Light) if hasattr(dev, "modules") else None
            if light is None or not light.has_feature("brightness"):
                return ControlResult(ok=False, error=f"{ip} has no dimmable light")
            await light.set_brightness(level)
            return ControlResult(ok=True)
        except Exception as e:
            return ControlResult(ok=False, error=f"couldn't reach {ip}: {e}")

    async def set_color(self, ip: str, hue: int, saturation: int, value: int) -> ControlResult:
        if not self.cfg.enabled:
            return ControlResult(ok=False, error="smart home control disabled on this node")
        if Discover is None:
            return ControlResult(ok=False, error="python-kasa not installed (pip install 'boddos[smarthome]')")
        try:
            dev = await self._device(ip)
            if dev is None:
                return ControlResult(ok=False, error=f"no device found at {ip}")
            await dev.update()
            light = dev.modules.get(Module.Light) if hasattr(dev, "modules") else None
            if light is None or not light.has_feature("hsv"):
                return ControlResult(ok=False, error=f"{ip} has no color light")
            await light.set_hsv(hue, saturation, value)
            return ControlResult(ok=True)
        except Exception as e:
            return ControlResult(ok=False, error=f"couldn't reach {ip}: {e}")
