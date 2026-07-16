#!/usr/bin/env python3
"""Porta de entrada do Akita on Rails to Podcast.

Uso:
    python3 start_app.py             # menu interativo (recomendado)
    python3 start_app.py list        # lista artigos
    python3 start_app.py generate <artigo-id | número da listagem>
    python3 start_app.py sync|status|setup
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from akita_podcast.config import Settings, SOURCE_REPO_DIR, EPISODES_DIR  # noqa: E402

BOLD, DIM, GREEN, YELLOW, RED, CYAN, RESET = (
    "\033[1m", "\033[2m", "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[0m"
)


def _ok(message: str) -> None:
    print(f"  {GREEN}✔{RESET} {message}")


def _warn(message: str) -> None:
    print(f"  {YELLOW}⚠{RESET} {message}")


def _fail(message: str) -> None:
    print(f"  {RED}✖{RESET} {message}")


# ── Setup e status ──────────────────────────────────────────────────────────

def do_setup() -> None:
    """Verifica dependências e cria o .env a partir do .env.example."""
    print(f"\n{BOLD}Verificando dependências…{RESET}")
    checks_ok = True
    for binary, hint in (("git", "instale via gerenciador de pacotes"),
                         ("ffmpeg", "necessário para montar o áudio")):
        if shutil.which(binary):
            _ok(f"{binary} encontrado")
        else:
            _fail(f"{binary} não encontrado — {hint}")
            checks_ok = False
    try:
        import requests  # noqa: F401
        _ok("biblioteca requests disponível")
    except ImportError:
        _fail("biblioteca requests ausente — rode: pip install requests")
        checks_ok = False

    env_path = PROJECT_ROOT / ".env"
    if not env_path.is_file():
        shutil.copy(PROJECT_ROOT / ".env.example", env_path)
        _warn(f"Criei {env_path.name} a partir do exemplo — edite e preencha a "
              f"OPENROUTER_API_KEY (https://openrouter.ai/keys).")
    elif Settings().api_key:
        _ok("OPENROUTER_API_KEY configurada")
    else:
        _warn("Arquivo .env existe, mas OPENROUTER_API_KEY está vazia.")
    if checks_ok:
        print(f"\n{GREEN}Setup concluído.{RESET}")


def do_configure() -> None:
    """Grava a chave do OpenRouter no .env de forma interativa."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.is_file():
        shutil.copy(PROJECT_ROOT / ".env.example", env_path)
    key = input("Cole sua OPENROUTER_API_KEY (Enter para manter a atual): ").strip()
    if not key:
        print("Nada alterado.")
        return
    lines = env_path.read_text(encoding="utf-8").splitlines()
    lines = [line for line in lines if not line.startswith("OPENROUTER_API_KEY=")]
    lines.insert(0, f"OPENROUTER_API_KEY={key}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _ok("Chave gravada no .env (arquivo ignorado pelo Git).")


def do_status() -> None:
    print(f"\n{BOLD}Status do projeto{RESET}")
    settings = Settings()
    _ok("Chave configurada") if settings.api_key else _warn("OPENROUTER_API_KEY ausente")
    if (SOURCE_REPO_DIR / "content").is_dir():
        commit = subprocess.run(
            ["git", "-C", str(SOURCE_REPO_DIR), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True,
        ).stdout.strip()
        from akita_podcast.source_repo import list_articles
        _ok(f"Blog sincronizado (commit {commit}, {len(list_articles())} artigos)")
    else:
        _warn("Blog ainda não sincronizado (opção Sincronizar)")
    episodes = sorted(EPISODES_DIR.glob("*/episode.mp3")) if EPISODES_DIR.is_dir() else []
    _ok(f"{len(episodes)} episódio(s) finalizado(s) em {EPISODES_DIR}")
    for episode in episodes:
        print(f"      {DIM}{episode.parent.name}{RESET}")
    print(f"  {DIM}Modelos: roteiro={settings.text_model} | auditoria={settings.audit_model} | "
          f"tts={settings.tts_model}{RESET}")


# ── Fluxo principal ─────────────────────────────────────────────────────────

def do_sync() -> None:
    from akita_podcast.source_repo import sync_repo
    print(f"{CYAN}Sincronizando repositório do blog…{RESET}")
    commit = sync_repo()
    _ok(f"Repositório atualizado no commit {commit[:12]}")


def ensure_synced() -> None:
    if not (SOURCE_REPO_DIR / "content").is_dir():
        do_sync()


def do_list(page_size: int = 30) -> None:
    from akita_podcast.source_repo import list_articles
    ensure_synced()
    articles = list_articles()
    print(f"\n{BOLD}{len(articles)} artigos encontrados (mais recentes primeiro):{RESET}\n")
    for index, article in enumerate(articles, 1):
        print(f"  {DIM}{index:4d}.{RESET} {article.date}  {article.title}")
        if index % page_size == 0 and index < len(articles):
            answer = input(f"{DIM}— Enter para continuar, q para parar —{RESET} ").strip().lower()
            if answer == "q":
                break
    print()


def do_generate(selector: str, force: bool = False) -> None:
    from akita_podcast.source_repo import list_articles
    ensure_synced()
    articles = list_articles()
    article = None
    if selector.isdigit():
        index = int(selector)
        if 1 <= index <= len(articles):
            article = articles[index - 1]
    else:
        article = next((a for a in articles if a.article_id == selector), None)
    if article is None:
        _fail(f"Artigo '{selector}' não encontrado. Use o número da listagem "
              f"ou o id no formato AAAA-MM-DD/slug.")
        return

    settings = Settings()
    try:
        settings.require_api_key()
    except RuntimeError as error:
        _fail(str(error))
        return

    words = len(article.path.read_text(encoding="utf-8", errors="replace").split())
    print(f"\n{BOLD}Artigo:{RESET}  {article.title}")
    print(f"{BOLD}URL:{RESET}     {article.canonical_url}")
    print(f"{BOLD}Tamanho:{RESET} ~{words} palavras")
    print(f"{BOLD}Modelos:{RESET} roteiro={settings.text_model} | "
          f"auditoria={settings.audit_model} | tts={settings.tts_model}")
    print(f"{YELLOW}A geração consome créditos do OpenRouter "
          f"(ordem de US$ 0,30–1,10 por episódio).{RESET}")
    if input("Continuar? [s/N] ").strip().lower() not in ("s", "sim", "y"):
        print("Cancelado.")
        return

    from akita_podcast.pipeline import generate_episode

    try:
        generate_episode(settings, article, force=force)
    except Exception as error:  # noqa: BLE001 — o menu reporta e preserva artefatos parciais
        _fail(f"Falha: {error}")
        print(f"{DIM}Artefatos parciais foram preservados; rode novamente para retomar "
              f"de onde parou.{RESET}")
        sys.exit(1)


def menu() -> None:
    while True:
        print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════╗
║            🎙️  Akita on Rails to Podcast                  ║
╚══════════════════════════════════════════════════════════╝{RESET}
  {BOLD}1{RESET} — 🛠️  Instalar / Setup       {DIM}verifica dependências e cria o .env{RESET}
  {BOLD}2{RESET} — 🔑 Configurar chave        {DIM}grava a OPENROUTER_API_KEY{RESET}
  {BOLD}3{RESET} — 🔄 Sincronizar blog        {DIM}clona/atualiza os artigos do Akita{RESET}
  {BOLD}4{RESET} — 📚 Listar artigos          {DIM}mais recentes primeiro, paginado{RESET}
  {BOLD}5{RESET} — 🎙️  Gerar episódio         {DIM}matriz → roteiro → auditoria → áudio{RESET}
  {BOLD}6{RESET} — ♻️  Regerar do zero        {DIM}ignora artefatos salvos do episódio{RESET}
  {BOLD}7{RESET} — 📊 Status                  {DIM}chave, sincronização e episódios{RESET}
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
        elif choice in ("5", "6"):
            selector = input("Número do artigo na listagem (ou id AAAA-MM-DD/slug): ").strip()
            if selector:
                do_generate(selector, force=choice == "6")
        elif choice == "7":
            do_status()
        elif choice in ("0", "q"):
            return
        else:
            _warn("Opção inválida.")


def main() -> None:
    # Saída em tempo real mesmo quando redirecionada para arquivo/pipe (tail -f).
    sys.stdout.reconfigure(line_buffering=True)
    args = sys.argv[1:]
    commands = {"list": do_list, "sync": do_sync, "status": do_status, "setup": do_setup}
    if not args:
        try:
            menu()
        except (KeyboardInterrupt, EOFError):
            print("\nAté mais!")
    elif args[0] in commands:
        commands[args[0]]()
    elif args[0] == "generate" and len(args) >= 2:
        do_generate(args[1], force="--force" in args)
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
