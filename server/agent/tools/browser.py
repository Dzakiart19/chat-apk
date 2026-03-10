"""
Browser tools for Dzeck AI Agent.
Upgraded to use Playwright for real browser automation when available.
Falls back to HTTP-based browsing if Playwright is not installed.

Real browser capabilities (Playwright):
- JavaScript rendering
- Real click/type/scroll interactions
- Screenshot capture
- Console log access
- Form submissions

Fallback (HTTP):
- Basic HTML fetching and parsing
- Link extraction
"""
import re
import os
import json
import asyncio
import logging
import urllib.request
import urllib.parse
import ssl
from typing import Optional, List, Dict, Any

from server.agent.models.tool_result import ToolResult

logger = logging.getLogger(__name__)

PLAYWRIGHT_ENABLED = os.environ.get("PLAYWRIGHT_ENABLED", "true").lower() == "true"

_playwright_available = False
_playwright = None
_browser_instance = None
_browser_page = None

if PLAYWRIGHT_ENABLED:
    try:
        from playwright.sync_api import sync_playwright, Browser, Page, Playwright
        _playwright_available = True
        logger.info("[Browser] Playwright available - using real browser automation.")
    except ImportError:
        logger.warning("[Browser] Playwright not installed - using HTTP fallback.")


class PlaywrightSession:
    """Real browser session using Playwright."""

    def __init__(self) -> None:
        self._pw: Any = None
        self._browser: Any = None
        self._page: Any = None
        self._started = False
        self.current_url: Optional[str] = None
        self.console_logs: List[str] = []

    def start(self) -> bool:
        """Start Playwright browser."""
        if not _playwright_available:
            return False
        try:
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-extensions",
                    "--disable-background-networking",
                ],
            )
            ctx = self._browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            self._page = ctx.new_page()
            self._page.on("console", lambda msg: self.console_logs.append(
                f"[{msg.type}] {msg.text}"
            ))
            self._started = True
            logger.info("[Browser] Playwright browser started.")
            return True
        except Exception as e:
            logger.error("[Browser] Failed to start Playwright: %s", e)
            return False

    def navigate(self, url: str) -> ToolResult:
        """Navigate to URL and return page content."""
        if not self._started and not self.start():
            return ToolResult(success=False, message="Playwright not available.")
        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            self._page.wait_for_timeout(1000)
            self.current_url = self._page.url
            title = self._page.title()
            content = self._page.inner_text("body")
            content = content[:8000]
            return ToolResult(
                success=True,
                message=f"Page: {title}\nURL: {self.current_url}\n\n{content}",
                data={
                    "url": self.current_url,
                    "title": title,
                    "content": content,
                },
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Navigate failed: {e}",
                              data={"error": str(e), "url": url})

    def view(self) -> ToolResult:
        """Get current page content."""
        if not self._started:
            return ToolResult(success=False, message="No page loaded.")
        try:
            content = self._page.inner_text("body")[:8000]
            title = self._page.title()
            return ToolResult(
                success=True,
                message=f"Page: {title}\nURL: {self.current_url}\n\n{content}",
                data={"url": self.current_url, "title": title, "content": content},
            )
        except Exception as e:
            return ToolResult(success=False, message=f"View failed: {e}")

    def click(self, x: float, y: float, button: str = "left") -> ToolResult:
        """Real mouse click at coordinates."""
        if not self._started:
            return ToolResult(success=False, message="No page loaded.")
        try:
            btn_map = {"left": "left", "right": "right", "middle": "middle"}
            self._page.mouse.click(x, y, button=btn_map.get(button, "left"))
            self._page.wait_for_timeout(500)
            self.current_url = self._page.url
            return ToolResult(
                success=True,
                message=f"Clicked at ({x}, {y}) with {button} button.",
                data={"x": x, "y": y, "button": button, "url": self.current_url},
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Click failed: {e}")

    def type_text(self, text: str) -> ToolResult:
        """Type text into focused element."""
        if not self._started:
            return ToolResult(success=False, message="No page loaded.")
        try:
            self._page.keyboard.type(text)
            return ToolResult(
                success=True,
                message=f"Typed: {repr(text)}",
                data={"text": text},
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Type failed: {e}")

    def scroll(self, x: float, y: float, direction: str, amount: int = 3) -> ToolResult:
        """Scroll the page."""
        if not self._started:
            return ToolResult(success=False, message="No page loaded.")
        try:
            delta_y = amount * 200 if direction == "down" else -amount * 200
            delta_x = amount * 200 if direction == "right" else (-amount * 200 if direction == "left" else 0)
            self._page.mouse.wheel(delta_x, delta_y)
            self._page.wait_for_timeout(300)
            content = self._page.inner_text("body")[:4000]
            return ToolResult(
                success=True,
                message=f"Scrolled {direction} by {amount}.\n\n{content}",
                data={"direction": direction, "amount": amount},
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Scroll failed: {e}")

    def scroll_to_bottom(self, x: float = 0, y: float = 0) -> ToolResult:
        """Scroll to bottom of page."""
        if not self._started:
            return ToolResult(success=False, message="No page loaded.")
        try:
            self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self._page.wait_for_timeout(500)
            content = self._page.inner_text("body")[-4000:]
            return ToolResult(
                success=True,
                message=f"Scrolled to bottom.\n\n{content}",
                data={"content_bottom": content},
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Scroll to bottom failed: {e}")

    def read_links(self, max_links: int = 20) -> ToolResult:
        """Get all links on the page."""
        if not self._started:
            return ToolResult(success=False, message="No page loaded.")
        try:
            links_raw = self._page.evaluate("""
                Array.from(document.querySelectorAll('a[href]'))
                    .slice(0, 100)
                    .map(a => ({url: a.href, text: a.innerText.trim().slice(0, 100)}))
            """)
            subset = links_raw[:max_links]
            links_text = "\n".join(
                f"[{i+1}] {l.get('text', '')} -> {l.get('url', '')}"
                for i, l in enumerate(subset)
            )
            return ToolResult(
                success=True,
                message=f"Found {len(links_raw)} links (showing {len(subset)}):\n\n{links_text}",
                data={"links": subset, "total": len(links_raw)},
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Read links failed: {e}")

    def console_view(self, max_lines: int = 100) -> ToolResult:
        """View browser console logs."""
        logs = self.console_logs[-max_lines:]
        text = "\n".join(logs) if logs else "(No console logs)"
        return ToolResult(
            success=True,
            message=f"Console logs:\n\n{text}",
            data={"logs": logs},
        )

    def save_image(self, x: float, y: float, save_dir: str, base_name: str) -> ToolResult:
        """Save screenshot of current page."""
        if not self._started:
            return ToolResult(success=False, message="No page loaded.")
        try:
            os.makedirs(save_dir, exist_ok=True)
            path = os.path.join(save_dir, f"{base_name}.png")
            self._page.screenshot(path=path, full_page=False)
            return ToolResult(
                success=True,
                message=f"Screenshot saved to: {path}",
                data={"save_path": path},
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Save image failed: {e}")

    def restart(self, url: str = "") -> ToolResult:
        """Restart browser session."""
        self.close()
        self.__init__()
        if url:
            return self.navigate(url)
        return ToolResult(success=True, message="Browser restarted.")

    def close(self) -> None:
        """Close Playwright browser."""
        try:
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._started = False


class HTTPBrowserSession:
    """HTTP-based browser fallback (no JavaScript)."""

    def __init__(self) -> None:
        self.current_url: Optional[str] = None
        self.current_title: str = ""
        self.current_content: str = ""
        self.current_html: str = ""
        self.links: list = []
        self.history: list = []
        self.console_logs: list = []

    def navigate(self, url: str) -> ToolResult:
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

            title_match = re.search(r"<title[^>]*>(.*?)</title>", self.current_html,
                                    re.DOTALL | re.IGNORECASE)
            self.current_title = (
                re.sub(r"<[^>]+>", "", title_match.group(1)).strip()
                if title_match else ""
            )
            self.links = self._extract_links(self.current_html, url)
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
            return ToolResult(success=False, message=f"Failed to navigate to {url}: {e}",
                              data={"error": str(e), "url": url})

    def view(self) -> ToolResult:
        if not self.current_url:
            return ToolResult(success=False, message="No page loaded. Use browser_navigate first.")
        content = self.current_content[:8000]
        return ToolResult(
            success=True,
            message=f"Current page: {self.current_title}\nURL: {self.current_url}\n\n{content}",
            data={"url": self.current_url, "title": self.current_title, "content": content},
        )

    def click(self, x: float, y: float, button: str = "left") -> ToolResult:
        if not self.current_url:
            return ToolResult(success=False, message="No page loaded.")
        if self.links:
            idx = max(0, min(int(y / 100), len(self.links) - 1))
            target = self.links[idx].get("url", "")
            if target:
                return self.navigate(target)
        return ToolResult(
            success=True,
            message=f"Click simulated at ({x}, {y}). No navigable link found.",
            data={"x": x, "y": y},
        )

    def type_text(self, text: str) -> ToolResult:
        self.console_logs.append(f"[type] {text}")
        return ToolResult(success=True, message=f"Typed: {repr(text)}", data={"text": text})

    def scroll(self, x: float, y: float, direction: str, amount: int = 3) -> ToolResult:
        if not self.current_url:
            return ToolResult(success=False, message="No page loaded.")
        content = self.current_content
        chunk = 2000 * amount
        if direction == "down":
            offset = min(int(y * 10) + chunk, len(content))
            snippet = content[max(0, offset - 4000):offset]
        else:
            snippet = content[:4000]
        return ToolResult(
            success=True,
            message=f"Scrolled {direction}.\n\n{snippet}",
            data={"direction": direction},
        )

    def scroll_to_bottom(self, x: float = 0, y: float = 0) -> ToolResult:
        if not self.current_url:
            return ToolResult(success=False, message="No page loaded.")
        bottom = self.current_content[-4000:]
        return ToolResult(success=True, message=f"Scrolled to bottom.\n\n{bottom}",
                          data={"content_bottom": bottom})

    def read_links(self, max_links: int = 20) -> ToolResult:
        if not self.current_url:
            return ToolResult(success=False, message="No page loaded.")
        subset = self.links[:max_links]
        text = "\n".join(
            f"[{i+1}] {l.get('text','')} -> {l.get('url','')}"
            for i, l in enumerate(subset)
        )
        return ToolResult(
            success=True,
            message=f"Found {len(self.links)} links:\n\n{text}",
            data={"links": subset, "total": len(self.links)},
        )

    def console_view(self, max_lines: int = 100) -> ToolResult:
        logs = self.console_logs[-max_lines:]
        text = "\n".join(logs) if logs else "(No console logs)"
        return ToolResult(success=True, message=f"Console:\n\n{text}", data={"logs": logs})

    def save_image(self, x: float, y: float, save_dir: str, base_name: str) -> ToolResult:
        if not self.current_html:
            return ToolResult(success=False, message="No page loaded.")
        img_pattern = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
        images = [m.group(1) for m in img_pattern.finditer(self.current_html)]
        if not images:
            return ToolResult(success=False, message="No images found.")
        idx = max(0, min(int(y / 100), len(images) - 1))
        img_url = images[idx]
        if img_url.startswith("//"):
            img_url = "https:" + img_url
        elif img_url.startswith("/") and self.current_url:
            parsed = urllib.parse.urlparse(self.current_url)
            img_url = f"{parsed.scheme}://{parsed.netloc}{img_url}"
        try:
            os.makedirs(save_dir, exist_ok=True)
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(
                urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"}),
                context=ctx, timeout=15
            ) as resp:
                ct = resp.headers.get("Content-Type", "image/jpeg")
                data = resp.read()
            ext = "png" if "png" in ct else "gif" if "gif" in ct else "webp" if "webp" in ct else "jpg"
            path = os.path.join(save_dir, f"{base_name}.{ext}")
            with open(path, "wb") as f:
                f.write(data)
            return ToolResult(success=True, message=f"Image saved to: {path}",
                              data={"save_path": path, "url": img_url})
        except Exception as e:
            return ToolResult(success=False, message=f"Failed to save image: {e}")

    def restart(self, url: str = "") -> ToolResult:
        self.__init__()
        if url:
            return self.navigate(url)
        return ToolResult(success=True, message="Browser session restarted.")

    def _extract_links(self, html: str, base_url: str) -> list:
        links = []
        pattern = re.compile(
            r'<a[^>]+href=["\']([^"\'#][^"\']*)["\'][^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )
        seen = set()
        for match in pattern.finditer(html):
            href = match.group(1).strip()
            text = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            if href.startswith("//"):
                href = "https:" + href
            elif href.startswith("/") and base_url:
                parsed = urllib.parse.urlparse(base_url)
                href = f"{parsed.scheme}://{parsed.netloc}{href}"
            elif not href.startswith("http"):
                continue
            if href not in seen and len(links) < 100:
                seen.add(href)
                links.append({"url": href, "text": text[:100]})
        return links

    def _html_to_text(self, html: str) -> str:
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
        html = re.sub(
            r"<(?:br|p|div|h[1-6]|li|tr|section|article)[^>]*>", "\n", html,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"<[^>]+>", "", html)
        text = (text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                .replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " "))
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        return "\n".join(lines)


def _make_session() -> Any:
    """Create the best available browser session."""
    if _playwright_available and PLAYWRIGHT_ENABLED:
        sess = PlaywrightSession()
        if sess.start():
            return sess
        logger.warning("[Browser] Playwright start failed, falling back to HTTP.")
    return HTTPBrowserSession()


_browser = _make_session()


def _reset_browser() -> None:
    global _browser
    _browser = _make_session()


def browser_navigate(url: str) -> ToolResult:
    return _browser.navigate(url)


def browser_view() -> ToolResult:
    return _browser.view()


def browser_click(
    coordinate_x: Optional[float] = None,
    coordinate_y: Optional[float] = None,
    index: Optional[int] = None,
    button: str = "left",
) -> ToolResult:
    x = coordinate_x or 0.0
    y = coordinate_y or 0.0
    return _browser.click(x, y, button)


def browser_input(
    text: str,
    press_enter: bool = False,
    coordinate_x: Optional[float] = None,
    coordinate_y: Optional[float] = None,
    index: Optional[int] = None,
) -> ToolResult:
    """Type text into a focused element, optionally clicking a coordinate/index first."""
    if coordinate_x is not None and coordinate_y is not None:
        _browser.click(coordinate_x, coordinate_y)
    result = _browser.type_text(text)
    if press_enter and result.success:
        _press_key("Enter")
    return result


def browser_move_mouse(coordinate_x: float, coordinate_y: float) -> ToolResult:
    """Move cursor to coordinates without clicking."""
    if hasattr(_browser, "_page") and _browser._page:
        try:
            _browser._page.mouse.move(coordinate_x, coordinate_y)
            return ToolResult(
                success=True,
                message=f"Mouse moved to ({coordinate_x}, {coordinate_y}).",
                data={"x": coordinate_x, "y": coordinate_y},
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Move mouse failed: {e}")
    return ToolResult(
        success=True,
        message=f"Mouse move simulated to ({coordinate_x}, {coordinate_y}).",
        data={"x": coordinate_x, "y": coordinate_y},
    )


def _press_key(key: str) -> ToolResult:
    """Internal helper to press a keyboard key."""
    if hasattr(_browser, "_page") and _browser._page:
        try:
            _browser._page.keyboard.press(key)
            return ToolResult(success=True, message=f"Pressed key: {key}", data={"key": key})
        except Exception as e:
            return ToolResult(success=False, message=f"Press key failed: {e}")
    return ToolResult(success=True, message=f"Key press simulated: {key}", data={"key": key})


def browser_press_key(key: str) -> ToolResult:
    """Simulate a keyboard key press on the current browser page."""
    return _press_key(key)


def browser_select_option(index: int, option: int) -> ToolResult:
    """Select a specific option from a dropdown list element."""
    if hasattr(_browser, "_page") and _browser._page:
        try:
            selects = _browser._page.query_selector_all("select")
            if index < 0 or index >= len(selects):
                return ToolResult(
                    success=False,
                    message=f"No dropdown at index {index}. Found {len(selects)} dropdowns.",
                )
            select_el = selects[index]
            options = select_el.query_selector_all("option")
            if option < 0 or option >= len(options):
                return ToolResult(
                    success=False,
                    message=f"No option at index {option}. Found {len(options)} options.",
                )
            value = options[option].get_attribute("value") or ""
            select_el.select_option(value=value)
            return ToolResult(
                success=True,
                message=f"Selected option {option} from dropdown {index}.",
                data={"dropdown_index": index, "option_index": option, "value": value},
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Select option failed: {e}")
    return ToolResult(success=False, message="Browser not available for select_option.")


def browser_scroll_up(to_top: bool = False) -> ToolResult:
    """Scroll the current browser page upward."""
    if hasattr(_browser, "_page") and _browser._page:
        try:
            if to_top:
                _browser._page.evaluate("window.scrollTo(0, 0)")
                msg = "Scrolled to top."
            else:
                _browser._page.mouse.wheel(0, -600)
                msg = "Scrolled up."
            _browser._page.wait_for_timeout(300)
            content = _browser._page.inner_text("body")[:4000]
            return ToolResult(success=True, message=f"{msg}\n\n{content}", data={"to_top": to_top})
        except Exception as e:
            return ToolResult(success=False, message=f"Scroll up failed: {e}")
    if hasattr(_browser, "current_content") and _browser.current_content:
        snippet = _browser.current_content[:4000]
        return ToolResult(success=True, message=f"Scrolled up.\n\n{snippet}", data={"to_top": to_top})
    return ToolResult(success=False, message="No page loaded.")


def browser_scroll_down(to_bottom: bool = False) -> ToolResult:
    """Scroll the current browser page downward."""
    if hasattr(_browser, "_page") and _browser._page:
        try:
            if to_bottom:
                _browser._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                msg = "Scrolled to bottom."
            else:
                _browser._page.mouse.wheel(0, 600)
                msg = "Scrolled down."
            _browser._page.wait_for_timeout(300)
            content = _browser._page.inner_text("body")[-4000:]
            return ToolResult(success=True, message=f"{msg}\n\n{content}", data={"to_bottom": to_bottom})
        except Exception as e:
            return ToolResult(success=False, message=f"Scroll down failed: {e}")
    if hasattr(_browser, "current_content") and _browser.current_content:
        snippet = _browser.current_content[-4000:]
        return ToolResult(success=True, message=f"Scrolled down.\n\n{snippet}", data={"to_bottom": to_bottom})
    return ToolResult(success=False, message="No page loaded.")


def browser_console_exec(javascript: str) -> ToolResult:
    """Execute JavaScript code in the browser console."""
    if hasattr(_browser, "_page") and _browser._page:
        try:
            result = _browser._page.evaluate(javascript)
            result_str = str(result) if result is not None else "undefined"
            return ToolResult(
                success=True,
                message=f"JavaScript executed. Result: {result_str}",
                data={"result": result_str, "javascript": javascript},
            )
        except Exception as e:
            return ToolResult(success=False, message=f"JavaScript execution failed: {e}")
    return ToolResult(success=False, message="Browser not available for console_exec.")


def browser_console_view(max_lines: int = 100) -> ToolResult:
    return _browser.console_view(max_lines)


def browser_save_image(coordinate_x: float, coordinate_y: float,
                       save_dir: str, base_name: str) -> ToolResult:
    return _browser.save_image(coordinate_x, coordinate_y, save_dir, base_name)


def image_view(image: str) -> ToolResult:
    """View an image file from the local filesystem."""
    if not os.path.isfile(image):
        return ToolResult(success=False, message=f"Image file not found: {image}")
    try:
        size = os.path.getsize(image)
        ext = os.path.splitext(image)[1].lower()
        return ToolResult(
            success=True,
            message=f"Image file: {image} ({size} bytes, type: {ext})",
            data={"image": image, "size": size, "ext": ext},
        )
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to view image: {e}")
