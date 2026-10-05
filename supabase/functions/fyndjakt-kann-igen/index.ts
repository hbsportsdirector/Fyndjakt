// Fyndjakt: känner igen ett fotograferat föremål med Claude, och föreslår sökord för en ny profil (typ: "profil").
// Kräver inloggad Fyndjakt-medlem. Anthropic-nyckeln ligger som hemlighet ANTHROPIC_API_KEY i Supabase.
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
  const { data: medlem, error: medlemsfel } = await supabase.rpc("fyndjakt_ar_medlem");
  if (medlemsfel || !medlem) return svar({ fel: "Inte inloggad som Fyndjakt-användare" }, 403, origin);

  // Godta vanliga namnvarianter; trimma bort mellanslag som lätt följer med vid inklistring.
  const NAMN = ["ANTHROPIC_API_KEY", "ANTHROPIC_KEY", "CLAUDE_API_KEY", "CLAUDE_KEY", "ANTHROPIC_APIKEY"];
  const nyckel = NAMN.map((n) => (Deno.env.get(n) ?? "").trim()).find((v) => v);
  if (!nyckel) {
    // Visa bara NAMNEN på hemligheter som liknar en Claude-nyckel – aldrig värdena.
    const liknande = Object.keys(Deno.env.toObject()).filter((n) => /anthropic|claude|api_?key/i.test(n));
    return svar({ fel: "Fotofunktionen hittar ingen Anthropic-nyckel. Lägg in den som ANTHROPIC_API_KEY under Edge Functions → Secrets i projektet WORK." +
      (liknande.length ? " Hittade bara: " + liknande.join(", ") : "") }, 503, origin);
  }

  let kropp: { typ?: string; bild?: string; bilder?: string[]; mediatyp?: string; samtal?: { roll: string; text: string }[];
               beskrivning?: string; har_redan?: string; namn?: string };
  try { kropp = await req.json(); } catch { return svar({ fel: "Ogiltig förfrågan" }, 400, origin); }

  if (kropp.typ === "profil") {
    if (String(kropp.beskrivning ?? "").trim().length < 10) return svar({ fel: "Beskriv lite mer först" }, 400, origin);
    const res = await profilforslag(nyckel, kropp);
    return res ? svar(res, 200, origin) : svar({ fel: "Kunde inte ta fram sökord just nu" }, 502, origin);
  }
  const bilder = (kropp.bilder?.length ? kropp.bilder : [kropp.bild ?? ""])
    .map((b) => String(b ?? "").replace(/^data:image\/\w+;base64,/, "")).filter((b) => b).slice(0, 4);
  const mediatyp = ["image/jpeg", "image/png", "image/webp"].includes(kropp.mediatyp ?? "") ? kropp.mediatyp! : "image/jpeg";
  if (!bilder.length || bilder.some((b) => b.length > MAX_BILD)) return svar({ fel: "Bilden saknas eller är för stor" }, 400, origin);

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
