/* Epic 무료 에셋 라이브러리
   데이터: data/assets.json (에셋 목록), data/effects/index.json (이펙트 색인),
           data/effects/<에셋 id>.json (에셋별 이펙트 상세) */
(() => {
  "use strict";

  const COLORS = { char:"--c-char", env:"--c-env", anim:"--c-anim", sample:"--c-sample", limited:"--c-limited", comm:"--c-comm" };
  const SPEEDS = [0.1, 0.25, 0.5, 1, 1.5, 2];
  const $ = s => document.querySelector(s);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const store = {
    get(k, d){ try { const v = localStorage.getItem("efl-" + k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } },
    set(k, v){ try { localStorage.setItem("efl-" + k, JSON.stringify(v)); } catch(e){} }
  };

  let DATA = null, FXINDEX = { assets:{} };
  const fxCache = new Map();
  const state = { id:null, q:"", scope:"all", cat:store.get("cat","all"), speed:store.get("speed",1) };
  let visible = [];

  const fabUrl = f => f.startsWith("http") ? f : "https://www.fab.com/listings/" + f;
  const now = new Date();
  const expired = a => a.until && new Date(a.until) < now;
  const byId = id => DATA.assets.find(a => a.id === id);
  const fxInfo = id => FXINDEX.assets[id];
  function initials(name){
    const n = name.replace(/^Paragon:\s*/, "");
    const w = n.split(/[\s.&-]+/).filter(Boolean);
    return (w.length > 1 ? w[0][0] + w[1][0] : n.slice(0, 2)).toUpperCase();
  }
  const shortName = a => a.name.replace(/^Paragon:\s*/, "");
  const kst = iso => new Date(iso).toLocaleString("ko-KR", { month:"long", day:"numeric", hour:"2-digit", minute:"2-digit", timeZone:"Asia/Seoul" }) + " (KST)";
  const mediaUrl = v => !v ? "" : /^https?:/.test(v) ? v : (DATA.mediaBase || "") + v;

  /* ---------- 불러오기 ---------- */
  async function getJSON(url){ const r = await fetch(url, { cache:"no-cache" }); if (!r.ok) throw new Error(url + " " + r.status); return r.json(); }
  async function loadEffects(id){
    if (!fxInfo(id)) return [];
    if (fxCache.has(id)) return fxCache.get(id);
    try { const d = await getJSON("data/effects/" + encodeURIComponent(id) + ".json"); fxCache.set(id, d.effects || []); }
    catch(e){ fxCache.set(id, []); }
    return fxCache.get(id);
  }

  /* ---------- 검색 ---------- */
  function assetMatches(a, q){
    const hay = [a.name, a.desc, a.by, DATA.cats[a.cat]?.label, ...(a.types || [])].join(" ").toLowerCase();
    return hay.includes(q);
  }
  function fxNameMatches(id, q){
    const info = fxInfo(id);
    return !!(info && (info.names || []).some(n => n.toLowerCase().includes(q)));
  }
  const fxMatches = (f, q) => [f.name, f.desc, f.path].join(" ").toLowerCase().includes(q);

  function computeVisible(){
    const q = state.q.trim().toLowerCase();
    visible = DATA.assets.filter(a => {
      if (state.cat !== "all" && a.cat !== state.cat) return false;
      if (state.scope === "all" && q) return assetMatches(a, q) || fxNameMatches(a.id, q);
      return true;
    });
  }

  /* ---------- 왼쪽 목록 ---------- */
  function renderList(){
    const list = $("#list");
    list.innerHTML = visible.map((a, i) => {
      const info = fxInfo(a.id);
      const live = a.cat === "limited" && !expired(a);
      return `<li><button class="item" data-id="${esc(a.id)}" aria-current="${a.id === state.id}" style="--k:var(${COLORS[a.cat]})">
        <span class="tile" aria-hidden="true">${esc(initials(a.name))}</span>
        <span class="item-text"><span class="item-name">${i + 1}. ${esc(shortName(a))}</span>
        <span class="item-sub">${esc(DATA.cats[a.cat]?.short || "")}${a.official === false ? " · 비공식" : ""}</span></span>
        ${info ? `<span class="n" title="이펙트 수">${info.count}</span>` : ""}
        ${live ? `<span class="dot" title="기간 한정 무료 진행 중"></span>` : ""}
      </button></li>`;
    }).join("") || `<li class="meta" style="padding:10px 4px">검색 결과가 없습니다.</li>`;
    const pos = visible.findIndex(a => a.id === state.id);
    $("#count").textContent = `${pos >= 0 ? pos + 1 : "-"} / ${visible.length}`;
    list.querySelector('[aria-current="true"]')?.scrollIntoView({ block:"nearest" });
  }

  /* ---------- 가운데 상세 ---------- */
  function renderHero(a){
    const k = `var(${COLORS[a.cat]})`;
    const badges = [];
    if (a.official === false) badges.push(`<span class="badge">비공식</span>`);
    if (a.until) badges.push(expired(a) ? `<span class="badge off">무료 종료</span>` : `<span class="badge">무료 ~ ${esc(kst(a.until))}</span>`);
    const info = fxInfo(a.id);
    $("#hero").style.setProperty("--k", k);
    $("#hero").innerHTML = `
      <div class="tile" aria-hidden="true">${esc(initials(a.name))}</div>
      <div class="hero-body">
        <div class="kind">${esc(DATA.cats[a.cat]?.label || "")}</div>
        <h1>${esc(shortName(a))}</h1>
        <div class="row">
          <a class="btn primary" href="${esc(fabUrl(a.fab))}" target="_blank" rel="noopener">Fab 페이지 보기 ↗</a>
          ${a.docs ? `<a class="btn" href="${esc(a.docs)}" target="_blank" rel="noopener">공식 문서 ↗</a>` : ""}
          ${badges.join("")}
        </div>
        <div class="meta">${esc(a.name)}${info ? ` · 이펙트 ${info.count}개` : ""}${a.by ? ` · 제작 ${esc(a.by)}` : ""}</div>
        ${a.desc ? `<p class="hero-desc">${esc(a.desc)}</p>` : ""}
        <div class="row">${(a.types || []).map(t => `<span class="tag">${esc(t)}</span>`).join("")}</div>
      </div>`;
    $("#topTitle").textContent = shortName(a);
    document.title = shortName(a) + " · Epic 무료 에셋 라이브러리";
  }

  function fxCard(f, i, ownerId){
    const src = mediaUrl(f.video);
    const owner = ownerId ? byId(ownerId) : null;
    return `<article class="fx">
      <div class="fx-media">
        ${src ? `<video muted loop playsinline preload="none" data-src="${esc(src)}"${f.poster ? ` poster="${esc(mediaUrl(f.poster))}"` : ""}></video>`
              : `<span class="no-video">${f.visible === false ? "화면에 보이는 입자 없음" : "영상 준비 중"}</span>`}
        <span class="fx-num">${i + 1}</span>
      </div>
      <div class="fx-body">
        <h3 class="fx-name">${esc(f.name)}</h3>
        ${f.loop != null ? `<span class="loop ${f.loop ? "y" : "n"}">Loop: ${f.loop ? "Yes" : "No"}</span>` : ""}
        <div class="fx-path">${esc(f.path || "")}${f.duration ? ` · ${esc(f.duration)}s` : ""}</div>
        ${f.desc ? `<p class="fx-desc">${esc(f.desc)}</p>` : ""}
        ${owner ? `<button class="fx-owner" data-id="${esc(owner.id)}">${esc(shortName(owner))} →</button>` : ""}
      </div>
    </article>`;
  }

  let renderToken = 0;
  async function renderEffects(a){
    const token = ++renderToken;
    const q = state.q.trim().toLowerCase();
    const grid = $("#effects");

    // 전체 범위 검색: 여러 에셋의 이펙트를 모아서 보여줌
    if (state.scope === "all" && q) {
      const owners = visible.filter(x => fxNameMatches(x.id, q));
      if (owners.length) {
        $("#effectsTitle").textContent = "EFFECTS · 검색 결과";
        const sets = await Promise.all(owners.map(async o => (await loadEffects(o.id)).filter(f => fxMatches(f, q)).map(f => [f, o.id])));
        if (token !== renderToken) return;
        const all = sets.flat();
        $("#effectsMeta").textContent = `${owners.length}개 항목 · ${all.length}개`;
        grid.innerHTML = all.map(([f, id], i) => fxCard(f, i, id)).join("");
        wireVideos();
        return;
      }
    }

    $("#effectsTitle").textContent = "EFFECTS";
    const info = fxInfo(a.id);
    if (!info) {
      $("#effectsMeta").textContent = "";
      grid.innerHTML = emptyState(a);
      return;
    }
    grid.innerHTML = `<p class="meta">이펙트 불러오는 중…</p>`;
    let list = await loadEffects(a.id);
    if (token !== renderToken) return;
    if (q && state.scope === "cur") list = list.filter(f => fxMatches(f, q));
    $("#effectsMeta").textContent = q && state.scope === "cur" ? `${list.length} / ${info.count}개` : `${info.count}개`;
    grid.innerHTML = list.length ? groupedCards(list)
      : `<div class="empty"><strong>검색어와 맞는 이펙트가 없습니다.</strong>검색어를 지우거나 범위를 '전체'로 바꿔 보세요.</div>`;
    wireVideos();
  }

  // 경로 기준 묶음 제목: 'Greystone/Abilities/ClearAPath' → 'Abilities / ClearAPath'
  function groupedCards(list){
    let html = "", last = null;
    list.forEach((f, i) => {
      const g = (f.path || "").split("/").slice(1).join(" / ") || "기타";
      if (g !== last) {
        const n = list.filter(x => ((x.path || "").split("/").slice(1).join(" / ") || "기타") === g).length;
        html += `<h3 class="fx-group">${esc(g)} <span>${n}</span></h3>`;
        last = g;
      }
      html += fxCard(f, i);
    });
    return html;
  }

  function emptyState(a){
    if (a.cat === "char" || a.id === "paragon-agora-monolith") {
      return `<div class="empty"><strong>이펙트 데이터를 준비하고 있습니다.</strong>
        이 팩의 파티클 이펙트 목록과 미리보기 영상은 언리얼 에디터에서 추출한 뒤 추가됩니다. 그 전까지는 Fab 페이지에서 구성을 확인해 주세요.
        <ol><li>언리얼 에디터에서 이펙트 이름·경로·루프 여부 추출</li><li>이펙트별 미리보기 영상 녹화</li><li>이 화면에 자동 표시</li></ol></div>`;
    }
    return `<div class="empty"><strong>이 항목은 이펙트 목록을 제공하지 않습니다.</strong>구성과 사용 조건은 Fab 페이지${a.docs ? "와 공식 문서" : ""}에서 확인해 주세요.</div>`;
  }

  /* ---------- 영상 재생 ---------- */
  let io = null;
  function wireVideos(){
    io?.disconnect();
    const vids = document.querySelectorAll("#effects video");
    if (!vids.length) return;
    io = new IntersectionObserver(entries => entries.forEach(e => {
      const v = e.target;
      if (e.isIntersecting) {
        if (!v.src) v.src = v.dataset.src;
        v.playbackRate = state.speed;
        v.play().catch(() => {});
      } else v.pause();
    }), { rootMargin:"120px" });
    vids.forEach(v => {
      v.addEventListener("loadedmetadata", () => { v.playbackRate = state.speed; });
      io.observe(v);
    });
  }
  function setSpeed(s){
    state.speed = Math.round(Math.min(2, Math.max(0.1, s)) * 100) / 100;
    store.set("speed", state.speed);
    $("#speedNow").textContent = state.speed + "x";
    $("#speedRange").value = state.speed;
    document.querySelectorAll("#speedBtns button").forEach(b => b.setAttribute("aria-pressed", String(+b.dataset.s === state.speed)));
    document.querySelectorAll("#effects video").forEach(v => { v.playbackRate = state.speed; });
  }

  /* ---------- 공지·하단 ---------- */
  function renderNotice(){
    const live = DATA.assets.filter(a => a.cat === "limited" && !expired(a));
    if (!live.length) { $("#notice").innerHTML = ""; return; }
    const until = live.map(a => a.until).sort()[0];
    $("#notice").innerHTML = `<div class="notice"><strong>기간 한정 무료 ${live.length}종 진행 중</strong>
      <span class="meta">${esc(kst(until))}까지</span>
      <a href="#" data-cat="limited">목록 보기</a></div>`;
  }
  function renderFoot(){
    $("#foot").innerHTML = `
      <h3>바로가기</h3>
      <div class="row">${(DATA.links || []).map(l => `<a class="btn" href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.label)} ↗</a>`).join("")}</div>
      <h3>갱신 기록 · 마지막 갱신 ${esc(DATA.updated)}</h3>
      <ul class="log">${(DATA.log || []).slice().reverse().map(l => `<li><time>${esc(l.date)}</time><span>${esc(l.text)}</span></li>`).join("")}</ul>
      <h3>이용 메모</h3>
      <p>Paragon 팩은 언리얼 엔진 프로젝트에서 자유롭게 쓸 수 있지만, 'PARAGON' 상표를 게임 이름이나 홍보에 쓰는 것은 허용되지 않습니다.</p>
      <p>기간 한정 무료 에셋은 무료 기간이 끝나면 다시 유료로 돌아갈 수 있으니, 기간 안에 Fab 라이브러리에 추가해 두세요.</p>
      <p>이 사이트는 에셋 파일을 직접 배포하지 않습니다. 모든 항목은 Fab 원본 페이지로 연결됩니다.</p>`;
  }

  /* ---------- 화면 갱신 ---------- */
  function select(id, push = true){
    const a = byId(id) || visible[0] || DATA.assets[0];
    if (!a) return;
    state.id = a.id;
    if (push && location.hash.slice(1) !== a.id) history.replaceState(null, "", "#" + a.id);
    renderList(); renderHero(a); renderEffects(a);
    $("#main").scrollTop = 0;
    closeSide();
  }
  function refresh(){
    computeVisible();
    if (!visible.some(a => a.id === state.id) && visible.length) state.id = visible[0].id;
    const a = byId(state.id);
    renderList();
    if (a) { renderHero(a); renderEffects(a); }
  }
  function step(d){
    if (!visible.length) return;
    const i = visible.findIndex(a => a.id === state.id);
    select(visible[(i + d + visible.length) % visible.length].id);
  }
  const openSide = () => $("#side").classList.add("open");
  const closeSide = () => $("#side").classList.remove("open");

  function buildControls(){
    const counts = {};
    DATA.assets.forEach(a => counts[a.cat] = (counts[a.cat] || 0) + 1);
    $("#cat").innerHTML = `<option value="all">전체 분류 (${DATA.assets.length})</option>` +
      Object.entries(DATA.cats).filter(([k]) => counts[k]).map(([k, c]) => `<option value="${k}">${esc(c.label)} (${counts[k]})</option>`).join("");
    if (state.cat !== "all" && !counts[state.cat]) state.cat = "all";
    $("#cat").value = state.cat;
    $("#speedBtns").innerHTML = SPEEDS.map(s => `<button data-s="${s}" aria-pressed="false">${s}x</button>`).join("");
  }

  function bind(){
    let t;
    $("#q").addEventListener("input", e => { clearTimeout(t); t = setTimeout(() => { state.q = e.target.value; refresh(); }, 120); });
    $("#scopeAll").addEventListener("click", () => setScope("all"));
    $("#scopeCur").addEventListener("click", () => setScope("cur"));
    $("#cat").addEventListener("change", e => { state.cat = e.target.value; store.set("cat", state.cat); refresh(); });
    $("#prev").addEventListener("click", () => step(-1));
    $("#next").addEventListener("click", () => step(1));
    $("#openSide").addEventListener("click", openSide);
    $("#closeSide").addEventListener("click", closeSide);
    $("#speedRange").addEventListener("input", e => setSpeed(+e.target.value));
    document.addEventListener("click", e => {
      const it = e.target.closest("[data-id]"); if (it) { select(it.dataset.id); return; }
      const sb = e.target.closest("[data-s]"); if (sb) { setSpeed(+sb.dataset.s); return; }
      const c = e.target.closest("[data-cat]");
      if (c) { e.preventDefault(); state.cat = c.dataset.cat; $("#cat").value = state.cat; store.set("cat", state.cat); refresh(); select(visible[0]?.id); }
    });
    document.addEventListener("keydown", e => {
      if (e.target.matches("input, select, textarea")) return;
      if (e.key === "ArrowLeft") step(-1);
      if (e.key === "ArrowRight") step(1);
      if (e.key === "/") { e.preventDefault(); $("#q").focus(); }
    });
    window.addEventListener("hashchange", () => { const id = location.hash.slice(1); if (id && id !== state.id) select(id, false); });
  }
  function setScope(s){
    state.scope = s;
    $("#scopeAll").setAttribute("aria-pressed", String(s === "all"));
    $("#scopeCur").setAttribute("aria-pressed", String(s === "cur"));
    $("#q").placeholder = s === "all" ? "에셋·이펙트 이름, 설명 검색" : "현재 항목의 이펙트 검색";
    refresh();
  }

  /* ---------- 시작 ---------- */
  (async () => {
    try {
      DATA = await getJSON("data/assets.json");
      try { FXINDEX = await getJSON("data/effects/index.json"); } catch(e){ FXINDEX = { assets:{} }; }
    } catch(e) {
      $("#hero").innerHTML = `<div class="empty"><strong>데이터를 불러오지 못했습니다.</strong>페이지를 새로고침해 주세요. 파일을 직접 열었다면 웹 주소로 접속해야 합니다.</div>`;
      return;
    }
    buildControls(); bind(); setSpeed(state.speed); renderNotice(); renderFoot();
    computeVisible();
    select(location.hash.slice(1) || visible[0]?.id, true);
  })();
})();
