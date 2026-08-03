// Geometry Agent frontend logic

let mode = "single";

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

async function solve() {
  document.getElementById("error").classList.add("hidden");
  document.getElementById("result").classList.add("hidden");

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
    let url, body;
    if (mode === "single") {
      url = "/api/solve";
      body = { text: problem, grade, max_calls: maxCalls };
    } else {
      const subs = [...document.querySelectorAll(".sub-input")]
        .map((i) => i.value.trim())
        .filter((s) => s);
      if (!subs.length) {
        showError("请至少添加一个小题");
        setLoading(false);
        return;
      }
      url = "/api/solve-multi";
      body = { text: problem, subs, grade, max_calls: maxCalls };
    }

    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      throw new Error(data.detail || `服务器错误 (${resp.status})`);
    }

    const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
    const status = document.getElementById("status-bar");
    const partsDiv = document.getElementById("parts");

    if (mode === "single") {
      const sol = data.solution;
      const retries = data.retries ? ` · 重试 ${data.retries} 次` : "";
      status.className = "status-bar success";
      status.textContent = `✓ 求解完成 · 耗时 ${elapsed}s${retries} · 置信度 ${sol.confidence}`;
      partsDiv.innerHTML = `<div class="part">${renderSolution(sol)}</div>`;
    } else {
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
    }

    if (data.pdf) {
      const link = document.getElementById("pdf-link");
      link.href = data.pdf;
      document.getElementById("pdf-link-wrap").classList.remove("hidden");
    }
    document.getElementById("result").classList.remove("hidden");
  } catch (e) {
    showError(e.message);
  } finally {
    setLoading(false);
  }
}
