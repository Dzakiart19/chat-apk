"""
Browser tools for Dzeck AI agent.
Based on the official Dzeck function calls specification.
Provides web browsing capabilities using HTTP requests.
Note: Full browser automation (click/type/scroll) is provided as best-effort
using HTTP-based navigation since Playwright is not available in this environment.
"""
import re
import json
import os
import urllib.request
import urllib.parse
import ssl
from typing import Optional

from server.agent.models.tool_result import ToolResult


class BrowserSession:
    """Browser session with page state tracking."""

    def __init__(self) -> None:
        self.current_url: Optional[str] = None
        self.current_title: str = ""
        self.current_content: str = ""
        self.current_html: str = ""
        self.links: list = []
        self.history: list = []
        self.console_logs: list = []

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
                    "Accept-Language": "en-US,en;q=0.9",
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
                self.current_html = response.read().decode("utf-8", errors="replace")

            # Extract title
            title_match = re.search(
                r"<title[^>]*>(.*?)</title>", self.current_html,
                re.DOTALL | re.IGNORECASE
            )
            self.current_title = (
                re.sub(r"<[^>]+>", "", title_match.group(1)).strip()
                if title_match else ""
            )

            # Extract links
            self.links = self._extract_links(self.current_html, url)

            # Convert to readable text
            self.current_content = self._html_to_text(self.current_html)
            self.current_url = url

            if url not in self.history:
                self.history.append(url)

            max_chars = 8000
            display = (
                self.current_content[:max_chars] + "\n[Content truncated...]"
                if len(self.current_content) > max_chars
                else self.current_content
            )

            return ToolResult(
                success=True,
                message=f"Page: {self.current_title}\nURL: {url}\n\n{display}",
                data={
                    "url": url,
                    "title": self.current_title,
                    "content": display,
                    "links_count": len(self.links),
                },
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
        content = self.current_content[:8000]
        return ToolResult(
            success=True,
            message=f"Current page: {self.current_title}\nURL: {self.current_url}\n\n{content}",
            data={
                "url": self.current_url,
                "title": self.current_title,
                "content": content,
                "links_count": len(self.links),
            },
        )

    def click(self, coordinate_x: float, coordinate_y: float,
              button: str = "left") -> ToolResult:
        """Simulate a click - extracts link near the given coordinates (best-effort).

        Since we use HTTP requests (not a real browser), clicking on a link
        means navigating to the URL closest to the given coordinates in the page.

        Args:
            coordinate_x: Horizontal coordinate
            coordinate_y: Vertical coordinate
            button: Mouse button ('left', 'right', 'middle')
        """
        if not self.current_url:
            return ToolResult(
                success=False,
                message="No page loaded. Use browser_navigate first.",
            )

        # If we have links, try to navigate to the first one as a proxy for click
        # Real click coordinates can't be resolved without a browser engine
        if self.links:
            # Use link index as a rough proxy for vertical position
            link_idx = max(0, min(int(coordinate_y / 100), len(self.links) - 1))
            target_url = self.links[link_idx].get("url", "")
            if target_url:
                return self.navigate(target_url)

        return ToolResult(
            success=True,
            message=f"Click simulated at ({coordinate_x}, {coordinate_y}) with {button} button. "
                    "No navigable link found at position; page content unchanged.",
            data={"coordinate_x": coordinate_x, "coordinate_y": coordinate_y, "button": button},
        )

    def type_text(self, text: str) -> ToolResult:
        """Simulate typing text (best-effort - logs the action).

        Args:
            text: Text to type into the currently focused element
        """
        self.console_logs.append(f"[type] Typed: {text}")
        return ToolResult(
            success=True,
            message=f"Typed text: {repr(text)}",
            data={"text": text},
        )

    def scroll(self, coordinate_x: float, coordinate_y: float,
               direction: str, amount: int = 3) -> ToolResult:
        """Simulate scrolling (best-effort - shows more content).

        Args:
            coordinate_x: Horizontal coordinate
            coordinate_y: Vertical coordinate
            direction: Scroll direction ('up', 'down', 'left', 'right')
            amount: Number of scroll units (default 3)
        """
        if not self.current_url:
            return ToolResult(
                success=False,
                message="No page loaded. Use browser_navigate first.",
            )

        content = self.current_content
        total = len(content)
        chunk = 2000 * amount

        if direction == "down":
            offset = min(int(coordinate_y * 10) + chunk, total)
            snippet = content[max(0, offset - 4000):offset]
        else:
            snippet = content[:4000]

        return ToolResult(
            success=True,
            message=f"Scrolled {direction} by {amount} units.\n\n{snippet}",
            data={
                "direction": direction,
                "amount": amount,
                "content_snippet": snippet[:2000],
            },
        )

    def scroll_to_bottom(self, coordinate_x: float = 0,
                          coordinate_y: float = 0) -> ToolResult:
        """Scroll to the bottom of the page to load all content."""
        if not self.current_url:
            return ToolResult(
                success=False,
                message="No page loaded. Use browser_navigate first.",
            )

        content = self.current_content
        bottom_content = content[-4000:] if len(content) > 4000 else content
        return ToolResult(
            success=True,
            message=f"Scrolled to bottom of page.\n\n{bottom_content}",
            data={"content_bottom": bottom_content},
        )

    def read_links(self, max_links: int = 20) -> ToolResult:
        """Get all links from the current page.

        Args:
            max_links: Maximum number of links to return (default 20)
        """
        if not self.current_url:
            return ToolResult(
                success=False,
                message="No page loaded. Use browser_navigate first.",
            )

        links_subset = self.links[:max_links]
        links_text = "\n".join(
            f"[{i+1}] {l.get('text', '')} -> {l.get('url', '')}"
            for i, l in enumerate(links_subset)
        )

        return ToolResult(
            success=True,
            message=f"Found {len(self.links)} links (showing {len(links_subset)}):\n\n{links_text}",
            data={"links": links_subset, "total": len(self.links)},
        )

    def console_view(self, max_lines: int = 100) -> ToolResult:
        """View browser console logs.

        Args:
            max_lines: Maximum number of log lines to return (default 100)
        """
        logs = self.console_logs[-max_lines:]
        logs_text = "\n".join(logs) if logs else "(No console logs)"
        return ToolResult(
            success=True,
            message=f"Browser console logs (last {max_lines}):\n\n{logs_text}",
            data={"logs": logs, "total": len(self.console_logs)},
        )

    def save_image(self, coordinate_x: float, coordinate_y: float,
                   save_dir: str, base_name: str) -> ToolResult:
        """Save an image from the current page to a local file.

        Extracts image URLs from the page and downloads one near the given coordinates.

        Args:
            coordinate_x: Horizontal coordinate of the image element
            coordinate_y: Vertical coordinate of the image element
            save_dir: Local directory to save the image file
            base_name: Base name for the image file (without extension)
        """
        if not self.current_html:
            return ToolResult(
                success=False,
                message="No page loaded. Use browser_navigate first.",
            )

        # Find image URLs in the HTML
        img_pattern = re.compile(
            r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE
        )
        images = [m.group(1) for m in img_pattern.finditer(self.current_html)]

        if not images:
            return ToolResult(
                success=False,
                message="No images found on the current page.",
                data={"coordinate_x": coordinate_x, "coordinate_y": coordinate_y},
            )

        # Pick image closest to coordinates (use index as rough proxy)
        img_idx = max(0, min(int(coordinate_y / 100), len(images) - 1))
        img_url = images[img_idx]

        # Resolve relative URLs
        if img_url.startswith("//"):
            img_url = "https:" + img_url
        elif img_url.startswith("/") and self.current_url:
            from urllib.parse import urlparse
            parsed = urlparse(self.current_url)
            img_url = f"{parsed.scheme}://{parsed.netloc}{img_url}"

        try:
            os.makedirs(save_dir, exist_ok=True)
            ctx = ssl.create_default_context()
            req = urllib.request.Request(
                img_url,
                headers={"User-Agent": "Mozilla/5.0 Chrome/120.0.0.0"},
            )

            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                content_type = resp.headers.get("Content-Type", "image/jpeg")
                data = resp.read()

            ext = "jpg"
            if "png" in content_type:
                ext = "png"
            elif "gif" in content_type:
                ext = "gif"
            elif "webp" in content_type:
                ext = "webp"
            elif "svg" in content_type:
                ext = "svg"

            save_path = os.path.join(save_dir, f"{base_name}.{ext}")
            with open(save_path, "wb") as f:
                f.write(data)

            return ToolResult(
                success=True,
                message=f"Image saved to: {save_path} ({len(data)} bytes)",
                data={"save_path": save_path, "url": img_url, "size": len(data)},
            )

        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Failed to save image: {str(e)}",
                data={"error": str(e), "url": img_url},
            )

    def _extract_links(self, html: str, base_url: str) -> list:
        """Extract all links from HTML."""
        links = []
        pattern = re.compile(
            r'<a[^>]+href=["\']([^"\'#][^"\']*)["\'][^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )
        seen = set()
        for match in pattern.finditer(html):
            href = match.group(1).strip()
            text = re.sub(r"<[^>]+>", "", match.group(2)).strip()

            # Resolve relative URLs
            if href.startswith("//"):
                href = "https:" + href
            elif href.startswith("/") and base_url:
                from urllib.parse import urlparse
                parsed = urlparse(base_url)
                href = f"{parsed.scheme}://{parsed.netloc}{href}"
            elif not href.startswith("http"):
                continue

            if href not in seen and len(links) < 100:
                seen.add(href)
                links.append({"url": href, "text": text[:100]})

        return links

    def _html_to_text(self, html: str) -> str:
        """Convert HTML to clean readable text."""
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
        html = re.sub(r"<(?:br|p|div|h[1-6]|li|tr|section|article)[^>]*>", "\n", html, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", html)
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
        lines = [line.strip() for line in text.split("\n")]
        lines = [line for line in lines if line]
        return "\n".join(lines)


# ─── Global browser session ─────────────────────────────────────────

_browser = BrowserSession()


def browser_navigate(url: str) -> ToolResult:
    """Navigate to a URL and get page content."""
    return _browser.navigate(url)


def browser_view() -> ToolResult:
    """Get the current page content and visible elements."""
    return _browser.view()


def browser_click(coordinate_x: float, coordinate_y: float,
                  button: str = "left") -> ToolResult:
    """Click on an element at the given coordinates (best-effort via link navigation).

    Args:
        coordinate_x: Horizontal coordinate relative to viewport left edge
        coordinate_y: Vertical coordinate relative to viewport top edge
        button: Mouse button to use ('left', 'right', 'middle')
    """
    return _browser.click(coordinate_x, coordinate_y, button)


def browser_type(text: str) -> ToolResult:
    """Type text into the currently focused browser element.

    Args:
        text: Text to type
    """
    return _browser.type_text(text)


def browser_scroll(coordinate_x: float, coordinate_y: float,
                   direction: str, amount: int = 3) -> ToolResult:
    """Scroll the browser page.

    Args:
        coordinate_x: Horizontal coordinate of scroll position
        coordinate_y: Vertical coordinate of scroll position
        direction: Scroll direction ('up', 'down', 'left', 'right')
        amount: Number of scroll units (default 3)
    """
    return _browser.scroll(coordinate_x, coordinate_y, direction, amount)


def browser_scroll_to_bottom(coordinate_x: float = 0,
                              coordinate_y: float = 0) -> ToolResult:
    """Scroll to the bottom of the current page to load all content."""
    return _browser.scroll_to_bottom(coordinate_x, coordinate_y)


def browser_read_links(max_links: int = 20) -> ToolResult:
    """Get all links from the current page.

    Args:
        max_links: Maximum number of links to return (default 20)
    """
    return _browser.read_links(max_links)


def browser_console_view(max_lines: int = 100) -> ToolResult:
    """View browser console logs.

    Args:
        max_lines: Maximum number of log lines to return (default 100)
    """
    return _browser.console_view(max_lines)


def browser_restart(url: str = "") -> ToolResult:
    """Restart the browser session and clear all state.

    Args:
        url: Optional URL to navigate to after restart
    """
    global _browser
    _browser = BrowserSession()
    if url:
        return _browser.navigate(url)
    return ToolResult(success=True, message="Browser session restarted and cleared.")


def browser_save_image(coordinate_x: float, coordinate_y: float,
                       save_dir: str, base_name: str) -> ToolResult:
    """Save an image from the current browser page to a local file.

    Args:
        coordinate_x: Horizontal coordinate of the image element
        coordinate_y: Vertical coordinate of the image element
        save_dir: Local directory to save the image file (absolute path)
        base_name: Base name for the image file (without extension)
    """
    return _browser.save_image(coordinate_x, coordinate_y, save_dir, base_name)
