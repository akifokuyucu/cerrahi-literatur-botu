"""
Gemini ile Türkçe kısa özet üretimi (haftalık toplu hazırlık için).

Ücretsiz katmanda dakika başına istek sınırı olduğu için her alanın 5-6
makalesi TEK istekte özetlenir (haftada ~15 istek).
"""
import json
import os
import time

import requests

API = "https://generativelanguage.googleapis.com/v1beta/models"
VARSAYILAN_MODEL = "gemini-flash-latest"

KISA_OZET_TALIMATI = """Sen genel cerrahi alanında deneyimli bir akademisyensin.
Aşağıda PubMed'den alınmış makaleler var. Her biri için:

1. "baslik_tr": Başlığın kısa, doğal Türkçe karşılığı (en fazla 12 kelime).
2. "kisa_ozet": Türkçe, 2-3 cümlelik kısa özet (en fazla 350 karakter).

Kurallar:
- Tıbbi terimleri ve kısaltmaları İngilizce bırak (ör. anastomotic leak,
  RCT, hazard ratio, TNT, ERAS). Cümle yapısı Türkçe olsun.
- Çalışma tasarımını, hasta sayısını ve ana bulguyu SAYILARLA ver.
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
        },
        "required": ["pmid", "baslik_tr", "kisa_ozet"],
    },
}


class Gemini:
    def __init__(self, api_key=None, model=None):
        self.api_key = api_key or os.environ["GEMINI_API_KEY"]
        self.model = model or os.getenv("GEMINI_MODEL", VARSAYILAN_MODEL)

    def uret(self, metin, sema=None, sicaklik=0.2):
        govde = {
            "contents": [{"role": "user", "parts": [{"text": metin}]}],
            "generationConfig": {"temperature": sicaklik},
        }
        if sema:
            govde["generationConfig"]["responseMimeType"] = "application/json"
            govde["generationConfig"]["responseSchema"] = sema
        url = f"{API}/{self.model}:generateContent"
        bekle = 20
        for deneme in range(5):
            r = requests.post(url, json=govde, timeout=180,
                              headers={"x-goog-api-key": self.api_key})
            if r.status_code in (429, 500, 503):
                # Ücretsiz katman sınırı ya da geçici yoğunluk: bekle, tekrar dene
                print(f"  Gemini {r.status_code}, {bekle} sn bekleniyor...")
                time.sleep(bekle)
                bekle *= 2
                continue
            r.raise_for_status()
            veri = r.json()
            parcalar = veri["candidates"][0]["content"]["parts"]
            yanit = "".join(p.get("text", "") for p in parcalar)
            return json.loads(yanit) if sema else yanit
        r.raise_for_status()


def _makale_metni(m):
    return (f"pmid: {m['pmid']}\nDergi: {m['dergi']}\n"
            f"Çalışma tipi: {m.get('tip_etiketi', '')}\n"
            f"Başlık: {m['baslik']}\nÖzet:\n{m['ozet'] or '(özet yok)'}")


def kisa_ozetle(gemini, makaleler):
    """{pmid: {"baslik_tr", "kisa_ozet"}} döndürür."""
    if not makaleler:
        return {}
    metin = KISA_OZET_TALIMATI + "\n\n---\n\n" + "\n\n---\n\n".join(
        _makale_metni(m) for m in makaleler)
    sonuc = gemini.uret(metin, sema=KISA_OZET_SEMASI)
    return {s["pmid"]: s for s in sonuc}


class SahteGemini:
    """Test için: API'ye gitmeden yer tutucu özet üretir."""
    model = "sahte"

    def uret(self, metin, sema=None, sicaklik=0.2):
        pmidler = [s.split(":", 1)[1].strip()
                   for s in metin.splitlines() if s.startswith("pmid:")]
        return [{"pmid": p, "baslik_tr": f"(test başlığı {p})",
                 "kisa_ozet": f"(test özeti {p})"} for p in pmidler]
