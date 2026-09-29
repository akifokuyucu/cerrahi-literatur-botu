# Cerrahi Literatür Botu

Genel cerrahinin 14 alt alanında her hafta öne çıkan makaleleri seçip Telegram'da sunan kişisel bot.

- **Her pazartesi 07:00:** GitHub Actions, PubMed'deki son 7 günün makalelerini tarar ve dergi ağırlığı ile çalışma tipine göre puanlar. Her alanda en iyi 5 makaleyi seçer, Turkish Journal of Surgery'den bir makale ekler, Gemini ile Türkçe kısa özetlerini yazar ve sonucu `cikti/hafta.json` dosyasına kaydeder.
- **Telegram'da:** `/start` → alan seç → 5 makale ve kısa özetleri görünür → 📄 tuşuna basınca ayrıntılı özet gelir. Makale açık erişimliyse ayrıntılı özet tam metinden, değilse özetten (abstract) hazırlanır.
- Bot yalnızca sahibine cevap verir.

## Klasörler

| Klasör | Ne işe yarar |
|---|---|
| `motor/config.py` | **Ayarlar:** dergi kademeleri, puanlar, alan arama terimleri |
| `motor/` | PubMed'den çekme, puanlama, özetleme (Python) |
| `worker/` | Telegram botu (Cloudflare Worker, JavaScript) |
| `cikti/` | Haftalık sonuç dosyası (otomatik oluşur) |
| `.github/workflows/haftalik.yml` | Pazartesi zamanlaması |

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

**Elenenler:** Olgu sunumu, editoryal, yorum, mektup, kongre bildirisi, özeti olmayan kayıtlar ve çalışma protokolleri listeye girmez. Hayvan deneyleri 1 puan alır.

## Kurulum

1. **GitHub:** Bu depo herkese açık (public) olmalı. Bot, `cikti/hafta.json` dosyasını buradan okur. Depoda hiçbir gizli bilgi bulunmaz.
2. **GitHub'a gizli değerleri gir:** Settings → Secrets and variables → Actions yolunu izle ve şunları ekle:
   - `GEMINI_API_KEY`
   - `TELEGRAM_TOKEN`
   - `TELEGRAM_CHAT_ID` (Telegram kullanıcı numaran)
   - İsteğe bağlı olarak `NCBI_EMAIL`
3. **Cloudflare Worker:** Workers & Pages → Create → Import a repository yolunu izle. Bu depoyu seç ve kök klasör olarak `worker` yaz.
   - Settings → Variables and Secrets altına **Secret** olarak şunları ekle: `TELEGRAM_TOKEN`, `GEMINI_API_KEY`, `WEBHOOK_SECRET` (kendi uydurduğun uzun bir parola) ve `IZINLI_KULLANICI`.
4. **Webhook'u bağla:** Tarayıcıda `https://<worker-adresin>/kurulum?anahtar=<WEBHOOK_SECRET>` adresini bir kez aç.
5. **İlk listeyi oluştur:** GitHub'da Actions → Haftalık hazırlık → Run workflow yolunu izle.

## Elle deneme (isteğe bağlı)

```bash
cd motor
python hazirla.py --alan kolorektal --girdi test_verisi/kolorektal_2026-09-29.xml --sahte-ozet --bildirim-yok
cd ../worker && node test/sahte_test.mjs
```
