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
YEDEK_MODELLER = ["gemini-flash-lite-latest", "gemini-2.5-flash", "gemini-2.5-flash-lite"]

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
        # Boş değişken ("") de varsayılana düşsün
        self.model = model or os.getenv("GEMINI_MODEL") or VARSAYILAN_MODEL
        # Ana model yoğun/erişilemezse sırayla denenecek yedekler
        yedek = os.getenv("GEMINI_YEDEK") or ",".join(YEDEK_MODELLER)
        self.modeller = [self.model] + [m.strip() for m in yedek.split(",")
                                        if m.strip() and m.strip() != self.model]

    def uret(self, metin, sema=None, sicaklik=0.2):
        govde = {
            "contents": [{"role": "user", "parts": [{"text": metin}]}],
            "generationConfig": {"temperature": sicaklik},
        }
        if sema:
            govde["generationConfig"]["responseMimeType"] = "application/json"
            govde["generationConfig"]["responseSchema"] = sema
        son_hata = ""
        for model in self.modeller:
            url = f"{API}/{model}:generateContent"
            for deneme in range(3):
                r = requests.post(url, json=govde, timeout=180,
                                  headers={"x-goog-api-key": self.api_key})
                if r.ok:
                    veri = r.json()
                    parcalar = veri["candidates"][0]["content"]["parts"]
                    yanit = "".join(p.get("text", "") for p in parcalar)
                    self.son_model = model
                    return json.loads(yanit) if sema else yanit
                son_hata = f"{model} {r.status_code}: {r.text[:300]}"
                if r.status_code == 429:
                    if "PerDay" in r.text or "per day" in r.text.lower():
                        print(f"  {model}: günlük kota dolu, sonraki modele geçiliyor")
                        break
                    bekle = min(_bekleme_suresi(r) or 20, 90)
                elif r.status_code in (500, 503):
                    # Model yoğun: kısa bekle, 2. denemeden sonra yedeğe geç
                    if deneme >= 1:
                        print(f"  {model} yoğun (503), yedek modele geçiliyor")
                        break
                    bekle = 10
                else:
                    # 404 (model yok), 400 vb.: bu modeli bırak
                    print(f"  {model} hata {r.status_code}: {r.text[:200]}")
                    break
                print(f"  {model} {r.status_code}, {bekle} sn bekleniyor...")
                time.sleep(bekle)
        raise RuntimeError(f"Hiçbir Gemini modeli yanıt vermedi. Son hata: {son_hata}")


def _bekleme_suresi(r):
    """429 yanıtındaki RetryInfo'dan önerilen bekleme süresini (sn) okur."""
    try:
        for d in r.json()["error"].get("details", []):
            if "retryDelay" in d:
                return int(float(d["retryDelay"].rstrip("s"))) + 2
    except Exception:
        pass
    return None


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
