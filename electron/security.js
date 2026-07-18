"use strict";

const path = require("path");

const MAX_ARGUMENT_LENGTH = 16 * 1024;
const MAX_STDIN_LENGTH = 6 * 1024 * 1024;

const COMMAND_ARITY = Object.freeze({
  "sources": [1, 1], "sync": [2, 2], "items": [2, 2], "search": [3, 3],
  "item": [3, 3], "generate": [3, 4], "status": [1, 2], "abort": [2, 2],
  "tts-catalog": [1, 1], "notebooklm": [3, 3], "add-url": [2, 2],
  "add-text": [1, 1], "chat": [1, 2], "chat-history": [1, 2],
  "chat-clear": [1, 2], "settings-info": [1, 1], "keys-list": [1, 1],
  "keys-add": [2, 2], "keys-activate": [2, 2], "keys-use": [2, 2],
  "keys-use-environment": [1, 1], "keys-check": [2, 2],
  "keys-check-environment": [1, 1], "keys-remove": [2, 2],
  "balance": [1, 1], "profiles-list": [1, 1], "profiles-activate": [2, 2],
  "profiles-save": [1, 1], "profiles-remove": [2, 2], "models-list": [1, 2],
  "setup-check": [1, 1], "setup-install": [1, 1],
});

function validateBridgeRequest(args, stdinData) {
  if (!Array.isArray(args) || !args.every((value) => typeof value === "string")) {
    throw new TypeError("A bridge exige uma lista de argumentos textuais.");
  }
  const arity = COMMAND_ARITY[args[0]];
  if (!arity || args.length < arity[0] || args.length > arity[1]) {
    throw new Error("Comando da bridge não permitido ou com argumentos inválidos.");
  }
  if (args.some((value) => value.length > MAX_ARGUMENT_LENGTH || value.includes("\0"))) {
    throw new Error("Um argumento da bridge excede o limite permitido.");
  }
  if (stdinData !== undefined && typeof stdinData !== "string") {
    throw new TypeError("A entrada da bridge precisa ser texto.");
  }
  if ((stdinData || "").length > MAX_STDIN_LENGTH) {
    throw new Error("A entrada da bridge excede o limite permitido.");
  }
  return args;
}

function resolveProjectPath(target, projectRoot) {
  if (typeof target !== "string" || !target.trim() || target.includes("\0")) {
    throw new TypeError("Caminho inválido.");
  }
  const root = path.resolve(projectRoot);
  const resolved = path.resolve(root, target);
  if (resolved !== root && !resolved.startsWith(root + path.sep)) {
    throw new Error("O app só pode abrir arquivos dentro do projeto.");
  }
  return resolved;
}

module.exports = { resolveProjectPath, validateBridgeRequest };
