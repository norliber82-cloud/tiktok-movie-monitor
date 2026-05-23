/* Vanilla JS dashboard — no bundler needed. */

let VIDEOS = [];
let CREATORS = [];
let GENERATED_AT = 0;

async function loadData() {
  const [v, c] = await Promise.all([
    fetch("videos.json").then(r => r.json()).catch(() => ({ items: [] })),
    fetch("creators.json").then(r => r.json()).catch(() => ({ items: [] })),
  ]);
  VIDEOS = (v.items || []).sort(
    (a, b) => (b.create_time || 0) - (a.create_time || 0)
  );
  CREATORS = c.items || [];
  GENERATED_AT = v.generated_at || c.generated_at || Date.now();

  document.getElementById("generated-at").textContent =
    "Last refresh: " + new Date(GENERATED_AT).toLocaleString();
  document.getElementById("totals").textContent =
    `${VIDEOS.length} videos · ${CREATORS.length} creators`;
}

function fmt(n) {
  if (!n && n !== 0) return "—";
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return String(n);
}

function ageShort(ms) {
  if (!ms) return "—";
  const diff = Date.now() - ms;
  const h = diff / 3.6e6;
  if (h < 24) return `${h.toFixed(1)}h`;
  return `${(h / 24).toFixed(1)}d`;
}

/* ------------- Videos tab ------------- */


/* ------------ Review mode ------------ */
let selected = new Set();
let reviewMode = false;

function toggleReview() {
  reviewMode = !reviewMode;
  document.getElementById("review-bar").style.display = reviewMode ? "flex" : "none";
  document.querySelectorAll(".cb-review").forEach(cb => { cb.style.display = reviewMode ? "inline" : "none"; });
  if (!reviewMode) { selected.clear(); updateReviewCount(); }
}

function selAll() {
  if (!reviewMode) return;
  const filtered = getFilteredVideos();
  if (selected.size === filtered.length) { selected.clear(); }
  else { filtered.forEach(v => selected.add(v._record_id || v.video_id)); }
  updateReviewCount();
  document.querySelectorAll(".cb-review").forEach(cb => {
    const vid = cb.dataset.id;
    cb.checked = selected.has(vid);
  });
}

function toggleVideo(e, id) {
  if (e.target.checked) selected.add(id);
  else selected.delete(id);
  updateReviewCount();
}

function updateReviewCount() {
  document.getElementById("review-count").textContent = selected.size;
}

function sendToHermes() {
  if (selected.size === 0) return;
  const filtered = getFilteredVideos();
  const toDelete = filtered.filter(v => selected.has(v._record_id || v.video_id));
  
  // Group by region
  const jp = toDelete.filter(v => v._region === 'JP');
  const us = toDelete.filter(v => v._region === 'US');
  
  let cmd = "删除以下飞书视频记录:\n\n";
  if (jp.length) {
    cmd += `JP Videos (tblGCE433yHlyi19) — ${jp.length}条:\n`;
    jp.forEach(v => { cmd += `${v._record_id}\t${(v.caption||'').slice(0,50).replace(/\n/g,' ')}\n`; });
    cmd += "\n";
  }
  if (us.length) {
    cmd += `US Videos (tblrY6LqfrQsc1qv) — ${us.length}条:\n`;
    us.forEach(v => { cmd += `${v._record_id}\t${(v.caption||'').slice(0,50).replace(/\n/g,' ')}\n`; });
  }
  
  navigator.clipboard.writeText(cmd).then(() => {
    const btn = document.getElementById("btn-hermes");
    btn.textContent = "✅ 已复制! 粘贴给 Hermes";
    setTimeout(() => { btn.textContent = `📋 发送给 Hermes (${selected.size}条)`; }, 2000);
  });
}

function getFilteredVideos() {
  const plat = document.getElementById("f-platform").value;
  const lang = document.getElementById("f-language").value;
  const tier = document.getElementById("f-tier").value;
  const q = document.getElementById("f-q").value.trim().toLowerCase();
  return VIDEOS.filter(v => {
    if (plat && v.platform !== plat) return false;
    if (lang && v.language !== lang) return false;
    if (tier && v.tier !== tier) return false;
    if (q) {
      const txt = ((v.caption||"") + " " + (v.author||"") + " " + (v.tags||"")).toLowerCase();
      if (!txt.includes(q)) return false;
    }
    return true;
  });
}

function renderVideos() {
  const plat = document.getElementById("f-platform").value;
  const lang = document.getElementById("f-language").value;
  const tier = document.getElementById("f-tier").value;
  const q = document.getElementById("f-q").value.trim().toLowerCase();

  const filtered = VIDEOS.filter(v => {
    if (plat && v.platform !== plat) return false;
    if (lang && v.language !== lang) return false;
    if (tier && v.tier !== tier) return false;
    if (q) {
      const hay = (v.caption + " " + (v.author || "")).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  document.getElementById("videos-count").textContent =
    `${filtered.length} / ${VIDEOS.length}`;

  const grid = document.getElementById("videos-grid");
  grid.innerHTML = "";
  const langFlag = { en: "🇺🇸", ja: "🇯🇵", zh: "🇨🇳", ko: "🇰🇷" };

  for (const v of filtered.slice(0, 500)) {
    const card = document.createElement("a");
    card.className = "card";
    card.href = v.video_url || "#";
    card.target = "_blank";
    card.rel = "noopener";

    // Review checkbox
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "cb-review";
    cb.dataset.id = v._record_id || v.video_id;
    cb.style.display = reviewMode ? "inline" : "none";
    cb.checked = selected.has(v._record_id || v.video_id);
    cb.addEventListener("change", (e) => toggleVideo(e, cb.dataset.id));
    card.appendChild(cb);

    const cover = document.createElement("img");
    cover.className = "cover";
    cover.loading = "lazy";
    cover.src = v.cover_url || "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg'/>";
    cover.onerror = () => { cover.style.display = "none"; };
    card.appendChild(cover);

    const body = document.createElement("div");
    body.className = "body";

    const badges = document.createElement("div");
    badges.className = "badges";
    if (v.tier) {
      const b = document.createElement("span");
      b.className = "badge tier-" + v.tier;
      b.textContent = v.tier;
      badges.appendChild(b);
    }
    if (v.platform) {
      const b = document.createElement("span");
      b.className = "badge";
      b.textContent = v.platform === "youtube" ? "📺 YT" : "▶️ TT";
      badges.appendChild(b);
    }
    if (v.language) {
      const b = document.createElement("span");
      b.className = "badge";
      b.textContent = (langFlag[v.language] || "") + " " + v.language.toUpperCase();
      badges.appendChild(b);
    }
    body.appendChild(badges);

    const author = document.createElement("span");
    author.className = "author";
    author.textContent = v.author || "";
    body.appendChild(author);

    const caption = document.createElement("div");
    caption.className = "caption";
    caption.textContent = v.caption || "";
    body.appendChild(caption);

    const stats = document.createElement("div");
    stats.className = "stats";
    stats.innerHTML =
      `👀 ${fmt(v.play_count)} · ❤️ ${fmt(v.like_count)} · 💬 ${fmt(v.comment_count)} · ⏱ ${ageShort(v.create_time)}`;
    body.appendChild(stats);

    card.appendChild(body);
    grid.appendChild(card);
  }
}

/* ------------- Creators tab ------------- */

  // Sync checkboxes with review mode
  document.querySelectorAll(".cb-review").forEach(cb => {
    cb.style.display = reviewMode ? "inline" : "none";
    cb.checked = selected.has(cb.dataset.id);
  });
  updateReviewCount();

function renderCreators() {
  const lang = document.getElementById("c-language").value;
  const q = document.getElementById("c-q").value.trim().toLowerCase();

  const filtered = CREATORS.filter(c => {
    if (lang && c.language !== lang) return false;
    if (q && !(c.author_unique || "").toLowerCase().includes(q)) return false;
    return true;
  }).sort((a, b) => (b.evaluated_at || 0) - (a.evaluated_at || 0));

  document.getElementById("creators-count").textContent =
    `${filtered.length} / ${CREATORS.length}`;

  const tbody = document.querySelector("#creators-table tbody");
  tbody.innerHTML = "";
  for (const c of filtered.slice(0, 500)) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><a href="${c.profile_url || "#"}" target="_blank" rel="noopener">@${c.author_unique || ""}</a>
          ${c.nickname ? `<br><small style="color:var(--muted)">${c.nickname}</small>` : ""}</td>
      <td>${c.language || ""}</td>
      <td>${fmt(c.follower_count)}</td>
      <td>${fmt(c.median_plays)}</td>
      <td>${fmt(c.max_plays_7d)}</td>
      <td>${c.posts_14d || 0}</td>
      <td>${Math.round((c.vertical_ratio || 0) * 100)}%</td>
      <td>${c.evaluated_at ? new Date(c.evaluated_at).toLocaleString() : ""}</td>`;
    tbody.appendChild(tr);
  }
}

/* ------------- Stats tab ------------- */

function renderStats() {
  const stats = {
    total: VIDEOS.length,
    red: VIDEOS.filter(v => v.tier === "RED").length,
    orange: VIDEOS.filter(v => v.tier === "ORANGE").length,
    yellow: VIDEOS.filter(v => v.tier === "YELLOW").length,
    tt: VIDEOS.filter(v => v.platform === "tiktok").length,
    yt: VIDEOS.filter(v => v.platform === "youtube").length,
    en: VIDEOS.filter(v => v.language === "en").length,
    ja: VIDEOS.filter(v => v.language === "ja").length,
    creators: CREATORS.length,
  };
  const grid = document.getElementById("stat-grid");
  grid.innerHTML = Object.entries({
    "Total videos": stats.total,
    "🔥 Red (1M+)": stats.red,
    "🟧 Orange (500K+)": stats.orange,
    "🟡 Yellow (200K+)": stats.yellow,
    "TikTok": stats.tt,
    "YouTube": stats.yt,
    "🇺🇸 English": stats.en,
    "🇯🇵 Japanese": stats.ja,
    "Creators monitored": stats.creators,
  }).map(([label, n]) =>
    `<div class="stat"><div class="n">${n}</div><div class="label">${label}</div></div>`
  ).join("");

  drawTimeline();
  drawTierPie();
}

function drawTimeline() {
  const canvas = document.getElementById("chart-timeline");
  const ctx = canvas.getContext("2d");
  const W = canvas.width = canvas.offsetWidth;
  const H = canvas.height;
  ctx.clearRect(0, 0, W, H);

  const days = 7;
  const now = Date.now();
  const buckets = Array(days).fill(0).map(() => ({ R: 0, O: 0, Y: 0 }));
  for (const v of VIDEOS) {
    if (!v.create_time) continue;
    const dayAgo = Math.floor((now - v.create_time) / 86400000);
    if (dayAgo < 0 || dayAgo >= days) continue;
    const key = v.tier === "RED" ? "R" : v.tier === "ORANGE" ? "O" : "Y";
    buckets[days - 1 - dayAgo][key]++;
  }

  const max = Math.max(1, ...buckets.map(b => b.R + b.O + b.Y));
  const bw = W / days;
  const colors = { R: "#ff4d4f", O: "#fa8c16", Y: "#fadb14" };
  buckets.forEach((b, i) => {
    let y = H - 20;
    ["Y", "O", "R"].forEach(k => {
      const h = (b[k] / max) * (H - 30);
      ctx.fillStyle = colors[k];
      ctx.fillRect(i * bw + 4, y - h, bw - 8, h);
      y -= h;
    });
    ctx.fillStyle = "#8b95a3";
    ctx.font = "11px sans-serif";
    ctx.textAlign = "center";
    const d = new Date(now - (days - 1 - i) * 86400000);
    ctx.fillText(`${d.getMonth() + 1}/${d.getDate()}`, i * bw + bw / 2, H - 6);
  });
}

function drawTierPie() {
  const canvas = document.getElementById("chart-tier");
  const ctx = canvas.getContext("2d");
  const W = canvas.width = canvas.offsetWidth;
  const H = canvas.height;
  ctx.clearRect(0, 0, W, H);

  const data = [
    { label: "RED", n: VIDEOS.filter(v => v.tier === "RED").length, c: "#ff4d4f" },
    { label: "ORANGE", n: VIDEOS.filter(v => v.tier === "ORANGE").length, c: "#fa8c16" },
    { label: "YELLOW", n: VIDEOS.filter(v => v.tier === "YELLOW").length, c: "#fadb14" },
  ];
  const total = data.reduce((s, d) => s + d.n, 0) || 1;
  const cx = H, cy = H / 2, r = H / 2 - 20;
  let a = -Math.PI / 2;
  data.forEach(d => {
    const ang = (d.n / total) * Math.PI * 2;
    ctx.fillStyle = d.c;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, r, a, a + ang);
    ctx.closePath();
    ctx.fill();
    a += ang;
  });

  // Legend
  ctx.font = "13px sans-serif";
  data.forEach((d, i) => {
    const ly = 20 + i * 24;
    const lx = H * 2 + 10;
    ctx.fillStyle = d.c;
    ctx.fillRect(lx, ly - 10, 12, 12);
    ctx.fillStyle = "#e8eaed";
    ctx.fillText(`${d.label}: ${d.n} (${((d.n / total) * 100).toFixed(0)}%)`, lx + 20, ly);
  });
}

/* ------------- Tabs ------------- */

function wireTabs() {
  document.querySelectorAll("nav.tabs button").forEach(b => {
    b.addEventListener("click", () => {
      document.querySelectorAll("nav.tabs button").forEach(x => x.classList.remove("active"));
      document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
      b.classList.add("active");
      document.getElementById("tab-" + b.dataset.tab).classList.add("active");
      if (b.dataset.tab === "stats") renderStats();
    });
  });
}

/* ------------- Init ------------- */

(async function init() {
  wireTabs();
  await loadData();
  renderVideos();
  renderCreators();
  renderStats();

  ["f-platform", "f-language", "f-tier"].forEach(id =>
    document.getElementById(id).addEventListener("change", renderVideos));
  document.getElementById("f-q").addEventListener("input", renderVideos);
  document.getElementById("c-language").addEventListener("change", renderCreators);
  document.getElementById("c-q").addEventListener("input", renderCreators);

  window.addEventListener("resize", () => {
    if (document.getElementById("tab-stats").classList.contains("active")) {
      drawTimeline(); drawTierPie();
    }
  });
})();
