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
  // Kanalerna sorterade efter vinst (netto − inköp) vid försäljning till `varde`. Bäst först.
  // Blocket (0 %) räknas inte som standard – det är avhämtning utan köparskydd, inte en försäljningskanal att jämföra med.
  const JAMFORDA = ["tradera", "bukowskis", "auktionsverket", "catawiki"];
  function bestChannel(varde, inkop, kanaler) {
    inkop = +inkop || 0;
    const lista = (kanaler || JAMFORDA).map(k => ({
      kanal: k, namn: KANALER[k].namn, netto: Math.round(channelNet(k, varde)),
      vinst: Math.round(channelNet(k, varde) - inkop),
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
    const d = Math.floor(((nu || Date.now()) - new Date(upplagd).getTime()) / 86400000);
    const sista = stege.steg.length - 1;
    const bor = Math.min(sista, Math.max(0, Math.floor(d / STEG_DAGAR)));
    const a = Math.min(sista, Math.max(0, +stegSatt || 0));
    return { dagar: d, satt: a, bor, pris: stege.steg[a], sank: bor > a ? stege.steg[bor] : null,
             nasta: a < sista && bor <= a ? STEG_DAGAR * (a + 1) - d : null,
             slut: a === sista && d >= STEG_DAGAR * stege.steg.length };
  }

  function saljplan(forvantat, lage) {
    const e = +forvantat;
    if (!e) return { typ: "okand", text: "Sätt ett förväntat pris först." };
    if (e < 300) return { typ: "auktion", e, text: `Under 300 kr: Tradera-auktion 7 dagar, utrop 1 kr${e >= 150 ? " (eller 49 kr)" : ""}. Ingen prisstege – marknaden hittar priset på en vecka.` };
    if (e > 2000) return { typ: "auktionshus", e, netto: Math.round(channelNet("bukowskis", e)),
      text: `Över 2 000 kr: lämna till Bukowskis eller Auktionsverket (17–17,5 % + 170 kr), eller Catawiki. Tradera bara med reservationspris på ${kr(Math.round(e * STEG_GOLV))}.` };
    const stege = prisstege(e);
    const nu = lage ? stegeLage(stege, lage.upplagd, lage.steg_satt, lage.nu) : null;
    return { typ: "stege", e, ...stege, lage: nu,
      text: `300–2 000 kr: köp nu på ${kr(stege.start)} med "ta emot bud", sänk 10 % var ${STEG_DAGAR}:e dag ner till golvet ${kr(stege.golv)}. Därefter auktion med reservationspris eller paketera.` };
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
  // Värdet på ett föremål: auktionsmedianen, annars mitten av min egen bedömning, annars mitten av marknaden.
  function mitt(a, b) { return a != null || b != null ? Math.round(((a ?? b) + (b ?? a)) / 2) : null; }
  function varde(it) {
    const v = it.auk_median ?? mitt(it.uppskattat_min, it.uppskattat_max) ?? mitt(it.marknad_min, it.marknad_max);
    return v == null ? null : v * Math.max(1, +it.antal || 1);
  }
  // Det pris man väntar sig få vid försäljning: Tradera-priset om satt, annars värdet per styck.
  function forvantat(it) {
    if (it.tradera_pris != null) return +it.tradera_pris;
    const v = varde(it);
    return v == null ? null : Math.round(v / Math.max(1, +it.antal || 1));
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

  const Logik = { KANALER, avgift, channelNet, bestChannel, koptak, butikBesked, prisstege, stegeLage, saljplan, nice,
                  slutarSnart, bradskande, tidKvar, tidText, kvot, varde, forvantat, sammanstallning, kr,
                  STEG_DAGAR, KOPTAK_FLIPP, KOPTAK_SAMLING };
  if (typeof module !== "undefined" && module.exports) module.exports = Logik;
  else rot.Logik = Logik;
})(typeof window !== "undefined" ? window : globalThis);
