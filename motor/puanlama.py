"""
Puanlama: her makaleye dergi puanı + çalışma tipi puanı verir.
"""
import re

import config

KILAVUZ_PT = {"Practice Guideline", "Guideline",
              "Consensus Development Conference",
              "Consensus Development Conference, NIH"}
# Başlıkta kılavuz/konsensus olduğunu gösteren kalıplar. Yalnızca "guideline"
# kelimesi yetmez: "Guideline-Directed Testing", "adherence to guidelines"
# gibi başlıklar kılavuz değildir.
KILAVUZ_BASLIK = re.compile(
    r"\b(?:practice|clinical|consensus|evidence-based|international|national|"
    r"joint|updated?|society|management|wses|esmo|nccn|asco|sages|eaes|"
    r"ascrs|escp|ehs|ahs) guidelines?\b"
    r"|\bguidelines? (?:for|on|of the|from)\b"
    r"|\bthe [\w-]+ guidelines?\b"
    r"|\bconsensus (?:statement|guideline|recommendations?|conference|document|report)"
    r"|\bposition (?:statement|paper)\b"
    r"|\brecommendations (?:for|from|of|on|by)\b"
    r"|\bclinical practice update\b"
    r"|:\s*(?:an? )?(?:\w+ )?(?:guideline|consensus)\b")
# Kılavuza uyumu/uygulanmasını inceleyen çalışmalar kılavuz değildir
KILAVUZ_UYUMU = re.compile(
    r"\b(?:adherence|complian\w*|concordan\w*|implementation|uptake|"
    r"awareness|knowledge|deviation|non-?adherence) (?:to|with|of|from) "
    r"(?:the )?(?:[\w-]+ ){0,3}guidelines?\b"
    r"|\b(?:impact|effects?|evaluation|introduction) of (?:an? |the )?"
    r"(?:[\w-]+ ){0,4}guidelines?\b")
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
        (config.DERGI_PUANI["dusuk"], "Düşük", config.DUSUK_DERGILER),
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
    if re.search(r"\b(study|trial) protocol\b|\bprotocol (for|of)\b", baslik):
        return None
    if config.COCUK_ELE and yalniz_cocuk(kayit):
        return None

    if pt & KILAVUZ_PT or (KILAVUZ_BASLIK.search(baslik)
                           and not KILAVUZ_UYUMU.search(baslik)):
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
    mesh = set(kayit.get("mesh") or ())
    if re.search(r"\b(rats?|mice|murine|porcine|pigs?|rabbits?|swine|"
                 r"in vitro|animal model)\b", baslik + " " + ozet[:1500]) or \
            ("Animals" in mesh and "Humans" not in mesh):
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


COCUK_MESH = {"Infant", "Infant, Newborn", "Child", "Child, Preschool",
              "Adolescent"}
YETISKIN_MESH = {"Adult", "Young Adult", "Middle Aged", "Aged",
                 "Aged, 80 and over"}
# "Child-Pugh" / "Child-Turcotte-Pugh" karaciğer sınıflamasıdır, çocuk değil
COCUK_BASLIK = re.compile(r"\b(?:pediatric|paediatric|children|child(?![-–‐ ]"
                          r"(?:pugh|turcotte))|childhood|infants?|neonat\w*|"
                          r"newborns?)\b", re.I)


def yalniz_cocuk(kayit):
    """Çalışma yalnızca çocuk hastalarda mı? MeSH yaş etiketleri varsa onlar
    belirler; yoksa başlık ("adult" geçmeden çocuk terimi) ya da dergi."""
    mesh = set(kayit.get("mesh") or ())
    if mesh & (COCUK_MESH | YETISKIN_MESH):
        return bool(mesh & COCUK_MESH) and not mesh & YETISKIN_MESH
    if _norm(kayit["dergi"]) in {_norm(d) for d in config.COCUK_DERGILERI}:
        return True
    return bool(COCUK_BASLIK.search(kayit["baslik"])) and \
        not re.search(r"\badults?\b", kayit["baslik"], re.I)


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


_ALAN_DESENLERI = {}


def _alan_desenleri(alan_kodu, tur="anahtar"):
    """Alanın terimleri → kelime sınırlı ifadeler ("hernia*" → "hernia" ile başlayan kelime)."""
    if (alan_kodu, tur) not in _ALAN_DESENLERI:
        _ALAN_DESENLERI[alan_kodu, tur] = [
            re.compile(r"\b" + re.escape(t).replace(r"\*", r"\w*") + r"\b", re.I)
            for t in config.ALANLAR[alan_kodu].get(tur, [])]
    return _ALAN_DESENLERI[alan_kodu, tur]


def alan_haric(kayit, alan_kodu):
    """Alanın "haric" terimlerinden biri başlık ya da özette geçiyor mu?"""
    metin = kayit["baslik"] + " " + kayit["ozet"]
    return any(d.search(metin) for d in _alan_desenleri(alan_kodu, "haric"))


def alan_uyumu(kayit, alan_kodu):
    """Makalenin bu alana ne kadar ait olduğu (kural tabanlı, kaba).
    Başlıkta geçen her terim 3, MeSH başlıklarında geçen 2, özette geçen 1
    puan; alanın kendi dergisi 4, alanın üst dergisi ya da geniş kapsamlı
    dergi 1 puan."""
    desenler = _alan_desenleri(alan_kodu)
    mesh = " | ".join(kayit.get("mesh") or ())
    puan = sum(3 for d in desenler if d.search(kayit["baslik"])) + \
        sum(2 for d in desenler if mesh and d.search(mesh)) + \
        sum(1 for d in desenler if d.search(kayit["ozet"]))
    a = config.ALANLAR[alan_kodu]
    n = _norm(kayit["dergi"])
    if n in {_norm(d) for d in a["alan_dergileri"]}:
        genis = n in {_norm(d) for d in config.GENIS_DERGILER}
        puan += 1 if genis else 4
    elif n in {_norm(d) for d in a["ust"]}:
        puan += 1
    return puan


def alanlara_dagit(listeler):
    """{alan: [puanlı makale]} → her makale yalnızca en uygun alanında kalır.
    Eşitlikte config.ALANLAR'da önce gelen alan kazanır."""
    en_iyi = {}
    for kod, liste in listeler.items():
        for m in liste:
            u = alan_uyumu(m, kod)
            if m["pmid"] not in en_iyi or u > en_iyi[m["pmid"]][0]:
                en_iyi[m["pmid"]] = (u, kod)
    return {kod: [m for m in liste if en_iyi[m["pmid"]][1] == kod]
            for kod, liste in listeler.items()}


def _yz_degeri(o, ad):
    """Yapay zekânın 0–2 değerlendirmesi; yoksa ya da bozuksa 1 (nötr)."""
    try:
        return max(0, min(2, int(o.get(ad, 1))))
    except (TypeError, ValueError):
        return 1


def yz_uygun(o):
    """Yapay zekâ "cerrahiyle ilgisiz" ya da "bu alanın konusu değil" dediyse
    makale listeye girmez. Değerlendirme yoksa (özet üretilemediyse) girer."""
    o = o or {}
    return _yz_degeri(o, "cerrahi_ilgi") != 0 and _yz_degeri(o, "alan_uyumu") != 0


def yz_puani(o):
    """Alan uyumu ve pratiğe etkiden sıralama katkısı (nötr 0, en fazla ±2)."""
    o = o or {}
    return config.YZ_AGIRLIK * (_yz_degeri(o, "alan_uyumu") - 1
                                + _yz_degeri(o, "pratik_etkisi") - 1)


def sira_anahtari(p):
    # Eşitlikte: çok merkezli, sonra kayıtlı (NCT) deneme, sonra büyük örneklem
    return (p["toplam"] + (p.get("kisisel") or 0) + (p.get("yz_puani") or 0),
            p["cok_merkezli"], bool(p.get("nct")), p["orneklem"])


def yz_ile_sec(adaylar, yz, n=config.ALAN_BASINA):
    """Yapay zekânın elediği adayları çıkarır, kalanları yapay zekâ puanıyla
    birlikte yeniden sıralar ve ilk n'i döndürür. yz: {pmid: değerlendirme}."""
    uygun = [{**m, "yz_puani": yz_puani(yz.get(m["pmid"]))}
             for m in adaylar if yz_uygun(yz.get(m["pmid"]))]
    uygun.sort(key=sira_anahtari, reverse=True)
    return uygun[:n]


def puanla(kayit, alan_kodu):
    tip = calisma_tipi(kayit)
    if tip is None:
        return None
    d_puan, d_etiket = dergi_puani(kayit["dergi"], alan_kodu)
    t_puan = config.TIP_PUANI[tip]
    e_puan = config.EDITORYAL_PUANI if kayit.get("editoryal") else 0
    return {
        **kayit,
        "tip": tip,
        "tip_etiketi": config.TIP_ETIKETI[tip],
        "dergi_puani": d_puan,
        "dergi_kademesi": d_etiket,
        "tip_puani": t_puan,
        "editoryal_puani": e_puan,
        "toplam": d_puan + t_puan + e_puan,
        "cok_merkezli": _cok_merkezli(kayit),
        "orneklem": _orneklem(kayit),
    }


def tercihleri_hesapla(oylar):
    """Bottaki oylardan dergi ve çalışma tipi için kişisel katkı hesaplar."""
    net = {"dergi": {}, "tip": {}}
    for o in oylar:
        yon = 1 if o.get("oy") else -1
        if o.get("dergi"):
            d = _norm(o["dergi"])
            net["dergi"][d] = net["dergi"].get(d, 0) + yon
        if o.get("tip"):
            net["tip"][o["tip"]] = net["tip"].get(o["tip"], 0) + yon
    sinir = lambda x: max(-config.KISISEL_SINIR, min(config.KISISEL_SINIR, x))
    return {tur: {k: sinir(v * config.KISISEL_ADIM) for k, v in d.items() if v}
            for tur, d in net.items()}


def kisisel_puan(p, tercih):
    if not tercih:
        return 0.0
    return (tercih["dergi"].get(_norm(p["dergi"]), 0)
            + tercih["tip"].get(p["tip"], 0))


def ilk_n(kayitlar, alan_kodu, n=config.ALAN_BASINA, tercih=None):
    """Puanlar, Türk dergisini ana listeden ayırır, en iyi n'i döndürür."""
    turk = {_norm(d) for d in config.TUM_TURK_DERGILERI}
    puanli = []
    gorulen = set()
    for k in kayitlar:
        if k["pmid"] in gorulen or _norm(k["dergi"]) in turk or \
                alan_haric(k, alan_kodu):
            continue
        gorulen.add(k["pmid"])
        p = puanla(k, alan_kodu)
        if p:
            p["kisisel"] = kisisel_puan(p, tercih)
            puanli.append(p)
    puanli.sort(key=sira_anahtari, reverse=True)
    return puanli[:n], puanli
