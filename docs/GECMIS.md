# Geliştirme geçmişi

> **Not (14 Ekim 2026):** Bu dosya eski kopyadan (`Belgeler\cerrahi-literatur-botu-ESKI`, 29 Eylül 2026) taşındı ve o tarihten sonra güncellenmedi. Çelişki olursa `README.md`, kod ve `git log` geçerlidir.

Depodaki commit'lerden derlendi (en eskiden en yeniye). Hepsi 29 Eylül 2026. "Haftalık liste" commit'leri GitHub Actions'ın deneme çalıştırmalarıdır ve burada ayrıca listelenmedi.

## İlk sürüm
- Kaynak motoru (PubMed), özetleyici (Gemini), Telegram botu (Cloudflare Worker) ve haftalık iş akışı.

## Kararlılık ve Gemini
- Gemini model varsayılanı belirlendi; Transplantasyon ve MIS alanlarında isabet artırıldı; tarama sınırı eklendi.
- Worker günlükleri (Observability) açıldı.
- İş akışı, sonucu kaydetmeden önce depodaki yeni değişiklikleri çekecek şekilde düzeltildi.
- Gemini: RetryInfo'ya göre bekleme, günlük kota ve hata mesajları, canlı log.
- Gemini yoğunken yedek modellere geçiş (hem Python hem bot). Zincir: gemini-flash-latest → gemini-flash-lite-latest → gemini-2.5-flash → gemini-2.5-flash-lite.

## Özet kalitesi ve seçim
- Özet talimatı: sayılar rakamla, etki büyüklüğü zorunlu.
- Deneme çalıştırmalarının Türk dergisi kayıtları sıfırlandı.
- Geniş kapsamlı dergiler bir alana otomatik girmez; PubMed geçici hatalarında yeniden deneme.

## 1. grup iyileştirmeler
- Cerrahi ilgi filtresi, Acil Cerrahi için TJTES, ayrıntılı özet önbelleği (KV).
- Aynı hafta için Türk dergisi seçimleri sıfırlandı.
- Cerrahi ilgi ölçütü daha katı hale getirildi, aday sayısı 12'ye çıktı; travma terimleri düzeltildi.
- Göz, jinekoloji, üroloji ve baş-boyun makaleleri dışlandı.

## 2. grup iyileştirmeler
- Geri bildirim (👍/👎), Notion Okuma Arşivi, İçerik Havuzu köprüsü, soru sorma, kişisel puan.
- Test: Türk dergisi tuşu olduğunda da geçsin.
- Ayrıntılı özet: PICO alanları için net talimat. (Son commit: 4379ce9)
