import sys, shutil, tempfile, json
from pathlib import Path
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent / "fiyat_takip"))
FIX = _P(__file__).resolve().parent / "fixtures"
import takip
G = takip.genel_coz

# 1) Ticimax/T-Soft tarzı JSON-LD (fiyat metin, nokta ondalık)
s1 = '''<html><head><meta property="og:title" content="Aqara Su Valf Kontrol T1 | Nethouse">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","name":"Aqara Su Valf Kontrol T1 VC-X01D (Apple Home Destekli)",
"offers":{"@type":"Offer","price":"2999.00","priceCurrency":"TRY","availability":"https://schema.org/InStock"}}</script></head>
<body><h1>Aqara</h1><div class="related"><span class="price">1.299,00 TL</span></div></body></html>'''
assert G(s1) == {"baslik": "Aqara Su Valf Kontrol T1 VC-X01D (Apple Home Destekli)", "fiyat": 2999.0, "kaynak": "JSON-LD"}
# 2) @graph + teklif listesi + sayı fiyat; biri stokta yok
s2 = '''<script type="application/ld+json">{"@graph":[{"@type":"BreadcrumbList"},{"@type":["Product"],"name":"Sonoff Zigbee Akıllı Su Vanası",
"offers":[{"@type":"Offer","price":1849.9,"availability":"OutOfStock"},{"@type":"Offer","price":1899.9,"availability":"InStock"}]}]}</script>'''
assert G(s2)["fiyat"] == 1849.9
# 3) tümü stokta yok -> fiyat None (stok bildirimi için)
s3 = s1.replace("InStock", "OutOfStock"); assert G(s3)["fiyat"] is None
# 4) AggregateOffer lowPrice, Türkçe biçim
s4 = '<script type="application/ld+json">[{"@type":"Product","name":"X","offers":{"@type":"AggregateOffer","lowPrice":"1.249,90"}}]</script>'
assert G(s4)["fiyat"] == 1249.9
# 5) mikroveri ve meta etiketi
s5 = '<html><title>Ürün Y</title><div itemscope itemtype="http://schema.org/Product"><span itemprop="price" content="459.90">459,90 TL</span></div></html>'
assert G(s5) == {"baslik": "Ürün Y", "fiyat": 459.9, "kaynak": "meta"}
s6 = '<meta property="og:title" content="Z"><meta property="product:price:amount" content="12999">'
assert G(s6)["fiyat"] == 12999
# 6) bozuk JSON-LD atlanır; yapısal veri yoksa hata
try: G('<script type="application/ld+json">{bozuk</script><span class="fiyat">10 TL</span>'); assert False
except ValueError: pass

# 7) yapısal verisiz sayfada konum öğrenme: benzer ürün fiyatına takılmaz
s7 = '''<html><body><h1>Sonoff Vana</h1>
<div class="urun-detay"><div class="fiyat-alani"><span class="eski">2.499,00 TL</span><span class="product-price">1.899,90 TL</span></div></div>
<div class="similar-products"><div class="kart"><span class="product-price">1.899,90 TL</span></div></div>
<footer><span>1.899,90 TL</span></footer></body></html>'''
sec = takip.fiyat_konumu_bul(s7, 1899.90); print("seçici:", sec)
assert sec and G(s7, sec) == {"baslik": "Sonoff Vana", "fiyat": 1899.9, "kaynak": "öğretilen konum"}
assert G(s7.replace("1.899,90 TL</span></div></div>\n<div class=\"similar", "1.699,90 TL</span></div></div>\n<div class=\"similar"), sec)["fiyat"] == 1699.9
assert takip.fiyat_konumu_bul(s7, 5555) is None
# id'li öğe
s8 = '<div><span id="urunFiyat">₺2.999,00</span></div><span class="x">₺2.999,00</span>'
assert takip.fiyat_konumu_bul(s8, 2999) == "#urunFiyat"

# ---- uçtan uca: /ekle, öğrenme, fiyat düşüşü bildirimi, liste
tmp = Path(tempfile.mkdtemp())
for d in ("AYAR_DOSYA","URUN_DOSYA","DURUM_DOSYA","IZLEME_DOSYA","GECMIS_DOSYA","CEREZ_DOSYA"):
    setattr(takip, d, tmp / getattr(takip, d).name)
takip.KLASOR = takip.HATA_KLASOR = tmp
takip.json_yaz(takip.AYAR_DOSYA, {"telegram_token": "T", "telegram_chat_id": "42"})
takip.json_yaz(takip.URUN_DOSYA, [{"asin": "B08G1RB541", "hedef": None}])
t = takip.Takip(); msj = []; t.bildir = lambda m: msj.append(m) or True
class R:
    def __init__(s, text, code=200, url=""): s.text, s.status_code, s.url = text, code, url
    def raise_for_status(s): pass
sayfalar = {}
t.oturum.get = lambda url, timeout=0, params=None, headers=None: R(sayfalar[url])
N = "https://www.nethouse.com.tr/aqara-su-valf-kontrol-t1-vc-x01d-apple-home-destekli"
Q = "https://www.reqasmart.com/urun/sonoff-zigbee-akilli-su-vanasi"
sayfalar[N] = s1; sayfalar[Q] = s7
c = t.komut(f"/ekle {N} 2500"); print(c)
assert "Eklendi" in c and "Aqara Su Valf" in c and "2.999,00 TL" in c and N in c
c = t.komut(f"/ekle {Q}"); print(c)
assert "kendiliğimden bulamadım" in c and "/fiyat 3 2999,00" in c and (tmp / "hata_www.reqasmart.com.html").exists()
c = t.komut("/fiyat 3 1.899,90"); print(c)
assert "yerini öğrendim" in c and "1.899,90 TL" in c and t.urunler()[2]["secici"]
assert "zaten listede" in t.komut(f"/ekle {N}")
assert "gerek yok" in t.komut("/fiyat 1 100")
assert "bulamadım" in t.komut("/fiyat 3 7777")
# fiyat düşüşü ve hedef
sayfalar[N] = s1.replace('"2999.00"', '"2399.00"')
msj.clear(); t.kontrol(t.urunler()[1]); print(msj[-1])
assert "Fiyat düştü" in msj[-1] and "2.999,00 TL → <b>2.399,00 TL</b>" in msj[-1] and "Hedefinizin" in msj[-1] and N in msj[-1]
sayfalar[N] = s3; t.kontrol(t.urunler()[1])
sayfalar[N] = s1; t.kontrol(t.urunler()[1]); assert "Tekrar stokta" in msj[-1]
l = t.komut("/liste"); print(l)
assert "Aqara Su Valf" in l and "Sonoff Vana" in l and Q in l
# site engeli Amazon'un çarpanını etkilemez
t.oturum.get = lambda url, timeout=0, params=None, headers=None: R("yasak", 403)
t.engel = False; t.kontrol(t.urunler()[1]); assert not t.engel
assert "Bu linkten ürün çıkaramadım" in t.komut("/ekle merhaba")
shutil.rmtree(tmp)
print("GENEL SİTE TESTLERİ GEÇTİ")
