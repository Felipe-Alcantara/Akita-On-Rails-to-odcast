# Régua de qualidade

O Audiofy usa uma única automação local e a mesma política na CI:

```bash
python scripts/check_quality.py
```

O utilitário é interno e não tem usuário final; por isso é uma exceção documentada ao menu
interativo exigido para programas do produto. `start_app.py` continua sendo a porta de entrada
única do Audiofy.

## Conformidade com o Felixo System Design

Esta régua traduz os quatro guias aplicáveis do padrão local em controles do projeto:

| Guia | Como o Audiofy atende |
|---|---|
| Qualidade mínima | módulos por responsabilidade, dependências fixadas, CI, testes, auditorias e documentação viva |
| Backend | bridge com erros previsíveis, validação nas fronteiras, integrações isoladas, timeout, retomada e observabilidade por artefatos |
| Frontend | um único landmark principal, HTML semântico, labels, teclado, foco visível, redução de movimento, CSP e DOM sem `innerHTML` |
| README | ordem padronizada, estrutura comentada, ferramentas, uso, guia rápido, limites, segurança e governança |
| `start_app.py` | menu colorido por setas com Rodar, Configurar, Setup, Status e Sair; prompts e subescolhas usam a mesma TUI |

O Status consulta o ambiente real: virtualenv, `.env`, Git, FFmpeg, Node/npm, bibliotecas,
CLIs opcionais, chave ativa, fonte, gerações e episódios. O Setup usa `requirements.txt` e
`electron/package-lock.json`, evitando instalações livres de versão.

CSRF, autenticação HTTP e rate limiting não se aplicam enquanto o produto permanecer um desktop
local sem servidor web público. A fronteira equivalente é a bridge: allowlist de comandos,
limites de argumentos/saída, timeout, validação de caminhos e sandbox do Electron. Se surgir uma
API de rede, esses três controles passam a ser obrigatórios antes de expô-la.

## Controles automatizados

| Área | Controle | Critério |
|---|---|---|
| Python | Ruff lint + formatter | zero erro e formatação estável |
| Regras de negócio | `unittest` + coverage.py | todos os testes verdes e cobertura ≥ 70% |
| Electron | ESLint + `node --check` + Node test runner | zero warning, sintaxe e contratos verdes |
| Dados/documentação | parser JSON + links Markdown | JSON válidos e links internos existentes |
| Dependências | `pip-audit` + `npm audit` | nenhuma vulnerabilidade conhecida moderada ou superior |
| Git | `git diff --check` | nenhum erro de whitespace |

`python scripts/check_quality.py --quick` pula apenas as auditorias que dependem da rede. A CI
repete os controles em Python 3.10/3.12 e Node 18, as versões mínimas relevantes do projeto.

## Verificações manuais

Interfaces puramente visuais são conferidas em janelas de 600 px e 380 px. O fluxo deve continuar
operável por teclado, com foco visível, labels acessíveis, contraste suficiente e respeito a
`prefers-reduced-motion`.

Além da inspeção manual, testes Node impedem regressões no landmark principal, nos painéis ARIA,
no uso de `innerHTML`, no foco visível e na preferência por menos movimento. O teste manual ainda
é necessário para contraste percebido, zoom, textos longos e navegação completa por teclado.

O gerenciamento de chaves tem regressões em três fronteiras: o cofre testa persistência e
precedência; a bridge testa seleção e verificação sem devolver o segredo; o Electron testa a
allowlist dos comandos e a presença das ações de registrar, usar, trocar e verificar. Status,
banner e log também testam o rótulo da chave efetiva e a mensagem de `402` diferencia saldo global
do limite individual, sem persistir o segredo.
Ordem e fallback também são contratos: o cofre migra arquivos antigos, persiste a fila e troca a
prioridade ativa; bridge/Electron expõem reordenação; o pipeline prova avanço tanto em `402` quanto
em `403`, para chamadas de texto e TTS, sem repetir uma chave pelo mesmo valor.

A leitura fiel também tem três fronteiras: funções puras provam recomposição exata e lotes
limitados; a importação preserva espaços e quebras nas bordas; o pipeline prova que respostas do
planejador nunca substituem o texto e que o cache é retomável; bridge/Electron validam modo, voz,
ausência de teto para texto colado e controles responsivos. A inspeção manual da aba Conteúdo
precisa exercitar os dois formatos em 600 px e 380 px.

O cancelamento testa separadamente encerramento portátil da árvore do worker, transição
imediata para `abortado`, fallback cooperativo quando o sistema nega o sinal, contrato da bridge
e feedback de cancelamento pendente no Electron.

A observabilidade da geração testa cauda limitada do arquivo, sanitização de segredos, detecção
do PID vivo, allowlist IPC e renderização somente por `textContent`. A inspeção visual confirma
que log, estado do worker e rolagem continuam operáveis em 600 px e 380 px.

A auditoria de áudio testa o parser de `silencedetect`, limites de aviso/crítico, persistência
atômica, contrato limitado da bridge e modal sem HTML dinâmico. A inspeção manual precisa abrir o
modal, tocar chunks e manter lista/player utilizáveis em 600 px e 380 px. Alertas não removem
artefatos nem disparam regeneração paga.

Gerações reais com OpenRouter não rodam na CI porque consomem créditos e exigem segredo. Mudanças
no pipeline devem usar mocks nos testes e, quando necessário, registrar no `IA.md` o smoke test
real executado sem incluir conteúdo sensível ou chaves.

As estimativas possuem regressão de estratificação: agregam todos os perfis do mesmo TTS e formato,
mas nunca misturam adaptação com leitura fiel. A troca de formato no Electron precisa trocar também
a amostra e o custo usados na confirmação.

## Dependências e atualização

Dependências diretas ficam fixadas em `requirements.txt` e `electron/package-lock.json`.
Ferramentas de desenvolvimento ficam em `requirements-dev.txt`. O Dependabot propõe atualizações
semanais de Python/npm e mensais das actions; cada proposta passa pela régua completa antes de ser
aceita.

O `akita-articles` vem diretamente do GitHub e não possui registro auditável no banco do PyPI.
Para reduzir esse risco, a dependência fica presa a um commit imutável e sua instalação é validada
em ambiente limpo. O restante da árvore Python continua coberto pelo `pip-audit`.
