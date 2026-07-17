"use strict";

(function initStatusView() {
function isKeyLimitFailure(error) {
  return /Key limit exceeded|monthly limit/i.test(String(error || ""));
}

function friendlyGenerationError(error) {
  const detail = String(error || "");
  if (isKeyLimitFailure(detail)) {
    return "A chave usada naquela execução atingiu o limite mensal. A configuração atual " +
      "pode já ser outra; o Audiofy retoma automaticamente quando ela está disponível.";
  }
  if (/HTTP 401|unauthorized|invalid.*key/i.test(detail)) {
    return "A chave do OpenRouter não foi aceita. Confira a chave configurada.";
  }
  if (/HTTP 402|insufficient.*credit|credit.*insufficient/i.test(detail)) {
    return "A conta do OpenRouter está sem créditos suficientes.";
  }
  const sanitized = detail
    .replace(/https?:\/\/\S+/g, "")
    .replace(/\s+/g, " ")
    .trim();
  return sanitized.slice(0, 300) || "A geração encontrou um erro não identificado.";
}

function generationFeedback(status) {
  if (!status) return { visible: false, tone: "", percent: 0, label: "", cost: "" };
  const progress = status.progress || {};
  const current = Number(progress.current) || 0;
  const total = Number(progress.total) || 0;
  const percent = total ? Math.max(0, Math.min(100, Math.round(100 * current / total))) : 0;
  const count = total ? `${current}/${total} (${percent}%)` : "preparando";
  const accuracy = status.cost_exact ? "" : " (aproximado)";
  const cost = `💰 US$ ${(Number(status.cost_usd) || 0).toFixed(4)}${accuracy} até agora`;

  if (status.state === "rodando") {
    const retry = status.retry
      ? ` · retomando fala ${status.retry.segment}, tentativa ` +
        `${status.retry.attempt}/${status.retry.max_attempts}`
      : "";
    const label = status.stage === "iniciando"
      ? `Iniciando a retomada — checkpoint ${count}.`
      : `Etapa: ${status.stage || "iniciando"} — ${count}${retry}`;
    return { visible: true, tone: "active", percent, label, cost };
  }

  if (status.state === "falhou") {
    const stage = status.stage ? ` na etapa ${status.stage}` : "";
    const checkpoint = total ? ` após ${current}/${total}` : "";
    const reason = friendlyGenerationError(status.last_error);
    return {
      visible: true,
      tone: "error",
      percent,
      label: `A execução anterior falhou${stage}${checkpoint}. ${reason} ` +
        "O progresso foi preservado.",
      cost,
    };
  }

  if (status.state === "abortado") {
    return {
      visible: true,
      tone: "warning",
      percent,
      label: `Geração abortada no checkpoint ${count}; o progresso foi preservado.`,
      cost,
    };
  }

  return { visible: false, tone: "", percent, label: "", cost };
}

function canAutoResumeKeyLimit(status, keyCheck) {
  return Boolean(
    status && status.state === "falhou" && isKeyLimitFailure(status.last_error)
    && keyCheck && keyCheck.ok && keyCheck.valid
  );
}

const statusView = {
  canAutoResumeKeyLimit, friendlyGenerationError, generationFeedback, isKeyLimitFailure,
};
if (typeof module !== "undefined" && module.exports) module.exports = statusView;
if (typeof window !== "undefined") window.audiofyStatusView = statusView;
})();
