"""External camera registry + snapshot grabbing.

Add any camera with minimal info: a name and a URL. Supported source kinds:
  * snapshot — an HTTP(S) URL that returns a single JPEG/PNG frame (most IP
    cameras expose one, e.g. http://cam/snapshot.jpg). Zero extra deps.
  * mjpeg    — an HTTP multipart MJPEG stream; the first frame is extracted.
  * rtsp     — needs ffmpeg on the host (grabbed via a subprocess).

Phone and smart-glasses cameras are handled in the browser (getUserMedia) and
posted as frames to /api/vision, so they don't need to be registered here.
Registered cameras are the "easily add an external camera" path.
"""
from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, asdict

import httpx


@dataclass
class Camera:
    name: str
    url: str
    kind: str = "snapshot"       # snapshot | mjpeg | rtsp
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class CameraRegistry:
    def __init__(self):
        self._cams: dict[str, Camera] = {}

    def add(self, name: str, url: str, kind: str = "snapshot", note: str = "") -> Camera:
        cam = Camera(name=name, url=url, kind=kind, note=note)
        self._cams[name] = cam
        return cam

    def remove(self, name: str) -> bool:
        return self._cams.pop(name, None) is not None

    def list(self) -> list[dict]:
        return [c.to_dict() for c in self._cams.values()]

    def get(self, name: str) -> Camera | None:
        return self._cams.get(name)

    async def snapshot_b64(self, name: str) -> dict:
        """Grab one frame and return it base64-encoded (no data: prefix)."""
        cam = self._cams.get(name)
        if not cam:
            return {"ok": False, "error": "no such camera"}
        try:
            if cam.kind in ("snapshot", "mjpeg"):
                data = await self._http_frame(cam)
            elif cam.kind == "rtsp":
                data = await self._rtsp_frame(cam.url)
            else:
                return {"ok": False, "error": f"unknown kind {cam.kind}"}
            return {"ok": True, "name": name, "image_b64": base64.b64encode(data).decode()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def _http_frame(self, cam: Camera) -> bytes:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as c:
            if cam.kind == "snapshot":
                r = await c.get(cam.url)
                r.raise_for_status()
                return r.content
            # mjpeg: read until we can extract one JPEG (FFD8..FFD9)
            async with c.stream("GET", cam.url) as r:
                r.raise_for_status()
                buf = b""
                async for chunk in r.aiter_bytes():
                    buf += chunk
                    start = buf.find(b"\xff\xd8")
                    end = buf.find(b"\xff\xd9", start + 2)
                    if start != -1 and end != -1:
                        return buf[start:end + 2]
                    if len(buf) > 5_000_000:
                        break
                raise RuntimeError("no JPEG frame found in MJPEG stream")

    async def _rtsp_frame(self, url: str) -> bytes:
        # Requires ffmpeg on the host.
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-loglevel", "error", "-rtsp_transport", "tcp",
            "-i", url, "-frames:v", "1", "-f", "image2", "-c:v", "mjpeg", "pipe:1",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=20)
        if proc.returncode != 0 or not out:
            raise RuntimeError(f"ffmpeg failed: {err.decode(errors='replace')[:200]}")
        return out
