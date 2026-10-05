"""
🎓 YÖK Ulusal Tez Merkezi'nden alan başına bir tez.

Her alanın Türkçe başlık terimleri (config.YOKTEZ_TERIMLERI) Ulusal Tez
Merkezi'nin başlık aramasında taranır. Konusu "Genel Cerrahi" olan, son iki
yılın uzmanlık/doktora tezlerinden henüz gösterilmemiş en yenisi (en büyük
Tez No) seçilir. Özeti (Türkçe, yoksa İngilizce) ayrıntı uç noktasından
alınır; kısa özeti makalelerle aynı yoldan yapay zekâ yazar.

Not: Sitenin "Detaylı Arama"sı betikten "Geçersiz sorgulama" döndürüyor;
"Gelişmiş Arama" (başlıkta kelime) tarayıcı başlıklarıyla çalışıyor. Sunucuya
yük olmamak için istekler arasında bekleniyor ve aynı terim bir kez aranıyor.
Tezlerin herkese açık ayrıntı sayfası yok: botta Tez No ve arama sayfası
bağlantısı gösterilir.
"""
import datetime as dt
import html
import json
import os
import re
import time

import requests

import config

KOK = "https://tez.yok.gov.tr/UlusalTezMerkezi"
ARAMA_SAYFASI = f"{KOK}/tarama.jsp"
CIKTI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cikti")
GOSTERILEN = os.path.join(CIKTI, "tez_gosterilen.json")

BASLIKLAR = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/141.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Origin": "https://tez.yok.gov.tr",
    "Referer": ARAMA_SAYFASI,
    "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin", "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def _sade(metin):
    metin = html.unescape(re.sub(r"<[^>]+>", " ", metin or ""))
    return " ".join(metin.split())


def sonuclari_ayristir(sayfa):
    """Arama sonuç sayfası → tez listesi. Kartlarda kimlikler ve Tez No,
    sayfadaki referenceData'da yazar/yıl/konu/tür bilgisi var."""
    meta = {}
    for no, govde in re.findall(r'"(\d+)":\s*\{\s*"meta":\s*(\{.*?\})\s*\}', sayfa, re.S):
        try:
            meta[no] = json.loads(govde)
        except json.JSONDecodeError:
            continue
    tezler = []
    kartlar = re.split(r'<div class="result-card"', sayfa)[1:]
    for kart in kartlar:
        m = re.search(r'data-index="(\d+)"\s+data-kayitno="([^"]+)"\s+data-tezno="([^"]+)"', kart)
        no = re.search(r"Tez No:</strong>\s*(\d+)", kart)
        if not (m and no):
            continue
        bilgi = meta.get(m.group(1), {})
        en = re.search(r'card-info" style="font-style: italic">\s*(.*?)\s*</div>', kart, re.S)
        tezler.append({
            "kayit": m.group(2), "anahtar": m.group(3), "no": int(no.group(1)),
            "baslik": bilgi.get("title") or _sade(re.search(
                r'card-title">\s*(.*?)\s*</div>', kart, re.S).group(1)),
            "baslik_en": _sade(en.group(1)) if en else "",
            "yazar": bilgi.get("author", ""), "yil": bilgi.get("year", ""),
            "konu": bilgi.get("subject", ""), "tur": bilgi.get("type", ""),
            "universite": (bilgi.get("yer") or "").strip(" /"),
        })
    return tezler


class YokTez:
    def __init__(self, bekleme=2):
        self.s = requests.Session()
        self.s.headers.update(BASLIKLAR)
        self.bekleme = bekleme
        self._onbellek = {}
        self._oturum = False

    def _istek(self, yontem, url, **kw):
        for deneme in range(3):
            try:
                if not self._oturum:
                    self.s.get(ARAMA_SAYFASI, timeout=30)
                    self._oturum = True
                r = self.s.request(yontem, url, timeout=180, **kw)
                r.raise_for_status()
                time.sleep(self.bekleme)
                return r
            except requests.RequestException as e:
                if deneme == 2:
                    raise
                print(f"  YÖK Tez hata ({e}), yeniden deneniyor...")
                self._oturum = False
                time.sleep(5 * (deneme + 1))

    def ara(self, terim):
        """Başlığında terim geçen tezler (en yeniden eskiye)."""
        if terim not in self._onbellek:
            r = self._istek("POST", f"{KOK}/SearchTez", data=[
                ("keyword", terim), ("keyword1", ""), ("keyword2", ""),
                ("ops_field", "and"), ("ops_field1", "and"),
                ("nevi", "1"),  # 1 = tez adı
                ("tip", "2"),   # 2 = kelimenin içinde geçsin
                ("islem", "4"), ("-find", "  Bul")])
            if "Hata" in r.url:
                raise RuntimeError(f"YÖK Tez araması reddedildi ({terim})")
            self._onbellek[terim] = sonuclari_ayristir(r.text)
        return self._onbellek[terim]

    def ayrinti(self, tez):
        """Özet, danışman ve tam kurum adı."""
        r = self._istek("GET", f"{KOK}/tezBilgiDetay.jsp",
                        params={"kayitNo": tez["kayit"], "tezNo": tez["anahtar"]},
                        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest",
                                 "Sec-Fetch-Mode": "cors", "Sec-Fetch-Dest": "empty"})
        j = r.json()
        return {"ozet_tr": _sade(j.get("trOzet")), "ozet_en": _sade(j.get("enOzet")),
                "danisman": _sade(j.get("danisman")).replace("Danışman: ", ""),
                "kurum": _sade(j.get("yer"))}


def uygun_mu(tez, yil_alt):
    # Hemşirelik doktora tezlerinin konusu da "Genel Cerrahi" içerebiliyor
    return ("Genel Cerrahi" in tez["konu"] and "Hemşirelik" not in tez["konu"]
            and tez["tur"] in config.YOKTEZ_TURLER
            and tez["yil"].isdigit() and int(tez["yil"]) >= yil_alt)


def oku_gosterilen():
    try:
        with open(GOSTERILEN, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def gosterildi_isaretle(alan_kodu, tez_no):
    g = oku_gosterilen()
    g.setdefault(alan_kodu, []).append(tez_no)
    os.makedirs(CIKTI, exist_ok=True)
    with open(GOSTERILEN, "w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False, indent=1)


def tez_sec(yt, alan_kodu, haric=(), bugun=None):
    """Alan için gösterilmemiş en yeni genel cerrahi tezi (makale biçiminde).
    haric: bu çalışmada başka alanda seçilen Tez No'lar."""
    bugun = bugun or dt.date.today()
    gosterilen = {n for liste in oku_gosterilen().values() for n in liste} | set(haric)
    adaylar = {}
    for terim in config.YOKTEZ_TERIMLERI.get(alan_kodu, []):
        for t in yt.ara(terim):
            if uygun_mu(t, bugun.year - config.YOKTEZ_YIL_GERI) and t["no"] not in gosterilen:
                adaylar[t["no"]] = t
    # En yeni önce; özeti olmayanı atla (en fazla 3 deneme)
    for t in sorted(adaylar.values(), key=lambda t: t["no"], reverse=True)[:3]:
        a = yt.ayrinti(t)
        ozet = a["ozet_tr"] or a["ozet_en"]
        if len(ozet) < 100:
            continue
        return {
            "pmid": f"tez{t['no']}", "tez_no": t["no"], "baslik": t["baslik"],
            "ozet": ozet, "dergi": "YÖK Tez", "dergi_tam": a["kurum"] or t["universite"],
            "yil": t["yil"], "tip": "tez", "tip_etiketi": f"{t['tur']} tezi",
            "yazar": t["yazar"], "danisman": a["danisman"],
            "universite": t["universite"], "url": ARAMA_SAYFASI,
        }
    return None
