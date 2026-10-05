"""
Ayrıntılı (journal club) özetlerin pazartesi toplu hazırlanması.

Bot 📄 tuşunda bu özetleri cikti/detay.json'dan anında okur; yapay zekâyı
yalnızca listede olmayan makaleler ve soru-cevap için çağırır. Talimat ve
şema worker/src/index.js'teki DETAY_TALIMATI / DETAY_SEMASI ile aynı
tutulmalı.
"""
import html
import re
import time

import requests

import denetim

DETAY_TALIMATI = """Sen genel cerrahi alanında deneyimli bir akademisyensin ve
yeni mezun bir hekime journal club tarzında makale anlatıyorsun.
Aşağıdaki makaleyi Türkçe olarak yapılandırılmış biçimde özetle.

Kurallar:
- Tıbbi terimleri ve kısaltmaları İngilizce bırak (anastomotic leak, hazard
  ratio, RCT, per-protocol, NNT vb.). Cümle yapısı Türkçe olsun.
- YALNIZCA verilen metindeki bilgiyi kullan. Metinde olmayan sayı veya
  sonuç uydurma. Bir bilgi metinde yoksa "belirtilmemiş" de.
- Ana bulgularda sayıları (oran, %95 CI, p) mutlaka ver. Sayıları her zaman
  RAKAMLA yaz (750 hasta, %59); asla yazıyla yazma.
- "pratige_etkisi" kısmında, bulguların klinik pratiği değiştirip
  değiştirmeyeceğini kanıt düzeyiyle birlikte dengeli biçimde değerlendir.
- "journal_club_sorulari": çalışmayı eleştirel okumaya yönelten 2-3 soru.
- "pico": dört alanın HER BİRİNİ kısa bir ifadeyle doldur (en fazla 1 cümle).
  Gözlemsel çalışmalarda I = incelenen yaklaşım/maruziyet, C = karşılaştırma
  grubu; meta-analizde dahil edilen çalışmaların PICO'sunu yaz. Alanlara
  asla talimat, açıklama veya "belirtilmemiş" dışında meta yorum yazma."""

DETAY_SEMASI = {
    "type": "OBJECT",
    "properties": {
        "baslik_tr": {"type": "STRING"},
        "tek_cumle": {"type": "STRING"},
        "tasarim": {"type": "STRING"},
        "pico": {
            "type": "OBJECT",
            "properties": {"P": {"type": "STRING"}, "I": {"type": "STRING"},
                           "C": {"type": "STRING"}, "O": {"type": "STRING"}},
        },
        "ana_bulgular": {"type": "ARRAY", "items": {"type": "STRING"}},
        "guclu_yanlar": {"type": "ARRAY", "items": {"type": "STRING"}},
        "sinirliliklar": {"type": "ARRAY", "items": {"type": "STRING"}},
        "pratige_etkisi": {"type": "STRING"},
        "journal_club_sorulari": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["baslik_tr", "tek_cumle", "tasarim", "ana_bulgular",
                 "sinirliliklar", "pratige_etkisi"],
}

TAM_METIN_SINIRI = 60000


def jats_metne(xml):
    """JATS tam metninden kaynakça ve tabloları atıp düz metin çıkarır."""
    m = re.search(r"<body[\s\S]*</body>", xml)
    govde = m.group(0) if m else ""
    govde = re.sub(r"<ref-list[\s\S]*?</ref-list>", "", govde)
    govde = re.sub(r"<table-wrap[\s\S]*?</table-wrap>", "", govde)
    govde = re.sub(r"<xref[^>]*>[\s\S]*?</xref>", "", govde)
    govde = govde.replace("<title>", "\n\n## ").replace("</title>", "\n")
    govde = govde.replace("</p>", "\n")
    govde = html.unescape(re.sub(r"<[^>]+>", "", govde))
    govde = re.sub(r"\s*\[[,\s–-]*\]", "", govde)  # atıflardan kalan boş köşeli parantezler
    return re.sub(r"\n{3,}", "\n\n", govde).strip()


def tam_metin(pmc):
    """Açık erişimli makalenin tam metni (Europe PMC, olmazsa NCBI)."""
    if not pmc:
        return ""
    kaynaklar = [
        f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmc}/fullTextXML",
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc"
        f"&id={pmc.replace('PMC', '')}&tool=cerrahi-literatur-botu",
    ]
    for url in kaynaklar:
        try:
            r = requests.get(url, timeout=60)
            if not r.ok:
                continue
            metin = jats_metne(r.text)
            if len(metin) > 2000:
                return metin[:TAM_METIN_SINIRI]
        except requests.RequestException as e:
            print(f"  tam metin hatası {url[:60]}: {e}")
    return ""


def girdi_metni(m, tam):
    return (f"{DETAY_TALIMATI}\n\n---\nDergi: {m['dergi']} ({m.get('yil') or ''})\n"
            f"Çalışma tipi (PubMed): {m.get('tip_etiketi') or 'belirtilmemiş'}\n"
            f"Başlık: {m['baslik']}\n\nÖzet (abstract):\n{m.get('ozet') or '(yok)'}"
            + (f"\n\nTAM METİN:\n{tam}" if tam else ""))


def detay_hazirla(zincir, m, tam_metin_al=True):
    """{"d": özet, "tam": bool, "model": ad[, "sayi_uyarisi": [...]]}.
    Metinde olmayan sayı yazılırsa bir kez uyarıyla yeniden üretilir."""
    tam = tam_metin(m.get("pmc")) if tam_metin_al else ""
    girdi = girdi_metni(m, tam)
    kaynak = (f"{m['dergi']} {m.get('yil') or ''} {m.get('tip_etiketi') or ''} "
              f"{m['baslik']} {m.get('ozet') or ''} {tam}")
    d = zincir.uret(girdi, sema=DETAY_SEMASI)
    model = zincir.son_model
    hatali = denetim.dogrulanamayan(denetim.metinler(d), kaynak)
    if hatali:
        print(f"  {m['pmid']}: doğrulanamayan sayılar {hatali}, yeniden deneniyor")
        try:
            d2 = zincir.uret(girdi + denetim.uyari_notu(hatali), sema=DETAY_SEMASI)
            kalan = denetim.dogrulanamayan(denetim.metinler(d2), kaynak)
            if len(kalan) < len(hatali):
                d, hatali, model = d2, kalan, zincir.son_model
        except Exception as e:
            print(f"  Yeniden deneme başarısız: {str(e)[:120]}")
    kayit = {"d": d, "tam": bool(tam), "model": model}
    if hatali:
        kayit["sayi_uyarisi"] = hatali
    return kayit


def hepsini_hazirla(zincir, makaleler, onceki, sure_dk, bekleme=4, tam_metin_al=True):
    """Makaleleri sırayla özetler; süre dolunca kalanlar bota (anlık üretime)
    bırakılır. onceki: aynı hafta önceki çalıştırmadan kalan özetler."""
    sonuc, bitis = {}, time.monotonic() + sure_dk * 60
    ardisik_hata = 0
    for m in makaleler:
        if m["pmid"] in onceki:
            sonuc[m["pmid"]] = onceki[m["pmid"]]
            continue
        if time.monotonic() > bitis:
            print(f"  Süre doldu; {len(makaleler) - len(sonuc)} makale bota bırakıldı")
            break
        try:
            sonuc[m["pmid"]] = detay_hazirla(zincir, m, tam_metin_al)
            ardisik_hata = 0
            print(f"  {m['pmid']}: hazır ({sonuc[m['pmid']]['model']}"
                  f"{', tam metin' if sonuc[m['pmid']]['tam'] else ''})")
        except Exception as e:
            print(f"  {m['pmid']}: ayrıntılı özet hatası ({str(e)[:150]})")
            ardisik_hata += 1
            # Tek makaleye özgü hatalar (bozuk JSON vb.) döngüyü durdurmasın;
            # art arda 4 hata ise sağlayıcıların hepsinin düştüğünü gösterir
            if ardisik_hata >= 4:
                print("  Art arda hata; kalanlar bota bırakıldı")
                break
        time.sleep(bekleme)
    return sonuc
