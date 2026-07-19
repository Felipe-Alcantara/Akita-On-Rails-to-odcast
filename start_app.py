#!/usr/bin/env python3
"""Porta de entrada do Audiofy Content AI.

Uso:
    python3 start_app.py             # menu interativo (recomendado)
    python3 start_app.py list|sync|status|setup|catalog|chat|keys|profiles
    python3 start_app.py search <termos>
    python3 start_app.py add-url <url>
    python3 start_app.py generate <item-id | número da listagem> [--bg]
    python3 start_app.py narrate <item-id | número> [--voice=Sulafat] [--bg]
    python3 start_app.py watch <item-id>
    python3 start_app.py abort <item-id>
    python3 start_app.py notebooklm <item-id>
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from audiofy.config import EPISODES_DIR, Settings, desktop_environment  # noqa: E402
from audiofy.runtime.status import GenerationTracker  # noqa: E402
from audiofy.sources import get_source  # noqa: E402

SOURCE_KEY = "custom"  # fonte ativa do menu (trocável); "custom" = qualquer conteúdo
_TUI = None

BOLD, DIM, GREEN, YELLOW, RED, CYAN, RESET = (
    "\033[1m",
    "\033[2m",
    "\033[92m",
    "\033[93m",
    "\033[91m",
    "\033[96m",
    "\033[0m",
)


def _ok(message: str) -> None:
    print(f"  {GREEN}✔{RESET} {message}")


def _warn(message: str) -> None:
    print(f"  {YELLOW}⚠{RESET} {message}")


def _fail(message: str) -> None:
    print(f"  {RED}✖{RESET} {message}")


def _safe_call(action, *args, **kwargs) -> None:
    """Executa uma ação do menu sem derrubar a porta de entrada com traceback cru."""
    try:
        action(*args, **kwargs)
    except Exception as error:  # noqa: BLE001 — fronteira da interface com o usuário
        _fail(str(error))


def _tui():
    """Carrega a TUI e prepara suas dependências na primeira execução."""
    global _TUI
    if _TUI is None:
        from audiofy.setup import ensure_tui

        action = ensure_tui()
        if action and not action["ok"]:
            raise RuntimeError("Não foi possível preparar o menu interativo: " + action["detail"])
        from audiofy import tui

        _TUI = tui
    return _TUI


# ── Setup, configuração e status ────────────────────────────────────────────


def do_setup() -> None:
    """Verifica dependências, instala o módulo akita-articles e cria o .env."""
    from audiofy.setup import apply_setup

    print(f"\n{BOLD}Verificando dependências…{RESET}")
    report = apply_setup()
    for action in report["actions"]:
        (_ok if action["ok"] else _fail)(f"{action['name']}: {action['detail']}")
    for check in report["checks"]:
        if check["ok"]:
            _ok(f"{check['name']} disponível")
        elif check["required"]:
            _fail(f"{check['name']} ausente — {check['hint']}")
        else:
            _warn(f"{check['name']} indisponível — {check['hint']}")


def do_keys() -> None:
    """Registra, seleciona, verifica e remove chaves sem expor seus valores."""
    import os

    from audiofy.config import api_key_source, environment_key_source, key_store
    from audiofy.keystore import ENV_VAR
    from audiofy.providers.openrouter import check_api_key_value

    store = key_store()
    while True:
        keys = store.list_keys()
        effective = api_key_source() or "nenhuma"
        print(
            f"\n{BOLD}Chaves do OpenRouter{RESET} "
            f"{DIM}— {len(keys)} cadastrada(s); em uso: {effective}{RESET}"
        )
        environment_source = environment_key_source()
        if environment_source:
            marker = f"{GREEN}● em uso{RESET}" if effective == environment_source else " "
            print(f"  {'OPENROUTER_API_KEY':<20} {DIM}{environment_source}{RESET} {marker}")
        if not keys:
            _warn("Nenhuma chave no cofre.")
        for named in keys:
            marker = f"{GREEN}● em uso{RESET}" if named.name == effective else " "
            print(f"  {named.name:<20} {DIM}{named.masked}{RESET} {marker}")
        choice = _tui().choose(
            "O que deseja fazer?",
            [
                ("➕ Registrar chave — guarda uma nova chave nomeada", "add"),
                ("✅ Usar / trocar chave — escolhe a origem efetiva", "use"),
                ("🔎 Verificar chave — valida e consulta limite/saldo", "check"),
                ("🗑️ Remover chave — exclui do cofre local", "remove"),
                ("↩ Voltar ao menu principal", "back"),
            ],
        )
        if choice == "add":
            name = (_tui().text("Nome da chave:") or "").strip()
            key = (_tui().secret("Chave do OpenRouter (sk-or-…):") or "").strip()
            try:
                store.add(name, key)
                _ok(f"Chave '{name}' guardada.")
                if _tui().confirm(f"Usar a chave '{name}' agora?", default=True):
                    store.set_active(name)
                    _ok(f"'{name}' agora é a chave efetiva.")
            except ValueError as error:
                _fail(str(error))
        elif choice in {"use", "check"}:
            options = [(named.name, ("named", named.name)) for named in keys]
            if environment_source:
                options.insert(
                    0,
                    (f"OPENROUTER_API_KEY ({environment_source})", ("environment", "")),
                )
            if not options:
                _warn("Nenhuma chave disponível; registre uma chave primeiro.")
                continue
            selected = _tui().choose(
                "Qual origem deseja usar?" if choice == "use" else "Qual chave deseja verificar?",
                options,
            )
            if not selected:
                continue
            source_kind, name = selected
            if choice == "use":
                if source_kind == "environment":
                    store.use_environment()
                    _ok(f"{environment_source} agora é a origem efetiva.")
                else:
                    store.set_active(name)
                    _ok(f"'{name}' agora é a chave efetiva.")
            else:
                value = (
                    os.environ.get(ENV_VAR, "")
                    if source_kind == "environment"
                    else store.get(name).key
                )
                available, detail = check_api_key_value(value)
                (_ok if available else _warn)(detail)
        elif choice == "remove":
            if not keys:
                _warn("Nenhuma chave cadastrada para remover.")
                continue
            name = _tui().choose(
                "Qual chave deseja remover?", [(named.name, named.name) for named in keys]
            )
            if name and _tui().confirm(f"Remover permanentemente a chave '{name}'?"):
                store.remove(name)
                _ok("Chave removida.")
        elif choice in ("back", None):
            return


def _pick_model(
    settings: Settings, label: str, current: str, modality: str | tuple[str, ...] | None = None
) -> str:
    """Escolha em dois passos (empresa → modelo, com preço), padrão Openia."""
    from audiofy.catalog import load_models, models_of, vendors

    try:
        models = load_models(settings)
    except Exception as error:  # noqa: BLE001 — sem catálogo, mantém o atual
        _warn(f"Não consegui carregar o catálogo ({error}); mantendo {current}.")
        return current
    companies = vendors(models)
    vendor = _tui().choose(
        f"{label} — escolha a empresa (atual: {current})",
        [(company, company) for company in companies] + [("Manter modelo atual", "")],
    )
    if not vendor:
        return current
    options = models_of(models, vendor, modality)
    if not options:
        _warn("Nenhum modelo dessa empresa (para essa modalidade).")
        return current
    return (
        _tui().choose(
            f"{label} — escolha o modelo",
            [(f"{model.id}  ·  {model.price_line}", model.id) for model in options]
            + [("Manter modelo atual", current)],
            default=current,
        )
        or current
    )


def do_profiles() -> None:
    """Perfis nomeados: modelos + apresentadores, com troca e criação."""
    from audiofy.config import profile_store
    from audiofy.profiles import Profile

    store = profile_store()
    while True:
        print(f"\n{BOLD}Perfis de geração{RESET} {DIM}(env AUDIOFY_* tem prioridade){RESET}")
        for profile in store.list_profiles():
            marker = f"{GREEN}● ativo{RESET}" if profile.name == store.active().name else " "
            print(f"  {profile.name:<16} {marker}  {DIM}{profile.description}{RESET}")
            print(
                f"    {DIM}roteiro={profile.text_model} | auditoria={profile.audit_model}"
                f" | tts={profile.tts_model}{RESET}"
            )
            if profile.text_provider != "openrouter":
                from audiofy.providers.subscription import configured_model

                detected = configured_model(profile.text_provider) or "padrão da CLI"
                print(f"    {DIM}texto via {profile.text_provider}: {detected}{RESET}")
            print(f"    {DIM}apresentadores: {profile.presenters_spec}{RESET}")
        choice = _tui().choose(
            "O que deseja fazer?",
            [
                ("✅ Trocar perfil ativo", "activate"),
                ("➕ Criar novo perfil", "new"),
                ("🗑️ Remover perfil customizado", "remove"),
                ("↩ Voltar ao menu principal", "back"),
            ],
        )
        if choice == "activate":
            name = _tui().choose(
                "Qual perfil deseja ativar?",
                [(profile.name, profile.name) for profile in store.list_profiles()],
            )
            if not name:
                continue
            try:
                store.set_active(name)
                _ok(f"Perfil ativo: {store.active().name}")
            except LookupError as error:
                _fail(str(error))
        elif choice == "new":
            name = (_tui().text("Nome do novo perfil:") or "").strip()
            if not name:
                continue
            base = store.active()
            settings = Settings()
            from audiofy.providers.subscription import SUBSCRIPTION_CLIS

            providers = [("OpenRouter — API, custo por token", "openrouter")]
            providers.extend(
                (f"{cli.name} — custo US$ 0", cli.key)
                for cli in SUBSCRIPTION_CLIS
                if cli.is_available()
            )
            provider = (
                _tui().choose(
                    "Provedor das etapas de texto:",
                    providers,
                    default=base.text_provider,
                )
                or base.text_provider
            )
            if provider == "openrouter":
                text_model = _pick_model(settings, "Modelo do roteiro", base.text_model)
                audit_model = _pick_model(settings, "Modelo da auditoria", base.audit_model)
            else:
                text_model = audit_model = "(assinatura)"
            tts_model = _pick_model(
                settings,
                "Modelo TTS",
                base.tts_model,
                modality=("speech", "audio"),
            )
            spec = (
                _tui().text("Apresentadores:", default=base.presenters_spec) or base.presenters_spec
            ).strip()
            try:
                from audiofy.presenters import parse_presenters

                parse_presenters(spec)  # valida antes de salvar
                description = (_tui().text("Descrição curta:") or "").strip()
                store.save(
                    Profile(
                        name,
                        text_model,
                        audit_model,
                        tts_model,
                        spec,
                        description,
                        text_provider=provider,
                    )
                )
                store.set_active(name)
                _ok(f"Perfil '{name}' criado e ativado.")
            except ValueError as error:
                _fail(str(error))
        elif choice == "remove":
            removable = [
                profile for profile in store.list_profiles() if store.is_custom(profile.name)
            ]
            name = _tui().choose(
                "Qual perfil deseja remover?",
                [(profile.name, profile.name) for profile in removable],
            )
            if name and _tui().confirm(f"Remover o perfil '{name}'?"):
                try:
                    store.remove(name)
                    _ok("Perfil removido.")
                except ValueError as error:
                    _fail(str(error))
        elif choice in ("back", None):
            return


def _running_generations() -> list[dict]:
    running = []
    if EPISODES_DIR.is_dir():
        for directory in EPISODES_DIR.iterdir():
            status = GenerationTracker.load(directory) if directory.is_dir() else None
            if status and status.get("state") == "rodando":
                status["dir"] = directory
                running.append(status)
    return running


def do_status() -> None:
    print(f"\n{BOLD}Status do Audiofy{RESET}")
    settings = Settings()
    from audiofy.config import api_key_source
    from audiofy.setup import inspect_setup

    print(f"\n{BOLD}Ambiente{RESET}")
    if sys.prefix != sys.base_prefix:
        _ok(f"Ambiente virtual ativo ({sys.prefix})")
    else:
        _warn("Ambiente virtual não está ativo (o menu ainda pode funcionar)")
    if (PROJECT_ROOT / ".env").is_file():
        _ok("Arquivo .env presente")
    else:
        _warn("Arquivo .env ausente — use Instalar / Setup para criá-lo")
    for check in inspect_setup():
        if check.key == "openrouter-key":
            continue
        if check.ok:
            _ok(f"{check.name} disponível")
        elif check.required:
            _fail(f"{check.name} ausente — {check.hint}")
        else:
            _warn(f"{check.name} indisponível — {check.hint}")

    print(f"\n{BOLD}Configuração e execução{RESET}")
    if settings.api_key:
        _ok(f"Chave configurada ({api_key_source() or 'origem desconhecida'})")
    else:
        _warn("Nenhuma chave configurada (menu Configurar → Chaves e verificação)")
    provider_note = (
        "assinatura: " + settings.text_provider
        if settings.text_provider not in ("", "openrouter")
        else "openrouter (API)"
    )
    print(f"  {DIM}Perfil ativo: {settings.profile_name} — texto via {provider_note}{RESET}")
    if settings.text_provider not in ("", "openrouter"):
        from audiofy.providers.subscription import configured_model

        model = configured_model(settings.text_provider) or "padrão da CLI"
        print(f"  {DIM}Modelo efetivo da assinatura: {model}{RESET}")
    source = get_source(SOURCE_KEY)
    if source.is_ready():
        _ok(f"Fonte '{source.name}' sincronizada ({len(source.list_items())} itens)")
    else:
        _warn(f"Fonte '{source.name}' ainda não sincronizada (opção Sincronizar)")

    running = _running_generations()
    if running:
        print(f"\n  {YELLOW}{BOLD}⚡ GERAÇÃO EM ANDAMENTO (consumindo créditos):{RESET}")
        for status in running:
            progress = status.get("progress", {})
            print(
                f"     {status['episode_id']} — etapa {status.get('stage')}"
                f" {progress.get('current', 0)}/{progress.get('total', 0)}"
                f" — US$ {status.get('cost_usd', 0):.4f}"
            )
        print(f"     {DIM}Use Acompanhar geração ou Abortar geração pelo menu.{RESET}")
    else:
        _ok("Nenhuma geração em segundo plano — nada consumindo créditos agora")

    episodes = sorted(EPISODES_DIR.glob("*/episode.mp3")) if EPISODES_DIR.is_dir() else []
    _ok(f"{len(episodes)} episódio(s) finalizado(s) em {EPISODES_DIR}")
    for episode in episodes:
        status = GenerationTracker.load(episode.parent) or {}
        cost = f" — US$ {status.get('cost_usd', 0):.4f}" if status else ""
        print(f"      {DIM}{episode.parent.name}{cost}{RESET}")
    presenters = ", ".join(f"{p.speaker}:{p.voice}" for p in settings.presenters)
    print(
        f"  {DIM}Modelos: roteiro={settings.text_model} | auditoria={settings.audit_model} | "
        f"tts={settings.tts_model}{RESET}"
    )
    print(f"  {DIM}Apresentadores: {presenters}{RESET}")


# ── Fonte de conteúdo ────────────────────────────────────────────────────────


def do_sync() -> None:
    print(f"{CYAN}Sincronizando fonte '{SOURCE_KEY}'…{RESET}")
    version = get_source(SOURCE_KEY).sync()
    _ok(f"Fonte atualizada (versão {version[:12]})")


def ensure_synced() -> None:
    if not get_source(SOURCE_KEY).is_ready():
        do_sync()


def do_list(page_size: int = 30) -> None:
    ensure_synced()
    items = get_source(SOURCE_KEY).list_items()
    print(f"\n{BOLD}{len(items)} itens (mais recentes primeiro):{RESET}\n")
    for index, item in enumerate(items, 1):
        print(f"  {DIM}{index:4d}.{RESET} {item.published_at}  {item.title}")
        if index % page_size == 0 and index < len(items):
            action = _tui().choose(
                f"Exibidos {index} de {len(items)} itens. O que deseja fazer?",
                [
                    ("Continuar a listagem", "continue"),
                    ("Gerar um episódio — informar número ou ID", "generate"),
                    ("Encerrar a listagem", "stop"),
                ],
            )
            if action in ("stop", None):
                break
            if action == "generate":
                selector = (_tui().text("Número da listagem ou ID do item:") or "").strip()
                if selector:
                    do_generate(selector)
                    return
    print()


def do_search(query: str) -> None:
    ensure_synced()
    hits = get_source(SOURCE_KEY).search(query)
    print(f'\n{BOLD}{len(hits)} resultado(s) para "{query}":{RESET}\n')
    for index, item in enumerate(hits[:50], 1):
        print(f"  {DIM}{index:3d}.{RESET} {item.item_id}  {item.title}")
    print()


# ── Geração ──────────────────────────────────────────────────────────────────


def _resolve_item_id(selector: str) -> str | None:
    source = get_source(SOURCE_KEY)
    if selector.isdigit():
        items = source.list_items()
        index = int(selector)
        if 1 <= index <= len(items):
            return items[index - 1].item_id
        return None
    try:
        return source.get_item(selector).item_id
    except LookupError:
        return None


def do_generate(
    selector: str,
    force: bool = False,
    background: bool = False,
    generation_mode: str = "adaptation",
    narration_voice: str | None = None,
) -> None:
    ensure_synced()
    item_id = _resolve_item_id(selector)
    if item_id is None:
        _fail(f"Item '{selector}' não encontrado (use o número da listagem ou o id).")
        return
    item = get_source(SOURCE_KEY).get_item(item_id)

    settings = Settings()
    if generation_mode == "verbatim":
        from dataclasses import replace

        from audiofy.presenters import Presenter
        from audiofy.providers.openrouter import GEMINI_VOICES

        if narration_voice is None:
            narration_voice = _tui().choose(
                "Escolha o narrador:",
                [(f"{voice} — {style}", voice) for voice, style in GEMINI_VOICES.items()],
                default=(
                    settings.presenters[0].voice if len(settings.presenters) == 1 else "Sulafat"
                ),
            )
        if narration_voice not in GEMINI_VOICES:
            _fail("Escolha uma voz de narrador disponível no catálogo Gemini.")
            return
        settings = replace(
            settings,
            presenters=[Presenter("narrador", narration_voice, GEMINI_VOICES[narration_voice])],
        )
    try:
        settings.require_api_key()
    except RuntimeError as error:
        _fail(str(error))
        return

    from audiofy.estimates import estimate_episode

    estimate = estimate_episode(item.words, settings.tts_model, profile_name=settings.profile_name)
    presenters = ", ".join(f"{p.speaker} ({p.voice})" for p in settings.presenters)
    print(f"\n{BOLD}Item:{RESET}     {item.title}")
    print(f"{BOLD}URL:{RESET}      {item.url}")
    print(f"{BOLD}Tamanho:{RESET}  ~{item.words} palavras de prosa")
    print(f"{BOLD}Vozes:{RESET}    {presenters}")
    if generation_mode == "verbatim":
        print(
            f"{BOLD}Formato:{RESET}  leitura fiel — texto preservado; "
            "a IA planeja apenas a interpretação em lotes"
        )
    basis = (
        f"{estimate.sample_count} episódio(s) medido(s)"
        if estimate.sample_count
        else "piloto medido"
    )
    print(
        f"{YELLOW}Estimativa: ~US$ {estimate.cost_usd:.2f} "
        f"(faixa US$ {estimate.cost_min_usd:.2f}–{estimate.cost_max_usd:.2f}) · "
        f"~{estimate.duration_minutes:.1f} min · {basis}.{RESET}"
    )
    if not _tui().confirm("Continuar e consumir créditos?", default=False):
        print("Cancelado.")
        return

    if background:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "audiofy.bridge",
                "generate",
                SOURCE_KEY,
                item_id,
                f"--mode={generation_mode}",
                *([f"--voice={narration_voice}"] if narration_voice else []),
                *(["--force"] if force else []),
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
            env={**__import__("os").environ, "PYTHONPATH": "src"},
        )
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            _fail((result.stderr or "A bridge não retornou uma resposta válida.")[:300])
            return
        if payload.get("started"):
            _ok(f"Geração iniciada em segundo plano. Log: {payload['log']}")
            print(
                f"  {DIM}Acompanhe com watch, aborte com abort. O Status sempre mostra o "
                f"que está consumindo créditos.{RESET}"
            )
            do_watch(item_id)
        else:
            _fail(f"Não iniciou: {payload.get('reason') or payload.get('error')}")
        return

    from audiofy.pipeline import generate_episode
    from audiofy.runtime.status import GenerationAborted

    try:
        generate_episode(
            settings,
            item,
            force=force,
            generation_mode=generation_mode,
            narration_voice=narration_voice,
        )
    except GenerationAborted:
        _warn("Geração abortada a pedido. Artefatos preservados; gere de novo para retomar.")
    except Exception as error:  # noqa: BLE001 — o menu reporta e preserva artefatos parciais
        _fail(f"Falha: {error}")
        print(
            f"{DIM}As tentativas automáticas terminaram. Os segmentos concluídos e o custo "
            f"foram preservados; gere novamente para continuar do checkpoint.{RESET}"
        )
        sys.exit(1)


def do_watch(selector: str) -> None:
    """Acompanha ao vivo uma geração: etapa, progresso, custo. Ctrl+C sai (não aborta)."""
    from audiofy.pipeline import episode_dir

    item_id = _resolve_item_id(selector) or selector
    directory = episode_dir(item_id)
    print(
        f"{DIM}Acompanhando {item_id} — Ctrl+C sai do acompanhamento (NÃO aborta a geração).{RESET}"
    )
    try:
        while True:
            status = GenerationTracker.load(directory)
            if status is None:
                _warn("Sem status para este item.")
                return
            progress = status.get("progress", {})
            total = progress.get("total", 0)
            bar = ""
            if total:
                filled = int(24 * progress.get("current", 0) / total)
                bar = f"[{'█' * filled}{'░' * (24 - filled)}] {progress.get('current', 0)}/{total} "
            line = (
                f"{status['state']} | {status.get('stage', '')} {bar}"
                f"| US$ {status.get('cost_usd', 0):.4f}"
            )
            retry = status.get("retry")
            if retry:
                line += (
                    f" | retomando fala {retry['segment']} "
                    f"({retry['attempt']}/{retry['max_attempts']})"
                )
            print(f"\r\033[K  {line}", end="", flush=True)
            if status["state"] != "rodando":
                print()
                if status["state"] == "concluido":
                    _ok(f"Episódio pronto: {directory / 'episode.mp3'}")
                else:
                    _warn(f"Estado final: {status['state']}")
                return
            time.sleep(2)
    except KeyboardInterrupt:
        print(
            f"\n{DIM}Saí do acompanhamento; a geração continua. "
            f"Use abort para cancelar de verdade.{RESET}"
        )


def do_abort(selector: str) -> None:
    from audiofy.pipeline import episode_dir

    item_id = _resolve_item_id(selector) or selector
    directory = episode_dir(item_id)
    status = GenerationTracker.load(directory)
    if not status or status.get("state") != "rodando":
        _warn("Nenhuma geração rodando para este item.")
        return
    accepted, stopped = GenerationTracker.abort_running(directory)
    if not accepted:
        _warn("A geração terminou antes do pedido de abort.")
    elif stopped:
        _ok("Geração abortada agora. O checkpoint e os artefatos concluídos foram preservados.")
    else:
        _warn("Abort registrado; aguardando o primeiro checkpoint disponível.")


def do_switch_source() -> None:
    """Troca a fonte ativa do menu."""
    global SOURCE_KEY
    from audiofy.sources import available_sources

    sources = available_sources()
    choice = _tui().choose(
        "Escolha a fonte ativa:",
        [(f"{source.name} — {source.description}", source.key) for source in sources],
        default=SOURCE_KEY,
    )
    if choice:
        SOURCE_KEY = choice
        _ok(f"Fonte ativa: {SOURCE_KEY}")


def do_add_url(url: str) -> None:
    """Adiciona uma página como conteúdo próprio (fonte 'custom')."""
    from audiofy.sources.custom import CustomSource

    try:
        item_id = CustomSource().add_url(url)
        _ok(f"Conteúdo adicionado: {item_id} (fonte 'custom')")
    except Exception as error:  # noqa: BLE001 — rede/extração reportadas ao usuário
        _fail(str(error))


def do_add_text() -> None:
    """Adiciona conteúdo colado pela interface interativa."""
    from audiofy.sources.custom import CustomSource

    title = (_tui().text("Título:") or "").strip()
    if not title:
        return
    content = (_tui().multiline_text("Cole o conteúdo:") or "").strip()
    if content:
        item_id = CustomSource().add_text(title, content)
        _ok(f"Conteúdo adicionado: {item_id} (fonte 'custom')")


def _run_chat_action(action: dict) -> None:
    global SOURCE_KEY
    kind = action.get("tipo")
    if kind == "adicionar_texto":
        from audiofy.sources.custom import CustomSource

        item_id = CustomSource().add_text(action.get("titulo", ""), action.get("texto", ""))
        _ok(f"Conteúdo criado: {item_id}")
    elif kind == "adicionar_url":
        do_add_url(action.get("url", ""))
    elif kind == "buscar":
        hits = get_source(action.get("fonte", SOURCE_KEY)).search(action.get("termos", ""))
        for item in hits[:10]:
            print(f"  {item.item_id}  {DIM}{item.title}{RESET}")
    elif kind == "gerar":
        previous, SOURCE_KEY = SOURCE_KEY, action.get("fonte", SOURCE_KEY)
        try:
            do_generate(action.get("item_id", ""))
        finally:
            SOURCE_KEY = previous
    elif kind == "exportar_notebooklm":
        from audiofy.export import export_notebooklm_pack

        item = get_source(action.get("fonte", SOURCE_KEY)).get_item(action.get("item_id", ""))
        _ok(f"Pacote NotebookLM: {export_notebooklm_pack(item)}")
    else:
        _warn(f"Ação desconhecida: {kind}")


def do_chat() -> None:
    """Chat de pesquisa: qualquer tema, com ações executáveis (Enter vazio sai)."""
    from audiofy.chat import ChatSession

    session = ChatSession("principal")
    settings = Settings()
    provider = (
        settings.text_provider
        if settings.text_provider not in ("", "openrouter")
        else f"API ({settings.text_model})"
    )
    print(
        f"\n{BOLD}💬 Chat de pesquisa{RESET} {DIM}— via {provider}; "
        f"'limpar' zera a conversa; Enter vazio sai.{RESET}"
    )
    while True:
        try:
            message = (_tui().text("Você:") or "").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return
        if not message:
            return
        if message.lower() == "limpar":
            session.clear()
            _ok("Conversa limpa.")
            continue
        print(f"{DIM}… pesquisando{RESET}")
        try:
            text, actions = session.send(message, settings)
        except Exception as error:  # noqa: BLE001 — falha de provedor vai ao usuário
            _fail(str(error))
            continue
        print(f"\n{CYAN}{BOLD}Audiofy:{RESET} {text}")
        # O chat age sozinho: cada ação proposta roda automaticamente, sem pedir aprovação.
        for action in actions:
            print(f"  {YELLOW}⚡{RESET} {action.get('descricao', action['tipo'])}")
            _safe_call(_run_chat_action, action)


def do_notebooklm(selector: str) -> None:
    """Prepara o pacote NotebookLM (caminho de custo zero na assinatura Google)."""
    ensure_synced()
    item_id = _resolve_item_id(selector)
    if item_id is None:
        _fail(f"Item '{selector}' não encontrado.")
        return
    from audiofy.export import export_notebooklm_pack

    item = get_source(SOURCE_KEY).get_item(item_id)
    pack = export_notebooklm_pack(item)
    _ok(f"Pacote pronto em {pack}")
    print(
        f"  {DIM}Abra o instrucoes.md dessa pasta: upload do fonte.md no "
        f"notebooklm.google.com, foco sugerido incluído. Custo: US$ 0,00.{RESET}"
    )


def do_catalog() -> None:
    """Lista modelos TTS do OpenRouter e as vozes do Gemini para configurar."""
    from audiofy.providers.openrouter import GEMINI_VOICES, list_tts_models

    settings = Settings()
    try:
        settings.require_api_key()
        models = list_tts_models(settings)
        print(f"\n{BOLD}Modelos com saída de áudio no OpenRouter:{RESET}")
        for model in models:
            print(f"  {model['id']}  {DIM}{model['name']}{RESET}")
    except RuntimeError as error:
        _warn(f"Sem chave para consultar modelos ao vivo ({error}).")
    print(f"\n{BOLD}Vozes do Gemini TTS (use em AUDIOFY_PRESENTERS):{RESET}")
    for voice, style in GEMINI_VOICES.items():
        print(f"  {voice:<16} {DIM}{style}{RESET}")
    print(f'\n{DIM}Exemplo: AUDIOFY_PRESENTERS="ana:Kore:animada, beto:Puck:cético"{RESET}')


def do_configure() -> None:
    """Centraliza as escolhas de configuração acessíveis pela porta principal."""
    while True:
        choice = _tui().choose(
            "O que deseja configurar?",
            [
                ("🔑 Chaves e verificação — credenciais locais do OpenRouter", "keys"),
                ("👤 Perfis e modelos — provedor, modelos e vozes", "profiles"),
                ("🎛️ Catálogo TTS/vozes — opções disponíveis", "catalog"),
                ("↩ Voltar ao menu principal", "back"),
            ],
        )
        if choice == "keys":
            _safe_call(do_keys)
        elif choice == "profiles":
            _safe_call(do_profiles)
        elif choice == "catalog":
            _safe_call(do_catalog)
        elif choice in ("back", None):
            return


def _npm_command() -> list[str] | None:
    """Mantém o resolvedor compartilhado acessível à porta de entrada."""
    from audiofy.setup import npm_command

    return npm_command()


def _electron_executable(electron_dir: Path) -> Path | None:
    """Binário real do Electron instalado — dispensa o ``npm start`` (e o cmd.exe)."""
    package = electron_dir / "node_modules" / "electron"
    path_txt = package / "path.txt"
    if path_txt.is_file():
        candidate = package / "dist" / path_txt.read_text(encoding="utf-8").strip()
        if candidate.exists():
            return candidate
    return None


def do_desktop() -> None:
    """Abre a interface Electron (instala as dependências na primeira vez)."""
    electron_dir = PROJECT_ROOT / "electron"
    npm = _npm_command()
    if not npm:
        _fail("npm não encontrado — instale Node.js para usar o app desktop.")
        return
    if not (electron_dir / "node_modules" / "electron").is_dir():
        print(f"{CYAN}Instalando dependências do app (primeira vez)…{RESET}")
        try:
            result = subprocess.run(
                [*npm, "ci", "--no-fund", "--no-audit"],
                cwd=electron_dir,
                capture_output=True,
                text=True,
            )
        except OSError as error:
            _fail(f"Não foi possível executar o npm ({npm[0]}): {error}")
            return
        if result.returncode != 0:
            _fail(f"Falha ao instalar o Electron: {(result.stderr or result.stdout)[-300:]}")
            return
    environment = desktop_environment(prefer_dotenv=True)
    # O Electron chama o backend com este interpretador — o mesmo que já roda o menu.
    environment.setdefault("AUDIOFY_PYTHON", sys.executable)
    detach: dict = (
        {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
        if sys.platform == "win32"
        else {"start_new_session": True}
    )
    electron = _electron_executable(electron_dir)
    command = [str(electron), "."] if electron else [*npm, "start"]
    print(f"  {DIM}Comando: {' '.join(command)}{RESET}")
    try:
        subprocess.Popen(
            command,
            cwd=electron_dir,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **detach,
        )
    except OSError as error:
        _fail(f"Não foi possível iniciar o app desktop ({command[0]}): {error}")
        return
    _ok("App desktop iniciado em outra janela.")


def menu() -> None:
    while True:
        running = _running_generations()
        _tui().show_header(SOURCE_KEY, len(running))
        choice = _tui().choose(
            "O que deseja fazer?",
            [
                ("▶️ Iniciar / Rodar — abra o chat e execute ações propostas", "chat"),
                ("➕ Adicionar conteúdo — importe uma URL ou cole um texto", "add"),
                ("🧭 Trocar fonte — conteúdo próprio, Akita on Rails…", "source"),
                ("📚 Listar itens — consulte o catálogo da fonte ativa", "list"),
                ("🔍 Buscar — encontre conteúdo na fonte ativa", "search"),
                ("🎙️ Gerar episódio — acompanhe progresso e custo ao vivo", "generate"),
                (
                    "📖 Leitura fiel — narre livro/fanfic sem reescrever o texto",
                    "narrate",
                ),
                ("🚀 Gerar em segundo plano — libera o terminal", "generate-bg"),
                ("👀 Acompanhar geração — veja progresso e custo", "watch"),
                ("🛑 Abortar geração agora — preserva o checkpoint", "abort"),
                ("📓 Exportar para NotebookLM — prepara pacote de custo zero", "notebooklm"),
                ("⚙️ Configurar — ajuste chaves, perfis, modelos e vozes", "configure"),
                ("🔄 Sincronizar fonte — atualiza o conteúdo disponível", "sync"),
                ("📊 Status — mostra ambiente, modelos e gerações", "status"),
                ("🛠️ Instalar / Setup — prepara todas as dependências", "setup"),
                ("🖥️ Abrir app desktop — inicia a interface Electron", "desktop"),
                ("🚪 Sair do Audiofy", "exit"),
            ],
        )
        if choice == "chat":
            _safe_call(do_chat)
        elif choice == "add":
            mode = _tui().choose(
                "Como deseja adicionar o conteúdo?",
                [
                    ("🌐 Importar uma URL pública", "url"),
                    ("📝 Colar texto no terminal", "text"),
                    ("↩ Cancelar", None),
                ],
            )
            if mode == "url":
                if url := (_tui().text("URL pública:") or "").strip():
                    _safe_call(do_add_url, url)
            elif mode == "text":
                _safe_call(do_add_text)
        elif choice == "source":
            _safe_call(do_switch_source)
        elif choice == "list":
            _safe_call(do_list)
        elif choice == "search":
            if query := (_tui().text("Buscar por:") or "").strip():
                _safe_call(do_search, query)
        elif choice in ("generate", "generate-bg"):
            selector = (_tui().text("Número da listagem ou ID do item:") or "").strip()
            if selector:
                _safe_call(do_generate, selector, background=choice == "generate-bg")
        elif choice == "narrate":
            selector = (_tui().text("Número da listagem ou ID do texto:") or "").strip()
            if selector:
                background = _tui().confirm(
                    "Gerar em segundo plano? Recomendado para livros e textos longos.",
                    default=True,
                )
                _safe_call(
                    do_generate,
                    selector,
                    background=background,
                    generation_mode="verbatim",
                )
        elif choice == "watch":
            if selector := (_tui().text("ID do item (ou número):") or "").strip():
                _safe_call(do_watch, selector)
        elif choice == "abort":
            if (
                selector := (_tui().text("ID do item (ou número):") or "").strip()
            ) and _tui().confirm(f"Solicitar o abort da geração '{selector}'?"):
                _safe_call(do_abort, selector)
        elif choice == "notebooklm":
            if selector := (_tui().text("Número da listagem ou ID do item:") or "").strip():
                _safe_call(do_notebooklm, selector)
        elif choice == "configure":
            _safe_call(do_configure)
        elif choice == "sync":
            _safe_call(do_sync)
        elif choice == "status":
            _safe_call(do_status)
        elif choice == "setup":
            _safe_call(do_setup)
        elif choice == "desktop":
            _safe_call(do_desktop)
        elif choice in ("exit", None):
            if _running_generations():
                _warn("Atenção: ainda há geração em segundo plano consumindo créditos.")
            return


def main() -> None:
    # Saída em tempo real mesmo quando redirecionada para arquivo/pipe (tail -f).
    sys.stdout.reconfigure(line_buffering=True)
    args = sys.argv[1:]
    simple = {
        "list": do_list,
        "sync": do_sync,
        "status": do_status,
        "setup": do_setup,
        "catalog": do_catalog,
        "keys": do_keys,
        "profiles": do_profiles,
    }
    if not args:
        try:
            menu()
        except (KeyboardInterrupt, EOFError):
            print("\nAté mais!")
    elif args[0] in simple:
        simple[args[0]]()
    elif args[0] == "search" and len(args) >= 2:
        do_search(" ".join(args[1:]))
    elif args[0] == "generate" and len(args) >= 2:
        do_generate(args[1], force="--force" in args, background="--bg" in args)
    elif args[0] == "narrate" and len(args) >= 2:
        voice = next(
            (
                argument.partition("=")[2]
                for argument in args[2:]
                if argument.startswith("--voice=")
            ),
            None,
        )
        do_generate(
            args[1],
            force="--force" in args,
            background="--bg" in args,
            generation_mode="verbatim",
            narration_voice=voice,
        )
    elif args[0] == "watch" and len(args) >= 2:
        do_watch(args[1])
    elif args[0] == "abort" and len(args) >= 2:
        do_abort(args[1])
    elif args[0] == "notebooklm" and len(args) >= 2:
        do_notebooklm(args[1])
    elif args[0] == "chat":
        do_chat()
    elif args[0] == "add-url" and len(args) >= 2:
        do_add_url(args[1])
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
