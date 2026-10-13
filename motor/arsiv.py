"""
Aday arşivi: puanlama kurallarını ölçerek ayarlamak için.

Her pazartesi taranan tüm PubMed kayıtları ve yapay zekânın değerlendirmeleri
cikti/aday_arsivi/<tarih>.json.gz'ye yazılır. Kurallar (config.py,
puanlama.py) değiştiğinde geçmiş haftalar PubMed'e ve yapay zekâya gitmeden
yeni kurallarla yeniden sıralanır ve altın listeyle (altin_liste.json)
karşılaştırılır.

  python arsiv.py --cek 2026-10-05        # o güne biten haftayı PubMed'den
                                          # arşivle (yapay zekâ değerlendirmesiz)
  python arsiv.py ../cikti/aday_arsivi/2026-10-05.json.gz   # yeni kurallarla ilk 5'ler
  python arsiv.py ../cikti/aday_arsivi/*.json.gz --ozet     # yalnızca ölçüm özeti
"""
import argparse
import datetime as dt
import glob
import gzip
import json
import os

import config
import puanlama

KLASOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cikti",
                      "aday_arsivi")
ALTIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "altin_liste.json")
# Arşive yazılan PubMed alanları (puanlamanın ihtiyacı olanlar)
KAYIT_ALANLARI = ["pmid", "baslik", "ozet", "dergi", "dergi_tam",
                  "yayin_tipleri", "yil", "doi", "pmc"]
YZ_ALANLARI = ["cerrahi_ilgi", "alan_uyumu", "pratik_etkisi"]


def yaz(tarih, alan_kayitlari, yz=None, klasor=KLASOR):
    """alan_kayitlari: {alan: [PubMed kaydı]}; yz: {pmid: {..., "alan": kod}}."""
    kayitlar, alanlar = {}, {}
    for kod, liste in alan_kayitlari.items():
        alanlar[kod] = [k["pmid"] for k in liste]
        for k in liste:
            kayitlar.setdefault(k["pmid"], {a: k.get(a) for a in KAYIT_ALANLARI})
    yz = {p: {a: o[a] for a in YZ_ALANLARI + ["alan"] if a in o}
          for p, o in (yz or {}).items()}
    os.makedirs(klasor, exist_ok=True)
    yol = os.path.join(klasor, f"{tarih}.json.gz")
    with gzip.open(yol, "wt", encoding="utf-8") as f:
        json.dump({"tarih": tarih, "alanlar": alanlar, "kayitlar": kayitlar,
                   "yz": yz}, f, ensure_ascii=False, separators=(",", ":"))
    return yol


def oku(yol):
    with gzip.open(yol, "rt", encoding="utf-8") as f:
        return json.load(f)


def sec(arsiv, tercih=None):
    """Arşivi güncel kurallarla hazirla.py'deki sırayla işler:
    puanla → alanlara dağıt → ilk ADAY_SAYISI → yapay zekâ süzgeci ve sırası.
    Yapay zekâ değerlendirmesi başka alan için yapılmışsa nötr sayılır."""
    kayitlar = arsiv["kayitlar"]
    tum = {kod: puanlama.ilk_n([kayitlar[p] for p in pmidler], kod,
                               n=0, tercih=tercih)[1]
           for kod, pmidler in arsiv["alanlar"].items() if kod in config.ALANLAR}
    dagitim = puanlama.alanlara_dagit(tum)
    secim = {}
    for kod, liste in dagitim.items():
        yz = {p: o for p, o in arsiv.get("yz", {}).items() if o.get("alan") == kod}
        secim[kod] = puanlama.yz_ile_sec(liste[:config.ADAY_SAYISI], yz)
    return secim


def altin_oku(yol=ALTIN):
    try:
        with open(yol, encoding="utf-8") as f:
            veri = json.load(f)
    except FileNotFoundError:
        return {"olmali": {}, "olmamali": {}}
    return {t: {k: set(v) for k, v in veri.get(t, {}).items() if not k.startswith("_")}
            for t in ("olmali", "olmamali")}


def olc(secim, altin, arsiv):
    """Alan başına: altın listedeki "olmalı"lardan kaçı ilk 5'te, "olmamalı"
    lardan kaçı ilk 5'e girmiş. "olmamalı"da "*" anahtarı tüm alanlar için."""
    mevcut = set(arsiv["kayitlar"])
    hepsi_olmamali = altin["olmamali"].get("*", set())
    sonuc = {}
    for kod, liste in secim.items():
        ilk = {m["pmid"] for m in liste}
        olmali = altin["olmali"].get(kod, set()) & mevcut
        olmamali = (altin["olmamali"].get(kod, set()) | hepsi_olmamali) & mevcut
        sonuc[kod] = {"isabet": len(ilk & olmali), "olmali": len(olmali),
                      "hatali": len(ilk & olmamali)}
    return sonuc


def cek(bitis):
    """Geçmiş bir haftayı PubMed'den çekip arşivler (yapay zekâsız)."""
    import motor
    import pubmed
    pm = pubmed.PubMed(email=os.getenv("NCBI_EMAIL"), api_key=os.getenv("NCBI_API_KEY"))
    alanlar = {}
    for kod in config.ALANLAR:
        s = motor.alan_hazirla(kod, pm, bitis=bitis)
        print(f"  {s['ad']}: {s['taranan']} kayıt")
        alanlar[kod] = s["kayitlar"]
    return yaz(bitis.isoformat(), alanlar)


def _yazdir(secim, altin, olcum):
    for kod, liste in secim.items():
        o = olcum[kod]
        print(f"\n== {config.ALANLAR[kod]['ad']} "
              f"(olmalı {o['isabet']}/{o['olmali']}, olmamalı {o['hatali']}) ==")
        for i, m in enumerate(liste, 1):
            isaret = ("✅" if m["pmid"] in altin["olmali"].get(kod, ()) else
                      "❌" if m["pmid"] in (altin["olmamali"].get(kod, set())
                                           | altin["olmamali"].get("*", set())) else "  ")
            print(f"{isaret}{i}. [{m['toplam']}{m['yz_puani']:+g}] "
                  f"{m['tip']} · {m['dergi']} · {m['pmid']} · {m['baslik'][:80]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("arsivler", nargs="*")
    ap.add_argument("--cek", help="YYYY-AA-GG: o güne biten haftayı arşivle")
    ap.add_argument("--altin", default=ALTIN)
    ap.add_argument("--ozet", action="store_true", help="yalnızca ölçüm özeti")
    a = ap.parse_args()

    if a.cek:
        print("Arşiv:", cek(dt.date.fromisoformat(a.cek)))
    altin = altin_oku(a.altin)
    yollar = [y for desen in a.arsivler for y in sorted(glob.glob(desen))]
    for yol in yollar:
        arsiv = oku(yol)
        secim = sec(arsiv)
        olcum = olc(secim, altin, arsiv)
        if not a.ozet:
            _yazdir(secim, altin, olcum)
        top = {k: sum(o[k] for o in olcum.values()) for k in ("isabet", "olmali", "hatali")}
        print(f"\n{arsiv['tarih']}: olmalı {top['isabet']}/{top['olmali']} ilk 5'te, "
              f"{top['hatali']} olmamalı ilk 5'e girdi")
