"""Ponte JSON do Audiofy: cada comando imprime um único JSON no stdout.

É a interface programática usada pelo app Electron e por automações:

    python3 -m audiofy.bridge sources
    python3 -m audiofy.bridge sync <fonte>
    python3 -m audiofy.bridge items <fonte>
    python3 -m audiofy.bridge search <fonte> <termos…>
    python3 -m audiofy.bridge item <fonte> <item-id>
    python3 -m audiofy.bridge generate <fonte> <item-id> [--force]
        [--mode=adaptation|verbatim|reflexive] [--voice=<voz>]
        [--background-music=<arquivo>] [--background-volume=0.01..0.25]
    python3 -m audiofy.bridge run-generation <fonte> <item-id> [opções]  # uso interno
    python3 -m audiofy.bridge repair <fonte> <item-id>
    python3 -m audiofy.bridge run-repair <fonte> <item-id> [opções]     # uso interno
    python3 -m audiofy.bridge status [<item-id>]
    python3 -m audiofy.bridge generation-log <item-id>
    python3 -m audiofy.bridge audio-chunks <item-id>
    python3 -m audiofy.bridge abort <item-id>
    python3 -m audiofy.bridge tts-catalog
    python3 -m audiofy.bridge add-file <caminho-do-arquivo>
    python3 -m audiofy.bridge setup-check|setup-install
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .artifacts import resolve_final_audio
from .config import EPISODES_DIR, PROJECT_ROOT, STATE_DIR, Settings, api_key_source
from .runtime.status import GenerationTracker
from .sources import available_sources, get_source

_MAX_GENERATION_LOG_BYTES = 64 * 1024
_MAX_GENERATION_LOG_LINES = 160
_LOG_SECRET_PATTERNS = (
    re.compile(r"sk-or-v1-[A-Za-z0-9_-]+"),
    re.compile(r"AIza[0-9A-Za-z_-]+"),
    re.compile(r"(?i)(?:OPENROUTER_API_KEY\s*=\s*|Authorization:\s*Bearer\s+)\S+"),
)
_BACKGROUND_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
_MAX_BACKGROUND_AUDIO_BYTES = 500 * 1024 * 1024


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _episode_dir(item_id: str, language: str = "") -> Path:
    # Import tardio: o setup precisa funcionar mesmo se ``requests`` ainda faltar.
    from .pipeline import episode_dir

    if not language:
        from .config import profile_store

        language = profile_store().active().language
    return episode_dir(item_id, language)


def _episode_summary(directory: Path) -> dict:
    # reconcile: um "rodando" cujo worker morreu vira "falhou" em vez de
    # ficar pendurado para sempre na interface.
    status = GenerationTracker.reconcile(directory) or {}
    from .audio_audit import read_audio_audit
    from .estimates import read_episode_metrics

    audio_audit = read_audio_audit(directory)
    metrics = read_episode_metrics(directory)
    metrics_data = asdict(metrics) if metrics else {}
    completed_mp3 = resolve_final_audio(directory, metrics_data.get("final_audio_file"))
    episode_id = status.get("episode_id", directory.name.replace("__", "/"))
    title = str(metrics_data.get("title") or "").strip()
    notes = directory / "NOTES.md"
    if not title and notes.is_file():
        try:
            first_line = notes.read_text(encoding="utf-8").splitlines()[0]
            title = first_line.removeprefix("# ").strip()
        except (IndexError, OSError, UnicodeError):
            pass
    title = title or episode_id
    source_created_at = str(metrics_data.get("source_created_at") or "")
    if not source_created_at:
        created_match = re.match(r"^(\d{4}-\d{2}-\d{2})", episode_id)
        source_created_at = created_match.group(1) if created_match else ""
    file_stat = completed_mp3.stat() if completed_mp3 else None
    file_updated_at = (
        datetime.fromtimestamp(file_stat.st_mtime).astimezone().isoformat(timespec="seconds")
        if file_stat
        else None
    )
    state = status.get("state") or ("concluido" if file_stat else "desconhecido")
    cost_usd = status.get("cost_usd")
    if cost_usd is None or (not cost_usd and state == "concluido"):
        cost_usd = metrics_data.get("cost_usd", 0.0)
    cost_exact = (
        status.get("cost_exact")
        if "cost_exact" in status
        else metrics_data.get("cost_exact", False)
    )
    return {
        "dir": str(directory),
        "episode_id": episode_id,
        "title": title,
        "state": state,
        "stage": status.get("stage", ""),
        "progress": status.get("progress", {}),
        "cost_usd": cost_usd,
        "cost_exact": cost_exact,
        "retry": status.get("retry"),
        "abort_requested_at": status.get("abort_requested_at"),
        "last_error": status.get("last_error"),
        "resume_count": status.get("resume_count", 0),
        "generation_mode": status.get(
            "generation_mode", metrics_data.get("generation_mode", "adaptation")
        ),
        "narration_voice": status.get("narration_voice"),
        "key_source": status.get("key_source"),
        "background_music": status.get("background_music"),
        "background_music_cache": status.get("background_music_cache"),
        "background_volume": status.get("background_volume"),
        "audio_audit": audio_audit.get("summary") if audio_audit else None,
        "source_created_at": source_created_at or None,
        "generated_at": metrics_data.get("generated_at") or file_updated_at,
        "file_updated_at": file_updated_at,
        "file_name": completed_mp3.name if completed_mp3 else None,
        "file_size_bytes": file_stat.st_size if file_stat else None,
        "duration_seconds": metrics_data.get("duration_seconds"),
        "source_words": metrics_data.get("source_words"),
        "script_words": metrics_data.get("script_words"),
        "source_key": metrics_data.get("source_key") or None,
        "source_file": metrics_data.get("source_file") or None,
        "artifact_schema_version": metrics_data.get("artifact_schema_version", 1),
        "profile_name": metrics_data.get("profile_name"),
        "tts_model": metrics_data.get("tts_model"),
        "verified_at": metrics_data.get("verified_at") or None,
        "updated_at": status.get("updated_at") or file_updated_at,
        "mp3": (str(completed_mp3) if completed_mp3 and status.get("state") != "rodando" else None),
        "language": "en" if directory.name.endswith("__en") else "pt-BR",
    }


def _sanitize_generation_log(text: str) -> str:
    for pattern in _LOG_SECRET_PATTERNS:
        text = pattern.sub("[SEGREDO PROTEGIDO]", text)
    return text


def _cmd_generation_log(item_id: str, language: str = "") -> dict:
    """Retorna somente a cauda segura do log, sem carregar um arquivo ilimitado."""
    directory = _episode_dir(item_id, language)
    path = directory / "generation.log"
    status = GenerationTracker.load(directory) or {}
    pid = status.get("pid")
    worker_alive = False
    if status.get("state") == "rodando" and isinstance(pid, int):
        from .runtime.process import pid_alive

        worker_alive = pid_alive(pid)
    if not path.is_file():
        return {
            "exists": False,
            "text": "",
            "truncated": False,
            "updated_at": None,
            "worker_alive": worker_alive,
        }

    size = path.stat().st_size
    offset = max(0, size - _MAX_GENERATION_LOG_BYTES)
    with path.open("rb") as source:
        source.seek(offset)
        raw = source.read(_MAX_GENERATION_LOG_BYTES)
    if offset and b"\n" in raw:
        raw = raw.partition(b"\n")[2]
    decoded = raw.decode("utf-8", errors="replace")
    lines = decoded.splitlines()
    line_truncated = len(lines) > _MAX_GENERATION_LOG_LINES
    text = "\n".join(lines[-_MAX_GENERATION_LOG_LINES:])
    return {
        "exists": True,
        "text": _sanitize_generation_log(text),
        "truncated": bool(offset or line_truncated),
        "updated_at": path.stat().st_mtime,
        "worker_alive": worker_alive,
    }


def _cmd_audio_chunks(item_id: str, language: str = "") -> dict:
    """Lista somente chunks confinados ao episódio e seus achados de auditoria."""
    from .audio_audit import read_audio_audit

    directory = _episode_dir(item_id, language)
    segments_directory = directory / "segments"
    audit = read_audio_audit(directory)
    manifest = {}
    manifest_path = directory / "segments.json"
    if manifest_path.is_file():
        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = loaded if isinstance(loaded, dict) else {}
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass
    segment_metadata = manifest.get("segments", {})
    if not isinstance(segment_metadata, dict):
        segment_metadata = {}
    findings = {
        segment.get("file"): segment
        for segment in (audit or {}).get("segments", [])
        if isinstance(segment, dict) and isinstance(segment.get("file"), str)
    }
    chunks = []
    if segments_directory.is_dir():
        for path in sorted(segments_directory.iterdir()):
            if not path.is_file() or path.suffix.lower() not in {".wav", ".mp3", ".m4a", ".flac"}:
                continue
            finding = findings.get(path.name, {})
            metadata = segment_metadata.get(path.name, {})
            if not isinstance(metadata, dict):
                metadata = {}
            chunks.append(
                {
                    "file": path.name,
                    "path": str(path),
                    "kind": metadata.get("kind", "chunk"),
                    "chunk_index": metadata.get("chunk_index"),
                    "chunk_total": metadata.get("chunk_total"),
                    "speaker": metadata.get("speaker"),
                    "duration_seconds": finding.get("duration_seconds"),
                    "severity": finding.get("severity", "unknown"),
                    "longest_silence_seconds": finding.get("longest_silence_seconds"),
                    "silence_ratio": finding.get("silence_ratio"),
                    "silences": finding.get("silences", []),
                }
            )
    return {
        "chunks": chunks,
        "audit": audit.get("summary") if audit else None,
        "audited_at": audit.get("audited_at") if audit else None,
        "source_key": manifest.get("source_key"),
        "generation_mode": manifest.get("generation_mode"),
    }


def _cmd_sources() -> dict:
    return {
        "sources": [
            {"key": s.key, "name": s.name, "description": s.description, "ready": s.is_ready()}
            for s in available_sources()
        ]
    }


def _cmd_items(source_key: str) -> dict:
    return {"items": [asdict(i) for i in get_source(source_key).list_items()]}


def _cmd_search(source_key: str, query: str) -> dict:
    return {"items": [asdict(i) for i in get_source(source_key).search(query)]}


def _cmd_item(source_key: str, item_id: str) -> dict:
    from .estimates import estimate_episode, read_episode_metrics

    item = get_source(source_key).get_item(item_id)
    settings = Settings()
    estimates = {
        mode: estimate_episode(
            item.words,
            settings.tts_model,
            generation_mode=mode,
        )
        for mode in ("adaptation", "verbatim", "reflexive")
    }
    estimate = estimates["adaptation"]
    payload = asdict(item)
    payload.pop("text")  # o texto integral não interessa à interface
    payload["estimated_cost_usd"] = round(estimate.cost_usd, 2)
    payload["estimate"] = asdict(estimate)
    payload["estimates"] = {mode: asdict(value) for mode, value in estimates.items()}
    metrics = read_episode_metrics(_episode_dir(item_id))
    payload["actual"] = asdict(metrics) if metrics else None
    return payload


def _validate_generation_options(
    generation_mode: str, narration_voice: str | None
) -> tuple[str, str | None]:
    if generation_mode not in {"adaptation", "verbatim", "reflexive"}:
        raise ValueError(f"Modo de geração desconhecido: {generation_mode}")
    if generation_mode == "adaptation":
        return generation_mode, None
    from .providers.openrouter import GEMINI_VOICES

    if narration_voice not in GEMINI_VOICES:
        raise ValueError("Escolha uma voz de narrador disponível no catálogo Gemini.")
    return generation_mode, narration_voice


def _cache_background_music(value: str) -> tuple[str, str]:
    """Valida e copia música externa para cache privado, retornando caminho relativo e nome."""
    source = Path(value).expanduser().resolve(strict=True)
    if not source.is_file() or source.suffix.lower() not in _BACKGROUND_AUDIO_EXTENSIONS:
        raise ValueError("Escolha um arquivo de áudio MP3, WAV, M4A, AAC, FLAC ou OGG.")
    if source.stat().st_size > _MAX_BACKGROUND_AUDIO_BYTES:
        raise ValueError("A música de fundo excede o limite de 500 MiB.")
    digest = hashlib.sha256()
    with source.open("rb") as audio:
        for block in iter(lambda: audio.read(1024 * 1024), b""):
            digest.update(block)
    cache_directory = STATE_DIR / "music"
    cache_directory.mkdir(parents=True, exist_ok=True)
    target = cache_directory / f"{digest.hexdigest()}{source.suffix.lower()}"
    if source != target and (
        not target.is_file() or target.stat().st_size != source.stat().st_size
    ):
        temporary = target.with_suffix(f"{target.suffix}.{os.getpid()}.tmp")
        try:
            shutil.copyfile(source, temporary)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    return target.relative_to(PROJECT_ROOT).as_posix(), source.name


def _cached_background_path(value: str) -> Path:
    """Aceita no worker apenas um arquivo previamente copiado para o cache privado."""
    cache_directory = (STATE_DIR / "music").resolve()
    candidate = (PROJECT_ROOT / value).resolve()
    if (
        candidate.parent != cache_directory
        or candidate.suffix.lower() not in _BACKGROUND_AUDIO_EXTENSIONS
        or not candidate.is_file()
    ):
        raise ValueError("A música do worker precisa vir do cache privado do Audiofy.")
    return candidate


def _background_volume(value: str | float) -> float:
    try:
        volume = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("O volume da música precisa ser numérico.") from error
    if not 0.01 <= volume <= 0.25:
        raise ValueError("O volume da música precisa ficar entre 1% e 25%.")
    return volume


def _generation_options(
    arguments: list[str],
) -> tuple[bool, str, str | None, str | None, float, str]:
    force = False
    generation_mode = "adaptation"
    narration_voice = None
    background_music = None
    background_volume = 0.08
    language = "pt-BR"
    for argument in arguments:
        if argument == "--force":
            force = True
        elif argument.startswith("--mode="):
            generation_mode = argument.partition("=")[2]
        elif argument.startswith("--voice="):
            narration_voice = argument.partition("=")[2]
        elif argument.startswith("--background-music="):
            background_music = argument.partition("=")[2]
        elif argument.startswith("--background-volume="):
            background_volume = _background_volume(argument.partition("=")[2])
        elif argument.startswith("--language="):
            from .languages import is_supported

            language = argument.partition("=")[2]
            if not is_supported(language):
                raise ValueError(f"Idioma desconhecido: {language}")
        else:
            raise ValueError(f"Opção de geração desconhecida: {argument}")
    mode, voice = _validate_generation_options(generation_mode, narration_voice)
    return force, mode, voice, background_music, background_volume, language


def _cmd_generate(
    source_key: str,
    item_id: str,
    force: bool = False,
    generation_mode: str = "adaptation",
    narration_voice: str | None = None,
    background_music: str | None = None,
    background_volume: float = 0.08,
    language: str = "pt-BR",
) -> dict:
    generation_mode, narration_voice = _validate_generation_options(
        generation_mode, narration_voice
    )
    background_volume = _background_volume(background_volume)
    background_cache = None
    background_name = None
    if background_music:
        background_cache, background_name = _cache_background_music(background_music)
    directory = _episode_dir(item_id, language)
    # reconcile: um "rodando" órfão (worker morto) não pode bloquear a nova
    # geração — era isso que fazia todo clique responder "já em andamento".
    status = GenerationTracker.reconcile(directory)
    if status and status.get("state") == "rodando":
        return {"started": False, "reason": "geração já em andamento", "dir": str(directory)}
    previous_mode = status.get("generation_mode", "adaptation") if status else None
    previous_voice = status.get("narration_voice") if status else None
    if status and (
        previous_mode != generation_mode
        or (generation_mode == "verbatim" and previous_voice != narration_voice)
    ):
        # Trocar formato ou voz muda todos os segmentos e precisa reiniciar a contabilidade.
        force = True
    Settings().require_api_key()
    directory.mkdir(parents=True, exist_ok=True)
    GenerationTracker.mark_starting(
        directory,
        item_id,
        resume=not force,
        generation_mode=generation_mode,
        narration_voice=narration_voice,
        key_source=api_key_source(),
        background_music=background_name,
        background_music_cache=background_cache,
        background_volume=background_volume if background_cache else None,
    )
    child_args = [
        sys.executable,
        "-m",
        "audiofy.bridge",
        "run-generation",
        source_key,
        item_id,
    ]
    if force:
        child_args.append("--force")
    child_args.append(f"--mode={generation_mode}")
    if narration_voice:
        child_args.append(f"--voice={narration_voice}")
    if background_cache:
        child_args.append(f"--background-music={background_cache}")
        child_args.append(f"--background-volume={background_volume}")
    if language != "pt-BR":
        child_args.append(f"--language={language}")
    from .runtime.process import launch_detached

    try:
        with (directory / "generation.log").open("a", encoding="utf-8") as log:
            launch_detached(
                child_args,
                cwd=Path(__file__).resolve().parents[2],
                # UTF-8 forçado: no Windows o worker herdaria cp1252 e os prints
                # de progresso (emojis) derrubariam o processo em silêncio.
                env={
                    **os.environ,
                    "PYTHONPATH": "src",
                    "PYTHONUTF8": "1",
                    "PYTHONIOENCODING": "utf-8",
                    # Sem buffer para o painel de log acompanhar cada etapa em tempo real.
                    "PYTHONUNBUFFERED": "1",
                },
                log_handle=log,
            )
    except OSError as error:
        detail = f"Não foi possível iniciar o worker de geração: {error}"
        GenerationTracker.mark_launch_failed(directory, detail)
        raise RuntimeError(detail) from error
    return {
        "started": True,
        "force": force,
        "generation_mode": generation_mode,
        "narration_voice": narration_voice,
        "background_music": background_name,
        "background_volume": background_volume if background_cache else None,
        "dir": str(directory),
        "log": str(directory / "generation.log"),
    }


def _cmd_run_generation(
    source_key: str,
    item_id: str,
    force: bool = False,
    generation_mode: str = "adaptation",
    narration_voice: str | None = None,
    background_music: str | None = None,
    background_volume: float = 0.08,
    language: str = "pt-BR",
) -> dict:
    generation_mode, narration_voice = _validate_generation_options(
        generation_mode, narration_voice
    )
    from .pipeline import generate_episode

    try:
        settings = Settings()
        if language != "pt-BR":
            from dataclasses import replace as _replace_lang

            settings = _replace_lang(settings, language=language)
        if generation_mode in {"verbatim", "reflexive"}:
            from dataclasses import replace

            from .presenters import Presenter
            from .providers.openrouter import GEMINI_VOICES

            settings = replace(
                settings,
                presenters=[
                    Presenter("narrador", narration_voice or "", GEMINI_VOICES[narration_voice])
                ],
            )
        item = get_source(source_key).get_item(item_id)
        final = generate_episode(
            settings,
            item,
            force=force,
            generation_mode=generation_mode,
            narration_voice=narration_voice,
            background_music=(
                _cached_background_path(background_music) if background_music else None
            ),
            background_volume=_background_volume(background_volume),
            source_key=source_key,
        )
    except Exception as error:
        # Falha antes/fora do pipeline (fonte, configuração, imports tardios):
        # sem esta marca o status ficaria "rodando" para sempre.
        directory = _episode_dir(item_id)
        status = GenerationTracker.load(directory) or {}
        if status.get("state") == "rodando":
            GenerationTracker.mark_launch_failed(directory, str(error))
        raise
    return {"mp3": str(final)}


def _cmd_repair(source_key: str, item_id: str, language: str = "") -> dict:
    """Regenera somente segmentos com silêncio problemático (lançador de worker)."""
    from .audio_audit import read_audio_audit

    directory = _episode_dir(item_id, language)
    status = GenerationTracker.reconcile(directory)
    if status and status.get("state") == "rodando":
        return {"started": False, "reason": "geração já em andamento"}

    audit = read_audio_audit(directory)
    if not audit:
        return {
            "started": False,
            "reason": "nenhuma auditoria encontrada — gere o episódio primeiro",
        }
    bad_count = sum(
        1 for seg in audit.get("segments", []) if seg.get("severity") in ("critical", "warning")
    )
    if bad_count == 0:
        return {"started": False, "reason": "nenhum segmento com problema detectado"}

    Settings().require_api_key()

    generation_mode = (status or {}).get("generation_mode", "adaptation")
    narration_voice = (status or {}).get("narration_voice")
    background_cache = (status or {}).get("background_music_cache")
    background_volume = (status or {}).get("background_volume") or 0.08

    GenerationTracker.mark_starting(
        directory,
        item_id,
        resume=True,
        generation_mode=generation_mode,
        narration_voice=narration_voice,
        key_source=api_key_source(),
        background_music=(status or {}).get("background_music"),
        background_music_cache=background_cache,
        background_volume=background_volume,
    )

    child_args = [
        sys.executable,
        "-m",
        "audiofy.bridge",
        "run-repair",
        source_key,
        item_id,
    ]
    if language:
        child_args.append(f"--language={language}")
    if background_cache:
        child_args.append(f"--background-music={background_cache}")
        child_args.append(f"--background-volume={background_volume}")
    from .runtime.process import launch_detached

    try:
        with (directory / "generation.log").open("a", encoding="utf-8") as log:
            launch_detached(
                child_args,
                cwd=Path(__file__).resolve().parents[2],
                env={
                    **os.environ,
                    "PYTHONPATH": "src",
                    "PYTHONUTF8": "1",
                    "PYTHONIOENCODING": "utf-8",
                    "PYTHONUNBUFFERED": "1",
                },
                log_handle=log,
            )
    except OSError as error:
        detail = f"Não foi possível iniciar o worker de reparo: {error}"
        GenerationTracker.mark_launch_failed(directory, detail)
        raise RuntimeError(detail) from error
    return {
        "started": True,
        "segments_to_repair": bad_count,
        "generation_mode": generation_mode,
        "dir": str(directory),
    }


def _cmd_run_repair(
    source_key: str,
    item_id: str,
    background_music: str | None = None,
    background_volume: float = 0.08,
    language: str = "",
) -> dict:
    """Worker de reparo — roda em processo filho."""
    from .pipeline import repair_episode

    try:
        settings = Settings()
        if language:
            from dataclasses import replace as _replace

            settings = _replace(settings, language=language)
        previous = GenerationTracker.load(_episode_dir(item_id, language)) or {}
        generation_mode = previous.get("generation_mode", "adaptation")
        narration_voice = previous.get("narration_voice")
        if generation_mode == "verbatim" and narration_voice:
            from dataclasses import replace

            from .presenters import Presenter
            from .providers.openrouter import GEMINI_VOICES

            settings = replace(
                settings,
                presenters=[
                    Presenter("narrador", narration_voice, GEMINI_VOICES.get(narration_voice, ""))
                ],
            )
        item = get_source(source_key).get_item(item_id)
        final = repair_episode(
            settings,
            item,
            source_key=source_key,
            generation_mode=generation_mode,
            narration_voice=narration_voice,
            background_music=(
                _cached_background_path(background_music) if background_music else None
            ),
            background_volume=_background_volume(background_volume),
        )
    except Exception as error:
        directory = _episode_dir(item_id, language)
        status = GenerationTracker.load(directory) or {}
        if status.get("state") == "rodando":
            GenerationTracker.mark_launch_failed(directory, str(error))
        raise
    return {"mp3": str(final)}


def _cmd_status(item_id: str | None) -> dict:
    if item_id:
        return _episode_summary(_episode_dir(item_id))
    episodes = []
    if EPISODES_DIR.is_dir():
        for directory in sorted(EPISODES_DIR.iterdir(), reverse=True):
            if directory.is_dir():
                episodes.append(_episode_summary(directory))
    running = [e for e in episodes if e["state"] == "rodando"]
    return {"episodes": episodes, "running": running, "anything_running": bool(running)}


def _cmd_abort(item_id: str, language: str = "") -> dict:
    directory = _episode_dir(item_id, language)
    status = GenerationTracker.load(directory)
    if not status or status.get("state") != "rodando":
        return {"aborted": False, "reason": "nenhuma geração rodando para este item"}
    accepted, stopped = GenerationTracker.abort_running(directory)
    return {
        "aborted": accepted,
        "stopped": stopped,
        "note": (
            "worker encerrado; o checkpoint foi preservado"
            if stopped
            else (
                "pedido registrado; aguardando o primeiro checkpoint disponível"
                if accepted
                else "a geração terminou antes do pedido de abort"
            )
        ),
    }


def _cmd_settings_info() -> dict:
    """Resumo de configuração para a interface: perfil, provedor, CLIs, apresentadores."""
    import os

    from .config import api_key_source
    from .languages import LANGUAGES
    from .providers.openrouter import GEMINI_VOICES
    from .providers.subscription import SUBSCRIPTION_CLIS, configured_model

    settings = Settings()
    overrides = [
        name
        for name in (
            "AUDIOFY_TEXT_PROVIDER",
            "AUDIOFY_SUBSCRIPTION_MODEL",
            "AUDIOFY_TEXT_MODEL",
            "AUDIOFY_AUDIT_MODEL",
            "AUDIOFY_TTS_MODEL",
            "AUDIOFY_PRESENTERS",
        )
        if os.environ.get(name)
    ]
    return {
        "profile": settings.profile_name,
        "text_provider": settings.text_provider or "openrouter",
        # O modelo escolhido no perfil vence o que a CLI tem configurado.
        "subscription_model": (
            settings.subscription_model or configured_model(settings.text_provider)
        ),
        "profile_subscription_model": settings.subscription_model,
        "text_model": settings.text_model,
        "audit_model": settings.audit_model,
        "tts_model": settings.tts_model,
        "presenters": [
            {"speaker": p.speaker, "voice": p.voice, "style": p.style} for p in settings.presenters
        ],
        "gemini_voices": GEMINI_VOICES,
        "language": settings.language,
        # Registro único de idiomas: a interface pode montar o seletor a partir daqui
        # em vez de manter os <option> fixos no HTML.
        "languages": [{"code": lang.code, "label": lang.ui_label} for lang in LANGUAGES.values()],
        "has_key": bool(settings.api_key),
        "key_source": api_key_source(),
        "overrides": overrides,
        "subscription_clis": [
            {
                "key": c.key,
                "name": c.name,
                "available": c.is_available(),
                "configured_model": configured_model(c.key),
                "model_suggestions": list(c.model_suggestions),
                "supports_model": bool(c.model_flag),
            }
            for c in SUBSCRIPTION_CLIS
        ],
    }


def _cmd_keys_list() -> dict:
    """Lista somente metadados seguros e identifica a origem realmente usada."""
    from .config import api_key_source, environment_key_source, key_store

    store = key_store()
    environment_source = environment_key_source()
    active_name = store.active_name()
    named_in_use = store.prefers_named() or environment_source is None
    return {
        "count": len(store.list_keys()),
        "active": active_name,
        "effective_source": api_key_source(),
        "environment": {
            "available": environment_source is not None,
            "source": environment_source,
            "in_use": environment_source is not None and not store.prefers_named(),
        },
        "keys": [
            {
                "name": named.name,
                "masked": named.masked,
                "priority": priority,
                "selected": named.name == active_name,
                "in_use": named.name == active_name and named_in_use,
            }
            for priority, named in enumerate(store.list_keys(), start=1)
        ],
    }


def _cmd_check_named_key(name: str) -> dict:
    from .config import key_store
    from .providers.openrouter import check_api_key_value

    available, detail = check_api_key_value(key_store().get(name).key)
    return {"name": name, "available": available, "detail": detail}


def _cmd_check_environment_key() -> dict:
    import os

    from .config import environment_key_source
    from .providers.openrouter import check_api_key_value

    source = environment_key_source()
    if source is None:
        raise RuntimeError("Nenhuma OPENROUTER_API_KEY disponível no ambiente ou .env.")
    available, detail = check_api_key_value(os.environ["OPENROUTER_API_KEY"])
    return {"name": source, "available": available, "detail": detail}


def _cmd_use_named_key(name: str) -> dict:
    from .config import key_store

    key_store().set_active(name)
    return {"active": name}


def _cmd_use_environment_key() -> dict:
    from .config import environment_key_source, key_store

    source = environment_key_source()
    if source is None:
        raise RuntimeError("Nenhuma OPENROUTER_API_KEY disponível no ambiente ou .env.")
    key_store().use_environment()
    return {"active": source}


def _cmd_move_named_key(name: str, direction: str) -> dict:
    from .config import key_store

    key_store().move(name, direction)
    return {"moved": name, "direction": direction}


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
        return {
            "id": model.id,
            "name": model.name,
            "vendor": model.vendor,
            "price_line": model.price_line,
        }

    try:
        tts_models = []
        for model in list_tts_models(Settings()):
            prompt = float(model.get("prompt_price", 0) or 0) * 1_000_000
            completion = float(model.get("completion_price", 0) or 0) * 1_000_000
            model_id = model.get("id", "")
            tts_models.append(
                {
                    "id": model_id,
                    "name": model.get("name", ""),
                    "vendor": model_id.split("/", 1)[0],
                    "price_line": (f"US$ {prompt:.2f}/M entrada · US$ {completion:.2f}/M saída"),
                }
            )
    except Exception as exception:
        tts_models = [
            payload(model) for model in models if {"audio", "speech"} & set(model.output_modalities)
        ]
        errors.append(str(exception))

    return {
        "text_models": [payload(model) for model in models if "text" in model.output_modalities],
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
            force, mode, voice, music, volume, lang = _generation_options(rest[2:])
            result = _cmd_generate(rest[0], rest[1], force, mode, voice, music, volume, lang)
        elif command == "run-generation" and len(rest) >= 2:
            force, mode, voice, music, volume, lang = _generation_options(rest[2:])
            result = _cmd_run_generation(rest[0], rest[1], force, mode, voice, music, volume, lang)
        elif command == "status":
            result = _cmd_status(rest[0] if rest else None)
        elif command == "generation-log" and rest:
            log_lang = ""
            for arg in rest[1:]:
                if arg.startswith("--language="):
                    log_lang = arg.split("=", 1)[1]
            result = _cmd_generation_log(rest[0], log_lang)
        elif command == "repair" and len(rest) >= 2:
            _, _, _, music, volume, repair_lang = _generation_options(rest[2:])
            result = _cmd_repair(rest[0], rest[1], repair_lang)
        elif command == "run-repair" and len(rest) >= 2:
            _, _, _, music, volume, repair_lang = _generation_options(rest[2:])
            result = _cmd_run_repair(rest[0], rest[1], music, volume, repair_lang)
        elif command == "audio-chunks" and rest:
            lang = ""
            for arg in rest[1:]:
                if arg.startswith("--language="):
                    lang = arg.split("=", 1)[1]
            result = _cmd_audio_chunks(rest[0], lang)
        elif command == "abort" and rest:
            abort_lang = ""
            for arg in rest[1:]:
                if arg.startswith("--language="):
                    abort_lang = arg.split("=", 1)[1]
            result = _cmd_abort(rest[0], abort_lang)
        elif command == "tts-catalog":
            result = _cmd_tts_catalog()
        elif command == "notebooklm" and len(rest) >= 2:
            from .export import export_notebooklm_pack

            item = get_source(rest[0]).get_item(rest[1])
            from .config import profile_store as _ps

            result = {"pack": str(export_notebooklm_pack(item, rest[0], _ps().active().language))}
        elif command == "add-url" and rest:
            from .sources.custom import CustomSource

            item_id = CustomSource().add_url(rest[0])
            result = {"item_id": item_id, "source": "custom"}
        elif command == "add-text":
            from .sources.custom import CustomSource

            payload = json.loads(sys.stdin.read())
            item_id = CustomSource().add_text(
                payload["title"], payload["text"], payload.get("url", "")
            )
            result = {"item_id": item_id, "source": "custom"}
        elif command == "add-file" and rest:
            from .file_extraction import extract_file
            from .sources.custom import CustomSource

            extraction = extract_file(Path(rest[0]))
            if extraction.needs_fallback:
                result = {
                    "added": False,
                    "needs_fallback": True,
                    "reason": extraction.reason,
                    "title": extraction.title,
                }
            else:
                item_id = CustomSource().add_text(extraction.title, extraction.text)
                result = {
                    "added": True,
                    "item_id": item_id,
                    "source": "custom",
                    "title": extraction.title,
                    "method": extraction.method,
                    "words": len(extraction.text.split()),
                }
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
            result = _cmd_keys_list()
        elif command == "keys-add" and rest:
            from .config import key_store

            key_store().add(rest[0], sys.stdin.read().strip())
            result = {"added": rest[0]}
        elif command in {"keys-activate", "keys-use"} and rest:
            result = _cmd_use_named_key(rest[0])
        elif command == "keys-use-environment":
            result = _cmd_use_environment_key()
        elif command == "keys-move" and len(rest) >= 2:
            result = _cmd_move_named_key(rest[0], rest[1])
        elif command == "keys-check" and rest:
            result = _cmd_check_named_key(rest[0])
        elif command == "keys-check-environment":
            result = _cmd_check_environment_key()
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
            result = {
                "active": store.active().name,
                "profiles": [
                    {**_asdict(p), "custom": store.is_custom(p.name)} for p in store.list_profiles()
                ],
            }
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
