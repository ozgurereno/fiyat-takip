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

Amazon ürünlerinde takip edilen fiyat **sıfır (yeni) satış fiyatıdır**. Bir ürün Amazon'da yalnızca ikinci el (ör. Amazon Depo) olarak satılıyorsa listede "stokta yok" görünür; sıfırı tekrar satışa çıkınca 📦 bildirimi gelir. İkinci el fiyatlarını izlemek için aşağıdaki **Amazon Depo izleme**yi kullanın.

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
| `/izlekelime 1 apple, iphone, ssd` | 1 numaralı izlemenin kelime süzgecini değiştirir (`/izlekelime 1 sil` kaldırır, `/izlekelime 1` gösterir) |

Ek seçenekler (linkten sonra, istediğiniz sırayla):

- bir sayı (ör. `30`): olağan fiyatına göre bu oranda düşen ürünü bildirir (hiçbir seçenek yazmazsanız %50). Amazon Depo'da anlamı farklıdır, aşağıya bakın.
- `yeni`: listeye yeni giren ürünü bildirir; Amazon Depo gibi stoğu gelip giden listeler için
- `yeni=30`: **yalnızca bundan sonra listeye giren** ürünlere bakar; ürün kıyas fiyatının en az %30 altındaysa bildirir. Listede zaten olan ürünlerin fiyat düşüşleri bu izlemede bildirilmez. Amazon aramalarında kıyas fiyatı, kartta Amazon'un gösterdiği üstü çizili **"Önceki"** fiyattır; kartta önceki fiyat yoksa ürün bildirilmez (yeni listelenen ürünlerin çoğunda önceki fiyat olmaz, bu yüzden bildirim seyrek gelir). Amazon Depo'daki anlamı için aşağıya bakın. `yeni=30` ile ayrıca bir yüzde yazılmaz; `30 yeni` ise eskisi gibi "yeni çıkan ya da %30 düşen" demektir.
- `yenigibi` / `cokiyi` / `iyi`: yalnızca Amazon Depo linklerinde; en az bu durumdaki ürünleri bildirir (aşağıya bakın)
- `alarm`: bildirimler sesli (kritik) uyarıyla gelir
- `kelime=apple,iphone,ram,ssd`: yalnızca adında bu kelimelerden **herhangi biri** geçen ürünler değerlendirilir; diğerlerine hiç bakılmaz (Depo'da panelleri de okunmaz). Kelimeler grup alarmlarındaki gibi kelime başında aranır (`ram`, "program" içinde eşleşmez; `iphone`, "iPhone16" içinde eşleşir), büyük/küçük harf ve i/ı farkı önemsenmez. Virgülden sonra boşluk bırakmayın; boşluklu ifade (ör. "iphone 16", iki kelimenin de geçmesi gerekir) için sonradan `/izlekelime` kullanın. Süzgeci değiştirdiğinizde, daha önce listede görülmüş ürünler "yeni" sayılmaz.
- `20sayfa` gibi bir sayı: bu izlemede okunacak en fazla sayfa sayısı (1–30). Her sayfa bir istek demektir.
- `5dk` gibi bir süre: bu izlemenin tarama aralığı (en az 1 dakika; yazmazsanız `arama_araligi_sn` ayarı geçerlidir). Site engel gösterirse uygulama yalnızca o izlemenin aralığını geçici olarak açar.
- sonuna yazdığınız diğer kelimeler izlemenin adı olur

Örnekler: `/izle <depo linki> yeni alarm 3dk Depo iPhone` · `/izle <vatan ssd linki> 30 10dk` · Prime bilgisayar kategorisinde "En Son Gelenler" sıralamasıyla yeni girenler: `/izle https://www.amazon.com.tr/s?rh=n%3A12466439031%2Cp_85%3A21345931031&s=date-desc-rank yeni=30 3sayfa 5dk Prime bilgisayar`.

Amazon'un "En Son Gelenler" sıralaması ürünün Amazon'a eklenme tarihine göredir. Kalabalık kategorilerde ilk birkaç sayfayı okumak yeni listelenen ürünleri yakalar; ama eskiden beri satılan bir ürün sonradan Prime'a geçerse ya da Depo'ya düşerse listenin ilk sayfalarına çıkmaz. Bu yüzden listeyi `k=` arama kelimesi ya da fiyat süzgeciyle küçültüp tamamını okutmak en güvenilir yoldur. Yeni-ürün izlemesinde, 6 saatten uzun süre listede görünmeyen bir ürünün geri dönmesi de "yeni" sayılır.

### Amazon Depo izleme

Amazon Depo (ikinci el / iade) listesinin linkini `/izle` ile gönderin; uygulama bunu kendiliğinden tanır. Örnek: Amazon'da **Amazon Depo** bölümünü açıp "En yeni" sıralamasını seçin ve adres çubuğundaki linki gönderin (`…/s?i=warehouse-deals&…&s=date-desc-rank`). Süzgeç ya da arama kelimesi eklediyseniz onlar da korunur.

- Depo arama kartlarında sıfır fiyat yoktur; kartta görünen "Diğer satın alma seçenekleri … TL" ürünün **en düşük ikinci el fiyatıdır** ve izleme bu fiyatla yapılır. Bu fiyatlar normal ürün takibinin fiyat geçmişine karışmaz.
- Hiçbir seçenek yazmazsanız Depo izlemesi **yeni çıkan ürünü** bildirir (normal aramalardaki %50 varsayılanı yerine).
- **Yüzde eşiği sıfır fiyatına göredir:** `/izle <depo linki> 30`, ürünün Amazon Depo fiyatı sıfır (yeni) fiyatından en az %30 düşükse bildirir (listedeki tüm ürünlere bakılır). Sıfır fiyat olarak önce Amazon.com.tr'nin fiyatı, yoksa en ucuz satıcınınki kullanılır. Ürünün sıfırı satılmıyorsa Amazon'un "Önceki Fiyat"ı (liste fiyatı) esas alınır; ikisi de yoksa ürün bildirilmez. Aynı ürün, fiyatı daha da düşmedikçe yeniden bildirilmez.
- Sıfır fiyatı, durum ve satıcı ürünün **teklif panelinden** okunur (sayfadaki "(1 İkinci El ürün)" linkinin açtığı panel). Bildirime şunlar eklenir: durumu (ör. "İkinci El - Yeni Gibi"), satıcısı (Amazon Depo ya da başka bir satıcı), sıfır fiyatı (Amazon.com.tr'ninki ve daha ucuz başka satıcı varsa onunki) ve ne kadar ucuz olduğu, "Önceki Fiyat" ve durum açıklaması. Mesajdaki link ürün sayfasını ikinci el teklifleri açık olarak getirir.
- **Yalnızca yeni girenler: `yeni=20`.** Örnek: `/izle <depo apple linki> yeni=20 3dk`. İzlemeye aldığınız andaki ürünler bildirilmez; bundan sonra listeye giren her ürünün paneli okunur. Satıcısı **Amazon Depo** olan teklif önce **Amazon.com.tr**'nin sıfır fiyatıyla, Amazon.com.tr sıfırı satmıyorsa en ucuz satıcının sıfır fiyatıyla kıyaslanır ve en az %20 ucuzsa bildirilir. Kıyaslanacak sıfır fiyatı hiç yoksa ürün yine bildirilir ("Kıyaslanacak sıfır fiyatı yok" notuyla). Paneli okunamayan yeni ürün sonraki taramada yeniden denenir.
- Fiyat aralığı: Amazon'un fiyat süzgeci Depo linkinde de çalışır. Örnek: `…&low-price=0.01&high-price=250` eklenmiş Depo linki 0,01–250 TL arasındaki ürünleri listeler; `/izle <bu link> yeni 20sayfa 10dk` ile bu aralıkta listeye giren her ürün bildirilir. İzleme adı "Amazon Depo · 0,01–250 TL" olur.
- Durum süzgeci: `yenigibi`, `cokiyi` ya da `iyi` yazarsanız yalnızca en az o durumdaki ürünler bildirilir. Örnek: `/izle <depo linki> 30 yenigibi alarm 3dk`.
- İstek sayısını düşük tutmak için bir taramada en çok 8 panel okunur. Okunan panel bilgisi ürün başına saklanır ve kartta görünen fiyat değişmedikçe 24 saat yeniden okunmaz; yeni çıkan ürünün paneli her zaman yeniden okunur. Kalabalık listelerde `kelime=` süzgeciyle istek sayısını iyice azaltabilirsiniz.
- Eşik ya da durum süzgeci varsa panel okunmadan bildirim yapılmaz: 8 sınırını aşan ürünler bir sonraki taramaya kalır, paneli okunamayan ürün bir saat sonra yeniden denenir. Yalnızca `yeni` seçeneği varken (eşik ve durum süzgeci yokken) panel okunamayan ürün beklemeden, "Durum bilgisi alınamadı" notuyla bildirilir.

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
| `/grupdepo 1 30 yenigibi kelime=…` | Gruptaki Amazon paylaşımlarını Depo'da doğrular (aşağıya bakın) |

Mesajdaki ürün linki kısaltıcı ya da fırsat sitesi linkiyse (ör. `firsatl.ar/go/…`, `amzn.eu/d/…`), bildirimde ortaklık etiketi temizlenmiş düz Amazon linkine (`https://www.amazon.com.tr/dp/<ürün kodu>`) çevrilir. Bunun için yalnızca yönlendirme servisine bakılır, Amazon'a istek atılmaz.

#### Depo kanalları: anında doğrulama

Amazon Depo'ya yeni giren ürünler dakikalar içinde satılır ve Amazon'da "Depo'ya yeni eklenen" sıralaması yoktur; bu yüzden Depo izlemesi yeni gelen ürünü her zaman hemen göremez. Depo fırsatlarını paylaşan kanalları (ör. "Amazon Depo - İkinci El Fırsatlar") **haber kaynağı** olarak kullanıp kararı kendi kurallarınıza bırakabilirsiniz:

1. Kanalı `/gruplar` ve `/grupekle` ile dinlemeye alın, numarasını `/dinleme` ile görün.
2. `/grupdepo <no> [yüzde] [yenigibi|cokiyi|iyi] [kelime=a,b]` yazın. Örnek: `/grupdepo 2 30 yenigibi kelime=apple,iphone,ssd`

Bundan sonra o kanalda Amazon ürün linki içeren her paylaşımda:

- `kelime=` verdiyseniz önce mesaj metnine bakılır; kelimelerden biri kelime başında geçmiyorsa Amazon'a hiç istek atılmaz.
- Link düz Amazon linkine çevrilir ve ürünün teklif paneli Amazon'dan **bir kez** okunur: ürün hâlâ satışta mı, gerçek Depo fiyatı, durumu (Yeni Gibi…), satıcısı ve sıfır fiyatı.
- Satılmışsa, durum süzgecine uymuyorsa ya da Depo fiyatı sıfır fiyatından (önce Amazon.com.tr'ninki, yoksa en ucuz satıcınınki; sıfırı yoksa önceki fiyatından) verdiğiniz yüzde kadar ucuz değilse sessizce geçilir. Kanalın yazdığı indirim oranına değil, Amazon'dan okunan fiyatlara bakılır.
- Kurala uyarsa sesli uyarı ve ayrıntılı bildirim gelir (🔥 Sıfırından %N ucuz, durum, satıcı, düz link, mesaja git).
- Amazon o an okunamazsa (ör. CAPTCHA): kural verdiyseniz sesli uyarı çalmaz, yalnızca "doğrulanamadı" mesajı gelir; kural vermediyseniz paylaşım sesli bildirilir.
- Aynı ürün 10 dakika içinde başka kanaldan da paylaşılırsa yeniden okunmaz. Amazon'u yormamak için saatte en çok 30 paylaşım doğrulanır; Amazon geri çekilmesi sürerken doğrulama yapılmaz.

Yüzde ve süzgeç vermeden `/grupdepo 2` yazarsanız, satışta olduğu doğrulanan her paylaşım bildirilir. Kapatmak için `/grupdepo 2 kapat`. Depo doğrulaması açık kanalda Amazon ürün linki olmayan mesajlar (ve `kelime=` süzgecine uymayanlar) için `/kelime` kuralları eskisi gibi çalışır.

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
