"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const rendererDirectory = path.resolve(__dirname, "../renderer");

function readRendererFile(name) {
  return fs.readFileSync(path.join(rendererDirectory, name), "utf8");
}

test("página usa um único landmark principal e painéis semânticos", () => {
  const html = readRendererFile("index.html");

  assert.equal((html.match(/<main\b/g) || []).length, 1);
  assert.equal((html.match(/<section\b[^>]*role="tabpanel"/g) || []).length, 4);
  assert.match(html, /id="pf-presenters"[^>]*role="group"[^>]*aria-labelledby=/);
  assert.doesNotMatch(html, /<label>Apresentadores<\/label>/);
});

test("renderer não usa innerHTML para manipular a interface", () => {
  const renderer = readRendererFile("renderer.js");

  assert.doesNotMatch(renderer, /\.innerHTML\s*=/);
});

test("abas de perfil fixam a família do modelo de texto", () => {
  const renderer = readRendererFile("renderer.js");

  assert.match(renderer, /"Claude Code": "claude-code"/);
  assert.match(renderer, /"Claude API": "openrouter"/);
  assert.match(renderer, /const lockedProvider = providerMap\[tabCategory\]/);
  assert.match(renderer, /pf-provider-field.*classList\.toggle\("hidden", Boolean\(lockedProvider\)\)/);
  assert.match(renderer, /providerSelect\.disabled = Boolean\(lockedProvider\)/);
  assert.match(renderer, /openProfileForm\(profile, category\)/);
});

test("TTS oferece uma lista única agrupada por tiers", () => {
  const html = readRendererFile("index.html");
  const renderer = readRendererFile("renderer.js");

  assert.doesNotMatch(html, /id="pf-tts-vendor"/);
  assert.match(renderer, /function configureTtsPicker\(/);
  assert.match(renderer, /modelsCatalog\.tts_tiers/);
  assert.match(renderer, /Ultra-econômico — prototipagem/);
});

test("modelo TTS sem catálogo não pede uma voz inventada", () => {
  const renderer = readRendererFile("renderer.js");

  assert.match(renderer, /Nenhuma voz catalogada para este modelo/);
  assert.match(renderer, /voiceElement\.disabled = true/);
  assert.doesNotMatch(renderer, /voiceElement\.type = "text"/);
});

test("vozes mostram nomes normalizados sem origem do catálogo", () => {
  const renderer = readRendererFile("renderer.js");

  assert.match(renderer, /function voiceLabel\(voice, ttsModel\)/);
  assert.match(renderer, /replace\(\/\[_-\]\+\/g, " "\)/);
  assert.match(renderer, /languageNames =/);
  assert.match(renderer, /inglês \(EUA\)/);
  assert.match(renderer, /kokoroLanguages =/);
  assert.match(renderer, /português — Brasil/);
  assert.match(renderer, /function voiceToneLabel\(tone\)/);
  assert.match(renderer, /character\.toUpperCase\(\)/);
  assert.doesNotMatch(renderer, /voz informada pelo OpenRouter/);
});

test("trocar o TTS descarta voz que não pertence ao novo catálogo", () => {
  const renderer = readRendererFile("renderer.js");

  assert.match(renderer, /voices\.some\(\(\[name\]\) => name === voice\) \? voice : voices\[0\]\[0\]/);
  assert.doesNotMatch(renderer, /configuração atual.*voiceLabel/);
});

test("leitura fiel usa o catálogo e os nomes normalizados do TTS ativo", () => {
  const renderer = readRendererFile("renderer.js");

  assert.match(renderer, /info\.voice_catalogs\[info\.tts_model\]/);
  assert.match(renderer, /voiceLabel\(voice, info\.tts_model\)/);
  assert.match(renderer, /Nenhuma voz catalogada para este modelo/);
});

test("voz do perfil único não é perguntada novamente na geração", () => {
  const renderer = readRendererFile("renderer.js");

  assert.match(renderer, /settingsInfo\.presenters\.length === 1/);
  assert.match(renderer, /!needsNarrator \|\| Boolean\(profileVoice\)/);
  assert.match(renderer, /updateGenerationMode\(\);/);
});

test("estilos preservam foco visível e preferência por menos movimento", () => {
  const styles = readRendererFile("styles.css");

  assert.match(styles, /:focus-visible/);
  assert.match(styles, /@media\s*\(prefers-reduced-motion:\s*reduce\)/);
});

test("gerenciamento permite registrar, usar, trocar e verificar chaves", () => {
  const html = readRendererFile("index.html");
  const renderer = readRendererFile("renderer.js");
  const styles = readRendererFile("styles.css");

  assert.match(html, /id="keys-summary"/);
  assert.match(html, /Registrar chave/);
  assert.match(renderer, /\["keys-use", key\.name\]/);
  assert.match(renderer, /\["keys-use-environment"\]/);
  assert.match(renderer, /\["keys-check", key\.name\]/);
  assert.match(renderer, /\["keys-check-environment"\]/);
  assert.match(renderer, /\["keys-move", key\.name, "up"\]/);
  assert.match(renderer, /#\$\{key\.priority\}/);
  assert.match(renderer, /row\.className = "key-row"/);
  assert.match(styles, /\.key-row \.row-main\s*\{[^}]*flex:\s*1 0 100%/s);
  assert.match(styles, /\.settings-grid\s*\{[^}]*grid-template-rows:\s*repeat\(2, max-content\)/s);
  assert.match(styles, /#tab-content\s*\{[^}]*grid-template-rows:\s*minmax\(280px, 45vh\)/s);
});

test("leitura fiel permite escolher um narrador sem enviar texto reescrito", () => {
  const html = readRendererFile("index.html");
  const renderer = readRendererFile("renderer.js");

  assert.match(html, /id="generation-mode"/);
  assert.match(html, /value="verbatim">Leitura fiel, sem reescrita/);
  assert.match(html, /id="narration-voice"/);
  assert.match(renderer, /`--mode=\$\{selectedMode\}`/);
  assert.match(renderer, /`--voice=\$\{selectedVoice\}`/);
  assert.match(renderer, /O texto não será reescrito/);
  assert.match(renderer, /selectedItem\.estimates\[mode\]/);
  assert.match(renderer, /renderItemEstimate\(\)/);
});

test("abort diferencia encerramento imediato do fallback por checkpoint", () => {
  const renderer = readRendererFile("renderer.js");

  assert.match(renderer, /result\.stopped/);
  assert.match(renderer, /Geração abortada agora/);
  assert.match(renderer, /aguardando o primeiro checkpoint disponível/);
});

test("conteúdo mostra log vivo e atividade do worker sem HTML dinâmico", () => {
  const html = readRendererFile("index.html");
  const renderer = readRendererFile("renderer.js");
  const styles = readRendererFile("styles.css");

  assert.match(html, /id="generation-log-panel"/);
  assert.match(html, /id="generation-log"[^>]*role="log"/s);
  assert.match(renderer, /\["generation-log", itemId\]/);
  assert.match(renderer, /result\.worker_alive/);
  assert.match(renderer, /output\.textContent/);
  assert.match(renderer, /chave efetiva:/);
  assert.match(renderer, /configChip\("Chave efetiva"/);
  assert.match(styles, /#generation-log\s*\{[^}]*max-height:\s*230px/s);
});

test("modal permite auditar e ouvir chunks individualmente", () => {
  const html = readRendererFile("index.html");
  const renderer = readRendererFile("renderer.js");

  assert.match(html, /<dialog id="chunk-modal"/);
  assert.match(html, /id="chunk-player"[^>]*controls/);
  assert.match(renderer, /"audio-chunks", itemId/);
  assert.match(renderer, /projectPathToFileUrl\(chunk\.path\)/);
  assert.match(renderer, /chunk\.longest_silence_seconds/);
  assert.match(renderer, /Chunk \$\{chunkIndex\} de \$\{chunkTotal\}/);
  assert.match(renderer, /chunk\.file/);
  assert.match(renderer, /chunk-now-playing"\)\.textContent = "Escolha um chunk para ouvir\./);
  assert.doesNotMatch(renderer, /\.innerHTML\s*=/);
});

test("música de fundo usa seletor nativo, volume limitado e confirma direitos", () => {
  const html = readRendererFile("index.html");
  const renderer = readRendererFile("renderer.js");
  const preload = fs.readFileSync(path.resolve(__dirname, "../preload.js"), "utf8");
  const main = fs.readFileSync(path.resolve(__dirname, "../main.js"), "utf8");

  assert.match(html, /id="btn-background-music"/);
  assert.match(html, /id="background-volume"[^>]*min="1"[^>]*max="25"/s);
  assert.match(html, /direito de publicar/);
  assert.match(preload, /chooseBackgroundMusic/);
  assert.match(main, /dialog\.showOpenDialog/);
  assert.match(renderer, /`--background-music=\$\{backgroundMusic\}`/);
  assert.match(renderer, /`--background-volume=\$\{volume \|\| 0\.08\}`/);
});

test("catálogo de episódios mostra datas, duração, arquivo e auditoria", () => {
  const html = readRendererFile("index.html");
  const renderer = readRendererFile("renderer.js");
  const styles = readRendererFile("styles.css");

  assert.match(html, /id="episodes-summary"/);
  assert.match(renderer, /Criação do conteúdo/);
  assert.match(renderer, /Geração do áudio/);
  assert.match(renderer, /formatEpisodeDuration\(episode\.duration_seconds\)/);
  assert.match(renderer, /formatFileSize\(episode\.file_size_bytes\)/);
  assert.match(renderer, /episode\.audio_audit\.critical/);
  assert.match(styles, /\.episode-facts\s*\{[^}]*grid-template-columns:/s);
  assert.match(styles, /\.episode-actions\s*\{[^}]*display:\s*flex/s);
  assert.match(styles, /\.player-dock audio\s*\{[^}]*flex:\s*0 0 auto/s);
  assert.match(styles, /\.player-title\s*\{[^}]*flex:\s*0 0 auto/s);
});

test("escolhas que custam crédito não mudam sozinhas com a roda do mouse", () => {
  const html = readRendererFile("index.html");
  const renderer = readRendererFile("renderer.js");

  // A roda sobre um <select> troca a opção no Chromium sem o usuário perceber.
  assert.match(
    renderer,
    /GENERATION_OPTION_IDS = \["narration-voice", "generation-mode", "generation-language"\]/,
  );
  assert.match(renderer, /addEventListener\("wheel", \(event\) => event\.preventDefault\(\)/);

  // Só uma escolha deliberada sobrepõe a voz do perfil ao redesenhar o combo.
  assert.match(renderer, /voiceTouchedByUser && previousVoice/);
  assert.match(renderer, /voiceTouchedByUser = true/);

  // E a divergência precisa ficar visível, com volta em um clique.
  assert.match(html, /id="narration-voice-hint"/);
  assert.match(renderer, /Diferente do perfil/);
  assert.match(renderer, /markVoiceMatchesProfile/);
});

test("configuração da geração fica travada enquanto o episódio é sintetizado", () => {
  const html = readRendererFile("index.html");
  const renderer = readRendererFile("renderer.js");
  const styles = readRendererFile("styles.css");

  // Trocar voz/formato/idioma no meio misturaria configurações no mesmo episódio:
  // os segmentos já sintetizados não mudam.
  assert.match(renderer, /function lockGenerationOptions\(running\)/);
  assert.match(renderer, /\$\(id\)\.disabled = running/);
  assert.match(renderer, /lockGenerationOptions\(Boolean\(running\)\)/);
  assert.match(renderer, /btn-background-music"\)\.disabled = running/);
  assert.match(renderer, /background-volume"\)\.disabled = running/);

  // Sem item selecionado não há geração para proteger — a trava precisa sair.
  assert.match(renderer, /lockGenerationOptions\(false\)/);

  // E o motivo da trava precisa estar visível, não só o campo cinza.
  assert.match(html, /id="generation-options-lock"/);
  assert.match(html, /aborte e gere novamente/);
  assert.match(styles, /\.options-lock\s*\{/);
});
