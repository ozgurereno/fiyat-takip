import sys, types, asyncio, shutil, tempfile, time, threading
from pathlib import Path
from datetime import datetime, timedelta
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent / "fiyat_takip"))
FIX = _P(__file__).resolve().parent / "fixtures"
import takip, grup

tmp = Path(tempfile.mkdtemp())
for d in ("AYAR_DOSYA","URUN_DOSYA","DURUM_DOSYA","IZLEME_DOSYA","GECMIS_DOSYA","CEREZ_DOSYA","GRUP_DOSYA","OTURUM_DOSYA"):
    setattr(takip, d, tmp / getattr(takip, d).name)
takip.KLASOR = takip.HATA_KLASOR = tmp
takip.json_yaz(takip.AYAR_DOSYA, {"telegram_token": "T", "telegram_chat_id": "42"})
takip.json_yaz(takip.URUN_DOSYA, [])
takip.time.sleep = lambda x: None
t = takip.Takip(); msj = []; ha = []
t.bildir = lambda m: msj.append(m) or True
t.kritik_uyari = lambda b, m, u=None: ha.append((b, m, u)) or ["mobile_app_x"]
class R:
    def __init__(s, text, code=200, url=""): s.text, s.status_code, s.url = text, code, url
    def raise_for_status(s): pass
cevap = {}
t.oturum.get = lambda url, timeout=0, params=None, headers=None: cevap["r"]

# 1) kullanıcının linki: srs korunur, ad numaralı markadan uydurulmaz
U = "https://www.amazon.com.tr/s?i=electronics&srs=21034474031&bbn=21034474031&rh=n%3A12466496031%2Cn%3A21034474031%2Cn%3A13709880031%2Cp_36%3A100000-%2Cp_123%3A110955&s=price-desc-rank"
temiz = takip.arama_url_temizle(U); print(temiz)
assert "srs=21034474031" in temiz and "bbn=21034474031" in temiz and "p_123%3A110955" in temiz
assert takip.arama_adi(temiz) == "Arama"

def kart(asin, ad, fiyat):
    return f'<div data-component-type="s-search-result" data-asin="{asin}"><h2><span>{ad}</span></h2><span class="a-price"><span class="a-offscreen">{fiyat}</span></span></div>'
sayfa = lambda *k: R("<html>" + "".join(k) + "</html>")
bos = R("<html><body><span>Arama sonucunuz için hiçbir sonuç bulunamadı.</span></body></html>")

# 2) depo boşken izleme: eklenir, sonra yeni çıkan ürün sesli bildirilir
cevap["r"] = bos
c = t.komut(f"/izle {U} yeni alarm Depo iPhone"); print(c)
assert "Şu an listede ürün yok" in c and "Listeye yeni bir ürün girince haber veririm (🚨 sesli uyarıyla)." in c, c
iz = t.izlemeler()[0]; assert iz == {"url": temiz, "ad": "Depo iPhone", "esik": None, "yeni": True, "alarm": True}
assert "yeni çıkanı bildir, 🚨 sesli" in t.komut("/izlemeler")
cevap["r"] = sayfa(kart("B0IPHONE01", "Apple iPhone 16 Pro 256 GB", "52.000,00 TL"))
t.izleme_calistir(iz); print(msj[-1])
assert "Yeni çıktı" in msj[-1] and "<b>52.000,00 TL</b>" in msj[-1] and ha[-1][2] == "https://www.amazon.com.tr/dp/B0IPHONE01"
n = len(msj); t.izleme_calistir(iz); assert len(msj) == n            # hâlâ listede: tekrar yok
cevap["r"] = bos; t.izleme_calistir(iz); assert len(msj) == n        # satıldı
cevap["r"] = sayfa(kart("B0IPHONE01", "Apple iPhone 16 Pro 256 GB", "52.000,00 TL"))
t.izleme_calistir(iz); assert len(msj) == n                          # 6 saat içinde geri geldi: titreme sayılır
d = t.durum["izleme"][temiz]; d["gorulen"]["B0IPHONE01"] = (datetime.now() - timedelta(hours=7)).isoformat()
t.izleme_calistir(iz); assert len(msj) == n + 1 and len(ha) == 2     # 7 saat sonra yeniden stok: bildir

# 3) bozuk sayfa (sonuç yok yazısı da yok) yine hata sayılır
cevap["r"] = R("<html>garip</html>"); assert t.izleme_calistir(iz) is None

# 4) yüzde + yeni birlikte; ilk taramada mevcut ürünler bildirilmez
t.komut("/izlesil 1"); msj.clear(); ha.clear()
cevap["r"] = sayfa(kart("B0A", "Ürün A", "1.000,00 TL"))
assert "ya da" in t.komut(f"/izle {U} 30 yeni")
iz = t.izlemeler()[0]; assert iz["esik"] == 30 and iz["yeni"] and not iz["alarm"]
assert len(msj) == 0
t.gecmis["B0A"]["gunluk"] = {(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"): 1000}
cevap["r"] = sayfa(kart("B0A", "Ürün A", "650,00 TL")); t.izleme_calistir(iz)
assert "%35 indirim" in msj[-1] and not ha
assert "Yüzde 1 ile 99" in t.komut("/izle https://www.amazon.com.tr/s?k=kalem 150")

# 5) grup komutları kapalıyken yönlendirme
assert "Grup dinleme kapalı" in t.komut("/gruplar")
assert "/grupekle" in t.komut("/yardim")

# 6) zamanlayıcı: aramalar ürün turunu beklemeden kendi aralığında çalışır
t2 = takip.Takip(); t2.bildir = lambda m: True
sayac = {"urun": 0, "arama": 0, "bekle": 0}
t2.urunler = lambda: [{"asin": "X"}]
t2.kontrol = lambda u: sayac.__setitem__("urun", sayac["urun"] + 1)
t2.izlemeler = lambda: [{"url": "u", "ad": "a"}]
t2.izleme_calistir = lambda iz: sayac.__setitem__("arama", sayac["arama"] + 1)
saat = {"t": 1000.0}
takip.time.time = lambda: saat["t"]
def bekle(s):
    saat["t"] += s; sayac["bekle"] += 1
    if saat["t"] > 1000 + 3600: raise StopIteration
t2.bekle = bekle
takip.json_yaz(takip.AYAR_DOSYA, {"telegram_token": "T", "telegram_chat_id": "42", "kontrol_araligi_sn": 300, "arama_araligi_sn": 120})
try: t2.calis()
except StopIteration: pass
print(sayac)
assert 10 <= sayac["urun"] <= 16 and 25 <= sayac["arama"] <= 36, sayac
takip.time.time = time.time

# ---- grup modülü (sahte Telethon ile)
g = grup.GrupDinleyici(t, tmp / "gruplar.json", tmp / "oturum.txt", takip.fiyat_coz)
assert grup.normalle("IPHONE İnanılmaz ıphone") == "iphone inanilmaz iphone"
assert "Alarm kuralı eklendi" in g.komut("/kelime", ["/kelime", "iphone", "depo"])
g.komut("/kelime", ["/kelime", "iphone", "16", "pro", "<50.000"])
assert g.eslesen_kural("🔥 Amazon DEPO'da IPHONE 15 128GB 38.999 TL")["kelimeler"] == ["iphone", "depo"]
assert g.eslesen_kural("iPhone 16 Pro 256GB sadece 47.500 TL!")["en_cok"] == 50000
assert g.eslesen_kural("iPhone 16 Pro 256GB 61.000 TL") is None             # fiyat sınırı üstünde
assert g.eslesen_kural("iPhone 16 Pro: eski fiyat ₺65.000, yeni ₺45.999") is not None   # en düşük fiyat
assert g.eslesen_kural("iPhone 16 Pro stokta!") is not None                  # fiyat yoksa yine bildir
assert g.eslesen_kural("Samsung depo fırsatı") is None
assert "iphone + 16 + pro (en çok 50.000 TL)" in g.komut("/dinleme", ["/dinleme"])
assert "Kural silindi" in g.komut("/kelimesil", ["/kelimesil", "2"]) and len(g.ayarlar["kurallar"]) == 1
assert grup.json_oku(tmp / "gruplar.json", {})["kurallar"] == [{"kelimeler": ["iphone", "depo"], "en_cok": None}]
# alarm + tekrar engeli
msj.clear(); ha.clear()
kural = g.ayarlar["kurallar"][0]
assert g.alarm("Fırsat Grubu", "iPhone depo 30.000 TL", kural, "https://amzn.eu/d/x", "https://t.me/c/1/5")
assert not g.alarm("Diğer Grup", "iPhone depo 30.000 TL!!", kural, "https://amzn.eu/d/x", "https://t.me/c/2/9")
assert len(ha) == 1 and ha[0][2] == "https://amzn.eu/d/x" and "Ürüne git" in msj[-1] and "Fırsat Grubu" in msj[-1]
print(msj[-1])

# sahte telethon
class Hata(Exception): pass
errors = types.SimpleNamespace(SessionPasswordNeededError=type("SP", (Hata,), {}), PhoneCodeInvalidError=type("PI", (Hata,), {}),
                               PhoneCodeExpiredError=type("PE", (Hata,), {}), PasswordHashInvalidError=type("PH", (Hata,), {}))
class Oturum:
    def __init__(s, x=""): s.x = x
    def save(s): return "OTURUM123"
class Dialog:
    def __init__(s, id, name, grup=True): s.id, s.name, s.is_group, s.is_channel = id, name, grup, False
class Client:
    son = None
    def __init__(s, oturum, api_id, api_hash):
        s.oturum, s.session, s.yetkili, s.isleyiciler, s.kodlar = oturum, Oturum(), bool(oturum.x), [], []
        s.kopma = asyncio.Event() if False else None; Client.son = s
    async def connect(s): s.kopma = asyncio.Event()
    async def is_user_authorized(s): return s.yetkili
    async def send_code_request(s, tel): s.kodlar.append(tel)
    async def sign_in(s, tel=None, kod=None, password=None):
        if password: s.yetkili = password == "2fa"; return
        if kod == "11111": raise errors.PhoneCodeInvalidError()
        if kod == "22222": raise errors.SessionPasswordNeededError()
        s.yetkili = True
    def add_event_handler(s, f, e): s.isleyiciler.append(f)
    async def run_until_disconnected(s): await s.kopma.wait()
    async def disconnect(s): pass
    async def iter_dialogs(s):
        for d in [Dialog(-1001, "Fırsat Avcıları"), Dialog(5, "Annem", False), Dialog(-1002, "iPhone Depo Takip")]: yield d
events = types.SimpleNamespace(NewMessage=lambda **k: "yeni", MessageEdited=lambda **k: "duz")
sys.modules["telethon"] = types.SimpleNamespace(TelegramClient=Client, errors=errors, events=events)
sys.modules["telethon.sessions"] = types.SimpleNamespace(StringSession=Oturum)

t.ayar.update(telegram_api_id="123", telegram_api_hash="abc", telegram_telefon="+90 555 000 00 00", telegram_2fa_sifre="2fa")
msj.clear()
g2 = grup.GrupDinleyici(t, tmp / "gruplar2.json", tmp / "oturum2.txt", takip.fiyat_coz)
g2.baslat()
def bekle_kosul(f, s=3):
    son = time.time() + s
    while time.time() < son:
        if f(): return True
        time.sleep(0.02)
    raise AssertionError("zaman aşımı")
bekle_kosul(lambda: g2.durum == "giriş kodu bekleniyor" and msj)
assert Client.son.kodlar == ["+905550000000"] and "/kod 1-2-3-4-5" in msj[-1]
assert "Kod alındı" in g2.komut("/kod", ["/kod", "1-1-1-1-1"])
bekle_kosul(lambda: "Kod hatalı" in msj[-1])
g2.komut("/kod", ["/kod", "2", "2", "2", "2", "2"])        # 2FA gerekiyor, ayardaki şifre kullanılır
bekle_kosul(lambda: g2.durum == "çalışıyor")
bekle_kosul(lambda: "Grup dinleme açık" in msj[-1])
assert (tmp / "oturum2.txt").read_text() == "OTURUM123"
assert "Şu an giriş kodu beklenmiyor" in g2.komut("/kod", ["/kod", "1"])
l = g2.komut("/gruplar", ["/gruplar"]); print(l)
assert "1. Fırsat Avcıları" in l and "Annem" not in l and "2. iPhone Depo Takip" in l
assert "1. iPhone Depo Takip" in g2.komut("/gruplar", ["/gruplar", "IPHONE"])
g2.komut("/gruplar", ["/gruplar"])
assert "Dinlemeye alındı: Fırsat Avcıları, iPhone Depo Takip" in g2.komut("/grupekle", ["/grupekle", "1", "2"])
assert "✅ Fırsat Avcıları" in g2.komut("/gruplar", ["/gruplar"])
g2.komut("/kelime", ["/kelime", "iphone", "depo"])
# gelen mesaj
class Olay:
    def __init__(s, chat_id, metin, id=77):
        s.chat_id, s.raw_text, s.id = chat_id, metin, id
        s.message = types.SimpleNamespace(entities=[types.SimpleNamespace(url="https://www.amazon.com.tr/dp/B0GIZLI")])
    async def get_chat(s): return types.SimpleNamespace(title="Fırsat Avcıları", username=None)
isle = Client.son.isleyiciler[0]; ha.clear(); msj.clear()
fut = asyncio.run_coroutine_threadsafe(isle(Olay(-1001, "Amazon Depo: iPhone 15 31.999 TL")), g2.loop); fut.result(3)
assert ha and ha[-1][2] == "https://www.amazon.com.tr/dp/B0GIZLI" and "https://t.me/c/1/77" in msj[-1], (ha, msj)
asyncio.run_coroutine_threadsafe(isle(Olay(5, "iphone depo")), g2.loop).result(3)          # dinlenmeyen sohbet
asyncio.run_coroutine_threadsafe(isle(Olay(-1002, "Samsung depo")), g2.loop).result(3)     # kurala uymuyor
assert len(ha) == 1
assert "Dinleme bırakıldı: Fırsat Avcıları" in g2.komut("/grupsil", ["/grupsil", "1"])

# eksik telefon: kod istemeden durur
t.ayar["telegram_telefon"] = ""; msj.clear()
g3 = grup.GrupDinleyici(t, tmp / "g3.json", tmp / "o3.txt", takip.fiyat_coz); g3.baslat()
bekle_kosul(lambda: g3.durum == "telefon numarası girilmemiş" and msj)
assert "telegram_telefon" in msj[-1]
shutil.rmtree(tmp)
print("YENİ TESTLER GEÇTİ")
