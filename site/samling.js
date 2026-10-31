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
      && (!q || App.norm([App.fjNr(it), it.namn, it.tillverkare, it.serie, it.sokord, it.anteckning, it.beskrivning].join(" ")).includes(q)))
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
    kropp.append(el("div", { class: "under" }, ...[it.nummer ? el("span", { class: "fjnr" }, App.fjNr(it)) : null, under(it) || it.kategori || ""].filter(Boolean)));
    if ((+it.antal || 1) > 1) kropp.append(el("div", { class: "under" }, it.antal + " st"));
    const pris = el("div", { class: "pris" });
    if (it.lada === "salt") pris.append("Såld för ", el("b", {}, kr(it.salt_for)));
    else pris.append(...vardeRad(it));
    kropp.append(pris);
    k.append(kropp);
    k.onclick = () => oppnaDetalj(it.id);
    return k;
  }

  // Ett värde per föremål: auktionsmedianen (omvärderas varje månad), annars Claudes uppskattning från Butik.
  // Värden som inte omvärderats märks "ej kontrollerat".
  const harMarknad = it => it.marknad_min != null || it.marknad_max != null;
  const manad = d => { try { return new Date(d).toLocaleDateString("sv-SE", { month: "short", year: "numeric" }); } catch (e) { return ""; } };
  function vardeRad(it) {
    if (it.auk_median) return ["Värde ca ", el("b", {}, kr(it.auk_median)), el("span", { class: "muted" }, " · " + (it.pris_uppdaterad ? manad(it.pris_uppdaterad) : "ej kontrollerat"))];
    if (harMarknad(it)) return ["Uppskattat ", el("b", {}, spann(it.marknad_min, it.marknad_max))];
    return ["Inget värde än"];
  }
  // Varifrån "Värde ca" kommer, och varför ett föremål inte har omvärderats (samma regler som vardering.beslut).
  function vardeKalla(it) {
    if (it.pris_uppdaterad) return "Auctionet " + App.datum(it.pris_uppdaterad);
    const kalla = /Köpt via Fyndjakt/.test(it.anteckning || "") ? "Fyndjakts jämförelse när den köptes"
      : /Bedömd i butiken/.test(it.anteckning || "") ? "butiksbedömningen" : "gamla Loppiskollen";
    return `Äldre värde från ${kalla} – ej kontrollerat. Inte omvärderat: ${ejOmvarderatSkal(it)}.` + (it.jfr ? " Underlaget står nedan." : "");
  }
  function ejOmvarderatSkal(it) {
    if (/orört|lås(t)? värde/i.test(it.anteckning || "")) return "värdet är låst i anteckningen";
    if ((+it.antal || 1) > 1) return `parti om ${it.antal} – jämförs inte automatiskt`;
    if (forslagFor(it)) return "ett förslag väntar på dig";
    const sok = it.sokord ? ` (sökte ”${it.sokord}”)` : "";
    return `för få sålda att jämföra med på Auctionet${sok}` + (it.kategori === "Konst" ? "; konst ändras aldrig automatiskt" : "");
  }

  async function fyllBilder(sek) {
    const imgs = [...sek.querySelectorAll("img[data-path]")].filter(i => !i.src);
    if (!imgs.length) return;
    const urls = await App.bildUrlar(imgs.map(i => i.dataset.path));
    for (const i of imgs) { const u = urls[i.dataset.path]; if (u) i.src = u; else i.replaceWith(el("div", { class: "ingen" }, "Bild saknas")); }
  }

  // ── Värderingsförslag att granska ─────────────────────────────────
  // Omvärderingen lägger här de värden den inte vågar ändra själv. Man väljer "Använd" eller "Behåll mitt".
  const forslagFor = it => konto.forslag.get(it.id);
  function renderForslagRad() {
    const ruta = $("s-forslag"); if (!ruta) return;
    const n = lista().filter(forslagFor).length;
    ruta.replaceChildren(...(n ? [el("div", { class: "ruta tips forslag-rad" },
      el("span", {}, el("b", {}, `${n} ${n === 1 ? "värdering" : "värderingar"} att granska`),
        " – omvärderingen hittade nya priser som den inte ändrade själv."),
      el("button", { class: "knapp primar", type: "button", onclick: granskaLista }, "Granska"))] : []));
  }
  function forslagKort(it, fs, klar) {
    const k = el("div", { class: "forslag-kort" });
    const bild = el("div", { class: "fk-bild" });
    const p = forstaBild(it);
    if (p) App.bildUrl(p).then(u => { if (u) bild.append(el("img", { src: u, alt: "" })); });
    const andring = it.auk_median ? fs.median / it.auk_median : null;
    k.append(bild, el("div", { class: "fk-txt" },
      el("div", { class: "fk-namn" }, it.namn),
      el("div", { class: "fk-varden" },
        el("span", {}, ...(it.auk_median ? ["Nu ", el("b", {}, kr(it.auk_median))] : ["Inget värde nu"])), " → ",
        el("span", { class: andring && andring > 1 ? "upp" : "ner" }, "förslag ", el("b", {}, kr(fs.median))),
        andring ? el("span", { class: "muted" }, ` (${andring >= 1 ? "×" + andring.toFixed(1) : "−" + Math.round((1 - andring) * 100) + " %"})`) : null),
      el("div", { class: "muted fk-skal" }, "Varför inte automatiskt: " + fs.skal + "."),
      el("div", { class: "fk-underlag" }, fs.url ? el("a", { href: fs.url, target: "_blank", rel: "noopener" }, fs.text) : fs.text,
        fs.fras ? el("span", { class: "muted" }, ` Sökte ”${fs.fras}”.`) : null),
      el("div", { class: "rad" },
        el("button", { class: "knapp primar liten", type: "button", onclick: e => svara(it, true, e.currentTarget, klar) }, "Använd " + kr(fs.median)),
        el("button", { class: "knapp liten", type: "button", onclick: e => svara(it, false, e.currentTarget, klar) }, "Behåll " + (it.auk_median ? kr(it.auk_median) : "mitt")),
        el("button", { class: "knapp liten", type: "button", onclick: () => oppnaDetalj(it.id) }, "Öppna"))));
    return k;
  }
  async function svara(it, anvand, knapp, klar) {
    knapp.disabled = true;
    const { data, error } = await konto.sb.rpc("samling_forslag_svara", { p_id: it.id, p_anvand: anvand });
    if (error) { knapp.disabled = false; toast("Kunde inte spara: " + error.message); return; }
    konto.forslag.delete(it.id);
    if (data) { Object.assign(it, data); const i = konto.samling.findIndex(x => x.id === it.id); if (i >= 0) konto.samling[i] = it; }
    toast(anvand ? "Nytt värde: " + kr(it.auk_median) : "Behåller " + (it.auk_median ? kr(it.auk_median) : "värdet"));
    render(); klar();
  }
  function granskaLista() {
    const lista_ = el("div", { class: "forslag-lista" });
    const p = App.panel([el("div", { class: "huvud" }, el("h2", {}, "Värderingar att granska"), el("button", { class: "knapp liten", type: "button", onclick: () => p.stang() }, "Klar")),
      el("p", { class: "muted" }, "Omvärderingen jämför med sålda föremål på Auctionet. De här ändrade den inte själv – för att ändringen är stor, sökordet allmänt, attributionen osäker eller underlaget litet. Titta på jämförelserna (länken) innan du väljer."),
      lista_]);
    const fyll = () => {
      const rader = lista().filter(forslagFor).sort((a, b) => Math.abs(Math.log((forslagFor(b).median || 1) / (b.auk_median || 1))) - Math.abs(Math.log((forslagFor(a).median || 1) / (a.auk_median || 1))));
      lista_.replaceChildren(...rader.map(it => forslagKort(it, forslagFor(it), fyll)));
      if (!rader.length) lista_.append(el("div", { class: "tom" }, el("div", { class: "stor" }, "Allt granskat"), el("p", {}, "Nästa omvärdering görs den 2:a i nästa månad.")));
    };
    fyll();
  }

  function render() {
    if (!$("s-rutnat")) return;  // vyn är inte monterad än (t.ex. Köpt från Butik)
    renderForslagRad();
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
    App.sheet("Nytt köp eller föremål", [
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
  const MER = [["marknad_sakerhet", "Säkerhet, uppskattning", "text"], ["jfr", "Underlag", "text", "bred"], ["jfr_url", "Underlag – länk", "text"],
    ["pris_uppdaterad", "Värderat", "date"], ["sokord", "Sökord (används vid omvärderingen)", "text", "bred"]];
  const ANTECKNING = [["anteckning", "Anteckning", "textarea", "bred"]];
  const TEXTER = [["beskrivning", "Beskrivning", "textarea", "bred"], ["annons_rubrik", "Annonsrubrik", "text", "bred"],
    ["annons_text", "Annonstext", "textarea", "bred"], ["proveniens", "Köpt (proveniens)", "textarea", "bred"]];
  const FALT = [...GRUNDFAKTA, ...KOP, ...VARDE, ...MER, ...TEXTER, ...ANTECKNING];
  const SALJ = [["tradera_pris", "Utgångspris (kr)", "number"], ["tradera_lagsta", "Lägsta pris (kr)", "number"], ["upplagd", "Upplagd", "datetime-local"], ["steg_satt", "Steg satt (0 = första)", "number"]];
  const SALT = [["salt_for", "Såld för (kr)", "number"], ["salt_datum", "Såld datum", "date"], ["salt_kanal", "Kanal", "text"]];

  function falt(it, [id, etikett, typ, bred]) {
    let inp;
    if (typ === "select") { inp = el("select", { name: id }, ...KATEGORIER.map(k => el("option", { value: k }, k))); inp.value = it[id] || KATEGORIER[0]; }
    else if (typ === "textarea") { inp = el("textarea", { name: id, rows: id === "annons_text" || id === "beskrivning" ? 6 : 3 }); inp.value = it[id] || ""; }
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
    v.append(el("div", { class: "muted", style: "margin:-8px 0 12px" }, ...[it.nummer ? el("span", { class: "fjnr" }, App.fjNr(it)) : null,
      [LADNAMN[it.lada], under(it), it.kategori].filter(Boolean).join(" · ")].filter(Boolean)));
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
      f("Värderat", vardeKalla(it), it.pris_uppdaterad ? "" : "bred");
    }
    f("Inköpt", [it.inkopt ? App.datum(it.inkopt) : "", it.inkopsstalle].filter(Boolean).join(" på "));
    f("Antal", (+it.antal || 1) > 1 ? it.antal + " st" : null); f("Period", it.period); f("Stämpel", it.stampel); f("Skick", it.skick);
    if (it.jfr) fakta.append(el("div", { style: "grid-column:1/-1" }, el("b", {}, "Underlag"), it.jfr_url ? el("a", { href: it.jfr_url, target: "_blank", rel: "noopener" }, it.jfr) : el("span", {}, it.jfr)));
    v.append(fakta);
    if (forslagFor(it)) v.append(el("div", { style: "margin-top:12px" }, forslagKort(it, forslagFor(it), () => p.byt("visa"))));
    v.append(textRuta(it, () => p.byt("visa")));
    if (it.anteckning) v.append(el("div", { class: "ruta", style: "margin-top:12px;white-space:pre-wrap" }, it.anteckning));
    const saljRuta = el("div"); v.append(saljRuta); renderSalj(it, saljRuta, p);
    const hist = el("div"); v.append(el("h3", {}, "Prishistorik")); v.append(hist); laddaHistorik(it, hist);
    v.append(el("div", { class: "rad", style: "margin-top:16px" },
      el("span", { class: "muted", style: "font-size:13px" }, `Tillagd ${it.skapad ? App.datum(it.skapad) : "–"} · ändrad ${it.uppdaterad ? App.datum(it.uppdaterad) : "–"}`),
      el("button", { class: "knapp fara liten hoger", type: "button", onclick: () => taBort(it, p) }, "🗑 Ta bort")));
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
    form.append(grupp("Texter", it, TEXTER, false, "beskrivning, annons, köpt"));
    form.append(grupp("Mer", it, MER, false, "underlag, sökord"));
    form.append(el("div", { class: "falt-grid", style: "margin-top:10px" }, ...ANTECKNING.map(f => falt(it, f))));
    const status = el("div", { class: "status" });
    form.append(el("div", { class: "rad", style: "margin-top:16px" },
      el("button", { class: "knapp primar", type: "submit" }, "Spara"),
      el("button", { class: "knapp", type: "button", onclick: () => p.byt("visa") }, "Avbryt"),
      el("button", { class: "knapp fara hoger", type: "button", onclick: () => taBort(it, p) }, "🗑 Ta bort")), status);
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
    r.append(el("div", { class: "etik" }, "Till salu" + (e ? " · förväntat pris " + kr(e) : "")));
    if (!e) r.append(el("p", { style: "margin:6px 0" }, "Sätt ett utgångspris (Redigera → Till salu) eller ett värde, så räknas säljplanen ut."));
    else {
      // Var den ska ligga – det viktigaste, överst och tydligt.
      r.append(el("div", { class: "salj-kanal" }, el("span", { class: "muted" }, "Lägg ut på"), el("b", {}, plan.kanalNamn),
        el("span", { class: "muted" }, `ca ${kr(plan.netto)} i handen${plan.typ === "stege" ? " vid startpriset" : ""} efter avgifter`)));
      r.append(el("p", { style: "margin:6px 0" }, plan.text));
    }
    if (it.upplagd) r.append(el("p", { class: "muted", style: "margin:0 0 6px" }, `Upplagd ${App.datum(it.upplagd)}${it.tradera_lagsta ? " · lägsta pris " + kr(it.tradera_lagsta) : ""}`));
    if (plan.typ === "stege") {
      const steg = el("div", { class: "stege" });
      plan.steg.forEach((pris, i) => {
        const s = el("span", { title: `ca ${kr(plan.nettoSteg[i])} i handen på Tradera` }, (i === 0 ? "Start " : i === plan.steg.length - 1 ? "Golv " : "") + kr(pris),
          el("small", {}, ` → ${kr(plan.nettoSteg[i])}`));
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
    if (plan.typ === "stege") r.append(el("p", { class: "muted", style: "margin:6px 0 0;font-size:13px" }, "Siffran efter pilen är vad du får i handen på Tradera (10 %, max 200 kr, emballage och svinn)."));
    if (plan.alternativ) r.append(el("p", { class: "muted", style: "margin:6px 0 0;font-size:13px" }, "Alternativ: " + plan.alternativ));
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
  // Ta bort: frågar först i ett ark – det går inte att ångra, och samlingen är gemensam.
  function taBort(it, p) {
    App.sheet(`Ta bort ”${it.namn}”?`, [
      { ikon: "🗑", text: "Ja, ta bort för gott", under: "Föremålet, bilderna och prishistoriken försvinner för alla som delar samlingen. Går inte att ångra.", onclick: () => radera(it, p) },
      ...(it.lada !== "salt" ? [{ ikon: "✓", text: "Den är såld – flytta till Sålt i stället", under: "Då finns den kvar i statistiken över vinst", onclick: () => markeraSald(it, p) }] : []),
      { ikon: "↩", text: "Avbryt", onclick: () => {} },
    ]);
  }
  async function radera(it, p) {
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
    form.append(el("div", { class: "huvud" }, el("h2", {}, "Nytt köp"), el("button", { class: "knapp liten", type: "button", onclick: () => p.stang() }, "Avbryt")));
    form.append(bilder, status);
    const tom = { lada: "oklart", kategori: "Keramik & porslin", antal: 1, tillverkare: "", serie: "", inkopt: App.idag() };
    const lada = el("select", { name: "lada" }, ...[...VART, ["salt", "✓ Redan såld"]].map(([v, t]) => el("option", { value: v }, t))); lada.value = tom.lada;
    form.append(el("div", { class: "falt-grid" }, el("label", { class: "bred" }, "Vad ska du göra med den?", lada)));
    form.append(grupp("Köp", tom, KOP, true, "pris, datum, ställe"));
    const forslag = el("div", { class: "ruta tips", hidden: true, style: "margin-top:10px" });
    form.append(forslag);
    form.append(grupp("Grundfakta", tom, GRUNDFAKTA, true));
    form.append(grupp("Värde", tom, VARDE, false, "fylls i av Claude om du fotat"));
    form.append(el("div", { class: "rad", style: "margin-top:16px" }, el("button", { class: "knapp primar", type: "submit" }, "Spara i samlingen")));
    const p = App.panel(form);
    if (!filer.length) form.elements.namn.focus();

    const skalade = [];
    let claude = null;
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
        form.dataset.sokord = r.sokord || ""; claude = r;
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
      const proveniens = v.inkopspris != null || v.inkopsstalle ? [`Köpt ${v.inkopt ? App.datum(v.inkopt) : ""}${v.inkopsstalle ? " på " + v.inkopsstalle : ""}${v.inkopspris != null ? " för " + kr(v.inkopspris) : ""}.`.replace("Köpt  ", "Köpt "),
        claude ? `Claude: ${[claude.tillverkare, claude.formgivare, claude.serie, claude.period].filter(Boolean).join(" · ")}${claude.marknad_min != null ? `, marknad ${spann(claude.marknad_min, claude.marknad_max)}` : ""} (säkerhet ${Math.round(claude.sakerhet * 100)} %).` : ""].filter(Boolean).join("\n") : null;
      const rad = { id, user_id: konto.uid, lada: lada.value, ...v, antal: Math.max(1, v.antal || 1), tillverkare: v.tillverkare || "Okänd",
        sokord: form.dataset.sokord || "", anteckning: claude && claude.formgivare ? "Formgivare: " + claude.formgivare + "." : "", proveniens, bilder: [] };
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
        p.stang(); render();
        // Samma avslutning som Köpt i Butik/Fynd: FJ-numret stort och Claudes texter.
        const ark = App.sheet("", el("div", { class: "kopt-ark" }));
        koptKlar(data, ark.el.querySelector(".kopt-ark"), ark, data.inkopspris);
      } catch (x) { status.textContent = x.message; }
    };
  }
  function harRedanText() {
    return lista().filter(it => it.lada !== "salt").map(it => `${it.id} | ${it.namn} | ${it.tillverkare || ""} | ${it.serie || ""}`).join("\n").slice(0, 12000);
  }

  // ── CSV ───────────────────────────────────────────────────────────
  function exportCsv() {
    const kol = ["id", "lada", "namn", "kategori", "tillverkare", "serie", "antal", "period", "stampel", "skick", "inkopspris", "inkopt", "inkopsstalle",
      "marknad_min", "marknad_max", "auk_median", "tradera_pris", "tradera_lagsta", "upplagd", "steg_satt",
      "salt_for", "salt_datum", "salt_kanal", "sokord", "anteckning", "skapad", "uppdaterad"];
    const c = v => { const s = v == null ? "" : String(v); return /[";\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
    const rader = [kol.join(";"), ...synliga().map(it => kol.map(k => c(it[k])).join(";"))];
    const blob = new Blob(["﻿" + rader.join("\n")], { type: "text/csv;charset=utf-8" });
    const a = el("a", { href: URL.createObjectURL(blob), download: `samling-${st.lada || "allt"}-${App.idag()}.csv` });
    document.body.append(a); a.click(); a.remove();
  }

  // ── Texter: beskrivning, säljannons, proveniens ─────────────────────
  async function kopiera(text, knapp) {
    try { await navigator.clipboard.writeText(text); } catch (e) {
      const t = el("textarea", {}, text); document.body.append(t); t.select(); try { document.execCommand("copy"); } catch (x) {} t.remove();
    }
    if (knapp) { const f = knapp.textContent; knapp.textContent = "✓ Kopierad"; setTimeout(() => { knapp.textContent = f; }, 1500); }
  }
  function textBlock(rubrik, text, kopieraText) {
    const k = el("button", { class: "knapp liten", type: "button" }, "Kopiera");
    k.onclick = () => kopiera(kopieraText ?? text, k);
    return el("div", { class: "textblock" }, el("div", { class: "textblock-huvud" }, el("b", {}, rubrik), k), el("div", { class: "textblock-text" }, text));
  }
  function textRuta(it, klar) {
    const r = el("div", { class: "ruta texter" });
    const annons = it.annons_rubrik || it.annons_text ? [it.annons_rubrik, it.annons_text].filter(Boolean).join("\n\n") : "";
    if (it.lada === "salj" && annons) r.append(textBlock("Säljannons", annons));
    if (it.beskrivning) r.append(textBlock("Beskrivning", it.beskrivning));
    if (it.lada !== "salj" && annons) { const d = el("details", {}, el("summary", {}, "Säljannons (om du vill sälja)"), textBlock("Säljannons", annons)); r.append(d); }
    if (it.proveniens) r.append(textBlock("Köpt", it.proveniens));
    const status = el("span", { class: "muted" });
    const knapp = el("button", { class: "knapp liten", type: "button" }, it.beskrivning ? "✍ Skriv om texterna" : "✍ Skriv beskrivning och annons");
    knapp.onclick = async () => {
      knapp.disabled = true; status.textContent = "Claude skriver …";
      try { await skrivTexter(it); render(); klar(); toast("Texterna är klara"); }
      catch (e) { status.textContent = e.message; knapp.disabled = false; }
    };
    r.append(el("div", { class: "rad", style: "margin-top:8px" }, knapp, status));
    return r;
  }
  async function skrivTexter(it) {
    const e = Logik.forvantat(it);
    const plan = e ? Logik.saljplan(e) : null;
    const r = await App.kannIgen({ typ: "beskriv", foremal: { ...it, nummer: App.fjNr(it) }, kanal: plan && plan.kanalNamn || "",
      paths: (it.bilder || []).map(b => b.path).filter(Boolean).slice(0, 3) });
    if (!r.beskrivning && !r.annons_text) throw new Error("Claude gav inget svar – försök igen.");
    Object.assign(it, await spara(it.id, { beskrivning: r.beskrivning || null, annons_rubrik: r.annons_rubrik || null, annons_text: r.annons_text || null }));
    return it;
  }

  // ── Köpt: ett flöde för Butik, Fynd och Samling ─────────────────────
  // rad = förifyllda fält för samling_foremal; blobs = egna foton (Butik); urlar = annonsens bilder (Fynd);
  // kalla = rader till proveniensen (bedömning, annonslänk, jämförelser).
  const VART = [["egen", "🏠 Behålla – egen samling"], ["salj", "🏷 Sälja – till salu"], ["oklart", "❓ Bestämmer senare"], ["pappas", "👴 Pappas"]];
  async function kopt({ rad, blobs = [], urlar = [], kalla = [] }) {
    const svar = await App.fraga("Köpt! 🎉", { ok: "Spara i samlingen", falt: [
      { id: "pris", etikett: "Vad betalade du? (kr)", typ: "number", varde: rad.inkopspris ?? "" },
      { id: "stalle", etikett: "Var?", varde: rad.inkopsstalle || "", placeholder: "t.ex. Myrorna Hornstull" },
      { id: "lada", etikett: "Vad ska du göra med den?", val: VART, varde: rad.lada || "oklart" }] });
    if (!svar) return null;
    const pris = svar.pris === "" ? null : Math.round(+svar.pris);
    const stalle = (svar.stalle || "").trim() || rad.inkopsstalle || null;
    const idag = App.idag();
    const proveniens = [`Köpt ${App.datum(idag)}${stalle ? " på " + stalle : ""}${pris != null ? " för " + kr(pris) : ""}.`, ...kalla].filter(Boolean).join("\n");
    const ny = { ...rad, id: rad.id || App.nyttId(rad.namn), user_id: konto.uid, lada: svar.lada, inkopspris: pris, inkopsstalle: stalle,
                 inkopt: idag, proveniens, bilder: [] };
    const ark = App.sheet("", el("div", { class: "kopt-ark" }, el("div", { class: "muted" }, "Sparar …")));
    const vis = ark.el.querySelector(".kopt-ark");
    try {
      const { data, error } = await konto.sb.from("samling_foremal").insert(ny).select().single();
      if (error) throw new Error("Kunde inte spara: " + error.message);
      const it = data; konto.samling.unshift(it);
      const steg = koptHuvud(it, vis, pris);
      steg.textContent = "Sparar bilderna …";
      let bilder = [];
      if (blobs.length) {
        let n = 0;
        for (const b of blobs) { n += 1; const path = `${konto.uid}/${it.id}/${n}.jpg`; await App.laddaUppBild(path, b); bilder.push({ n, path }); }
      } else if (urlar.length) {
        try { bilder = (await App.kannIgen({ typ: "kopiera_bilder", id: it.id, urlar: urlar.slice(0, 4) })).bilder || []; } catch (e) { console.error(e); }
      }
      if (bilder.length) Object.assign(it, await spara(it.id, { bilder }));
      await koptKlar(it, vis, ark, pris, steg);
      return it;
    } catch (e) { vis.replaceChildren(el("p", {}, e.message), el("button", { class: "knapp", type: "button", onclick: () => ark.stang() }, "Stäng")); return null; }
  }
  App.kopt = kopt;
  function koptHuvud(it, vis, pris) {
    const steg = el("div", { class: "muted" });
    vis.replaceChildren(
      el("div", { class: "kopt-nr" }, App.fjNr(it)),
      el("p", {}, "Skriv numret på en lapp eller maskeringstejp under föremålet – då hittar du det i appen."),
      el("div", { class: "muted" }, it.namn + " · " + (LADNAMN[it.lada] || it.lada) + (pris != null ? " · " + kr(pris) : "")),
      steg);
    return steg;
  }
  // FJ-numret, Claudes texter och knapparna – sista steget för alla sätt att registrera ett köp.
  async function koptKlar(it, vis, ark, pris, steg) {
    steg = steg || koptHuvud(it, vis, pris);
    steg.textContent = "Claude skriver beskrivning och annons …";
    try {
      await skrivTexter(it);
      steg.replaceChildren(...[
        it.lada === "salj" && it.annons_text ? textBlock("Säljannons", [it.annons_rubrik, it.annons_text].filter(Boolean).join("\n\n")) : null,
        it.beskrivning ? textBlock("Beskrivning", it.beskrivning) : null].filter(Boolean));
    } catch (e) { steg.textContent = "Texterna kunde inte skrivas nu (" + e.message + "). Tryck ”Skriv beskrivning” i föremålet senare."; }
    vis.append(el("div", { class: "rad", style: "margin-top:12px" },
      el("button", { class: "knapp primar", type: "button", onclick: () => { ark.stang(); App.visa("samling"); oppnaDetalj(it.id); } }, "Öppna i samlingen"),
      el("button", { class: "knapp", type: "button", onclick: () => ark.stang() }, "Klar")));
    App.sand("samling-andrad"); render();
  }

  App.del("samling", { namn: "Samling", ikon: "🏺",
    montera(sek) {
      rot = sek;
      sek.replaceChildren();
      const h = App.huvud("samling", "Samling", "");
      h.querySelector(".sub").id = "s-antal";
      h.insertBefore(el("span", { class: "rad hoger" },
        el("button", { class: "knapp primar", type: "button", id: "s-ny", onclick: laggTillMeny }, "＋ Nytt köp"),
        el("button", { class: "knapp", type: "button", "aria-label": "Mer", onclick: merMeny }, "⋯")), h.querySelector(".hjalp"));
      sek.append(h,
        el("div", { id: "s-forslag" }),
        el("div", { class: "lador", id: "s-lador" }), el("div", { class: "sammanstallning", id: "s-sammanstallning" }),
        el("div", { class: "verktyg" }, el("div", { class: "rad" },
          el("input", { id: "s-q", type: "search", placeholder: "Sök namn, tillverkare, serie …", "aria-label": "Sök i samlingen" }),
          el("select", { id: "s-kategori", "aria-label": "Kategori" }),
          el("select", { id: "s-sort", "aria-label": "Sortera" }, new Option("Senast ändrad", "andrad"), new Option("Namn A–Ö", "namn"), new Option("Mest värt först", "varde"), new Option("Kategori", "kategori")))),
        el("div", { class: "s-rutnat", id: "s-rutnat" }),
        el("button", { class: "fab", type: "button", "aria-label": "Nytt köp", onclick: laggTillMeny }, "＋"));
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
