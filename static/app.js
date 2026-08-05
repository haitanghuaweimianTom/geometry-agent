// Geometry Agent frontend logic

let mode = "single";
let streamAbort = null;

function switchMode(m) {
  mode = m;
  document.getElementById("tab-single").classList.toggle("active", m === "single");
  document.getElementById("tab-multi").classList.toggle("active", m === "multi");
  document.getElementById("sub-questions").classList.toggle("hidden", m !== "multi");
}

function addSub() {
  const list = document.getElementById("sub-list");
  const idx = list.children.length + 1;
  const input = document.createElement("input");
  input.type = "text";
  input.className = "sub-input";
  input.placeholder = `(${idx}) ...`;
  list.appendChild(input);
}

function setLoading(on) {
  document.getElementById("solve-btn").disabled = on;
  document.getElementById("solve-text").textContent = on ? "求解中…" : "开始求解";
  document.getElementById("spinner").classList.toggle("hidden", !on);
}

function showError(msg) {
  const el = document.getElementById("error");
  el.textContent = "❌ " + msg;
  el.classList.remove("hidden");
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s || "";
  return d.innerHTML;
}

function renderSolution(sol) {
  let html = "";
  if (sol.answer) {
    html += `<div class="part-answer">✅ <strong>答案：</strong>${escapeHtml(sol.answer)}</div>`;
  }
  if (sol.reasoning_summary) {
    html += `<div class="summary-box"><h4>解题思路</h4>${escapeHtml(sol.reasoning_summary)}</div>`;
  }

  if (sol.steps && sol.steps.length) {
    html += `<div class="steps"><h4 style="color:var(--muted);font-size:.85rem;margin-bottom:.4rem">解题步骤</h4>`;
    sol.steps.forEach((st) => {
      const mark = st.verified ? '<span class="step-mark ok">✓</span>' : '<span class="step-mark no">○</span>';
      html += `<div class="step"><span class="step-num">${st.step}.</span>${mark}${escapeHtml(st.statement)}`;
      if (st.reason) html += `<div class="step-reason">依据：${escapeHtml(st.reason)}</div>`;
      html += `</div>`;
    });
    html += `</div>`;
  }
  return html;
}

// ---- SSE Streaming ----
function streamSolve() {
  document.getElementById("error").classList.add("hidden");
  document.getElementById("result").classList.add("hidden");
  const streamLog = document.getElementById("stream-log");
  streamLog.innerHTML = "";
  streamLog.classList.remove("hidden");

  const problem = document.getElementById("problem").value.trim();
  if (!problem) {
    showError("请输入题目");
    return;
  }

  const grade = document.getElementById("grade").value;
  const maxCalls = parseInt(document.getElementById("max-calls").value, 10) || 60;

  if (mode !== "single") {
    showError("流式模式仅支持单题，多小题请使用普通模式");
    return;
  }

  setLoading(true);
  const t0 = Date.now();

  const controller = new AbortController();
  streamAbort = controller;

  fetch("/api/solve/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: problem, grade, max_calls: maxCalls }),
    signal: controller.signal,
  }).then(async (resp) => {
    if (!resp.ok) {
      const err = await resp.text();
      throw new Error(`服务器错误 (${resp.status}): ${err}`);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      let eventName = "";
      for (const line of lines) {
        if (line.startsWith("event: ")) {
          eventName = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          try {
            const data = JSON.parse(line.slice(6));
            handleSSE(eventName, data);
          } catch (e) {
            // skip malformed
          }
          eventName = "";
        }
      }
    }

    const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
    setLoading(false);
    streamLog.classList.add("hidden");
    document.getElementById("stream-log").classList.add("hidden");
    document.getElementById("status-bar").textContent = `✓ 求解完成 · 耗时 ${elapsed}s`;
    document.getElementById("status-bar").className = "status-bar success";
  }).catch((err) => {
    if (err.name === "AbortError") return;
    setLoading(false);
    showError(err.message);
  });
}

function handleSSE(event, data) {
  const log = document.getElementById("stream-log");
  const t = new Date().toLocaleTimeString();

  switch (event) {
    case "start":
      log.innerHTML += `<div class="sse-msg sse-info"><span class="sse-time">${t}</span> ${escapeHtml(data.message)}</div>`;
      break;
    case "attempt":
      log.innerHTML += `<div class="sse-msg sse-info"><span class="sse-time">${t}</span> 第 ${data.attempt}/${data.total} 次尝试</div>`;
      break;
    case "tool_call":
      const icon = data.success ? "✓" : "✗";
      const cls = data.success ? "sse-success" : "sse-warn";
      const summary = data.result_summary ? escapeHtml(data.result_summary).substring(0, 200) : "";
      log.innerHTML += `<div class="sse-msg ${cls}"><span class="sse-time">${t}</span> ${icon} <strong>${escapeHtml(data.tool)}</strong> <span class="sse-call">#${data.call}</span>${summary ? `<div class="sse-summary">${summary}</div>` : ""}</div>`;
      break;
    case "done":
      log.innerHTML += `<div class="sse-msg sse-done"><span class="sse-time">${t}</span> ✅ 完成 · 置信度 ${data.confidence}</div>`;
      if (data.answer) {
        log.innerHTML += `<div class="part-answer" style="margin-top:0.5rem">✅ <strong>答案：</strong>${escapeHtml(data.answer)}</div>`;
      }
      if (data.pdf) {
        document.getElementById("pdf-link").href = data.pdf;
        document.getElementById("pdf-link-wrap").classList.remove("hidden");
      }
      if (data.steps && data.steps.length) {
        const partsDiv = document.getElementById("parts");
        let html = `<div class="part"><div class="steps"><h4 style="color:var(--muted);font-size:.85rem;margin-bottom:.4rem">解题步骤</h4>`;
        data.steps.forEach((st) => {
          const mark = st.verified ? '<span class="step-mark ok">✓</span>' : '<span class="step-mark no">○</span>';
          html += `<div class="step"><span class="step-num">${st.step}.</span>${mark}${escapeHtml(st.statement)}`;
          if (st.reason) html += `<div class="step-reason">依据：${escapeHtml(st.reason)}</div>`;
          html += `</div>`;
        });
        html += `</div></div>`;
        partsDiv.innerHTML = html;
      }
      document.getElementById("result").classList.remove("hidden");
      break;
    case "error":
      log.innerHTML += `<div class="sse-msg sse-error"><span class="sse-time">${t}</span> ❌ ${escapeHtml(data.message)}</div>`;
      showError(data.message);
      setLoading(false);
      break;
  }
  log.scrollTop = log.scrollHeight;
}

// ---- Non-streaming solve ----
async function solve() {
  // Use streaming for single mode, fallback for multi
  if (mode === "single") {
    return streamSolve();
  }

  document.getElementById("error").classList.add("hidden");
  document.getElementById("result").classList.add("hidden");
  document.getElementById("stream-log").classList.add("hidden");

  const problem = document.getElementById("problem").value.trim();
  if (!problem) {
    showError("请输入题目");
    return;
  }
  const grade = document.getElementById("grade").value;
  const maxCalls = parseInt(document.getElementById("max-calls").value, 10) || 60;

  setLoading(true);
  const t0 = Date.now();

  try {
    const subs = [...document.querySelectorAll(".sub-input")]
      .map((i) => i.value.trim())
      .filter((s) => s);
    if (!subs.length) {
      showError("请至少添加一个小题");
      setLoading(false);
      return;
    }

    const resp = await fetch("/api/solve-multi", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: problem, subs, grade, max_calls: maxCalls }),
    });
    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      throw new Error(data.detail || `服务器错误 (${resp.status})`);
    }

    const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
    const status = document.getElementById("status-bar");
    const partsDiv = document.getElementById("parts");

    let html = "";
    let totalOk = 0;
    data.parts.forEach((p) => {
      if (p.solution.verified) totalOk++;
      html += `<div class="part"><div class="part-label">${p.label} ${escapeHtml(p.question)}</div>`;
      html += renderSolution(p.solution);
      html += `</div>`;
    });
    status.className = "status-bar success";
    status.textContent = `✓ ${data.parts.length} 小题完成 · ${totalOk} 题验证通过 · 耗时 ${elapsed}s`;
    partsDiv.innerHTML = html;

    if (data.pdf) {
      document.getElementById("pdf-link").href = data.pdf;
      document.getElementById("pdf-link-wrap").classList.remove("hidden");
    }
    document.getElementById("result").classList.remove("hidden");
  } catch (e) {
    showError(e.message);
  } finally {
    setLoading(false);
  }
}