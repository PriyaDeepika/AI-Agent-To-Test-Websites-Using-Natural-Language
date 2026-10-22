(() => {
  const $ = (id) => document.getElementById(id);
  const api = async (method, path, body) => {
    const r = await fetch(path, {method, headers: {"Content-Type": "application/json"}, body: body ? JSON.stringify(body) : undefined});
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || `Request failed (${r.status})`);
    return data;
  };
  const el = (tag, attrs = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") n.className = v; else if (k.startsWith("on")) n.addEventListener(k.slice(2), v); else if (v !== null && v !== undefined) n.setAttribute(k, v);
    }
    for (const k of kids.flat()) if (k !== null && k !== undefined) n.append(k.nodeType ? k : document.createTextNode(k));
    return n;
  };
  const ACTIVE = new Set(["queued", "running", "awaiting_user"]);
  let currentId = null, pollTimer = null, answering = false;

  // ---------- navigation ----------
  function show(view) {
    document.querySelectorAll(".nav").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
    $("view-workspace").hidden = view !== "workspace";
    $("view-history").hidden = view !== "history";
    if (view === "history") loadHistory();
  }
  document.querySelectorAll(".nav").forEach((b) => b.addEventListener("click", () => show(b.dataset.view)));

  // ---------- system status (real values from /api/health) ----------
  async function loadHealth() {
    try {
      const h = await api("GET", "/api/health");
      const s = $("sys"); s.replaceChildren(
        el("div", {}, "Chromium: ", el("b", {}, h.chromium_installed ? "installed" : "NOT installed")),
        el("div", {}, "Planner: ", el("b", {}, h.llm_planner ? "LLM + rules" : "rules only")),
        el("div", {}, "Browser: ", el("b", {}, h.headless ? "headless" : "visible window")),
        el("div", {}, `Limits: ${h.limits.max_actions} actions · ${h.limits.timeout_s}s`));
    } catch { $("sys").textContent = "Server unreachable"; }
  }

  // ---------- examples ----------
  async function loadExamples() {
    const list = await api("GET", "/api/examples");
    $("examples").replaceChildren(...list.map((ex) => el("li", {}, el("button", {title: ex.text, onclick: () => {
      $("instruction").value = ex.text; $("url").value = ex.url; clearTimelineForPreview();
    }}, el("span", {class: "tag" + (ex.real ? " real" : "")}, ex.real ? "real site" : "local"), ex.title))));
  }

  // ---------- plan preview ----------
  function clearTimelineForPreview() { if (!currentId || !ACTIVE.has(lastStatus)) { /* keep history view */ } }
  let lastStatus = null;
  function setError(msg) { const e = $("formError"); e.textContent = msg || ""; e.hidden = !msg; }

  $("planBtn").addEventListener("click", async () => {
    setError("");
    try {
      const p = await api("POST", "/api/plan", {instruction: $("instruction").value, url: $("url").value});
      stopPolling(); currentId = null; $("runstate").hidden = true; $("resultBanner").hidden = true; $("pausePanel").hidden = true;
      $("rightTitle").textContent = "Planned actions";
      $("planMeta").textContent = `${p.steps.length} steps · planner: ${p.planner}`;
      renderNotes(p.notes);
      renderSteps(p.steps.map((s, i) => ({idx: i, status: "pending", description: s.description, action: s.action, params: s.params || {target: s.target, value: s.value}})));
    } catch (e) { setError(e.message); }
  });

  // ---------- run ----------
  $("runBtn").addEventListener("click", async () => {
    setError(""); $("runBtn").disabled = true;
    try {
      const {id} = await api("POST", "/api/runs", {instruction: $("instruction").value, url: $("url").value});
      openRun(id);
    } catch (e) { setError(e.message); } finally { $("runBtn").disabled = false; }
  });
  $("cancelBtn").addEventListener("click", async () => { try { await api("POST", `/api/runs/${currentId}/cancel`); } catch (e) { setError(e.message); } });

  function openRun(id) {
    show("workspace"); currentId = id; stopPolling(); tick();
    pollTimer = setInterval(tick, 1000);
  }
  function stopPolling() { if (pollTimer) clearInterval(pollTimer); pollTimer = null; }

  async function tick() {
    if (!currentId || answering) return;
    let run;
    try { run = await api("GET", `/api/runs/${currentId}`); } catch (e) { setError(e.message); stopPolling(); return; }
    render(run);
    if (!ACTIVE.has(run.status)) { stopPolling(); loadRecent(); }
  }

  function render(run) {
    lastStatus = run.status;
    $("instruction").value = $("instruction").value || run.instruction;
    $("runstate").hidden = false;
    $("runDot").className = "dot " + run.status;
    const running = run.steps.find((s) => s.status === "running");
    const labels = {queued: "Queued", running: running ? `Step ${running.idx + 1}/${run.steps.length}: ${running.description}` : "Planning…",
      awaiting_user: "Waiting for you", passed: "Passed", failed: "Failed", inconclusive: "Inconclusive", blocked: "Blocked", cancelled: "Cancelled"};
    $("runLabel").textContent = labels[run.status] || run.status;
    const last = [...run.steps].reverse().find((s) => s.url);
    $("runUrl").textContent = last ? last.url : "";
    $("rightTitle").textContent = "Execution";
    $("planMeta").textContent = `${run.steps.length} steps · planner: ${run.planner || "…"} · run ${run.id}`;
    $("cancelBtn").hidden = !ACTIVE.has(run.status);
    renderNotes(run.notes);
    renderSteps(run.steps);
    renderPause(run);
    renderResult(run);
  }

  function renderNotes(notes) {
    const n = $("notes"); n.hidden = !(notes && notes.length);
    n.replaceChildren(...(notes || []).map((t) => el("p", {}, t)));
  }

  function renderSteps(steps) {
    const ol = $("timeline");
    if (!steps.length) { ol.replaceChildren(el("li", {class: "empty"}, "Waiting for the planner…")); return; }
    ol.replaceChildren(...steps.map((s) => {
      const ev = s.evidence && Object.keys(s.evidence).length ? el("details", {}, el("summary", {}, "Evidence"), el("pre", {}, JSON.stringify(s.evidence, null, 2))) : null;
      const shot = s.screenshot && currentId ? el("img", {class: "shot", alt: `Screenshot of step ${s.idx + 1}`, loading: "lazy",
        src: `/api/runs/${currentId}/screenshots/${s.screenshot}`, onclick: (e) => openLightbox(e.target.src)}) : null;
      const tgt = s.params ? [s.params.target, s.params.value].filter(Boolean).join(" · ") : "";
      return el("li", {class: `step ${s.status}`},
        el("div", {class: "badge"}, String(s.idx + 1)),
        el("div", {class: "card"},
          el("div", {class: "row"}, el("span", {class: "desc"}, s.description), el("span", {class: "pill"}, s.status)),
          el("div", {class: "meta"}, [s.action, tgt].filter(Boolean).join(" · ")),
          s.detail ? el("p", {class: "detail"}, s.detail) : null,
          s.error ? el("p", {class: "detail err"}, s.error) : null,
          ev, shot));
    }));
  }

  function renderPause(run) {
    const box = $("pausePanel");
    if (run.status !== "awaiting_user" || !run.pending) { box.hidden = true; if (!answering) box.replaceChildren(); return; }
    if (!box.hidden && box.dataset.key === run.pending.prompt) return;   // keep typed input while polling
    const p = run.pending; box.dataset.key = p.prompt; box.hidden = false;
    const title = {confirm: "Confirmation required", human: "Human action required", input: "Input needed"}[p.kind] || "Paused";
    const input = p.kind === "input" ? el("input", {type: p.secret ? "password" : "text", id: "pauseInput", autocomplete: "off", placeholder: p.secret ? "Password (not stored)" : "Your answer"}) : null;
    const send = async (approved) => {
      answering = true;
      try { await api("POST", `/api/runs/${run.id}/respond`, {approved, text: input ? input.value : ""}); box.hidden = true; box.dataset.key = ""; }
      catch (e) { setError(e.message); } finally { answering = false; tick(); }
    };
    const btns = p.kind === "confirm" ? [el("button", {class: "primary", onclick: () => send(true)}, "Allow this action"), el("button", {class: "ghost", onclick: () => send(false)}, "Stop here")]
      : p.kind === "human" ? [el("button", {class: "primary", onclick: () => send(true)}, "I've handled it — continue"), el("button", {class: "ghost", onclick: () => send(false)}, "Stop")]
      : [el("button", {class: "primary", onclick: () => send(true)}, "Continue"), el("button", {class: "ghost", onclick: () => send(false)}, "Stop")];
    const chips = (p.options || []).length ? el("div", {class: "chips"}, p.options.map((o) => el("button", {class: "chip", onclick: () => { input.value = o.replace(/^US\s*/i, ""); }}, o))) : null;
    box.replaceChildren(el("h3", {}, title), el("p", {}, p.prompt), chips, input, el("div", {class: "btns"}, ...btns));
    if (input) input.focus();
  }

  function renderResult(run) {
    const b = $("resultBanner");
    if (ACTIVE.has(run.status) || !run.outcome) { b.hidden = true; return; }
    b.hidden = false; b.className = "result " + run.outcome;
    const scope = {real_website: "Real website", local_regression: "Local regression page", unknown: "Unknown"}[run.kind] || "";
    b.replaceChildren(
      el("div", {}, el("span", {class: "o"}, run.outcome), " ", el("span", {class: "scope " + run.kind}, scope)),
      el("p", {}, run.summary || ""),
      el("div", {class: "dl"},
        el("a", {href: `/api/runs/${run.id}/report.html`}, "HTML report"),
        el("a", {href: `/api/runs/${run.id}/report.json`}, "JSON report"),
        el("a", {href: `/api/runs/${run.id}/script.py`}, "Replay script (.py)")));
  }

  // ---------- recent + history ----------
  const when = (t) => t ? new Date(t * 1000).toLocaleString() : "";
  async function loadRecent() {
    const runs = await api("GET", "/api/runs");
    $("recent").replaceChildren(...runs.slice(0, 8).map((r) => el("li", {onclick: () => { $("instruction").value = r.instruction; openRun(r.id); }, title: r.instruction},
      el("span", {class: "dot " + r.status}), el("span", {class: "t"}, r.instruction))));
  }
  async function loadHistory() {
    const runs = await api("GET", "/api/runs");
    $("historyEmpty").hidden = runs.length > 0;
    $("historyBody").replaceChildren(...runs.map((r) => el("tr", {class: "row", onclick: () => { $("instruction").value = r.instruction; $("url").value = r.start_url || ""; openRun(r.id); }},
      el("td", {}, el("span", {class: "dot " + r.status}), " ", r.outcome || r.status),
      el("td", {class: "ins", title: r.instruction}, r.instruction),
      el("td", {}, r.kind ? el("span", {class: "scope " + r.kind}, r.kind === "real_website" ? "real site" : "local") : ""),
      el("td", {}, ""), el("td", {class: "muted"}, when(r.started || r.created)),
      el("td", {}, el("button", {class: "ghost", onclick: async (e) => { e.stopPropagation(); if (confirm("Delete this run and its screenshots?")) { await api("DELETE", `/api/runs/${r.id}`); loadHistory(); loadRecent(); } }}, "Delete")))));
  }

  function openLightbox(src) { const l = $("lightbox"); l.querySelector("img").src = src; l.hidden = false; }
  $("lightbox").addEventListener("click", () => { $("lightbox").hidden = true; });

  loadHealth(); loadExamples(); loadRecent();
})();
