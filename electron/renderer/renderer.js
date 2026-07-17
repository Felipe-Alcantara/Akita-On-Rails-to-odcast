// Renderer do Audiofy Desktop: lista itens, gera episódios e acompanha
// progresso + custo ao vivo lendo o status da bridge a cada 2 segundos.

const SOURCE = "akita";
const $ = (id) => document.getElementById(id);

let selectedItem = null;
let pollTimer = null;

// ── Lista de itens ────────────────────────────────────────────────────────

async function loadItems(query = "") {
  const command = query ? ["search", SOURCE, query] : ["items", SOURCE];
  const result = await window.audiofy.bridge(...command);
  const list = $("items");
  list.innerHTML = "";
  if (!result.ok) {
    list.innerHTML = `<li class="muted">Erro: ${result.error}</li>`;
    return;
  }
  for (const item of result.items) {
    const row = document.createElement("li");
    row.innerHTML = `<span class="date">${item.published_at}</span><span>${item.title}</span>`;
    row.onclick = () => selectItem(item, row);
    list.appendChild(row);
  }
}

async function selectItem(item, row) {
  document.querySelectorAll("#items li").forEach((li) => li.classList.remove("selected"));
  row.classList.add("selected");
  const detail = await window.audiofy.bridge("item", SOURCE, item.item_id);
  if (!detail.ok) return;
  selectedItem = detail;
  $("detail-empty").classList.add("hidden");
  $("detail").classList.remove("hidden");
  $("detail-title").textContent = detail.title;
  $("detail-meta").textContent =
    `${detail.published_at} · ~${detail.words} palavras · ${detail.url}`;
  $("detail-estimate").textContent =
    `Custo estimado: ~US$ ${detail.estimated_cost_usd.toFixed(2)} ` +
    `(razão real medida: US$ 0,60 ≈ 13 min)`;
  refreshStatus();
}

// ── Geração e acompanhamento ──────────────────────────────────────────────

async function generate() {
  if (!selectedItem) return;
  const confirmed = confirm(
    `Gerar episódio de "${selectedItem.title}"?\n\n` +
    `Custo estimado: ~US$ ${selectedItem.estimated_cost_usd.toFixed(2)} ` +
    `(consome créditos do OpenRouter).`
  );
  if (!confirmed) return;
  const result = await window.audiofy.bridge("generate", SOURCE, selectedItem.item_id);
  if (!result.ok || !result.started) {
    alert(`Não iniciou: ${result.reason || result.error}`);
  }
  refreshStatus();
}

async function abortGeneration() {
  if (!selectedItem) return;
  const result = await window.audiofy.bridge("abort", selectedItem.item_id);
  if (result.ok && result.aborted) {
    alert("Abort solicitado — a geração para no próximo segmento.");
  }
  refreshStatus();
}

async function refreshStatus() {
  const overview = await window.audiofy.bridge("status");
  if (!overview.ok) return;

  // Banner global: deixa explícito o que está consumindo créditos.
  const banner = $("running-banner");
  if (overview.anything_running) {
    const running = overview.running
      .map((e) => `${e.episode_id} (US$ ${e.cost_usd.toFixed(3)})`)
      .join(", ");
    $("running-detail").textContent = running;
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

  $("btn-abort").classList.toggle("hidden", !running);
  $("btn-generate").disabled = running;
  $("btn-play").classList.toggle("hidden", !done);
  $("btn-folder").classList.toggle("hidden", !status);
  $("progress-box").classList.toggle("hidden", !running);

  if (running) {
    const progress = status.progress || {};
    const percent = progress.total
      ? Math.round((100 * progress.current) / progress.total) : 0;
    $("progress-fill").style.width = `${percent}%`;
    $("progress-label").textContent =
      `Etapa: ${status.stage} — ${progress.current || 0}/${progress.total || "?"} (${percent}%)`;
    $("cost-label").textContent = `💰 US$ ${status.cost_usd.toFixed(4)} até agora`;
  }

  $("btn-play").onclick = () => window.audiofy.openPath(status.mp3);
  $("btn-folder").onclick = () => status && window.audiofy.openPath(status.dir);
}

function renderEpisodes(episodes) {
  const list = $("episodes");
  list.innerHTML = episodes.length ? "" : `<li class="muted">Nenhum episódio ainda.</li>`;
  for (const episode of episodes) {
    const row = document.createElement("li");
    const cost = episode.cost_usd ? ` · US$ ${episode.cost_usd.toFixed(4)}` : "";
    row.innerHTML =
      `<span class="state-${episode.state}">●</span> ${episode.episode_id}` +
      `<span class="muted">${episode.state}${cost}</span>`;
    if (episode.mp3) {
      const play = document.createElement("button");
      play.textContent = "▶️";
      play.title = "Ouvir";
      play.onclick = () => window.audiofy.openPath(episode.mp3);
      row.appendChild(play);
    }
    list.appendChild(row);
  }
}

// ── Eventos ───────────────────────────────────────────────────────────────

$("btn-generate").onclick = generate;
$("btn-abort").onclick = abortGeneration;
$("btn-sync").onclick = async () => {
  $("btn-sync").disabled = true;
  await window.audiofy.bridge("sync", SOURCE);
  $("btn-sync").disabled = false;
  loadItems($("search").value.trim());
};

let searchDebounce = null;
$("search").oninput = () => {
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => loadItems($("search").value.trim()), 350);
};

loadItems();
refreshStatus();
