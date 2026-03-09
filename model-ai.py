import json
import re
import time
import uuid
import urllib.request
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

AIRFORCE_API_URL = "https://api.airforce/v1/chat/completions"
AIRFORCE_API_KEY = (
    "sk-air-QzarypeWD8oB4vEUy5ucuVl1Efef6NSFepurPPiQaeChKQEQxTT7u03T09ikagyg"
)


def airforce_chat(messages, model="gpt-4o-mini", stream=False):
    """Call airforce API for chat completions."""
    body = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 4096,
        "stream": stream,
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

    resp = urllib.request.urlopen(req, timeout=120)
    return json.loads(resp.read().decode("utf-8"))

WORKING_MODELS = {
    "gpt-4o-mini":        {"status": "responsive", "avg_ms": 2900, "note": "OpenAI-compatible via free proxy"},
    "mistral-small-24b":  {"status": "responsive", "avg_ms": 1000, "note": "Tercepat, stabil"},
    "command-a":          {"status": "responsive", "avg_ms": 1500, "note": "Cohere Command, bagus untuk instruksi"},
    "qwen-3-32b":         {"status": "responsive", "avg_ms": 6000, "note": "Alibaba Qwen, pintar & multilingüe"},
}

ALL_MODELS = list(WORKING_MODELS.keys()) + [
    "gpt-4o",
    "gpt-4",
    "llama-3.3-70b",
    "llama-3.1-70b",
    "llama-4-scout",
    "llama-4-maverick",
    "gemini-2.0-flash",
    "gemini-2.5-flash",
    "qwen-3-235b",
    "qwen-2.5-72b",
    "qwen-2.5-coder-32b",
    "deepseek-v3",
    "deepseek-r1",
    "deepseek-r1-distill-llama-70b",
    "mixtral-8x7b",
    "phi-4",
    "nemotron-70b",
    "grok-3",
    "command-r-plus",
    "sonar",
    "sonar-pro",
]

AD_PATTERNS = [
    r"Need proxies cheaper.*",
    r"https?://\S+proxy\S*",
    r"\n\nhttps?://\S+",
]


def clean_response(text: str) -> str:
    for pattern in AD_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.DOTALL)
    return text.strip()


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "status": "ok",
        "message": "Dzeck AI API — Powered by Airforce",
        "recommended_models": list(WORKING_MODELS.keys()),
        "total_models": len(ALL_MODELS),
        "endpoints": {
            "chat":       "POST /v1/chat/completions",
            "models":     "GET  /v1/models",
            "models_info":"GET  /v1/models/info",
            "test_model": "GET  /v1/models/test?model=mistral-small-24b",
            "health":     "GET  /health"
        },
        "rate_limit": "Rate limit tergantung provider airforce API."
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": time.time(),
        "recommended_models": list(WORKING_MODELS.keys()),
        "total_models": len(ALL_MODELS)
    })


@app.route("/v1/models", methods=["GET"])
def list_models():
    models = [
        {
            "id": model,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "airforce",
            "permission": [],
            "root": model,
            "parent": None
        }
        for model in ALL_MODELS
    ]
    return jsonify({"object": "list", "data": models})


@app.route("/v1/models/info", methods=["GET"])
def models_info():
    return jsonify({
        "tested_and_working": WORKING_MODELS,
        "all_available": ALL_MODELS,
        "note": "Model di luar 'tested_and_working' mungkin timeout tergantung kondisi API",
        "streaming_support": "Semua model mendukung streaming (stream: true)",
        "rate_limit": {
            "server": "Tidak ada",
            "provider": "Tergantung provider airforce API"
        }
    })


@app.route("/v1/models/test", methods=["GET"])
def test_model():
    model = request.args.get("model", "gpt-4o-mini")
    start = time.time()
    try:
        response = airforce_chat(
            [{"role": "user", "content": "Reply with exactly: OK"}],
            model=model,
        )
        raw = response.get("choices", [{}])[0].get("message", {}).get("content", "") if response.get("choices") else ""
        content = clean_response(raw)
        elapsed = round((time.time() - start) * 1000)
        return jsonify({
            "model": model,
            "status": "responsive" if content else "empty_response",
            "response_time_ms": elapsed,
            "sample_response": content[:200],
            "streaming_supported": True
        })
    except Exception as e:
        elapsed = round((time.time() - start) * 1000)
        return jsonify({
            "model": model,
            "status": "error",
            "response_time_ms": elapsed,
            "error": str(e),
            "suggestion": "Coba: mistral-small-24b, command-a, gpt-4o-mini, qwen-3-32b"
        })


@app.route("/v1/chat/completions", methods=["POST"])
def chat_completions():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": {"message": "Request body harus berupa JSON", "type": "invalid_request_error"}}), 400

        messages = data.get("messages", [])
        model = data.get("model", "gpt-4o-mini")
        stream = data.get("stream", False)

        if not messages:
            return jsonify({"error": {"message": "Field 'messages' wajib diisi", "type": "invalid_request_error"}}), 400

        if stream:
            def generate():
                try:
                    response = airforce_chat(messages, model=model, stream=False)
                    raw = response.get("choices", [{}])[0].get("message", {}).get("content", "") if response.get("choices") else ""
                    content_text = clean_response(raw)
                    if content_text:
                        chunk_data = {
                            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": model,
                            "choices": [{
                                "index": 0,
                                "delta": {"content": content_text, "role": "assistant"},
                                "finish_reason": None
                            }]
                        }
                        yield f"data: {json.dumps(chunk_data)}\n\n"

                    final = {
                        "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model,
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
                    }
                    yield f"data: {json.dumps(final)}\n\n"
                    yield "data: [DONE]\n\n"
                except Exception as e:
                    error_data = {
                        "error": {
                            "message": str(e),
                            "type": "api_error",
                            "suggestion": "Model yang stabil: gpt-4o-mini, command-a, qwen-3-32b"
                        }
                    }
                    yield f"data: {json.dumps(error_data)}\n\n"

            return Response(
                stream_with_context(generate()),
                mimetype="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                    "Connection": "keep-alive"
                }
            )

        response = airforce_chat(messages, model=model)
        raw = response.get("choices", [{}])[0].get("message", {}).get("content", "") if response.get("choices") else ""
        content = clean_response(raw)
        prompt_tokens = sum(len(m.get("content", "").split()) for m in messages)
        completion_tokens = len(content.split())

        return jsonify({
            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens
            }
        })

    except Exception as e:
        error_msg = str(e)
        print(f"[ERROR] model={model} — {error_msg}")

        return jsonify({
            "error": {
                "message": error_msg,
                "type": "api_error",
                "suggestion": "Model stabil: gpt-4o-mini, command-a, qwen-3-32b"
            }
        }), 500


if __name__ == "__main__":
    print("=" * 60)
    print("  Dzeck AI API — Powered by Airforce")
    print(f"  {len(ALL_MODELS)} models available, {len(WORKING_MODELS)} confirmed working")
    print("  POST /v1/chat/completions  (supports streaming)")
    print("  GET  /v1/models")
    print("  GET  /v1/models/info       (status tiap model)")
    print("  GET  /v1/models/test?model=mistral-small-24b")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=False)
