import asyncio

from mcp.client.stdio import stdio_client
from mcp import ClientSession, StdioServerParameters

# 为 stdio 连接创建服务器参数
server_params = StdioServerParameters(
    # 服务器执行的命令，这里我们使用 uv 来运行 web_search.py
    command='uv',
    # 运行的参数
    args=['run', 'server.py'],
    # 环境变量，默认为 None，表示使用当前环境变量
    # env=None
)


async def main():
    # 创建 stdio 客户端
    async with stdio_client(server_params) as (stdio, write):
        # 创建 ClientSession 对象
        async with ClientSession(stdio, write) as session:
            # 初始化 ClientSession
            await session.initialize()

            # 列出可用的工具
            response = await session.list_tools()
            print(response.model_dump_json(indent=2))

            response = await session.list_resources()
            print(response.model_dump_json(indent=2))

            response = await session.list_prompts()
            print(response.model_dump_json(indent=2))

            # 调用工具
            response = await session.call_tool('add', {"a": "2", "b": "3"})
            print(response.model_dump_json(indent=2))

            # 调用工具
            response = await session.read_resource('config://app')
            print(response.model_dump_json(indent=2))

            # 调用工具
            response = await session.get_prompt('debug_error', {"error": "test"})
            print(response.model_dump_json(indent=2))


if __name__ == '__main__':
    asyncio.run(main())
