# Cerrahi Literatür Botu

Genel cerrahinin 14 alt alanında her hafta öne çıkan makaleleri seçip Telegram'da sunan kişisel bot. Perşembeleri ayrıca cerrahi haberlerini ve gelişmeleri (📰 Gündem) derler.

- **Her pazartesi 07:00:** GitHub Actions, PubMed'deki son 7 günün makalelerini tarar ve dergi ağırlığı ile çalışma tipine göre puanlar. Her alanda en iyi 5 makaleyi seçer, Turkish Journal of Surgery'den bir makale ekler, yapay zekâ ile (önce Gemini, yoğunsa ücretsiz yedekler) Türkçe kısa özetlerini yazar ve sonucu `cikti/hafta.json` dosyasına kaydeder. Ardından listedeki makalelerin ayrıntılı özetlerini en fazla 20 dakika boyunca hazırlar (önce öne çıkanlar) ve `cikti/detay.json` dosyasına yazar.
- **Her perşembe 07:00 (📰 Gündem):** GitHub Actions dört bölüm hazırlar ve sonucu `cikti/gundem.json` dosyasına kaydeder:
  - 📘 Kılavuz & Kongre: WSES, ESCP ve ASCRS haber sayfaları, EAES ve SAGES RSS akışları (okunamazsa sitelerin Google Haberler'deki sayfaları), Google Haberler
  - 🤖 Teknoloji & Onaylar: FDA 510(k) kararları (openFDA), FDA/CE onayı, cerrahi robotik ve yapay zekâ haberleri
  - 🇹🇷 Türkiye: Türk Cerrahi Derneği, TTB ve ulusal kongre haberleri
  - 🧪 Yeni RCT'ler: ClinicalTrials.gov'a o hafta kaydedilen cerrahi randomize çalışmalar

  Adaylar yapay zekânın genel cerrahi süzgecinden geçer; tanıtım, borsa ve başka branş haberleri elenir. Kalanlara Türkçe başlık ve kısa özet yazılır. Dernek sayfalarında yalnızca önceki haftadan sonra eklenen bağlantılar alınır. Daha önce gösterilen haberler `cikti/gundem_gorulen.json` sayesinde tekrar gelmez.
- **Telegram'da:** `/start` → alan seç → 5 makale ve kısa özetleri görünür → 📄 tuşuna basınca ayrıntılı özet gelir. Pazartesi hazırlanmışsa anında gelir; hazırlanmamışsa bot o anda üretir. Makale açık erişimliyse ayrıntılı özet tam metinden, değilse özetten (abstract) hazırlanır.
- Ayrıntılı özetin altında: **👍 / 👎** (oylar sonraki haftaların puanlamasına küçük bir kişisel katkı ekler), **📌 Arşive ekle** (Notion Okuma Arşivi), **📸 İçerik adayı** (Notion İçerik Havuzu'na "fikir"), **❓ Soru sor** (makale metnine dayalı soru-cevap; /iptal ile çıkılır). `/istatistik` oyların özetini gösterir. `/gundem` ya da menüdeki **📰 Gündem** tuşu haber bölümlerini açar. `/onecikanlar` ya da **🔥 Haftanın öne çıkanları** tuşu tüm alanlardan en yüksek puanlı 5 makaleyi gösterir.
- Bot yalnızca sahibine cevap verir.

## Klasörler

| Klasör | Ne işe yarar |
|---|---|
| `motor/config.py` | **Ayarlar:** dergi kademeleri, puanlar, alan arama terimleri |
| `motor/` | PubMed'den çekme, puanlama, özetleme (Python) |
| `motor/llm.py` | Yapay zekâ sağlayıcı zinciri (Gemini ve ücretsiz yedekler) |
| `motor/detay.py` | Ayrıntılı (journal club) özetlerin pazartesi toplu hazırlanması |
| `motor/gundem.py` | 📰 Gündem: haber kaynaklarını tarama ve süzme (kaynak listesi `config.py` içinde) |
| `worker/` | Telegram botu (Cloudflare Worker, JavaScript) |
| `cikti/` | Haftalık sonuç dosyası (otomatik oluşur) |
| `.github/workflows/haftalik.yml` | Pazartesi zamanlaması (makaleler) |
| `.github/workflows/gundem.yml` | Perşembe zamanlaması (gündem) |

İki iş akışı da saat 10:00'da bir kez daha tetiklenir. O günün dosyası sabah hazırlandıysa bu çalışma hiçbir şey yapmadan biter. Sabahki çalışma GitHub tarafından atlandıysa ya da başarısız olduysa liste 10:00'da hazırlanır.

## Puanlama

Toplam puan = dergi puanı + çalışma tipi puanı.

**Dergi puanı**
- Kademe 1: 3
- Kademe 2: 2
- Kademe 3: 1
- Listede olmayan dergi: 0

**Çalışma tipi puanı**
- Kılavuz: 4
- Meta-analiz / sistematik derleme: 3
- RCT: 3
- Prospektif, Delphi / konsensus çalışması: 2
- Retrospektif ve diğer: 1

**Cerrahi ilgi filtresi:** Her alanda en yüksek puanlı 12 aday yapay zekâya gönderilir (7 ve 6 makalelik iki istekle; bozuk bir yanıt bütün alanı boş bırakmaz, atlanan makaleler bir kez daha istenir). Yapay zekâ, genel cerrahi pratiğiyle ilgisiz bulduklarını (cerrahi bağlamı olmayan radyoterapi/ilaç çalışması, temel bilim, başka branş) eler. Kalanlardan puan sırasıyla ilk 5 gösterilir.

**Türk dergisi satırı:** Turkish Journal of Surgery; Acil Cerrahi alanında ayrıca Ulusal Travma ve Acil Cerrahi Dergisi (TJTES).

**Kişisel puan:** Bottaki her net 👍/👎, o dergi ve çalışma tipi için ±0,25 puan; dergi ve tip başına en fazla ±0,5. Yalnızca sıralamayı etkiler, gösterilen puan değişmez.

**Elenenler:** Olgu sunumu, editoryal, yorum, mektup, kongre bildirisi, özeti olmayan kayıtlar ve çalışma protokolleri listeye girmez. Hayvan deneyleri 1 puan alır.

## Yapay zekâ sağlayıcıları

Özetler sırayla denenen bir sağlayıcı zinciriyle üretilir. Biri yoğunsa (503), kotası dolduysa (429) ya da bozuk yanıt verirse sıradakine geçilir. Günlük kotası dolan ya da kaldırılmış (404) model o çalışma boyunca bir daha denenmez. Anahtarı tanımlı olmayan sağlayıcı atlanır, bu yüzden yalnızca `GEMINI_API_KEY` ile de çalışır.

Gemini'nin ücretsiz kotası **model başına ayrı** tutulur. `gemini-flash-latest` günde yalnızca birkaç istekte doluyor (5 Ekim 2026: 5 istek). Bu yüzden zincirde birkaç Flash sürümü art arda yer alıyor.

**Haftalık hazırlık (GitHub Actions)** varsayılan sırası:
1. Gemini: `gemini-flash-latest`, `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`
2. Groq: `openai/gpt-oss-120b` (`GROQ_API_KEY`, [console.groq.com](https://console.groq.com); ücretsiz planda günde 1.000 istek)
3. Gemini: `gemini-flash-lite-latest`, `gemini-3.5-flash-lite`
4. Groq: `qwen/qwen3.8-27b` (aynı anahtar, ayrı kota); Cerebras: `gpt-oss-120b` (`CEREBRAS_API_KEY`)
5. OpenRouter: ücretsiz Llama 3.3 70B (`OPENROUTER_API_KEY`)
6. Gemini: `gemini-3.1-flash-lite`
7. Ollama: yerel model (`OLLAMA_URL`; yalnızca kendi bilgisayarında çalıştırırken)

Not: GitHub Models 30 Temmuz 2026'da kapatıldı; Gemini 2.5 modelleri Eylül 2026'dan beri yeni projelere kapalı. Bu yüzden ikisi de zincirde yok.

Sırayı değiştirmek için GitHub'da Settings → Secrets and variables → Actions → **Variables** altına `LLM_ZINCIRI` ekle. Örnek: `gemini:gemini-flash-latest,groq:openai/gpt-oss-120b,gemini:gemini-flash-lite-latest`.

Hangi modelin kullanıldığı ve yedeğe neden geçildiği `cikti/hafta.json` dosyasında görünür (`model_kullanimi`, `model_notlari`).

**Uydurma sayı denetimi (`motor/denetim.py`):** Özetteki her sayı (oran, HR, p değeri, hasta sayısı) kaynak metinde aranır. Ondalık virgül/nokta farkı, binlik ayırıcılar ve İngilizce yazıyla geçen sayılar ("Thirty-six patients") hesaba katılır. Kaynakta olmayan sayı varsa özet bir kez uyarı notuyla yeniden ürettirilir. Yine düzelmezse botta ⚠️ ile işaretlenir; ayrıntılı özette hangi sayıların doğrulanamadığı yazar.

**Bot (anlık ayrıntılı özet ve soru-cevap)** sırası: Gemini Flash modelleri → Groq (Cloudflare'de `GROQ_API_KEY` secret'ı varsa) → Workers AI (`wrangler.toml` içindeki `AI` bağlantısı, günde 10.000 neuron ücretsiz) → Gemini Flash-Lite modelleri.

## Kurulum

1. **GitHub:** Bu depo herkese açık (public) olmalı. Bot, `cikti/hafta.json` dosyasını buradan okur. Depoda hiçbir gizli bilgi bulunmaz.
2. **GitHub'a gizli değerleri gir:** Settings → Secrets and variables → Actions yolunu izle ve şunları ekle:
   - `GEMINI_API_KEY`
   - `TELEGRAM_TOKEN`
   - `TELEGRAM_CHAT_ID` (Telegram kullanıcı numaran)
   - `BOT_ANAHTAR` (Cloudflare'deki WEBHOOK_SECRET ile aynı değer; oyları okumak için)
   - İsteğe bağlı olarak `NCBI_EMAIL`
   - İsteğe bağlı yedek yapay zekâ anahtarları: `GROQ_API_KEY`, `CEREBRAS_API_KEY`, `OPENROUTER_API_KEY`
3. **Cloudflare Worker:** Workers & Pages → Create → Import a repository yolunu izle. Bu depoyu seç ve kök klasör olarak `worker` yaz.
   - Settings → Variables and Secrets altına **Secret** olarak şunları ekle: `TELEGRAM_TOKEN`, `GEMINI_API_KEY`, `WEBHOOK_SECRET` (kendi uydurduğun uzun bir parola), `IZINLI_KULLANICI`, isteğe bağlı `GROQ_API_KEY` ve `NOTION_TOKEN` (Notion entegrasyon anahtarı; Okuma Arşivi ve İçerik Havuzu veritabanları bu entegrasyonla paylaşılmalı).
4. **Webhook'u bağla:** Tarayıcıda `https://<worker-adresin>/kurulum?anahtar=<WEBHOOK_SECRET>` adresini bir kez aç.
5. **İlk listeyi oluştur:** GitHub'da Actions → Haftalık hazırlık → Run workflow yolunu izle. Gündem için Actions → Haftalık gündem → Run workflow.

## Elle deneme (isteğe bağlı)

```bash
cd motor
python hazirla.py --alan kolorektal --girdi test_verisi/kolorektal_2026-09-29.xml --sahte-ozet --bildirim-yok
python gundem.py --sahte-ozet --bildirim-yok   # gündem, yapay zekâsız
python -m unittest test_motor                  # birim testleri
cd ../worker && node test/sahte_test.mjs
```
