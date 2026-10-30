// Samling: lådor, rutnät, detaljpanel med redigering, bilder, sälj-fält och prishistorik.
(() => {
  "use strict";
  const { konto, el, kr, toast, $ } = App;
  const LADOR = [["egen", "Egen samling"], ["pappas", "Pappas"], ["oklart", "Oklart"], ["salj", "Till salu"], ["salt", "Sålt"]];
  const LADNAMN = Object.fromEntries(LADOR);
  const KATEGORIER = ["Keramik & porslin", "Glas", "Konst", "Möbler", "Belysning", "Skulptur", "Böcker", "Övrigt"];
  const KANALER = [["tradera", "Tradera"], ["blocket", "Blocket"], ["bukowskis", "Bukowskis"], ["auktionsverket", "Auktionsverket"], ["catawiki", "Catawiki"], ["loppis", "Loppis"], ["annat", "Annat"]];
  const st = { lada: "", q: "", sort: "andrad", kategori: "" };
  try { Object.assign(st, JSON.parse(localStorage.getItem("samling-vy") || "{}")); } catch (e) {}
  let rot;
  const lista = () => konto.samling;
  const under = it => [it.tillverkare && it.tillverkare !== "Okänd" ? it.tillverkare : "", it.serie || ""].filter(Boolean).join(" · ");
  const forstaBild = it => ((it.bilder || [])[0] || {}).path || null;

  function synliga() {
    const q = App.norm(st.q);
    return lista().filter(it => (!st.lada || it.lada === st.lada) && (!st.kategori || it.kategori === st.kategori)
      && (!q || App.norm([it.namn, it.tillverkare, it.serie, it.sokord, it.anteckning].join(" ")).includes(q)))
      .sort({
        namn: (a, b) => (a.namn || "").localeCompare(b.namn || "", "sv"),
        varde: (a, b) => (Logik.varde(b) || 0) - (Logik.varde(a) || 0),
        andrad: (a, b) => String(b.uppdaterad || "").localeCompare(String(a.uppdaterad || "")),
        kategori: (a, b) => (a.kategori || "").localeCompare(b.kategori || "", "sv") || (a.namn || "").localeCompare(b.namn || "", "sv"),
      }[st.sort]);
  }

  // ── Lådor och sammanställning ─────────────────────────────────────
  function renderLador() {
    const s = Logik.sammanstallning(lista());
    const alla = lista().length, allaVarde = lista().reduce((n, it) => n + (Logik.varde(it) || 0), 0);
    const knapp = (id, namn, antal, varde, extra) => {
      const b = el("button", { class: "lada" + (id ? "" : " alla"), type: "button", "aria-pressed": String(st.lada === id) },
        el("span", { class: "etik" }, namn), el("div", { class: "siffra" }, String(antal)), el("div", { class: "varde" }, extra || ("värde " + kr(varde))));
      b.onclick = () => { st.lada = id; render(); };
      return b;
    };
    const rad = [knapp("", "Allt", alla, allaVarde)];
    for (const [id, namn] of LADOR) {
      const l = s[id] || { antal: 0, varde: 0, inkopt: 0, salt: 0 };
      rad.push(knapp(id, namn, l.antal, l.varde, id === "salt" ? `sålt för ${kr(l.salt)} · vinst ${kr(l.salt - l.inkopt)}` : null));
    }
    $("s-lador").replaceChildren(...rad);
    const sam = $("s-sammanstallning"); sam.replaceChildren();
    const l = st.lada ? (s[st.lada] || { antal: 0, varde: 0, inkopt: 0, salt: 0 }) : { antal: alla, varde: allaVarde, inkopt: lista().reduce((n, it) => n + (+it.inkopspris || 0), 0), salt: s.salt ? s.salt.salt : 0 };
    const post = (t, v) => sam.append(el("span", {}, t + " ", el("b", {}, v)));
    post("Uppskattat värde", kr(l.varde));
    post("Inköpt för", kr(l.inkopt));
    if (st.lada === "salt") { post("Sålt för", kr(l.salt)); post("Vinst", kr(l.salt - l.inkopt)); }
    else if (!st.lada && s.salt) post("Vinst på sålt", kr(s.salt.vinst));
  }

  // ── Rutnät ────────────────────────────────────────────────────────
  function sKort(it) {
    const k = el("button", { class: "s-kort", type: "button", "data-id": it.id });
    const b = el("div", { class: "bild" });
    const p = forstaBild(it);
    if (p) { const i = el("img", { alt: "", loading: "lazy", "data-path": p }); b.append(i); } else b.append(el("div", { class: "ingen" }, "Ingen bild"));
    b.append(el("span", { class: "lada-etikett " + it.lada }, LADNAMN[it.lada] || it.lada));
    k.append(b);
    const kropp = el("div", { class: "kropp" });
    kropp.append(el("div", { class: "namn" }, it.namn));
    kropp.append(el("div", { class: "under" }, under(it) || it.kategori || ""));
    if ((+it.antal || 1) > 1) kropp.append(el("div", { class: "under" }, it.antal + " st"));
    const pris = el("div", { class: "pris" });
    if (it.lada === "salt") pris.append("Såld för ", el("b", {}, kr(it.salt_for)));
    else {
      if (it.auk_median) pris.append("Auktion ca ", el("b", {}, kr(it.auk_median)));
      if (it.uppskattat_min != null || it.uppskattat_max != null) pris.append(el("div", {}, "Min bedömning " + spann(it.uppskattat_min, it.uppskattat_max)));
      if (!it.auk_median && it.uppskattat_min == null && it.uppskattat_max == null) pris.append(it.marknad_min != null || it.marknad_max != null ? "Marknad " + spann(it.marknad_min, it.marknad_max) : "Inget pris än");
    }
    kropp.append(pris);
    k.append(kropp);
    k.onclick = () => oppnaDetalj(it.id);
    return k;
  }
  const spann = (a, b) => a == null && b == null ? "–" : a == null ? "upp till " + kr(b) : b == null || a === b ? kr(a) : Math.round(a).toLocaleString("sv-SE") + "–" + kr(b);

  async function fyllBilder(sek) {
    const imgs = [...sek.querySelectorAll("img[data-path]")].filter(i => !i.src);
    if (!imgs.length) return;
    const urls = await App.bildUrlar(imgs.map(i => i.dataset.path));
    for (const i of imgs) { const u = urls[i.dataset.path]; if (u) i.src = u; else i.replaceWith(el("div", { class: "ingen" }, "Bild saknas")); }
  }

  function render() {
    try { localStorage.setItem("samling-vy", JSON.stringify(st)); } catch (e) {}
    renderLador();
    const rader = synliga();
    $("s-antal").textContent = rader.length + " föremål";
    const g = $("s-rutnat"); g.replaceChildren(...rader.map(sKort));
    if (!rader.length) g.append(el("div", { class: "tom", style: "grid-column:1/-1" }, lista().length ? "Inget matchar." : "Samlingen är tom – lägg till ditt första föremål."));
    fyllBilder(g);
    App.rakna("samling", lista().length);
    const kat = $("s-kategori");
    const finns = KATEGORIER.filter(k => lista().some(it => it.kategori === k));
    kat.replaceChildren(new Option("Alla kategorier", ""), ...finns.map(k => new Option(k, k)));
    kat.value = finns.includes(st.kategori) ? st.kategori : "";
  }

  // ── Detaljpanel ───────────────────────────────────────────────────
  const FALT = [
    ["namn", "Namn", "text", "bred"], ["kategori", "Kategori", "select"], ["tillverkare", "Tillverkare", "text"], ["serie", "Serie", "text"],
    ["antal", "Antal", "number"], ["period", "Period", "text"], ["stampel", "Stämpel", "text"], ["skick", "Skick", "text"],
    ["inkopspris", "Inköpspris (kr)", "number"], ["inkopt", "Inköpt", "date"], ["inkopsstalle", "Inköpsställe", "text"],
    ["uppskattat_min", "Min bedömning, lägst (kr)", "number"], ["uppskattat_max", "Min bedömning, högst (kr)", "number"], ["saker", "Hur säker", "text"],
    ["marknad_min", "Marknad lägst (kr)", "number"], ["marknad_max", "Marknad högst (kr)", "number"], ["marknad_sakerhet", "Marknad säkerhet", "text"],
    ["auk_median", "Auktion median (kr)", "number"], ["jfr", "Jämförelse", "text"], ["jfr_url", "Jämförelse-länk", "text"], ["pris_uppdaterad", "Pris uppdaterat", "date"],
    ["sokord", "Sökord", "text", "bred"], ["anteckning", "Anteckning", "textarea", "bred"],
  ];
  const SALJ = [["tradera_pris", "Utgångspris (kr)", "number"], ["tradera_lagsta", "Lägsta pris (kr)", "number"], ["upplagd", "Upplagd", "datetime-local"], ["steg_satt", "Steg satt (0 = första)", "number"]];
  const SALT = [["salt_for", "Såld för (kr)", "number"], ["salt_datum", "Såld datum", "date"], ["salt_kanal", "Kanal", "text"]];

  function falt(it, [id, etikett, typ, bred]) {
    let inp;
    if (typ === "select") { inp = el("select", { name: id }, ...KATEGORIER.map(k => el("option", { value: k }, k))); inp.value = it[id] || KATEGORIER[0]; }
    else if (typ === "textarea") { inp = el("textarea", { name: id, rows: 3 }); inp.value = it[id] || ""; }
    else {
      let v = it[id] ?? "";
      if (typ === "datetime-local" && v) v = new Date(v).toISOString().slice(0, 16);
      inp = el("input", { name: id, type: typ, value: v, inputmode: typ === "number" ? "numeric" : null });
    }
    return el("label", { class: bred || "" }, etikett, inp);
  }
  function lasFalt(form, lista) {
    const ut = {};
    for (const [id, , typ] of lista) {
      const e = form.elements[id]; if (!e) continue;
      let v = e.value.trim();
      if (typ === "number") v = v === "" ? null : Math.round(+v);
      else if (typ === "datetime-local") v = v ? new Date(v).toISOString() : null;
      else if (typ === "date") v = v || null;
      ut[id] = v;
    }
    return ut;
  }
  async function spara(id, andring) {
    andring.uppdaterad = new Date().toISOString();
    const { data, error } = await konto.sb.from("samling_foremal").update(andring).eq("id", id).select().single();
    if (error) throw new Error("Kunde inte spara: " + error.message);
    const i = konto.samling.findIndex(x => x.id === id);
    if (i >= 0) konto.samling[i] = data; else konto.samling.unshift(data);
    App.sand("samling-andrad");
    return data;
  }

  function oppnaDetalj(id) {
    const it = lista().find(x => x.id === id); if (!it) return;
    const form = el("form", { class: "detalj" });
    form.noValidate = true;
    const huvud = el("div", { class: "huvud" }, el("h2", {}, it.namn), el("button", { class: "knapp liten", type: "button", onclick: () => p.stang() }, "Stäng"));
    form.append(huvud);
    form.append(el("div", { class: "muted", style: "margin:-8px 0 12px" }, `${LADNAMN[it.lada]} · ${under(it) || it.kategori || ""}${it.skapad ? " · tillagd " + App.datum(it.skapad) : ""}`));

    // Bilder
    form.append(el("h3", {}, "Bilder"));
    const galleri = el("div", { class: "galleri" });
    form.append(galleri);
    const bildrad = el("div", { class: "rad", style: "margin-top:8px" });
    const kam = el("label", { class: "knapp" }, "📷 Fota");
    const kamIn = el("input", { type: "file", accept: "image/*", capture: "environment", class: "dold" }); kam.append(kamIn);
    const gal = el("label", { class: "knapp" }, "🖼 Galleri");
    const galIn = el("input", { type: "file", accept: "image/*", multiple: "", class: "dold" }); gal.append(galIn);
    bildrad.append(kam, gal);
    form.append(bildrad);
    const bildStatus = el("div", { class: "status" }); form.append(bildStatus);
    kamIn.onchange = galIn.onchange = async e => { const filer = [...e.target.files]; e.target.value = ""; if (filer.length) await laggTillBilder(it, filer, bildStatus, () => renderGalleri(it, galleri)); };
    renderGalleri(it, galleri);

    // Fält
    form.append(el("h3", {}, "Uppgifter"));
    form.append(el("div", { class: "falt-grid" }, ...FALT.map(f => falt(it, f))));

    // Sälj-fält
    const saljRuta = el("div");
    form.append(saljRuta);
    renderSalj(it, saljRuta);

    // Prishistorik
    const hist = el("div"); form.append(el("h3", {}, "Prishistorik")); form.append(hist);
    laddaHistorik(it, hist);

    // Knappar
    const status = el("div", { class: "status" });
    const knappar = el("div", { class: "rad", style: "margin-top:16px" },
      el("button", { class: "knapp primar", type: "submit" }, "Spara"),
      el("button", { class: "knapp", type: "button", onclick: () => flytta(it, p) }, "📦 Flytta till låda"),
      it.lada !== "salt" ? el("button", { class: "knapp", type: "button", onclick: () => markeraSald(it, p) }, "✓ Markera som såld") : null,
      el("button", { class: "knapp fara hoger", type: "button", onclick: e => taBort(it, e.target, p) }, "Ta bort"));
    form.append(knappar, status);
    form.onsubmit = async e => {
      e.preventDefault(); status.textContent = "Sparar …";
      try {
        const andring = { ...lasFalt(form, FALT), ...lasFalt(form, SALJ), ...lasFalt(form, SALT) };
        andring.antal = Math.max(1, andring.antal || 1);
        const ny = await spara(it.id, andring);
        Object.assign(it, ny); status.textContent = "Sparat."; huvud.querySelector("h2").textContent = it.namn; render();
      } catch (x) { status.textContent = x.message; }
    };
    const p = App.panel(form);
  }

  function renderSalj(it, ruta) {
    ruta.replaceChildren();
    if (it.lada === "salt") {
      ruta.append(el("h3", {}, "Såld"), el("div", { class: "falt-grid" }, ...SALT.map(f => falt(it, f))));
      return;
    }
    if (it.lada !== "salj") return;
    ruta.append(el("h3", {}, "Till salu"), el("div", { class: "falt-grid" }, ...SALJ.map(f => falt(it, f))));
    const e = Logik.forvantat(it);
    const plan = Logik.saljplan(e, { upplagd: it.upplagd, steg_satt: it.steg_satt });
    const r = el("div", { class: "ruta", style: "margin-top:10px" });
    r.append(el("div", { class: "etik" }, "Säljplan" + (e ? " · förväntat " + kr(e) : "")));
    r.append(el("p", { style: "margin:6px 0" }, plan.text));
    if (plan.typ === "stege") {
      const steg = el("div", { class: "stege" });
      plan.steg.forEach((pris, i) => {
        const s = el("span", {}, (i === 0 ? "Start " : i === plan.steg.length - 1 ? "Golv " : "") + kr(pris));
        if (plan.lage && i === plan.lage.satt) s.classList.add("nu");
        if (plan.lage && plan.lage.sank != null && i === plan.lage.bor) s.classList.add("sank");
        steg.append(s);
      });
      r.append(steg);
      if (plan.lage) {
        const l = plan.lage;
        r.append(el("p", { class: "muted", style: "margin:8px 0 0" }, l.sank != null ? `Dag ${l.dagar} – dags att sänka till ${kr(l.sank)}. `
          : l.slut ? "Stegen är slut – auktion med reservationspris, eller paketera. " : `Dag ${l.dagar} – ligger ute på ${kr(l.pris)}${l.nasta != null ? ", nästa sänkning om " + l.nasta + " dagar" : ""}. `));
        if (l.sank != null) {
          const b = el("button", { class: "knapp liten", type: "button" }, "Jag har sänkt till " + kr(l.sank));
          b.onclick = async () => { try { Object.assign(it, await spara(it.id, { steg_satt: l.bor, tradera_pris: it.tradera_pris })); renderSalj(it, ruta); toast("Steget sparat"); } catch (x) { toast(x.message); } };
          r.append(b);
        }
      }
    }
    if (plan.typ === "auktionshus") r.append(el("p", { class: "muted" }, "Netto via Bukowskis ca " + kr(plan.netto)));
    ruta.append(r);
  }

  async function flytta(it, p) {
    const svar = await App.fraga("Flytta till låda", { ok: "Flytta", falt: [{ id: "lada", etikett: "Låda", val: LADOR, varde: it.lada }] });
    if (!svar || svar.lada === it.lada) return;
    try { Object.assign(it, await spara(it.id, { lada: svar.lada })); p.stang(); render(); toast("Flyttad till " + LADNAMN[svar.lada]); }
    catch (x) { toast(x.message); }
  }
  async function markeraSald(it, p) {
    const svar = await App.fraga("Markera som såld", { ok: "Såld!", falt: [
      { id: "salt_for", etikett: "Såld för (kr)", typ: "number", varde: it.tradera_pris ?? Logik.forvantat(it) ?? "" },
      { id: "salt_datum", etikett: "Datum", typ: "date", varde: App.idag() },
      { id: "salt_kanal", etikett: "Kanal", val: KANALER, varde: konto.installningar.kanal || "tradera" }] });
    if (!svar) return;
    try {
      Object.assign(it, await spara(it.id, { lada: "salt", salt_for: svar.salt_for === "" ? null : Math.round(+svar.salt_for), salt_datum: svar.salt_datum || App.idag(), salt_kanal: svar.salt_kanal }));
      p.stang(); render(); toast("Markerad som såld");
    } catch (x) { toast(x.message); }
  }
  async function taBort(it, knapp, p) {
    if (knapp.dataset.saker !== "1") { knapp.dataset.saker = "1"; knapp.textContent = "Tryck igen för att ta bort"; return; }
    const { error } = await konto.sb.from("samling_foremal").delete().eq("id", it.id);
    if (error) { toast("Kunde inte ta bort: " + error.message); return; }
    for (const b of it.bilder || []) { try { await App.taBortBild(b.path); } catch (e) {} }
    konto.samling = konto.samling.filter(x => x.id !== it.id); App.sand("samling-andrad");
    p.stang(); render(); toast("Borttagen");
  }

  async function renderGalleri(it, galleri) {
    galleri.replaceChildren();
    const bilder = it.bilder || [];
    if (!bilder.length) { galleri.append(el("div", { class: "muted" }, "Inga bilder än.")); return; }
    const urls = await App.bildUrlar(bilder.map(b => b.path));
    for (const b of bilder) {
      const d = el("div", { class: "b" + (bilder.length === 1 ? " stor" : "") });
      const i = el("img", { src: urls[b.path] || "", alt: "" }); i.onclick = () => App.lightbox(urls[b.path]);
      const x = el("button", { type: "button", "aria-label": "Ta bort bild" }, "✕");
      x.onclick = async () => {
        if (x.dataset.saker !== "1") { x.dataset.saker = "1"; x.textContent = "?"; setTimeout(() => { x.dataset.saker = ""; x.textContent = "✕"; }, 2500); return; }
        try { await App.taBortBild(b.path); Object.assign(it, await spara(it.id, { bilder: bilder.filter(y => y.path !== b.path) })); renderGalleri(it, galleri); render(); }
        catch (e) { toast(e.message); }
      };
      d.append(i, x); galleri.append(d);
    }
  }
  // Nya bilder: nedskalade till 1600 px, numrerade efter de som finns.
  async function laggTillBilder(it, filer, status, klar) {
    let n = Math.max(0, ...(it.bilder || []).map(b => +b.n || 0));
    const nya = [...(it.bilder || [])];
    for (const f of filer.slice(0, 6)) {
      n += 1;
      status.textContent = `Laddar upp bild ${n} …`;
      try {
        const { blob } = await App.skalaNer(f, 1600);
        const path = `${konto.uid}/${it.id}/${n}.jpg`;
        await App.laddaUppBild(path, blob);
        nya.push({ n, path });
      } catch (e) { status.textContent = e.message; return; }
    }
    try { Object.assign(it, await spara(it.id, { bilder: nya })); status.textContent = ""; klar(); render(); }
    catch (e) { status.textContent = e.message; }
  }

  async function laddaHistorik(it, ruta) {
    const { data } = await konto.sb.from("samling_prishistorik").select("datum,median,lag,hog,antal,kalla").eq("foremal_id", it.id).order("datum");
    const rader = data || [];
    if (!rader.length) { ruta.append(el("div", { class: "muted" }, "Ingen prishistorik än.")); return; }
    ruta.append(spark(rader.map(r => ({ d: r.datum, v: r.median })), 600, 60));
    const t = el("table", {}, el("tr", {}, el("th", {}, "Datum"), el("th", {}, "Median"), el("th", {}, "Lägst–högst"), el("th", {}, "Antal"), el("th", {}, "Källa")));
    for (const r of rader.slice(-8).reverse()) t.append(el("tr", {}, el("td", {}, App.datum(r.datum)), el("td", {}, kr(r.median)), el("td", {}, spann(r.lag, r.hog)), el("td", {}, String(r.antal ?? "")), el("td", {}, r.kalla || "")));
    ruta.append(t);
  }
  function spark(pts, w, h) {
    if (pts.length < 2) return el("div", { class: "muted" }, `Ett värde: ${kr(pts[0].v)} (${App.datum(pts[0].d)})`);
    const vs = pts.map(p => p.v), mn = Math.min(...vs), mx = Math.max(...vs), rng = mx - mn || 1;
    const xy = pts.map((p, i) => [4 + i * (w - 8) / (pts.length - 1), h - 4 - (p.v - mn) / rng * (h - 8)]);
    const d = xy.map((c, i) => (i ? "L" : "M") + c[0].toFixed(1) + " " + c[1].toFixed(1)).join(" ");
    const s = el("div", { class: "spark", html: `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" preserveAspectRatio="none" role="img" aria-label="Värde ${vs[0]} till ${vs[vs.length - 1]} kr">
      <path d="${d} L${xy[xy.length - 1][0].toFixed(1)} ${h} L${xy[0][0].toFixed(1)} ${h} Z" fill="#c9a35b" opacity=".15"/>
      <path d="${d}" fill="none" stroke="#c9a35b" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round"/></svg>` });
    return s;
  }

  // ── Nytt föremål ──────────────────────────────────────────────────
  async function nyttForemal(filer) {
    const status = el("div", { class: "status" });
    const bilder = el("div", { class: "galleri" });
    const form = el("form", { class: "detalj" });
    form.noValidate = true;
    form.append(el("div", { class: "huvud" }, el("h2", {}, "Nytt föremål"), el("button", { class: "knapp liten", type: "button", onclick: () => p.stang() }, "Stäng")));
    form.append(bilder, status);
    const tom = { lada: "egen", kategori: "Keramik & porslin", antal: 1, tillverkare: "", serie: "", inkopt: App.idag() };
    const grid = el("div", { class: "falt-grid" }, ...FALT.slice(0, 11).map(f => falt(tom, f)));
    const lada = el("select", { name: "lada" }, ...LADOR.map(([v, t]) => el("option", { value: v }, t)));
    grid.prepend(el("label", {}, "Låda", lada));
    form.append(grid);
    const forslag = el("div", { class: "ruta", hidden: true, style: "margin-top:10px" });
    form.append(forslag);
    form.append(el("div", { class: "rad", style: "margin-top:16px" }, el("button", { class: "knapp primar", type: "submit" }, "Spara i samlingen")));
    const p = App.panel(form);

    // Visa bilderna, fråga Claude och fyll i förslag.
    const skalade = [];
    for (const f of filer.slice(0, 4)) { const s = await App.skalaNer(f, 1600); skalade.push(s); bilder.append(el("div", { class: "b" }, el("img", { src: s.dataUrl, alt: "" }))); }
    if (skalade.length) {
      status.textContent = "Claude tittar på bilden …";
      try {
        const r = await App.kannIgen({ typ: "butik", bilder: skalade.map(s => App.dataUrlTillBase64(s.dataUrl)), mediatyp: "image/jpeg",
                                       smak: konto.installningar.smak || "", har_redan: harRedanText() });
        const satt = (id, v) => { const e = form.elements[id]; if (e && v != null && v !== "" && !e.value) e.value = v; };
        satt("namn", r.namn); satt("tillverkare", r.tillverkare); satt("serie", r.serie); satt("period", r.period); satt("stampel", r.stampel_last);
        satt("skick", r.skick); satt("antal", r.antal); if (KATEGORIER.includes(r.kategori)) form.elements.kategori.value = r.kategori;
        satt("sokord", r.sokord); satt("marknad_min", r.marknad_min); satt("marknad_max", r.marknad_max);
        form.dataset.marknadMin = r.marknad_min ?? ""; form.dataset.marknadMax = r.marknad_max ?? ""; form.dataset.sokord = r.sokord || "";
        forslag.hidden = false;
        forslag.replaceChildren(el("div", { class: "etik" }, "Claudes förslag – ändra fritt"),
          el("p", { style: "margin:6px 0" }, `${r.namn} · ${[r.tillverkare, r.formgivare, r.serie, r.period].filter(Boolean).join(" · ")} · säkerhet ${Math.round(r.sakerhet * 100)} %`),
          el("p", { class: "muted", style: "margin:0" }, `Marknad ${spann(r.marknad_min, r.marknad_max)}${r.nyproduktion ? " · ⚠ nyproduktion" : ""}${r.varning ? " · " + r.varning : ""}`),
          ...(r.resonemang ? [el("p", { class: "muted", style: "margin:6px 0 0" }, r.resonemang)] : []));
        status.textContent = "";
      } catch (e) { status.textContent = e.message; }
    }
    form.onsubmit = async e => {
      e.preventDefault();
      const v = lasFalt(form, FALT.slice(0, 11));
      if (!v.namn) { status.textContent = "Ge föremålet ett namn."; return; }
      status.textContent = "Sparar …";
      const id = App.nyttId(v.namn);
      const rad = { id, user_id: konto.uid, lada: lada.value, ...v, antal: Math.max(1, v.antal || 1), tillverkare: v.tillverkare || "Okänd",
        marknad_min: form.dataset.marknadMin ? +form.dataset.marknadMin : null, marknad_max: form.dataset.marknadMax ? +form.dataset.marknadMax : null,
        sokord: form.dataset.sokord || "", anteckning: "", bilder: [] };
      try {
        const { data, error } = await konto.sb.from("samling_foremal").insert(rad).select().single();
        if (error) throw new Error("Kunde inte spara: " + error.message);
        konto.samling.unshift(data);
        const nya = [];
        for (let i = 0; i < skalade.length; i++) {
          status.textContent = `Laddar upp bild ${i + 1} …`;
          const path = `${konto.uid}/${id}/${i + 1}.jpg`;
          await App.laddaUppBild(path, skalade[i].blob); nya.push({ n: i + 1, path });
        }
        if (nya.length) Object.assign(data, await spara(id, { bilder: nya }));
        App.sand("samling-andrad");
        p.stang(); render(); toast("Sparat i " + LADNAMN[lada.value]);
      } catch (x) { status.textContent = x.message; }
    };
  }
  function harRedanText() {
    return lista().filter(it => it.lada !== "salt").map(it => `${it.id} | ${it.namn} | ${it.tillverkare || ""} | ${it.serie || ""}`).join("\n").slice(0, 12000);
  }

  // ── CSV ───────────────────────────────────────────────────────────
  function exportCsv() {
    const kol = ["id", "lada", "namn", "kategori", "tillverkare", "serie", "antal", "period", "stampel", "skick", "inkopspris", "inkopt", "inkopsstalle",
      "uppskattat_min", "uppskattat_max", "marknad_min", "marknad_max", "auk_median", "tradera_pris", "tradera_lagsta", "upplagd", "steg_satt",
      "salt_for", "salt_datum", "salt_kanal", "sokord", "anteckning", "skapad", "uppdaterad"];
    const c = v => { const s = v == null ? "" : String(v); return /[";\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
    const rader = [kol.join(";"), ...synliga().map(it => kol.map(k => c(it[k])).join(";"))];
    const blob = new Blob(["﻿" + rader.join("\n")], { type: "text/csv;charset=utf-8" });
    const a = el("a", { href: URL.createObjectURL(blob), download: `samling-${st.lada || "allt"}-${App.idag()}.csv` });
    document.body.append(a); a.click(); a.remove();
  }

  App.del("samling", { namn: "Samling", ikon: "🏺",
    montera(sek) {
      rot = sek;
      sek.innerHTML = `
        <div class="vy-huvud"><h2>Samling</h2><span class="sub" id="s-antal"></span>
          <span class="hoger rad"><label class="knapp primar" id="s-ny-kam">📷 Fota nytt<input type="file" accept="image/*" capture="environment" class="dold"></label>
          <label class="knapp" id="s-ny-gal">🖼 Från galleri<input type="file" accept="image/*" multiple class="dold"></label>
          <button class="knapp" type="button" id="s-ny-tom">＋ Utan bild</button>
          <button class="knapp" type="button" id="s-csv">⬇ CSV</button></span></div>
        <div class="lador" id="s-lador"></div>
        <div class="sammanstallning" id="s-sammanstallning"></div>
        <div class="verktyg"><div class="rad">
          <input id="s-q" type="search" placeholder="Sök namn, tillverkare, serie, sökord …" aria-label="Sök i samlingen">
          <select id="s-kategori" aria-label="Kategori"></select>
          <select id="s-sort" aria-label="Sortera"><option value="andrad">Senast ändrad</option><option value="namn">Namn A–Ö</option><option value="varde">Mest värt först</option><option value="kategori">Kategori</option></select>
        </div></div>
        <div class="s-rutnat" id="s-rutnat"></div>`;
      $("s-q").value = st.q; $("s-sort").value = st.sort;
      $("s-q").oninput = e => { st.q = e.target.value.trim(); render(); };
      $("s-sort").onchange = e => { st.sort = e.target.value; render(); };
      $("s-kategori").onchange = e => { st.kategori = e.target.value; render(); };
      $("s-csv").onclick = exportCsv;
      $("s-ny-tom").onclick = () => nyttForemal([]);
      for (const id of ["s-ny-kam", "s-ny-gal"]) $(id).querySelector("input").onchange = e => { const f = [...e.target.files]; e.target.value = ""; if (f.length) nyttForemal(f); };
      render();
    },
    visa() { if (rot) render(); },
  });
  App.pa("samling-andrad", () => { if (rot && rot.classList.contains("aktiv")) render(); App.rakna("samling", lista().length); });
  App.pa("inloggad", () => App.rakna("samling", lista().length));
  App.oppnaForemal = oppnaDetalj;
})();
