"""
Türkçe kısa özet üretimi (haftalık toplu hazırlık için).

Ücretsiz katmanda dakika başına istek sınırı olduğu için her alanın aday
makaleleri (en fazla 12 + Türk dergisi) TEK istekte özetlenir ve cerrahi
ilgi puanı alır (haftada ~15 istek). İstekler llm.Zincir üzerinden gider.
"""
import denetim

KISA_OZET_TALIMATI = """Sen genel cerrahi alanında deneyimli bir akademisyensin.
Aşağıda PubMed'den alınmış makaleler var. Her biri için:

1. "baslik_tr": Başlığın kısa, doğal Türkçe karşılığı (en fazla 12 kelime).
2. "kisa_ozet": Türkçe, 2-3 cümlelik kısa özet (en fazla 350 karakter).
3. "cerrahi_ilgi": Makale bir GENEL CERRAHIN karar verme veya ameliyat
   pratiğini değiştirebilir mi? Katı değerlendir:
   2 = doğrudan: ameliyat endikasyonu/zamanlaması, cerrahi teknik veya
       yaklaşım, perioperatif bakım, cerrahi komplikasyon ve sonuçlar,
       cerrahi kılavuzlar
   1 = dolaylı ama cerrahın kararını etkiler: ör. ameliyatın kapsamını veya
       zamanlamasını belirleyen neoadjuvan tedavi, preoperatif görüntüleme/
       evreleme, cerrahi eğitim, cerrahide yapay zekâ/teknoloji, cerrahi
       hizmetin organizasyonu
   0 = cerrahın pratiğini değiştirmez: radyoterapi dozu/fraksiyonu
       karşılaştırmaları, sistemik ilaç etkinliği veya biyobenzer çalışmaları,
       prognostik biyobelirteç/ctDNA çalışmaları, ilaç yan etkileri, temel
       bilim ve hayvan deneyleri, başka branşın konusu
   Emin değilsen 0 ile 1 arasında 0'ı seç.

Kurallar:
- Tıbbi terimleri ve kısaltmaları İngilizce bırak (ör. anastomotic leak,
  RCT, hazard ratio, TNT, ERAS). Cümle yapısı Türkçe olsun.
- Çalışma tasarımını, hasta sayısını ve ana bulguyu ver.
- Sayıları MUTLAKA RAKAMLA yaz (750 hasta, %59, RR 0,68); asla yazıyla
  yazma ("yedi yüz elli" YANLIŞ).
- Metinde varsa ana etki büyüklüğünü mutlaka ekle: oranlar (%4,8'e karşı
  %13,5), RR/OR/HR, %95 CI veya p değeri.
- Örnek: "233 hastalık tek merkezli RCT'de dikişsiz teknikte parastomal
  hernia %4,8, dikişlide %13,5 bulundu (RR 0,35; p=0,047)."
- YALNIZCA verilen metindeki bilgiyi kullan. Metinde olmayan sayı, sonuç
  veya yorum ekleme. Özet yoksa yalnızca başlıktan çıkarılabileni yaz.
- Kendi görüşünü, "önemli bir çalışma" gibi değerlendirmeleri ekleme.
- Her makale için verilen pmid değerini aynen geri döndür.
"""

KISA_OZET_SEMASI = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "pmid": {"type": "STRING"},
            "baslik_tr": {"type": "STRING"},
            "kisa_ozet": {"type": "STRING"},
            "cerrahi_ilgi": {"type": "INTEGER"},
        },
        "required": ["pmid", "baslik_tr", "kisa_ozet", "cerrahi_ilgi"],
    },
}


def _makale_metni(m):
    return (f"pmid: {m['pmid']}\nDergi: {m['dergi']}\n"
            f"Çalışma tipi: {m.get('tip_etiketi', '')}\n"
            f"Başlık: {m['baslik']}\nÖzet:\n{m['ozet'] or '(özet yok)'}")


def _kaynak(m):
    """Sayı denetiminde özetin karşılaştırılacağı metin (talimat hariç)."""
    return f"{m['dergi']} {m.get('tip_etiketi', '')} {m['baslik']} {m.get('ozet') or ''}"


def _istek(zincir, makaleler, ek_not=""):
    metin = KISA_OZET_TALIMATI + ek_not + "\n\n---\n\n" + "\n\n---\n\n".join(
        _makale_metni(m) for m in makaleler)
    return {s["pmid"]: s for s in zincir.uret(metin, sema=KISA_OZET_SEMASI)}


def _hatali_sayilar(s, m):
    return denetim.dogrulanamayan(f"{s.get('baslik_tr', '')} {s.get('kisa_ozet', '')}",
                                  _kaynak(m))


def kisa_ozetle(zincir, makaleler):
    """{pmid: {"baslik_tr", "kisa_ozet", "cerrahi_ilgi"[, "sayi_uyarisi"]}}.
    Metinde olmayan sayı yazılan özetler bir kez uyarıyla yeniden üretilir;
    yine düzelmezse "sayi_uyarisi" alanıyla işaretlenir."""
    if not makaleler:
        return {}
    sonuc = _istek(zincir, makaleler)
    hatali = {m["pmid"]: _hatali_sayilar(sonuc[m["pmid"]], m)
              for m in makaleler if m["pmid"] in sonuc}
    hatali = {p: s for p, s in hatali.items() if s}
    if hatali:
        print(f"  Sayı denetimi: {len(hatali)} özette doğrulanamayan sayı, yeniden deneniyor")
        tekrar = [m for m in makaleler if m["pmid"] in hatali]
        sayilar = sorted({x for s in hatali.values() for x in s})
        try:
            yeni = _istek(zincir, tekrar, denetim.uyari_notu(sayilar))
        except Exception as e:
            print(f"  Yeniden deneme başarısız: {str(e)[:120]}")
            yeni = {}
        for m in tekrar:
            p = m["pmid"]
            if p in yeni:
                kalan = _hatali_sayilar(yeni[p], m)
                if len(kalan) < len(hatali[p]):
                    sonuc[p], hatali[p] = yeni[p], kalan
            if hatali[p]:
                sonuc[p]["sayi_uyarisi"] = hatali[p]
    return sonuc


class SahteGemini:
    """Test için: API'ye gitmeden yer tutucu özet üretir."""
    model = son_model = "sahte"
    notlar = []
    kullanim = {}

    def uret(self, metin, sema=None, sicaklik=0.2):
        if sema and sema.get("type") == "OBJECT":  # ayrıntılı özet (detay.py)
            baslik = next((s[8:] for s in metin.splitlines() if s.startswith("Başlık: ")), "")
            return {"baslik_tr": f"(test) {baslik[:60]}", "tek_cumle": "(test cümlesi)",
                    "tasarim": "(test tasarımı)", "ana_bulgular": ["(test bulgusu)"],
                    "sinirliliklar": ["(test sınırlılığı)"], "pratige_etkisi": "(test)"}
        idler = [s.split(":", 1)[1].strip()
                 for s in metin.splitlines() if s.startswith("id:")]
        if idler:  # gündem adayları (gundem.py)
            return [{"id": i, "baslik_tr": f"(test başlığı {i})",
                     "ozet": f"(test özeti {i})", "ilgi": 0 if n % 3 == 2 else 2}
                    for n, i in enumerate(idler)]
        pmidler = [s.split(":", 1)[1].strip()
                   for s in metin.splitlines() if s.startswith("pmid:")]
        # Testte her 3. makale "ilgisiz" sayılır ki filtre denenebilsin
        return [{"pmid": p, "baslik_tr": f"(test başlığı {p})",
                 "kisa_ozet": f"(test özeti {p})",
                 "cerrahi_ilgi": 0 if i % 3 == 2 else 2}
                for i, p in enumerate(pmidler)]
