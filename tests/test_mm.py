import sys, shutil, tempfile, json, re
from pathlib import Path
from datetime import datetime, timedelta
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent / "fiyat_takip"))
FIX = _P(__file__).resolve().parent / "fixtures"
import takip
gercek = open(FIX / "mediamarkt_telefon.html", encoding="utf-8").read()
ur, toplam = takip.mm_coz(gercek)
for u in ur: print(f'{u["fiyat"]:>10,.0f}  {u["baslik"][:60]}  {u["url"][-40:]}')
assert len(ur) == 12 and toplam == 30, (len(ur), toplam)
assert ur[0] == {"asin": "mm:1256758", "url": "https://www.mediamarkt.com.tr/tr/product/_apple-mjrr4tua-iphone-18-pro-256-gb-akilli-telefon-bordo-1256758.html",
                 "baslik": "APPLE MJRR4TU/A iPhone 18 Pro 256 GB Akıllı Telefon Bordo", "fiyat": 137999.0, "not": ""}, ur[0]
U = "https://www.mediamarkt.com.tr/tr/category/telefon-465595.html?marketplace=MediaMarkt"
assert takip.site_bul(U) == "mediamarkt" and takip.arama_url_temizle(U + "&page=2") == U
assert takip.arama_adi(U) == "MediaMarkt · telefon"
assert takip.arama_url_temizle("https://www.mediamarkt.com.tr/tr/product/_x-1256758.html") is None
assert takip.arama_adi("https://www.mediamarkt.com.tr/tr/search.html?query=iphone%2016") == "MediaMarkt · iphone 16"
# satın alınamayan ürün atlanır, promosyon fiyatı esas alınır
st_html = gercek.replace('"isAvailableAndBuyable":true', '"isAvailableAndBuyable":false', 1)
assert len(takip.mm_coz(st_html)[0]) == 11
i = gercek.index('"promoPrice":{"__typename":"CofrPriceFeaturePromoPrice","amount":137999')
indirimli = gercek[:i] + gercek[i:].replace('"amount":137999', '"amount":99999', 1)
assert takip.mm_coz(indirimli)[0][0]["fiyat"] == 99999
# süzgeçli link: sorgu metni olduğu gibi korunmalı ('%20' -> '+' olursa MediaMarkt 0 ürün döner)
SZ = ("https://www.mediamarkt.com.tr/tr/category/iphone-644527.html?brand=APPLE&marketplace=MediaMarkt"
      "&producttypeTRonly=Ak%C4%B1ll%C4%B1%20Telefon&rest[0]=brand:APPLE&rest[1]=marketplace:MediaMarkt"
      "&rest[2]=producttypeTRonly:Ak%C4%B1ll%C4%B1%20Telefon")
assert takip.arama_url_temizle(SZ + "&page=4") == SZ and takip.arama_url_temizle(SZ.replace("?", "?page=2&")) == SZ
assert takip.sayfa_ekle(SZ, 5) == SZ + "&page=5" and takip.sayfa_ekle(SZ + "&page=4", 5) == SZ + "&page=5"
assert takip.arama_adi(SZ) == "MediaMarkt · iphone"
sz = open(FIX / "mediamarkt_iphone_suzgecli.html", encoding="utf-8").read()
ur5, top5 = takip.mm_coz(sz)
assert top5 == 7 and len(ur5) == 11, (top5, len(ur5))        # 78 ürün / 12; 1 ürün geçici olarak satışta değil
assert "mm:1249239" not in {u["asin"] for u in ur5}          # TEMPORARILY_NOT_AVAILABLE
assert all(u["fiyat"] > 10000 and "iPhone" in u["baslik"] for u in ur5)
# Cloudflare doğrulama sayfası engel sayılır, bozuk sayfa kaydedilir
tmp = Path(tempfile.mkdtemp())
for d in ("AYAR_DOSYA","URUN_DOSYA","DURUM_DOSYA","IZLEME_DOSYA","GECMIS_DOSYA","CEREZ_DOSYA"):
    setattr(takip, d, tmp / getattr(takip, d).name)
takip.KLASOR = takip.HATA_KLASOR = tmp
takip.json_yaz(takip.AYAR_DOSYA, {"telegram_token": "T", "telegram_chat_id": "42"})
takip.json_yaz(takip.URUN_DOSYA, [])
takip.time.sleep = lambda x: None
t = takip.Takip(); msj = []; t.bildir = lambda m: msj.append(m) or True
class R:
    def __init__(s, text, code=200): s.text, s.status_code, s.url = text, code, ""
    def raise_for_status(s): pass
istek = []
def get(url, timeout=0, params=None, headers=None):
    istek.append(url); return R(cevap["r"])
t.oturum.get = get
cevap = {"r": gercek}
c = t.komut(f"/izle {U}&page=2 25 3sayfa 10dk"); print(c)
assert "36 ürün" not in c and "12 ürün" in c          # aynı sayfa döndüğü için tekrarlar birleşir
assert istek == [U, U + "&page=2", U + "&page=3"], istek
iz = t.izlemeler()[0]; assert iz["sayfa"] == 3 and iz["aralik"] == 600 and iz["esik"] == 25
assert "3 sayfa" in t.komut("/izlemeler")
for g in t.gecmis.values(): g["gunluk"] = {(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"): list(g["gunluk"].values())[0]}
cevap["r"] = indirimli; t.izleme_calistir(iz); print(msj[-1])
assert "%28 indirim" in msj[-1] and "<b>99.999,00 TL</b>" in msj[-1] and "1256758.html" in msj[-1]
cevap["r"] = '<html><title>Just a moment...</title><script src="/cdn-cgi/challenge-platform/x.js"></script></html>'
assert t.izleme_calistir(iz) is None and t.durum["izleme"][iz["url"]]["engel"]
cevap["r"] = "<html>bakım</html>"; assert t.izleme_calistir(iz) is None and (tmp / "hata_mediamarkt.html").exists()
assert "1 ile 30" in t.komut(f"/izle {U}&x=1 50sayfa")
shutil.rmtree(tmp)
print("MEDIAMARKT TESTLERİ GEÇTİ")
