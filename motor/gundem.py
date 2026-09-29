"""
📰 Gündem: haftalık cerrahi haberleri ve gelişmeler (her perşembe).

Dört bölüm: kılavuz ve kongre duyuruları, teknoloji (FDA/CE onayları,
robotik, yapay zekâ), yerli gelişmeler ve ClinicalTrials.gov'a o hafta
kaydedilen cerrahi RCT'ler. Kaynaklar config.GUNDEM_KAYNAKLARI'nda.
Adaylar Gemini'nin genel cerrahi süzgecinden geçer, Türkçe başlık ve kısa
özet alır, sonuç cikti/gundem.json'a yazılır.

GitHub Actions her perşembe bunu çalıştırır. Elle deneme:
  python gundem.py --sahte-ozet --bildirim-yok   # Gemini'siz deneme
  python gundem.py --tohum                       # yalnızca dernek sayfalarının
                                                 # mevcut bağlantılarını kaydet
"""
import argparse
import datetime as dt
import email.utils
import hashlib
import html
import itertools
import json
import os
import re
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from urllib.parse import quote, urljoin

import requests

import config
import ozetleyici
from hazirla import hafta_etiketi, telegram_bildir

CIKTI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cikti")
GORULEN = os.path.join(CIKTI, "gundem_gorulen.json")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36"}
# Görülen bağlantı listeleri bu boyutta tutulur
GORULEN_SINIRI = 3000


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
def _oku_json(yol, varsayilan):
    try:
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return varsayilan


def _sade(metin, sinir=None):
    """HTML etiketlerini ve fazla boşlukları atar."""
    metin = html.unescape(re.sub(r"<[^>]+>", " ", metin or ""))
    metin = " ".join(metin.split())
    return metin[:sinir] if sinir else metin


def _kimlik(url):
    return hashlib.sha1(url.encode()).hexdigest()[:10]


def _getir(url, **kw):
    for deneme in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=40, **kw)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"{r.status_code}")
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            if deneme == 2:
                raise
            print(f"  {url[:60]} hata ({e}), yeniden deneniyor...")
            time.sleep(5 * (deneme + 1))


def _aday(bolum, kaynak, baslik, url, tarih="", metin="", **ek):
    return {"id": _kimlik(url), "bolum": bolum, "kaynak": kaynak,
            "baslik": _sade(baslik, 300), "url": url, "tarih": tarih,
            "metin": _sade(metin, 700), **ek}


def _tarih(rfc822):
    try:
        return email.utils.parsedate_to_datetime(rfc822).date().isoformat()
    except (TypeError, ValueError):
        return ""


# ---------------------------------------------------------------------------
# Kaynak türleri
# ---------------------------------------------------------------------------
def rss_oku(k, url=None, kaynak_ad=None):
    """RSS 2.0 akışından son GUNDEM_PENCERE_GUN günün kayıtları."""
    kok = ET.fromstring(_getir(url or k["url"]).content)
    sinir = dt.date.today() - dt.timedelta(days=config.GUNDEM_PENCERE_GUN)
    sonuc = []
    for it in kok.iter("item"):
        tarih = _tarih(it.findtext("pubDate"))
        if tarih and tarih < sinir.isoformat():
            continue
        baslik = it.findtext("title") or ""
        kaynak = kaynak_ad or k["ad"]
        yayinci = it.findtext("source")
        if yayinci:  # Google Haberler: "Başlık - Yayıncı"
            kaynak = yayinci.strip()
            baslik = re.sub(r"\s+-\s+[^-]+$", "", baslik)
        sonuc.append(_aday(k["bolum"], kaynak, baslik, it.findtext("link") or "",
                           tarih, it.findtext("description") or ""))
    return sonuc


def haber_oku(k):
    """Google Haberler araması (RSS)."""
    dil = k.get("dil", "en")
    bolge = {"en": "hl=en-US&gl=US&ceid=US:en", "tr": "hl=tr&gl=TR&ceid=TR:tr"}[dil]
    sorgu = quote(f"{k['sorgu']} when:{config.GUNDEM_PENCERE_GUN}d")
    url = f"https://news.google.com/rss/search?q={sorgu}&{bolge}"
    return rss_oku(k, url, kaynak_ad="Google Haberler")


def sayfa_baglantilari(k):
    """Haber sayfasındaki desene uyan bağlantılar: {url: başlık}."""
    metin = _getir(k["url"]).text
    bag = {}
    for href, yazi in re.findall(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', metin, re.S | re.I):
        url = urljoin(k["url"], html.unescape(href))
        yazi = _sade(yazi)
        if len(yazi) >= 15 and re.search(k["desen"], url) and url not in bag:
            bag[url] = yazi
    return bag


def sayfa_aciklamasi(url):
    """Bağlantının kısa açıklaması (meta description ya da ilk paragraflar)."""
    try:
        t = _getir(url).text
    except requests.RequestException:
        return ""
    m = re.search(r'<meta[^>]+(?:property="og:description"|name="description")'
                  r'[^>]+content="([^"]+)"', t, re.I)
    if m and len(m.group(1)) > 40:
        return m.group(1)
    paragraflar = [_sade(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", t, re.S | re.I)]
    return " ".join(p for p in paragraflar if len(p) > 60)[:700]


def sayfa_oku(k, gorulen):
    """Önceki haftada görülmemiş bağlantılar. Kaynak ilk kez taranıyorsa
    bağlantılar yalnızca kaydedilir (menü/eski haber gürültüsü gelmesin)."""
    bag = sayfa_baglantilari(k)
    kayitli = gorulen["sayfa"].get(k["ad"])
    gorulen["sayfa"][k["ad"]] = (list(bag) + [u for u in (kayitli or []) if u not in bag]
                                 )[:GORULEN_SINIRI]
    if kayitli is None:
        print(f"  {k['ad']}: ilk tarama, {len(bag)} bağlantı kaydedildi")
        return []
    yeni = [u for u in bag if u not in set(kayitli)][:10]
    return [_aday(k["bolum"], k["ad"], bag[u], u, "", sayfa_aciklamasi(u)) for u in yeni]


def openfda_oku(k):
    """FDA 510(k) kararları. openFDA birkaç hafta geriden geldiği için pencere
    geniş tutulur; tekrarları görülenler listesi önler."""
    bugun = dt.date.today()
    bas = bugun - dt.timedelta(days=config.GUNDEM_PENCERE_GUN + 21)
    kurullar = "+OR+".join(k["kurullar"])
    url = ("https://api.fda.gov/device/510k.json?search="
           f"advisory_committee:({kurullar})+AND+decision_date:"
           f"[{bas:%Y%m%d}+TO+{bugun:%Y%m%d}]&limit=100")
    r = requests.get(url, headers=UA, timeout=40)
    if r.status_code == 404:  # openFDA sonuç yoksa 404 döner
        return []
    r.raise_for_status()
    sonuc = []
    for s in r.json().get("results", []):
        kno = s.get("k_number", "")
        sonuc.append(_aday(
            k["bolum"], "FDA 510(k)", s.get("device_name", ""),
            f"https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID={kno}",
            dt.datetime.strptime(s["decision_date"], "%Y-%m-%d").date().isoformat()
            if s.get("decision_date") else "",
            f"Başvuran: {s.get('applicant', '')} ({s.get('country_code', '')}). "
            f"Kurul: {s.get('advisory_committee_description', '')}. "
            f"Karar: {s.get('decision_description', '')}. 510(k) no: {kno}."))
    return sonuc


def rct_oku():
    """ClinicalTrials.gov'a son haftada kaydedilen cerrahi RCT'ler."""
    bas = dt.date.today() - dt.timedelta(days=config.GUNDEM_PENCERE_GUN)
    terimler = " OR ".join(f'"{t}"' for t in config.RCT_TERIMLERI)
    sorgu = (f"AREA[StudyFirstPostDate]RANGE[{bas.isoformat()},MAX] AND "
             "AREA[StudyType]INTERVENTIONAL AND AREA[DesignAllocation]RANDOMIZED "
             f"AND ({terimler})")
    r = _getir("https://clinicaltrials.gov/api/v2/studies", params={
        "query.term": sorgu, "pageSize": 100,
        "fields": "NCTId,BriefTitle,BriefSummary,Condition,InterventionName,"
                  "EnrollmentCount,LeadSponsorName,LocationCountry,Phase,"
                  "StudyFirstPostDate",
    })
    sonuc = []
    for s in r.json().get("studies", []):
        p = s["protocolSection"]
        nct = p["identificationModule"]["nctId"]
        n = (p.get("designModule", {}).get("enrollmentInfo") or {}).get("count")
        ulkeler = sorted({l.get("country") for l in
                          p.get("contactsLocationsModule", {}).get("locations", [])
                          if l.get("country")})
        sponsor = p.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name", "")
        girisim = [i.get("name") for i in
                   p.get("armsInterventionsModule", {}).get("interventions", [])]
        sonuc.append(_aday(
            "rct", "ClinicalTrials.gov", p["identificationModule"]["briefTitle"],
            f"https://clinicaltrials.gov/study/{nct}",
            p["statusModule"].get("studyFirstPostDateStruct", {}).get("date", ""),
            f"Hastalık: {', '.join(p.get('conditionsModule', {}).get('conditions', []))}. "
            f"Girişimler: {', '.join(girisim)}. "
            f"Özet: {p.get('descriptionModule', {}).get('briefSummary', '')}",
            nct=nct, n=n, ulke=", ".join(ulkeler[:3]), sponsor=sponsor))
    return sonuc


# ---------------------------------------------------------------------------
# Gemini süzgeci
# ---------------------------------------------------------------------------
ORTAK_TALIMAT = """Sen genel cerrahi alanında deneyimli bir akademisyensin ve
genel cerrahi asistanları için haftalık bir "gündem" bülteni hazırlıyorsun.
Aşağıda bu haftanın aday haberleri var. Her aday için:

1. "ilgi": Bir genel cerrah ya da asistan için değeri:
   2 = doğrudan ilgili ve haber değeri yüksek
   1 = ilgili ama ikincil
   0 = alakasız, tanıtım/reklam, tekrar ya da başka branşın konusu
2. "baslik_tr": Kısa, doğal Türkçe başlık (en fazla 14 kelime).
3. "ozet": Ne olduğunu anlatan 1-2 Türkçe cümle (en fazla 250 karakter).

Kurallar:
- YALNIZCA verilen metindeki bilgiyi kullan; tarih, sayı veya ayrıntı uydurma.
- Tıbbi terimleri, cihaz ve kurum adlarını özgün hâliyle bırak.
- Aynı olayı anlatan birden çok aday varsa yalnızca en bilgilendirici olanına
  ilgi ver, diğerlerine 0 ver.
- Yorum ve övgü ("çığır açan", "önemli") ekleme.
- Her aday için verilen id değerini aynen geri döndür.

Bu bölümün ölçütü:
"""

BOLUM_TALIMATI = {
    "kilavuz": """Cerrahi derneklerinin (WSES, ESCP, ASCRS, EAES, SAGES, ACS vb.)
duyuruları. 2: yeni ya da güncellenen kılavuz, konsensus, pozisyon bildirisi;
kongre tarihleri, bildiri/burs/kurs başvuru duyuruları. 1: dernek eğitim
programları, önemli kurumsal kararlar. 0: üye tanıtımları, podcast bölümleri,
içeriği olmayan başkan mesajları, kitap/ürün tanıtımları, dernek dışı
hastane haberleri.""",
    "teknoloji": """Cerrahi teknoloji. 2: genel cerrahide kullanılan cihaz ya da
platform için FDA onayı/510(k)/De Novo ve CE işareti, yeni robotik cerrahi
sistemleri, cerrahide yapay zekâ uygulamalarına dair somut gelişmeler (onay,
klinik çalışma, düzenleyici kılavuz). 1: genel cerrahiyi dolaylı ilgilendiren
teknoloji gelişmeleri. 0: estetik/dermatoloji, ortopedi, diş, göz, üroloji ya
da jinekolojiye özgü cihazlar; hastanelerin "robotik ameliyat sayısı" ve
tanıtım haberleri; borsa ve yatırımcı haberleri; basit sarf malzemesi
510(k)'leri (dikiş, gazlı bez, eldiven vb.).""",
    "yerli": """Türkiye'deki gelişmeler. 2: Türk Cerrahi Derneği duyuruları,
ulusal cerrahi kongreleri, TTB'nin cerrahları ilgilendiren açıklamaları,
cerrahi eğitim ve uzmanlık eğitimini etkileyen düzenlemeler. 1: Türkiye'den
dikkat çeken cerrahi ilkler ya da çok merkezli çalışmalar. 0: tek bir hekimin
ya da hastanenin tanıtım/başarı haberleri, hasta bilgilendirme yazıları,
sağlık turizmi, magazin, başka branşların haberleri.""",
    "rct": """ClinicalTrials.gov'a bu hafta kaydedilen randomize çalışmalar.
Alanlar: kolorektal, hepatobilier, pankreas, üst GİS, bariatrik, meme,
herni, transplantasyon, cerrahi onkoloji, acil cerrahi ve travma, MIS ve
robotik, cerrahi enfeksiyonlar, endokrin cerrahi. 2: cerrahi teknik ya da
ameliyat kararını karşılaştıran çalışmalar (ör. laparoskopik ve açık,
aksiller cerrahiden kaçınma, mesh kullanımı). 1: perioperatif bakım,
komplikasyon önleme, ERAS. 0: yalnızca anestezi/analjezi (sinir bloğu,
anestezik ilaç karşılaştırması) çalışmaları, yalnızca ilaç ya da radyoterapi
karşılaştırmaları, başka branşların ameliyatları.
"ozet" için: hangi hastada neyin neyle karşılaştırıldığını ve planlanan hasta
sayısını yaz.""",
}

GUNDEM_SEMASI = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "id": {"type": "STRING"},
            "ilgi": {"type": "INTEGER"},
            "baslik_tr": {"type": "STRING"},
            "ozet": {"type": "STRING"},
        },
        "required": ["id", "ilgi", "baslik_tr", "ozet"],
    },
}


def _aday_metni(a):
    ek = ""
    if a.get("nct"):
        ek = f"\nPlanlanan hasta: {a.get('n') or '?'} · Sponsor: {a['sponsor']} · Ülke: {a['ulke']}"
    return (f"id: {a['id']}\nKaynak: {a['kaynak']}\nTarih: {a['tarih'] or '?'}\n"
            f"Başlık: {a['baslik']}\nMetin: {a['metin'] or '(yok)'}{ek}")


def suz(gem, bolum, adaylar):
    """Gemini ile süz ve Türkçeleştir; ilgi sırasına göre dizilmiş öğeler."""
    if not adaylar:
        return []
    metin = (ORTAK_TALIMAT + BOLUM_TALIMATI[bolum] + "\n\n---\n\n" +
             "\n\n---\n\n".join(_aday_metni(a) for a in adaylar))
    yanit = {s["id"]: s for s in gem.uret(metin, sema=GUNDEM_SEMASI)}
    ogeler = []
    for a in adaylar:
        s = yanit.get(a["id"])
        if not s or s.get("ilgi", 0) < 1:
            continue
        o = {k: a[k] for k in ("kaynak", "baslik", "url", "tarih")}
        o.update(baslik_tr=s["baslik_tr"], ozet=s["ozet"], ilgi=s["ilgi"])
        if a.get("nct"):
            o.update({k: a[k] for k in ("nct", "n", "ulke", "sponsor")})
        ogeler.append(o)
    ogeler.sort(key=lambda o: (o["ilgi"], o["tarih"]), reverse=True)
    return ogeler[:config.GUNDEM_BOLUMLERI[bolum]["en_fazla"]]


# ---------------------------------------------------------------------------
# Ana akış
# ---------------------------------------------------------------------------
OKUYUCULAR = {"rss": rss_oku, "haber": haber_oku, "openfda": openfda_oku}


def adaylari_topla(bolumler, gorulen, hatalar):
    # Her kaynağın adayları ayrı liste; sonra sırayla karıştırılır ki tek bir
    # kalabalık kaynak (ör. FDA) sınırı tek başına doldurmasın
    kaynaklar = {b: [] for b in bolumler}
    for k in config.GUNDEM_KAYNAKLARI:
        if k["bolum"] not in bolumler:
            continue
        try:
            yeni = (sayfa_oku(k, gorulen) if k["tur"] == "sayfa"
                    else OKUYUCULAR[k["tur"]](k))
            print(f"  {k['bolum']:9} {k['ad']:22} {len(yeni)} aday")
            kaynaklar[k["bolum"]].append(yeni)
        except Exception as e:
            traceback.print_exc()
            hatalar.append(f"{k['ad']} ({k['bolum']}): {str(e)[:80]}")
    if "rct" in bolumler:
        try:
            kaynaklar["rct"] = [rct_oku()]
            print(f"  rct       ClinicalTrials.gov     {len(kaynaklar['rct'][0])} aday")
        except Exception as e:
            traceback.print_exc()
            hatalar.append(f"ClinicalTrials.gov: {str(e)[:80]}")

    # Daha önce değerlendirilenleri ve aynı başlıklı tekrarları at
    once = set(gorulen["ogeler"])
    adaylar = {}
    for b, listeler in kaynaklar.items():
        sirali = [a for grup in itertools.zip_longest(*listeler) for a in grup if a]
        tekil, basliklar = [], set()
        for a in sirali:
            anahtar = re.sub(r"\W+", "", a["baslik"].lower())[:80]
            if a["id"] in once or anahtar in basliklar or not a["url"]:
                continue
            basliklar.add(anahtar)
            tekil.append(a)
        adaylar[b] = tekil[:config.GUNDEM_ADAY_SINIRI]
    return adaylar


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bolum", choices=list(config.GUNDEM_BOLUMLERI),
                    help="yalnızca bu bölüm (deneme için)")
    ap.add_argument("--sahte-ozet", action="store_true")
    ap.add_argument("--bildirim-yok", action="store_true")
    ap.add_argument("--tohum", action="store_true",
                    help="yalnızca dernek sayfalarının bağlantılarını kaydet")
    a = ap.parse_args()

    gorulen = _oku_json(GORULEN, {})
    gorulen.setdefault("sayfa", {})
    gorulen.setdefault("ogeler", [])
    os.makedirs(CIKTI, exist_ok=True)

    def gorulen_yaz():
        with open(GORULEN, "w", encoding="utf-8") as f:
            json.dump(gorulen, f, ensure_ascii=False, indent=1)

    if a.tohum:
        for k in config.GUNDEM_KAYNAKLARI:
            if k["tur"] == "sayfa":
                gorulen["sayfa"].pop(k["ad"], None)
                sayfa_oku(k, gorulen)
        gorulen_yaz()
        return

    gem = ozetleyici.SahteGemini() if a.sahte_ozet else ozetleyici.Gemini()
    bolumler = [a.bolum] if a.bolum else list(config.GUNDEM_BOLUMLERI)
    bugun = dt.date.today()
    cikti = {"hafta": hafta_etiketi(bugun), "hazirlanma": bugun.isoformat(),
             "model": gem.model, "bolumler": {}, "hatalar": []}

    print("== Kaynaklar taranıyor ==")
    adaylar = adaylari_topla(bolumler, gorulen, cikti["hatalar"])

    for b in bolumler:
        ad = config.GUNDEM_BOLUMLERI[b]["ad"]
        print(f"\n== {ad}: {len(adaylar[b])} aday ==")
        try:
            ogeler = suz(gem, b, adaylar[b])
        except Exception as e:
            print(f"  SÜZGEÇ HATASI: {e}")
            cikti["hatalar"].append(f"{ad}: özet üretilemedi")
            continue
        print(f"  {len(ogeler)} öğe seçildi")
        cikti["bolumler"][b] = {"ad": ad, "aday": len(adaylar[b]), "ogeler": ogeler}
        # Değerlendirilen adaylar bir daha gelmesin (süzgeç başarılıysa)
        gorulen["ogeler"] = ([x["id"] for x in adaylar[b]] + gorulen["ogeler"]
                             )[:GORULEN_SINIRI]
        time.sleep(0 if a.sahte_ozet else 5)
    cikti["model"] = getattr(gem, "son_model", gem.model)

    with open(os.path.join(CIKTI, "gundem.json"), "w", encoding="utf-8") as f:
        json.dump(cikti, f, ensure_ascii=False, indent=1)
    if not a.sahte_ozet:
        gorulen_yaz()
    sayilar = " · ".join(f"{s['ad']} {len(s['ogeler'])}"
                         for s in cikti["bolumler"].values())
    print(f"\nTamam: {sayilar}")

    if not a.bildirim_yok:
        ek = (f"\n⚠️ Sorunlu kaynaklar: {'; '.join(cikti['hatalar'])}"
              if cikti["hatalar"] else "")
        telegram_bildir(f"📰 {cikti['hafta']} gündemi hazır.\n{sayilar}\n"
                        f"Bakmak için /gundem{ek}")
    if not cikti["bolumler"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
