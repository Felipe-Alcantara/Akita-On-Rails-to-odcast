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
  });

  assert.equal(feedback.visible, true);
  assert.equal(feedback.tone, "active");
  assert.match(feedback.label, /iniciando/i);
});

test("helper e renderer compartilham a página sem colisão de escopo", () => {
  const rendererDirectory = path.resolve(__dirname, "../renderer");
  const source = ["status-view.js", "renderer.js"]
    .map((file) => fs.readFileSync(path.join(rendererDirectory, file), "utf8"))
    .join("\n");

  assert.doesNotThrow(() => new vm.Script(source));
});
