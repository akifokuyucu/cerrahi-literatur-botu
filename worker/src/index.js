/**
 * Cerrahi Literatür Botu — Telegram botu (Cloudflare Worker)
 *
 * Ayarlar (Cloudflare panelinde "Variables and Secrets"):
 *   TELEGRAM_TOKEN     (gizli) BotFather'ın verdiği token
 *   GEMINI_API_KEY     (gizli) Google AI Studio anahtarı
 *   WEBHOOK_SECRET     (gizli) Kendi uydurduğun uzun rastgele bir parola
 *   VERI_URL           hafta.json'un GitHub "raw" adresi
 *   GUNDEM_URL         (isteğe bağlı) gundem.json adresi; boşsa VERI_URL'in yanındaki dosya
 *   IZINLI_KULLANICI   Telegram kullanıcı numaran (boşsa bot numaranı söyler)
 *   GEMINI_MODEL       (isteğe bağlı) varsayılan: gemini-flash-latest
 *   NOTION_TOKEN       (gizli, isteğe bağlı) Notion entegrasyon anahtarı
 *   NOTION_ARSIV_DB    Okuma Arşivi veritabanı kimliği
 *   NOTION_ICERIK_DB   İçerik Havuzu veritabanı kimliği
 * Bağlantı (Binding):
 *   ONBELLEK           KV alanı — ayrıntılı özetler, oylar, arşiv kayıtları
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

// 📰 Gündem (perşembe hazırlanır). İlk hazırlıktan önce dosya yoksa null.
async function gundemVerisi(env) {
  const url = env.GUNDEM_URL || env.VERI_URL.replace(/hafta\.json$/, "gundem.json");
  const r = await fetch(url, { cf: { cacheTtl: 300 } });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error("gundem.json okunamadı: " + r.status);
  return r.json();
}

function makaleBul(veri, pmid) {
  for (const a of Object.values(veri.alanlar || {})) {
    for (const m of [...a.makaleler, a.turk]) if (m && m.pmid === pmid) return { ...m, alan: a.ad };
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
  satirlar.push([
    { text: "🔥 Haftanın öne çıkanları", callback_data: "g" },
    { text: "📰 Gündem", callback_data: "h" },
  ]);
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

function oneCikanlarEkrani(veri) {
  const bas = `🔥 <b>Haftanın öne çıkanları</b>\n${esc(veri.hafta)} · tüm alanlardan en yüksek puanlılar`;
  const bloklar = (veri.gundem || []).map((m, i) =>
    makaleBlogu(i + 1, m, ` · ${esc(m.alan)}`));
  const detay = (veri.gundem || []).map((m, i) => ({ text: `📄 ${i + 1}`, callback_data: `d:${m.pmid}` }));
  return {
    metin: sigdir(bloklar, bas, "📄 Ayrıntılı özet için numaraya bas."),
    klavye: [detay, [geriTusu]].filter((s) => s.length),
  };
}

const geriTusu = { text: "← Alanlar", callback_data: "m" };
const gundemTusu = { text: "← Gündem", callback_data: "h" };

// ------------------------------------------------------------ 📰 Gündem
function gundemMenuEkrani(gv) {
  if (!gv) {
    return {
      metin: "📰 <b>Gündem</b>\n\nGündem her perşembe sabah hazırlanıyor; ilk liste henüz çıkmadı.",
      klavye: [[geriTusu]],
    };
  }
  const bolumler = Object.entries(gv.bolumler || {});
  const satirlar = bolumler.map(([, b]) => `${esc(b.ad)}: ${b.ogeler.length} haber`);
  const uyari = gv.hatalar?.length
    ? `\n\n<i>⚠️ Bu hafta okunamayan kaynaklar: ${esc(gv.hatalar.join("; "))}</i>` : "";
  const tuslar = bolumler.map(([kod, b]) => ({ text: `${b.ad} (${b.ogeler.length})`, callback_data: `h:${kod}` }));
  const klavye = [];
  for (let i = 0; i < tuslar.length; i += 2) klavye.push(tuslar.slice(i, i + 2));
  klavye.push([geriTusu]);
  return {
    metin: `📰 <b>Gündem</b>\n${esc(gv.hafta)} · kılavuzlar, teknoloji, Türkiye ve yeni RCT'ler\n\n` +
      satirlar.join("\n") + uyari,
    klavye,
  };
}

function haberBlogu(no, o) {
  const tarih = o.tarih ? ` · ${esc(o.tarih.split("-").reverse().join("."))}` : "";
  const rct = o.nct
    ? `\n${o.n ? `${o.n} hasta · ` : ""}${esc(o.ulke || "ülke belirtilmemiş")}` +
      (o.sponsor ? ` · ${esc(o.sponsor)}` : "")
    : "";
  return (
    `<b>${no}. ${esc(o.baslik_tr || o.baslik)}</b>\n` +
    esc(o.ozet || "") + rct + "\n" +
    `<a href="${esc(o.url)}">${esc(o.nct || o.kaynak)}</a>${tarih}`
  );
}

function haberBolumEkrani(gv, kod) {
  const b = gv?.bolumler?.[kod];
  if (!b) return { metin: "Bu bölüm bu hafta hazırlanamadı.", klavye: [[gundemTusu]] };
  const bas = `<b>${esc(b.ad)}</b>\n${esc(gv.hafta)} · ${b.aday} aday tarandı`;
  const son = "<i>Başlık ve özetler yapay zekâ ile Türkçeleştirildi; ayrıntı için kaynağa bak.</i>";
  // HTML'i ortadan kesmemek için sığmayan haberler bütün olarak dışarıda kalır
  const bloklar = [];
  for (const [i, o] of b.ogeler.entries()) {
    const blok = haberBlogu(i + 1, o);
    if ([bas, ...bloklar, blok, son].join("\n\n").length > SINIR) break;
    bloklar.push(blok);
  }
  if (!bloklar.length) bloklar.push("<i>Bu hafta bu bölümde kayda değer bir gelişme yok.</i>");
  return { metin: [bas, ...bloklar, son].join("\n\n"), klavye: [[gundemTusu, geriTusu]] };
}

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
- "journal_club_sorulari": çalışmayı eleştirel okumaya yönelten 2-3 soru.
- "pico": dört alanın HER BİRİNİ kısa bir ifadeyle doldur (en fazla 1 cümle).
  Gözlemsel çalışmalarda I = incelenen yaklaşım/maruziyet, C = karşılaştırma
  grubu; meta-analizde dahil edilen çalışmaların PICO'sunu yaz. Alanlara
  asla talimat, açıklama veya "belirtilmemiş" dışında meta yorum yazma.`;

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

const GUN = 60 * 60 * 24;

async function kvJson(env, anahtar) {
  if (!env.ONBELLEK) return null;
  const v = await env.ONBELLEK.get(anahtar);
  return v ? JSON.parse(v) : null;
}

async function kvYaz(env, anahtar, deger, gun = 120) {
  if (!env.ONBELLEK) return;
  await env.ONBELLEK.put(anahtar, typeof deger === "string" ? deger : JSON.stringify(deger),
    { expirationTtl: GUN * gun });
}

async function makaleGetir(env, pmid) {
  let m = null;
  try {
    m = makaleBul(await haftaVerisi(env), pmid);
  } catch (e) { /* aşağıda PubMed'den denenir */ }
  if (!m || !m.ozet) m = { ...(await pubmeddenGetir(pmid)), alan: m?.alan || "" };
  return m;
}

// Ayrıntılı özet: {m, d, tam} — KV'de 120 gün saklanır
async function detayHazirla(env, pmid, sohbet) {
  const kayitli = await kvJson(env, `detay:${pmid}`);
  if (kayitli) return kayitli;
  if (env.ONBELLEK) {
    if (await env.ONBELLEK.get(`kilit:${pmid}`)) return null; // aynı istek zaten işleniyor
    await env.ONBELLEK.put(`kilit:${pmid}`, "1", { expirationTtl: 120 });
  }
  if (sohbet) await tg(env, "sendChatAction", { chat_id: sohbet, action: "typing" });
  const m = await makaleGetir(env, pmid);
  const tam = await tamMetin(m.pmc);
  if (tam) await kvYaz(env, `metin:${pmid}`, tam, 30); // soru-cevap için
  const girdi =
    `${DETAY_TALIMATI}\n\n---\nDergi: ${m.dergi} (${m.yil || ""})\n` +
    `Çalışma tipi (PubMed): ${m.tip_etiketi || "belirtilmemiş"}\n` +
    `Başlık: ${m.baslik}\n\nÖzet (abstract):\n${m.ozet || "(yok)"}` +
    (tam ? `\n\nTAM METİN:\n${tam}` : "");
  const d = await gemini(env, girdi, DETAY_SEMASI);
  const kayit = { m, d, tam: Boolean(tam) };
  await kvYaz(env, `detay:${pmid}`, kayit);
  if (env.ONBELLEK) await env.ONBELLEK.delete(`kilit:${pmid}`);
  return kayit;
}

function detayKlavye(pmid, oy) {
  return [
    [
      { text: oy === 1 ? "✅ 👍 Faydalı" : "👍 Faydalı", callback_data: `o:1:${pmid}` },
      { text: oy === 0 ? "✅ 👎 Değil" : "👎 Değil", callback_data: `o:0:${pmid}` },
    ],
    [
      { text: "📌 Arşive ekle", callback_data: `n:${pmid}` },
      { text: "📸 İçerik adayı", callback_data: `i:${pmid}` },
    ],
    [{ text: "❓ Soru sor", callback_data: `s:${pmid}` }, geriTusu],
  ];
}

async function detayGonder(env, sohbet, pmid) {
  const k = await detayHazirla(env, pmid, sohbet);
  if (!k) return;
  const oy = (await kvJson(env, `oy:${pmid}`))?.oy;
  const parcalar = parcala(detayMetni(k.m, k.d, k.tam));
  for (let i = 0; i < parcalar.length; i++) {
    const son = i === parcalar.length - 1;
    await tg(env, "sendMessage", {
      chat_id: sohbet, text: parcalar[i], parse_mode: "HTML",
      link_preview_options: { is_disabled: true },
      ...(son ? { reply_markup: { inline_keyboard: detayKlavye(pmid, oy) } } : {}),
    });
  }
}

// ------------------------------------------------------------- 👍 / 👎
async function oyVer(env, q, pmid, oy) {
  const k = await kvJson(env, `detay:${pmid}`);
  const m = k?.m || (await makaleGetir(env, pmid));
  await kvYaz(env, `oy:${pmid}`, {
    oy, dergi: m.dergi, tip: m.tip || "", alan: m.alan || "", tarih: new Date().toISOString(),
  }, 730);
  await tg(env, "answerCallbackQuery", {
    callback_query_id: q.id, text: oy ? "👍 Kaydedildi, benzerlerini öne çıkaracağım" : "👎 Kaydedildi",
  });
  // Tuşlarda seçimi göster
  await tg(env, "editMessageReplyMarkup", {
    chat_id: q.message.chat.id, message_id: q.message.message_id,
    reply_markup: { inline_keyboard: detayKlavye(pmid, oy) },
  });
  // Arşivdeyse Notion'daki "Oyum" alanını da güncelle
  const sayfa = await kvJson(env, `notion:${pmid}`);
  if (sayfa && env.NOTION_TOKEN) {
    await notion(env, `pages/${sayfa.id}`, "PATCH", {
      properties: { "Oyum": { select: { name: oy ? "👍 Faydalı" : "👎 Değil" } } },
    }).catch((e) => console.log("Notion oy hatası", e.message));
  }
}

async function oylariListele(env) {
  const oylar = [];
  if (!env.ONBELLEK) return oylar;
  let cursor;
  do {
    const l = await env.ONBELLEK.list({ prefix: "oy:", cursor });
    for (const k of l.keys) {
      const v = await kvJson(env, k.name);
      if (v) oylar.push({ pmid: k.name.slice(3), ...v });
    }
    cursor = l.list_complete ? null : l.cursor;
  } while (cursor);
  return oylar;
}

async function istatistikGonder(env, sohbet) {
  const oylar = await oylariListele(env);
  if (!oylar.length) {
    return tg(env, "sendMessage", { chat_id: sohbet, text: "Henüz oy yok. Ayrıntılı özetlerin altındaki 👍 / 👎 tuşlarını kullan." });
  }
  const say = (alan) => {
    const t = {};
    for (const o of oylar) {
      if (!o[alan]) continue;
      t[o[alan]] = t[o[alan]] || [0, 0];
      t[o[alan]][o.oy ? 0 : 1]++;
    }
    return Object.entries(t).sort((a, b) => (b[1][0] - b[1][1]) - (a[1][0] - a[1][1]))
      .slice(0, 6).map(([ad, [a, b]]) => `• ${esc(ad)}: 👍${a} 👎${b}`).join("\n");
  };
  const begeni = oylar.filter((o) => o.oy).length;
  const metin = `📊 <b>Geri bildirimlerin</b>\nToplam ${oylar.length} oy (👍${begeni} 👎${oylar.length - begeni})\n\n` +
    `<b>Dergiler</b>\n${say("dergi")}\n\n<b>Alanlar</b>\n${say("alan")}\n\n` +
    `<i>Bu oylar her pazartesi puanlamaya küçük bir kişisel katkı olarak ekleniyor.</i>`;
  return tg(env, "sendMessage", { chat_id: sohbet, text: metin, parse_mode: "HTML" });
}

// ------------------------------------------------------------- Notion
async function notion(env, yol, metod, govde) {
  const r = await fetch(`https://api.notion.com/v1/${yol}`, {
    method: metod,
    headers: {
      Authorization: `Bearer ${env.NOTION_TOKEN}`,
      "Notion-Version": "2022-06-28",
      "content-type": "application/json",
    },
    body: govde ? JSON.stringify(govde) : undefined,
  });
  const j = await r.json();
  if (!r.ok) throw new Error(`Notion ${r.status}: ${j.message || ""}`);
  return j;
}

const yazi = (t) => [{ type: "text", text: { content: String(t || "").slice(0, 1900) } }];
const blok = {
  baslik: (t) => ({ object: "block", type: "heading_3", heading_3: { rich_text: yazi(t) } }),
  paragraf: (t) => ({ object: "block", type: "paragraph", paragraph: { rich_text: yazi(t) } }),
  madde: (t) => ({ object: "block", type: "bulleted_list_item", bulleted_list_item: { rich_text: yazi(t) } }),
  numara: (t) => ({ object: "block", type: "numbered_list_item", numbered_list_item: { rich_text: yazi(t) } }),
  not: (t) => ({ object: "block", type: "callout", callout: { rich_text: yazi(t), icon: { emoji: "ℹ️" } } }),
};

function detayBloklari(k) {
  const { m, d } = k;
  const p = d.pico || {};
  const b = [
    blok.not(`${m.dergi}${m.yil ? " · " + m.yil : ""}${m.tip_etiketi ? " · " + m.tip_etiketi : ""} — ` +
      (k.tam ? "Tam metin üzerinden hazırlandı." : "Yalnızca özet (abstract) üzerinden hazırlandı.") +
      " Yapay zekâ özetidir; klinik karar için makalenin kendisine başvur."),
    blok.baslik("Bir cümlede"), blok.paragraf(d.tek_cumle),
    blok.baslik("Tasarım"), blok.paragraf(d.tasarim),
  ];
  if (p.P || p.I) {
    b.push(blok.baslik("PICO"), ...["P", "I", "C", "O"].map((x) => blok.madde(`${x}: ${p[x] || "-"}`)));
  }
  b.push(blok.baslik("Ana bulgular"), ...(d.ana_bulgular || []).map(blok.madde));
  if (d.guclu_yanlar?.length) b.push(blok.baslik("Güçlü yanlar"), ...d.guclu_yanlar.map(blok.madde));
  b.push(blok.baslik("Sınırlılıklar"), ...(d.sinirliliklar || []).map(blok.madde));
  b.push(blok.baslik("Pratiğe etkisi"), blok.paragraf(d.pratige_etkisi));
  if (d.journal_club_sorulari?.length)
    b.push(blok.baslik("Journal club soruları"), ...d.journal_club_sorulari.map(blok.numara));
  return b.slice(0, 95);
}

const TIP_SECENEK = {
  kilavuz: "Kılavuz/Konsensus", meta_analiz: "Meta-analiz", rct: "RCT",
  prospektif: "Prospektif", diger: "Retrospektif/Diğer",
};
const urlOz = (u) => (u ? { url: u } : { url: null });

async function arsiveEkle(env, sohbet, pmid) {
  const onceki = await kvJson(env, `notion:${pmid}`);
  if (onceki) {
    return tg(env, "sendMessage", {
      chat_id: sohbet, parse_mode: "HTML",
      text: `📌 Bu makale zaten arşivde: <a href="${onceki.url}">Notion'da aç</a>`,
    });
  }
  const k = await detayHazirla(env, pmid, sohbet);
  if (!k) return;
  const { m, d } = k;
  const oy = (await kvJson(env, `oy:${pmid}`))?.oy;
  const ozellik = {
    "Başlık": { title: yazi(d.baslik_tr || m.baslik) },
    "Orijinal başlık": { rich_text: yazi(m.baslik) },
    "Dergi": { rich_text: yazi(m.dergi) },
    "Kaynak": { select: { name: k.tam ? "Tam metin" : "Yalnızca özet" } },
    "Durum": { select: { name: "Okunacak" } },
    "PubMed": urlOz(pubmedLink(pmid)),
    "DOI": urlOz(m.doi ? `https://doi.org/${m.doi}` : null),
  };
  if (m.alan) ozellik["Alan"] = { select: { name: m.alan.replace(", ", " - ") } };
  if (TIP_SECENEK[m.tip]) ozellik["Çalışma tipi"] = { select: { name: TIP_SECENEK[m.tip] } };
  if (m.toplam != null) ozellik["Puan"] = { number: m.toplam };
  if (/^\d{4}$/.test(m.yil || "")) ozellik["Yıl"] = { number: Number(m.yil) };
  if (oy != null) ozellik["Oyum"] = { select: { name: oy ? "👍 Faydalı" : "👎 Değil" } };
  const sayfa = await notion(env, "pages", "POST", {
    parent: { database_id: env.NOTION_ARSIV_DB }, icon: { emoji: "📄" },
    properties: ozellik, children: detayBloklari(k),
  });
  await kvYaz(env, `notion:${pmid}`, { id: sayfa.id, url: sayfa.url }, 3650);
  return tg(env, "sendMessage", {
    chat_id: sohbet, parse_mode: "HTML",
    text: `📌 Okuma Arşivi'ne eklendi: <a href="${sayfa.url}">Notion'da aç</a>`,
  });
}

async function icerikAdayi(env, sohbet, pmid) {
  const onceki = await kvJson(env, `icerik:${pmid}`);
  if (onceki) {
    return tg(env, "sendMessage", {
      chat_id: sohbet, parse_mode: "HTML",
      text: `📸 Bu makale zaten İçerik Havuzu'nda: <a href="${onceki.url}">Notion'da aç</a>`,
    });
  }
  const k = await detayHazirla(env, pmid, sohbet);
  if (!k) return;
  const { m, d } = k;
  const sayfa = await notion(env, "pages", "POST", {
    parent: { database_id: env.NOTION_ICERIK_DB },
    properties: {
      "Başlık": { title: yazi(d.baslik_tr || m.baslik) },
      "Durum": { select: { name: "fikir" } },
      "Köken": { select: { name: "Literatür botu" } },
      "Kategori": { select: { name: "Bilimsel" } },
      "Eksen": { select: { name: "E3 Haber" } },
      "Kaynak linki": urlOz(m.doi ? `https://doi.org/${m.doi}` : pubmedLink(pmid)),
      "Teyit gerekiyor": { checkbox: true },
      "Notlar": { rich_text: yazi(`${m.dergi} · ${m.tip_etiketi || ""} · ${m.alan || ""}. ${d.tek_cumle || ""}`) },
    },
    children: [
      blok.not("Literatür botundan içerik adayı. Aşağıdaki özet yapay zekâ tarafından çıkarıldı; yayın metni değildir, rakamlar makaleden teyit edilmeli."),
      ...detayBloklari(k).slice(1),
    ],
  });
  await kvYaz(env, `icerik:${pmid}`, { id: sayfa.id, url: sayfa.url }, 3650);
  return tg(env, "sendMessage", {
    chat_id: sohbet, parse_mode: "HTML",
    text: `📸 İçerik Havuzu'na "fikir" olarak eklendi: <a href="${sayfa.url}">Notion'da aç</a>`,
  });
}

// ------------------------------------------------------------- ❓ Soru sor
const SORU_TALIMATI = `Sen genel cerrahi alanında deneyimli bir akademisyensin.
Aşağıdaki makale hakkında yeni mezun bir hekimin sorusunu Türkçe yanıtla.
Kurallar:
- YALNIZCA verilen makale metnine dayan. Metinde cevap yoksa bunu açıkça söyle
  ("makalede belirtilmemiş") ve tahmin yürütme.
- Tıbbi terimleri İngilizce bırak, sayıları rakamla yaz.
- Kısa ve net ol (en fazla 8 cümle). İlgili bölümü belirt (Methods, Results vb.).`;

async function soruBaslat(env, sohbet, pmid) {
  const k = await kvJson(env, `detay:${pmid}`);
  await kvYaz(env, `soru:${sohbet}`, { pmid }, 1);
  return tg(env, "sendMessage", {
    chat_id: sohbet, parse_mode: "HTML",
    text: `❓ <b>${esc(k?.d?.baslik_tr || k?.m?.baslik || "Bu makale")}</b> hakkında sorunu yaz.\n` +
      `<i>Ör. "Dışlama kriterleri neydi?" · Bitirmek için /iptal</i>`,
    reply_markup: { force_reply: true, input_field_placeholder: "Sorunu yaz…" },
  });
}

async function soruCevapla(env, sohbet, pmid, soru) {
  await tg(env, "sendChatAction", { chat_id: sohbet, action: "typing" });
  const k = await detayHazirla(env, pmid, null);
  if (!k) return;
  let metin = env.ONBELLEK ? await env.ONBELLEK.get(`metin:${pmid}`) : "";
  if (!metin && k.tam) metin = await tamMetin(k.m.pmc);
  const girdi = `${SORU_TALIMATI}\n\n---\nBaşlık: ${k.m.baslik}\nDergi: ${k.m.dergi}\n\n` +
    `Özet:\n${k.m.ozet || "(yok)"}` + (metin ? `\n\nTAM METİN:\n${metin}` : "") +
    `\n\n---\nSORU: ${soru}`;
  const c = await gemini(env, girdi, {
    type: "OBJECT", properties: { cevap: { type: "STRING" } }, required: ["cevap"],
  });
  const uyari = metin ? "" : "\n\n<i>⚠️ Tam metin açık değil; cevap yalnızca özete dayanıyor.</i>";
  await kvYaz(env, `soru:${sohbet}`, { pmid }, 1); // oturumu uzat
  return tg(env, "sendMessage", {
    chat_id: sohbet, parse_mode: "HTML",
    text: `💬 ${esc(c.cevap)}${uyari}\n\n<i>Başka sorun varsa yaz · bitirmek için /iptal</i>`,
  });
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

async function hataBildir(env, sohbet, is, e) {
  console.log(is, "hatası", e.stack || e);
  await tg(env, "sendMessage", { chat_id: sohbet, text: `⚠️ ${is} yapılamadı: ${e.message}` });
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
    const [tur, ...kalan] = veri.split(":");

    if (tur === "d") {
      await tg(env, "answerCallbackQuery", {
        callback_query_id: q.id, text: "Ayrıntılı özet hazırlanıyor… (10–30 sn)",
      });
      try {
        await detayGonder(env, sohbet, kalan[0]);
      } catch (e) {
        if (env.ONBELLEK) await env.ONBELLEK.delete(`kilit:${kalan[0]}`);
        await hataBildir(env, sohbet, "Ayrıntılı özet", e);
      }
      return;
    }
    if (tur === "o") return oyVer(env, q, kalan[1], Number(kalan[0]));
    if (tur === "n" || tur === "i") {
      if (!env.NOTION_TOKEN) {
        return tg(env, "answerCallbackQuery", {
          callback_query_id: q.id, show_alert: true,
          text: "Notion bağlantısı henüz kurulmadı (NOTION_TOKEN eksik).",
        });
      }
      await tg(env, "answerCallbackQuery", { callback_query_id: q.id, text: "Notion'a ekleniyor…" });
      try {
        return tur === "n" ? await arsiveEkle(env, sohbet, kalan[0]) : await icerikAdayi(env, sohbet, kalan[0]);
      } catch (e) {
        return hataBildir(env, sohbet, tur === "n" ? "Arşive ekleme" : "İçerik Havuzu'na ekleme", e);
      }
    }
    if (tur === "s") {
      await tg(env, "answerCallbackQuery", { callback_query_id: q.id });
      return soruBaslat(env, sohbet, kalan[0]);
    }

    await tg(env, "answerCallbackQuery", { callback_query_id: q.id });
    if (veri === "h") return ekranGoster(env, sohbet, gundemMenuEkrani(await gundemVerisi(env)), mesajId);
    if (tur === "h") return ekranGoster(env, sohbet, haberBolumEkrani(await gundemVerisi(env), kalan[0]), mesajId);
    const hafta = await haftaVerisi(env);
    if (veri === "m") return ekranGoster(env, sohbet, menuEkrani(hafta), mesajId);
    if (veri === "g") return ekranGoster(env, sohbet, oneCikanlarEkrani(hafta), mesajId);
    if (tur === "a") return ekranGoster(env, sohbet, alanEkrani(hafta, kalan[0]), mesajId);
    return;
  }

  const metin = (u.message.text || "").trim();
  if (metin.startsWith("/iptal")) {
    if (env.ONBELLEK) await env.ONBELLEK.delete(`soru:${sohbet}`);
    return tg(env, "sendMessage", { chat_id: sohbet, text: "Tamam, soru modu kapandı." });
  }
  if (metin.startsWith("/istatistik")) return istatistikGonder(env, sohbet);

  // Soru modundaysa, komut olmayan metin bir sorudur
  const bekleyen = !metin.startsWith("/") && (await kvJson(env, `soru:${sohbet}`));
  if (bekleyen && metin) {
    try {
      return await soruCevapla(env, sohbet, bekleyen.pmid, metin);
    } catch (e) {
      return hataBildir(env, sohbet, "Soruyu yanıtlama", e);
    }
  }

  if (metin.startsWith("/gundem")) return ekranGoster(env, sohbet, gundemMenuEkrani(await gundemVerisi(env)));
  const hafta = await haftaVerisi(env);
  if (metin.startsWith("/onecikanlar")) return ekranGoster(env, sohbet, oneCikanlarEkrani(hafta));
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
          { command: "gundem", description: "Haberler ve gelişmeler (perşembe)" },
          { command: "onecikanlar", description: "Haftanın en yüksek puanlı makaleleri" },
          { command: "istatistik", description: "Oylarının özeti" },
          { command: "iptal", description: "Soru modunu kapat" },
        ],
      });
      return new Response(
        (w.ok && k.ok ? "✅ Kurulum tamam. Telegram'da botuna /start yaz.\n\n" : "❌ Sorun var:\n\n") +
          JSON.stringify({ webhook: w, komutlar: k }, null, 2),
        { headers: { "content-type": "text/plain; charset=utf-8" } });
    }

    // Haftalık hazırlık (GitHub Actions) oyları buradan okur
    if (url.pathname === "/geri-bildirim") {
      if (request.headers.get("X-Bot-Anahtar") !== env.WEBHOOK_SECRET)
        return new Response("Yetkisiz", { status: 403 });
      return Response.json(await oylariListele(env));
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
