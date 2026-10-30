// Samling: lådor, rutnät, detaljpanel (visa först – redigera bakom en knapp), bilder, sälj-fält och prishistorik.
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
  const spann = (a, b) => a == null && b == null ? "–" : a == null ? "upp till " + kr(b) : b == null || a === b ? kr(a) : Math.round(a).toLocaleString("sv-SE") + "–" + kr(b);

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
    if (p) b.append(el("img", { alt: "", loading: "lazy", "data-path": p })); else b.append(el("div", { class: "ingen" }, "Ingen bild"));
    b.append(el("span", { class: "lada-etikett " + it.lada }, LADNAMN[it.lada] || it.lada));
    k.append(b);
    const kropp = el("div", { class: "kropp" });
    kropp.append(el("div", { class: "namn" }, it.namn));
    kropp.append(el("div", { class: "under" }, under(it) || it.kategori || ""));
    if ((+it.antal || 1) > 1) kropp.append(el("div", { class: "under" }, it.antal + " st"));
    const pris = el("div", { class: "pris" });
    if (it.lada === "salt") pris.append("Såld för ", el("b", {}, kr(it.salt_for)));
    else pris.append(...vardeRad(it));
    kropp.append(pris);
    k.append(kropp);
    k.onclick = () => oppnaDetalj(it.id);
    return k;
  }

  // Ett värde per föremål: auktionsmedianen (omvärderas varje månad), annars Claudes uppskattning, annars den egna.
  const harMarknad = it => it.marknad_min != null || it.marknad_max != null;
  const harEgen = it => it.uppskattat_min != null || it.uppskattat_max != null;
  const manad = d => { try { return new Date(d).toLocaleDateString("sv-SE", { month: "short", year: "numeric" }); } catch (e) { return ""; } };
  function vardeRad(it) {
    if (it.auk_median) return ["Värde ca ", el("b", {}, kr(it.auk_median)), it.pris_uppdaterad ? el("span", { class: "muted" }, " · " + manad(it.pris_uppdaterad)) : ""];
    if (harMarknad(it)) return ["Uppskattat ", el("b", {}, spann(it.marknad_min, it.marknad_max))];
    if (harEgen(it)) return ["Egen värdering ", el("b", {}, spann(it.uppskattat_min, it.uppskattat_max))];
    return ["Inget värde än"];
  }
  // Den egna värderingen ligger långt över marknaden (mer än dubbla värdet)?
  const egenForHog = it => harEgen(it) && it.auk_median && (it.uppskattat_min ?? it.uppskattat_max) > 2 * it.auk_median;

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
    $("s-antal").textContent = rader.length + " föremål" + (st.lada ? " i " + LADNAMN[st.lada] : "");
    const g = $("s-rutnat"); g.replaceChildren(...rader.map(sKort));
    if (!rader.length) {
      const tom = el("div", { class: "tom", style: "grid-column:1/-1" });
      if (!lista().length) tom.append(el("div", { class: "stor" }, "Samlingen är tom"), el("p", {}, "Lägg till ditt första föremål – fota det så föreslår Claude namn, tillverkare och värde."),
        el("div", { class: "rad" }, el("button", { class: "knapp primar", type: "button", onclick: laggTillMeny }, "＋ Lägg till föremål")));
      else if (st.q || st.kategori) tom.append(el("div", { class: "stor" }, "Inget matchar"), el("p", {}, "Prova ett annat ord, eller rensa filtret."),
        el("div", { class: "rad" }, el("button", { class: "knapp", type: "button", onclick: () => { st.q = ""; st.kategori = ""; $("s-q").value = ""; render(); } }, "Rensa sökning")));
      else tom.append(el("div", { class: "stor" }, "Inget i " + LADNAMN[st.lada]), el("p", {}, st.lada === "salj" ? "Öppna ett föremål och tryck Flytta för att lägga det till salu." : st.lada === "salt" ? "När du markerar ett föremål som sålt hamnar det här, med vinst och kanal." : "Flytta föremål hit från detaljvyn, eller lägg till nya."));
      g.append(tom);
    }
    fyllBilder(g);
    App.rakna("samling", lista().length);
    const kat = $("s-kategori");
    const finns = KATEGORIER.filter(k => lista().some(it => it.kategori === k));
    kat.replaceChildren(new Option("Alla kategorier", ""), ...finns.map(k => new Option(k, k)));
    kat.value = finns.includes(st.kategori) ? st.kategori : "";
  }

  // ── Lägg till (ark med tre val) ───────────────────────────────────
  function laggTillMeny() {
    App.sheet("Lägg till föremål", [
      { ikon: "📷", text: "Fota med kameran", under: "Claude föreslår namn, tillverkare och värde", label: true, capture: "environment", primar: true, onchange: e => { const f = [...e.target.files]; if (f.length) nyttForemal(f); } },
      { ikon: "🖼", text: "Välj från galleriet", under: "en eller flera bilder av samma föremål", label: true, multiple: true, onchange: e => { const f = [...e.target.files]; if (f.length) nyttForemal(f); } },
      { ikon: "✎", text: "Skriv in utan bild", under: "bilder kan läggas till senare", onclick: () => nyttForemal([]) },
    ]);
  }
  function merMeny() {
    App.sheet("Samlingen", [
      { ikon: "⬇", text: "Exportera som CSV", under: `${synliga().length} föremål i aktuell vy`, onclick: exportCsv },
      { ikon: "?", text: "Hjälp om Samling", onclick: () => App.hjalp("samling") },
    ]);
  }

  // ── Detaljpanel ───────────────────────────────────────────────────
  const GRUNDFAKTA = [["namn", "Namn", "text", "bred"], ["kategori", "Kategori", "select"], ["tillverkare", "Tillverkare", "text"], ["serie", "Serie", "text"],
    ["antal", "Antal", "number"], ["period", "Period", "text"], ["stampel", "Stämpel", "text"], ["skick", "Skick", "text"]];
  const KOP = [["inkopspris", "Inköpspris (kr)", "number"], ["inkopt", "Inköpt", "date"], ["inkopsstalle", "Inköpsställe", "text"]];
  const VARDE = [["auk_median", "Värde – auktionsmedian (kr)", "number"], ["marknad_min", "Uppskattat lägst (kr)", "number"], ["marknad_max", "Uppskattat högst (kr)", "number"]];
  const MER = [["uppskattat_min", "Egen värdering lägst (kr)", "number"], ["uppskattat_max", "Egen värdering högst (kr)", "number"], ["saker", "Säkerhet, egen värdering", "text"],
    ["marknad_sakerhet", "Säkerhet, uppskattning", "text"], ["jfr", "Underlag", "text", "bred"], ["jfr_url", "Underlag – länk", "text"],
    ["pris_uppdaterad", "Värderat", "date"], ["sokord", "Sökord (används vid omvärderingen)", "text", "bred"]];
  const ANTECKNING = [["anteckning", "Anteckning", "textarea", "bred"]];
  const FALT = [...GRUNDFAKTA, ...KOP, ...VARDE, ...MER, ...ANTECKNING];
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
  const grupp = (titel, it, falten, oppen, small) => {
    const d = el("details", { class: "grupp" }, el("summary", {}, titel, small ? el("small", {}, small) : null), el("div", { class: "falt-grid" }, ...falten.map(f => falt(it, f))));
    if (oppen) d.open = true;
    return d;
  };

  function oppnaDetalj(id, lage = "visa") {
    const it = lista().find(x => x.id === id); if (!it) return;
    const p = App.panel(el("div"));
    const byt = l => { p.el.replaceChildren(l === "redigera" ? redigeraVy(it, p) : visaVy(it, p)); p.el.scrollTop = 0; };
    p.byt = byt;
    byt(lage);
  }

  // Visa-läget: bild, det viktigaste, fyra stora knappar – inga formulär.
  function visaVy(it, p) {
    const v = el("div");
    v.append(el("div", { class: "huvud" }, el("h2", {}, it.namn), el("button", { class: "knapp liten", type: "button", onclick: () => p.stang() }, "Stäng")));
    v.append(el("div", { class: "muted", style: "margin:-8px 0 12px" }, `${LADNAMN[it.lada]} · ${under(it) || ""}${it.kategori ? " · " + it.kategori : ""}`));
    const galleri = el("div", { class: "galleri" }); v.append(galleri); renderGalleri(it, galleri, p);
    const knappar = el("div", { class: "knapprad-stor" },
      el("button", { class: "knapp primar", type: "button", onclick: () => p.byt("redigera") }, "✎ Redigera"),
      el("button", { class: "knapp", type: "button", onclick: () => bildMeny(it, () => p.byt("visa")) }, "📷 Lägg till bild"),
      el("button", { class: "knapp", type: "button", onclick: () => flytta(it, p) }, "📦 Flytta"),
      it.lada !== "salt" ? el("button", { class: "knapp", type: "button", onclick: () => markeraSald(it, p) }, "✓ Såld") : null);
    v.append(knappar);
    const fakta = el("div", { class: "visa-fakta" });
    const f = (b, s, cls) => { if (s == null || s === "" || s === "–") return; fakta.append(el("div", { class: cls || "" }, el("b", {}, b), el("span", { class: cls === "stor" && /Köp|Sål/.test(b) ? "kop" : "" }, s))); };
    if (it.lada === "salt") { f("Såld för", kr(it.salt_for), "stor"); f("Inköpt för", it.inkopspris != null ? kr(it.inkopspris) : null, "stor"); f("Vinst", it.salt_for != null && it.inkopspris != null ? kr(it.salt_for - it.inkopspris) : null, "stor"); f("Såld", [it.salt_datum ? App.datum(it.salt_datum) : "", it.salt_kanal].filter(Boolean).join(" via ")); }
    else {
      f("Värde ca", it.auk_median ? kr(it.auk_median) : null, "stor");
      if (!it.auk_median) f("Uppskattat", harMarknad(it) ? spann(it.marknad_min, it.marknad_max) + (it.marknad_sakerhet ? " (" + it.marknad_sakerhet + ")" : "") : null, "stor");
      f("Inköpt för", it.inkopspris != null ? kr(it.inkopspris) : null, "stor");
      f("Värderat", it.pris_uppdaterad ? App.datum(it.pris_uppdaterad) : "inte omvärderat än");
    }
    f("Inköpt", [it.inkopt ? App.datum(it.inkopt) : "", it.inkopsstalle].filter(Boolean).join(" på "));
    f("Antal", (+it.antal || 1) > 1 ? it.antal + " st" : null); f("Period", it.period); f("Stämpel", it.stampel); f("Skick", it.skick);
    if (harEgen(it)) f("Egen värdering", spann(it.uppskattat_min, it.uppskattat_max) + (it.saker ? " (" + it.saker + ")" : "") + (egenForHog(it) ? " ⚠ långt över marknaden" : ""));
    if (it.jfr) fakta.append(el("div", { style: "grid-column:1/-1" }, el("b", {}, "Underlag"), it.jfr_url ? el("a", { href: it.jfr_url, target: "_blank", rel: "noopener" }, it.jfr) : el("span", {}, it.jfr)));
    v.append(fakta);
    if (it.anteckning) v.append(el("div", { class: "ruta", style: "margin-top:12px;white-space:pre-wrap" }, it.anteckning));
    const saljRuta = el("div"); v.append(saljRuta); renderSalj(it, saljRuta, p);
    const hist = el("div"); v.append(el("h3", {}, "Prishistorik")); v.append(hist); laddaHistorik(it, hist);
    v.append(el("p", { class: "muted", style: "margin-top:16px;font-size:13px" }, `Tillagd ${it.skapad ? App.datum(it.skapad) : "–"} · ändrad ${it.uppdaterad ? App.datum(it.uppdaterad) : "–"}`));
    return v;
  }

  // Redigera-läget: fälten i grupper, de ovanliga hopfällda.
  function redigeraVy(it, p) {
    const form = el("form", { class: "detalj" }); form.noValidate = true;
    form.append(el("div", { class: "huvud" }, el("h2", {}, "Redigera"), el("button", { class: "knapp liten", type: "button", onclick: () => p.byt("visa") }, "Avbryt")));
    const lada = el("select", { name: "lada" }, ...LADOR.map(([v, t]) => el("option", { value: v }, t))); lada.value = it.lada;
    form.append(el("div", { class: "falt-grid" }, el("label", {}, "Låda", lada)));
    form.append(grupp("Grundfakta", it, GRUNDFAKTA, true));
    form.append(grupp("Köp", it, KOP, true, [it.inkopspris != null ? kr(it.inkopspris) : "", it.inkopsstalle].filter(Boolean).join(" · ")));
    form.append(grupp("Värde", it, VARDE, it.lada !== "salt", it.auk_median ? "värde ca " + kr(it.auk_median) : ""));
    if (it.lada === "salj") form.append(grupp("Till salu", it, SALJ, true, "pris, upplagd, steg"));
    if (it.lada === "salt") form.append(grupp("Såld", it, SALT, true));
    form.append(grupp("Mer", it, MER, false, "egen värdering, underlag, sökord"));
    form.append(el("div", { class: "falt-grid", style: "margin-top:10px" }, ...ANTECKNING.map(f => falt(it, f))));
    const status = el("div", { class: "status" });
    form.append(el("div", { class: "rad", style: "margin-top:16px" },
      el("button", { class: "knapp primar", type: "submit" }, "Spara"),
      el("button", { class: "knapp", type: "button", onclick: () => p.byt("visa") }, "Avbryt"),
      el("button", { class: "knapp fara hoger", type: "button", onclick: e => taBort(it, e.target, p) }, "Ta bort")), status);
    form.onsubmit = async e => {
      e.preventDefault(); status.textContent = "Sparar …";
      try {
        const andring = { ...lasFalt(form, FALT), ...lasFalt(form, SALJ), ...lasFalt(form, SALT), lada: lada.value };
        andring.antal = Math.max(1, andring.antal || 1);
        Object.assign(it, await spara(it.id, andring)); render(); toast("Sparat"); p.byt("visa");
      } catch (x) { status.textContent = x.message; }
    };
    return form;
  }

  function renderSalj(it, ruta, p) {
    ruta.replaceChildren();
    if (it.lada !== "salj") return;
    const e = Logik.forvantat(it);
    const plan = Logik.saljplan(e, { upplagd: it.upplagd, steg_satt: it.steg_satt });
    const r = el("div", { class: "ruta", style: "margin-top:14px" });
    r.append(el("div", { class: "etik" }, "Till salu" + (e ? " · förväntat " + kr(e) : "")));
    if (!e) r.append(el("p", { style: "margin:6px 0" }, "Sätt ett utgångspris (Redigera → Till salu) eller ett värde, så räknas säljplanen ut."));
    else r.append(el("p", { style: "margin:6px 0" }, plan.text));
    if (it.upplagd) r.append(el("p", { class: "muted", style: "margin:0 0 6px" }, `Upplagd ${App.datum(it.upplagd)}${it.tradera_lagsta ? " · lägsta pris " + kr(it.tradera_lagsta) : ""}`));
    if (plan.typ === "stege") {
      const steg = el("div", { class: "stege" });
      plan.steg.forEach((pris, i) => {
        const s = el("span", {}, (i === 0 ? "Start " : i === plan.steg.length - 1 ? "Golv " : "") + kr(pris));
        if (plan.lage && i === plan.lage.satt) s.classList.add("nu");
        if (plan.lage && plan.lage.sank != null && i === plan.lage.bor) s.classList.add("sank");
        steg.append(s);
      });
      r.append(steg);
      if (!it.upplagd) {
        const b = el("button", { class: "knapp liten", type: "button", style: "margin-top:8px" }, "Jag har lagt upp den nu");
        b.onclick = async () => { try { Object.assign(it, await spara(it.id, { upplagd: new Date().toISOString(), steg_satt: 0, tradera_pris: it.tradera_pris ?? plan.start })); renderSalj(it, ruta, p); toast("Prisstegen startad"); } catch (x) { toast(x.message); } };
        r.append(b);
      } else if (plan.lage) {
        const l = plan.lage;
        r.append(el("p", { class: "muted", style: "margin:8px 0 0" }, l.sank != null ? `Dag ${l.dagar} – dags att sänka till ${kr(l.sank)}. `
          : l.slut ? "Stegen är slut – auktion med reservationspris, eller paketera. " : `Dag ${l.dagar} – ligger ute på ${kr(l.pris)}${l.nasta != null ? ", nästa sänkning om " + l.nasta + " dagar" : ""}. `));
        if (l.sank != null) {
          const b = el("button", { class: "knapp liten", type: "button" }, "Jag har sänkt till " + kr(l.sank));
          b.onclick = async () => { try { Object.assign(it, await spara(it.id, { steg_satt: l.bor })); renderSalj(it, ruta, p); toast("Steget sparat"); } catch (x) { toast(x.message); } };
          r.append(b);
        }
      }
    }
    if (plan.typ === "auktionshus") r.append(el("p", { class: "muted" }, "Netto via Bukowskis ca " + kr(plan.netto)));
    ruta.append(r);
  }

  async function flytta(it, p) {
    App.sheet("Flytta till låda", LADOR.filter(([v]) => v !== it.lada).map(([v, t]) => ({ ikon: { egen: "🏠", pappas: "👴", oklart: "❓", salj: "🏷", salt: "✓" }[v], text: t,
      onclick: async () => {
        if (v === "salt") return markeraSald(it, p);
        try { Object.assign(it, await spara(it.id, { lada: v })); render(); toast("Flyttad till " + t); p.byt("visa"); } catch (x) { toast(x.message); }
      } })));
  }
  async function markeraSald(it, p) {
    const svar = await App.fraga("Markera som såld", { ok: "Såld!", falt: [
      { id: "salt_for", etikett: "Såld för (kr)", typ: "number", varde: it.tradera_pris ?? Logik.forvantat(it) ?? "" },
      { id: "salt_datum", etikett: "Datum", typ: "date", varde: App.idag() },
      { id: "salt_kanal", etikett: "Kanal", val: KANALER, varde: konto.installningar.kanal || "tradera" }] });
    if (!svar) return;
    try {
      Object.assign(it, await spara(it.id, { lada: "salt", salt_for: svar.salt_for === "" ? null : Math.round(+svar.salt_for), salt_datum: svar.salt_datum || App.idag(), salt_kanal: svar.salt_kanal }));
      render(); toast("Markerad som såld"); p.byt("visa");
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

  function bildMeny(it, klar) {
    App.sheet("Lägg till bild", [
      { ikon: "📷", text: "Fota med kameran", label: true, capture: "environment", primar: true, onchange: e => { const f = [...e.target.files]; if (f.length) laggTillBilder(it, f, klar); } },
      { ikon: "🖼", text: "Välj från galleriet", label: true, multiple: true, onchange: e => { const f = [...e.target.files]; if (f.length) laggTillBilder(it, f, klar); } },
    ]);
  }
  async function renderGalleri(it, galleri, p) {
    galleri.replaceChildren();
    const bilder = it.bilder || [];
    if (!bilder.length) { galleri.append(el("div", { class: "muted" }, "Ingen bild än – tryck Lägg till bild.")); return; }
    const urls = await App.bildUrlar(bilder.map(b => b.path));
    bilder.forEach((b, i) => {
      const d = el("div", { class: "b" + (i === 0 ? " stor" : "") });
      const img = el("img", { src: urls[b.path] || "", alt: "" }); img.onclick = () => App.lightbox(urls[b.path]);
      const x = el("button", { type: "button", "aria-label": "Ta bort bild" }, "✕");
      x.onclick = async () => {
        if (x.dataset.saker !== "1") { x.dataset.saker = "1"; x.textContent = "?"; setTimeout(() => { x.dataset.saker = ""; x.textContent = "✕"; }, 2500); return; }
        try { await App.taBortBild(b.path); Object.assign(it, await spara(it.id, { bilder: bilder.filter(y => y.path !== b.path) })); renderGalleri(it, galleri, p); render(); }
        catch (e) { toast(e.message); }
      };
      d.append(img, x); galleri.append(d);
    });
  }
  // Nya bilder: nedskalade till 1600 px, numrerade efter de som finns.
  async function laggTillBilder(it, filer, klar) {
    let n = Math.max(0, ...(it.bilder || []).map(b => +b.n || 0));
    const nya = [...(it.bilder || [])];
    toast("Laddar upp …");
    for (const f of filer.slice(0, 6)) {
      n += 1;
      try {
        const { blob } = await App.skalaNer(f, 1600);
        const path = `${konto.uid}/${it.id}/${n}.jpg`;
        await App.laddaUppBild(path, blob);
        nya.push({ n, path });
      } catch (e) { toast(e.message); return; }
    }
    try { Object.assign(it, await spara(it.id, { bilder: nya })); toast(filer.length > 1 ? "Bilderna är sparade" : "Bilden är sparad"); klar(); render(); }
    catch (e) { toast(e.message); }
  }

  async function laddaHistorik(it, ruta) {
    const { data } = await konto.sb.from("samling_prishistorik").select("datum,median,lag,hog,antal,kalla").eq("foremal_id", it.id).order("datum");
    const rader = data || [];
    if (!rader.length) { ruta.append(el("div", { class: "muted" }, "Ingen prishistorik än – den fylls på när priser hämtas.")); return; }
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
    return el("div", { class: "spark", html: `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" preserveAspectRatio="none" role="img" aria-label="Värde ${vs[0]} till ${vs[vs.length - 1]} kr">
      <path d="${d} L${xy[xy.length - 1][0].toFixed(1)} ${h} L${xy[0][0].toFixed(1)} ${h} Z" fill="#c9a35b" opacity=".15"/>
      <path d="${d}" fill="none" stroke="#c9a35b" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round"/></svg>` });
  }

  // ── Nytt föremål ──────────────────────────────────────────────────
  async function nyttForemal(filer) {
    const status = el("div", { class: "status" });
    const bilder = el("div", { class: "galleri" });
    const form = el("form", { class: "detalj" }); form.noValidate = true;
    form.append(el("div", { class: "huvud" }, el("h2", {}, "Nytt föremål"), el("button", { class: "knapp liten", type: "button", onclick: () => p.stang() }, "Avbryt")));
    form.append(bilder, status);
    const tom = { lada: "egen", kategori: "Keramik & porslin", antal: 1, tillverkare: "", serie: "", inkopt: App.idag() };
    const lada = el("select", { name: "lada" }, ...LADOR.map(([v, t]) => el("option", { value: v }, t)));
    form.append(el("div", { class: "falt-grid" }, el("label", {}, "Låda", lada)));
    const forslag = el("div", { class: "ruta tips", hidden: true, style: "margin-top:10px" });
    form.append(forslag);
    form.append(grupp("Grundfakta", tom, GRUNDFAKTA, true));
    form.append(grupp("Köp", tom, KOP, true, "pris, datum, ställe"));
    form.append(grupp("Värde", tom, VARDE, false, "fylls i av Claude om du fotat"));
    form.append(el("div", { class: "rad", style: "margin-top:16px" }, el("button", { class: "knapp primar", type: "submit" }, "Spara i samlingen")));
    const p = App.panel(form);
    if (!filer.length) form.elements.namn.focus();

    const skalade = [];
    for (const f of filer.slice(0, 4)) { const s = await App.skalaNer(f, 1600); skalade.push(s); bilder.append(el("div", { class: "b" }, el("img", { src: s.dataUrl, alt: "" }))); }
    if (skalade.length) {
      status.textContent = "Claude tittar på bilden – fyll gärna i låda och pris så länge …";
      try {
        const r = await App.kannIgen({ typ: "butik", bilder: skalade.map(s => App.dataUrlTillBase64(s.dataUrl)), mediatyp: "image/jpeg",
                                       smak: konto.installningar.smak || "", har_redan: harRedanText() });
        const satt = (id, v) => { const e = form.elements[id]; if (e && v != null && v !== "" && !e.value) e.value = v; };
        satt("namn", r.namn); satt("tillverkare", r.tillverkare); satt("serie", r.serie); satt("period", r.period); satt("stampel", r.stampel_last);
        satt("skick", r.skick); satt("antal", r.antal); if (KATEGORIER.includes(r.kategori)) form.elements.kategori.value = r.kategori;
        satt("sokord", r.sokord); satt("marknad_min", r.marknad_min); satt("marknad_max", r.marknad_max);
        form.dataset.sokord = r.sokord || "";
        forslag.hidden = false;
        forslag.replaceChildren(el("b", {}, "Claudes förslag – ändra fritt. "),
          `${r.namn} · ${[r.tillverkare, r.formgivare, r.serie, r.period].filter(Boolean).join(" · ")} · säkerhet ${Math.round(r.sakerhet * 100)} %. `,
          `Marknad ${spann(r.marknad_min, r.marknad_max)}${r.nyproduktion ? " · ⚠ nyproduktion" : ""}${r.varning ? " · " + r.varning : ""}. `,
          r.resonemang || "");
        status.textContent = "";
      } catch (e) { status.textContent = e.message + " Fyll i själv så länge."; }
    }
    form.onsubmit = async e => {
      e.preventDefault();
      const v = { ...lasFalt(form, GRUNDFAKTA), ...lasFalt(form, KOP), ...lasFalt(form, VARDE) };
      if (!v.namn) { status.textContent = "Ge föremålet ett namn."; form.elements.namn.focus(); return; }
      status.textContent = "Sparar …";
      const id = App.nyttId(v.namn);
      const rad = { id, user_id: konto.uid, lada: lada.value, ...v, antal: Math.max(1, v.antal || 1), tillverkare: v.tillverkare || "Okänd",
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
      sek.replaceChildren();
      const h = App.huvud("samling", "Samling", "");
      h.querySelector(".sub").id = "s-antal";
      h.insertBefore(el("span", { class: "rad hoger" },
        el("button", { class: "knapp primar", type: "button", id: "s-ny", onclick: laggTillMeny }, "＋ Lägg till"),
        el("button", { class: "knapp", type: "button", "aria-label": "Mer", onclick: merMeny }, "⋯")), h.querySelector(".hjalp"));
      sek.append(h,
        el("div", { class: "lador", id: "s-lador" }), el("div", { class: "sammanstallning", id: "s-sammanstallning" }),
        el("div", { class: "verktyg" }, el("div", { class: "rad" },
          el("input", { id: "s-q", type: "search", placeholder: "Sök namn, tillverkare, serie …", "aria-label": "Sök i samlingen" }),
          el("select", { id: "s-kategori", "aria-label": "Kategori" }),
          el("select", { id: "s-sort", "aria-label": "Sortera" }, new Option("Senast ändrad", "andrad"), new Option("Namn A–Ö", "namn"), new Option("Mest värt först", "varde"), new Option("Kategori", "kategori")))),
        el("div", { class: "s-rutnat", id: "s-rutnat" }),
        el("button", { class: "fab", type: "button", "aria-label": "Lägg till föremål", onclick: laggTillMeny }, "＋"));
      $("s-q").value = st.q; $("s-sort").value = st.sort;
      $("s-q").oninput = e => { st.q = e.target.value.trim(); render(); };
      $("s-sort").onchange = e => { st.sort = e.target.value; render(); };
      $("s-kategori").onchange = e => { st.kategori = e.target.value; render(); };
      render();
    },
    visa() { if (rot) render(); },
  });
  App.pa("samling-andrad", () => { if (rot && rot.classList.contains("aktiv")) render(); App.rakna("samling", lista().length); });
  App.pa("inloggad", () => App.rakna("samling", lista().length));
  App.oppnaForemal = oppnaDetalj;
})();
