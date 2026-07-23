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

function chunkSeverityLabel(chunk) {
  if (chunk.severity === "critical") return "silêncio crítico";
  if (chunk.severity === "warning") return "revisar pausa";
  if (chunk.severity === "ok") return "auditado";
  return "sem auditoria";
}

async function openChunkReview(itemId, title, language) {
  const args = ["audio-chunks", itemId];
  if (language) args.push(`--language=${language}`);
  const result = await bridge(args);
  if (!result.ok) {
    alert(result.error);
    return;
  }
  const dialog = $("chunk-modal");
  $("chunk-modal-title").textContent = `Revisão dos chunks · ${title}`;
  $("chunk-now-playing").textContent = "Escolha um chunk para ouvir.";
  const summary = result.audit;
  $("chunk-audit-summary").textContent = summary
    ? `${summary.segments} chunks · ${summary.critical} crítico(s) · ` +
      `${summary.warnings} aviso(s)`
    : "Ainda não há auditoria automática para este episódio.";
  $("chunk-audit-criteria").textContent =
    "Critérios: ok (< 2,5 s) · aviso (\u2265 2,5 s) · " +
    "cr\u00edtico (\u2265 5 s ou \u2265 35% do chunk em sil\u00eancio)";
  const list = $("chunk-list");
  list.replaceChildren();
  for (const [index, chunk] of result.chunks.entries()) {
    const row = document.createElement("li");
    row.className = `chunk-row severity-${chunk.severity}`;
    const detail = makeElement("div", "row-main");
    const chunkIndex = chunk.chunk_index || index + 1;
    const chunkTotal = chunk.chunk_total || result.chunks.length;
    const voice = chunk.speaker ? ` · voz ${chunk.speaker}` : "";
    detail.appendChild(makeElement(
      "span", "row-title", `Chunk ${chunkIndex} de ${chunkTotal}${voice}`
    ));
    const duration = Number.isFinite(chunk.duration_seconds)
      ? `${chunk.duration_seconds.toFixed(1)}s` : "duração desconhecida";
    const silence = Number.isFinite(chunk.longest_silence_seconds)
      ? ` · maior silêncio ${chunk.longest_silence_seconds.toFixed(1)}s` : "";
    detail.appendChild(makeElement(
      "span", "muted small", `${chunk.file} · ${duration} · ` +
        `${chunkSeverityLabel(chunk)}${silence}`
    ));
    row.appendChild(detail);
    const play = makeElement("button", "ghost", "▶️ ouvir");
    play.onclick = () => {
      const player = $("chunk-player");
      player.src = projectPathToFileUrl(chunk.path);
      player.load();
      $("chunk-now-playing").textContent =
        `Tocando chunk ${chunkIndex} de ${chunkTotal} · ${chunk.file}`;
      player.play().catch(() => player.focus());
    };
    row.appendChild(play);
    list.appendChild(row);
  }
  dialog.showModal();
}

function closeChunkReview() {
  const player = $("chunk-player");
  player.pause();
  player.removeAttribute("src");
  player.load();
  $("chunk-modal").close();
}

let currentSource = "custom";
let selectedItem = null;
let pollTimer = null;
let sourcesByKey = new Map();
let generationRequestPending = false;
let generationLogRequest = 0;
let backgroundMusicPath = null;
let backgroundMusicName = null;
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

const _ACTION_LABELS = {
  adicionar_texto: "Adicionar conteúdo",
  adicionar_url: "Adicionar URL",
  buscar: "Buscar conteúdo",
  gerar: "Gerar episódio",
  exportar_notebooklm: "Exportar NotebookLM",
};

function addChatMessage(role, text, actions = []) {
  const box = $("chat-messages");
  // Não cria balão vazio — acontece quando a LLM retorna só ações sem texto.
  if (text) {
    const message = document.createElement("div");
    message.className = `msg ${role}`;
    message.textContent = text;
    box.appendChild(message);
  }
  const pending = [];
  for (const action of actions) {
    const button = document.createElement("button");
    button.className = "action-chip";
    const label = action.descricao || _ACTION_LABELS[action.tipo] || action.tipo;
    button.textContent = `⚡ ${label}`;
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

// ── Modos do chat ────────────────────────────────────────────────────────
let chatMode = "";
const _MODE_PREFIXES = {
  pesquisa:
    "[MODO PESQUISA] Pesquise o tema abaixo na web, escreva um texto completo e " +
    "substancial com suas palavras e adicione-o aos conteúdos via ação " +
    "adicionar_texto. Não pergunte nada, entregue direto.\n\n",
  podcast:
    "[MODO PODCAST] Pesquise o tema abaixo, escreva um texto completo e adicione " +
    "via adicionar_texto. Depois, gere o episódio em modo adaptation via ação " +
    "gerar. Não peça confirmação, execute tudo.\n\n",
  narracao:
    "[MODO NARRAÇÃO] Pesquise o tema abaixo, escreva um texto completo e adicione " +
    "via adicionar_texto. Depois, gere o episódio em modo verbatim via ação " +
    "gerar. Não peça confirmação, execute tudo.\n\n",
  reflexiva:
    "[MODO LEITURA REFLEXIVA] Pesquise o tema abaixo, escreva um texto completo e adicione " +
    "via adicionar_texto. Depois, gere o episódio em modo reflexive via ação " +
    "gerar. Não peça confirmação, execute tudo.\n\n",
  url:
    "[MODO URL] O texto abaixo contém uma ou mais URLs. Adicione cada uma como " +
    "conteúdo via ação adicionar_url. Não pergunte nada.\n\n",
};
const _MODE_PLACEHOLDERS = {
  "": "Ex.: pesquise bons artigos sobre computação quântica para virar episódio…",
  pesquisa: "Digite o tema para pesquisar e adicionar como conteúdo…",
  podcast: "Digite o tema — será pesquisado e gerado como podcast adaptado…",
  narracao: "Digite o tema — será pesquisado e gerado como leitura fiel…",
  reflexiva: "Digite o tema — será pesquisado e gerado como leitura reflexiva com comentários…",
  url: "Cole a URL para adicionar como conteúdo…",
};

for (const btn of document.querySelectorAll(".chat-mode")) {
  btn.onclick = () => {
    document.querySelector(".chat-mode.active")?.classList.remove("active");
    btn.classList.add("active");
    chatMode = btn.dataset.mode;
    $("chat-text").placeholder = _MODE_PLACEHOLDERS[chatMode] || _MODE_PLACEHOLDERS[""];
    $("chat-text").focus();
  };
}

async function sendChat() {
  const text = $("chat-text").value.trim();
  if (!text) return;
  $("chat-text").value = "";
  addChatMessage("user", text);
  const prefix = _MODE_PREFIXES[chatMode] || "";
  const fullMessage = prefix + text;
  const thinking = document.createElement("div");
  thinking.className = "msg assistant muted";
  thinking.textContent = "… pesquisando";
  $("chat-messages").appendChild(thinking);
  $("chat-send").disabled = true;
  const result = await bridge(["chat", "principal"], fullMessage);
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
    option.textContent = source.name;
    option.title = source.description;
    select.appendChild(option);
  }
  select.value = currentSource;
  renderSourceStatus();
}

function renderSourceStatus(message = "") {
  const source = sourcesByKey.get(currentSource);
  const status = $("source-status");
  const badge = $("source-status-badge");
  if (source) {
    badge.textContent = source.ready ? "✓ pronta" : "⚠ requer sync";
    badge.className = `badge ${source.ready ? "ok" : "warn"}`;
  } else {
    badge.textContent = "";
    badge.className = "badge hidden";
  }
  status.textContent = message || source?.description || "";
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
  const list = $("items");
  const count = $("items-count");
  list.replaceChildren();
  count.textContent = "";
  const result = await bridge(command);
  if (!result.ok) {
    list.appendChild(makeElement("li", "muted empty-state", `✖ Erro: ${result.error}`));
    return;
  }
  if (!result.items.length) {
    list.appendChild(makeElement("li", "muted empty-state",
      query
        ? "Nenhum resultado para essa busca."
        : "Nenhum item — adicione conteúdo acima ou peça sugestões no Chat."));
    return;
  }
  count.textContent = `${result.items.length} item${result.items.length === 1 ? "" : "ns"}`;
  for (const item of result.items) {
    const row = document.createElement("li");
    row.className = "item-row";
    const main = makeElement("div", "item-main");
    main.appendChild(makeElement("span", "item-title", item.title));
    main.appendChild(makeElement("span", "date", item.published_at));
    row.appendChild(main);
    row.onclick = () => selectItem(item, row);
    list.appendChild(row);
  }
}

async function selectItem(item, row) {
  document.querySelectorAll("#items li").forEach((li) => li.classList.remove("selected"));
  row.classList.add("selected");
  const detail = await bridge(["item", currentSource, item.item_id]);
  if (!detail.ok) return;
  clearBackgroundMusic();
  selectedItem = { ...detail, source: currentSource };
  $("detail-empty").classList.add("hidden");
  $("detail").classList.remove("hidden");
  $("detail-title").textContent = detail.title;
  $("detail-meta").textContent =
    `${detail.published_at} · ~${detail.words} palavras · ${detail.url || "texto local"}`;
  renderItemEstimate();
  refreshStatus();
}

function selectedEstimate() {
  if (!selectedItem) return null;
  const mode = $("generation-mode").value;
  return (selectedItem.estimates && selectedItem.estimates[mode]) || selectedItem.estimate;
}

function renderItemEstimate() {
  if (!selectedItem) return;
  const estimate = selectedEstimate();
  const mode = $("generation-mode").value;
  const actual = selectedItem.actual;
  if (actual && (actual.generation_mode || "adaptation") === mode) {
    const accuracy = actual.cost_exact ? "confirmado pelo provedor" : "aproximado";
    $("detail-estimate").textContent =
      `Realizado: US$ ${actual.cost_usd.toFixed(4)} (${accuracy}) · ` +
      `${(actual.duration_seconds / 60).toFixed(1)} min`;
  } else {
    const count = estimate.sample_count;
    const basis = count
      ? `${count} episódio(s) de ${generationModeLabel(mode)}` +
        (count < 2 ? " · faixa pela variância do histórico do TTS" : "")
      : "piloto medido";
    $("detail-estimate").textContent =
      `Estimativa: ~US$ ${estimate.cost_usd.toFixed(2)} ` +
      `(faixa US$ ${estimate.cost_min_usd.toFixed(2)}–${estimate.cost_max_usd.toFixed(2)}) · ` +
      `~${estimate.duration_minutes.toFixed(1)} min · ${basis}`;
  }
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

// ── Envio de arquivos ─────────────────────────────────────────────────────
// A extração roda por bibliotecas locais (pypdf/python-docx/ebooklib/OCR).
// A IA só é sugerida quando nada local funcionou, porque um livro ou dezenas
// de páginas escaneadas custariam caro e demorariam muito para transcrever.

function fileBaseName(filePath) {
  return String(filePath).split(/[\\/]/).pop() || filePath;
}

function describeExtraction(result) {
  const methodLabels = {
    "pypdf": "PDF lido localmente",
    "python-docx": "DOCX lido localmente",
    "ebooklib": "EPUB lido localmente",
    "plain-text": "texto lido diretamente",
    "tesseract-ocr": "OCR local (Tesseract)",
  };
  const method = methodLabels[result.method] || result.method;
  return `${result.title} — ${result.words} palavras · ${method}`;
}

async function askAgentToExtract(filePath, reason) {
  const name = fileBaseName(filePath);
  const confirmed = confirm(
    `Não consegui extrair o texto de "${name}" localmente.\n\n${reason}\n\n` +
    "Quer que o agente de IA leia e transcreva o arquivo?\n\n" +
    "⚠️ Isso consome créditos e pode ficar lento/caro em arquivos grandes " +
    "(livros, dezenas de páginas ou muitas imagens). " +
    "Alternativa sem custo: instalar o OCR local em Configurações → Diagnóstico, " +
    "ou colar o texto manualmente."
  );
  if (!confirmed) return { skipped: true };
  const instruction =
    `[EXTRAÇÃO DE ARQUIVO] Leia o arquivo em "${filePath}" e transcreva o texto ` +
    "integralmente, sem resumir nem reescrever. Depois adicione o resultado como " +
    "conteúdo via ação adicionar_texto, usando o título do próprio documento. " +
    "Não peça confirmação.";
  activateTab($("tab-button-chat"));
  $("chat-text").value = instruction;
  $("chat-text").focus();
  addChatMessage("system",
    `Transcrição de "${name}" preparada no chat — revise e envie para o agente executar.`);
  return { delegated: true };
}

$("btn-add-files").onclick = async () => {
  const paths = await window.audiofy.chooseContentFiles();
  if (!paths.length) return;
  const button = $("btn-add-files");
  const status = $("add-files-status");
  button.disabled = true;
  const added = [];
  const failed = [];
  const pending = [];
  for (const [index, filePath] of paths.entries()) {
    status.textContent =
      `Extraindo ${index + 1}/${paths.length}: ${fileBaseName(filePath)}…`;
    const result = await bridge(["add-file", filePath]);
    if (!result.ok) {
      failed.push(`${fileBaseName(filePath)}: ${result.error}`);
    } else if (result.added) {
      added.push(describeExtraction(result));
    } else {
      pending.push({ filePath, reason: result.reason });
    }
  }
  button.disabled = false;
  const lines = [];
  if (added.length) lines.push(`✓ ${added.length} adicionado(s): ${added.join(" · ")}`);
  if (failed.length) lines.push(`✖ ${failed.length} com erro: ${failed.join(" · ")}`);
  status.textContent = lines.join("  |  ") || "Nenhum arquivo processado.";
  if (added.length) loadItems();
  for (const { filePath, reason } of pending) {
    await askAgentToExtract(filePath, reason);
  }
};

// ── Geração, episódios e status ───────────────────────────────────────────

function updateGenerateButton() {
  const button = $("btn-generate");
  const running = button.dataset.running === "true";
  const done = button.dataset.done === "true";
  button.disabled = generationRequestPending || running;
  const mode = $("generation-mode").value;
  if (generationRequestPending) {
    button.textContent = "⏳ Iniciando…";
  } else if (done) {
    button.textContent = mode === "verbatim" ? "📖 Re-gerar leitura fiel"
      : mode === "reflexive" ? "📖 Re-gerar leitura reflexiva"
      : "🔄 Re-gerar episódio";
  } else {
    button.textContent = mode === "verbatim" ? "📖 Gerar leitura fiel"
      : mode === "reflexive" ? "📖 Gerar leitura reflexiva"
      : "🎙️ Gerar episódio";
  }
}

function updateGenerationMode() {
  const mode = $("generation-mode").value;
  const needsNarrator = mode === "verbatim" || mode === "reflexive";
  $("narration-voice-label").classList.toggle("hidden", !needsNarrator);
  $("generation-mode-note").textContent = mode === "verbatim"
    ? "O texto falado é preservado integralmente. A IA planeja apenas ritmo, pausas, " +
      "emoção e tensão em lotes retomáveis."
    : mode === "reflexive"
    ? "O texto é lido integralmente, parágrafo a parágrafo. Após cada parágrafo, " +
      "o narrador acrescenta um breve comentário reflexivo, explicativo ou contextual."
    : "Cria matriz de cobertura, adapta o texto como roteiro e audita o resultado.";
  $("force-label").textContent = mode === "verbatim"
    ? "Replanejar interpretação e regenerar áudios"
    : mode === "reflexive"
    ? "Replanejar leitura reflexiva e regenerar áudios"
    : "Regenerar cobertura, roteiro e auditoria";
  renderItemEstimate();
  updateGenerateButton();
}

function generationArgs(
  source,
  itemId,
  { force = false, mode = null, voice = null, backgroundMusic = null, volume = null,
    language = null } = {}
) {
  const selectedMode = mode || $("generation-mode").value;
  const selectedVoice = voice || $("narration-voice").value;
  const selectedLang = language || $("generation-language").value;
  const args = ["generate", source, itemId, `--mode=${selectedMode}`];
  if (selectedMode === "verbatim" || selectedMode === "reflexive") args.push(`--voice=${selectedVoice}`);
  if (force) args.push("--force");
  if (backgroundMusic) {
    args.push(`--background-music=${backgroundMusic}`);
    args.push(`--background-volume=${volume || 0.08}`);
  }
  if (selectedLang !== "pt-BR") args.push(`--language=${selectedLang}`);
  return args;
}

$("generation-mode").onchange = updateGenerationMode;
$("generation-language").onchange = () => refreshStatus();

function clearBackgroundMusic() {
  backgroundMusicPath = null;
  backgroundMusicName = null;
  $("background-music-name").textContent = "Sem música de fundo";
  $("btn-clear-background-music").classList.add("hidden");
}

$("btn-background-music").onclick = async () => {
  const selected = await window.audiofy.chooseBackgroundMusic();
  if (!selected) return;
  backgroundMusicPath = selected;
  backgroundMusicName = String(selected).split(/[\\/]/).pop();
  $("background-music-name").textContent = backgroundMusicName;
  $("btn-clear-background-music").classList.remove("hidden");
};

$("btn-clear-background-music").onclick = clearBackgroundMusic;
$("background-volume").oninput = () => {
  $("background-volume-value").textContent = `${$("background-volume").value}%`;
};

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
    const result = await bridge(generationArgs(item.source, item.itemId, {
      mode: status.generation_mode || "adaptation",
      voice: status.narration_voice,
      backgroundMusic: status.background_music_cache,
      volume: status.background_volume,
    }));
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
  const mode = $("generation-mode").value;
  const needsNarrator = mode === "verbatim" || mode === "reflexive";
  const voice = $("narration-voice").value;
  const backgroundVolume = Number($("background-volume").value) / 100;
  const estimate = selectedEstimate();
  if (needsNarrator && !voice) {
    alert("Escolha a voz do narrador.");
    return;
  }
  const modeLabel = mode === "verbatim" ? "Gerar leitura fiel"
    : mode === "reflexive" ? "Gerar leitura reflexiva"
    : "Gerar episódio";
  const narratorNote = mode === "verbatim"
    ? `\n\nNarrador: ${voice}. O texto não será reescrito; somente a interpretação será planejada.`
    : mode === "reflexive"
    ? `\n\nNarrador: ${voice}. O texto será lido integralmente, com comentários reflexivos intercalados.`
    : "";
  const forceNote = force
    ? mode === "verbatim"
      ? "\n\nO plano de interpretação e os áudios serão regenerados."
      : mode === "reflexive"
      ? "\n\nO plano reflexivo e os áudios serão regenerados."
      : "\n\nA cobertura, o roteiro e a auditoria serão regenerados."
    : "";
  const confirmed = confirm(
    `${modeLabel} de "${selectedItem.title}"?\n\n` +
    `Custo estimado: ~US$ ${estimate.cost_usd.toFixed(2)} ` +
    `(faixa US$ ${estimate.cost_min_usd.toFixed(2)}–` +
    `${estimate.cost_max_usd.toFixed(2)}) ` +
    `(consome créditos do OpenRouter).` +
    narratorNote +
    (backgroundMusicName
      ? `\n\nMúsica de fundo: ${backgroundMusicName} a ${Math.round(backgroundVolume * 100)}%. ` +
        "Os chunks de voz serão reaproveitados quando compatíveis."
      : "") +
    forceNote
  );
  if (!confirmed) return;
  const args = generationArgs(selectedItem.source, selectedItem.item_id, {
    force,
    mode,
    voice,
    backgroundMusic: backgroundMusicPath,
    volume: backgroundVolume,
  });
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
  const abortLang = $("generation-language").value;
  const abortArgs = ["abort", selectedItem.item_id];
  if (abortLang) abortArgs.push(`--language=${abortLang}`);
  const result = await bridge(abortArgs);
  if (result.ok && result.aborted) {
    alert(result.stopped
      ? "Geração abortada agora. O checkpoint foi preservado."
      : "Abort registrado; aguardando o primeiro checkpoint disponível.");
  }
  refreshStatus();
};

$("btn-repair").onclick = async () => {
  if (!selectedItem) return;
  if (!confirm(
    "Reparar epis\u00f3dio? Apenas os segmentos com sil\u00eancio problem\u00e1tico " +
    "ser\u00e3o regenerados.\n\nIsso consome cr\u00e9ditos da API."
  )) return;
  showGenerationRequest("Solicitando reparo\u2026", "active");
  const lang = $("generation-language").value;
  const repairArgs = ["repair", selectedItem.source, selectedItem.item_id];
  if (lang) repairArgs.push(`--language=${lang}`);
  const result = await bridge(repairArgs);
  if (!result.ok || !result.started) {
    showGenerationRequest(result.reason || "Erro ao iniciar reparo", "error");
    return;
  }
  showGenerationRequest(
    `Reparando ${result.segments_to_repair} segmento(s) com problema\u2026`, "active"
  );
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
        const key = e.key_source ? ` · chave ${e.key_source}` : "";
        return `${e.episode_id} (US$ ${e.cost_usd.toFixed(3)}${accuracy}${key}${retry})`;
      }).join(", ");
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }

  renderEpisodes(overview.episodes);
  if (selectedItem) {
    renderSelectedStatus(overview.episodes);
  } else {
    // Sem item selecionado não há geração para proteger; deixar travado prenderia
    // os campos até o próximo clique em um item.
    lockGenerationOptions(false);
  }

  clearTimeout(pollTimer);
  if (overview.anything_running) pollTimer = setTimeout(refreshStatus, 2000);
}

function renderSelectedStatus(episodes) {
  const lang = $("generation-language").value;
  const status = episodes.find(
    (e) => e.episode_id === selectedItem.item_id && (e.language || "pt-BR") === lang
  );
  const running = status && status.state === "rodando";
  const done = status && status.mp3;
  const feedback = generationFeedback(status);

  $("btn-abort").classList.toggle(
    "hidden", !running || Boolean(status && status.abort_requested_at)
  );
  $("btn-generate").dataset.running = String(Boolean(running));
  $("btn-generate").dataset.done = String(Boolean(done));
  updateGenerateButton();
  lockGenerationOptions(Boolean(running));
  $("btn-play").classList.toggle("hidden", !done);
  $("btn-chunks").classList.toggle("hidden", !status);
  $("btn-folder").classList.toggle("hidden", !status);

  // Botão Reparar: visível quando concluído com problemas de auditoria e não rodando.
  const auditProblems = status && status.audio_audit &&
    (status.audio_audit.critical > 0 || status.audio_audit.warnings > 0);
  $("btn-repair").classList.toggle("hidden", !auditProblems || running);

  const box = $("progress-box");
  // Mostra warning pós-geração quando há problemas de auditoria.
  const showAuditWarning = !running && auditProblems && status.state === "concluido";
  const showBox = feedback.visible || showAuditWarning;
  box.classList.toggle("hidden", !showBox);
  box.classList.remove("active", "error", "warning");
  if (showAuditWarning && !feedback.visible) {
    box.classList.add("warning");
    const total = status.audio_audit.critical + status.audio_audit.warnings;
    $("progress-fill").style.width = "100%";
    $("progress-track").setAttribute("aria-valuenow", "100");
    $("progress-label").textContent = "";
    $("progress-label").appendChild(makeElement("span", "spinner"));
    $("progress-label").appendChild(document.createTextNode(
      ` Auditoria detectou ${total} segmento(s) com ` +
      `sil\u00eancio problem\u00e1tico \u2014 use \ud83d\udd27 Reparar`
    ));
    $("cost-label").textContent = "";
  } else if (feedback.visible) {
    if (feedback.tone) box.classList.add(feedback.tone);
    $("progress-fill").style.width = `${feedback.percent}%`;
    $("progress-track").setAttribute("aria-valuenow", String(feedback.percent));
    $("progress-label").textContent = "";
    if (running) $("progress-label").appendChild(makeElement("span", "spinner"));
    $("progress-label").appendChild(document.createTextNode(feedback.label));
    $("cost-label").textContent = feedback.cost;
  }
  $("btn-play").onclick = () => status && status.mp3
    && playInApp(status.mp3, selectedItem.title);
  $("btn-chunks").onclick = () => status
    && openChunkReview(selectedItem.item_id, selectedItem.title, lang);
  $("btn-folder").onclick = () => status && openProjectPath(status.dir);
  void refreshGenerationLog(status);
  void maybeAutoResume(status);
}

function elapsedLabel(timestamp) {
  if (!timestamp) return "sem saída ainda";
  const seconds = Math.max(0, Math.round(Date.now() / 1000 - Number(timestamp)));
  if (seconds < 5) return "agora";
  if (seconds < 60) return `há ${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `há ${minutes}min`;
  return `há ${Math.floor(minutes / 60)}h`;
}

async function refreshGenerationLog(status) {
  const panel = $("generation-log-panel");
  if (!selectedItem || !status) {
    generationLogRequest += 1;
    panel.classList.add("hidden");
    $("generation-log").textContent = "";
    return;
  }
  const itemId = selectedItem.item_id;
  const lang = $("generation-language").value;
  const request = ++generationLogRequest;
  const logArgs = ["generation-log", itemId];
  if (lang) logArgs.push(`--language=${lang}`);
  const result = await bridge(logArgs);
  if (request !== generationLogRequest || !selectedItem || selectedItem.item_id !== itemId) return;

  panel.classList.remove("hidden");
  const health = $("generation-log-health");
  health.className = result.worker_alive ? "small state-rodando" : "small muted";
  health.textContent = result.worker_alive ? "● worker ativo" : `● ${status.state}`;
  const suffix = result.truncated ? " · exibindo somente as últimas linhas" : "";
  const key = status.key_source ? ` · chave efetiva: ${status.key_source}` : "";
  $("generation-log-meta").textContent = result.ok
    ? `Última saída ${elapsedLabel(result.updated_at)}${key}${suffix}`
    : "Não foi possível consultar o log.";

  const output = $("generation-log");
  const nearBottom = output.scrollHeight - output.scrollTop - output.clientHeight < 48;
  output.textContent = result.ok && result.exists
    ? (result.text || "Aguardando a primeira mensagem do worker…")
    : (result.error || "O worker ainda não criou o arquivo de log.");
  if (panel.open && nearBottom) output.scrollTop = output.scrollHeight;
}

function formatEpisodeDate(value, includeTime = false) {
  if (!value) return "não registrada";
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (dateOnly) return `${dateOnly[3]}/${dateOnly[2]}/${dateOnly[1]}`;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("pt-BR", includeTime
    ? { dateStyle: "short", timeStyle: "short" }
    : { dateStyle: "short" }).format(date);
}

function formatEpisodeDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "não medida";
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainder = total % 60;
  return hours ? `${hours}h ${minutes}min ${remainder}s` : `${minutes}min ${remainder}s`;
}

function formatFileSize(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return "não medido";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KiB", "MiB", "GiB"];
  let value = bytes / 1024;
  let unit = units[0];
  for (let index = 1; value >= 1024 && index < units.length; index += 1) {
    value /= 1024;
    unit = units[index];
  }
  return `${value.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} ${unit}`;
}

function episodeFact(label, value) {
  const fact = makeElement("div", "episode-fact");
  fact.appendChild(makeElement("dt", "", label));
  fact.appendChild(makeElement("dd", "", value));
  return fact;
}

function generationModeLabel(mode) {
  return mode === "verbatim" ? "leitura fiel"
    : mode === "reflexive" ? "leitura reflexiva"
    : "podcast adaptado";
}

function renderEpisodes(episodes) {
  const list = $("episodes");
  list.replaceChildren();
  const completed = episodes.filter((episode) => episode.mp3).length;
  $("episodes-summary").textContent = episodes.length
    ? `${completed} áudio(s) pronto(s) em ${episodes.length} registro(s), do mais recente ao mais antigo.`
    : "Nenhum episódio gerado ainda.";
  if (!episodes.length) list.appendChild(makeElement("li", "muted", "Nenhum episódio ainda."));
  for (const episode of episodes) {
    const row = document.createElement("li");
    row.className = "episode-card";
    const accuracy = episode.cost_exact ? "" : " aprox.";
    const cost = episode.cost_usd
      ? `US$ ${episode.cost_usd.toFixed(4)}${accuracy}` : "custo não registrado";
    const progress = episode.state === "rodando" && episode.progress.total
      ? ` · ${episode.progress.current}/${episode.progress.total}` : "";
    const retry = episode.retry
      ? ` · retry ${episode.retry.attempt}/${episode.retry.max_attempts}` : "";
    row.appendChild(makeElement("span", `episode-state-dot state-${episode.state}`, "●"));

    const body = makeElement("div", "episode-card-body");
    const heading = makeElement("div", "episode-heading");
    const identity = makeElement("div", "episode-identity");
    identity.appendChild(makeElement("h3", "episode-title", episode.title || episode.episode_id));
    identity.appendChild(makeElement("code", "episode-id", episode.episode_id));
    heading.appendChild(identity);
    heading.appendChild(makeElement(
      "span", `badge episode-state state-${episode.state}`, `${episode.state}${progress}${retry}`
    ));
    body.appendChild(heading);

    const facts = makeElement("dl", "episode-facts");
    facts.appendChild(episodeFact(
      "Criação do conteúdo", formatEpisodeDate(episode.source_created_at)
    ));
    facts.appendChild(episodeFact(
      "Geração do áudio", formatEpisodeDate(episode.generated_at, true)
    ));
    facts.appendChild(episodeFact("Duração", formatEpisodeDuration(episode.duration_seconds)));
    facts.appendChild(episodeFact(
      "Arquivo", episode.file_name
        ? `${episode.file_name} · ${formatFileSize(episode.file_size_bytes)}`
        : "ainda não gerado"
    ));
    body.appendChild(facts);

    const production = makeElement("p", "episode-production muted small");
    const words = Number.isFinite(episode.source_words)
      ? ` · ${episode.source_words.toLocaleString("pt-BR")} palavras de origem` : "";
    const audit = episode.audio_audit
      ? ` · auditoria: ${episode.audio_audit.critical} crítico(s), ` +
        `${episode.audio_audit.warnings} aviso(s)`
      : " · sem auditoria";
    const profile = episode.profile_name ? ` · perfil ${episode.profile_name}` : "";
    const music = episode.background_music ? ` · música ${episode.background_music}` : "";
    const source = episode.source_key ? `fonte ${episode.source_key} · ` : "";
    production.textContent =
      `${source}${generationModeLabel(episode.generation_mode)} · ` +
      `${cost}${profile}${words}${audit}${music}`;
    if (episode.source_file) {
      production.title = `Fonte preservada: ${episode.source_file}`;
    }
    if (episode.tts_model) {
      production.title = `${production.title ? production.title + " · " : ""}` +
        `TTS: ${episode.tts_model}`;
    }
    body.appendChild(production);
    row.appendChild(body);

    if (episode.state === "falhou" && episode.last_error) {
      row.title = friendlyGenerationError(episode.last_error, episode.key_source);
    }
    const actions = makeElement("div", "episode-actions");
    if (episode.state === "rodando" && !episode.abort_requested_at) {
      const abortButton = document.createElement("button");
      abortButton.textContent = "🛑";
      abortButton.title = "Abortar";
      abortButton.setAttribute("aria-label", `Abortar ${episode.episode_id}`);
      abortButton.onclick = () => {
        const args = ["abort", episode.episode_id];
        if (episode.language) args.push(`--language=${episode.language}`);
        bridge(args).then(refreshStatus);
      };
      actions.appendChild(abortButton);
    }
    if (episode.mp3) {
      const play = document.createElement("button");
      play.textContent = "▶️";
      play.title = "Ouvir";
      play.setAttribute("aria-label", `Ouvir ${episode.episode_id}`);
      play.onclick = () => playInApp(episode.mp3, episode.title || episode.episode_id);
      actions.appendChild(play);
    }
    const chunks = makeElement("button", "ghost", "🧪 chunks");
    chunks.onclick = () => openChunkReview(
      episode.episode_id, episode.title || episode.episode_id, episode.language
    );
    actions.appendChild(chunks);
    const folder = document.createElement("button");
    folder.textContent = "📂";
    folder.title = "Abrir pasta";
    folder.setAttribute("aria-label", `Abrir pasta de ${episode.episode_id}`);
    folder.onclick = () => openProjectPath(episode.dir);
    actions.appendChild(folder);
    row.appendChild(actions);
    list.appendChild(row);
  }
}

$("btn-close-chunks").onclick = closeChunkReview;
$("chunk-modal").addEventListener("cancel", (event) => {
  event.preventDefault();
  closeChunkReview();
});

// ── Configurações ─────────────────────────────────────────────────────────

let modelsCatalog = null; // {text_models, tts_models, gemini_voices, voice_catalogs, tts_tiers}
let settingsInfo = null;
let activeProfileCategory = null;

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
    const origin = info.profile_subscription_model ? " (perfil)" : "";
    strip.appendChild(configChip("Texto",
      `${cli ? cli.name : info.text_provider} · ${model}${origin}${availability}`,
      cli && !cli.available ? "warn" : ""));
  }

  strip.appendChild(configChip("TTS", `${info.tts_model}${info.has_key ? "" : " · sem chave"}`,
    info.has_key ? "" : "warn"));
  strip.appendChild(configChip("Chave efetiva", info.key_source || "nenhuma",
    info.has_key ? "" : "warn"));
  const langLabel = info.language === "en" ? "English" : "Português";
  strip.appendChild(configChip("Idioma", langLabel));

  // Sincroniza o seletor de idioma com o perfil ativo
  $("generation-language").value = info.language || "pt-BR";

  const voiceSelect = $("narration-voice");
  const previousVoice = voiceSelect.value;
  voiceSelect.replaceChildren();
  const activeCatalog = (info.voice_catalogs && info.voice_catalogs[info.tts_model])
    || info.gemini_voices || {};
  const catalogEntries = Object.entries(activeCatalog);
  if (catalogEntries.length) {
    for (const [voice, style] of catalogEntries) {
      const option = document.createElement("option");
      option.value = voice;
      option.textContent = `${voice} · ${style}`;
      voiceSelect.appendChild(option);
    }
  } else {
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Sem catálogo — configure pelo perfil";
    placeholder.disabled = true;
    voiceSelect.appendChild(placeholder);
  }
  const profileVoice = info.presenters.length === 1 ? info.presenters[0].voice : "";
  // Só uma escolha deliberada do usuário sobrepõe a voz do perfil. Sem isso, um
  // valor mudado sem querer (roda do mouse sobre o combo) virava o "preferido" e
  // se perpetuava a cada refresh, gerando o episódio com outra voz em silêncio.
  const preferred = (voiceTouchedByUser && previousVoice) || profileVoice || "Sulafat";
  if ([...voiceSelect.options].some((option) => option.value === preferred)) {
    voiceSelect.value = preferred;
  }
  markVoiceMatchesProfile(profileVoice);
}

// A roda do mouse sobre um <select> troca a opção no Chromium sem o usuário
// perceber; num campo que decide o custo e a voz do episódio inteiro, isso é
// mudança silenciosa demais. Só teclado e clique contam como escolha.
let voiceTouchedByUser = false;

function markVoiceMatchesProfile(profileVoice) {
  const voiceSelect = $("narration-voice");
  const hint = $("narration-voice-hint");
  if (!hint) return;
  const differs = Boolean(profileVoice) && voiceSelect.value !== profileVoice;
  hint.classList.toggle("hidden", !differs);
  if (differs) {
    hint.textContent = `⚠ Diferente do perfil (${profileVoice}). Clique para voltar.`;
    hint.onclick = () => {
      voiceSelect.value = profileVoice;
      voiceTouchedByUser = false;
      markVoiceMatchesProfile(profileVoice);
    };
  }
}

// Formato e idioma também mudam o custo e o áudio final; o mesmo cuidado vale.
const GENERATION_OPTION_IDS = ["narration-voice", "generation-mode", "generation-language"];

for (const id of GENERATION_OPTION_IDS) {
  $(id).addEventListener("wheel", (event) => event.preventDefault(), { passive: false });
}

// Trocar voz, formato ou idioma no meio da geração produziria um episódio com
// duas configurações misturadas — os segmentos já sintetizados não mudam. Quem
// quiser outra configuração precisa abortar e gerar de novo.
function lockGenerationOptions(running) {
  for (const id of [...GENERATION_OPTION_IDS, "generate-force"]) {
    $(id).disabled = running;
  }
  $("btn-background-music").disabled = running;
  $("btn-clear-background-music").disabled = running;
  $("background-volume").disabled = running;
  $("generation-options-lock").classList.toggle("hidden", !running);
}
$("narration-voice").addEventListener("change", () => {
  voiceTouchedByUser = true;
  const profileVoice = settingsInfo && settingsInfo.presenters.length === 1
    ? settingsInfo.presenters[0].voice : "";
  markVoiceMatchesProfile(profileVoice);
});

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
      `${keys.count} ${plural} · fila na ordem exibida · em uso: ` +
      `${keys.effective_source || "nenhuma"}`;

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
      row.className = "key-row";
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
      row.className = "key-row";
      const detail = makeElement("div", "row-main");
      detail.appendChild(makeElement("span", "row-title", `#${key.priority} · ${key.name}`));
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
      const up = makeElement("button", "ghost", "↑");
      up.title = `Aumentar prioridade de ${key.name}`;
      up.setAttribute("aria-label", up.title);
      up.disabled = key.priority === 1;
      up.onclick = () => bridge(["keys-move", key.name, "up"]).then(loadSettings);
      row.appendChild(up);
      const down = makeElement("button", "ghost", "↓");
      down.title = `Diminuir prioridade de ${key.name}`;
      down.setAttribute("aria-label", down.title);
      down.disabled = key.priority === keys.count;
      down.onclick = () => bridge(["keys-move", key.name, "down"]).then(loadSettings);
      row.appendChild(down);
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

    const categoryOf = (p) => {
      if (p.text_provider === "claude-code") return "Claude Code";
      if (p.text_provider === "codex") return "Codex";
      if (p.text_provider === "gemini-cli") return "Gemini CLI";
      if (p.text_model.startsWith("anthropic/")) return "Claude API";
      if (p.text_model.startsWith("openai/")) return "OpenAI API";
      return "Gemini API";
    };

    const grouped = new Map();
    for (const profile of profiles.profiles) {
      const cat = profile.custom ? "Personalizados" : categoryOf(profile);
      if (!grouped.has(cat)) grouped.set(cat, []);
      grouped.get(cat).push(profile);
    }

    const tabBar = $("profile-tabs");
    tabBar.replaceChildren();
    let firstTab = null;

    const showCategory = (category) => {
      activeProfileCategory = category;
      list.replaceChildren();
      for (const btn of tabBar.querySelectorAll("button")) {
        btn.classList.toggle("active", btn.dataset.cat === category);
      }
      const items = grouped.get(category) || [];
      for (const profile of items) {
        const row = document.createElement("li");
        const active = profile.name === profiles.active;
        const provider = profile.text_provider === "openrouter"
          ? "API"
          : `assinatura ${profile.text_provider}` +
            (profile.subscription_model ? ` (${profile.subscription_model})` : "");
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
    };

    // Aba que contém o perfil ativo aparece primeiro
    const activeCat = categoryOf(
      profiles.profiles.find((p) => p.name === profiles.active) || profiles.profiles[0]
    );

    for (const category of grouped.keys()) {
      const btn = document.createElement("button");
      btn.textContent = category;
      btn.dataset.cat = category;
      btn.setAttribute("role", "tab");
      btn.onclick = () => showCategory(category);
      tabBar.appendChild(btn);
      if (!firstTab) firstTab = category;
    }

    showCategory(activeCat || firstTab);
  }

  const info = await loadActiveConfig();
  if (info.ok) {
    const clis = info.subscription_clis
      .map((c) => `${c.key}${c.configured_model ? ` (${c.configured_model})` : ""}` +
        `${c.available ? " ✓" : " ✗"}`).join("  ");
    const textModel = info.text_provider === "openrouter"
      ? info.text_model
      : (info.subscription_model || "modelo padrão da CLI") +
        (info.profile_subscription_model ? " (escolhido no perfil)" : "");
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
  const warning = result.catalog_error ? `Aviso: ${result.catalog_error}\n\n` : "";
  let voicesText = "";
  for (const [modelId, voices] of Object.entries(result.voice_catalogs || {})) {
    const entries = Object.entries(voices);
    const tier = (result.tts_tiers && result.tts_tiers[modelId]) || {};
    const tierLabel = tier.label ? ` [${tier.label} — US$ ${tier.effective_cost_per_m_chars}/M]` : "";
    voicesText += `\n${modelId}${tierLabel}:\n`;
    if (entries.length) {
      voicesText += entries.map(([v, s]) => `  ${v} (${s})`).join("\n") + "\n";
    } else {
      voicesText += "  (voz livre — digite o nome ao configurar)\n";
    }
  }
  $("catalog-box").textContent =
    `${warning}Modelos TTS:\n${models}\n\nVozes por modelo:${voicesText}`;
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

function currentVoiceCatalog() {
  const ttsModel = $("pf-tts-model") && $("pf-tts-model").value;
  if (!ttsModel || !modelsCatalog || !modelsCatalog.voice_catalogs) return null;
  return modelsCatalog.voice_catalogs[ttsModel] || null;
}

function addPresenterRow(speaker = "", voice = "Kore", style = "") {
  const catalog = currentVoiceCatalog();
  const voices = catalog ? Object.entries(catalog) : [];
  const row = document.createElement("div");
  row.className = "presenter-row";
  const speakerInput = makeElement("input", "pf-speaker");
  speakerInput.type = "text";
  speakerInput.placeholder = "nome";
  speakerInput.value = speaker;

  let voiceElement;
  if (voices.length) {
    voiceElement = makeElement("select", "pf-voice");
    if (voice && !voices.some(([name]) => name === voice)) {
      const option = document.createElement("option");
      option.value = voice;
      option.textContent = `${voice} (configuração atual)`;
      voiceElement.appendChild(option);
    }
    for (const [name, tone] of voices) {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = `${name} (${tone})`;
      voiceElement.appendChild(option);
    }
    voiceElement.value = voice;
  } else {
    voiceElement = makeElement("input", "pf-voice");
    voiceElement.type = "text";
    voiceElement.placeholder = "nome da voz";
    voiceElement.value = voice || "";
  }

  const styleInput = makeElement("input", "pf-style");
  styleInput.type = "text";
  styleInput.placeholder = "tom (opcional)";
  styleInput.value = style;
  row.append(speakerInput, voiceElement, styleInput);
  const remove = document.createElement("button");
  remove.type = "button";
  remove.textContent = "✕";
  remove.className = "ghost";
  remove.setAttribute("aria-label", `Remover apresentador ${speaker || "sem nome"}`);
  remove.onclick = () => row.remove();
  row.appendChild(remove);
  $("pf-presenters").appendChild(row);
}

function refreshPresenterVoices() {
  const rows = [...document.querySelectorAll(".presenter-row")];
  const current = rows.map((row) => ({
    speaker: row.querySelector(".pf-speaker").value,
    voice: row.querySelector(".pf-voice").value,
    style: row.querySelector(".pf-style").value,
  }));
  $("pf-presenters").replaceChildren();
  for (const p of current) {
    addPresenterRow(p.speaker, p.voice, p.style);
  }
}

function renderTtsTierInfo() {
  const el = $("pf-tts-tier-info");
  if (!el) return;
  const ttsModel = $("pf-tts-model") && $("pf-tts-model").value;
  const tier = modelsCatalog && modelsCatalog.tts_tiers && modelsCatalog.tts_tiers[ttsModel];
  if (!tier) {
    el.textContent = "";
    el.className = "pf-tier-badge hidden";
    return;
  }
  el.textContent = `${tier.label} — US$ ${tier.effective_cost_per_m_chars}/M caracteres`;
  el.className = `pf-tier-badge tier-${tier.tier}`;
}

function presentersFromSpec(spec) {
  return spec.split(",").map((chunk) => {
    const [speaker = "", voice = "Kore", style = ""] = chunk.trim().split(":");
    return { speaker: speaker.trim(), voice: voice.trim(), style: style.trim() };
  }).filter((presenter) => presenter.speaker && presenter.voice);
}

async function openProfileForm(profile = null, tabCategory = null) {
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
  const applyProviderVisibility = () => {
    const isOpenRouter = providerSelect.value === "openrouter";
    $("pf-api-models").classList.toggle("hidden", !isOpenRouter);
    const cli = (settingsInfo ? settingsInfo.subscription_clis : [])
      .find((item) => item.key === providerSelect.value);
    const canPickModel = Boolean(cli && cli.supports_model);
    $("pf-subscription-model-label").classList.toggle("hidden", isOpenRouter || !canPickModel);
    const options = $("pf-subscription-model-options");
    options.replaceChildren();
    for (const suggestion of (cli && cli.model_suggestions) || []) {
      const option = document.createElement("option");
      option.value = suggestion;
      options.appendChild(option);
    }
    $("pf-subscription-model").placeholder = cli && cli.configured_model
      ? `vazio = ${cli.configured_model} (configurado na CLI)`
      : "vazio = modelo padrão da CLI";
  };
  providerSelect.onchange = applyProviderVisibility;

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
  if (profile) {
    providerSelect.value = base.text_provider || "openrouter";
  } else if (tabCategory) {
    const providerMap = {
      "Claude Code": "claude-code", "Codex": "codex", "Gemini CLI": "gemini-cli",
    };
    providerSelect.value = providerMap[tabCategory] || "openrouter";
  } else {
    providerSelect.value = base.text_provider || "openrouter";
  }
  $("pf-subscription-model").value = profile
    ? profile.subscription_model || ""
    : (settingsInfo && settingsInfo.profile_subscription_model) || "";
  applyProviderVisibility();
  configureModelPicker($("pf-text-vendor"), $("pf-text-model"),
    modelsCatalog.text_models, base.text_model);
  configureModelPicker($("pf-audit-vendor"), $("pf-audit-model"),
    modelsCatalog.text_models, base.audit_model);
  configureModelPicker($("pf-tts-vendor"), $("pf-tts-model"),
    modelsCatalog.tts_models, base.tts_model);

  // Ao trocar vendor ou modelo TTS, atualizar vozes dos apresentadores e badge de tier
  const origTtsVendorChange = $("pf-tts-vendor").onchange;
  $("pf-tts-vendor").onchange = () => {
    if (origTtsVendorChange) origTtsVendorChange();
    refreshPresenterVoices();
    renderTtsTierInfo();
  };
  $("pf-tts-model").addEventListener("change", () => {
    refreshPresenterVoices();
    renderTtsTierInfo();
  });
  renderTtsTierInfo();

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

$("btn-profile-new").onclick = () => openProfileForm(null, activeProfileCategory);
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
    subscription_model: provider === "openrouter"
      ? "" : $("pf-subscription-model").value.trim(),
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
updateGenerationMode();
