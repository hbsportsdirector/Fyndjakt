// Fyndjakt: känner igen ett fotograferat föremål med Claude, och föreslår sökord för en ny profil (typ: "profil").
// typ "butik": strukturerad bedömning i butiken (tillverkare, serie, marknadsvärde, äkthet) för Samlingen-sajten.
// typ "akta": original eller nyproduktion, utifrån annonsens bilder (hämtas här – webbläsaren får inte läsa dem).
// typ "kopiera_bilder": kopierar annonsens bilder till den inloggades mapp i bucketen samling.
// typ "beskriv": katalogtext och säljannons för ett föremål i samlingen (Köpt-flödet), utifrån fälten och bilderna.
// typ "om": faktaruta om pjäsen (formgivare, serie, tillverkning, kännetecken) grundad på Wikipedia-utdrag, med källor.
// typ "importera_bilder": engångsimport av samlingens bilder med bot-nyckeln (ingen inloggning).
// Kräver inloggad Fyndjakt-medlem (utom importen). Anthropic-nyckeln ligger som hemlighet ANTHROPIC_API_KEY i Supabase.
import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const TILLATNA_URSPRUNG = ["https://hbsportsdirector.github.io", "http://localhost:8000"];
const MODELL = "claude-sonnet-5-5";
const MAX_BILD = 6_000_000; // tecken base64 (~4,5 MB)

function cors(origin: string | null) {
  const o = origin && TILLATNA_URSPRUNG.includes(origin) ? origin : TILLATNA_URSPRUNG[0];
  return {
    "Access-Control-Allow-Origin": o,
    "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Vary": "Origin",
  };
}

function svar(data: unknown, status: number, origin: string | null) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...cors(origin), "Content-Type": "application/json" },
  });
}

const INSTRUKTION = `Du är en kunnig värderare av svenskt och nordiskt porslin, glas, keramik, konst, möbler och
inredning. En samlare visar dig ett eller flera foton av ett föremål (t.ex. framsida, undersida, stämpel, signatur).

Ge ALLTID din bästa gissning på vad det är: tillverkare, serie/modell, formgivare/konstnär och ungefärlig tid –
även när du inte är säker. Var konkret ("Rörstrand, Swedish Grace, Louise Adelborg") hellre än vag
("skandinavisk skål"). Ange hur säker du är. Om flera alternativ är rimliga, nämn de två troligaste.
Hitta inte på fakta: om du är osäker, säg det i säkerheten – men gissa ändå.

Om något skulle avgöra saken (stämpel, signatur, etikett, undersida, detalj, mått) – be om just den bilden i "tips".
Användaren kan också rätta dig eller berätta mer. Lita på hens kunskap och bygg vidare på den, men säg vänligt
till om bilderna tydligt talar emot. Använd det du vet om serien och tillverkaren för att göra sökorden träffsäkra.

Svara ENBART med JSON:
{"gissning": "<din bästa gissning, kort, t.ex. 'Rörstrand, Swedish Grace (Louise Adelborg), 1930-tal–'>",
 "alternativ": "<näst troligaste gissning, eller tom sträng>",
 "sakerhet": "<hög|medel|låg>",
 "beskrivning": "<en mening på svenska om föremålet, inklusive gissningen>",
 "svar": "<1–2 meningar till användaren: vad du baserar gissningen på, eller bekräftelse/kommentar på det hen skrev>",
 "tips": "<om du inte är säker: vilken bild eller uppgift som skulle avgöra, t.ex. 'Fota undersidan – Rörstrands stämpel visar årtal.' Annars tom sträng>",
 "sokord": "<2–4 ord som hittar liknande föremål på en svensk auktionssajt, t.ex. 'Rörstrand Swedish Grace'>",
 "kategori": "<en av: Möbler, Belysning, Konst, Glas, Keramik, Porslin, Textil, Dekor, Övrigt>"}`;

const PROFIL_INSTRUKTION = `Du hjälper en person att sätta upp en daglig bevakning av svenska auktionssajter
(Auctionet, Bukowskis) och second hand-butiker (Myrorna, Stadsmissionen). Personen beskriver sin stil, sitt hem
eller sin samling. Föreslå sökord som hittar RÄTT begagnade och vintage-föremål.

Regler för sökorden:
- Svenska, 1–4 ord, så som föremål faktiskt rubriceras på auktion: "Josef Frank", "Rörstrand Picknick",
  "byrå gustaviansk", "pinnstol allmoge", "Orrefors vas", "matta rya".
- Namngivna formgivare, konstnärer, fabriker och serier ger bäst träffar – ta med dem när de passar stilen.
- Blanda: några breda (föremålstyp + material/epok) och många specifika (namn, serier).
- Inget som personen säger att hen redan har eller inte vill ha.
- 15–30 sökord totalt, grupperade i 3–6 kategorier med korta namn (t.ex. "Möbler", "Glas", "Konst", "Belysning").

Svara ENBART med JSON:
{"namn": "<kort namn på bevakningen, max 30 tecken, om personen inte gett något>",
 "sokningar": {"<Kategori>": ["<sökord>", ...], ...},
 "kommentar": "<1–2 meningar till personen om vad du fokuserat på>"}`;

async function profilforslag(nyckel: string, kropp: { beskrivning?: string; har_redan?: string; namn?: string }) {
  const text = [
    kropp.namn ? `Bevakningens namn: ${String(kropp.namn).slice(0, 40)}` : "",
    `Så här beskriver personen vad hen söker:\n${String(kropp.beskrivning ?? "").slice(0, 6000)}`,
    kropp.har_redan ? `Har redan / vill inte ha:\n${String(kropp.har_redan).slice(0, 1500)}` : "",
  ].filter(Boolean).join("\n\n");
  const r = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "x-api-key": nyckel, "anthropic-version": "2023-06-01", "content-type": "application/json" },
    body: JSON.stringify({ model: MODELL, max_tokens: 1200, system: PROFIL_INSTRUKTION,
                           messages: [{ role: "user", content: text }] }),
  });
  if (!r.ok) { console.error("Anthropic", r.status, await r.text()); return null; }
  const data = await r.json();
  const svarstext: string = (data?.content ?? []).filter((b: { type: string }) => b.type === "text")
    .map((b: { text: string }) => b.text).join("\n");
  const m = svarstext.match(/\{[\s\S]*\}/);
  try {
    const res = JSON.parse(m ? m[0] : "{}");
    const sokningar: Record<string, string[]> = {};
    let antal = 0;
    for (const [kat, lista] of Object.entries(res.sokningar ?? {}).slice(0, 8)) {
      if (!Array.isArray(lista)) continue;
      const rena = lista.map((q) => String(q).trim().slice(0, 60)).filter((q) => q.length > 1);
      const plats = Math.max(0, 30 - antal);
      if (rena.length && plats) { sokningar[String(kat).slice(0, 40)] = rena.slice(0, plats); antal += Math.min(rena.length, plats); }
    }
    return { namn: String(res.namn ?? "").slice(0, 40), sokningar, kommentar: String(res.kommentar ?? "").slice(0, 400) };
  } catch { return null; }
}

// "Hitta liknande": vad finns till salu just nu, och vad har liknande sålts för (Auctionet, Sverige).
const SMAORD = new Set(["och", "med", "i", "av", "på", "för", "en", "ett", "the", "a"]);
function ordIFras(f: string) { return (f.toLowerCase().match(/[\wåäöéü]+/g) ?? []).filter((o) => !SMAORD.has(o) && o.length > 1); }
function relevant(titel: string, fras: string) {
  const t = titel.toLowerCase();
  return ordIFras(fras).every((o) => t.includes(o.slice(0, Math.max(3, o.length - 2))));
}
async function auctionet(params: string) {
  const r = await fetch("https://auctionet.com/api/v2/items.json?per_page=48&" + params,
    { headers: { "User-Agent": "Fyndjakt/1.0 (privat bevakning)" } });
  return r.ok ? ((await r.json()).items ?? []) as Record<string, any>[] : [];
}
async function liknande(sokord: string) {
  const q = "q=" + encodeURIComponent(sokord);
  const [aktiva, s1, s2] = await Promise.all([auctionet(q), auctionet(q + "&is=ended&page=1"), auctionet(q + "&is=ended&page=2")]);
  const nu = Date.now() / 1000;
  const sv = aktiva.filter((p) => p.state === "published" && (p.currency ?? "SEK") === "SEK" && (!p.ends_at || p.ends_at > nu));
  const traff = sv.filter((p) => relevant(String(p.title ?? ""), sokord));
  const till_salu = (traff.length >= 3 ? traff : sv).slice(0, 12).map((p) => {
    const bud = Math.max(0, ...((p.bids ?? []) as { amount: number }[]).map((b) => b.amount || 0));
    return { titel: String(p.title ?? "").trim(), url: String(p.url ?? "").replace("auctionet.com/en/", "auctionet.com/sv/"),
      bild: ((p.images ?? [])[0] ?? {}).w640 ?? null, pris_text: bud ? `Bud ${bud} kr` : `Utrop ${p.estimate ?? "?"} kr`,
      slutar_ts: p.ends_at ?? null, plats: [p.house, p.location].filter(Boolean).join(", ") };
  });
  const grans = nu - 5 * 365 * 86400;
  const priser = [...s1, ...s2].filter((p) => p.state === "sold" && p.currency === "SEK" && (p.ends_at ?? 0) >= grans &&
      relevant(String(p.title ?? ""), sokord))
    .map((p) => p.highest_bid || Math.max(0, ...((p.bids ?? []) as { amount: number }[]).map((b) => b.amount || 0)))
    .filter((x) => x > 0).sort((x, y) => x - y);
  const salda = [...s1, ...s2].filter((p) => p.state === "sold" && p.currency === "SEK" && (p.ends_at ?? 0) >= grans &&
      relevant(String(p.title ?? "") + " " + String(p.description ?? "").replace(/<[^>]+>/g, " "), sokord))
    .slice(0, 20).map((p) => ({ titel: String(p.title ?? "").trim().slice(0, 140), url: String(p.url ?? "").replace("auctionet.com/en/", "auctionet.com/sv/"),
      pris: p.highest_bid || Math.max(0, ...((p.bids ?? []) as { amount: number }[]).map((b) => b.amount || 0)), slutade: p.ends_at ?? null }));
  const kvantil = (k: number) => { const i = (priser.length - 1) * k, l = Math.floor(i); return priser[l] + (priser[Math.ceil(i)] - priser[l]) * (i - l); };
  const salt = priser.length >= 3 ? { median: Math.round(kvantil(0.5)), lag: Math.round(kvantil(0.25)),
                                      hog: Math.round(kvantil(0.75)), antal: priser.length } : null;
  return { sokord, till_salu, antal: traff.length, salt, salda };
}

// ── Butik, äkthet och bildkopiering ──────────────────────────────────
const NYPROD = `KÄNNETECKEN PÅ NYPRODUKTION/REPLIKA: Rörstrand krönt R-logo (2000+) i stället för tre kronor; "Made in Sri Lanka/Thailand/Indonesia/Portugal"; Picknick i vit, blank, tunn benporslin med skarpt tryck, runda muggar eller underlägg med kork; Berså med ankarstämpel utan bladlogotyp eller tryckt "Gustafsberg"; Paratiisi med runda tallrikar; Lisa Larson "K-Studion" eller japansk märkning utan krackelering; Mon Amie 0,33 l-mugg; Muminmugg "By Arabia" eller Made in Thailand; glas/porslin med streckkodsetikett eller nypris; "ny", "oanvänd", "i kartong", "nyutgåva". Original: tre kronor/ankare med blad/krona Arabia Finland, mjukare färger, glasyrkrackelering på fajans/flintgods, stödmärken, slitage på botten.`;
const STAMPLAR = `STÄMPELGUIDE (datera och avslöja nyproduktion):
Gustavsberg: "Gustafsberg" med f präglat=före 1920; "Gustafsberg" tryckt + fyrsiffrigt årtal=nyproduktion 1995–2015; ankare rep bakom(höger)=före 1945; rep framför(vänster)=1940–70; utan rep=1970+; seriestämpel med Berså-blad=original Berså 1961–74, ankare på Berså=nytt; studiohand (hand över G)=Gustavsbergs Studio handgjort 1944+; årsbokstav vid studiohand R=48 S=49 T=50 U=51 V=52 X=53 Y=54 Z=55 Å=56 Ä=57 Ö=58 a=59 b=60 c=61 d=62 e=63 f=64 G=65 H=66 I=67 J=68 K=69 L=70 M=71 N=72 O=73 P=74, från 1975 helt årtal; "Selecta" etikett=fabriksgjord Friberg; Lisa Larson "Gustavsberg"=fabrik 1954–79 (värdefull), "K-Studion"=1992+ (nära nypris).
Rörstrand: tre kronor=1884–2000; tresiffrig kod från 1937 (två första=år); "Sweden"=1940-tal, längre engelsk text 1951+; krönt R=2000+ (Mon Amie-nyutgåva 2008); "R SWEDEN CHS"=Stålhane; "R GN Sweden"=Nylund.
Arabia: krönt A=1928–49; ARABIA FINLAND=1949+; Kilta 1953–75 fajans, Teema 1981+ alltid stämplad Teema; Paratiisi viol-logo 1969–71, bladlogo 1971–74, krona 1988+, ny logo dec 2014 Thailand; Mumin: krona+årtal (1996–2001)=2–10× värde, "Made in Finland"-etikett bäst.
Royal Copenhagen: tre vågor; 1935–49 punkt ovanför bokstav; 1950–84 punkt under bokstav; 1985–2014 två bokstäver RO/RY/RA/RL/RC; rits genom vågorna=andrasortering; B&G vågrät rits över tornen=2:a.
Danskt studio: Saxbo-stämpel, PLS=Palshus, HAK=Kähler/Hammershøi, SALTO+vågor=Axel Salto.
Meissen: äkta svärd handmålade koboltblå under glasyr, rits=fabriks-2:a; kopior: Samson, Dresden-krona, Wolfsohn AR.
Glas: Kosta "LH"=Vicke Lindstrand hyttsigill, Boda "H"/"Höglund"=Erik Höglund, Orrefors-gravyr med formgivarsignatur och nummer.
Skadeavdrag: fabriks-2:a –20–30 %, nagg –30–50 %, hårspricka –50–70 %, lagning –70–90 %.`;

function butikInstruktion(smak: string, harRedan: string) {
  return `Du är expert på nordisk keramik, porslin, glas, konst och design (Gustavsberg, Rörstrand, Upsala-Ekeby, Arabia, Royal
Copenhagen, Boda, Kosta, Orrefors, svensk och dansk studiokeramik) och hjälper en loppishandlare och samlare i Stockholm att
bedöma ett fynd i butiken. Bilderna visar föremålet och ibland dess botten/stämpel. Läs stämplar, signaturer, modellnummer och
årskoder noggrant. Bedöm form, glasyr, dekor, godstyp, stödmärken, krackelering och skador. Skilj original från nyproduktion.

${NYPROD}

${STAMPLAR}
${smak ? `\nÄGARENS SMAK (avgör passar_smak – bara det som uttryckligen passar profilen räknas):\n${smak.slice(0, 6000)}\n` : ""}
${harRedan ? `\nÄGAREN HAR REDAN (id | namn | tillverkare | serie):\n${harRedan.slice(0, 12000)}\n` : ""}
Svara ENBART med ett JSON-objekt:
{"namn": "<kort namn på föremålet, t.ex. 'Vas, Berså'>",
 "tillverkare": "<fabrik eller 'Okänd'>", "formgivare": "<formgivare eller tom sträng>", "serie": "<serie/modell/figur eller tom sträng>",
 "period": "<t.ex. 1961–74 eller tom sträng>", "material": "<godstyp/material>",
 "kategori": "<en av: Keramik & porslin, Glas, Konst, Möbler, Belysning, Skulptur, Böcker, Övrigt>",
 "antal": <heltal – antal separata föremål som hör ihop>,
 "stampel_last": "<vad du faktiskt kan läsa av stämpeln, ordagrant, eller 'ingen stämpel synlig'>",
 "nyproduktion": <true|false>, "varning": "<kort om nyproduktion/kopia/skada, annars tom sträng>",
 "skick": "<skador du ser eller 'inga synliga'>",
 "marknad_min": <lågt realistiskt slutpris i kr i Sverige för alla föremålen>, "marknad_max": <högt realistiskt slutpris i kr>,
 "sakerhet": <0–1 hur säker du är på identifieringen>,
 "passar_smak": <true|false – passar föremålet ägarens smak enligt profilen ovan (false om ingen profil)>,
 "har_redan": "<id ur ägarens lista om hen tydligt redan har exakt detta, annars null>",
 "kompletterar": "<en mening om det kompletterar något hen har, annars tom sträng>",
 "sokord": "<2–5 ord som hittar liknande sålda på Tradera/Auctionet>",
 "nasta_kontroll": ["<konkreta saker att kontrollera på plats, max 4>"],
 "resonemang": "<2–3 meningar på svenska om varför>"}
Var ärlig om osäkerhet: sänk sakerhet och säg vad som saknas (t.ex. 'fota botten'). Gissa aldrig en signatur eller tillverkare
du inte kan belägga – skriv "Okänd".`;
}

const BESKRIV_INSTRUKTION = `Du är katalogskribent på ett svenskt auktionshus och säljer också själv på Tradera och Blocket.
Du får uppgifter om ett föremål i en samling (JSON) och ibland bilder (föremålet, stämpeln). Skriv på svenska:

1. "beskrivning": katalogtext i auktionshusens stil, 2–5 korta rader. Första raden: FORMGIVARE/TILLVERKARE i versaler, föremålstyp,
   modell/serie, material, fabrik, tid – som "MARI SIMMULSON. Vas, stengods, modell 1034, Upsala-Ekeby, 1960-tal." Sedan stämpel/signering
   (ordagrant det som går att läsa), mått om de är kända, skick. Hitta aldrig på mått, årtal, formgivare eller signaturer: står det inte i
   uppgifterna och syns det inte på bilden, skriv "troligen" eller utelämna. Ange osäker attribution som "i stil med" eller "troligen".
2. "annons_rubrik": Tradera/Blocket-rubrik, max 80 tecken, med de ord köpare söker på (formgivare, fabrik, serie, föremålstyp, tid).
3. "annons_text": säljannons 4–8 rader: vad det är, varför det är eftertraktat (kort, sakligt), stämpel, mått (eller "[mått]" om de saknas
   så att säljaren fyller i), skick ärligt, och sist "Skickas välpackat eller hämtas i Stockholm." Inga utropstecken, inga emojis,
   inget pris i texten.

Svara ENBART med JSON: {"beskrivning": "...", "annons_rubrik": "...", "annons_text": "..."}`;

const OM_INSTRUKTION = `Du skriver korta faktarutor för en samlare av nordisk keramik, porslin och glas. Du får uppgifter om en pjäs
(JSON) och ibland utdrag ur Wikipedia. Skriv på svenska, 4–7 meningar löptext:
- vem formgivaren är (kort: verksam var och när, känd för vad),
- vad serien/modellen är, när och var den tillverkades,
- kännetecken: form, dekor, glasyr, stämpel, varianter eller storlekar,
- vad samlare tittar efter (tidiga stämplar, färger, skick) och om det finns nyproduktion att se upp med.
Regler: använd bara det du säkert vet eller som står i utdragen. Är du osäker – skriv "troligen" eller utelämna. Hitta aldrig på
modellnummer, årtal, upplagor eller namn. Känner du inte till just den här modellen: säg det rakt ut och beskriv formgivaren/fabriken.
Svara ENBART med JSON: {"text": "...", "sokord": ["<2–3 korta sökfraser för att läsa vidare>"]}`;

// Wikipedia: bästa träffen för en sökning, med sammanfattning. Null om inget rimligt finns.
async function wiki(q: string, maste: string, sprak = "sv") {
  const ua = { headers: { "User-Agent": "Fyndjakt/1.0 (privat samling; hbsportsdirector.github.io/Fyndjakt)" } };
  try {
    const s = await fetch(`https://${sprak}.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit=3&srsearch=${encodeURIComponent(q)}`, ua);
    if (!s.ok) return null;
    const traffar = ((await s.json())?.query?.search ?? []) as { title: string }[];
    const nyckel = maste.toLowerCase().replace(/[^a-zåäöéü ]/g, " ").trim().split(/\s+/).pop() ?? "";
    const titel = traffar.map((t) => t.title).find((t) => nyckel.length >= 3 && t.toLowerCase().includes(nyckel.slice(0, 6)));
    if (!titel) return null;
    const r = await fetch(`https://${sprak}.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(titel.replace(/ /g, "_"))}`, ua);
    if (!r.ok) return null;
    const d = await r.json();
    if (d.type === "disambiguation" || !d.extract) return null;
    return { titel: String(d.title), url: String(d.content_urls?.desktop?.page ?? `https://${sprak}.wikipedia.org/wiki/${encodeURIComponent(titel)}`),
             utdrag: String(d.extract).slice(0, 900) };
  } catch { return null; }
}

const AKTA_INSTRUKTION = `Du är expert på nordisk keramik, porslin och glas. Avgör om föremålet i annonsen är ORIGINAL från
produktionsperioden eller NYPRODUKTION/REPLIKA. Titta på alla bilder (stämpel, baksida, etiketter) innan du avgör.
${NYPROD}
${STAMPLAR}
Svara ENBART med JSON: {"bedomning": "original|nyproduktion|osäkert", "sakerhet": <0–1>, "tecken": ["<konkreta tecken du ser, max 4>"],
 "behover": "<vad som skulle avgöra det, t.ex. 'foto på stämpeln', eller tom sträng>", "svar": "<1–2 meningar på svenska>"}`;

async function claude(nyckel: string, system: string, innehall: unknown[], max_tokens = 900) {
  const r = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "x-api-key": nyckel, "anthropic-version": "2023-06-01", "content-type": "application/json" },
    body: JSON.stringify({ model: MODELL, max_tokens, system, messages: [{ role: "user", content: innehall }] }),
  });
  if (!r.ok) { console.error("Anthropic", r.status, await r.text()); return null; }
  const data = await r.json();
  const text: string = (data?.content ?? []).filter((b: { type: string }) => b.type === "text").map((b: { text: string }) => b.text).join("\n");
  const m = text.match(/\{[\s\S]*\}/);
  try { return JSON.parse(m ? m[0] : "{}"); } catch { console.error("Otolkbart svar:", text.slice(0, 400)); return null; }
}
const tal = (v: unknown) => { const n = Number(v); return Number.isFinite(n) ? Math.round(n) : null; };
const bool = (v: unknown) => v === true || String(v).toLowerCase() === "true";
const bildblock = (data: string, mediatyp: string) => ({ type: "image", source: { type: "base64", media_type: mediatyp, data } });

// Hämtar en bild från nätet (annonsens bild) som base64. Null om den inte går att läsa eller är för stor.
const MAX_BYTES = 4_000_000;
async function hamtaBild(url: string): Promise<{ data: string; mediatyp: string; bytes: Uint8Array } | null> {
  try {
    const r = await fetch(url, { headers: { "User-Agent": "Fyndjakt/1.0 (privat bevakning)" } });
    if (!r.ok) return null;
    const typ = (r.headers.get("content-type") ?? "image/jpeg").split(";")[0].trim();
    const mediatyp = ["image/jpeg", "image/png", "image/webp", "image/gif"].includes(typ) ? typ : "image/jpeg";
    const bytes = new Uint8Array(await r.arrayBuffer());
    if (!bytes.length || bytes.length > MAX_BYTES) return null;
    let bin = "";
    for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    return { data: btoa(bin), mediatyp, bytes };
  } catch { return null; }
}

function adminKlient() {
  return createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
}
// Laddar upp bilder till bucketen samling som <user_id>/<id>/<n>.jpg med servicenyckeln. Returnerar [{n, path}].
async function laddaUppBilder(user_id: string, id: string, bilder: { n: number; url: string }[]) {
  const admin = adminKlient();
  const ut: { n: number; path: string }[] = [];
  for (const b of bilder) {
    const h = await hamtaBild(b.url);
    if (!h) { console.error("Kunde inte hämta", b.url); continue; }
    const path = `${user_id}/${id}/${b.n}.jpg`;
    const { error } = await admin.storage.from("samling").upload(path, h.bytes, { contentType: h.mediatyp, upsert: true, cacheControl: "3600" });
    if (error) { console.error("Uppladdning", path, error.message); continue; }
    ut.push({ n: b.n, path });
  }
  return ut;
}

// Första frågan med bilden, sedan växelvis Claudes tidigare svar och användarens kommentarer.
function bygg_meddelanden(bilder: string[], mediatyp: string, samtal: { roll: string; text: string }[]) {
  const meddelanden: unknown[] = [{ role: "user", content: [
    ...bilder.map((data) => ({ type: "image", source: { type: "base64", media_type: mediatyp, data } })),
    { type: "text", text: bilder.length > 1
      ? `Här är ${bilder.length} bilder av samma föremål. Vad är det?` : "Vad är det här för föremål?" },
  ] }];
  for (const s of samtal.slice(-10)) {
    const text = String(s?.text ?? "").slice(0, 1500);
    if (!text) continue;
    const roll = s.roll === "claude" ? "assistant" : "user";
    const sista = meddelanden[meddelanden.length - 1] as { role: string };
    if (sista.role === roll) continue;  // API:t kräver växelvisa roller
    meddelanden.push({ role: roll, content: text });
  }
  const sista = meddelanden[meddelanden.length - 1] as { role: string };
  if (sista.role === "assistant") meddelanden.pop();
  return meddelanden;
}

Deno.serve(async (req) => {
  const origin = req.headers.get("origin");
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors(origin) });
  if (req.method !== "POST") return svar({ fel: "Endast POST" }, 405, origin);

  const auth = req.headers.get("authorization") ?? "";
  const supabase = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_ANON_KEY")!, {
    global: { headers: { Authorization: auth } },
  });

  let kropp: { typ?: string; bild?: string; bilder?: string[]; mediatyp?: string; samtal?: { roll: string; text: string }[];
               beskrivning?: string; har_redan?: string; namn?: string; token?: string; anvandare?: string;
               stampel?: boolean; smak?: string; id?: string; urlar?: string[]; titel?: string; pris_text?: string;
               kalla?: string; identifierat?: string; extra?: string; poster?: { id: string; n: number; url: string }[] };
  try { kropp = await req.json(); } catch { return svar({ fel: "Ogiltig förfrågan" }, 400, origin); }

  // Engångsimport av samlingens bilder: skyddad med bot-nyckeln (samma som nattkörningen), inte med inloggning.
  if (kropp.typ === "importera_bilder") {
    const admin = adminKlient();
    const { error: nyckelfel } = await admin.rpc("fyndjakt_kolla_nyckel", { token: String(kropp.token ?? "") });
    if (nyckelfel) return svar({ fel: "Ogiltig nyckel" }, 403, origin);
    const { data: anv } = await admin.from("fyndjakt_anvandare").select("user_id").eq("namn", String(kropp.anvandare ?? "Per"));
    if (!anv || anv.length !== 1) return svar({ fel: "Hittade inte användaren" }, 400, origin);
    const user_id = anv[0].user_id as string;
    const { data: finns } = await admin.from("samling_foremal").select("id").eq("user_id", user_id);
    const ids = new Set((finns ?? []).map((r: { id: string }) => r.id));
    const perId: Record<string, { n: number; url: string }[]> = {};
    for (const p of (kropp.poster ?? []).slice(0, 500)) (perId[String(p.id)] ??= []).push({ n: Number(p.n) || 1, url: String(p.url) });
    const resultat: Record<string, number> = {}, saknade: string[] = [];
    for (const [id, lista] of Object.entries(perId)) {
      if (!ids.has(id)) { saknade.push(id); continue; }
      const bilder = await laddaUppBilder(user_id, id, lista.sort((a, b) => a.n - b.n));
      if (bilder.length) {
        const { error } = await admin.from("samling_foremal").update({ bilder }).eq("id", id);
        if (error) console.error("Uppdatering", id, error.message);
      }
      resultat[id] = bilder.length;
    }
    return svar({ user_id, foremal: Object.keys(resultat).length, bilder: Object.values(resultat).reduce((a, b) => a + b, 0),
                  resultat, saknade }, 200, origin);
  }

  const { data: medlem, error: medlemsfel } = await supabase.rpc("fyndjakt_ar_medlem");
  if (medlemsfel || !medlem) return svar({ fel: "Inte inloggad som Fyndjakt-användare" }, 403, origin);

  // Kopiera annonsens bilder till den inloggades mapp i bucketen (webbläsaren får inte läsa bilderna själv).
  if (kropp.typ === "kopiera_bilder") {
    const { data: anv } = await supabase.auth.getUser();
    const uid = anv?.user?.id;
    const id = String(kropp.id ?? "").replace(/[^a-z0-9-]/g, "").slice(0, 80);
    if (!uid || !id) return svar({ fel: "Saknar användare eller id" }, 400, origin);
    const urlar = (kropp.urlar ?? []).map(String).filter((u) => /^https?:\/\//.test(u)).slice(0, 4);
    const bilder = await laddaUppBilder(uid, id, urlar.map((url, i) => ({ n: i + 1, url })));
    return svar({ bilder }, 200, origin);
  }

  // Godta vanliga namnvarianter; trimma bort mellanslag som lätt följer med vid inklistring.
  const NAMN = ["ANTHROPIC_API_KEY", "ANTHROPIC_KEY", "CLAUDE_API_KEY", "CLAUDE_KEY", "ANTHROPIC_APIKEY"];
  const nyckel = NAMN.map((n) => (Deno.env.get(n) ?? "").trim()).find((v) => v);
  if (!nyckel) {
    // Visa bara NAMNEN på hemligheter som liknar en Claude-nyckel – aldrig värdena.
    const liknande = Object.keys(Deno.env.toObject()).filter((n) => /anthropic|claude|api_?key/i.test(n));
    return svar({ fel: "Fotofunktionen hittar ingen Anthropic-nyckel. Lägg in den som ANTHROPIC_API_KEY under Edge Functions → Secrets i projektet WORK." +
      (liknande.length ? " Hittade bara: " + liknande.join(", ") : "") }, 503, origin);
  }

  if (kropp.typ === "liknande") {
    const sokord = String((kropp as { sokord?: string }).sokord ?? "").trim().slice(0, 60);
    if (sokord.length < 2) return svar({ fel: "Skriv vad du söker efter" }, 400, origin);
    try { return svar(await liknande(sokord), 200, origin); }
    catch (e) { console.error(e); return svar({ fel: "Kunde inte söka just nu" }, 502, origin); }
  }
  if (kropp.typ === "profil") {
    if (String(kropp.beskrivning ?? "").trim().length < 10) return svar({ fel: "Beskriv lite mer först" }, 400, origin);
    const res = await profilforslag(nyckel, kropp);
    return res ? svar(res, 200, origin) : svar({ fel: "Kunde inte ta fram sökord just nu" }, 502, origin);
  }
  // Läs mer om pjäsen: Wikipedia om formgivare, fabrik och serie + Claudes faktaruta grundad på utdragen.
  if (kropp.typ === "om") {
    const f = (kropp as { foremal?: Record<string, unknown> }).foremal ?? {};
    const t = (k: string) => String(f[k] ?? "").trim().slice(0, 120);
    const fg = t("formgivare"), tv = t("tillverkare") === "Okänd" ? "" : t("tillverkare"), serie = t("serie");
    const glas = /glas/i.test(t("kategori"));
    const [wf, wt, ws] = await Promise.all([
      fg ? wiki(fg, fg) : null,
      tv ? wiki(`${tv} ${glas ? "glasbruk" : "porslinsfabrik keramik"}`, tv.split(/[\s-]/)[0]) : null,
      serie && serie.length > 2 ? wiki(`${serie} ${tv || fg}`.trim(), serie) : null,
    ]);
    const kallor = [wf, wt, ws].filter((k, i, a) => k && a.findIndex((x) => x && x.url === k.url) === i) as { titel: string; url: string; utdrag: string }[];
    const falt = ["namn", "kategori", "tillverkare", "formgivare", "serie", "period", "stampel", "antal"].reduce((o, k) => (t(k) ? { ...o, [k]: t(k) } : o), {});
    const text = `Pjäsen:\n${JSON.stringify(falt, null, 1)}\n\n` + (kallor.length
      ? "Utdrag ur Wikipedia:\n" + kallor.map((k) => `[${k.titel}] ${k.utdrag}`).join("\n\n") : "Inga Wikipedia-utdrag hittades.");
    const res = await claude(nyckel, OM_INSTRUKTION, [{ type: "text", text }], 700);
    if (!res) return svar({ fel: "Kunde inte ta fram fakta just nu" }, 502, origin);
    return svar({ text: String(res.text ?? "").slice(0, 2000), sokord: (Array.isArray(res.sokord) ? res.sokord : []).map((x: unknown) => String(x).slice(0, 60)).slice(0, 3),
                  kallor }, 200, origin);
  }
  // Köpt-flödet: katalogtext + säljannons. Bilderna läses ur bucketen med den inloggades behörighet.
  if (kropp.typ === "beskriv") {
    const f = (kropp as { foremal?: Record<string, unknown> }).foremal ?? {};
    const falt = ["nummer", "namn", "kategori", "tillverkare", "formgivare", "serie", "antal", "period", "stampel", "skick", "anteckning", "jfr",
                  "inkopsstalle", "lada"].reduce((o, k) => (f[k] != null && f[k] !== "" ? { ...o, [k]: String(f[k]).slice(0, 800) } : o), {});
    const innehall: unknown[] = [];
    for (const path of ((kropp as { paths?: string[] }).paths ?? []).map(String).filter((p) => /^[\w-]+\/[\w-]+\/\d+\.jpg$/.test(p)).slice(0, 3)) {
      const { data } = await supabase.storage.from("samling").download(path);
      if (!data || data.size > MAX_BYTES) continue;
      const bytes = new Uint8Array(await data.arrayBuffer());
      let bin = "";
      for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
      innehall.push(bildblock(btoa(bin), "image/jpeg"));
    }
    const kanal = String((kropp as { kanal?: string }).kanal ?? "").slice(0, 120);
    innehall.push({ type: "text", text: `Föremålet:\n${JSON.stringify(falt, null, 1)}${kanal ? `\nSäljs troligen via: ${kanal}` : ""}\n` +
      (innehall.length ? `${innehall.length} bild(er) ovan.` : "Inga bilder.") });
    const res = await claude(nyckel, BESKRIV_INSTRUKTION, innehall, 900);
    if (!res) return svar({ fel: "Kunde inte skriva texterna just nu" }, 502, origin);
    return svar({ beskrivning: String(res.beskrivning ?? "").slice(0, 1500), annons_rubrik: String(res.annons_rubrik ?? "").slice(0, 100),
                  annons_text: String(res.annons_text ?? "").slice(0, 2500), bilder: innehall.length - 1 }, 200, origin);
  }
  // Äkta? – annonsens bilder hämtas här, plus eventuellt en egen skärmbild (base64).
  if (kropp.typ === "akta") {
    const innehall: unknown[] = [];
    const extra = String(kropp.extra ?? "").replace(/^data:image\/\w+;base64,/, "");
    if (extra && extra.length <= MAX_BILD) innehall.push(bildblock(extra, "image/jpeg"));
    for (const u of (kropp.urlar ?? []).map(String).filter((u) => /^https?:\/\//.test(u)).slice(0, 3)) {
      const h = await hamtaBild(u);
      if (h) innehall.push(bildblock(h.data, h.mediatyp));
    }
    innehall.push({ type: "text", text: `${innehall.length ? `Bilderna (${innehall.length} st) är från annonsen${extra ? ", den första en skärmbild i full upplösning" : ""}.` : "Inga bilder gick att hämta – bedöm bara utifrån texten och säg att bild behövs."}
ANNONS: "${String(kropp.titel ?? "").slice(0, 300)}" · ${String(kropp.pris_text ?? "").slice(0, 60)} · ${String(kropp.kalla ?? "").slice(0, 30)}
Fyndjakts identifiering: ${String(kropp.identifierat ?? "-").slice(0, 200)}` });
    const res = await claude(nyckel, AKTA_INSTRUKTION, innehall, 500);
    if (!res) return svar({ fel: "Kunde inte granska just nu" }, 502, origin);
    const b = String(res.bedomning ?? "osäkert").toLowerCase();
    return svar({ bedomning: ["original", "nyproduktion"].includes(b) ? b : "osäkert", sakerhet: Math.max(0, Math.min(1, Number(res.sakerhet) || 0)),
                  tecken: (Array.isArray(res.tecken) ? res.tecken : []).map((t: unknown) => String(t).slice(0, 200)).slice(0, 4),
                  behover: String(res.behover ?? "").slice(0, 200), svar: String(res.svar ?? "").slice(0, 400), bilder: innehall.length - 1 }, 200, origin);
  }

  const bilder = (kropp.bilder?.length ? kropp.bilder : [kropp.bild ?? ""])
    .map((b) => String(b ?? "").replace(/^data:image\/\w+;base64,/, "")).filter((b) => b).slice(0, 4);
  const mediatyp = ["image/jpeg", "image/png", "image/webp"].includes(kropp.mediatyp ?? "") ? kropp.mediatyp! : "image/jpeg";
  if (!bilder.length || bilder.some((b) => b.length > MAX_BILD)) return svar({ fel: "Bilden saknas eller är för stor" }, 400, origin);

  // Butiken: strukturerat svar med marknadsvärde och äkthet. Smaken och "har redan"-listan skickas från sajten.
  if (kropp.typ === "butik") {
    const innehall: unknown[] = bilder.map((b) => bildblock(b, mediatyp));
    const kommentar = String((kropp as { kommentar?: string }).kommentar ?? "").trim().slice(0, 600);
    innehall.push({ type: "text", text: (kropp.stampel
      ? `Bild 1 är föremålet, bild 2 är stämpeln/botten${bilder.length > 2 ? `, bild 3–${bilder.length} är detaljer du bett om` : ""}. Läs stämpeln tecken för tecken innan du bestämmer tillverkare, formgivare och modell. Vad är det, och vad är det värt?`
      : `${bilder.length > 1 ? bilder.length + " bilder av samma föremål" : "Bara en bild på föremålet"} – be om stämpelbild i nasta_kontroll om det behövs. Vad är det, och vad är det värt?`) +
      (kommentar ? `\n\nÄgaren rättar/kompletterar: "${kommentar}". Väg in det – det ägaren läser på föremålet går före din tolkning av en suddig bild.` : "") });
    const res = await claude(nyckel, butikInstruktion(String(kropp.smak ?? ""), String(kropp.har_redan ?? "")), innehall, 1000);
    if (!res) return svar({ fel: "Kunde inte bedöma just nu" }, 502, origin);
    const min = tal(res.marknad_min), max = tal(res.marknad_max);
    const str = (v: unknown, n: number) => String(v ?? "").slice(0, n);
    return svar({
      namn: str(res.namn, 120), tillverkare: str(res.tillverkare, 80) || "Okänd", formgivare: str(res.formgivare, 80), serie: str(res.serie, 80),
      period: str(res.period, 40), material: str(res.material, 60), kategori: str(res.kategori, 40) || "Keramik & porslin",
      antal: Math.max(1, tal(res.antal) ?? 1), stampel_last: str(res.stampel_last, 200), skick: str(res.skick, 200),
      nyproduktion: bool(res.nyproduktion), varning: str(res.varning, 200),
      marknad_min: min, marknad_max: max, median: min != null && max != null ? Math.round((min + max) / 2) : (min ?? max),
      sakerhet: Math.max(0, Math.min(1, Number(res.sakerhet) || 0)), passar_smak: bool(res.passar_smak),
      har_redan: res.har_redan ? str(res.har_redan, 80) : null, kompletterar: str(res.kompletterar, 300), sokord: str(res.sokord, 60),
      nasta_kontroll: (Array.isArray(res.nasta_kontroll) ? res.nasta_kontroll : []).map((t: unknown) => String(t).slice(0, 160)).slice(0, 4),
      resonemang: str(res.resonemang, 600),
    }, 200, origin);
  }

  const r = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "x-api-key": nyckel, "anthropic-version": "2023-06-01", "content-type": "application/json" },
    body: JSON.stringify({
      model: MODELL,
      max_tokens: 700,
      system: INSTRUKTION,
      messages: bygg_meddelanden(bilder, mediatyp, kropp.samtal ?? []),
    }),
  });
  if (!r.ok) {
    console.error("Anthropic", r.status, await r.text());
    return svar({ fel: "Kunde inte analysera bilden just nu" }, 502, origin);
  }
  const data = await r.json();
  // Läs alla textblock – svaret kan innehålla andra blocktyper före texten.
  const text: string = (data?.content ?? []).filter((b: { type: string }) => b.type === "text")
    .map((b: { text: string }) => b.text).join("\n");
  if (!text) console.error("Tomt svar från Claude:", JSON.stringify(data).slice(0, 500));
  const match = text.match(/\{[\s\S]*\}/);
  try {
    const res = JSON.parse(match ? match[0] : "{}");
    const sokord = String(res.sokord ?? res.sökord ?? res.search ?? "").trim();
    const gissning = String(res.gissning ?? "").trim();
    let beskrivning = String(res.beskrivning ?? res.description ?? res.beskrivelse ?? gissning).trim();
    if (!beskrivning) {
      console.error("Svar utan beskrivning:", text.slice(0, 500));
      beskrivning = sokord ? sokord.charAt(0).toUpperCase() + sokord.slice(1) : "Fotat föremål";
    }
    return svar({
      svar: String(res.svar ?? "").slice(0, 600),
      gissning: gissning.slice(0, 200),
      alternativ: String(res.alternativ ?? "").slice(0, 200),
      tips: String(res.tips ?? "").slice(0, 300),
      beskrivning: beskrivning.slice(0, 300),
      sokord: sokord.slice(0, 60),
      kategori: String(res.kategori ?? ""),
      sakerhet: String(res.sakerhet ?? ""),
    }, 200, origin);
  } catch {
    return svar({ fel: "Kunde inte tolka svaret" }, 502, origin);
  }
});
