// Fynd: Fyndjakts nattliga fynd inne i sajten. "Slutar snart" överst, sedan listan med sortering och filter.
(() => {
  "use strict";
  const { konto, el, esc, kr, toast, $ } = App;
  const KALLNAMN = { auctionet: "Auctionet", tradera: "Tradera", bukowskis: "Bukowskis", myrorna: "Myrorna", stadsmissionen: "Stadsmissionen" };
  const REGORDNING = ["Stockholm", "Uppsala och Mälardalen", "Östergötland, Småland och Blekinge", "Västsverige och Värmland",
    "Skåne", "Norrland och Dalarna", "Övriga Sverige", "Okänd ort"];
  const st = { spar: "alla", sort: "slutar", kalla: "", region: "", q: "", min: 0, visa: 60 };
  try { Object.assign(st, JSON.parse(localStorage.getItem("fynd-vy") || "{}")); } catch (e) {}
  const mini = new Map();   // nyckel → data-URL (fyndjakt_bilder)
  let rot, timer;

  const spar = () => ((konto.fynd || {}).spar || []);
  const poster = () => ((konto.fynd || {}).poster || []);
  const flippSpar = id => !!(spar().find(s => s.id === id) || {}).flipp;
  const kvot = p => Logik.kvot(p) ?? (p.kvot ?? null);
  const norm = App.norm;
  function iSpar(p) {
    if (st.spar === "alla") return true;
    if (st.spar === "flipp") return flippSpar(p.spar);
    return p.spar === st.spar;
  }
  function traffSok(p) {
    if (!st.q) return true;
    const t = norm((p.titel || "") + " " + (p.motivering || "") + " " + (p.identifierat || ""));
    return st.q.split(/\s+/).map(norm).filter(Boolean).every(o => t.includes(o));
  }
  // Det du ogillat eller köpt visas inte – inte heller samma föremål upplagt igen (samma titel, minst 20 tecken).
  const titelNyckel = p => { const t = App.norm(p.titel); return t.length >= 20 ? p.spar + "|" + t : null; };
  let doldaTitlar = null, doldaAntal = -1;
  function dold(p) {
    const r = konto.reakt.get(p.nyckel);
    if (r && (r.typ === "ogillar" || r.typ === "kopt")) return true;
    if (!doldaTitlar || doldaAntal !== konto.reakt.size) {
      doldaTitlar = new Set([...konto.reakt.values()].filter(x => x.typ === "ogillar" || x.typ === "kopt").map(titelNyckel).filter(Boolean));
      doldaAntal = konto.reakt.size;
    }
    const k = titelNyckel(p);
    return !!(k && doldaTitlar.has(k));
  }
  function synliga() {
    const nu = Date.now() / 1000;
    return poster().filter(p => !dold(p) && iSpar(p) && (!st.kalla || p.kalla === st.kalla) && (!st.region || p.region === st.region || p.region === "Okänd ort")
      && (+p.betyg || 0) >= st.min && traffSok(p) && (!p.slutar_ts || p.slutar_ts > nu - 3600));
  }
  function sorterare() {
    return {
      slutar: (a, b) => (a.slutar_ts || 9e12) - (b.slutar_ts || 9e12),
      kvot: (a, b) => (kvot(a) ?? 9) - (kvot(b) ?? 9) || (b.betyg || 0) - (a.betyg || 0),
      betyg: (a, b) => (b.betyg || 0) - (a.betyg || 0) || (a.slutar_ts || 9e12) - (b.slutar_ts || 9e12),
    }[st.sort] || ((a, b) => 0);
  }
  function minnas() { try { localStorage.setItem("fynd-vy", JSON.stringify({ spar: st.spar, sort: st.sort, min: st.min, region: st.region })); } catch (e) {} }

  // ── Kort ───────────────────────────────────────────────────────────
  function kort(p) {
    const k = el("article", { class: "kort" + (konto.reakt.get(p.nyckel) && konto.reakt.get(p.nyckel).typ === "ogillar" ? " ogillad" : ""), "data-ankare": p.nyckel });
    const bild = el("a", { class: "bild", href: p.url, target: "_blank", rel: "noopener" });
    const src = mini.get(p.nyckel) || (p.bilder || [])[0];
    if (src) { const i = el("img", { src, alt: "", loading: "lazy", referrerpolicy: "no-referrer" }); i.onerror = () => { i.remove(); bild.prepend(el("div", { class: "ingen" }, "Ingen bild")); }; bild.append(i); }
    else bild.append(el("div", { class: "ingen" }, "Ingen bild"));
    if (p.betyg != null) bild.append(el("span", { class: "marke" }, "★ " + p.betyg + "/10"));
    const kv = kvot(p);
    // Kvoten (pris ÷ typiskt): grönt = fyndläge, mässing = under typiskt pris, dämpat = inget särskilt.
    if (kv != null) bild.append(el("span", { class: "marke hoger kvot " + (kv <= 0.5 ? "fynd" : kv <= 0.8 ? "bra" : "neutral"), title: "Pris nu delat med typiskt slutpris" },
      Math.round(kv * 100) + " %" + (kv <= 0.5 ? " · fynd" : "")));
    k.append(bild);
    const kropp = el("div", { class: "kropp" });
    kropp.append(el("div", { class: "etik" }, [p.kategori, (spar().find(s => s.id === p.spar) || {}).namn].filter(Boolean).join(" · ")));
    kropp.append(el("h3", { class: "titel" }, el("a", { href: p.url, target: "_blank", rel: "noopener" }, p.titel)));
    if (p.identifierat) kropp.append(el("p", { class: "varfor" }, "Claude: " + p.identifierat));
    if (p.motivering && !flippSpar(p.spar)) kropp.append(el("p", { class: "varfor" }, p.motivering));
    if (p.varning) kropp.append(el("p", { class: "varning" }, "⚠ " + p.varning));
    const tal = el("div", { class: "tal" });
    const cell = (b, v, cls) => el("div", { class: cls || "" }, el("b", {}, b), el("span", {}, v));
    tal.append(cell("Pris nu", p.pris ? kr(p.pris) : (p.pris_text || "–")));
    const slutpris = p.jmf_median ? p.jmf_median * (p.styck > 1 ? p.styck : 1) : null;
    tal.append(cell("Köp max", p.kop_max ? kr(p.kop_max) : p.jmf_median ? kr(Math.round(p.jmf_median * Logik.KOPTAK_FLIPP)) : "–", "kop"));
    tal.append(cell("Säljs för", slutpris ? kr(slutpris) : "–"));
    kropp.append(tal);
    // Storleken: en liten vas jämförs bara med sålda i samma höjd. Står det "för få" är jämförelsen osäkrare.
    if (p.jmf_storlek) kropp.append(el("p", { class: /för få/.test(p.jmf_storlek) ? "varning" : "muted", style: "font-size:13px;margin:4px 0 0" },
      (/för få/.test(p.jmf_storlek) ? "⚠ " : "📏 ") + p.jmf_storlek + "."));
    // Hur köp max räknas – annars ser glappet mellan köp max och slutpris obegripligt ut.
    if (slutpris) kropp.append(el("details", { class: "rakning" }, el("summary", {}, "Hur räknas köp max?"), rakning(p, slutpris)));
    const sald = saldaLista(p);
    if (sald) kropp.append(sald);
    const meta = el("div", { class: "meta" });
    const t = Logik.tidKvar(p);
    if (t != null) { const s = el("span", { class: t < 6 * 3600 ? "het" : t < 86400 ? "snart" : "", "data-ts": p.slutar_ts }); s.textContent = tidtext(t); meta.append(s); }
    meta.append(el("span", {}, KALLNAMN[p.kalla] || p.kalla));
    if (p.ort || p.plats) meta.append(el("span", {}, p.ort || p.plats));
    if (p.jmf_antal) meta.append(el("span", {}, p.jmf_antal + " jämförelser"));
    kropp.append(meta);
    kropp.append(reaktioner(p, k));
    const status = el("div", { class: "r-status" }); kropp.append(status);
    const akta = el("div", { class: "akta", hidden: true }); kropp.append(akta);
    k.append(kropp);
    return k;
  }
  function rakning(p, slutpris) {
    const st = p.styck > 1 ? ` (${p.styck} st à ${kr(p.jmf_median)})` : "";
    const salda = p.jmf_antal ? ` – medianen av ${p.jmf_antal} sålda på Auctionet` : "";
    if (!p.kop_max) return el("p", {}, `Liknande klubbas för ca ${kr(slutpris)}${st}${salda}. Köp max är en tredjedel av det: ${kr(Math.round(slutpris * Logik.KOPTAK_FLIPP))}.`);
    const r = Logik.flippRakning(slutpris, p.kalla);
    if (!r.kopMax) return el("p", {}, `Liknande klubbas för ca ${kr(slutpris)}${st}${salda}. Efter auktionshusets provision (20 %) och avgift (100 kr) blir nettot bara ${kr(r.netto)} – det lönar sig inte att köpa för att sälja vidare.`);
    const rad = (t, v, cls) => el("div", { class: cls || "" }, el("span", {}, t), el("b", {}, v));
    const ut = el("div", { class: "rakning-rader" },
      rad("Klubbas typiskt" + st, kr(r.slutpris)),
      rad("− auktionshusets provision 20 % och avgift 100 kr", "= " + kr(r.netto) + " netto"),
      rad(r.halva ? "Betala högst halva nettot" : "Lämna minst 300 kr i vinst", kr(r.tak)));
    if (r.frakt) ut.append(rad(`− frakt ${kr(r.frakt)} från ${KALLNAMN[p.kalla] || p.kalla}`, kr(r.efterFrakt)));
    if (r.prov) ut.append(rad(`÷ köparprovision ${Math.round(r.prov * 100)} % på ${KALLNAMN[p.kalla] || p.kalla}`, ""));
    ut.append(rad("Köp max", kr(r.kopMax), "summa"));
    return el("div", {}, el("p", { class: "muted" }, `Räknat på att du säljer vidare via ett auktionshus på Auctionet${salda}.${p.jmf_storlek ? " Storlek: " + p.jmf_storlek + "." : " Annonsen anger ingen höjd – jämförelsen blandar storlekar."} Halva nettot är marginalen för risk, arbete och att priset kan bli lägre.`), ut);
  }
  // Länkar till de sålda auktionerna som jämförelsen bygger på + Auctionets sökning på avslutade.
  const MAN = ["jan", "feb", "mar", "apr", "maj", "jun", "jul", "aug", "sep", "okt", "nov", "dec"];
  const datum = ts => { const d = new Date(ts * 1000); return `${d.getDate()} ${MAN[d.getMonth()]} ${d.getFullYear()}`; };
  function saldaLista(p) {
    const ex = (p.jmf_exempel || []).filter(x => x && x.url);
    if (!ex.length && !p.jamforsok) return null;
    const lista = el("ul", { class: "salda-lista" }, ...ex.map(x => el("li", {},
      el("a", { href: x.url, target: "_blank", rel: "noopener" }, x.titel || "Auktion"),
      el("span", { class: "salda-pris" },
        kr(x.klubbat || x.pris) + (x.styck > 1 ? ` · ${x.styck} st à ${kr(x.pris)}` : "") + (x.slutade ? ` · ${datum(x.slutade)}` : "")))));
    const sok = p.jamforsok ? el("a", { class: "salda-alla", href: "https://auctionet.com/sv/search?is=ended&q=" + encodeURIComponent(p.jamforsok), target: "_blank", rel: "noopener" },
      `Alla avslutade på Auctionet för ”${p.jamforsok}” →`) : null;
    const rubrik = ex.length ? `Sålda jämförelser (${ex.length}${p.jmf_antal > ex.length ? " senaste av " + p.jmf_antal : ""})` : "Sålda jämförelser";
    const not = p.jmf_sakerhet === "låg" ? el("p", { class: "muted" }, "Få sålda av just den typen – jämförelsen är bredare (alla typer), därför räknas bara 40 % av medianen.") : null;
    return el("details", { class: "rakning salda" }, el("summary", {}, rubrik), ...[not, ex.length ? lista : null, sok].filter(Boolean));
  }
  const tidtext = t => t < 0 ? "Avslutad" : "Slutar om " + Logik.tidText(t);

  function reaktioner(p, k) {
    const rad = el("div", { class: "knappar" });
    const typer = [["gillar", "👍 Gilla"], ["ogillar", "👎 Ogilla"]];
    const knappar = typer.map(([typ, text]) => {
      const b = el("button", { type: "button", "aria-pressed": String((konto.reakt.get(p.nyckel) || {}).typ === typ) }, text);
      b.onclick = async () => {
        const nu = (konto.reakt.get(p.nyckel) || {}).typ;
        b.disabled = true;
        try {
          if (nu === typ) { await taBortReaktion(p.nyckel); knappar.forEach(x => x.setAttribute("aria-pressed", "false")); }
          else {
            await sparaReaktion(p, typ); knappar.forEach(x => x.setAttribute("aria-pressed", String(x === b)));
            if (typ === "ogillar") {
              // Kortet tonar ut och försvinner ur listan; Ångra lägger tillbaka det.
              k.classList.add("borta");
              setTimeout(() => { k.remove(); byggChips(); $("fynd-antal").textContent = antalText(); App.uppdateraBanner(); }, 350);
              toast("Dold – appen lär sig", { text: "Ångra", onclick: async () => { try { await taBortReaktion(p.nyckel); byggChips(); render(); App.uppdateraBanner(); } catch (e) { toast(e.message); } } });
            } else toast("Sparad – du gillar den");
          }
        } catch (e) { toast(e.message); } finally { b.disabled = false; }
      };
      return b;
    });
    rad.append(...knappar);
    const akta = el("button", { type: "button" }, "🔍 Äkta?");
    akta.onclick = () => kollaAkthet(p, k, akta);
    rad.append(akta);
    const kopte = el("button", { type: "button", style: "border-color:var(--brass);color:var(--brass)" }, "🛒 Köpte den");
    kopte.onclick = () => kopteDen(p, kopte);
    rad.append(kopte);
    return rad;
  }

  async function sparaReaktion(p, typ) {
    const rad = { nyckel: p.nyckel, typ, spar: p.spar, kategori: p.kategori, titel: p.titel, url: p.url,
                  bild: (p.bilder || [])[0] || null, pris_text: p.pris_text, motivering: p.motivering, skapad: new Date().toISOString() };
    const { error } = await konto.sb.from("fyndjakt_reaktioner").upsert(rad, { onConflict: "user_id,nyckel" });
    if (error) throw new Error("Kunde inte spara – försök igen.");
    konto.reakt.set(p.nyckel, rad);
  }
  async function taBortReaktion(nyckel) {
    const { error } = await konto.sb.from("fyndjakt_reaktioner").delete().eq("nyckel", nyckel);
    if (error) throw new Error("Kunde inte ta bort – försök igen.");
    konto.reakt.delete(nyckel);
  }

  // Äkta? – edge-funktionen hämtar annonsens bilder och frågar Claude: original eller nyproduktion.
  async function kollaAkthet(p, k, knapp, extra) {
    const ruta = k.querySelector(".akta"); ruta.hidden = false; ruta.textContent = "Claude granskar bilderna …";
    knapp.disabled = true;
    try {
      const r = await App.kannIgen({ typ: "akta", urlar: (p.bilder || []).slice(0, 3), titel: p.titel, pris_text: p.pris_text,
                                     kalla: p.kalla, identifierat: p.identifierat || "", extra: extra || "" });
      const farg = r.bedomning === "original" ? "var(--gron-ljus)" : r.bedomning === "nyproduktion" ? "var(--rod-ljus)" : "var(--brass)";
      ruta.replaceChildren(...[
        el("div", {}, el("b", { style: "color:" + farg + ";text-transform:uppercase" }, r.bedomning), ` · säkerhet ${Math.round(r.sakerhet * 100)} %`
          + (r.bilder ? ` · ${r.bilder} bild${r.bilder > 1 ? "er" : ""} granskade` : " · inga bilder gick att läsa")),
        r.svar ? el("div", {}, r.svar) : null,
        r.tecken && r.tecken.length ? el("ul", {}, ...r.tecken.map(t => el("li", {}, t))) : null,
        r.behover ? el("div", { class: "muted" }, "Behövs: " + r.behover) : null].filter(Boolean));
      const lab = el("label", { class: "knapp liten", style: "margin-top:6px" }, "🖼 Lägg till egen skärmbild");
      const inp = el("input", { type: "file", accept: "image/*", class: "dold" });
      inp.onchange = async e => { const f = e.target.files[0]; e.target.value = ""; if (f) { const { dataUrl } = await App.skalaNer(f, 1280); kollaAkthet(p, k, knapp, dataUrl); } };
      lab.append(inp); ruta.append(lab);
    } catch (e) { ruta.textContent = e.message; }
    finally { knapp.disabled = false; }
  }

  // Köpte den → samma Köpt-flöde som i Butik (pris, ställe, behålla/sälja, FJ-nummer, texter). Annonsens bilder kopieras.
  async function kopteDen(p, knapp) {
    const rad = { namn: String(p.titel || "Fynd").slice(0, 120), lada: "salj", kategori: kategoriFor(p.kategori),
      tillverkare: (p.identifierat || "").split(",")[0].trim() || "Okänd", serie: "",
      antal: p.styck > 1 ? p.styck : 1, sokord: p.jamforsok || "", inkopspris: p.pris || null, inkopsstalle: KALLNAMN[p.kalla] || p.kalla,
      anteckning: p.identifierat ? "Claude: " + p.identifierat : "",
      auk_median: p.jmf_median ? p.jmf_median * (p.styck > 1 ? p.styck : 1) : null, tradera_pris: p.jmf_median || null,
      pris_uppdaterad: p.jmf_median ? App.idag() : null, jfr_url: p.jamforsok ? "https://auctionet.com/sv/search?is=ended&q=" + encodeURIComponent(p.jamforsok) : null,
      jfr: p.jmf_median ? `Fyndjakt: ${p.jmf_antal || "?"} sålda på Auctionet, median ${kr(p.jmf_median)}${p.jmf_lag ? ` (${kr(p.jmf_lag)}–${kr(p.jmf_hog)})` : ""}.` : "" };
    const kalla = ["Annons: " + (p.url || ""), p.jmf_median ? `Jämförelse: ${p.jmf_antal || "?"} sålda på Auctionet, median ${kr(p.jmf_median)}${p.jamforsok ? ` (”${p.jamforsok}”)` : ""}.` : "",
      ...(p.jmf_exempel || []).slice(0, 3).map(x => `  ${kr(x.klubbat || x.pris)} – ${x.titel} ${x.url}`)];
    const it = await App.kopt({ rad, urlar: (p.bilder || []).slice(0, 4), kalla });
    if (!it) return;
    try { await sparaReaktion(p, "kopt"); } catch (e) {}
    knapp.disabled = true; knapp.textContent = "✓ " + App.fjNr(it);
  }
  function kategoriFor(k) {
    const t = (k || "").toLowerCase();
    if (/glas/.test(t)) return "Glas"; if (/konst|grafik|tavl/.test(t)) return "Konst"; if (/möbl/.test(t)) return "Möbler";
    if (/belys|lamp/.test(t)) return "Belysning"; if (/bok|böck/.test(t)) return "Böcker"; if (/skulpt/.test(t)) return "Skulptur";
    return "Keramik & porslin";
  }

  // ── Miniatyrer från fyndjakt_bilder ───────────────────────────────
  async function laddaMini(nycklar) {
    const saknas = nycklar.filter(n => n && !mini.has(n));
    for (let i = 0; i < saknas.length; i += 100) {
      const bit = saknas.slice(i, i + 100);
      const { data } = await konto.sb.from("fyndjakt_bilder").select("nyckel,mini").in("nyckel", bit);
      for (const r of data || []) mini.set(r.nyckel, r.mini);
      bit.forEach(n => { if (!mini.has(n)) mini.set(n, null); });
    }
    rot.querySelectorAll(".kort").forEach(() => {});
  }

  // ── Rendering ─────────────────────────────────────────────────────
  function render() {
    minnas();
    const alla = synliga();
    const snart = Logik.slutarSnart(alla);
    const snartIds = new Set(snart.map(p => p.nyckel));
    let rader = alla.filter(p => !snartIds.has(p.nyckel)).sort(sorterare());
    const lista = $("fynd-lista"); lista.replaceChildren();
    if (!alla.length) {
      const tom = el("div", { class: "tom" });
      if (!poster().length) tom.append(el("div", { class: "stor" }, "Inga fynd än"), el("p", {}, "Fyndjakt letar varje natt. Har du ingen bevakning än – skapa en under Inställningar, så letar appen direkt."),
        el("div", { class: "rad" }, el("button", { class: "knapp", type: "button", onclick: () => App.visa("installningar") }, "Till Inställningar")));
      else tom.append(el("div", { class: "stor" }, "Inget matchar"), el("p", {}, "Prova ett annat spår, ett annat ord eller nollställ filtret."),
        el("div", { class: "rad" }, el("button", { class: "knapp", type: "button", onclick: () => { st.q = ""; st.kalla = ""; st.region = ""; st.min = 0; st.spar = "alla"; $("fynd-q").value = ""; byggChips(); render(); } }, "Visa alla fynd")));
      lista.append(tom);
    }
    if (snart.length) {
      lista.append(el("div", { class: "avsnitt-rubrik het" }, el("h3", {}, "⏱ Slutar inom 24 timmar"), el("span", {}, snart.length + " st – kolla dessa först")));
      lista.append(el("div", { class: "rutnat" }, ...snart.map(kort)));
      if (rader.length) lista.append(el("div", { class: "avsnitt-rubrik" }, el("h3", {}, "Övriga"), el("span", {}, rader.length + " st")));
    }
    if (rader.length) {
      const g = el("div", { class: "rutnat" }, ...rader.slice(0, st.visa).map(kort));
      if (rader.length > st.visa) {
        const mer = el("button", { class: "knapp visa-fler", type: "button" }, `Visa ${Math.min(60, rader.length - st.visa)} till (${rader.length - st.visa} kvar)`);
        mer.onclick = () => { st.visa += 60; const y = window.scrollY; render(); window.scrollTo(0, y); };
        g.append(mer);
      }
      lista.append(g);
    }
    $("fynd-antal").textContent = antalText();
    App.rakna("fynd", snart.length || "");
    laddaMini([...snart, ...rader.slice(0, st.visa)].map(p => p.nyckel)).then(() => {
      lista.querySelectorAll(".kort").forEach(k => {});
      // Byt in miniatyrerna där annonsbilden saknas eller inte gick att läsa.
      [...snart, ...rader.slice(0, st.visa)].forEach((p, i) => {
        const m = mini.get(p.nyckel); if (!m) return;
        const k = lista.querySelectorAll(".kort")[i]; if (!k) return;
        const img = k.querySelector(".bild img"); if (!img) { const b = k.querySelector(".bild"); b.querySelector(".ingen")?.remove(); b.prepend(el("img", { src: m, alt: "" })); }
      });
    });
    App.renderKlar("fynd");
    clearInterval(timer);
    timer = setInterval(() => lista.querySelectorAll("[data-ts]").forEach(s => { const t = +s.dataset.ts - Date.now() / 1000; s.textContent = tidtext(t); s.className = t < 6 * 3600 ? "het" : t < 86400 ? "snart" : ""; }), 60000);
  }

  // Spåren som chips – allt annat (sortering, källa, område, betyg) ligger bakom Filter-knappen.
  function antalText() {
    const alla = synliga(), snart = Logik.slutarSnart(alla).length;
    return `${alla.length} aktiva fynd${snart ? ` · ${snart} slutar inom 24 h` : ""}`;
  }
  function byggChips() {
    const val = [["alla", "Alla"], ...spar().filter(s => !s.flipp).map(s => [s.id, s.namn]), ...(spar().some(s => s.flipp) ? [["flipp", "Flipp"]] : [])];
    if (!val.some(([v]) => v === st.spar)) st.spar = "alla";
    const antal = id => poster().filter(p => !dold(p) && (id === "alla" || (id === "flipp" ? flippSpar(p.spar) : p.spar === id))).length;
    $("fynd-chips").replaceChildren(...val.map(([v, t]) => {
      const b = el("button", { class: "chip", type: "button", "aria-pressed": String(st.spar === v) }, t, el("span", { class: "n" }, String(antal(v))));
      b.onclick = () => { st.spar = v; st.visa = 60; byggChips(); render(); };
      return b;
    }));
    const aktiva = [st.kalla, st.region, st.min ? "m" : ""].filter(Boolean).length;
    const fk = $("fynd-filter"); fk.replaceChildren(...["⚙ Filter", aktiva ? el("span", { class: "n" }, String(aktiva)) : null].filter(Boolean));
    fk.classList.toggle("primar", aktiva > 0);
  }
  function filterArk() {
    const finns = new Set(poster().map(p => p.region));
    const sel = (id, etikett, val, varde) => { const s = el("select", { id }, ...val.map(([v, t]) => new Option(t, v))); s.value = varde; return el("label", { class: "falt" }, etikett, s); };
    const sort = sel("fa-sort", "Sortera", [["slutar", "Slutar snart först"], ["kvot", "Bäst pris (kvot) först"], ["betyg", "Högst betyg först"]], st.sort);
    const kalla = sel("fa-kalla", "Källa", [["", "Alla källor"], ...[...new Set(poster().map(p => p.kalla))].sort().map(k => [k, KALLNAMN[k] || k])], st.kalla);
    const region = sel("fa-region", "Område", [["", "Hela Sverige"], ...REGORDNING.filter(r => finns.has(r)).map(r => [r, r])], st.region);
    const min = sel("fa-min", "Lägsta betyg", [["0", "Alla betyg"], ["6", "Betyg 6+"], ["8", "Betyg 8+"], ["10", "Bara 10"]], String(st.min));
    const ark = App.sheet("Sortera och filtrera", el("div", {}, sort, kalla, region, min,
      el("div", { class: "rad knappar-rad" },
        el("button", { class: "knapp primar", type: "button", onclick: () => { st.sort = sort.querySelector("select").value; st.kalla = kalla.querySelector("select").value; st.region = region.querySelector("select").value; st.min = +min.querySelector("select").value; ark.stang(); byggChips(); render(); } }, "Visa fynden"),
        el("button", { class: "knapp", type: "button", onclick: () => { st.sort = "slutar"; st.kalla = ""; st.region = ""; st.min = 0; ark.stang(); byggChips(); render(); } }, "Nollställ"))));
  }

  App.del("fynd", { namn: "Fynd", ikon: "🔎",
    montera(sek) {
      rot = sek;
      sek.replaceChildren(App.huvud("fynd", "Fynd", konto.fynd && konto.fynd.uppdaterad ? "uppdaterade " + konto.fynd.uppdaterad : ""),
        el("div", { class: "verktyg" },
          el("div", { class: "chips", id: "fynd-chips" }),
          el("div", { class: "rad", style: "margin-top:6px" },
            el("input", { id: "fynd-q", type: "search", placeholder: "Sök i fynden …", "aria-label": "Sök" }),
            el("button", { class: "knapp filter-knapp", type: "button", id: "fynd-filter", onclick: filterArk }, "⚙ Filter"),
            el("span", { class: "muted hoger", id: "fynd-antal" }))),
        el("div", { id: "fynd-lista" }));
      // Kom tillbaka till samma spår och lika många visade fynd som innan appen laddades om.
      const plats = App.plats("fynd");
      if (plats && plats.extra) {
        if (plats.extra.visa > st.visa) st.visa = plats.extra.visa;
        if (plats.extra.spar) st.spar = plats.extra.spar;  // byggChips faller tillbaka på "alla" om spåret inte finns
      }
      byggChips();
      $("fynd-q").oninput = e => { st.q = e.target.value.trim(); render(); };
      render();
    },
    visa() { if (rot) render(); },
    plats() { return { visa: st.visa, spar: st.spar }; },
  });
  App.pa("visa-slutar-snart", () => { st.sort = "slutar"; st.spar = "alla"; if (rot) { byggChips(); render(); } });
  App.pa("inloggad", () => { App.rakna("fynd", Logik.slutarSnart(poster().filter(p => !dold(p))).length || ""); });
})();
