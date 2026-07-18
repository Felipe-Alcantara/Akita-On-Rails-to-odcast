"""Chat de pesquisa do Audiofy.

Assistente conversacional para pesquisar temas (qualquer assunto, não só uma
fonte específica), avaliar conteúdos e comandar o programa. As respostas podem
conter ações estruturadas em blocos ```acao — a interface (CLI ou app) mostra
e executa cada ação com um clique, pela mesma bridge de sempre.

Provedor: a CLI de assinatura configurada (custo zero; no Claude Code a
pesquisa na web é liberada via WebSearch) ou a API do OpenRouter.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from pathlib import Path

from .config import DATA_DIR, Settings
from .security import validate_identifier

CHAT_DIR = DATA_DIR / "chat"

SYSTEM_PROMPT = """Você é o assistente do Audiofy Content AI, um programa que transforma
conteúdo em podcasts auditáveis. Responda sempre em português brasileiro, de forma direta.

AJA, NÃO PERGUNTE. Quando o usuário pedir um tema, pesquise e ENTREGUE o conteúdo pronto na
mesma resposta — não peça confirmação, não pergunte "quer que eu faça?", não devolva perguntas
esclarecedoras a menos que o pedido seja realmente impossível de interpretar. O usuário quer o
resultado, não um plano. Se tiver acesso a pesquisa na web, use-a para reunir informações atuais
com as fontes e então redija você mesmo um texto próprio, coeso e substancial sobre o tema (não
copie páginas na íntegra: sintetize com suas palavras), e adicione-o aos conteúdos.

Para adicionar o que você pesquisou e escreveu, inclua ao final um bloco de ação. Formato
(um JSON por bloco):

```acao
{"tipo": "adicionar_texto", "titulo": "Título do conteúdo", "texto": "Texto completo…", "descricao": "Adicionar conteúdo pesquisado"}
```

Tipos disponíveis:
- adicionar_texto {titulo, texto} — guarda um texto que VOCÊ escreveu como conteúdo gerável.
  Use este para entregar o que pesquisou. O texto deve ser autossuficiente, com vários
  parágrafos, pronto para virar um episódio.
- adicionar_url {url} — baixa uma página existente e guarda o texto como conteúdo gerável
- buscar {fonte, termos} — busca itens já salvos numa fonte ("akita" ou "custom")
- gerar {fonte, item_id} — inicia a geração de um episódio (consome créditos; sempre avise)
- exportar_notebooklm {fonte, item_id} — prepara o pacote de custo zero

As ações são executadas automaticamente pela interface — não peça permissão para incluí-las.
Nunca invente item_id: use os que a conversa apresentou. Fora dos blocos ```acao, escreva
texto normal (um breve resumo do que você fez)."""

_ACTION_FIELDS = {
    "adicionar_texto": ("titulo", "texto"),
    "adicionar_url": ("url",),
    "buscar": ("fonte", "termos"),
    "gerar": ("fonte", "item_id"),
    "exportar_notebooklm": ("fonte", "item_id"),
}


# O corpo do conteúdo pesquisado pode ser longo; o limite real (5 MiB) é
# aplicado por CustomSource.add_text. Os demais campos são identificadores curtos.
_LONG_FIELDS = {"texto"}


def _valid_action(data: object) -> bool:
    if not isinstance(data, dict) or data.get("tipo") not in _ACTION_FIELDS:
        return False
    description = data.get("descricao")
    if description is not None and not isinstance(description, str):
        return False
    return all(
        isinstance(data.get(field), str)
        and bool(data[field].strip())
        and (field in _LONG_FIELDS or len(data[field]) <= 4096)
        for field in _ACTION_FIELDS[data["tipo"]]
    )


def parse_actions(reply: str) -> tuple[str, list[dict]]:
    """Separa o texto da resposta e as ações estruturadas."""
    actions = []
    for block in re.findall(r"```acao\s*\n(.*?)\n\s*```", reply, re.DOTALL):
        try:
            data = json.loads(block)
            if _valid_action(data):
                actions.append(data)
        except json.JSONDecodeError:
            continue
    text = re.sub(r"```acao\s*\n.*?\n\s*```", "", reply, flags=re.DOTALL).strip()
    return text, actions


class ChatSession:
    def __init__(self, session_id: str = "principal", chat_dir: Path | None = None) -> None:
        session_id = validate_identifier(session_id, "ID da sessão", max_length=64)
        self.path = (chat_dir or CHAT_DIR) / f"{session_id}.json"
        self.messages: list[dict] = []
        if self.path.is_file():
            self.messages = json.loads(self.path.read_text(encoding="utf-8"))

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.messages, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def clear(self) -> None:
        self.messages = []
        self._flush()

    def _transcript(self) -> str:
        lines = []
        for message in self.messages[-20:]:  # janela de contexto do histórico
            speaker = "Usuário" if message["role"] == "user" else "Assistente"
            lines.append(f"{speaker}: {message['content']}")
        return "\n\n".join(lines)

    def send(
        self,
        message: str,
        settings: Settings,
        call_provider: Callable[[str, str, Settings], str] | None = None,
    ) -> tuple[str, list[dict]]:
        """Envia uma mensagem e retorna (texto da resposta, ações propostas)."""
        if not isinstance(message, str) or not message.strip():
            raise ValueError("A mensagem não pode ser vazia.")
        if len(message) > 50_000:
            raise ValueError("A mensagem excede o limite de 50.000 caracteres.")
        history = self._transcript()
        user_prompt = (
            f"Histórico da conversa:\n{history}\n\nUsuário: {message}" if history else message
        )
        caller = call_provider or _default_provider
        reply = caller(SYSTEM_PROMPT, user_prompt, settings)
        self.messages.append({"role": "user", "content": message, "at": time.time()})
        self.messages.append({"role": "assistant", "content": reply, "at": time.time()})
        self._flush()
        return parse_actions(reply)


def _default_provider(system: str, user: str, settings: Settings) -> str:
    """CLI de assinatura quando configurada (com pesquisa web no Claude Code);
    senão, API do OpenRouter em texto livre."""
    if settings.text_provider not in ("", "openrouter"):
        from .providers.subscription import get_cli, run_cli

        cli = get_cli(settings.text_provider)
        if cli.args:
            command, stdin = cli.chat_command(system), user
        else:
            command, stdin = [cli.binary, *cli.chat_args], f"{system}\n\n{user}"
        try:
            result = run_cli(command, stdin)
        except OSError as error:
            raise RuntimeError(
                f"Não foi possível executar a CLI '{cli.binary}' ({cli.name}): {error}"
            ) from error
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "")[:300]
            raise RuntimeError(f"{cli.name} falhou: {detail}")
        reply = (result.stdout or "").strip()
        if not reply:
            raise RuntimeError(f"{cli.name} terminou sem retornar uma resposta.")
        return reply

    import requests

    from .config import OPENROUTER_BASE_URL

    response = requests.post(
        f"{OPENROUTER_BASE_URL}/chat/completions",
        json={
            "model": settings.text_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        headers={"Authorization": f"Bearer {settings.require_api_key()}"},
        timeout=300,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]
