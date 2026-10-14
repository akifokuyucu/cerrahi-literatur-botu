# Cerrahi Literatür Botu — Claude Code için proje bağlamı

> **Son güncelleme: 14 Ekim 2026.** Çelişki olursa `README.md`, kod ve `git log` geçerlidir.

Kişisel Telegram botu. Sahibi Ahmet (yeni mezun doktor). Sistem canlıda; kod ve kararlar bu klasörde. Üç haftalık modül:
- **Pazartesi 07:00:** genel cerrahinin 14 alt alanında öne çıkan makaleler (PubMed), Türkçe kısa ve ayrıntılı özetlerle
- **Perşembe 07:00 · 📰 Gündem:** kılavuz/kongre, teknoloji/onaylar, Türkiye, yeni RCT'ler
- **Cumartesi 08:00 · 🌍 Dünya brifingi:** ABD, Çin ve dünyadan sağlık politikası, tıp teknolojisi, toplum, teknoloji/jeopolitik

Belgeler:
- Ayrıntılı kararlar ve gerekçeleri: `docs/KARARLAR.md` (bir şeyi değiştirmeden önce oku)
- Geliştirme geçmişi: `docs/GECMIS.md`
- Kurulum ve puanlama özeti: `README.md`

## İletişim
- Ahmet ile Türkçe konuş. Kod içi adlar, yorumlar ve commit mesajları da Türkçe (mevcut üslupla aynı: kısa, "ne değişti" odaklı).
- Ahmet yazılımcı değil; açıklamaları sade tut, komutları kopyalanabilir ver.
- Klinik kararlar (hangi makale "olmalı", hangi branş dışlanır, hangi dergi puan alır) Ahmet'indir: öner, ölç, onaylatmadan kural yapma.

## Yapı
| Yol | Ne |
|---|---|
| `motor/config.py` | Bütün ayarlar: dergi kademeleri, puanlar, 14 alanın terimleri, dışlanan branşlar, SJR/editoryal/çocuk/yapay zekâ ağırlıkları, gündem ve dünya brifingi kaynakları |
| `motor/pubmed.py` | PubMed sorguları ve XML ayrıştırma (MeSH, editoryal, NCT, ISSN dahil) |
| `motor/puanlama.py` | Dergi + çalışma tipi + editoryal puanı, alan uyumu ve alanlar arası dağıtım, yapay zekâ puanı, kişisel puan (oy + dolaylı ilgi) |
| `motor/ozetleyici.py` | Kısa Türkçe özet + cerrahi ilgi, alan uyumu, pratiğe etki (0–2); `SahteGemini` test için |
| `motor/llm.py` | Yapay zekâ sağlayıcı zinciri (Gemini → Groq/Cerebras/OpenRouter → Ollama) |
| `motor/denetim.py` | Özetlerde kaynakta olmayan sayıları yakalar |
| `motor/motor.py` | Bir alanı tarar ve puanlar; Türk dergisi satırı |
| `motor/hazirla.py` | Pazartesi giriş noktası: tara → alanlara dağıt → özetle → `cikti/hafta.json`, `detay.json`, aday arşivi |
| `motor/detay.py` · `motor/yoktez.py` | Ayrıntılı özetler · her alana bir YÖK tezi |
| `motor/gundem.py` · `motor/dunya.py` | 📰 Gündem (perşembe) · 🌍 Dünya brifingi (cumartesi) |
| `motor/arsiv.py` · `motor/altin_liste.json` | Aday arşivi; kural değişikliklerini geçmiş haftalarda ölçme (`python arsiv.py ../cikti/aday_arsivi/*.json.gz --ozet`) |
| `motor/sjr.py` · `motor/veri/sjr.json` | SJR çeyreklik tablosu (yılda bir, elle indirilen CSV'den) |
| `motor/test_motor.py` | Python birim testleri |
| `worker/src/index.js` | Telegram botu (Cloudflare Worker): menüler, ayrıntılı özet, 👍/👎, dolaylı ilgi (`/git`, `/ilgi`), Notion, soru-cevap, gündem ve dünya ekranları |
| `worker/test/sahte_test.mjs` | Worker'ı sahte Telegram/Gemini/GitHub/Notion ile uçtan uca dener |
| `.github/workflows/` | `haftalik.yml` (pazartesi), `gundem.yml` (perşembe), `dunya.yml` (cumartesi); hepsi başarısız olursa Telegram'a bildirir |
| `cikti/` | Haftalık çıktı ve aday arşivi; **GitHub Actions yazar**, elle düzenleme |

## Çalıştırma ve test (ağ ve anahtar gerektirmez)
```bash
pip install -r motor/requirements.txt
cd motor
python -m unittest test_motor
cd ../worker
node test/sahte_test.mjs
```
Her kod değişikliğinden sonra iki testi de çalıştır; ikisi de geçmeden push etme.

Elle deneme komutları (`hazirla.py`, `gundem.py`, `dunya.py` için `--sahte-ozet --bildirim-yok`) `cikti/` dosyalarını ezer: deneme sonrası `git checkout -- cikti/` ile geri al, yeni oluşan dosyaları sil; commit'leme.

Bash'te heredoc içinde ters eğik çizgi teke iniyor: içinde `\` olan kodu Edit/Write ile yaz.

## Yayına çıkış
- `main`'e push → Cloudflare Worker otomatik güncellenir (Cloudflare'in GitHub bağlantısı, kök klasör `worker`).
- Motor değişiklikleri bir sonraki zamanlanmış çalışmada ya da GitHub'da Actions → (iş akışı) → Run workflow ile çalışır.
- Actions her çalıştığında `cikti/` altına commit atar. Push etmeden önce daima `git pull --rebase origin main`.
- Puanlama değişikliğinden önce ve sonra arşiv ölçümünü çalıştır; sonucu Ahmet'e sayılarla bildir.

## Kurallar
- Depo **herkese açık**. Anahtar, token, Telegram ID ya da parola asla koda, commit'e veya bu dosyaya yazılmaz. Gizli değerler:
  - GitHub Actions secrets: `GEMINI_API_KEY`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, `BOT_ANAHTAR`; isteğe bağlı `GROQ_API_KEY`, `CEREBRAS_API_KEY`, `OPENROUTER_API_KEY`, `NCBI_EMAIL`, `NCBI_API_KEY`; değişkenler `GEMINI_MODEL`, `LLM_ZINCIRI`
  - Cloudflare Worker secrets: `TELEGRAM_TOKEN`, `GEMINI_API_KEY`, `WEBHOOK_SECRET`, `IZINLI_KULLANICI`, `NOTION_TOKEN`; isteğe bağlı `GROQ_API_KEY`, geçici `KURULUM_ANAHTARI`
  - Yerel deneme için `.dev.vars` / `.env` kullan (ikisi de `.gitignore`'da).
- Yapay zekâ **ücretsiz katmanla** (Gemini ve ücretsiz yedekler). Çağrı sayısını artıran değişikliklerde kotayı düşün; yedek zinciri koru. Ücretli API (ör. Claude Haiku) Ahmet'in 14 Ekim 2026 kararıyla şimdilik yok.
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
`reset` dosyalara dokunmaz, yalnızca geçmişi bağlar.

## Sıradaki iş
- 19 Ekim pazartesi listesi: yeni puanlama kurallarının yapay zekâlı ilk gerçek çalışması. Arşiv ölçümüyle doğrula (rotasyonplasti ve yüz travması hatası elendi mi, CRS-HIPEC geri geldi mi).
- 17 Ekim cumartesi: ilk dünya brifingi; seçim ve dil kalitesine Ahmet'le bak.
- `motor/altin_liste.json` "olmalı" seçimleri Claude'un tahmini; Ahmet onaylamadı.
- Önerilip bekleyen: push öncesi testleri çalıştıran hook; `/hafta-incele`, `/olc`, `/kaynak-dene` skill'leri; aylık okuma özeti; brifingi Notion'a ekleme.
