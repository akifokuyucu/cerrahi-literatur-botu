"""
Yapay zekâ sağlayıcı zinciri.

Özetler sırayla denenen sağlayıcılarla üretilir: biri yoğunsa (503), kotası
dolduysa (429) ya da bozuk yanıt verirse sıradakine geçilir. Tüm yedekler
aynı şirkette olmasın diye zincirde farklı sağlayıcılar var.

Zincir LLM_ZINCIRI değişkeniyle değiştirilebilir ("saglayici:model" listesi):
  LLM_ZINCIRI="gemini:gemini-flash-latest,groq:llama-3.3-70b-versatile,ollama:gemma3:4b"
Anahtarı tanımlı olmayan sağlayıcılar zincirden sessizce çıkarılır.

Sağlayıcılar ve anahtarları:
  gemini      GEMINI_API_KEY      (Google AI Studio)
  groq        GROQ_API_KEY
  cerebras    CEREBRAS_API_KEY
  openrouter  OPENROUTER_API_KEY
  ollama      OLLAMA_URL          (yerel model, ör. http://localhost:11434)
"""
import json
import os
import re
import time

import requests

# Sıra: önce Türkçe tıbbi özette en iyi sonuç verenler. Gemini'nin ücretsiz
# kotası model başına ayrı tutulur: birkaç Flash sürümü art arda denenince
# biri günlük kotasını doldurduğunda (gemini-flash-latest günde birkaç
# istekte doluyor) diğerleri devreye girer. Google genel olarak yoğunken de
# çalışsın diye başka şirketlerin modelleri (anahtar varsa) araya girer.
# Kaldırılan modeller (404) ilk denemede o çalışma için devre dışı kalır.
VARSAYILAN_ZINCIR = [
    "gemini:gemini-flash-latest",
    "gemini:gemini-3.7-flash",
    "gemini:gemini-3.6-flash",
    "gemini:gemini-3.5-flash",
    "groq:llama-3.3-70b-versatile",
    "gemini:gemini-flash-lite-latest",
    "gemini:gemini-3.5-flash-lite",
    "cerebras:gpt-oss-120b",
    "openrouter:meta-llama/llama-3.3-70b-instruct:free",
    "gemini:gemini-3.1-flash-lite",
    "ollama:gemma3:4b",
]

# OpenAI uyumlu sağlayıcılar: (adres, anahtar değişkeni, azami girdi karakteri)
# Azami girdi, ücretsiz katmanın istek başı token sınırına göre kaba bir
# karşılık; daha uzun metinler (ör. tam metin) bu sağlayıcıya gönderilmez.
OPENAI_UYUMLU = {
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY", 30000),
    "cerebras": ("https://api.cerebras.ai/v1/chat/completions", "CEREBRAS_API_KEY", 24000),
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY", 60000),
}


class SaglayiciHatasi(Exception):
    """tur: "yogun" (tekrar denenebilir), "kota" (bekle), "kalici" (bu istek
    için sıradakine geç), "gunluk" ya da "yok" (model kaldırılmış/erişim yok:
    bu çalışma boyunca bir daha denenmez)."""

    def __init__(self, tur, mesaj, bekle=None):
        super().__init__(mesaj)
        self.tur, self.bekle = tur, bekle


# ---------------------------------------------------------------------------
# Şema yardımcıları
# ---------------------------------------------------------------------------
def json_semasi(sema):
    """Gemini şeması (type: "OBJECT") → standart JSON Schema (type: "object")."""
    if isinstance(sema, dict):
        return {k: (v.lower() if k == "type" and isinstance(v, str) else json_semasi(v))
                for k, v in sema.items()}
    if isinstance(sema, list):
        return [json_semasi(x) for x in sema]
    return sema


def sema_uyuyor(veri, sema):
    """Yanıtın üst düzey türü ve zorunlu alanları şemaya uyuyor mu?"""
    tur = sema.get("type", "").upper()
    if tur == "ARRAY":
        if not isinstance(veri, list):
            return False
        oge = sema.get("items", {})
        return all(sema_uyuyor(x, oge) for x in veri)
    if tur == "OBJECT":
        return isinstance(veri, dict) and all(k in veri for k in sema.get("required", []))
    return True


def json_coz(yanit):
    """Model yanıtındaki JSON'u çözer (```json çitlerini ve baştaki/sondaki
    açıklamaları yok sayar)."""
    yanit = yanit.strip()
    yanit = re.sub(r"^```(?:json)?\s*|\s*```$", "", yanit)
    try:
        return json.loads(yanit)
    except json.JSONDecodeError:
        m = re.search(r"[\[{].*[\]}]", yanit, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def _sarmala(sema):
    """OpenAI JSON modu üst düzeyde nesne ister: diziyi {"sonuc": [...]} içine al."""
    if sema.get("type", "").upper() == "ARRAY":
        return {"type": "OBJECT", "properties": {"sonuc": sema}, "required": ["sonuc"]}
    return sema


def _ac(veri, sema):
    if sema.get("type", "").upper() == "ARRAY" and isinstance(veri, dict):
        return veri.get("sonuc", veri)
    return veri


def _bekleme_suresi(r):
    """429 yanıtından önerilen bekleme süresini (sn) okur."""
    try:
        if r.headers.get("retry-after"):
            return int(float(r.headers["retry-after"])) + 1
        for d in r.json()["error"].get("details", []):
            if "retryDelay" in d:
                return int(float(d["retryDelay"].rstrip("s"))) + 2
    except Exception:
        pass
    return None


def _hata(ad, r):
    """HTTP yanıtını SaglayiciHatasi'na çevirir."""
    govde = r.text[:300]
    if r.status_code == 429:
        if "PerDay" in r.text or "per day" in r.text.lower() or "daily" in r.text.lower():
            return SaglayiciHatasi("gunluk", f"{ad}: günlük kota dolu")
        return SaglayiciHatasi("kota", f"{ad} 429: {govde}", _bekleme_suresi(r))
    if r.status_code in (500, 502, 503, 504):
        return SaglayiciHatasi("yogun", f"{ad} {r.status_code}: {govde}")
    if r.status_code in (401, 403, 404):
        # Model kaldırılmış ya da anahtarın erişimi yok: her istekte yeniden denenmesin
        return SaglayiciHatasi("yok", f"{ad}: erişilemiyor ({r.status_code})")
    return SaglayiciHatasi("kalici", f"{ad} hata {r.status_code}: {govde}")


# ---------------------------------------------------------------------------
# Sağlayıcılar
# ---------------------------------------------------------------------------
class GeminiSaglayici:
    API = "https://generativelanguage.googleapis.com/v1beta/models"
    azami_girdi = 10 ** 7

    def __init__(self, model, api_key):
        self.model, self.api_key = model, api_key
        self.ad = model  # geriye uyum: çıktıda "gemini-flash-latest" görünsün

    def uret(self, metin, sema=None, sicaklik=0.2):
        govde = {"contents": [{"role": "user", "parts": [{"text": metin}]}],
                 "generationConfig": {"temperature": sicaklik}}
        if sema:
            govde["generationConfig"].update(responseMimeType="application/json",
                                             responseSchema=sema)
        r = requests.post(f"{self.API}/{self.model}:generateContent", json=govde,
                          timeout=180, headers={"x-goog-api-key": self.api_key})
        if not r.ok:
            raise _hata(self.ad, r)
        try:
            parcalar = r.json()["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError):
            # Güvenlik süzgeci ya da boş yanıt
            raise SaglayiciHatasi("kalici", f"{self.ad}: boş yanıt {r.text[:200]}")
        yanit = "".join(p.get("text", "") for p in parcalar)
        return json_coz(yanit) if sema else yanit


class OpenAIUyumlu:
    def __init__(self, saglayici, model, api_key):
        self.url, _, self.azami_girdi = OPENAI_UYUMLU[saglayici]
        self.model, self.api_key = model, api_key
        self.ad = f"{saglayici}/{model}"
        self.json_modu = True

    def uret(self, metin, sema=None, sicaklik=0.2):
        if sema:
            metin += ("\n\nYanıtı YALNIZCA şu JSON şemasına uyan tek bir JSON nesnesi "
                      "olarak ver, başka hiçbir şey yazma:\n" +
                      json.dumps(json_semasi(_sarmala(sema)), ensure_ascii=False))
        govde = {"model": self.model, "temperature": sicaklik,
                 "messages": [{"role": "user", "content": metin}]}
        if sema and self.json_modu:
            govde["response_format"] = {"type": "json_object"}
        r = requests.post(self.url, json=govde, timeout=180,
                          headers={"Authorization": f"Bearer {self.api_key}"})
        if r.status_code == 400 and "response_format" in r.text and self.json_modu:
            # Bazı modeller JSON modunu desteklemez: talimatla yetin
            self.json_modu = False
            return self.uret(metin.split("\n\nYanıtı YALNIZCA")[0], sema, sicaklik)
        if not r.ok:
            raise _hata(self.ad, r)
        try:
            yanit = r.json()["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError):
            raise SaglayiciHatasi("kalici", f"{self.ad}: boş yanıt {r.text[:200]}")
        return _ac(json_coz(yanit), sema) if sema else yanit


class OllamaSaglayici:
    """Yerel Ollama (https://ollama.com). Yavaş ama kotasız; son çare."""
    azami_girdi = 60000

    def __init__(self, model, url):
        self.model, self.url = model, url.rstrip("/")
        self.ad = f"ollama/{model}"

    def uret(self, metin, sema=None, sicaklik=0.2):
        govde = {"model": self.model, "stream": False,
                 "messages": [{"role": "user", "content": metin}],
                 # Ollama varsayılan bağlamı (4096) özet listesine yetmez
                 "options": {"temperature": sicaklik, "num_ctx": 16384}}
        if sema:
            govde["format"] = json_semasi(sema)
        try:
            r = requests.post(f"{self.url}/api/chat", json=govde, timeout=1800)
        except requests.ConnectionError:
            raise SaglayiciHatasi("kalici", f"{self.ad}: sunucuya bağlanılamadı ({self.url})")
        if not r.ok:
            raise _hata(self.ad, r)
        yanit = r.json()["message"]["content"]
        return json_coz(yanit) if sema else yanit


# ---------------------------------------------------------------------------
# Zincir
# ---------------------------------------------------------------------------
def saglayici_kur(tanim):
    """"groq:llama-3.3-70b-versatile" → sağlayıcı nesnesi (anahtar yoksa None)."""
    tur, _, model = tanim.strip().partition(":")
    if tur == "gemini":
        anahtar = os.getenv("GEMINI_API_KEY")
        return GeminiSaglayici(model, anahtar) if anahtar else None
    if tur in OPENAI_UYUMLU:
        anahtar = os.getenv(OPENAI_UYUMLU[tur][1])
        return OpenAIUyumlu(tur, model, anahtar) if anahtar else None
    if tur == "ollama":
        url = os.getenv("OLLAMA_URL")
        return OllamaSaglayici(model, url) if url else None
    raise ValueError(f"Bilinmeyen sağlayıcı: {tanim}")


def zincir_tanimi():
    tanim = os.getenv("LLM_ZINCIRI")
    liste = ([t.strip() for t in tanim.split(",") if t.strip()] if tanim
             else list(VARSAYILAN_ZINCIR))
    # Eski ayar: GEMINI_MODEL ana modeli belirler
    ana = os.getenv("GEMINI_MODEL")
    if ana and not tanim:
        liste = [f"gemini:{ana}"] + [t for t in liste if t != f"gemini:{ana}"]
    return liste


class Zincir:
    def __init__(self, saglayicilar=None, yogun_deneme=2, yogun_bekleme=10):
        if saglayicilar is None:
            saglayicilar = [s for s in map(saglayici_kur, zincir_tanimi()) if s]
        if not saglayicilar:
            raise RuntimeError("Hiçbir yapay zekâ sağlayıcısının anahtarı tanımlı değil "
                               "(en az GEMINI_API_KEY gerekir).")
        self.saglayicilar = saglayicilar
        # Bir sağlayıcı yoğunken (503) kaç kez, kaç saniye arayla denensin
        self.yogun_deneme, self.yogun_bekleme = yogun_deneme, yogun_bekleme
        self.model = saglayicilar[0].ad      # ana model
        self.son_model = self.model          # son başarılı yanıtı veren
        self.notlar = []                     # yedeğe geçiş nedenleri
        self.kullanim = {}                   # {model: başarılı istek sayısı}
        self._devre_disi = set()             # günlük kotası dolanlar
        print("Sağlayıcı zinciri:", " > ".join(s.ad for s in saglayicilar))

    def uret(self, metin, sema=None, sicaklik=0.2):
        son_hata = ""
        for s in self.saglayicilar:
            if s.ad in self._devre_disi:
                continue
            if len(metin) > s.azami_girdi:
                continue  # metin bu sağlayıcının ücretsiz sınırını aşıyor
            deneme = 0
            while True:
                try:
                    veri = s.uret(metin, sema, sicaklik)
                    if sema and not sema_uyuyor(veri, sema):
                        raise SaglayiciHatasi("kalici", f"{s.ad}: yanıt şemaya uymuyor")
                    self.son_model = s.ad
                    self.kullanim[s.ad] = self.kullanim.get(s.ad, 0) + 1
                    return veri
                except (SaglayiciHatasi, ValueError, KeyError,
                        requests.RequestException) as e:
                    # Bağlantı/zaman aşımı → yoğun; JSON olmayan ya da bozuk
                    # yanıt (requests'in JSON hatası da ValueError) → kalıcı
                    tur = getattr(e, "tur", None) or (
                        "kalici" if isinstance(e, (ValueError, KeyError)) else "yogun")
                    son_hata = str(e)[:300]
                    onerilen = getattr(e, "bekle", None)
                deneme += 1
                if tur in ("gunluk", "yok"):
                    neden = "günlük kota dolu" if tur == "gunluk" else "erişilemiyor"
                    print(f"  {s.ad}: {neden}, bu çalışmada bir daha denenmeyecek")
                    self._devre_disi.add(s.ad)
                    self._not(f"{s.ad}: {neden}")
                    break
                bekle = None
                if tur == "kota" and deneme < 3:
                    bekle = min(onerilen or 20, 90)
                elif tur == "yogun" and deneme < self.yogun_deneme:
                    bekle = self.yogun_bekleme
                neden = {"kota": "dakika kotası", "yogun": "yoğun"}.get(tur, "hata")
                if bekle is None:
                    print(f"  {s.ad}: {neden}, sıradakine geçiliyor ({son_hata[:150]})")
                    self._not(f"{s.ad}: {neden}")
                    break
                print(f"  {s.ad}: {neden}, {bekle} sn bekleniyor...")
                time.sleep(bekle)
        raise RuntimeError(f"Hiçbir sağlayıcı yanıt vermedi. Son hata: {son_hata}")

    def _not(self, metin):
        if metin not in self.notlar:
            self.notlar.append(metin)
