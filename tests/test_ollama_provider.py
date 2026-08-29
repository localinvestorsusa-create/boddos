import httpx
import respx

from boddos.models.base import ChatMessage
from boddos.models.ollama_adapter import OllamaProvider


@respx.mock
async def test_preload_sends_empty_messages_and_keep_alive():
    route = respx.post("http://x/api/chat").mock(return_value=httpx.Response(200, json={"message": {}}))
    provider = OllamaProvider(base_url="http://x", keep_alive="30m")
    ok = await provider.preload("qwen3:1.7b")
    assert ok
    body = route.calls.last.request.content
    import json
    payload = json.loads(body)
    assert payload["model"] == "qwen3:1.7b"
    assert payload["messages"] == []
    assert payload["keep_alive"] == "30m"


@respx.mock
async def test_preload_fails_cleanly_when_ollama_unreachable():
    respx.post("http://x/api/chat").mock(side_effect=httpx.ConnectError("refused"))
    provider = OllamaProvider(base_url="http://x")
    ok = await provider.preload("qwen3:1.7b")
    assert ok is False


@respx.mock
async def test_chat_and_chat_stream_include_keep_alive():
    respx.post("http://x/api/chat").mock(
        return_value=httpx.Response(200, json={"message": {"content": "hi"}}),
    )
    provider = OllamaProvider(base_url="http://x", keep_alive="45m")
    reply = await provider.chat("qwen3:1.7b", [ChatMessage("user", "hello")])
    assert reply == "hi"

    import json
    body = respx.calls.last.request.content
    payload = json.loads(body)
    assert payload["keep_alive"] == "45m"


@respx.mock
async def test_chat_with_tools_includes_keep_alive():
    respx.post("http://x/api/chat").mock(
        return_value=httpx.Response(200, json={"message": {"role": "assistant", "content": "ok"}}),
    )
    provider = OllamaProvider(base_url="http://x", keep_alive="45m")
    await provider.chat_with_tools("qwen3:1.7b", [{"role": "user", "content": "hi"}], [])

    import json
    body = respx.calls.last.request.content
    payload = json.loads(body)
    assert payload["keep_alive"] == "45m"
