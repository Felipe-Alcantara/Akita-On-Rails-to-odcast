#!/usr/bin/env python3
"""Porta de entrada do Audiofy Content AI.

Uso:
    python3 start_app.py             # menu interativo (recomendado)
    python3 start_app.py list|sync|status|setup|catalog
    python3 start_app.py search <termos>
    python3 start_app.py generate <item-id | número da listagem> [--bg]
    python3 start_app.py watch <item-id>
    python3 start_app.py abort <item-id>
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from audiofy.config import EPISODES_DIR, Settings  # noqa: E402
from audiofy.runtime.status import GenerationTracker  # noqa: E402
from audiofy.sources import get_source  # noqa: E402

SOURCE_KEY = "akita"  # fonte padrão do menu; outras fontes via bridge/registro

BOLD, DIM, GREEN, YELLOW, RED, CYAN, RESET = (
    "\033[1m", "\033[2m", "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[0m"
)


def _ok(message: str) -> None:
    print(f"  {GREEN}✔{RESET} {message}")


def _warn(message: str) -> None:
    print(f"  {YELLOW}⚠{RESET} {message}")


def _fail(message: str) -> None:
    print(f"  {RED}✖{RESET} {message}")


# ── Setup, configuração e status ────────────────────────────────────────────

def do_setup() -> None:
    """Verifica dependências, instala o módulo akita-articles e cria o .env."""
    print(f"\n{BOLD}Verificando dependências…{RESET}")
    for binary, hint in (("git", "instale via gerenciador de pacotes"),
                         ("ffmpeg", "necessário para montar o áudio")):
        _ok(f"{binary} encontrado") if shutil.which(binary) else _fail(
            f"{binary} não encontrado — {hint}")
    try:
        import requests  # noqa: F401
        _ok("biblioteca requests disponível")
    except ImportError:
        _fail("biblioteca requests ausente — rode: pip install requests")

    try:
        import akita_articles  # noqa: F401
        _ok("módulo akita-articles disponível")
    except ImportError:
        _warn("módulo akita-articles ausente — instalando…")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--user",
             "git+https://github.com/Felipe-Alcantara/akita-articles"],
            text=True,
        )
        _ok("akita-articles instalado") if result.returncode == 0 else _fail(
            "instalação falhou — instale manualmente (ver README)")

    env_path = PROJECT_ROOT / ".env"
    if not env_path.is_file():
        shutil.copy(PROJECT_ROOT / ".env.example", env_path)
        _warn("Criei .env a partir do exemplo — preencha a OPENROUTER_API_KEY "
              "(https://openrouter.ai/keys).")
    elif Settings().api_key:
        _ok("OPENROUTER_API_KEY configurada")
    else:
        _warn("Arquivo .env existe, mas OPENROUTER_API_KEY está vazia.")


def do_configure() -> None:
    """Grava a chave do OpenRouter no .env de forma interativa."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.is_file():
        shutil.copy(PROJECT_ROOT / ".env.example", env_path)
    key = input("Cole sua OPENROUTER_API_KEY (Enter para manter a atual): ").strip()
    if not key:
        print("Nada alterado.")
        return
    lines = [line for line in env_path.read_text(encoding="utf-8").splitlines()
             if not line.startswith("OPENROUTER_API_KEY=")]
    lines.insert(0, f"OPENROUTER_API_KEY={key}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _ok("Chave gravada no .env (arquivo ignorado pelo Git).")


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
    _ok("Chave configurada") if settings.api_key else _warn("OPENROUTER_API_KEY ausente")
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
            print(f"     {status['episode_id']} — etapa {status.get('stage')}"
                  f" {progress.get('current', 0)}/{progress.get('total', 0)}"
                  f" — US$ {status.get('cost_usd', 0):.4f}")
        print(f"     {DIM}Acompanhe (watch) ou aborte (abort) pelo menu.{RESET}")
    else:
        _ok("Nenhuma geração em segundo plano — nada consumindo créditos agora")

    episodes = sorted(EPISODES_DIR.glob("*/episode.mp3")) if EPISODES_DIR.is_dir() else []
    _ok(f"{len(episodes)} episódio(s) finalizado(s) em {EPISODES_DIR}")
    for episode in episodes:
        status = GenerationTracker.load(episode.parent) or {}
        cost = f" — US$ {status.get('cost_usd', 0):.4f}" if status else ""
        print(f"      {DIM}{episode.parent.name}{cost}{RESET}")
    presenters = ", ".join(f"{p.speaker}:{p.voice}" for p in settings.presenters)
    print(f"  {DIM}Modelos: roteiro={settings.text_model} | auditoria={settings.audit_model} | "
          f"tts={settings.tts_model}{RESET}")
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
            answer = input(
                f"{DIM}— Enter continua, q para, ou digite o número para gerar —{RESET} "
            ).strip().lower()
            if answer == "q":
                break
            if answer.isdigit():
                do_generate(answer)
                return
    print()


def do_search(query: str) -> None:
    ensure_synced()
    hits = get_source(SOURCE_KEY).search(query)
    print(f"\n{BOLD}{len(hits)} resultado(s) para \"{query}\":{RESET}\n")
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


def do_generate(selector: str, force: bool = False, background: bool = False) -> None:
    ensure_synced()
    item_id = _resolve_item_id(selector)
    if item_id is None:
        _fail(f"Item '{selector}' não encontrado (use o número da listagem ou o id).")
        return
    item = get_source(SOURCE_KEY).get_item(item_id)

    settings = Settings()
    try:
        settings.require_api_key()
    except RuntimeError as error:
        _fail(str(error))
        return

    estimated = 0.60 * item.words / 2200  # razão medida no episódio piloto
    presenters = ", ".join(f"{p.speaker} ({p.voice})" for p in settings.presenters)
    print(f"\n{BOLD}Item:{RESET}     {item.title}")
    print(f"{BOLD}URL:{RESET}      {item.url}")
    print(f"{BOLD}Tamanho:{RESET}  ~{item.words} palavras de prosa")
    print(f"{BOLD}Vozes:{RESET}    {presenters}")
    print(f"{YELLOW}Custo estimado: ~US$ {estimated:.2f} "
          f"(razão real medida: US$ 0,60 ≈ 13 min ≈ 2200 palavras).{RESET}")
    if input("Continuar? [s/N] ").strip().lower() not in ("s", "sim", "y"):
        print("Cancelado.")
        return

    if background:
        result = subprocess.run(
            [sys.executable, "-m", "audiofy.bridge", "generate", SOURCE_KEY, item_id],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
            env={**__import__("os").environ, "PYTHONPATH": "src"},
        )
        payload = json.loads(result.stdout or "{}")
        if payload.get("started"):
            _ok(f"Geração iniciada em segundo plano. Log: {payload['log']}")
            print(f"  {DIM}Acompanhe com watch, aborte com abort. O Status sempre mostra o "
                  f"que está consumindo créditos.{RESET}")
            do_watch(item_id)
        else:
            _fail(f"Não iniciou: {payload.get('reason') or payload.get('error')}")
        return

    from audiofy.pipeline import generate_episode
    from audiofy.runtime.status import GenerationAborted

    try:
        generate_episode(settings, item, force=force)
    except GenerationAborted:
        _warn("Geração abortada a pedido. Artefatos preservados; gere de novo para retomar.")
    except Exception as error:  # noqa: BLE001 — o menu reporta e preserva artefatos parciais
        _fail(f"Falha: {error}")
        print(f"{DIM}Artefatos parciais preservados; rode novamente para retomar.{RESET}")
        sys.exit(1)


def do_watch(selector: str) -> None:
    """Acompanha ao vivo uma geração: etapa, progresso, custo. Ctrl+C sai (não aborta)."""
    from audiofy.pipeline import episode_dir
    item_id = _resolve_item_id(selector) or selector
    directory = episode_dir(item_id)
    print(f"{DIM}Acompanhando {item_id} — Ctrl+C sai do acompanhamento "
          f"(NÃO aborta a geração).{RESET}")
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
                bar = f"[{'█' * filled}{'░' * (24 - filled)}] " \
                      f"{progress.get('current', 0)}/{total} "
            line = (f"{status['state']} | {status.get('stage', '')} {bar}"
                    f"| US$ {status.get('cost_usd', 0):.4f}")
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
        print(f"\n{DIM}Saí do acompanhamento; a geração continua. "
              f"Use abort para cancelar de verdade.{RESET}")


def do_abort(selector: str) -> None:
    from audiofy.pipeline import episode_dir
    item_id = _resolve_item_id(selector) or selector
    directory = episode_dir(item_id)
    status = GenerationTracker.load(directory)
    if not status or status.get("state") != "rodando":
        _warn("Nenhuma geração rodando para este item.")
        return
    GenerationTracker.request_abort(directory)
    _ok("Abort solicitado — efetiva no próximo segmento (nada é corrompido).")


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
    print(f"\n{DIM}Exemplo: AUDIOFY_PRESENTERS=\"ana:Kore:animada, beto:Puck:cético\"{RESET}")


def do_desktop() -> None:
    """Abre a interface Electron (instala as dependências na primeira vez)."""
    electron_dir = PROJECT_ROOT / "electron"
    if not shutil.which("npm"):
        _fail("npm não encontrado — instale Node.js para usar o app desktop.")
        return
    if not (electron_dir / "node_modules" / "electron").is_dir():
        print(f"{CYAN}Instalando dependências do app (primeira vez)…{RESET}")
        subprocess.run(["npm", "install", "--no-fund", "--no-audit"], cwd=electron_dir)
    subprocess.Popen(["npm", "start"], cwd=electron_dir, start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _ok("App desktop iniciado em outra janela.")


def menu() -> None:
    while True:
        running = _running_generations()
        alert = (f"\n  {YELLOW}⚡ {len(running)} geração(ões) em andamento — "
                 f"consumindo créditos! (opção 8 acompanha, 9 aborta){RESET}"
                 if running else "")
        print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════╗
║              🎙️  Audiofy Content AI                        ║
╚══════════════════════════════════════════════════════════╝{RESET}{alert}
  {BOLD}1{RESET} — 🛠️  Instalar / Setup     {DIM}dependências, akita-articles, .env{RESET}
  {BOLD}2{RESET} — 🔑 Configurar chave      {DIM}grava a OPENROUTER_API_KEY{RESET}
  {BOLD}3{RESET} — 🔄 Sincronizar fonte     {DIM}atualiza os artigos do Akita{RESET}
  {BOLD}4{RESET} — 📚 Listar itens          {DIM}digite o número para gerar direto{RESET}
  {BOLD}5{RESET} — 🔍 Buscar                {DIM}por título, slug ou tag{RESET}
  {BOLD}6{RESET} — 🎙️  Gerar episódio       {DIM}ao vivo, com barra e custo em US${RESET}
  {BOLD}7{RESET} — 🚀 Gerar em 2º plano     {DIM}libera o terminal; watch acompanha{RESET}
  {BOLD}8{RESET} — 👀 Acompanhar geração    {DIM}progresso e custo ao vivo{RESET}
  {BOLD}9{RESET} — 🛑 Abortar geração       {DIM}para no próximo segmento{RESET}
 {BOLD}10{RESET} — 🎛️  Catálogo TTS/vozes   {DIM}modelos e vozes para configurar{RESET}
 {BOLD}11{RESET} — 📊 Status                {DIM}mostra o que está gastando créditos{RESET}
 {BOLD}12{RESET} — 🖥️  Abrir app desktop    {DIM}interface Electron (npm start){RESET}
  {BOLD}0{RESET} — 🚪 Sair
""")
        choice = input(f"{BOLD}Opção:{RESET} ").strip()
        if choice == "1":
            do_setup()
        elif choice == "2":
            do_configure()
        elif choice == "3":
            do_sync()
        elif choice == "4":
            do_list()
        elif choice == "5":
            if query := input("Buscar por: ").strip():
                do_search(query)
        elif choice in ("6", "7"):
            selector = input("Número da listagem ou id do item: ").strip()
            if selector:
                do_generate(selector, background=choice == "7")
        elif choice == "8":
            if selector := input("Id do item (ou número): ").strip():
                do_watch(selector)
        elif choice == "9":
            if selector := input("Id do item (ou número): ").strip():
                do_abort(selector)
        elif choice == "10":
            do_catalog()
        elif choice == "11":
            do_status()
        elif choice == "12":
            do_desktop()
        elif choice in ("0", "q"):
            if _running_generations():
                _warn("Atenção: ainda há geração em segundo plano consumindo créditos.")
            return
        else:
            _warn("Opção inválida.")


def main() -> None:
    # Saída em tempo real mesmo quando redirecionada para arquivo/pipe (tail -f).
    sys.stdout.reconfigure(line_buffering=True)
    args = sys.argv[1:]
    simple = {"list": do_list, "sync": do_sync, "status": do_status,
              "setup": do_setup, "catalog": do_catalog}
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
    elif args[0] == "watch" and len(args) >= 2:
        do_watch(args[1])
    elif args[0] == "abort" and len(args) >= 2:
        do_abort(args[1])
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
