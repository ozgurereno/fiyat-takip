# Kişisel Fiyat Takip (Home Assistant uygulaması)

Amazon.com.tr, Vatan Bilgisayar, MediaMarkt ve yapısal ürün verisi veren diğer sitelerdeki fiyatları izler; düşüşleri Telegram'dan ve iPhone'a kritik uyarı olarak bildirir. Ayrıca seçilen Telegram fırsat gruplarını dinleyip kelime kurallarına göre sesli alarm verir.

Kullanım belgesi: [fiyat_takip/DOCS.md](fiyat_takip/DOCS.md) · Geliştirme notları: [CLAUDE.md](CLAUDE.md)

## Testler

```bash
for f in tests/test_*.py; do python3 "$f" || break; done
```

Gereken paketler: `requests`, `beautifulsoup4` (grup testleri Telethon'u taklit eder, kurulu olması gerekmez).
