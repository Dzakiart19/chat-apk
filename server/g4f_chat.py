#!/usr/bin/env python3
"""
Airforce Chat Handler for Dzeck AI
Uses airforce API (OpenAI-compatible) for chat completions.
Reads JSON from stdin, streams response as JSON lines to stdout.
"""
import sys
import json
import urllib.request

AIRFORCE_API_URL = "https://api.airforce/v1/chat/completions"
AIRFORCE_API_KEY = (
    "sk-air-QzarypeWD8oB4vEUy5ucuVl1Efef6NSFepurPPiQaeChKQEQxTT7u03T09ikagyg"
)


def stream_response(messages: list, model: str = "gpt-4o-mini") -> None:
    """Stream response from airforce API."""
    body = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 4096,
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        AIRFORCE_API_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(AIRFORCE_API_KEY),
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    if "choices" in result and result["choices"]:
        content = result["choices"][0]["message"].get("content", "")
        if content:
            data = json.dumps({"content": content})
            sys.stdout.write(data + "\n")
            sys.stdout.flush()


def main():
    try:
        raw_input = sys.stdin.read()
        input_data = json.loads(raw_input)
        messages = input_data.get("messages", [])
        model = input_data.get("model", "gpt-4o-mini")

        stream_response(messages, model)

        sys.stdout.write(json.dumps({"done": True}) + "\n")
        sys.stdout.flush()

    except Exception as e:
        error_msg = json.dumps({"error": str(e)})
        sys.stdout.write(error_msg + "\n")
        sys.stdout.flush()
        sys.exit(1)


if __name__ == "__main__":
    main()
