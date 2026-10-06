// Fyndjakt snabbstart: första sökningen direkt när någon sparat en ny bevakning.
// Söker på Auctionet med bevakningens sökord, låter Claude bedöma de bästa träffarna med SAMMA regler
// som nattkörningen och lägger fynden i användarens egna fynd. Nattkörningen tar sedan över (alla källor).
// GENERERAD av tools/bygg_snabbstart.py från mall.ts – ändra i mallen och kör skriptet.
import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const TILLATNA_URSPRUNG = ["https://hbsportsdirector.github.io", "http://localhost:8000"];
const MODELL = "claude-haiku-4-5-20251001";
const INSTRUKTION: string = "Du är en erfaren inredare och samlingsrådgivare som letar begagnade fynd åt en kund.\nHär är kundens profil:\n\n<stilprofil>\n{stil}\n</stilprofil>\n\nBedöm annonsen nedan: hur väl passar föremålet kundens profil?\nTitta främst på bilderna (material, färg, form, patina, kvalitet), och använd texten för detaljer.\n\n{kalibrering}\n\nGe också en kort sökfras (2–4 ord, på svenska) som hittar JÄMFÖRBARA föremål på en\nauktionssajt, för prisjämförelse. Använd konstnär/formgivare/tillverkare + föremålstyp om det\nfinns, annars föremålstyp + material/epok. Exempel: \"Erik Höglund vas\", \"bokskåp mahogny\",\n\"jordglob 1930-tal\", \"Stig Lindberg fat\".\n\nSvara ENBART med JSON, utan annan text:\n{\"betyg\": <heltal 0-10>, \"motivering\": \"<EN kort mening på svenska, max 30 ord>\", \"jamforsok\": \"<sökfras>\"}";
const KALIBRERING: string = "Var kräsen men rättvis – kunden vill se ett urval, inte allt. Ungefär 1 av 6 annonser bör få 8 eller mer.\n- 10: Ett tydligt fynd: exakt det kunden beskriver, ovanligt eller långt under vad det brukar kosta.\n- 9: Exakt rätt sak, stil och kvalitet för kunden.\n- 8: Mycket bra match, väl värt att titta på.\n- 6–7: Rätt riktning men vardagligt, fel detalj eller osäkert skick.\n- 4–5: Kanske, men något skaver (fel färg, epok, material eller storlek).\n- 0–3: Fel sak, reproduktion, trasigt, eller sådant kunden redan har.\nKända formgivare och eftersökta serier ska inte dras ner för att de är serietillverkade.\n";
const REGIONER: Record<string, string> = {"stockholm": "Stockholm", "hägersten": "Stockholm", "västberga": "Stockholm", "ropsten": "Stockholm", "norrtälje": "Stockholm", "järna": "Stockholm", "jarna": "Stockholm", "södertälje": "Stockholm", "nacka": "Stockholm", "täby": "Stockholm", "lidingö": "Stockholm", "sollentuna": "Stockholm", "solna": "Stockholm", "sundbyberg": "Stockholm", "huddinge": "Stockholm", "haninge": "Stockholm", "värmdö": "Stockholm", "sigtuna": "Stockholm", "danderyd": "Stockholm", "upplands väsby": "Stockholm", "vallentuna": "Stockholm", "österåker": "Stockholm", "tyresö": "Stockholm", "botkyrka": "Stockholm", "ekerö": "Stockholm", "sickla": "Stockholm", "bromma": "Stockholm", "uppsala": "Uppsala och Mälardalen", "västerås": "Uppsala och Mälardalen", "örebro": "Uppsala och Mälardalen", "eskilstuna": "Uppsala och Mälardalen", "katrineholm": "Uppsala och Mälardalen", "nyköping": "Uppsala och Mälardalen", "enköping": "Uppsala och Mälardalen", "sala": "Uppsala och Mälardalen", "strängnäs": "Uppsala och Mälardalen", "köping": "Uppsala och Mälardalen", "arboga": "Uppsala och Mälardalen", "flen": "Uppsala och Mälardalen", "tierp": "Uppsala och Mälardalen", "östhammar": "Uppsala och Mälardalen", "norrköping": "Östergötland, Småland och Blekinge", "linköping": "Östergötland, Småland och Blekinge", "motala": "Östergötland, Småland och Blekinge", "söderköping": "Östergötland, Småland och Blekinge", "kalmar": "Östergötland, Småland och Blekinge", "växjö": "Östergötland, Småland och Blekinge", "jönköping": "Östergötland, Småland och Blekinge", "oskarshamn": "Östergötland, Småland och Blekinge", "karlshamn": "Östergötland, Småland och Blekinge", "karlskrona": "Östergötland, Småland och Blekinge", "västervik": "Östergötland, Småland och Blekinge", "vimmerby": "Östergötland, Småland och Blekinge", "värnamo": "Östergötland, Småland och Blekinge", "ljungby": "Östergötland, Småland och Blekinge", "nässjö": "Östergötland, Småland och Blekinge", "vadstena": "Östergötland, Småland och Blekinge", "mjölby": "Östergötland, Småland och Blekinge", "ronneby": "Östergötland, Småland och Blekinge", "visby": "Östergötland, Småland och Blekinge", "gotland": "Östergötland, Småland och Blekinge", "helsingborg": "Skåne", "lund": "Skåne", "landskrona": "Skåne", "malmö": "Skåne", "malmo": "Skåne", "trelleborg": "Skåne", "ängelholm": "Skåne", "engelholm": "Skåne", "höör": "Skåne", "höganäs": "Skåne", "ystad": "Skåne", "kristianstad": "Skåne", "hässleholm": "Skåne", "eslöv": "Skåne", "simrishamn": "Skåne", "båstad": "Skåne", "skurup": "Skåne", "staffanstorp": "Skåne", "gothenburg": "Västsverige och Värmland", "göteborg": "Västsverige och Värmland", "borås": "Västsverige och Värmland", "vänersborg": "Västsverige och Värmland", "varberg": "Västsverige och Värmland", "halmstad": "Västsverige och Värmland", "laholm": "Västsverige och Värmland", "henån": "Västsverige och Värmland", "lysekil": "Västsverige och Värmland", "uddevalla": "Västsverige och Värmland", "trollhättan": "Västsverige och Värmland", "kungsbacka": "Västsverige och Värmland", "alingsås": "Västsverige och Värmland", "skövde": "Västsverige och Värmland", "lidköping": "Västsverige och Värmland", "mariestad": "Västsverige och Värmland", "falkenberg": "Västsverige och Värmland", "karlstad": "Västsverige och Värmland", "arvika": "Västsverige och Värmland", "kristinehamn": "Västsverige och Värmland", "strömstad": "Västsverige och Värmland", "kungälv": "Västsverige och Värmland", "stenungsund": "Västsverige och Värmland", "falköping": "Västsverige och Värmland", "umeå": "Norrland och Dalarna", "falun": "Norrland och Dalarna", "sundsvall": "Norrland och Dalarna", "hudiksvall": "Norrland och Dalarna", "sandviken": "Norrland och Dalarna", "mora": "Norrland och Dalarna", "örnsköldsvik": "Norrland och Dalarna", "gävle": "Norrland och Dalarna", "luleå": "Norrland och Dalarna", "skellefteå": "Norrland och Dalarna", "östersund": "Norrland och Dalarna", "borlänge": "Norrland och Dalarna", "härnösand": "Norrland och Dalarna", "kiruna": "Norrland och Dalarna", "piteå": "Norrland och Dalarna", "bollnäs": "Norrland och Dalarna", "söderhamn": "Norrland och Dalarna", "ludvika": "Norrland och Dalarna", "leksand": "Norrland och Dalarna", "rättvik": "Norrland och Dalarna", "avesta": "Norrland och Dalarna", "hedemora": "Norrland och Dalarna"};
const UTESLUT: string[] = ["ikea", "plast", "reservdel", "defekt", "reproduktion"];
const MAX_KANDIDATER = 60;
const MIN_BETYG = 8;
const MAX_PER_SOKORD = 3;
const SPARR_MINUTER = 30;

function cors(origin: string | null) {
  const o = origin && TILLATNA_URSPRUNG.includes(origin) ? origin : TILLATNA_URSPRUNG[0];
  return { "Access-Control-Allow-Origin": o, "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info",
           "Access-Control-Allow-Methods": "POST, OPTIONS", "Vary": "Origin" };
}
function svar(data: unknown, status: number, origin: string | null) {
  return new Response(JSON.stringify(data), { status, headers: { ...cors(origin), "Content-Type": "application/json" } });
}

type Annons = { id: string; titel: string; url: string; beskrivning: string; pris: number | null; pris_text: string;
  bilder: string[]; plats: string; slutar: string; slutar_ts: number | null; kategori: string; sokord: string };

function rensaHtml(t: string | null | undefined) {
  return String(t ?? "").replace(/<br\s*\/?>/g, "\n").replace(/<[^>]+>/g, "")
    .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").trim();
}

function tolka(post: Record<string, any>, kategori: string, sokord: string): Annons | null {
  if (post.state !== "published") return null;
  const slut = post.ends_at as number | undefined;
  if (slut && slut < Date.now() / 1000) return null;
  if ((post.currency ?? "SEK") !== "SEK") return null;  // bara Sverige
  const hogsta = Math.max(0, ...((post.bids ?? []) as { amount: number }[]).map((b) => b.amount || 0));
  const utrop = post.estimate || 0;
  const belopp = hogsta || utrop;
  const bilder = ((post.images ?? []) as Record<string, string>[]).map((b) => b.w640 || b.hd).filter(Boolean);
  let beskrivning = rensaHtml(post.description);
  const skick = rensaHtml(post.condition);
  if (skick) beskrivning += "\nSkick: " + skick;
  const slutar = slut ? new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Stockholm", day: "numeric", month: "numeric",
    hour: "2-digit", minute: "2-digit" }).format(new Date(slut * 1000)).replace(/(\d+)\/(\d+) /, "$1/$2 ") : "";
  return {
    id: String(post.id), titel: String(post.title ?? "").trim(),
    url: String(post.url ?? "").replace("auctionet.com/en/", "auctionet.com/sv/"),
    beskrivning, pris: belopp || null, pris_text: hogsta ? `Bud ${hogsta} SEK` : `Utrop ${utrop} SEK`,
    bilder, plats: [post.house, post.location].filter(Boolean).join(", "), slutar, slutar_ts: slut ?? null, kategori, sokord,
  };
}

async function sokAuctionet(fraga: string): Promise<Record<string, any>[]> {
  const u = "https://auctionet.com/api/v2/items.json?per_page=48&page=1&q=" + encodeURIComponent(fraga);
  const r = await fetch(u, { headers: { "User-Agent": "Fyndjakt/1.0 (privat bevakning)" } });
  if (!r.ok) return [];
  return ((await r.json()).items ?? []) as Record<string, any>[];
}

function region(plats: string): [string, string] {
  const ort = plats.split(", ").pop()!.trim();
  if (!ort) return ["", "Övriga Sverige"];
  if (REGIONER[ort.toLowerCase()]) return [ort, REGIONER[ort.toLowerCase()]];
  const text = plats.toLowerCase();
  for (const k of Object.keys(REGIONER).sort((a, b) => b.length - a.length)) {
    if (new RegExp(`(?<![a-zåäö])${k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![a-zåäö])`).test(text))
      return [k.charAt(0).toUpperCase() + k.slice(1), REGIONER[k]];
  }
  return [ort, "Övriga Sverige"];
}

function profiltext(p: Record<string, any>): string {
  // Namnet och sökorden talar om VAD som söks, beskrivningen om stilen – samma text som nattkörningen (smak.py).
  const namn = String(p.namn ?? "").trim() || "Min bevakning";
  const exempel = Object.entries(p.sokningar ?? {}).map(([k, v]) => `${k}: ${(v as string[]).join(", ")}`).join("; ");
  const delar = [`Kunden letar begagnade och vintage-föremål i Sverige. Den här bevakningen heter «${namn}» – ` +
    `kunden letar alltså efter just den SORTENS föremål.`];
  if (exempel) delar.push(`Bevakningens sökord visar vad som avses: ${exempel}`);
  delar.push("Kundens egen beskrivning av sin stil och vad hen söker:\n" + (String(p.beskrivning ?? "").trim() || "(ingen beskrivning)"));
  delar.push(`VIKTIGT: Föremål av fel sort för bevakningen «${namn}» ger högst 3, hur fina eller stilrena de än är. ` +
    "Det räcker inte att föremålet passar hemmets färger – det måste vara det kunden letar efter.");
  const har = String(p.har_redan ?? "").split("\n").map((r) => r.replace(/^[\s\-•]+|[\s\-•]+$/g, "")).filter(Boolean);
  if (har.length) delar.push("Kunden HAR REDAN följande – ge 0–3 åt samma typ av föremål:\n- " + har.slice(0, 30).join("\n- "));
  return delar.join("\n\n");
}

function tolkaSvar(text: string): [number, string, string] {
  const m = text.match(/\{[\s\S]*\}/);
  try {
    const d = JSON.parse(m ? m[0] : "");
    return [parseInt(d.betyg) || 0, String(d.motivering ?? "").trim(), String(d.jamforsok ?? "").trim()];
  } catch {
    const b = text.match(/"betyg"\s*:\s*"?(\d+)/);
    const mo = text.match(/"motivering"\s*:\s*"([^"]*)/);
    return [b ? parseInt(b[1]) : 0, mo ? mo[1] : "", ""];
  }
}

async function bedom(nyckel: string, system: string, a: Annons): Promise<[number, string, string] | null> {
  const text = `Titel: ${a.titel}\nPris: ${a.pris_text}\nPlats: ${a.plats}\nBeskrivning: ${a.beskrivning.slice(0, 1200)}`;
  const fraga = async (medBilder: boolean) => fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "x-api-key": nyckel, "anthropic-version": "2023-06-01", "content-type": "application/json" },
    body: JSON.stringify({ model: MODELL, max_tokens: 400, system, messages: [{ role: "user", content: [
      ...(medBilder ? a.bilder.slice(0, 3).map((u) => ({ type: "image", source: { type: "url", url: u } })) : []),
      { type: "text", text }] }] }),
  });
  let r = await fraga(true);
  if (r.status === 400) r = await fraga(false);  // t.ex. en bild som inte gick att hämta
  if (!r.ok) { console.error("Anthropic", r.status, (await r.text()).slice(0, 300)); return null; }
  const d = await r.json();
  return tolkaSvar((d.content ?? []).filter((b: { type: string }) => b.type === "text").map((b: { text: string }) => b.text).join("\n"));
}

async function iParallell<T, R>(lista: T[], antal: number, f: (x: T) => Promise<R>, stopp: number): Promise<R[]> {
  const ut: R[] = []; let i = 0;
  await Promise.all(Array.from({ length: antal }, async () => {
    while (i < lista.length && Date.now() < stopp) { const x = lista[i++]; ut.push(await f(x)); }
  }));
  return ut;
}

Deno.serve(async (req) => {
  const origin = req.headers.get("origin");
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors(origin) });
  if (req.method !== "POST") return svar({ fel: "Endast POST" }, 405, origin);
  const start = Date.now();

  const anv = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_ANON_KEY")!, {
    global: { headers: { Authorization: req.headers.get("authorization") ?? "" } } });
  const { data: medlem } = await anv.rpc("fyndjakt_ar_medlem");
  if (!medlem) return svar({ fel: "Inte inloggad som Fyndjakt-användare" }, 403, origin);
  const { data: { user } } = await anv.auth.getUser();
  if (!user) return svar({ fel: "Inte inloggad" }, 401, origin);

  let kropp: { profil_id?: number };
  try { kropp = await req.json(); } catch { return svar({ fel: "Ogiltig förfrågan" }, 400, origin); }
  // Profilen läses med användarens egna rättigheter – man kan bara starta sina egna bevakningar.
  const { data: profil } = await anv.from("fyndjakt_profiler").select("*").eq("id", kropp.profil_id ?? -1).maybeSingle();
  if (!profil) return svar({ fel: "Hittar inte bevakningen" }, 404, origin);
  const sid = "p" + profil.id;

  const NAMN = ["ANTHROPIC_API_KEY", "ANTHROPIC_KEY", "CLAUDE_API_KEY", "CLAUDE_KEY", "ANTHROPIC_APIKEY"];
  const nyckel = NAMN.map((n) => (Deno.env.get(n) ?? "").trim()).find((v) => v);
  if (!nyckel) return svar({ fel: "Ingen Anthropic-nyckel i Supabase" }, 503, origin);

  const admin = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  const { data: rad } = await admin.from("fyndjakt_fynd").select("data").eq("user_id", user.id).maybeSingle();
  const data = (rad?.data ?? { spar: [], poster: [] }) as Record<string, any>;
  const senast = data.snabbstart?.[sid];
  if (senast && Date.now() - Date.parse(senast) < SPARR_MINUTER * 60_000)
    return svar({ fel: `Bevakningen letades igenom nyss – vänta en stund eller till i morgon bitti.` }, 429, origin);

  // 1. Sök – alla sökord parallellt (högst 6 åt gången, snällt mot Auctionet)
  const fragor: [string, string][] = [];
  for (const [kat, lista] of Object.entries(profil.sokningar ?? {}))
    for (const q of (lista as string[]).slice(0, 30)) fragor.push([kat, String(q).slice(0, 60)]);
  const traffar = await iParallell(fragor.slice(0, 30), 6, async ([kat, q]) =>
    (await sokAuctionet(q)).map((p) => tolka(p, kat, q)).filter((a): a is Annons => !!a), start + 25_000);

  // 2. Förfiltrera och välj kandidater – varva sökorden så att alla får chansen
  const sett = new Set<string>();
  const maxPris = profil.max_pris || 0;
  const grupper = traffar.map((l) => l.filter((a) => {
    if (sett.has(a.id)) return false; sett.add(a.id);
    const t = (a.titel + " " + a.beskrivning).toLowerCase();
    if (UTESLUT.some((o) => t.includes(o))) return false;
    return !(maxPris && a.pris && a.pris > maxPris);
  }));
  const kandidater: Annons[] = [];
  for (let i = 0; kandidater.length < MAX_KANDIDATER && grupper.some((g) => g.length > i); i++)
    for (const g of grupper) if (g[i] && kandidater.length < MAX_KANDIDATER) kandidater.push(g[i]);

  // 3. Claude bedömer – samma instruktion och regler som nattkörningen
  const system = INSTRUKTION.replace("{stil}", profiltext(profil)).replace("{kalibrering}", KALIBRERING.trim());
  const bedomda = await iParallell(kandidater, 8, async (a) => ({ a, r: await bedom(nyckel, system, a) }), start + 110_000);

  // 4. Bästa fynden, högst några per sökord
  const prefix = user.id.slice(0, 8) + "|";
  const per: Record<string, number> = {};
  const sedd = new Date().toISOString().replace("T", " ").slice(0, 19);
  const nya = bedomda.filter((x) => x.r && x.r[0] >= MIN_BETYG).sort((x, y) => y.r![0] - x.r![0]).filter((x) => {
    per[x.a.sokord] = (per[x.a.sokord] ?? 0) + 1; return per[x.a.sokord] <= MAX_PER_SOKORD;
  }).map(({ a, r }) => {
    const [ort, reg] = region(a.plats);
    return { nyckel: prefix + "auctionet:" + a.id, titel: a.titel, url: a.url, betyg: r![0], motivering: r![1],
      kalla: "auctionet", kategori: a.kategori, pris: a.pris, pris_text: a.pris_text, plats: a.plats, slutar: a.slutar,
      slutar_ts: a.slutar_ts, bilder: a.bilder.slice(0, 4), sedd, spar: sid, jamforsok: r![2],
      jmf_median: null, jmf_lag: null, jmf_hog: null, jmf_antal: null, ort, region: reg };
  });

  // 5. Spara – behåll det nattkörningen redan hittat
  const finns = new Set((data.poster ?? []).map((p: { nyckel: string }) => p.nyckel));
  data.poster = [...(data.poster ?? []), ...nya.filter((p) => !finns.has(p.nyckel))];
  data.spar = (data.spar ?? []).filter((s: { id: string }) => s.id !== sid);
  data.spar.push({ id: sid, namn: profil.namn, kategorier: Object.keys(profil.sokningar ?? {}), sokningar: profil.sokningar });
  data.snabbstart = { ...(data.snabbstart ?? {}), [sid]: new Date().toISOString() };
  data.uppdaterad = data.uppdaterad ?? new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Stockholm", day: "numeric",
    month: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date());
  const { error } = await admin.from("fyndjakt_fynd").upsert({ user_id: user.id, data, uppdaterad: new Date().toISOString() });
  if (error) { console.error(error); return svar({ fel: "Kunde inte spara fynden" }, 500, origin); }

  return svar({ sokta: fragor.length, annonser: sett.size, bedomda: bedomda.filter((x) => x.r).length, fynd: nya.length,
                sekunder: Math.round((Date.now() - start) / 1000) }, 200, origin);
});
