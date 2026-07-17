"""Ponte JSON do Audiofy: cada comando imprime um único JSON no stdout.

É a interface programática usada pelo app Electron e por automações:

    python3 -m audiofy.bridge sources
    python3 -m audiofy.bridge sync <fonte>
    python3 -m audiofy.bridge items <fonte>
    python3 -m audiofy.bridge search <fonte> <termos…>
    python3 -m audiofy.bridge item <fonte> <item-id>
    python3 -m audiofy.bridge generate <fonte> <item-id> [--force]
    python3 -m audiofy.bridge run-generation <fonte> <item-id> [--force]  # uso interno
    python3 -m audiofy.bridge status [<item-id>]
    python3 -m audiofy.bridge abort <item-id>
    python3 -m audiofy.bridge tts-catalog
    python3 -m audiofy.bridge setup-check|setup-install
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from .config import EPISODES_DIR, Settings
from .runtime.status import GenerationTracker
from .sources import available_sources, get_source


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _episode_dir(item_id: str) -> Path:
    # Import tardio: o setup precisa funcionar mesmo se ``requests`` ainda faltar.
    from .pipeline import episode_dir
    return episode_dir(item_id)


def _episode_summary(directory: Path) -> dict:
    status = GenerationTracker.load(directory) or {}
    completed_mp3 = directory / "episode.mp3"
    return {
        "dir": str(directory),
        "episode_id": status.get("episode_id", directory.name.replace("__", "/")),
        "state": status.get("state", "desconhecido"),
        "stage": status.get("stage", ""),
        "progress": status.get("progress", {}),
        "cost_usd": status.get("cost_usd", 0.0),
        "cost_exact": status.get("cost_exact", False),
        "retry": status.get("retry"),
        "last_error": status.get("last_error"),
        "resume_count": status.get("resume_count", 0),
        "updated_at": status.get("updated_at"),
        "mp3": (str(completed_mp3)
                if status.get("state") == "concluido" and completed_mp3.is_file()
                else None),
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
    from .estimates import estimate_episode, read_episode_metrics
    item = get_source(source_key).get_item(item_id)
    settings = Settings()
    estimate = estimate_episode(
        item.words, settings.tts_model, profile_name=settings.profile_name
    )
    payload = asdict(item)
    payload.pop("text")  # o texto integral não interessa à interface
    payload["estimated_cost_usd"] = round(estimate.cost_usd, 2)
    payload["estimate"] = asdict(estimate)
    metrics = read_episode_metrics(_episode_dir(item_id))
    payload["actual"] = asdict(metrics) if metrics else None
    return payload


def _cmd_generate(source_key: str, item_id: str, force: bool = False) -> dict:
    directory = _episode_dir(item_id)
    status = GenerationTracker.load(directory)
    if status and status.get("state") == "rodando":
        return {"started": False, "reason": "geração já em andamento", "dir": str(directory)}
    Settings().require_api_key()
    directory.mkdir(parents=True, exist_ok=True)
    GenerationTracker.mark_starting(directory, item_id, resume=not force)
    child_args = [
        sys.executable, "-m", "audiofy.bridge", "run-generation", source_key, item_id,
    ]
    if force:
        child_args.append("--force")
    try:
        with (directory / "generation.log").open("a", encoding="utf-8") as log:
            subprocess.Popen(
                child_args,
                cwd=str(Path(__file__).resolve().parents[2]),
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                env={**__import__("os").environ, "PYTHONPATH": "src"},
            )
    except OSError as error:
        detail = f"Não foi possível iniciar o worker de geração: {error}"
        GenerationTracker.mark_launch_failed(directory, detail)
        raise RuntimeError(detail) from error
    return {"started": True, "force": force, "dir": str(directory),
            "log": str(directory / "generation.log")}


def _cmd_run_generation(source_key: str, item_id: str, force: bool = False) -> dict:
    from .pipeline import generate_episode
    settings = Settings()
    item = get_source(source_key).get_item(item_id)
    final = generate_episode(settings, item, force=force)
    return {"mp3": str(final)}


def _cmd_status(item_id: str | None) -> dict:
    if item_id:
        return _episode_summary(_episode_dir(item_id))
    episodes = []
    if EPISODES_DIR.is_dir():
        for directory in sorted(EPISODES_DIR.iterdir()):
            if directory.is_dir():
                episodes.append(_episode_summary(directory))
    running = [e for e in episodes if e["state"] == "rodando"]
    return {"episodes": episodes, "running": running, "anything_running": bool(running)}


def _cmd_abort(item_id: str) -> dict:
    directory = _episode_dir(item_id)
    status = GenerationTracker.load(directory)
    if not status or status.get("state") != "rodando":
        return {"aborted": False, "reason": "nenhuma geração rodando para este item"}
    GenerationTracker.request_abort(directory)
    return {"aborted": True, "note": "abort é cooperativo; efetiva no próximo segmento"}


def _cmd_settings_info() -> dict:
    """Resumo de configuração para a interface: perfil, provedor, CLIs, apresentadores."""
    import os
    from .config import api_key_source
    from .providers.subscription import SUBSCRIPTION_CLIS, configured_model
    settings = Settings()
    overrides = [
        name for name in (
            "AUDIOFY_TEXT_PROVIDER", "AUDIOFY_TEXT_MODEL", "AUDIOFY_AUDIT_MODEL",
            "AUDIOFY_TTS_MODEL", "AUDIOFY_PRESENTERS",
        )
        if os.environ.get(name)
    ]
    return {
        "profile": settings.profile_name,
        "text_provider": settings.text_provider or "openrouter",
        "subscription_model": configured_model(settings.text_provider),
        "text_model": settings.text_model,
        "audit_model": settings.audit_model,
        "tts_model": settings.tts_model,
        "presenters": [
            {"speaker": p.speaker, "voice": p.voice, "style": p.style}
            for p in settings.presenters
        ],
        "has_key": bool(settings.api_key),
        "key_source": api_key_source(),
        "overrides": overrides,
        "subscription_clis": [
            {"key": c.key, "name": c.name, "available": c.is_available(),
             "configured_model": configured_model(c.key)}
            for c in SUBSCRIPTION_CLIS
        ],
    }


def _cmd_models_list(force_refresh: bool = False) -> dict:
    """Modelos de texto e de TTS com preços, para os seletores da interface."""
    from .catalog import load_models
    from .providers.openrouter import GEMINI_VOICES, list_tts_models
    try:
        models = load_models(Settings(), force_refresh)
        errors = []
    except Exception as exception:  # catálogo é auxiliar; formulário aceita valores atuais
        models = []
        errors = [str(exception)]

    def payload(model) -> dict:
        return {"id": model.id, "name": model.name, "vendor": model.vendor,
                "price_line": model.price_line}

    try:
        tts_models = []
        for model in list_tts_models(Settings()):
            prompt = float(model.get("prompt_price", 0) or 0) * 1_000_000
            completion = float(model.get("completion_price", 0) or 0) * 1_000_000
            model_id = model.get("id", "")
            tts_models.append({
                "id": model_id,
                "name": model.get("name", ""),
                "vendor": model_id.split("/", 1)[0],
                "price_line": (f"US$ {prompt:.2f}/M entrada · "
                               f"US$ {completion:.2f}/M saída"),
            })
    except Exception as exception:
        tts_models = [payload(model) for model in models
                      if {"audio", "speech"} & set(model.output_modalities)]
        errors.append(str(exception))

    return {
        "text_models": [payload(model) for model in models
                        if "text" in model.output_modalities],
        "tts_models": tts_models,
        "gemini_voices": GEMINI_VOICES,
        "catalog_error": " | ".join(dict.fromkeys(errors)) if errors else None,
    }


def _cmd_setup_check() -> dict:
    from .setup import setup_report
    return setup_report()


def _cmd_tts_catalog() -> dict:
    from .providers.openrouter import GEMINI_VOICES, list_tts_models
    try:
        models = list_tts_models(Settings())
        error = None
    except Exception as exception:  # as vozes locais continuam úteis sem chave/rede
        models = []
        error = str(exception)
    return {
        "models": models,
        "gemini_voices": GEMINI_VOICES,
        "catalog_error": error,
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
            result = _cmd_generate(rest[0], rest[1], force="--force" in rest[2:])
        elif command == "run-generation" and len(rest) >= 2:
            result = _cmd_run_generation(rest[0], rest[1], force="--force" in rest[2:])
        elif command == "status":
            result = _cmd_status(rest[0] if rest else None)
        elif command == "abort" and rest:
            result = _cmd_abort(rest[0])
        elif command == "tts-catalog":
            result = _cmd_tts_catalog()
        elif command == "notebooklm" and len(rest) >= 2:
            from .export import export_notebooklm_pack
            item = get_source(rest[0]).get_item(rest[1])
            result = {"pack": str(export_notebooklm_pack(item))}
        elif command == "add-url" and rest:
            from .sources.custom import CustomSource
            item_id = CustomSource().add_url(rest[0])
            result = {"item_id": item_id, "source": "custom"}
        elif command == "add-text":
            from .sources.custom import CustomSource
            payload = json.loads(sys.stdin.read())
            item_id = CustomSource().add_text(
                payload["title"], payload["text"], payload.get("url", ""))
            result = {"item_id": item_id, "source": "custom"}
        elif command == "chat":
            from .chat import ChatSession
            message = sys.stdin.read().strip()
            if not message:
                raise ValueError("mensagem vazia (envie pelo stdin)")
            session = ChatSession(rest[0] if rest else "principal")
            text, actions = session.send(message, Settings())
            result = {"reply": text, "actions": actions}
        elif command == "chat-history":
            from .chat import ChatSession
            result = {
                "messages": ChatSession(rest[0] if rest else "principal").messages,
                "sources": _cmd_sources()["sources"],
            }
        elif command == "chat-clear":
            from .chat import ChatSession
            ChatSession(rest[0] if rest else "principal").clear()
            result = {"cleared": True}
        elif command == "settings-info":
            result = _cmd_settings_info()
        elif command == "keys-list":
            from .config import key_store
            store = key_store()
            result = {"active": store.active_name(),
                      "keys": [{"name": k.name, "masked": k.masked}
                               for k in store.list_keys()]}
        elif command == "keys-add" and rest:
            from .config import key_store
            key_store().add(rest[0], sys.stdin.read().strip())
            result = {"added": rest[0]}
        elif command == "keys-activate" and rest:
            from .config import key_store
            key_store().set_active(rest[0])
            result = {"active": rest[0]}
        elif command == "keys-remove" and rest:
            from .config import key_store
            key_store().remove(rest[0])
            result = {"removed": rest[0]}
        elif command == "balance":
            from .providers.openrouter import check_api_key
            ok_flag, detail = check_api_key(Settings())
            result = {"valid": ok_flag, "detail": detail}
        elif command == "profiles-list":
            from dataclasses import asdict as _asdict
            from .config import profile_store
            store = profile_store()
            result = {"active": store.active().name,
                      "profiles": [{**_asdict(p), "custom": store.is_custom(p.name)}
                                   for p in store.list_profiles()]}
        elif command == "profiles-activate" and rest:
            from .config import profile_store
            profile_store().set_active(rest[0])
            result = {"active": rest[0]}
        elif command == "profiles-save":
            from .config import profile_store
            from .profiles import profile_from_payload
            payload = json.loads(sys.stdin.read())
            profile = profile_from_payload(payload)
            store = profile_store()
            store.save(profile)
            if payload.get("activate"):
                store.set_active(profile.name)
            result = {"saved": profile.name}
        elif command == "profiles-remove" and rest:
            from .config import profile_store
            profile_store().remove(rest[0])
            result = {"removed": rest[0]}
        elif command == "models-list":
            result = _cmd_models_list("--refresh" in rest)
        elif command == "setup-check":
            result = _cmd_setup_check()
        elif command == "setup-install":
            from .setup import apply_setup
            result = apply_setup()
        else:
            raise ValueError(f"Comando inválido: {' '.join(args)}\n{__doc__}")
        _emit({"ok": True, **result})
    except Exception as error:  # noqa: BLE001 — contrato JSON: erro vira payload
        _emit({"ok": False, "error": str(error)})
        sys.exit(1)


if __name__ == "__main__":
    main()
