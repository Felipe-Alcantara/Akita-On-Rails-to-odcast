# AGENTS.md — guia operacional do Audiofy

Este arquivo orienta agentes de IA e pessoas que automatizam mudanças neste repositório.

## Antes de alterar

1. Leia `README.md` para entender o produto e `IA.md` para recuperar as decisões anteriores.
2. Preserve a separação existente: fontes, provedores, pipeline, runtime, bridge e interfaces.
3. Procure testes e automações relacionados antes de editar manualmente.
4. Nunca versione `.env`, `.audiofy/`, conversas de `data/chat/` ou conteúdo de `data/inbox/`.

## Contratos obrigatórios

- `start_app.py` é a porta de entrada para usuários e precisa continuar cross-platform.
- A bridge aceita somente comandos declarados e dados limitados; mudanças de contrato exigem
  teste Python e teste Electron quando alcançarem o IPC.
- Operações de rede devem ter timeout, validar entradas e não expor chaves em erros ou logs.
- Artefatos de episódio são retomáveis e auditáveis; não quebre formatos existentes sem migração.
- O Electron mantém `contextIsolation`, sandbox, CSP restritiva e navegação externa bloqueada.

## Critério de pronto

Execute, a partir da raiz:

```bash
python scripts/check_quality.py
```

Durante iterações sem rede, use `python scripts/check_quality.py --quick`. Mudanças visuais no
Electron também exigem verificação manual nas larguras de 600 px e 380 px. Registre mudanças de
arquitetura, comportamento, dependências ou riscos em uma nova entrada datada no fim de `IA.md`.

Commits seguem Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
