"""Apresentadores do episódio: 1..N vozes configuráveis.

Formato da especificação (env AUDIOFY_PRESENTERS):
    "nome:Voz[:tom], nome2:Voz2[:tom2], ..."
Exemplo: "ana:Kore:animada, beto:Puck:cético"
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_SPEC = "apresentador_a:Kore:curioso, apresentador_b:Puck:didático"


@dataclass(frozen=True)
class Presenter:
    speaker: str  # identificador usado nos turnos do roteiro
    voice: str  # nome da voz no modelo TTS
    style: str = ""  # tom/estilo de fala (livre, vai para o prompt e o TTS)


def parse_presenters(spec: str) -> list[Presenter]:
    """Interpreta a especificação de apresentadores; vazio usa o padrão."""
    spec = spec.strip() or DEFAULT_SPEC
    presenters: list[Presenter] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [p.strip() for p in chunk.split(":")]
        if len(parts) < 2 or not parts[0] or not parts[1]:
            raise ValueError(f"Apresentador inválido: '{chunk}'. Use nome:Voz ou nome:Voz:tom.")
        presenters.append(Presenter(parts[0], parts[1], parts[2] if len(parts) > 2 else ""))
    speakers = [p.speaker for p in presenters]
    if len(speakers) != len(set(speakers)):
        raise ValueError(f"Apresentadores com nomes duplicados: {spec!r}")
    if not presenters:
        raise ValueError("É preciso pelo menos um apresentador.")
    return presenters
