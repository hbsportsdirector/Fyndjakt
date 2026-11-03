// Sälj: kvällens lista (en uppgift i taget, en knapp), pengarna och lagret. Allt som ligger i Till salu i samlingen.
// Regeln är: inga formulär. Appen säger vad som ska göras med just det här föremålet, du gör det, nästa.
(() => {
  "use strict";
  const { konto, el, kr, toast, $ } = App;
  const MINUTER = 30;
  const st = { allaUppgifter: false };
  let rot;
  const lista = () => konto.samling || [];
  const kanalNamn = k => (k === "blocket" ? "Blocket" : k === "tradera" ? "Tradera" : k || "");
  const forstaBild = it => ((it.bilder || [])[0] || {}).path || null;

  // ── Miniatyr (signerad bild ur bucketen) ────────────────────────────
  function bild(it) {
    const b = el("div", { class: "sj-bild" });
    const p = forstaBild(it);
    if (p) { const img = el("img", { alt: "" }); b.append(img); App.bildUrlar([p]).then(u => { if (u[p]) img.src = u[p]; }); }
    else b.append(el("span", { class: "ingen" }, "📷"));
    return b;
  }
  const oppna = it => { App.visa("samling"); App.oppnaForemal(it.id); };

  // ── En uppgift = ett kort med en knapp ───────────────────────────────
  function uppgiftKort(u) {
    const it = u.it, A = App.samling.saljAtgard(it, render);
    const k = el("div", { class: "sj-kort", "data-ankare": it.id });
    const huvud = el("div", { class: "sj-huvud" }, bild(it),
      el("div", { class: "sj-text" }, el("b", {}, it.namn), el("div", { class: "muted" }, [App.fjNr(it), u.e ? kr(u.e) : "inget pris", u.plan ? kanalNamn(u.plan.kanal) : ""].filter(Boolean).join(" · "))));
    huvud.onclick = () => oppna(it);
    k.append(huvud);
    const rad = el("div", { class: "sj-atgard" });
    const knapp = (text, fn, primar = true) => { const b = el("button", { class: "knapp" + (primar ? " primar" : ""), type: "button" }, text); b.onclick = e => { e.stopPropagation(); fn(b); }; return b; };
    const sag = t => el("p", { class: "sj-varfor" }, t);
    if (u.typ === "fota") {
      const har = (it.bilder || []).length, saknas = ["framsidan", "stämpeln/botten", "en detalj eller skada"].slice(har);
      rad.append(sag(`Har ${har} av ${Logik.KLAR_BILDER} bilder – saknas: ${saknas.join(", ")}.`), knapp("📷 Fota", () => A.bilder()));
    } else if (u.typ === "skriv") {
      rad.append(sag("Bilderna finns. Claude skriver katalogtext och annons utifrån dem."),
        knapp("✍ Låt Claude skriva annonsen", async b => { b.disabled = true; b.textContent = "Claude skriver …"; try { await A.annons(b); } finally { render(); } }));
    } else if (u.typ === "matt") {
      rad.append(sag("Annonsen är skriven men måtten saknas."), knapp("📏 Fyll i måtten", () => A.matt()));
    } else if (u.typ === "pris") {
      rad.append(sag("Inget pris att utgå från än."), knapp("Sätt pris", () => A.pris()));
    } else if (u.typ === "laggupp") {
      const p = u.plan;
      rad.append(sag(p ? `${p.kanalNamn}: ${p.kort}.` : "Sätt ett pris först."), knapp(p ? `📤 Lägg upp på ${kanalNamn(p.kanal)} – ${kr(p.start)}` : "Sätt pris", () => (p ? laggUppArk(u, A) : A.pris())));
    } else if (u.typ === "sank") {
      const l = u.plan.lage;
      rad.append(sag(`Dag ${l.dagar} på Blocket utan napp – dags att sänka från ${kr(l.pris)}.`),
        knapp(`✓ Jag har sänkt till ${kr(l.sank)}`, () => A.steg(l.bor, "blocket")));
    } else if (u.typ === "resultat") {
      const l = u.plan.lage;
      rad.append(sag(l.slut ? `Utropen på Tradera är slut (lägsta ${kr(u.plan.golv)}).` : `Auktionen på Tradera är över (utrop ${kr(l.pris)}). Gick den?`));
      const r2 = el("div", { class: "rad" }, knapp("✓ Såld", () => A.sald()));
      if (!l.slut) r2.append(knapp(`↻ Lägg om med utrop ${kr(l.sank)}`, () => A.steg(l.bor, "tradera"), false));
      else r2.append(knapp("Prova Blocket i stället", () => A.bytKanal("blocket"), false), knapp("Behåll den", () => A.behall(), false));
      rad.append(r2);
    } else if (u.typ === "byt") {
      rad.append(sag(`Golvet på Blocket är nått (${kr(u.plan.golv)}) utan napp.`),
        el("div", { class: "rad" }, knapp("✓ Såld", () => A.sald()), knapp("Prova Tradera-auktion", () => A.bytKanal("tradera"), false), knapp("Behåll den", () => A.behall(), false)));
    }
    k.append(rad);
    return k;
  }

  // Lägg upp: allt du behöver för att skapa annonsen, med kopiera-knappar – och sedan "Upplagd".
  function laggUppArk(u, A) {
    const it = u.it, p = u.plan;
    const kop = (text, etik) => { const b = el("button", { class: "knapp liten", type: "button" }, "Kopiera " + etik); b.onclick = () => App.samling.kopiera(text, b); return b; };
    const block = (etik, text) => el("div", { class: "textblock" }, el("div", { class: "textblock-huvud" }, el("b", {}, etik), kop(text, etik.toLowerCase())), el("div", { class: "textblock-text" }, text));
    const inneh = el("div", { class: "sj-ark" },
      el("p", {}, el("b", {}, p.kanalNamn), " · ", p.stegNamn, " ", el("b", {}, kr(p.start)), el("span", { class: "muted" }, p.kanal === "tradera" ? " · 7 dagar · frakt av – köparen hämtar" : " · skriv att den hämtas och inte skickas")),
      block("Rubrik", it.annons_rubrik || it.namn),
      block("Annons", it.annons_text || ""),
      el("p", { class: "muted", style: "font-size:13px" }, p.text),
      el("div", { class: "rad knappar-rad" },
        el("button", { class: "knapp primar", type: "button", onclick: () => { ark.stang(); A.upplagd(); } }, "📤 Jag har lagt upp den"),
        el("button", { class: "knapp", type: "button", onclick: () => { ark.stang(); A.bytKanal(p.annanKanal); } }, "Byt till " + kanalNamn(p.annanKanal)),
        el("button", { class: "knapp", type: "button", onclick: () => ark.stang() }, "Inte nu")));
    const ark = App.sheet("Lägg upp " + it.namn, inneh);
  }

  // ── Lagret: en rad per föremål, med läge och nästa steg ──────────────
  const LAGE = { resultat: "auktion slut", sank: "sänk", byt: "golvet nått", laggupp: "klar att lägga upp", pris: "saknar pris", fota: "saknar bilder", skriv: "saknar annons", matt: "saknar mått", ute: "ute" };
  function lagerRad(u) {
    const it = u.it, l = u.plan && u.plan.lage;
    const text = u.typ === "ute" ? `dag ${l.dagar} på ${kanalNamn(u.plan.kanal)} för ${kr(l.pris)}${l.nasta != null ? ", nästa steg om " + l.nasta + " d" : ""}`
      : u.typ === "resultat" ? `auktionen slut – såld, eller lägg om med ${kr(u.pris)}` : u.typ === "sank" ? `dag ${l.dagar} – sänk till ${kr(u.pris)}` : LAGE[u.typ];
    const r = el("button", { class: "sj-rad", type: "button", "data-ankare": "lager-" + it.id }, bild(it),
      el("div", { class: "sj-text" }, el("b", {}, it.namn), el("div", { class: "muted" }, text)),
      el("div", { class: "sj-pris" }, u.e ? kr(u.e) : "–", el("span", { class: "steg-pill " + (u.typ === "ute" || u.typ === "resultat" || u.typ === "sank" || u.typ === "byt" ? "upplagd" : u.typ === "laggupp" ? "klar" : "fixa") }, u.typ === "ute" ? "Ute" : u.typ === "laggupp" ? "Klar" : ["resultat", "sank", "byt"].includes(u.typ) ? "Ute" : "Att fixa")));
    r.onclick = () => oppna(it);
    return r;
  }

  function render() {
    if (!rot || !$("sj-ikvall")) return;
    const alla = Logik.saljUppgifter(lista());
    const kvall = Logik.kvallensLista(alla, MINUTER);
    const p = Logik.saljPengar(lista());
    $("sj-antal").textContent = `${p.vantar.antal + p.ute.antal} till salu · ${p.ute.antal} ute · ${kr(p.vantar.varde + p.ute.begart)}`;
    // Ikväll
    const ik = $("sj-ikvall"); ik.replaceChildren();
    const visa = st.allaUppgifter ? alla.filter(u => u.typ !== "ute") : kvall.lista;
    ik.append(el("div", { class: "avsnitt-rubrik" }, el("h3", {}, "Ikväll"), el("span", {}, visa.length ? `${visa.length} saker · ca ${visa.reduce((n, u) => n + u.minuter, 0)} min` : "")));
    if (!visa.length) ik.append(el("div", { class: "ruta sj-tom" }, p.ute.antal ? "Inget att göra just nu – allt som är klart ligger ute. Kom tillbaka när en auktion är slut eller det är dags att sänka."
      : "Inget till salu än. Flytta något till Till salu i Samlingen, eller markera ett köp som ”sälja”."));
    for (const u of visa) ik.append(uppgiftKort(u));
    if (!st.allaUppgifter && kvall.kvar > 0) ik.append(el("button", { class: "knapp visa-fler", type: "button", onclick: () => { st.allaUppgifter = true; render(); } }, `Visa resten (${kvall.kvar} till)`));
    else if (st.allaUppgifter && kvall.kvar > 0) ik.append(el("button", { class: "knapp visa-fler", type: "button", onclick: () => { st.allaUppgifter = false; render(); } }, "Visa bara kvällens"));
    // Pengarna
    const pe = $("sj-pengar"); pe.replaceChildren();
    const post = (t, v, under) => el("div", { class: "sj-post" }, el("span", { class: "etik" }, t), el("b", {}, v), under ? el("small", {}, under) : null);
    const man = new Date().toLocaleDateString("sv-SE", { month: "long" });
    pe.append(post(man.charAt(0).toUpperCase() + man.slice(1), kr(p.manad.vinst), `${p.manad.antal} sålda för ${kr(p.manad.salt)}`),
      post("I år", kr(p.ar.vinst), `${p.ar.antal} sålda för ${kr(p.ar.salt)} · avgifter ${kr(p.ar.avgift)}`),
      post("Ute nu", kr(p.ute.begart), `${p.ute.antal} annonser`),
      post("Väntar", kr(p.vantar.varde), `${p.vantar.antal} saker att göra klara`));
    // Lagret
    const la = $("sj-lager"); la.replaceChildren();
    la.append(el("div", { class: "avsnitt-rubrik" }, el("h3", {}, "Lagret"), el("span", {}, alla.length + " st")));
    const ordning = { ute: 0, resultat: 0, sank: 0, byt: 0, laggupp: 1, pris: 2, fota: 2, skriv: 2, matt: 2 };
    for (const u of [...alla].sort((a, b) => ordning[a.typ] - ordning[b.typ] || (b.e || 0) - (a.e || 0))) la.append(lagerRad(u));
    if (!alla.length) la.append(el("div", { class: "muted" }, "Tomt."));
    App.rakna("salj", kvall.lista.length || "");
    App.renderKlar("salj");
  }

  App.del("salj", { namn: "Sälj", ikon: "🏷️",
    montera(sek) {
      rot = sek;
      sek.replaceChildren();
      const h = App.huvud("salj", "Sälj", "");
      h.querySelector(".sub").id = "sj-antal";
      sek.append(h, el("div", { id: "sj-ikvall" }), el("div", { class: "sj-pengar", id: "sj-pengar" }), el("div", { id: "sj-lager" }));
      render();
    },
    visa() { if (rot) render(); },
  });
  App.pa("samling-andrad", () => { if (rot && rot.classList.contains("aktiv")) render(); else if (konto.samling) App.rakna("salj", Logik.kvallensLista(Logik.saljUppgifter(konto.samling), MINUTER).lista.length || ""); });
  App.pa("inloggad", () => { if (konto.samling) App.rakna("salj", Logik.kvallensLista(Logik.saljUppgifter(konto.samling), MINUTER).lista.length || ""); });
})();
