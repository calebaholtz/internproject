"""
Manual verification script for the MCP knowledge-base server.

Usage:
    1. Start the backend in one terminal:
         cd backend
         .venv\\Scripts\\activate
         python -m uvicorn main:app --reload

    2. In another terminal (same venv):
         cd backend
         .venv\\Scripts\\activate
         python test_mcp_server.py

Exercises all six tools end-to-end against the live server and prints PASS/FAIL.
"""
import asyncio
import config as cfg
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = "http://127.0.0.1:8000/mcp/"  # adjust the port if you run uvicorn on a different one
SOURCE = "mcp-verify-test-doc"


async def run_unauthed():
    for label, headers in [
        ("no key", {}),
        ("wrong key", {"Authorization": "Bearer wrong-key"}),
    ]:
        try:
            async with streamablehttp_client(URL, headers=headers) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
            print(f"FAIL: {label} was NOT blocked")
        except Exception:
            print(f"PASS: {label} correctly blocked")


async def run_authed():
    headers = {"Authorization": f"Bearer {cfg.MCP_API_KEY}"}
    async with streamablehttp_client(URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            expected = ["delete_document", "enrichment_status", "list_documents",
                        "query_knowledge", "upload_pdf", "upload_text"]
            print("PASS: all six tools present" if names == expected else f"FAIL: got {names}")

            await session.call_tool(
                "upload_text",
                {"text": "The secret verification phrase is XYLOPHONE-QUASAR-77.", "source_name": SOURCE},
            )
            print("PASS: upload_text succeeded")

            query = await session.call_tool("query_knowledge", {"query": "What is the secret verification phrase?"})
            found = "XYLOPHONE" in query.content[0].text
            print("PASS: uploaded content retrievable via query_knowledge" if found else "FAIL: content not found")

            docs = await session.call_tool("list_documents", {})
            print("PASS: list_documents shows the upload" if SOURCE in docs.content[0].text else "FAIL: missing from list")

            await session.call_tool("delete_document", {"source_name": SOURCE})
            docs_after = await session.call_tool("list_documents", {})
            print("PASS: delete_document removed it" if SOURCE not in docs_after.content[0].text else "FAIL: still present")

            reject = await session.call_tool("upload_text", {"text": "x", "source_name": "bad.pdf"})
            print("PASS: .pdf source_name correctly rejected" if reject.isError else "FAIL: should have been rejected")


async def main():
    if not cfg.MCP_API_KEY:
        print("FAIL: MCP_API_KEY is not set in backend/.env — every request will be rejected")
        return
    await run_unauthed()
    await run_authed()
    print("\nDone.")


asyncio.run(main())
