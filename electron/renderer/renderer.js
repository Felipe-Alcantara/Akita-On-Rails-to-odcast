// Renderer do Audiofy Desktop — paridade completa com a CLI:
// chat de pesquisa com ações, fontes plugáveis (conteúdo próprio + Akita),
// geração com progresso/custo ao vivo, abort, NotebookLM, chaves, saldo e perfis.

const $ = (id) => document.getElementById(id);
const bridge = (args, stdin) => window.audiofy.bridge(args, stdin);
const {
  canAutoResumeKeyLimit, friendlyGenerationError, generationFeedback, isKeyLimitFailure,
} = window.audiofyStatusView;

async function openProjectPath(target) {
  const error = await window.audiofy.openPath(target);
  if (error) alert(error);
}

function makeElement(tag, className = "", text = "") {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text) element.textContent = text;
  return element;
}

function projectPathToFileUrl(target) {
  const encoded = String(target).split(/[\\/]/).map(encodeURIComponent).join("/");
  return `file://${encoded.startsWith("/") ? encoded : `/${encoded}`}`;
}

function setPlayerSource(path, title = "Episódio") {
  const player = $("episode-player");
  const url = projectPathToFileUrl(path);
  if (player.dataset.source !== url) {
    player.pause();
    player.src = url;
    player.dataset.source = url;
    player.load();
  }
  $("player-title").textContent = `🎧 ${title}`;
  $("player-dock").classList.remove("hidden");
  return player;
}

function playInApp(path, title) {
  const player = setPlayerSource(path, title);
  player.play().catch(() => player.focus());
}

let currentSource = "custom";
let selectedItem = null;
let pollTimer = null;
let sourcesByKey = new Map();
let generationRequestPending = false;
const automaticResumeAttempts = new Set();
const AUTOMATIC_RESUME_RECHECK_MS = 60 * 1000;

// ── Abas ──────────────────────────────────────────────────────────────────

const tabButtons = [...document.querySelectorAll("#tabs .tab")];

function activateTab(button, moveFocus = false) {
  for (const candidate of tabButtons) {
    const active = candidate === button;
    candidate.classList.toggle("active", active);
    candidate.setAttribute("aria-selected", String(active));
    candidate.tabIndex = active ? 0 : -1;
    const page = $(`tab-${candidate.dataset.tab}`);
    page.classList.toggle("hidden", !active);
    page.setAttribute("aria-hidden", String(!active));
  }
  if (moveFocus) button.focus();
  if (button.dataset.tab === "settings") loadSettings();
  if (button.dataset.tab === "episodes") refreshStatus();
  if (button.dataset.tab === "content") loadItems($("search").value.trim());
}

tabButtons.forEach((button, index) => {
  button.onclick = () => activateTab(button);
  button.onkeydown = (event) => {
    const direction = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!direction && event.key !== "Home" && event.key !== "End") return;
    event.preventDefault();
    const targetIndex = event.key === "Home" ? 0 : event.key === "End"
      ? tabButtons.length - 1 : (index + direction + tabButtons.length) % tabButtons.length;
    activateTab(tabButtons[targetIndex], true);
  };
});

// ── Chat ──────────────────────────────────────────────────────────────────

function addChatMessage(role, text, actions = []) {
  const box = $("chat-messages");
  const message = document.createElement("div");
  message.className = `msg ${role}`;
  message.textContent = text;
  box.appendChild(message);
  const pending = [];
  for (const action of actions) {
    const button = document.createElement("button");
    button.className = "action-chip";
    button.textContent = `⚡ ${action.descricao || action.tipo}`;
    button.onclick = () => runAction(action, button);
    box.appendChild(button);
    pending.push({ action, button });
  }
  box.scrollTop = box.scrollHeight;
  return pending;
}

async function runAction(action, button) {
  if (button) button.disabled = true;
  let result;
  if (action.tipo === "adicionar_texto") {
    result = await bridge(["add-text"],
      JSON.stringify({ title: action.titulo, text: action.texto }));
    if (result.ok) {
      addChatMessage("system", `✔ Conteúdo criado: ${result.item_id}`);
      if (currentSource === "custom") loadItems();
    }
  } else if (action.tipo === "adicionar_url") {
    result = await bridge(["add-url", action.url]);
    if (result.ok) {
      addChatMessage("system", `✔ Conteúdo adicionado: ${result.item_id}`);
      if (currentSource === "custom") loadItems();
    }
  } else if (action.tipo === "buscar") {
    result = await bridge(["search", action.fonte || "akita", action.termos || ""]);
    if (result.ok) {
      const lines = result.items.slice(0, 10)
        .map((i) => `• ${i.item_id} — ${i.title}`).join("\n");
      addChatMessage("system", lines || "Nada encontrado.");
    }
  } else if (action.tipo === "gerar") {
    const source = action.fonte || currentSource;
    const detail = await bridge(["item", source, action.item_id]);
    const estimate = detail.ok
      ? ` (~US$ ${detail.estimated_cost_usd.toFixed(2)}; faixa ` +
        `US$ ${detail.estimate.cost_min_usd.toFixed(2)}–` +
        `${detail.estimate.cost_max_usd.toFixed(2)})`
      : "";
    // Sem confirmação por decisão do usuário: o custo fica visível no chat e o
    // banner global de gasto ativo continua alertando enquanto a geração roda.
    addChatMessage("system", `Gerando "${action.item_id}"${estimate} — consome créditos.`);
    result = await bridge(["generate", source, action.item_id]);
    if (result.ok && result.started) {
      addChatMessage("system", "✔ Geração iniciada — acompanhe na aba Episódios.");
      refreshStatus();
    } else if (result.ok) {
      addChatMessage("system", `✖ ${result.reason || "a geração não foi iniciada"}`);
    }
  } else if (action.tipo === "exportar_notebooklm") {
    result = await bridge(["notebooklm", action.fonte || currentSource, action.item_id]);
    if (result.ok) addChatMessage("system", `✔ Pacote NotebookLM: ${result.pack}`);
  } else {
    result = { ok: false, error: `ação desconhecida: ${action.tipo}` };
  }
  if (result && !result.ok) {
    addChatMessage("system", `✖ ${result.reason || result.error}`);
  }
}

async function sendChat() {
  const text = $("chat-text").value.trim();
  if (!text) return;
  $("chat-text").value = "";
  addChatMessage("user", text);
  const thinking = document.createElement("div");
  thinking.className = "msg assistant muted";
  thinking.textContent = "… pesquisando";
  $("chat-messages").appendChild(thinking);
  $("chat-send").disabled = true;
  const result = await bridge(["chat", "principal"], text);
  thinking.remove();
  $("chat-send").disabled = false;
  if (result.ok) {
    const pending = addChatMessage("assistant", result.reply, result.actions);
    // O chat executa tudo sozinho: cada ação proposta roda automaticamente,
    // em ordem, sem esperar clique. Os botões continuam para reexecutar à mão.
    for (const { action, button } of pending) {
      await runAction(action, button);
    }
    // O Chat pode criar/atualizar conteúdo enquanto outra aba está aberta.
    // Recarregar aqui evita deixar a lista de Conteúdo próprio com snapshot antigo.
    if (currentSource === "custom") await loadItems($("search").value.trim());
  } else addChatMessage("system", `✖ ${result.error}`);
}

$("chat-send").onclick = sendChat;
$("chat-text").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendChat();
  }
});
$("chat-clear").onclick = async () => {
  await bridge(["chat-clear", "principal"]);
  $("chat-messages").replaceChildren();
};

async function loadChatHistory() {
  const result = await bridge(["chat-history", "principal"]);
  if (!result.ok) return;
  if (Array.isArray(result.sources)) {
    sourcesByKey = new Map(result.sources.map((source) => [source.key, source]));
  }
  for (const message of result.messages) {
    addChatMessage(message.role === "user" ? "user" : "assistant", message.content);
  }
}

// ── Fontes e itens ────────────────────────────────────────────────────────

async function loadSources() {
  const result = await bridge(["sources"]);
  if (!result.ok) return;
  sourcesByKey = new Map(result.sources.map((source) => [source.key, source]));
  const select = $("source-select");
  select.replaceChildren();
  for (const source of result.sources) {
    const option = document.createElement("option");
    option.value = source.key;
    option.textContent = `${source.name}${source.ready ? "  ·  pronta" : "  ·  requer sync"}`;
    option.title = source.description;
    select.appendChild(option);
  }
  select.value = currentSource;
  renderSourceStatus();
}

function renderSourceStatus(message = "") {
  const source = sourcesByKey.get(currentSource);
  const status = $("source-status");
  if (message) {
    status.textContent = message;
    return;
  }
  status.textContent = source
    ? `${source.ready ? "✓ Fonte pronta" : "⚠ Fonte ainda não sincronizada"} · ${source.description}`
    : "";
}

$("source-select").onchange = () => {
  currentSource = $("source-select").value;
  $("add-content").classList.toggle("hidden", currentSource !== "custom");
  selectedItem = null;
  $("detail").classList.add("hidden");
  $("detail-empty").classList.remove("hidden");
  renderSourceStatus();
  loadItems();
};

async function loadItems(query = "") {
  const command = query ? ["search", currentSource, query] : ["items", currentSource];
  const result = await bridge(command);
  const list = $("items");
  list.replaceChildren();
  if (!result.ok) {
    list.appendChild(makeElement("li", "muted", `Erro: ${result.error}`));
    return;
  }
  if (!result.items.length) {
    list.appendChild(makeElement("li", "muted",
      "Nenhum item — adicione conteúdo acima ou peça sugestões no Chat."));
  }
  for (const item of result.items) {
    const row = document.createElement("li");
    row.appendChild(makeElement("span", "date", item.published_at));
    row.appendChild(makeElement("span", "item-title", item.title));
    row.onclick = () => selectItem(item, row);
    list.appendChild(row);
  }
}

async function selectItem(item, row) {
  document.querySelectorAll("#items li").forEach((li) => li.classList.remove("selected"));
  row.classList.add("selected");
  const detail = await bridge(["item", currentSource, item.item_id]);
  if (!detail.ok) return;
  selectedItem = { ...detail, source: currentSource };
  $("detail-empty").classList.add("hidden");
  $("detail").classList.remove("hidden");
  $("detail-title").textContent = detail.title;
  $("detail-meta").textContent =
    `${detail.published_at} · ~${detail.words} palavras · ${detail.url || "texto local"}`;
  if (detail.actual) {
    const accuracy = detail.actual.cost_exact ? "confirmado pelo provedor" : "aproximado";
    $("detail-estimate").textContent =
      `Realizado: US$ ${detail.actual.cost_usd.toFixed(4)} (${accuracy}) · ` +
      `${(detail.actual.duration_seconds / 60).toFixed(1)} min`;
  } else {
    const estimate = detail.estimate;
    const basis = estimate.sample_count
      ? `${estimate.sample_count} episódio(s) medido(s)` : "piloto medido";
    $("detail-estimate").textContent =
      `Estimativa: ~US$ ${estimate.cost_usd.toFixed(2)} ` +
      `(faixa US$ ${estimate.cost_min_usd.toFixed(2)}–${estimate.cost_max_usd.toFixed(2)}) · ` +
      `~${estimate.duration_minutes.toFixed(1)} min · ${basis}`;
  }
  refreshStatus();
}

$("btn-sync").onclick = async () => {
  $("btn-sync").disabled = true;
  renderSourceStatus("… sincronizando fonte");
  const result = await bridge(["sync", currentSource]);
  $("btn-sync").disabled = false;
  if (!result.ok) {
    renderSourceStatus(`✖ ${result.error}`);
    return;
  }
  await loadSources();
  loadItems($("search").value.trim());
};

let searchDebounce = null;
$("search").oninput = () => {
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => loadItems($("search").value.trim()), 350);
};

$("btn-add-url").onclick = async () => {
  const url = $("add-url").value.trim();
  if (!url) return;
  $("btn-add-url").disabled = true;
  const result = await bridge(["add-url", url]);
  $("btn-add-url").disabled = false;
  if (result.ok) {
    $("add-url").value = "";
    loadItems();
  } else {
    alert(result.error);
  }
};

$("btn-add-text").onclick = async () => {
  const title = $("add-title").value.trim();
  const text = $("add-text").value.trim();
  if (!title || !text) return;
  const result = await bridge(["add-text"], JSON.stringify({ title, text }));
  if (result.ok) {
    $("add-title").value = "";
    $("add-text").value = "";
    loadItems();
  } else {
    alert(result.error);
  }
};

// ── Geração, episódios e status ───────────────────────────────────────────

function updateGenerateButton() {
  const button = $("btn-generate");
  const running = button.dataset.running === "true";
  button.disabled = generationRequestPending || running;
  button.textContent = generationRequestPending ? "⏳ Iniciando…" : "🎙️ Gerar episódio";
}

function showGenerationRequest(message, tone = "active") {
  const box = $("progress-box");
  box.classList.remove("hidden", "active", "error", "warning");
  box.classList.add(tone);
  $("progress-label").textContent = message;
  $("cost-label").textContent = "";
}

function scheduleAutomaticResumeRecheck(status, attemptKey, itemId) {
  setTimeout(() => {
    automaticResumeAttempts.delete(attemptKey);
    if (selectedItem && selectedItem.item_id === itemId) void maybeAutoResume(status);
  }, AUTOMATIC_RESUME_RECHECK_MS);
}

async function maybeAutoResume(status) {
  if (!selectedItem || !status || status.state !== "falhou"
      || !isKeyLimitFailure(status.last_error)) return;
  const item = { source: selectedItem.source, itemId: selectedItem.item_id };
  const attemptKey = `${item.itemId}:${status.updated_at || 0}`;
  if (automaticResumeAttempts.has(attemptKey)) return;
  automaticResumeAttempts.add(attemptKey);

  const keyCheck = await bridge(["balance"]);
  if (!selectedItem || selectedItem.item_id !== item.itemId) return;
  if (!canAutoResumeKeyLimit(status, keyCheck)) {
    scheduleAutomaticResumeRecheck(status, attemptKey, item.itemId);
    return;
  }

  generationRequestPending = true;
  updateGenerateButton();
  showGenerationRequest(
    "A falha era de uma chave anterior. Retomando automaticamente do checkpoint…"
  );
  try {
    const result = await bridge(["generate", item.source, item.itemId]);
    if (!result.ok || (!result.started && result.reason !== "geração já em andamento")) {
      showGenerationRequest(
        `Não foi possível retomar automaticamente: ${result.reason || result.error}`,
        "error"
      );
      scheduleAutomaticResumeRecheck(status, attemptKey, item.itemId);
      return;
    }
    await refreshStatus();
  } finally {
    generationRequestPending = false;
    updateGenerateButton();
  }
}

$("btn-generate").onclick = async () => {
  if (!selectedItem) return;
  const force = $("generate-force").checked;
  const confirmed = confirm(
    `Gerar episódio de "${selectedItem.title}"?\n\n` +
    `Custo estimado: ~US$ ${selectedItem.estimated_cost_usd.toFixed(2)} ` +
    `(faixa US$ ${selectedItem.estimate.cost_min_usd.toFixed(2)}–` +
    `${selectedItem.estimate.cost_max_usd.toFixed(2)}) ` +
    `(consome créditos do OpenRouter).` +
    (force ? "\n\nA cobertura, o roteiro e a auditoria serão regenerados." : "")
  );
  if (!confirmed) return;
  const args = ["generate", selectedItem.source, selectedItem.item_id];
  if (force) args.push("--force");
  generationRequestPending = true;
  updateGenerateButton();
  showGenerationRequest("Solicitando a retomada ao backend…");
  try {
    const result = await bridge(args);
    if (!result.ok || !result.started) {
      const reason = result.reason || result.error || "a geração não foi iniciada";
      showGenerationRequest(`Não foi possível iniciar: ${reason}`, "error");
      return;
    }
    $("generate-force").checked = false;
    showGenerationRequest("Geração iniciada; carregando o checkpoint…");
    await refreshStatus();
  } finally {
    generationRequestPending = false;
    updateGenerateButton();
  }
};

$("btn-notebooklm").onclick = async () => {
  if (!selectedItem) return;
  const result = await bridge(["notebooklm", selectedItem.source, selectedItem.item_id]);
  if (result.ok) {
    openProjectPath(result.pack);
  } else {
    alert(result.error);
  }
};

$("btn-abort").onclick = async () => {
  if (!selectedItem) return;
  const result = await bridge(["abort", selectedItem.item_id]);
  if (result.ok && result.aborted) {
    alert("Abort solicitado — a geração para no próximo segmento.");
  }
  refreshStatus();
};

async function refreshStatus() {
  const overview = await bridge(["status"]);
  if (!overview.ok) return;

  const banner = $("running-banner");
  if (overview.anything_running) {
    $("running-detail").textContent = overview.running
      .map((e) => {
        const retry = e.retry
          ? ` · retomando fala ${e.retry.segment} (${e.retry.attempt}/${e.retry.max_attempts})`
          : "";
        const accuracy = e.cost_exact ? "" : " aprox.";
        return `${e.episode_id} (US$ ${e.cost_usd.toFixed(3)}${accuracy}${retry})`;
      }).join(", ");
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }

  renderEpisodes(overview.episodes);
  if (selectedItem) renderSelectedStatus(overview.episodes);

  clearTimeout(pollTimer);
  if (overview.anything_running) pollTimer = setTimeout(refreshStatus, 2000);
}

function renderSelectedStatus(episodes) {
  const status = episodes.find((e) => e.episode_id === selectedItem.item_id);
  const running = status && status.state === "rodando";
  const done = status && status.mp3;
  const feedback = generationFeedback(status);

  $("btn-abort").classList.toggle("hidden", !running);
  $("btn-generate").dataset.running = String(Boolean(running));
  updateGenerateButton();
  $("btn-play").classList.toggle("hidden", !done);
  $("btn-folder").classList.toggle("hidden", !status);
  const box = $("progress-box");
  box.classList.toggle("hidden", !feedback.visible);
  box.classList.remove("active", "error", "warning");
  if (feedback.tone) box.classList.add(feedback.tone);

  $("progress-fill").style.width = `${feedback.percent}%`;
  $("progress-track").setAttribute("aria-valuenow", String(feedback.percent));
  $("progress-label").textContent = feedback.label;
  $("cost-label").textContent = feedback.cost;
  $("btn-play").onclick = () => status && status.mp3
    && playInApp(status.mp3, selectedItem.title);
  $("btn-folder").onclick = () => status && openProjectPath(status.dir);
  void maybeAutoResume(status);
}

function renderEpisodes(episodes) {
  const list = $("episodes");
  list.replaceChildren();
  if (!episodes.length) list.appendChild(makeElement("li", "muted", "Nenhum episódio ainda."));
  for (const episode of episodes) {
    const row = document.createElement("li");
    const accuracy = episode.cost_exact ? "" : " aprox.";
    const cost = episode.cost_usd
      ? ` · US$ ${episode.cost_usd.toFixed(4)}${accuracy}` : "";
    const progress = episode.state === "rodando" && episode.progress.total
      ? ` · ${episode.progress.current}/${episode.progress.total}` : "";
    const retry = episode.retry
      ? ` · retry ${episode.retry.attempt}/${episode.retry.max_attempts}` : "";
    row.appendChild(makeElement("span", `state-${episode.state}`, "●"));
    row.appendChild(makeElement("span", "episode-title", episode.episode_id));
    row.appendChild(makeElement("span", "muted", `${episode.state}${progress}${retry}${cost}`));
    if (episode.state === "falhou" && episode.last_error) {
      row.title = friendlyGenerationError(episode.last_error);
    }
    if (episode.state === "rodando") {
      const abortButton = document.createElement("button");
      abortButton.textContent = "🛑";
      abortButton.title = "Abortar";
      abortButton.setAttribute("aria-label", `Abortar ${episode.episode_id}`);
      abortButton.onclick = () => bridge(["abort", episode.episode_id]).then(refreshStatus);
      row.appendChild(abortButton);
    }
    if (episode.mp3) {
      const play = document.createElement("button");
      play.textContent = "▶️";
      play.title = "Ouvir";
      play.setAttribute("aria-label", `Ouvir ${episode.episode_id}`);
      play.onclick = () => playInApp(episode.mp3, episode.episode_id);
      row.appendChild(play);
    }
    const folder = document.createElement("button");
    folder.textContent = "📂";
    folder.title = "Abrir pasta";
    folder.setAttribute("aria-label", `Abrir pasta de ${episode.episode_id}`);
    folder.onclick = () => openProjectPath(episode.dir);
    row.appendChild(folder);
    list.appendChild(row);
  }
}

// ── Configurações ─────────────────────────────────────────────────────────

let modelsCatalog = null; // {text_models, tts_models, gemini_voices}
let settingsInfo = null;

function configChip(label, value, className = "") {
  const chip = makeElement("span", `config-chip ${className}`.trim());
  chip.appendChild(makeElement("strong", "", `${label}:`));
  chip.appendChild(makeElement("span", "model-id", value));
  return chip;
}

function renderActiveConfig(info) {
  const strip = $("active-config-strip");
  strip.replaceChildren();
  strip.appendChild(makeElement("span", "config-strip-label", "Configuração ativa"));
  strip.appendChild(configChip("Perfil", info.profile));
  if (info.overrides.length) {
    const override = configChip("Override", info.overrides.join(", "), "warn");
    override.title = "Variáveis de ambiente têm prioridade sobre o perfil ativo";
    strip.appendChild(override);
  }

  if (info.text_provider === "openrouter") {
    strip.appendChild(configChip("Texto", `OpenRouter · ${info.text_model}`));
  } else {
    const cli = info.subscription_clis.find((item) => item.key === info.text_provider);
    const availability = cli && !cli.available ? " · CLI não encontrada" : "";
    const model = info.subscription_model || (cli && cli.configured_model) || "modelo padrão da CLI";
    strip.appendChild(configChip("Texto",
      `${cli ? cli.name : info.text_provider} · ${model}${availability}`,
      cli && !cli.available ? "warn" : ""));
  }

  strip.appendChild(configChip("TTS", `${info.tts_model}${info.has_key ? "" : " · sem chave"}`,
    info.has_key ? "" : "warn"));
}

async function loadActiveConfig() {
  const info = await bridge(["settings-info"]);
  if (info.ok) {
    settingsInfo = info;
    renderActiveConfig(info);
  } else {
    $("active-config-strip").textContent = `✖ Não foi possível carregar os modelos: ${info.error}`;
  }
  return info;
}

function renderSetup(setup) {
  const list = $("setup-list");
  list.replaceChildren();
  for (const check of setup.checks) {
    const row = document.createElement("li");
    row.appendChild(makeElement("span", `badge ${check.ok ? "ok" : "warn"}`,
      check.ok ? "✓" : "✗"));
    const detail = makeElement("div", "row-main");
    detail.appendChild(makeElement("span", "row-title", check.name));
    if (!check.ok) detail.appendChild(makeElement("span", "muted small", check.hint));
    row.appendChild(detail);
    if (!check.required) row.appendChild(makeElement("span", "badge", "opcional"));
    list.appendChild(row);
  }
  $("setup-message").textContent = setup.ready
    ? "✓ Ambiente pronto para gerar episódios."
    : "Há itens obrigatórios que precisam de atenção.";
}

async function useKey(command, label) {
  const result = await bridge(command);
  if (!result.ok) {
    $("balance-line").className = "small state-falhou";
    $("balance-line").textContent = `✖ ${result.error}`;
    return;
  }
  $("balance-line").className = "small state-concluido";
  $("balance-line").textContent = `✓ ${label} agora está em uso.`;
  await loadSettings();
}

async function loadSettings() {
  const keys = await bridge(["keys-list"]);
  if (keys.ok) {
    const list = $("keys-list");
    list.replaceChildren();
    const plural = keys.count === 1 ? "chave cadastrada" : "chaves cadastradas";
    $("keys-summary").textContent =
      `${keys.count} ${plural} · em uso: ${keys.effective_source || "nenhuma"}`;

    const appendVerificationButton = (row, command) => {
      const status = makeElement("span", "muted small");
      const verify = makeElement("button", "ghost", "verificar");
      verify.onclick = async () => {
        verify.disabled = true;
        status.className = "muted small";
        status.textContent = "consultando…";
        const result = await bridge(command);
        verify.disabled = false;
        status.className = result.ok && result.available
          ? "small state-concluido" : "small state-falhou";
        status.textContent = result.ok ? result.detail : `✖ ${result.error}`;
      };
      row.querySelector(".row-main").appendChild(status);
      row.appendChild(verify);
    };

    if (keys.environment.available) {
      const row = document.createElement("li");
      const detail = makeElement("div", "row-main");
      detail.appendChild(makeElement("span", "row-title", "OPENROUTER_API_KEY"));
      detail.appendChild(makeElement("span", "muted mono",
        `${keys.environment.source} · valor protegido`));
      row.appendChild(detail);
      if (keys.environment.in_use) row.appendChild(makeElement("span", "badge ok", "em uso"));
      else {
        const use = makeElement("button", "ghost", "usar");
        use.onclick = () => useKey(["keys-use-environment"], keys.environment.source);
        row.appendChild(use);
      }
      appendVerificationButton(row, ["keys-check-environment"]);
      list.appendChild(row);
    }

    if (!keys.keys.length && !keys.environment.available) {
      list.appendChild(makeElement("li", "muted", "Nenhuma chave disponível."));
    }
    for (const key of keys.keys) {
      const row = document.createElement("li");
      const detail = makeElement("div", "row-main");
      detail.appendChild(makeElement("span", "row-title", key.name));
      detail.appendChild(makeElement("span", "muted mono", key.masked));
      row.appendChild(detail);
      if (key.in_use) row.appendChild(makeElement("span", "badge ok", "em uso"));
      else {
        if (key.selected) row.appendChild(makeElement("span", "badge", "selecionada"));
        const use = makeElement("button", "ghost", "usar");
        use.onclick = () => useKey(["keys-use", key.name], key.name);
        row.appendChild(use);
      }
      appendVerificationButton(row, ["keys-check", key.name]);
      const remove = document.createElement("button");
      remove.textContent = "🗑️";
      remove.className = "ghost";
      remove.setAttribute("aria-label", `Remover chave ${key.name}`);
      remove.onclick = () => {
        if (confirm(`Remover a chave "${key.name}"?`)) {
          bridge(["keys-remove", key.name]).then(loadSettings);
        }
      };
      row.appendChild(remove);
      list.appendChild(row);
    }
  }

  const profiles = await bridge(["profiles-list"]);
  if (profiles.ok) {
    const list = $("profiles-list");
    list.replaceChildren();
    for (const profile of profiles.profiles) {
      const row = document.createElement("li");
      const active = profile.name === profiles.active;
      const provider = profile.text_provider === "openrouter"
        ? "API" : `assinatura ${profile.text_provider}`;
      const detail = makeElement("div", "row-main");
      detail.appendChild(makeElement("span", "row-title", profile.name));
      if (profile.description) {
        detail.appendChild(makeElement("span", "muted small", profile.description));
      }
      detail.appendChild(makeElement("span", "muted small",
        `texto: ${provider} · tts: ${profile.tts_model} · ${profile.presenters_spec}`));
      row.appendChild(detail);
      if (active) row.appendChild(makeElement("span", "badge ok", "ativo"));
      if (!active) {
        const activate = document.createElement("button");
        activate.textContent = "ativar";
        activate.className = "ghost";
        activate.onclick = () =>
          bridge(["profiles-activate", profile.name]).then(loadSettings);
        row.appendChild(activate);
      }
      const edit = makeElement("button", "ghost", "editar");
      edit.onclick = () => openProfileForm(profile);
      row.appendChild(edit);
      if (profile.custom) {
        const remove = document.createElement("button");
        remove.textContent = "🗑️";
        remove.className = "ghost";
        remove.setAttribute("aria-label", `Remover perfil ${profile.name}`);
        remove.onclick = () => {
          if (confirm(`Remover o perfil "${profile.name}"?`)) {
            bridge(["profiles-remove", profile.name]).then(loadSettings);
          }
        };
        row.appendChild(remove);
      }
      list.appendChild(row);
    }
  }

  const info = await loadActiveConfig();
  if (info.ok) {
    const clis = info.subscription_clis
      .map((c) => `${c.key}${c.configured_model ? ` (${c.configured_model})` : ""}` +
        `${c.available ? " ✓" : " ✗"}`).join("  ");
    const textModel = info.text_provider === "openrouter"
      ? info.text_model
      : info.subscription_model || "modelo padrão da CLI";
    const auditModel = info.text_provider === "openrouter" ? info.audit_model : textModel;
    $("settings-info").textContent =
      `perfil ativo:   ${info.profile}\n` +
      `texto via:      ${info.text_provider}\n` +
      `roteiro:        ${textModel}\n` +
      `auditoria:      ${auditModel}\n` +
      `tts:            ${info.tts_model}\n` +
      `chave:          ${info.has_key ? `configurada (${info.key_source || "ativa"})` : "não configurada"}\n` +
      `overrides:      ${info.overrides.length ? info.overrides.join(", ") : "nenhum"}\n` +
      `apresentadores: ${info.presenters
        .map((p) => `${p.speaker}:${p.voice}${p.style ? ":" + p.style : ""}`).join(", ")}\n` +
      `assinaturas:    ${clis}`;
  }

  const setup = await bridge(["setup-check"]);
  if (setup.ok) renderSetup(setup);
}

$("btn-key-add").onclick = async () => {
  const name = $("key-name").value.trim();
  const value = $("key-value").value.trim();
  if (!name || !value) return;
  const result = await bridge(["keys-add", name], value);
  if (result.ok) {
    $("key-name").value = "";
    $("key-value").value = "";
    $("balance-line").className = "small state-concluido";
    $("balance-line").textContent = `✓ Chave "${name}" registrada. Use o botão “usar” para ativá-la.`;
    loadSettings();
  } else {
    alert(result.error);
  }
};

$("btn-balance").onclick = async () => {
  $("balance-line").textContent = "consultando…";
  const result = await bridge(["balance"]);
  $("balance-line").className = result.ok && result.valid
    ? "small state-concluido" : "small state-falhou";
  $("balance-line").textContent = result.ok ? result.detail : `✖ ${result.error}`;
};

$("btn-setup-check").onclick = async () => {
  $("setup-message").textContent = "… verificando ambiente";
  const result = await bridge(["setup-check"]);
  if (result.ok) renderSetup(result);
  else $("setup-message").textContent = `✖ ${result.error}`;
};

$("btn-setup-install").onclick = async () => {
  if (!confirm("Instalar tudo que estiver faltando (git, ffmpeg, dependências Python) e criar o .env, se necessário?")) return;
  const button = $("btn-setup-install");
  button.disabled = true;
  $("setup-message").textContent = "… preparando o ambiente; isso pode levar alguns minutos";
  const result = await bridge(["setup-install"]);
  button.disabled = false;
  if (!result.ok) {
    $("setup-message").textContent = `✖ ${result.error}`;
    return;
  }
  renderSetup(result);
  if (result.actions.length) {
    $("setup-message").textContent = result.actions
      .map((action) => `${action.ok ? "✓" : "✗"} ${action.name}: ${action.detail}`)
      .join(" · ");
  }
};

$("btn-load-catalog").onclick = async () => {
  $("catalog-box").textContent = "carregando…";
  const result = await bridge(["tts-catalog"]);
  if (!result.ok) {
    $("catalog-box").textContent = `✖ ${result.error}`;
    return;
  }
  const models = result.models.length
    ? result.models.map((model) => model.id).join("\n")
    : "Nenhum modelo carregado.";
  const voices = Object.entries(result.gemini_voices)
    .map(([voice, style]) => `${voice} (${style})`).join(", ");
  const warning = result.catalog_error ? `Aviso: ${result.catalog_error}\n\n` : "";
  $("catalog-box").textContent =
    `${warning}Modelos TTS:\n${models}\n\nVozes Gemini:\n${voices}`;
};

// ── Editor de perfil ──────────────────────────────────────────────────────

function fillModelSelect(select, models, current) {
  select.replaceChildren();
  const knownIds = new Set(models.map((model) => model.id));
  if (current && !knownIds.has(current)) {
    const currentOption = document.createElement("option");
    currentOption.value = current;
    currentOption.textContent = `${current} — configuração atual`;
    select.appendChild(currentOption);
  }
  let vendor = "";
  let group = null;
  for (const model of models) {
    if (model.vendor !== vendor) {
      vendor = model.vendor;
      group = document.createElement("optgroup");
      group.label = vendor;
      select.appendChild(group);
    }
    const option = document.createElement("option");
    option.value = model.id;
    option.textContent = `${model.id} — ${model.price_line}`;
    group.appendChild(option);
  }
  if (current) select.value = current;
}

function configureModelPicker(vendorSelect, modelSelect, models, current) {
  const currentVendor = current && current.includes("/") ? current.split("/", 1)[0] : "";
  const vendors = [...new Set([
    ...models.map((model) => model.vendor),
    ...(currentVendor ? [currentVendor] : []),
  ])].sort();
  vendorSelect.replaceChildren();
  for (const vendor of vendors) {
    const option = document.createElement("option");
    option.value = vendor;
    option.textContent = vendor;
    vendorSelect.appendChild(option);
  }
  vendorSelect.value = currentVendor || vendors[0] || "";

  const renderModels = (selectedModel = "") => {
    const matches = models.filter((model) => model.vendor === vendorSelect.value);
    fillModelSelect(modelSelect, matches, selectedModel);
  };
  vendorSelect.onchange = () => renderModels();
  renderModels(current);
}

function addPresenterRow(speaker = "", voice = "Kore", style = "") {
  const voices = modelsCatalog ? Object.entries(modelsCatalog.gemini_voices) : [];
  const row = document.createElement("div");
  row.className = "presenter-row";
  const speakerInput = makeElement("input", "pf-speaker");
  speakerInput.type = "text";
  speakerInput.placeholder = "nome";
  speakerInput.value = speaker;
  const voiceSelect = makeElement("select", "pf-voice");
  if (voice && !voices.some(([name]) => name === voice)) {
    const option = document.createElement("option");
    option.value = voice;
    option.textContent = `${voice} (configuração atual)`;
    voiceSelect.appendChild(option);
  }
  for (const [name, tone] of voices) {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = `${name} (${tone})`;
    voiceSelect.appendChild(option);
  }
  voiceSelect.value = voice;
  const styleInput = makeElement("input", "pf-style");
  styleInput.type = "text";
  styleInput.placeholder = "tom (opcional)";
  styleInput.value = style;
  row.append(speakerInput, voiceSelect, styleInput);
  const remove = document.createElement("button");
  remove.type = "button";
  remove.textContent = "✕";
  remove.className = "ghost";
  remove.setAttribute("aria-label", `Remover apresentador ${speaker || "sem nome"}`);
  remove.onclick = () => row.remove();
  row.appendChild(remove);
  $("pf-presenters").appendChild(row);
}

function presentersFromSpec(spec) {
  return spec.split(",").map((chunk) => {
    const [speaker = "", voice = "Kore", style = ""] = chunk.trim().split(":");
    return { speaker: speaker.trim(), voice: voice.trim(), style: style.trim() };
  }).filter((presenter) => presenter.speaker && presenter.voice);
}

async function openProfileForm(profile = null) {
  $("pf-error").textContent = "";
  $("profile-form").classList.remove("hidden");
  $("btn-profile-new").disabled = true;
  $("profile-form-title").textContent = profile ? `Editar perfil: ${profile.name}` : "Novo perfil";
  $("pf-name").value = profile ? profile.name : "";
  $("pf-name").readOnly = Boolean(profile);
  $("pf-description").value = profile ? profile.description : "";

  const providerSelect = $("pf-provider");
  providerSelect.replaceChildren();
  const openrouter = document.createElement("option");
  openrouter.value = "openrouter";
  openrouter.textContent = "OpenRouter (API, custo por token)";
  providerSelect.appendChild(openrouter);
  for (const cli of settingsInfo ? settingsInfo.subscription_clis : []) {
    const option = document.createElement("option");
    option.value = cli.key;
    option.textContent = `${cli.name} — custo US$ 0` +
      (cli.available ? "" : " (não instalada)");
    option.disabled = !cli.available;
    providerSelect.appendChild(option);
  }
  providerSelect.onchange = () =>
    $("pf-api-models").classList.toggle("hidden", providerSelect.value !== "openrouter");

  if (!modelsCatalog) {
    $("pf-error").textContent = "carregando catálogo de modelos…";
    const result = await bridge(["models-list"]);
    if (!result.ok) {
      $("pf-error").textContent = `✖ catálogo indisponível: ${result.error}`;
      return;
    }
    modelsCatalog = result;
    $("pf-error").textContent = result.catalog_error
      ? `⚠ Catálogo remoto indisponível; mantendo os modelos atuais: ${result.catalog_error}`
      : "";
  }
  const base = profile || settingsInfo || {};
  providerSelect.value = base.text_provider || "openrouter";
  $("pf-api-models").classList.toggle("hidden", providerSelect.value !== "openrouter");
  configureModelPicker($("pf-text-vendor"), $("pf-text-model"),
    modelsCatalog.text_models, base.text_model);
  configureModelPicker($("pf-audit-vendor"), $("pf-audit-model"),
    modelsCatalog.text_models, base.audit_model);
  configureModelPicker($("pf-tts-vendor"), $("pf-tts-model"),
    modelsCatalog.tts_models, base.tts_model);

  $("pf-presenters").replaceChildren();
  const presenters = profile
    ? presentersFromSpec(profile.presenters_spec)
    : settingsInfo && settingsInfo.presenters.length
      ? settingsInfo.presenters
      : [{ speaker: "apresentador_a", voice: "Kore", style: "curioso" }];
  for (const presenter of presenters) {
    addPresenterRow(presenter.speaker, presenter.voice, presenter.style);
  }
}

function closeProfileForm() {
  $("profile-form").classList.add("hidden");
  $("btn-profile-new").disabled = false;
  $("pf-name").readOnly = false;
}

$("btn-profile-new").onclick = () => openProfileForm();
$("pf-cancel").onclick = closeProfileForm;
$("pf-add-presenter").onclick = () => addPresenterRow();

$("profile-form").onsubmit = async (event) => {
  event.preventDefault();
  const rows = [...document.querySelectorAll(".presenter-row")];
  const spec = rows.map((row) => {
    const speaker = row.querySelector(".pf-speaker").value.trim();
    const voice = row.querySelector(".pf-voice").value;
    const style = row.querySelector(".pf-style").value.trim();
    return style ? `${speaker}:${voice}:${style}` : `${speaker}:${voice}`;
  }).filter((chunk) => !chunk.startsWith(":")).join(", ");
  const provider = $("pf-provider").value;
  const payload = {
    name: $("pf-name").value.trim(),
    description: $("pf-description").value.trim(),
    text_provider: provider,
    text_model: provider === "openrouter" ? $("pf-text-model").value : "(assinatura)",
    audit_model: provider === "openrouter" ? $("pf-audit-model").value : "(assinatura)",
    tts_model: $("pf-tts-model").value,
    presenters_spec: spec,
    activate: true,
  };
  if (!payload.name || !spec) {
    $("pf-error").textContent = "✖ preencha o nome e pelo menos um apresentador";
    return;
  }
  if (!payload.tts_model || (provider === "openrouter" &&
      (!payload.text_model || !payload.audit_model))) {
    $("pf-error").textContent = "✖ selecione os modelos obrigatórios";
    return;
  }
  const submit = $("profile-form").querySelector("button[type='submit']");
  submit.disabled = true;
  const result = await bridge(["profiles-save"], JSON.stringify(payload));
  submit.disabled = false;
  if (result.ok) {
    closeProfileForm();
    loadSettings();
  } else {
    $("pf-error").textContent = `✖ ${result.error}`;
  }
};

// ── Boot ──────────────────────────────────────────────────────────────────

$("add-content").classList.toggle("hidden", currentSource !== "custom");
loadSources().then(loadItems);
loadChatHistory();
refreshStatus();
loadActiveConfig();
