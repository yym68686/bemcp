from typing import Any, Dict
from mcp import types

def convert_tool_format(tool: types.Tool) -> Dict[str, Any]:
    """
    Converts an MCP tool to a format compatible with LLM providers.
    """
    # This is one possible format, similar to OpenAI's function calling.
    # The commented-out section shows another common variation.
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