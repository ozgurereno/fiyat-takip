import sys, shutil, tempfile, time
from pathlib import Path
from datetime import datetime, timedelta
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent / "fiyat_takip"))
FIX = _P(__file__).resolve().parent / "fixtures"
import takip
gercek = open(FIX / "vatan_ssd.html", encoding="utf-8").read()

# gerçek sayfa ayrıştırma
ur, toplam = takip.vatan_coz(gercek)
assert len(ur) == 24 and toplam == 5, (len(ur), toplam)
assert ur[0] == {"asin": "vatan:verbatim-256gb-vi550-s3-sata-3-0-ssd-okuma-550mb-yazma-460mb.html",
                 "url": "https://www.vatanbilgisayar.com/verbatim-256gb-vi550-s3-sata-3-0-ssd-okuma-550mb-yazma-460mb.html",
                 "baslik": "Verbatim 256GB Vi550 S3 SATA 3.0 SSD (Okuma 550MB / Yazma 460MB)", "fiyat": 3559.0, "not": ""}, ur[0]
adata = [u for u in ur if "ADATA 512GB Legend 710" in u["baslik"]][0]
assert adata["fiyat"] == 5599 and adata["not"] == "Web'e Özel", adata     # kampanya fiyatı
assert len({u["asin"] for u in ur}) == 24 and all(u["fiyat"] > 1000 for u in ur)
for u in ur[:6]: print(f'{u["fiyat"]:>9,.0f}  {u["not"]:12} {u["baslik"][:55]}')

U = "https://www.vatanbilgisayar.com/solid-state-disk/?srt=UP"
assert takip.site_bul(U) == "vatan" and takip.arama_url_temizle(U) == U
assert takip.arama_url_temizle(U + "&page=3") == U
assert takip.arama_url_temizle("https://www.vatanbilgisayar.com/solid-state-disk/") == "https://www.vatanbilgisayar.com/solid-state-disk/"
assert takip.arama_url_temizle("https://www.vatanbilgisayar.com/verbatim-256gb.html") is None
assert takip.arama_url_temizle("https://www.hepsiburada.com/ssd-c-123") is None
assert takip.sayfa_ekle(U, 3) == U + "&page=3"
assert takip.arama_adi(U) == "Vatan · solid state disk"

# uçtan uca: 5 sayfa okunur, kampanya fiyatı ile indirim yakalanır, aralık seçeneği
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
    def raise_for_status(s):
        if s.status_code >= 400: raise Exception(f"HTTP {s.status_code}")
istekler = []; sayfalar = {}
def get(url, timeout=0, params=None, headers=None):
    istekler.append(url)
    no = int(url.split("page=")[1]) if "page=" in url else 1
    return R(sayfalar.get(no, gercek))
t.oturum.get = get
def kart(slug, ad, fiyat, web=None):
    yard = f'<div class="price-basket-camp--helper"><span>Web\'e Özel <span>{web} TL</span></span></div>' if web else ""
    return (f'<div class="product-list product-list--list-page"><a class="product-list-link" href="https://www.vatanbilgisayar.com/{slug}.html">'
            f'<div class="product-list__product-name"><h3>{ad}</h3></div>{yard}<span class="product-list__price">{fiyat}</span></a></div>')
def sayfa(kartlar, toplam=3):
    return f'<html><div id="productsLoad">{"".join(kartlar)}</div><button id="loadMoreBtn" data-current-page="1" data-total-pages="{toplam}"></button></html>'
sayfalar = {1: sayfa([kart("a", "Samsung 990 Pro 2TB", "10.000")]), 2: sayfa([kart("b", "WD SN850X 1TB", "6.000")]),
            3: sayfa([kart("c", "Kingston NV3 1TB", "3.000")])}
c = t.komut(f"/izle {U} 30 5dk"); print(c)
assert "3 ürün bulundu" in c and "5 dakikada bir" in c
assert istekler == [U, U + "&page=2", U + "&page=3"], istekler
iz = t.izlemeler()[0]; assert iz["aralik"] == 300 and iz["esik"] == 30 and iz["ad"] == "Vatan · solid state disk"
for g in t.gecmis.values(): g["gunluk"] = {(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"): list(g["gunluk"].values())[0]}
sayfalar[2] = sayfa([kart("b", "WD SN850X 1TB", "6.000", web="3.900")])
t.izleme_calistir(iz); print(msj[-1])
assert "%35 indirim" in msj[-1] and "<b>3.900,00 TL</b> (Web'e Özel)" in msj[-1] and 'href="https://www.vatanbilgisayar.com/b.html"' in msj[-1]
assert "5 dk'da bir" in t.komut("/izlemeler")
# 403: engel, izlemeye özel geri çekilme (Amazon çarpanı etkilenmez)
sayfalar[1] = None
t.oturum.get = lambda url, timeout=0, params=None, headers=None: R("Access denied", 403)
saat = {"t": 10_000.0}; gercek_time = time.time; takip.time.time = lambda: saat["t"]
t.bekle = lambda s: None
t.aramalari_tara()
d = t.durum["izleme"][iz["url"]]
assert d["carpan"] == 2 and t.carpan == 1 and 2 * 300 * 0.85 <= d["sonraki"] - saat["t"] <= 2 * 300 * 1.15, d
saat["t"] += 100; n = d["hata_sayisi"]; t.aramalari_tara(); assert d["hata_sayisi"] == n      # vakti gelmedi
saat["t"] += 700; t.oturum.get = get; sayfalar[1] = sayfa([kart("a", "Samsung 990 Pro 2TB", "10.000")])
t.aramalari_tara(); assert d["carpan"] == 1 and d["hata_sayisi"] == 0
takip.time.time = gercek_time
# bozuk sayfa kaydedilir
t.oturum.get = lambda url, timeout=0, params=None, headers=None: R("<html>bakım</html>")
assert t.izleme_calistir(iz) is None and (tmp / "hata_vatan.html").exists()
assert "en az 1 dakika" in t.komut(f"/izle {U}&x=1 30sn")
assert "desteklenmiyor" in t.komut("/izle https://www.hepsiburada.com/ssd-c-123")
# kelime süzgeci Depo dışındaki izlemelerde de çalışır
t.oturum.get = get; msj.clear()
U2 = "https://www.vatanbilgisayar.com/ssd/"
sayfalar.clear(); sayfalar[1] = sayfa([kart("a", "Samsung 990 Pro 2TB", "10.000"), kart("k", "Kingston NV3 1TB", "3.000"),
                                       kart("s", "Sandisk Extreme Program SSD", "4.000")], toplam=1)
c = t.komut(f"/izle {U2} 30 kelime=samsung,ram"); print(c)
assert "Kelime süzgeci (samsung, ram): 1 ürün uyuyor" in c          # 'ram' 'Program' içinde eşleşmez
iz2 = [i for i in t.izlemeler() if i["url"] == U2][0]; assert iz2["kelimeler"] == ["samsung", "ram"]
assert "vatan:k.html" not in t.gecmis and "vatan:a.html" in t.gecmis
for g in t.gecmis.values(): g["gunluk"] = {(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"): list(g["gunluk"].values())[0]}
sayfalar[1] = sayfa([kart("a", "Samsung 990 Pro 2TB", "6.000"), kart("k", "Kingston NV3 1TB", "1.000"),
                     kart("s", "Sandisk Extreme Program SSD", "1.000")], toplam=1)
t.izleme_calistir(iz2)
assert len(msj) == 1 and "Samsung 990 Pro" in msj[0] and "%40 indirim" in msj[0], msj
assert "kelime: samsung, ram" in t.komut("/izlemeler") and "(1 uyan)" in t.komut("/izlemeler")
shutil.rmtree(tmp)
print("VATAN TESTLERİ GEÇTİ")
