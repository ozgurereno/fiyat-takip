# Amazon Fiyat Takip – proje notları

Kişisel fiyat takip sistemi. Home Assistant OS çalışan bir Raspberry Pi 5 üzerinde **Home Assistant uygulaması (eski adıyla eklenti)** olarak çalışır; bildirimler Telegram botu ve Home Assistant iPhone uygulamasının kritik uyarıları üzerinden gelir.

## Yapı

- `fiyat_takip/` – Home Assistant uygulaması (bu klasör HA'ya kopyalanır / depodan kurulur)
  - `takip.py` – ana döngü, site okuyucuları, Telegram bot komutları
  - `grup.py` – Telethon ile kullanıcının kendi hesabından Telegram grup dinleme
  - `config.yaml` – HA uygulama tanımı; **her yayında `version` artırılmalı**, yoksa HA güncelleme göstermez
  - `Dockerfile` – `ghcr.io/home-assistant/base` üzerine Alpine paketleri; Telethon `<2` sabit (v2 API'si farklı)
  - `DOCS.md` – HA arayüzünde görünen kullanıcı belgesi (Türkçe)
- `tests/` – bağımsız test betikleri; ağa çıkmaz, sahte `requests` cevapları ve `tests/fixtures/` içindeki gerçek kaydedilmiş sayfalarla çalışır

## Çalışma kuralları

- Kullanıcıya giden tüm metinler (bot mesajları, DOCS.md) **Türkçe**.
- Telegram mesajları `parse_mode=HTML`: kullanıcı/site kaynaklı her metin `html.escape` ile kaçırılmalı.
- Testler: her değişiklikten sonra `for f in tests/test_*.py; do python3 $f || break; done`. Hepsi son satırda "GEÇTİ" yazmalı.
- Site okuyucusu eklerken önce gerçek sayfayı `tests/fixtures/` altına kaydet, okuyucuyu ona karşı test et.
- Siteye istek sıklığını artıran değişikliklerden kaçın; varsayılan aralıklar engellenmemek için bilerek yüksek.
- **Gizli bilgiler asla depoya girmez**: bot token, api_id/api_hash, telefon, 2FA şifresi, `telegram_oturum.txt`, `cerezler.json`, `durum.json`. Bunlar HA'da `/data` altında ya da yerelde `.gitignore`'daki dosyalarda durur.

## Veri dosyaları (HA'da /data, yerelde betiğin klasörü)

`options.json`/`ayarlar.json` ayarlar · `urunler.json` takip listesi · `izlemeler.json` arama/kategori izlemeleri · `durum.json` son fiyatlar ve hata sayaçları · `gecmis.json` arama ürünlerinin günlük fiyat geçmişi · `gruplar.json` dinlenen gruplar ve kurallar · `telegram_oturum.txt` Telethon oturumu · `cerezler.json` site çerezleri.

## Yerelde deneme

`fiyat_takip/ayarlar.json` oluşturup (`.gitignore`'da) ayrı bir **test botunun** token'ını yazın, sonra `python3 fiyat_takip/takip.py --test` ya da `python3 fiyat_takip/takip.py`. Gerçek botla aynı anda çalıştırmayın: iki süreç aynı botun mesajlarını paylaşır.
