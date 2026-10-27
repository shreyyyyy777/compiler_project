const $ = (sel) => document.querySelector(sel);

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------

const tabButtons = document.querySelectorAll(".tab-btn");
tabButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    tabButtons.forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $(`#tab-${btn.dataset.tab}`).classList.add("active");
    if (btn.dataset.tab === "automaton") drawAutomaton();
    if (btn.dataset.tab === "tests" && !testsLoadedOnce) runTests();
  });
});

// ---------------------------------------------------------------------------
// Match tab
// ---------------------------------------------------------------------------

async function checkMatch() {
  const regex = $("#regex-input").value;
  const input = $("#text-input").value;

  const res = await fetch("/api/match", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ regex, input }),
  });
  const data = await res.json();

  const badge = $("#result-badge");
  const errorBanner = $("#error-banner");
  const meta = $("#match-meta");
  const trace = $("#trace");

  if (data.error) {
    badge.classList.add("hidden");
    errorBanner.classList.remove("hidden");
    errorBanner.textContent = `${data.error_type === "limit" ? "Limit exceeded" : "Invalid regex"}: ${data.error}`;
    meta.classList.add("hidden");
    trace.classList.add("hidden");
    return;
  }

  errorBanner.classList.add("hidden");
  badge.classList.remove("hidden");
  badge.textContent = data.matches ? "MATCH" : "NO MATCH";
  badge.className = "badge " + (data.matches ? "match" : "no-match");

  meta.classList.remove("hidden");
  meta.textContent = `DFA states explored: ${data.dfa_states_explored}` +
    (data.steps_truncated ? " (trace truncated for display)" : "");

  trace.classList.remove("hidden");
  trace.innerHTML = "";
  for (const step of data.steps) {
    const el = document.createElement("span");
    el.className = "trace-step" + (step.accept ? " accept" : "");
    el.textContent = step.char === null ? `start(q${step.dfa_state})` : `${step.char}→q${step.dfa_state}`;
    trace.appendChild(el);
  }
}

$("#check-btn").addEventListener("click", checkMatch);
[$("#regex-input"), $("#text-input")].forEach((el) =>
  el.addEventListener("keydown", (e) => { if (e.key === "Enter") checkMatch(); })
);

// ---------------------------------------------------------------------------
// Automaton tab
// ---------------------------------------------------------------------------

let automatonKind = "dfa";
document.querySelectorAll(".seg-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".seg-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    automatonKind = btn.dataset.kind;
    drawAutomaton();
  });
});
$("#refresh-automaton").addEventListener("click", drawAutomaton);

async function drawAutomaton() {
  const regex = $("#regex-input").value;
  const res = await fetch("/api/automaton", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ regex, kind: automatonKind }),
  });
  const data = await res.json();

  const note = $("#automaton-note");
  if (data.error) {
    note.classList.remove("hidden");
    note.textContent = `Cannot draw automaton: ${data.error}`;
    $("#automaton-svg").innerHTML = "";
    return;
  }
  if (data.truncated) {
    note.classList.remove("hidden");
    note.textContent = `Pattern produces a large automaton - showing the first states reached (render capped for readability). Matching itself is unaffected.`;
  } else {
    note.classList.add("hidden");
  }

  renderGraph(data.nodes, data.edges, data.start);
}

function renderGraph(nodes, edges, startId) {
  const svg = $("#automaton-svg");
  svg.innerHTML = "";
  if (nodes.length === 0) return;

  const R = 20;
  const xSpacing = 130;
  const ySpacing = 84;
  const marginX = 60;
  const marginY = 50;

  // BFS layering from the start state, following edges forward.
  const adj = new Map(nodes.map((n) => [n.id, []]));
  edges.forEach((e) => { if (adj.has(e.from)) adj.get(e.from).push(e.to); });

  const layer = new Map([[startId, 0]]);
  const queue = [startId];
  while (queue.length) {
    const id = queue.shift();
    for (const t of adj.get(id) || []) {
      if (!layer.has(t)) { layer.set(t, layer.get(id) + 1); queue.push(t); }
    }
  }
  let maxLayer = Math.max(0, ...layer.values());
  nodes.forEach((n) => { if (!layer.has(n.id)) layer.set(n.id, ++maxLayer); });

  const byLayer = new Map();
  nodes.forEach((n) => {
    const l = layer.get(n.id);
    if (!byLayer.has(l)) byLayer.set(l, []);
    byLayer.get(l).push(n.id);
  });

  const pos = new Map();
  let maxNodesInLayer = 1;
  byLayer.forEach((ids) => { maxNodesInLayer = Math.max(maxNodesInLayer, ids.length); });

  byLayer.forEach((ids, l) => {
    ids.forEach((id, i) => {
      pos.set(id, {
        x: marginX + l * xSpacing,
        y: marginY + i * ySpacing,
      });
    });
  });

  const width = marginX * 2 + (maxLayer + 1) * xSpacing;
  const height = Math.max(300, marginY * 2 + maxNodesInLayer * ySpacing);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("width", width);
  svg.setAttribute("height", height);

  const NS = "http://www.w3.org/2000/svg";
  const defs = document.createElementNS(NS, "defs");
  defs.innerHTML = `
    <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto" markerUnits="userSpaceOnUse">
      <path d="M0,0 L0,6 L7,3 z" fill="#5b8cff" />
    </marker>`;
  svg.appendChild(defs);

  // Edges (draw first, under nodes). Curve everything slightly so
  // parallel/backward edges (e.g. star loops) stay legible.
  edges.forEach((e) => {
    const from = pos.get(e.from);
    const to = pos.get(e.to);
    if (!from || !to) return;
    const path = document.createElementNS(NS, "path");
    let d, labelX, labelY;

    if (e.from === e.to) {
      // self-loop: small arc above the node
      const x = from.x, y = from.y;
      d = `M ${x - 10} ${y - R} C ${x - 26} ${y - R - 40}, ${x + 26} ${y - R - 40}, ${x + 10} ${y - R}`;
      labelX = x; labelY = y - R - 34;
    } else {
      const dx = to.x - from.x, dy = to.y - from.y;
      const mx = (from.x + to.x) / 2, my = (from.y + to.y) / 2;
      const dist = Math.hypot(dx, dy) || 1;
      const curve = Math.min(40, dist * 0.25) * (from.x <= to.x ? 1 : -1);
      const nx = -dy / dist, ny = dx / dist;
      const cx = mx + nx * curve, cy = my + ny * curve;
      const startX = from.x + (dx / dist) * R, startY = from.y + (dy / dist) * R;
      const endX = to.x - (dx / dist) * R, endY = to.y - (dy / dist) * R;
      d = `M ${startX} ${startY} Q ${cx} ${cy} ${endX} ${endY}`;
      labelX = cx; labelY = cy;
    }

    path.setAttribute("d", d);
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", "#3a4666");
    path.setAttribute("stroke-width", "1.5");
    path.setAttribute("marker-end", "url(#arrow)");
    svg.appendChild(path);

    const label = document.createElementNS(NS, "text");
    label.setAttribute("x", labelX);
    label.setAttribute("y", labelY);
    label.setAttribute("fill", "#92a0bd");
    label.setAttribute("font-size", "11");
    label.setAttribute("font-family", "monospace");
    label.setAttribute("text-anchor", "middle");
    label.textContent = e.label;
    svg.appendChild(label);
  });

  // Nodes
  nodes.forEach((n) => {
    const p = pos.get(n.id);
    const g = document.createElementNS(NS, "g");

    const circle = document.createElementNS(NS, "circle");
    circle.setAttribute("cx", p.x);
    circle.setAttribute("cy", p.y);
    circle.setAttribute("r", R);
    circle.setAttribute("fill", n.accept ? "rgba(53,201,143,0.15)" : "#0d1220");
    circle.setAttribute("stroke", n.accept ? "#35c98f" : "#5b8cff");
    circle.setAttribute("stroke-width", "2");
    g.appendChild(circle);

    if (n.accept) {
      const inner = document.createElementNS(NS, "circle");
      inner.setAttribute("cx", p.x);
      inner.setAttribute("cy", p.y);
      inner.setAttribute("r", R - 5);
      inner.setAttribute("fill", "none");
      inner.setAttribute("stroke", "#35c98f");
      inner.setAttribute("stroke-width", "1.5");
      g.appendChild(inner);
    }

    if (n.start) {
      const startMark = document.createElementNS(NS, "path");
      startMark.setAttribute("d", `M ${p.x - R - 22} ${p.y} L ${p.x - R - 4} ${p.y}`);
      startMark.setAttribute("stroke", "#5b8cff");
      startMark.setAttribute("stroke-width", "2");
      startMark.setAttribute("marker-end", "url(#arrow)");
      g.appendChild(startMark);
    }

    const text = document.createElementNS(NS, "text");
    text.setAttribute("x", p.x);
    text.setAttribute("y", p.y + 4);
    text.setAttribute("text-anchor", "middle");
    text.setAttribute("font-size", "11");
    text.setAttribute("font-family", "monospace");
    text.setAttribute("fill", "#e7ebf3");
    text.textContent = `q${n.id}`;
    g.appendChild(text);

    svg.appendChild(g);
  });
}

// ---------------------------------------------------------------------------
// Test Suite tab
// ---------------------------------------------------------------------------

let testsLoadedOnce = false;

async function runTests() {
  testsLoadedOnce = true;
  $("#test-summary").textContent = "Running…";
  const res = await fetch("/api/tests");
  const data = await res.json();

  $("#test-summary").textContent = `${data.passed} / ${data.total} passed`;

  const tbody = document.querySelector("#test-table tbody");
  tbody.innerHTML = "";
  for (const r of data.results) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${r.category}</td>
      <td>${r.description}</td>
      <td class="pattern">${escapeHtml(r.pattern)}</td>
      <td class="input">${escapeHtml(r.input)}</td>
      <td>${r.expected}</td>
      <td>${escapeHtml(r.actual)}</td>
      <td class="${r.passed ? "pass" : "fail"}">${r.passed ? "PASS" : "FAIL"}</td>
    `;
    tbody.appendChild(tr);
  }
}

$("#run-tests-btn").addEventListener("click", runTests);

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// Initial render
checkMatch();
