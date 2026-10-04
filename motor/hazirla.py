"""
Haftalık hazırlık: 14 alanı tara, puanla, özetle, cikti/hafta.json'a yaz,
listedeki makalelerin ayrıntılı özetlerini cikti/detay.json'a yaz,
Telegram'dan "liste hazır" bildirimi gönder.

GitHub Actions her pazartesi bunu çalıştırır. Elle deneme:
  python hazirla.py                      # canlı (en az GEMINI_API_KEY gerekir)
  python hazirla.py --sahte-ozet         # yapay zekâsız deneme
  python hazirla.py --alan kolorektal --girdi test_verisi/x.xml --sahte-ozet
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import traceback

import requests

import config
import detay
import llm
import motor
import ozetleyici
import pubmed
import puanlama

CIKTI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cikti")
AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
         "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

# Botun ihtiyaç duyduğu alanlar (hafta.json'u küçük tutmak için)
TUTULAN = ["pmid", "baslik", "baslik_tr", "kisa_ozet", "ozet", "dergi",
           "dergi_tam", "yil", "doi", "pmc", "tip", "tip_etiketi", "toplam",
           "dergi_puani", "tip_puani", "cok_merkezli", "orneklem",
           "cerrahi_ilgi", "kisisel", "sayi_uyarisi"]


def hafta_etiketi(bugun):
    bas = bugun - dt.timedelta(days=config.PENCERE_GUN)
    if bas.month == bugun.month:
        return f"{bas.day}–{bugun.day} {AYLAR[bugun.month - 1]} {bugun.year}"
    return (f"{bas.day} {AYLAR[bas.month - 1]} – "
            f"{bugun.day} {AYLAR[bugun.month - 1]} {bugun.year}")


def sadelestir(m):
    return {k: m.get(k) for k in TUTULAN if k in m} if m else None


def oylari_getir():
    """Bottaki 👍/👎 oylarını okur (BOT_ANAHTAR yoksa kişisel puan kapalı)."""
    anahtar = os.getenv("BOT_ANAHTAR")
    if not anahtar:
        print("BOT_ANAHTAR yok, kişisel puanlama atlanıyor.")
        return []
    try:
        r = requests.get(f"{config.BOT_URL}/geri-bildirim", timeout=30,
                         headers={"X-Bot-Anahtar": anahtar})
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"Oylar okunamadı ({e}), kişisel puanlama atlanıyor.")
        return []


def telegram_bildir(metin):
    token, sohbet = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (token and sohbet):
        print("Telegram bilgileri yok, bildirim atlanıyor.")
        return
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": sohbet, "text": metin}, timeout=30)
    print("Telegram bildirimi:", r.status_code)


def ayrintili_ozetler(gem, cikti, sahte=False):
    """Listedeki makalelerin ayrıntılı özetlerini cikti/detay.json'a yazar.
    Sıra: önce öne çıkanlar, sonra alanlar; süre dolarsa kalanları bot
    tuşa basılınca üretir."""
    sira = list(cikti["gundem"])
    for s in cikti["alanlar"].values():
        sira += s["makaleler"] + ([s["turk"]] if s["turk"] else [])
    tekil = {}
    for m in sira:
        tekil.setdefault(m["pmid"], m)
    makaleler = list(tekil.values())

    yol = os.path.join(CIKTI, "detay.json")
    onceki = {}
    try:
        with open(yol, encoding="utf-8") as f:
            eski = json.load(f)
        # Aynı gün yeniden çalıştırılırsa hazır özetler tekrar üretilmez
        if eski.get("hazirlanma") == cikti["hazirlanma"]:
            onceki = eski.get("detaylar", {})
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    print(f"\n== Ayrıntılı özetler: {len(makaleler)} makale ==")
    detaylar = detay.hepsini_hazirla(
        gem, makaleler, onceki, config.DETAY_SURE_DK,
        bekleme=0 if sahte else 4, tam_metin_al=not sahte)
    with open(yol, "w", encoding="utf-8") as f:
        json.dump({"hafta": cikti["hafta"], "hazirlanma": cikti["hazirlanma"],
                   "detaylar": detaylar}, f, ensure_ascii=False, indent=1)
    print(f"  {len(detaylar)}/{len(makaleler)} ayrıntılı özet hazır")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alan", help="yalnızca bu alan (deneme için)")
    ap.add_argument("--girdi", help="kayıtlı PubMed XML (deneme için)")
    ap.add_argument("--sahte-ozet", action="store_true")
    ap.add_argument("--bildirim-yok", action="store_true")
    ap.add_argument("--detay-yok", action="store_true",
                    help="ayrıntılı özetleri hazırlama (bot anlık üretir)")
    a = ap.parse_args()

    pm = None if a.girdi else pubmed.PubMed(
        email=os.getenv("NCBI_EMAIL"), api_key=os.getenv("NCBI_API_KEY"))
    gem = ozetleyici.SahteGemini() if a.sahte_ozet else llm.Zincir()
    alanlar = [a.alan] if a.alan else list(config.ALANLAR)

    bugun = dt.date.today()
    cikti = {"hafta": hafta_etiketi(bugun), "hazirlanma": bugun.isoformat(),
             "model": gem.model, "alanlar": {}, "hatalar": []}
    ozet_onbellek = {}
    oylar = [] if a.girdi else oylari_getir()
    tercih = puanlama.tercihleri_hesapla(oylar) if oylar else None
    cikti["oy_sayisi"] = len(oylar)
    if tercih:
        print(f"{len(oylar)} oy okundu; kişisel tercihler: {tercih}")

    for kod in alanlar:
        print(f"\n== {config.ALANLAR[kod]['ad']} ==")
        try:
            s = motor.alan_hazirla(kod, pm, a.girdi, n=config.ADAY_SAYISI,
                                   tercih=tercih)
        except Exception:
            traceback.print_exc()
            cikti["hatalar"].append(f"{kod}: PubMed hatası")
            continue
        print(f"  {s['taranan']} tarandı, {s['puanlanan']} puanlandı")

        ozetlenecek = [m for m in s["makaleler"] + [s["turk"]]
                       if m and m["pmid"] not in ozet_onbellek]
        try:
            ozet_onbellek.update(ozetleyici.kisa_ozetle(gem, ozetlenecek))
            print(f"  {len(ozetlenecek)} makale özetlendi")
        except Exception as e:
            print(f"  ÖZET HATASI: {e}")
            cikti["hatalar"].append(f"{kod}: özet üretilemedi")
        time.sleep(0 if a.sahte_ozet else 5)  # dakika başı istek sınırına saygı

        def ekle(m):
            if not m:
                return None
            o = ozet_onbellek.get(m["pmid"], {})
            return sadelestir({**m, "baslik_tr": o.get("baslik_tr", ""),
                               "kisa_ozet": o.get("kisa_ozet", ""),
                               "cerrahi_ilgi": o.get("cerrahi_ilgi"),
                               # yalnızca doğrulanamayan sayı varsa yazılır
                               **({"sayi_uyarisi": o["sayi_uyarisi"]}
                                  if o.get("sayi_uyarisi") else {})})

        # Cerrahi ilgi filtresi: yapay zekânın "ilgisiz" (0) dediği adaylar elenir,
        # kalanlar puan sırasını koruyarak ilk 5'e girer
        uygun = [m for m in s["makaleler"]
                 if ozet_onbellek.get(m["pmid"], {}).get("cerrahi_ilgi", 1) != 0]
        elenen = len(s["makaleler"]) - len(uygun)
        if elenen:
            print(f"  {elenen} aday cerrahiyle ilgisiz bulunup elendi")

        cikti["alanlar"][kod] = {
            "ad": s["ad"], "taranan": s["taranan"],
            "makaleler": [ekle(m) for m in uygun[:config.ALAN_BASINA]],
            "turk": ekle(s["turk"]),
        }
        if s["turk"] and not a.girdi:
            motor.turk_gosterildi_isaretle(kod, s["turk"]["pmid"])

    # 🔥 Bu hafta gündemde: tüm alanlardan en yüksek puanlı 5 makale
    havuz = {}
    for kod, s in cikti["alanlar"].items():
        for m in s["makaleler"]:
            havuz.setdefault(m["pmid"], {**m, "alan": s["ad"]})
    cikti["model"] = gem.son_model
    cikti["ana_model"] = gem.model
    cikti["model_kullanimi"] = gem.kullanim
    cikti["model_notlari"] = gem.notlar
    cikti["gundem"] = sorted(
        havuz.values(), reverse=True,
        key=lambda m: (m["toplam"] + (m.get("kisisel") or 0),
                       m["cok_merkezli"], m["orneklem"]))[:5]

    os.makedirs(CIKTI, exist_ok=True)
    with open(os.path.join(CIKTI, "hafta.json"), "w", encoding="utf-8") as f:
        json.dump(cikti, f, ensure_ascii=False, indent=1)
    toplam = sum(len(s["makaleler"]) for s in cikti["alanlar"].values())
    print(f"\nTamam: {len(cikti['alanlar'])} alan, {toplam} makale.")

    if not a.detay_yok and cikti["alanlar"]:
        ayrintili_ozetler(gem, cikti, sahte=a.sahte_ozet)

    if not a.bildirim_yok:
        ek = (f"\n⚠️ Sorunlu alanlar: {', '.join(cikti['hatalar'])}"
              if cikti["hatalar"] else "")
        telegram_bildir(f"📚 {cikti['hafta']} listeleri hazır "
                        f"({len(cikti['alanlar'])} alan, {toplam} makale).\n"
                        f"Bakmak için /start{ek}")
    # Hiç alan hazırlanamadıysa iş akışı başarısız görünsün
    if not cikti["alanlar"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
