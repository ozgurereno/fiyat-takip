import sys, json, shutil, tempfile
from pathlib import Path
from unittest import mock
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent / "fiyat_takip"))
FIX = _P(__file__).resolve().parent / "fixtures"
import takip

# fiyat çözme
assert takip.fiyat_coz("1.234,56 TL") == 1234.56
assert takip.fiyat_coz("1.234,56TL") == 1234.56
assert takip.fiyat_coz("999,00 TL") == 999.0
assert takip.fiyat_coz("12.499 TL") == 12499.0
assert takip.fiyat_coz("₺1,234.56") == 1234.56
assert takip.fiyat_coz("") is None
assert takip.tl(1234.5) == "1.234,50 TL"

def sayfa(fiyat_html, ek=""):
    return f'''<html><body><span id="productTitle">  Deneme Ürünü 500GB  </span>
    <div id="corePriceDisplay_desktop_feature_div">{fiyat_html}</div>{ek}
    <div id="carousel"><span class="a-price"><span class="a-offscreen">5,00 TL</span></span></div></body></html>'''

yeni = '''<span class="a-price aok-align-center priceToPay"><span class="a-offscreen"> </span>
<span aria-hidden="true"><span class="a-price-whole">2.499<span class="a-price-decimal">,</span></span><span class="a-price-fraction">90</span><span class="a-price-symbol">TL</span></span></span>
<span class="a-price a-text-price" data-a-strike="true"><span class="a-offscreen">3.199,00 TL</span></span>'''
assert takip.sayfa_coz(sayfa(yeni)) == {"baslik": "Deneme Ürünü 500GB", "fiyat": 2499.90}
klasik = '<span class="a-price a-text-price"><span class="a-offscreen">3.199,00TL</span></span><span class="a-price priceToPay"><span class="a-offscreen">2.100,00TL</span></span>'
assert takip.sayfa_coz(sayfa(klasik))["fiyat"] == 2100.0
assert takip.sayfa_coz(sayfa("", '<div id="availability"><span>Şu anda mevcut değil.</span></div>'))["fiyat"] is None
assert takip.sayfa_coz(sayfa("", '<input id="priceValue" value="1750.5">'))["fiyat"] == 1750.5
try: takip.sayfa_coz("<html>Alışverişe devam et</html>"); assert False
except ValueError: pass

# uçtan uca: sahte ağ
tmp = Path(tempfile.mkdtemp())
for d in ("AYAR_DOSYA","URUN_DOSYA","DURUM_DOSYA","IZLEME_DOSYA","GECMIS_DOSYA","CEREZ_DOSYA"):
    setattr(takip, d, tmp / getattr(takip, d).name)
takip.KLASOR = takip.HATA_KLASOR = tmp
takip.json_yaz(takip.AYAR_DOSYA, {"telegram_token": "T", "telegram_chat_id": "42", "hata_esigi": 2})
takip.json_yaz(takip.URUN_DOSYA, [{"asin": "B08G1RB541", "hedef": 2000}])
t = takip.Takip()
mesajlar = []
t.bildir = lambda m: mesajlar.append(m) or True
class R:
    def __init__(s, text, code=200, url=""): s.text, s.status_code, s.url = text, code, url
    def raise_for_status(s): pass
cevap = {}
t.oturum.get = lambda url, timeout=0: cevap["r"]
u = t.urunler()[0]
p = lambda f: R(sayfa(f'<span class="a-price priceToPay"><span class="a-offscreen">{f}</span></span>'))

cevap["r"] = p("2.500,00 TL"); assert t.kontrol(u) == 2500 and not mesajlar          # ilk okuma: sessiz
cevap["r"] = p("2.500,00 TL"); t.kontrol(u); assert not mesajlar                      # değişmedi
cevap["r"] = p("2.650,00 TL"); t.kontrol(u); assert not mesajlar                      # artış: sessiz
cevap["r"] = p("1.990,00 TL"); t.kontrol(u)
assert "Fiyat düştü" in mesajlar[-1] and "2.650,00 TL → <b>1.990,00 TL</b>" in mesajlar[-1] and "🎯" in mesajlar[-1]
cevap["r"] = R(sayfa("", '<div id="outOfStock">x</div>')); assert t.kontrol(u) is None and len(mesajlar) == 1
cevap["r"] = p("2.100,00 TL"); t.kontrol(u); assert "Tekrar stokta" in mesajlar[-1] and "1.990,00" in mesajlar[-1]
# captcha: 2 hatada uyarı, tek kez; düzelince haber
cevap["r"] = R("<form action='/errors/validateCaptcha'>", 200)
t.kontrol(u); assert len(mesajlar) == 2 and t.engel
t.oturum.get = lambda url, timeout=0: cevap["r"]
t.kontrol(u); assert "okunamıyor" in mesajlar[-1] and len(mesajlar) == 3
t.oturum.get = lambda url, timeout=0: cevap["r"]
t.kontrol(u); assert len(mesajlar) == 3
t.oturum.get = lambda url, timeout=0: cevap["r"]
cevap["r"] = p("2.100,00 TL"); t.kontrol(u); assert "Tekrar okunabiliyor" in mesajlar[-1] and len(mesajlar) == 4
assert t.durum["urunler"]["B08G1RB541"]["en_dusuk"] == 1990

# komutlar
cevap["r"] = p("300,00 TL")
assert "Eklendi" in t.komut("/ekle https://www.amazon.com.tr/Bir-Urun/dp/B0CBN6KXNC/ref=sr_1?x=1 250")
assert t.urunler()[1] == {"asin": "B0CBN6KXNC", "hedef": 250.0}
assert "zaten" in t.komut("/ekle https://www.amazon.com.tr/dp/B0CBN6KXNC")
cevap["r"] = R(sayfa(""), url="https://www.amazon.com.tr/dp/B0FJRYZQGQ?ref=x")   # kısa link yönlendirmesi
assert "Eklendi" in t.komut("/ekle https://amzn.eu/d/abc123")
assert len(t.urunler()) == 3
l = t.komut("/liste"); print(l); assert "300,00 TL" in l and "hedef 250,00 TL" in l and "stokta yok" in l
assert "Hedef 1.500,00 TL" in t.komut("/hedef 1 1500") and t.urunler()[0]["hedef"] == 1500
assert "kaldırıldı" in t.komut("/hedef 1")
assert "Silindi" in t.komut("/sil 3") and len(t.urunler()) == 2
assert "numarada" in t.komut("/sil 9")
assert "Komutlar" in t.komut("/start")

# bekle(): yalnızca sahibinin komutu işlenir
gelen = [[{"update_id": 7, "message": {"chat": {"id": 99}, "text": "/liste"}},
          {"update_id": 8, "message": {"chat": {"id": 42}, "text": "/liste"}}]]
def tg(yontem, zaman_asimi=30, **v):
    import time; 
    if gelen: return gelen.pop()
    time.sleep(0.3); return []
t.tg = tg; n = len(mesajlar)
t.bekle(1); assert len(mesajlar) == n + 1 and t.durum["tg_offset"] == 9
# chat_id otomatik bulma + kapalı günlük özet
t.ayar["telegram_chat_id"] = ""; assert t.chat_id == ""
t.tg = lambda y, zaman_asimi=30, **v: [{"update_id": 1, "message": {"chat": {"id": 555}, "text": "/start"}}]
assert takip.chat_id_bul(t) and t.chat_id == "555"
t.ayar["gunluk_ozet"] = "kapali"; t.gunluk_ozet(); assert "son_ozet" not in t.durum
t.ayar["gunluk_ozet"] = "00:00"; t.gunluk_ozet(); assert "son_ozet" in t.durum

# ---- arama izleme
U = "https://www.amazon.com.tr/s?i=office-products&rh=n%3A12467009031%2Cp_4%3AConklin&s=price-asc-rank&qid=1794766062&xpid=oJJ6Lc2itEWCN&ref=sr_pg_1"
temiz = takip.arama_url_temizle(U)
assert temiz == "https://www.amazon.com.tr/s?i=office-products&rh=n%3A12467009031%2Cp_4%3AConklin&s=price-asc-rank", temiz
assert takip.arama_adi(temiz) == "Conklin"
assert takip.arama_url_temizle("https://www.amazon.com.tr/dp/B08G1RB541") is None
assert takip.arama_adi(takip.arama_url_temizle("https://www.amazon.com.tr/s?k=dolma+kalem&ref=x")) == "dolma kalem"
def kart(asin, ad, fiyat, ek="", sinif=""):
    return f"""<div data-component-type="s-search-result" data-asin="{asin}" class="s-result-item {sinif}">
    <h2 class="a-size-mini"><span>Conklin</span></h2><a><h2><span>{ad}</span></h2></a>
    <span class="a-price" data-a-color="base"><span class="a-offscreen">{fiyat}</span></span>
    <span class="a-price a-text-price" data-a-strike="true"><span class="a-offscreen">9.999,00 TL</span></span>{ek}</div>"""
def arama(kartlar, sonraki=""):
    return R("<html><body>" + "".join(kartlar) + sonraki + "</body></html>")
s1 = arama([kart("A000000001", "Duragraph Dolma Kalem", "2.000,00 TL"), kart("A000000002", "All American", "4.000,00 TL"),
            kart("A000000009", "Reklam", "1,00 TL", sinif="AdHolder"),
            '<div data-component-type="s-search-result" data-asin="A000000008"><h2>Fiyatsız</h2></div>'],
           '<a class="s-pagination-next" href="/s?i=office-products&page=2">Sonraki</a>')
s2 = arama([kart("A000000003", "Mark Twain", "6.000,00 TL")])
ur, nx = takip.arama_coz(s1.text)
assert [u["asin"] for u in ur] == ["A000000001", "A000000002"] and ur[0] == {"asin": "A000000001", "baslik": "Conklin Duragraph Dolma Kalem", "fiyat": 2000.0, "onceki": 9999.0}
assert nx == "https://www.amazon.com.tr/s?i=office-products&page=2"
takip.time.sleep = lambda x: None
sira = []
def get(url, timeout=0):
    sira.append(url); return s2 if "page=2" in url else cevap["r"]
t.oturum.get = get; mesajlar.clear(); t.bildir = lambda m: mesajlar.append(m) or True
cevap["r"] = s1
c = t.komut("/izle " + U); print(c)
assert "İzlemeye alındı" in c and "3 ürün" in c and "2.000,00 TL – 6.000,00 TL" in c and sira[0] == temiz
assert t.izlemeler() == [{"url": temiz, "ad": "Conklin", "esik": 50.0, "yeni": False, "alarm": False}]
assert "zaten" in t.komut("/izle " + U)
iz = t.izlemeler()[0]
# %40 düşüş: sessiz; %55 düşüş: bildirim; aynı fiyat: tekrar yok; daha da düşerse yeniden
cevap["r"] = arama([kart("A000000001", "Duragraph Dolma Kalem", "1.200,00 TL")]); s2 = arama([])
assert t.izleme_calistir(iz) == 1 and not mesajlar
cevap["r"] = arama([kart("A000000001", "Duragraph Dolma Kalem", "900,00 TL")])
t.izleme_calistir(iz); print(mesajlar[-1]); assert "%55 indirim" in mesajlar[-1] and "2.000,00 TL → <b>900,00 TL</b>" in mesajlar[-1]
t.izleme_calistir(iz); assert len(mesajlar) == 1
cevap["r"] = arama([kart("A000000001", "Duragraph Dolma Kalem", "800,00 TL")]); t.izleme_calistir(iz); assert len(mesajlar) == 2
cevap["r"] = arama([kart("A000000001", "Duragraph Dolma Kalem", "2.000,00 TL")]); t.izleme_calistir(iz)
cevap["r"] = arama([kart("A000000001", "Duragraph Dolma Kalem", "900,00 TL")]); t.izleme_calistir(iz); assert len(mesajlar) == 3
# geçmiş: olağan fiyat günlerin ortancası, eski günler budanır
from datetime import datetime, timedelta
g = t.gecmis["A000000002"]; gun = lambda n: (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")
g["gunluk"] = {gun(40): 9000, gun(3): 4000, gun(2): 4000, gun(1): 4200}
cevap["r"] = arama([kart("A000000002", "All American", "1.900,00 TL")]); t.izleme_calistir(iz)
assert "Olağan fiyat 4.000,00 TL" in mesajlar[-1] and gun(40) not in t.gecmis["A000000002"]["gunluk"]
# boş sayfa -> hata, eşikte uyarı; captcha -> engel
cevap["r"] = arama([]); n = len(mesajlar)
assert t.izleme_calistir(iz) is None and t.izleme_calistir(iz) is None and "okunamıyor" in mesajlar[-1] and (tmp / "hata_arama.html").exists()
assert "okunamıyor" in t.komut("/izlemeler")
cevap["r"] = arama([kart("A000000002", "All American", "1.900,00 TL")]); t.izleme_calistir(iz); assert "Tekrar okunabiliyor" in mesajlar[-1]
l = t.komut("/izlemeler"); print(l); assert "Conklin" in l and "%50+ düşüşte bildir" in l and "1 ürün" in l
assert "desteklenmiyor" in t.komut("/izle https://www.amazon.com.tr/dp/B08G1RB541")
assert "silindi" in t.komut("/izlesil 1") and t.izlemeler() == []
assert "/izle" in t.komut("/yardim")

# ---- "Alışverişe devam et" ara sayfası: gizli alanlarla form gönderilip yeniden denenir
ara = R('<form method="get" action="/errors/validateCaptcha"><input type="hidden" name="amzn" value="X1"><input type="hidden" name="amzn-r" value="/dp/B08G1RB541"><button>Alışverişe devam et</button></form>')
cagri = []; gecti = {"v": False}
def get(url, timeout=0, params=None, headers=None):
    cagri.append((url, params))
    if "validateCaptcha" in url: gecti["v"] = True; return R("ok")
    return p("1.500,00 TL") if gecti["v"] else ara
t.oturum.get = get
assert t.oku("B08G1RB541")["fiyat"] == 1500
assert cagri[1] == ("https://www.amazon.com.tr/errors/validateCaptcha", {"amzn": "X1", "amzn-r": "/dp/B08G1RB541"}) and len(cagri) == 3
# gerçek (yazı girilen) CAPTCHA geçilemez; sayfa kaydedilir
t.oturum.get = lambda url, timeout=0, params=None, headers=None: R('<form action="/errors/validateCaptcha"><input type="hidden" name="amzn" value="X"><input type="text" name="field-keywords"></form>')
try: t.oku("B08G1RB541"); assert False
except takip.Engellendi: assert (tmp / "hata_captcha.html").exists()
# çerezler saklanır ve yeni oturuma yüklenir
t.oturum = t.yeni_oturum(); t.oturum.cookies.set("session-id", "abc"); t.kaydet()
assert t.yeni_oturum().cookies.get("session-id") == "abc" and t.yeni_oturum(cerezli=False).cookies.get("session-id") is None

# ---- sesli alarm
assert "yalnızca Home Assistant" in t.komut("/alarmtest")
takip.HA_TOKEN = "TKN"; ha = []
class J:
    def __init__(s, j=None): s.j = j
    def json(s): return s.j
    def raise_for_status(s): pass
takip.requests.get = lambda url, timeout=0, headers=None: J([{"domain": "light", "services": {"turn_on": {}}}, {"domain": "notify", "services": {"notify": {}, "mobile_app_ozgur_iphone": {}, "mobile_app_ipad": {}}}])
takip.requests.post = lambda url, timeout=0, headers=None, json=None: ha.append((url, headers, json)) or J()
c = t.komut("/alarmtest"); assert c == "Sesli uyarı gönderildi: ipad, ozgur_iphone", c
t.ayar["alarm_cihazi"] = "iphone"; t.ayar_yukle = lambda: None; ha.clear()
assert t.komut("/alarmtest").endswith(": ozgur_iphone")
assert ha[0][0] == "http://supervisor/core/api/services/notify/mobile_app_ozgur_iphone" and ha[0][1] == {"Authorization": "Bearer TKN"}
assert ha[0][2]["data"]["push"]["sound"] == {"name": "default", "critical": 1, "volume": 1.0}
c = t.komut("/alarm 1 20"); assert "Alarm kuruldu" in c and t.urunler()[0]["alarm"] == 20
assert "alarm %20" in t.komut("/liste")
u = t.urunler()[0]; d = t.durum["urunler"][u["asin"]]; d.pop("gunluk", None); d.pop("hata_bildirildi", None)
t.oturum.get = lambda url, timeout=0, params=None, headers=None: cevap["r"]
ha.clear(); mesajlar.clear()
cevap["r"] = p("1.000,00 TL"); t.kontrol(u); assert not ha                       # olağan fiyat = 1000
cevap["r"] = p("900,00 TL"); t.kontrol(u); assert not ha                          # %10: alarm yok
cevap["r"] = p("790,00 TL"); t.kontrol(u)                                         # iki adımda %21: alarm
assert len(ha) == 1 and "%21" in ha[0][2]["title"] and ha[0][2]["data"]["url"].endswith("/dp/B08G1RB541")
assert "Alarm: %21 indirim" in mesajlar[-1] and "Sesli uyarı gönderildi" in mesajlar[-1]; print(mesajlar[-1])
t.kontrol(u); assert len(ha) == 1                                                 # aynı fiyat: tekrar yok
cevap["r"] = p("700,00 TL"); t.kontrol(u); assert len(ha) == 2                    # daha da düştü
# ertesi gün gece yarısından sonra düşmüş olsa da önceki günlere göre hesaplanır
from datetime import datetime, timedelta
d["gunluk"] = {(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"): 1000}; d.pop("alarm_fiyat"); ha.clear()
cevap["r"] = p("750,00 TL"); t.kontrol(u); assert len(ha) == 1 and "%25" in ha[0][2]["title"]
assert "kaldırıldı" in t.komut("/alarm 1") and t.urunler()[0]["alarm"] is None
shutil.rmtree(tmp)
print("TÜM TESTLER GEÇTİ")
