import sys, shutil, tempfile, re
from pathlib import Path
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fiyat_takip"))
FIX = Path(__file__).resolve().parent / "fixtures"
import takip
oku = lambda ad: open(FIX / ad, encoding="utf-8").read()
arama = oku("amazon_depo_arama.html")
aod = oku("amazon_depo_aod_inissia.html")

# ---- link tanıma
U = "https://www.amazon.com.tr/s?i=warehouse-deals&srs=44219324031&bbn=44219324031&s=date-desc-rank"
assert takip.depo_mu(U) and not takip.depo_mu("https://www.amazon.com.tr/s?k=ssd")
assert not takip.depo_mu("https://www.vatanbilgisayar.com/x/?i=warehouse-deals")
assert takip.arama_url_temizle(U + "&qid=1795211850&ref=sr_pg_1") == U
assert takip.arama_adi(U) == "Amazon Depo" and takip.arama_adi(U + "&k=iphone") == "Amazon Depo · iphone"
assert takip.depo_url("B0X") == "https://www.amazon.com.tr/dp/B0X?aod=1&condition=used"

# ---- arama kartları: fiyat 'Diğer satın alma seçenekleri' satırındaki ikinci el fiyatı
ur, sonraki = takip.arama_coz(arama, depo=True)
assert len(ur) == 24 and sonraki and "page=2" in sonraki, (len(ur), sonraki)
assert ur[0] == {"asin": "B0FLF2MK1L", "baslik": "Rgb Şerit Led Seti 54 Çip Ct-4557", "fiyat": 355.23,
                 "url": "https://www.amazon.com.tr/dp/B0FLF2MK1L?aod=1&condition=used", "not": ""}, ur[0]
stanley = [u for u in ur if u["asin"] == "B0GYZKVSZT"][0]
assert stanley["fiyat"] == 1027.87 and stanley["not"] == "4 ikinci el teklif", stanley
assert [u for u in ur if u["asin"] == "B0HJWZZVDB"][0]["fiyat"] == 6532.69
assert takip.arama_coz(arama)[0] == []          # normal kipte Depo kartı okunmaz (sıfır fiyat yok)

# ---- teklif paneli
t = takip.aod_coz(aod)
assert t == [{"durum": "Yeni", "fiyat": 6999.0, "satici": "Amazon.com.tr", "gonderen": "Amazon.com.tr",
              "yorum": "", "onceki": 12168.0},
             {"durum": "İkinci El - Yeni Gibi", "fiyat": 6532.69, "satici": "Amazon Depo",
              "gonderen": "Amazon Lojistik", "yorum": "Ürün orijinal ambalajında gönderilir.", "onceki": None}], t
oz = takip.depo_ozet(t)
assert oz["depo"]["fiyat"] == 6532.69 and oz["yeni"] == 6999 and oz["onceki"] == 12168
assert takip.depo_ozet([]) == {"depo": None, "yeni": None, "amazon": None, "onceki": None}
D = takip.durum_derecesi
assert D("Yeni") == 5 and D("İkinci El - Yeni Gibi") == 4 and D("İkinci El - Çok İyi") == 3
assert D("İkinci El - İyi") == 2 and D("İkinci El - Kabul Edilebilir") == 1 and D("??") == 0
# Depo dışı ikinci el satıcısı daha ucuz olsa da Depo teklifi seçilir; Depo yoksa en ucuz ikinci el
diger = {"durum": "İkinci El - İyi", "fiyat": 5000.0, "satici": "Başka Satıcı", "gonderen": "", "yorum": "", "onceki": None}
assert takip.depo_ozet(t + [diger])["depo"]["satici"] == "Amazon Depo"
assert takip.depo_ozet([t[0], diger])["depo"]["satici"] == "Başka Satıcı"

# ---- ürün sayfası: yalnızca ikinci el teklifi olan sayfa sıfır fiyat gibi okunmamalı
assert takip.sayfa_coz(oku("amazon_depo_urun_sadece_ikinciel.html"))["fiyat"] is None
s = takip.sayfa_coz(oku("amazon_depo_urun_yeni_ve_depo.html"))
assert s == {"baslik": "Inissia D40 Siyah ve Kireç Çözme Kiti", "fiyat": 6999.0}, s

# ---- uçtan uca izleme
tmp = Path(tempfile.mkdtemp())
for d in ("AYAR_DOSYA", "URUN_DOSYA", "DURUM_DOSYA", "IZLEME_DOSYA", "GECMIS_DOSYA", "CEREZ_DOSYA"):
    setattr(takip, d, tmp / getattr(takip, d).name)
takip.KLASOR = takip.HATA_KLASOR = tmp
takip.json_yaz(takip.AYAR_DOSYA, {"telegram_token": "T", "telegram_chat_id": "42"})
takip.json_yaz(takip.URUN_DOSYA, [])
takip.time.sleep = lambda x: None
t = takip.Takip(); msj = []; ha = []
t.bildir = lambda m: msj.append(m) or True
t.kritik_uyari = lambda b, m, u=None: ha.append((b, m, u)) or ["mobile_app_x"]
class R:
    def __init__(s, text, code=200): s.text, s.status_code, s.url = text, code, ""
    def raise_for_status(s):
        if s.status_code >= 400: raise Exception(f"HTTP {s.status_code}")
def kartsiz(sayfa, *asinler):
    soup = BeautifulSoup(sayfa, "html.parser")
    for a in asinler:
        soup.select_one(f'div[data-component-type="s-search-result"][data-asin="{a}"]').decompose()
    return str(soup)
istek = []; cevap = {"arama": kartsiz(arama, "B0HJWZZVDB"), "aod": {}}
def get(url, timeout=0, params=None, headers=None):
    istek.append(url)
    m = re.search(r"aodAjaxMain.*asin=(\w+)", url)
    if m:
        r = cevap["aod"].get(m.group(1))
        return R(r) if r else R("yok", 404)
    return R(cevap["arama"])
t.oturum.get = get

assert "yalnızca Amazon Depo" in t.komut("/izle https://www.amazon.com.tr/s?k=ssd yenigibi")
c = t.komut(f"/izle {U} 1sayfa yenigibi"); print(c)
assert "23 ürün bulundu" in c and "Amazon Depo kipi" in c and "Yeni Gibi" in c and "yeni bir ürün girince" in c.lower()
iz = t.izlemeler()[0]
assert iz["yeni"] and iz["esik"] is None and iz["durum"] == "yeni gibi" and iz["ad"] == "Amazon Depo", iz
assert istek == [U] and not msj                                         # ilk taramada bildirim ve panel yok
assert "depo:B0FLF2MK1L" in t.gecmis and "B0FLF2MK1L" not in t.gecmis    # sıfır fiyat geçmişine karışmaz
assert "📦 Depo" in t.komut("/izlemeler") and "en az Yeni Gibi" in t.komut("/izlemeler")

# yeni ürün girer: panel okunur, bildirimde durum, satıcı, sıfır ve önceki fiyat
cevap["arama"] = arama; cevap["aod"]["B0HJWZZVDB"] = aod; istek.clear()
assert t.izleme_calistir(iz) == 24
assert istek == [U, takip.AOD_URL.format("B0HJWZZVDB")], istek
print(msj[-1])
assert len(msj) == 1 and "🆕 Yeni çıktı" in msj[0] and "Inissia D40" in msj[0]
assert "Fiyat: <b>6.532,69 TL</b>" in msj[0] and "İkinci El - Yeni Gibi · Satıcı: Amazon Depo" in msj[0]
assert "Amazon.com.tr sıfırı 6.999,00 TL (%7 daha ucuz)" in msj[0] and "Önceki fiyat 12.168,00 TL (%46 altında)" in msj[0]
assert "<i>Ürün orijinal ambalajında gönderilir.</i>" in msj[0] and "bu satıcının" not in msj[0]
assert 'href="https://www.amazon.com.tr/dp/B0HJWZZVDB?aod=1&condition=used"' in msj[0]
istek.clear(); t.izleme_calistir(iz); assert istek == [U] and len(msj) == 1      # tekrar bildirilmez

# durum süzgeci: panel zorunlu. Okunamayan panel ayrıntısız bildirilmez, sonraki tura kalır (1 saat sonra
# yeniden denenir); 8 sınırını aşanlar da sonraki tura kalır. 'İyi' durumdaki ürün bildirilmez.
_s = BeautifulSoup(aod, "html.parser"); _s.select_one("#aod-offer #aod-offer-heading").string = "İkinci El - İyi"
kotu = str(_s); assert [x["durum"] for x in takip.aod_coz(kotu)] == ["Yeni", "İkinci El - İyi"]
G = t.durum["izleme"][U]["gorulen"]
for a in G: G[a] = "2000-01-01T00:00:00"                      # hepsi 'yeni' sayılsın
cevap["arama"] = arama; cevap["aod"] = {"B0CVRGQWF6": kotu}; msj.clear()   # Razer 18. sırada; diğerleri 404
for tur in range(3):
    istek.clear(); t.izleme_calistir(iz)
    assert len([u for u in istek if "aodAjaxMain" in u]) == 8 and not msj, (tur, istek, msj)
istek.clear(); t.izleme_calistir(iz); assert istek == [U] and not msj, (istek, msj)     # hepsi bekliyor ya da işlendi
assert t.gecmis["depo:B0FLF2MK1L"].get("panel_bekle") and not t.gecmis["depo:B0CVRGQWF6"].get("panel_bekle")
# bir saat geçti, paneller artık okunuyor: 23 ürün ayrıntılı bildirilir, Razer ('İyi') bildirilmez
for k, g in t.gecmis.items():
    if g.get("panel_bekle"): g["panel_bekle"] = "2000-01-01T00:00:00"
cevap["aod"] = {a: aod for a in [u["asin"] for u in ur] if a != "B0CVRGQWF6"}
for tur, beklenen in ((1, 8), (2, 8), (3, 7)):
    n = len(msj); t.izleme_calistir(iz); assert len(msj) - n == beklenen, (tur, len(msj) - n)
assert len(msj) == 23 and not any("Razer" in m or "alınamadı" in m for m in msj)
assert all("İkinci El - Yeni Gibi · Satıcı: Amazon Depo" in m for m in msj)
istek.clear(); t.izleme_calistir(iz); assert istek == [U]
t.komut("/izlesil 1")

# süzgeçsiz yeni-ürün izlemesi: panel okunamazsa beklemeden ayrıntısız bildirilir
cevap["arama"] = kartsiz(arama, "B0HJWZZVDB"); cevap["aod"] = {}; msj.clear()
c = t.komut(f"/izle {U} 1sayfa Depo yeni"); iz3 = t.izlemeler()[0]
assert iz3["yeni"] and not iz3.get("esik") and not iz3.get("durum")
cevap["arama"] = arama; t.izleme_calistir(iz3)
assert len(msj) == 1 and "Fiyat: <b>6.532,69 TL</b>" in msj[0] and "Durum bilgisi alınamadı" in msj[0], msj
t.komut("/izlesil 1")

# ---- eşik: Depo fiyatı sıfır fiyatına göre
def fiyatli(sayfa, depo_fiyat):
    """Panelde Depo teklifinin fiyatını değiştirir."""
    s2 = BeautifulSoup(sayfa, "html.parser"); o = s2.select_one("#aod-offer")
    tam, kesir = takip.tl(depo_fiyat).removesuffix(" TL").split(",")
    o.select_one(".a-price-whole").string = tam; o.select_one(".a-price-fraction").string = kesir
    return str(s2)
def kartli(sayfa, fiyat):
    s2 = BeautifulSoup(sayfa, "html.parser")
    s2.select_one('[data-asin="B0HJWZZVDB"] [data-cy="secondary-offer-recipe"] .a-color-base').string = takip.tl(fiyat)
    return str(s2)
assert takip.aod_coz(fiyatli(aod, 4000))[1]["fiyat"] == 4000
msj.clear(); ha.clear()
assert t.gecmis["depo:B0HJWZZVDB"].get("panel_bekle")      # yukarıda paneli 404 verdi: 1 saat bekliyor
t.gecmis["depo:B0HJWZZVDB"].pop("panel_bekle")             # ... ve o bir saat geçti
cevap["arama"] = kartli(arama, 4000); cevap["aod"] = {"B0HJWZZVDB": fiyatli(aod, 4000)}; istek.clear()
c = t.komut(f"/izle {U} 30 1sayfa alarm Depo indirim"); print(c)
iz2 = t.izlemeler()[0]
assert iz2["esik"] == 30 and not iz2["yeni"] and "durum" not in iz2 and iz2["ad"] == "Depo indirim"
assert "sıfır fiyatından (sıfırı yoksa önceki fiyatından) %30" in c
# panel bilgisi ürün başına önbellekte (önceki izlemeden): yalnızca kart fiyatı değişen Inissia yeniden okunur.
# Diğerleri sıfırına göre %7 ucuz (eşik altında). Inissia %43 ucuz -> ilk taramada hemen bildirilir.
assert [u for u in istek if "aodAjaxMain" in u] == [takip.AOD_URL.format("B0HJWZZVDB")], istek
print(msj[-1])
assert len(msj) == 1 and "🔥 Amazon.com.tr fiyatından %43 ucuz" in msj[0] and "Fiyat: <b>4.000,00 TL</b>" in msj[0]
assert "Amazon.com.tr sıfırı 6.999,00 TL (%43 daha ucuz)" in msj[0] and "Önceki fiyat 12.168,00 TL (%67 altında)" in msj[0]
assert ha and ha[-1][2].endswith("B0HJWZZVDB?aod=1&condition=used") and "listede en düşük" not in msj[0]
# kart fiyatı değişmedi: panel önbellekten okunur, yeniden bildirilmez
istek.clear(); t.izleme_calistir(iz2)
assert takip.AOD_URL.format("B0HJWZZVDB") not in istek and len(msj) == 1
# fiyat daha da düştü: kart değişince panel yeniden okunur, yeniden bildirilir
cevap["arama"] = kartli(arama, 3500); cevap["aod"]["B0HJWZZVDB"] = fiyatli(aod, 3500); istek.clear()
t.izleme_calistir(iz2)
assert takip.AOD_URL.format("B0HJWZZVDB") in istek and len(msj) == 2 and "%50 ucuz" in msj[-1]
# kart aynı ama önbellek 24 saatten eski: yeniden okunur; fiyat aynıysa yeniden bildirilmez
t.gecmis["depo:B0HJWZZVDB"]["panel"]["zaman"] = "2000-01-01T00:00:00"; istek.clear()
t.izleme_calistir(iz2); assert takip.AOD_URL.format("B0HJWZZVDB") in istek and len(msj) == 2
# başka bir satıcı listede daha ucuzsa bildirimde yazar (eşik Depo teklifine göre)
assert "listede en düşük ikinci el 3.000,00 TL" in takip.Takip.depo_metin(
    {"fiyat": 3000.0}, takip.depo_ozet(takip.aod_coz(fiyatli(aod, 3500))))

# depo_degerlendir: önbellekteki panel bilgisiyle tek tek durumlar (ağ yok)
simdi = datetime.now().isoformat(timespec="seconds")
def panel(depo, yeni=None, onceki=None, durum="İkinci El - Çok İyi"):
    return {"depo": {"durum": durum, "fiyat": depo, "satici": "Amazon Depo", "gonderen": "", "yorum": "", "onceki": None},
            "yeni": yeni, "onceki": onceki, "kart": depo, "zaman": simdi}
u = {"asin": "B0TEST0001", "baslik": "Deneme Ürünü <b>", "fiyat": 6000.0}
IZ = {"url": U, "ad": "Depo", "esik": 30}
msj.clear()
g = {"panel": panel(6000, onceki=10000)}
assert t.depo_degerlendir(IZ, u, g, False, "", "https://x") is True and "🔥 Önceki fiyatından %40 ucuz" in msj[-1]
assert "Deneme Ürünü &lt;b&gt;" in msj[-1] and g["bildirilen"] == 6000
g = {"panel": panel(6000)}                                                  # sıfır da önceki de yok
assert t.depo_degerlendir(IZ, u, g, False, "", "x") is True and len(msj) == 1
g = {"panel": panel(6000, yeni=8000, onceki=20000)}                         # sıfır varsa o esas: %25 < %30
assert t.depo_degerlendir(IZ, u, g, False, "", "x") is True and len(msj) == 1 and "bildirilen" not in g
g = {"panel": panel(6000, yeni=10000, durum="İkinci El - İyi")}             # eşik tamam ama durum süzgeci
assert t.depo_degerlendir({**IZ, "durum": "çok iyi"}, u, g, False, "", "x") is True and len(msj) == 1
assert t.depo_degerlendir({**IZ, "durum": "iyi"}, u, g, False, "", "x") is True and len(msj) == 2
t.panel_hakki = 0                                                           # hak bitti: önbellek yoksa ertele
assert t.depo_degerlendir(IZ, u, {}, False, "", "x") is takip.ERTELE and len(msj) == 2
assert t.depo_degerlendir(IZ, u, {"panel": panel(6000, yeni=9000)}, False, "", "x") is True and len(msj) == 3
assert t.depo_degerlendir({"url": U, "ad": "D", "yeni": True}, u, {}, True, "", "x") is True and "alınamadı" in msj[-1]
assert t.depo_degerlendir({"url": U, "ad": "D", "yeni": True, "esik": 30}, u, {}, True, "", "x") is takip.ERTELE

# panelde site engeli: bildirim yok, bu tur başka panel okunmaz, Amazon geri çekilmesi devreye girer
cevap["arama"] = kartli(arama, 3000)
cevap["aod"] = {"B0HJWZZVDB": '<html><form action="/errors/validateCaptcha"></form></html>'}
t.engeli_gec = lambda sayfa, url: False
t.engel = False; msj.clear(); istek.clear()
t.izleme_calistir(iz2)
assert t.engel and t.panel_hakki == 0 and not msj
assert len([u for u in istek if "aodAjaxMain" in u]) == 1
assert not t.gecmis["depo:B0HJWZZVDB"].get("panel_bekle")                  # engelde 1 saat bekleme yok
t.komut("/izlesil 1")

# ---- kelime süzgeci
assert takip.kelime_listesi("apple, iphone 16 ,,ssd") == ["apple", "iphone 16", "ssd"]
KU = takip.kelime_uyar; K = ["apple", "iphone", "ram", "ssd"]
assert KU(K, "Kingston SSD 1TB") and KU(K, "iPhone16 kılıf") and KU(K, "İPHONE 15") and KU(K, "16GB RAM'li")
assert not KU(K, "Program kitabı") and not KU(K, "Stanley termos") and not KU(K, "Pineapple dilimleyici")
assert KU(["iphone 16"], "Apple iPhone 16 Pro") and not KU(["iphone 16"], "Apple iPhone 15 Pro")
assert KU(None, "her şey") and KU([], "her şey")
assert "kelime=apple" in t.komut(f"/izle {U} kelime=")

cevap["arama"] = arama; cevap["aod"] = {}; msj.clear(); istek.clear()
c = t.komut(f"/izle {U} 1sayfa yeni kelime=stanley,razer"); print(c)
iz4 = t.izlemeler()[0]; uyan = sum(KU(["stanley", "razer"], u["baslik"]) for u in ur)
assert iz4["kelimeler"] == ["stanley", "razer"] and uyan == 8
assert "Kelime süzgeci (stanley, razer): 8 ürün uyuyor" in c
L = t.komut("/izlemeler"); assert "kelime: stanley, razer" in L and "24 ürün (8 uyan)" in L, L
for a in t.durum["izleme"][U]["gorulen"]: t.durum["izleme"][U]["gorulen"][a] = "2000-01-01T00:00:00"
istek.clear(); t.izleme_calistir(iz4)
paneller = [re.search(r"asin=(\w+)", u).group(1) for u in istek if "aodAjaxMain" in u]
uyanlar = {u["asin"] for u in ur if KU(["stanley", "razer"], u["baslik"])}
assert len(paneller) == 8 and set(paneller) == uyanlar                      # uymayanların paneli okunmaz
assert len(msj) == 8 and all(re.search("stanley|razer", m, re.I) for m in msj)
# süzgeç değişince eski ürünler 'yeni' sayılmaz
assert "Inissia" not in t.komut("/izlekelime 1") and "stanley, razer" in t.komut("/izlekelime 1")
c = t.komut("/izlekelime 1 inissia, spigen kamera"); assert "inissia, spigen kamera" in c, c
assert t.izlemeler()[0]["kelimeler"] == ["inissia", "spigen kamera"]
msj.clear(); istek.clear(); t.izleme_calistir(t.izlemeler()[0]); assert istek == [U] and not msj
assert "(6 uyan)" in t.komut("/izlemeler")                                  # Inissia + 5 Spigen kamera lens
assert "kaldırıldı" in t.komut("/izlekelime 1 sil") and "kelimeler" not in t.izlemeler()[0]
assert "Bu numarada izleme yok" in t.komut("/izlekelime 9 ssd") and "Örnek" in t.komut("/izlekelime")
shutil.rmtree(tmp)
print("DEPO TESTLERİ GEÇTİ")
