// Ren logik som delas av sajtens delar och testas i tests/test_logik.py (körs med node).
// Inga DOM-anrop här – bara funktioner på tal och listor.
(function (rot) {
  "use strict";

  // ── Kanaler och avgifter ───────────────────────────────────────────
  const KANALER = {
    tradera:    { namn: "Tradera",              avgift: p => Math.min(200, Math.max(3, p * 0.10)) },
    blocket:    { namn: "Blocket / Marketplace", avgift: () => 0 },
    bukowskis:  { namn: "Bukowskis",            avgift: p => p * 0.175 + 170 + p * 0.0195 },
    auktionsverket: { namn: "Auktionsverket",   avgift: p => p * 0.17 + 170 + p * 0.0175 },
    catawiki:   { namn: "Catawiki",             avgift: p => p * 0.125 + 10 },
  };
  const EMBALLAGE = 15;   // kr per försäljning
  const SVINN = 0.02;     // andel av priset som går bort i fraktskador och strul

  function avgift(kanal, pris) {
    const k = KANALER[kanal];
    return k ? k.avgift(pris) : 0;
  }
  // Vad man får ut av en försäljning till priset `pris` i kanalen, efter avgift, emballage och svinn.
  function channelNet(kanal, pris) {
    pris = +pris || 0;
    return pris - avgift(kanal, pris) - EMBALLAGE - pris * SVINN;
  }
  // Vi säljer bara med avhämtning (ingen frakt): då försvinner emballage och fraktsvinn – kvar är bara avgiften.
  function nettoHamtning(kanal, pris) {
    pris = +pris || 0;
    return pris - avgift(kanal, pris);
  }
  // Kanalerna sorterade efter vinst (netto − inköp) vid försäljning till `varde`. Bäst först.
  // Vi säljer på Tradera och Blocket, med avhämtning.
  const JAMFORDA = ["tradera", "blocket"];
  function bestChannel(varde, inkop, kanaler) {
    inkop = +inkop || 0;
    const lista = (kanaler || JAMFORDA).map(k => ({
      kanal: k, namn: KANALER[k].namn, netto: Math.round(nettoHamtning(k, varde)),
      vinst: Math.round(nettoHamtning(k, varde) - inkop),
    }));
    lista.sort((a, b) => b.vinst - a.vinst);
    return lista;
  }

  // ── Köptak i butiken ───────────────────────────────────────────────
  // Flipp: köp max en tredjedel av typiskt slutpris (som Fyndjakts kop_max). Passar föremålet min smak är det
  // samling, inte flipp – då får det kosta 60 %.
  const KOPTAK_FLIPP = 0.33, KOPTAK_SAMLING = 0.6;
  function koptak(median, passarSmak) {
    if (!median) return { tak: null, faktor: null, regel: "" };
    const faktor = passarSmak ? KOPTAK_SAMLING : KOPTAK_FLIPP;
    return { tak: Math.floor(median * faktor), faktor,
             regel: passarSmak ? "samling: 60 % av typiskt slutpris" : "flipp: en tredjedel av typiskt slutpris" };
  }

  // Beskedet i butiken: KÖP / KÖP INTE / FOTA STÄMPELN FÖRST.
  // r = {marknad_min, marknad_max, median, sakerhet (0–1), nyproduktion, varning, passar_smak}, pris = vad det kostar,
  // harStampel = om en stämpelbild skickats.
  const OSAKER = 0.45;
  function butikBesked(r, pris, harStampel) {
    r = r || {};
    const median = r.median || ((r.marknad_min != null && r.marknad_max != null) ? Math.round((+r.marknad_min + +r.marknad_max) / 2) : null);
    const tak = koptak(median, !!r.passar_smak);
    const sak = +r.sakerhet || 0;
    const ut = { median, ...tak, sakerhet: sak };
    if (r.nyproduktion) return { ...ut, besked: "KÖP INTE", klass: "nej", skal: "Nyproduktion" + (r.varning ? " – " + r.varning : "") };
    if (sak < OSAKER && !harStampel) return { ...ut, besked: "FOTA STÄMPELN FÖRST", klass: "kanske",
      skal: `För osäkert (${Math.round(sak * 100)} %) för ett besked` };
    if (!median) return { ...ut, besked: "KÖP INTE", klass: "nej", skal: "Inget andrahandsvärde att räkna på" };
    if (pris == null || pris === "") return { ...ut, besked: "KÖP UNDER " + kr(tak.tak), klass: "vanta", skal: "Skriv in priset" };
    pris = +pris;
    if (pris <= tak.tak) {
      const b = bestChannel(median, pris)[0];
      return { ...ut, besked: "KÖP", klass: "ja", skal: `${tak.regel} · bäst via ${b.namn}, netto ${kr(b.netto)}, vinst ca ${kr(b.vinst)}`
        + (r.varning ? " · ⚠ " + r.varning : ""), kanal: b };
    }
    return { ...ut, besked: "KÖP INTE", klass: "nej", skal: `Max ${kr(tak.tak)} (${tak.regel})` + (r.varning ? " · ⚠ " + r.varning : "") };
  }

  // ── Fyndjakts "köp max" (samma räkning som flipp.py) ──────────────
  // Sälj via ett auktionshus på Auctionet: netto = slutpris − 20 % − 100 kr. Köp max = högst halva nettot (och minst
  // 300 kr vinst), minus frakt, delat med köparprovisionen där köpet görs.
  const FLIPP = { saljProvision: 0.20, saljAvgift: 100, kvot: 0.5, minVinst: 300,
                  kopProvision: { auctionet: 0.25, bukowskis: 0.25 }, frakt: { tradera: 80 } };
  function flippRakning(slutpris, kalla) {
    if (!slutpris) return null;
    const netto = slutpris * (1 - FLIPP.saljProvision) - FLIPP.saljAvgift;
    const halva = netto * FLIPP.kvot, tak = Math.min(halva, netto - FLIPP.minVinst);
    const frakt = FLIPP.frakt[kalla] || 0, prov = FLIPP.kopProvision[kalla] || 0;
    const kopMax = Math.trunc((tak - frakt) / (1 + prov));
    return { slutpris, netto: Math.round(netto), tak: Math.round(tak), halva: tak === halva, frakt, prov,
             efterFrakt: Math.trunc(tak - frakt), kopMax: kopMax > 0 ? kopMax : null };
  }

  // ── Säljplan och prisstege ─────────────────────────────────────────
  // < 300 kr → auktion från 1 kr. 300–2 000 kr → prisstege: start +15 % över förväntat, −10 % var 10:e dag,
  // golv 85 %. > 2 000 kr → auktionshus.
  const STEG_DAGAR = 10, STEG_START = 1.15, STEG_SANK = 0.9, STEG_GOLV = 0.85;
  const nice = n => n < 1000 ? Math.max(45, Math.round(n / 50) * 50 - 5) : Math.round(n / 100) * 100 - 5;

  function prisstege(forvantat) {
    const start = nice(forvantat * STEG_START), golv = nice(forvantat * STEG_GOLV);
    const steg = [start];
    let p = start;
    for (let k = 0; k < 8; k++) {
      const nx = nice(p * STEG_SANK);
      if (nx <= golv || nx >= p) break;
      steg.push(nx); p = nx;
    }
    if (steg[steg.length - 1] > golv) steg.push(golv);
    return { start, golv, steg };
  }

  // Var i stegen är vi? upplagd = ISO-tid, stegSatt = index på steget som faktiskt ligger ute, nu = ms.
  function stegeLage(stege, upplagd, stegSatt, nu) {
    if (!upplagd) return null;
    const dg = stege.dagar || STEG_DAGAR;
    const d = Math.floor(((nu || Date.now()) - new Date(upplagd).getTime()) / 86400000);
    const sista = stege.steg.length - 1;
    const bor = Math.min(sista, Math.max(0, Math.floor(d / dg)));
    const a = Math.min(sista, Math.max(0, +stegSatt || 0));
    return { dagar: d, satt: a, bor, pris: stege.steg[a], sank: bor > a ? stege.steg[bor] : null,
             nasta: a < sista && bor <= a ? dg * (a + 1) - d : null,
             slut: a === sista && d >= dg * stege.steg.length };
  }

  // Säljplan med avhämtning: Blocket (överpris som sänks) eller Tradera (auktion med utrop som sänks vid omläggning).
  const SALJ_DAGAR = 7;
  function nedtrappning(start, faktor, golv) {
    const steg = [start];
    let p = start;
    for (let k = 0; k < 8; k++) {
      const nx = nice(p * faktor);
      if (nx <= golv || nx >= p) break;
      steg.push(nx); p = nx;
    }
    if (steg[steg.length - 1] > golv) steg.push(golv);
    return steg;
  }
  function blocketPlan(e) {
    const start = nice(e * 1.25), golv = nice(e * 0.85), steg = nedtrappning(start, 0.9, golv);
    return { typ: "stege", e, kanal: "blocket", kanalNamn: "Blocket – avhämtning", start, golv, steg, dagar: SALJ_DAGAR, stegNamn: "Pris",
      netto: start, nettoSteg: steg.map(p => Math.round(nettoHamtning("blocket", p))),
      kort: `begär ${kr(start)} (överpris – räkna med prut), sänk 10 % i veckan ner till ${kr(golv)}`,
      text: `Lägg ut på Blocket för ${kr(start)} – med marginal för prut – och skriv att den hämtas. Sänk 10 % var ${SALJ_DAGAR}:e dag ner till ${kr(golv)}. Ingen avgift.` };
  }
  function traderaPlan(e) {
    const start = nice(e * 0.8), golv = nice(e * 0.5), steg = nedtrappning(start, 0.85, golv);
    return { typ: "stege", e, kanal: "tradera", kanalNamn: "Tradera – auktion, avhämtning", start, golv, steg, dagar: SALJ_DAGAR, stegNamn: "Utrop",
      netto: Math.round(nettoHamtning("tradera", e)), nettoSteg: steg.map(p => Math.round(nettoHamtning("tradera", p))),
      kort: `auktion 7 dagar med utrop ${kr(start)} och avhämtning, lägg om med 15 % lägre utrop om den blir osåld`,
      text: `Tradera-auktion 7 dagar med utropspris ${kr(start)}, frakt avstängd – köparen hämtar. Blir den osåld: lägg upp igen med 15 % lägre utrop, ner till ${kr(golv)}. Tradera tar 10 % (högst 200 kr).` };
  }
  // Vilken kanal? Billigt, möbler och lampor: Blocket (lokala köpare, ingen avgift). Samlarobjekt från ca 400 kr: Tradera
  // (samlarna söker där och budgivningen hittar priset). info.kanal ("blocket"/"tradera") går före – Claudes eller ditt val.
  const TRADERA_FRAN = 400;
  function rekommenderadKanal(e, info) {
    info = info || {};
    if (info.kanal === "blocket" || info.kanal === "tradera") return { kanal: info.kanal, varfor: info.kanal_varfor || "ditt val" };
    if (/Möbler|Belysning/.test(info.kategori || "")) return { kanal: "blocket", varfor: "stort att hämta – lokala köpare på Blocket" };
    if (e < TRADERA_FRAN) return { kanal: "blocket", varfor: `under ${kr(TRADERA_FRAN)} – ingen avgift och snabb affär lokalt` };
    return { kanal: "tradera", varfor: "samlarobjekt – budgivningen på Tradera hittar rätt pris" };
  }

  function saljplan(forvantat, lage, info) {
    const e = +forvantat;
    if (!e) return { typ: "okand", text: "Sätt ett förväntat pris först." };
    const r = rekommenderadKanal(e, info);
    const val = r.kanal === "blocket" ? blocketPlan(e) : traderaPlan(e);
    const annan = r.kanal === "blocket" ? traderaPlan(e) : blocketPlan(e);
    const nu = lage ? stegeLage(val, lage.upplagd, lage.steg_satt, lage.nu) : null;
    return { ...val, lage: nu, varfor: r.varfor, annanKanal: annan.kanal, alternativ: `${annan.kanalNamn}: ${annan.kort}.` };
  }

  // ── Fynd: slutar snart ─────────────────────────────────────────────
  const TIM = 3600;
  function tidKvar(p, nu) { return p.slutar_ts ? p.slutar_ts - (nu || Date.now() / 1000) : null; }
  function kvot(p) { return p.pris && p.jmf_median ? p.pris / p.jmf_median : null; }
  // Alla aktiva fynd som slutar inom 24 h, först det som slutar först.
  function slutarSnart(poster, nu, timmar) {
    const grans = (timmar || 24) * TIM;
    return (poster || []).filter(p => { const t = tidKvar(p, nu); return t != null && t >= 0 && t < grans; })
      .sort((a, b) => a.slutar_ts - b.slutar_ts);
  }
  // Röd banner: ≤ 6 h kvar och (betyg ≥ 8 eller kvot ≤ 0,5).
  function bradskande(poster, nu) {
    return slutarSnart(poster, nu, 6).filter(p => (+p.betyg || 0) >= 8 || (kvot(p) != null && kvot(p) <= 0.5));
  }
  function tidText(sek) {
    if (sek == null) return "";
    if (sek < 0) return "avslutad";
    const m = Math.floor(sek / 60);
    if (m < 60) return m + " min";
    const h = Math.floor(m / 60);
    if (h < 24) return h + " h " + (m % 60) + " min";
    const d = Math.floor(h / 24);
    return d + " d " + (h % 24) + " h";
  }

  // ── Samlingens värde ───────────────────────────────────────────────
  // Värdet på ett föremål: auktionsmedianen (omvärderas mot Auctionet), annars mitten av Claudes uppskattning,
  // (uppskattat_min/max används inte längre – de gamla uppskattningarna raderades 2026-10-30.)
  function mitt(a, b) { return a != null || b != null ? Math.round(((a ?? b) + (b ?? a)) / 2) : null; }
  function varde(it) {
    // Värdet gäller hela posten – ett parti om 60 delar har ett värde för alla 60, inte per del.
    return it.auk_median ?? mitt(it.marknad_min, it.marknad_max);
  }
  // Det pris man väntar sig få vid försäljning: Tradera-priset om satt, annars värdet per styck.
  function forvantat(it) {
    if (it.tradera_pris != null) return +it.tradera_pris;
    const v = varde(it);
    return v == null ? null : Math.round(v / Math.max(1, +it.antal || 1));
  }
  // Till salu: vad som saknas innan annonsen kan läggas ut. steg = fixa → klar → upplagd.
  const KLAR_BILDER = 3;
  function saljKlar(it) {
    const bilder = (it.bilder || []).length;
    const annons = String(it.annons_text || "").trim();
    const krav = [
      { id: "bilder", ok: bilder >= KLAR_BILDER, text: `Bilder ${Math.min(bilder, KLAR_BILDER)}/${KLAR_BILDER}`, tips: "framsida, stämpel/botten och en detalj eller eventuell skada" },
      { id: "annons", ok: annons.length >= 60 && !!String(it.annons_rubrik || "").trim(), text: "Annons", tips: "rubrik och text" },
      { id: "matt", ok: !!annons && !/\[\s*mått\s*\]/i.test(annons), text: "Mått", tips: "höjd och bredd/diameter i annonsen" },
      { id: "pris", ok: !!forvantat(it), text: "Pris", tips: "utgångspris eller värde" },
    ];
    const saknas = krav.filter(k => !k.ok);
    return { krav, saknas, alla: !saknas.length, steg: it.upplagd ? "upplagd" : it.klar ? "klar" : "fixa" };
  }
  // Mått in i texten: "[mått]" byts ut, annars läggs en rad till.
  function sattMatt(text, matt) {
    const t = String(text || "");
    if (!matt) return t;
    return /\[\s*mått\s*\]/i.test(t) ? t.replace(/\[\s*mått\s*\]/gi, matt) : (t ? t.replace(/\s*$/, "") + "\n" : "") + "Mått: " + matt + ".";
  }

  // ── Sälj: kvällens lista, pengarna och lagret ──────────────────────
  // En uppgift per föremål i Till salu, närmast pengarna först: svara på en avslutad auktion, sänka priset, byta kanal,
  // lägga upp, sätta pris, fota, skriva, mått. Varje uppgift har en uppskattad tid i minuter så att en kväll kan planeras.
  const UPPGIFT_MIN = { resultat: 1, sank: 2, byt: 2, laggupp: 5, pris: 1, fota: 5, skriv: 2, matt: 2, ute: 0 };
  const PRIO = { resultat: 1, sank: 2, byt: 3, laggupp: 4, pris: 5, fota: 6, skriv: 7, matt: 8, ute: 9 };
  function saljUppgifter(lista, nu) {
    nu = nu || Date.now();
    const ut = [];
    for (const it of lista || []) {
      if (it.lada !== "salj") continue;
      const e = forvantat(it), k = saljKlar(it);
      const info = { kategori: it.kategori, kanal: it.kanal, kanal_varfor: it.kanal_varfor };
      let u;
      if (it.upplagd && e) {
        const plan = saljplan(e, { upplagd: it.upplagd, steg_satt: it.steg_satt, nu }, info), l = plan.lage;
        if (plan.kanal === "tradera" && (l.sank != null || l.slut)) u = { typ: "resultat", plan, pris: l.sank };   // auktionen är slut: såld, eller lägg om
        else if (l.sank != null) u = { typ: "sank", plan, pris: l.sank };
        else if (l.slut) u = { typ: "byt", plan };
        else u = { typ: "ute", plan };                                                                           // ligger ute – inget att göra än
      } else if (k.alla || it.klar) u = { typ: "laggupp", plan: e ? saljplan(e, null, info) : null };
      else {
        const saknas = k.saknas.map((x) => x.id);
        u = { typ: saknas.includes("pris") ? "pris" : saknas.includes("bilder") ? "fota" : saknas.includes("annons") ? "skriv" : "matt", saknas, krav: k.krav };
      }
      ut.push({ ...u, it, e, prio: PRIO[u.typ], minuter: UPPGIFT_MIN[u.typ] });
    }
    return ut.sort((a, b) => a.prio - b.prio || (b.e || 0) - (a.e || 0));
  }
  // Kvällens lista: uppgifterna som ryms i `minuter` (standard 30), i prioritetsordning. Minst en om det finns någon.
  function kvallensLista(uppgifter, minuter) {
    const tak = minuter || 30, ut = [];
    let summa = 0;
    for (const u of uppgifter || []) {
      if (u.typ === "ute") continue;
      if (ut.length && summa + u.minuter > tak) break;
      ut.push(u); summa += u.minuter;
    }
    return { lista: ut, minuter: summa, kvar: (uppgifter || []).filter((u) => u.typ !== "ute").length - ut.length };
  }
  // Pengarna: sålt, inköp, avgifter och vinst för månaden och året, plus vad som ligger ute och vad som väntar.
  function saljPengar(lista, nu) {
    const d = new Date(nu || Date.now()), manad = d.toISOString().slice(0, 7), ar = d.toISOString().slice(0, 4);
    const tom = () => ({ antal: 0, salt: 0, inkop: 0, avgift: 0, vinst: 0 });
    const ut = { manad: tom(), ar: tom(), ute: { antal: 0, begart: 0 }, vantar: { antal: 0, varde: 0 } };
    for (const it of lista || []) {
      if (it.lada === "salt" && it.salt_for != null) {
        const p = +it.salt_for || 0, a = avgift(it.salt_kanal || "tradera", p), dat = String(it.salt_datum || "");
        for (const [k, pre] of [["manad", manad], ["ar", ar]]) {
          if (!dat.startsWith(pre)) continue;
          const m = ut[k]; m.antal += 1; m.salt += p; m.inkop += +it.inkopspris || 0; m.avgift += a; m.vinst = m.salt - m.inkop - m.avgift;
        }
      } else if (it.lada === "salj") {
        const e = forvantat(it) || 0;
        if (it.upplagd && e) {
          const plan = saljplan(e, { upplagd: it.upplagd, steg_satt: it.steg_satt, nu: nu || Date.now() }, { kategori: it.kategori, kanal: it.kanal });
          ut.ute.antal += 1; ut.ute.begart += plan.lage ? plan.lage.pris : e;
        } else { ut.vantar.antal += 1; ut.vantar.varde += e; }
      }
    }
    return ut;
  }

  function sammanstallning(lista) {
    const ut = {};
    for (const it of lista || []) {
      const l = ut[it.lada] || (ut[it.lada] = { antal: 0, varde: 0, inkopt: 0, salt: 0 });
      l.antal += 1;
      l.varde += varde(it) || 0;
      l.inkopt += +it.inkopspris || 0;
      l.salt += +it.salt_for || 0;
    }
    if (ut.salt) ut.salt.vinst = ut.salt.salt - ut.salt.inkopt;
    return ut;
  }

  function kr(n) { return n == null || isNaN(n) ? "–" : Math.round(n).toLocaleString("sv-SE") + " kr"; }

  const Logik = { KANALER, avgift, channelNet, bestChannel, koptak, butikBesked, flippRakning, prisstege, stegeLage, saljplan, nice,
                  slutarSnart, bradskande, tidKvar, tidText, kvot, varde, forvantat, saljKlar, nettoHamtning, rekommenderadKanal, SALJ_DAGAR, sattMatt, KLAR_BILDER, sammanstallning, kr,
                  saljUppgifter, kvallensLista, saljPengar,
                  STEG_DAGAR, KOPTAK_FLIPP, KOPTAK_SAMLING };
  if (typeof module !== "undefined" && module.exports) module.exports = Logik;
  else rot.Logik = Logik;
})(typeof window !== "undefined" ? window : globalThis);
