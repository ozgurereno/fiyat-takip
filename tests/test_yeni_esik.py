"""'yeni=N' izlemesi: yalnızca bundan sonra listeye giren ürünler, kıyas fiyatının %N altındaysa.
Depo'da kıyas: Amazon.com.tr sıfır fiyatı, yoksa en ucuz sıfır teklif, o da yoksa yine bildirilir.
Diğer Amazon aramalarında kıyas: kartta görünen 'Önceki' fiyatı; yoksa bildirilmez."""
import sys, re, shutil, tempfile
from pathlib import Path
from bs4 import BeautifulSoup
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fiyat_takip"))
FIX = Path(__file__).resolve().parent / "fixtures"
import takip
oku = lambda ad: open(FIX / ad, encoding="utf-8").read()
prime, depo_arama, aod = oku("amazon_prime_bilgisayar_yeni.html"), oku("amazon_depo_arama.html"), oku("amazon_depo_aod_inissia.html")

# ---- gerçek sayfa: kartlardaki 'Önceki' fiyatı okunur, Depo kartlarında okunmaz
ur, sonraki = takip.arama_coz(prime)
assert len(ur) == 22 and sonraki and "page=2" in sonraki, (len(ur), sonraki)
assert {u["asin"]: u["onceki"] for u in ur if "onceki" in u} == {"B0HPQS6P3P": 599.0, "B0HS4RFY8D": 2290.0, "B0HS4MTQGZ": 1299.0}
assert [u for u in ur if u["asin"] == "B0HPQS6P3P"][0]["fiyat"] == 539.0
assert not any("onceki" in u for u in takip.arama_coz(depo_arama, depo=True)[0])
# panel: Amazon.com.tr'nin sıfır fiyatı ayrıca tutulur
p0 = takip.depo_ozet(takip.aod_coz(aod)); assert p0["amazon"] == 6999.0 and p0["yeni"] == 6999.0
assert takip.depo_kiyas(p0) == (6999.0, "Amazon.com.tr fiyatından")
assert takip.depo_kiyas({**p0, "amazon": None}) == (6999.0, "Sıfırından")
assert takip.depo_kiyas({**p0, "amazon": None, "yeni": None}) == (12168.0, "Önceki fiyatından")
assert takip.depo_kiyas({**p0, "amazon": None, "yeni": None}, onceki=False) == (None, "")
# fiyat aralıklı Depo linkinin adı
D = "https://www.amazon.com.tr/s?i=warehouse-deals&srs=44219324031&bbn=44219324031&s=date-desc-rank"
assert takip.arama_url_temizle(D + "&low-price=0.01&high-price=250") == D + "&low-price=0.01&high-price=250"
assert takip.arama_adi(D + "&low-price=0.01&high-price=250") == "Amazon Depo · 0,01–250 TL"
assert takip.arama_adi(D + "&k=apple&high-price=1500") == "Amazon Depo · apple · 0–1.500 TL"

tmp = Path(tempfile.mkdtemp())
for d in ("AYAR_DOSYA", "URUN_DOSYA", "DURUM_DOSYA", "IZLEME_DOSYA", "GECMIS_DOSYA", "CEREZ_DOSYA"):
    setattr(takip, d, tmp / getattr(takip, d).name)
takip.KLASOR = takip.HATA_KLASOR = tmp
takip.json_yaz(takip.AYAR_DOSYA, {"telegram_token": "T", "telegram_chat_id": "42"})
takip.json_yaz(takip.URUN_DOSYA, [])
takip.time.sleep = lambda x: None
t = takip.Takip(); msj = []
t.bildir = lambda m: msj.append(m) or True
class R:
    def __init__(s, text, code=200): s.text, s.status_code, s.url = text, code, ""
    def raise_for_status(s):
        if s.status_code >= 400: raise Exception(f"HTTP {s.status_code}")
cevap = {"arama": prime, "aod": R(aod)}; istek = []
def get(url, timeout=0, params=None, headers=None):
    istek.append(url)
    return cevap["aod"] if "aodAjaxMain" in url else R(cevap["arama"])
t.oturum.get = get

# ---- seçenek denetimi
P = "https://www.amazon.com.tr/s?rh=n%3A12466439031%2Cp_85%3A21345931031&s=date-desc-rank"
assert "Yüzde 1 ile 99" in t.komut(f"/izle {P} yeni=150")
assert "yanına ayrıca yüzde yazmayın" in t.komut(f"/izle {P} 30 yeni=20")
assert not t.izlemeler() and not istek

# ---- Prime bilgisayar: yalnızca yeni girenler, kartın 'Önceki' fiyatına göre
c = t.komut(f"/izle {P} yeni=30 1sayfa 5dk Prime bilgisayar"); print(c)
assert "22 ürün bulundu" in c and "önceki fiyatından %30 ve üzeri ucuzsa (önceki fiyatı yoksa bildirilmez)" in c
iz = t.izlemeler()[0]
assert iz["yeni"] and iz["yeni_esik"] == 30 and iz["esik"] is None and iz["ad"] == "Prime bilgisayar" and iz["sayfa"] == 1
assert not msj                                                               # mevcut ürünler bildirilmez
assert "yeni çıkan %30+ ucuzsa bildir" in t.komut("/izlemeler")
def kart(asin, ad, fiyat, onceki=None):
    c = f'<span class="a-price a-text-price" data-a-strike="true"><span class="a-offscreen">{onceki}</span></span>' if onceki else ""
    return (f'<div data-component-type="s-search-result" data-asin="{asin}"><a><h2><span>{ad}</span></h2></a>'
            f'<span class="a-price" data-a-color="base"><span class="a-offscreen">{fiyat}</span></span>{c}</div>')
soup = BeautifulSoup(prime, "html.parser")
eski = soup.select_one('div[data-component-type="s-search-result"][data-asin="B0HPQS6P3P"]')
eski.select_one('.a-price:not([data-a-strike]) .a-offscreen').string = "100,00 TL"   # mevcut ürün %83 düştü
yeniler = BeautifulSoup(kart("B0YENI0001", "Yeni SSD 2TB", "6.000,00 TL", "10.000,00 TL") +       # %40: bildirilir
                        kart("B0YENI0002", "Yeni Klavye", "850,00 TL", "1.000,00 TL") +           # %15: hayır
                        kart("B0YENI0003", "Yeni Fare", "100,00 TL"), "html.parser")              # kıyas yok: hayır
soup.select_one('div[data-component-type="s-search-result"]').insert_before(yeniler)
cevap["arama"] = str(soup)
t.izleme_calistir(iz); print(msj)
assert len(msj) == 1 and "🔥 Yeni · Önceki fiyatından %40 ucuz" in msj[0] and "Yeni SSD 2TB" in msj[0]
assert "Önceki fiyat 10.000,00 TL → <b>6.000,00 TL</b>" in msj[0] and "https://www.amazon.com.tr/dp/B0YENI0001" in msj[0]
t.izleme_calistir(iz); assert len(msj) == 1                                 # artık yeni değil
assert not any("aodAjaxMain" in u for u in istek)                           # normal aramada panel okunmaz

# ---- Amazon Depo: yalnızca yeni girenler, Amazon Depo fiyatı Amazon.com.tr sıfır fiyatına göre
msj.clear(); cevap["arama"] = depo_arama; istek.clear()
c = t.komut(f"/izle {D}&k=apple yeni=5 5dk"); print(c)
assert "Amazon Depo fiyatı Amazon.com.tr'nin (yoksa en ucuz satıcının) sıfır fiyatından %5 ve üzeri ucuzsa" in c
assert "kıyaslanacak sıfır fiyatı yoksa" in c and not msj
assert not any("aodAjaxMain" in u for u in istek)                           # mevcut ürünlerin paneli okunmaz
izd = [i for i in t.izlemeler() if "warehouse" in i["url"]][0]
assert izd["yeni_esik"] == 5 and izd["ad"] == "Amazon Depo · apple"
def depo_yeni(asin):
    s = BeautifulSoup(depo_arama, "html.parser")
    s.select_one('div[data-component-type="s-search-result"][data-asin="B0HJWZZVDB"]')["data-asin"] = asin
    return str(s)
# panel okunamazsa ürün 'yeni' olarak bir sonraki tura kalır
cevap["arama"], cevap["aod"] = depo_yeni("B0DEPO0001"), R("hata", 500)
t.izleme_calistir(izd); assert not msj and "B0DEPO0001" not in t.durum["izleme"][izd["url"]]["gorulen"]
t.durum["izleme"][izd["url"]]["sonraki"] = 0
t.gecmis["depo:B0DEPO0001"].pop("panel_bekle", None)                          # bir saat geçti
cevap["aod"] = R(aod); t.izleme_calistir(izd); print(msj)
assert len(msj) == 1 and "🔥 Yeni · Amazon.com.tr fiyatından %7 ucuz" in msj[0]
assert "Amazon.com.tr sıfırı 6.999,00 TL (%7 daha ucuz)" in msj[0] and "Satıcı: Amazon Depo" in msj[0]

# ---- birim: depo_yeni_esik kararları
u = {"asin": "X", "baslik": "Ürün", "fiyat": 6532.69}; iz5 = {"ad": "D", "yeni_esik": 20}
def karar(p, iz=iz5, yeni=True):
    msj.clear(); t.depo_panel = lambda u, g, taze=False: p
    return t.depo_yeni_esik(iz, u, {}, yeni, "", "https://x"), (msj[0] if msj else None)
assert karar(p0, yeni=False) == (True, None) and karar(None) == (takip.ERTELE, None)
assert karar(p0) == (True, None)                                             # %7 < %20
r, m = karar({**p0, "amazon": 9000.0, "yeni": 7000.0})                       # Amazon.com.tr önce gelir
assert "Amazon.com.tr fiyatından %27 ucuz" in m and "en ucuz sıfır 7.000,00 TL" in m, m
r, m = karar({**p0, "amazon": None, "yeni": 9000.0}); assert "🔥 Yeni · Sıfırından %27 ucuz" in m, m
r, m = karar({**p0, "amazon": None, "yeni": None})                           # kıyas yok: yine bildirilir
assert "🆕 Yeni çıktı" in m and "Kıyaslanacak sıfır fiyatı yok" in m and "Önceki fiyat 12.168,00 TL" in m, m
baska = {**p0, "amazon": None, "yeni": None, "depo": {**p0["depo"], "satici": "Başka Satıcı"}}
assert karar(baska) == (True, None)                                          # satıcısı Amazon Depo değil
iyi = {**p0, "amazon": 9000.0, "depo": {**p0["depo"], "durum": "İkinci El - İyi"}}
assert karar(iyi, {**iz5, "durum": "yeni gibi"}) == (True, None) and karar(iyi)[1]
del t.depo_panel
shutil.rmtree(tmp)
print("YENİ EŞİK TESTLERİ GEÇTİ")
