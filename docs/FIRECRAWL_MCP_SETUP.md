# Firecrawl MCP Setup Guide

This guide will help you install and configure Firecrawl MCP (Model Context Protocol) server for enhanced web scraping capabilities in your ZapAI project.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Quick Setup](#quick-setup)
- [Manual Setup](#manual-setup)
- [Configuration](#configuration)
- [Testing](#testing)
- [Usage Examples](#usage-examples)
- [Troubleshooting](#troubleshooting)
- [Available Tools](#available-tools)

## Overview

Firecrawl MCP provides powerful web scraping capabilities through the Model Context Protocol, allowing AI assistants to:

- 🔥 **Scrape** single web pages with advanced options
- 🕸️ **Crawl** entire websites systematically  
- 🔍 **Search** the web and extract content
- 🎯 **Extract** structured data using AI
- 📊 **Research** topics deeply across multiple sources
- 🗺️ **Map** website structures and discover URLs

## Prerequisites

Before starting, ensure you have:

- **Node.js** (v16 or higher) - [Download here](https://nodejs.org/)
- **npm** (comes with Node.js)
- **Firecrawl API Key** - [Get it here](https://firecrawl.dev/app/api-keys)

## Quick Setup

### Option 1: Automated Setup Script

Run our setup script to automatically install and configure everything:

```bash
python scripts/setup_firecrawl_mcp.py
```

The script will:
1. Check prerequisites
2. Install firecrawl-mcp
3. Prompt for your API key
4. Create/update .env file
5. Test the installation
6. Show configuration examples

### Option 2: One-Line Installation

If you already have your API key:

```bash
# Install firecrawl-mcp globally
npm install -g firecrawl-mcp

# Test installation
env FIRECRAWL_API_KEY=your-api-key npx firecrawl-mcp --help
```

## Manual Setup

### Step 1: Install firecrawl-mcp

```bash
npm install -g firecrawl-mcp
```

### Step 2: Get API Key

1. Visit [https://firecrawl.dev/app/api-keys](https://firecrawl.dev/app/api-keys)
2. Sign up or log in
3. Create a new API key (starts with `fc-`)

### Step 3: Configure Environment

Create or update your `.env` file:

```bash
# Copy the template
cp env.template .env

# Edit the .env file and add your API key
FIRECRAWL_API_KEY=fc-your-api-key-here
```

### Step 4: Update Python Dependencies

Install the latest Firecrawl Python SDK:

```bash
pip install firecrawl-py==2.15.0
```

## Configuration

### For Cursor

1. Open Cursor Settings → Features → MCP Servers
2. Click "+ Add new global MCP server"  
3. Add this configuration:

```json
{
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
```

### For Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "firecrawl": {
      "url": "https://mcp.firecrawl.dev/{YOUR_API_KEY}/sse"
    }
  }
}
```

### For VS Code

Add to your User Settings (JSON):

```json
{
  "mcp": {
    "inputs": [
      {
        "type": "promptString",
        "id": "apiKey",
        "description": "Firecrawl API Key",
        "password": true
      }
    ],
    "servers": {
      "firecrawl": {
        "command": "npx",
        "args": ["-y", "firecrawl-mcp"],
        "env": {
          "FIRECRAWL_API_KEY": "${input:apiKey}"
        }
      }
    }
  }
}
```

### For Windsurf

Add to `./codeium/windsurf/model_config.json`:

```json
{
  "mcpServers": {
    "mcp-server-firecrawl": {
      "command": "npx",
      "args": ["-y", "firecrawl-mcp"],
      "env": {
        "FIRECRAWL_API_KEY": "YOUR_API_KEY"
      }
    }
  }
}
```

## Testing

### Test MCP Server

```bash
# Basic test
env FIRECRAWL_API_KEY=your-api-key npx firecrawl-mcp --help

# Test with SSE mode
env SSE_LOCAL=true FIRECRAWL_API_KEY=your-api-key npx firecrawl-mcp
```

### Test Python Integration

```python
from firecrawl import FirecrawlApp

app = FirecrawlApp(api_key="fc-YOUR_API_KEY")

# Test scraping
result = app.scrape_url('https://example.com', formats=['markdown'])
print(result)
```

## Usage Examples

### In AI Conversations

Once configured, you can ask your AI assistant to perform web scraping tasks:

**Scraping:**
- "Scrape the content from https://example.com and summarize it"
- "Get the main content from this blog post: [URL]"

**Crawling:**
- "Crawl the first 5 pages of example.com and extract all article titles"
- "Map all URLs on this website: https://docs.example.com"

**Searching:**
- "Search for 'AI trends 2024' and scrape the top 3 results"
- "Find recent news about electric vehicles and summarize"

**Data Extraction:**
- "Extract all product names and prices from this e-commerce page"
- "Get contact information from this company website"

### Advanced Configuration

#### Custom Retry Settings

```bash
export FIRECRAWL_RETRY_MAX_ATTEMPTS=5
export FIRECRAWL_RETRY_INITIAL_DELAY=2000
export FIRECRAWL_RETRY_MAX_DELAY=30000
export FIRECRAWL_RETRY_BACKOFF_FACTOR=3
```

#### Credit Monitoring

```bash
export FIRECRAWL_CREDIT_WARNING_THRESHOLD=2000
export FIRECRAWL_CREDIT_CRITICAL_THRESHOLD=500
```

#### Self-Hosted Instance

```bash
export FIRECRAWL_API_URL=https://firecrawl.your-domain.com
export FIRECRAWL_API_KEY=your-api-key  # Optional for self-hosted
```

## Available Tools

The Firecrawl MCP server provides these tools:

| Tool | Description | Best For |
|------|-------------|----------|
| `firecrawl_scrape` | Scrape single URL | Getting content from known pages |
| `firecrawl_batch_scrape` | Scrape multiple URLs | Processing lists of URLs |
| `firecrawl_search` | Web search + scraping | Finding and extracting info |
| `firecrawl_crawl` | Crawl entire websites | Comprehensive site analysis |
| `firecrawl_extract` | AI-powered data extraction | Structured data from pages |
| `firecrawl_deep_research` | Multi-source research | In-depth topic analysis |
| `firecrawl_map` | Discover site URLs | Website structure mapping |
| `firecrawl_generate_llmstxt` | Generate LLMs.txt | AI interaction guidelines |

## Troubleshooting

### Common Issues

**1. "FIRECRAWL_API_KEY environment variable is required"**
- Ensure your API key is set in the environment
- Check that the key starts with `fc-`
- Restart your editor after configuration

**2. "Command not found: npx"**
- Install Node.js from [nodejs.org](https://nodejs.org/)
- Restart your terminal after installation

**3. "firecrawl-mcp not found"**
- Install globally: `npm install -g firecrawl-mcp`
- Check npm global path: `npm config get prefix`

**4. Rate limit errors**
- The server automatically handles rate limits with backoff
- Adjust retry settings if needed
- Check your API quota at [firecrawl.dev](https://firecrawl.dev/)

**5. MCP server not appearing in editor**
- Restart your editor after configuration
- Check the configuration syntax
- Look for error messages in editor logs

### Debug Mode

Enable debug logging:

```bash
DEBUG=firecrawl* npx firecrawl-mcp
```

### Getting Help

- 📖 [Official Documentation](https://docs.firecrawl.dev/mcp)
- 🐛 [GitHub Issues](https://github.com/mendableai/firecrawl-mcp-server/issues)
- 💬 [Community Discord](https://discord.gg/firecrawl)

## Performance Tips

1. **Use batch operations** for multiple URLs
2. **Set appropriate limits** to avoid timeouts
3. **Cache results** when possible using `maxAge` parameter
4. **Monitor credit usage** to avoid service interruption
5. **Use specific selectors** for faster extraction

## Security Notes

- Keep your API key secure and never commit it to version control
- Use environment variables or secure configuration files
- Regularly rotate your API keys
- Monitor usage for unexpected activity

---

✨ **You're all set!** Your Firecrawl MCP server is now ready to enhance your AI assistant with powerful web scraping capabilities. 