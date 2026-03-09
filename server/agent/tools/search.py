"""
Web search and browsing tools for the AI agent.
Ported from ai-manus: app/domain/services/tools/search.py
Uses DuckDuckGo (free, no API key required) and requests for browsing.
"""
import re
import json
import urllib.request
import urllib.parse
import urllib.error
import ssl
from typing import Optional

from server.agent.models.tool_result import ToolResult


def web_search(query: str, num_results: int = 5) -> ToolResult:
    """Search the web using DuckDuckGo HTML search (no API key needed).

    Matching ai-manus info_search_web tool interface.

    Args:
        query: Search query string
        num_results: Max results to return (default 5)

    Returns:
        ToolResult with search results
    """
    try:
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

        ctx = ssl.create_default_context()
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            },
        )

        with urllib.request.urlopen(req, context=ctx, timeout=15) as response:
            html = response.read().decode("utf-8", errors="replace")

        results = []
        # Parse DuckDuckGo HTML results
        result_pattern = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            re.DOTALL,
        )

        for match in result_pattern.finditer(html):
            if len(results) >= num_results:
                break
            link = match.group(1)
            if "uddg=" in link:
                link_match = re.search(r"uddg=([^&]+)", link)
                if link_match:
                    link = urllib.parse.unquote(link_match.group(1))
            title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            snippet = re.sub(r"<[^>]+>", "", match.group(3)).strip()
            if title and link:
                results.append(
                    {"title": title, "url": link, "snippet": snippet}
                )

        if not results:
            link_pattern = re.compile(
                r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
                re.DOTALL,
            )
            for match in link_pattern.finditer(html):
                if len(results) >= num_results:
                    break
                link = match.group(1)
                if "uddg=" in link:
                    link_match = re.search(r"uddg=([^&]+)", link)
                    if link_match:
                        link = urllib.parse.unquote(link_match.group(1))
                title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
                if title and link:
                    results.append(
                        {"title": title, "url": link, "snippet": ""}
                    )

        result_text = json.dumps(results, indent=2, ensure_ascii=False)
        return ToolResult(
            success=True,
            message=f"Found {len(results)} results for '{query}':\n{result_text}",
            data={"results": results, "query": query, "count": len(results)},
        )

    except Exception as e:
        return ToolResult(
            success=False,
            message=f"Search failed: {str(e)}",
            data={"error": str(e), "query": query},
        )


def web_browse(url: str) -> ToolResult:
    """Browse a web page and extract its text content.

    Matching ai-manus browser_navigate/browser_view interface.

    Args:
        url: Full URL to browse

    Returns:
        ToolResult with page content
    """
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )

        with urllib.request.urlopen(req, context=ctx, timeout=20) as response:
            content_type = response.headers.get("Content-Type", "")
            if "text" not in content_type and "html" not in content_type:
                return ToolResult(
                    success=True,
                    message=f"[Binary content: {content_type}]",
                    data={"url": url, "content": f"[Binary content: {content_type}]", "title": ""},
                )

            html = response.read().decode("utf-8", errors="replace")

        # Extract title
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
        title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip() if title_match else ""

        # Remove script and style tags
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)

        # Convert common block elements to newlines
        html = re.sub(r"<(?:br|p|div|h[1-6]|li|tr)[^>]*>", "\n", html, flags=re.IGNORECASE)

        # Remove all remaining tags
        text = re.sub(r"<[^>]+>", "", html)

        # Decode HTML entities
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")

        # Clean up whitespace
        lines = [line.strip() for line in text.split("\n")]
        lines = [line for line in lines if line]
        text = "\n".join(lines)

        # Truncate to avoid massive responses
        max_chars = 8000
        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n[Content truncated...]"

        return ToolResult(
            success=True,
            message=f"Page: {title}\nURL: {url}\n\n{text}",
            data={"url": url, "title": title, "content": text, "length": len(text)},
        )

    except Exception as e:
        return ToolResult(
            success=False,
            message=f"Failed to browse {url}: {str(e)}",
            data={"error": str(e), "url": url},
        )
