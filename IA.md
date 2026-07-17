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

---

## 2026-07-17 — Rebrand para Audiofy Content AI e extração do módulo akita-articles

**O que mudou:** o projeto deixou de ser "Akita to Podcast" e virou um programa geral de
geração de podcasts a partir de conteúdo. Reposicionamento completo:

- **Repositório renomeado** para `Audiofy-Content-AI` (o GitHub redireciona o nome antigo);
  a pasta local pode ser renomeada quando conveniente.
- **Módulo `akita-articles` extraído** para repositório próprio
  (https://github.com/Felipe-Alcantara/akita-articles): sincronização, busca com normalização
  de acentos, separação de seções e análise editorial; 17 testes próprios. O Audiofy o consome
  via pip (o Setup instala) ou clone irmão em desenvolvimento.
- **Pacote `audiofy` substitui `akita_podcast`**: fontes de conteúdo viram um registro
  Open/Closed (`sources/`, contrato `ContentSource`/`ContentItem`, inspirado no padrão de
  interfaces declarativas do Openia); provedor OpenRouter em `providers/`; runtime de geração
  em `runtime/`.
- **1..N apresentadores** por configuração (`AUDIOFY_PRESENTERS="nome:Voz[:tom], …"`), com
  prompts montados dinamicamente; catálogo de modelos TTS (API) e das 30 vozes Gemini no menu.
- **Custo em tempo real** (feature obrigatória definida pelo usuário): etapas de texto usam
  `usage.cost` exato da API; TTS usa delta de `total_usage` da conta (aproximação documentada,
  no espírito do OpenRouter-Monitorator). Custo aparece na barra, no `status.json`, no Status
  e no `NOTES.md`.
- **Transparência de gasto em segundo plano**: `status.json` por episódio, geração em 2º plano
  via bridge, `watch` ao vivo, abort cooperativo (arquivo `ABORT`, para no próximo segmento) e
  Status/menu/app sempre alertando quando algo está consumindo créditos.
- **Bridge JSON** (`python3 -m audiofy.bridge`) como interface programática única.
- **App desktop Electron** (`electron/`): lista/busca, estimativa antes de gerar, banner de
  gasto ativo, progresso+custo ao vivo, abortar, ouvir episódio. Lógica 100% no Python.

**Custo real medido (episódio piloto do TikTok):** **US$ 0,60 ≈ 13 minutos ≈ 2.200 palavras**.
A estimativa pré-geração da CLI e do app usa essa razão. Feedback do usuário sobre o áudio:
qualidade muito boa.

**Validação:** 17 testes no repositório principal (presenters, status/abort, sources) +
17 no akita-articles, todos verdes; CLI e bridge smoke-testados contra a fonte real
(771 itens); sintaxe do Electron verificada e binário instalado.

**Decisão de versionamento:** a pedido do usuário, `data/episodes/` inteiro (incluindo áudio)
passa a ser versionado; apenas o clone da fonte (`data/source/`) fica fora.

**Riscos que sobraram:** o custo de TTS por delta de conta mistura usos concorrentes da mesma
chave; o app Electron ainda não foi testado visualmente de ponta a ponta (a bridge que o
alimenta foi). Roadmap registrado no README: módulo de chat estilo Openia, modo NotebookLM
barato, planejamento editorial em lote, STT final.

---

## 2026-07-17 — Chaves nomeadas, saldo, perfis e seletor de modelos (padrões do Openia)

**O que mudou:** portadas as features de gestão do Openia que faltavam:

- **Keystore** (`keystore.py` + menu "Chaves & saldo"): chaves nomeadas com uma ativa,
  validação de formato (`sk-or-`), armazenamento em `.audiofy/keys.json` com `0600`,
  prioridade da env var/.env, máscara na exibição; checagem de chave e saldo/uso via
  `/credits` (`account_balance`, `check_api_key`).
- **Perfis** (`profiles.py` + menu "Perfis & modelos"): presets nomeados de modelos +
  apresentadores; embutidos `padrao`, `economico`, `narrador-unico`; customizados persistidos
  sem segredos; ativo trocável; `Settings` resolve env > perfil > padrão.
- **Seletor de modelos** (`catalog.py`): catálogo `/models` com cache de 24h em
  `.audiofy/models-cache.json`, navegação empresa → modelo com preço por milhão de tokens,
  filtro por modalidade (áudio para TTS).
- `.audiofy/` entrou no .gitignore; o antigo "Configurar chave" (que gravava no .env) foi
  substituído pelo cofre — o .env segue suportado como override.

**Sobre "assinatura":** no Openia, assinatura refere-se a rodar CLIs sob a assinatura do
provedor (ex.: Claude Code com plano Anthropic) em vez de chave de API. No Audiofy a geração é
via API do OpenRouter, onde esse conceito não se aplica diretamente; o equivalente barato/manual
é o modo NotebookLM, que segue no roadmap.

**Validação:** 35 testes verdes (17 novos de keystore/perfis); saldo checado ao vivo contra a
conta real (US$ 5,01 restantes / US$ 18,99 usados em 17/07/2026); menu smoke-testado.

**Risco que sobrou:** o parse do catálogo assume `pricing.prompt/completion` por token; se o
OpenRouter mudar o esquema de preços, o seletor mostra valores errados (a geração não é afetada).

---

## 2026-07-17 — Modo assinatura, exportação NotebookLM e pesquisa de modelos/custos

**O que mudou** (correção da interpretação de "assinatura" após feedback do usuário — a
intenção era usar a assinatura para as etapas de texto, com modelos fora do OpenRouter):

- **Provedor de texto por assinatura** (`providers/subscription.py`): as etapas de matriz,
  roteiro e auditoria podem rodar em CLI local sob assinatura — `claude-code`, `gemini-cli`
  ou `codex` — em modo não interativo (prompt via stdin, JSON validado na saída), custo
  US$ 0,00. Perfil embutido `assinatura` e env `AUDIOFY_TEXT_PROVIDER`. TTS permanece via API
  (assinaturas não expõem TTS programável). Máquina do usuário tem as três CLIs.
- **Exportação NotebookLM** (`export.py`, menu 14, CLI `notebooklm <id>`, bridge): gera
  `notebooklm/fonte.md` + `instrucoes.md` (passo a passo + foco de cobertura integral +
  atribuição) na pasta do episódio — caminho de custo totalmente zero, com aviso explícito
  de que Audio Overview é resumo sem auditoria.
- **Pesquisa de modelos e custos** (`docs/MODELOS-E-CUSTOS.md`): catálogo `speech` consultado
  ao vivo (12 modelos TTS). Destaques por episódio de 13 min: Gemini TTS ~US$ 0,39 (validado
  em pt-BR), Voxtral mini ~US$ 0,05, Kokoro ~US$ 0,002 (qualidade pt-BR a validar);
  combinações sugeridas de US$ 0,60 até US$ 0,00.

**Validação:** 42 testes verdes (7 novos); provedor de assinatura testado ao vivo com o
Claude Code real (JSON válido, custo zero); exportação NotebookLM executada contra o episódio
piloto; menu e status smoke-testados.

**Risco que sobrou:** os flags headless das CLIs (`claude -p`, `gemini` via stdin,
`codex exec -`) podem mudar entre versões; a falha é explícita (stderr no erro) e o fallback
é voltar o perfil para a API. TTS alternativos (Voxtral/Kokoro) ainda não foram ouvidos em
pt-BR — testar num artigo curto antes de adotar.
