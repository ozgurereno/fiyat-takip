# Amazon Fiyat Takip – Home Assistant OS kurulumu

Not: Home Assistant'ın yeni sürümlerinde "Eklentiler" (Add-ons) bölümünün adı "Uygulamalar" (Apps) oldu. Sizde hangisi yazıyorsa o menüyü kullanın.

## 1. Telegram botu oluşturun

1. Telegram'da **@BotFather**'a yazın, `/newbot` gönderin, bota bir ad ve kullanıcı adı verin.
2. BotFather'ın verdiği **token**'ı (`123456:ABC...` biçiminde) bir kenara not edin.
3. Yeni botunuzun sohbetini açıp **/start** yazın.

## 2. Klasörü Home Assistant'a kopyalayın

1. Home Assistant'ta **Ayarlar → Uygulamalar (Eklentiler) → Mağaza**'dan **Samba share** uygulamasını yükleyin. Yapılandırma sekmesinde bir kullanıcı adı ve şifre belirleyip başlatın. (Zaten kuruluysa bu adımı atlayın.)
2. Bilgisayarınızda zip'i açın; içinden `fiyat_takip` klasörü çıkar.
3. Ağ paylaşımını açın:
   - Windows: Dosya Gezgini adres çubuğuna `\\homeassistant.local` yazın
   - Mac: Finder'da Cmd+K, sonra `smb://homeassistant.local`
   
   Samba için belirlediğiniz kullanıcı adı ve şifreyle girin.
4. `fiyat_takip` klasörünü **`local_apps`** paylaşımının içine kopyalayın (eski sürümlerde bu paylaşımın adı `addons`).

## 3. Yükleyin ve başlatın

1. **Ayarlar → Uygulamalar (Eklentiler) → Mağaza** sayfasında sağ üstteki üç nokta menüsünden **Güncellemeleri denetle / Yeniden yükle**'ye basın.
2. Sayfada "Yerel" (Local) başlığı altında **Amazon Fiyat Takip** görünür. Açıp **Yükle**'ye basın (ilk yükleme birkaç dakika sürebilir).
3. **Yapılandırma** sekmesinde `telegram_token` alanına token'ı yapıştırıp kaydedin.
4. **Bilgi** sekmesinde **Başlat**'a basın. "Önyüklemede başlat" ve "Watchdog" seçeneklerini açın; böylece Pi yeniden başlasa ya da uygulama çökse de kendiliğinden çalışır.

Bir-iki dakika içinde Telegram'a, üç ürünün adını ve güncel fiyatını içeren **"Fiyat takibi başladı"** mesajı gelmeli. Bu mesaj aynı zamanda sistemin testidir.

## Günlük kullanım (hepsi Telegram'dan)

| Komut | Ne yapar |
|---|---|
| `/liste` | Ürünler, güncel fiyatlar, görülen en düşük fiyat |
| `/ekle <link>` | Ürün ekler: Amazon ya da herhangi bir sitenin ürün sayfası (Amazon uygulamasındaki "Paylaş" linki de olur) |
| `/ekle <link> 1500` | Ürünü 1.500 TL hedef fiyatla ekler |
| `/sil 2` | Listedeki 2 numaralı ürünü çıkarır |
| `/hedef 2 1500` | 2 numaralı ürüne hedef koyar (`/hedef 2` kaldırır) |
| `/fiyat 4 2.999,00` | Fiyatı kendiliğinden bulunamayan bir sitede, sayfada gördüğünüz fiyatı yazarak yerini öğretir |

### Başka sitelerden ürün takibi

Amazon dışındaki bir sitenin ürün sayfasını da `/ekle <link>` ile ekleyebilirsiniz. Uygulama önce sitelerin arama motorları için sayfaya koyduğu standart ürün bilgisinden (schema.org / JSON-LD, ürün meta etiketleri) adı, fiyatı ve stok durumunu okur; Türkiye'deki e-ticaret altyapılarının çoğu bu bilgiyi verir. Bulamazsa bot sizden fiyatı ister: sayfada gördüğünüz fiyatı `/fiyat <no> <fiyat>` ile yazdığınızda uygulama o fiyatın sayfadaki yerini öğrenir ve sonraki okumalarda oradan okur. Fiyat yalnızca tarayıcıda çalışan kodla oluşuyorsa (sayfa kaynağında yoksa) o site izlenemez.

### Sesli alarm (rahatsız etme modunu aşar)

Seçtiğiniz ürünlerde büyük bir düşüş olursa, telefonunuzdaki Home Assistant uygulaması üzerinden "kritik uyarı" gönderilir; iPhone sessizde ya da rahatsız etme modunda olsa bile tam sesle çalar.

| Komut | Ne yapar |
|---|---|
| `/alarmtest` | Deneme uyarısı gönderir |
| `/alarm 2 20` | 2 numaralı ürün olağan fiyatına göre %20 ve üzeri düşerse sesli uyarı |
| `/alarm 2` | 2 numaralı ürünün alarmını kaldırır |

İlk denemede iPhone kritik uyarılara izin isteyebilir. Ses gelmezse iPhone'da Ayarlar → Bildirimler → Home Assistant → **Kritik Uyarılar** seçeneğini açın.

Evde Home Assistant uygulaması kurulu birden fazla telefon ya da tablet varsa uyarı hepsine gider. Yalnızca birine gitmesi için Yapılandırma sekmesindeki `alarm_cihazi` alanına cihaz adının bir parçasını yazın (ör. `iphone`); adları `/alarmtest` yanıtında görürsünüz.

### Arama izleme (indirim avı)

Desteklenen siteler: **Amazon.com.tr** (arama sonuçları), **Vatan Bilgisayar** ve **MediaMarkt** (kategori ve arama sayfaları). Sitede aramayı ya da kategoriyi açın, süzgeçleri seçin ve adres çubuğundaki linki bota gönderin. Vatan'da sayfa kaydırdıkça yüklense de uygulama kategorinin tüm sayfalarını (en çok 10) okur ve "Web'e Özel" gibi kampanya fiyatı varsa onu esas alır.

MediaMarkt'ta yalnızca MediaMarkt'ın sattığı ürünler için linkte `?marketplace=MediaMarkt` süzgeci olmalı (sol taraftaki "Tüm Satıcılar → MediaMarkt"). MediaMarkt sayfa başına 12 ürün gösterir ve bir listede en çok 30 sayfaya izin verir; uygulama varsayılan olarak ilk 10 sayfayı (120 ürün) okur. Kalabalık kategorileri alt kategori, marka ya da fiyat süzgeciyle daraltın. Şu an satın alınamayan ürünler atlanır, promosyon fiyatı varsa o esas alınır.

| Komut | Ne yapar |
|---|---|
| `/izle <arama linki>` | Aramadaki ürünleri izler; biri olağan fiyatına göre %50 ve üzeri düşerse bildirir |
| `/izle <arama linki> 40` | Aynısı, eşik %40 |
| `/izlemeler` | İzlenen aramalar |
| `/izlesil 1` | 1 numaralı izlemeyi kaldırır |

Ek seçenekler (linkten sonra, istediğiniz sırayla):

- bir sayı (ör. `30`): olağan fiyatına göre bu oranda düşen ürünü bildirir (hiçbir seçenek yazmazsanız %50)
- `yeni`: listeye yeni giren ürünü bildirir; Amazon Depo gibi stoğu gelip giden listeler için
- `alarm`: bildirimler sesli (kritik) uyarıyla gelir
- `20sayfa` gibi bir sayı: bu izlemede okunacak en fazla sayfa sayısı (1–30). Her sayfa bir istek demektir.
- `5dk` gibi bir süre: bu izlemenin tarama aralığı (en az 1 dakika; yazmazsanız `arama_araligi_sn` ayarı geçerlidir). Site engel gösterirse uygulama yalnızca o izlemenin aralığını geçici olarak açar.
- sonuna yazdığınız diğer kelimeler izlemenin adı olur

Örnekler: `/izle <depo linki> yeni alarm 3dk Depo iPhone` · `/izle <vatan ssd linki> 30 10dk`. Yeni-ürün izlemesinde, 6 saatten uzun süre listede görünmeyen bir ürünün geri dönmesi de "yeni" sayılır.

"Olağan fiyat", uygulamanın o ürün için son 30 günde kaydettiği günlük fiyatların ortancasıdır; Amazon'un üstü çizili etiket fiyatı kullanılmaz. Uygulama geçmişi izlemeye aldığınız andan itibaren biriktirir.

### Grup dinleme (fırsat gruplarını sesli alarma çevirme)

Uygulama, üye olduğunuz fırsat gruplarını kendi Telegram hesabınızla okur; seçtiğiniz kelimeler geçen bir mesaj gelince sesli uyarı verir. Hiçbir gruba yazmaz.

Kurulum:

1. my.telegram.org'a telefon numaranızla girin, "API development tools" bölümünde bir uygulama oluşturun ve verilen **api_id** ile **api_hash** değerlerini not edin.
2. Uygulamanın Yapılandırma sekmesinde `telegram_api_id`, `telegram_api_hash` ve `telegram_telefon` (ör. `+905551234567`) alanlarını doldurun. Hesabınızda iki adımlı doğrulama varsa şifresini `telegram_2fa_sifre` alanına yazın. Kaydedip uygulamayı yeniden başlatın.
3. Telegram size bir giriş kodu gönderir; bot da sizden kodu ister. Kodu **rakamların arasına tire koyarak** bota yazın: `/kod 1-2-3-4-5`. (Tiresiz yazılan kodu Telegram güvenlik gereği geçersiz sayar.)
4. `/gruplar` ile gruplarınızı listeleyin, `/grupekle 3` ile dinlenecekleri seçin.
5. `/kelime iphone depo` ile alarm kuralı ekleyin. Boşlukla ayrılan kelimelerin hepsi mesajda geçmelidir. Virgülle ayırarak tek seferde birden çok kural ekleyebilirsiniz: `/kelime ssd, iphone 16, ddr5` üç ayrı kural oluşturur (biri tutsa yeter). Fiyat sınırı da koyabilirsiniz: `/kelime iphone 16 pro <50000` (mesajdaki en düşük fiyat 50.000 TL'yi aşarsa alarm çalmaz; mesajda fiyat yoksa yine çalar). Fiyat sınırı yalnızca yazıldığı kurala uygulanır: `/kelime ssd <3000, iphone 16 <50000`.

   Kelimeler **kelime başında** aranır: `ram`, "program" içinde eşleşmez ama "RAM'li" ve "ramfiyat" içinde eşleşir; `iphone`, "iPhone16" içinde eşleşir. Harften rakama geçiş de kelime başı sayılır, bu yüzden `16` da "iPhone16" içinde bulunur. Büyük/küçük harf ve i/ı/İ/I farkı önemsenmez.

| Komut | Ne yapar |
|---|---|
| `/dinleme` | Durum, dinlenen gruplar ve kelimeler |
| `/gruplar [ara]` | Gruplarınızı listeler (ör. `/gruplar fırsat`) |
| `/grupekle 3 7` | Listedeki grupları dinlemeye alır |
| `/grupsil 1` | Grubu dinlemekten çıkarır |
| `/kelime …` | Alarm kuralı ekler |
| `/kelimesil 1` | Kuralı siler |

Güvenlik: giriş yapıldıktan sonra uygulama, Telegram oturumunu Pi'de `telegram_oturum.txt` dosyasında saklar; bu dosya hesabınıza erişim sağlar ve Home Assistant yedeklerine de girer. api_hash, oturum dosyası ve giriş kodunu kimseyle paylaşmayın. Oturumu iptal etmek için Telegram'da Ayarlar → Cihazlar'dan ilgili oturumu sonlandırmanız yeterli.

Gelen bildirimler:

- 🔻 **Fiyat düştü** – eski ve yeni fiyat, fark, yüzde
- 🚨 **Alarm** – alarm kurulu üründe eşik aşılınca (Telegram mesajı ve sesli uyarı)
- 🆕 **Yeni çıktı** – `yeni` seçeneğiyle izlenen listeye yeni ürün girince
- 🚨 **Grup alarmı** – dinlenen bir grupta kurala uyan mesaj gelince (sesli uyarı ve mesajın kendisi)
- 🔥 **%… indirim** – izlenen bir aramadaki ürün eşiği aşan oranda düşünce
- 📦 **Tekrar stokta** – stokta olmayan ürün satışa dönünce
- ⚠️ **Okunamıyor** – bir ürün art arda 5 kez okunamazsa (düzelince ✅ gelir)
- 🗓 **Günlük özet** – her sabah 09:00'da; sistemin çalıştığının kanıtı

## Ayarlar (Yapılandırma sekmesi)

- `kontrol_araligi_sn`: turlar arası bekleme, varsayılan 180 saniye. 120'nin altına inmenizi önermem; Amazon'un engelleme ihtimali artar.
- `arama_araligi_sn`: izlenen aramaların taranma aralığı, varsayılan 600 saniye (10 dakika).
- `min_dusus_tl`: bundan küçük düşüşler bildirilmez (ör. `10`).
- `artis_bildir`: açarsanız fiyat artışları da bildirilir.
- `gunluk_ozet`: özet saati (`09:00` gibi); kapatmak için `kapali` yazın.

## Sorun giderme

- **Mesaj gelmiyorsa:** uygulamanın **Günlük** (Log) sekmesine bakın. "Botunuza /start yazın" yazıyorsa bota bir mesaj gönderin; başka bir hata varsa o satırları Claude'a iletin.
- **Bir ürün "okunamıyor" derse:** uygulama o sayfayı `share` paylaşımındaki `fiyat_takip` klasörüne `hata_<ürün kodu>.html` (Amazon aramaları için `hata_arama.html`, Vatan için `hata_vatan.html`, MediaMarkt için `hata_mediamarkt.html`) olarak kaydeder. Bu dosyayı Claude'a gönderirseniz fiyat okuma kuralı ona göre düzeltilir.
- **Amazon CAPTCHA gösterirse:** uygulama kontrol aralığını kendiliğinden açar (en çok 8 kat) ve düzelince normale döner.
- **Güncelleme:** yeni bir `takip.py` geldiğinde `local_apps/fiyat_takip` içindeki dosyanın üzerine yazın, `config.yaml` içindeki `version` değerini artırın, mağazada "Güncellemeleri denetle" deyip uygulamayı güncelleyin. Ürün listeniz ve fiyat geçmişiniz korunur.
