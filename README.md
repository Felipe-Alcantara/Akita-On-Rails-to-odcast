# 🎙️ Audiofy Content AI

<div align="center">

![Status](https://img.shields.io/badge/status-MVP-green?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Electron](https://img.shields.io/badge/Electron-41-47848F?style=for-the-badge&logo=electron&logoColor=white)
![OpenRouter](https://img.shields.io/badge/OpenRouter-API-6C47FF?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

**Transforme qualquer conteúdo em podcasts auditáveis com IA — pipeline verificável, múltiplos apresentadores e custo em tempo real.**

[📖 Plano técnico](docs/PLANO-TECNICO.md) • [🚀 Como usar](#-como-usar) • [🧩 Fontes](#-fontes-de-conteúdo) • [⚠️ Limites](#-limites-atuais)

</div>

---

## 📋 Índice

- [🎯 Sobre o projeto](#-sobre-o-projeto)
- [🚀 Como usar](#-como-usar)
- [🖥️ App desktop (Electron)](#️-app-desktop-electron)
- [🧩 Fontes de conteúdo](#-fontes-de-conteúdo)
- [🎛️ Apresentadores e vozes](#️-apresentadores-e-vozes)
- [💰 Custo em tempo real](#-custo-em-tempo-real)
- [🛡️ Segurança](#️-segurança)
- [✅ Qualidade e testes](#-qualidade-e-testes)
- [📁 Estrutura](#-estrutura)
- [⚠️ Limites atuais](#-limites-atuais)
- [🤝 Contribuições](#-contribuições)
- [📝 Licença](#-licença)

---

## 🎯 Sobre o projeto

O Audiofy transforma conteúdo escrito em episódios de podcast com um pipeline **auditável** —
não um resumo cego: cada episódio tem matriz de cobertura, roteiro verificável, auditoria
contra o texto original e registro de custo.

```text
conteúdo → matriz de cobertura → roteiro (N apresentadores) → auditoria → TTS → montagem
```

**Qualquer conteúdo vira episódio**: cole um texto, aponte uma URL (o extrator puxa o texto
principal da página) ou peça sugestões ao **chat de pesquisa** — um assistente que pesquisa
qualquer tema (com busca na web quando roda pela CLI de assinatura) e propõe ações executáveis
com um clique: adicionar conteúdo, buscar, gerar episódio, exportar para NotebookLM.

O projeto nasceu como "Akita on Rails to Podcast"; hoje os artigos do
[AkitaOnRails](https://akitaonrails.com) são apenas uma das fontes, empacotada no módulo
independente [akita-articles](https://github.com/Felipe-Alcantara/akita-articles). Novas fontes
(outros blogs, feeds, pastas de arquivos) entram implementando um contrato pequeno, sem tocar
no núcleo.

## 🚀 Como usar

Requisitos: Python 3.10+, `git`, `ffmpeg` e uma chave do
[OpenRouter](https://openrouter.ai/keys) com créditos. Para o app desktop: Node.js.

```bash
python3 start_app.py
```

O menu interativo, colorido e navegável por setas é a porta de entrada principal. Na primeira
execução, ele prepara automaticamente `questionary` e `rich`; a opção **Instalar / Setup**
instala as demais dependências declaradas em `requirements.txt` e diagnostica o ambiente.

| Opção | O que faz |
|---|---|
| Chat de pesquisa | pesquise qualquer tema; o assistente propõe ações executáveis |
| Adicionar conteúdo | por URL (extrai o texto da página) ou texto colado |
| Trocar fonte | conteúdo próprio, Akita on Rails, ou qualquer fonte registrada |
| Listar / Buscar | catálogo da fonte ativa, com busca |
| Gerar episódio | ao vivo, com barra de progresso e custo em US$ |
| Gerar em 2º plano | libera o terminal; `watch` acompanha |
| Acompanhar / Abortar | progresso e custo ao vivo; cancela com segurança |
| Exportar p/ NotebookLM | episódio de **custo zero** dentro da assinatura Google |
| Chaves & saldo | chaves **nomeadas** (pessoal, trabalho…), chave ativa, saldo/uso em US$ |
| Perfis & modelos | presets de modelos + apresentadores; escolha empresa → modelo com preço |
| Catálogo TTS/vozes | modelos de áudio do OpenRouter e vozes do Gemini |
| Sincronizar / Status / Setup | fonte atualizada; o que está gastando créditos; instalação |
| Abrir app desktop | interface Electron com **todas** essas funções |

Para automações e integrações, continuam disponíveis os comandos secundários `list`,
`search <termos>`, `generate <n|id> [--bg] [--force]`,
`watch <id>`, `abort <id>`, `sync`, `status`, `setup`, `catalog`.

Cada episódio fica em `data/episodes/<item>/` com artefatos auditáveis (`coverage.json`,
`script.json`, `audit.json`, `status.json`, `segments.json`, `segments/`, `episode.mp3`,
`NOTES.md`). Falhas temporárias no TTS são retomadas automaticamente por fala, com backoff e
jitter (cinco tentativas por padrão), sem refazer nem repagar segmentos concluídos. Se o limite
terminar ou o processo for encerrado, rodar novamente continua do checkpoint; o manifesto vincula
cada áudio ao texto, modelo, voz e formato usados. A política pode ser ajustada com
`AUDIOFY_TTS_RETRY_ATTEMPTS`, `AUDIOFY_TTS_RETRY_BASE_SECONDS` e
`AUDIOFY_TTS_RETRY_MAX_SECONDS`.

## 🖥️ App desktop (Electron)

```bash
cd electron && npm install && npm start
```

(ou opção "Abrir app desktop" no menu). O app tem **paridade completa com a CLI**, em quatro
abas:

- **💬 Chat** — o assistente de pesquisa: qualquer tema, com ações executáveis em um clique
  (adicionar URL, buscar, gerar, exportar NotebookLM);
- **📚 Conteúdo** — seletor e prontidão da fonte, busca, adicionar por URL ou texto colado,
  estimativa de custo, geração normal ou forçada e NotebookLM;
- **🎧 Episódios** — todos os episódios com estado, progresso, custo, abortar, ouvir e abrir
  pasta;
- **⚙️ Configurações** — chaves nomeadas (adicionar/ativar/remover), saldo em US$,
  criar/editar/ativar/remover perfis, escolha provedor + empresa + modelo com preços,
  apresentadores, setup compartilhado e catálogo TTS/vozes.

Um banner global alerta **sempre que qualquer geração estiver consumindo créditos**. Toda a
lógica continua no backend Python. Uma faixa de configuração permanece visível em todas as abas
e mostra o perfil, o provedor/modelo efetivo das etapas de texto e o modelo TTS — inclusive quando
uma variável `AUDIOFY_*` está sobrescrevendo o perfil ativo. Para o Codex, o modelo global definido
em `~/.codex/config.toml` também é identificado (somente esse campo é lido). A interface reorganiza
navegação, cartões e formulários ao redimensionar a janela até sua largura mínima de 360 px.
O app fala com o backend pela bridge JSON
(`python3 -m audiofy.bridge`), a mesma interface disponível para qualquer automação.

O processo Electron roda com `contextIsolation`, sandbox e uma Content Security Policy
restritiva. A bridge aceita somente os comandos públicos usados pela interface, limita argumentos
e volume de dados, trata timeout/falha de processo e só abre arquivos localizados dentro do projeto.
O desktop fixa Electron 41.7.1, última correção dessa linha compatível com Node 18+, com lockfile
reproduzível e `npm audit` sem vulnerabilidades conhecidas.

## 🧩 Fontes de conteúdo

Uma fonte implementa o contrato `ContentSource` (`sync`, `list_items`, `search`, `get_item`)
e devolve `ContentItem`s com texto e atribuição. O registro em `src/audiofy/sources/__init__.py`
é o único ponto que muda ao adicionar uma fonte (Open/Closed).

| Fonte | Módulo | Estado |
|---|---|---|
| Conteúdo próprio (URL ou texto colado) | embutida (`sources/custom.py`) | ✅ funcional |
| Akita on Rails | [akita-articles](https://github.com/Felipe-Alcantara/akita-articles) | ✅ funcional |

## 🔑 Chaves, perfis e modelos

Padrões portados do [Openia](https://github.com/Felipe-Alcantara/Openia):

- **Chaves nomeadas** — várias chaves do OpenRouter ("pessoal", "trabalho"…), uma ativa,
  guardadas em `.audiofy/keys.json` com permissão `0600` e fora do Git. A variável
  `OPENROUTER_API_KEY` (inclusive via `.env`) tem prioridade, para CI/sessões temporárias.
  O menu mostra o **saldo e o uso em US$** da chave ativa.
- **Perfis** — presets nomeados de modelos + apresentadores. Embutidos: `padrao` (qualidade),
  `economico` (tudo no modelo barato), `narrador-unico` (audiolivro), `assinatura`
  (Claude Code) e `assinatura-codex` (Codex CLI). Crie e edite os seus pelo menu ou pelo app;
  variáveis `AUDIOFY_*` continuam tendo prioridade sobre o perfil ativo.
- **Escolha de modelo em dois passos** — empresa → modelo, com preço por milhão de tokens em
  cada linha, vindo da API ao vivo com cache local de 24h.

### 💳 Modo assinatura (texto a custo zero)

As etapas de **texto** (matriz de cobertura, roteiro, auditoria) podem rodar em uma CLI de IA
instalada na máquina, sob a assinatura do usuário, em vez da API:

| CLI | Assinatura |
|---|---|
| `claude-code` | Anthropic (Claude Code) |
| `gemini-cli` | Google |
| `codex` | OpenAI |

Ative com o perfil embutido `assinatura` (Claude Code), `assinatura-codex` (OpenAI Codex) ou
com `AUDIOFY_TEXT_PROVIDER=claude-code`. O TTS continua
via API (assinaturas não expõem TTS programável) — o custo do episódio cai para só a voz
(~US$ 0,39 no Gemini TTS; centavos em modelos alternativos). O caminho de custo **totalmente
zero** é o modo NotebookLM (menu "Exportar p/ NotebookLM"): o Audiofy prepara a fonte e as
instruções de foco, e você gera o Audio Overview manualmente na sua conta — sem garantia de
cobertura integral, como documentado.

Comparativo completo de modelos TTS/texto e custos por episódio:
[docs/MODELOS-E-CUSTOS.md](docs/MODELOS-E-CUSTOS.md).

## 🎛️ Apresentadores e vozes

De 1 a N apresentadores, por configuração (`.env`):

```bash
AUDIOFY_PRESENTERS="ana:Kore:animada, beto:Puck:cético, carla:Aoede:técnica"
```

O roteiro é gerado para os apresentadores configurados (nome e tom vão para o prompt e para o
TTS). O menu **Catálogo TTS/vozes** lista os modelos de áudio disponíveis no OpenRouter e as
30 vozes do Gemini TTS com seus estilos.

## 💰 Custo em tempo real

- **Etapas de texto** (matriz, roteiro, auditoria): custo **exato** por chamada, retornado pela
  própria API (`usage.cost`).
- **TTS**: a resposta é binária e não carrega custo; o pipeline acompanha pelo **delta de uso da
  conta** durante a etapa — uma aproximação honesta (se outra coisa usar a mesma conta ao mesmo
  tempo, o valor mistura os usos).
- O custo aparece na barra de progresso, no `status.json`, no app desktop, no Status do menu e
  fica registrado no `NOTES.md` do episódio.
- **Referência real medida**: US$ 0,60 ≈ 13 minutos ≈ 2.200 palavras (episódio piloto). A
  estimativa pré-geração usa essa razão.

O Status (CLI e app) sempre deixa explícito se algo está rodando em segundo plano gastando
créditos, inclusive a fala e a tentativa durante uma retomada automática. O abort continua
responsivo durante a espera e para a geração no próximo checkpoint, sem corromper artefatos.

## 🛡️ Segurança

- Segredos ficam em `.env` ou `.audiofy/keys.json` (`0600` em sistemas POSIX), ambos ignorados
  pelo Git; a interface nunca devolve a chave sem máscara. Históricos em `data/chat/` e conteúdo
  pessoal em `data/inbox/` também não entram no versionamento.
- A importação por URL aceita somente HTTP(S) público, sem credenciais incorporadas. Destinos
  locais, privados ou reservados são rejeitados, inclusive após redirecionamento; downloads são
  limitados a 5 MiB.
- IDs usados em arquivos, nomes de sessão, perfis e ações propostas pelo modelo são validados na
  fronteira antes de persistir ou executar.
- Operações com custo ou destrutivas exigem confirmação; o abort é cooperativo e preserva os
  artefatos já concluídos.
- O Electron usa CSP, sandbox, navegação bloqueada, allowlist de IPC e confinamento de caminhos.

## ✅ Qualidade e testes

```bash
# Backend, regras de negócio e regressões
PYTHONPATH=src python3 -m unittest discover -s tests -v

# Lint Python
ruff check start_app.py src tests

# Sintaxe e contratos de segurança do Electron
npm --prefix electron run check

# Auditoria das dependências do desktop
npm --prefix electron audit
```

A suíte cobre perfis, chaves, fontes, parsing, chat, setup, status/abort, bridge, modelo efetivo
do Codex, proteção contra path traversal/SSRF e os limites do IPC Electron. Responsividade foi
verificada visualmente em 600 px e 380 px, incluindo Chat e Configurações.

## 📁 Estrutura

```text
Audiofy-Content-AI/
├── 📁 docs/
│   └── PLANO-TECNICO.md         # Arquitetura e decisões do projeto
├── 📁 src/
│   └── 📁 audiofy/
│       ├── config.py            # Env, caminhos, modelos, apresentadores
│       ├── presenters.py        # 1..N apresentadores configuráveis
│       ├── prompts.py           # Prompts montados para N apresentadores
│       ├── pipeline.py          # Cobertura → roteiro → auditoria → áudio
│       ├── bridge.py            # Interface JSON (Electron e automações)
│       ├── setup.py             # Diagnóstico e instalação compartilhados
│       ├── security.py          # Validações de IDs e URLs públicas
│       ├── tui.py               # Menu navegável questionary + Rich
│       ├── 📁 providers/        # OpenRouter: chat+custo, TTS, catálogo
│       ├── 📁 sources/          # Contrato + registro de fontes (akita)
│       └── 📁 runtime/          # status.json, custo acumulado, abort
├── 📁 electron/                 # App desktop (npm start)
├── 📁 tests/                    # python3 -m unittest discover -s tests
├── 📁 data/                     # Episódios e clone da fonte
├── start_app.py                 # Menu interativo — porta de entrada
├── requirements.txt             # Dependências Python declaradas
├── IA.md                        # Linha do tempo de decisões
└── README.md
```

## ⚠️ Limites atuais

- A auditoria pós-áudio (STT do arquivo final) ainda não foi implementada; a revisão dos
  episódios é humana (`audit.json` + ouvir).
- A auditoria do roteiro reporta pendências, mas não bloqueia a geração — a decisão de publicar
  é de quem revisa.
- O custo do TTS é aproximado pelo uso da conta (ver acima); o valor exato consta no painel do
  OpenRouter.
- Nomes de modelos e vozes mudam com o catálogo do OpenRouter; tudo é configurável via `.env`.
- A importação por URL não acessa intranets ou serviços locais; nesses casos, cole o texto
  manualmente para preservar a fronteira de segurança.

## 🤝 Contribuições

Ideias que o projeto adoraria receber:

- **Novas fontes de conteúdo** (outros blogs, feeds RSS, pastas de Markdown, Notion);
- **Planejamento editorial em lote** — inserir muitos dados e gerar pauta de episódios/tópicos;
- STT + auditoria automática do MP3 final (fase 4 do plano técnico);
- Métricas de cobertura semântica reproduzíveis.

## 📝 Licença

Código e documentação originais sob MIT. Conteúdo derivado de fontes de terceiros segue a
licença de cada fonte — os artigos do Akita e suas adaptações são **CC BY-NC-SA 4.0** (uso
não comercial, atribuição, mesma licença), como detalhado no
[plano técnico](docs/PLANO-TECNICO.md#-licenciamento-e-atribuição).

## 👤 Autor

**Felipe Martin**

- GitHub: [@Felipe-Alcantara](https://github.com/Felipe-Alcantara)

---

⭐ Se o projeto for útil, considere acompanhar sua evolução e contribuir.
