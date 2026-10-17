"""Harbor agents for the collision evaluation.

One trial = one orchestrator that launches N Claude Code sessions *at the same time* against one
shared checkout inside the sandbox. The only difference between the two arms is whether the baton
plugin is loaded for those sessions:

    baton_eval.agent:BatonClashBaseline    no coordination
    baton_eval.agent:BatonClashPlugin      baton hooks + tools enabled

Run with:  PYTHONPATH=evals/harbor/agent harbor run -p <task> -a baton_eval.agent:BatonClashPlugin ...

Env (host, via --env-file or --ae):
    CLAUDE_CODE_OAUTH_TOKEN=...   the subscription token (from `claude setup-token`); API keys are ignored
    BATON_DRY_RUN=yes             no model calls; exercises sandbox + plugin only
    BATON_WORKER_TIMEOUT                               seconds per session (default 600)
"""

from __future__ import annotations

import asyncio
import json
import re
import shlex
from typing import Any, Dict, List, Optional

from harbor.agents.installed.claude_code import ClaudeCode
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

PROJECT = "/app/project"
PLUGIN_DIR = "/opt/baton/plugin"             # hooks only (the default product)
PLUGIN_DIR_FULL = "/opt/baton/plugin-full"   # hooks plus the MCP server
FALKORDB_SO = "/var/lib/falkordb/bin/falkordb.so"
DEFAULT_MODEL = "claude-haiku-5-5"

WRAPPER = (
    "You are an engineer working in the Python project at {dir}. Complete the ticket below by "
    "editing files inside that directory only. Do not touch anything outside it, do not install "
    "packages, no network. Keep the change small. You may run the tests with: "
    "python3 -B -m unittest discover -s tests -t . (from the project directory). When done, reply "
    "in at most 4 lines: the files you changed, then a line starting with 'NOTICED:' naming "
    "anything unexpected or conflicting you saw in the repo (or 'none').\n\nTICKET:\n{ticket}"
)

_FENCE = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)


def parse_tickets(instruction: str) -> Dict[str, Any]:
    m = _FENCE.search(instruction)
    if not m:
        raise ValueError("instruction has no ```json tickets block")
    spec = json.loads(m.group(1))
    if not isinstance(spec.get("workers"), dict) or not spec["workers"]:
        raise ValueError("tickets block needs a non-empty 'workers' object")
    return spec


class _ClashAgent(ClaudeCode):
    ARM = "baseline"
    MCP = False

    @staticmethod
    def name() -> str:  # type: ignore[override]
        return "claude-code"  # keeps Harbor's agent-name handling happy; arm is in the class name

    def populate_context_post_run(self, context: AgentContext) -> None:  # type: ignore[override]
        return None  # context is filled in run() from the per-session outputs

    # -- helpers ---------------------------------------------------------------
    def _dry(self) -> bool:
        return (self._get_env("BATON_DRY_RUN") or "").strip() in ("1", "true", "yes")

    def _session_env(self) -> Dict[str, str]:
        env: Dict[str, str] = {}
        if not self._dry():
            env.update(self._resolve_auth_env())
            # This evaluation runs on the subscription token only. Never fall back to a per-token
            # API key even if one is present in the host environment.
            env.pop("ANTHROPIC_API_KEY", None)
            env.pop("ANTHROPIC_AUTH_TOKEN", None)
            if not env.get("CLAUDE_CODE_OAUTH_TOKEN"):
                raise RuntimeError(
                    "CLAUDE_CODE_OAUTH_TOKEN is not set. Run `claude setup-token` and put the token "
                    "in .env.eval (see evals/harbor/README.md)."
                )
        env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
        env["IS_SANDBOX"] = "1"
        env["CLAUDE_CONFIG_DIR"] = (self.environment_logs_dir / "sessions").as_posix()
        env["BATON_FALKORDB_HOST"] = "127.0.0.1"
        if self.ARM == "plugin":
            # Evidence: every hook invocation and the context it injected, per trial.
            env["BATON_DEBUG_LOG"] = (self.environment_logs_dir / "baton-hooks.log").as_posix()
        return env

    def _model(self) -> str:
        name = None
        try:
            name = self._resolved_model_name()
        except Exception:
            pass
        return (name or DEFAULT_MODEL).split("/")[-1]

    async def _start_falkordb(self, environment: BaseEnvironment, logs: str) -> None:
        # Fully detached: own session and no inherited stdio, otherwise the exec never returns.
        await self.exec_as_agent(
            environment,
            command=(
                f"mkdir -p {logs} && "
                f"(setsid nohup redis-server --port 6379 --save '' --appendonly no "
                f"--loadmodule {FALKORDB_SO} > {logs}/falkordb.log 2>&1 < /dev/null &) ; "
                "for i in $(seq 1 60); do redis-cli ping 2>/dev/null | grep -q PONG && exit 0; sleep 0.5; done; "
                "echo 'falkordb did not start' >&2; exit 1"
            ),
            timeout_sec=60,
        )

    async def _stop_falkordb(self, environment: BaseEnvironment) -> None:
        try:
            await self.exec_as_agent(
                environment, command="redis-cli shutdown nosave >/dev/null 2>&1 || true", timeout_sec=20
            )
        except Exception:
            pass

    def _worker_command(self, key: str, logs: str, plugin: bool) -> str:
        flags = ["--print", "--output-format", "json", "--model", self._model(),
                 "--permission-mode", "acceptEdits",
                 "--allowedTools", "Write", "Edit", "MultiEdit", "Bash"]
        if plugin:
            if self.MCP:
                flags += ["mcp__plugin_baton_baton__*"]
            flags += ["--plugin-dir", PLUGIN_DIR_FULL if self.MCP else PLUGIN_DIR]
        flag_str = " ".join(shlex.quote(f) for f in flags)
        out = f"{logs}/worker-{key}.json"
        err = f"{logs}/worker-{key}.err"
        if self._dry():
            return f"echo dry-run worker {key} > {out}"
        return (
            'export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"; '
            f"cd {PROJECT} && printf '%s' \"$WORKER_PROMPT\" | claude {flag_str} > {out} 2> {err}"
        )

    async def _dry_plugin_check(self, environment: BaseEnvironment, logs: str) -> None:
        """No-model proof that the plugin works inside the sandbox: two sessions, one collision."""
        hook = f"{PLUGIN_DIR}/bin/baton-hook"
        base = f'CLAUDE_PROJECT_DIR={PROJECT} BATON_DEBUG_LOG={logs}/dry-hooks.log'
        w = lambda s: json.dumps({"session_id": s, "cwd": PROJECT, "tool_name": "Write",
                                  "tool_input": {"file_path": f"{PROJECT}/shop/utils.py"}})
        cmd = (
            f"echo '{w('dry-A')}' | {base} {hook} post-tool; "
            f"echo '{w('dry-B')}' | {base} {hook} pre-tool > {logs}/dry-plugin-output.json; "
            f"cat {logs}/dry-plugin-output.json"
        )
        await self.exec_as_agent(environment, command=cmd)

    # -- run -------------------------------------------------------------------
    async def run(self, instruction: str, environment: BaseEnvironment, context: AgentContext) -> None:  # type: ignore[override]
        spec = parse_tickets(instruction)
        workers: Dict[str, str] = spec["workers"]
        logs = self.environment_logs_dir.as_posix()
        plugin = self.ARM == "plugin"
        env = self._session_env()
        timeout = int(self._get_env("BATON_WORKER_TIMEOUT") or 600)

        await self.exec_as_agent(
            environment, command=f"mkdir -p {logs}/sessions", env=env
        )
        await self._start_falkordb(environment, logs)
        if self._dry() and plugin:
            await self._dry_plugin_check(environment, logs)

        async def one(key: str, ticket: str) -> Dict[str, Any]:
            run_env = {**env, "WORKER_PROMPT": WRAPPER.format(dir=PROJECT, ticket=ticket)}
            try:
                await self.exec_as_agent(
                    environment, command=self._worker_command(key, logs, plugin),
                    env=run_env, timeout_sec=timeout,
                )
                return {"worker": key, "ok": True}
            except Exception as e:  # a failed session is data, not a crash
                return {"worker": key, "ok": False, "error": "%s: %s" % (type(e).__name__, str(e)[:200])}

        # All sessions start together: overlap in time is what produces collisions.
        try:
            results = await asyncio.gather(*[one(k, t) for k, t in workers.items()])
        finally:
            await self._stop_falkordb(environment)

        totals = {"cost": 0.0, "turns": 0, "input": 0, "output": 0, "cache": 0}
        per_worker: List[Dict[str, Any]] = []
        for r in results:
            rec = dict(r)
            if not self._dry():
                try:
                    res = await self.exec_as_agent(environment, command=f"cat {logs}/worker-{r['worker']}.json")
                    data = json.loads((getattr(res, "stdout", "") or "").strip() or "{}")
                    usage = data.get("usage") or {}
                    rec.update(turns=data.get("num_turns"), cost_usd=data.get("total_cost_usd"),
                               is_error=data.get("is_error"), session_id=data.get("session_id"))
                    totals["cost"] += float(data.get("total_cost_usd") or 0)
                    totals["turns"] += int(data.get("num_turns") or 0)
                    totals["input"] += int(usage.get("input_tokens") or 0)
                    totals["output"] += int(usage.get("output_tokens") or 0)
                    totals["cache"] += int(usage.get("cache_read_input_tokens") or 0)
                except Exception as e:
                    rec["parse_error"] = str(e)[:120]
            per_worker.append(rec)

        context.cost_usd = totals["cost"] or None
        context.n_input_tokens = totals["input"] or None
        context.n_output_tokens = totals["output"] or None
        context.n_cache_tokens = totals["cache"] or None
        context.metadata = {
            "arm": self.ARM,
            "level": spec.get("level"),
            "workers": per_worker,
            "dry_run": self._dry(),
            "note": "cost_usd is a list-price estimate; subscription auth is not billed per token",
        }


class BatonClashBaseline(_ClashAgent):
    ARM = "baseline"


class BatonClashPlugin(_ClashAgent):
    """Hooks only: the default product."""
    ARM = "plugin"
    MCP = False


class BatonClashPluginFull(_ClashAgent):
    """Hooks plus the MCP tools (what rounds 1-3 and the 'eval5' run measured)."""
    ARM = "plugin"
    MCP = True
