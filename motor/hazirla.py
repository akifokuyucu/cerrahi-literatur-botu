"""
Haftalık hazırlık: 14 alanı tara, puanla, her alana 1 YÖK Tez ekle, özetle,
cikti/hafta.json'a yaz, ayrıntılı özetleri cikti/detay.json'a yaz,
Telegram'dan "liste hazır" bildirimi gönder.

GitHub Actions her pazartesi bunu çalıştırır. Elle deneme:
  python hazirla.py                      # canlı (en az GEMINI_API_KEY gerekir)
  python hazirla.py --sahte-ozet         # yapay zekâsız deneme
  python hazirla.py --alan kolorektal --girdi test_verisi/x.xml --sahte-ozet
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import time
import traceback

import requests

import arsiv
import config
import detay
import llm
import motor
import ozetleyici
import pubmed
import puanlama
import yoktez

CIKTI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cikti")
AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
         "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

# Botun ihtiyaç duyduğu alanlar (hafta.json'u küçük tutmak için)
TUTULAN = ["pmid", "baslik", "baslik_tr", "kisa_ozet", "ozet", "dergi",
           "dergi_tam", "yil", "doi", "pmc", "tip", "tip_etiketi", "toplam",
           "dergi_puani", "tip_puani", "cok_merkezli", "orneklem",
           "editoryal", "nct",
           "cerrahi_ilgi", "alan_uyumu", "pratik_etkisi", "yz_puani",
           "kisisel", "sayi_uyarisi",
           # 🎓 YÖK Tez satırı
           "tez_no", "yazar", "danisman", "universite", "url"]


def hafta_etiketi(bugun):
    bas = bugun - dt.timedelta(days=config.PENCERE_GUN)
    if bas.month == bugun.month:
        return f"{bas.day}–{bugun.day} {AYLAR[bugun.month - 1]} {bugun.year}"
    return (f"{bas.day} {AYLAR[bas.month - 1]} – "
            f"{bugun.day} {AYLAR[bugun.month - 1]} {bugun.year}")


def sadelestir(m):
    return {k: m.get(k) for k in TUTULAN if k in m} if m else None


def oylari_getir(uc="geri-bildirim", ad="Oylar"):
    """Bottaki 👍/👎 oylarını (/geri-bildirim) ya da dolaylı ilgiyi (/ilgi)
    okur. BOT_ANAHTAR yoksa ya da okunamazsa boş liste: kişisel puan kapalı."""
    anahtar = os.getenv("BOT_ANAHTAR")
    if not anahtar:
        print(f"BOT_ANAHTAR yok, {ad.lower()} atlanıyor.")
        return []
    try:
        r = requests.get(f"{config.BOT_URL}/{uc}", timeout=30,
                         headers={"X-Bot-Anahtar": anahtar})
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"{ad} okunamadı ({e}), atlanıyor.")
        return []


def telegram_bildir(metin, html_bicim=False):
    """html_bicim: metin Telegram HTML'i (kaçışlı); bağlantı önizlemesi kapalı."""
    token, sohbet = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (token and sohbet):
        print("Telegram bilgileri yok, bildirim atlanıyor.")
        return
    govde = {"chat_id": sohbet, "text": metin}
    if html_bicim:
        govde.update(parse_mode="HTML", link_preview_options={"is_disabled": True})
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json=govde, timeout=30)
    if html_bicim and r.status_code == 400:
        # Telegram HTML'i reddettiyse mesaj kaybolmasın: etiketsiz düz metin
        print("Telegram HTML'i reddetti, düz metin gönderiliyor:", r.text[:200])
        duz = html.unescape(re.sub(r"<[^>]+>", "", metin))
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": sohbet, "text": duz}, timeout=30)
    print("Telegram bildirimi:", r.status_code)


def ayrintili_ozetler(gem, cikti, sahte=False):
    """Listedeki makalelerin ayrıntılı özetlerini cikti/detay.json'a yazar.
    Sıra: önce öne çıkanlar, sonra alanlar; süre dolarsa kalanları bot
    tuşa basılınca üretir."""
    sira = list(cikti["gundem"])
    for s in cikti["alanlar"].values():
        sira += s["makaleler"] + [x for x in (s["turk"], s.get("tez")) if x]
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
    ap.add_argument("--tez-yok", action="store_true",
                    help="YÖK Tez satırını atla (--girdi ile kendiliğinden atlanır)")
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
    ilgiler = [] if a.girdi else oylari_getir("ilgi", "Dolaylı ilgi")
    tercih = puanlama.tercihleri_hesapla(oylar, ilgiler) if (oylar or ilgiler) else None
    cikti["oy_sayisi"] = len(oylar)
    cikti["ilgi_sayisi"] = len(ilgiler)
    if tercih:
        print(f"{len(oylar)} oy, {len(ilgiler)} ilgi kaydı okundu; kişisel tercihler: {tercih}")
    # 🎓 Her alana fazladan 1 YÖK Tez; site erişilemezse o hafta atlanır
    yt = None if (a.girdi or a.tez_yok) else yoktez.YokTez()
    secilen_tezler = []

    # 1) Tüm alanları tara ve puanla
    taranan = {}
    for kod in alanlar:
        try:
            s = motor.alan_hazirla(kod, pm, a.girdi, n=config.ADAY_SAYISI,
                                   tercih=tercih)
        except Exception:
            traceback.print_exc()
            cikti["hatalar"].append(f"{kod}: PubMed hatası")
            continue
        print(f"{s['ad']}: {s['taranan']} tarandı, {s['puanlanan']} puanlandı")
        taranan[kod] = s

    # 2) Birden çok alanın sorgusuna takılan makale yalnızca en uygun alanında
    #    kalır; yapay zekâya da tek kez gider
    dagitim = puanlama.alanlara_dagit({k: s["tum"] for k, s in taranan.items()})
    yz = {}  # aday arşivi için: {pmid: yapay zekâ değerlendirmesi + alan}

    for kod, s in taranan.items():
        print(f"\n== {s['ad']} ==")
        s["makaleler"] = dagitim[kod][:config.ADAY_SAYISI]
        tasinan = len(s["tum"]) - len(dagitim[kod])
        if tasinan:
            print(f"  {tasinan} aday daha uygun olduğu alana bırakıldı")

        tez = None
        if yt:
            try:
                tez = yoktez.tez_sec(yt, kod, haric=secilen_tezler)
                print(f"  YÖK Tez: {tez['tez_no']} {tez['baslik'][:60]}" if tez
                      else "  YÖK Tez: uygun tez yok")
            except Exception as e:
                print(f"  YÖK Tez okunamadı, bu hafta atlanıyor: {str(e)[:150]}")
                cikti["hatalar"].append("YÖK Tez okunamadı")
                yt = None
        if tez:
            secilen_tezler.append(tez["tez_no"])

        ozetlenecek = [m for m in s["makaleler"] + [s["turk"], tez]
                       if m and m["pmid"] not in ozet_onbellek]
        try:
            yeni = ozetleyici.kisa_ozetle(
                gem, ozetlenecek, parti=config.OZET_PARTI,
                bekleme=0 if a.sahte_ozet else 5, alan=s["ad"])
            ozet_onbellek.update(yeni)
            yz.update({p: {**o, "alan": kod} for p, o in yeni.items()})
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
                               "alan_uyumu": o.get("alan_uyumu"),
                               "pratik_etkisi": o.get("pratik_etkisi"),
                               # yalnızca doğrulanamayan sayı varsa yazılır
                               **({"sayi_uyarisi": o["sayi_uyarisi"]}
                                  if o.get("sayi_uyarisi") else {})})

        # Yapay zekâ süzgeci ve sırası: "cerrahiyle ilgisiz" ya da "bu alanın
        # konusu değil" (0) denen adaylar elenir; alan uyumu ve pratiğe etkisi
        # kural puanına eklenip yeniden sıralanır
        elenen = sum(1 for m in s["makaleler"]
                     if not puanlama.yz_uygun(ozet_onbellek.get(m["pmid"])))
        if elenen:
            print(f"  {elenen} aday ilgisiz ya da alan dışı bulunup elendi")
        secilen = puanlama.yz_ile_sec(s["makaleler"], ozet_onbellek)

        cikti["alanlar"][kod] = {
            "ad": s["ad"], "taranan": s["taranan"],
            "makaleler": [ekle(m) for m in secilen],
            "turk": ekle(s["turk"]),
            "tez": ekle(tez),
        }
        if s["turk"] and not a.girdi:
            motor.turk_gosterildi_isaretle(kod, s["turk"]["pmid"])
        if tez:
            yoktez.gosterildi_isaretle(kod, tez["tez_no"])

    # 🔥 Bu hafta gündemde: tüm alanlardan en yüksek puanlı 5 makale
    havuz = {}
    for kod, s in cikti["alanlar"].items():
        for m in s["makaleler"]:
            havuz.setdefault(m["pmid"], {**m, "alan": s["ad"]})
    cikti["model"] = gem.son_model
    cikti["ana_model"] = gem.model
    cikti["model_kullanimi"] = gem.kullanim
    cikti["model_notlari"] = gem.notlar
    cikti["gundem"] = sorted(havuz.values(), reverse=True,
                             key=puanlama.sira_anahtari)[:5]

    # Aday arşivi: kurallar değiştiğinde geçmiş haftaları yeniden oynatmak için
    if taranan and not a.girdi and not a.sahte_ozet:
        try:
            yol = arsiv.yaz(bugun.isoformat(),
                            {k: s["kayitlar"] for k, s in taranan.items()}, yz)
            print(f"Aday arşivi: {yol}")
        except Exception as e:
            print(f"Aday arşivi yazılamadı: {e}")

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
