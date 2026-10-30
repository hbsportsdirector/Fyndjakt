// Prisguide, Stämplar, Kalkyl och Säljplan – data i site/data/*.json, renderat i sajtens stil.
(() => {
  "use strict";
  const { el, kr, $ } = App;
  const RAD = { "köp": "Köp", "kolla": "Kolla", "undvik": "Undvik" };
  const enc = s => encodeURIComponent(String(s || "").replace(/\s+/g, " ").trim());
  const data = {};
  async function hamta(namn) {
    if (!data[namn]) data[namn] = fetch(`data/${namn}.json`).then(r => { if (!r.ok) throw new Error("Kunde inte läsa " + namn); return r.json(); });
    return data[namn];
  }

  // ── Prisguide ─────────────────────────────────────────────────────
  const pg = { q: "", kategori: "", rad: "" };
  function fabrikAv(i) { return (i.fabrik || "").split("·")[0].trim(); }
  function renderPrisguide(lista) {
    const q = App.norm(pg.q);
    const rader = lista.filter(i => (!pg.kategori || i.kategori === pg.kategori) && (!pg.rad || i.rad === pg.rad)
      && (!q || App.norm([i.namn, i.fabrik, i.anteckning, i.kategori].join(" ")).includes(q)));
    $("pg-rad").querySelectorAll(".chip").forEach(c => c.setAttribute("aria-pressed", String(c.dataset.v === pg.rad)));
    $("pg-kat").querySelectorAll(".chip").forEach(c => c.setAttribute("aria-pressed", String(c.dataset.v === pg.kategori)));
    const ordning = { "köp": 0, "kolla": 1, "undvik": 2 };
    rader.sort((a, b) => ordning[a.rad] - ordning[b.rad] || b.salj_max - a.salj_max);
    $("pg-antal").textContent = `${rader.length} objekt · ${rader.filter(r => r.rad === "köp").length} köp`;
    $("pg-lista").replaceChildren(...rader.map(i => {
      const marg = i.kop_max && i.salj_min ? Math.round(Logik.channelNet("tradera", i.salj_min) - i.kop_max) : null;
      const k = el("article", { class: "pg-kort" });
      k.append(el("div", { class: "rad" }, el("h3", { style: "flex:1" }, i.namn), el("span", { class: "rad-etikett-stor rad-" + i.rad }, RAD[i.rad] || i.rad)));
      k.append(el("div", { class: "fabrik" }, i.fabrik + " · " + i.kategori));
      const tal = el("div", { class: "pg-tal" });
      const cell = (b, v) => el("div", {}, el("b", {}, b), el("span", {}, v));
      tal.append(cell("Köp max", i.kop_max ? "≤ " + kr(i.kop_max) : "köp inte"), cell("Sälj för", i.salj_max ? Math.round(i.salj_min).toLocaleString("sv-SE") + "–" + kr(i.salj_max) : "–"),
        cell("Min. vinst", marg != null ? (marg > 0 ? "+" : "") + kr(marg) : "–"));
      k.append(tal);
      if (i.anteckning) k.append(el("div", { class: "not" }, i.anteckning));
      k.append(el("div", { class: "not" }, (i.kanal ? i.kanal + " · " : "") + i.kalla));
      k.append(el("div", { class: "lankar" },
        el("a", { href: "https://www.google.com/search?tbm=isch&q=" + enc(i.namn + " " + fabrikAv(i)), target: "_blank", rel: "noopener" }, "Bilder"),
        el("a", { href: "https://www.tradera.com/search?q=" + enc(i.namn.split(",")[0] + " " + fabrikAv(i)), target: "_blank", rel: "noopener" }, "Tradera"),
        el("a", { href: "https://www.barnebys.se/search?q=" + enc(i.namn.split(",")[0]), target: "_blank", rel: "noopener" }, "Slutpriser")));
      return k;
    }));
    if (!rader.length) $("pg-lista").append(el("div", { class: "tom" }, el("div", { class: "stor" }, "Inget träffar"), el("p", {}, "Prova fabrik eller formgivare, t.ex. ”Lisa Larson” eller ”Rörstrand”."),
      el("div", { class: "rad" }, el("button", { class: "knapp", type: "button", onclick: () => { pg.q = ""; pg.kategori = ""; pg.rad = ""; $("pg-q").value = ""; renderPrisguide(lista); } }, "Visa allt"))));
  }
  const chip = (v, t, pa) => { const b = el("button", { class: "chip", type: "button", "data-v": v, "aria-pressed": "false" }, t); b.onclick = () => pa(v); return b; };
  App.del("prisguide", { namn: "Prisguide", ikon: "📖",
    async montera(sek) {
      sek.replaceChildren(App.huvud("prisguide", "Prisguide", ""),
        el("div", { class: "verktyg" },
          el("div", { class: "rad" }, el("input", { id: "pg-q", type: "search", placeholder: "Sök objekt, fabrik, formgivare …", "aria-label": "Sök" }), el("span", { class: "muted hoger", id: "pg-antal" })),
          el("div", { class: "chips", id: "pg-rad", style: "margin-top:6px" }),
          el("div", { class: "chips", id: "pg-kat" })),
        el("div", { class: "pg-lista", id: "pg-lista" }));
      sek.querySelector(".vy-huvud .sub").remove();
      $("pg-lista").append(el("div", { class: "laddar" }, "Hämtar prisguiden"));
      const lista = await hamta("prisguide");
      const kat = [...new Set(lista.map(i => i.kategori))];
      $("pg-rad").replaceChildren(...[["", "Alla råd"], ["köp", "✓ Köp"], ["kolla", "? Kolla"], ["undvik", "✕ Undvik"]].map(([v, t]) => chip(v, t, x => { pg.rad = x; renderPrisguide(lista); })));
      $("pg-kat").replaceChildren(...[["", "Alla kategorier"], ...kat.map(k => [k, k])].map(([v, t]) => chip(v, t, x => { pg.kategori = x; renderPrisguide(lista); })));
      $("pg-q").oninput = e => { pg.q = e.target.value; renderPrisguide(lista); };
      renderPrisguide(lista);
    },
  });

  // ── Stämplar ──────────────────────────────────────────────────────
  App.del("stamplar", { namn: "Stämplar", ikon: "🔍",
    async montera(sek) {
      sek.replaceChildren(App.huvud("stamplar", "Stämplar", "Vad betyder märket under föremålet?"),
        el("div", { class: "verktyg" }, el("div", { class: "rad" }, el("input", { id: "st-q", type: "search", placeholder: "Sök: tre kronor, hand, vågor, krona, rits, HAK …", "aria-label": "Sök stämpel" }), el("span", { class: "muted hoger", id: "st-antal" }))),
        el("div", { id: "st-lista" }, el("div", { class: "laddar" }, "Hämtar stämpelguiden")));
      const grupper = await hamta("stamplar");
      const render = () => {
        const q = App.norm($("st-q").value);
        let n = 0;
        $("st-lista").replaceChildren(...grupper.map(g => {
          const rader = g.rader.filter(r => !q || App.norm(r.stampel + " " + r.betyder + " " + g.fabrik).includes(q));
          if (!rader.length) return null;
          n += rader.length;
          return el("div", { class: "ruta" }, el("h3", {}, g.fabrik), el("table", {}, ...rader.map(r => el("tr", {}, el("td", {}, r.stampel), el("td", {}, r.betyder)))));
        }).filter(Boolean));
        $("st-antal").textContent = q ? n + " träffar" : grupper.reduce((a, g) => a + g.rader.length, 0) + " stämplar";
      };
      $("st-q").oninput = render; render();
    },
  });

  // ── Kalkyl ────────────────────────────────────────────────────────
  App.del("kalkyl", { namn: "Kalkyl", ikon: "🧮",
    montera(sek) {
      const kanaler = Object.entries(Logik.KANALER).map(([k, v]) => `<option value="${k}">${v.namn}</option>`).join("");
      sek.innerHTML = `
        <div class="vy-huvud" id="k-huvud"></div>
        <div class="kalkyl">
          <div class="ruta">
            <label>Inköp (kr)<input id="k-inkop" type="number" inputmode="numeric" value="100" min="0"></label>
            <label>Förväntat slutpris (kr) – kolla Tradera ”Avslutade”<input id="k-pris" type="number" inputmode="numeric" value="500" min="0"></label>
            <label>Kanal<select id="k-kanal">${kanaler}</select></label>
            <label>Timmar nedlagda (foto, annons, packning)<input id="k-timmar" type="number" inputmode="decimal" value="1" min="0.1" step="0.5"></label>
            <label>Köpregel<select id="k-regel"><option value="3">Köp max 1/3 av nettot (flipp)</option><option value="2">Köp max 1/2 av nettot (sällsynt)</option><option value="1.667">Köp max 60 % av nettot (samling)</option><option value="4">Köp max 1/4 av nettot (osäkert, långsamt)</option></select></label>
          </div>
          <div class="resultat" id="k-resultat"></div>
        </div>
        <div class="ruta" style="margin-top:14px"><h3>Avgifter per kanal vid <span id="k-prisrubrik"></span></h3><table id="k-kanaler"></table></div>
        <p class="muted" style="font-size:13px;margin-top:10px">Emballage 15 kr och svinn 2 % inräknat. Skatt tillkommer: köp-för-vidareförsäljning är näringsverksamhet.</p>`;
      const r = () => {
        const inkop = +$("k-inkop").value || 0, pris = +$("k-pris").value || 0, kanal = $("k-kanal").value, timmar = +$("k-timmar").value || 1, regel = +$("k-regel").value;
        const netto = Logik.channelNet(kanal, pris), vinst = netto - inkop, max = Math.max(0, Math.floor(netto / regel / 10) * 10);
        const rad = (b, v, cls) => el("div", { class: cls || "" }, el("b", {}, b), el("span", {}, v));
        $("k-resultat").replaceChildren(
          rad("Netto efter avgifter", kr(netto)), rad("Vinst", kr(vinst), "stor"), rad("Marginal", pris ? Math.round(vinst / pris * 100) + " %" : "–"),
          rad("Timlön", kr(vinst / timmar) + "/h"), rad("Köp max enligt regeln", kr(max)), rad("Avgift i kanalen", kr(Logik.avgift(kanal, pris))));
        $("k-prisrubrik").textContent = kr(pris);
        $("k-kanaler").replaceChildren(el("tr", {}, el("th", {}, "Kanal"), el("th", {}, "Avgift"), el("th", {}, "Netto"), el("th", {}, "Vinst")),
          ...Logik.bestChannel(pris, inkop).map(k => el("tr", {}, el("td", {}, k.namn), el("td", {}, kr(Logik.avgift(k.kanal, pris))), el("td", {}, kr(k.netto)), el("td", {}, kr(k.vinst)))));
      };
      $("k-huvud").replaceWith(App.huvud("kalkyl", "Kalkyl", "Vad får jag betala – och vad blir kvar?"));
      ["k-inkop", "k-pris", "k-kanal", "k-timmar", "k-regel"].forEach(id => $(id).addEventListener("input", r));
      r();
    },
  });

  // ── Säljplan ──────────────────────────────────────────────────────
  App.del("saljplan", { namn: "Säljplan", ikon: "📈",
    async montera(sek) {
      sek.innerHTML = `
        <div class="vy-huvud" id="sp-huvud"></div>
        <div class="saljplan-klass">
          <div class="ruta"><b class="pris">&lt; 300 kr</b>Tradera-auktion 7 dagar, utrop 1 kr (eller 49 kr), samfrakt. Marketplace/Blocket för avhämtning. Ingen prisstege.</div>
          <div class="ruta"><b class="pris">300–2 000 kr</b>Prisstege på Tradera: start +15 % över förväntat pris med ”ta emot bud”, sänk 10 % var ${Logik.STEG_DAGAR}:e dag ner till golvet 85 %. Därefter auktion med reservationspris eller paketera.</div>
          <div class="ruta"><b class="pris">&gt; 2 000 kr</b>Auktionshus: Bukowskis eller Auktionsverket online (17–17,5 % + 170 kr), eller Catawiki. Tradera bara med reservationspris på 85 %.</div>
        </div>
        <div class="ruta" style="margin-top:14px">
          <h3>Räkna på ett pris</h3>
          <div class="rad"><label class="rad-etikett">Förväntat pris (kr) <input id="sp-pris" type="number" inputmode="numeric" value="800" min="0"></label></div>
          <div id="sp-resultat" style="margin-top:10px"></div>
        </div>
        <div id="sp-checklista" style="margin-top:14px"></div>`;
      const r = () => {
        const plan = Logik.saljplan(+$("sp-pris").value || 0);
        const ut = $("sp-resultat"); ut.replaceChildren(el("p", {}, plan.text));
        if (plan.typ === "stege") {
          ut.append(el("div", { class: "stege" }, ...plan.steg.map((p, i) => el("span", { class: i === 0 ? "nu" : "" }, `Dag ${i * Logik.STEG_DAGAR}: ${kr(p)}`))));
          ut.append(el("p", { class: "muted", style: "margin-top:8px" }, `Netto på Tradera vid start ${kr(Logik.channelNet("tradera", plan.start))}, vid golv ${kr(Logik.channelNet("tradera", plan.golv))}.`));
        }
        if (plan.typ === "auktionshus") ut.append(el("p", { class: "muted" }, `Netto via Bukowskis ca ${kr(plan.netto)}, via Catawiki ${kr(Logik.channelNet("catawiki", plan.e))}.`));
      };
      $("sp-huvud").replaceWith(App.huvud("saljplan", "Säljplan", "Rätt kanal och rätt pris per prisklass"));
      $("sp-pris").oninput = r; r();
      const c = await hamta("checklista");
      $("sp-checklista").replaceChildren(...c.filter(x => x.rubrik !== "På loppisen").map(x => {
        const r2 = el("div", { class: "ruta" }, el("h3", {}, x.rubrik));
        if (x.tabell) r2.append(el("table", {}, ...x.tabell.map(rad => el("tr", {}, ...rad.map(c2 => el("td", {}, c2))))));
        else r2.append(el(x.numrerad ? "ol" : "ul", { style: "padding-left:20px;margin:0;color:var(--muted)" }, ...x.punkter.map(p => el("li", {}, p))));
        return r2;
      }));
    },
  });
})();
