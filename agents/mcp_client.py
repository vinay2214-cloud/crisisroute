import os
import sys
import time
import asyncio
import threading
import logging
import json
from typing import Dict, Any, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger("crisisroute.mcp_client")

class MCPClientManager:
    """
    A thread-safe singleton manager that maintains a persistent connection
    to the Elasticsearch MCP Server subprocess via stdio.
    Bridges the synchronous agent code to the asynchronous MCP SDK using a
    background daemon thread event loop.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(MCPClientManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self.loop = None
        self.session = None
        self.client_ctx = None
        self.thread = None
        self.connected = False
        self.connect_lock = threading.Lock()
        self.start()

    def start(self):
        """Starts the background event loop and connects to the MCP server."""
        with self.connect_lock:
            if self.connected:
                return
            
            logger.info("Starting background event loop for MCP client...")
            self.loop = asyncio.new_event_loop()
            self.thread = threading.Thread(target=self._run_loop, daemon=True, name="MCP-Client-Loop")
            self.thread.start()
            
            # Connect to server
            future = asyncio.run_coroutine_threadsafe(self._connect(), self.loop)
            try:
                # Wait up to 10 seconds for initialization to complete
                future.result(timeout=10.0)
                self.connected = True
                logger.info("Successfully connected and initialized session with MCP server.")
            except Exception as e:
                logger.error(f"Failed to connect to MCP server: {e}")
                self.connected = False
                self.stop()

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def _connect(self):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        server_path = os.path.join(project_root, "mcp_server.py")
        
        logger.info(f"Spawning MCP server subprocess: {sys.executable} {server_path}")
        
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[server_path],
            env=os.environ.copy()
        )
        
        self.client_ctx = stdio_client(server_params)
        read_stream, write_stream = await self.client_ctx.__aenter__()
        
        self.session = ClientSession(read_stream, write_stream)
        await self.session.__aenter__()
        await self.session.initialize()

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """
        Synchronously call an MCP tool. Automatically reconnects if disconnected.
        """
        if not self.connected or not self.session:
            logger.warning(f"MCP client not connected. Attempting reconnection for tool: {name}")
            self.start()
            if not self.connected or not self.session:
                raise RuntimeError("Elasticsearch MCP Server is offline or cannot be spawned.")

        start_time = time.time()
        future = asyncio.run_coroutine_threadsafe(
            self.session.call_tool(name, arguments=arguments),
            self.loop
        )
        try:
            result = future.result(timeout=15.0)
            execution_time_ms = int((time.time() - start_time) * 1000)
            
            # Determine result size and parse content
            parsed_result = None
            result_size = 0
            if result and result.content:
                first_content = result.content[0]
                if hasattr(first_content, 'text'):
                    raw_text = first_content.text
                    result_size = len(raw_text)
                    try:
                        parsed_result = json.loads(raw_text)
                    except json.JSONDecodeError:
                        parsed_result = raw_text
                elif hasattr(first_content, 'data'):
                    parsed_result = first_content.data
                    result_size = len(str(parsed_result))
            
            # Log success
            log_payload = {
                "event": "mcp_tool_invocation",
                "tool_name": name,
                "parameters": arguments,
                "duration_ms": execution_time_ms,
                "status": "success",
                "result_size_bytes": result_size
            }
            logger.info(f"MCP Tool Success: {json.dumps(log_payload)}")
            
            return parsed_result
            
        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            # Log failure
            log_payload = {
                "event": "mcp_tool_invocation",
                "tool_name": name,
                "parameters": arguments,
                "duration_ms": execution_time_ms,
                "status": "failure",
                "exception_type": type(e).__name__,
                "exception_message": str(e)
            }
            logger.error(f"MCP Tool Failure: {json.dumps(log_payload)}")
            
            # If the session got closed, mark as disconnected
            if "closed" in str(e).lower() or "session" in str(e).lower():
                self.connected = False
            raise

    def stop(self):
        """Cleanly disconnects the session and shuts down the background loop."""
        if not self.loop:
            return
            
        logger.info("Stopping MCP client session...")
        
        async def _disconnect():
            try:
                if self.session:
                    await self.session.__aexit__(None, None, None)
            except Exception:
                pass
            try:
                if self.client_ctx:
                    await self.client_ctx.__aexit__(None, None, None)
            except Exception:
                pass
                
        if self.loop.is_running():
            future = asyncio.run_coroutine_threadsafe(_disconnect(), self.loop)
            try:
                future.result(timeout=5.0)
            except Exception:
                pass
                
            self.loop.call_soon_threadsafe(self.loop.stop)
            
        self.connected = False
        self.session = None
        self.client_ctx = None
        logger.info("MCP client manager stopped.")

# Singleton helper instance
mcp_client = MCPClientManager()
