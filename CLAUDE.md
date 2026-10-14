# Cerrahi Literatür Botu — Claude Code için proje bağlamı

> **Not (14 Ekim 2026):** Bu dosya eski kopyadan (`Belgeler\cerrahi-literatur-botu-ESKI`, 29 Eylül 2026) taşındı ve o tarihten sonra güncellenmedi. Çelişki olursa `README.md`, kod ve `git log` geçerlidir.

Genel cerrahinin 14 alt alanında her hafta öne çıkan makaleleri seçip Telegram'da Türkçe özetleriyle sunan kişisel bot. Sahibi Ahmet (yeni mezun doktor). Sistem canlıda; kod ve kararlar bu klasörde.

- Ayrıntılı kararlar ve gerekçeleri: `docs/KARARLAR.md` (bir şeyi değiştirmeden önce oku)
- Geliştirme geçmişi: `docs/GECMIS.md`
- Kurulum ve puanlama özeti: `README.md`

## İletişim
- Ahmet ile Türkçe konuş. Kod içi adlar, yorumlar ve commit mesajları da Türkçe (mevcut üslupla aynı: kısa, "ne değişti" odaklı).
- Ahmet yazılımcı değil; açıklamaları sade tut, komutları kopyalanabilir ver.

## Yapı
| Yol | Ne |
|---|---|
| `motor/config.py` | Ayarlar: dergi kademeleri, puanlar, 14 alanın arama terimleri, dışlanan branşlar, geniş dergiler, aday sayısı (12), pencere (7 gün) |
| `motor/pubmed.py` | PubMed E-utilities sorguları ve XML ayrıştırma |
| `motor/puanlama.py` | Dergi + çalışma tipi puanı, kişisel puan (oylardan), ilk N seçimi |
| `motor/ozetleyici.py` | Gemini ile kısa Türkçe özet + cerrahi ilgi puanı; yedek model zinciri |
| `motor/motor.py` | Bir alanı hazırlar; Türk dergisi satırını seçer (`cikti/turk_gosterilen.json` tekrarı önler) |
| `motor/hazirla.py` | Giriş noktası: 14 alanı dolaşır, oyları botun `/geri-bildirim` ucundan çeker, `cikti/hafta.json` yazar, Telegram'a "liste hazır" bildirir |
| `worker/src/index.js` | Telegram botu (Cloudflare Worker): menüler, ayrıntılı özet, 👍/👎, Notion arşiv/içerik, soru-cevap, KV önbelleği |
| `worker/wrangler.toml` | Worker ayarları: VERI_URL, Notion veritabanı kimlikleri, KV bağlaması |
| `worker/test/sahte_test.mjs` | Worker'ı sahte Telegram/Gemini/GitHub/Notion ile uçtan uca dener |
| `.github/workflows/haftalik.yml` | Pazartesi 04:00 UTC (07:00 TR) çalışan haftalık hazırlık |
| `cikti/` | Haftalık çıktı; **GitHub Actions yazar**, elle düzenleme |

## Çalıştırma ve test (ağ ve anahtar gerektirmez)
```bash
pip install -r motor/requirements.txt
cd motor
python hazirla.py --alan kolorektal --girdi test_verisi/kolorektal_2026-09-29.xml --sahte-ozet --bildirim-yok
cd ../worker
node test/sahte_test.mjs
```
Not: Birinci komut `cikti/hafta.json` ve `cikti/turk_gosterilen.json` dosyalarını değiştirir. Deneme sonrası bu değişiklikleri commit'leme: `git checkout -- cikti/`.

Her kod değişikliğinden sonra iki testi de çalıştır; ikisi de geçmeden push etme.

## Yayına çıkış
- `main`'e push → Cloudflare Worker otomatik güncellenir (Cloudflare'in GitHub bağlantısı, kök klasör `worker`).
- Motor değişiklikleri bir sonraki pazartesi ya da GitHub'da Actions → Haftalık hazırlık → Run workflow ile çalışır.
- Actions her çalıştığında `cikti/` altına commit atar. Push etmeden önce daima `git pull --rebase origin main`.

## Kurallar
- Depo **herkese açık**. Anahtar, token, Telegram ID ya da parola asla koda, commit'e veya bu dosyaya yazılmaz. Gizli değerler:
  - GitHub Actions secrets: `GEMINI_API_KEY`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, `BOT_ANAHTAR`, isteğe bağlı `NCBI_EMAIL`, `NCBI_API_KEY`; değişken `GEMINI_MODEL`
  - Cloudflare Worker secrets: `TELEGRAM_TOKEN`, `GEMINI_API_KEY`, `WEBHOOK_SECRET`, `IZINLI_KULLANICI`, `NOTION_TOKEN`
  - Yerel deneme için `.dev.vars` / `.env` kullan (ikisi de `.gitignore`'da).
- Gemini **ücretsiz katman**: çağrı sayısını artıran değişikliklerde kotayı düşün; yedek model zincirini koru.
- Özet dili Türkçe, İngilizce tıbbi terimler korunur; sayılar rakamla, etki büyüklükleri (RR, HR, %95 CI) özetlerde yer alır.
- Bot yalnızca `IZINLI_KULLANICI` ID'sine cevap verir; bu kontrolü gevşetme.
- Puanlama/filtre kurallarını değiştirirken `docs/KARARLAR.md`'deki gerekçelere uy; karar değişirse o dosyayı da güncelle.

## Git bağlantısı (bu klasör claude.ai'dan indirildiyse)
Bu klasör depodaki dosyaların kopyasıdır; `.git` klasörü yoksa GitHub'a bağlamak için bir kez:
```bash
git init -b main
git remote add origin https://github.com/akifokuyucu/cerrahi-literatur-botu.git
git fetch origin
git reset origin/main
```
`reset` dosyalara dokunmaz, yalnızca geçmişi bağlar. `CLAUDE.md` ve `docs/` depoda yok; eklemek ya da yerel tutmak Ahmet'in kararı (içlerinde gizli bilgi yok).

## Sıradaki iş
Haber ve gelişmeler modülü: kılavuzlar, kongreler, FDA/CE onayları, ClinicalTrials.gov, yerli duyurular. Karar: önce birkaç hafta mevcut botu kullanıp eksikleri görmek. Ayrıntı `docs/KARARLAR.md` → "Sonraki adımlar".
