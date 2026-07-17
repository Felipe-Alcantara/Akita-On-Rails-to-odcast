# 💰 Modelos e custos — pesquisa de mercado

> Preços consultados **ao vivo no catálogo do OpenRouter em 17 de julho de 2026**
> (`/models?output_modalities=speech`). Preços mudam; o menu "Perfis & modelos" consulta o
> catálogo atual com cache de 24h. As estimativas do app são recalculadas com média ponderada e
> faixa dos `metrics.json` do mesmo TTS e perfil. O piloto é somente o fallback inicial:
> **13min01s, 2.155 palavras de fonte, 1.860 palavras de roteiro e US$ 0,624287**.

## 🔊 Modelos TTS disponíveis (OpenRouter)

A maioria dos TTS cobra por **token ou caractere de entrada**; o Gemini cobra por **token de áudio
de saída** (25 tokens/segundo na tabela oficial). Estimativa de voz para um episódio de 13 min:

| Modelo | Preço | ~Custo/episódio (voz) | Observações |
|---|---|---:|---|
| `hexgrad/kokoro-82m` | US$ 0,62/M in | **~US$ 0,002** | aberto, muito barato; qualidade pt-BR precisa de teste |
| `sesame/csm-1b` | US$ 7/M in | ~US$ 0,02 | conversacional, aberto |
| `zyphra/zonos-v0.1` (2 variantes) | US$ 7/M in | ~US$ 0,02 | clonagem de voz |
| `canopylabs/orpheus-3b` | US$ 7/M in | ~US$ 0,02 | expressivo, aberto |
| `x-ai/grok-voice-tts-1.0` | US$ 15/M in | ~US$ 0,05 | |
| `mistralai/voxtral-mini-tts-2603` | US$ 16/M in | ~US$ 0,05 | multilíngue, candidato forte |
| `microsoft/mai-voice-2` | US$ 22/M in | ~US$ 0,07 | naturalidade alta |
| `deepgram/aura-2` | US$ 30/M in | ~US$ 0,09 | latência baixa |
| `minimax/speech-2.8-turbo` | US$ 60/M in | ~US$ 0,19 | |
| `google/gemini-3.1-flash-tts-preview` | US$ 1/M in + US$ 20/M out (áudio) | **~US$ 0,39** | 30 vozes, pt-BR excelente — o validado hoje |
| `minimax/speech-2.8-hd` | US$ 100/M in | ~US$ 0,31 | HD |
| `openai/gpt-audio-mini` | US$ 0,60/M in + US$ 2,40/M out | ~US$ 0,05–0,10 | via chat de áudio, não TTS puro |

**Leitura prática:** o Gemini TTS é o único já validado em pt-BR neste projeto (episódio piloto
aprovado). O maior potencial de economia é testar `voxtral-mini` (~8x mais barato) e
`kokoro-82m` (~200x mais barato) num artigo curto e comparar a naturalidade — o custo do teste
é de centavos. Troque pelo menu Perfis ou `AUDIOFY_TTS_MODEL` (atenção: vozes têm nomes
próprios por modelo; `AUDIOFY_TTS_FORMAT` pode precisar de ajuste, ex.: `mp3`/`wav` em vez
de `pcm`).

## ✍️ Etapas de texto (matriz, roteiro, auditoria)

Três formas de pagar (medição do piloto: ~US$ 0,21 das etapas de texto no perfil `padrao`):

| Via | Custo/episódio | Como ativar |
|---|---:|---|
| **Assinatura (CLI local)** — Claude Code, Gemini CLI, Codex | **US$ 0,00** | perfil `assinatura` ou `AUDIOFY_TEXT_PROVIDER=claude-code` |
| API econômica — ex.: `google/gemini-2.5-flash` em tudo | ~US$ 0,03–0,08 | perfil `economico` |
| API qualidade — `gemini-2.5-pro` no roteiro | ~US$ 0,15–0,25 | perfil `padrao` |

O provedor de assinatura roda a CLI instalada na máquina em modo não interativo e valida o
JSON retornado — mesma auditoria, custo marginal zero dentro do plano.

## 📓 NotebookLM (o caminho mais barato de todos)

Custo **zero** dentro da assinatura Google (gratuito ≈ 3 áudios/dia; AI Plus ≈ 6/dia), com a
ressalva de que o Audio Overview é um *resumo aprofundado* — sem garantia de cobertura
integral nem auditoria. O menu "Exportar p/ NotebookLM" prepara a fonte e as instruções de
foco; o áudio é gerado e baixado manualmente.

## Combinações sugeridas

| Cenário | Texto | TTS | ~Custo/episódio |
|---|---|---|---:|
| Máxima qualidade auditável | API `padrao` | Gemini TTS | ~US$ 0,60 |
| **Assinatura + Gemini TTS** | CLI assinatura | Gemini TTS | **~US$ 0,39** |
| Econômico a validar | CLI assinatura | Voxtral mini | ~US$ 0,05 |
| Ultra barato a validar | CLI assinatura | Kokoro | ~US$ 0,01 |
| Zero custo, sem auditoria | — | NotebookLM | US$ 0,00 |
