// Butik: fota föremålet och stämpeln, skriv priset – och få KÖP / KÖP INTE / FOTA STÄMPELN FÖRST.
(() => {
  "use strict";
  const { konto, el, kr, toast, $ } = App;
  let rot, tips = [];
  const bk = { obj: null, stampel: null, res: null };

  function harRedanText() {
    return konto.samling.filter(it => it.lada !== "salt").map(it => `${it.id} | ${it.namn} | ${it.tillverkare || ""} | ${it.serie || ""}`).join("\n").slice(0, 12000);
  }
  // Snabb koll utan Claude: samma tillverkare + serie i samlingen?
  function harJagRedan(r) {
    const n = App.norm;
    const tv = n(r.tillverkare), se = n(r.serie);
    if (!tv || tv === "okand") return [];
    return konto.samling.filter(it => it.lada !== "salt" && n(it.tillverkare) === tv && (!se || n(it.serie) === se)).slice(0, 4);
  }

  function pris() { const v = $("bk-pris").value; return v === "" ? null : Math.max(0, +v); }
  function visaBesked() {
    const box = $("bk-besked");
    if (!bk.res) { box.className = "bk-besked vanta"; box.replaceChildren(el("div", { class: "stort" }, bk.obj ? "Skriv priset" : "Fota föremålet"),
      el("div", { class: "under" }, bk.obj ? "Beskedet kommer av sig självt. Fota gärna stämpeln också – det ger säkrare svar." : "Tryck på den stora knappen – stämpeln (undersidan) är frivillig men hjälper.")); return; }
    const r = bk.res;
    const b = Logik.butikBesked(r, pris(), !!bk.stampel);
    const namn = [r.tillverkare !== "Okänd" ? r.tillverkare : "", r.serie, r.namn].filter(Boolean).join(" · ") || "Okänt föremål";
    box.className = "bk-besked " + b.klass;
    box.replaceChildren(el("div", { class: "stort" }, b.besked), el("div", { class: "under" }, namn + " · " + b.skal));
    const d = $("bk-detalj"); d.hidden = false;
    // På telefon är detaljerna hopfällda – beskedet, köptaket och "har redan" räcker i butiken.
    const fall = $("bk-detalj-fall");
    fall.open = !App.mobil();
    fall.querySelector("summary").textContent = `Detaljer · marknad ${r.marknad_min != null ? kr(r.marknad_min) + "–" + kr(r.marknad_max) : "okänd"} · säkerhet ${Math.round(r.sakerhet * 100)} %`;
    const rad = (t, v) => v ? [el("dt", {}, t), el("dd", {}, v)] : [];
    const dl = el("dl", {},
      ...rad("Marknad", r.marknad_min != null ? `${kr(r.marknad_min)} – ${kr(r.marknad_max)} (median ${kr(b.median)})` : "okänd"),
      ...rad("Köptak", b.tak != null ? `${kr(b.tak)} – ${b.regel}` : ""),
      ...rad("Säkerhet", Math.round(r.sakerhet * 100) + " %" + (bk.stampel ? " (med stämpelbild)" : "")),
      ...rad("Period", r.period), ...rad("Material", r.material), ...rad("Stämpel", r.stampel_last), ...rad("Skick", r.skick),
      ...rad("Smak", r.passar_smak ? "passar min samling → köptak 60 %" : konto.installningar.smak ? "passar inte profilen → flipp, köptak 33 %" : "ingen smakprofil (Inställningar) → flipp"),
      ...rad("Kompletterar", r.kompletterar), ...rad("Resonemang", r.resonemang));
    d.replaceChildren(dl);
    if (r.nasta_kontroll && r.nasta_kontroll.length) d.append(el("p", { style: "margin-top:8px" }, el("b", {}, "Kolla på plats: "), r.nasta_kontroll.join(" · ")));
    // Netto per kanal på medianen.
    if (b.median) {
      const kanaler = el("div", { class: "kanaler" });
      Logik.bestChannel(b.median, pris() || 0).forEach((k, i) => kanaler.append(el("span", { class: i === 0 ? "bast" : "" }, `${k.namn}: netto ${kr(k.netto)}${pris() != null ? ", vinst " + kr(k.vinst) : ""}`)));
      d.append(el("p", { style: "margin:10px 0 4px" }, el("b", {}, "Netto efter avgifter vid " + kr(b.median))), kanaler);
    }
    // Har jag redan?
    const redan = harJagRedan(r);
    const egen = r.har_redan ? konto.samling.find(it => it.id === r.har_redan) : null;
    const redanRuta = $("bk-redan"); redanRuta.replaceChildren(); redanRuta.hidden = !(egen || redan.length);
    if (egen || redan.length) {
      redanRuta.append(el("div", { class: "etik" }, "Du har redan något liknande"));
      for (const it of (egen ? [egen, ...redan.filter(x => x.id !== egen.id)] : redan)) {
        redanRuta.append(el("div", {}, el("a", { href: "#", onclick: e => { e.preventDefault(); App.visa("samling"); App.oppnaForemal(it.id); } }, it.namn), ` – ${[it.tillverkare, it.serie].filter(Boolean).join(" · ")}`));
      }
    }
    $("bk-knappar").hidden = false;
    $("bk-lagg").textContent = "🛒 Köpt";
  }

  // Stegraden överst: 1 Fota · 2 Pris · 3 Besked. Beskedet kommer av sig självt när bild och pris finns.
  function visaSteg() {
    const s = $("bk-steg"); if (!s) return;
    const har = [!!bk.obj, pris() != null, !!bk.res];
    const nu = har[0] ? (har[1] ? 2 : 1) : 0;
    [...s.children].forEach((e, i) => { e.className = har[i] ? "klar" : i === nu ? "nu" : ""; });
    $("bk-go").disabled = !bk.obj;
    $("bk-go").textContent = bk.res ? "Bedöm igen" : bk.obj ? (pris() == null ? "Bedöm (utan pris)" : "Bedöm") : "Fota föremålet först";
    $("bk-go").classList.toggle("primar", !bk.res);   // när beskedet finns är den bara en extraknapp
  }
  let autoT = null;
  function kanskeBedom() { clearTimeout(autoT); if (bk.obj && !bk.res && pris() != null) autoT = setTimeout(bedom, 700); }
  async function valjBild(vad, fil) {
    if (!fil) return;
    const s = await App.skalaNer(fil, 1600);
    bk[vad] = s;
    const lab = $("bk-" + vad);
    lab.classList.add("har");
    lab.querySelector("img").src = s.dataUrl; lab.querySelector("img").hidden = false;
    lab.querySelector(".txt").textContent = vad === "obj" ? "Byt bild på föremålet" : "Byt bild på stämpeln";
    visaSteg();
    if (bk.res && vad === "stampel") bedom(); else kanskeBedom();
    if (vad === "obj" && !bk.res && pris() == null) $("bk-pris").focus();
  }
  async function bedom() {
    if (!bk.obj) return;
    $("bk-go").disabled = true; $("bk-knappar").hidden = true; $("bk-detalj").hidden = true; $("bk-redan").hidden = true;
    const box = $("bk-besked"); box.className = "bk-besked vanta"; box.replaceChildren(el("div", { class: "stort" }, "Tittar …"), el("div", { class: "under" }, "5–40 sekunder"));
    try {
      const bilder = [bk.obj, bk.stampel].filter(Boolean).map(s => App.dataUrlTillBase64(s.dataUrl));
      bk.res = await App.kannIgen({ typ: "butik", bilder, mediatyp: "image/jpeg", stampel: !!bk.stampel, smak: konto.installningar.smak || "", har_redan: harRedanText() });
      visaBesked();
      box.scrollIntoView({ behavior: "smooth", block: App.mobil() ? "start" : "nearest" });  // på telefon: beskedet överst
    } catch (e) { bk.res = null; box.className = "bk-besked vanta"; box.replaceChildren(el("div", { class: "stort" }, "Gick inte"), el("div", { class: "under" }, e.message + " Tryck Bedöm för att försöka igen.")); }
    finally { visaSteg(); }
  }
  function nasta() {
    bk.obj = bk.stampel = bk.res = null;
    for (const vad of ["obj", "stampel"]) { const lab = $("bk-" + vad); lab.classList.remove("har"); lab.querySelector("img").hidden = true; lab.querySelector(".txt").textContent = vad === "obj" ? "Fota föremålet" : "Fota stämpeln"; }
    $("bk-pris").value = ""; $("bk-knappar").hidden = true; $("bk-detalj").hidden = true; $("bk-redan").hidden = true;
    visaBesked(); visaSteg(); window.scrollTo(0, 0);
  }
  // Köpt → samma flöde som i Fynd: pris, ställe, behålla/sälja → FJ-nummer, bilder, beskrivning och annons.
  async function laggISamlingen(knapp) {
    if (!bk.res) return;
    const r = bk.res, b = Logik.butikBesked(r, pris(), !!bk.stampel);
    const namn = r.namn || [r.tillverkare, r.serie].filter(Boolean).join(" ") || "Föremål";
    const rad = { namn: namn.slice(0, 120), lada: r.passar_smak ? "egen" : b.besked === "KÖP" ? "salj" : "oklart",
      kategori: r.kategori || "Keramik & porslin", tillverkare: r.tillverkare || "Okänd", serie: r.serie || "", antal: r.antal || 1,
      period: r.period || null, stampel: r.stampel_last || null, skick: r.skick || null, sokord: r.sokord || "",
      inkopspris: pris() != null ? Math.round(pris()) : null, inkopsstalle: "",
      marknad_min: r.marknad_min, marknad_max: r.marknad_max, marknad_sakerhet: Math.round(r.sakerhet * 100) + " %",
      tradera_pris: b.besked === "KÖP" ? b.median : null, saker: r.sakerhet >= 0.7 ? "säker" : "trolig",
      anteckning: [r.formgivare ? "Formgivare: " + r.formgivare + "." : "", `Bedömd i butiken ${App.idag()}: ${b.besked}. ${r.resonemang || ""}`.trim()].filter(Boolean).join("\n") };
    const kalla = [`Bedömd i butiken: ${b.besked}${r.marknad_min != null ? `, marknad ${kr(r.marknad_min)}–${kr(r.marknad_max)}` : ""} (säkerhet ${Math.round(r.sakerhet * 100)} %).`,
      r.stampel_last ? "Stämpel: " + r.stampel_last : ""];
    const it = await App.kopt({ rad, blobs: [bk.obj, bk.stampel].filter(Boolean).map(s => s.blob), kalla });
    if (it) { knapp.textContent = "✓ " + App.fjNr(it) + " i samlingen"; knapp.disabled = true; }
  }

  App.del("butik", { namn: "Butik", ikon: "🛍️",
    montera(sek) {
      rot = sek;
      sek.innerHTML = `
        <div class="butik">
          <div class="vy-huvud" id="bk-huvud"></div>
          <div class="steg-rad" id="bk-steg"><span>1 · Fota<b class="bara-desk"> föremålet</b></span><span>2 · <b class="bara-desk">Skriv priset</b><b class="bara-mob">Pris</b></span><span>3 · Besked</span></div>
          <div class="bk-rad">
            <label class="bk-knapp" id="bk-obj"><img alt="" hidden><span class="ikon">📷</span><span class="txt">Fota föremålet</span><input type="file" accept="image/*" capture="environment" class="dold"></label>
            <label class="bk-knapp" id="bk-stampel"><img alt="" hidden><span class="ikon">🔍</span><span class="txt">Fota stämpeln</span><input type="file" accept="image/*" capture="environment" class="dold"></label>
          </div>
          <div class="bk-gal">
            <label>🖼 <span class="bara-desk">Föremål från galleriet</span><span class="bara-mob">Galleri</span><input type="file" accept="image/*" class="dold" id="bk-obj-gal"></label>
            <label>🖼 <span class="bara-desk">Stämpel från galleriet</span><span class="bara-mob">Galleri</span><input type="file" accept="image/*" class="dold" id="bk-stampel-gal"></label>
          </div>
          <label class="bk-pris">Pris? <input type="number" inputmode="numeric" pattern="[0-9]*" enterkeyhint="done" id="bk-pris" placeholder="kr"></label>
          <button class="knapp primar stor" type="button" id="bk-go" disabled style="width:100%;justify-content:center;margin-bottom:12px">Bedöm</button>
          <div class="bk-besked vanta" id="bk-besked"></div>
          <div class="bk-knappar" id="bk-knappar" hidden>
            <button class="knapp primar" type="button" id="bk-lagg">🛒 Köpt</button>
            <button class="knapp" type="button" id="bk-nasta">Nästa sak</button>
          </div>
          <div class="ruta bk-redan" id="bk-redan" hidden></div>
          <details class="bk-detalj-fall" id="bk-detalj-fall"><summary>Detaljer</summary><div class="ruta bk-detalj" id="bk-detalj" hidden></div></details>
          <details class="sec"><summary>Fototips som höjer träffsäkerheten</summary><ul id="bk-tips"></ul></details>
          <details class="sec"><summary>På loppisen – checklista</summary><ol id="bk-checklista"></ol></details>
          <p class="muted" style="font-size:13px;margin-top:12px">Claude tittar på bilderna. Bedömningen kan vara fel – kolla stämpeln själv vid dyrare köp.</p>
        </div>`;
      $("bk-obj").querySelector("input").onchange = e => { valjBild("obj", e.target.files[0]); e.target.value = ""; };
      $("bk-stampel").querySelector("input").onchange = e => { valjBild("stampel", e.target.files[0]); e.target.value = ""; };
      $("bk-obj-gal").onchange = e => { valjBild("obj", e.target.files[0]); e.target.value = ""; };
      $("bk-stampel-gal").onchange = e => { valjBild("stampel", e.target.files[0]); e.target.value = ""; };
      $("bk-huvud").replaceWith(App.huvud("butik", "Butik", "Ska jag köpa?"));
      $("bk-pris").oninput = () => { visaSteg(); if (bk.res) visaBesked(); else kanskeBedom(); };
      $("bk-pris").onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); $("bk-pris").blur(); if (bk.obj) bedom(); } };
      $("bk-go").onclick = bedom;
      $("bk-nasta").onclick = nasta;
      $("bk-lagg").onclick = e => laggISamlingen(e.currentTarget);
      visaBesked(); visaSteg();
      fetch("data/fototips.json").then(r => r.json()).then(t => { tips = t; $("bk-tips").replaceChildren(...t.map(x => el("li", {}, x))); }).catch(() => {});
      fetch("data/checklista.json").then(r => r.json()).then(c => { const l = (c.find(x => x.rubrik === "På loppisen") || {}).punkter || []; $("bk-checklista").replaceChildren(...l.map(x => el("li", {}, x))); }).catch(() => {});
    },
  });
})();
