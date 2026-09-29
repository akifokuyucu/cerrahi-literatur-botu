"""
PubMed erişimi: sorgu kurma, PMID arama ve makale kayıtlarını ayrıştırma.

Ücretsiz NCBI E-utilities API'sini kullanır. API anahtarı olmadan saniyede
3, anahtarla 10 istek sınırı vardır; haftalık toplu çalışmada ikisi de yeter.
"""
import re
import time
import xml.etree.ElementTree as ET

import requests

import config

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ARAC_ADI = "cerrahi-literatur-botu"


# ---------------------------------------------------------------------------
# Sorgu kurma
# ---------------------------------------------------------------------------
def _terim(t, etiket="tiab"):
    """Tek terimi PubMed ifadesine çevirir ([tiab] ya da [ti])."""
    # Boşluk/tire içeren terimler öbek olarak aranır (PubMed öbek içinde * destekler)
    return f'"{t}"[{etiket}]' if (" " in t or "-" in t) else f"{t}[{etiket}]"


def _veya(liste, etiket):
    return "(" + " OR ".join(etiket(x) for x in liste) + ")"


def alan_sorgusu(alan_kodu):
    """Bir alt alan için PubMed arama ifadesini döndürür."""
    a = config.ALANLAR[alan_kodu]
    etiket = a.get("anahtar_etiket", "tiab")
    konu = _veya(a["anahtar"], lambda t: _terim(t, etiket))
    if a["cerrahi"]:
        konu = f"({konu} AND {_veya(a['cerrahi'], _terim)})"
    dergiler = a["alan_dergileri"]
    if dergiler:
        dergi_ifadesi = _veya(dergiler, lambda d: '"' + d + '"[ta]')
        konu = f"({konu} OR {dergi_ifadesi})"
    elenen = _veya(config.ELENEN_TIPLER, lambda p: f'"{p}"[pt]')
    brans = _veya(config.DIGER_BRANSLAR, lambda t: _terim(t, "ti"))
    return f"{konu} NOT {elenen} NOT {brans} AND english[la]"


def turk_dergisi_sorgusu(alan_kodu):
    a = config.ALANLAR[alan_kodu]
    konu = _veya(a["anahtar"], _terim)
    elenen = _veya(config.ELENEN_TIPLER, lambda p: f'"{p}"[pt]')
    return f'"{config.TURK_DERGISI}"[ta] AND {konu} NOT {elenen}'


# ---------------------------------------------------------------------------
# API çağrıları
# ---------------------------------------------------------------------------
class PubMed:
    def __init__(self, email=None, api_key=None):
        self.ortak = {"tool": ARAC_ADI}
        if email:
            self.ortak["email"] = email
        if api_key:
            self.ortak["api_key"] = api_key
        self.bekleme = 0.12 if api_key else 0.35

    def _post(self, uc, veri):
        time.sleep(self.bekleme)
        for deneme in range(3):
            r = requests.post(f"{EUTILS}/{uc}", data={**self.ortak, **veri},
                              timeout=60)
            if r.status_code == 429:
                time.sleep(2 * (deneme + 1))
                continue
            r.raise_for_status()
            return r
        r.raise_for_status()

    def ara(self, sorgu, gun, en_fazla=2000):
        """Son `gun` günde PubMed'e eklenen makalelerin PMID'lerini döndürür."""
        r = self._post("esearch.fcgi", {
            "db": "pubmed", "term": sorgu, "retmode": "json",
            "retmax": en_fazla, "datetype": "edat", "reldate": gun,
            "sort": "pub_date",
        })
        return r.json()["esearchresult"]["idlist"]

    def getir(self, pmidler):
        """PMID listesi için ayrıştırılmış makale kayıtları döndürür."""
        kayitlar = []
        for i in range(0, len(pmidler), 200):
            r = self._post("efetch.fcgi", {
                "db": "pubmed", "id": ",".join(pmidler[i:i + 200]),
                "retmode": "xml",
            })
            kayitlar.extend(xml_ayristir(r.text))
        return kayitlar


# ---------------------------------------------------------------------------
# XML ayrıştırma — her makale için sade bir sözlük
# ---------------------------------------------------------------------------
def _metin(el):
    return "".join(el.itertext()).strip() if el is not None else ""


def xml_ayristir(xml_metni):
    kok = ET.fromstring(xml_metni)
    sonuc = []
    for pa in kok.iter("PubmedArticle"):
        mc = pa.find("MedlineCitation")
        art = mc.find("Article")
        ozet_parcalari = []
        for at in art.findall("Abstract/AbstractText"):
            etiket = at.get("Label")
            parca = _metin(at)
            ozet_parcalari.append(f"{etiket}: {parca}" if etiket else parca)
        kimlikler = {i.get("IdType"): i.text
                     for i in pa.findall("PubmedData/ArticleIdList/ArticleId")}
        yil = _metin(art.find("Journal/JournalIssue/PubDate/Year")) or \
            _metin(art.find("Journal/JournalIssue/PubDate/MedlineDate"))[:4]
        sonuc.append({
            "pmid": _metin(mc.find("PMID")),
            "baslik": _metin(art.find("ArticleTitle")),
            "ozet": "\n".join(ozet_parcalari),
            "dergi": _metin(mc.find("MedlineJournalInfo/MedlineTA")) or
                     _metin(art.find("Journal/ISOAbbreviation")),
            "dergi_tam": _metin(art.find("Journal/Title")),
            "yayin_tipleri": [_metin(p) for p in
                              art.findall("PublicationTypeList/PublicationType")],
            "yil": yil,
            "doi": kimlikler.get("doi", ""),
            "pmc": kimlikler.get("pmc", ""),
        })
    return sonuc
