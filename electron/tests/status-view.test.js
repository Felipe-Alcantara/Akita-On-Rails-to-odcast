"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const {
  canAutoResumeKeyLimit, friendlyGenerationError, generationFeedback,
} = require("../renderer/status-view");

test("traduz limite mensal da chave sem expor URL interna do provedor", () => {
  const message = friendlyGenerationError(
    "HTTP 403 em /audio/speech: Key limit exceeded (monthly limit). " +
    "Manage it using https://openrouter.ai/workspaces/default/keys/identificador"
  );

  assert.match(message, /chave usada naquela execução/i);
  assert.match(message, /retoma automaticamente/i);
  assert.doesNotMatch(message, /https?:\/\//);
  assert.doesNotMatch(message, /identificador/);
});

test("falha rápida permanece visível com checkpoint e ação recomendada", () => {
  const feedback = generationFeedback({
    state: "falhou",
    stage: "tts",
    progress: { current: 66, total: 92 },
    cost_usd: 0.854023,
    last_error: "HTTP 403: Key limit exceeded (monthly limit)",
  });

  assert.equal(feedback.visible, true);
  assert.equal(feedback.tone, "error");
  assert.equal(feedback.percent, 72);
  assert.match(feedback.label, /66\/92/);
  assert.match(feedback.label, /execução anterior/i);
  assert.match(feedback.label, /progresso foi preservado/i);
  assert.match(feedback.cost, /aproximado/i);
});

test("retoma limite antigo somente quando a chave atual tem saldo", () => {
  const status = {
    state: "falhou",
    last_error: "HTTP 403: Key limit exceeded (monthly limit)",
  };

  assert.equal(canAutoResumeKeyLimit(status, { ok: true, valid: true }), true);
  assert.equal(canAutoResumeKeyLimit(status, { ok: true, valid: false }), false);
  assert.equal(canAutoResumeKeyLimit(
    { ...status, last_error: "HTTP 401: unauthorized" },
    { ok: true, valid: true }
  ), false);
});

test("estado de inicialização aparece antes do primeiro segmento", () => {
  const feedback = generationFeedback({
    state: "rodando",
    stage: "iniciando",
    progress: { current: 66, total: 92 },
    cost_usd: 0.8,
    cost_exact: true,
  });

  assert.equal(feedback.visible, true);
  assert.equal(feedback.tone, "active");
  assert.match(feedback.label, /iniciando/i);
  assert.doesNotMatch(feedback.cost, /aproximado/i);
});

test("pedido de abort pendente aparece como cancelamento em andamento", () => {
  const feedback = generationFeedback({
    state: "rodando",
    stage: "tts",
    abort_requested_at: Date.now() / 1000,
    progress: { current: 1, total: 12 },
    cost_usd: 0.1,
    cost_exact: true,
  });

  assert.equal(feedback.visible, true);
  assert.equal(feedback.tone, "warning");
  assert.match(feedback.label, /cancelamento solicitado/i);
});

test("geração nova não é anunciada como retomada", () => {
  const fresh = generationFeedback({
    state: "rodando",
    stage: "iniciando",
    progress: { current: 0, total: 0 },
    resume_count: 0,
    cost_usd: 0,
    cost_exact: true,
  });
  assert.doesNotMatch(fresh.label, /retomada/i);
  assert.match(fresh.label, /geração/i);

  const resumed = generationFeedback({
    state: "rodando",
    stage: "iniciando",
    progress: { current: 66, total: 92 },
    resume_count: 2,
    cost_usd: 0.8,
    cost_exact: true,
  });
  assert.match(resumed.label, /retomada/i);
});

test("helper e renderer compartilham a página sem colisão de escopo", () => {
  const rendererDirectory = path.resolve(__dirname, "../renderer");
  const source = ["status-view.js", "renderer.js"]
    .map((file) => fs.readFileSync(path.join(rendererDirectory, file), "utf8"))
    .join("\n");

  assert.doesNotThrow(() => new vm.Script(source));
});

test("player embutido fica disponível e não abre o MP3 externamente", () => {
  const html = fs.readFileSync(path.resolve(__dirname, "../renderer/index.html"), "utf8");
  const renderer = fs.readFileSync(path.resolve(__dirname, "../renderer/renderer.js"), "utf8");

  assert.match(html, /id="episode-player"[^>]*controls/);
  assert.match(renderer, /function playInApp\(/);
  assert.match(renderer, /playInApp\(episode\.mp3/);
  assert.doesNotMatch(renderer, /onclick = \(\) => openProjectPath\(episode\.mp3\)/);
});

test("renderer recarrega Conteúdo ao abrir a aba e depois do Chat", () => {
  const renderer = fs.readFileSync(
    path.resolve(__dirname, "../renderer/renderer.js"), "utf8"
  );

  assert.match(renderer, /button\.dataset\.tab === "content"\) loadItems/);
  assert.match(renderer, /if \(currentSource === "custom"\) await loadItems/);
});
