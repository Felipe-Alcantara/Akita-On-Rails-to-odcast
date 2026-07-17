"""Ponte JSON do Audiofy: cada comando imprime um único JSON no stdout.

É a interface programática usada pelo app Electron e por automações:

    python3 -m audiofy.bridge sources
    python3 -m audiofy.bridge sync <fonte>
    python3 -m audiofy.bridge items <fonte>
    python3 -m audiofy.bridge search <fonte> <termos…>
    python3 -m audiofy.bridge item <fonte> <item-id>
    python3 -m audiofy.bridge generate <fonte> <item-id>   # inicia em segundo plano
    python3 -m audiofy.bridge run-generation <fonte> <item-id>  # uso interno
    python3 -m audiofy.bridge status [<item-id>]
    python3 -m audiofy.bridge abort <item-id>
    python3 -m audiofy.bridge tts-catalog
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from .config import EPISODES_DIR, Settings
from .pipeline import episode_dir, generate_episode
from .runtime.status import GenerationTracker
from .sources import available_sources, get_source


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _episode_summary(directory: Path) -> dict:
    status = GenerationTracker.load(directory) or {}
    return {
        "dir": str(directory),
        "episode_id": status.get("episode_id", directory.name.replace("__", "/")),
        "state": status.get("state", "desconhecido"),
        "stage": status.get("stage", ""),
        "progress": status.get("progress", {}),
        "cost_usd": status.get("cost_usd", 0.0),
        "updated_at": status.get("updated_at"),
        "mp3": str(directory / "episode.mp3") if (directory / "episode.mp3").is_file() else None,
    }


def _cmd_sources() -> dict:
    return {"sources": [
        {"key": s.key, "name": s.name, "description": s.description, "ready": s.is_ready()}
        for s in available_sources()
    ]}


def _cmd_items(source_key: str) -> dict:
    return {"items": [asdict(i) for i in get_source(source_key).list_items()]}


def _cmd_search(source_key: str, query: str) -> dict:
    return {"items": [asdict(i) for i in get_source(source_key).search(query)]}


def _cmd_item(source_key: str, item_id: str) -> dict:
    item = get_source(source_key).get_item(item_id)
    payload = asdict(item)
    payload.pop("text")  # o texto integral não interessa à interface
    payload["estimated_cost_usd"] = round(0.60 * item.words / 2200, 2)  # razão do piloto real
    return payload


def _cmd_generate(source_key: str, item_id: str) -> dict:
    directory = episode_dir(item_id)
    status = GenerationTracker.load(directory)
    if status and status.get("state") == "rodando":
        return {"started": False, "reason": "geração já em andamento", "dir": str(directory)}
    directory.mkdir(parents=True, exist_ok=True)
    log = (directory / "generation.log").open("a", encoding="utf-8")
    subprocess.Popen(
        [sys.executable, "-m", "audiofy.bridge", "run-generation", source_key, item_id],
        cwd=str(Path(__file__).resolve().parents[2]),
        stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        env={**__import__("os").environ, "PYTHONPATH": "src"},
    )
    return {"started": True, "dir": str(directory), "log": str(directory / "generation.log")}


def _cmd_run_generation(source_key: str, item_id: str) -> dict:
    settings = Settings()
    item = get_source(source_key).get_item(item_id)
    final = generate_episode(settings, item)
    return {"mp3": str(final)}


def _cmd_status(item_id: str | None) -> dict:
    if item_id:
        return _episode_summary(episode_dir(item_id))
    episodes = []
    if EPISODES_DIR.is_dir():
        for directory in sorted(EPISODES_DIR.iterdir()):
            if directory.is_dir():
                episodes.append(_episode_summary(directory))
    running = [e for e in episodes if e["state"] == "rodando"]
    return {"episodes": episodes, "running": running, "anything_running": bool(running)}


def _cmd_abort(item_id: str) -> dict:
    directory = episode_dir(item_id)
    status = GenerationTracker.load(directory)
    if not status or status.get("state") != "rodando":
        return {"aborted": False, "reason": "nenhuma geração rodando para este item"}
    GenerationTracker.request_abort(directory)
    return {"aborted": True, "note": "abort é cooperativo; efetiva no próximo segmento"}


def _cmd_tts_catalog() -> dict:
    from .providers.openrouter import GEMINI_VOICES, list_tts_models
    return {
        "models": list_tts_models(Settings()),
        "gemini_voices": GEMINI_VOICES,
    }


def main() -> None:
    args = sys.argv[1:]
    try:
        if not args:
            raise ValueError(__doc__)
        command, rest = args[0], args[1:]
        if command == "sources":
            result = _cmd_sources()
        elif command == "sync" and rest:
            result = {"version": get_source(rest[0]).sync()}
        elif command == "items" and rest:
            result = _cmd_items(rest[0])
        elif command == "search" and len(rest) >= 2:
            result = _cmd_search(rest[0], " ".join(rest[1:]))
        elif command == "item" and len(rest) >= 2:
            result = _cmd_item(rest[0], rest[1])
        elif command == "generate" and len(rest) >= 2:
            result = _cmd_generate(rest[0], rest[1])
        elif command == "run-generation" and len(rest) >= 2:
            result = _cmd_run_generation(rest[0], rest[1])
        elif command == "status":
            result = _cmd_status(rest[0] if rest else None)
        elif command == "abort" and rest:
            result = _cmd_abort(rest[0])
        elif command == "tts-catalog":
            result = _cmd_tts_catalog()
        else:
            raise ValueError(f"Comando inválido: {' '.join(args)}\n{__doc__}")
        _emit({"ok": True, **result})
    except Exception as error:  # noqa: BLE001 — contrato JSON: erro vira payload
        _emit({"ok": False, "error": str(error)})
        sys.exit(1)


if __name__ == "__main__":
    main()
