"""
🌍 Dünya brifingi: ABD, Çin ve dünyadan haftanın önemli sağlık politikası,
tıp teknolojisi, toplum ve teknoloji/jeopolitik haberleri (her cumartesi).

İki adım:
  1. Süzgeç: kaynaklardaki adaylar partilerle yapay zekâya gider; her biri
     bölüm, bölge, önem (0–3), Türkçe başlık ve kısa özet alır.
  2. Brifing: seçilen haberlerden haftanın giriş paragrafı ve en önemli
     DUNYA_ANA_BASLIK gelişme Türkçe yazılır.
Sonuç cikti/dunya.json'a yazılır; brifing Telegram'a doğrudan gönderilir,
bölümler botta /dunya ile açılır. Kaynaklar config.DUNYA_KAYNAKLARI'nda.

GitHub Actions her cumartesi bunu çalıştırır. Elle deneme:
  python dunya.py --sahte-ozet --bildirim-yok   # yapay zekâsız deneme
"""
import argparse
import datetime as dt
import html
import itertools
import json
import os
import re
import sys
import time
import traceback

import config
import denetim
import llm
import ozetleyici
from gundem import birlestir, haber_oku, kisalt, rss_oku
from hazirla import hafta_etiketi, telegram_bildir

CIKTI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cikti")
GORULEN = os.path.join(CIKTI, "dunya_gorulen.json")
GORULEN_SINIRI = 3000
BOLGELER = ["ABD", "Çin", "Avrupa", "Küresel", "Diğer"]

SUZGEC_TALIMATI = """Sen, Türkiye'de çalışan genç bir hekim için haftalık "dünya
brifingi" hazırlayan bir editörsün. Okurun ilgisi: ABD, Çin ve dünyadaki önemli
sağlık, tıp teknolojisi, toplum ve teknoloji gelişmeleri.
Aşağıda bu haftanın aday haberleri var. Her aday için:

1. "bolum": şunlardan biri:
   saglik_politikasi = sağlık sistemleri, sigorta, ilaç fiyatları, kamu
     sağlığı, salgınlar, düzenleyici kurum kararları (FDA, NMPA, EMA, WHO)
   tip_teknoloji = tıbbi cihaz, sağlıkta yapay zekâ, biyoteknoloji, ilaç
     geliştirme, dijital sağlık, önemli klinik araştırma sonuçları
   toplum = demografi, yaşlanma, doğurganlık, hekim ve sağlık iş gücü,
     eşitsizlik, eğitim, göç, toplumsal eğilimler
   teknoloji_jeopolitik = tıp dışı büyük teknoloji gelişmeleri (yapay zekâ,
     çip, enerji, uzay) ve ABD–Çin teknoloji/ticaret rekabeti
   diger = hiçbirine uymuyor
2. "bolge": ABD, Çin, Avrupa, Küresel ya da Diğer
3. "onem": Haftalık brifing için değeri:
   3 = birçok ülkeyi ya da milyonlarca insanı etkileyen, kalıcı sonucu olan
       gelişme: yasa, düzenleme, politika değişikliği, büyük bir çalışmanın
       sonucu, büyük bir teknoloji sürümü ya da yasağı
   2 = önemli ama etkisi daha dar
   1 = ilginç ayrıntı
   0 = magazin, suç ve dava haberleri, tek bir kişinin hikâyesi, borsa ve
       şirket kazançları, ürün tanıtımı/reklam, görüş yazısı, spor, bölümlere
       uymayan siyaset ve savaş haberleri
4. "baslik_tr": Kısa, doğal Türkçe başlık (en fazla 14 kelime).
5. "ozet": Ne oldu ve kimi etkiliyor: 1-2 Türkçe cümle (en fazla 250 karakter).

Kurallar:
- YALNIZCA verilen metindeki bilgiyi kullan; tarih, sayı veya ayrıntı uydurma.
- Kurum, şirket, ilaç ve teknoloji adlarını özgün hâliyle bırak.
- Aynı olayı anlatan birden çok aday varsa yalnızca en bilgilendirici olanına
  önem ver, diğerlerine 0 ver.
- Yorum ve övgü ("çığır açan", "tarihi") ekleme.
- Her aday için verilen id değerini aynen geri döndür.
"""

SUZGEC_SEMASI = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "id": {"type": "STRING"},
            "bolum": {"type": "STRING"},
            "bolge": {"type": "STRING"},
            "onem": {"type": "INTEGER"},
            "baslik_tr": {"type": "STRING"},
            "ozet": {"type": "STRING"},
        },
        "required": ["id", "bolum", "bolge", "onem", "baslik_tr", "ozet"],
    },
}

BRIFING_TALIMATI = f"""Sen, Türkiye'de çalışan genç bir hekim için haftalık "dünya
brifingi" yazan bir editörsün. Aşağıda bu haftanın seçilmiş haberleri var
(Türkçe başlık, özet, bölge ve önem derecesiyle). Bunlardan brifingi yaz:

- "giris": Haftayı 2 cümlede özetleyen giriş.
- "ana_basliklar": Haftanın en önemli {config.DUNYA_ANA_BASLIK} gelişmesi. Mümkünse farklı
  bölgelerden ve bölümlerden seç. Her biri için:
  "baslik": en fazla 10 kelimelik Türkçe başlık,
  "aciklama": 2-3 cümle: ne oldu ve neden önemli,
  "idler": dayandığı haberlerin id değerleri.

Kurallar:
- YALNIZCA verilen haberlerdeki bilgiyi kullan; sayı, tarih, isim uydurma ve
  haberlerde olmayan sonuç çıkarma.
- Sayıları rakamla yaz.
- Abartı ve övgü yok; sakin, bilgilendirici bir dil kullan.
"""

BRIFING_SEMASI = {
    "type": "OBJECT",
    "properties": {
        "giris": {"type": "STRING"},
        "ana_basliklar": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "baslik": {"type": "STRING"},
                    "aciklama": {"type": "STRING"},
                    "idler": {"type": "ARRAY", "items": {"type": "STRING"}},
                },
                "required": ["baslik", "aciklama", "idler"],
            },
        },
    },
    "required": ["giris", "ana_basliklar"],
}

OKUYUCULAR = {"rss": rss_oku, "haber": haber_oku}


def _oku_json(yol, varsayilan):
    try:
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return varsayilan


# ---------------------------------------------------------------------------
# 1) Adayları topla
# ---------------------------------------------------------------------------
def adaylari_topla(gorulen, hatalar):
    """Kaynakları okur; sırayla karıştırır, daha önce değerlendirilenleri ve
    aynı başlıklı tekrarları atar, DUNYA_ADAY_SINIRI kadarını döndürür."""
    listeler = []
    for k in config.DUNYA_KAYNAKLARI:
        k = {**k, "bolum": "dunya"}
        try:
            yeni = OKUYUCULAR[k["tur"]](k)
            etiket = k["ad"] + (f" ({k['sorgu']})" if k.get("sorgu") else "")
            print(f"  {etiket:45} {len(yeni)} aday")
            listeler.append(yeni)
        except Exception as e:
            traceback.print_exc()
            hatalar.append(f"{k['ad']}: {str(e)[:80]}")
    once = set(gorulen)
    tekil, basliklar = [], set()
    for a in (a for grup in itertools.zip_longest(*listeler) for a in grup if a):
        anahtar = re.sub(r"\W+", "", a["baslik"].lower())[:80]
        if a["id"] in once or anahtar in basliklar or not a["url"] or not a["baslik"]:
            continue
        basliklar.add(anahtar)
        tekil.append(a)
    return tekil[:config.DUNYA_ADAY_SINIRI]


# ---------------------------------------------------------------------------
# 2) Süzgeç
# ---------------------------------------------------------------------------
def _aday_metni(a):
    return (f"id: {a['id']}\nKaynak: {a['kaynak']}\nTarih: {a['tarih'] or '?'}\n"
            f"Başlık: {a['baslik']}\nMetin: {a['metin'] or '(yok)'}")


def _onem(s):
    try:
        return max(0, min(3, int(s.get("onem", 0))))
    except (TypeError, ValueError):
        return 0


def suz(gem, adaylar, bekleme=5):
    """Adayları yapay zekâyla bölüm/bölge/önem'e ayırır ve Türkçeleştirir.
    {bolum: [öğe]} döndürür; her bölüm önem ve tarih sırasıyla, en fazla
    "en_fazla" öğe. Partilerden biri başarısız olursa diğerleri yine işlenir."""
    yanit, son_hata = {}, None
    p = config.GUNDEM_PARTI
    for i in range(0, len(adaylar), p):
        if i:
            time.sleep(bekleme)
        metin = SUZGEC_TALIMATI + "\n\n---\n\n" + "\n\n---\n\n".join(
            _aday_metni(a) for a in adaylar[i:i + p])
        try:
            yanit.update({str(s["id"]): s for s in gem.uret(metin, sema=SUZGEC_SEMASI)})
        except Exception as e:
            son_hata = e
            print(f"  Parti {i // p + 1} süzülemedi: {str(e)[:120]}")
    if not yanit and son_hata:
        raise son_hata
    bolumler = {b: [] for b in config.DUNYA_BOLUMLERI}
    for a in adaylar:
        s = yanit.get(a["id"])
        if not s or s.get("bolum") not in bolumler or _onem(s) < config.DUNYA_EN_AZ_ONEM:
            continue
        o = {k: a[k] for k in ("id", "kaynak", "baslik", "url", "tarih")}
        o.update(baslik_tr=s.get("baslik_tr") or a["baslik"], ozet=kisalt(s.get("ozet") or ""),
                 onem=_onem(s), bolge=s.get("bolge") if s.get("bolge") in BOLGELER else "Diğer")
        # Haber metninde olmayan sayı yazıldıysa bot özeti ⚠️ ile işaretler
        hatali = denetim.dogrulanamayan(f"{o['baslik_tr']} {o['ozet']}",
                                        f"{a['kaynak']} {a['baslik']} {a['metin']} {a['tarih']}")
        if hatali:
            o["sayi_uyarisi"] = hatali
        o["_kaynak_metni"] = f"{a['baslik']} {a['metin']}"
        bolumler[s["bolum"]].append(o)
    for b, ogeler in bolumler.items():
        ogeler.sort(key=lambda o: (o["onem"], o["tarih"]), reverse=True)
        bolumler[b] = birlestir(ogeler)[:config.DUNYA_BOLUMLERI[b]["en_fazla"]]
    return bolumler


# ---------------------------------------------------------------------------
# 3) Brifing
# ---------------------------------------------------------------------------
def brifing_yaz(gem, bolumler):
    """Seçilen haberlerden giriş ve ana başlıklar. Ana başlıklar yalnızca
    gerçekten verilen haberlere (id) dayanıyorsa alınır; kaynak bağlantıları
    o haberlerden eklenir. Hiç geçerli ana başlık yoksa None."""
    ogeler = {o["id"]: o for liste in bolumler.values() for o in liste}
    if not ogeler:
        return None
    metin = BRIFING_TALIMATI + "\n\n---\n\n" + "\n\n---\n\n".join(
        f"id: {o['id']}\nBölüm: {config.DUNYA_BOLUMLERI[b]['ad']}\nBölge: {o['bolge']}\n"
        f"Önem: {o['onem']}\nBaşlık: {o['baslik_tr']}\nÖzet: {o['ozet']}"
        for b, liste in bolumler.items() for o in liste)
    y = gem.uret(metin, sema=BRIFING_SEMASI)
    basliklar = []
    for ab in (y.get("ana_basliklar") or [])[:config.DUNYA_ANA_BASLIK]:
        dayanak = [ogeler[str(i)] for i in ab.get("idler") or [] if str(i) in ogeler]
        if not dayanak or not ab.get("baslik"):
            continue  # uydurma ya da eşleşmeyen id: kaynaksız ana başlık yazılmaz
        b = {"baslik": ab["baslik"], "aciklama": ab.get("aciklama", ""),
             "kaynaklar": [{"ad": o["kaynak"], "url": o["url"]} for o in dayanak[:3]]}
        kaynak = " ".join(f"{o['_kaynak_metni']} {o['baslik_tr']} {o['ozet']}" for o in dayanak)
        hatali = denetim.dogrulanamayan(f"{b['baslik']} {b['aciklama']}", kaynak)
        if hatali:
            b["sayi_uyarisi"] = hatali
        basliklar.append(b)
    if not basliklar:
        return None
    return {"giris": y.get("giris", ""), "ana_basliklar": basliklar}


def telegram_metni(cikti, aciklama_siniri=None):
    """Telegram'a doğrudan gönderilecek brifing (HTML). Mesaj sınırını
    aşarsa metin kesilmez (HTML etiketi bölünür); açıklamalar kısaltılır."""
    e = lambda s: html.escape(str(s or ""), quote=True)
    b = cikti.get("brifing")
    satirlar = [f"🌍 <b>Dünya brifingi</b> · {e(cikti['hafta'])}"]
    if b:
        if b.get("giris"):
            satirlar.append(f"<i>{e(b['giris'])}</i>")
        for i, ab in enumerate(b["ana_basliklar"], 1):
            kaynaklar = ", ".join(f'<a href="{e(k["url"])}">{e(k["ad"])}</a>'
                                  for k in ab["kaynaklar"])
            aciklama = kisalt(ab["aciklama"], aciklama_siniri) if aciklama_siniri else ab["aciklama"]
            satirlar.append(f"<b>{i}. {e(ab['baslik'])}</b>\n{e(aciklama)}"
                            f"{' ⚠️' if ab.get('sayi_uyarisi') else ''}\n🔗 {kaynaklar}")
    sayilar = " · ".join(f"{s['ad']} {len(s['ogeler'])}"
                         for s in cikti["bolumler"].values())
    satirlar.append(f"{e(sayilar)}\nTüm haberler: /dunya")
    if any(ab.get("sayi_uyarisi") for ab in (b or {}).get("ana_basliklar", [])):
        satirlar.append("<i>⚠️ Bazı sayılar kaynak haberlerde bulunamadı; teyit et.</i>")
    if cikti["hatalar"]:
        satirlar.append(f"<i>⚠️ Okunamayan kaynaklar: {e('; '.join(cikti['hatalar']))}</i>")
    metin = "\n\n".join(satirlar)
    if len(metin) > 4000 and (aciklama_siniri or 1000) > 150:
        return telegram_metni(cikti, (aciklama_siniri or 600) - 150)
    return metin


# ---------------------------------------------------------------------------
# Ana akış
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sahte-ozet", action="store_true")
    ap.add_argument("--bildirim-yok", action="store_true")
    a = ap.parse_args()

    gorulen = _oku_json(GORULEN, [])
    os.makedirs(CIKTI, exist_ok=True)
    # Brifing acil değil: ana model yoğunsa yedeğe geçmeden önce bekleyerek dene
    gem = (ozetleyici.SahteGemini() if a.sahte_ozet
           else llm.Zincir(yogun_deneme=5, yogun_bekleme=30))
    bugun = dt.date.today()
    cikti = {"hafta": hafta_etiketi(bugun), "hazirlanma": bugun.isoformat(),
             "model": gem.model, "bolumler": {}, "brifing": None, "hatalar": []}

    print("== Kaynaklar taranıyor ==")
    adaylar = adaylari_topla(gorulen, cikti["hatalar"])
    print(f"\n== Süzgeç: {len(adaylar)} aday ==")
    try:
        bolumler = suz(gem, adaylar, bekleme=0 if a.sahte_ozet else 5)
    except Exception as e:
        print(f"SÜZGEÇ HATASI: {e}")
        if not a.bildirim_yok:
            telegram_bildir(f"⚠️ Dünya brifingi hazırlanamadı: yapay zekâ yanıt vermedi ({str(e)[:100]}).")
        sys.exit(1)
    for b, ogeler in bolumler.items():
        print(f"  {config.DUNYA_BOLUMLERI[b]['ad']}: {len(ogeler)} haber")

    print("\n== Brifing yazılıyor ==")
    try:
        cikti["brifing"] = brifing_yaz(gem, bolumler)
    except Exception as e:
        # Brifing yazılamasa da bölümler yayımlanır
        print(f"  BRİFİNG HATASI: {e}")
        cikti["hatalar"].append("brifing metni üretilemedi")
    for b, ogeler in bolumler.items():
        for o in ogeler:
            o.pop("_kaynak_metni", None)
        cikti["bolumler"][b] = {"ad": config.DUNYA_BOLUMLERI[b]["ad"], "ogeler": ogeler}
    cikti["aday"] = len(adaylar)
    cikti["model"] = gem.son_model
    cikti["ana_model"] = gem.model
    cikti["model_kullanimi"] = gem.kullanim
    cikti["model_notlari"] = gem.notlar

    with open(os.path.join(CIKTI, "dunya.json"), "w", encoding="utf-8") as f:
        json.dump(cikti, f, ensure_ascii=False, indent=1)
    if not a.sahte_ozet:
        # Değerlendirilen adaylar sonraki haftalarda tekrar gelmesin
        with open(GORULEN, "w", encoding="utf-8") as f:
            json.dump(([x["id"] for x in adaylar] + gorulen)[:GORULEN_SINIRI], f, indent=0)
    print(f"\nTamam: brifing {'var' if cikti['brifing'] else 'YOK'}, "
          f"{sum(len(s['ogeler']) for s in cikti['bolumler'].values())} haber")

    if not a.bildirim_yok:
        telegram_bildir(telegram_metni(cikti), html_bicim=True)


if __name__ == "__main__":
    main()
