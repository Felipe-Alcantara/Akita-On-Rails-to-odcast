"""Registro de idiomas suportados na geração.

Fonte única de verdade sobre idiomas. Cada idioma é uma entrada em ``LANGUAGES``
com o código usado nos artefatos e os rótulos que aparecem nos prompts e nas
notas de produção. Para adicionar um idioma novo, acrescente uma entrada aqui e
os textos correspondentes nos dicionários de ``prompts.py`` e ``narration.py`` —
o código de orquestração consulta este registro e não precisa mudar.

O código canônico (``code``) é o que vai para ``metrics.json``, para o nome da
pasta do episódio e para o payload da interface; mantê-lo estável preserva o
histórico e os artefatos já gerados.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_LANGUAGE = "pt-BR"


@dataclass(frozen=True)
class Language:
    code: str  # identificador estável nos artefatos (ex.: "pt-BR", "en")
    prompt_label: str  # como o idioma é nomeado dentro dos prompts do modelo
    ui_label: str  # rótulo curto para a interface e logs


LANGUAGES: dict[str, Language] = {
    "pt-BR": Language(code="pt-BR", prompt_label="português brasileiro", ui_label="Português"),
    "en": Language(code="en", prompt_label="English", ui_label="English"),
}


def get_language(code: str) -> Language:
    """Retorna o idioma pedido ou o padrão, nunca levanta para código desconhecido.

    A geração não deve quebrar por um código de idioma inesperado vindo de um
    artefato antigo ou de uma integração; cair no padrão é o comportamento seguro.
    """
    return LANGUAGES.get(code, LANGUAGES[DEFAULT_LANGUAGE])


def is_supported(code: str) -> bool:
    return code in LANGUAGES


def supported_codes() -> list[str]:
    return list(LANGUAGES)


def prompt_label(code: str) -> str:
    """Nome do idioma para interpolar nos prompts do modelo."""
    return get_language(code).prompt_label


def normalize(code: str) -> str:
    """Reduz qualquer código ao de um idioma suportado (o padrão como último recurso)."""
    return code if is_supported(code) else DEFAULT_LANGUAGE
