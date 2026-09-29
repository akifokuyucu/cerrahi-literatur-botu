// Worker'ı sahte Telegram/Gemini/GitHub ile uçtan uca dener.
import fs from "node:fs";
import worker from "../src/index.js";

const hafta = JSON.parse(fs.readFileSync(new URL("../../cikti/hafta.json", import.meta.url)));
const giden = [];
const kv = new Map();
globalThis.fetch = async (url, opt = {}) => {
  url = String(url);
  const json = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: { "content-type": "application/json" } });
  if (url.includes("raw.githubusercontent")) return json(hafta);
  if (url.includes("api.telegram.org")) {
    const metod = url.split("/").pop();
    giden.push({ metod, govde: JSON.parse(opt.body) });
    return json({ ok: true, result: {} });
  }
  if (url.includes("generativelanguage")) {
    const g = JSON.parse(opt.body);
    const girdi = g.contents[0].parts[0].text;
    giden.push({ metod: "GEMINI", tamMetin: girdi.includes("TAM METİN:"), uzunluk: girdi.length });
    const d = { baslik_tr: "ICG anjiyografi ve anastomotic leak", tek_cumle: "Test <cümlesi> & özel karakter.",
      tasarim: "8 RCT'nin meta-analizi", pico: { P: "Kolorektal rezeksiyon", I: "ICG-FA", C: "Standart", O: "AL" },
      ana_bulgular: ["RR 0.68 (95% CI 0.58-0.81)"], guclu_yanlar: ["TSA"], sinirliliklar: ["Heterojen tanım"],
      pratige_etkisi: "Test", journal_club_sorulari: ["Soru 1?", "Soru 2?"] };
    return json({ candidates: [{ content: { parts: [{ text: JSON.stringify(d) }] } }] });
  }
  if (url.includes("europepmc")) {
    return new Response("<article><body><sec><title>Methods</title><p>" + "Uzun metin. ".repeat(400) + "</p></sec><ref-list>KAYNAKLAR</ref-list></body></article>");
  }
  throw new Error("beklenmeyen istek " + url);
};
const env = { TELEGRAM_TOKEN: "T", GEMINI_API_KEY: "G", WEBHOOK_SECRET: "S", IZINLI_KULLANICI: "111",
  VERI_URL: "https://raw.githubusercontent.com/x/y/main/cikti/hafta.json",
  ONBELLEK: { get: async (k) => kv.get(k) ?? null, put: async (k, v) => kv.set(k, v), delete: async (k) => kv.delete(k) } };

const gonder = (u, sirr = "S") => worker.fetch(new Request("https://bot.example/telegram", {
  method: "POST", headers: { "X-Telegram-Bot-Api-Secret-Token": sirr }, body: JSON.stringify(u) }), env, {});
const mesaj = (id, text) => ({ message: { from: { id }, chat: { id }, text } });
const tik = (id, data) => ({ callback_query: { id: "q", from: { id }, data, message: { message_id: 5, chat: { id } } } });
const kontrol = (ad, kosul) => { console.log((kosul ? "✅ " : "❌ ") + ad); if (!kosul) process.exitCode = 1; };

// 1) Yanlış gizli anahtar reddedilir
kontrol("Yanlış webhook anahtarı 403", (await gonder(mesaj(111, "/start"), "yanlis")).status === 403);
// 2) Yabancı kullanıcıya cevap verilmez
giden.length = 0; await gonder(mesaj(999, "/start"));
kontrol("Yabancı kullanıcıya sessiz", giden.length === 0);
// 3) /start → menü
giden.length = 0; await gonder(mesaj(111, "/start"));
const menu = giden.find((g) => g.metod === "sendMessage");
kontrol("Menü gönderildi", menu && menu.govde.text.includes("Hangi alana"));
kontrol("Menüde Kolorektal ve Gündem tuşu", JSON.stringify(menu.govde.reply_markup).includes("a:kolorektal") && JSON.stringify(menu.govde.reply_markup).includes('"g"'));
// 4) Alan seçimi → liste (mesaj yerinde düzenlenir)
giden.length = 0; await gonder(tik(111, "a:kolorektal"));
const liste = giden.find((g) => g.metod === "editMessageText");
kontrol("Alan listesi düzenlendi", !!liste);
kontrol("Liste 4096 sınırında", liste.govde.text.length <= 4096);
kontrol("5 ayrıntı tuşu", liste.govde.reply_markup.inline_keyboard[0].length === 5);
console.log("\n--- Liste önizleme ---\n" + liste.govde.text + "\n---\n");
// 5) Gündem
giden.length = 0; await gonder(tik(111, "g"));
kontrol("Gündem ekranı", giden.some((g) => g.metod === "editMessageText" && g.govde.text.includes("gündemde")));
// 6) Ayrıntılı özet: açık erişimli (PMC) makale → tam metin
giden.length = 0; await gonder(tik(111, "d:42778806"));
const gem = giden.find((g) => g.metod === "GEMINI");
kontrol("Gemini'ye tam metin gitti", gem && gem.tamMetin);
const detay = giden.filter((g) => g.metod === "sendMessage").map((g) => g.govde.text).join("\n");
kontrol("Detayda 'Tam metin' etiketi", detay.includes("🔓 Tam metin"));
kontrol("HTML kaçışı yapıldı", detay.includes("&lt;cümlesi&gt; &amp;"));
console.log("\n--- Detay önizleme ---\n" + detay + "\n---\n");
// 7) Aynı makale ikinci kez → önbellekten, Gemini çağrılmaz
giden.length = 0; await gonder(tik(111, "d:42778806"));
kontrol("İkinci istek önbellekten", !giden.some((g) => g.metod === "GEMINI") && giden.some((g) => g.metod === "sendMessage"));
// 8) Kapalı erişimli makale → yalnızca özet
giden.length = 0; await gonder(tik(111, "d:42776522"));
kontrol("Kapalı erişimde 'yalnızca özet' uyarısı", giden.some((g) => g.metod === "sendMessage" && g.govde.text.includes("Yalnızca özet")));
// 9) Kurulum modu
giden.length = 0; await worker.fetch(new Request("https://bot.example/telegram", { method: "POST", headers: { "X-Telegram-Bot-Api-Secret-Token": "S" }, body: JSON.stringify(mesaj(222, "/start")) }), { ...env, IZINLI_KULLANICI: "" }, {});
kontrol("Kurulum modunda numara söylenir", giden[0]?.govde.text.includes("222"));
// 10) /kurulum sayfası
const r = await worker.fetch(new Request("https://bot.example/kurulum?anahtar=S"), env, {});
kontrol("Kurulum sayfası çalışır", (await r.text()).includes("Kurulum tamam"));
