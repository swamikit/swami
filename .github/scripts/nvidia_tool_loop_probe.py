"""Prove NVIDIA Kimi can complete a real, allow-listed tool-calling loop."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import urllib.error
import urllib.request


ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL = "moonshotai/kimi-k3"
ALLOWED_PATH = "README.md"


def post(messages: list[dict], *, tools: list[dict] | None = None) -> dict:
    api_key = os.environ.get("NVIDIA_API_KEY", "")
    if not api_key:
        raise RuntimeError("NVIDIA_API_KEY is unavailable")

    payload: dict = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": 1024,
        "stream": False,
        "temperature": 0,
    }
    if tools is not None:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:1000]
        raise RuntimeError(f"NVIDIA HTTP {exc.code}: {detail}") from exc


def main() -> None:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "inspect_repository_file",
                "description": "Read one explicitly allow-listed repository file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "enum": [ALLOWED_PATH],
                            "description": "Allow-listed repository-relative path.",
                        }
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
        }
    ]
    messages: list[dict] = [
        {
            "role": "system",
            "content": (
                "You are a read-only Builder capability probe. Use the supplied "
                "repository tool exactly once before answering. Do not guess file contents."
            ),
        },
        {
            "role": "user",
            "content": (
                "Inspect README.md. After the tool result, respond with the exact "
                "proof_token followed by the first Markdown heading."
            ),
        },
    ]

    first = post(messages, tools=tools)
    choices = first.get("choices") or []
    if not choices:
        raise RuntimeError("NVIDIA returned no choices")
    assistant = choices[0].get("message") or {}
    tool_calls = assistant.get("tool_calls") or []
    if len(tool_calls) != 1:
        raise RuntimeError(f"expected exactly one tool call, received {len(tool_calls)}")

    call = tool_calls[0]
    function = call.get("function") or {}
    if function.get("name") != "inspect_repository_file":
        raise RuntimeError(f"unexpected tool requested: {function.get('name')!r}")
    try:
        arguments = json.loads(function.get("arguments") or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError("tool arguments were not valid JSON") from exc
    if arguments != {"path": ALLOWED_PATH}:
        raise RuntimeError(f"tool arguments escaped allow list: {arguments!r}")

    contents = Path(ALLOWED_PATH).read_text(encoding="utf-8")
    first_heading = next(
        (line.removeprefix("# ").strip() for line in contents.splitlines() if line.startswith("# ")),
        "",
    )
    if not first_heading:
        raise RuntimeError("README.md has no level-one Markdown heading")
    proof_token = "repo-" + hashlib.sha256(contents.encode()).hexdigest()[:16]
    tool_result = {
        "path": ALLOWED_PATH,
        "proof_token": proof_token,
        "first_heading": first_heading,
    }

    messages.append(assistant)
    messages.append(
        {
            "role": "tool",
            "tool_call_id": call.get("id"),
            "name": "inspect_repository_file",
            "content": json.dumps(tool_result),
        }
    )
    second = post(messages)
    second_choices = second.get("choices") or []
    final = str(((second_choices[0].get("message") or {}).get("content") or "")) if second_choices else ""
    if proof_token not in final or first_heading not in final:
        raise RuntimeError("final answer did not consume the repository tool result")

    print(f"model={MODEL}")
    print("structured_tool_call=true")
    print("allow_list_enforced=true")
    print("tool_result_consumed=true")
    print(f"tool=inspect_repository_file path={ALLOWED_PATH}")
    print(f"proof_token={proof_token}")
    print(f"first_heading={first_heading}")


if __name__ == "__main__":
    main()
