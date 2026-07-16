# IA.md — Contexto operacional

> Linha do tempo de decisões do projeto. Não reescreva registros antigos: acrescente
> uma nova entrada datada com contexto, motivo e validação.

## Objetivo atual

MVP funcional: listar os artigos do blog AkitaOnRails e gerar episódios de podcast com dois
apresentadores via OpenRouter, seguindo o pipeline auditável de [docs/PLANO-TECNICO.md](docs/PLANO-TECNICO.md).

## Stack e convenções

- Python 3.12, apenas stdlib + `requests`; `ffmpeg` para montagem de áudio.
- Estrutura `src/akita_podcast/` com módulos por responsabilidade: `config` (env/modelos),
  `source_repo` (Git + parser), `openrouter` (adaptador HTTP), `pipeline` (casos de uso).
- Porta de entrada: `start_app.py` (menu interativo, padrão Felixo).
- Artefatos locais em `data/` (ignorado pelo Git); segredos somente em `.env`.
- Testes com `unittest` em `tests/unit/`.

---

## 2026-07-16 — MVP inicial (listagem + geração via OpenRouter)

**O que mudou:** primeira implementação executável. Sincronizador Git do repositório
`akitaonrails/akitaonrails.github.io`, parser mínimo de frontmatter, listagem de artigos,
e pipeline de episódio em 5 etapas: matriz de cobertura → roteiro (2 apresentadores) →
auditoria do roteiro → TTS por turno → montagem/normalização com ffmpeg.

**Decisões:**

- **Parser de frontmatter mínimo (regex), sem PyYAML** — o frontmatter do blog usa apenas
  chaves simples; evita dependência. Se aparecerem estruturas complexas, migrar para PyYAML.
- **Cada etapa persiste artefato JSON** em `data/episodes/<id>/` — permite retomada após falha
  e auditoria humana (`coverage.json`, `script.json`, `audit.json`, `segments/`).
- **Auditoria não bloqueia a geração no MVP** — reporta pendências críticas no terminal e
  registra em `audit.json`; a decisão de publicar é humana (revisão obrigatória nos pilotos).
- **STT (fase 4 do plano) ficou de fora do MVP** — a auditoria pós-áudio será humana por
  enquanto; o plano prevê a etapa e a estrutura comporta adicioná-la.
- **Uma voz por chamada TTS** (contrato portável do OpenRouter); multivoz nativo fica como
  otimização futura.
- Modelos padrão em `config.py`, todos substituíveis por variáveis de ambiente `AKITA_*`.

**Validação:** `python3 -m unittest` (parser) e fluxo real de sync + listagem (771+ artigos,
commit registrado). A geração de episódio depende de `OPENROUTER_API_KEY` e ainda não foi
executada ponta a ponta com créditos reais.

**Risco que sobrou:** nomes de modelos TTS/voz podem divergir do catálogo atual do OpenRouter —
o primeiro teste real deve validar `AKITA_TTS_MODEL` e as vozes; ajuste via `.env` sem mudar código.
