"""
Puanlama: her makaleye dergi puanı + çalışma tipi puanı verir.
"""
import re

import config

KILAVUZ_PT = {"Practice Guideline", "Guideline",
              "Consensus Development Conference",
              "Consensus Development Conference, NIH"}
META_PT = {"Meta-Analysis", "Systematic Review"}
RCT_PT = {"Randomized Controlled Trial"}
KLINIK_PT = {"Clinical Trial", "Clinical Trial, Phase II",
             "Clinical Trial, Phase III", "Clinical Trial, Phase IV",
             "Pragmatic Clinical Trial", "Equivalence Trial"}


def _norm(ad):
    return re.sub(r"[^a-z0-9]", "", ad.lower())


def dergi_puani(dergi, alan_kodu):
    """(puan, etiket) döndürür."""
    n = _norm(dergi)
    alan = config.ALANLAR[alan_kodu]
    adaylar = [
        (config.DERGI_PUANI["kademe1"], "Kademe 1", alan["ust"]),
        (config.DERGI_PUANI["kademe1"], "Kademe 1", config.ORTAK_DERGILER["kademe1"]),
        (config.DERGI_PUANI["kademe2"], "Kademe 2", config.ORTAK_DERGILER["kademe2"]),
        (config.DERGI_PUANI["kademe3"], "Kademe 3", config.ORTAK_DERGILER["kademe3"]),
        (config.DERGI_PUANI["kademe3"], "Kademe 3", alan["alan_dergileri"]),
    ]
    for puan, etiket, liste in adaylar:
        if n in {_norm(d) for d in liste}:
            return puan, etiket
    return config.DERGI_PUANI["listede_yok"], "Listede yok"


def calisma_tipi(kayit):
    """Makalenin çalışma tipini belirler. Elenecekse None döndürür."""
    pt = set(kayit["yayin_tipleri"])
    baslik = kayit["baslik"].lower()
    ozet = kayit["ozet"].lower()

    if pt & set(config.ELENEN_TIPLER) or "case report" in baslik:
        return None
    # Özeti olmayan kayıtlar (yorum, görsel özet, video olgu, bildiri) elenir
    if not ozet.strip():
        return None
    if re.search(r"\b(study|trial) protocol\b|\bprotocol for\b", baslik):
        return None

    if pt & KILAVUZ_PT or re.search(r"guideline|recommendations?\b", baslik):
        return "kilavuz"
    if pt & META_PT or re.search(
            r"meta-?analys|systematic review|umbrella review", baslik):
        return "meta_analiz"
    # Öneri üretmeyen Delphi/konsensus çalışmaları uzman görüşü sayılır
    if re.search(r"consensus|delphi", baslik):
        return "prospektif"
    if "retrospective" in baslik:
        return "diger"
    # Hayvan/deneysel çalışmalar klinik kanıt sayılmaz (randomize olsa bile)
    if re.search(r"\b(rats?|mice|murine|porcine|pigs?|rabbits?|swine|"
                 r"in vitro|animal model)\b", baslik + " " + ozet[:1500]):
        return "diger"
    if pt & RCT_PT or re.search(r"randomi[sz]ed\b.*\btrial", baslik) or \
            re.search(r"(?<!not )randomly (assigned|allocated)|"
                      r"(?<!not )(were|was) randomi[sz]ed", ozet):
        return "rct"
    geriye = "retrospective" in ozet[:1500]
    if not geriye and (pt & KLINIK_PT or re.search(
            r"\bprospective\b", baslik + " " + ozet[:1500])):
        return "prospektif"
    return "diger"


def _cok_merkezli(kayit):
    metin = (kayit["baslik"] + " " + kayit["ozet"]).lower()
    return "Multicenter Study" in kayit["yayin_tipleri"] or bool(
        re.search(r"multi-?cent(er|re)|nationwide|multinational|international",
                  metin))


def _orneklem(kayit):
    """Özetteki en büyük hasta sayısını kabaca yakalar (eşitlik bozucu)."""
    sayilar = re.findall(
        r"(\d[\d,]{1,9})\s+(?:patients|participants|women|men|cases|"
        r"individuals|subjects|procedures|adults)", kayit["ozet"])
    return max((int(s.replace(",", "")) for s in sayilar), default=0)


def puanla(kayit, alan_kodu):
    tip = calisma_tipi(kayit)
    if tip is None:
        return None
    d_puan, d_etiket = dergi_puani(kayit["dergi"], alan_kodu)
    t_puan = config.TIP_PUANI[tip]
    return {
        **kayit,
        "tip": tip,
        "tip_etiketi": config.TIP_ETIKETI[tip],
        "dergi_puani": d_puan,
        "dergi_kademesi": d_etiket,
        "tip_puani": t_puan,
        "toplam": d_puan + t_puan,
        "cok_merkezli": _cok_merkezli(kayit),
        "orneklem": _orneklem(kayit),
    }


def ilk_n(kayitlar, alan_kodu, n=config.ALAN_BASINA):
    """Puanlar, Türk dergisini ana listeden ayırır, en iyi n'i döndürür."""
    turk = {_norm(d) for d in config.TUM_TURK_DERGILERI}
    puanli = []
    gorulen = set()
    for k in kayitlar:
        if k["pmid"] in gorulen or _norm(k["dergi"]) in turk:
            continue
        gorulen.add(k["pmid"])
        p = puanla(k, alan_kodu)
        if p:
            puanli.append(p)
    puanli.sort(key=lambda p: (p["toplam"], p["cok_merkezli"], p["orneklem"]),
                reverse=True)
    return puanli[:n], puanli
