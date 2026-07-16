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

---

## 2026-07-16 — Primeiro episódio real: correção de PCM e barra de progresso

**O que mudou:** o primeiro teste ponta a ponta com créditos reais confirmou o risco registrado
acima: o Gemini TTS no OpenRouter rejeita `response_format=mp3` (HTTP 400) e só aceita `pcm`.
O adaptador agora recebe PCM cru (16-bit mono, taxa configurável via `AKITA_TTS_SAMPLE_RATE`,
padrão 24 kHz) e o embrulha em WAV — o que o plano já recomendava como intermediário sem perdas.
A etapa de TTS ganhou barra de progresso (linha única no terminal, linha por turno em log) e a
saída passou a ter flush por linha, para acompanhamento via `tail -f`.

**Validação:** episódio piloto gerado com sucesso a partir do artigo
"Fiz o Fable 5 analisar código do TikTok…" (2026-07-08): 66 itens de cobertura, 41 turnos,
auditoria sem pendências críticas, ~13 min de áudio, MP3 normalizado. A retomada após falha
funcionou como projetado — matriz/roteiro/auditoria foram reaproveitados do disco e a síntese
recomeçou do primeiro segmento faltante, sem custo duplicado nas etapas textuais.

**Pendências registradas:** revisão humana integral do episódio piloto (exigência do plano);
registrar o custo real da rodada (painel do OpenRouter) antes de gerar em lote.
