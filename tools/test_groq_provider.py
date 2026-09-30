"""
Тесты GroqLLM. Без HTTP, без реальных ключей.

Запуск через pytest:
    pytest -v tools/test_groq_provider.py
Прямой запуск:
    python -m tools.test_groq_provider
"""
import os
import sys
from types import SimpleNamespace
from unittest import mock

from assistant.llm.groq_provider import GroqLLM


def _fake_response(text: str):
    msg = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=msg)
    return SimpleNamespace(choices=[choice])


def test_no_key_does_not_create_client(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    llm = GroqLLM()
    assert llm._client is None
    out = llm.chat("привет")
    assert "не задан" in out.lower() or "не настроен" in out.lower()


def test_no_model_does_not_create_client(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake-groq-key")
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    llm = GroqLLM()
    assert llm._client is None


def test_client_created_with_key_and_model(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake-groq-key")
    monkeypatch.setenv("GROQ_MODEL", "llama-3.1-8b-instant")

    fake_client = mock.MagicMock()
    with mock.patch("assistant.llm.groq_provider.OpenAI", return_value=fake_client) as m:
        llm = GroqLLM()
        assert llm._client is fake_client
        m.assert_called_once()
        kwargs = m.call_args.kwargs
        assert kwargs.get("api_key") == "fake-groq-key"
        assert kwargs.get("base_url") == "https://api.groq.com/openai/v1"


def test_success_response(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake-groq-key")
    monkeypatch.setenv("GROQ_MODEL", "llama-3.1-8b-instant")

    fake_client = mock.MagicMock()
    fake_client.chat.completions.create.return_value = _fake_response("привет")

    with mock.patch("assistant.llm.groq_provider.OpenAI", return_value=fake_client):
        llm = GroqLLM()
        out = llm.chat("привет", "система")

    assert out == "привет"
    call_kwargs = fake_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "llama-3.1-8b-instant"
    assert any(m["role"] == "system" for m in call_kwargs["messages"])


def test_timeout_classified(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake-groq-key")
    monkeypatch.setenv("GROQ_MODEL", "m")

    fake_client = mock.MagicMock()
    fake_client.chat.completions.create.side_effect = TimeoutError("timeout occurred")

    with mock.patch("assistant.llm.groq_provider.OpenAI", return_value=fake_client):
        llm = GroqLLM()
        out = llm.chat("привет")

    assert "время ожидания" in out.lower() or "timeout" in out.lower()


def test_network_error_classified(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake-groq-key")
    monkeypatch.setenv("GROQ_MODEL", "m")

    fake_client = mock.MagicMock()
    fake_client.chat.completions.create.side_effect = ConnectionError("connect failed")

    with mock.patch("assistant.llm.groq_provider.OpenAI", return_value=fake_client):
        llm = GroqLLM()
        out = llm.chat("привет")

    assert "соединения" in out.lower() or "network" in out.lower()


def test_rate_limit_classified(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake-groq-key")
    monkeypatch.setenv("GROQ_MODEL", "m")

    fake_client = mock.MagicMock()
    fake_client.chat.completions.create.side_effect = RuntimeError("429 rate limit")

    with mock.patch("assistant.llm.groq_provider.OpenAI", return_value=fake_client):
        llm = GroqLLM()
        out = llm.chat("привет")

    assert "лимит" in out.lower()


def test_auth_error_classified(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake-groq-key")
    monkeypatch.setenv("GROQ_MODEL", "m")

    fake_client = mock.MagicMock()
    fake_client.chat.completions.create.side_effect = RuntimeError("401 unauthorized")

    with mock.patch("assistant.llm.groq_provider.OpenAI", return_value=fake_client):
        llm = GroqLLM()
        out = llm.chat("привет")

    assert "авторизац" in out.lower() or "ключ" in out.lower()


def test_server_error_classified(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake-groq-key")
    monkeypatch.setenv("GROQ_MODEL", "m")

    fake_client = mock.MagicMock()
    fake_client.chat.completions.create.side_effect = RuntimeError("500 internal")

    with mock.patch("assistant.llm.groq_provider.OpenAI", return_value=fake_client):
        llm = GroqLLM()
        out = llm.chat("привет")

    assert "ошибка запроса" in out.lower() or "500" in out


def test_empty_response_classified(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake-groq-key")
    monkeypatch.setenv("GROQ_MODEL", "m")

    fake_client = mock.MagicMock()
    fake_client.chat.completions.create.return_value = _fake_response("")

    with mock.patch("assistant.llm.groq_provider.OpenAI", return_value=fake_client):
        llm = GroqLLM()
        out = llm.chat("привет")

    assert "пустой" in out.lower()


def test_empty_user_message(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake-groq-key")
    monkeypatch.setenv("GROQ_MODEL", "m")

    fake_client = mock.MagicMock()
    with mock.patch("assistant.llm.groq_provider.OpenAI", return_value=fake_client):
        llm = GroqLLM()
        out = llm.chat("")
    assert "пустой запрос" in out.lower()


def run_all():
    tests = [
        test_no_key_does_not_create_client,
        test_no_model_does_not_create_client,
        test_client_created_with_key_and_model,
        test_success_response,
        test_timeout_classified,
        test_network_error_classified,
        test_rate_limit_classified,
        test_auth_error_classified,
        test_server_error_classified,
        test_empty_response_classified,
        test_empty_user_message,
    ]
    failed = 0
    for t in tests:
        try:
            # monkeypatch недоступен в direct-run, эмулируем
            t(_DirectMonkey())
            print(f"[OK] {t.__name__}", flush=True)
        except AssertionError as e:
            failed += 1
            print(f"[FAIL] {t.__name__}: {e}", flush=True)
        except Exception as e:
            failed += 1
            print(f"[ERROR] {t.__name__}: {type(e).__name__}: {e}", flush=True)
    print()
    print(f"=== {len(tests) - failed}/{len(tests)} GROQ TESTS PASSED ===", flush=True)
    return failed


class _DirectMonkey:
    def setenv(self, k, v):
        os.environ[k] = v

    def delenv(self, k, raising=True):
        if k in os.environ:
            del os.environ[k]


def main():
    if not os.path.exists("assistant"):
        print("Запускать из корня проекта.", flush=True)
        sys.exit(2)
    sys.exit(1 if run_all() else 0)


if __name__ == "__main__":
    main()
