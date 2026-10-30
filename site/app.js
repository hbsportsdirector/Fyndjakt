// Fyndjakt-sajten: inloggning, meny och det som delas mellan delarna. Varje del (fynd.js, samling.js …)
// registrerar sig med App.del(...). Allt läses direkt från Supabase efter inloggning.
const App = (() => {
  "use strict";
  // Den publika nyckeln får synas – åtkomsten styrs av databasens regler (RLS). Samma som i config.yaml.
  const KONFIG = {
    url: "https://abwmdhvaxqlpyzgvuedj.supabase.co",
    nyckel: "sb_publishable_R1OuxhyY7HJq68XcEoFnSw_Zl16Gux9",
    vapid: "BHOqwvHBwlipvfyrB5aTdgRynU2jU_R24b2YES3HW6ty8L7MRaUHAz_8nOd6TcF7pgjz-qx4sqhLwUCdkpc0VZM",
  };
  const $ = id => document.getElementById(id);
  const konto = { sb: null, inloggad: false, session: null, uid: null, admin: false, namn: "", profiler: [], fynd: null,
                  reakt: new Map(), anteckningar: [], sokordVal: new Map(), installningar: { smak: "", kanal: "tradera" },
                  samling: [], harRedan: [] };
  const delar = {};          // id → {namn, ikon, montera(el), visa(), mobil?}
  const ordning = [];
  const MOBIL_FLIKAR = ["fynd", "samling", "butik", "prisguide", "mer"];
  const MOBIL_MER = ["stamplar", "kalkyl", "saljplan", "installningar"];
  let aktiv = null;
  const lyssnare = {};

  function del(id, def) { delar[id] = def; ordning.push(id); }
  function pa(h, fn) { (lyssnare[h] = lyssnare[h] || []).push(fn); }
  function sand(h, ...a) { for (const fn of lyssnare[h] || []) { try { fn(...a); } catch (e) { console.error(e); } } }
  const mobil = () => window.innerWidth < 720;

  // ── Små hjälpare ──────────────────────────────────────────────────
  const kr = Logik.kr;
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
  function el(tag, attrs, ...barn) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "class") e.className = v; else if (k.startsWith("on")) e[k] = v;
      else if (k === "html") e.innerHTML = v; else if (v != null) e.setAttribute(k, v);
    }
    for (const b of barn.flat()) if (b != null) e.append(b);
    return e;
  }
  let toastT = null;
  function toast(text) {
    document.querySelectorAll(".toast").forEach(t => t.remove());
    const t = el("div", { class: "toast", role: "status" }, text); document.body.appendChild(t);
    clearTimeout(toastT); toastT = setTimeout(() => t.remove(), 2800);
  }
  function datum(d) { try { return new Date(d).toLocaleDateString("sv-SE", { day: "numeric", month: "short", year: "numeric" }); } catch (e) { return d; } }
  function idag() { return new Date().toISOString().slice(0, 10); }
  function slug(s) { return String(s || "").toLowerCase().replace(/[åä]/g, "a").replace(/ö/g, "o").replace(/ø/g, "o").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60); }
  function nyttId(namn) { return (slug(namn) || "foremal") + "-" + Math.random().toString(36).slice(2, 6); }
  function norm(t) { return (t || "").toLowerCase().normalize("NFD").replace(/[^a-z0-9]/g, ""); }

  // Foto → JPEG högst `max` px på längsta sidan. Returnerar {blob, dataUrl}.
  function skalaNer(fil, max = 1600, kvalitet = 0.85) {
    return new Promise((ok, fel) => {
      const img = new Image();
      img.onload = () => {
        const k = Math.min(1, max / Math.max(img.width, img.height));
        const c = document.createElement("canvas"); c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
        c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
        URL.revokeObjectURL(img.src);
        const dataUrl = c.toDataURL("image/jpeg", kvalitet);
        c.toBlob(blob => ok({ blob, dataUrl, bredd: c.width, hojd: c.height }), "image/jpeg", kvalitet);
      };
      img.onerror = fel; img.src = URL.createObjectURL(fil);
    });
  }
  function dataUrlTillBase64(u) { return String(u || "").replace(/^data:image\/\w+;base64,/, ""); }

  // Edge-funktionen fyndjakt-kann-igen. Kastar ett läsbart fel.
  async function kannIgen(body) {
    const { data, error } = await konto.sb.functions.invoke("fyndjakt-kann-igen", { body });
    if (error || !data || data.fel) {
      let txt = (data && data.fel) || "";
      try { if (!txt && error && error.context) txt = (await error.context.json()).fel; } catch (x) {}
      throw new Error(txt || "Claude svarade inte just nu – försök igen.");
    }
    return data;
  }

  // ── Bilder i bucketen samling: signerade adresser som cachas en timme ──
  const BILD_TID = 3600;
  const bildCache = new Map();  // path → {url, till}
  try { for (const [k, v] of Object.entries(JSON.parse(sessionStorage.getItem("samling-bilder") || "{}"))) bildCache.set(k, v); } catch (e) {}
  function sparaBildCache() { try { sessionStorage.setItem("samling-bilder", JSON.stringify(Object.fromEntries(bildCache))); } catch (e) {} }
  async function bildUrlar(paths) {
    const nu = Date.now();
    const saknas = [...new Set(paths.filter(p => p && !(bildCache.get(p) && bildCache.get(p).till > nu + 60000)))];
    for (let i = 0; i < saknas.length; i += 100) {
      const bit = saknas.slice(i, i + 100);
      const { data, error } = await konto.sb.storage.from("samling").createSignedUrls(bit, BILD_TID);
      if (error) { console.error(error); continue; }
      for (const d of data || []) if (d.signedUrl && !d.error) bildCache.set(d.path || bit[data.indexOf(d)], { url: d.signedUrl, till: nu + BILD_TID * 1000 });
    }
    if (saknas.length) sparaBildCache();
    return Object.fromEntries(paths.map(p => [p, (bildCache.get(p) || {}).url || null]));
  }
  async function bildUrl(path) { return path ? (await bildUrlar([path]))[path] : null; }
  async function laddaUppBild(path, blob) {
    const { error } = await konto.sb.storage.from("samling").upload(path, blob, { contentType: "image/jpeg", upsert: true, cacheControl: "3600" });
    if (error) throw new Error("Kunde inte ladda upp bilden: " + error.message);
    bildCache.delete(path);
    return path;
  }
  async function taBortBild(path) {
    const { error } = await konto.sb.storage.from("samling").remove([path]);
    if (error) throw new Error("Kunde inte ta bort bilden: " + error.message);
    bildCache.delete(path);
  }

  // Databasen lämnar högst 1000 rader per anrop – hämta sida för sida.
  async function hamtaAlla(fraga) {
    const ut = [];
    for (let fran = 0; ; fran += 1000) {
      const { data, error } = await fraga().range(fran, fran + 999);
      if (error) return { data: ut, error };
      ut.push(...(data || []));
      if (!data || data.length < 1000) return { data: ut };
    }
  }

  // ── Paneler (detaljvy, dialoger) ──────────────────────────────────
  function panel(innehall, { mitten } = {}) {
    const bak = el("div", { class: "panel-bak" + (mitten ? " mitten" : "") });
    const p = el("div", { class: "panel" + (mitten ? " mitten" : ""), role: "dialog", "aria-modal": "true" });
    p.append(...[innehall].flat());
    bak.appendChild(p);
    const stang = () => { bak.remove(); document.removeEventListener("keydown", esc_); };
    const esc_ = e => { if (e.key === "Escape") stang(); };
    bak.addEventListener("click", e => { if (e.target === bak) stang(); });
    document.addEventListener("keydown", esc_);
    document.body.appendChild(bak);
    const f = p.querySelector("input,select,textarea,button"); if (f && !mobil()) f.focus();
    return { el: p, stang };
  }
  function lightbox(src) {
    const lb = el("div", { class: "lightbox" }, el("img", { src, alt: "" }), el("button", { class: "knapp st", type: "button" }, "Stäng"));
    lb.onclick = () => lb.remove(); document.body.appendChild(lb);
  }
  function fraga(text, { ok = "OK", avbryt = "Avbryt", falt } = {}) {
    return new Promise(res => {
      const form = el("form", {}, el("h2", {}, text));
      const inputs = {};
      for (const f of falt || []) {
        const i = el("input", { type: f.typ || "text", value: f.varde ?? "", inputmode: f.typ === "number" ? "numeric" : null, placeholder: f.placeholder || "" });
        if (f.val) { const s = el("select", {}, ...f.val.map(([v, t]) => el("option", { value: v }, t))); s.value = f.varde ?? f.val[0][0]; inputs[f.id] = s; form.append(el("label", { class: "rad-etikett", style: "margin-top:10px;display:flex" }, f.etikett, s)); }
        else { inputs[f.id] = i; form.append(el("label", { style: "display:block;margin-top:10px" }, f.etikett, el("div", {}, i))); }
      }
      const rad = el("div", { class: "rad", style: "margin-top:16px" },
        el("button", { class: "knapp primar", type: "submit" }, ok),
        el("button", { class: "knapp", type: "button", onclick: () => { p.stang(); res(null); } }, avbryt));
      form.append(rad);
      form.onsubmit = e => { e.preventDefault(); p.stang(); res(Object.fromEntries(Object.entries(inputs).map(([k, i]) => [k, i.value]))); };
      const p = panel(form, { mitten: true });
    });
  }

  // ── Meny och vyer ─────────────────────────────────────────────────
  function byggMeny() {
    $("meny").replaceChildren(...ordning.filter(id => id !== "mer").map(id => {
      const d = delar[id];
      const b = el("button", { class: "meny-knapp", type: "button", "data-vy": id, onclick: () => visa(id) },
        el("span", { class: "ikon" }, d.ikon), el("span", {}, d.namn), el("span", { class: "n", "data-n": id }));
      return b;
    }));
    $("flikrad").replaceChildren(...MOBIL_FLIKAR.map(id => {
      const d = delar[id] || { ikon: "☰", namn: "Mer" };
      return el("button", { type: "button", "data-vy": id, onclick: () => visa(id) }, el("span", { class: "ikon" }, d.ikon), d.namn);
    }));
    $("mer-lista").replaceChildren(...MOBIL_MER.map(id => el("button", { class: "knapp", type: "button", onclick: () => visa(id) },
      delar[id].ikon + "  " + delar[id].namn)),
      el("button", { class: "knapp", type: "button", onclick: loggaUt }, "🚪  Logga ut"));
  }
  const monterade = new Set();
  function visa(id, { tyst } = {}) {
    if (!delar[id] && id !== "mer") id = mobil() ? "butik" : "fynd";
    aktiv = id;
    document.querySelectorAll(".vy").forEach(s => s.classList.toggle("aktiv", s.dataset.vy === id));
    document.querySelectorAll("[data-vy]").forEach(b => { if (b.tagName === "BUTTON") b.setAttribute("aria-current", b.dataset.vy === id || (b.dataset.vy === "mer" && MOBIL_MER.includes(id)) ? "page" : "false"); });
    if (!tyst) { try { history.replaceState(null, "", "#" + id); localStorage.setItem("fyndjakt-del", id); } catch (e) {} }
    const d = delar[id];
    if (d && konto.inloggad) {
      const sektion = document.querySelector(`.vy[data-vy="${id}"]`);
      if (!monterade.has(id)) { monterade.add(id); d.montera(sektion); }
      if (d.visa) d.visa(sektion);
    }
    window.scrollTo(0, 0);
  }
  function rakna(id, n) { document.querySelectorAll(`[data-n="${id}"]`).forEach(e => e.textContent = n || ""); }
  function startvy() {
    const h = location.hash.slice(1);
    if (h && (delar[h] || h === "mer")) return h;
    let s = null; try { s = localStorage.getItem("fyndjakt-del"); } catch (e) {}
    return s && delar[s] ? s : (mobil() ? "butik" : "fynd");
  }

  // ── Banner: brådskande fynd på alla flikar ────────────────────────
  function uppdateraBanner() {
    const b = $("banner");
    const poster = ((konto.fynd || {}).poster || []);
    const u = Logik.bradskande(poster);
    if (!u.length) { b.hidden = true; return; }
    const p = u[0];
    b.hidden = false;
    b.replaceChildren(el("b", {}, `⏱ ${u.length === 1 ? "1 fynd slutar snart" : u.length + " fynd slutar inom 6 h"}`),
      el("span", {}, `${p.titel} – ${p.pris_text || ""} · ${Logik.tidText(Logik.tidKvar(p))}`));
    b.onclick = () => { visa("fynd"); sand("visa-slutar-snart"); };
  }
  setInterval(() => { if (konto.inloggad) uppdateraBanner(); }, 60000);

  // ── Inloggning ────────────────────────────────────────────────────
  async function loggaUt() { await konto.sb.auth.signOut(); }
  async function laddaKonto() {
    const sb = konto.sb;
    // Samlingen är gemensam för administratörerna (Per och Jill) – databasens regler avgör vad man ser,
    // så den filtreras inte på user_id här.
    const [jag, prof, fynd, r, a, v, inst, saml] = await Promise.all([
      sb.from("fyndjakt_anvandare").select("admin,namn").eq("user_id", konto.uid).maybeSingle(),
      sb.from("fyndjakt_profiler").select("*").order("id"),
      sb.from("fyndjakt_fynd").select("data").maybeSingle(),
      hamtaAlla(() => sb.from("fyndjakt_reaktioner").select("*").order("skapad", { ascending: false }).order("nyckel")),
      sb.from("fyndjakt_anteckningar").select("*").order("skapad", { ascending: false }),
      sb.from("fyndjakt_sokord_val").select("spar,sokord,aktiv"),
      sb.from("samling_installningar").select("smak,kanal").eq("user_id", konto.uid).maybeSingle(),
      hamtaAlla(() => sb.from("samling_foremal").select("*").order("uppdaterad", { ascending: false })),
    ]);
    konto.admin = !!(jag.data && jag.data.admin);
    konto.namn = (jag.data && jag.data.namn) || konto.session.user.email || "";
    konto.profiler = prof.data || [];
    konto.fynd = (fynd.data && fynd.data.data) || null;
    konto.reakt = new Map((r.data || []).map(x => [x.nyckel, x]));
    konto.anteckningar = a.data || [];
    konto.sokordVal = new Map((v.data || []).map(x => [x.spar + "|" + x.sokord, x.aktiv]));
    konto.installningar = inst.data || { smak: "", kanal: "tradera" };
    konto.samling = saml.data || [];
    if (saml.error) console.error(saml.error);
  }
  async function uppdateraKonto(session) {
    konto.session = session; konto.uid = session ? session.user.id : null;
    konto.inloggad = false;
    $("ingen-profil").hidden = true;
    if (session) {
      const { data: medlem } = await konto.sb.rpc("fyndjakt_ga_med");
      if (!medlem) { $("ingen-profil").hidden = false; }
      else {
        try { await laddaKonto(); } catch (e) { console.error(e); toast("Kunde inte läsa allt från databasen."); }
        konto.inloggad = true;
      }
    }
    document.body.classList.toggle("utloggad", !konto.inloggad);
    if (konto.inloggad) {
      $("konto-namn").textContent = konto.namn;
      $("konto-upd").textContent = konto.fynd && konto.fynd.uppdaterad ? "Fynd uppdaterade " + konto.fynd.uppdaterad : "";
      monterade.clear();
      sand("inloggad");
      uppdateraBanner();
      visa(startvy(), { tyst: true });
    }
  }

  function start() {
    if (!window.supabase) {
      $("login-status").textContent = "Kunde inte ladda inloggningen (supabase-js från cdn.jsdelivr.net). Kontrollera nätet och ladda om.";
      return;
    }
    konto.sb = window.supabase.createClient(KONFIG.url, KONFIG.nyckel);
    byggMeny();
    $("b-google").onclick = async () => {
      $("login-status").textContent = "Öppnar Google …";
      const { error } = await konto.sb.auth.signInWithOAuth({ provider: "google",
        options: { redirectTo: location.origin + location.pathname, queryParams: { prompt: "select_account" } } });
      if (error) { console.error(error); $("login-status").textContent = "Google-inloggningen är inte påslagen än – använd e-postlänken så länge."; }
    };
    $("f-login").onsubmit = async e => {
      e.preventDefault();
      $("login-status").textContent = "Skickar …";
      const email = $("login-epost").value.trim();
      // Inbjudna som inte har ett konto än får ett skapat; andra kan bara logga in om de redan finns.
      const { data: inbjuden } = await konto.sb.rpc("fyndjakt_ar_inbjuden", { epost: email });
      const { error } = await konto.sb.auth.signInWithOtp({ email, options: { emailRedirectTo: location.origin + location.pathname, shouldCreateUser: !!inbjuden } });
      $("login-status").textContent = error ? "Det gick inte – är det rätt e-post?" : "Klart! Öppna länken i mejlet på den här enheten.";
    };
    $("b-logga-ut").onclick = loggaUt; $("b-logga-ut-2").onclick = loggaUt;
    $("banner").onkeydown = e => { if (e.key === "Enter") $("banner").click(); };
    window.addEventListener("hashchange", () => { const h = location.hash.slice(1); if (h !== aktiv && konto.inloggad) visa(h, { tyst: true }); });
    konto.sb.auth.onAuthStateChange((_ev, session) => { setTimeout(() => uppdateraKonto(session), 0); });
  }

  return { KONFIG, konto, del, pa, sand, visa, rakna, start, mobil, $, kr, esc, el, toast, datum, idag, slug, nyttId, norm,
           skalaNer, dataUrlTillBase64, kannIgen, bildUrlar, bildUrl, laddaUppBild, taBortBild, hamtaAlla, panel, lightbox, fraga,
           uppdateraBanner, laddaKonto };
})();
