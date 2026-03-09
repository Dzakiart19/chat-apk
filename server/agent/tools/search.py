"""
Web search and browsing tools for the AI agent.
Uses DuckDuckGo (free, no API key required) and requests for browsing.
"""
import re
import urllib.request
import urllib.parse
import urllib.error
import ssl


def web_search(query: str, num_results: int = 5) -> dict:
    """Search the web using DuckDuckGo HTML search (no API key needed).

    Args:
        query: Search query string
        num_results: Max results to return (default 5)

    Returns:
        dict with success status and results list
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
            # DuckDuckGo wraps links in a redirect
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
            # Fallback: try a simpler pattern
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

        return {
            "success": True,
            "results": results,
            "query": query,
            "count": len(results),
        }

    except Exception as e:
        return {"success": False, "error": str(e), "results": [], "query": query}


def web_browse(url: str) -> dict:
    """Browse a web page and extract its text content.

    Args:
        url: Full URL to browse

    Returns:
        dict with success status and page content
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
                return {
                    "success": True,
                    "url": url,
                    "content": f"[Binary content: {content_type}]",
                    "title": "",
                }

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

        return {
            "success": True,
            "url": url,
            "title": title,
            "content": text,
            "length": len(text),
        }

    except Exception as e:
        return {"success": False, "error": str(e), "url": url, "content": ""}
