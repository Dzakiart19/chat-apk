"""
Message tool for the AI agent.
Provides user notification capabilities.
"""


def message_notify(text: str) -> dict:
    """Send a progress notification to the user.

    Args:
        text: Message text to display

    Returns:
        dict with success status
    """
    return {
        "success": True,
        "message": text,
    }
