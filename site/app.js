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
                  samling: [], harRedan: [], forslag: new Map() };
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
  // Kort besked nere i mitten. aktion = {text, onclick} ger en knapp (t.ex. Ångra) och visar beskedet längre.
  function toast(text, aktion) {
    document.querySelectorAll(".toast").forEach(t => t.remove());
    const t = el("div", { class: "toast", role: "status" }, text);
    if (aktion) t.append(el("button", { type: "button", onclick: () => { t.remove(); aktion.onclick(); } }, aktion.text));
    document.body.appendChild(t);
    clearTimeout(toastT); toastT = setTimeout(() => t.remove(), aktion ? 6000 : 2800);
  }
  function datum(d) { try { return new Date(d).toLocaleDateString("sv-SE", { day: "numeric", month: "short", year: "numeric" }); } catch (e) { return d; } }
  function idag() { return new Date().toISOString().slice(0, 10); }
  function slug(s) { return String(s || "").toLowerCase().replace(/[åä]/g, "a").replace(/ö/g, "o").replace(/ø/g, "o").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60); }
  // Löpnummer i samlingen: FJ-0001 … (kolumnen nummer, sätts av databasen).
  function fjNr(it) { return it && it.nummer ? "FJ-" + String(it.nummer).padStart(4, "0") : ""; }
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

  // Bottenark med stora val (mobil: underifrån, desktop: i mitten). val = [{ikon, text, under, onclick}] eller eget innehåll.
  function sheet(titel, innehall) {
    const bak = el("div", { class: "ark-bak" });
    const ark = el("div", { class: "ark", role: "dialog", "aria-modal": "true" }, el("div", { class: "handtag" }));
    if (titel) ark.append(el("h2", {}, titel));
    const stang = () => { bak.remove(); document.removeEventListener("keydown", esc_); };
    const esc_ = e => { if (e.key === "Escape") stang(); };
    if (Array.isArray(innehall)) {
      ark.append(el("div", { class: "val" }, ...innehall.map(v => {
        const b = el(v.label ? "label" : "button", { class: "knapp" + (v.primar ? " primar" : ""), type: v.label ? null : "button" },
          el("span", { class: "ikon" }, v.ikon || ""), el("span", { class: "txt" }, v.text, v.under ? el("small", {}, v.under) : null));
        if (v.label) { const inp = el("input", { type: "file", accept: "image/*", class: "dold", capture: v.capture || null, multiple: v.multiple ? "" : null }); inp.onchange = e => { stang(); v.onchange(e); }; b.append(inp); }
        else b.onclick = () => { stang(); v.onclick(); };
        return b;
      })));
    } else ark.append(...[innehall].flat());
    bak.append(ark);
    bak.addEventListener("click", e => { if (e.target === bak) stang(); });
    document.addEventListener("keydown", esc_);
    document.body.appendChild(bak);
    return { el: ark, stang };
  }

  // Hjälptexter per del – visas med ?-knappen i rubriken.
  const HJALP = {
    fynd: `<p><b>Vad är det här?</b> Fyndjakt letar varje natt igenom Auctionet, Bukowskis, Tradera, Myrorna och Stadsmissionen och visar det som passar dina bevakningar.</p>
      <p><b>Slutar snart</b> ligger alltid överst – det är de du måste ta ställning till i dag. Blir det riktigt bråttom (under 6 timmar, bra betyg eller lågt pris) dyker en röd rad upp överst på hela sajten.</p>
      <p><b>Siffrorna på kortet:</b> Pris nu är budet eller utropet. Köp max är vad du som mest bör betala för att kunna sälja med vinst. Typiskt är vad liknande klubbats för. Procenttalet uppe i hörnet är pris ÷ typiskt – under 50 % är fyndläge.</p>
      <p><b>Knapparna:</b> 👍/👎 lär appen din smak (👎 döljer kortet). <b>Äkta?</b> låter Claude titta på annonsens bilder efter tecken på nyproduktion. <b>Köpte den</b> frågar vad du betalade och om du ska behålla eller sälja – föremålet får ett FJ-nummer, bilderna följer med och Claude skriver beskrivning och säljannons.</p>`,
    samling: `<p><b>Lådorna</b> överst är samlingens delar – tryck på en för att bara se den. Siffran är antal föremål, raden under är deras uppskattade värde.</p>
      <p><b>＋ Nytt köp → Fota och identifiera</b> tar dig igenom fyra steg: fota föremålet, fota stämpeln (eller tryck ”Ingen stämpel”), Claude läser stämpeln och föreslår tillverkare, formgivare och serie – vill Claude se mer får du en knapp per bild, och du kan rätta (”det står UE, inte LE”). Till sist kollas formgivaren mot sålda exemplar på Auctionet. Du bekräftar fälten, fyller i köpet och sparar. Du får ett FJ-nummer och Claude skriver beskrivning och annons, precis som med 🛒 Köpt i Butik.</p>
      <p><b>Tryck på ett föremål</b> för att se allt om det. Där kan du redigera, lägga till bilder, flytta det till en annan låda, se prishistorik och – när det ligger i Till salu – följa prisstegen. <b>🗑 Ta bort</b> finns längst ner; är föremålet sålt är det bättre att flytta det till Sålt, så finns det kvar i vinststatistiken.</p>
      <p><b>Till salu</b> har tre steg: <b>Att fixa</b> → <b>Klara att lägga ut</b> → <b>Upplagda</b>. Öppna ett föremål så ser du en checklista – minst tre bilder (framsida, stämpel, detalj), annons, mått och pris – med en knapp för varje sak som saknas. När allt är bockat: <b>✓ Markera som klar</b>, och när annonsen ligger ute: <b>📤 Jag har lagt upp den nu</b> (då startar prisstegen). <b>＋ Bild</b> i bildraden lägger till fler bilder direkt.</p>
      <p><b>📖 Läs mer om pjäsen</b> i varje föremål: Claude skriver en faktaruta om formgivaren, serien och kännetecknen utifrån Wikipedia (källorna länkas), och det finns snabblänkar till sålda på Auctionet, DigitaltMuseum (svenska museers samlingar), Wikipedia och Google.</p>
      <p><b>FJ-nummer:</b> varje föremål har ett löpnummer (FJ-0001 …). Sök på numret för att hitta det. Under <b>✍ Skriv beskrivning och annons</b> skriver Claude en katalogtext och en färdig annons att kopiera till Tradera eller Blocket.</p>
      <p><b>Värde ca</b> är medianen av vad liknande sålts för på Auctionet. Samlingen omvärderas automatiskt en gång i månaden – står höjden i namnet ("höjd 25 cm") jämförs bara med föremål i samma storlek. Under <b>Underlag</b> ser du hur många som sålts, spannet och hur stor andel som gick osåld.</p>
      <p>Under <b>Värderat</b> står varifrån värdet kommer: ett datum om det är omvärderat mot Auctionet, annars "äldre värde – ej kontrollerat" och varför det inte omvärderats (för få sålda, parti, konst). Underlaget visar vilka sålda föremål värdet bygger på.</p>`,
    butik: `<p><b>Tre steg:</b> fota föremålet, fota gärna stämpeln (undersidan), skriv priset. Beskedet kommer av sig självt när båda finns.</p>
      <p><b>KÖP</b> = priset är under köptaket. Köptaket är en tredjedel av typiskt slutpris när du köper för att sälja, men 60 % när föremålet passar din smak (den du skrivit under Inställningar) – då är det samling, inte flipp.</p>
      <p><b>FOTA STÄMPELN FÖRST</b> betyder att Claude är för osäker på vad det är. <b>KÖP INTE</b> visar alltid varför – för dyrt, nyproduktion eller för lågt värde.</p>
      <p>Under beskedet ser du nettot per säljkanal och om något liknande redan finns i samlingen. <b>🛒 Köpt</b> sparar föremålet med bilderna: du anger pris, butik och om du ska behålla eller sälja. Det får ett FJ-nummer (skriv det på en lapp under föremålet) och Claude skriver beskrivning och säljannons att kopiera.</p>`,
    prisguide: `<p>En lista över vad vanliga loppisfynd brukar gå för, med råd: <b>Köp</b> (säljer med marginal), <b>Kolla</b> (beror på skick, variant eller stämpel) och <b>Undvik</b> (för lågt andrahandsvärde).</p>
      <p>Sök på objekt, fabrik eller formgivare. "Köp max" är högsta inköp som lämnar vinst när det säljs för det lägre priset på Tradera.</p>`,
    stamplar: `<p>Så daterar du och avslöjar nyproduktion på stämplar från Gustavsberg, Rörstrand, Arabia, Royal Copenhagen och Meissen. Sök på det du ser under föremålet – "tre kronor", "hand", "vågor", "krona".</p>`,
    kalkyl: `<p>Skriv in inköp, förväntat slutpris och kanal – kalkylen visar netto efter avgifter, vinst, marginal och timlön. Tabellen under jämför alla kanaler för samma pris.</p>`,
    saljplan: `<p>Rätt kanal och rätt pris efter prisklass: under 300 kr auktion från 1 kr, 300–2 000 kr prisstege på Tradera (start +15 %, sänk 10 % var tionde dag, golv 85 %), över 2 000 kr auktionshus. Samma stege används i Samlingens sälj-fält.</p>`,
    installningar: `<p><b>Samlingen:</b> smaken avgör köptaket i butiken, kanalen är förvald när du markerar något som sålt. <b>Bevakningar</b> styr vad Fyndjakt letar efter varje natt. <b>Min smak</b> visar vad appen lärt sig av dina 👍 och 👎.</p>`,
  };
  function hjalp(id) {
    const d = delar[id];
    const p = panel(el("div", { class: "hjalp-text" }, el("div", { class: "huvud" }, el("h2", {}, (d ? d.ikon + " " : "") + (d ? d.namn : "Hjälp")),
      el("button", { class: "knapp liten", type: "button", onclick: () => p.stang() }, "Stäng")), el("div", { html: HJALP[id] || "" })), { mitten: true });
  }
  // Rubrikraden i en vy, med ?-knapp. Returnerar elementet så att delen kan lägga till egna knappar.
  function huvud(id, titel, sub) {
    const h = el("div", { class: "vy-huvud" }, el("h2", {}, titel), el("span", { class: "sub" }, sub || ""));
    h.append(el("button", { class: "knapp hjalp", type: "button", "aria-label": "Hjälp om " + titel, onclick: () => hjalp(id) }, "?"));
    return h;
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
  // ── Kom tillbaka dit du var ──────────────────────────────────────
  // När man öppnar en annons i Chrome kan telefonen stänga appen i bakgrunden; då laddas den om från toppen.
  // Därför sparas platsen per vy: vilket kort som låg överst (data-ankare), hur långt ner, och vyns egna
  // uppgifter (t.ex. hur många fynd som visades, vilket föremål som var öppet). Gäller i sex timmar.
  const PLATS_NYCKEL = "fyndjakt-plats", PLATS_TID = 6 * 3600 * 1000;
  let platser = {};
  try { platser = JSON.parse(localStorage.getItem(PLATS_NYCKEL) || "{}") || {}; } catch (e) { platser = {}; }
  const vantarAterstall = new Set();
  function sparaPlats() {
    if (!aktiv || !konto.inloggad) return;
    const sek = document.querySelector(`.vy[data-vy="${aktiv}"]`); if (!sek) return;
    let ankare = null;
    for (const e of sek.querySelectorAll("[data-ankare]")) {
      const r = e.getBoundingClientRect();
      if (r.bottom > 70) { ankare = { id: e.dataset.ankare, top: Math.round(r.top) }; break; }
    }
    const d = delar[aktiv];
    const detalj = document.querySelector(".panel[data-detalj]");
    platser[aktiv] = { y: Math.round(window.scrollY), ankare, extra: d && d.plats ? d.plats() : null,
                       detalj: detalj ? detalj.dataset.detalj : null, t: Date.now() };
    try { localStorage.setItem(PLATS_NYCKEL, JSON.stringify(platser)); } catch (e) {}
  }
  function plats(id) { const p = platser[id]; return p && Date.now() - p.t < PLATS_TID ? p : null; }
  // Anropas av vyerna när listan är ritad. Returnerar true när platsen är återställd (eller inget fanns).
  function renderKlar(id) {
    if (!vantarAterstall.has(id) || id !== aktiv) return;
    const p = plats(id);
    if (!p) { vantarAterstall.delete(id); return; }
    const sek = document.querySelector(`.vy[data-vy="${id}"]`);
    const kandidater = sek ? sek.querySelectorAll("[data-ankare]") : [];
    if (p.ankare && !kandidater.length) return;  // listan är inte ritad än – försök igen vid nästa render
    vantarAterstall.delete(id);
    const mal = p.ankare && [...kandidater].find(e => e.dataset.ankare === p.ankare.id);
    if (mal) window.scrollTo(0, window.scrollY + mal.getBoundingClientRect().top - p.ankare.top);
    else window.scrollTo(0, p.y || 0);
    if (p.detalj && delar[id] && delar[id].oppnaDetalj && !document.querySelector(".panel")) delar[id].oppnaDetalj(p.detalj);
  }
  let platsTimer = null;
  window.addEventListener("scroll", () => { clearTimeout(platsTimer); platsTimer = setTimeout(sparaPlats, 250); }, { passive: true });
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") sparaPlats(); });
  window.addEventListener("pagehide", sparaPlats);
  document.addEventListener("click", e => { if (e.target.closest && e.target.closest("a[target=_blank]")) sparaPlats(); }, true);

  function visa(id, { tyst } = {}) {
    if (!delar[id] && id !== "mer") id = mobil() ? "butik" : "fynd";
    if (aktiv && aktiv !== id) sparaPlats();
    aktiv = id;
    document.body.dataset.vy = id;   // stilen kan anpassa sig efter vyn (t.ex. ingen fyndbanner i Butik på telefon)
    document.querySelectorAll(".vy").forEach(s => s.classList.toggle("aktiv", s.dataset.vy === id));
    document.querySelectorAll("[data-vy]").forEach(b => { if (b.tagName === "BUTTON") b.setAttribute("aria-current", b.dataset.vy === id || (b.dataset.vy === "mer" && MOBIL_MER.includes(id)) ? "page" : "false"); });
    if (!tyst) { try { history.replaceState(null, "", "#" + id); localStorage.setItem("fyndjakt-del", id); } catch (e) {} }
    const d = delar[id];
    if (d && konto.inloggad) {
      const sektion = document.querySelector(`.vy[data-vy="${id}"]`);
      if (!monterade.has(id)) { monterade.add(id); d.montera(sektion); }
      vantarAterstall.add(id);
      setTimeout(() => vantarAterstall.delete(id), 8000);  // hoppa inte senare, när man redan börjat bläddra
      if (d.visa) d.visa(sektion);
    }
    if (!plats(id)) { vantarAterstall.delete(id); window.scrollTo(0, 0); }
    else if (vantarAterstall.has(id)) renderKlar(id);
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
    // Det du ogillat eller köpt ska inte larma.
    const poster = ((konto.fynd || {}).poster || []).filter(p => !["ogillar", "kopt"].includes((konto.reakt.get(p.nyckel) || {}).typ));
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
    const [jag, prof, fynd, r, a, v, inst, saml, fors] = await Promise.all([
      sb.from("fyndjakt_anvandare").select("admin,namn").eq("user_id", konto.uid).maybeSingle(),
      sb.from("fyndjakt_profiler").select("*").order("id"),
      sb.from("fyndjakt_fynd").select("data").maybeSingle(),
      hamtaAlla(() => sb.from("fyndjakt_reaktioner").select("*").order("skapad", { ascending: false }).order("nyckel")),
      sb.from("fyndjakt_anteckningar").select("*").order("skapad", { ascending: false }),
      sb.from("fyndjakt_sokord_val").select("spar,sokord,aktiv"),
      sb.from("samling_installningar").select("smak,kanal").eq("user_id", konto.uid).maybeSingle(),
      hamtaAlla(() => sb.from("samling_foremal").select("*").order("uppdaterad", { ascending: false })),
      sb.from("samling_forslag").select("*"),
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
    konto.forslag = new Map(((fors && fors.data) || []).map(x => [x.foremal_id, x]));
    if (saml.error) console.error(saml.error);
  }
  async function uppdateraKonto(session) {
    konto.session = session; konto.uid = session ? session.user.id : null;
    konto.inloggad = false;
    $("ingen-profil").hidden = true;
    if (session) {
      $("login-status").textContent = "Hämtar din samling och dina fynd …";
      const { data: medlem } = await konto.sb.rpc("fyndjakt_ga_med");
      if (!medlem) { $("ingen-profil").hidden = false; $("login-status").textContent = ""; }
      else {
        try { await laddaKonto(); } catch (e) { console.error(e); toast("Kunde inte läsa allt från databasen."); }
        konto.inloggad = true;
      }
      $("login-status").textContent = "";
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

  return { KONFIG, konto, del, pa, sand, visa, rakna, start, mobil, $, kr, esc, el, toast, datum, idag, slug, nyttId, fjNr, norm, plats, renderKlar, sparaPlats,
           skalaNer, dataUrlTillBase64, kannIgen, bildUrlar, bildUrl, laddaUppBild, taBortBild, hamtaAlla, panel, lightbox, fraga,
           sheet, hjalp, huvud, uppdateraBanner, laddaKonto };
})();
