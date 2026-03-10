"""
Message tools for the AI agent.
Ported from ai-manus: app/domain/services/tools/message.py
Provides user notification and interaction capabilities.
"""
from typing import Optional, List

from server.agent.models.tool_result import ToolResult


def message_notify_user(text: str, attachments: Optional[List[str]] = None) -> ToolResult:
    """Send a progress notification to the user.

    Matching ai-manus message_notify_user tool interface.

    Args:
        text: Message text to display

    Returns:
        ToolResult indicating success
    """
    return ToolResult(
        success=True,
        message=text,
        data={"type": "notify", "text": text},
    )


def message_ask_user(
    text: str,
    attachments: Optional[List[str]] = None,
    suggest_user_takeover: str = "none",
) -> ToolResult:
    """Ask the user a question and wait for response.

    Matching ai-manus message_ask_user tool interface.
    Note: In the current architecture, this sends the question as a message
    and the response will come in the next interaction.

    Args:
        text: Question text to ask the user
        attachments: Optional file attachments
        suggest_user_takeover: Suggest user takes over ("none", "browser", "shell")

    Returns:
        ToolResult with the question sent
    """
    return ToolResult(
        success=True,
        message=text,
        data={
            "type": "ask",
            "text": text,
            "attachments": attachments or [],
            "suggest_user_takeover": suggest_user_takeover,
        },
    )
