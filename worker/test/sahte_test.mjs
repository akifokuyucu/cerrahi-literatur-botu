// Worker'ı sahte Telegram/Gemini/GitHub ile uçtan uca dener.
// hafta_ornek.json: 29 Eylül 2026 listesinin sabit kopyası (cikti/hafta.json her hafta değişir)
import fs from "node:fs";
import worker, { sayiDenetimi } from "../src/index.js";

const hafta = JSON.parse(fs.readFileSync(new URL("./hafta_ornek.json", import.meta.url)));
const gundem = JSON.parse(fs.readFileSync(new URL("./gundem_ornek.json", import.meta.url)));
const giden = [];
const kv = new Map();
let gundemYok = false; // perşembeden önce gundem.json henüz yoksa
let geminiYogun = false; // tüm Gemini modelleri 503 versin
let detayDosyasi = null; // pazartesi hazırlanan detay.json (null: henüz yok)
globalThis.fetch = async (url, opt = {}) => {
  url = String(url);
  const json = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: { "content-type": "application/json" } });
  if (url.includes("raw.githubusercontent") && url.endsWith("gundem.json"))
    return gundemYok ? new Response("404: Not Found", { status: 404 }) : json(gundem);
  if (url.includes("raw.githubusercontent") && url.endsWith("detay.json"))
    return detayDosyasi ? json(detayDosyasi) : new Response("404: Not Found", { status: 404 });
  if (url.includes("raw.githubusercontent")) return json(hafta);
  if (url.includes("api.telegram.org")) {
    const metod = url.split("/").pop();
    giden.push({ metod, govde: JSON.parse(opt.body) });
    return json({ ok: true, result: {} });
  }
  if (url.includes("generativelanguage") && geminiYogun) {
    giden.push({ metod: "GEMINI_503", model: url.split("/models/")[1].split(":")[0] });
    return new Response("overloaded", { status: 503 });
  }
  if (url.includes("api.groq.com")) {
    const g = JSON.parse(opt.body);
    giden.push({ metod: "GROQ", model: g.model, json: g.response_format?.type, semaVar: g.messages[0].content.includes('"ana_bulgular"') });
    return json({ choices: [{ message: { content: "```json\n" + JSON.stringify({ baslik_tr: "Groq başlığı", tek_cumle: "Groq özeti", tasarim: "RCT", ana_bulgular: ["HR 0,8"], sinirliliklar: ["Tek merkez"], pratige_etkisi: "Sınırlı" }) + "\n```" } }] });
  }
  if (url.includes("generativelanguage")) {
    const g = JSON.parse(opt.body);
    const girdi = g.contents[0].parts[0].text;
    giden.push({ metod: "GEMINI", tamMetin: girdi.includes("TAM METİN:"), uzunluk: girdi.length, soru: girdi.includes("SORU:") });
    if (girdi.includes("SORU:")) return json({ candidates: [{ content: { parts: [{ text: JSON.stringify({ cevap: "Dışlama kriterleri Methods bölümünde: acil ameliyat." }) }] } }] });
    const d = { baslik_tr: "ICG anjiyografi ve anastomotic leak", tek_cumle: "Test <cümlesi> & özel karakter.",
      tasarim: "8 RCT'nin meta-analizi", pico: { P: "Kolorektal rezeksiyon", I: "ICG-FA", C: "Standart", O: "AL" },
      ana_bulgular: ["RR 0.68 (95% CI 0.58-0.81)"], guclu_yanlar: ["TSA"], sinirliliklar: ["Heterojen tanım"],
      pratige_etkisi: "Test", journal_club_sorulari: ["Soru 1?", "Soru 2?"] };
    return json({ candidates: [{ content: { parts: [{ text: JSON.stringify(d) }] } }] });
  }
  if (url.includes("api.notion.com")) {
    const g = opt.body ? JSON.parse(opt.body) : {};
    giden.push({ metod: "NOTION", yol: url.split("/v1/")[1], yontem: opt.method, govde: g });
    return json({ id: "sayfa-" + giden.length, url: "https://notion.so/sayfa-" + giden.length });
  }
  if (url.includes("europepmc")) {
    return new Response("<article><body><sec><title>Methods</title><p>" + "Uzun metin. ".repeat(400) + "</p></sec><ref-list>KAYNAKLAR</ref-list></body></article>");
  }
  throw new Error("beklenmeyen istek " + url);
};
const env = { TELEGRAM_TOKEN: "T", GEMINI_API_KEY: "G", GROQ_API_KEY: "Q", WEBHOOK_SECRET: "S", IZINLI_KULLANICI: "111",
  VERI_URL: "https://raw.githubusercontent.com/x/y/main/cikti/hafta.json",
  NOTION_TOKEN: "N", NOTION_ARSIV_DB: "arsivdb", NOTION_ICERIK_DB: "icerikdb",
  ONBELLEK: { get: async (k) => kv.get(k) ?? null, put: async (k, v) => kv.set(k, v), delete: async (k) => kv.delete(k),
    list: async ({ prefix }) => ({ keys: [...kv.keys()].filter((k) => k.startsWith(prefix)).map((name) => ({ name })), list_complete: true }) } };

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
kontrol("Menüde Kolorektal, Öne çıkanlar ve Gündem tuşu", ["a:kolorektal", '"g"', '"h"', "📰 Gündem"].every((x) => JSON.stringify(menu.govde.reply_markup).includes(x)));
// 4) Alan seçimi → liste (mesaj yerinde düzenlenir)
giden.length = 0; await gonder(tik(111, "a:kolorektal"));
const liste = giden.find((g) => g.metod === "editMessageText");
kontrol("Alan listesi düzenlendi", !!liste);
kontrol("Liste 4096 sınırında", liste.govde.text.length <= 4096);
kontrol("En az 5 ayrıntı tuşu", liste.govde.reply_markup.inline_keyboard[0].length >= 5);
console.log("\n--- Liste önizleme ---\n" + liste.govde.text + "\n---\n");
// 5) Haftanın öne çıkanları
giden.length = 0; await gonder(tik(111, "g"));
kontrol("Öne çıkanlar ekranı", giden.some((g) => g.metod === "editMessageText" && g.govde.text.includes("öne çıkanları")));
giden.length = 0; await gonder(mesaj(111, "/onecikanlar"));
kontrol("/onecikanlar komutu", giden.some((g) => g.metod === "sendMessage" && g.govde.text.includes("öne çıkanları")));
// 5b) 📰 Gündem: bölüm menüsü → bölüm listesi
giden.length = 0; await gonder(tik(111, "h"));
const gmenu = giden.find((g) => g.metod === "editMessageText");
kontrol("Gündem menüsü", gmenu && gmenu.govde.text.includes("Gündem") && ["h:kilavuz", "h:teknoloji", "h:yerli", "h:rct"].every((x) => JSON.stringify(gmenu.govde.reply_markup).includes(x)));
giden.length = 0; await gonder(tik(111, "h:rct"));
const rct = giden.find((g) => g.metod === "editMessageText");
kontrol("RCT listesi ClinicalTrials.gov bağlantılı", rct && rct.govde.text.includes("clinicaltrials.gov/study/NCT") && rct.govde.text.length <= 4096);
kontrol("RCT listesinde ← Gündem tuşu", JSON.stringify(rct.govde.reply_markup).includes('"h"'));
console.log("\n--- Gündem önizleme ---\n" + rct.govde.text + "\n---\n");
giden.length = 0; await gonder(tik(111, "h:teknoloji"));
kontrol("Birleştirilen haberde '+2 kaynak daha'", giden.some((g) => g.govde?.text?.includes("+2 kaynak daha")));
giden.length = 0; await gonder(tik(111, "h:yerli"));
kontrol("Boş bölümde açıklama", giden.some((g) => g.govde?.text?.includes("kayda değer bir gelişme yok")));
// Çok uzun liste: HTML ortadan kesilmez, sığmayan haber dışarıda kalır
const eskiRct = gundem.bolumler.rct.ogeler;
gundem.bolumler.rct.ogeler = Array.from({ length: 12 }, (_, i) => ({ ...eskiRct[0], ozet: "Uzun <özet> ".repeat(40) + i }));
giden.length = 0; await gonder(tik(111, "h:rct"));
const uzun = giden.find((g) => g.metod === "editMessageText").govde.text;
kontrol("Uzun gündem 4096 sınırında ve bütün bloklarla", uzun.length <= 4096 && uzun.trim().endsWith("kaynağa bak.</i>") && (uzun.match(/<a /g) || []).length < 12);
gundem.bolumler.rct.ogeler = eskiRct;
giden.length = 0; await gonder(mesaj(111, "/gundem"));
kontrol("/gundem komutu gündemi açar", giden.some((g) => g.metod === "sendMessage" && g.govde.text.includes("kılavuzlar, teknoloji")));
gundemYok = true;
giden.length = 0; await gonder(tik(111, "h"));
kontrol("gundem.json yokken açıklayıcı mesaj", giden.some((g) => g.govde?.text?.includes("henüz çıkmadı")));
gundemYok = false;
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

// 11) Ayrıntılı özetin altında yeni tuşlar
giden.length = 0; await gonder(tik(111, "d:42778806"));
const detayMesaj = giden.filter((g) => g.metod === "sendMessage").pop();
const tuslar = JSON.stringify(detayMesaj.govde.reply_markup);
kontrol("Detayda 👍/👎, Arşiv, İçerik, Soru tuşları", ["o:1:42778806", "o:0:42778806", "n:42778806", "i:42778806", "s:42778806"].every((x) => tuslar.includes(x)));
// 12) 👍 oy kaydı
giden.length = 0; await gonder({ callback_query: { id: "q", from: { id: 111 }, data: "o:1:42778806", message: { message_id: 9, chat: { id: 111 } } } });
kontrol("Oy KV'ye yazıldı", JSON.parse(kv.get("oy:42778806")).oy === 1);
kontrol("Tuşta seçim işaretlendi", giden.some((g) => g.metod === "editMessageReplyMarkup" && JSON.stringify(g.govde).includes("✅ 👍")));
// 13) Arşive ekle → Notion sayfası
giden.length = 0; await gonder(tik(111, "n:42778806"));
const nsayfa = giden.find((g) => g.metod === "NOTION");
kontrol("Notion Okuma Arşivi'ne sayfa açıldı", nsayfa && nsayfa.govde.parent.database_id === "arsivdb");
kontrol("Arşiv özellikleri doğru", nsayfa.govde.properties["Oyum"].select.name === "👍 Faydalı" && nsayfa.govde.properties["Kaynak"].select.name === "Tam metin" && nsayfa.govde.properties["Alan"].select.name === "Kolorektal");
kontrol("Arşiv bağlantısı gönderildi", giden.some((g) => g.metod === "sendMessage" && g.govde.text.includes("Okuma Arşivi")));
// 14) İkinci kez arşiv → tekrar sayfa açılmaz
giden.length = 0; await gonder(tik(111, "n:42778806"));
kontrol("Aynı makale iki kez arşivlenmez", !giden.some((g) => g.metod === "NOTION") && giden.some((g) => g.govde?.text?.includes("zaten arşivde")));
// 15) Arşivdeki makalede oy değişince Notion güncellenir
giden.length = 0; await gonder({ callback_query: { id: "q", from: { id: 111 }, data: "o:0:42778806", message: { message_id: 9, chat: { id: 111 } } } });
kontrol("Oy değişimi Notion'a yansıdı", giden.some((g) => g.metod === "NOTION" && g.yontem === "PATCH" && g.govde.properties["Oyum"].select.name === "👎 Değil"));
// 16) İçerik adayı → İçerik Havuzu
giden.length = 0; await gonder(tik(111, "i:42778806"));
const icerik = giden.find((g) => g.metod === "NOTION");
kontrol("İçerik Havuzu'na 'fikir' olarak eklendi", icerik && icerik.govde.parent.database_id === "icerikdb" && icerik.govde.properties["Durum"].select.name === "fikir" && icerik.govde.properties["Köken"].select.name === "Literatür botu");
// 17) Soru sor → soru modu → cevap
giden.length = 0; await gonder(tik(111, "s:42778806"));
kontrol("Soru modu açıldı", giden.some((g) => g.metod === "sendMessage" && g.govde.reply_markup?.force_reply));
giden.length = 0; await gonder(mesaj(111, "Dışlama kriterleri neydi?"));
kontrol("Soru Gemini'ye tam metinle gitti", giden.some((g) => g.metod === "GEMINI" && g.soru && g.tamMetin));
kontrol("Cevap gönderildi", giden.some((g) => g.metod === "sendMessage" && g.govde.text.includes("Dışlama kriterleri Methods")));
// 18) /iptal → normal menüye dönüş
giden.length = 0; await gonder(mesaj(111, "/iptal")); giden.length = 0; await gonder(mesaj(111, "merhaba"));
kontrol("İptalden sonra metin menüyü açar", giden.some((g) => g.metod === "sendMessage" && g.govde.text.includes("Hangi alana")));
// 19) /istatistik
giden.length = 0; await gonder(mesaj(111, "/istatistik"));
kontrol("İstatistik gösterildi", giden.some((g) => g.govde?.text?.includes("Geri bildirimlerin") && g.govde.text.includes("Tech Coloproctol")));
// 20) Geri bildirim uç noktası: anahtarsız 403, anahtarla JSON
kontrol("Geri bildirim ucu anahtarsız 403", (await worker.fetch(new Request("https://bot.example/geri-bildirim"), env, {})).status === 403);
const gb = await (await worker.fetch(new Request("https://bot.example/geri-bildirim", { headers: { "X-Bot-Anahtar": "S" } }), env, {})).json();
kontrol("Geri bildirim ucu oyları döndürür", gb.length === 1 && gb[0].dergi === "Tech Coloproctol" && gb[0].oy === 0);
// 21) Notion token yoksa uyarı
giden.length = 0; await worker.fetch(new Request("https://bot.example/telegram", { method: "POST", headers: { "X-Telegram-Bot-Api-Secret-Token": "S" }, body: JSON.stringify(tik(111, "n:42776522")) }), { ...env, NOTION_TOKEN: "" }, {});
kontrol("Notion yoksa açıklayıcı uyarı", giden.some((g) => g.metod === "answerCallbackQuery" && g.govde.text?.includes("NOTION_TOKEN")));

// 22) Gemini yoğunken Google dışı yedeğe geçilir
const eskiZamanlayici = globalThis.setTimeout;
globalThis.setTimeout = (f) => f(); // yeniden deneme beklemesini atla
geminiYogun = true;
kv.delete("detay:42776522");
giden.length = 0; await gonder(tik(111, "d:42776522"));
const gemDenenen = [...new Set(giden.filter((g) => g.metod === "GEMINI_503").map((g) => g.model))];
kontrol("Gemini yoğunken önce güçlü Gemini modelleri denendi", ["gemini-flash-latest", "gemini-3.7-flash", "gemini-3.5-flash"].every((m) => gemDenenen.includes(m)));
kontrol("Lite modellerden önce Google dışı yedeğe geçildi", !gemDenenen.some((m) => m.includes("lite")));
const groq = giden.find((g) => g.metod === "GROQ");
kontrol("Sonra Groq'a JSON modu ve şemayla gidildi", groq && groq.json === "json_object" && groq.semaVar);
kontrol("Groq yanıtıyla ayrıntılı özet gönderildi", giden.some((g) => g.metod === "sendMessage" && g.govde.text.includes("Groq özeti")));
kontrol("Kayıtta modeli tutuldu", JSON.parse(kv.get("detay:42776522")).model === "groq/openai/gpt-oss-120b");
// 23) Groq anahtarı yoksa Workers AI devreye girer
kv.delete("detay:42776522");
let aiGirdi = null;
const aiEnv = { ...env, GROQ_API_KEY: "", AI: { run: async (model, g) => { aiGirdi = { model, g }; return { response: { cevap: "Workers AI cevabı" } }; } } };
await worker.fetch(new Request("https://bot.example/telegram", { method: "POST", headers: { "X-Telegram-Bot-Api-Secret-Token": "S" }, body: JSON.stringify(tik(111, "s:42778806")) }), aiEnv, {});
giden.length = 0;
await worker.fetch(new Request("https://bot.example/telegram", { method: "POST", headers: { "X-Telegram-Bot-Api-Secret-Token": "S" }, body: JSON.stringify(mesaj(111, "Hasta sayısı?")) }), aiEnv, {});
kontrol("Workers AI'a JSON şemasıyla gidildi", aiGirdi && aiGirdi.g.response_format.type === "json_schema" && aiGirdi.g.response_format.json_schema.type === "object");
kontrol("Workers AI cevabı gönderildi", giden.some((g) => g.metod === "sendMessage" && g.govde.text.includes("Workers AI cevabı")));
// 24) Hiçbiri yanıt vermezse anlaşılır hata
kv.delete("detay:42776522");
giden.length = 0;
await worker.fetch(new Request("https://bot.example/telegram", { method: "POST", headers: { "X-Telegram-Bot-Api-Secret-Token": "S" }, body: JSON.stringify(tik(111, "d:42776522")) }), { ...env, GROQ_API_KEY: "" }, {});
kontrol("Hepsi yoğunken kullanıcıya açıklama", giden.some((g) => g.govde?.text?.includes("yanıt vermiyor")));
geminiYogun = false;
globalThis.setTimeout = eskiZamanlayici;

// 25) Pazartesi hazırlanan ayrıntılı özet yapay zekâ çağırmadan gelir
const hazirPmid = hafta.alanlar.kolorektal.makaleler.map((m) => m.pmid)
  .find((p) => !["42778806", "42776522"].includes(p));
detayDosyasi = { hazirlanma: "2026-09-29", detaylar: { [hazirPmid]: {
  d: { baslik_tr: "Hazır başlık", tek_cumle: "Pazartesi hazırlanan özet", tasarim: "RCT",
    ana_bulgular: ["OR 0,5"], sinirliliklar: ["Kısa izlem"], pratige_etkisi: "Orta" },
  tam: true, model: "gemini-flash-latest" } } };
giden.length = 0; await gonder(tik(111, `d:${hazirPmid}`));
kontrol("Hazır özet yapay zekâsız gönderildi", !giden.some((g) => ["GEMINI", "GEMINI_503", "GROQ"].includes(g.metod)) &&
  giden.some((g) => g.metod === "sendMessage" && g.govde.text.includes("Pazartesi hazırlanan özet") && g.govde.text.includes("🔓 Tam metin")));
kontrol("Hazır özet KV'ye kopyalandı (makale bilgisiyle)", JSON.parse(kv.get(`detay:${hazirPmid}`)).m.pmid === hazirPmid);
detayDosyasi = null;

// 26) Uydurma sayı denetimi (motor/denetim.py ile aynı sonuçlar)
const KAYNAK = "In this RCT of 1,250 patients, leak rate was 4.8% vs 13.50% (RR 0.35; 95% CI 0.12-0.98; P = .047). Median follow-up 24 months.";
kontrol("Sayı denetimi: biçim farkları kabul", sayiDenetimi("1.250 hastalık RCT'de kaçak %4,8'e karşı %13,5 (RR 0,35; %95 CI 0,12-0,98; p=0,047); 24 ay izlem, 3 kol.", KAYNAK).length === 0);
kontrol("Sayı denetimi: binlik ayırıcısız", sayiDenetimi("1250 hasta", KAYNAK).length === 0);
kontrol("Sayı denetimi: uydurmalar bulunur", JSON.stringify(sayiDenetimi("HR 0,72 bulundu; %13,5 ve 1.300 hasta; NNT 12.", KAYNAK)) === '["0,72","1.300","12"]');
kontrol("Sayı denetimi: yazıyla sayı ve boşluklu binlik", sayiDenetimi("36 hasta, 17 çalışma, 53562 €, 90", "Thirty-six patients and Seventeen studies; cost €53 562 vs ninety.").length === 0);
// 27) Uyarılı özetler listede ⚠️ ile işaretlenir
hafta.alanlar.kolorektal.makaleler[0].sayi_uyarisi = ["0,7"];
giden.length = 0; await gonder(tik(111, "a:kolorektal"));
const uyariliListe = giden.find((g) => g.metod === "editMessageText").govde.text;
kontrol("Listede ⚠️ işareti ve açıklama", uyariliListe.includes(" ⚠️\n") && uyariliListe.includes("kaynak metinde bulunamadı"));
delete hafta.alanlar.kolorektal.makaleler[0].sayi_uyarisi;
// 28) Anlık üretilen ayrıntılı özette uydurma sayı uyarısı
geminiYogun = true; globalThis.setTimeout = (f) => f();
kv.delete("detay:42776522");
giden.length = 0; await gonder(tik(111, "d:42776522"));
const uyariliDetay = giden.filter((g) => g.metod === "sendMessage").map((g) => g.govde.text).join("\n");
kontrol("Ayrıntılı özette doğrulanamayan sayı uyarısı", uyariliDetay.includes("Şu sayılar kaynak metinde bulunamadı") && JSON.parse(kv.get("detay:42776522")).sayi_uyarisi?.length > 0);
geminiYogun = false; globalThis.setTimeout = eskiZamanlayici;

// 29) Yedek model kullanıldıysa menüde not, ayrıntılı özette model adı
hafta.ana_model = "gemini-flash-latest";
hafta.model_kullanimi = { "gemini-flash-latest": 20, "groq/openai/gpt-oss-120b": 8 };
giden.length = 0; await gonder(mesaj(111, "/start"));
const yedekMenu = giden.find((g) => g.metod === "sendMessage").govde.text;
kontrol("Menüde yedek model notu", yedekMenu.includes("yedek modelle") && yedekMenu.includes("groq/openai/gpt-oss-120b (8 istek)") && !yedekMenu.includes("gemini-flash-latest (20"));
hafta.model_kullanimi = { "gemini-flash-latest": 28 };
giden.length = 0; await gonder(mesaj(111, "/start"));
kontrol("Yedek yoksa not yok", !giden.find((g) => g.metod === "sendMessage").govde.text.includes("yedek modelle"));
delete hafta.ana_model; delete hafta.model_kullanimi;
giden.length = 0; await gonder(tik(111, "d:42776522"));
kontrol("Ayrıntılı özette model adı", giden.some((g) => g.metod === "sendMessage" && g.govde.text.includes("Yapay zekâ özetidir (groq/openai/gpt-oss-120b)")));
kontrol("Sayı denetimi: %95 CI kalıbı denetlenmez", JSON.stringify(sayiDenetimi("%95 CI belirtilmemiş; 95% CI ve %95 güven aralığı da yok. Ama %95 başarı.", "no numbers here")) === '["95"]');
