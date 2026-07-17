"""Pipeline do episódio: cobertura → roteiro → auditoria → áudio → montagem.

Genérico sobre qualquer `ContentItem` e 1..N apresentadores. Cada etapa persiste
seu artefato em data/episodes/<item>/ para retomada e auditoria; `status.json`
expõe etapa, progresso e custo em tempo real; um arquivo `ABORT` na pasta do
episódio interrompe a geração no próximo checkpoint.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
import wave
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

from .config import EPISODES_DIR, Settings, api_key_candidates
from .estimates import EpisodeMetrics, estimate_tts_cost
from .prompts import AUDIT_PROMPT, COVERAGE_PROMPT, SYSTEM_PROMPT, script_prompt
from .providers import openrouter
from .runtime.process import run_tool
from .runtime.retry import RetryPolicy
from .runtime.status import GenerationTracker
from .sources.base import ContentItem


def episode_dir(item_id: str) -> Path:
    return EPISODES_DIR / item_id.replace("/", "__")


def _save_json(path: Path, data: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _load_json(path: Path) -> object | None:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def generate_episode(settings: Settings, item: ContentItem, force: bool = False) -> Path:
    """Executa o pipeline completo para um item e retorna o MP3 final."""
    directory = episode_dir(item.item_id)
    tracker = GenerationTracker(directory, episode_id=item.item_id, resume=not force)
    try:
        result = _run(settings, item, directory, tracker, force)
        tracker.finish("concluido")
        return result
    except Exception as error:
        status = GenerationTracker.load(directory) or {}
        if status.get("state") == "rodando":
            tracker.finish("falhou", error=str(error))
        raise


def _run(settings: Settings, item: ContentItem, directory: Path,
         tracker: GenerationTracker, force: bool) -> Path:
    print(f"\n📄 {item.title} ({item.published_at})")
    print(f"   Pasta do episódio: {directory}")

    subscription = settings.text_provider not in ("", "openrouter")

    def _chat_step(stage: str, path: Path, model: str, prompt: str) -> dict:
        cached = None if force else _load_json(path)
        if cached is not None:
            return cached
        tracker.stage(stage)
        tracker.checkpoint()
        if subscription:
            from .providers import subscription as subscription_provider
            result = subscription_provider.chat_json(
                settings.text_provider, SYSTEM_PROMPT, prompt
            )
            print(f"    [{settings.text_provider}] via assinatura — custo US$ 0,00")
        else:
            result = openrouter.chat_json(settings, model, SYSTEM_PROMPT, prompt)
            print(f"    [{model}] {result.prompt_tokens}/{result.completion_tokens} tokens, "
                  f"US$ {result.cost_usd:.4f}")
        tracker.add_cost(result.cost_usd)
        _save_json(path, result.data)
        return result.data

    print("🧠 1/5 Matriz de cobertura…")
    coverage = _chat_step(
        "cobertura", directory / "coverage.json", settings.audit_model,
        COVERAGE_PROMPT.format(content=item.text),
    )
    print(f"   {len(coverage.get('items', []))} itens de cobertura.")

    print("✍️  2/5 Roteiro…")
    script = _chat_step(
        "roteiro", directory / "script.json", settings.text_model,
        script_prompt(settings.presenters, item.attribution).format(
            content=item.text, matrix=json.dumps(coverage, ensure_ascii=False),
        ),
    )
    turns = script.get("turns", [])
    print(f"   {len(turns)} turnos para {len(settings.presenters)} apresentador(es).")

    print("✅ 3/5 Auditoria do roteiro…")
    audit = _chat_step(
        "auditoria", directory / "audit.json", settings.audit_model,
        AUDIT_PROMPT.format(
            content=item.text,
            matrix=json.dumps(coverage, ensure_ascii=False),
            script=json.dumps(script, ensure_ascii=False),
        ),
    )
    _report_audit(coverage, audit)

    print("🎙️  4/5 Síntese de áudio por turno…")
    segments = _synthesize_turns(
        settings, directory, turns, tracker, trust_legacy_segments=not force,
    )

    print("🎧 5/5 Montagem com ffmpeg…")
    tracker.stage("montagem")
    tracker.checkpoint()
    final_path = _assemble(directory, segments, item)
    duration_seconds = _media_duration_seconds(final_path)
    EpisodeMetrics(
        source_words=item.words,
        script_words=sum(len(turn.get("text", "").split()) for turn in turns),
        duration_seconds=duration_seconds,
        cost_usd=tracker.cost_usd,
        cost_exact=tracker.cost_exact,
        tts_model=settings.tts_model,
        profile_name=settings.profile_name,
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        cost_source=("generation_ids" if tracker.cost_exact else "model_pricing_fallback"),
    ).write(directory)
    _write_show_notes(directory, item, tracker.cost_usd, tracker.cost_exact)
    print(f"\n✔ Episódio gerado: {final_path}")
    print(f"💰 Custo total registrado: US$ {tracker.cost_usd:.4f}")
    return final_path


def _report_audit(coverage: dict, audit: dict) -> None:
    criticality = {i["id"]: i.get("criticality", "contextual") for i in coverage.get("items", [])}
    problems = [
        r for r in audit.get("results", [])
        if r.get("status") in ("ausente", "distorcido", "parcial")
        and criticality.get(r.get("coverage_id"), "contextual") in ("critica", "importante")
    ]
    if problems:
        print(f"   ⚠ {len(problems)} itens críticos/importantes com pendência:")
        for problem in problems[:10]:
            print(f"     - {problem['coverage_id']} [{problem['status']}]: "
                  f"{problem.get('notes', '')[:120]}")
        print("   O episódio será gerado mesmo assim; revise audit.json antes de publicar.")
    else:
        print("   Cobertura crítica e importante completa. ✔")
    for claim in audit.get("unsupported_claims", [])[:5]:
        print(f"   ⚠ Afirmação sem base no conteúdo: {claim[:120]}")


def _progress_bar(current: int, total: int, label: str, width: int = 30) -> None:
    """Barra de linha única no terminal; linha por item quando a saída é arquivo."""
    filled = int(width * current / total)
    bar = "█" * filled + "░" * (width - filled)
    line = f"   [{bar}] {current}/{total} ({100 * current // total}%) {label}"
    if sys.stdout.isatty():
        print(f"\r\033[K{line}", end="" if current < total else "\n", flush=True)
    else:
        print(line, flush=True)


def _wrap_pcm_as_wav(pcm: bytes, path: Path, sample_rate: int) -> None:
    """Embrulha PCM cru (16-bit mono) em um contêiner WAV."""
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)


def _valid_segment(path: Path) -> bool:
    """Rejeita arquivos parciais; WAV também precisa ter cabeçalho e frames válidos."""
    if not path.is_file() or path.stat().st_size <= 512:
        return False
    if path.suffix.lower() != ".wav":
        return True
    try:
        with wave.open(str(path), "rb") as audio:
            return audio.getnchannels() > 0 and audio.getnframes() > 0
    except (EOFError, wave.Error):
        return False


def _segment_fingerprint(settings: Settings, text: str, voice: str,
                         instructions: str) -> str:
    """Vincula o cache ao conteúdo e às opções que alteram a identidade sonora."""
    payload = {
        "model": settings.tts_model,
        "text": text,
        "voice": voice,
        "instructions": instructions,
        "format": settings.tts_format,
        "sample_rate": settings.tts_sample_rate,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _wait_for_retry(delay_seconds: float, tracker: GenerationTracker) -> None:
    """Espera em passos curtos para que o abort continue responsivo."""
    remaining = delay_seconds
    while remaining > 0:
        tracker.checkpoint()
        step = min(1.0, remaining)
        time.sleep(step)
        remaining -= step


def _is_key_limit_error(error: openrouter.OpenRouterError) -> bool:
    message = str(error).lower()
    return error.status_code == 403 and "limit" in message


@dataclass(frozen=True)
class _SynthesisResult:
    speech: openrouter.SpeechResult
    settings: Settings
    key_label: str


def _synthesize_with_retry(settings: Settings, text: str, voice: str,
                           instructions: str, segment_number: int,
                           tracker: GenerationTracker) -> _SynthesisResult:
    policy = RetryPolicy(
        max_attempts=settings.tts_retry_attempts,
        base_delay_seconds=settings.tts_retry_base_seconds,
        max_delay_seconds=settings.tts_retry_max_seconds,
    )
    candidates = api_key_candidates(settings) or [("chave atual", settings)]
    last_error: openrouter.OpenRouterError | None = None
    for key_index, (key_label, candidate) in enumerate(candidates):
        for attempt in range(1, policy.max_attempts + 1):
            tracker.checkpoint()
            try:
                speech = openrouter.text_to_speech(
                    candidate, text, voice, instructions=instructions,
                )
                return _SynthesisResult(speech, candidate, key_label)
            except openrouter.OpenRouterError as error:
                last_error = error
                if _is_key_limit_error(error) and key_index + 1 < len(candidates):
                    next_label = candidates[key_index + 1][0]
                    print(
                        f"\n   ↪ Limite da {key_label}; tentando {next_label} "
                        f"na fala {segment_number}.", flush=True,
                    )
                    break
                if not error.retryable or attempt == policy.max_attempts:
                    tracker.record_error(str(error))
                    raise
                delay = policy.delay_after(attempt)
                tracker.retrying(
                    segment=segment_number,
                    next_attempt=attempt + 1,
                    max_attempts=policy.max_attempts,
                    delay_seconds=delay,
                    error=str(error),
                )
                print(
                    f"\n   ↻ Falha temporária na fala {segment_number}; "
                    f"tentativa {attempt + 1}/{policy.max_attempts} em {delay:.1f}s.",
                    flush=True,
                )
                _wait_for_retry(delay, tracker)
    if last_error:
        tracker.record_error(str(last_error))
        raise last_error
    raise AssertionError("A política de retry terminou sem resultado nem erro.")


def _synthesize_turns(settings: Settings, directory: Path, turns: list[dict],
                      tracker: GenerationTracker,
                      trust_legacy_segments: bool = True) -> list[Path]:
    voices = {p.speaker: p for p in settings.presenters}
    default = settings.presenters[0]
    segments_dir = directory / "segments"
    segments_dir.mkdir(exist_ok=True)
    extension = "wav" if settings.tts_format == "pcm" else settings.tts_format
    manifest_path = directory / "segments.json"
    loaded_manifest = _load_json(manifest_path)
    if loaded_manifest is not None and not isinstance(loaded_manifest, dict):
        raise ValueError("segments.json inválido: era esperado um objeto JSON.")
    manifest = loaded_manifest or {"version": 1, "segments": {}}
    entries = manifest.get("segments")
    if not isinstance(entries, dict):
        raise ValueError("segments.json inválido: campo 'segments' ausente ou inválido.")

    plans: list[dict] = []
    completed = 0
    for index, turn in enumerate(turns, 1):
        if (not isinstance(turn, dict) or not isinstance(turn.get("text"), str)
                or not turn["text"].strip()):
            raise ValueError(f"Turno {index} inválido no roteiro.")
        speaker = turn.get("speaker")
        presenter = voices.get(speaker, default)
        segment = segments_dir / f"{index:03d}_{presenter.speaker}.{extension}"
        style = f", tom {presenter.style}" if presenter.style else ""
        instructions = f"Fala natural de podcast em português brasileiro{style}."
        fingerprint = _segment_fingerprint(
            settings, turn["text"], presenter.voice, instructions,
        )
        entry = entries.get(segment.name)
        entry_matches = isinstance(entry, dict) and entry.get("fingerprint") == fingerprint
        legacy_segment = entry is None and trust_legacy_segments
        reusable = _valid_segment(segment) and (entry_matches or legacy_segment)
        if reusable:
            completed += 1
            entries[segment.name] = {
                "fingerprint": fingerprint,
                "bytes": segment.stat().st_size,
            }
        plans.append({
            "index": index,
            "turn": turn,
            "presenter": presenter,
            "segment": segment,
            "instructions": instructions,
            "fingerprint": fingerprint,
            "reusable": reusable,
        })

    # Importa segmentos legados para o manifesto antes de qualquer nova chamada.
    _save_json(manifest_path, manifest)
    tracker.stage("tts", total=len(turns), current=completed)

    paths = [plan["segment"] for plan in plans]
    for plan in plans:
        tracker.checkpoint()
        index = plan["index"]
        segment = plan["segment"]
        if plan["reusable"]:
            continue
        presenter = plan["presenter"]
        cost_label = f"US$ {tracker.cost_usd:.3f}"
        _progress_bar(index, len(turns), f"{presenter.speaker} ({presenter.voice}) {cost_label}")
        synthesis = _synthesize_with_retry(
            settings, plan["turn"]["text"], presenter.voice,
            plan["instructions"], index, tracker,
        )
        speech = synthesis.speech
        speech_settings = synthesis.settings
        temporary = segment.with_suffix(segment.suffix + ".tmp")
        temporary.unlink(missing_ok=True)
        try:
            if settings.tts_format == "pcm":
                _wrap_pcm_as_wav(speech.audio, temporary, settings.tts_sample_rate)
            else:
                temporary.write_bytes(speech.audio)
            if not _valid_segment(temporary):
                raise ValueError(f"O áudio da fala {index} ficou vazio ou inválido.")
            temporary.replace(segment)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        duration_seconds = _media_duration_seconds(segment)
        cost_exact = False
        segment_cost = 0.0
        if speech.generation_id:
            try:
                segment_cost = openrouter.generation_cost_usd(
                    speech_settings, speech.generation_id
                )
                cost_exact = True
            except (openrouter.OpenRouterError, RuntimeError, ValueError):
                pass
        if not cost_exact:
            segment_cost = estimate_tts_cost(
                settings, plan["turn"]["text"], plan["instructions"], duration_seconds
            )
        tracker.add_cost(segment_cost, exact=cost_exact)
        entries[segment.name] = {
            "fingerprint": plan["fingerprint"],
            "bytes": segment.stat().st_size,
            "generation_id": speech.generation_id,
            "key_label": synthesis.key_label,
            "cost_usd": round(segment_cost, 8),
            "cost_exact": cost_exact,
        }
        _save_json(manifest_path, manifest)
        completed += 1
        tracker.advance(completed)
    return paths


_FFPROBE_TIMEOUT = 120
_FFMPEG_TIMEOUT = 1800


def _concat_line(path: Path) -> str:
    """Linha do concat demuxer do ffmpeg para um segmento.

    O ffmpeg interpreta ``\\`` como escape na lista de concatenação; no Windows
    o caminho resolvido usa barras invertidas. Normaliza para ``/`` (aceito em
    todas as plataformas) e escapa aspas simples, evitando falha silenciosa de
    montagem quando o caminho tem caractere especial.
    """
    text = path.resolve().as_posix().replace("'", r"'\''")
    return f"file '{text}'\n"


def _media_duration_seconds(path: Path) -> float:
    """Obtém duração real de WAV/MP3 usando as dependências do pipeline."""
    if path.suffix.lower() == ".wav":
        with wave.open(str(path), "rb") as audio:
            framerate = audio.getframerate()
            if framerate <= 0:
                raise ValueError(f"WAV com taxa de amostragem inválida: {path.name}")
            return audio.getnframes() / framerate
    result = run_tool(
        "ffprobe",
        [
            "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        timeout=_FFPROBE_TIMEOUT,
    )
    raw = result.stdout.strip()
    try:
        return float(raw)
    except ValueError as error:
        raise ValueError(
            f"ffprobe não retornou a duração de {path.name}: {raw[:100] or 'vazio'}"
        ) from error


def _assemble(directory: Path, segments: list[Path], item: ContentItem) -> Path:
    if not segments:
        raise ValueError("Não há segmentos de áudio para montar o episódio.")
    concat_list = directory / "segments.txt"
    concat_list.write_text(
        "".join(_concat_line(p) for p in segments), encoding="utf-8"
    )
    final_path = directory / "episode.mp3"
    temporary = directory / "episode.tmp.mp3"
    temporary.unlink(missing_ok=True)
    try:
        run_tool(
            "ffmpeg",
            [
                "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
                "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                "-metadata", f"title={item.title}",
                "-metadata", "artist=Audiofy Content AI",
                "-metadata", f"comment={item.attribution}",
                "-codec:a", "libmp3lame", "-b:a", "128k",
                str(temporary),
            ],
            timeout=_FFMPEG_TIMEOUT,
        )
        temporary.replace(final_path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return final_path


def _write_show_notes(directory: Path, item: ContentItem, cost_usd: float,
                      cost_exact: bool) -> None:
    (directory / "NOTES.md").write_text(
        f"# {item.title}\n\n"
        f"{item.attribution}\n\n"
        f"Adaptação em áudio gerada com inteligência artificial; revise `audit.json` antes de\n"
        f"publicar. Fonte original: {item.url}\n\n"
        f"Custo de geração registrado: US$ {cost_usd:.4f} "
        f"({'exato por geração' if cost_exact else 'aproximado'})\n",
        encoding="utf-8",
    )
