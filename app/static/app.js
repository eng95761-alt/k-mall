"use strict";
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
const NUM = new Intl.NumberFormat("en-US");
let timer = null;
let currentUser = null;
let currentDetailRouter = null;
let lastOverview = null;
let currentBatchId = null;

async function api(path, opts = {}) {
  const res = await fetch(path, {
    credentials: "same-origin",
    ...opts,
    headers: { "Content-Type": "application/json", "X-Kmall": "1", ...(opts.headers || {}) },
  });
  if (res.status === 401) { showLogin(); throw new Error("401"); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "خطأ");
  return data;
}

function showLogin() {
  clearInterval(timer);
  $("#app-view").hidden = true;
  $("#login-view").hidden = false;
}

async function showApp(user) {
  currentUser = user;
  $("#login-view").hidden = true;
  $("#app-view").hidden = false;
  $("#whoami").textContent = `${user.username} (${user.role})`;
  const isOwner = user.role === "owner";
  const canWrite = user.role === "owner" || user.role === "staff";
  $("#form-settings").hidden = !isOwner;
  $("#form-user").hidden = !isOwner;
  $("#users-box").hidden = !isOwner;
  $("#audit-box").hidden = !isOwner;
  $("#form-plan").hidden = !canWrite;
  $("#form-customer").hidden = !canWrite;
  $("#form-sub").hidden = !canWrite;
  $("#form-batch").hidden = !canWrite;
  await refresh();
  clearInterval(timer);
  timer = setInterval(refresh, 30000);
}

function ago(iso) {
  if (!iso) return "لم يُفحص بعد";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "قبل ثوانٍ";
  if (s < 3600) return `قبل ${NUM.format(Math.round(s / 60))} د`;
  if (s < 86400) return `قبل ${NUM.format(Math.round(s / 3600))} س`;
  return `قبل ${NUM.format(Math.round(s / 86400))} ي`;
}
const clock = (iso) => iso ? new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }) : "—";
const dateStr = (iso) => iso ? new Date(iso).toLocaleDateString("en-CA") : "—";
const n = (v) => (v == null ? "—" : NUM.format(v));
const mib = (b) => (b == null ? "?" : `${Math.round(b / (1024 * 1024))}`);

function setMeter(barEl, textEl, usedPct, text) {
  textEl.textContent = text;
  if (usedPct == null) { barEl.style.width = "0%"; barEl.className = "bar-fill"; return; }
  const pct = Math.max(0, Math.min(100, Math.round(usedPct)));
  barEl.style.width = `${pct}%`;
  barEl.className = "bar-fill" + (pct >= 85 ? " bad" : pct >= 65 ? " warn" : "");
}

function buildTable(headers, rows) {
  const wrap = document.createElement("div");
  if (!rows.length) {
    const p = document.createElement("p");
    p.className = "muted";
    p.textContent = "لا توجد بيانات بعد.";
    wrap.appendChild(p);
    return wrap;
  }
  const tbl = document.createElement("table");
  const thead = document.createElement("thead");
  const trh = document.createElement("tr");
  headers.forEach((h) => { const th = document.createElement("th"); th.textContent = h; trh.appendChild(th); });
  thead.appendChild(trh);
  tbl.appendChild(thead);
  const tbody = document.createElement("tbody");
  rows.forEach((r) => {
    const tr = document.createElement("tr");
    r.forEach((cell) => {
      const td = document.createElement("td");
      if (cell instanceof Node) td.appendChild(cell);
      else td.textContent = cell == null ? "—" : String(cell);
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  tbl.appendChild(tbody);
  wrap.appendChild(tbl);
  return wrap;
}

function renderSvgChart(container, values, unit) {
  container.replaceChildren();
  const clean = values.filter((v) => v != null);
  if (clean.length < 2) {
    const p = document.createElement("p");
    p.className = "muted";
    p.textContent = "تجميع القراءات جارٍ...";
    container.appendChild(p);
    return;
  }
  const w = 280, h = 95, pad = 6;
  const min = Math.min(...clean), max = Math.max(...clean);
  const span = max === min ? 1 : max - min;
  const coords = clean.map((v, i) => {
    const x = pad + (i * (w - pad * 2)) / (clean.length - 1);
    const y = h - pad - ((v - min) * (h - pad * 2)) / span;
    return [x.toFixed(1), y.toFixed(1)];
  });
  const pts = coords.map((c) => c.join(",")).join(" ");
  const areaPts = `${coords[0][0]},${h - pad} ${pts} ${coords[coords.length - 1][0]},${h - pad}`;

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  svg.setAttribute("class", "chart-svg");
  const area = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
  area.setAttribute("class", "chart-area");
  area.setAttribute("points", areaPts);
  const poly = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  poly.setAttribute("class", "chart-line");
  poly.setAttribute("points", pts);
  svg.appendChild(area);
  svg.appendChild(poly);
  container.appendChild(svg);

  const meta = document.createElement("p");
  meta.className = "muted";
  meta.textContent = `الأدنى: ${NUM.format(Math.round(min))}${unit} · الأعلى: ${NUM.format(Math.round(max))}${unit} · الأخير: ${NUM.format(Math.round(clean[clean.length - 1]))}${unit}`;
  container.appendChild(meta);
}

function renderRouter(r) {
  const el = $("#router-tpl").content.firstElementChild.cloneNode(true);
  $(".r-name", el).textContent = r.name;
  const badge = $(".badge", el);
  const dot = $(".status-dot", el);
  if (!r.last_check) { badge.textContent = "بانتظار الفحص"; badge.className = "badge wait"; }
  else if (r.online) { badge.textContent = "متصل"; badge.className = "badge ok"; dot.classList.add("ok"); }
  else { badge.textContent = "غير متصل"; badge.className = "badge bad"; dot.classList.add("bad"); }

  const L = r.latest || {}, F = r.latest_full || {};
  const sub = [F.board, F.version && `v${F.version}`, F.uptime && `منذ ${F.uptime}`, r.vlan_id && `VLAN ${r.vlan_id}`].filter(Boolean);
  $(".r-sub", el).textContent = sub.length ? sub.join(" · ") : (r.note || "");

  const cpuVal = L.cpu_load;
  setMeter($(".m-cpu", el), $(".m-cpu-t", el), cpuVal, cpuVal == null ? "—" : `${NUM.format(cpuVal)}%`);
  const memPct = (L.mem_free != null && L.mem_total) ? ((L.mem_total - L.mem_free) * 100 / L.mem_total) : null;
  setMeter($(".m-mem", el), $(".m-mem-t", el), memPct, memPct == null ? "—" : `${Math.round(memPct)}% (${mib(L.mem_free)}M)`);
  const hddPct = (L.hdd_free != null && L.hdd_total) ? ((L.hdd_total - L.hdd_free) * 100 / L.hdd_total) : null;
  setMeter($(".m-hdd", el), $(".m-hdd-t", el), hddPct, hddPct == null ? "—" : `${Math.round(hddPct)}% (${mib(L.hdd_free)}M)`);

  $(".r-clients", el).textContent = n(L.hotspot_active ?? F.hotspot_active);
  const umU = L.um_users ?? F.um_users;
  const umS = L.um_sessions ?? F.um_sessions;
  $(".r-cards", el).textContent = umU != null ? (umS != null ? `${n(umU)} / ${n(umS)}` : n(umU)) : "—";
  $(".r-lat", el).textContent = L.latency_ms == null ? "—" : `${NUM.format(Math.round(L.latency_ms))} ms`;
  $(".r-mode", el).textContent = r.method.toUpperCase();
  $(".r-foot", el).textContent = `آخر فحص: ${ago(r.last_check)} · ${clock(r.last_seen)}`;
  $(".r-detail-btn", el).addEventListener("click", () => openRouterDetail(r));

  const err = $(".r-err", el);
  if (r.last_error && !r.online) {
    err.className = "error r-err";
    err.textContent = r.last_error.includes("timed out")
      ? `انتهت المهلة للاتصال بـ ${r.host}:${r.port} — تأكد من عنوان PPPoE.`
      : r.last_error;
  } else if (r.method === "umweb" && r.online) {
    err.textContent = r.last_error || "قراءة حية عبر User Manager Web (:800)";
    err.className = "muted r-err";
  } else {
    err.className = "error r-err";
    err.textContent = r.last_error || "";
  }
  return el;
}

async function openRouterDetail(r) {
  currentDetailRouter = r;
  $("#router-detail").hidden = false;
  $("#rd-title").textContent = r.name;
  $("#rd-sub").textContent = `${r.host}:${r.port} (${r.method.toUpperCase()})` + (r.vlan_id ? ` · VLAN ${r.vlan_id}` : "");
  await loadRouterDetail();
}

async function loadRouterDetail() {
  if (!currentDetailRouter) return;
  const hours = $("#rd-hours").value;
  const [hist, snap] = await Promise.all([
    api(`/api/routers/${currentDetailRouter.id}/history?hours=${hours}`),
    api(`/api/routers/${currentDetailRouter.id}/snapshot`),
  ]);
  renderSvgChart($("#chart-cpu"), hist.map((x) => x.cpu_load), "%");
  renderSvgChart($("#chart-clients"), hist.map((x) => x.hotspot_active), "");
  renderSvgChart($("#chart-lat"), hist.map((x) => x.latency_ms), " ms");

  $("#rd-ifaces").replaceChildren(
    buildTable(["الاسم", "النوع", "الحالة", "RX (MiB)", "TX (MiB)"],
      (snap.interfaces || []).map((i) => [
        i.name, i.type, i.running === "true" ? "نشط" : "متوقف",
        mib(Number(i["rx-byte"] || 0)), mib(Number(i["tx-byte"] || 0)),
      ]))
  );
  $("#rd-hs").replaceChildren(
    buildTable(["المستخدم", "IP", "MAC", "المدة"],
      (snap.hotspot_active || []).slice(0, 50).map((h) => [h.user, h.address, h["mac-address"], h.uptime]))
  );
  const netRows = (snap.addresses || []).map((a) => ["IP", a.address, a.interface, a.disabled === "true" ? "معطل" : "مفعّل"])
    .concat((snap.vlans || []).map((v) => ["VLAN", v["vlan-id"], `${v.name} ← ${v.interface}`, v.running === "true" ? "نشط" : "متوقف"]));
  $("#rd-net").replaceChildren(buildTable(["النوع", "القيمة", "الواجهة", "الحالة"], netRows));
}

function renderTopology(routers) {
  $("#topo-branches").replaceChildren(...routers.map((r) => {
    const div = document.createElement("div");
    div.className = "topo-router";
    const t = document.createElement("strong"); t.textContent = r.name;
    const s1 = document.createElement("span"); s1.textContent = `${r.host} (${r.method.toUpperCase()})`;
    const s2 = document.createElement("span"); s2.className = "muted"; s2.textContent = `${r.vlan_id ? "VLAN " + r.vlan_id : "—"} · ${r.subnet || "—"}`;
    const b = document.createElement("span"); b.className = r.online ? "badge ok" : "badge bad"; b.textContent = r.online ? "متصل" : "مفصول";
    div.append(t, s1, s2, b);
    return div;
  }));
  const rows = routers.map((r) => [
    r.name, r.host, r.vlan_id ? `VLAN ${r.vlan_id}` : "—", r.subnet || "—",
    r.method.toUpperCase(), r.online ? "متصل" : "غير متصل", r.note || "—",
  ]);
  $("#vlan-table").replaceChildren(
    buildTable(["الراوتر", "العنوان", "VLAN", "الشبكة", "المراقبة", "الحالة", "ملاحظات"], rows)
  );
}

let lastCleanupPreview = null;

async function updateVoucherRouterHint() {
  const rid = $("#v-router").value;
  const r = (lastOverview?.routers || []).find((x) => x.id === rid);
  const hint = $("#batch-cap-hint");
  if (!r) { hint.textContent = "—"; return; }
  hint.textContent = r.can_write_vouchers ? `يدعم الدفع (${r.um.toUpperCase()})` : "عرض حقيقي من الويب / طباعة محلية";
  hint.className = r.can_write_vouchers ? "badge ok" : "badge wait";
  const snap = await api(`/api/routers/${rid}/snapshot`).catch(() => ({ um_profiles: [] }));
  const profs = snap.um_profiles || [];
  const dl = $("#v-profile-list");
  dl.replaceChildren(...profs.map((p) => {
    const o = document.createElement("option"); o.value = p.name; return o;
  }));
  $("#um-profiles-table").replaceChildren(
    buildTable(["اسم الباقة", "الصلاحية (Validity)", "السعر", "التفاصيل", "اختيار"],
      profs.map((p) => {
        const btn = document.createElement("button");
        btn.className = "ghost small"; btn.type = "button"; btn.textContent = "استخدام";
        btn.addEventListener("click", () => { $("#v-profile").value = p.name; });
        return [p.name, p.validity || "—", p.price || "—", p["starts-when"] || p["starts-at"] || p["name-for-users"] || "—", btn];
      }))
  );
}

async function loadCleanupPreview() {
  const rid = $("#v-router").value;
  if (!rid) return;
  $("#cln-summary").textContent = "جاري فحص المنتهية والسشنات...";
  const d = await api(`/api/cleanup/${rid}/preview?min_age_days=180`);
  lastCleanupPreview = d;
  const dbTxt = (d.db_info || []).map((x) => `${x.address}: ${x.interface}`).join(" · ");
  $("#cln-summary").textContent =
    `${d.router_name} — إجمالي الكروت المزامنة: ${NUM.format(d.total_cached_users)} | المنتهية: ${NUM.format(d.expired_count)} | إجمالي السشنات: ${n(d.total_sessions)}` +
    (dbTxt ? ` | (${dbTxt})` : "");

  const isOwner = currentUser && currentUser.role === "owner";
  const hasItems = d.expired_users.length > 0 || d.old_closed_sessions.length > 0;
  $("#cln-approval").hidden = !(isOwner && hasItems);
  $("#cln-chk").checked = false;
  $("#cln-rm-users").hidden = !(d.can_auto_clean && d.expired_users.length > 0);
  $("#cln-rm-sess").hidden = !(d.can_auto_clean && d.old_closed_sessions.length > 0);
  $("#cln-note").textContent = d.can_auto_clean
    ? (d.allow_router_writes
        ? "الحذف الآلي مفعّل: يتحقق النظام أولاً من عدم اتصال أي مشترك قبل الحذف، ويحذف حتى 100 سجل بالدفعة."
        : "الحماية مفعّلة (ALLOW_ROUTER_WRITES=false): للعرض والمراجعة فقط حالياً.")
    : "هذا الراوتر يعمل بواجهة User Manager Web (:800) ولا يملك API؛ استخدم هذه القائمة الموثقة للمراجعة الآمنة قبل التنظيف اليدوي من الويب.";

  $("#cln-users-table").replaceChildren(
    buildTable(["الاسم", "الباقة", "الانتهاء", "آخر ظهور"],
      d.expired_users.slice(0, 50).map((u) => [u.username, u.profile || "—", u.end_time || u.till_time || "—", u.last_seen || "—"]))
  );
  $("#cln-sess-table").replaceChildren(
    buildTable(["ID", "المستخدم", "من", "إلى"],
      d.old_closed_sessions.slice(0, 50).map((s) => [s.id, s.user, s.from_time, s.till_time]))
  );
}

async function loadVouchersAndCards() {
  await updateVoucherRouterHint();
  const st = $("#cards-status").value;
  const [bData, cData] = await Promise.all([
    api("/api/vouchers/batches"),
    api(`/api/cards?router_id=${encodeURIComponent($("#cards-router").value)}&q=${encodeURIComponent($("#cards-q").value)}&status=${encodeURIComponent(st)}`),
  ]);
  $("#batches-table").replaceChildren(
    buildTable(["الكود", "الراوتر", "الباقة", "العدد", "السعر", "الحالة", "عرض"],
      bData.batches.map((b) => {
        const btn = document.createElement("button");
        btn.className = "ghost small";
        btn.type = "button";
        btn.textContent = "فتح";
        btn.addEventListener("click", () => openBatchPreview(b.id));
        return [b.batch_code, b.router_id, b.profile_name, b.count, NUM.format(b.price_iqd), b.status, btn];
      }))
  );
  $("#cards-meta").textContent = `إجمالي الكروت المطابقة: ${NUM.format(cData.count)}`;
  $("#cards-table").replaceChildren(
    buildTable(["الراوتر", "اسم الكرت", "الباقة", "الحالة", "البداية", "الانتهاء", "الاستهلاك"],
      cData.items.map((c) => [
        c.router_name, c.username, c.profile || "—",
        c.expired ? "منتهي" : (c.disabled ? "معطّل" : "فعّال"),
        c.start_time || "—", c.end_time || c.till_time || "—", c.uptime_used || c.last_seen || "—",
      ]))
  );
}

async function openBatchPreview(batchId) {
  currentBatchId = batchId;
  const d = await api(`/api/vouchers/batches/${batchId}`);
  const b = d.batch;
  $("#batch-preview").hidden = false;
  $("#bp-title").textContent = `دفعة ${b.batch_code} (${b.count} كرت)`;
  $("#bp-meta").textContent = `الراوتر: ${b.router_id} · الباقة: ${b.profile_name} · الحالة: ${b.status}`;
  $("#bp-csv").href = `/api/reports/batch/${b.id}.csv`;
  $("#bp-proposal").textContent = d.proposal.summary;
  $("#bp-cmd").textContent = d.proposal.commands;
  $("#bp-rollback").textContent = `التراجع: ${d.proposal.rollback}`;
  const isOwner = currentUser && currentUser.role === "owner";
  const allPushed = d.cards.every((c) => c.pushed_to_router);
  $("#bp-push-controls").hidden = !(isOwner && d.proposal.can_push && !allPushed);
  $("#bp-approve-chk").checked = false;
  $("#bp-push-msg").textContent = !d.proposal.can_push
    ? "هذا الراوتر لا يدعم الدفع الآلي عبر API (قراءة/طباعة محلية فقط)."
    : (!d.proposal.allow_router_writes ? "ملاحظة: الكتابة التلقائية مقفلة حالياً (ALLOW_ROUTER_WRITES=false)." : "");

  $("#bp-cards-grid").replaceChildren(...d.cards.map((c) => {
    const card = document.createElement("div"); card.className = "v-card";
    const head = document.createElement("div"); head.className = "v-card-head";
    const s1 = document.createElement("span"); s1.textContent = "شبكة مجمع كربلاء";
    const s2 = document.createElement("span"); s2.textContent = c.profile_name;
    head.append(s1, s2);
    const creds = document.createElement("div"); creds.className = "v-creds";
    const u = document.createElement("strong"); u.textContent = c.username;
    const p = document.createElement("span"); p.textContent = `PASS: ${c.password}`;
    creds.append(u, p);
    const foot = document.createElement("div"); foot.className = "v-card-foot";
    const pr = document.createElement("span"); pr.textContent = `${NUM.format(c.price_iqd)} د.ع`;
    const st = document.createElement("span"); st.textContent = c.pushed_to_router ? "مفعّل بالراوتر" : "مسودة";
    foot.append(pr, st);
    card.append(head, creds, foot);
    return card;
  }));
}

async function loadSales() {
  const [plans, custs, subs] = await Promise.all([api("/api/plans"), api("/api/customers"), api("/api/subscriptions")]);
  $("#sub-cust").replaceChildren(...custs.map((c) => {
    const o = document.createElement("option"); o.value = c.id; o.textContent = `${c.full_name} (${c.shop_unit || c.phone || "-"})`; return o;
  }));
  $("#sub-plan").replaceChildren(...plans.map((p) => {
    const o = document.createElement("option"); o.value = p.id; o.textContent = `${p.name} (${NUM.format(p.price_iqd)} د.ع)`; return o;
  }));
  $("#subs-table").replaceChildren(
    buildTable(["#", "الزبون", "الباقة", "الراوتر", "الكرت", "الانتهاء", "السعر", "المدفوع", "المتبقي", "الحالة", "إجراء"],
      subs.map((s) => {
        const btn = document.createElement("button");
        btn.className = "ghost small";
        btn.type = "button";
        btn.textContent = "تسديد";
        btn.disabled = s.balance_iqd <= 0;
        btn.addEventListener("click", async () => {
          const amt = prompt(`أدخل مبلغ الدفعة بالدينار العراقي (المتبقي ${s.balance_iqd}):`, String(s.balance_iqd));
          if (!amt) return;
          await api(`/api/subscriptions/${s.id}/payments`, { method: "POST", body: JSON.stringify({ amount_iqd: Number(amt) }) });
          await Promise.all([loadSales(), refresh()]);
        });
        return [s.id, s.customer_name, s.plan_name, s.router_id || "—", s.voucher_code || "—",
                dateStr(s.expires_at), NUM.format(s.price_iqd), NUM.format(s.paid_iqd), NUM.format(s.balance_iqd), s.status, btn];
      }))
  );
}

async function loadChangesAndAlerts() {
  const [ch, al] = await Promise.all([api("/api/changes"), api("/api/alerts")]);
  $("#changes-table").replaceChildren(
    buildTable(["OP ID", "الوقت", "الراوتر", "المنفذ", "الإجراء", "النتيجة", "التفاصيل"],
      ch.map((c) => [c.op_id, clock(c.ts), c.router_id, c.operator, c.action, c.result, c.detail]))
  );
  $("#alerts-history").replaceChildren(
    buildTable(["الراوتر", "النوع", "المستوى", "الرسالة", "الفتح", "الإغلاق"],
      al.map((a) => [a.router_id, a.kind, a.level, a.message, clock(a.opened_at), a.closed_at ? clock(a.closed_at) : "مفتوح"]))
  );
}

async function loadAdmin() {
  const st = await api("/api/settings");
  const f = $("#form-settings");
  f.cpu_warn.value = st.cpu_warn;
  f.storage_warn_pct.value = st.storage_warn_pct;
  f.offline_after_fails.value = st.offline_after_fails;

  if (currentUser && currentUser.role === "owner") {
    const [users, audits] = await Promise.all([api("/api/users"), api("/api/audit")]);
    $("#users-table").replaceChildren(
      buildTable(["#", "المستخدم", "الدور", "الحالة", "تغيير"],
        users.map((u) => {
          const btn = document.createElement("button");
          btn.className = "ghost small";
          btn.type = "button";
          btn.textContent = u.active ? "تعطيل" : "تفعيل";
          btn.addEventListener("click", async () => {
            await api(`/api/users/${u.id}`, { method: "PATCH", body: JSON.stringify({ active: !u.active }) });
            loadAdmin();
          });
          return [u.id, u.username, u.role, u.active ? "مفعّل" : "معطّل", btn];
        }))
    );
    $("#audit-table").replaceChildren(
      buildTable(["الوقت", "المستخدم", "الإجراء", "التفاصيل", "IP"],
        audits.map((a) => [clock(a.ts), a.username || "—", a.action, a.detail || "—", a.ip || "—"]))
    );
  }
}

async function refresh() {
  try {
    const d = await api("/api/overview");
    lastOverview = d;
    const wm = $("#write-mode-pill");
    wm.textContent = d.allow_router_writes ? "دفع الكروت مفعّل (بموافقة)" : "وضع القراءة فقط";
    wm.className = d.allow_router_writes ? "badge ok" : "badge wait";

    $("#t-online").textContent = `${NUM.format(d.totals.online)} / ${NUM.format(d.totals.routers)}`;
    $("#t-clients").textContent = NUM.format(d.totals.hotspot_active);
    $("#t-cards").textContent = NUM.format(d.totals.um_users || 0);
    $("#t-alerts").textContent = NUM.format(d.alerts.length);
    $("#t-sales").textContent = NUM.format(d.totals.sales_today_iqd || 0);
    $("#t-debt").textContent = NUM.format(d.totals.outstanding_iqd || 0);
    $("#updated").textContent = `آخر تحديث: ${clock(d.now)}`;

    $("#alerts").replaceChildren(...d.alerts.map((a) => {
      const div = document.createElement("div");
      div.className = `alert ${a.level}`;
      div.textContent = `${a.message} — منذ ${clock(a.opened_at)}`;
      return div;
    }));

    const grid = $("#routers");
    grid.replaceChildren(...(d.routers.length ? d.routers.map(renderRouter) : [Object.assign(document.createElement("p"), { className: "muted", textContent: "لا توجد راوترات." })]));

    const opts = d.routers.map((r) => new Option(r.name, r.id));
    const prevCardR = $("#cards-router").value;
    const prevVR = $("#v-router").value;
    $("#cards-router").replaceChildren(new Option("كل الراوترات", ""), ...opts.map((o) => o.cloneNode(true)));
    $("#cards-router").value = prevCardR;
    $("#sub-router").replaceChildren(new Option("غير محدد", ""), ...opts.map((o) => o.cloneNode(true)));
    $("#v-router").replaceChildren(...opts.map((o) => o.cloneNode(true)));
    if (prevVR) $("#v-router").value = prevVR;

    renderTopology(d.routers);
    if (currentDetailRouter) {
      const updated = d.routers.find((x) => x.id === currentDetailRouter.id);
      if (updated) currentDetailRouter = updated;
      await loadRouterDetail();
    }
  } catch (e) {
    if (e.message !== "401") $("#updated").textContent = `تعذّر التحديث: ${e.message}`;
  }
}

$$(".tab").forEach((btn) => {
  btn.addEventListener("click", async () => {
    $$(".tab").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const target = btn.dataset.tab;
    $$(".panel").forEach((p) => { p.hidden = p.id !== `tab-${target}`; });
    if (target === "vouchers") { await loadVouchersAndCards(); await loadCleanupPreview().catch(() => {}); }
    if (target === "sales") await loadSales();
    if (target === "changes") await loadChangesAndAlerts();
    if (target === "admin") await loadAdmin();
  });
});

$("#rd-close").addEventListener("click", () => { currentDetailRouter = null; $("#router-detail").hidden = true; });
$("#rd-hours").addEventListener("change", loadRouterDetail);
$("#v-router").addEventListener("change", async () => { await updateVoucherRouterHint(); await loadCleanupPreview().catch(() => {}); });
$("#cards-search").addEventListener("click", loadVouchersAndCards);
$("#cards-router").addEventListener("change", loadVouchersAndCards);
$("#cards-status").addEventListener("change", loadVouchersAndCards);
$("#um-sync-now").addEventListener("click", async () => {
  const rid = $("#v-router").value;
  if (!rid) return;
  $("#um-sync-msg").textContent = "جاري المزامنة الكاملة من الراوتر بحذر...";
  try {
    const res = await api(`/api/routers/${rid}/sync`, { method: "POST" });
    $("#um-sync-msg").textContent = res.ok
      ? `تمت المزامنة: ${res.profiles} باقة · ${res.users} كرت.`
      : `تعذرت المزامنة: ${res.error || "خطأ"}`;
    await Promise.all([loadVouchersAndCards(), loadCleanupPreview()]);
  } catch (e) { $("#um-sync-msg").textContent = e.message; }
});
$("#cln-scan").addEventListener("click", loadCleanupPreview);

async function runCleanup(action, ids) {
  if (!$("#cln-chk").checked) { $("#cln-msg").textContent = "يرجى تفعيل خانة الموافقة الصريحة أولاً."; return; }
  const rid = $("#v-router").value;
  try {
    const res = await api(`/api/cleanup/${rid}/execute`, {
      method: "POST",
      body: JSON.stringify({ approved: true, confirm_router_id: rid, action, ids }),
    });
    $("#cln-msg").textContent = `تم التنفيذ (${res.op_id}): حذف ${res.removed} سجل بأمان.`;
    await Promise.all([loadVouchersAndCards(), loadCleanupPreview()]);
  } catch (e) { $("#cln-msg").textContent = e.message; }
}
$("#cln-rm-users").addEventListener("click", () => {
  const ids = (lastCleanupPreview?.expired_users || []).map((u) => u.id).filter(Boolean).slice(0, 100);
  if (ids.length) runCleanup("remove_expired_users", ids);
});
$("#cln-rm-sess").addEventListener("click", () => {
  const ids = (lastCleanupPreview?.old_closed_sessions || []).map((s) => s.id).filter(Boolean).slice(0, 100);
  if (ids.length) runCleanup("remove_old_sessions", ids);
});
$("#bp-print").addEventListener("click", () => window.print());
$("#bp-close").addEventListener("click", () => { $("#batch-preview").hidden = true; });
$("#print-page").addEventListener("click", () => window.print());
$("#refresh-now").addEventListener("click", refresh);

$("#form-batch").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = new FormData(ev.target);
  try {
    const res = await api("/api/vouchers/batches", {
      method: "POST",
      body: JSON.stringify({
        router_id: f.get("router_id"),
        profile_name: f.get("profile_name"),
        count: Number(f.get("count")),
        price_iqd: Number(f.get("price_iqd")),
        prefix: f.get("prefix"),
        user_len: Number(f.get("user_len")),
        pass_len: Number(f.get("pass_len")),
        digits_only: Boolean(f.get("digits_only")),
        notes: f.get("notes") || "",
      }),
    });
    $("#msg-batch").textContent = `تم إنشاء الدفعة ${res.batch_code}`;
    await Promise.all([loadVouchersAndCards(), openBatchPreview(res.id)]);
  } catch (e) { $("#msg-batch").textContent = e.message; }
});

$("#bp-push-btn").addEventListener("click", async () => {
  if (!currentBatchId) return;
  if (!$("#bp-approve-chk").checked) {
    $("#bp-push-msg").textContent = "يرجى تفعيل خانة الموافقة الصريحة أولاً.";
    return;
  }
  const b = await api(`/api/vouchers/batches/${currentBatchId}`);
  try {
    const res = await api(`/api/vouchers/batches/${currentBatchId}/push`, {
      method: "POST",
      body: JSON.stringify({ approved: true, confirm_router_id: b.batch.router_id }),
    });
    $("#bp-push-msg").textContent = `تم التنفيذ بنجاح (${res.op_id}): دفع ${res.pushed} كرت.`;
    await Promise.all([loadVouchersAndCards(), openBatchPreview(currentBatchId)]);
  } catch (e) { $("#bp-push-msg").textContent = e.message; }
});

$("#form-plan").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = new FormData(ev.target);
  try {
    await api("/api/plans", { method: "POST", body: JSON.stringify({
      name: f.get("name"), speed_label: f.get("speed_label"),
      duration_days: Number(f.get("duration_days")), price_iqd: Number(f.get("price_iqd")),
    }) });
    ev.target.reset(); $("#msg-plan").textContent = "تم حفظ الباقة";
    loadSales();
  } catch (e) { $("#msg-plan").textContent = e.message; }
});

$("#form-customer").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = new FormData(ev.target);
  try {
    await api("/api/customers", { method: "POST", body: JSON.stringify({
      full_name: f.get("full_name"), phone: f.get("phone"), shop_unit: f.get("shop_unit"), notes: f.get("notes"),
    }) });
    ev.target.reset(); $("#msg-cust").textContent = "تمت إضافة الزبون";
    loadSales();
  } catch (e) { $("#msg-cust").textContent = e.message; }
});

$("#form-sub").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = new FormData(ev.target);
  try {
    await api("/api/subscriptions", { method: "POST", body: JSON.stringify({
      customer_id: Number(f.get("customer_id")), plan_id: Number(f.get("plan_id")),
      router_id: f.get("router_id"), voucher_code: f.get("voucher_code"), paid_iqd: Number(f.get("paid_iqd")),
    }) });
    ev.target.reset(); $("#msg-sub").textContent = "تم تسجيل الاشتراك";
    await Promise.all([loadSales(), refresh()]);
  } catch (e) { $("#msg-sub").textContent = e.message; }
});

$("#form-settings").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = new FormData(ev.target);
  try {
    await api("/api/settings", { method: "PUT", body: JSON.stringify({
      cpu_warn: Number(f.get("cpu_warn")), storage_warn_pct: Number(f.get("storage_warn_pct")),
      offline_after_fails: Number(f.get("offline_after_fails")),
    }) });
    $("#msg-settings").textContent = "تم حفظ العتبات";
  } catch (e) { $("#msg-settings").textContent = e.message; }
});

$("#form-user").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = new FormData(ev.target);
  try {
    await api("/api/users", { method: "POST", body: JSON.stringify({
      username: f.get("username"), password: f.get("password"), role: f.get("role"),
    }) });
    ev.target.reset(); $("#msg-user").textContent = "تم إنشاء الحساب";
    loadAdmin();
  } catch (e) { $("#msg-user").textContent = e.message; }
});

$("#login-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = new FormData(ev.target);
  $("#login-error").textContent = "";
  try {
    const user = await api("/api/login", { method: "POST",
      body: JSON.stringify({ username: f.get("username"), password: f.get("password") }) });
    ev.target.reset();
    showApp(user);
  } catch (e) {
    $("#login-error").textContent = e.message !== "401" ? e.message : "اسم المستخدم أو كلمة المرور غير صحيحة";
  }
});

$("#logout").addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" }).catch(() => {});
  showLogin();
});

api("/api/me").then(showApp).catch(() => showLogin());
