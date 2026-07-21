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
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .artifacts import (
    ARTIFACT_SCHEMA_VERSION,
    LEGACY_FINAL_AUDIO,
    final_audio_filename,
    segment_audio_filename,
    write_source_document,
)
from .audio_audit import audit_segments
from .config import EPISODES_DIR, Settings, api_key_candidates, api_key_source
from .estimates import EpisodeMetrics, estimate_tts_cost
from .media import media_duration_seconds
from .narration import (
    MAX_TTS_CHARS,
    commentary_direction,
    fallback_commentary,
    fallback_direction,
    parse_prosody_plan,
    parse_reflexive_commentary,
    podcast_direction,
    prosody_batches,
    prosody_prompt,
    prosody_system,
    reflexive_batches,
    reflexive_prompt,
    reflexive_system,
    split_into_paragraphs,
    split_verbatim_text,
    tts_direction,
)
from .prompts import audit_prompt, coverage_prompt, script_prompt, system_prompt
from .providers import openrouter
from .runtime.process import run_tool
from .runtime.retry import RetryPolicy
from .runtime.status import GenerationTracker
from .sources.base import ContentItem


def episode_dir(item_id: str, language: str = "pt-BR") -> Path:
    base = item_id.replace("/", "__")
    if language != "pt-BR":
        base = f"{base}__{language}"
    return EPISODES_DIR / base


def _save_json(path: Path, data: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _load_json(path: Path) -> object | None:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def generate_episode(
    settings: Settings,
    item: ContentItem,
    force: bool = False,
    generation_mode: str = "adaptation",
    narration_voice: str | None = None,
    background_music: Path | None = None,
    background_volume: float = 0.08,
    source_key: str = "conteudo",
) -> Path:
    """Executa o pipeline completo para um item e retorna o MP3 final."""
    if generation_mode not in {"adaptation", "verbatim", "reflexive"}:
        raise ValueError(f"Modo de geração desconhecido: {generation_mode}")
    if generation_mode in {"verbatim", "reflexive"} and len(settings.presenters) != 1:
        raise ValueError("A leitura reflexiva e a leitura fiel exigem exatamente um narrador.")
    directory = episode_dir(item.item_id, settings.language)
    previous = GenerationTracker.load(directory)
    if previous and (
        previous.get("generation_mode", "adaptation") != generation_mode
        or (
            generation_mode in {"verbatim", "reflexive"}
            and previous.get("narration_voice") != narration_voice
        )
    ):
        force = True
    tracker = GenerationTracker(
        directory,
        episode_id=item.item_id,
        resume=not force,
        generation_mode=generation_mode,
        narration_voice=narration_voice,
        key_source=(
            previous.get("key_source")
            if previous and previous.get("stage") == "iniciando"
            else api_key_source()
        ),
        background_music=(
            previous.get("background_music")
            if previous and previous.get("stage") == "iniciando"
            else (background_music.name if background_music else None)
        ),
        background_music_cache=(
            previous.get("background_music_cache")
            if previous and previous.get("stage") == "iniciando"
            else None
        ),
        background_volume=background_volume if background_music else None,
    )
    try:
        result = _run(
            settings,
            item,
            directory,
            tracker,
            force,
            generation_mode,
            background_music,
            background_volume,
            source_key,
        )
        tracker.finish("concluido")
        return result
    except Exception as error:
        status = GenerationTracker.load(directory) or {}
        if status.get("state") == "rodando":
            tracker.finish("falhou", error=str(error))
        raise


# ── Reparo seletivo de segmentos com silêncio problemático ────────────────


def repair_episode(
    settings: Settings,
    item: ContentItem,
    source_key: str = "conteudo",
    generation_mode: str = "adaptation",
    narration_voice: str | None = None,
    background_music: Path | None = None,
    background_volume: float = 0.08,
) -> Path:
    """Regenera somente os segmentos com silêncio problemático e remonta o MP3.

    Usa o cache por fingerprint: segmentos bons permanecem intactos, apenas os WAVs
    identificados pela auditoria como warning/critical são deletados e re-sintetizados.
    """
    from .audio_audit import read_audio_audit

    directory = episode_dir(item.item_id, settings.language)
    audit = read_audio_audit(directory)
    if not audit:
        raise FileNotFoundError("Não há auditoria de áudio para este episódio. Gere-o primeiro.")
    bad_files = {
        seg["file"]
        for seg in audit.get("segments", [])
        if seg.get("severity") in ("critical", "warning")
    }
    if not bad_files:
        from .artifacts import resolve_final_audio

        final = resolve_final_audio(directory)
        if final:
            return final
        raise FileNotFoundError("Nenhum segmento com problema e nenhum áudio final encontrado.")

    # Carregar turnos do roteiro salvo (funciona para adaptation e verbatim).
    from .episode_verification import _turns

    _detected_mode, turns = _turns(directory)
    if not generation_mode:
        generation_mode = _detected_mode

    # Deletar WAVs problemáticos para que _synthesize_turns os regenere.
    segments_dir = directory / "segments"
    for filename in bad_files:
        target = segments_dir / filename
        target.unlink(missing_ok=True)

    tracker = GenerationTracker(
        directory,
        episode_id=item.item_id,
        resume=True,
        generation_mode=generation_mode,
        narration_voice=narration_voice,
        key_source=api_key_source(),
        background_music=(background_music.name if background_music else None),
        background_volume=background_volume if background_music else None,
    )
    try:
        print(f"🔧 Reparando {len(bad_files)} segmento(s) com silêncio problemático…")
        tracker.stage("reparacao", total=len(turns), current=0)

        segments = _synthesize_turns(
            settings,
            directory,
            turns,
            tracker,
            trust_legacy_segments=False,
            source_key=source_key,
            item_id=item.item_id,
            generation_mode=generation_mode,
        )

        tracker.stage("auditoria_audio", total=len(segments), current=0)
        audio_audit_result = audit_segments(directory, segments, on_progress=tracker.advance)
        summary = audio_audit_result["summary"]
        if summary["critical"]:
            print(
                f"⚠ Após reparo ainda há {summary['critical']} chunk(s) com silêncio "
                "crítico; a voz pode ter limitações nesse trecho.",
                flush=True,
            )

        tracker.stage("montagem")
        tracker.checkpoint()
        final_path = _assemble(
            directory,
            segments,
            item,
            background_music,
            background_volume,
            background_music_name=(background_music.name if background_music else None),
            source_key=source_key,
            generation_mode=generation_mode,
        )
        print(f"\n✔ Episódio reparado: {final_path}")
        print(f"💰 Custo total acumulado: US$ {tracker.cost_usd:.4f}")
        tracker.finish("concluido")
        return final_path
    except Exception as error:
        status = GenerationTracker.load(directory) or {}
        if status.get("state") == "rodando":
            tracker.finish("falhou", error=str(error))
        raise


def _run(
    settings: Settings,
    item: ContentItem,
    directory: Path,
    tracker: GenerationTracker,
    force: bool,
    generation_mode: str,
    background_music: Path | None,
    background_volume: float,
    source_key: str,
) -> Path:
    print(f"\n📄 {item.title} ({item.published_at})")
    print(f"   Pasta do episódio: {directory}")
    source_file = write_source_document(directory, item, source_key)

    subscription = settings.text_provider not in ("", "openrouter")

    lang = settings.language
    _sys = system_prompt(lang)

    def _chat_request(model: str, prompt: str, system: str = "") -> dict:
        system = system or _sys
        if subscription:
            from .providers import subscription as subscription_provider

            result = subscription_provider.chat_json(
                settings.text_provider, system, prompt, settings.subscription_model
            )
            label = settings.subscription_model or "modelo padrão da CLI"
            print(f"    [{settings.text_provider}: {label}] via assinatura — custo US$ 0,00")
        else:
            result = _chat_with_key_fallback(settings, model, system, prompt, tracker)
            print(
                f"    [{model}] {result.prompt_tokens}/{result.completion_tokens} tokens, "
                f"US$ {result.cost_usd:.4f}"
            )
        tracker.add_cost(result.cost_usd)
        return result.data

    def _chat_step(stage: str, path: Path, model: str, prompt: str) -> dict:
        cached = None if force else _load_json(path)
        if cached is not None:
            return cached
        tracker.stage(stage)
        tracker.checkpoint()
        data = _chat_request(model, prompt)
        _save_json(path, data)
        return data

    if generation_mode == "verbatim":
        print("🎭 1/3 Planejamento de interpretação em lotes…")
        turns = _prepare_verbatim_turns(
            settings,
            item,
            directory,
            tracker,
            force,
            lambda prompt: _chat_request(settings.audit_model, prompt, prosody_system(lang)),
        )
        print(f"   {len(turns)} trechos; texto original preservado integralmente.")
        print("🎙️  2/3 Síntese da leitura fiel…")
    elif generation_mode == "reflexive":
        print("🎭 1/3 Planejamento de leitura reflexiva em lotes…")
        turns = _prepare_reflexive_turns(
            settings,
            item,
            directory,
            tracker,
            force,
            lambda prompt: _chat_request(settings.audit_model, prompt, prosody_system(lang)),
            lambda prompt: _chat_request(settings.audit_model, prompt, reflexive_system(lang)),
        )
        verbatim_count = sum(1 for t in turns if t.get("kind") == "verbatim")
        commentary_count = len(turns) - verbatim_count
        print(f"   {verbatim_count} trechos verbatim + {commentary_count} comentários reflexivos.")
        print("🎙️  2/3 Síntese da leitura reflexiva…")
    else:
        print("🧠 1/5 Matriz de cobertura…")
        coverage = _chat_step(
            "cobertura",
            directory / "coverage.json",
            settings.audit_model,
            coverage_prompt(lang).format(content=item.text),
        )
        print(f"   {len(coverage.get('items', []))} itens de cobertura.")

        print("✍️  2/5 Roteiro…")
        script = _chat_step(
            "roteiro",
            directory / "script.json",
            settings.text_model,
            script_prompt(settings.presenters, item.attribution, lang).format(
                content=item.text,
                matrix=json.dumps(coverage, ensure_ascii=False),
            ),
        )
        turns = script.get("turns", [])
        print(f"   {len(turns)} turnos para {len(settings.presenters)} apresentador(es).")

        print("✅ 3/5 Auditoria do roteiro…")
        audit = _chat_step(
            "auditoria",
            directory / "audit.json",
            settings.audit_model,
            audit_prompt(lang).format(
                content=item.text,
                matrix=json.dumps(coverage, ensure_ascii=False),
                script=json.dumps(script, ensure_ascii=False),
            ),
        )
        _report_audit(coverage, audit)
        print("🎙️  4/5 Síntese de áudio por turno…")

    segments = _synthesize_turns(
        settings,
        directory,
        turns,
        tracker,
        trust_legacy_segments=not force and generation_mode != "verbatim",
        source_key=source_key,
        item_id=item.item_id,
        generation_mode=generation_mode,
    )

    print(
        "🎧 3/3 Montagem com ffmpeg…"
        if generation_mode in {"verbatim", "reflexive"}
        else "🎧 5/5 Montagem com ffmpeg…"
    )
    tracker.stage("auditoria_audio", total=len(segments), current=0)
    audio_audit = audit_segments(directory, segments, on_progress=tracker.advance)
    audit_summary = audio_audit["summary"]
    if audit_summary["critical"]:
        print(
            f"⚠ Auditoria encontrou {audit_summary['critical']} chunk(s) com silêncio crítico; "
            "revise-os individualmente no app.",
            flush=True,
        )
    tracker.stage("montagem")
    tracker.checkpoint()
    final_path = _assemble(
        directory,
        segments,
        item,
        background_music,
        background_volume,
        tracker.background_music,
        source_key=source_key,
        generation_mode=generation_mode,
    )
    duration_seconds = media_duration_seconds(final_path)
    EpisodeMetrics(
        source_words=item.words,
        script_words=sum(len(turn.get("text", "").split()) for turn in turns),
        duration_seconds=duration_seconds,
        cost_usd=tracker.cost_usd,
        cost_exact=tracker.cost_exact,
        tts_model=settings.tts_model,
        profile_name=settings.profile_name,
        generation_mode=generation_mode,
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        cost_source=("generation_ids" if tracker.cost_exact else "model_pricing_fallback"),
        background_music=tracker.background_music,
        background_volume=tracker.background_volume,
        title=item.title,
        source_created_at=item.published_at,
        source_key=source_key,
        source_file=source_file.name,
        final_audio_file=final_path.name,
        artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
    ).write(directory)
    _write_show_notes(
        directory,
        item,
        tracker.cost_usd,
        tracker.cost_exact,
        generation_mode,
        tracker.background_music,
        tracker.background_volume,
    )
    print(f"\n✔ Episódio gerado: {final_path}")
    print(f"💰 Custo total registrado: US$ {tracker.cost_usd:.4f}")
    return final_path


def _prepare_verbatim_turns(
    settings: Settings,
    item: ContentItem,
    directory: Path,
    tracker: GenerationTracker,
    force: bool,
    analyze: Callable[[str], dict],
) -> list[dict]:
    """Planeja somente a interpretação; o texto falado sempre vem da fonte original."""
    chunks = split_verbatim_text(item.text)
    source_digest = hashlib.sha256(item.text.encode("utf-8")).hexdigest()
    path = directory / "prosody.json"
    loaded = None if force else _load_json(path)
    if not isinstance(loaded, dict) or loaded.get("source_sha256") != source_digest:
        loaded = {"version": 1, "source_sha256": source_digest, "segments": {}}
    entries = loaded.get("segments")
    if not isinstance(entries, dict):
        entries = {}
        loaded["segments"] = entries

    def cache_key(index: int, text: str) -> str:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"{index}:{digest}"

    cached = {
        chunk.index
        for chunk in chunks
        if isinstance(entries.get(cache_key(chunk.index, chunk.text)), dict)
        and isinstance(entries[cache_key(chunk.index, chunk.text)].get("direction"), str)
    }
    tracker.stage("planejamento de interpretação", total=len(chunks), current=len(cached))
    missing = [chunk for chunk in chunks if chunk.index not in cached]
    completed = len(cached)
    for batch in prosody_batches(missing):
        tracker.checkpoint()
        planned = parse_prosody_plan(analyze(prosody_prompt(batch)), {c.index for c in batch})
        for chunk in batch:
            entries[cache_key(chunk.index, chunk.text)] = {
                "direction": planned.get(chunk.index) or fallback_direction(chunk.text)
            }
        completed += len(batch)
        _save_json(path, loaded)
        tracker.advance(completed)

    narrator = settings.presenters[0]
    turns = []
    for chunk in chunks:
        direction = entries[cache_key(chunk.index, chunk.text)]["direction"]
        turns.append(
            {
                "turn_id": f"N{chunk.index:05d}",
                "speaker": narrator.speaker,
                "text": chunk.text,
                "instructions": tts_direction(direction, narrator.style, settings.language),
            }
        )
    if "".join(turn["text"] for turn in turns) != item.text:
        raise AssertionError("O planejamento de interpretação alterou o texto original.")
    _save_json(
        directory / "narration-script.json",
        {"mode": "verbatim", "source_sha256": source_digest, "turns": turns},
    )
    return turns


def _prepare_reflexive_turns(
    settings: Settings,
    item: ContentItem,
    directory: Path,
    tracker: GenerationTracker,
    force: bool,
    analyze_prosody: Callable[[str], dict],
    analyze_reflexive: Callable[[str], dict],
) -> list[dict]:
    """Lê cada parágrafo verbatim e intercala um breve comentário reflexivo após cada um."""
    paragraphs = split_into_paragraphs(item.text)
    if not paragraphs:
        raise ValueError("O texto não contém parágrafos para a leitura reflexiva.")

    # Divide parágrafos longos em sub-chunks para o limite do TTS.
    # Cada parágrafo lógico tem um id; sub-chunks compartilham o mesmo para-id.
    para_chunks: list[tuple[int, str]] = []  # (para_id, text)
    for para_id, para in enumerate(paragraphs, 1):
        if len(para) <= MAX_TTS_CHARS:
            para_chunks.append((para_id, para))
        else:
            sub_chunks = split_verbatim_text(para)
            for sub in sub_chunks:
                para_chunks.append((para_id, sub.text))

    source_digest = hashlib.sha256(item.text.encode("utf-8")).hexdigest()
    path = directory / "reflexive.json"
    loaded = None if force else _load_json(path)
    if not isinstance(loaded, dict) or loaded.get("source_sha256") != source_digest:
        loaded = {
            "version": 1,
            "source_sha256": source_digest,
            "prosody": {},
            "commentary": {},
        }

    prosody_cache: dict = loaded.get("prosody") or {}
    commentary_cache: dict = loaded.get("commentary") or {}

    def _chunk_key(para_id: int, text: str) -> str:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"{para_id}:{digest}"

    def _para_key(para_id: int, text: str) -> str:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"{para_id}:{digest}"

    # ── 1. Planejamento de prosódia para os chunks verbatim ──────────────────
    from .narration import NarrationChunk

    narration_chunks = [NarrationChunk(i + 1, text) for i, (_, text) in enumerate(para_chunks)]
    cached_prosody = {
        i + 1
        for i, (para_id, text) in enumerate(para_chunks)
        if isinstance(prosody_cache.get(_chunk_key(para_id, text)), dict)
        and isinstance(prosody_cache[_chunk_key(para_id, text)].get("direction"), str)
    }
    tracker.stage(
        "planejamento de interpretação",
        total=len(narration_chunks),
        current=len(cached_prosody),
    )
    missing_prosody = [c for c in narration_chunks if c.index not in cached_prosody]
    completed = len(cached_prosody)
    for batch in prosody_batches(missing_prosody):
        tracker.checkpoint()
        planned = parse_prosody_plan(
            analyze_prosody(prosody_prompt(batch)), {c.index for c in batch}
        )
        for chunk in batch:
            para_id, text = para_chunks[chunk.index - 1]
            key = _chunk_key(para_id, text)
            prosody_cache[key] = {"direction": planned.get(chunk.index) or fallback_direction(text)}
        completed += len(batch)
        _save_json(path, loaded)
        tracker.advance(completed)

    # ── 2. Geração de comentários reflexivos por parágrafo ───────────────────
    unique_paras = list(
        dict.fromkeys(
            (para_id, para)
            for para_id, para in [(pid, paragraphs[pid - 1]) for pid, _ in para_chunks]
        )
    )
    cached_commentary = {
        para_id
        for para_id, para_text in unique_paras
        if isinstance(commentary_cache.get(_para_key(para_id, para_text)), dict)
        and isinstance(commentary_cache[_para_key(para_id, para_text)].get("commentary"), str)
    }
    missing_commentary = [(pid, text) for pid, text in unique_paras if pid not in cached_commentary]
    tracker.stage(
        "geração de comentários reflexivos",
        total=len(unique_paras),
        current=len(cached_commentary),
    )
    completed = len(cached_commentary)
    for batch in reflexive_batches(missing_commentary):
        tracker.checkpoint()
        batch_ids = {pid for pid, _ in batch}
        generated = parse_reflexive_commentary(
            analyze_reflexive(reflexive_prompt(batch, settings.language)),
            batch_ids,
        )
        for para_id, para_text in batch:
            key = _para_key(para_id, para_text)
            commentary_cache[key] = {
                "commentary": generated.get(para_id) or fallback_commentary(settings.language)
            }
        completed += len(batch)
        _save_json(path, loaded)
        tracker.advance(completed)

    # ── 3. Montagem dos turnos ───────────────────────────────────────────────
    narrator = settings.presenters[0]
    lang = settings.language
    turns: list[dict] = []

    for i, (para_id, chunk_text) in enumerate(para_chunks):
        direction = prosody_cache[_chunk_key(para_id, chunk_text)]["direction"]
        turns.append(
            {
                "turn_id": f"R{len(turns) + 1:05d}",
                "speaker": narrator.speaker,
                "text": chunk_text,
                "instructions": tts_direction(direction, narrator.style, lang),
                "kind": "verbatim",
            }
        )
        # Adiciona o comentário somente ao final do último chunk de cada parágrafo.
        is_last_chunk_of_para = i == len(para_chunks) - 1 or para_chunks[i + 1][0] != para_id
        if is_last_chunk_of_para:
            para_text = paragraphs[para_id - 1]
            commentary = commentary_cache[_para_key(para_id, para_text)]["commentary"]
            commentary_instructions = commentary_direction(narrator.style, lang)
            turns.append(
                {
                    "turn_id": f"R{len(turns) + 1:05d}",
                    "speaker": narrator.speaker,
                    "text": commentary,
                    "instructions": commentary_instructions,
                    "kind": "commentary",
                }
            )

    # Os turnos verbatim precisam reproduzir os trechos originais na ordem exata;
    # só os comentários podem ser texto novo.
    verbatim_texts = [t["text"] for t in turns if t.get("kind") == "verbatim"]
    if verbatim_texts != [text for _, text in para_chunks]:
        raise AssertionError("A montagem reflexiva alterou o texto original.")

    _save_json(
        directory / "reflexive.json",
        {
            "version": 1,
            "source_sha256": source_digest,
            "prosody": prosody_cache,
            "commentary": commentary_cache,
            "turns": turns,
        },
    )
    return turns


def _report_audit(coverage: dict, audit: dict) -> None:
    criticality = {i["id"]: i.get("criticality", "contextual") for i in coverage.get("items", [])}
    problems = [
        r
        for r in audit.get("results", [])
        if r.get("status") in ("ausente", "distorcido", "parcial")
        and criticality.get(r.get("coverage_id"), "contextual") in ("critica", "importante")
    ]
    if problems:
        print(f"   ⚠ {len(problems)} itens críticos/importantes com pendência:")
        for problem in problems[:10]:
            print(
                f"     - {problem['coverage_id']} [{problem['status']}]: "
                f"{problem.get('notes', '')[:120]}"
            )
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


def _segment_fingerprint(settings: Settings, text: str, voice: str, instructions: str) -> str:
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


def _is_empty_audio_error(error: openrouter.OpenRouterError) -> bool:
    """Identifica a resposta de TTS sem áudio, que repetir não resolve."""
    return "vazia ou curta demais" in str(error)


def _is_key_exhaustion_error(error: openrouter.OpenRouterError) -> bool:
    message = str(error).lower()
    return error.status_code == 402 or (error.status_code == 403 and "limit" in message)


def _exhaustion_label(error: openrouter.OpenRouterError) -> str:
    if error.status_code == 402:
        return "sem saldo na conta"
    return "sem limite"


def _chat_with_key_fallback(
    settings: Settings,
    model: str,
    system: str,
    prompt: str,
    tracker: GenerationTracker,
) -> openrouter.ChatResult:
    current_label = tracker.key_source or "chave atual"
    candidates = api_key_candidates(settings, current_label=current_label) or [
        (current_label, settings)
    ]
    for key_index, (key_label, candidate) in enumerate(candidates):
        tracker.using_key(key_label)
        try:
            return openrouter.chat_json(candidate, model, system, prompt)
        except openrouter.OpenRouterError as error:
            if _is_key_exhaustion_error(error) and key_index + 1 < len(candidates):
                reason = _exhaustion_label(error)
                print(
                    f"    ↪ {key_label} {reason}; tentando {candidates[key_index + 1][0]}.",
                    flush=True,
                )
                continue
            raise
    raise RuntimeError("Nenhuma chave OpenRouter disponível para a chamada de texto.")


@dataclass(frozen=True)
class _SynthesisResult:
    speech: openrouter.SpeechResult
    settings: Settings
    key_label: str


def _synthesize_with_retry(
    settings: Settings,
    text: str,
    voice: str,
    instructions: str,
    segment_number: int,
    tracker: GenerationTracker,
) -> _SynthesisResult:
    policy = RetryPolicy(
        max_attempts=settings.tts_retry_attempts,
        base_delay_seconds=settings.tts_retry_base_seconds,
        max_delay_seconds=settings.tts_retry_max_seconds,
    )
    current_label = tracker.key_source or "chave atual"
    candidates = api_key_candidates(settings, current_label=current_label) or [
        (current_label, settings)
    ]
    last_error: openrouter.OpenRouterError | None = None
    for key_index, (key_label, candidate) in enumerate(candidates):
        # Publica a chave antes da chamada: o painel precisa mostrar qual limite
        # está sendo consumido inclusive enquanto a requisição estiver pendente.
        tracker.using_key(key_label)
        for attempt in range(1, policy.max_attempts + 1):
            tracker.checkpoint()
            try:
                speech = openrouter.text_to_speech(
                    candidate,
                    text,
                    voice,
                    instructions=instructions,
                )
                return _SynthesisResult(speech, candidate, key_label)
            except openrouter.OpenRouterError as error:
                last_error = error
                if _is_key_exhaustion_error(error) and key_index + 1 < len(candidates):
                    next_label = candidates[key_index + 1][0]
                    reason = _exhaustion_label(error)
                    print(
                        f"\n   ↪ {key_label} {reason}; tentando {next_label} "
                        f"na fala {segment_number}.",
                        flush=True,
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


def _synthesize_turns(
    settings: Settings,
    directory: Path,
    turns: list[dict],
    tracker: GenerationTracker,
    trust_legacy_segments: bool = True,
    source_key: str = "conteudo",
    item_id: str | None = None,
    generation_mode: str = "adaptation",
) -> list[Path]:
    voices = {p.speaker: p for p in settings.presenters}
    default = settings.presenters[0]
    segments_dir = directory / "segments"
    segments_dir.mkdir(exist_ok=True)
    extension = "wav" if settings.tts_format == "pcm" else settings.tts_format
    manifest_path = directory / "segments.json"
    loaded_manifest = _load_json(manifest_path)
    if loaded_manifest is not None and not isinstance(loaded_manifest, dict):
        raise ValueError("segments.json inválido: era esperado um objeto JSON.")
    manifest = loaded_manifest or {"version": ARTIFACT_SCHEMA_VERSION, "segments": {}}
    entries = manifest.get("segments")
    if not isinstance(entries, dict):
        raise ValueError("segments.json inválido: campo 'segments' ausente ou inválido.")

    resolved_item_id = item_id or directory.name.replace("__", "/")
    manifest.update(
        {
            "version": ARTIFACT_SCHEMA_VERSION,
            "source_key": source_key,
            "episode_id": resolved_item_id,
            "generation_mode": generation_mode,
        }
    )
    plans: list[dict] = []
    completed = 0
    for index, turn in enumerate(turns, 1):
        if (
            not isinstance(turn, dict)
            or not isinstance(turn.get("text"), str)
            or not turn["text"].strip()
        ):
            raise ValueError(f"Turno {index} inválido no roteiro.")
        speaker = turn.get("speaker")
        presenter = voices.get(speaker, default)
        segment = segments_dir / segment_audio_filename(
            source_key,
            resolved_item_id,
            generation_mode,
            index,
            len(turns),
            presenter.speaker,
            extension,
        )
        legacy_segment = segments_dir / f"{index:03d}_{presenter.speaker}.{extension}"
        if not segment.exists() and legacy_segment.is_file():
            legacy_segment.replace(segment)
            legacy_entry = entries.pop(legacy_segment.name, None)
            if isinstance(legacy_entry, dict):
                entries[segment.name] = legacy_entry
        supplied_instructions = turn.get("instructions")
        if supplied_instructions is not None and (
            not isinstance(supplied_instructions, str) or len(supplied_instructions) > 2_000
        ):
            raise ValueError(f"Instrução de interpretação inválida no turno {index}.")
        instructions = supplied_instructions or podcast_direction(
            presenter.style, settings.language
        )
        fingerprint = _segment_fingerprint(
            settings,
            turn["text"],
            presenter.voice,
            instructions,
        )
        entry = entries.get(segment.name)
        entry_matches = isinstance(entry, dict) and entry.get("fingerprint") == fingerprint
        legacy_entry = (
            entry is None or (isinstance(entry, dict) and not entry.get("fingerprint"))
        ) and trust_legacy_segments
        reusable = _valid_segment(segment) and (entry_matches or legacy_entry)
        if reusable:
            completed += 1
            preserved = entry.copy() if isinstance(entry, dict) else {}
            preserved.update(
                {
                    "fingerprint": fingerprint,
                    "bytes": segment.stat().st_size,
                    "kind": "chunk",
                    "chunk_index": index,
                    "chunk_total": len(turns),
                    "speaker": presenter.speaker,
                }
            )
            entries[segment.name] = preserved
        plans.append(
            {
                "index": index,
                "turn": turn,
                "presenter": presenter,
                "segment": segment,
                "instructions": instructions,
                "fingerprint": fingerprint,
                "reusable": reusable,
            }
        )

    # Importa segmentos legados para o manifesto antes de qualquer nova chamada.
    _save_json(manifest_path, manifest)
    tracker.stage("tts", total=len(turns), current=completed)

    paths = [plan["segment"] for plan in plans]
    skipped: list[int] = []
    for plan in plans:
        tracker.checkpoint()
        index = plan["index"]
        segment = plan["segment"]
        if plan["reusable"]:
            continue
        presenter = plan["presenter"]
        cost_label = f"US$ {tracker.cost_usd:.3f}"
        _progress_bar(index, len(turns), f"{presenter.speaker} ({presenter.voice}) {cost_label}")
        try:
            synthesis = _synthesize_with_retry(
                settings,
                plan["turn"]["text"],
                presenter.voice,
                plan["instructions"],
                index,
                tracker,
            )
        except openrouter.OpenRouterError as error:
            # Alguns trechos são impronunciáveis para o modelo (rodapés de
            # diagramação, nomes de arquivo, marcas de página que sobram na
            # extração). O erro é determinístico: já esgotou as tentativas, e
            # abortar aqui jogaria fora todo o áudio pago até agora.
            if not _is_empty_audio_error(error):
                raise
            skipped.append(index)
            paths.remove(segment)
            entries.pop(segment.name, None)
            print(
                f"\n   ⚠ Fala {index} pulada: o TTS não gerou áudio para este trecho "
                f"({plan['turn']['text'].strip()[:60]!r}).",
                flush=True,
            )
            completed += 1
            tracker.advance(completed)
            continue
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
        duration_seconds = media_duration_seconds(segment)
        cost_exact = False
        segment_cost = 0.0
        if speech.generation_id:
            try:
                segment_cost = openrouter.generation_cost_usd(speech_settings, speech.generation_id)
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
            "kind": "chunk",
            "chunk_index": index,
            "chunk_total": len(turns),
            "speaker": presenter.speaker,
            "generation_id": speech.generation_id,
            "key_label": synthesis.key_label,
            "cost_usd": round(segment_cost, 8),
            "cost_exact": cost_exact,
        }
        _save_json(manifest_path, manifest)
        completed += 1
        tracker.advance(completed)
    if skipped:
        _save_json(manifest_path, manifest)
        print(
            f"\n⚠ {len(skipped)} fala(s) sem áudio foram puladas "
            f"(fala {', '.join(str(i) for i in skipped)}); o episódio segue sem esses trechos.",
            flush=True,
        )
    if not paths:
        raise ValueError(
            "Nenhuma fala gerou áudio: o texto não tem conteúdo que o TTS consiga pronunciar."
        )
    return paths


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


def _assemble(
    directory: Path,
    segments: list[Path],
    item: ContentItem,
    background_music: Path | None = None,
    background_volume: float = 0.08,
    background_music_name: str | None = None,
    *,
    source_key: str = "conteudo",
    generation_mode: str = "adaptation",
) -> Path:
    if not segments:
        raise ValueError("Não há segmentos de áudio para montar o episódio.")
    concat_list = directory / "segments.txt"
    concat_list.write_text("".join(_concat_line(p) for p in segments), encoding="utf-8")
    item_id = getattr(item, "item_id", None) or directory.name.replace("__", "/")
    final_path = directory / final_audio_filename(source_key, item_id, generation_mode)
    legacy_final = directory / LEGACY_FINAL_AUDIO
    if not final_path.exists() and legacy_final.is_file():
        legacy_final.replace(final_path)
    temporary = final_path.with_name(f"{final_path.stem}.tmp.mp3")
    temporary.unlink(missing_ok=True)
    try:
        arguments = [
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
        ]
        if background_music:
            if not background_music.is_file():
                raise ValueError("A música de fundo selecionada não está mais disponível.")
            if not 0.01 <= background_volume <= 0.25:
                raise ValueError("O volume da música precisa ficar entre 1% e 25%.")
            arguments.extend(
                [
                    "-stream_loop",
                    "-1",
                    "-i",
                    str(background_music),
                    "-filter_complex",
                    (
                        f"[1:a]volume={background_volume:.4f}[music];"
                        "[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[mixed];"
                        "[mixed]loudnorm=I=-16:TP=-1.5:LRA=11[out]"
                    ),
                    "-map",
                    "[out]",
                ]
            )
        else:
            arguments.extend(["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"])
        arguments.extend(
            [
                "-metadata",
                f"title={item.title}",
                "-metadata",
                "artist=Audiofy Content AI",
                "-metadata",
                f"comment={item.attribution}",
                "-codec:a",
                "libmp3lame",
                "-b:a",
                "128k",
                str(temporary),
            ]
        )
        run_tool("ffmpeg", arguments, timeout=_FFMPEG_TIMEOUT)
        temporary.replace(final_path)
        legacy_final.unlink(missing_ok=True)
        mix_path = directory / "mix.json"
        if background_music:
            digest = hashlib.sha256()
            with background_music.open("rb") as audio:
                for block in iter(lambda: audio.read(1024 * 1024), b""):
                    digest.update(block)
            _save_json(
                mix_path,
                {
                    "version": 1,
                    "background_music": background_music_name or background_music.name,
                    "background_sha256": digest.hexdigest(),
                    "background_volume": background_volume,
                    "mix_duration": "narration",
                },
            )
        else:
            mix_path.unlink(missing_ok=True)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return final_path


def _write_show_notes(
    directory: Path,
    item: ContentItem,
    cost_usd: float,
    cost_exact: bool,
    generation_mode: str = "adaptation",
    background_music: str | None = None,
    background_volume: float | None = None,
) -> None:
    if generation_mode == "verbatim":
        production_note = (
            "Leitura fiel gerada com inteligência artificial; o texto falado foi segmentado "
            "sem reescrita e a direção vocal está em `prosody.json`."
        )
    elif generation_mode == "reflexive":
        production_note = (
            "Leitura reflexiva gerada com inteligência artificial; o texto foi lido integralmente "
            "e comentários breves foram intercalados entre os parágrafos. "
            "O plano de leitura está em `reflexive.json`."
        )
    else:
        production_note = (
            "Adaptação em áudio gerada com inteligência artificial; revise `audit.json` "
            "antes de publicar."
        )
    music_note = ""
    if background_music and background_volume is not None:
        music_note = (
            f"\n\nMúsica de fundo: `{background_music}` a {background_volume:.0%}. "
            "Confirme os direitos de uso antes de publicar."
        )
    (directory / "NOTES.md").write_text(
        f"# {item.title}\n\n"
        f"{item.attribution}\n\n"
        f"{production_note} Fonte original: {item.url}\n\n"
        f"Custo de geração registrado: US$ {cost_usd:.4f} "
        f"({'exato por geração' if cost_exact else 'aproximado'}){music_note}\n",
        encoding="utf-8",
    )
