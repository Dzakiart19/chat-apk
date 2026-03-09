"""
Memory model for the AI agent.
Matching ai-manus memory management with message compaction.
"""
from typing import List, Dict, Any, Optional


class Memory:
    """Manages conversation history with compaction support.
    
    Ported from ai-manus: app/domain/models/memory.py
    Handles message storage, retrieval, and context window optimization
    through compaction of large tool results.
    """

    def __init__(self) -> None:
        self._messages: List[Dict[str, Any]] = []

    @property
    def empty(self) -> bool:
        return len(self._messages) == 0

    def add_message(self, message: Dict[str, Any]) -> None:
        """Add a single message to memory."""
        self._messages.append(message)

    def add_messages(self, messages: List[Dict[str, Any]]) -> None:
        """Add multiple messages to memory."""
        self._messages.extend(messages)

    def get_messages(self) -> List[Dict[str, Any]]:
        """Get all messages in memory."""
        return list(self._messages)

    def get_last_message(self) -> Optional[Dict[str, Any]]:
        """Get the most recent message."""
        if self._messages:
            return self._messages[-1]
        return None

    def roll_back(self, count: int = 1) -> None:
        """Remove the last N messages from memory."""
        for _ in range(min(count, len(self._messages))):
            self._messages.pop()

    def compact(self) -> None:
        """Compact memory by removing large tool results.
        
        Ported from ai-manus: removes large content from tool results
        (browser_view, browser_navigate, file_read, web_browse) to save
        context window space. Replaces with truncated summaries.
        """
        large_tool_names = {
            "browser_view", "browser_navigate", "web_browse",
            "file_read", "web_search", "shell_exec"
        }
        max_content_len = 500

        compacted: List[Dict[str, Any]] = []
        for msg in self._messages:
            if msg.get("role") == "tool":
                tool_name = msg.get("tool_name", "")
                content = msg.get("content", "")
                if tool_name in large_tool_names and len(str(content)) > max_content_len:
                    msg = dict(msg)
                    msg["content"] = str(content)[:max_content_len] + "\n[Content compacted to save context...]"
            compacted.append(msg)
        self._messages = compacted

    def clear(self) -> None:
        """Clear all messages from memory."""
        self._messages.clear()

    def __len__(self) -> int:
        return len(self._messages)
