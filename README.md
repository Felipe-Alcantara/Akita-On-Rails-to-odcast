# 🎙️ Audiofy Content AI

<div align="center">

![Status](https://img.shields.io/badge/status-MVP-green?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Electron](https://img.shields.io/badge/Electron-33-47848F?style=for-the-badge&logo=electron&logoColor=white)
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

O projeto nasceu como "Akita on Rails to Podcast" e evoluiu para um programa geral: os artigos
do [AkitaOnRails](https://akitaonrails.com) são a primeira **fonte de conteúdo**, empacotada no
módulo independente [akita-articles](https://github.com/Felipe-Alcantara/akita-articles).
Novas fontes (outros blogs, feeds, pastas de arquivos) entram implementando um contrato pequeno,
sem tocar no núcleo.

## 🚀 Como usar

Requisitos: Python 3.10+, `git`, `ffmpeg`, biblioteca `requests` e uma chave do
[OpenRouter](https://openrouter.ai/keys) com créditos. Para o app desktop: Node.js.

```bash
python3 start_app.py
```

O menu interativo é a porta de entrada única:

| Opção | O que faz |
|---|---|
| Instalar / Setup | verifica dependências, instala o módulo akita-articles, cria o `.env` |
| Chaves & saldo | chaves **nomeadas** (pessoal, trabalho…), chave ativa, saldo/uso em US$ |
| Perfis & modelos | presets de modelos + apresentadores; escolha empresa → modelo com preço |
| Sincronizar fonte | baixa/atualiza os artigos |
| Listar / Buscar | catálogo com busca por título, slug ou tag |
| Gerar episódio | ao vivo, com barra de progresso e custo em US$ |
| Gerar em 2º plano | libera o terminal; `watch` acompanha |
| Acompanhar geração | progresso e custo ao vivo de uma geração em andamento |
| Abortar geração | cancela com segurança no próximo segmento |
| Catálogo TTS/vozes | modelos de áudio do OpenRouter e vozes do Gemini |
| Status | mostra **explicitamente** o que está consumindo créditos |
| Abrir app desktop | interface Electron |
| Exportar p/ NotebookLM | episódio de **custo zero** dentro da assinatura Google |

Atalhos de linha de comando: `list`, `search <termos>`, `generate <n|id> [--bg]`,
`watch <id>`, `abort <id>`, `sync`, `status`, `setup`, `catalog`.

Cada episódio fica em `data/episodes/<item>/` com artefatos auditáveis (`coverage.json`,
`script.json`, `audit.json`, `status.json`, `segments/`, `episode.mp3`, `NOTES.md`).
Falhou no meio? Rodar de novo retoma de onde parou sem regenerar (nem repagar) o que já existe.

## 🖥️ App desktop (Electron)

```bash
cd electron && npm install && npm start
```

(ou opção "Abrir app desktop" no menu). A interface lista e busca artigos, mostra estimativa
de custo antes de gerar, exibe **banner de alerta enquanto qualquer geração estiver consumindo
créditos**, barra de progresso e custo ao vivo, botão de abortar e player dos episódios prontos.
Toda a lógica continua no backend Python — o app fala com ele pela bridge JSON
(`python3 -m audiofy.bridge`), a mesma interface disponível para qualquer automação.

## 🧩 Fontes de conteúdo

Uma fonte implementa o contrato `ContentSource` (`sync`, `list_items`, `search`, `get_item`)
e devolve `ContentItem`s com texto e atribuição. O registro em `src/audiofy/sources/__init__.py`
é o único ponto que muda ao adicionar uma fonte (Open/Closed).

| Fonte | Módulo | Estado |
|---|---|---|
| Akita on Rails | [akita-articles](https://github.com/Felipe-Alcantara/akita-articles) | ✅ funcional |

## 🔑 Chaves, perfis e modelos

Padrões portados do [Openia](https://github.com/Felipe-Alcantara/Openia):

- **Chaves nomeadas** — várias chaves do OpenRouter ("pessoal", "trabalho"…), uma ativa,
  guardadas em `.audiofy/keys.json` com permissão `0600` e fora do Git. A variável
  `OPENROUTER_API_KEY` (inclusive via `.env`) tem prioridade, para CI/sessões temporárias.
  O menu mostra o **saldo e o uso em US$** da chave ativa.
- **Perfis** — presets nomeados de modelos + apresentadores. Embutidos: `padrao` (qualidade),
  `economico` (tudo no modelo barato) e `narrador-unico` (audiolivro). Crie os seus pelo menu;
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

Ative com o perfil embutido `assinatura` ou `AUDIOFY_TEXT_PROVIDER=claude-code`. O TTS continua
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
créditos — e o abort para a geração no próximo segmento, sem corromper artefatos.

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
│       ├── 📁 providers/        # OpenRouter: chat+custo, TTS, catálogo
│       ├── 📁 sources/          # Contrato + registro de fontes (akita)
│       └── 📁 runtime/          # status.json, custo acumulado, abort
├── 📁 electron/                 # App desktop (npm start)
├── 📁 tests/                    # python3 -m unittest discover -s tests
├── 📁 data/                     # Episódios e clone da fonte
├── start_app.py                 # Menu interativo — porta de entrada
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

## 🤝 Contribuições

Ideias que o projeto adoraria receber:

- **Novas fontes de conteúdo** (outros blogs, feeds RSS, pastas de Markdown, Notion);
- **Modo NotebookLM** — caminho manual/barato para episódios simples, complementando o pipeline;
- **Módulo de chat** — conversar com o programa para checar módulos, baixar conteúdo, inserir
  dados e configurar (no espírito do [Openia](https://github.com/Felipe-Alcantara/Openia));
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

---

⭐ Se o projeto for útil, considere acompanhar sua evolução e contribuir.
