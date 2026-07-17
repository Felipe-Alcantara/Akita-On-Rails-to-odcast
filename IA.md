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
  caracteres dos identificadores curtos (o limite real de 5 MiB é aplicado por `add_text`).
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
