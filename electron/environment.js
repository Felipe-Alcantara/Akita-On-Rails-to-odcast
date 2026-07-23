"use strict";

const DOTENV_PROVENANCE_ENV = "AUDIOFY_DOTENV_LOADED_KEYS";
const ENV_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;

function buildBridgeEnvironment(baseEnvironment = process.env) {
  // A bridge responde em JSON com acentos e caminhos do projeto. Sem forçar
  // UTF-8, o Python usa o encoding do console (cp1252 no Windows) e devolve
  // caminhos corrompidos, que deixam de casar com a raiz validada pelo app.
  const environment = { ...baseEnvironment, PYTHONPATH: "src", PYTHONIOENCODING: "utf-8" };
  const dotenvKeys = (environment[DOTENV_PROVENANCE_ENV] || "").split(",");
  for (const key of dotenvKeys) {
    if (ENV_NAME.test(key)) delete environment[key];
  }
  delete environment[DOTENV_PROVENANCE_ENV];
  return environment;
}

module.exports = { buildBridgeEnvironment, DOTENV_PROVENANCE_ENV };
