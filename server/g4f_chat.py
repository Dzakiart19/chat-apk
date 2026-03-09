#!/usr/bin/env python3
"""
g4f Chat Handler for Dzeck AI
Uses gpt4free library with PollinationsAI provider (free, no API key required).
Reads JSON from stdin, streams response as JSON lines to stdout.

PollinationsAI supports true token-by-token streaming.
"""
import sys
import json
import asyncio


async def stream_response(messages: list) -> None:
    """Stream response using PollinationsAI async generator."""
    from g4f.Provider import PollinationsAI

    gen = PollinationsAI.create_async_generator(
        model="",
        messages=messages,
        stream=True,
    )

    async for chunk in gen:
        if hasattr(chunk, "choices") and chunk.choices:
            choice = chunk.choices[0]
            if (
                hasattr(choice, "delta")
                and hasattr(choice.delta, "content")
                and choice.delta.content
            ):
                data = json.dumps({"content": choice.delta.content})
                sys.stdout.write(data + "\n")
                sys.stdout.flush()


def main():
    try:
        raw_input = sys.stdin.read()
        input_data = json.loads(raw_input)
        messages = input_data.get("messages", [])

        asyncio.run(stream_response(messages))

        sys.stdout.write(json.dumps({"done": True}) + "\n")
        sys.stdout.flush()

    except Exception as e:
        error_msg = json.dumps({"error": str(e)})
        sys.stdout.write(error_msg + "\n")
        sys.stdout.flush()
        sys.exit(1)


if __name__ == "__main__":
    main()
