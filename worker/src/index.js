/**
 * Cerrahi Literatür Botu — Telegram botu (Cloudflare Worker)
 *
 * Ayarlar (Cloudflare panelinde "Variables and Secrets"):
 *   TELEGRAM_TOKEN     (gizli) BotFather'ın verdiği token
 *   GEMINI_API_KEY     (gizli) Google AI Studio anahtarı
 *   WEBHOOK_SECRET     (gizli) Kendi uydurduğun uzun rastgele bir parola
 *   VERI_URL           hafta.json'un GitHub "raw" adresi
 *   IZINLI_KULLANICI   Telegram kullanıcı numaran (boşsa bot numaranı söyler)
 *   GEMINI_MODEL       (isteğe bağlı) varsayılan: gemini-flash-latest
 * Bağlantı (Binding):
 *   ONBELLEK           (isteğe bağlı) KV alanı — ayrıntılı özetleri saklar
 */

const TG = (env, metod) => `https://api.telegram.org/bot${env.TELEGRAM_TOKEN}/${metod}`;
const SINIR = 4000; // Telegram mesaj sınırı 4096

// ---------------------------------------------------------------- yardımcılar
const esc = (s) =>
  String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

async function tg(env, metod, govde) {
  const r = await fetch(TG(env, metod), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(govde),
  });
  const j = await r.json().catch(() => ({}));
  if (!j.ok && !String(j.description || "").includes("message is not modified")) {
    console.log("Telegram hatası", metod, j.description);
  }
  return j;
}

function parcala(metin) {
  // Uzun mesajları paragraf sınırlarından böler
  const parcalar = [];
  let simdiki = "";
  for (const p of metin.split("\n\n")) {
    if ((simdiki + "\n\n" + p).length > SINIR && simdiki) {
      parcalar.push(simdiki);
      simdiki = p;
    } else {
      simdiki = simdiki ? simdiki + "\n\n" + p : p;
    }
  }
  if (simdiki) parcalar.push(simdiki);
  return parcalar;
}

async function haftaVerisi(env) {
  const r = await fetch(env.VERI_URL, { cf: { cacheTtl: 300 } });
  if (!r.ok) throw new Error("hafta.json okunamadı: " + r.status);
  return r.json();
}

function makaleBul(veri, pmid) {
  for (const a of Object.values(veri.alanlar || {})) {
    for (const m of [...a.makaleler, a.turk]) if (m && m.pmid === pmid) return m;
  }
  return null;
}

const pubmedLink = (pmid) => `https://pubmed.ncbi.nlm.nih.gov/${pmid}/`;

// ------------------------------------------------------------------ ekranlar
function menuEkrani(veri) {
  const metin =
    `🩺 <b>Cerrahi Literatür</b>\n${esc(veri.hafta)}\n\nHangi alana bakalım?`;
  const tuslar = Object.entries(veri.alanlar).map(([kod, a]) => ({
    text: a.ad, callback_data: `a:${kod}`,
  }));
  const satirlar = [];
  for (let i = 0; i < tuslar.length; i += 2) satirlar.push(tuslar.slice(i, i + 2));
  satirlar.push([{ text: "🔥 Bu hafta gündemde", callback_data: "g" }]);
  return { metin, klavye: satirlar };
}

function makaleBlogu(no, m, ekEtiket = "") {
  const baslik = m.baslik_tr || m.baslik;
  const acik = m.pmc ? " · 🔓 tam metin açık" : "";
  return (
    `<b>${no}. ${esc(m.tip_etiketi)} · ${esc(m.dergi)}</b>${ekEtiket}\n` +
    `<i>${esc(baslik)}</i>\n` +
    (m.kisa_ozet ? `${esc(m.kisa_ozet)}\n` : "") +
    `<a href="${pubmedLink(m.pmid)}">PubMed</a>${acik}`
  );
}

function sigdir(bloklar, bas, son) {
  // Toplam uzunluk sınırı aşılırsa kısa özetleri kısaltır
  let metin = [bas, ...bloklar, son].filter(Boolean).join("\n\n");
  if (metin.length <= SINIR) return metin;
  const kisalt = bloklar.map((b) => b.replace(/\n([^<\n][^\n]{220})[^\n]+\n/, "\n$1…\n"));
  return [bas, ...kisalt, son].filter(Boolean).join("\n\n").slice(0, SINIR);
}

function alanEkrani(veri, kod) {
  const a = veri.alanlar[kod];
  if (!a) return { metin: "Bu alan bu hafta hazırlanamadı.", klavye: [[geriTusu]] };
  const bas =
    `<b>${esc(a.ad)}</b> — bu haftanın öne çıkanları\n` +
    `${esc(veri.hafta)} · ${a.taranan} makale tarandı`;
  const bloklar = a.makaleler.map((m, i) =>
    makaleBlogu(i + 1, m, ` · ${m.toplam} puan`));
  let not = "";
  if (a.makaleler.length === 0) not = "Bu hafta bu alanda öne çıkan çalışma yok.";
  else if (a.makaleler.length < 5)
    not = `Bu hafta bu alanda ${a.makaleler.length} güçlü çalışma var.`;
  if (not) bloklar.push(`<i>${not}</i>`);
  if (a.turk) {
    bloklar.push(
      "─────────────\n" +
        `🇹🇷 <b>Turkish J Surg'dan</b> · ${esc(a.turk.tip_etiketi)}\n` +
        `<i>${esc(a.turk.baslik_tr || a.turk.baslik)}</i>\n` +
        (a.turk.kisa_ozet ? `${esc(a.turk.kisa_ozet)}\n` : "") +
        `<a href="${pubmedLink(a.turk.pmid)}">PubMed</a> · 🔓 tam metin açık`
    );
  }
  const son = a.makaleler.length || a.turk ? "📄 Ayrıntılı özet için numaraya bas." : "";
  const detay = a.makaleler.map((m, i) => ({ text: `📄 ${i + 1}`, callback_data: `d:${m.pmid}` }));
  if (a.turk) detay.push({ text: "📄 🇹🇷", callback_data: `d:${a.turk.pmid}` });
  const klavye = [];
  if (detay.length) klavye.push(detay);
  klavye.push([geriTusu]);
  return { metin: sigdir(bloklar, bas, son), klavye };
}

function gundemEkrani(veri) {
  const bas = `🔥 <b>Bu hafta gündemde</b>\n${esc(veri.hafta)} · tüm alanlardan en yüksek puanlılar`;
  const bloklar = (veri.gundem || []).map((m, i) =>
    makaleBlogu(i + 1, m, ` · ${esc(m.alan)}`));
  const detay = (veri.gundem || []).map((m, i) => ({ text: `📄 ${i + 1}`, callback_data: `d:${m.pmid}` }));
  return {
    metin: sigdir(bloklar, bas, "📄 Ayrıntılı özet için numaraya bas."),
    klavye: [detay, [geriTusu]].filter((s) => s.length),
  };
}

const geriTusu = { text: "← Alanlar", callback_data: "m" };

// ---------------------------------------------------------- ayrıntılı özet
const DETAY_TALIMATI = `Sen genel cerrahi alanında deneyimli bir akademisyensin ve
yeni mezun bir hekime journal club tarzında makale anlatıyorsun.
Aşağıdaki makaleyi Türkçe olarak yapılandırılmış biçimde özetle.

Kurallar:
- Tıbbi terimleri ve kısaltmaları İngilizce bırak (anastomotic leak, hazard
  ratio, RCT, per-protocol, NNT vb.). Cümle yapısı Türkçe olsun.
- YALNIZCA verilen metindeki bilgiyi kullan. Metinde olmayan sayı veya
  sonuç uydurma. Bir bilgi metinde yoksa "belirtilmemiş" de.
- Ana bulgularda sayıları (oran, %95 CI, p) mutlaka ver. Sayıları her zaman
  RAKAMLA yaz (750 hasta, %59); asla yazıyla yazma.
- "pratige_etkisi" kısmında, bulguların klinik pratiği değiştirip
  değiştirmeyeceğini kanıt düzeyiyle birlikte dengeli biçimde değerlendir.
- "journal_club_sorulari": çalışmayı eleştirel okumaya yönelten 2-3 soru.`;

const DETAY_SEMASI = {
  type: "OBJECT",
  properties: {
    baslik_tr: { type: "STRING" },
    tek_cumle: { type: "STRING" },
    tasarim: { type: "STRING" },
    pico: {
      type: "OBJECT",
      properties: {
        P: { type: "STRING" }, I: { type: "STRING" },
        C: { type: "STRING" }, O: { type: "STRING" },
      },
    },
    ana_bulgular: { type: "ARRAY", items: { type: "STRING" } },
    guclu_yanlar: { type: "ARRAY", items: { type: "STRING" } },
    sinirliliklar: { type: "ARRAY", items: { type: "STRING" } },
    pratige_etkisi: { type: "STRING" },
    journal_club_sorulari: { type: "ARRAY", items: { type: "STRING" } },
  },
  required: ["baslik_tr", "tek_cumle", "tasarim", "ana_bulgular",
    "sinirliliklar", "pratige_etkisi"],
};

const YEDEK_MODELLER = ["gemini-flash-lite-latest", "gemini-2.5-flash", "gemini-2.5-flash-lite"];

async function gemini(env, metin, sema) {
  // Ana model yoğunsa (503) ya da kotası dolduysa sıradaki modele geçilir
  const ana = env.GEMINI_MODEL || "gemini-flash-latest";
  const modeller = [ana, ...YEDEK_MODELLER.filter((m) => m !== ana)];
  const govde = JSON.stringify({
    contents: [{ role: "user", parts: [{ text: metin }] }],
    generationConfig: { temperature: 0.2, responseMimeType: "application/json", responseSchema: sema },
  });
  let sonHata = "";
  for (const model of modeller) {
    const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`;
    for (let deneme = 0; deneme < 2; deneme++) {
      const r = await fetch(url, {
        method: "POST",
        headers: { "content-type": "application/json", "x-goog-api-key": env.GEMINI_API_KEY },
        body: govde,
      });
      if (r.ok) {
        const j = await r.json();
        const parca = j.candidates?.[0]?.content?.parts?.map((p) => p.text || "").join("") || "";
        return JSON.parse(parca);
      }
      sonHata = `${model} ${r.status}`;
      console.log("Gemini hatası", sonHata, (await r.text()).slice(0, 300));
      if (![429, 500, 503].includes(r.status)) break; // 404/400: sıradaki model
      if (deneme === 0) await new Promise((ok) => setTimeout(ok, 3000));
    }
  }
  throw new Error(`Yapay zekâ şu an yanıt vermiyor (${sonHata}). Birkaç dakika sonra tekrar dene.`);
}

function jatsMetne(xml) {
  // JATS tam metninden kaynakça ve tabloları atıp düz metin çıkarır
  const govde = (xml.match(/<body[\s\S]*<\/body>/) || [""])[0];
  return govde
    .replace(/<ref-list[\s\S]*?<\/ref-list>/g, "")
    .replace(/<table-wrap[\s\S]*?<\/table-wrap>/g, "")
    .replace(/<xref[^>]*>[\s\S]*?<\/xref>/g, "")
    .replace(/<title>/g, "\n\n## ").replace(/<\/title>/g, "\n")
    .replace(/<\/p>/g, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&")
    .replace(/\s*\[[,\s–-]*\]/g, "") // atıf numaralarından kalan boş köşeli parantezler
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

async function tamMetin(pmc) {
  if (!pmc) return "";
  const kaynaklar = [
    `https://www.ebi.ac.uk/europepmc/webservices/rest/${pmc}/fullTextXML`,
    `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id=${pmc.replace("PMC", "")}&tool=cerrahi-literatur-botu`,
  ];
  for (const url of kaynaklar) {
    try {
      const r = await fetch(url);
      if (!r.ok) continue;
      const metin = jatsMetne(await r.text());
      if (metin.length > 2000) return metin.slice(0, 60000);
    } catch (e) {
      console.log("tam metin hatası", url, e.message);
    }
  }
  return "";
}

async function pubmeddenGetir(pmid) {
  // hafta.json'da olmayan (eski haftadan kalma) makaleler için
  const r = await fetch(
    `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=${pmid}&retmode=xml&tool=cerrahi-literatur-botu`);
  const x = await r.text();
  const al = (re) => (x.match(re) || [, ""])[1].replace(/<[^>]+>/g, "").trim();
  const ozet = [...x.matchAll(/<AbstractText([^>]*)>([\s\S]*?)<\/AbstractText>/g)]
    .map(([, attr, t]) => {
      const e = (attr.match(/Label="([^"]+)"/) || [, ""])[1];
      return (e ? e + ": " : "") + t.replace(/<[^>]+>/g, "");
    }).join("\n");
  return {
    pmid, baslik: al(/<ArticleTitle>([\s\S]*?)<\/ArticleTitle>/), ozet,
    dergi: al(/<MedlineTA>([\s\S]*?)<\/MedlineTA>/), yil: al(/<PubDate>\s*<Year>(\d{4})/),
    pmc: al(/<ArticleId IdType="pmc">([^<]+)</), doi: al(/<ArticleId IdType="doi">([^<]+)</),
    tip_etiketi: "",
  };
}

function detayMetni(m, d, tamMetinVar) {
  const liste = (x) => (x || []).map((s) => `• ${esc(s)}`).join("\n");
  const kaynak = tamMetinVar
    ? "🔓 Tam metin üzerinden hazırlandı"
    : "⚠️ Yalnızca özet (abstract) üzerinden hazırlandı";
  const p = d.pico || {};
  const bolumler = [
    `📄 <b>${esc(d.baslik_tr || m.baslik)}</b>\n<i>${esc(m.baslik)}</i>\n` +
      `${esc(m.dergi)}${m.yil ? " · " + esc(m.yil) : ""}` +
      `${m.tip_etiketi ? " · " + esc(m.tip_etiketi) : ""}\n${kaynak}`,
    `<b>Bir cümlede</b>\n${esc(d.tek_cumle)}`,
    `<b>Tasarım</b>\n${esc(d.tasarim)}`,
    p.P || p.I ? `<b>PICO</b>\n• P: ${esc(p.P)}\n• I: ${esc(p.I)}\n• C: ${esc(p.C)}\n• O: ${esc(p.O)}` : "",
    `<b>Ana bulgular</b>\n${liste(d.ana_bulgular)}`,
    d.guclu_yanlar?.length ? `<b>Güçlü yanlar</b>\n${liste(d.guclu_yanlar)}` : "",
    `<b>Sınırlılıklar</b>\n${liste(d.sinirliliklar)}`,
    `<b>Pratiğe etkisi</b>\n${esc(d.pratige_etkisi)}`,
    d.journal_club_sorulari?.length
      ? `<b>Journal club soruları</b>\n${d.journal_club_sorulari.map((s, i) => `${i + 1}. ${esc(s)}`).join("\n")}`
      : "",
    `🔗 <a href="${pubmedLink(m.pmid)}">PubMed</a>` +
      (m.doi ? ` · <a href="https://doi.org/${esc(m.doi)}">Makale</a>` : "") +
      `\n<i>Yapay zekâ özetidir; klinik karar için makalenin kendisine başvur.</i>`,
  ];
  return bolumler.filter(Boolean).join("\n\n");
}

async function detayGonder(env, sohbet, pmid) {
  const kv = env.ONBELLEK;
  let metin = kv ? await kv.get(`ozet:${pmid}`) : null;

  if (!metin) {
    if (kv) {
      if (await kv.get(`kilit:${pmid}`)) return; // aynı istek zaten işleniyor
      await kv.put(`kilit:${pmid}`, "1", { expirationTtl: 120 });
    }
    await tg(env, "sendChatAction", { chat_id: sohbet, action: "typing" });
    let m = null;
    try {
      m = makaleBul(await haftaVerisi(env), pmid);
    } catch (e) { /* aşağıda PubMed'den denenir */ }
    if (!m || !m.ozet) m = await pubmeddenGetir(pmid);

    const tam = await tamMetin(m.pmc);
    const girdi =
      `${DETAY_TALIMATI}\n\n---\nDergi: ${m.dergi} (${m.yil || ""})\n` +
      `Çalışma tipi (PubMed): ${m.tip_etiketi || "belirtilmemiş"}\n` +
      `Başlık: ${m.baslik}\n\nÖzet (abstract):\n${m.ozet || "(yok)"}` +
      (tam ? `\n\nTAM METİN:\n${tam}` : "");
    const d = await gemini(env, girdi, DETAY_SEMASI);
    metin = detayMetni(m, d, Boolean(tam));
    if (kv) await kv.put(`ozet:${pmid}`, metin, { expirationTtl: 60 * 60 * 24 * 120 });
  }

  const parcalar = parcala(metin);
  for (let i = 0; i < parcalar.length; i++) {
    const son = i === parcalar.length - 1;
    await tg(env, "sendMessage", {
      chat_id: sohbet, text: parcalar[i], parse_mode: "HTML",
      link_preview_options: { is_disabled: true },
      ...(son ? { reply_markup: { inline_keyboard: [[geriTusu]] } } : {}),
    });
  }
}

// ------------------------------------------------------------ güncellemeler
async function ekranGoster(env, sohbet, ekran, mesajId) {
  const govde = {
    chat_id: sohbet, text: ekran.metin, parse_mode: "HTML",
    link_preview_options: { is_disabled: true },
    reply_markup: { inline_keyboard: ekran.klavye },
  };
  if (mesajId) {
    const j = await tg(env, "editMessageText", { ...govde, message_id: mesajId });
    if (j.ok || String(j.description || "").includes("not modified")) return;
  }
  await tg(env, "sendMessage", govde);
}

async function guncellemeIsle(env, u) {
  const kimden = u.message?.from || u.callback_query?.from;
  const sohbet = u.message?.chat.id ?? u.callback_query?.message?.chat.id;
  if (!kimden || !sohbet) return;

  if (!env.IZINLI_KULLANICI) {
    await tg(env, "sendMessage", {
      chat_id: sohbet,
      text: `🔧 Kurulum modu\nTelegram kullanıcı numaran: ${kimden.id}\n` +
        `Bu numarayı Cloudflare'de IZINLI_KULLANICI değişkenine yaz.`,
    });
    return;
  }
  if (String(kimden.id) !== String(env.IZINLI_KULLANICI)) return; // yabancılara sessiz

  if (u.callback_query) {
    const q = u.callback_query;
    const veri = q.data || "";
    const mesajId = q.message?.message_id;
    if (veri.startsWith("d:")) {
      await tg(env, "answerCallbackQuery", {
        callback_query_id: q.id, text: "Ayrıntılı özet hazırlanıyor… (10–30 sn)",
      });
      try {
        await detayGonder(env, sohbet, veri.slice(2));
      } catch (e) {
        console.log("detay hatası", e.stack || e);
        await tg(env, "sendMessage", {
          chat_id: sohbet, text: `⚠️ Ayrıntılı özet hazırlanamadı: ${e.message}`,
        });
        if (env.ONBELLEK) await env.ONBELLEK.delete(`kilit:${veri.slice(2)}`);
      }
      return;
    }
    await tg(env, "answerCallbackQuery", { callback_query_id: q.id });
    const hafta = await haftaVerisi(env);
    if (veri === "m") return ekranGoster(env, sohbet, menuEkrani(hafta), mesajId);
    if (veri === "g") return ekranGoster(env, sohbet, gundemEkrani(hafta), mesajId);
    if (veri.startsWith("a:"))
      return ekranGoster(env, sohbet, alanEkrani(hafta, veri.slice(2)), mesajId);
    return;
  }

  const metin = (u.message.text || "").trim();
  const hafta = await haftaVerisi(env);
  if (metin.startsWith("/gundem")) return ekranGoster(env, sohbet, gundemEkrani(hafta));
  return ekranGoster(env, sohbet, menuEkrani(hafta));
}

// ------------------------------------------------------------------ giriş
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // Tek seferlik kurulum: tarayıcıda /kurulum?anahtar=WEBHOOK_SECRET aç
    if (url.pathname === "/kurulum") {
      if (url.searchParams.get("anahtar") !== env.WEBHOOK_SECRET)
        return new Response("Yetkisiz", { status: 403 });
      const w = await tg(env, "setWebhook", {
        url: `${url.origin}/telegram`, secret_token: env.WEBHOOK_SECRET,
        allowed_updates: ["message", "callback_query"], drop_pending_updates: true,
      });
      const k = await tg(env, "setMyCommands", {
        commands: [
          { command: "start", description: "Alan menüsü" },
          { command: "gundem", description: "Bu hafta gündemde" },
        ],
      });
      return new Response(
        (w.ok && k.ok ? "✅ Kurulum tamam. Telegram'da botuna /start yaz.\n\n" : "❌ Sorun var:\n\n") +
          JSON.stringify({ webhook: w, komutlar: k }, null, 2),
        { headers: { "content-type": "text/plain; charset=utf-8" } });
    }

    if (url.pathname === "/telegram" && request.method === "POST") {
      if (request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.WEBHOOK_SECRET)
        return new Response("Yetkisiz", { status: 403 });
      const u = await request.json();
      try {
        await guncellemeIsle(env, u);
      } catch (e) {
        console.log("hata", e.stack || e);
      }
      return new Response("ok");
    }

    return new Response("Cerrahi Literatür Botu çalışıyor.");
  },
};
