"""
SJR (SCImago Journal Rank) çeyrekliklerini motor/veri/sjr.json'a dönüştürür.

Elle kademelendirilmemiş dergiler (config.ORTAK_DERGILER ve alan listeleri
dışındakiler) puanını bu tablodan alır (config.SJR_PUANI). Eşleştirme ISSN
iledir. Çeyreklik, derginin "Surgery" kategorisi varsa oradaki, yoksa en iyi
kategorisindeki değerdir. Genel cerrahi dergileri (Surgery kategorisinde olup
başka cerrahi branşa ait olmayanlar) "c" eki alır (ör. "Q1c").

Yılda bir (SJR her yıl Mayıs civarı güncellenir):
  1. Tarayıcıda https://www.scimagojr.com/journalrank.php → "Download data"
     (site bot koruması kullandığı için betikle indirilemiyor)
  2. python sjr.py "C:/Users/.../Downloads/scimagojr 2025.csv"
"""
import csv
import json
import os
import re
import sys

HEDEF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "veri", "sjr.json")


# SJR'nin "Surgery" kategorisi tüm cerrahi branşları kapsar. Bu kategorilerden
# biri de varsa ya da dergi adı başka bir branşı gösteriyorsa dergi genel
# cerrahi dergisi sayılmaz (çeyrekliği "c" eki almaz).
DIGER_KATEGORILER = [
    "Orthopedics and Sports Medicine", "Otorhinolaryngology", "Urology",
    "Neurology (clinical)", "Ophthalmology", "Obstetrics and Gynecology",
    "Cardiology and Cardiovascular Medicine", "Pulmonary and Respiratory Medicine",
    "Oral Surgery", "Pediatrics, Perinatology and Child Health",
]
DIGER_DERGI_ADI = re.compile(
    r"plastic|aesthetic|microsurg|hand |craniofac|maxillofac|oral |neurosurg|"
    r"spine|spinal|orthop|bone|joint|thorac|cardi|vascular|urolog|otolaryng|"
    r"ophthalm|pediatric|paediatric", re.I)


def _ceyreklik(satir):
    """(çeyreklik, genel_cerrahi_dergisi_mi); çeyreklik yoksa (None, False)."""
    kategoriler = satir.get("Categories", "")
    kategori = re.search(r"(?:^|;\s*)Surgery \((Q[1-4])\)", kategoriler)
    if kategori:
        diger = any(f"{k} (Q" in kategoriler for k in DIGER_KATEGORILER) or \
            DIGER_DERGI_ADI.search(satir.get("Title", ""))
        return kategori.group(1), not diger
    q = (satir.get("SJR Best Quartile") or "").strip()
    return (q, False) if re.fullmatch(r"Q[1-4]", q) else (None, False)


def donustur(csv_yolu):
    with open(csv_yolu, encoding="utf-8-sig", newline="") as f:
        okuyucu = csv.DictReader(f, delimiter=";")
        yil = next((m.group(1) for b in okuyucu.fieldnames
                    for m in [re.search(r"\((\d{4})\)", b)] if m), "")
        dergiler = {}
        for s in okuyucu:
            if s.get("Type", "").strip().lower() != "journal":
                continue
            if "Medicine" not in s.get("Areas", ""):
                continue
            q, cerrahi = _ceyreklik(s)
            if not q:
                continue
            for issn in re.split(r"[,\s]+", s.get("Issn", "")):
                issn = re.sub(r"[^0-9X]", "", issn.upper())
                if len(issn) == 8:
                    # "Q1c": Surgery kategorisinde Q1; "Q1": başka kategoride
                    dergiler[issn] = q + ("c" if cerrahi else "")
    return {"kaynak": "SCImago Journal & Country Rank (scimagojr.com)",
            "yil": yil, "dergiler": dict(sorted(dergiler.items()))}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    veri = donustur(sys.argv[1])
    os.makedirs(os.path.dirname(HEDEF), exist_ok=True)
    with open(HEDEF, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, separators=(",", ":"))
    sayac = {}
    for q in veri["dergiler"].values():
        sayac[q] = sayac.get(q, 0) + 1
    print(f"SJR {veri['yil']}: {len(veri['dergiler'])} ISSN → {HEDEF}")
    print("  " + ", ".join(f"{q}: {n}" for q, n in sorted(sayac.items())))
