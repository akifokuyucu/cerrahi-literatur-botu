# Cerrahi Literatür Botu: kararlar ve durum

> **Not (14 Ekim 2026):** Bu dosya eski kopyadan (`Belgeler\cerrahi-literatur-botu-ESKI`, 29 Eylül 2026) taşındı ve o tarihten sonra güncellenmedi. Çelişki olursa `README.md`, kod ve `git log` geçerlidir.

Son güncelleme: 29 Eylül 2026. Kaynak: claude.ai "Saha Analizi" projesindeki çalışma ve karar notları.

## Amaç
İnternetteki genel cerrahi ile ilgili bilimsel, teknolojik, yerli ve yabancı makaleleri, haberleri ve gelişmeleri araştırıp özet olarak sunan bir araç. İlk aşama: haftalık makale botu (bu depo). İkinci aşama: haber ve gelişmeler modülü.

## Başlangıç kararları
- Genel cerrahinin güncel/trend makaleleri düzenli takip edilecek; araç Telegram botu olacak.
- **"Öne çıkan" makale:** Ağırlığı yüksek olan makale. Yani yüksek ağırlıklı bir dergide çıkmış ya da meta-analiz gibi güçlü bir çalışma tipinde olmalı.
- Yapay zekâ API'sinde **ücretsiz katmanla** başlanacak (Gemini).
- Kurulum: Telegram botu BotFather'dan açıldı. Gemini API anahtarı alındı. GitHub deposu (akifokuyucu/cerrahi-literatur-botu, public) oluşturuldu.

## Konsept
- Telegram botu. `/start` ile 14 alt alanın butonları gelir. Bir alan seçilince o haftanın öne çıkan 5 makalesi kısa Türkçe özetleriyle listelenir. 📄 tuşu makalenin ayrıntılı özetini getirir: PICO, bulgular, sınırlılıklar, pratiğe etkisi, journal club soruları.
- Ayrıntılı özetin altındaki tuşlar:
  - **👍 / 👎:** Oy kaydedilir ve sonraki haftaların sıralamasına kişisel katkı olarak eklenir.
  - **📌 Arşive ekle:** Makaleyi Notion'daki Okuma Arşivi'ne ekler.
  - **📸 İçerik adayı:** Makaleyi Notion'daki İçerik Havuzu'na "fikir" olarak ekler.
  - **❓ Soru sor:** Makale metnine dayalı soru-cevap açar.
- Komutlar: `/gundem` (tüm alanlardan en yüksek puanlı 5 makale), `/istatistik` (oyların özeti), `/iptal` (soru modunu kapatır).
- Hazırlık her pazartesi 07:00'de yapılır; bitince "liste hazır" bildirimi gelir.
- Özet dili Türkçe, İngilizce tıbbi terimler korunur. Sayılar rakamla yazılır; etki büyüklükleri (RR, HR, %95 CI vb.) özetlere eklenir.
- Yapay zekâ olarak Gemini ücretsiz katmanı kullanılıyor. Ana model yoğunsa sistem kendiliğinden yedek modele geçer.

## Alanlar (14)
Kolorektal, Hepatobilier, Pankreas, Üst GİS, Bariatrik, Meme, Herni & Karın Duvarı, Transplantasyon, Onkoloji, Acil Cerrahi, MIS/Robotik/Endoskopi, Eğitim & Simülasyon, AI & Dijital Cerrahi, Cerrahi Enfeksiyonlar.

Liste Ahmet'in kendi seçimi. Onkoloji alanı yalnızca diğer alanlara girmeyen konuları kapsar: periton, sarkom, melanom, retroperiton. Organ bazlı onkoloji kendi alanında kalır.

## Puanlama ve filtreler
- **Dergi puanı:**
  - Kademe 1 = 3 puan (NEJM, Lancet, JAMA, BMJ, Nat Med ve alanın zirve dergileri)
  - Kademe 2 = 2 puan (Ann Surg, JAMA Surg, BJS, JACS)
  - Kademe 3 = 1 puan (geniş kapsamlı cerrahi dergiler ve alan dergileri)
  - Listede olmayan dergi = 0 puan (elenmez)
- **Çalışma tipi puanı:** Kılavuz 4, meta-analiz/sistematik derleme 3, RCT 3, prospektif/Delphi 2, retrospektif ve diğer 1.
- **Kişisel puan:** Bir dergi ya da çalışma tipi için verilen her net oy ±0,25 puan eder. Dergi ve tip başına en fazla ±0,5 eklenir. Bu puan yalnızca sıralamayı etkiler; listede görünen puan değişmez.
- **Elenenler:** Olgu sunumu, editoryal, yorum, mektup, bildiri, özeti olmayan kayıtlar ve çalışma protokolleri. Hayvan deneyleri elenmez, 1 puan alır.
- **Başka branşlar:** Başlığında ortopedi, jinekoloji, üroloji, göz, KBB ya da kalp-göğüs konusu geçen makaleler hiçbir alana girmez.
- **Geniş kapsamlı dergiler** (Ann Surg Oncol, EJSO vb.) puan alır, ama makaleleri bir alana ancak o alanın terimleriyle eşleşirse girer.
- **Transplantasyon:** Terimler yalnızca başlıkta aranır.
- **Cerrahi ilgi filtresi:** Her alanda en yüksek puanlı 12 aday Gemini'ye gönderilir. Gemini her birine ilgi puanı verir: 2 = doğrudan ilgili, 1 = dolaylı ilgili, 0 = ilgisiz. 0 alanlar elenir; kalanlardan puan sırasıyla ilk 5 gösterilir.
- **Eklenmeyen dergiler:** Cochrane, BJS Open ve Ann Surg Open (Ahmet'in kararı). Metodolojik derlemeler listede kalabilir.
- **Türk dergisi satırı:** Turkish J Surg'dan gelir; Acil Cerrahi alanında ayrıca TJTES taranır. Bu satır puanlanmaz ve aynı makale iki kez gösterilmez.

## Mimari
- **Depo:** github.com/akifokuyucu/cerrahi-literatur-botu (herkese açık).
- **Haftalık hazırlık:** GitHub Actions üzerinde çalışır ve sonucu `cikti/hafta.json` dosyasına yazar.
  - Gizli değerler: GEMINI_API_KEY, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, BOT_ANAHTAR.
  - Oyları botun `/geri-bildirim` adresinden okur.
- **Bot:** Cloudflare Worker, adresi cerrahi-literatur-botu.akif-okuyucu.workers.dev.
  - GitHub'a yüklenen her değişiklik otomatik olarak yayına çıkar.
  - Gizli değerler: TELEGRAM_TOKEN, GEMINI_API_KEY, WEBHOOK_SECRET, IZINLI_KULLANICI, NOTION_TOKEN.
  - Ayrıntılı özetler, oylar ve Notion kayıtları KV'de (cerrahi-literatur-onbellek) tutulur. Ayrıntılı özetler 120 gün saklanır.
  - Bot yalnızca Ahmet'in Telegram ID'sine cevap verir.
- **Notion:** "Literatür Botu" entegrasyonu iki veritabanına bağlı: HOME altındaki 📚 Okuma Arşivi ve İçerik Merkezi altındaki İçerik Havuzu. İçerik Havuzu'na eklenen kayıtlarda köken "Literatür botu" olarak görünür.
- **Tam metin:** Açık erişimli makalelerde metin Europe PMC'den alınır. Diğerlerinde yalnızca özet (abstract) kullanılır ve bot bunu belirtir.

## Durum (29 Eylül 2026)
- Sistem canlıda. İlk haftalık liste (22–29 Eylül) hazırlandı.
- 1. grup iyileştirmeler tamamlandı: KV önbelleği, cerrahi ilgi filtresi, Acil için TJTES.
- 2. grup iyileştirmeler tamamlandı: 👍/👎 ve kişisel puan, Notion Okuma Arşivi, İçerik Havuzu köprüsü, soru sorma. Gerçek kullanımda denendi ve çalışıyor.

## 🌍 Dünya brifingi (14 Ekim 2026)
- Ahmet'in isteği: ABD, Çin ve yurtdışından önemli sosyolojik, tıbbi ve teknolojik haberler haftalık brifing olarak Telegram'dan gelsin.
- Kapsam (Ahmet'in seçimi): sağlık politikası ve sistemleri; tıp teknolojisi ve yapay zekâ; toplum ve sosyoloji; genel teknoloji ve jeopolitik (ABD–Çin rekabeti dahil).
- Gün: cumartesi 08:00 (pazartesi makaleler, perşembe gündem; yük ve okuma dağılsın).
- **Yapay zekâ: şimdilik ücretsiz zincir** (Gemini → Groq/Cerebras/OpenRouter). Ahmet Claude Haiku (ücretli API, tahminen ayda 15 sentin altında) önerisini şimdilik istemedi; ücretsiz katman ilkesi sürüyor. İleride istenirse Haiku `motor/llm.py` zincirine bir sağlayıcı olarak eklenir.
- Haberler RSS ve Google Haberler'den toplanır; yapay zekâya internette arama yaptırılmaz (ücretsiz, kaynaklar belli ve tekrarlanabilir).
- Ana başlıklar yalnızca seçilen haberlere dayanabilir (id ile); kaynaksız başlık atılır.

## Sonraki adımlar
- **Haber ve gelişmeler modülü:** kılavuzlar, kongreler, FDA/CE onayları, ClinicalTrials.gov, yerli duyurular.
- Önce birkaç hafta kullanılıp eksikler görülecek.
