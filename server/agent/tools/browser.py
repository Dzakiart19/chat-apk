"""
Browser tools for the AI agent.
Ported from ai-manus: app/domain/services/tools/browser.py
Provides web browsing capabilities using HTTP requests.
Note: ai-manus uses Playwright for full browser automation in a Docker sandbox.
This implementation provides equivalent functionality using HTTP requests.
"""
import re
import json
import urllib.request
import urllib.parse
import ssl
from typing import Optional

from server.agent.models.tool_result import ToolResult


class BrowserSession:
    """Simple browser session tracking."""

    def __init__(self) -> None:
        self.current_url: Optional[str] = None
        self.current_title: str = ""
        self.current_content: str = ""
        self.history: list = []

    def navigate(self, url: str) -> ToolResult:
        """Navigate to a URL and get page content."""
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
                        data={"url": url, "content_type": content_type},
                    )
                html = response.read().decode("utf-8", errors="replace")

            # Extract title
            title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
            self.current_title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip() if title_match else ""

            # Clean HTML to text
            text = self._html_to_text(html)

            self.current_url = url
            self.current_content = text
            if url not in self.history:
                self.history.append(url)

            # Truncate
            max_chars = 8000
            display_text = text[:max_chars] + "\n[Content truncated...]" if len(text) > max_chars else text

            return ToolResult(
                success=True,
                message=f"Navigated to: {self.current_title}\nURL: {url}\n\n{display_text}",
                data={"url": url, "title": self.current_title, "content": display_text},
            )

        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Failed to navigate to {url}: {str(e)}",
                data={"error": str(e), "url": url},
            )

    def view(self) -> ToolResult:
        """Get current page content."""
        if not self.current_url:
            return ToolResult(
                success=False,
                message="No page loaded. Use browser_navigate first.",
            )

        return ToolResult(
            success=True,
            message=f"Current page: {self.current_title}\nURL: {self.current_url}\n\n{self.current_content[:8000]}",
            data={"url": self.current_url, "title": self.current_title, "content": self.current_content[:8000]},
        )

    def _html_to_text(self, html: str) -> str:
        """Convert HTML to clean text."""
        # Remove script and style tags
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
        # Convert block elements to newlines
        html = re.sub(r"<(?:br|p|div|h[1-6]|li|tr)[^>]*>", "\n", html, flags=re.IGNORECASE)
        # Remove tags
        text = re.sub(r"<[^>]+>", "", html)
        # Decode entities
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
        # Clean whitespace
        lines = [line.strip() for line in text.split("\n")]
        lines = [line for line in lines if line]
        return "\n".join(lines)


# Global browser session
_browser = BrowserSession()


def browser_navigate(url: str) -> ToolResult:
    """Navigate to a URL. Matching ai-manus browser_navigate interface."""
    return _browser.navigate(url)


def browser_view() -> ToolResult:
    """Get current page content. Matching ai-manus browser_view interface."""
    return _browser.view()


def browser_restart(url: str = "") -> ToolResult:
    """Restart browser session. Matching ai-manus browser_restart interface."""
    global _browser
    _browser = BrowserSession()
    if url:
        return _browser.navigate(url)
    return ToolResult(success=True, message="Browser session restarted")
