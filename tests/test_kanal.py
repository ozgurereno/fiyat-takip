"""Depo kanalı doğrulaması: dinlenen kanalda paylaşılan Amazon ürünü teklif panelinden doğrulanır,
kullanıcının kurallarına (kelime, durum, sıfırına göre yüzde) uyarsa sesli bildirilir."""
import sys, types, asyncio, shutil, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fiyat_takip"))
FIX = Path(__file__).resolve().parent / "fixtures"
import takip, grup
from bs4 import BeautifulSoup
aod = open(FIX / "amazon_depo_aod_inissia.html", encoding="utf-8").read()

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

# Amazon (teklif paneli) ve yönlendirme servisleri sahte
class R:
    def __init__(s, text, code=200): s.text, s.status_code, s.url = text, code, ""
    def raise_for_status(s):
        if s.status_code >= 400: raise Exception(f"HTTP {s.status_code}")
panel = {"r": R(aod)}; amazon = []
def amazon_get(url, timeout=0, params=None, headers=None):
    amazon.append(url); return panel["r"]
t.oturum.get = amazon_get
class Yanit:
    def __init__(s, yer): s.status_code, s.headers = 302, {"Location": yer}
YON = {"https://www.firsatl.ar/go/B0HJWZZVDB": Yanit("https://www.amazon.com.tr/dp/B0HJWZZVDB?tag=x-21&th=1"),
       "https://kisa.link/b": Yanit("https://www.amazon.com.tr/Inissia/dp/B0HJWZZVDB/ref=x"),
       "https://kisa.link/hb": Yanit("https://www.hepsiburada.com/urun-p-1")}
t.link_oturumu = types.SimpleNamespace(get=lambda url, allow_redirects=True, timeout=None: YON[url])
DUZ = "https://www.amazon.com.tr/dp/B0HJWZZVDB"

g = grup.GrupDinleyici(t, tmp / "gruplar.json", tmp / "oturum.txt", takip.fiyat_coz)
g.ayarlar["gruplar"] = [{"id": -100, "ad": "Amazon Depo <İkinci El>"}, {"id": -200, "ad": "Fırsatlar"}]
t.grup = g
class Olay:
    def __init__(s, chat_id, metin, linkler, id=7):
        s.chat_id, s.raw_text, s.id = chat_id, metin, id
        s.message = types.SimpleNamespace(entities=[types.SimpleNamespace(url=l) for l in linkler])
    async def get_chat(s):
        return types.SimpleNamespace(title=next(x["ad"] for x in g.ayarlar["gruplar"] if x["id"] == s.chat_id),
                                     username="amazondepo" if s.chat_id == -100 else None)
def gelsin(*a, **k):
    asyncio.run(g._mesaj(Olay(*a, **k)))
def sifirla():
    msj.clear(); ha.clear(); amazon.clear(); g.son_depo = {}
def degistir(durum, satici=None):
    """Panelin ikinci el teklifinin durum (ve satıcı) yazısını değiştirir."""
    soup = BeautifulSoup(aod, "html.parser")
    for o in soup.select("#aod-offer"):
        h = o.select_one("#aod-offer-heading")
        if "Yeni Gibi" in h.get_text():
            h.string = durum
            if satici:
                o.select_one("#aod-offer-soldBy").string = satici
    return str(soup)
METIN = "📦 Inissia D40 Siyah Kahve Makinesi\n💰 6.532 TL (Yeni Gibi)\n👉 FIRSATA GİT"

# ---- panel başlığı ve /grupdepo komutu
assert takip.aod_baslik(aod) == "Inissia D40 Siyah ve Kireç Çözme Kiti" and takip.aod_baslik("<html></html>") == ""
assert "Örnek" in t.komut("/grupdepo") and "Örnek" in t.komut("/grupdepo 9 30")
assert "Yüzde 1 ile 99" in t.komut("/grupdepo 1 150") and "Anlaşılmadı" in t.komut("/grupdepo 1 30 hızlı")
c = t.komut("/grupdepo 1 30 yenigibi kelime=kahve,inissia"); print(c)
assert "Depo doğrulama açık" in c and "&lt;İkinci El&gt;" in c and "%30 ve üzeri" in c and "“Yeni Gibi”" in c
assert g.ayarlar["gruplar"][0]["depo"] == {"esik": 30, "durum": "yeni gibi", "kelimeler": ["kahve", "inissia"]}
assert grup.json_oku(tmp / "gruplar.json", {})["gruplar"][0]["depo"]["esik"] == 30            # kaydedildi
oz = t.komut("/dinleme")
assert "Amazon Depo &lt;İkinci El&gt; · 📦 Depo doğrulama · kelime: kahve, inissia · en az Yeni Gibi · sıfırından %30+ ucuz" in oz, oz
assert "/grupdepo" in t.komut("/yardim")

# ---- %30 eşiği: Depo 6.532,69, sıfırı 6.999 (%7) -> tek panel isteği, bildirim yok
sifirla(); gelsin(-100, METIN, ["https://www.firsatl.ar/go/B0HJWZZVDB"])
assert amazon == [takip.AOD_URL.format("B0HJWZZVDB")] and not msj and not ha, (amazon, msj)
# aynı ürün 10 dk içinde başka kanaldan / düzenlemeyle gelirse yeniden okunmaz
gelsin(-100, METIN, ["https://kisa.link/b"], id=8); assert len(amazon) == 1
# ---- eşik %5: bildirilir, sesli uyarı düz linkle
t.komut("/grupdepo 1 5 yenigibi kelime=kahve,inissia"); sifirla()
gelsin(-100, METIN, ["https://www.firsatl.ar/go/B0HJWZZVDB"]); print(msj[-1])
assert len(amazon) == 1 and len(ha) == 1 and len(msj) == 1
b, m, u = ha[0]
assert b == "🔥 Amazon.com.tr fiyatından %7 ucuz" and u == DUZ and "Inissia D40" in m and "6.532,69 TL" in m and "Yeni Gibi" in m, ha
for parca in ("<b>🔥 Amazon.com.tr fiyatından %7 ucuz</b> · Amazon Depo &lt;İkinci El&gt;", f'<a href="{DUZ}">Inissia D40 Siyah ve Kireç Çözme Kiti</a>',
              "<b>6.532,69 TL</b>", "Satıcı: Amazon Depo", "Amazon.com.tr sıfırı 6.999,00 TL (%7 daha ucuz)", f'<a href="{DUZ}">Ürüne git</a>',
              '<a href="https://t.me/amazondepo/7">Mesaja git</a>'):
    assert parca in msj[0], parca
assert "firsatl.ar" not in msj[0]

# ---- kelime süzgecine uymayan paylaşım: Amazon'a hiç istek atılmaz
sifirla(); gelsin(-100, "📦 Huawei Watch GT5 Pro 8.503 TL", ["https://www.firsatl.ar/go/B0HJWZZVDB"])
assert not amazon and not msj
# ... ama /kelime kuralına uyarsa eskisi gibi grup alarmı çalar (Depo doğrulaması olmadan)
g.ayarlar["kurallar"] = [{"kelimeler": ["huawei"], "en_cok": None}]
gelsin(-100, "📦 Huawei Watch GT5 Pro 8.503 TL", ["https://www.firsatl.ar/go/B0HJWZZVDB"], id=9)
assert not amazon and len(ha) == 1 and "Grup alarmı" in msj[-1] and f'<a href="{DUZ}">Ürüne git</a>' in msj[-1]
g.ayarlar["kurallar"] = []
# Amazon dışı link: Depo doğrulaması yapılmaz
sifirla(); gelsin(-100, "Inissia kahve makinesi", ["https://kisa.link/hb"]); assert not amazon and not msj

# ---- durum süzgeci: 'İyi' durumdaki teklif 'yenigibi' kuralına uymaz
panel["r"] = R(degistir("İkinci El - İyi"))
sifirla(); gelsin(-100, METIN, ["https://kisa.link/b"]); assert len(amazon) == 1 and not msj
# ---- satılmış: panelde ikinci el teklif kalmamış -> sessiz
yalniz_yeni = degistir("Yeni", "Satıcı Amazon.com.tr")
assert takip.depo_ozet(takip.aod_coz(yalniz_yeni))["depo"] is None
panel["r"] = R(yalniz_yeni); sifirla(); gelsin(-100, METIN, ["https://kisa.link/b"]); assert len(amazon) == 1 and not msj

# ---- Amazon engeli: kurallar uygulanamadı, sesli uyarı yok, yalnızca haber; Amazon geri çekilmesi devreye girer
panel["r"] = R("<html>validateCaptcha</html>", 503); sifirla(); t.engel = False
gelsin(-100, METIN, ["https://kisa.link/b"]); print(msj[-1])
assert not ha and len(msj) == 1 and "doğrulanamadı" in msj[0] and "kurallarınız uygulanamadı" in msj[0] and t.engel
# kuralsız (yalnızca satışta mı) kanalda doğrulanamazsa paylaşım sesli bildirilir
t.komut("/grupdepo 2"); assert g.ayarlar["gruplar"][1]["depo"] == {}
sifirla(); gelsin(-200, "Kahve makinesi <b>fırsat</b>", ["https://kisa.link/b"])
assert len(ha) == 1 and ha[0][0] == "📦 Depo paylaşımı" and "&lt;b&gt;fırsat" in msj[0] and "Amazon'dan doğrulanamadı" in msj[0]
# ---- kuralsız kanal, doğrulandı: '📦 Depo'da satışta' değil oran varsa oranla başlar
panel["r"] = R(aod); sifirla(); gelsin(-200, "Kahve makinesi", ["https://kisa.link/b"])
assert ha[0][0] == "🔥 Amazon.com.tr fiyatından %7 ucuz" and "Fırsatlar" in msj[0]
p = takip.depo_ozet(takip.aod_coz(aod)); p["yeni"] = p["onceki"] = p["amazon"] = None
assert t.kanal_depo({"esik": 10}, "X")[0] == "dusuk"
t.kanal_panel = lambda asin: {**p}
assert t.kanal_depo({}, "X")[0] == "uygun" and t.kanal_depo({"esik": 10}, "X")[0] == "kiyas_yok"
del t.kanal_panel

# ---- saatlik sınır ve Amazon geri çekilmesi: panel okunmaz
t.kanal_istekleri = [time.time()] * takip.KANAL_SAATLIK; sifirla()
assert t.kanal_panel("B0HJWZZVDB") is None and not amazon
t.kanal_istekleri = [time.time() - 3700] * takip.KANAL_SAATLIK                                   # bir saatten eski: sayılmaz
assert t.kanal_panel("B0HJWZZVDB")["depo"]["fiyat"] == 6532.69 and len(t.kanal_istekleri) == 1
t.carpan = 2; assert t.kanal_panel("B0HJWZZVDB") is None and len(amazon) == 1; t.carpan = 1

# ---- kapatma
assert "Depo doğrulama kapatıldı" in t.komut("/grupdepo 1 kapat") and "depo" not in g.ayarlar["gruplar"][0]
sifirla(); gelsin(-100, METIN, ["https://kisa.link/b"]); assert not amazon and not msj
shutil.rmtree(tmp)
print("KANAL TESTLERİ GEÇTİ")
