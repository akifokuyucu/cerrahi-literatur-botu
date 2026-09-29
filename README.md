# Cerrahi Literatür Botu

Genel cerrahinin 14 alt alanında her hafta öne çıkan makaleleri seçip Telegram'da sunan kişisel bot. Perşembeleri ayrıca cerrahi haberlerini ve gelişmeleri (📰 Gündem) derler.

- **Her pazartesi 07:00:** GitHub Actions, PubMed'deki son 7 günün makalelerini tarar ve dergi ağırlığı ile çalışma tipine göre puanlar. Her alanda en iyi 5 makaleyi seçer, Turkish Journal of Surgery'den bir makale ekler, Gemini ile Türkçe kısa özetlerini yazar ve sonucu `cikti/hafta.json` dosyasına kaydeder.
- **Her perşembe 07:00 (📰 Gündem):** GitHub Actions dört bölüm hazırlar ve sonucu `cikti/gundem.json` dosyasına kaydeder:
  - 📘 Kılavuz & Kongre: WSES, ESCP ve ASCRS haber sayfaları, EAES ve SAGES RSS akışları, Google Haberler
  - 🤖 Teknoloji & Onaylar: FDA 510(k) kararları (openFDA), FDA/CE onayı, cerrahi robotik ve yapay zekâ haberleri
  - 🇹🇷 Türkiye: Türk Cerrahi Derneği, TTB ve ulusal kongre haberleri
  - 🧪 Yeni RCT'ler: ClinicalTrials.gov'a o hafta kaydedilen cerrahi randomize çalışmalar

  Adaylar Gemini'nin genel cerrahi süzgecinden geçer; tanıtım, borsa ve başka branş haberleri elenir. Kalanlara Türkçe başlık ve kısa özet yazılır. Dernek sayfalarında yalnızca önceki haftadan sonra eklenen bağlantılar alınır. Daha önce gösterilen haberler `cikti/gundem_gorulen.json` sayesinde tekrar gelmez.
- **Telegram'da:** `/start` → alan seç → 5 makale ve kısa özetleri görünür → 📄 tuşuna basınca ayrıntılı özet gelir. Makale açık erişimliyse ayrıntılı özet tam metinden, değilse özetten (abstract) hazırlanır.
- Ayrıntılı özetin altında: **👍 / 👎** (oylar sonraki haftaların puanlamasına küçük bir kişisel katkı ekler), **📌 Arşive ekle** (Notion Okuma Arşivi), **📸 İçerik adayı** (Notion İçerik Havuzu'na "fikir"), **❓ Soru sor** (makale metnine dayalı soru-cevap; /iptal ile çıkılır). `/istatistik` oyların özetini gösterir. `/gundem` ya da menüdeki **📰 Gündem** tuşu haber bölümlerini açar. `/onecikanlar` ya da **🔥 Haftanın öne çıkanları** tuşu tüm alanlardan en yüksek puanlı 5 makaleyi gösterir.
- Bot yalnızca sahibine cevap verir.

## Klasörler

| Klasör | Ne işe yarar |
|---|---|
| `motor/config.py` | **Ayarlar:** dergi kademeleri, puanlar, alan arama terimleri |
| `motor/` | PubMed'den çekme, puanlama, özetleme (Python) |
| `motor/gundem.py` | 📰 Gündem: haber kaynaklarını tarama ve süzme (kaynak listesi `config.py` içinde) |
| `worker/` | Telegram botu (Cloudflare Worker, JavaScript) |
| `cikti/` | Haftalık sonuç dosyası (otomatik oluşur) |
| `.github/workflows/haftalik.yml` | Pazartesi zamanlaması (makaleler) |
| `.github/workflows/gundem.yml` | Perşembe zamanlaması (gündem) |

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

**Cerrahi ilgi filtresi:** Her alanda en yüksek puanlı 12 aday Gemini'ye gönderilir. Gemini, genel cerrahi pratiğiyle ilgisiz bulduklarını (cerrahi bağlamı olmayan radyoterapi/ilaç çalışması, temel bilim, başka branş) eler. Kalanlardan puan sırasıyla ilk 5 gösterilir.

**Türk dergisi satırı:** Turkish Journal of Surgery; Acil Cerrahi alanında ayrıca Ulusal Travma ve Acil Cerrahi Dergisi (TJTES).

**Kişisel puan:** Bottaki her net 👍/👎, o dergi ve çalışma tipi için ±0,25 puan; dergi ve tip başına en fazla ±0,5. Yalnızca sıralamayı etkiler, gösterilen puan değişmez.

**Elenenler:** Olgu sunumu, editoryal, yorum, mektup, kongre bildirisi, özeti olmayan kayıtlar ve çalışma protokolleri listeye girmez. Hayvan deneyleri 1 puan alır.

## Kurulum

1. **GitHub:** Bu depo herkese açık (public) olmalı. Bot, `cikti/hafta.json` dosyasını buradan okur. Depoda hiçbir gizli bilgi bulunmaz.
2. **GitHub'a gizli değerleri gir:** Settings → Secrets and variables → Actions yolunu izle ve şunları ekle:
   - `GEMINI_API_KEY`
   - `TELEGRAM_TOKEN`
   - `TELEGRAM_CHAT_ID` (Telegram kullanıcı numaran)
   - `BOT_ANAHTAR` (Cloudflare'deki WEBHOOK_SECRET ile aynı değer; oyları okumak için)
   - İsteğe bağlı olarak `NCBI_EMAIL`
3. **Cloudflare Worker:** Workers & Pages → Create → Import a repository yolunu izle. Bu depoyu seç ve kök klasör olarak `worker` yaz.
   - Settings → Variables and Secrets altına **Secret** olarak şunları ekle: `TELEGRAM_TOKEN`, `GEMINI_API_KEY`, `WEBHOOK_SECRET` (kendi uydurduğun uzun bir parola), `IZINLI_KULLANICI` ve `NOTION_TOKEN` (Notion entegrasyon anahtarı; Okuma Arşivi ve İçerik Havuzu veritabanları bu entegrasyonla paylaşılmalı).
4. **Webhook'u bağla:** Tarayıcıda `https://<worker-adresin>/kurulum?anahtar=<WEBHOOK_SECRET>` adresini bir kez aç.
5. **İlk listeyi oluştur:** GitHub'da Actions → Haftalık hazırlık → Run workflow yolunu izle. Gündem için Actions → Haftalık gündem → Run workflow.

## Elle deneme (isteğe bağlı)

```bash
cd motor
python hazirla.py --alan kolorektal --girdi test_verisi/kolorektal_2026-09-29.xml --sahte-ozet --bildirim-yok
python gundem.py --sahte-ozet --bildirim-yok   # gündem, Gemini'siz
cd ../worker && node test/sahte_test.mjs
```
