"""M1 has no LLM anywhere: not in dependencies, the lock file, or imports."""

from __future__ import annotations

import re
import tomllib

from tests.conftest import ROOT

FORBIDDEN = ["openai", "anthropic", "ollama", "transformers", "langchain", "llama_cpp", "llama-cpp-python",
             "google-generativeai", "google-genai", "cohere", "mistralai", "groq", "litellm", "huggingface-hub",
             "huggingface_hub", "torch", "vllm"]


def _name(req: str) -> str:
    return re.split(r"[<>=!~\[; ]", req, maxsplit=1)[0].lower().replace("_", "-")


def test_no_model_clients_in_dependencies() -> None:
    py = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    reqs = list(py["project"]["dependencies"])
    for group in py["project"].get("optional-dependencies", {}).values():
        reqs += group
    for group in py.get("dependency-groups", {}).values():
        reqs += [r for r in group if isinstance(r, str)]
    names = {_name(r) for r in reqs}
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    locked = set(re.findall(r'^name = "([^"]+)"', lock, re.M))
    for bad in FORBIDDEN:
        b = bad.lower().replace("_", "-")
        assert b not in names, bad
        assert b not in locked, bad
    pkg = (ROOT / "client" / "package.json")
    if pkg.exists():
        text = pkg.read_text(encoding="utf-8").lower()
        for bad in ("openai", "anthropic", "langchain", "ollama", "@google/generative-ai"):
            assert f'"{bad}' not in text, bad


def test_no_model_imports() -> None:
    pat = re.compile(rf"^\s*(?:import|from)\s+({'|'.join(re.escape(f) for f in FORBIDDEN)})\b", re.M)
    for folder in ("server", "scripts", "tests"):
        for f in (ROOT / folder).rglob("*.py"):
            if f.name == "test_no_llm.py":
                continue
            assert not pat.search(f.read_text(encoding="utf-8")), f
    assert not (ROOT / "server" / "kohra" / "llm.py").exists()
