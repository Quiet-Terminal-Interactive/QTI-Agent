import json
import logging
import os
import re
from pathlib import Path
from llama_cpp import Llama

from tools import dispatch

MODEL_PATH = os.getenv("MODEL_PATH", str(Path.home() / "models" / "qwen3.5-4b-q4_k_m.gguf"))

MAX_ITERATIONS = 10

N_CTX = 2048

log = logging.getLogger("agent")

log.info(f"Loading model from {MODEL_PATH}...")
llm = Llama(
    model_path=MODEL_PATH,
    n_ctx=N_CTX,
    n_threads=os.cpu_count(),
    n_batch=512,
    n_gpu_layers=0,
    verbose=False,
)
log.info("Model loaded.")

def _extract_json(text: str) -> dict | None:
    text = re.sub(r"```(?:json)?", "", text).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None


def _format_tool_result(tool_name: str, result: dict) -> str:
    return json.dumps({
        "tool_result": {
            "tool": tool_name,
            "result": result,
        }
    }, indent=2)


def _call_model(system_prompt: str, messages: list[dict]) -> str:
    response = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            *messages,
        ],
        temperature=0.2,
        max_tokens=512,
        stop=["```\n", "\n\n\n"],
    )
    return response["choices"][0]["message"]["content"].strip()

def run_agent(context: dict) -> tuple[str, list[str]]:
    system_prompt = context["system_prompt"]
    messages = []
    iterations = 0

    log.debug("[agent] Starting run_agent")
    log.debug("[agent] System prompt (first 300 chars): %s", system_prompt[:300])

    messages.append({
        "role": "user",
        "content": "/no_think Respond with a JSON tool call to handle the request above.",
    })

    while iterations < MAX_ITERATIONS:
        iterations += 1
        log.debug("[agent] Iteration %d/%d", iterations, MAX_ITERATIONS)

        raw = _call_model(system_prompt, messages)
        log.debug("[agent] Raw model output: %r", raw)

        messages.append({"role": "assistant", "content": raw})

        parsed = _extract_json(raw)

        if parsed is None:
            log.debug("[agent] JSON parse failed — prompting model to retry")
            messages.append({
                "role": "user",
                "content": (
                    "Your response was not valid JSON. "
                    "Respond with a single JSON tool call and nothing else."
                ),
            })
            continue

        tool_name = parsed.get("tool") or parsed.get("name")
        params = parsed.get("params") or {k: v for k, v in parsed.items() if k not in ("tool", "name")}
        log.debug("[agent] Parsed tool=%r params=%r", tool_name, params)

        if not tool_name:
            log.debug("[agent] Missing 'tool' key in parsed JSON: %r", parsed)
            messages.append({
                "role": "user",
                "content": "Missing 'tool' key. Respond with a valid JSON tool call.",
            })
            continue

        if tool_name == "discord_respond":
            message = params.get("message", "Done.")
            files = [f for f in (params.get("files") or []) if f]
            log.debug("[agent] Finished via discord_respond after %d iteration(s)", iterations)
            return message, files

        log.debug("[agent] Dispatching tool %r", tool_name)
        result = dispatch(tool_name, params)
        log.debug("[agent] Tool %r result: %r", tool_name, result)

        messages.append({
            "role": "user",
            "content": _format_tool_result(tool_name, result),
        })

    log.warning(
        "[agent] Hit MAX_ITERATIONS (%d) without finishing. Last raw output: %r",
        MAX_ITERATIONS,
        messages[-1]["content"] if messages else "<no messages>",
    )
    return (
        "I hit my tool call limit without finishing — something may have gone wrong. "
        "Check the logs or try rephrasing.",
        [],
    )