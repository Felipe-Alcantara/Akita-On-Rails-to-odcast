"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");
const test = require("node:test");

const { resolveProjectPath, validateBridgeRequest } = require("../security");

test("bridge aceita somente comandos públicos conhecidos", () => {
  assert.deepEqual(validateBridgeRequest(["status"], undefined), ["status"]);
  assert.deepEqual(validateBridgeRequest(["generation-log", "livro"]),
    ["generation-log", "livro"]);
  assert.deepEqual(validateBridgeRequest(["keys-use", "trabalho"]),
    ["keys-use", "trabalho"]);
  assert.deepEqual(validateBridgeRequest(["keys-use-environment"]),
    ["keys-use-environment"]);
  assert.deepEqual(validateBridgeRequest(["keys-check", "trabalho"]),
    ["keys-check", "trabalho"]);
  assert.deepEqual(validateBridgeRequest(
    ["generate", "custom", "livro", "--mode=verbatim", "--voice=Sulafat"]
  ), ["generate", "custom", "livro", "--mode=verbatim", "--voice=Sulafat"]);
  assert.throws(() => validateBridgeRequest(["run-generation", "x", "y"]));
  assert.throws(() => validateBridgeRequest("status"));
});

test("bridge limita aridade, tipo e volume da entrada", () => {
  assert.throws(() => validateBridgeRequest(["item", "fonte"]));
  assert.throws(() => validateBridgeRequest(["status"], { payload: true }));
  assert.doesNotThrow(() => validateBridgeRequest(
    ["add-text"], "x".repeat(6 * 1024 * 1024 + 1)
  ));
  assert.throws(() => validateBridgeRequest(["chat"], "x".repeat(6 * 1024 * 1024 + 1)));
});

test("bridge não impõe teto de caracteres ao conteúdo colado", () => {
  const securitySource = require("node:fs").readFileSync(
    path.join(__dirname, "..", "security.js"), "utf8"
  );
  assert.match(securitySource, /args\[0\] !== "add-text"/);
  assert.doesNotMatch(securitySource, /MAX_PASTED_TEXT/);
});

test("abertura de arquivo fica confinada ao projeto", () => {
  const root = path.resolve("/tmp/audiofy-project");
  assert.equal(resolveProjectPath("data/episode.mp3", root),
    path.join(root, "data", "episode.mp3"));
  assert.throws(() => resolveProjectPath("../../etc/passwd", root));
});
