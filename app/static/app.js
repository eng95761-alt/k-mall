"use strict";
const $ = (s, el = document) => el.querySelector(s);
const NUM = new Intl.NumberFormat("ar-IQ");
let timer = null;

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
  $("#login-view").hidden = true;
  $("#app-view").hidden = false;
  $("#whoami").textContent = user.username;
  await refresh();
  clearInterval(timer);
  timer = setInterval(refresh, 30000);
}

function ago(iso) {
  if (!iso) return "لم يُفحص بعد";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "قبل ثوانٍ";
  if (s < 3600) return `قبل ${NUM.format(Math.round(s / 60))} دقيقة`;
  if (s < 86400) return `قبل ${NUM.format(Math.round(s / 3600))} ساعة`;
  return `قبل ${NUM.format(Math.round(s / 86400))} يوم`;
}
const clock = (iso) => iso ? new Date(iso).toLocaleTimeString("ar-IQ", { hour: "2-digit", minute: "2-digit" }) : "—";
const pct = (used, total) => (used != null && total) ? `${NUM.format(Math.round(used * 100 / total))}%` : "—";
const n = (v) => (v == null ? "—" : NUM.format(v));

function renderRouter(r) {
  const el = $("#router-tpl").content.firstElementChild.cloneNode(true);
  $(".r-name", el).textContent = r.name;
  const badge = $(".badge", el);
  if (!r.last_check) { badge.textContent = "بانتظار أول فحص"; badge.className = "badge wait"; }
  else if (r.online) { badge.textContent = "متصل"; badge.className = "badge ok"; }
  else { badge.textContent = "غير متصل"; badge.className = "badge bad"; }

  const L = r.latest || {}, F = r.latest_full || {};
  const sub = [F.board, F.version && `RouterOS ${F.version}`, F.uptime && `يعمل منذ ${F.uptime}`].filter(Boolean);
  $(".r-sub", el).textContent = sub.length ? sub.join(" · ") : (r.note || (r.method === "tcp" ? "مراقبة الاتصال فقط" : ""));

  $(".r-clients", el).textContent = n(L.hotspot_active);
  $(".r-cards", el).textContent = n(L.um_users);
  $(".r-cpu", el).textContent = L.cpu_load == null ? "—" : `${NUM.format(L.cpu_load)}%`;
  $(".r-mem", el).textContent = pct(L.mem_total != null ? L.mem_total - L.mem_free : null, L.mem_total);
  $(".r-hdd", el).textContent = pct(L.hdd_total != null ? L.hdd_total - L.hdd_free : null, L.hdd_total);
  $(".r-lat", el).textContent = L.latency_ms == null ? "—" : `${NUM.format(Math.round(L.latency_ms))} ms`;
  $(".r-foot", el).textContent = `آخر فحص: ${ago(r.last_check)} · آخر اتصال ناجح: ${clock(r.last_seen)}`;
  const err = $(".r-err", el);
  if (r.last_error && !r.online) {
    err.textContent = r.last_error;
  } else if (r.last_error && r.last_error.includes("credentials not configured")) {
    err.textContent = "الاتصال يعمل. لقراءة الكروت والمعالج أضف بيانات دخول الـ API في إعدادات الخدمة.";
    err.className = "muted r-err";
  } else {
    err.textContent = "";
  }
  return el;
}

async function refresh() {
  try {
    const d = await api("/api/overview");
    $("#t-online").textContent = `${NUM.format(d.totals.online)} / ${NUM.format(d.totals.routers)}`;
    $("#t-clients").textContent = NUM.format(d.totals.hotspot_active);
    $("#t-alerts").textContent = NUM.format(d.alerts.length);
    $("#updated").textContent = `آخر تحديث للصفحة: ${clock(d.now)}`;

    const alerts = $("#alerts");
    alerts.replaceChildren(...d.alerts.map((a) => {
      const div = document.createElement("div");
      div.className = `alert ${a.level}`;
      div.textContent = `${a.message} — منذ ${clock(a.opened_at)}`;
      return div;
    }));

    const grid = $("#routers");
    if (!d.routers.length) {
      const p = document.createElement("p");
      p.className = "muted";
      p.textContent = "لا توجد بيانات بعد. أول فحص يحدث خلال دقيقة من تشغيل الخدمة.";
      grid.replaceChildren(p);
    } else {
      grid.replaceChildren(...d.routers.map(renderRouter));
    }
  } catch (e) {
    if (e.message !== "401") $("#updated").textContent = `تعذّر التحديث: ${e.message}`;
  }
}

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
    if (e.message !== "401") $("#login-error").textContent = e.message;
    else $("#login-error").textContent = "اسم المستخدم أو كلمة المرور غير صحيحة";
  }
});

$("#logout").addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" }).catch(() => {});
  showLogin();
});

api("/api/me").then(showApp).catch(() => showLogin());
