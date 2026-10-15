"""Real protocol smoke test: spawn the server as a subprocess and talk MCP over stdio.

Two server processes against one workspace stand in for two parallel sessions.
"""

import asyncio
import contextlib
import json
import os
import sys
import time
import unittest
import uuid

from tests.support import DB_UP

SRC = os.path.join(os.path.dirname(__file__), "..", "src")


def _payload(result):
    sc = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
    if isinstance(sc, dict):
        return sc.get("result", sc) if set(sc) == {"result"} else sc
    for block in result.content:
        text = getattr(block, "text", None)
        if text:
            return json.loads(text)
    raise AssertionError("no payload in %r" % (result,))


@contextlib.asynccontextmanager
async def session(workspace, actor, port=None):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = {
        "PYTHONPATH": os.path.abspath(SRC),
        "BATON_WORKSPACE": workspace,
        "BATON_ACTOR": actor,
        "BATON_FALKORDB_PORT": str(port or os.environ.get("BATON_FALKORDB_PORT", "6379")),
        "BATON_CONNECT_TIMEOUT": "1",
        "BATON_QUERY_TIMEOUT": "3",
    }
    params = StdioServerParameters(command=sys.executable, args=["-B", "-m", "baton.mcp_server.server"], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            yield s


async def call(s, name, **args):
    return _payload(await s.call_tool(name, args))


@unittest.skipUnless(DB_UP, "FalkorDB not reachable")
class ProtocolTests(unittest.TestCase):
    def test_tool_surface_and_two_session_scenario(self):
        from baton.graph.client import Store
        from baton.mcp_server.server import TOOL_NAMES

        ws = "proto_" + uuid.uuid4().hex[:8]

        async def scenario():
            async with session(ws, "sess-a") as a, session(ws, "sess-b") as b:
                tools = {t.name for t in (await a.list_tools()).tools}
                self.assertEqual(tools, set(TOOL_NAMES))

                t = (await call(a, "create_task", goal="rename db module", touches=["shop/db.py"]))["task"]
                self.assertTrue((await call(a, "claim_task", task_id=t["id"]))["claimed"])
                held = await call(b, "claim_task", task_id=t["id"])
                self.assertFalse(held["claimed"])
                self.assertEqual(held["holder"], "sess-a")

                await call(a, "post_decision", text="db.py becomes store.py",
                           artifacts=["shop/db.py"], kind="rename")
                c = await call(b, "check_conflicts", paths=["shop/db.py"])
                self.assertTrue(c["has_conflicts"])
                self.assertIn("rename", c["summary"])

                ex = await call(a, "handoff_export", task_id=t["id"])
                imp = await call(b, "handoff_import", handoff_id=ex["handoff_id"])
                self.assertIn("db.py becomes store.py", imp["text"])

        try:
            asyncio.run(scenario())
        finally:
            Store(ws).drop()

    def test_unreachable_store_fails_open_over_the_protocol(self):
        async def scenario():
            async with session("deadws", "sess-d", port=6399) as s:
                t0 = time.time()
                r = await call(s, "check_conflicts", paths=["a.py"])
                self.assertFalse(r["ok"])
                self.assertTrue(r["degraded"])
                self.assertLess(time.time() - t0, 8)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
