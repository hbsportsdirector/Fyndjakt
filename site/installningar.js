// Inställningar: smak och kanal för samlingen, Fyndjakt-bevakningar, Min smak (reaktioner och anteckningar),
// notiser och inbjudningar – som i dag, flyttat från den gamla sidans paneler.
(() => {
  "use strict";
  const { konto, el, toast, $ } = App;
  const ANT_NAMN = { gillar: "Gillar", ogillar: "Vill inte ha", har: "Har redan" };
  let rot;
  const spar = () => ((konto.fynd || {}).spar || []);
  const filspar = () => spar().filter(s => !/^p\d+$/.test(s.id));
  const sparNamn = id => (spar().find(s => s.id === id) || {}).namn || "Alla flikar";

  // ── Smak och kanal för samlingen ──────────────────────────────────
  function renderSamling(sek) {
    const d = sek.querySelector("#in-samling");
    d.innerHTML = `<h3>Samlingen</h3>
      <p class="muted">Smaken styr köptaket i butiken: passar föremålet profilen räknas det som samling (60 % av typiskt slutpris), annars som flipp (33 %).</p>
      <label>Min smak och mina lärdomar<textarea id="in-smak" rows="8" placeholder="Vad du samlar, vad som passar hemmet, vad du lärt dig om priser …"></textarea></label>
      <div class="rad" style="margin-top:8px"><label class="rad-etikett">Standardkanal vid försäljning <select id="in-kanal">
        <option value="tradera">Tradera</option><option value="blocket">Blocket</option><option value="bukowskis">Bukowskis</option><option value="auktionsverket">Auktionsverket</option><option value="catawiki">Catawiki</option></select></label>
        <button class="knapp primar" type="button" id="in-spara">Spara</button><span class="status" id="in-status"></span></div>`;
    $("in-smak").value = konto.installningar.smak || ""; $("in-kanal").value = konto.installningar.kanal || "tradera";
    $("in-spara").onclick = async () => {
      const rad = { user_id: konto.uid, smak: $("in-smak").value.trim(), kanal: $("in-kanal").value, uppdaterad: new Date().toISOString() };
      const { error } = await konto.sb.from("samling_installningar").upsert(rad, { onConflict: "user_id" });
      if (error) { $("in-status").textContent = "Kunde inte spara: " + error.message; return; }
      konto.installningar = rad; $("in-status").textContent = "Sparat.";
    };
  }

  // ── Fyndjakt-bevakningar (profiler) ───────────────────────────────
  function sokTillText(sok) { return Object.entries(sok || {}).map(([k, l]) => k + ":\n" + l.join("\n")).join("\n\n"); }
  function textTillSok(text) {
    const ut = {}; let kat = "Sökningar";
    for (let rad of text.split("\n")) {
      rad = rad.replace(/^[\s•*-]+/, "").trim();
      if (!rad) continue;
      if (rad.endsWith(":")) { kat = rad.slice(0, -1).trim().slice(0, 40) || "Sökningar"; continue; }
      (ut[kat] = ut[kat] || []);
      if (!ut[kat].some(q => q.toLowerCase() === rad.toLowerCase())) ut[kat].push(rad.slice(0, 60));
    }
    for (const k of Object.keys(ut)) if (!ut[k].length) delete ut[k];
    return ut;
  }
  const antalSok = sok => Object.values(sok).reduce((n, l) => n + l.length, 0);

  function profilkort(p) {
    const kort = el("form", { class: "profilkort" }); kort.noValidate = true;
    const uid = "pk" + (p.id || ("ny" + Math.random().toString(36).slice(2, 7)));
    kort.innerHTML = `
      <label class="rubr" for="${uid}-namn">Namn på bevakningen</label>
      <input type="text" id="${uid}-namn" maxlength="40" placeholder="t.ex. Sommarhuset eller Glassamlingen">
      <label class="rubr" for="${uid}-beskr">Vad letar du efter? <small>Stil, färger, material, epoker, formgivare – med egna ord</small></label>
      <textarea id="${uid}-beskr" rows="6" maxlength="6000"></textarea>
      <label class="rubr" for="${uid}-har">Har redan eller vill inte ha <small>en sak per rad</small></label>
      <textarea id="${uid}-har" rows="3" maxlength="1500"></textarea>
      <label class="rubr" for="${uid}-pris">Högsta pris (kr) <small>tomt = ingen gräns</small></label>
      <input type="number" id="${uid}-pris" min="0" step="100" inputmode="numeric">
      <label class="rubr"><input type="checkbox" id="${uid}-flipp"> Flipp – betyg på pris i stället för smak</label>
      <label class="rubr" for="${uid}-sok">Sökord <small>en per rad · rader som slutar med kolon blir flikar · högst 30</small></label>
      <div class="rad"><button class="knapp" type="button" data-foresla>✨ Föreslå sökord</button></div>
      <p class="kommentar" data-kommentar hidden></p>
      <textarea id="${uid}-sok" rows="9"></textarea>
      <div class="rad" style="margin-top:10px">
        <button class="knapp primar" type="submit">Spara</button>
        ${p.id ? '<button class="knapp" type="button" data-leta>🔎 Leta nu</button><button class="knapp fara" type="button" data-bort>Ta bort</button>' : ""}
      </div>
      <div class="status" role="status" data-status></div>`;
    const f = id => kort.querySelector("#" + uid + "-" + id);
    f("namn").value = p.namn || ""; f("beskr").value = p.beskrivning || ""; f("har").value = p.har_redan || "";
    f("pris").value = p.max_pris || ""; f("sok").value = sokTillText(p.sokningar); f("flipp").checked = !!p.flipp;
    const status = t => kort.querySelector("[data-status]").textContent = t;
    kort.querySelector("[data-foresla]").onclick = async e => {
      if (f("beskr").value.trim().length < 10) { status("Skriv några rader om vad du letar efter först."); return; }
      e.target.disabled = true; status("Claude tänker ut sökord …");
      try {
        const data = await App.kannIgen({ typ: "profil", namn: f("namn").value, beskrivning: f("beskr").value, har_redan: f("har").value });
        f("sok").value = sokTillText(data.sokningar);
        if (!f("namn").value && data.namn) f("namn").value = data.namn;
        const k = kort.querySelector("[data-kommentar]"); k.textContent = data.kommentar || ""; k.hidden = !data.kommentar;
        status("Klart – ändra fritt och tryck Spara.");
      } catch (x) { status(x.message); } finally { e.target.disabled = false; }
    };
    kort.onsubmit = async e => {
      e.preventDefault();
      const sokningar = textTillSok(f("sok").value);
      const rad = { namn: f("namn").value.trim().slice(0, 40), beskrivning: f("beskr").value.trim(), har_redan: f("har").value.trim(),
                    max_pris: f("pris").value ? Math.max(0, Math.round(+f("pris").value)) : null, sokningar, flipp: f("flipp").checked, uppdaterad: new Date().toISOString() };
      if (!rad.namn) { status("Ge bevakningen ett namn."); return; }
      if (!antalSok(sokningar)) { status("Lägg till minst ett sökord – eller tryck ✨ Föreslå sökord."); return; }
      if (antalSok(sokningar) > 30) { status("Högst 30 sökord – ta bort " + (antalSok(sokningar) - 30) + "."); return; }
      status("Sparar …");
      const q = p.id ? konto.sb.from("fyndjakt_profiler").update(rad).eq("id", p.id) : konto.sb.from("fyndjakt_profiler").insert(rad);
      const { data, error } = await q.select().single();
      if (error) { status("Kunde inte spara – försök igen."); return; }
      const i = konto.profiler.findIndex(x => x.id === data.id);
      if (i >= 0) konto.profiler[i] = data; else konto.profiler.push(data);
      konto.vald = "p" + data.id; renderProfiler();
      if (!p.id) snabbstart(data.id); else profilStatus(data.id, "Sparat! Ändringarna används från nästa sökning.");
    };
    const leta = kort.querySelector("[data-leta]"); if (leta) leta.onclick = () => snabbstart(p.id);
    const bort = kort.querySelector("[data-bort]");
    if (bort) bort.onclick = async () => {
      if (bort.dataset.saker !== "1") { bort.dataset.saker = "1"; bort.textContent = "Tryck igen för att ta bort"; return; }
      const { error } = await konto.sb.from("fyndjakt_profiler").delete().eq("id", p.id);
      if (error) { status("Kunde inte ta bort – försök igen."); return; }
      konto.profiler = konto.profiler.filter(x => x.id !== p.id); konto.vald = null; renderProfiler();
    };
    if (p.id) { kort.dataset.id = p.id; const pa = pausadeRuta("p" + p.id); if (pa) kort.appendChild(pa); }
    return kort;
  }
  function profilStatus(id, text) { const e = $("prof-lista").querySelector('[data-id="' + id + '"] [data-status]'); if (e) e.textContent = text; }
  async function snabbstart(id) {
    const knappar = () => $("prof-lista").querySelectorAll('[data-id="' + id + '"] button');
    knappar().forEach(b => b.disabled = true);
    profilStatus(id, "🔎 Letar på Auctionet nu och låter Claude välja ut det som passar – det tar ungefär en minut …");
    try {
      const { data: res, error } = await konto.sb.functions.invoke("fyndjakt-snabbstart", { body: { profil_id: id } });
      if (error || !res || res.fel) {
        let txt = (res && res.fel) || "";
        try { if (!txt && error && error.context) txt = (await error.context.json()).fel; } catch (x) {}
        throw new Error(txt || "Det gick inte att leta just nu – appen letar i natt i stället.");
      }
      const f = await konto.sb.from("fyndjakt_fynd").select("data").maybeSingle();
      konto.fynd = (f.data && f.data.data) || konto.fynd;
      App.uppdateraBanner();
      profilStatus(id, res.fynd ? `Klart! ${res.fynd} fynd bland ${res.bedomda} bedömda annonser – se dem under Fynd. I natt letar appen även på fler sajter.`
        : `Claude gick igenom ${res.bedomda} annonser men inget passade riktigt än. Prova fler eller andra sökord.`);
    } catch (x) { profilStatus(id, x.message); }
    finally { knappar().forEach(b => b.disabled = false); }
  }
  function pausadeRuta(sid) {
    const sp = spar().find(s => s.id === sid);
    const lista = [...((sp && sp.pausade) || [])];
    for (const [k, aktiv] of konto.sokordVal) {
      const [s2, q] = [k.slice(0, k.indexOf("|")), k.slice(k.indexOf("|") + 1)];
      if (s2 === sid && aktiv === false && !lista.some(x => x.sokord === q)) lista.push({ sokord: q, eget: true });
    }
    if (!lista.length) return null;
    const d = el("div", { class: "pausade" }, el("div", { class: "etik" }, "⏸ Pausade sökord – sådant du sagt nej till, eller som inte gett något fynd på länge"));
    for (const x of lista) {
      const egen = x.eget || konto.sokordVal.get(sid + "|" + x.sokord) === false;
      const rad = el("div", { class: "p-rad" }, el("span", {}, egen ? `${x.sokord} · du har sagt nej` : `${x.sokord} · ${x.bedomda} bedömda, 0 fynd`));
      const b = el("button", { type: "button", class: "knapp liten" }, "Slå på igen");
      b.onclick = async e => {
        e.preventDefault(); b.disabled = true;
        const { error } = await konto.sb.from("fyndjakt_sokord_val").upsert({ spar: sid, sokord: x.sokord, aktiv: true, uppdaterad: new Date().toISOString() }, { onConflict: "user_id,spar,sokord" });
        if (error) { b.disabled = false; b.textContent = "Försök igen"; return; }
        if (sp && sp.pausade) sp.pausade = sp.pausade.filter(y => y.sokord !== x.sokord);
        konto.sokordVal.set(sid + "|" + x.sokord, true);
        rad.replaceChildren(el("span", {}, `${x.sokord} – på igen från i natt`));
      };
      rad.append(b); d.append(rad);
    }
    return d;
  }
  function filkort(sp) {
    const d = el("div", { class: "profilkort filspar" });
    const fil = sp.id === "hemmet" ? "stil.md" : sp.id === "samlingen" ? "samlingsprofil.md" : "config.yaml";
    d.append(el("p", { class: "muted", style: "margin:0" }, "Det här spåret styrs av filen ", el("b", {}, fil), ". Be Claude i chatten om du vill ändra stilen eller sökorden. Reaktioner och Min smak påverkar det precis som vanligt."));
    for (const [kat, lista] of Object.entries(sp.sokningar || {})) {
      d.append(el("div", { class: "kat" }, kat), el("div", { class: "ord" }, ...lista.map(q => el("span", {}, q))));
    }
    const pa = pausadeRuta(sp.id); if (pa) d.append(pa);
    return d;
  }
  function renderProfiler() {
    const val = [];
    filspar().forEach(sp => val.push({ v: "fil:" + sp.id, t: sp.namn + " (huvudspår)" }));
    konto.profiler.forEach(pr => val.push({ v: "p" + pr.id, t: pr.namn }));
    if (konto.profiler.length < 3) val.push({ v: "ny", t: "+ Ny bevakning" });
    if (!val.some(x => x.v === konto.vald)) konto.vald = konto.profiler.length ? "p" + konto.profiler[0].id : val[0].v;
    $("prof-val").replaceChildren(...val.map(x => new Option(x.t, x.v)));
    $("prof-val").value = konto.vald;
    let kort;
    if (konto.vald === "ny") kort = profilkort({});
    else if (konto.vald.startsWith("fil:")) kort = filkort(filspar().find(sp => "fil:" + sp.id === konto.vald));
    else kort = profilkort(konto.profiler.find(pr => "p" + pr.id === konto.vald));
    $("prof-lista").replaceChildren(kort);
  }

  // ── Min smak: reaktioner och anteckningar ─────────────────────────
  function listrad({ bild, etikett, titel, url, onBort }) {
    const li = el("li");
    if (bild !== undefined) { const i = el("img", { alt: "", referrerpolicy: "no-referrer" }); if (bild) i.src = bild; li.append(i); }
    const t = el("div", { class: "txt" });
    if (etikett) t.append(el("span", { class: "etik" }, etikett));
    t.append(url ? el("a", { href: url, target: "_blank", rel: "noopener" }, titel) : titel);
    li.append(t, el("button", { class: "bort", type: "button", "aria-label": "Ta bort " + titel, onclick: onBort }, "✕"));
    return li;
  }
  function renderSmak() {
    const ruta = $("l-lardomar"); ruta.replaceChildren();
    const med = spar().filter(sp => sp.lardomar);
    if (!med.length) ruta.append(el("p", { class: "muted" }, "Inget än – reagera på några fynd så gör Claude sin första analys i natt."));
    for (const sp of med) ruta.append(el("div", { class: "lardom" }, el("div", { class: "etik" }, sp.namn),
      el("ul", {}, ...sp.lardomar.split("\n").map(r => r.replace(/^[-•]\s*/, "").trim()).filter(Boolean).map(r => el("li", {}, r)))));
    const ant = $("l-anteckningar");
    ant.replaceChildren(...konto.anteckningar.map(a => listrad({ etikett: ANT_NAMN[a.typ] + " · " + sparNamn(a.spar) + (a.sokord ? " · söker ”" + a.sokord + "”" : ""), titel: a.text,
      onBort: async () => { konto.anteckningar = konto.anteckningar.filter(x => x.id !== a.id); await konto.sb.from("fyndjakt_anteckningar").delete().eq("id", a.id); renderSmak(); } })));
    if (!konto.anteckningar.length) ant.append(el("li", { class: "muted" }, "Inga ännu."));
    for (const typ of ["gillar", "kopt", "ogillar"]) {
      const ul = $("l-" + typ);
      const rader = [...konto.reakt.values()].filter(r => r.typ === typ);
      ul.replaceChildren(...rader.map(r => listrad({ bild: r.bild || "", etikett: sparNamn(r.spar) + (r.kommentar ? " · ”" + r.kommentar + "”" : ""), titel: r.titel, url: r.url,
        onBort: async () => { await konto.sb.from("fyndjakt_reaktioner").delete().eq("nyckel", r.nyckel); konto.reakt.delete(r.nyckel); renderSmak(); } })));
      if (!rader.length) ul.append(el("li", { class: "muted" }, "Inget här ännu."));
    }
  }

  // ── Notiser (Web Push) ────────────────────────────────────────────
  const NOTIS = { stod: "serviceWorker" in navigator && "PushManager" in window && "Notification" in window };
  const arIOS = /iPhone|iPad|iPod/.test(navigator.userAgent);
  const installerad = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  function b64TillBytes(s) { const b = atob((s + "=".repeat((4 - s.length % 4) % 4)).replace(/-/g, "+").replace(/_/g, "/")); return Uint8Array.from(b, c => c.charCodeAt(0)); }
  async function notisPrenumeration() {
    if (!NOTIS.stod) return null;
    try { const reg = await navigator.serviceWorker.getRegistration(); return reg ? await reg.pushManager.getSubscription() : null; } catch (x) { return null; }
  }
  async function visaNotisLage() {
    const knapp = $("b-notis");
    if (!NOTIS.stod || !App.KONFIG.vapid) {
      knapp.hidden = true;
      $("notis-status").textContent = arIOS && !installerad ? "På iPhone: tryck Dela-knappen i Safari → ”Lägg till på hemskärmen”, öppna Fyndjakt därifrån och slå på notiser här." : "Den här webbläsaren kan inte ta emot notiser.";
      return;
    }
    const pren = await notisPrenumeration();
    knapp.hidden = false; knapp.textContent = pren ? "Stäng av notiser" : "Slå på notiser"; knapp.classList.toggle("primar", !pren);
    $("notis-status").textContent = pren ? "Notiser är på för den här enheten." : Notification.permission === "denied" ? "Notiser är blockerade – tillåt dem för sidan i telefonens inställningar." : "";
  }
  async function vaxlaNotis() {
    const knapp = $("b-notis"); knapp.disabled = true;
    try {
      const finns = await notisPrenumeration();
      if (finns) { await konto.sb.from("fyndjakt_push").delete().eq("endpoint", finns.endpoint); await finns.unsubscribe(); }
      else {
        const reg = await navigator.serviceWorker.register("sw.js"); await navigator.serviceWorker.ready;
        if (await Notification.requestPermission() !== "granted") throw new Error("Du behöver tillåta notiser för att slå på dem.");
        const pren = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64TillBytes(App.KONFIG.vapid) });
        const j = pren.toJSON();
        const { error } = await konto.sb.from("fyndjakt_push").insert({ endpoint: j.endpoint, p256dh: j.keys.p256dh, auth: j.keys.auth });
        if (error && error.code !== "23505") { await pren.unsubscribe(); throw new Error("Kunde inte spara – försök igen."); }
      }
      await visaNotisLage();
    } catch (x) { $("notis-status").textContent = x.message || "Det gick inte att slå på notiser."; }
    finally { knapp.disabled = false; }
  }

  // ── Bjud in (admin) ───────────────────────────────────────────────
  async function laddaMedlemmar() {
    const { data, error } = await konto.sb.rpc("fyndjakt_medlemmar");
    if (error || !data) return;
    $("l-medlemmar").replaceChildren(...(data.medlemmar || []).map(m => el("li", {}, el("div", { class: "txt" }, el("span", { class: "etik" },
        m.admin ? "Administratör" : (m.profiler ? m.profiler + " bevakning" + (m.profiler > 1 ? "ar" : "") : "Inga bevakningar än")), m.epost || ""))),
      ...(data.vantar || []).map(e => el("li", {}, el("div", { class: "txt" }, el("span", { class: "etik" }, "Inbjuden – har inte loggat in än"), e))));
  }

  App.del("installningar", { namn: "Inställningar", ikon: "⚙️",
    montera(sek) {
      rot = sek;
      sek.innerHTML = `
        <div class="installningar">
          <div class="vy-huvud"><h2>Inställningar</h2></div>
          <div class="ruta" id="in-samling"></div>
          <div class="ruta"><h3>Fyndjakt-bevakningar</h3>
            <p class="muted">En bevakning är något du letar efter – appen letar åt dig varje natt. Dina fynd syns bara för dig.</p>
            <div class="profilval"><label for="prof-val">Välj bevakning</label><select id="prof-val"></select></div>
            <div id="prof-lista"></div></div>
          <div class="ruta"><h3>🔔 Morgonnotis</h3><p class="muted">En notis på telefonen när natten gett nya toppfynd (9–10/10).</p>
            <div class="rad"><button class="knapp primar" type="button" id="b-notis">Slå på notiser</button></div><div class="status" id="notis-status"></div></div>
          <div class="ruta"><h3>🧠 Det här har appen lärt sig</h3><div id="l-lardomar"></div>
            <h3>Säg det med egna ord</h3>
            <form class="rad" id="f-anteckning"><select id="a-typ"><option value="gillar">Jag gillar</option><option value="ogillar">Jag vill inte ha</option><option value="har">Jag har redan</option></select>
              <input type="text" id="a-text" maxlength="300" required placeholder="t.ex. gamla sjökort i ram" style="flex:1 1 200px"><select id="a-spar"></select><button class="knapp primar" type="submit">Lägg till</button></form>
            <h3>Mina anteckningar</h3><ul class="lista" id="l-anteckningar"></ul>
            <h3>👍 Gillade fynd</h3><ul class="lista" id="l-gillar"></ul>
            <h3>🛒 Köpt</h3><ul class="lista" id="l-kopt"></ul>
            <h3>👎 Inte min stil</h3><ul class="lista" id="l-ogillar"></ul></div>
          <div class="ruta" id="in-bjud" hidden><h3>Bjud in</h3>
            <p class="muted">Skriv in en e-postadress. Personen loggar sedan in med samma adress – eller med Google.</p>
            <form class="rad" id="f-bjud"><input type="email" id="bjud-epost" required placeholder="namn@epost.se" style="flex:1 1 220px"><button class="knapp primar" type="submit">Bjud in</button></form>
            <div class="status" id="bjud-status"></div><h3>Inbjudna</h3><ul class="lista" id="l-medlemmar"></ul></div>
          <div class="rad" style="margin-top:16px"><button class="knapp" type="button" id="in-logga-ut">Logga ut</button></div>
        </div>`;
      renderSamling(sek);
      $("prof-val").onchange = e => { konto.vald = e.target.value; renderProfiler(); };
      renderProfiler();
      $("a-spar").replaceChildren(new Option("Alla flikar", ""), ...spar().map(s => new Option(s.namn, s.id)));
      $("f-anteckning").onsubmit = async e => {
        e.preventDefault();
        const text = $("a-text").value.trim(); if (!text) return;
        const typ = $("a-typ").value;
        const rad = { typ, text: text.slice(0, 300), spar: $("a-spar").value || null, sokord: typ === "gillar" ? text.split(/\s+/).slice(0, 4).join(" ") : null };
        const { data, error } = await konto.sb.from("fyndjakt_anteckningar").insert(rad).select().single();
        if (error) { toast("Kunde inte spara – försök igen."); return; }
        konto.anteckningar.unshift(data); $("a-text").value = ""; renderSmak();
      };
      renderSmak();
      $("b-notis").onclick = vaxlaNotis; visaNotisLage();
      if (konto.admin) {
        $("in-bjud").hidden = false; laddaMedlemmar();
        $("f-bjud").onsubmit = async e => {
          e.preventDefault();
          const epost = $("bjud-epost").value.trim(); if (!epost) return;
          $("bjud-status").textContent = "Bjuder in …";
          const { error } = await konto.sb.rpc("fyndjakt_bjud_in", { epost });
          if (error) { $("bjud-status").textContent = "Det gick inte – kolla adressen."; return; }
          $("bjud-epost").value = ""; $("bjud-status").textContent = "Klart! " + epost + " är inbjuden – tipsa hen om adressen " + location.origin + location.pathname;
          laddaMedlemmar();
        };
      }
      $("in-logga-ut").onclick = () => konto.sb.auth.signOut();
    },
  });
})();
