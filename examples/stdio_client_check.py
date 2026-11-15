"""Connects to the server over stdio like a real MCP host would, and exercises it end to end."""
import asyncio
import os
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "ONBOARD_OPS_DATA": os.path.join(tmp, "store.json")}
        params = StdioServerParameters(command=sys.executable, args=["-m", "onboard_ops.server"], env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                print("tools:", ", ".join(t.name for t in tools.tools))
                await session.call_tool(
                    "add_teammate",
                    {"name": "Ada Lovelace", "email": "ada@example.com", "role": "Engineer", "start_date": "2026-12-01"},
                )
                queue = await session.call_tool("agent_queue", {"today": "2026-11-30"})
                print("agent_queue ->", queue.content[0].text[:160].replace("\n", " "), "...")
                done = await session.call_tool("complete_task", {"teammate_id": "tm-001", "task_id": "work_email", "today": "2026-11-30"})
                print("complete_task ->", "ok" if not done.isError else "ERROR")
                report = await session.call_tool("weekly_report", {"today": "2026-12-05"})
                print(report.content[0].text)
                bad = await session.call_tool("complete_task", {"teammate_id": "tm-999", "task_id": "x"})
                print("bad id isError =", bad.isError, "|", bad.content[0].text[:90])


asyncio.run(main())
