import os
import json
import asyncio
from typing import Optional
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("MODEL", "gpt-4o-mini")
BASE_URL = os.getenv("BASE_URL", None)

SERVER_CONFIG = {
    "mcpServers": {
        "test-mcp": {
            "command": "uv",
            "args": ["run", "server.py"],
            "env": None
        },
        "test-fetch": {
            "command": "uvx",
            "args": ["mcp-server-fetch"],
            "env": None
        },
        "markdownify": {
            "command": "node",
            "args": [
                "/Users/yanyuming/Downloads/GitHub/markdownify-mcp/dist/index.js"
            ],
            "env": None
        },
        "file-system": {
            "command": "npx",
            "args": [
                "-y",
                "@modelcontextprotocol/server-filesystem",
                f"/Applications/",
                "/Users/yanyuming/Library/Containers/com.tencent.xinWeChat/Data/Library/Application Support/com.tencent.xinWeChat/2.0b4.0.9/86c0a611e10e689b203ffc7e9537af68/Message/MessageTemp/087ed5d02dc21448497490d76086646e/File",
            ],
            "env": None
        },
        "@microsoft/playwright-mcp": {
            "url": "https://router.mcp.so/sse/aiii3nm8tl0qpe"
        },
        "uni-api Docs": {
            "url": "https://gitmcp.io/yym68686/uni-api"
        },
    }
}

# mcp_server = SERVER_CONFIG["mcpServers"]["test-mcp"]
# mcp_server = SERVER_CONFIG["mcpServers"]["markdownify"]
# mcp_server = SERVER_CONFIG["mcpServers"]["file-system"]
# mcp_server = SERVER_CONFIG["mcpServers"]["test-fetch"]
mcp_server = SERVER_CONFIG["mcpServers"]["uni-api Docs"]

def convert_tool_format(tool):
    # converted_tool = {
    #     "type": "function",
    #     "function": {
    #         "name": tool.name,
    #         "description": tool.description,
    #         "parameters": {
    #             "type": "object",
    #             "properties": tool.inputSchema["properties"],
    #             "required": tool.inputSchema["required"]
    #         }
    #     }
    # }
    converted_tool = {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.inputSchema
        }
    }
    return converted_tool


class MCPClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.client = OpenAI(
            base_url=BASE_URL
        )

    async def connect_to_server(self, server_config):
        if "command" in server_config:
            server_params = StdioServerParameters(**server_config)
            stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        else:
            stdio_transport = await self.exit_stack.enter_async_context(sse_client(**server_config))

        stdio, write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(stdio, write))

        await self.session.initialize()

        # List available tools from the MCP server
        response = await self.session.list_tools()
        print("\nConnected to server with tools:", [tool.name for tool in response.tools])

        self.messages = []

    async def process_query(self, query: str) -> str:

        self.messages.append({
            "role": "user",
            "content": query
        })

        # 获取所有 mcp 服务器 工具列表信息
        response = await self.session.list_tools()
        # 生成 function call 的描述信息
        available_tools = [convert_tool_format(tool) for tool in response.tools]


        # 请求 deepseek，function call 的描述信息通过 tools 参数传入
        response = self.client.chat.completions.create(
            model=MODEL,
            messages=self.messages,
            tools=available_tools
        )

        # 处理返回的内容
        content = response.choices[0]
        if content.finish_reason == "tool_calls":
            # 如何是需要使用工具，就解析工具
            tool_call = content.message.tool_calls[0]
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)

            # 执行工具
            result = await self.session.call_tool(tool_name, tool_args)
            print(f"\n\n[Calling tool {tool_name} with args {tool_args}]\n\n")

            # 将 deepseek 返回的调用哪个工具数据和工具执行完成后的数据都存入messages中
            self.messages.append(content.message.model_dump())
            self.messages.append({
                "role": "tool",
                "content": result.content[0].text,
                "tool_call_id": tool_call.id,
            })

            # 将上面的结果再返回给 deepseek 用于生产最终的结果
            response = self.client.chat.completions.create(
                model=MODEL,
                messages=self.messages,
            )
            return response.choices[0].message.content

        return content.message.content

    async def chat_loop(self):
        while True:
            try:
                query = input("\nQuery: ").strip()

                if query.lower() == 'quit':
                    break

                response = await self.process_query(query)
                print("\n" + response)

            except Exception as e:
                import traceback
                traceback.print_exc()

    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()

async def main():
    client = MCPClient()
    try:
        await client.connect_to_server(mcp_server)
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
