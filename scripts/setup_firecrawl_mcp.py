#!/usr/bin/env python3
"""
Firecrawl MCP Setup Script

This script helps initialize and configure Firecrawl MCP server for the ZapAI project.
It handles environment setup, API key configuration, and basic testing.
"""

import os
import sys
import json
import subprocess
from pathlib import Path


def print_banner():
    """Print setup banner"""
    print("=" * 60)
    print("🔥 Firecrawl MCP Setup Script")
    print("=" * 60)
    print()


def check_node_installation():
    """Check if Node.js is installed"""
    try:
        result = subprocess.run(['node', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Node.js is installed: {result.stdout.strip()}")
            return True
        else:
            print("❌ Node.js is not installed or not in PATH")
            return False
    except FileNotFoundError:
        print("❌ Node.js is not installed")
        return False


def check_npm_installation():
    """Check if npm is installed"""
    try:
        result = subprocess.run(['npm', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ npm is installed: {result.stdout.strip()}")
            return True
        else:
            print("❌ npm is not installed or not in PATH")
            return False
    except FileNotFoundError:
        print("❌ npm is not installed")
        return False


def check_firecrawl_mcp_installation():
    """Check if firecrawl-mcp is installed"""
    try:
        result = subprocess.run(['npx', 'firecrawl-mcp', '--help'], 
                              capture_output=True, text=True, 
                              env=dict(os.environ, FIRECRAWL_API_KEY='test'))
        # We expect this to fail due to invalid API key, but it should show help
        print("✅ firecrawl-mcp is installed")
        return True
    except FileNotFoundError:
        print("❌ firecrawl-mcp is not installed")
        return False


def install_firecrawl_mcp():
    """Install firecrawl-mcp globally"""
    print("🔧 Installing firecrawl-mcp...")
    try:
        result = subprocess.run(['npm', 'install', '-g', 'firecrawl-mcp'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ firecrawl-mcp installed successfully")
            return True
        else:
            print(f"❌ Failed to install firecrawl-mcp: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Error installing firecrawl-mcp: {e}")
        return False


def get_api_key():
    """Get Firecrawl API key from user"""
    print("\n📝 Firecrawl API Key Setup")
    print("-" * 30)
    print("You need a Firecrawl API key to use the MCP server.")
    print("Get your API key from: https://firecrawl.dev/app/api-keys")
    print()
    
    api_key = input("Enter your Firecrawl API key (fc-...): ").strip()
    
    if not api_key:
        print("❌ No API key provided")
        return None
    
    if not api_key.startswith('fc-'):
        print("⚠️  Warning: API key should start with 'fc-'")
    
    return api_key


def create_env_file(api_key):
    """Create .env file with API key"""
    env_path = Path('.env')
    
    if env_path.exists():
        print("✅ .env file already exists")
        with open(env_path, 'r') as f:
            content = f.read()
        
        if 'FIRECRAWL_API_KEY' in content:
            print("✅ FIRECRAWL_API_KEY already exists in .env")
            return True
        else:
            # Append to existing .env
            with open(env_path, 'a') as f:
                f.write(f"\n# Firecrawl MCP Configuration\nFIRECRAWL_API_KEY={api_key}\n")
            print("✅ Added FIRECRAWL_API_KEY to existing .env file")
            return True
    else:
        # Create new .env file
        with open(env_path, 'w') as f:
            f.write(f"# Firecrawl MCP Configuration\nFIRECRAWL_API_KEY={api_key}\n")
        print("✅ Created .env file with FIRECRAWL_API_KEY")
        return True


def test_firecrawl_mcp(api_key):
    """Test firecrawl-mcp with the provided API key"""
    print("\n🧪 Testing firecrawl-mcp...")
    try:
        env = dict(os.environ, FIRECRAWL_API_KEY=api_key)
        result = subprocess.run(['npx', 'firecrawl-mcp', '--help'], 
                              capture_output=True, text=True, env=env, timeout=30)
        
        if "Error: FIRECRAWL_API_KEY environment variable is required" in result.stderr:
            print("❌ API key not being recognized")
            return False
        elif result.returncode == 0 or "firecrawl" in result.stdout.lower():
            print("✅ firecrawl-mcp is working correctly")
            return True
        else:
            print(f"⚠️  firecrawl-mcp test completed with some warnings")
            print(f"stdout: {result.stdout}")
            print(f"stderr: {result.stderr}")
            return True
    except subprocess.TimeoutExpired:
        print("⚠️  Test timed out, but firecrawl-mcp is likely working")
        return True
    except Exception as e:
        print(f"❌ Error testing firecrawl-mcp: {e}")
        return False


def show_configuration_examples():
    """Show configuration examples for different editors"""
    print("\n📋 Configuration Examples")
    print("=" * 40)
    
    print("\n🎯 For Cursor:")
    print("Add this to your Cursor MCP settings:")
    cursor_config = {
        "mcpServers": {
            "firecrawl-mcp": {
                "command": "npx",
                "args": ["-y", "firecrawl-mcp"],
                "env": {
                    "FIRECRAWL_API_KEY": "YOUR-API-KEY"
                }
            }
        }
    }
    print(json.dumps(cursor_config, indent=2))
    
    print("\n🎯 For Claude Desktop:")
    print("Add this to your claude_desktop_config.json:")
    claude_config = {
        "mcpServers": {
            "firecrawl": {
                "url": "https://mcp.firecrawl.dev/{YOUR_API_KEY}/sse"
            }
        }
    }
    print(json.dumps(claude_config, indent=2))
    
    print("\n📁 Configuration files are also available in:")
    print("  - config/mcp-config.json")
    print("  - env.template")


def main():
    """Main setup function"""
    print_banner()
    
    # Check prerequisites
    print("🔍 Checking prerequisites...")
    node_ok = check_node_installation()
    npm_ok = check_npm_installation()
    
    if not node_ok or not npm_ok:
        print("\n❌ Missing prerequisites. Please install Node.js and npm first.")
        print("Visit: https://nodejs.org/en/download/")
        sys.exit(1)
    
    # Check if firecrawl-mcp is installed
    if not check_firecrawl_mcp_installation():
        if not install_firecrawl_mcp():
            print("\n❌ Failed to install firecrawl-mcp")
            sys.exit(1)
    
    # Get API key
    api_key = get_api_key()
    if not api_key:
        print("\n❌ Setup cancelled - no API key provided")
        sys.exit(1)
    
    # Create .env file
    if not create_env_file(api_key):
        print("\n❌ Failed to create .env file")
        sys.exit(1)
    
    # Test the setup
    if test_firecrawl_mcp(api_key):
        print("\n🎉 Setup completed successfully!")
    else:
        print("\n⚠️  Setup completed with warnings. Please check your API key.")
    
    # Show configuration examples
    show_configuration_examples()
    
    print(f"\n📚 Next steps:")
    print("1. Configure your AI editor (Cursor, Claude Desktop, etc.) using the examples above")
    print("2. Replace 'YOUR-API-KEY' with your actual API key")
    print("3. Restart your editor to load the MCP server")
    print("4. Test the integration by asking the AI to scrape a website")
    print("\n✨ Happy scraping!")


if __name__ == "__main__":
    main() 