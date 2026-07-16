# 🎙️ Akita on Rails to Podcast

<div align="center">

![Status](https://img.shields.io/badge/status-MVP-green?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)
![OpenRouter](https://img.shields.io/badge/OpenRouter-API-6C47FF?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

**Pipeline auditável para transformar artigos públicos do AkitaOnRails em podcasts técnicos com dois apresentadores.**

[📖 Plano técnico](docs/PLANO-TECNICO.md) • [🎯 Objetivo](#-sobre-o-projeto) • [⚠️ Limites](#-limites-atuais)

</div>

---

## 📋 Índice

- [🎯 Sobre o projeto](#-sobre-o-projeto)
- [🚀 Como usar](#-como-usar)
- [📖 Documentação](#-documentação)
- [📁 Estrutura](#-estrutura)
- [⚠️ Limites atuais](#-limites-atuais)
- [🤝 Contribuições](#-contribuições)
- [📝 Licença](#-licença)

---

## 🎯 Sobre o projeto

O projeto propõe transformar os artigos em Markdown do repositório público
[`akitaonrails/akitaonrails.github.io`](https://github.com/akitaonrails/akitaonrails.github.io)
em episódios com dois apresentadores. O objetivo central não é produzir apenas um resumo:
cada episódio deve ter uma **matriz de cobertura**, roteiro verificável, transcrição e auditoria
contra o artigo original.

O desenho recomendado usa o **OpenRouter** como interface unificada para modelos de texto,
Text-to-Speech e Speech-to-Text, preservando a possibilidade de trocar provedores sem acoplar a
regra de negócio a um modelo específico.

## 🚀 Como usar

Requisitos: Python 3.10+, `git`, `ffmpeg` e a biblioteca `requests`. É preciso uma chave do
[OpenRouter](https://openrouter.ai/keys) com créditos.

```bash
python3 start_app.py
```

O menu interativo é a porta de entrada única do programa:

1. **Instalar / Setup** — verifica dependências e cria o `.env`;
2. **Configurar chave** — grava a `OPENROUTER_API_KEY`;
3. **Sincronizar blog** — clona/atualiza o repositório oficial de artigos;
4. **Listar artigos** — todos os artigos em português, mais recentes primeiro;
5. **Gerar episódio** — pipeline completo: matriz de cobertura → roteiro com dois
   apresentadores → auditoria → TTS por turno → montagem com ffmpeg.

Também há atalhos diretos: `start_app.py list`, `start_app.py generate <número|id>`,
`start_app.py sync`, `start_app.py status`.

Cada episódio fica em `data/episodes/<artigo>/` com os artefatos auditáveis
(`coverage.json`, `script.json`, `audit.json`, `segments/`, `episode.mp3`, `NOTES.md`).
Se uma etapa falhar, rodar novamente retoma de onde parou sem regenerar o que já existe.
A geração exibe uma estimativa de custo e pede confirmação antes de consumir créditos.

## 📖 Documentação

O [plano técnico completo](docs/PLANO-TECNICO.md) registra:

- requisitos de fidelidade e critérios de aprovação;
- arquitetura do pipeline e responsabilidades;
- alternativas NotebookLM, Gemini e OpenRouter;
- contratos de dados e prompts iniciais;
- estimativas de custo;
- licenciamento, segurança, riscos e etapas do MVP.

## 📁 Estrutura

```text
Akita-On-Rails-to-Podcast/
├── 📁 docs/
│   └── PLANO-TECNICO.md     # Arquitetura e decisões do projeto
├── 📁 src/
│   └── 📁 akita_podcast/
│       ├── config.py        # Variáveis de ambiente, caminhos e modelos
│       ├── source_repo.py   # Sincronização Git e parser de artigos
│       ├── openrouter.py    # Adaptador HTTP (chat JSON e TTS)
│       └── pipeline.py      # Cobertura → roteiro → auditoria → áudio
├── 📁 tests/
│   └── 📁 unit/             # Testes do parser (python3 -m unittest discover -s tests)
├── 📁 data/                 # Artefatos locais, ignorados pelo Git
├── start_app.py             # Menu interativo — porta de entrada
├── IA.md                    # Linha do tempo de decisões
├── .env.example             # Nomes das variáveis, sem valores
├── LICENSE                  # Licença do código deste projeto
└── README.md
```

## ⚠️ Limites atuais

- A auditoria pós-áudio (STT do arquivo final, fase 4 do plano) ainda não foi implementada;
  a revisão dos episódios gerados é humana.
- A auditoria do roteiro reporta pendências, mas não bloqueia a geração — a decisão de
  publicar é de quem revisa (`audit.json`).
- Nomes de modelos e vozes do OpenRouter mudam com o tempo; tudo é configurável via `.env`.
- Conteúdo gerado por modelos pode conter omissões ou distorções; por isso, a auditoria faz
  parte do produto e não é uma etapa opcional.
- O conteúdo derivado dos artigos precisa respeitar a licença declarada pelo autor do blog.

## 🤝 Contribuições

Contribuições são bem-vindas. Ideias especialmente úteis incluem experimentos de qualidade de
voz em português, métricas de cobertura, parsers seguros de Markdown e formas transparentes de
publicar a atribuição de cada episódio.

## 📝 Licença

O código e a documentação originais deste repositório estão sob a licença MIT. Os artigos de
Fabio Akita e as adaptações produzidas a partir deles possuem condições próprias, documentadas no
[plano técnico](docs/PLANO-TECNICO.md#-licenciamento-e-atribuição).

## 👤 Autor

**Felipe Martin**

---

⭐ Se o projeto for útil, considere acompanhar sua evolução e contribuir.
