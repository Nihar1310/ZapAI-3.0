"""MCP (Model Context Protocol) Manager for ZapAI."""
import subprocess
import json
import asyncio
from typing import Dict, Any, Optional, List
from loguru import logger
import tempfile
import os

from app.config import settings, MCP_SERVERS


class MCPManager:
    """Manages MCP server connections and calls."""
    
    def __init__(self):
        self.available_servers = {}
        self.server_processes = {}
    
    async def initialize(self):
        """Initialize MCP connections."""
        logger.info("Initializing MCP Manager...")
        
        # Check which servers are available
        for server_name, command in MCP_SERVERS.items():
            is_available = await self._check_server(server_name, command)
            self.available_servers[server_name] = is_available
        
        logger.info("MCP Manager initialized")
        logger.info(f"Available MCP servers: {[k for k, v in self.available_servers.items() if v]}")
    
    async def cleanup(self):
        """Cleanup MCP connections."""
        # Stop any running server processes
        for process in self.server_processes.values():
            if process and not process.returncode:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    process.kill()
        
        self.server_processes.clear()
        logger.info("MCP Manager cleaned up")
    
    async def _check_server(self, server_name: str, command: str) -> bool:
        """Check if MCP server is available using proper JSON-RPC protocol."""
        try:
            # Parse the command to get the executable
            if command.startswith("npx "):
                # For npx commands, we need to check if the package exists
                package_name = command.split()[1]
                
                # First check if the package can be found
                check_result = await asyncio.create_subprocess_exec(
                    "npx", "--yes", package_name, "--version",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await check_result.communicate()
                
                if check_result.returncode != 0:
                    logger.warning(f"⚠️ {server_name} package not found: {stderr.decode().strip()}")
                    return False
                
                # Now test actual MCP communication
                return await self._test_mcp_communication(server_name, command)
            else:
                # For other commands, try direct execution
                return await self._test_mcp_communication(server_name, command)
                
        except Exception as e:
            logger.error(f"❌ Error checking {server_name} MCP server: {e}")
            return False
    
    async def _test_mcp_communication(self, server_name: str, command: str) -> bool:
        """Test MCP server communication using initialize message."""
        try:
            # Prepare the MCP initialize message
            init_message = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "zapai-health-check",
                        "version": "1.0.0"
                    }
                }
            }
            
            # Split command properly
            cmd_parts = command.split()
            
            # Create subprocess for MCP server
            process = await asyncio.create_subprocess_exec(
                *cmd_parts,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Send initialize message
            message_json = json.dumps(init_message) + '\n'
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=message_json.encode()),
                timeout=10.0
            )
            
            # Parse response
            if stdout:
                try:
                    response = json.loads(stdout.decode().strip())
                    if (response.get("jsonrpc") == "2.0" and 
                        response.get("id") == 1 and 
                        "result" in response):
                        
                        server_info = response["result"].get("serverInfo", {})
                        logger.info(f"✅ {server_name} MCP server is available - {server_info.get('name', 'Unknown')}")
                        return True
                    else:
                        logger.warning(f"⚠️ {server_name} returned invalid MCP response")
                        return False
                except json.JSONDecodeError:
                    logger.warning(f"⚠️ {server_name} returned non-JSON response: {stdout.decode()[:100]}")
                    return False
            else:
                error_msg = stderr.decode().strip() if stderr else "No output"
                logger.warning(f"⚠️ {server_name} MCP server check failed: {error_msg}")
                return False
                
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ {server_name} MCP server health check timed out")
            return False
        except Exception as e:
            logger.error(f"❌ Error testing {server_name} MCP communication: {e}")
            return False
        finally:
            # Ensure process is cleaned up
            if 'process' in locals() and process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    process.kill()
    
    def _get_mock_response(
        self, 
        server_name: str, 
        tool_name: str, 
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get mock response for MCP calls during development."""
        
        if server_name == "puppeteer_scraper" and tool_name == "scrape_page":
            return {
                "content": f"<html><body><h1>Mock scraped content from {parameters.get('url', 'example.com')}</h1><p>This is mock content that would be scraped from the webpage. Contact us at info@example.com or call (555) 123-4567.</p></body></html>",
                "title": "Mock Page Title",
                "url": parameters.get("url", "example.com"),
                "status": "success"
            }
        else:
            return {
                "result": f"Mock response from {server_name}.{tool_name}",
                "parameters": parameters,
                "status": "success"
            }

    # Web Scraping MCP
    async def call_puppeteer_scraper(
        self, 
        url: str, 
        timeout: int = 30
    ) -> Optional[Dict[str, Any]]:
        """Call Puppeteer scraping MCP."""
        parameters = {
            "url": url,
            "timeout": timeout
        }
        
        return await self._call_mcp_server(
            "puppeteer_scraper",
            "puppeteer_navigate",
            parameters
        )
    
    # Legacy method compatibility - these call the actual search APIs directly
    async def call_google_search(self, query: str, num_results: int = 10, start_index: int = 1) -> Optional[Dict]:
        """Direct Google Custom Search API call (not MCP)."""
        # This should use Google Custom Search API directly
        # For now, return mock data for development
        return {
            "items": [
                {
                    "title": f"Google result for: {query}",
                    "link": "https://example.com/google-result",
                    "snippet": "Mock Google search result"
                }
            ]
        }
    
    async def call_bing_search(self, query: str, count: int = 10, offset: int = 0) -> Optional[Dict]:
        """Direct Bing Web Search API call (not MCP)."""
        # This should use Bing Web Search API directly
        # For now, return mock data for development
        return {
            "webPages": {
                "value": [
                    {
                        "name": f"Bing result for: {query}",
                        "url": "https://example.com/bing-result",
                        "snippet": "Mock Bing search result"
                    }
                ]
            }
        }
    
    async def call_duckduckgo_search(self, query: str, max_results: int = 10) -> List[Dict]:
        """Direct DuckDuckGo search (not MCP)."""
        # This should use DuckDuckGo search directly
        # For now, return mock data for development
        return [
            {
                "title": f"DuckDuckGo result for: {query}",
                "url": "https://example.com/ddg-result",
                "snippet": "Mock DuckDuckGo search result"
            }
        ]
    
    async def _call_mcp_server(
        self, 
        server_name: str, 
        tool_name: str, 
        parameters: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Call an MCP server with the given parameters."""
        
        # Check if server is available
        if not self.available_servers.get(server_name, False):
            logger.warning(f"MCP server {server_name} not available, using mock response")
            return self._get_mock_response(server_name, tool_name, parameters)
        
        try:
            # Get server command
            command = MCP_SERVERS.get(server_name)
            if not command:
                logger.error(f"No command configured for MCP server {server_name}")
                return None
            
            # For now, use mock responses until full MCP protocol client is implemented
            logger.info(f"Calling MCP {server_name}.{tool_name} (mock mode - real implementation needed)")
            return self._get_mock_response(server_name, tool_name, parameters)
            
        except Exception as e:
            logger.error(f"Error calling MCP server {server_name}: {e}")
            return None

    def get_server_status(self) -> Dict[str, Any]:
        """Get status of all configured MCP servers."""
        return {
            "servers": {
                name: {
                    "available": self.available_servers.get(name, False),
                    "command": MCP_SERVERS.get(name, "Unknown")
                }
                for name in MCP_SERVERS.keys()
            },
            "total_configured": len(MCP_SERVERS),
            "total_available": sum(1 for available in self.available_servers.values() if available)
        }
