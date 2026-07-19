# 🎙️ Audiofy Content AI

<div align="center">

![Status](https://img.shields.io/badge/status-MVP-green?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Electron](https://img.shields.io/badge/Electron-41-47848F?style=for-the-badge&logo=electron&logoColor=white)
![OpenRouter](https://img.shields.io/badge/OpenRouter-API-6C47FF?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

**Transforme qualquer conteúdo em podcasts auditáveis ou leituras fiéis com IA — pipeline verificável, voz natural e custo em tempo real.**

[🧰 Ferramentas](#-ferramentas-disponíveis) • [🚀 Como usar](#-como-usar) • [📖 Plano técnico](docs/PLANO-TECNICO.md) • [⚠️ Limites](#-limites-atuais)

</div>

---

## 📋 Índice

- [🎯 Sobre o projeto](#-sobre-o-projeto)
- [📁 Estrutura do projeto](#-estrutura-do-projeto)
- [🧰 Ferramentas disponíveis](#-ferramentas-disponíveis)
- [🚀 Como usar](#-como-usar)
- [🧭 Guia rápido](#-guia-rápido)
- [🖥️ App desktop (Electron)](#️-app-desktop-electron)
- [📖 Leitura fiel de livros e textos longos](#-leitura-fiel-de-livros-e-textos-longos)
- [🧩 Fontes de conteúdo](#-fontes-de-conteúdo)
- [🔑 Chaves, perfis e modelos](#-chaves-perfis-e-modelos)
- [🎛️ Apresentadores e vozes](#️-apresentadores-e-vozes)
- [💰 Custo em tempo real](#-custo-em-tempo-real)
- [✅ Qualidade e testes](#-qualidade-e-testes)
- [⚠️ Limites atuais](#-limites-atuais)
- [🛡️ Segurança](#️-segurança)
- [🎯 Objetivo](#-objetivo)
- [📝 Licença](#-licença)
- [👤 Autor](#-autor)
- [🤝 Contribuições](#-contribuições)

---

## 🎯 Sobre o projeto

O Audiofy transforma conteúdo escrito em episódios de podcast ou audiolivros com pipelines
**auditáveis**. A adaptação tem matriz de cobertura, roteiro e auditoria; a leitura fiel mantém
o texto original e usa a IA somente como diretora de interpretação. Ambos registram custo.

```text
Podcast:     conteúdo → cobertura → roteiro (N vozes) → auditoria → TTS → montagem
Leitura fiel: texto → segmentação literal → plano prosódico → TTS (1 voz) → montagem
```

**Qualquer conteúdo vira episódio**: cole um texto, aponte uma URL (o extrator puxa o texto
principal da página) ou peça um tema ao **chat de pesquisa** — um assistente que **pesquisa,
escreve o conteúdo e o adiciona sozinho**, sem pedir aprovação (com busca na web quando roda
pela CLI de assinatura). Ele também executa automaticamente as demais ações que propõe: buscar,
gerar episódio, exportar para NotebookLM. Os botões de cada ação seguem visíveis para reexecutar
à mão quando quiser.

O projeto nasceu como "Akita on Rails to Podcast"; hoje os artigos do
[AkitaOnRails](https://akitaonrails.com) são apenas uma das fontes, empacotada no módulo
independente [akita-articles](https://github.com/Felipe-Alcantara/akita-articles). Novas fontes
(outros blogs, feeds, pastas de arquivos) entram implementando um contrato pequeno, sem tocar
no núcleo.

## 📁 Estrutura do projeto

```text
Audiofy-Content-AI/
├── 📁 .github/                  # CI, Dependabot e template de pull request
├── 📁 docs/
│   ├── PLANO-TECNICO.md         # Arquitetura e decisões do projeto
│   └── QUALIDADE.md             # Régua automatizada e verificações manuais
├── 📁 src/
│   └── 📁 audiofy/
│       ├── config.py            # Env, caminhos, modelos, apresentadores
│       ├── presenters.py        # 1..N apresentadores configuráveis
│       ├── prompts.py           # Prompts montados para N apresentadores
│       ├── narration.py         # Segmentação literal + direção prosódica
│       ├── pipeline.py          # Adaptação ou leitura fiel → áudio
│       ├── bridge.py            # Interface JSON (Electron e automações)
│       ├── setup.py             # Diagnóstico e instalação compartilhados
│       ├── security.py          # Validações de IDs e URLs públicas
│       ├── tui.py               # Menu navegável questionary + Rich
│       ├── 📁 providers/        # OpenRouter: chat+custo, TTS, catálogo
│       ├── 📁 sources/          # Contrato + registro de fontes
│       └── 📁 runtime/          # Status, custo acumulado e abort
├── 📁 electron/                 # App desktop iniciado pelo menu
├── 📁 scripts/                  # Automações internas de manutenção
├── 📁 tests/                    # Testes Python e Node
├── 📁 data/                     # Episódios e conteúdo local
├── start_app.py                 # Porta de entrada interativa
├── pyproject.toml               # Lint, formato e cobertura
├── requirements.txt             # Dependências de execução fixadas
├── requirements-dev.txt         # Ferramentas de desenvolvimento fixadas
├── CONTRIBUTING.md              # Fluxo para contribuições
├── SECURITY.md                  # Canal privado e escopo de segurança
├── IA.md                        # Linha do tempo de decisões
└── README.md                    # Este arquivo
```

## 🧰 Ferramentas disponíveis

### 🎙️ Menu interativo

**Arquivo:** `start_app.py`

- **Quando usar:** para instalar, configurar, iniciar, acompanhar ou diagnosticar o Audiofy.
- **Entrada:** escolhas por setas, URLs, textos ou IDs de conteúdo.
- **Saída:** configuração local, episódios, pacotes NotebookLM e estado operacional legível.
- **Exemplo:** `python3 start_app.py` → **Iniciar / Rodar** → conversar com o assistente.

---

### ⚙️ Pipeline e bridge

**Arquivos:** `src/audiofy/pipeline.py` e `src/audiofy/bridge.py`

- **Quando usar:** o pipeline gera episódios; a bridge atende o desktop e automações.
- **Entrada:** `ContentItem`, formato, perfil, modelos, vozes e opções de retomada.
- **Saída:** roteiro auditado ou plano prosódico literal, segmentos, MP3 e métricas.
- **Exemplo:** um item selecionado no menu → artefatos em `data/episodes/<item>/`.

---

### 🖥️ App desktop

**Diretório:** `electron/`

- **Quando usar:** para operar o mesmo backend por uma interface gráfica responsiva.
- **Entrada:** ações nas abas Chat, Conteúdo, Episódios e Configurações.
- **Saída:** progresso, custo, player embutido e configurações persistidas pelo backend.
- **Exemplo:** menu → **Abrir app desktop** → selecionar conteúdo → **Gerar episódio**.

---

### 🧩 Fontes e integrações

**Diretórios:** `src/audiofy/sources/` e `src/audiofy/providers/`

- **Quando usar:** para importar conteúdo próprio/Akita e acessar texto ou TTS por provedor.
- **Entrada:** URL pública, texto colado, consulta ou item de uma fonte registrada.
- **Saída:** `ContentItem`s normalizados e respostas de provedor isoladas do domínio.
- **Exemplo:** adicionar uma URL → extrair o texto principal → disponibilizar para geração.

## 🚀 Como usar

Requisitos: Python 3.10+ e uma chave do
[OpenRouter](https://openrouter.ai/keys) com créditos. Para o app desktop: Node.js 18.18+.
O botão **🛠️ Instalar/corrigir** (aba Configurações) instala o resto — `git`,
`ffmpeg`, as dependências Python e, quando npm está disponível, o desktop pelo lockfile — usando
o gerenciador do sistema (brew, apt, dnf, pacman ou winget). No macOS é preciso ter o
[Homebrew](https://brew.sh) instalado.

```bash
# Abre a porta de entrada principal do projeto
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
| Leitura fiel | escolhe uma voz e narra o texto sem reescrever palavras |
| Gerar em 2º plano | libera o terminal; `watch` acompanha |
| Acompanhar / Abortar | progresso e custo ao vivo; cancela com segurança |
| Exportar p/ NotebookLM | episódio de **custo zero** dentro da assinatura Google |
| Chaves e verificação | registre, use, troque e verifique chaves nomeadas ou a origem de ambiente |
| Perfis & modelos | presets de modelos + apresentadores; escolha empresa → modelo com preço |
| Catálogo TTS/vozes | modelos de áudio do OpenRouter e vozes do Gemini |
| Sincronizar / Status / Setup | fonte atualizada; o que está gastando créditos; instalação |
| Abrir app desktop | interface Electron com **todas** essas funções |

Para automações e integrações, continuam disponíveis os comandos secundários `list`,
`search <termos>`, `generate <n|id> [--bg] [--force]`,
`narrate <n|id> [--voice=Sulafat] [--bg] [--force]`,
`watch <id>`, `abort <id>`, `sync`, `status`, `setup`, `catalog`.

Cada episódio fica em `data/episodes/<item>/` com artefatos auditáveis. A adaptação usa
`coverage.json`, `script.json` e `audit.json`; a leitura fiel usa `prosody.json` e
`narration-script.json`. Ambos mantêm `status.json`, `segments.json`, `segments/`, `episode.mp3`
e `NOTES.md`. Falhas temporárias no TTS são retomadas automaticamente por fala, com backoff e
jitter (cinco tentativas por padrão), sem refazer nem repagar segmentos concluídos. Se o limite
terminar ou o processo for encerrado, rodar novamente continua do checkpoint; o manifesto vincula
cada áudio ao texto, modelo, voz e formato usados. A política pode ser ajustada com
`AUDIOFY_TTS_RETRY_ATTEMPTS`, `AUDIOFY_TTS_RETRY_BASE_SECONDS` e
`AUDIOFY_TTS_RETRY_MAX_SECONDS`.

## 🧭 Guia rápido

### Para iniciantes

1. Rode `python3 start_app.py`.
2. Escolha **Instalar / Setup** e confira os resultados exibidos.
3. Entre em **Configurar**, cadastre a chave já disponível e selecione um perfil.
4. Use **Adicionar conteúdo** para colar o texto e selecione **Leitura fiel** + uma voz.
5. Antes de consumir créditos, confira a estimativa; para livros, prefira segundo plano e Status.

### Para desenvolvimento e automação

1. Crie um ambiente virtual e instale `requirements-dev.txt`.
2. Instale o desktop de forma reproduzível com `npm ci --prefix electron`.
3. Execute `python scripts/check_quality.py --quick` durante o desenvolvimento.
4. Antes de entregar, rode `python scripts/check_quality.py`, incluindo auditorias.
5. Use a bridge JSON ou os comandos secundários somente em integrações não interativas.

## 🖥️ App desktop (Electron)

```bash
# Instala exatamente as versões do lockfile
npm ci --prefix electron

# Inicia o desktop diretamente; o menu continua sendo o caminho recomendado
npm start --prefix electron
```

(ou opção "Abrir app desktop" no menu). O app tem **paridade completa com a CLI**, em quatro
abas:

- **💬 Chat** — o assistente de pesquisa: qualquer tema, com ações executadas automaticamente
  (adicionar URL, buscar, gerar, exportar NotebookLM);
- **📚 Conteúdo** — seletor e prontidão da fonte, busca, adicionar por URL ou texto colado,
  estimativa, podcast adaptado ou leitura fiel com escolha de narrador, log vivo e NotebookLM;
- **🎧 Episódios** — todos os episódios com estado, progresso, custo, abortar, ouvir e abrir
  pasta;
- **⚙️ Configurações** — contador e origem efetiva das chaves, cadastro, troca, verificação
  individual, remoção e saldo em US$,
  criar/editar/ativar/remover perfis, escolha provedor + empresa + modelo com preços,
  apresentadores, setup compartilhado e catálogo TTS/vozes.

Um banner global alerta **sempre que qualquer geração estiver consumindo créditos**. Toda a
lógica continua no backend Python. Uma faixa de configuração permanece visível em todas as abas
e mostra o perfil, o provedor/modelo efetivo das etapas de texto, o modelo TTS e a **chave
efetivamente usada** — inclusive quando uma variável `AUDIOFY_*` está sobrescrevendo o perfil ativo.
Para o Codex, o modelo global definido em `~/.codex/config.toml` também é identificado (somente esse
campo é lido). A interface reorganiza navegação, cartões e formulários ao redimensionar a janela até
sua largura mínima de 360 px.
O cartão do conteúdo confirma imediatamente o início da geração e mantém falhas rápidas visíveis
com etapa, checkpoint, custo e orientação segura — por exemplo, limite mensal ou chave recusada —
em vez de parecer que o botão não respondeu.
Falhas antigas por limite são identificadas como históricas: ao abrir novamente o conteúdo, o app
valida a chave efetiva e retoma automaticamente do checkpoint quando houver limite disponível,
rechecando a configuração a cada minuto enquanto a tela permanecer aberta.
O app fala com o backend pela bridge JSON
(`python3 -m audiofy.bridge`), a mesma interface disponível para qualquer automação.

O processo Electron roda com `contextIsolation`, sandbox e uma Content Security Policy
restritiva. A bridge aceita somente os comandos públicos usados pela interface, limita argumentos
e volume de dados, trata timeout/falha de processo e só abre arquivos localizados dentro do projeto.
O desktop fixa Electron 41.7.1, última correção dessa linha compatível com Node 18+, com lockfile
reproduzível e `npm audit` sem vulnerabilidades conhecidas.

## 📖 Leitura fiel de livros e textos longos

Na aba **Conteúdo**, cole o texto, selecione o item e troque **Formato** para **Leitura fiel,
sem reescrita**. A única escolha editorial necessária é o narrador. O Audiofy então:

1. divide localmente o texto em pausas naturais de até 2.400 caracteres;
2. persiste inclusive espaços e quebras de borda e prova por teste que a concatenação dos
   trechos recompõe o texto colado caractere por caractere;
3. envia lotes pequenos ao modelo de texto, que devolve somente direção de ritmo, emoção,
   tensão, pausas e diálogos — qualquer texto reescrito na resposta é descartado;
4. sintetiza cada trecho com a voz escolhida e monta o MP3 final.

O tamanho total não precisa caber em uma janela de contexto: plano e áudio são processados em
lotes com checkpoint, cache por trecho, retry e retomada. Isso segue a recomendação do
[Google Gemini TTS](https://ai.google.dev/gemini-api/docs/speech-generation) de dividir saídas
longas para evitar perda de consistência. O aplicativo não impõe limite de caracteres ao texto
colado; os limites reais são armazenamento, memória, tempo e créditos disponíveis na máquina.

O modo preserva o texto; ele não concede direito de reproduzir livros ou fanfics. Importe apenas
obras próprias, em domínio público ou para as quais você tenha autorização adequada.

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

- **Chaves nomeadas** — várias chaves do OpenRouter ("pessoal", "trabalho"…), guardadas em
  `.audiofy/keys.json` com permissão `0600` e fora do Git. A tela mostra quantas estão cadastradas,
  nomes e valores mascarados, além da origem realmente usada. É possível registrar, verificar
  individualmente, usar/trocar ou remover cada chave e também voltar à `OPENROUTER_API_KEY` do
  `.env`/ambiente. O ambiente continua sendo o padrão para CI e sessões temporárias; uma escolha
  explícita de chave nomeada permanece efetiva até outra origem ser selecionada. A verificação
  consulta **limite, restante e uso mensal da própria chave**, sem confundir com o saldo global da
  conta. Cadastrar ou apenas destacar uma chave não troca a execução: use a ação **Usar** e confira
  o selo **em uso** ou a faixa **Chave efetiva**. O Electron relê valores originados no `.env` a
  cada operação.
- **Perfis** — presets nomeados de modelos + apresentadores. Embutidos: `padrao` (qualidade),
  `economico` (tudo no modelo barato), `narrador-unico` (adaptação solo), `assinatura`
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
# Define nome, voz e tom de cada apresentador
AUDIOFY_PRESENTERS="ana:Kore:animada, beto:Puck:cético, carla:Aoede:técnica"
```

O roteiro é gerado para os apresentadores configurados (nome e tom vão para o prompt e para o
TTS). O menu **Catálogo TTS/vozes** lista os modelos de áudio disponíveis no OpenRouter e as
30 vozes do Gemini TTS com seus estilos.

## 💰 Custo em tempo real

- **Etapas de texto** (matriz/roteiro/auditoria ou plano prosódico): custo **exato** por chamada,
  retornado pela própria API (`usage.cost`).
- **TTS**: a resposta binária traz `X-Generation-Id`; o pipeline consulta `/generation` e soma o
  **custo faturado de cada fala**, sem misturar o uso das outras chaves. Se o metadado remoto não
  estiver disponível, usa a tabela do modelo e marca explicitamente o total como aproximado.
- Se uma fala receber `403` por limite mensal, o pipeline tenta automaticamente a chave do `.env`
  e as chaves nomeadas do cofre antes de falhar; o rótulo da alternativa usada fica registrado no
  manifesto, sem qualquer segredo.
- O `status.json`, o banner e o log registram somente o rótulo seguro da chave em tentativa. Em
  `402`, a interface orienta conferir tanto o saldo global quanto o limite individual dessa chave.
- O custo aparece na barra de progresso, no `status.json`, no app desktop, no Status do menu e
  fica registrado no `NOTES.md` do episódio.
- **Estimativa adaptativa**: cada conclusão grava palavras da fonte/roteiro, duração, modelo,
  perfil, formato, custo e precisão em `metrics.json`. A previsão usa totais ponderados de todos os
  episódios do mesmo TTS e formato, sem misturar podcast adaptado com leitura fiel, e mostra valor
  central, faixa observada, duração e tamanho da amostra. Trocar o formato atualiza o cálculo antes
  da confirmação.
  Sem histórico, o piloto real (2.155 palavras, 13min01s, US$ 0,624287) é apenas o fallback
  inicial. Data da geração e origem da medição também ficam preservadas.

O Status (CLI e app) sempre deixa explícito se algo está rodando em segundo plano gastando
créditos, inclusive a fala e a tentativa durante uma retomada automática. O abort encerra
ativamente o worker e seus subprocessos, inclusive durante TTS, CLI ou montagem, preservando
segmentos e checkpoints concluídos. Se o sistema negar o encerramento, o arquivo `ABORT` continua
como fallback cooperativo no primeiro checkpoint disponível.

No cartão do conteúdo, **Log da geração** mostra as últimas 160 linhas, confirma se o worker
continua vivo e informa há quanto tempo saiu a última mensagem. O backend lê no máximo 64 KiB,
mascara padrões de chave e inicia novos workers sem buffer de stdout, mantendo o painel atualizável
sem carregar logs inteiros nem esperar a conclusão de uma etapa.

## ✅ Qualidade e testes

Prepare o ambiente de desenvolvimento uma vez:

```bash
# Cria e prepara um ambiente isolado de desenvolvimento
python -m venv .venv
python -m pip install -r requirements-dev.txt

# Instala exatamente a árvore do lockfile do desktop
npm ci --prefix electron
```

Depois execute a mesma régua usada pela CI:

```bash
# Lint, formatação, testes, cobertura, JSON, whitespace e auditorias
python scripts/check_quality.py

# Ciclo rápido sem as auditorias que dependem da rede
python scripts/check_quality.py --quick
```

Os controles incluem Ruff, cobertura mínima de 70%, ESLint sem warnings, testes Python/Node,
`pip-audit`, `npm audit` e validação de todos os JSON versionados. A CI repete a suíte em
Python 3.10/3.12 e Node 18. Consulte a [régua de qualidade](docs/QUALIDADE.md) para critérios,
exceções e verificações manuais.

A suíte cobre perfis, chaves, fontes, leitura literal, plano prosódico, parsing, chat, setup,
status/abort, bridge, modelo efetivo do Codex, path traversal/SSRF e limites do IPC Electron.
Responsividade foi verificada em 600 px e 380 px, incluindo os controles da leitura fiel.

## ⚠️ Limites atuais

- A auditoria pós-áudio (STT do arquivo final) ainda não foi implementada; a revisão dos
  episódios é humana (`audit.json` + ouvir).
- A auditoria do roteiro reporta pendências, mas não bloqueia a geração — a decisão de publicar
  é de quem revisa.
- Gerações antigas, sem `X-Generation-Id`, permanecem identificadas como aproximadas; novas falas
  guardam ID e custo individual no manifesto para auditoria posterior.
- Nomes de modelos e vozes mudam com o catálogo do OpenRouter; tudo é configurável via `.env`.
- O texto pode ser muito maior que a janela do modelo e não recebe teto de caracteres do
  aplicativo; a geração depende de disco, memória, tempo e créditos disponíveis.
- A importação por URL não acessa intranets ou serviços locais; nesses casos, cole o texto
  manualmente para preservar a fronteira de segurança.

## 🛡️ Segurança

- Segredos ficam em `.env` ou `.audiofy/keys.json` (`0600` em sistemas POSIX), ambos ignorados
  pelo Git; a interface nunca devolve a chave sem máscara. Históricos em `data/chat/` e conteúdo
  pessoal em `data/inbox/` também não entram no versionamento.
- A importação por URL aceita somente HTTP(S) público, sem credenciais incorporadas. Destinos
  locais, privados ou reservados são rejeitados, inclusive após redirecionamento; downloads são
  limitados a 5 MiB. Textos colados não recebem teto de caracteres e são segmentados antes da IA.
- IDs usados em arquivos, nomes de sessão, perfis e ações propostas pelo modelo são validados na
  fronteira antes de persistir ou executar.
- Operações destrutivas exigem confirmação; gerações iniciadas pelo chat podem ser automáticas,
  mas exibem estimativa e banner global de custo. O abort ativo preserva os artefatos concluídos;
  como uma requisição já entregue ao provedor ainda pode ser cobrada, o custo passa a aproximado.
- O Electron usa CSP, sandbox, navegação bloqueada, allowlist de IPC e confinamento de caminhos.

Reporte vulnerabilidades pelo processo privado descrito em [SECURITY.md](SECURITY.md), sem abrir
uma issue pública com detalhes exploráveis.

## 🎯 Objetivo

O projeto busca tornar a produção de podcasts por IA verificável e operável por qualquer pessoa:
uma única porta de entrada, custo explícito, fontes extensíveis e artefatos suficientes para
revisar o que foi coberto, dito e faturado.

## 📝 Licença

Código e documentação originais sob MIT. Conteúdo derivado de fontes de terceiros segue a
licença de cada fonte — os artigos do Akita e suas adaptações são **CC BY-NC-SA 4.0** (uso
não comercial, atribuição, mesma licença), como detalhado no
[plano técnico](docs/PLANO-TECNICO.md#-licenciamento-e-atribuição).

## 👤 Autor

**Felipe Martin**

- GitHub: [@Felipe-Alcantara](https://github.com/Felipe-Alcantara)

## 🤝 Contribuições

Veja [CONTRIBUTING.md](CONTRIBUTING.md) para preparar o ambiente, executar a régua de qualidade
e abrir uma mudança rastreável. Questões de segurança seguem o canal privado descrito em
[SECURITY.md](SECURITY.md).

Ideias que o projeto adoraria receber:

- **Novas fontes de conteúdo** (outros blogs, feeds RSS, pastas de Markdown, Notion);
- **Planejamento editorial em lote** — inserir muitos dados e gerar pauta de episódios/tópicos;
- STT + auditoria automática do MP3 final (fase 4 do plano técnico);
- Métricas de cobertura semântica reproduzíveis.

---

⭐ Se o projeto for útil, considere acompanhar sua evolução e contribuir.
