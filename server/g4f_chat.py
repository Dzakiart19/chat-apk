#!/usr/bin/env python3
"""
Airforce Chat Handler for Dzeck AI
Uses airforce API (OpenAI-compatible) for chat completions.
Reads JSON from stdin, streams response as JSON lines to stdout.
"""
import os
import sys
import json
import time
import urllib.request
import urllib.error


def _load_dotenv() -> None:
    """Load .env file into os.environ if it exists (for local/APK builds)."""
    env_path = os.path.join(os.getcwd(), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


_load_dotenv()

AIRFORCE_API_URL = "https://api.airforce/v1/chat/completions"
AIRFORCE_API_KEY = os.environ.get("AIRFORCE_API_KEY", "")


def call_api(messages: list, model: str = "gpt-4o-mini") -> dict:
    """Call Airforce API and return full response dict."""
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
        raw = resp.read().decode("utf-8")

    # Detect plain-text rate limit (API returns HTTP 200 with "Ratelimit" body)
    if raw.lstrip().startswith("Ratelimit") or "Ratelimit Exceeded" in raw:
        raise urllib.error.HTTPError(
            AIRFORCE_API_URL, 429, "Rate limit exceeded", {}, None)

    return json.loads(raw)


def call_api_with_retry(messages: list, model: str = "gpt-4o-mini", max_retries: int = 5) -> dict:
    """Call Airforce API with exponential backoff retry for rate limits."""
    last_error = None
    for attempt in range(max_retries):
        try:
            return call_api(messages, model)
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code == 429 or e.code >= 500:
                wait = 2 ** attempt
                sys.stderr.write("[chat] HTTP {} error, retrying in {}s (attempt {}/{})\n".format(
                    e.code, wait, attempt + 1, max_retries))
                sys.stderr.flush()
                time.sleep(wait)
            else:
                raise
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                time.sleep(wait)
    if last_error is not None:
        raise last_error
    raise RuntimeError("API call failed after {} retries".format(max_retries))


def stream_response(messages: list, model: str = "gpt-4o-mini") -> None:
    """Call Airforce API and stream response as JSON lines."""
    result = call_api_with_retry(messages, model)

    if "choices" in result and result["choices"]:
        content = result["choices"][0]["message"].get("content", "")
        if content:
            data = json.dumps({"content": content})
            sys.stdout.write(data + "\n")
            sys.stdout.flush()


def main():
    if not AIRFORCE_API_KEY:
        sys.stdout.write(json.dumps({"error": "AIRFORCE_API_KEY environment variable is not set"}) + "\n")
        sys.stdout.flush()
        sys.exit(1)

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
