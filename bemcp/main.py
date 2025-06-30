import asyncio
from typing import Any, Dict, List, Optional
from contextlib import AsyncExitStack
from .decorator import async_retry, reconnect_on_connection_error

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
import mcp.types as types

class MCPClient:
    """
    A client for interacting with a single Model Context Protocol (MCP) server.
    It can connect to a server via stdio or a URL (SSE).
    This class is an asynchronous context manager.
    """
    def __init__(self, server_config: Dict[str, Any]):
        """
        Initializes the MCPClient.

        Args:
            server_config: A dictionary containing server configuration.
                           It should have either 'command' and 'args' for stdio,
                           or 'url' for SSE.
        """
        if not ("command" in server_config or "url" in server_config):
            raise ValueError("Server config must contain 'command' or 'url'")
        self.server_config = server_config
        self.session: Optional[ClientSession] = None
        self._exit_stack: Optional[AsyncExitStack] = None

    async def connect(self):
        """Connects to the MCP server and initializes resources."""
        return await self.__aenter__()

    async def disconnect(self):
        """Disconnects from the MCP server and cleans up resources."""
        return await self.__aexit__(None, None, None)

    @async_retry(max_retries=2)
    async def __aenter__(self):
        """Connects to the MCP server and initializes resources."""
        if self.session:
            return self

        self._exit_stack = AsyncExitStack()
        try:
            if "command" in self.server_config:
                server_params = StdioServerParameters(**self.server_config)
                transport = await self._exit_stack.enter_async_context(stdio_client(server_params))
            else:
                transport = await self._exit_stack.enter_async_context(sse_client(**self.server_config))

            read_stream, write_stream = transport
            self.session = await self._exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
            await self.session.initialize()
            print(f"Connected to server.")
            return self
        except Exception:
            # If setup fails, make sure to clean up anything that was started.
            if self._exit_stack:
                await self._exit_stack.aclose()
            raise

    async def __aexit__(self, exc_type, exc_value, traceback):
        """Disconnects from the MCP server and cleans up resources."""
        if self._exit_stack:
            await self._exit_stack.aclose()
            self.session = None
            self._exit_stack = None
            print("Disconnected from server.")

    @reconnect_on_connection_error
    async def list_tools(self) -> List[types.Tool]:
        """Lists available tools from the server."""
        if not self.session:
            raise ConnectionError("Not connected to any server.")
        response = await self.session.list_tools()
        return response.tools

    @reconnect_on_connection_error
    async def call_tool(self, name: str, args: Dict[str, Any]) -> types.CallToolResult:
        """Calls a tool on the server."""
        if not self.session:
            raise ConnectionError("Not connected to any server.")
        return await self.session.call_tool(name, args)

    @reconnect_on_connection_error
    async def list_resources(self) -> List[types.Resource]:
        """Lists available resources from the server."""
        if not self.session:
            raise ConnectionError("Not connected to any server.")
        response = await self.session.list_resources()
        return response.resources

    @reconnect_on_connection_error
    async def read_resource(self, uri: str) -> types.ReadResourceResult:
        """Reads a resource from the server."""
        if not self.session:
            raise ConnectionError("Not connected to any server.")
        return await self.session.read_resource(uri)


class MCPManager:
    """
    Manages connections to multiple MCP servers.
    """
    def __init__(self):
        self.clients: Dict[str, MCPClient] = {}
        self._exit_stack = AsyncExitStack()

    async def add_server(self, name: str, config: Dict[str, Any]):
        """
        Adds and connects to a new MCP server.

        Args:
            name: A unique name for the server.
            config: The server configuration dictionary.
        """
        if name in self.clients:
            print(f"Server '{name}' already exists.")
            return

        client = MCPClient(config)
        await self._exit_stack.enter_async_context(client)
        self.clients[name] = client
        print(f"Server '{name}' added and connected.")

    async def remove_server(self, name: str):
        """
        Disconnects and removes an MCP server.
        """
        # NOTE: With the new ExitStack-based management, removing a single
        # server is complex. This method is left as a placeholder and will
        # not correctly clean up resources for the removed server.
        if name in self.clients:
            del self.clients[name]
            print(f"Server '{name}' removed (Warning: resources may not be cleaned up immediately).")
        else:
            print(f"Server '{name}' not found.")

    async def get_all_tools(self) -> Dict[str, List[types.Tool]]:
        """Gets a dictionary of all tools from all connected servers."""
        all_tools = {}
        for name, client in self.clients.items():
            try:
                tools = await client.list_tools()
                all_tools[name] = tools
            except Exception as e:
                print(f"Error getting tools from server '{name}': {e}")
        return all_tools

    async def call_tool(self, server_name: str, tool_name: str, args: Dict[str, Any]) -> types.CallToolResult:
        """
        Calls a specific tool on a specific server.
        """
        if server_name not in self.clients:
            raise ValueError(f"Server '{server_name}' not found.")
        return await self.clients[server_name].call_tool(tool_name, args)

    async def cleanup(self):
        """Disconnects all clients by closing the manager's exit stack."""
        if self.clients:
            await self._exit_stack.aclose()
            self.clients.clear()

async def test_bemcp():
    """
    Test function for MCPManager and MCPClient.
    """
    manager = MCPManager()

    # Configuration for a test server (using the existing test/server.py)
    test_server_config = {
        "command": "uv",
        "args": ["run", "test/server.py"],
        "env": None
    }

    # Add the test server
    await manager.add_server("test_server", test_server_config)

    # List all tools
    all_tools = await manager.get_all_tools()
    print("\n--- All Tools ---")
    for server_name, tools in all_tools.items():
        print(f"Server: {server_name}")
        for tool in tools:
            print(f"  - {tool.name}: {tool.description}")
    print("-------------------\n")

    # Call a tool
    print("--- Calling 'add' tool on 'test_server' with a=2, b=3 ---")
    try:
        result = await manager.call_tool("test_server", "add", {"a": 2, "b": 3})
        print("Result:", result.content[0].text)
    except Exception as e:
        print(f"Error calling tool: {e}")
    print("--------------------------------------------------------\n")

    # Call another tool
    print("--- Calling 'calculate_bmi' tool on 'test_server' with weight_kg=70, height_m=1.75 ---")
    try:
        result = await manager.call_tool("test_server", "calculate_bmi", {"weight_kg": 70, "height_m": 1.75})
        print("Result:", result.content[0].text)
    except Exception as e:
        print(f"Error calling tool: {e}")
    print("-------------------------------------------------------------------------------------\n")

    # Read a resource
    print("--- Reading resource 'config://app' from 'test_server' ---")
    client = manager.clients.get("test_server")
    if client:
        try:
            resource_result = await client.read_resource('config://app')
            print("Resource content:", resource_result.contents[0].text)
        except Exception as e:
            print(f"Error reading resource: {e}")
    print("----------------------------------------------------------\n")


    # Clean up
    await manager.cleanup()

if __name__ == "__main__":
    asyncio.run(test_bemcp())