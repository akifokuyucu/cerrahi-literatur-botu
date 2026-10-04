"""
Uydurma sayı denetimi: özetteki her sayı kaynak metinde geçiyor mu?

Yapay zekâ bazen metinde olmayan oran, HR ya da hasta sayısı yazar. Bu
denetim, özetteki sayıları (0,68 · %4,8 · 1.250) kaynakta (0.68 · 4.8% ·
1,250) arar; ondalık virgül/nokta, binlik ayırıcı ve sondaki sıfırlar
farkını yok sayar. Tek basamaklı tam sayılar ("3 RCT", "2 grup") metinde
yazıyla geçebildiği için denetlenmez.

worker/src/index.js'teki sayiDenetimi ile aynı mantık.
"""
import re

SAYI = re.compile(r"\d+(?:[.,]\d+)*")


def _bicimler(sayi):
    """"1,250" → {"1.25", "1250"}; "0.680" → {"0.68"}."""
    bicimler = set()
    nokta = sayi.replace(",", ".")
    if "." in nokta and nokta.count(".") == 1:
        tam, kesir = nokta.split(".")
        kesir = kesir.rstrip("0")
        bicimler.add(f"{int(tam)}.{kesir}" if kesir else str(int(tam)))
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", sayi):
        bicimler.add(str(int(re.sub(r"[.,]", "", sayi))))
    if not bicimler:
        bicimler.add(str(int(nokta)) if nokta.isdigit() else nokta)
    return bicimler


BIRLER = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
         "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
         "sixteen", "seventeen", "eighteen", "nineteen"]
ONLAR = ["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
SOZCUK_SAYI = re.compile(
    r"\b(?:(" + "|".join(ONLAR) + r")(?:[- ](" + "|".join(BIRLER[1:10]) + r"))?|("
    + "|".join(BIRLER) + r"))\b", re.I)


def _sozcuk_sayilari(metin):
    """İngilizce özetlerde cümle başında yazıyla geçen sayılar
    ("Thirty-six patients", "Seventeen studies") → {"36", "17"}."""
    sayilar = set()
    for onlar, birler, tek in SOZCUK_SAYI.findall(metin):
        if tek:
            sayilar.add(str(BIRLER.index(tek.lower())))
        else:
            sayilar.add(str(20 + 10 * ONLAR.index(onlar.lower()) +
                            (BIRLER.index(birler.lower()) if birler else 0)))
    return sayilar


def kaynak_sayilari(metin):
    # ".047" → "0.047"
    metin = re.sub(r"(?<![\d.,])[.,](\d)", r"0.\1", metin or "")
    sayilar = _sozcuk_sayilari(metin)
    for s in SAYI.findall(metin):
        sayilar |= _bicimler(s)
    # Boşlukla ayrılmış binlikler: "€53 562" → 53562
    for bas, son in re.findall(r"(?<![\d.,])(\d{1,3})[   ](\d{3})(?![\d.,]\d)", metin):
        sayilar.add(str(int(bas + son)))
    return sayilar


def dogrulanamayan(ozet, kaynak):
    """Özetteki, kaynakta bulunamayan sayılar (sırayla, tekrarsız)."""
    kaynaktaki = kaynak_sayilari(kaynak)
    ozet = re.sub(r"(?<![\d.,])[.,](\d)", r"0.\1", ozet or "")
    sonuc = []
    for s in SAYI.findall(ozet):
        if re.fullmatch(r"\d", s):
            continue
        if not (_bicimler(s) & kaynaktaki) and s not in sonuc:
            sonuc.append(s)
    return sonuc


def metinler(veri):
    """İç içe sözlük/listedeki tüm metinleri tek metinde birleştirir."""
    if isinstance(veri, str):
        return veri
    if isinstance(veri, dict):
        return "\n".join(metinler(v) for v in veri.values())
    if isinstance(veri, list):
        return "\n".join(metinler(v) for v in veri)
    return ""


def uyari_notu(sayilar):
    """Yeniden denemede talimata eklenen not."""
    return ("\n\nDİKKAT: Önceki denemede metinde OLMAYAN şu sayılar yazıldı: "
            f"{', '.join(sayilar)}. Yalnızca metinde geçen sayıları kullan; "
            "hesaplama yapma, yuvarlama yapma.")
