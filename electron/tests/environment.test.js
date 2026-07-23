"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { buildBridgeEnvironment } = require("../environment");

test("bridge remove somente valores que vieram do dotenv", () => {
  const environment = buildBridgeEnvironment({
    OPENROUTER_API_KEY: "chave-antiga",
    AUDIOFY_TEXT_MODEL: "modelo-antigo",
    AUDIOFY_DOTENV_LOADED_KEYS: "OPENROUTER_API_KEY,AUDIOFY_TEXT_MODEL",
    PATH: "/usr/bin",
  });

  assert.equal(environment.OPENROUTER_API_KEY, undefined);
  assert.equal(environment.AUDIOFY_TEXT_MODEL, undefined);
  assert.equal(environment.AUDIOFY_DOTENV_LOADED_KEYS, undefined);
  assert.equal(environment.PATH, "/usr/bin");
  assert.equal(environment.PYTHONPATH, "src");
});

test("bridge preserva chave definida explicitamente no shell", () => {
  const environment = buildBridgeEnvironment({
    OPENROUTER_API_KEY: "chave-do-shell",
    AUDIOFY_DOTENV_LOADED_KEYS: "AUDIOFY_TEXT_MODEL",
  });

  assert.equal(environment.OPENROUTER_API_KEY, "chave-do-shell");
});

test("bridge ignora nomes inválidos na marca de procedência", () => {
  const environment = buildBridgeEnvironment({
    PATH: "/usr/bin",
    "../TOKEN": "preservado",
    "CHAVE COM ESPAÇO": "preservada",
    AUDIOFY_DOTENV_LOADED_KEYS: "PATH,../TOKEN,CHAVE COM ESPAÇO",
  });

  assert.equal(environment.PATH, undefined);
  assert.equal(environment["../TOKEN"], "preservado");
  assert.equal(environment["CHAVE COM ESPAÇO"], "preservada");
});

test("bridge força UTF-8 para não corromper acentos em caminhos", () => {
  const environment = buildBridgeEnvironment({ PATH: "/usr/bin" });

  // Sem isso o Python usa o encoding do console (cp1252 no Windows) e devolve
  // caminhos corrompidos, que o app rejeita por não casarem com a raiz.
  assert.equal(environment.PYTHONIOENCODING, "utf-8");
});
