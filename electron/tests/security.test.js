"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");
const test = require("node:test");

const { resolveProjectPath, validateBridgeRequest } = require("../security");

test("bridge aceita somente comandos públicos conhecidos", () => {
  assert.deepEqual(validateBridgeRequest(["status"], undefined), ["status"]);
  assert.deepEqual(validateBridgeRequest(["keys-use", "trabalho"]),
    ["keys-use", "trabalho"]);
  assert.deepEqual(validateBridgeRequest(["keys-use-environment"]),
    ["keys-use-environment"]);
  assert.deepEqual(validateBridgeRequest(["keys-check", "trabalho"]),
    ["keys-check", "trabalho"]);
  assert.throws(() => validateBridgeRequest(["run-generation", "x", "y"]));
  assert.throws(() => validateBridgeRequest("status"));
});

test("bridge limita aridade, tipo e volume da entrada", () => {
  assert.throws(() => validateBridgeRequest(["item", "fonte"]));
  assert.throws(() => validateBridgeRequest(["status"], { payload: true }));
  assert.throws(() => validateBridgeRequest(["add-text"], "x".repeat(6 * 1024 * 1024 + 1)));
});

test("abertura de arquivo fica confinada ao projeto", () => {
  const root = path.resolve("/tmp/audiofy-project");
  assert.equal(resolveProjectPath("data/episode.mp3", root),
    path.join(root, "data", "episode.mp3"));
  assert.throws(() => resolveProjectPath("../../etc/passwd", root));
});
