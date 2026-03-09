#!/usr/bin/env python3
"""
g4f Chat Handler for Dzeck AI
Uses gpt4free library with mistral-small-24b model.
Reads JSON from stdin, streams response as JSON lines to stdout.
Uses Yqcloud provider (free, no API key required).
"""
import sys
import json


def main():
    try:
        from g4f.client import Client
        from g4f.Provider import Yqcloud

        raw_input = sys.stdin.read()
        input_data = json.loads(raw_input)
        messages = input_data.get("messages", [])
        model = input_data.get("model", "")

        client = Client(provider=Yqcloud)
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
        )

        for chunk in response:
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

        sys.stdout.write(json.dumps({"done": True}) + "\n")
        sys.stdout.flush()

    except Exception as e:
        error_msg = json.dumps({"error": str(e)})
        sys.stdout.write(error_msg + "\n")
        sys.stdout.flush()
        sys.exit(1)


if __name__ == "__main__":
    main()
