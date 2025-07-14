#!/usr/bin/env python3
"""
Test script for MCP server functionality.
This script tests the MCP server communication and demonstrates proper usage.
"""

import asyncio
import json
import sys
import subprocess
from typing import Dict, Any, Optional

async def test_mcp_server(server_command: str, server_name: str) -> Dict[str, Any]:
    """Test MCP server communication."""
    print(f"\n🧪 Testing {server_name} MCP Server")
    print(f"Command: {server_command}")
    print("-" * 50)
    
    results = {
        "server_name": server_name,
        "command": server_command,
        "tests": {}
    }
    
    # Test 1: Initialize
    try:
        print("1. Testing initialization...")
        init_message = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "zapai-test",
                    "version": "1.0.0"
                }
            }
        }
        
        cmd_parts = server_command.split()
        process = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        message_json = json.dumps(init_message) + '\n'
        stdout, stderr = await asyncio.wait_for(
            process.communicate(input=message_json.encode()),
            timeout=10.0
        )
        
        if stdout:
            response = json.loads(stdout.decode().strip())
            if response.get("result") and response.get("result", {}).get("serverInfo"):
                server_info = response["result"]["serverInfo"]
                print(f"   ✅ Server: {server_info.get('name')} v{server_info.get('version')}")
                results["tests"]["initialize"] = {"status": "passed", "response": response}
            else:
                print(f"   ❌ Invalid response: {response}")
                results["tests"]["initialize"] = {"status": "failed", "error": "Invalid response"}
        else:
            error_msg = stderr.decode().strip() if stderr else "No output"
            print(f"   ❌ No response: {error_msg}")
            results["tests"]["initialize"] = {"status": "failed", "error": error_msg}
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        results["tests"]["initialize"] = {"status": "failed", "error": str(e)}
    
    # Test 2: List Tools
    try:
        print("2. Testing tools/list...")
        tools_message = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list"
        }
        
        cmd_parts = server_command.split()
        process = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        message_json = json.dumps(tools_message) + '\n'
        stdout, stderr = await asyncio.wait_for(
            process.communicate(input=message_json.encode()),
            timeout=10.0
        )
        
        if stdout:
            response = json.loads(stdout.decode().strip())
            if response.get("result") and response.get("result", {}).get("tools"):
                tools = response["result"]["tools"]
                print(f"   ✅ Found {len(tools)} tools:")
                for tool in tools:
                    print(f"      - {tool.get('name')}: {tool.get('description')}")
                results["tests"]["tools_list"] = {"status": "passed", "tools": tools}
            else:
                print(f"   ❌ Invalid response: {response}")
                results["tests"]["tools_list"] = {"status": "failed", "error": "Invalid response"}
        else:
            error_msg = stderr.decode().strip() if stderr else "No output"
            print(f"   ❌ No response: {error_msg}")
            results["tests"]["tools_list"] = {"status": "failed", "error": error_msg}
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        results["tests"]["tools_list"] = {"status": "failed", "error": str(e)}
    
    # Test 3: Test a tool call (navigate)
    try:
        print("3. Testing tool call (puppeteer_navigate)...")
        tool_call_message = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "puppeteer_navigate",
                "arguments": {
                    "url": "https://httpbin.org/html"
                }
            }
        }
        
        cmd_parts = server_command.split()
        process = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        message_json = json.dumps(tool_call_message) + '\n'
        stdout, stderr = await asyncio.wait_for(
            process.communicate(input=message_json.encode()),
            timeout=30.0
        )
        
        if stdout:
            response = json.loads(stdout.decode().strip())
            if response.get("result"):
                print(f"   ✅ Navigation successful")
                results["tests"]["tool_call"] = {"status": "passed", "response": response}
            else:
                print(f"   ❌ Tool call failed: {response}")
                results["tests"]["tool_call"] = {"status": "failed", "error": response.get("error", "Unknown error")}
        else:
            error_msg = stderr.decode().strip() if stderr else "No output"
            print(f"   ❌ No response: {error_msg}")
            results["tests"]["tool_call"] = {"status": "failed", "error": error_msg}
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        results["tests"]["tool_call"] = {"status": "failed", "error": str(e)}
    
    return results

async def test_zapai_mcp_manager():
    """Test the ZapAI MCP Manager."""
    print("\n🧪 Testing ZapAI MCP Manager")
    print("-" * 50)
    
    try:
        # Import the MCP manager
        sys.path.append('/Users/niharsmac/Desktop/ZapAI 3.0')
        from app.services.mcp_manager import MCPManager
        from app.config import MCP_SERVERS
        
        # Initialize MCP manager
        mcp_manager = MCPManager()
        
        print("1. Initializing MCP Manager...")
        await mcp_manager.initialize()
        
        print("2. Getting server status...")
        status = mcp_manager.get_server_status()
        print(f"   Total configured: {status['total_configured']}")
        print(f"   Total available: {status['total_available']}")
        
        for name, info in status['servers'].items():
            status_icon = "✅" if info['available'] else "❌"
            print(f"   {status_icon} {name}: {info['command']}")
        
        print("3. Testing puppeteer scraper call...")
        result = await mcp_manager.call_puppeteer_scraper("https://httpbin.org/html")
        if result:
            print(f"   ✅ Scraper call successful: {result.get('status', 'Unknown')}")
        else:
            print("   ❌ Scraper call failed")
        
        # Cleanup
        await mcp_manager.cleanup()
        
        return True
        
    except Exception as e:
        print(f"   ❌ Error testing MCP Manager: {e}")
        return False

async def main():
    """Main test function."""
    print("🚀 ZapAI MCP Server Test Suite")
    print("=" * 50)
    
    # Test individual MCP server
    server_results = await test_mcp_server(
        "npx @hisma/server-puppeteer",
        "Hisma Puppeteer Server"
    )
    
    # Test ZapAI MCP Manager
    manager_result = await test_zapai_mcp_manager()
    
    # Summary
    print("\n📊 Test Summary")
    print("=" * 50)
    
    passed_tests = sum(1 for test in server_results["tests"].values() if test["status"] == "passed")
    total_tests = len(server_results["tests"])
    
    print(f"MCP Server Tests: {passed_tests}/{total_tests} passed")
    print(f"MCP Manager Test: {'✅ Passed' if manager_result else '❌ Failed'}")
    
    if passed_tests == total_tests and manager_result:
        print("\n🎉 All tests passed! MCP server is working correctly.")
        return 0
    else:
        print("\n⚠️ Some tests failed. Check the output above for details.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 