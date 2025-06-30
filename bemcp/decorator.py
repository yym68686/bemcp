import asyncio
import functools
from typing import Any, Callable, TypeVar

try:
    from mcp.shared.exceptions import McpError
except ImportError:
    # Define a dummy exception if mcp is not available,
    # although it should be in the target environment.
    class McpError(Exception):
        pass

try:
    from anyio import BrokenResourceError
except ImportError:
    class BrokenResourceError(Exception):
        pass

F = TypeVar('F', bound=Callable[..., Any])

def async_retry(max_retries: int = 2, delay: float = 1.0):
    """
    A decorator to automatically retry an async function if it raises an exception.

    Args:
        max_retries: The maximum number of retries.
        delay: The delay between retries in seconds.
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None
            # The number of attempts is max_retries + 1 (the initial attempt)
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        print(f"Attempt {attempt + 1} failed with error: {e}. Retrying in {delay}s...")
                        await asyncio.sleep(delay)
                    else:
                        print(f"All {max_retries + 1} attempts failed.")
            if last_exception is not None:
                raise last_exception
        return wrapper  # type: ignore
    return decorator


def reconnect_on_connection_error(func: F) -> F:
    """
    A decorator for MCPClient methods that automatically tries to reconnect
    and retry the call if a connection-related error is caught.
    It handles McpError and anyio.BrokenResourceError.
    """
    @functools.wraps(func)
    async def wrapper(self, *args: Any, **kwargs: Any) -> Any:
        try:
            return await func(self, *args, **kwargs)
        except (McpError, BrokenResourceError) as e:
            is_connection_error = False
            if isinstance(e, McpError):
                error_str = str(e).lower()
                if "connection closed" in error_str or "peer closed connection" in error_str:
                    is_connection_error = True
            elif isinstance(e, BrokenResourceError):
                is_connection_error = True

            if is_connection_error:
                print(f"Connection error detected ({type(e).__name__}): {e}. Attempting to reconnect...")
                try:
                    await self.disconnect()
                    await self.connect()
                    print("Reconnected successfully. Retrying the operation...")
                    return await func(self, *args, **kwargs)
                except Exception as reconnect_e:
                    print(f"Failed to reconnect and retry: {reconnect_e}")
                    # If reconnect fails, raise the original connection error
                    raise e
            else:
                # Not a connection-related McpError, re-raise it.
                raise
    return wrapper # type: ignore