"""
Haftalık hazırlık motoru.

Kullanım:
  python motor.py --alan kolorektal                 # PubMed'den canlı çek
  python motor.py --alan kolorektal --girdi x.xml   # kayıtlı XML ile test
  python motor.py --hepsi                           # 14 alanın hepsi
"""
import argparse
import datetime as dt
import json
import os

import config
import pubmed
import puanlama

VERI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cikti")
TURK_GOSTERILEN = os.path.join(VERI, "turk_gosterilen.json")


def _oku_json(yol, varsayilan):
    try:
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return varsayilan


def turk_makalesi_sec(kayitlar, alan_kodu):
    """Bu alan için henüz gösterilmemiş en yeni Turk J Surg makalesi."""
    gosterilen = _oku_json(TURK_GOSTERILEN, {})
    daha_once = set(gosterilen.get(alan_kodu, []))
    for k in kayitlar:  # PubMed en yeniden eskiye sıralı döner
        if k["pmid"] not in daha_once and puanlama.calisma_tipi(k):
            return {**k, "tip_etiketi":
                    config.TIP_ETIKETI[puanlama.calisma_tipi(k)]}
    return None


def turk_gosterildi_isaretle(alan_kodu, pmid):
    gosterilen = _oku_json(TURK_GOSTERILEN, {})
    gosterilen.setdefault(alan_kodu, []).append(pmid)
    os.makedirs(VERI, exist_ok=True)
    with open(TURK_GOSTERILEN, "w", encoding="utf-8") as f:
        json.dump(gosterilen, f, ensure_ascii=False, indent=1)


def alan_hazirla(alan_kodu, pm=None, girdi_xml=None, turk_xml=None):
    if girdi_xml:
        with open(girdi_xml, encoding="utf-8") as f:
            kayitlar = pubmed.xml_ayristir(f.read())
    else:
        pmidler = pm.ara(pubmed.alan_sorgusu(alan_kodu), config.PENCERE_GUN)
        kayitlar = pm.getir(pmidler)

    secilen, tum_puanli = puanlama.ilk_n(kayitlar, alan_kodu)

    turk = None
    if turk_xml:
        with open(turk_xml, encoding="utf-8") as f:
            turk = turk_makalesi_sec(pubmed.xml_ayristir(f.read()), alan_kodu)
    elif pm:
        ids = pm.ara(pubmed.turk_dergisi_sorgusu(alan_kodu),
                     config.TURK_DERGISI_GERIYE_GUN, en_fazla=20)
        turk = turk_makalesi_sec(pm.getir(ids), alan_kodu) if ids else None

    return {
        "alan": alan_kodu,
        "ad": config.ALANLAR[alan_kodu]["ad"],
        "hazirlanma": dt.date.today().isoformat(),
        "taranan": len(kayitlar),
        "puanlanan": len(tum_puanli),
        "makaleler": secilen,
        "turk": turk,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--alan")
    ap.add_argument("--hepsi", action="store_true")
    ap.add_argument("--girdi")
    ap.add_argument("--turk-girdi")
    ap.add_argument("--cikti", default=os.path.join(VERI, "hafta.json"))
    a = ap.parse_args()

    pm = None if a.girdi else pubmed.PubMed(
        email=os.getenv("NCBI_EMAIL"), api_key=os.getenv("NCBI_API_KEY"))
    alanlar = list(config.ALANLAR) if a.hepsi else [a.alan]
    sonuc = {k: alan_hazirla(k, pm, a.girdi, a.turk_girdi) for k in alanlar}
    with open(a.cikti, "w", encoding="utf-8") as f:
        json.dump(sonuc, f, ensure_ascii=False, indent=1)
    for k, s in sonuc.items():
        print(f"\n== {s['ad']}: {s['taranan']} tarandı, "
              f"{s['puanlanan']} puanlandı ==")
        for i, m in enumerate(s["makaleler"], 1):
            print(f"{i}. [{m['toplam']}={m['dergi_puani']}+{m['tip_puani']}] "
                  f"{m['tip_etiketi']} · {m['dergi']} · PMID {m['pmid']}\n"
                  f"   {m['baslik']}")
        if s["turk"]:
            print(f"TR: {s['turk']['dergi']} · PMID {s['turk']['pmid']} · "
                  f"{s['turk']['baslik']}")
