"""
Türkçe kısa özet üretimi (haftalık toplu hazırlık için).

Ücretsiz katmanda dakika başına istek sınırı olduğu için her alanın aday
makaleleri (en fazla 12 + Türk dergisi) TEK istekte özetlenir ve cerrahi
ilgi puanı alır (haftada ~15 istek). İstekler llm.Zincir üzerinden gider.
"""

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


def kisa_ozetle(zincir, makaleler):
    """{pmid: {"baslik_tr", "kisa_ozet"}} döndürür."""
    if not makaleler:
        return {}
    metin = KISA_OZET_TALIMATI + "\n\n---\n\n" + "\n\n---\n\n".join(
        _makale_metni(m) for m in makaleler)
    sonuc = zincir.uret(metin, sema=KISA_OZET_SEMASI)
    return {s["pmid"]: s for s in sonuc}


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
