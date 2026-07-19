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
  assert.match(renderer, /\["audio-chunks", itemId\]/);
  assert.match(renderer, /projectPathToFileUrl\(chunk\.path\)/);
  assert.match(renderer, /chunk\.longest_silence_seconds/);
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
