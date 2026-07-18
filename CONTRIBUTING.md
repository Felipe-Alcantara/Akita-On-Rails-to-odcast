# Como contribuir

Obrigado pelo interesse no Audiofy Content AI. Mudanças pequenas, testáveis e bem explicadas são
mais fáceis de revisar e manter.

## Preparar o ambiente

Requisitos: Python 3.10+, Node.js 18.18+, Git e FFmpeg.

```bash
python -m venv .venv

# Linux/macOS
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

python -m pip install -r requirements-dev.txt
npm ci --prefix electron
```

Para usar o produto, rode `python start_app.py`. O menu também diagnostica e prepara dependências
de execução.

## Validar uma mudança

```bash
# Ciclo rápido, sem auditorias que dependem da rede
python scripts/check_quality.py --quick

# Régua completa antes de entregar
python scripts/check_quality.py
```

A régua executa lint e formatação Python, testes com cobertura mínima, lint/testes Electron,
validação dos JSON versionados, whitespace e auditorias Python/npm. Uma alteração visual também
deve ser conferida manualmente em 600 px e 380 px, com teclado e foco visível.

## Convenções

- Adicione teste automatizado para regra de negócio, contrato, parser, segurança e correção de bug.
- Preserve compatibilidade de formatos e documente qualquer mudança quebradora.
- Não inclua segredos, conteúdo pessoal ou caminhos locais em código, fixtures, logs e documentação.
- Atualize `README.md` quando comandos ou comportamento público mudarem.
- Acrescente uma entrada datada ao fim de `IA.md` para decisões, riscos e validações relevantes;
  não reescreva o histórico anterior.
- Use commits no formato Conventional Commits, por exemplo `fix: limita redirecionamentos da fonte`.

## Pull requests

Explique o problema, a solução, a evidência de validação e os riscos restantes. Evite misturar uma
feature com refatorações não relacionadas. A CI precisa ficar verde antes da revisão final.
