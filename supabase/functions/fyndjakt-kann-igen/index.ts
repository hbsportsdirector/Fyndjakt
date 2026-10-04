// Fyndjakt: känner igen ett fotograferat föremål med Claude.
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

const INSTRUKTION = `Du hjälper en samlare och inredningsintresserad person att identifiera föremål från foton.
Titta på bilden och beskriv föremålet så exakt du kan: typ, material, färg, stil/epok och – om det går att
se eller är troligt – tillverkare, formgivare eller konstnär. Gissa inte vilt; säg "troligen" när du är osäker.
Svara ENBART med JSON:
{"beskrivning": "<en mening på svenska, t.ex. 'Bankirlampa i mässing med grön glaskupa, tidigt 1900-tal'>",
 "sokord": "<2–4 ord som hittar liknande föremål på en svensk auktionssajt, t.ex. 'bankirlampa mässing'>",
 "kategori": "<en av: Möbler, Belysning, Konst, Glas, Keramik, Textil, Dekor, Övrigt>",
 "sakerhet": "<hög|medel|låg>"}`;

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

  let kropp: { bild?: string; mediatyp?: string };
  try { kropp = await req.json(); } catch { return svar({ fel: "Ogiltig förfrågan" }, 400, origin); }
  const bild = (kropp.bild ?? "").replace(/^data:image\/\w+;base64,/, "");
  const mediatyp = ["image/jpeg", "image/png", "image/webp"].includes(kropp.mediatyp ?? "") ? kropp.mediatyp! : "image/jpeg";
  if (!bild || bild.length > MAX_BILD) return svar({ fel: "Bilden saknas eller är för stor" }, 400, origin);

  const r = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "x-api-key": nyckel, "anthropic-version": "2023-06-01", "content-type": "application/json" },
    body: JSON.stringify({
      model: MODELL,
      max_tokens: 300,
      system: INSTRUKTION,
      messages: [{ role: "user", content: [
        { type: "image", source: { type: "base64", media_type: mediatyp, data: bild } },
        { type: "text", text: "Vad är det här för föremål?" },
      ] }],
    }),
  });
  if (!r.ok) {
    console.error("Anthropic", r.status, await r.text());
    return svar({ fel: "Kunde inte analysera bilden just nu" }, 502, origin);
  }
  const data = await r.json();
  const text: string = data?.content?.[0]?.text ?? "";
  const match = text.match(/\{[\s\S]*\}/);
  try {
    const res = JSON.parse(match ? match[0] : "{}");
    return svar({
      beskrivning: String(res.beskrivning ?? "").slice(0, 300),
      sokord: String(res.sokord ?? "").slice(0, 60),
      kategori: String(res.kategori ?? ""),
      sakerhet: String(res.sakerhet ?? ""),
    }, 200, origin);
  } catch {
    return svar({ fel: "Kunde inte tolka svaret" }, 502, origin);
  }
});
