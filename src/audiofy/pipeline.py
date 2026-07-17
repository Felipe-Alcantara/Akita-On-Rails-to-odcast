"""Pipeline do episódio: cobertura → roteiro → auditoria → áudio → montagem.

Genérico sobre qualquer `ContentItem` e 1..N apresentadores. Cada etapa persiste
seu artefato em data/episodes/<item>/ para retomada e auditoria; `status.json`
expõe etapa, progresso e custo em tempo real; um arquivo `ABORT` na pasta do
episódio interrompe a geração no próximo checkpoint.
"""

from __future__ import annotations

import json
import subprocess
import sys
import wave
from pathlib import Path

from .config import EPISODES_DIR, Settings
from .prompts import AUDIT_PROMPT, COVERAGE_PROMPT, SYSTEM_PROMPT, script_prompt
from .providers import openrouter
from .runtime.status import GenerationTracker
from .sources.base import ContentItem


def episode_dir(item_id: str) -> Path:
    return EPISODES_DIR / item_id.replace("/", "__")


def _save_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_json(path: Path) -> object | None:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def generate_episode(settings: Settings, item: ContentItem, force: bool = False) -> Path:
    """Executa o pipeline completo para um item e retorna o MP3 final."""
    directory = episode_dir(item.item_id)
    tracker = GenerationTracker(directory, episode_id=item.item_id)
    try:
        result = _run(settings, item, directory, tracker, force)
        tracker.finish("concluido")
        return result
    except Exception:
        if GenerationTracker.load(directory).get("state") == "rodando":
            tracker.finish("falhou")
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
    segments = _synthesize_turns(settings, directory, turns, tracker)

    print("🎧 5/5 Montagem com ffmpeg…")
    tracker.stage("montagem")
    tracker.checkpoint()
    final_path = _assemble(directory, segments, item)
    _write_show_notes(directory, item, tracker.cost_usd)
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


def _synthesize_turns(settings: Settings, directory: Path, turns: list[dict],
                      tracker: GenerationTracker) -> list[Path]:
    voices = {p.speaker: p for p in settings.presenters}
    default = settings.presenters[0]
    segments_dir = directory / "segments"
    segments_dir.mkdir(exist_ok=True)
    extension = "wav" if settings.tts_format == "pcm" else settings.tts_format
    tracker.stage("tts", total=len(turns))

    # Custo do TTS: a resposta binária não traz valor; usamos o delta de uso da
    # conta desde o início da etapa (aproximação, ver README). Falha na leitura
    # do uso nunca pode derrubar a geração.
    def _account_usage() -> float | None:
        try:
            return openrouter.account_usage_usd(settings)
        except Exception:
            return None

    usage_baseline = _account_usage()
    cost_baseline = tracker.cost_usd

    paths: list[Path] = []
    for index, turn in enumerate(turns, 1):
        tracker.checkpoint()
        segment = segments_dir / f"{index:03d}_{turn['speaker']}.{extension}"
        paths.append(segment)
        if segment.is_file() and segment.stat().st_size > 512:
            tracker.advance(index)
            continue
        presenter = voices.get(turn["speaker"], default)
        cost_label = f"US$ {tracker.cost_usd:.3f}"
        _progress_bar(index, len(turns), f"{presenter.speaker} ({presenter.voice}) {cost_label}")
        style = f", tom {presenter.style}" if presenter.style else ""
        audio = openrouter.text_to_speech(
            settings, turn["text"], presenter.voice,
            instructions=f"Fala natural de podcast em português brasileiro{style}.",
        )
        temporary = segment.with_suffix(segment.suffix + ".tmp")
        if settings.tts_format == "pcm":
            _wrap_pcm_as_wav(audio, temporary, settings.tts_sample_rate)
        else:
            temporary.write_bytes(audio)
        temporary.rename(segment)
        tracker.advance(index)
        if usage_baseline is not None and (usage_now := _account_usage()) is not None:
            tts_cost = max(0.0, usage_now - usage_baseline)
            tracker.add_cost(cost_baseline + tts_cost - tracker.cost_usd)
    return paths


def _assemble(directory: Path, segments: list[Path], item: ContentItem) -> Path:
    concat_list = directory / "segments.txt"
    concat_list.write_text(
        "".join(f"file '{p.resolve()}'\n" for p in segments), encoding="utf-8"
    )
    final_path = directory / "episode.mp3"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-metadata", f"title={item.title}",
            "-metadata", "artist=Audiofy Content AI",
            "-metadata", f"comment={item.attribution}",
            "-codec:a", "libmp3lame", "-b:a", "128k",
            str(final_path),
        ],
        check=True, capture_output=True, text=True,
    )
    return final_path


def _write_show_notes(directory: Path, item: ContentItem, cost_usd: float) -> None:
    (directory / "NOTES.md").write_text(
        f"# {item.title}\n\n"
        f"{item.attribution}\n\n"
        f"Adaptação em áudio gerada com inteligência artificial; revise `audit.json` antes de\n"
        f"publicar. Fonte original: {item.url}\n\n"
        f"Custo de geração registrado: US$ {cost_usd:.4f}\n",
        encoding="utf-8",
    )
