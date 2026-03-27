"""
Repository Reader Agent — LangGraph Implementation
Phase 1 of the AI Coding Agent
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Annotated, Any, TypedDict

from dotenv import load_dotenv
load_dotenv()

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode


# ─── Agent State ─────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    repo_path: str
    current_task: str
    analysis_result: str | None


# ─── System prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert AI Coding Agent specializing in repository analysis.
You have deep knowledge of:
- Kotlin, Java, Spring Boot, Gradle (backend)
- TypeScript, JavaScript, React, CSS (frontend)
- Kotlin/Android, React Native (mobile)
- Python, FastAPI (AI/agent services)

You have access to tools for analyzing codebases. ALWAYS use them — never answer from imagination.

Your strategy for any repository question:
1. ALWAYS start with get_repo_summary to understand the codebase
2. Use get_repo_structure to map the architecture
3. Use list_files to find relevant files by language
4. Use read_file to read specific important files
5. Use search_code to find patterns, classes, functions
6. Use analyze_file_symbols to understand what's defined where

Be thorough. Use multiple tools. Always base your answer on actual file contents.
"""


# ─── MCP client ──────────────────────────────────────────────────────────────

def create_mcp_client() -> MultiServerMCPClient:
    server_path = Path(__file__).parent.parent / "mcp-server" / "server.py"
    return MultiServerMCPClient(
        {
            "repo-reader": {
                "command": "python",
                "args": [str(server_path)],
                "transport": "stdio",
            }
        }
    )


# ─── Graph ────────────────────────────────────────────────────────────────────

def should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        tool_names = [tc["name"] for tc in last.tool_calls]
        print(f"🔧 Calling tools: {tool_names}")
        return "tools"
    print("✅ Agent finished, generating response...")
    return END


def make_agent_node(llm_with_tools):
    def agent_node(state: AgentState) -> dict:
        print(f"🤖 Agent thinking... (messages so far: {len(state['messages'])})")
        system = SystemMessage(content=SYSTEM_PROMPT)
        context = HumanMessage(content=f"[Repository being analyzed: {state['repo_path']}]")

        if len(state["messages"]) == 1:
            messages = [system, context] + state["messages"]
        else:
            messages = [system] + state["messages"]

        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}
    return agent_node


async def build_graph(tools: list) -> Any:
    llm = ChatAnthropic(
        model="claude-sonnet-4-20250514",
        api_key=os.environ["ANTHROPIC_API_KEY"],
        max_tokens=4096,
    )
    llm_with_tools = llm.bind_tools(tools)
    tool_node = ToolNode(tools)

    graph = StateGraph(AgentState)
    graph.add_node("agent", make_agent_node(llm_with_tools))
    graph.add_node("tools", tool_node)

    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile()


# ─── Main entry point ─────────────────────────────────────────────────────────

async def analyze_repo(repo_path: str, question: str) -> str:
    mcp_client = create_mcp_client()
    tools = await mcp_client.get_tools()

    print(f"✅ MCP tools loaded: {[t.name for t in tools]}")

    agent = await build_graph(tools)

    initial_state: AgentState = {
        "messages": [HumanMessage(content=question)],
        "repo_path": repo_path,
        "current_task": question,
        "analysis_result": None,
    }

    result = await agent.ainvoke(initial_state, config={"recursion_limit": 50})

    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage) and not msg.tool_calls:
            return msg.content

    return "Analysis could not be completed."


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python agent.py <repo_path> <question>")
        sys.exit(1)

    repo = sys.argv[1]
    query = sys.argv[2]

    print(f"\n🔍 Analyzing: {repo}")
    print(f"❓ Question: {query}\n")
    print("─" * 60)

    result = asyncio.run(analyze_repo(repo, query))
    print(result)