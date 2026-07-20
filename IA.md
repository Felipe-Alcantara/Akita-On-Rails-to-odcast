# IA.md — Contexto operacional

> Linha do tempo de decisões do projeto. Não reescreva registros antigos: acrescente
> uma nova entrada datada com contexto, motivo e validação.

## Objetivo atual

MVP funcional: transformar conteúdo próprio, URLs públicas ou fontes registradas em episódios de
podcast auditáveis, com 1..N apresentadores, retomada por checkpoint, custo observável e interfaces
CLI/Electron, seguindo [docs/PLANO-TECNICO.md](docs/PLANO-TECNICO.md).

## Stack e convenções

- Python 3.10+ com `requests`, `questionary` e `rich`; `ffmpeg` para montagem de áudio.
- Electron 41 com Node.js 18.18+ para o desktop; lógica de negócio permanece no backend Python.
- Estrutura `src/audiofy/` separada em fontes, provedores, pipeline, runtime, bridge e interfaces.
- Porta de entrada: `start_app.py` (menu interativo, padrão Felixo).
- Episódios auditáveis em `data/episodes/`; estado pessoal (`data/chat/`, `data/inbox/`) ignorado.
- Segredos somente em `.env` ou `.audiofy/keys.json`, ambos fora do Git.
- Testes com `unittest` e coverage.py; JavaScript com Node test runner; régua em
  `scripts/check_quality.py`.

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
  `usage.cost` exato da API; cada TTS preserva `X-Generation-Id` e consulta seu `total_cost`
  individual, sem misturar as outras chaves da conta. Custo e precisão aparecem na barra, no
  `status.json`, no manifesto, no Status e no `NOTES.md`.
- **Transparência de gasto em segundo plano**: `status.json` por episódio, geração em 2º plano
  via bridge, `watch` ao vivo, abort cooperativo (arquivo `ABORT`, para no próximo segmento) e
  Status/menu/app sempre alertando quando algo está consumindo créditos.
- **Bridge JSON** (`python3 -m audiofy.bridge`) como interface programática única.
- **App desktop Electron** (`electron/`): lista/busca, estimativa antes de gerar, banner de
  gasto ativo, progresso+custo ao vivo, abortar, ouvir episódio. Lógica 100% no Python.

**Piloto medido:** **US$ 0,624287, 13min01s, 2.155 palavras de fonte e 1.860 de roteiro**.
A estimativa da CLI e do app usa média ponderada e faixa do mesmo TTS e perfil; o piloto
é apenas fallback quando ainda não há histórico. Feedback do usuário: qualidade muito boa.

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

---

## 2026-07-17 — Chat de pesquisa, fonte genérica e app Electron com paridade total

**O que mudou** (pedido do usuário: o Electron deve ter todas as funções da CLI, ganhar um
chat de pesquisa além do Akita, e o Akita deixa de ser o foco):

- **Fonte genérica `custom`** (`sources/custom.py`, fonte padrão do menu): qualquer conteúdo
  vira episódio — texto colado ou URL (extrator de texto principal em HTML puro, sem
  dependências, priorizando `<article>/<main>` e descartando nav/script/rodapé). Itens em
  `data/inbox/*.md` com frontmatter. Atribuição genérica com aviso de direitos.
- **Chat de pesquisa** (`chat.py`, aba própria no app e opção 1 da CLI): sessões persistidas
  em `data/chat/`, histórico na janela de prompt, provedor = CLI de assinatura (no Claude Code
  com `--allowedTools WebSearch`, pesquisa web real a custo zero) ou API. Protocolo de ações
  em blocos ```acao (adicionar_url, buscar, gerar, exportar_notebooklm) que a interface
  executa com um clique — geração sempre confirma custo antes.
- **Bridge completa**: chat/chat-history/chat-clear, add-url/add-text (stdin), keys-*
  (list/add/activate/remove), balance, profiles-list/activate, settings-info; `main.js` do
  Electron passou a suportar stdin nas chamadas.
- **App Electron reconstruído em 4 abas** (Chat, Conteúdo, Episódios, Configurações) com
  paridade total com a CLI: seletor de fonte, adicionar URL/texto, estimativa, gerar, abortar,
  NotebookLM, episódios com estado/custo, chaves nomeadas com saldo, perfis e catálogo.
- **CLI reorganizada**: chat como opção 1, fonte ativa visível e trocável (padrão `custom`),
  adicionar conteúdo por URL/texto, 17 opções no total.

**Validação:** 57 testes verdes (12 novos: fonte custom e chat); extração de URL testada
contra página real do blog; chat testado ao vivo via claude-code (resposta correta, custo
zero); bridge smoke-testada em todos os comandos novos; sintaxe do Electron verificada.

**Risco que sobrou:** o extrator de HTML é heurístico — páginas muito dinâmicas (JS) ou fora
do padrão `<article>` podem render texto insuficiente (o erro instrui a colar o texto);
o protocolo de ações depende de o modelo emitir JSON válido no bloco ```acao (ações inválidas
são ignoradas silenciosamente, por design).

---

## 2026-07-17 — Paridade real do Electron, perfil Codex e interface Felixo

**O que mudou:** uma auditoria entre as 16 funções operacionais do menu e a interface revelou
que a entrega anterior ainda não expunha criação/edição de perfis, setup, regeneração forçada
e parte do status. A paridade foi completada sem duplicar regra de negócio:

- **Perfis completos no Electron:** criar, editar, ativar e remover customizados; provedor de
  texto OpenRouter/assinatura; seleção empresa → modelo com preço; 1..N apresentadores e
  validação central em `profiles.profile_from_payload`. Perfis embutidos agora incluem
  `assinatura-codex`, que usa o Codex CLI para texto e OpenRouter apenas para TTS.
- **Setup compartilhado** em `audiofy.setup`: diagnóstico sem efeitos colaterais, instalação
  explícita de dependências Python e criação de `.env`; CLI e Electron consomem a mesma rotina.
- **`--force` ponta a ponta:** CLI em segundo plano, bridge, subprocesso e pipeline preservam a
  escolha; o app explica que cobertura, roteiro e auditoria serão refeitos antes de confirmar.
- **Catálogo resiliente:** a consulta TTS usa a modalidade `speech`; sem chave/rede, as 30 vozes
  locais e os modelos atuais continuam disponíveis no editor, com aviso em vez de tela vazia.
- **Status e segurança de UI:** prontidão da fonte, origem da chave, setup obrigatório/opcional,
  feedback de sincronização e estados de loading. Uma faixa global mostra perfil, provedor/modelo
  de texto efetivo e TTS em todas as abas, deixando visíveis overrides por `AUDIOFY_*`. Conteúdo
  externo e nomes configuráveis não são mais interpolados via `innerHTML`.
- **Correção de perfil efetivo:** `Settings.profile_name` deixou de nascer preenchido como
  `padrao`; agora recebe o nome resolvido do `ProfileStore`. Antes, ativar `assinatura-codex`
  alterava corretamente o provedor, mas a interface continuava rotulando o perfil como `padrao`.
- **Modelo Codex observável:** o backend lê exclusivamente o campo global `model` de
  `~/.codex/config.toml` (ou `$CODEX_HOME/config.toml`) e a interface mostra o valor efetivo na
  faixa global e no diagnóstico. Tabelas de perfis Codex não são confundidas com o modelo global.
- **Frontend Felixo:** tokens zinc/roxo, cards, badges, foco visível, grid responsivo, estados de
  hover/disabled, contraste, scrollbar e `prefers-reduced-motion`, adaptados ao desktop Audiofy.
  Removido o `min-width: 720px` que quebrava a janela estreita; navegação, chat, listas e
  formulários têm breakpoints em 700/480 px, com mínimo nativo de 360 × 480 px.

**Validação:** testes unitários ampliados para bridge, setup, perfis e `--force`; bridge
smoke-testada nos catálogos e perfis; JavaScript validado por sintaxe e IDs do DOM; Electron
aberto no ambiente gráfico e inspecionado visualmente em Chat e Configurações nas larguras de
600 px e 380 px.

**Risco que sobrou:** modelos e preços dependem do esquema vivo do OpenRouter; o editor preserva
o valor atual quando o catálogo não responde, mas novos modelos só aparecem após nova consulta.

---

## 2026-07-17 — Auditoria integral do Felixo System Design

**O que mudou:** a entrega foi revisada contra o guia mínimo e os contratos completos de
frontend, backend, README e `start_app.py`, cobrindo desvios que não apareciam em uma validação
apenas visual ou sintática:

- **Porta de entrada conforme o padrão:** o menu numérico cru foi substituído por uma TUI
  navegável por setas com `questionary` + `rich`, cabeçalho de estado, descrições por ação,
  seleção de fontes/chaves/perfis/modelos e confirmações explícitas. As dependências foram
  declaradas em `requirements.txt`, diagnosticadas pelo setup e têm bootstrap mínimo.
- **Electron endurecido:** CSP, sandbox, bloqueio de navegação/janelas, allowlist e aridade dos
  comandos IPC, limites de entrada/saída, timeout/falha previsíveis e abertura de arquivos
  confinada ao diretório real do projeto (inclusive contra escape por symlink).
- **Dependência Electron segura:** a versão 33 apresentou vulnerabilidades de alta severidade no
  `npm audit`. A linha foi atualizada e fixada em 41.7.1, última correção compatível com Node 18+;
  o lockfile regenerado ficou com zero vulnerabilidades conhecidas.
- **Fronteiras de dados:** IDs de arquivo/sessão protegidos contra path traversal; títulos não
  injetam frontmatter; perfis têm limites; ações do chat seguem esquema conhecido. A importação
  aceita somente HTTP(S) público, revalida redirecionamentos, bloqueia rede privada/credenciais
  e limita a resposta a 5 MiB. `data/chat/` e `data/inbox/` foram ignorados para impedir commit
  acidental de conversas ou conteúdo pessoal; episódios permanecem versionáveis por decisão prévia.
- **Acessibilidade:** tabs com papéis ARIA, `aria-selected`, navegação por setas/Home/End,
  painéis associados, campos rotulados, histórico como log ao vivo e progresso semântico.
- **Contrato corrigido:** `chat-history` agora devolve as fontes esperadas pelo renderer, e
  `loadSources` também atualiza o registro local; antes, a inicialização podia falhar ao acessar
  `result.sources` inexistente. O seletor TTS da CLI passou a aceitar `speech`/`audio`, e Status
  exibe o modelo efetivo das CLIs de assinatura.

**Validação:** 88 testes Python e 3 testes Node verdes; instalação e `pip check` aprovados em venv
limpo; Ruff, `git diff --check`, `npm audit` zerado, sintaxe de todos os processos Electron e
smoke test real da TUI aprovados. O Electron 41 com sandbox/CSP foi reinspecionado visualmente em
600 px e 380 px.

**Risco que sobrou:** o bloqueio de URLs privadas impede importar páginas de intranet por design;
o caminho seguro é colar o texto. O catálogo remoto e os flags das CLIs continuam integrações
externas sujeitas a mudança, com erros controlados e valores atuais preservados quando possível.

---

## 2026-07-17 — Retomada automática e idempotente do TTS

**O que mudou:** uma geração real parou na fala 45/92 porque o provedor TTS devolveu um `400`
genérico depois de 44 WAVs válidos. A síntese agora classifica falhas retomáveis, repete somente a
fala afetada com backoff exponencial e jitter (limite configurável), mantém o abort responsivo e
mostra fala/tentativa no Status da CLI e do Electron. Segmentos são gravados por arquivo temporário
e rename atômico; `segments.json` registra hash de texto, modelo, voz, instruções, formato e taxa de
amostragem, evitando reutilizar áudio incompatível. Segmentos legados válidos são importados para o
manifesto, portanto episódios parciais anteriores continuam do primeiro arquivo ausente.

**Decisões:** erros permanentes, como autenticação inválida, falham imediatamente; falhas de rede,
respostas vazias e o `Provider returned 400` genérico observado no TTS entram na política limitada.
Uma nova execução preserva também o custo acumulado e registra `resume_count`, em vez de zerar o
status. O limite evita loop infinito e troca silenciosa de modelo/voz continua proibida.

**Validação:** 101 testes Python e 3 testes Node verdes. As regressões cobrem segmento já pronto +
falha + sucesso, esgotamento de tentativas sem apagar checkpoint, erro permanente sem retry,
classificação do `400`, backoff, manifesto e preservação de custo/status entre execuções. Ruff,
compilação Python, sintaxe Electron, `git diff --check` e `npm audit` (zero vulnerabilidades)
também foram aprovados.

**Risco que sobrou:** um erro permanente devolvido incorretamente pelo provedor como `Provider
returned 400` consumirá as tentativas configuradas antes de parar; chamadas rejeitadas não produzem
áudio e nenhum segmento existente é sobrescrito.

---

## 2026-07-17 — Feedback persistente para falhas rápidas no Electron

**O que mudou:** o botão de geração funcionava e o worker retomava o episódio, mas uma falha
permanente muito rápida podia ocorrer entre o retorno da bridge e o primeiro polling. O cartão
escondia a área de progresso assim que `state` deixava de ser `rodando`, dando a impressão de que o
clique não fizera nada. A bridge agora grava atomicamente o estado `iniciando` antes de lançar o
worker; o Electron desabilita e rotula o botão durante a solicitação e mantém estados `falhou` e
`abortado` visíveis com etapa, checkpoint, custo e ação recomendada.

**Decisões:** mensagens conhecidas do OpenRouter são traduzidas localmente sem renderizar URLs ou
identificadores devolvidos pelo provedor. Um limite mensal de chave orienta aumentar esse limite ou
trocar `OPENROUTER_API_KEY/.env`; autenticação e falta de créditos têm mensagens próprias. Erros não
reconhecidos continuam disponíveis de forma sanitizada. Falha ao criar o processo também passa para
o `status.json`, evitando estado `iniciando` preso.

**Validação:** 104 testes Python e 7 testes Node verdes. As regressões cobrem publicação antecipada
do início, preservação do checkpoint, abort durante a inicialização e falha ao lançar o worker.
Os testes Node cobrem tradução segura do limite mensal e os estados de inicialização/falha. Ruff,
compilação Python, sintaxe Electron, `git diff --check` e `npm audit` (zero vulnerabilidades)
também foram aprovados.

**Risco que sobrou:** mensagens de erro desconhecidas ainda dependem do texto devolvido pelo
provedor para oferecer uma orientação específica; o detalhe é sanitizado antes de chegar à tela.

---

## 2026-07-17 — Chave efetiva atualizada no Electron

**O que mudou:** o Electron aberto havia herdado uma `OPENROUTER_API_KEY` antiga do processo que
o iniciou. Alterar o `.env` e recarregar a interface atualizava apenas o renderer; as bridges Python
continuavam recebendo a credencial antiga do processo principal. A inicialização agora marca, sem
valores secretos, quais variáveis foram carregadas do `.env`. Antes de cada bridge, o Electron
remove somente essas cópias para que o backend releia o arquivo atual. Variáveis realmente
definidas no shell continuam intactas e com prioridade.

**Decisões:** o diagnóstico de chave passou do saldo geral da conta (`/credits`) para os metadados
da chave autenticada (`/key`), exibindo o rótulo mascarado, limite, restante e uso mensal. A tela de
configurações também diferencia `ambiente`, `.env` e a chave nomeada do cofre. Nenhum valor integral
de credencial entra no IPC, em logs ou na interface.

**Validação:** 109 testes Python e 10 testes Node verdes. As regressões cobrem procedência,
atualização do arquivo sem sobrescrever o shell, interpretação do limite da chave, remoção
seletiva e rejeição de nomes inválidos. Ruff, compilação, sintaxe Electron, `git diff --check`
e `npm audit` também passaram. A consulta real confirmou a chave mascarada esperada e seu saldo
próprio, sem iniciar geração nem consumir TTS.

**Risco que sobrou:** processos de geração já iniciados preservam deliberadamente a configuração
com que nasceram; trocar o `.env` afeta novas operações, não muta workers que estejam em execução.

---

## 2026-07-17 — Recuperação automática após troca de chave

**O que mudou:** um cartão vermelho ainda dizia que "a chave atingiu o limite" depois da troca,
embora representasse o erro persistido da execução anterior. A mensagem agora usa passado e deixa
explícito que aquela execução usou outra chave. Ao selecionar um conteúdo parado especificamente
por limite, o Electron consulta a chave efetiva; havendo limite disponível, inicia a retomada sem
regenerar os checkpoints. Se a chave continuar esgotada, revalida a cada minuto enquanto o item
permanecer aberto.

**Decisões:** a consulta de chave retorna indisponível quando `limit_remaining` é zero, mesmo que a
credencial seja tecnicamente válida. Isso impede um loop de retomadas rejeitadas. A automação é
restrita ao erro conhecido de limite e ao item selecionado; autenticação, falta de crédito global
ou falhas desconhecidas continuam exigindo intervenção para não repetir custos ou efeitos.

**Validação:** 110 testes Python e 11 testes Node verdes. Uma retomada real preservou as 66 falas
existentes e avançou com a chave atual, sem refazer cobertura, roteiro ou auditoria. As verificações
de lint, compilação, sintaxe Electron e integridade do diff também passaram.

**Risco que sobrou:** a recuperação automática depende de o conteúdo afetado permanecer selecionado
no Electron; episódios falhos não são retomados silenciosamente apenas por abrir o aplicativo.

---

## 2026-07-17 — Custos por geração e médias ponderadas

**O que mudou:** o custo do TTS deixou de usar o delta de `/credits`, que é global à conta e
misturava potencialmente nove chaves do mesmo workspace. Cada resposta de áudio agora preserva o
`X-Generation-Id`; o backend consulta `/generation`, soma `total_cost` e registra ID, valor e
precisão junto ao segmento. Metadado indisponível usa somente a tabela oficial do modelo como
fallback e marca o total como aproximado. Um `403` de limite também alterna automaticamente entre
a chave efetiva, a chave atual do `.env` e o cofre, registrando somente o rótulo da alternativa.

**Médias:** cada episódio concluído grava `metrics.json` com palavras da fonte e do roteiro,
duração real, custo, precisão, perfil e TTS. A estimativa usa totais ponderados de episódios do
mesmo modelo e perfil, e expõe valor central, mínimo/máximo observado, duração, palavras por
minuto e tamanho da amostra. Data da geração e origem do custo ficam preservadas. Os dois
episódios locais resultam em 149,71 palavras/minuto quando analisados em conjunto; o piloto é
fallback somente quando ainda não existe histórico do perfil.

**Decisões:** o Fable, gerado integralmente em 16/07, foi reconciliado em US$ 0,624287 pelo
total diário confirmado da chave. O episódio de 17/07 trocou de chave na fala 67: US$ 0,854023
foram registrados antes da troca e US$ 0,337249 na retomada, total aproximado de US$ 1,191272.
A montagem passou a escrever `episode.tmp.mp3` e fazer rename atômico; a bridge só
expõe o player quando o estado é `concluido`, impedindo a duração parcial de 15:17 observada.

**Validação:** 122 testes Python e 11 testes Node verdes. As regressões cobrem média ponderada,
faixa, fallback oficial, captura de ID/custo, isolamento da conta global, precisão persistida,
montagem atômica e bloqueio do player parcial. Ruff, compilação, sintaxe Electron,
`git diff --check` e `npm audit` também passaram.

**Risco que sobrou:** o custo do Fable foi confirmado pelo total diário da chave, mas o episódio
que trocou de chave permanece aproximado. Cada perfil ainda tem uma única amostra; a faixa ganhará
confiabilidade conforme novas gerações, agora contabilizadas individualmente, forem concluídas.

---

## 2026-07-17 — Instalação automática de git e ffmpeg no setup

**O que mudou:** uma tentativa de instalação no macOS falhou em dois pontos que o botão
"Instalar/corrigir" não cobria: o `ffmpeg` (que não é pacote Python e nunca instalaria via pip)
e o `akita-articles` (bloqueado pelo `externally-managed-environment` do Python gerenciado,
PEP 668). O `apply_setup` agora também instala ferramentas de sistema ausentes — `git` antes do
`akita-articles`, pois o pip depende dele para `git+https://` — usando o primeiro gerenciador
disponível: `brew`, `winget`, `apt-get`, `dnf` ou `pacman`. No pip, quando a instalação falha
com `externally-managed-environment`, há uma nova tentativa automática com
`--user --break-system-packages`.

**Decisões:** no macOS sem Homebrew a ação falha com orientação explícita de instalá-lo — não é
seguro automatizar a instalação do próprio brew. No Linux os gerenciadores usam `sudo -n` (sem
prompt): se a senha não estiver em cache a ação falha com mensagem, em vez de travar o app
esperando entrada invisível. No Windows via winget, o PATH só atualiza após reiniciar o app, e o
detalhe da ação avisa. As dicas de `git`/`ffmpeg` no diagnóstico mudaram para "pode ser instalado
automaticamente" e o README passou a listar como pré-requisitos manuais apenas Python 3.10+,
Node.js (desktop) e o Homebrew no macOS.

**Validação:** 126 testes Python (2 novos: instalação de git/ffmpeg ausentes na ordem correta e
retry do pip com `--break-system-packages`) e 13 verificações Node verdes; Ruff, compilação
Python, sintaxe Electron, `git diff --check` e `npm audit` (zero vulnerabilidades) aprovados.
A instalação real no macOS ainda não foi reexecutada com as mudanças.

**Risco que sobrou:** a instalação de sistema depende de gerenciador presente e de permissão
(sudo no Linux); nesses casos a ação reporta a falha com orientação, mas não resolve sozinha.
O `--break-system-packages` instala no escopo do usuário fora de venv — aceito por ser o mesmo
escopo que o `--user` já usava, apenas destravando o bloqueio do PEP 668.

---

## 2026-07-17 — App desktop abre no Windows

**O que mudou:** no Windows, abrir o app desktop pelo menu não fazia nada. Duas causas no
lançamento: o `Popen(["npm", "start"])` falhava porque o npm do Windows é `npm.cmd` e o
`CreateProcess` não resolve o nome sem extensão (não consulta o `PATHEXT`); e, mesmo que a
janela abrisse, o processo principal chamava o backend como `python3`, que no Windows não
existe no PATH — ou é o atalho da Microsoft Store, que não executa nada. O `do_desktop` agora
usa o caminho completo retornado por `shutil.which("npm")` (instalação e lançamento), desanexa
o processo com `creationflags` no Windows (mantendo `start_new_session` no POSIX) e exporta
`AUDIOFY_PYTHON` com o interpretador que já roda o menu; o `main.js` usa essa variável e,
sem ela, cai para `python` no Windows e `python3` nos demais.

**Decisões:** o interpretador é propagado pela porta de entrada em vez de o Electron adivinhar,
garantindo que o backend rode com o mesmo Python (e venv) do menu; `AUDIOFY_PYTHON` definida
pelo usuário continua tendo prioridade. Quem roda `npm start` direto no Windows, sem passar
pelo menu, usa o fallback `python`.

**Validação:** 130 testes Python (4 novos: caminho completo do npm, desanexação por plataforma
e exportação do interpretador) e 13 verificações Node verdes; Ruff, compilação, sintaxe
Electron, `git diff --check` e `npm audit` (zero vulnerabilidades) aprovados. Falta confirmar
a abertura real numa máquina Windows.

**Risco que sobrou:** se o npm não estiver no PATH do Windows (Node instalado sem reiniciar o
terminal), o menu reporta "npm não encontrado" — a correção não cobre PATH desatualizado.

---

## 2026-07-17 — Lançamento do desktop sem depender do npm.cmd

**O que mudou:** mesmo com o caminho completo do npm, o Windows respondeu
"[WinError 2] O sistema não pode encontrar o arquivo": scripts `.cmd` só executam de forma
confiável através do `cmd.exe`, e o atalho implícito falha em caminhos com espaços ou acentos
(caso da pasta deste projeto). O lançamento deixou de depender do `npm.cmd`: no Windows, o
`npm install` roda pelo `node.exe` chamando o `npm-cli.js` (executável real, sem shell), e a
abertura do app usa o binário do Electron apontado por `node_modules/electron/path.txt`,
com `npm start` apenas como fallback quando o binário não é encontrado. A instalação também
ganhou tratamento de `OSError` com mensagem orientada em vez de erro cru.

**Decisões:** evitar o shell é mais robusto do que envolver o `cmd.exe` explicitamente, cuja
citação de argumentos com aspas é notoriamente frágil; o fallback preserva o comportamento
anterior em plataformas onde o npm é um executável normal.

**Validação:** 136 testes Python (6 novos: resolução do npm via node no Windows, preferência
pelo binário real do Electron, fallback e leitura do `path.txt`) e 13 verificações Node verdes;
Ruff, compilação, `git diff --check` e `npm audit` (zero vulnerabilidades) aprovados. Smoke
local confirmou a resolução do npm real; a abertura no Windows segue pendente de confirmação.

**Risco que sobrou:** instalações de Node que não colocam o `npm-cli.js` ao lado do `node.exe`
caem no fallback do `npm.cmd`, que pode repetir o erro original; nesse caso a mensagem agora
identifica o comando que falhou.

---

## 2026-07-17 — CLIs de assinatura funcionam no Windows

**O que mudou:** enviar mensagem no chat com o provedor de assinatura (Claude Code) falhava no
Windows com "o sistema não pode encontrar o arquivo": as CLIs instaladas via npm (`claude`,
`gemini`) são scripts `.cmd`, que o `subprocess` não executa diretamente — apenas o `cmd.exe`
os resolve pelo PATH/PATHEXT. A execução foi centralizada em `subscription.run_cli`, que no
Windows monta a linha de comando com `list2cmdline` e roda pelo shell, e nas demais plataformas
mantém a chamada direta sem shell. O `chat.py` deixou de duplicar a montagem do subprocess e
reutiliza o runner e o contrato declarativo da CLI (o caso Claude Code só acrescenta
`--allowedTools WebSearch`). `OSError` na execução agora vira erro amigável identificando a CLI,
tanto no pipeline quanto no chat.

**Decisões:** o shell só entra no Windows e a linha é montada por `list2cmdline` a partir do
contrato declarativo — nenhum conteúdo do usuário entra na linha de comando (o prompt segue por
stdin), preservando a fronteira de segurança.

**Validação:** 139 testes Python (3 novos: citação e shell no Windows, ausência de shell no
POSIX e tradução de OSError) e 13 verificações Node verdes; Ruff, compilação, `git diff --check`
e `npm audit` aprovados. Smoke real no Linux: `chat_json` com o Claude Code respondeu JSON
válido a custo zero. Confirmação no Windows pendente.

**Risco que sobrou:** no Windows o `cmd.exe` expande `%VAR%` mesmo entre aspas; os argumentos
vêm do contrato fixo (sem `%`), então o risco prático é nulo hoje, mas argumentos novos com
`%` exigiriam atenção.

---

## 2026-07-17 — Chat com permissão total nas CLIs de assinatura

**O que mudou:** o chat travava com o provedor de assinatura porque, em modo headless, a CLI
não tem como pedir confirmação de permissão ao usar ferramentas (pesquisa web, leitura de
páginas) — ficava presa ou falhava. A pedido do usuário, o chat passa a conceder permissão
total por padrão: o contrato declarativo `SubscriptionCli` ganhou `chat_args`
(`--dangerously-skip-permissions` no Claude Code, `--yolo` no Gemini CLI; o Codex `exec` já é
não interativo) e o `chat.py` usa `chat_command`, eliminando o caso especial do Claude que
existia ali (o `--allowedTools WebSearch` ficou redundante e saiu).

**Decisões:** a permissão total vale somente para o chat de pesquisa — as etapas do pipeline
(matriz, roteiro, auditoria) continuam com o comando básico, pois são texto puro e não usam
ferramentas. As ações propostas pelo chat (gerar episódio, adicionar URL) continuam sendo
executadas pela interface com confirmação explícita; a permissão ampla é da CLI, não do app.

**Validação:** 140 testes Python verdes (novo teste garante os flags no chat e a ausência deles
no pipeline); Ruff, compilação e `git diff --check` aprovados. Smoke real no Linux: o comando de
chat do Claude Code com o flag respondeu normalmente (código 0).

**Risco que sobrou:** com permissão total, a CLI do chat pode executar ferramentas locais sem
confirmação caso o modelo decida — aceito pelo usuário como padrão do chat; reverter é remover
os `chat_args` do contrato.

---

## 2026-07-17 — Chat executa as ações propostas automaticamente

**O que mudou:** o chat pedia aprovação a cada ação — era preciso clicar no botão de cada
proposta e ainda confirmar a geração num `confirm()`. A pedido do usuário, o chat passou a
executar tudo sozinho: `addChatMessage` retorna as ações pendentes e `sendChat` roda cada uma
em ordem, aguardando a anterior, assim que a resposta do assistente chega. O `confirm()` antes
de gerar episódio foi removido; no lugar, o chat anuncia "Gerando … — consome créditos" com a
estimativa visível. Os botões de ação continuam na conversa para reexecução manual, e
`runAction` passou a aceitar chamada sem botão (execução automática).

**Decisões:** a execução é serial (uma ação por vez, com `await`) para não disparar várias
gerações concorrentes nem competir por recarregamento de lista. A remoção da confirmação de
custo é segura porque o custo estimado aparece no chat e o banner global de gasto ativo
continua alertando em todas as abas enquanto qualquer geração roda. Ações destrutivas não
existem no protocolo do chat (adicionar_url, buscar, gerar, exportar_notebooklm) — a mais cara
é gerar, coberta pelo aviso e pelo banner.

**Validação:** 140 testes Python e 13 verificações Node verdes; sintaxe do renderer conferida
pelo `npm run check`, `git diff --check` e `npm audit` (zero vulnerabilidades) aprovados. Falta
confirmar visualmente o fluxo automático no app.

**Risco que sobrou:** o chat agora gera episódios sem confirmação explícita; se o modelo propuser
uma geração indevida, ela inicia (e consome créditos) até ser abortada pela aba Episódios. O
aviso no chat e o banner global mantêm o gasto visível, mas a barreira de clique deixou de existir.

---

## 2026-07-17 — Chat pesquisa e entrega o conteúdo sozinho

**O que mudou:** o chat via assinatura ficava perguntando/confirmando em vez de agir — o
protocolo só permitia *propor* ações (buscar, adicionar_url) para a interface executar depois,
então, pedido um tema, o Claude devolvia perguntas esclarecedoras em vez do resultado. Agora o
chat pesquisa e entrega o conteúdo pronto na mesma resposta:

- **Nova ação `adicionar_texto {titulo, texto}`**: o modelo escreve ele mesmo um texto próprio,
  coeso e substancial sobre o tema (sintetizado, não copiado) e o grava direto na fonte `custom`
  via a bridge `add-text` que já existia. O validador isenta o campo `texto` do limite de 4096
  caracteres dos identificadores curtos; textos colados não recebem teto de caracteres.
- **System prompt reescrito** com a diretriz "AJA, NÃO PERGUNTE": nada de pedir confirmação ou
  devolver perguntas, a menos que o pedido seja impossível de interpretar; as ações rodam
  automaticamente, então o modelo não deve pedir permissão para incluí-las.
- **CLI alinhada ao app**: `do_chat` deixou de perguntar "Executar uma ação proposta?" e passou
  a rodar cada ação automaticamente; `_run_chat_action` ganhou o caso `adicionar_texto`.

**Decisões:** o texto é redigido pelo próprio modelo (síntese autoral) em vez de copiar páginas,
o que evita despejar HTML bruto e reduz risco de direitos; a atribuição genérica da fonte custom
continua avisando para verificar direitos antes de publicar. Complementa a permissão total das
CLIs ([subscription chat_args]) e a execução automática de ações no renderer.

**Validação:** 142 testes Python (2 novos: corpo longo aceito e título obrigatório) e 13
verificações Node verdes; Ruff, compilação, sintaxe Electron, `git diff --check` e `npm audit`
(zero) aprovados. Smoke real no Linux via Claude Code: pedido "pesquise o MCP e adicione",
o chat retornou a ação `adicionar_texto` com um artigo de ~2,3 mil caracteres, salvo na inbox
sem qualquer pergunta de confirmação.

**Risco que sobrou:** o conteúdo é redigido pela IA a partir de pesquisa — pode conter
imprecisões; a revisão humana antes de publicar segue sendo exigência do projeto. Sem a etapa
de confirmação, um tema mal interpretado gera um conteúdo que precisa ser removido à mão.

---

## 2026-07-17 — Execução de processos portátil: fim do travamento silencioso do TTS no Windows

**O que mudou:** em outra máquina Windows a geração travava na fase de áudio. A causa raiz era
o lançamento do worker de segundo plano com `start_new_session=True` — argumento exclusivo do
POSIX. No Windows ele impede a desanexação correta e a geração fica presa em `rodando` sem nunca
progredir nem falhar visivelmente. Corrigido de forma sistêmica, com TDD:

- **Novo módulo `runtime/process.py`** centraliza as três armadilhas de subprocesso que
  travavam ou falhavam em silêncio: `detached_flags()` (creationflags no Windows,
  start_new_session no POSIX), `resolve_tool()` (caminho absoluto de ffmpeg/ffprobe ou erro
  claro em vez de FileNotFoundError cru), `run_tool()` (sempre com `timeout`, para nenhum
  subprocesso poder pendurar a geração) e `launch_detached()` (worker desanexado portátil).
- **Worker de geração** (`bridge._cmd_generate`) passou a usar `launch_detached` — a correção
  direta do travamento.
- **Montagem e duração** (`pipeline._assemble`, `_media_duration_seconds`) usam `run_tool` com
  timeout (ffmpeg 30 min, ffprobe 2 min) e ferramenta resolvida; a lista de concatenação
  normaliza o caminho para `/` (o ffmpeg trata `\` como escape) e escapa aspas; adicionados
  guardas para lista de segmentos vazia e saída não numérica do ffprobe.

**Por que não travava antes no Linux:** `start_new_session` é válido no POSIX, então o bug só
se manifestava no Windows. `generate_episode` já marcava `falhou` em exceção, mas a montagem
sem timeout e o ffmpeg pelo nome cru continuavam sendo pontos de trava potencial.

**Validação:** 159 testes Python (11 novos: flags por plataforma, resolução/timeout de
ferramenta, desanexação do worker portátil, normalização do concat, guardas de duração e
"falha nunca silenciosa" na montagem) e 13 Node verdes; Ruff, compilação, `git diff --check` e
`npm audit` aprovados. Smoke real no Linux: dois WAVs concatenados em MP3 de 2s via o novo
`run_tool`, com duração lida por ffprobe e por `wave` — o caminho POSIX segue intacto.

**Risco que sobrou:** se o worker desanexado morrer por erro de importação antes de entrar no
`generate_episode` (que marca `falhou`), o status pode ficar em `rodando`; o `generation.log`
por episódio registra o traceback. A confirmação do fluxo completo no Windows real segue
pendente, mas a causa estrutural do travamento foi removida.

---

## 2026-07-17 — Vigia de worker: geração presa em "iniciando" nunca mais bloqueia

**O que mudou:** no Windows a geração parava em "Iniciando a retomada" e não saía dali — e
clicar em Gerar de novo (mesmo após apagar a pasta) respondia "geração já em andamento". A
cadeia do problema: o worker desanexado morria logo ao subir sem tocar o `status.json`; o
status ficava `rodando/iniciando` para sempre; e o `generate` recusava novas execuções por
causa desse estado órfão. Três correções, com TDD:

- **Vigia de PID** (`GenerationTracker.reconcile` + `process.pid_alive`): ao consultar o
  status, um `rodando` cujo PID não existe mais vira `falhou` com orientação para o
  `generation.log`; um `iniciando` sem PID há mais de 90s idem. O `pid_alive` usa a API do
  kernel no Windows (`os.kill(pid, 0)` lá TERMINA o processo — nunca usar) e sinal 0 no POSIX.
  O `_cmd_generate` também usa `reconcile`, então o estado órfão deixa de bloquear regeneração.
- **UTF-8 forçado no worker** (`PYTHONUTF8=1` + `PYTHONIOENCODING=utf-8`): no Windows o worker
  herdava cp1252 e o primeiro print com emoji do pipeline podia derrubá-lo — causa provável da
  morte silenciosa observada.
- **Guarda no `run-generation`**: falha antes do pipeline (fonte, configuração) agora marca o
  status como `falhou` em vez de morrer só no log.
- **Texto honesto**: "Iniciando a retomada" só aparece quando há retomada de fato
  (`resume_count > 0`); geração nova diz "Iniciando a geração".

**Validação:** 171 testes Python (12 novos: pid_alive vivo/morto/inválido, reconcile em todos
os estados, UTF-8 do worker, órfão não bloqueia regeneração, falha fora do pipeline) e 14 Node
verdes; Ruff, compilação, `git diff --check` e `npm audit` aprovados. Smoke real: processo
morto de verdade reconciliado para `falhou` com checkpoint preservado.

**Risco que sobrou:** reutilização de PID pelo sistema pode, em tese, manter um órfão como
"rodando" se outro processo nascer com o mesmo PID; a janela é pequena e o custo é apenas
esperar o usuário abortar. A causa exata da morte do worker naquele Windows será confirmada
pelo generation.log agora que o erro fica visível.

---

## 2026-07-18 — Régua de qualidade reproduzível para Python e Electron

**O que mudou:** o repositório foi padronizado de ponta a ponta contra o Felixo System Design,
sem alterar contratos funcionais do pipeline:

- **Configuração central:** `pyproject.toml` define Ruff, formatter e cobertura mínima de 70%;
  `.editorconfig` e `.gitattributes` estabilizam encoding, indentação e fins de linha.
- **JavaScript verificável:** Electron ganhou ESLint 9 (linha compatível com Node 18), integrado
  ao `npm run check`; código Python foi normalizado pelo Ruff formatter e passou a usar um
  conjunto explícito de regras de bugs, imports e modernização segura.
- **Dependências reproduzíveis:** pacotes Python diretos ficaram fixados, `akita-articles` passou
  a apontar para um SHA imutável, ferramentas de desenvolvimento foram separadas em
  `requirements-dev.txt` e o lockfile npm foi regenerado. O setup instala pelo mesmo arquivo
  fixado, coberto por regressão.
- **Automação única:** `scripts/check_quality.py` executa lint, formato, testes+cobertura,
  Electron, JSON, links Markdown, whitespace e auditorias; `--quick` pula apenas rede. A CI
  repete Python 3.10/3.12, Node 18 e auditorias, com Actions presas por SHA. Dependabot cobre
  pip, npm e GitHub Actions.
- **Governança:** adicionados `AGENTS.md`, `CONTRIBUTING.md`, `SECURITY.md`, template de PR e
  `docs/QUALIDADE.md`; README e o resumo vivo deste arquivo foram alinhados ao estado real.

**Decisões:** cobertura inicial foi fixada em 70% por refletir a base real sem mascarar módulos
de UI/integração; aumentos futuros devem vir com testes de comportamento. ESLint 10 não foi usado
porque exige Node 20.19+, enquanto o produto ainda declara Node 18. O utilitário de qualidade é
interno, sem usuário final, e por isso é a exceção documentada ao menu `start_app.py`.

**Validação:** instalação do zero em venv temporário; 177 testes Python e 14 testes Node verdes;
cobertura agregada de 70%; Ruff lint/format, ESLint, `node --check`, compilação Python, JSON,
links internos, `git diff --check`, `pip-audit` e `npm audit` aprovados. Zero vulnerabilidades
conhecidas nas árvores auditáveis e lockfile npm reproduzível. A integração ao vivo também
validou autenticação, saldo e catálogo TTS (12 modelos retornados); a chave efetiva estava válida,
mas com limite mensal esgotado, então nenhuma chamada paga de texto/voz foi disparada.

**Risco que sobrou:** o `pip-audit` não possui registro PyPI para `akita-articles` e o marca como
não auditável; o risco foi reduzido prendendo a dependência a um commit e validando sua instalação
limpa. A compatibilidade Python 3.10 fica coberta pela nova matriz de CI quando ela rodar no GitHub;
a validação local desta mudança ocorreu em Python 3.12 e Node 25, além do alvo Node 18 configurado.

---

## 2026-07-18 — Conformidade explícita com os guias do padrão de qualidade

**O que mudou:** depois da régua automatizada, os guias de backend, frontend, README e
`start_app.py` do Felixo System Design foram tratados como requisitos normativos e auditados um
a um. A porta de entrada agora expõe explicitamente **Iniciar / Rodar**, **Configurar**,
**Instalar / Setup**, **Status** e **Sair**; paginação, chat e texto multilinha deixaram de usar
`input()` cru. O Status passou a consultar virtualenv, `.env`, ferramentas e dependências reais.
O Setup diagnostica Node/npm e instala o Electron com `npm ci`, pelo lockfile, quando disponível.

No frontend, as quatro abas viraram painéis ARIA dentro de um único landmark `<main>`; o rótulo
dos apresentadores ganhou associação semântica e todas as limpezas do renderer usam
`replaceChildren()`, eliminando `innerHTML`. Testes estáticos protegem landmark, painéis, labels,
foco visível e `prefers-reduced-motion`. O README foi reordenado segundo o guia e ganhou estrutura
comentada, ferramentas disponíveis, exemplos de entrada/saída, guia para iniciantes, objetivo e
governança na sequência exigida. `docs/QUALIDADE.md` registra a correspondência entre guias e
controles.

**Validação:** ambiente virtual criado do zero; 184 testes Python e 17 testes Node verdes;
cobertura agregada de 70%; Ruff lint/format, ESLint, sintaxe Node, JSON, links internos,
`git diff --check`, `pip-audit` e `npm audit` aprovados. O desktop foi aberto sem chamada paga e
inspecionado visualmente em 1200 px, 600 px e 380 px; navegação, cartões, configuração ativa e
campo do chat permaneceram íntegros. A chave já registrada havia sido validada na rodada anterior,
mas estava com o limite mensal esgotado, então nenhuma geração paga foi feita.

**Risco que sobrou:** o `akita-articles` continua fora do banco do PyPI Audit, mitigado pelo SHA
imutável e pela instalação limpa. A cobertura está exatamente no piso inicial de 70% e deve subir
gradualmente. A inspeção visual desta rodada foi no Linux; Windows e macOS seguem cobertos por
testes de processo/caminhos e pela CI, mas ainda merecem smoke visual nativo antes de uma release.

---

## 2026-07-18 — Gerenciamento completo e verificável de chaves

**O que mudou:** Configurações e a TUI passaram a mostrar o total de chaves cadastradas, seus
nomes mascarados e a origem efetivamente usada. Cada chave nomeada pode ser registrada, escolhida,
trocada, verificada individualmente contra `/key` e removida. A `OPENROUTER_API_KEY` do `.env` ou
ambiente aparece como uma origem protegida, também verificável e selecionável.

**Decisão de precedência:** configurações antigas preservam o comportamento anterior — ambiente
primeiro. Quando a pessoa clica em **usar** para uma chave nomeada, essa decisão fica persistida no
cofre e vence o ambiente até que outra chave ou a origem `.env`/ambiente seja selecionada. Isso
torna o botão de troca efetivo sem copiar segredo para outro arquivo ou devolvê-lo ao renderer.

**Segurança e contratos:** a bridge ganhou comandos separados para listar metadados, selecionar e
verificar; somente nome, máscara, disponibilidade e resumo de limite saem do backend. O valor
integral permanece no cofre ou ambiente. Arquivos antigos do cofre são migrados em memória com
fallback seguro e continuam compatíveis.

**Validação:** testes cobrem precedência, retorno ao ambiente, persistência, chave inexistente,
verificação de uma chave específica sem vazamento, allowlist IPC e presença das ações na interface.
A régua completa passou em ambiente virtual criado do zero: 195 testes Python, 18 testes Node,
71% de cobertura, lint/formatação, JSON, links, whitespace, `pip-audit` e `npm audit` verdes. O
Electron foi inspecionado manualmente em 600 px e 380 px; um ajuste de linhas `max-content`
impediu a sobreposição dos painéis no modo compacto. O smoke real consultou `/key` usando a
origem de ambiente já presente: a autenticação foi aceita e o limite esgotado foi informado sem
gerar conteúdo, consumir créditos ou expor o segredo. Não havia chave nomeada cadastrada no cofre.

**Risco que sobrou:** verificar uma chave faz uma consulta de rede ao OpenRouter e pode falhar por
indisponibilidade externa. A operação não gera conteúdo nem consome créditos, e a interface mantém
a mensagem de erro restrita ao resumo seguro retornado pelo adaptador.

---

## 2026-07-18 — Leitura fiel e longa com direção prosódica

**Problema:** o perfil `narrador-unico` continuava usando matriz, roteiro e auditoria; portanto
adaptava a obra em vez de apenas lê-la. Enviar um livro inteiro a uma chamada também criaria um
limite de contexto e aumentaria a deriva de voz em saídas longas.

**Decisão:** `verbatim` é um formato de geração, não um perfil. A pessoa escolhe somente uma das
vozes Gemini; modelos, chave e provedor de planejamento continuam na configuração ativa. O texto
é persistido sem normalizar suas bordas, segmentado localmente em até 2.400 caracteres e a
concatenação é verificada caractere por caractere contra a entrada.
O modelo de texto recebe lotes de até 18.000 caracteres e pode devolver apenas direção vocal. O
backend ignora qualquer texto reescrito e usa fallback local para direções ausentes.

**Retomada e segurança:** `prosody.json` guarda plano incremental por hash; o manifesto de áudio
já vincula texto, direção, voz e modelo. Trocar formato ou voz reinicia custo/cache incompatível.
Livros não dependem de uma janela total e textos colados não recebem teto de caracteres do
aplicativo: são persistidos e segmentados antes da IA. Downloads por URL continuam limitados a
5 MiB. Direitos autorais da obra permanecem responsabilidade de quem a importa.

**Interface:** Electron ganhou formato + narrador no cartão do item e a TUI ganhou **Leitura
fiel**, recomendando segundo plano. A inspeção encontrou sobreposição antiga dos painéis da aba
Conteúdo em largura compacta; a grade agora combina lista rolável e detalhe em fluxo normal.

**Validação:** `scripts/check_quality.py` aprovou lint e formatação Ruff, 207 testes Python
com 72% de cobertura, 20 testes Electron, auditorias de dependências Python/Node, whitespace,
JSON e links internos. A aba Conteúdo foi inspecionada nos modos adaptação e leitura fiel em
600 px e 380 px. A chave disponível estava autenticada, mas com limite mensal esgotado; por isso
nenhuma chamada paga de planejamento ou voz foi disparada.

**Risco que sobrou:** modelos TTS em preview podem variar a voz ou interpretar imperfeitamente a
direção. Segmentos curtos reduzem, mas não eliminam, essa limitação do provedor. Uma auditoria
pós-áudio por STT continua futura; antes de publicar uma obra longa, ainda é preciso ouvi-la.

---

## 2026-07-18 — Abort ativo durante chamadas bloqueantes

**Problema reproduzido:** o botão criava corretamente o arquivo `ABORT`, mas o worker só o lia
entre etapas/segmentos. Em uma geração real, o pedido permaneceu pendente durante uma chamada TTS
com timeout de 300 segundos; a execução levou cerca de 145 segundos para alcançar o checkpoint e
parar. Nesse intervalo, a chamada em voo foi concluída e contabilizada.

**Decisão:** a bridge e a TUI agora pedem o marcador cooperativo e também encerram ativamente a
árvore do PID registrado. No POSIX, o worker desanexado possui grupo próprio e recebe
`SIGTERM`, seguido de `SIGKILL` apenas se necessário; no Windows, `taskkill /T /F` encerra worker
e filhos. O próprio processo do comando nunca pode ser alvo. Se PID ou permissão estiverem
indisponíveis, ou se a linha de comando não comprovar que o PID é o worker do mesmo episódio, o
marcador continua aguardando o primeiro checkpoint e a interface mostra esse estado sem afirmar
falsamente que terminou.

**Auditoria de custo:** ao interromper uma chamada ativa, `cost_exact` passa a falso. Fechar a
conexão impede chamadas seguintes, mas não garante que o provedor cancele uma requisição já
recebida ou deixe de cobrá-la. Segmentos e manifestos concluídos permanecem retomáveis.

**Validação:** `scripts/check_quality.py` aprovou lint/formatação, 216 testes Python com 72% de
cobertura, 22 testes Electron, auditorias de dependências Python/Node, whitespace, JSON e links.
A interface permaneceu íntegra em 600 px e 380 px. Um smoke local com worker desanexado e
bloqueado por 60 segundos foi abortado em 0,064 segundo, terminando em `abortado` sem esperar o
checkpoint.

**Risco que sobrou:** a identidade é conferida imediatamente antes do sinal, mas ainda existe uma
janela de corrida muito curta entre essa leitura e o encerramento. O processo atual/grupo do
comando são explicitamente protegidos. Uma chamada remota já aceita pode gerar cobrança que o
processo encerrado não consegue consultar depois.

---

## 2026-07-18 — Log vivo e saúde do worker no Electron

**Problema observado:** o cartão mostrava apenas o último checkpoint concluído. Durante uma
chamada TTS longa, `3/12` podia significar tanto “processando o quarto trecho” quanto “travou”.
Na execução real investigada, o status ainda marcava quatro concluídos enquanto
`generation.log` já registrava o início do quinto e o PID permanecia vivo; depois a geração
continuou avançando até o provedor responder `HTTP 402` por créditos insuficientes, após oito
trechos concluídos.

**Decisão:** a bridge ganhou `generation-log <item-id>`, que lê somente os 64 KiB finais e devolve
no máximo 160 linhas, mtime e saúde do PID. Padrões de chave OpenRouter/Google, header Bearer e
atribuição de `OPENROUTER_API_KEY` são mascarados antes do IPC. Novos workers usam
`PYTHONUNBUFFERED=1`, de modo que cada mensagem chegue ao arquivo imediatamente.

**Interface:** o detalhe do conteúdo ganhou um painel aberto por padrão com cauda rolável,
indicador **worker ativo**, idade da última saída e aviso quando a cauda foi truncada. A consulta
acompanha o polling de dois segundos já usado pelo status; `aria-live` fica apenas no resumo de
saúde para não reler todo o log a cada atualização.

**Diagnóstico de chave:** as telas do OpenRouter mostravam saldo positivo na conta e na chave
nomeada, embora a resposta fosse `402`. O log real esclareceu a sequência: a chave do ambiente
atingiu seu limite, o fallback tentou a chave nomeada e foi ela que recebeu o `402`. Segundo o
contrato do provedor, `402` significa insuficiência na conta ou na chave, mas a resposta não informa
qual das duas; a interface não deve inventar uma causa mais específica.
O status passa a persistir somente o rótulo da chave em tentativa e o atualiza antes de cada
fallback. Faixa global, banner e log o exibem, e o erro orienta verificar saldo da conta e limite
da chave. O diagnóstico não troca a configuração e a falha `402` não é retomada automaticamente.

**Validação:** `scripts/check_quality.py` aprovou lint/formatação, 219 testes Python com 72% de
cobertura, 24 testes Electron, auditorias de dependências Python/Node, whitespace, JSON e links.
O painel, o rótulo da chave efetiva e a mensagem de falha foram inspecionados em 600 px e 380 px
sobre os artefatos da geração real, sem iniciar chamadas adicionais.

**Risco que sobrou:** estar vivo não prova que um provedor remoto responderá; por isso o painel
combina saúde do processo com idade da última linha. O abort ativo continua sendo a saída para
uma chamada que permaneça tempo demais sem progresso.

---

## 2026-07-19 — Estimativas recalibradas por formato

**Problema:** os quatro episódios concluídos tinham `metrics.json` coerentes com a duração real,
mas a interface filtrava a amostra pelo perfil ativo. Como cada piloto usou um perfil diferente,
o cálculo normalmente enxergava um único episódio ou voltava ao fallback, e a troca entre podcast
e leitura fiel não recalculava a confirmação.

**Decisão:** o formato passa a ser a fronteira empírica principal. A estimativa agrega todos os
perfis com o mesmo TTS e formato, usando totais ponderados, mas nunca mistura adaptação e leitura
fiel. A bridge entrega os dois cálculos e o Electron troca valor, faixa, duração e amostra ao mudar
o seletor, inclusive no diálogo que antecede o gasto.

**Validação:** 36 testes Python focados e 24 testes Electron passaram. Nos dados reais, a
adaptação passou a usar três episódios medidos; a leitura fiel usa o piloto compatível existente.
Nenhuma chamada de rede ou geração paga foi feita.

---

## 2026-07-19 — Auditoria objetiva e revisão individual dos chunks

**Problema reproduzido:** a escuta da leitura fiel indicou trechos de silêncio, mas o MP3 final não
permitia localizar rapidamente a fala de origem. A medição dos 12 WAVs encontrou 18,765 segundos
contínuos no fim de um chunk e 6,467 segundos em outro, confirmando que não era apenas impressão.

**Decisão:** entre TTS e montagem, `audiofy.audio_audit` executa `silencedetect` em cada chunk e
persiste `audio-audit.json` atomicamente. O limiar usa -45 dB por pelo menos 1,5 segundo; 2,5
segundos geram aviso e 5 segundos ou 35% do chunk geram achado crítico. A auditoria é diagnóstica:
não apaga áudio e não consome créditos para regenerar sem decisão humana.

**Interface:** Conteúdo e Episódios ganharam **Revisar chunks**. O modal lista arquivos em ordem,
duração, severidade, maior silêncio e player individual. A bridge entrega somente caminhos dos
formatos de áudio dentro da pasta de segmentos; o DOM usa `textContent`.

**Validação parcial:** 51 testes Python focados e 25 testes Electron passaram. A auditoria completa
dos episódios existentes e a inspeção responsiva serão registradas no commit de dados verificados.

---

## 2026-07-19 — Fila ordenada e fallback por saldo/limite

**Problema:** o cofre armazenava várias chaves, mas a ordem secundária vinha da ordenação alfabética
e a interface não permitia definir uma sequência. O TTS avançava apenas em `403` por limite mensal;
um `402` encerrava a geração mesmo quando havia outra chave cadastrada com saldo.

**Decisão:** `keys.json` ganhou `order`, migrado sem quebrar cofres existentes. **Usar** move a chave
para prioridade 1; setas alteram a fila e, no modo nomeado, a primeira é a efetiva. As candidatas
são deduplicadas pelo valor secreto e tentadas nessa ordem. `402` e `403` por limite avançam tanto
nas etapas OpenRouter de texto quanto no TTS, registrando somente o nome seguro no status/log.

**Validação:** 76 testes Python focados e 25 testes Electron passaram, incluindo migração,
persistência da ordem, reordenação, contrato IPC e fallback simulado em `402`/`403`. Nenhuma chave
real foi lida pelos testes e nenhuma chamada paga foi executada.

---

## 2026-07-19 — Música de fundo local com remixagem retomável

**Decisão:** o detalhe de Conteúdo ganhou seletor nativo de arquivo, remoção e volume entre 1% e
25%. MP3, WAV, M4A, AAC, FLAC e OGG de até 500 MiB são copiados pelo launcher para
`.audiofy/music/<sha256>.<ext>`; o worker rejeita qualquer caminho fora desse diretório. Isso evita
persistir caminhos pessoais e mantém a retomada funcional depois que o seletor fecha.

**Montagem:** a narração continua normalizada e a faixa, a 8% por padrão, é repetida pelo ffmpeg
somente até o fim da voz. A opção altera apenas a montagem: chunks compatíveis são reutilizados e
não geram novo custo TTS. `mix.json` registra nome original, hash, volume e regra de duração;
`metrics.json`, `status.json` e `NOTES.md` expõem metadados seguros e o aviso de direitos autorais.

**Segurança e validação parcial:** o IPC continua em allowlist e ganhou somente dois argumentos
limitados no comando `generate`; o renderer não recebe acesso genérico ao sistema de arquivos.
79 testes Python focados e 27 testes Electron passaram. A validação integral e a inspeção em
600 px/380 px serão registradas ao fim da entrega.

---

## 2026-07-19 — Recalibração e auditoria do histórico completo

**Escopo:** `scripts/recalculate_episode_data.py` percorreu localmente os quatro episódios
concluídos e 170 chunks, sem consultar rede ou provedor. Para cada episódio, a rotina mede o MP3
com ffprobe, conta palavras diretamente no roteiro persistido, compara a fonte quando ela ainda
está disponível, executa a política de silêncio e grava `verification.json`. Custos são preservados
com exatidão/procedência declarada, em vez de serem inventados a partir de manifestos antigos
incompletos.

**Resultado:** durações e palavras de roteiro coincidiram nos quatro episódios. As fontes dos dois
artigos e de *Cereja Rougue* também coincidiram; a fonte original de *O valor de terminar* não está
mais em `data/inbox/`, portanto seus 686 termos foram preservados e marcados como indisponíveis
para confronto. Os três episódios de adaptação tiveram 158/158 chunks sem alerta. Em *Cereja
Rougue*, 9/12 ficaram OK, `001_narrador.wav` recebeu aviso, e `006_narrador.wav`/`011_narrador.wav`
foram críticos por silêncios finais de 18,765 s e 6,467 s.

**Cálculos resultantes para 4.780 palavras:** adaptação usa três amostras e estima US$ 1,7190
(faixa US$ 1,3847–2,0550), 33,73 min; leitura fiel usa uma amostra e estima US$ 1,1525 (faixa
US$ 0,9220–1,3830), 35,45 min. A auditoria não regenerou os chunks problemáticos, evitando cobrança
automática e deixando a decisão para a revisão individual no modal.

**Inspeção responsiva:** em 600 px e 380 px, controles de música, ações empilhadas, alertas e
player individual permaneceram utilizáveis. A inspeção revelou e corrigiu um estado apenas visual:
ao reabrir o modal depois de ouvir um chunk, o rótulo antigo de reprodução agora volta para a
instrução neutra junto com o player vazio. A mesma inspeção encontrou nomes de chaves comprimidos
pelos controles da fila em 380 px; os cartões agora reservam a primeira linha inteira para
prioridade, nome e valor mascarado, deixando selo e ações na linha seguinte.

**Validação final:** `python scripts/check_quality.py` aprovou lint e formatação, 237 testes
Python com 74% de cobertura, 27 testes Electron, whitespace, JSON, links e auditorias Python/Node
sem vulnerabilidades conhecidas. `akita-articles` é uma dependência Git privada ao PyPI e por isso
foi explicitamente marcada pelo `pip-audit` como não auditável no índice. A mixagem também passou
por smoke real com ffmpeg: uma trilha curta em loop produziu MP3 válido limitado à narração.

---

## 2026-07-19 — Catálogo completo de episódios gerados

**Problema observado:** a aba Episódios dependia quase inteiramente de `status.json`, mostrava
somente o identificador e estado/custo, e classificava o piloto legado como desconhecido apesar de
existirem `episode.mp3` e `metrics.json` válidos.

**Decisão de contrato:** `_episode_summary` combina status operacional, métricas, auditoria,
`NOTES.md` e metadados reais do MP3. Um arquivo concluído sem status passa a ser reconhecido e
reproduzido; durante uma montagem ativa o MP3 continua oculto para não expor uma versão parcial.
Novas gerações também persistem título e data de criação do conteúdo em `metrics.json`, enquanto
episódios antigos usam o título auditável de `NOTES.md` e a data do identificador como fallback.

**Interface:** os registros agora aparecem do mais recente ao mais antigo em cartões com título,
ID, criação do conteúdo, geração do áudio, duração, arquivo/tamanho, formato, custo, perfil,
palavras e resumo dos achados de silêncio. Em telas estreitas, metadados e ações são empilhados.
A inspeção em 380 px também corrigiu o `flex-basis` horizontal do player global que virava altura
excessiva quando o componente mudava para coluna.

**Validação:** o catálogo foi conferido com os quatro episódios locais, inclusive reprodução e
metadados do piloto legado. A interface permaneceu legível e acionável em 600 px e 380 px.
`python scripts/check_quality.py` aprovou 238 testes Python com 74% de cobertura, 28 testes
Electron, lint, formatação, whitespace, JSON, links e auditorias Python/Node sem vulnerabilidades
conhecidas; `akita-articles` continua explicitamente fora da auditoria do PyPI por ser dependência
Git privada.

---

## 2026-07-19 — Nomes autoexplicativos para fonte, chunks e áudio completo

**Problema observado:** `episode.mp3` e nomes como `001_narrador.wav` só tinham significado
dentro da pasta do episódio. Ao copiar, compartilhar ou abrir o arquivo isoladamente, perdiam-se
a fonte, o episódio, o modo de geração, a completude e, no caso do chunk, sua posição total.

**Contrato v2:** os áudios novos carregam componentes portáveis e limitados de fonte, episódio e
modo. O MP3 termina em `audio-completo.mp3`; cada trecho informa `chunk-N-de-T` e `voz-*`; a entrada
integral é preservada como `fonte-original-completa.md`. `segments.json` registra a mesma semântica
por arquivo, e `metrics.json` aponta explicitamente o MP3 e a fonte. O resolver continua aceitando
`episode.mp3`, portanto integrações e acervos ainda não migrados não deixam de funcionar.

**Migração local:** `scripts/migrate_artifact_names.py --apply` renomeia sem sobrescrever,
sincroniza manifesto, auditoria e lista de concatenação, e nunca chama TTS ou rede. Os quatro
episódios locais, 170 chunks e quatro MP3s foram migrados. Os hashes SHA-256 ordenados antes e
depois permaneceram idênticos. Três fontes ainda disponíveis foram preservadas; *O valor de
terminar* continua honestamente sem documento de origem porque seu texto já não existe no inbox.

**Interface e inspeção:** o catálogo mostra a fonte e o nome descritivo do MP3. O modal identifica
`Chunk N de T`, voz e nome completo. A inspeção real em 600 px e a emulação do viewport de 380 px
confirmaram leitura, quebra dos nomes longos, botões e rolagem utilizáveis.

**Validação final:** `python scripts/check_quality.py` aprovou 240 testes Python com 75% de
cobertura, 28 testes Electron, lint, formatação, whitespace, JSON, links e auditorias Python/Node
sem vulnerabilidades conhecidas. `akita-articles` permanece identificado como dependência Git
privada que não existe no índice do PyPI.

---

## 2026-07-19 — Catálogo expandido de perfis embutidos (5 → 13)

**O que mudou:** oito novos perfis embutidos cobrem formatos e faixas de custo que antes exigiam
criação manual: podcast com 3 vozes (`podcast-trio`, `podcast-trio-economico`), debate com 4 vozes
(`podcast-mesa-redonda`), narração econômica (`narrador-economico`), narração premium com Pro em
texto e auditoria (`narrador-premium`), narração via assinatura (`narrador-assinatura`), podcast
com roteiro Claude Sonnet (`premium-claude`) e podcast via Gemini CLI (`assinatura-gemini`).
Constantes `_TTS`, `_PRO` e `_FLASH` eliminam repetição dos IDs de modelo. As descrições seguem
padrão uniforme: formato + voz + modelo/provedor + benefício.

**Decisões:**

- Vozes do trio escolhidas por contraste tímbrico: Kore (firme/curioso), Puck (animada/animado),
  Gacrux (madura/analítico). Mesa-redonda adiciona Sadachbia (vivaz/provocador) como debatedor.
- `narrador-premium` é o único perfil que usa Gemini Pro tanto para roteiro quanto para auditoria;
  os demais mantêm auditoria no Flash para economizar.
- `premium-claude` aponta `anthropic/claude-sonnet-4.6` via OpenRouter — o ID existe no cache
  local e foi verificado.
- Nomes existentes (`padrao`, `economico`, `narrador-unico`, `assinatura`, `assinatura-codex`)
  preservados para não quebrar `profiles.json` de quem já usa.

**Validação:** 247 testes Python (inclusive 8 novos para os perfis adicionados), 28 testes
Electron, Ruff, `compileall`, `npm run check`, `npm audit` (0 vulnerabilidades) e
`git diff --check` — tudo aprovado. README atualizado com a tabela completa dos 13 perfis.

**Risco que sobrou:** os IDs de modelo apontam versões disponíveis hoje no OpenRouter; se um
modelo for descontinuado, o perfil embutido falhará até que o ID seja atualizado no código.

---

## 2026-07-20 — Perfis expandidos, idioma, reparo e re-geração

**O que mudou:** seis commits entregaram funcionalidades complementares ao catálogo e à interface:

- **Reparo seletivo** (`pipeline.repair_episode`, bridge `repair`/`run-repair`): identifica
  segmentos com silêncio problemático via `audio-audit.json`, deleta apenas os WAVs afetados,
  regenera com cache dos bons e remonta o MP3. A UI mostra warning pós-geração e botão 🔧 Reparar.
  Spinner e shimmer animam etapas ativas.
- **Catálogo de perfis 13 → 30**: organizado por provedor em abas no app (Claude Code, Codex,
  Gemini CLI, Gemini, Claude, OpenAI). Assinaturas (texto grátis) aparecem antes dos perfis API.
  Claude prioriza Opus; OpenAI prioriza GPT SOL.
- **Idioma do episódio** (pt-BR / en): prompts convertidos de constantes para funções
  parametrizadas (`system_prompt(lang)`, `coverage_prompt(lang)`, etc.) com compatibilidade
  retroativa. Episódios em inglês ficam em `<item>__en`. O seletor na aba Conteúdo recalcula
  status e estimativa ao trocar.
- **Botão Re-gerar**: quando já existe episódio no idioma selecionado, o botão muda de
  "Gerar episódio" para "Re-gerar episódio", com status sensível ao idioma.

**Decisões:**

- Categorias de aba derivadas de `text_provider` + prefixo do modelo — sem campo extra no schema.
- `language` adicionado ao `Profile` e `Settings`; o worker recebe `--language=` via child_args.
- Funções de prompt mantêm constantes como alias padrão (`SYSTEM_PROMPT = system_prompt("pt-BR")`)
  para não quebrar imports existentes.
- Reparo reutiliza `_synthesize_turns()` (cache por fingerprint), `audit_segments()` e
  `_assemble()` do pipeline; não inventa fluxo paralelo.

**Validação:** 252 testes Python, 28 testes Electron, Ruff, `compileall`, `npm run check`,
`npm audit` (0 vulnerabilidades) e `git diff --check` — tudo aprovado. README atualizado com
tabela dos 30 perfis, seção de idioma e referências de perfis corrigidas.

**Risco que sobrou:** a troca de idioma não traduz o conteúdo-fonte automaticamente — a
tradução fica a cargo do modelo durante o roteiro, e a qualidade depende da capacidade do
modelo escolhido. IDs de modelo (Opus, GPT SOL) dependem do catálogo vivo do OpenRouter.

---

## 2026-07-20 — Erro de saldo da conta diferenciado do limite de chave

**O que mudou:** a geração real em inglês falhou na primeira fala TTS com HTTP 402
("Insufficient credits") e o app tratou como "saldo ou limite insuficiente" genérico, sem
orientar a recarregar créditos. O auto-resume só funcionava para 403 (limite de chave), não
para 402 (saldo da conta). Corrigido em backend e frontend:

- **Backend** (`pipeline._exhaustion_label`): nova função diferencia 402 ("sem saldo na conta")
  de 403 ("sem limite"). Os logs de fallback agora informam a causa correta.
- **Frontend** (`status-view.js`): mensagem 402 agora diz "O saldo da conta no OpenRouter acabou.
  Recarregue créditos em openrouter.ai/settings/credits e o Audiofy retoma automaticamente."
  A mensagem 403 permanece inalterada.
- **Auto-resume** (`canAutoResumeKeyLimit`): agora cobre tanto 402 quanto 403. Ao recarregar
  créditos, o Audiofy retoma a geração do checkpoint sem precisar clicar em nada.

**Decisões:** 402 é verificado antes de 403 no `friendlyGenerationError` porque uma resposta
com "Insufficient credits" e status 402 deve orientar recarga de saldo, não troca de chave.
O fallback entre chaves no pipeline continua tratando ambos como exaustão — a distinção é
apenas na mensagem ao usuário e no auto-resume.

**Validação:** 253 testes Python, 29 testes Electron (novo: retoma automática após 402), Ruff,
`compileall`, ESLint, `npm audit` (0 vulnerabilidades) e `git diff --check` — tudo aprovado.

**Risco que sobrou:** o auto-resume consulta a chave efetiva a cada minuto; se o usuário
recarregar créditos mas a consulta `/key` do OpenRouter ainda devolver indisponível por cache,
a retomada atrasa até a próxima checagem.
