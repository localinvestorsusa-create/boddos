"""Execute allowlisted OS tasks on the local machine.

Security model — this is intentionally conservative:
  * Disabled unless the node config opts in (`agent.enabled: true`).
  * Only commands whose first token is in `allowed_commands` may run.
  * No shell interpretation: args are passed as a list, never `shell=True`,
    so pipes / redirects / `;` cannot be smuggled in.
  * Execution is confined to a configured working directory.
  * Optionally requires an explicit `confirm=true` per request.

This runs tasks on YOUR OWN machine. It is not a remote-exploitation tool.
"""
from __future__ import annotations

import asyncio
import shlex
from dataclasses import dataclass
from pathlib import Path

from ..config import AgentCfg


@dataclass
class AgentResult:
    ok: bool
    command: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    error: str = ""

    def to_dict(self) -> dict:
        return self.__dict__


class OSAgent:
    def __init__(self, cfg: AgentCfg):
        self.cfg = cfg
        self.workdir = Path(cfg.workdir).expanduser()

    def _reject(self, command: str, reason: str) -> AgentResult:
        return AgentResult(ok=False, command=command, error=reason)

    async def run(self, command: str, confirm: bool = False, timeout: float = 30.0) -> AgentResult:
        if not self.cfg.enabled:
            return self._reject(command, "agent disabled on this node")
        if self.cfg.require_confirm and not confirm:
            return self._reject(command, "confirmation required (pass confirm=true)")

        try:
            parts = shlex.split(command)
        except ValueError as e:
            return self._reject(command, f"unparseable command: {e}")
        if not parts:
            return self._reject(command, "empty command")

        prog = parts[0]
        if prog not in self.cfg.allowed_commands:
            return self._reject(
                command,
                f"'{prog}' is not allowlisted (allowed: {self.cfg.allowed_commands})",
            )

        self.workdir.mkdir(parents=True, exist_ok=True)
        try:
            proc = await asyncio.create_subprocess_exec(
                *parts,
                cwd=str(self.workdir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return AgentResult(
                ok=proc.returncode == 0,
                command=command,
                stdout=out.decode(errors="replace")[:20000],
                stderr=err.decode(errors="replace")[:8000],
                exit_code=proc.returncode,
            )
        except asyncio.TimeoutError:
            return self._reject(command, f"timed out after {timeout}s")
        except FileNotFoundError:
            return self._reject(command, f"'{prog}' not found on this machine")
        except Exception as e:  # pragma: no cover - defensive
            return self._reject(command, f"execution error: {e}")
