#!/usr/bin/env python3
"""Amazon.com.tr fiyat takibi - fiyat düşünce Telegram bildirimi gönderir.

Kullanım:
  python3 takip.py --test   Her ürünü bir kez okur, Telegram'a deneme mesajı yollar
  python3 takip.py          Sürekli takip (normalde systemd servisi çalıştırır)
"""
import argparse
import hashlib
import html
import json
import logging
import math
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import shutil
import statistics
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from grup import YARDIM as GRUP_YARDIM, GrupDinleyici

KLASOR = Path(__file__).resolve().parent
# Home Assistant uygulaması olarak çalışırken ayarlar arayüzden gelir (/data/options.json)
# ve veriler kalıcı /data klasöründe tutulur; aksi halde her şey betiğin klasöründedir.
HA = Path("/data/options.json").exists()
VERI = Path("/data") if HA else KLASOR
AYAR_DOSYA = VERI / ("options.json" if HA else "ayarlar.json")
URUN_DOSYA = VERI / "urunler.json"
DURUM_DOSYA = VERI / "durum.json"
IZLEME_DOSYA = VERI / "izlemeler.json"   # izlenen arama sayfaları
GECMIS_DOSYA = VERI / "gecmis.json"      # aramalarda görülen ürünlerin fiyat geçmişi
CEREZ_DOSYA = VERI / "cerezler.json"     # yeniden başlatmalarda oturumu korumak için
GRUP_DOSYA = VERI / "gruplar.json"       # dinlenen Telegram grupları ve alarm kelimeleri
OTURUM_DOSYA = VERI / "telegram_oturum.txt"   # grup dinleme için Telegram oturumu (gizli)
HATA_KLASOR = Path("/share/fiyat_takip") if HA else KLASOR

VARSAYILAN = {
    "telegram_token": "",
    "telegram_chat_id": "",
    "kontrol_araligi_sn": 180,   # iki tur arası bekleme (saniye)
    "arama_araligi_sn": 600,     # izlenen arama sayfalarının taranma aralığı
    "arama_sayfa_siniri": 5,     # bir Amazon aramasında en çok kaç sonuç sayfası okunsun
    "vatan_sayfa_siniri": 10,    # bir Vatan kategorisinde en çok kaç sayfa okunsun (24 ürün/sayfa)
    "mediamarkt_sayfa_siniri": 10,   # MediaMarkt'ta en çok kaç sayfa okunsun (12 ürün/sayfa)
    "gecmis_gun": 30,            # olağan fiyat kaç günlük geçmişe göre hesaplansın
    "min_dusus_tl": 0,           # bundan küçük düşüşler bildirilmez
    "artis_bildir": False,       # fiyat artışını da bildir
    "hata_esigi": 5,             # art arda kaç başarısız okumada uyarı gelsin
    "gunluk_ozet": "09:00",      # her gün bu saatte liste gönder ("" = kapalı)
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
}

HA_API = "http://supervisor/core/api"       # Home Assistant'a uygulama içinden erişim
HA_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")

ASIN_RE = re.compile(r"/(?:dp|gp/product|gp/aw/d|product)/([A-Z0-9]{10})(?=[/?#]|$)")
log = logging.getLogger("takip")


class Engellendi(Exception):
    """Amazon bot koruması (CAPTCHA / 503) devreye girdi."""


# ---------------------------------------------------------------- yardımcılar
def json_oku(dosya, varsayilan):
    try:
        return json.loads(dosya.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return varsayilan


def json_yaz(dosya, veri):
    gecici = dosya.with_suffix(".tmp")
    gecici.write_text(json.dumps(veri, ensure_ascii=False, indent=2), encoding="utf-8")
    gecici.replace(dosya)


def tl(x):
    s = f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} TL"


def kisalt(metin, n=70):
    metin = metin or "?"
    return metin if len(metin) <= n else metin[: n - 1] + "…"


def fiyat_coz(metin):
    """'1.234,56 TL' -> 1234.56"""
    m = re.sub(r"[^\d.,]", "", metin or "").strip(".,")
    if not m:
        return None
    if "," in m and "." in m:
        if m.rfind(",") > m.rfind("."):
            m = m.replace(".", "").replace(",", ".")
        else:
            m = m.replace(",", "")
    elif "," in m:
        m = m.replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", m):
        m = m.replace(".", "")
    try:
        f = float(m)
    except ValueError:
        return None
    return f if f > 0 else None


def olagan_fiyat(gun, fiyat, gecmis_gun):
    """Günlük fiyat kaydını günceller ve olağan fiyatı döndürür: önceki günlerin
    ortancası; önceki gün yoksa bugün ilk görülen fiyat."""
    bugun = datetime.now().strftime("%Y-%m-%d")
    sinir = (datetime.now() - timedelta(days=int(gecmis_gun))).strftime("%Y-%m-%d")
    gun.setdefault(bugun, fiyat)
    for k in [k for k in gun if k < sinir]:
        del gun[k]
    onceki = [v for k, v in gun.items() if k < bugun]
    return statistics.median(onceki) if onceki else gun[bugun]


def a_price_coz(p):
    """Bir <span class="a-price"> öğesinden fiyatı okur."""
    off = p.select_one(".a-offscreen")
    metin = off.get_text(strip=True) if off else ""
    if not metin:
        tam = p.select_one(".a-price-whole")
        kesir = p.select_one(".a-price-fraction")
        if tam:
            metin = (tam.get_text(strip=True).rstrip(",.") + ","
                     + (kesir.get_text(strip=True) if kesir else "00"))
    return fiyat_coz(metin)


def asil_fiyat(kutu):
    """Kutudaki ilk gerçek satış fiyatı (üstü çizili liste fiyatı ve birim fiyat hariç)."""
    for p in kutu.select("span.a-price"):
        if "a-text-price" in p.get("class", []) or p.get("data-a-strike") == "true":
            continue
        f = a_price_coz(p)
        if f:
            return f
    return None


def site_bul(url):
    host = urlsplit(url).netloc.lower()
    if host.endswith("amazon.com.tr"):
        return "amazon"
    if host.endswith("vatanbilgisayar.com"):
        return "vatan"
    if host.endswith("mediamarkt.com.tr"):
        return "mediamarkt"
    return None


def arama_url_temizle(url):
    """Arama/kategori linkinden oturuma özel parametreleri atar. Desteklenmiyorsa None."""
    p = urlsplit(url.strip())
    if site_bul(url) == "vatan":
        if p.path.rstrip("/") in ("", "/") or p.path.endswith(".html"):
            return None   # ana sayfa ya da tek ürün sayfası
        q = _sorgu_page_siz(p.query)
        return "https://www.vatanbilgisayar.com" + p.path + ("?" + q if q else "")
    if site_bul(url) == "mediamarkt":
        if not ("/category/" in p.path or p.path.endswith("/search.html")):
            return None   # yalnızca kategori ve arama sayfaları
        q = _sorgu_page_siz(p.query)
        return "https://www.mediamarkt.com.tr" + p.path + ("?" + q if q else "")
    if site_bul(url) != "amazon" or not (p.path == "/s" or p.path.startswith("/s/")):
        return None
    q = [(k, v) for k, v in parse_qsl(p.query)
         if k in ("k", "i", "rh", "s", "bbn", "srs", "emi", "me", "low-price", "high-price")]
    return "https://www.amazon.com.tr/s?" + urlencode(q) if q else None


def arama_adi(url):
    if site_bul(url) == "vatan":
        return "Vatan · " + urlsplit(url).path.strip("/").split("/")[-1].replace("-", " ")
    if site_bul(url) == "mediamarkt":
        q = dict(parse_qsl(urlsplit(url).query))
        if q.get("query"):
            return "MediaMarkt · " + q["query"]
        son = urlsplit(url).path.rstrip("/").split("/")[-1].removesuffix(".html")
        return "MediaMarkt · " + re.sub(r"-\d+$", "", son).replace("-", " ")
    q = dict(parse_qsl(urlsplit(url).query))
    if q.get("k"):
        return q["k"]
    for m in re.finditer(r"p_(?:4|89|123):([^,|]+)", q.get("rh", "")):   # marka süzgeci
        if not m.group(1).isdigit():
            return m.group(1)
    return "Arama"


def arama_coz(sayfa):
    """Arama sonuç sayfası -> ([{'asin','baslik','fiyat'}], sonraki sayfa adresi | None)"""
    soup = BeautifulSoup(sayfa, "html.parser")
    urunler = []
    for kart in soup.select('div[data-component-type="s-search-result"][data-asin]'):
        asin = kart.get("data-asin")
        if not asin or "AdHolder" in kart.get("class", []):   # sponsorlu sonuçları atla
            continue
        parcalar = []
        for h in kart.select("h2"):
            t = h.get_text(" ", strip=True)
            if t and t not in parcalar:
                parcalar.append(t)
        fiyat = asil_fiyat(kart)
        if parcalar and fiyat:
            urunler.append({"asin": asin, "baslik": " ".join(parcalar), "fiyat": fiyat})
    sonraki = soup.select_one("a.s-pagination-next[href]")
    return urunler, (urljoin("https://www.amazon.com.tr", sonraki["href"]) if sonraki else None)


def vatan_coz(sayfa):
    """Vatan kategori sayfası -> ([{'asin','baslik','fiyat','url','not'}], toplam sayfa)"""
    soup = BeautifulSoup(sayfa, "html.parser")
    kap = soup.select_one("#productsLoad") or soup
    urunler = []
    for kart in kap.select("div.product-list--list-page"):
        a = kart.select_one("a.product-list-link[href]")
        ad = kart.select_one(".product-list__product-name")
        fiyat_el = kart.select_one(".product-list__price")
        if not (a and ad and fiyat_el):
            continue
        fiyat = fiyat_coz(fiyat_el.get_text(strip=True))
        not_ = ""
        yardim = kart.select_one(".price-basket-camp--helper")
        if yardim:   # "Web'e Özel 5.599 TL" gibi kampanya fiyatı daha düşükse onu al
            metin = yardim.get_text(" ", strip=True)
            for m in re.finditer(r"([\d.,]+)\s*TL", metin):
                f = fiyat_coz(m.group(1))
                if f and (not fiyat or f < fiyat):
                    fiyat, not_ = f, re.sub(r"\s*[\d.,]+\s*TL.*", "", metin).strip()
        if not fiyat:
            continue
        url = urljoin("https://www.vatanbilgisayar.com", a["href"])
        urunler.append({"asin": "vatan:" + urlsplit(url).path.strip("/"), "url": url,
                        "baslik": ad.get_text(" ", strip=True), "fiyat": fiyat, "not": not_})
    dugme = soup.select_one("#loadMoreBtn[data-total-pages]")
    try:
        toplam = int(dugme["data-total-pages"]) if dugme else 1
    except ValueError:
        toplam = 1
    return urunler, max(toplam, 1)


def mm_durum(sayfa):
    """MediaMarkt sayfasına gömülü veriyi (window.__PRELOADED_STATE__) çözer."""
    i = sayfa.find("window.__PRELOADED_STATE__")
    if i < 0:
        raise ValueError("MediaMarkt sayfa verisi bulunamadı")
    i = sayfa.index("=", i) + 1
    j = sayfa.find("</script>", i)
    ham = sayfa[i:j].strip().rstrip(";")
    ham = re.sub(r"(?<=[:\[,])undefined(?=[,\]}])", "null", ham)
    return json.loads(ham)


def mm_coz(sayfa):
    """MediaMarkt kategori/arama sayfası -> ([ürünler], toplam sayfa)"""
    ap = mm_durum(sayfa).get("apolloState", {})
    sira = []
    for k, v in ap.items():
        if k.startswith("ProductListPage"):
            sira += [p["productId"] for p in v.get("products") or [] if p.get("productId")]
    urun, fiyat, durum = {}, {}, {}
    for v in ap.values():
        if not isinstance(v, dict):
            continue
        tur = v.get("__typename")
        if tur == "GraphqlProduct":
            urun[str(v.get("id"))] = v
        elif tur == "CofrPriceFeature":
            fiyat[str(v.get("id", "")).split(":")[-1]] = v
        elif tur == "CofrOnlineStatusFeature":
            durum[str(v.get("id", "")).split(":")[-1]] = v
    sonuc = []
    for pid in dict.fromkeys(sira):
        u, f, d = urun.get(pid), fiyat.get(pid), durum.get(pid, {})
        if not u or not f or d.get("isAvailableAndBuyable") is False:
            continue   # bilgisi eksik ya da şu an satın alınamıyor
        adaylar = [x.get("amount") for x in (f.get("promoPrice"), f.get("price")) if x and x.get("amount")]
        if not adaylar:
            continue
        satici = (f.get("marketplaceSeller") or {}).get("name") if f.get("isProductOfTypeMarketplace") else None
        sonuc.append({"asin": "mm:" + pid, "url": urljoin("https://www.mediamarkt.com.tr", u.get("url", "")),
                      "baslik": u.get("title") or pid, "fiyat": float(min(adaylar)),
                      "not": f"satıcı: {satici}" if satici else ""})
    toplam = 1
    for k, v in ap.items():
        if k.startswith("ProductList:") and v.get("pageSize"):
            toplam = min(math.ceil((v.get("totalProducts") or 0) / v["pageSize"]), v.get("maxPage") or 1)
    return sonuc, max(toplam, 1)


def _ld_nesneleri(veri):
    """JSON-LD içindeki tüm nesneleri (liste ve @graph dahil) sırayla verir."""
    if isinstance(veri, list):
        for x in veri:
            yield from _ld_nesneleri(x)
    elif isinstance(veri, dict):
        yield veri
        for k in ("@graph", "mainEntity", "itemOffered"):
            if k in veri:
                yield from _ld_nesneleri(veri[k])


def _tur_mu(nesne, tur):
    t = nesne.get("@type")
    return tur in (t if isinstance(t, list) else [t])


def _ld_fiyat(deger):
    if isinstance(deger, (int, float)):
        return float(deger) if deger > 0 else None
    return fiyat_coz(str(deger)) if deger else None


def genel_coz(sayfa, secici=None):
    """Herhangi bir sitenin ürün sayfasından ad, fiyat ve stok bilgisini çıkarır.
    Sıra: öğretilmiş seçici → JSON-LD (schema.org Product) → mikroveri → meta etiketleri.
    Dönüş: {'baslik', 'fiyat' (stokta yoksa None), 'kaynak'}; fiyat bulunamazsa ValueError."""
    soup = BeautifulSoup(sayfa, "html.parser")
    baslik = None
    for sec, attr in (('meta[property="og:title"]', "content"), ("h1", None), ("title", None)):
        el = soup.select_one(sec)
        if el:
            baslik = (el.get(attr) if attr else el.get_text(" ", strip=True)) or None
            if baslik:
                break

    if secici:
        el = soup.select_one(secici)
        if el:
            f = fiyat_coz(el.get("content") or el.get_text(" ", strip=True))
            if f:
                return {"baslik": baslik or "?", "fiyat": f, "kaynak": "öğretilen konum"}

    for sc in soup.find_all("script", type=re.compile("ld\\+json", re.I)):
        try:
            veri = json.loads(sc.string or sc.get_text() or "null", strict=False)
        except ValueError:
            continue
        for n in _ld_nesneleri(veri):
            if not _tur_mu(n, "Product") and not _tur_mu(n, "ProductGroup"):
                continue
            teklifler = n.get("offers") or []
            teklifler = teklifler if isinstance(teklifler, list) else [teklifler]
            fiyatlar, stok_var, stok_bilgisi = [], False, False
            for o in teklifler:
                if not isinstance(o, dict):
                    continue
                f = _ld_fiyat(o.get("price")) or _ld_fiyat(o.get("lowPrice"))
                if not f and isinstance(o.get("priceSpecification"), dict):
                    f = _ld_fiyat(o["priceSpecification"].get("price"))
                durum = str(o.get("availability") or "")
                if durum:
                    stok_bilgisi = True
                yok = re.search(r"OutOfStock|SoldOut|Discontinued", durum, re.I)
                if f:
                    fiyatlar.append(f)
                    stok_var = stok_var or not yok
            if fiyatlar:
                ad = n.get("name") if isinstance(n.get("name"), str) else None
                return {"baslik": ad or baslik or "?",
                        "fiyat": min(fiyatlar) if (stok_var or not stok_bilgisi) else None,
                        "kaynak": "JSON-LD"}

    for sec, attr in (('[itemprop="price"]', "content"),
                      ('meta[property="product:price:amount"]', "content"),
                      ('meta[property="og:price:amount"]', "content")):
        for el in soup.select(sec):
            f = fiyat_coz(el.get(attr) or el.get_text(" ", strip=True))
            if f:
                stok = soup.select_one('[itemprop="availability"]')
                yok = stok and re.search(r"OutOfStock|SoldOut",
                                         stok.get("href") or stok.get("content") or "", re.I)
                return {"baslik": baslik or "?", "fiyat": None if yok else f, "kaynak": "meta"}
    raise ValueError("sayfada fiyat bilgisi bulunamadı")


def fiyat_konumu_bul(sayfa, fiyat):
    """Sayfada verilen fiyatı gösteren öğeyi bulup ona giden bir CSS seçici döndürür."""
    soup = BeautifulSoup(sayfa, "html.parser")
    for x in soup(["script", "style", "noscript"]):
        x.decompose()
    adaylar = []
    for sira, el in enumerate(soup.find_all(True)):
        metin = el.get_text(" ", strip=True)
        if not metin or len(metin) > 40:
            continue
        f = fiyat_coz(metin.split("+")[0])
        if not f or abs(f - fiyat) > 0.01:
            continue
        # aynı metni taşıyan en içteki öğeyi seç
        if any(abs((fiyat_coz(c.get_text(" ", strip=True)) or 0) - fiyat) <= 0.01
               for c in el.find_all(True)):
            continue
        isim = " ".join(el.get("class", [])) + " " + (el.get("id") or "")
        puan = 3 * bool(re.search(r"price|fiyat|amount|tutar", isim, re.I)) - sira / 10000
        for ata in el.parents:
            ai = " ".join(ata.get("class", []) if hasattr(ata, "get") else []) + " " + \
                (ata.get("id") or "" if hasattr(ata, "get") else "")
            if re.search(r"related|similar|benzer|carousel|slider|recommend|oneri|footer", ai, re.I):
                puan -= 5
                break
        adaylar.append((puan, el))
    for _, el in sorted(adaylar, key=lambda x: -x[0]):
        secici = _secici_yap(el)
        bulunan = soup.select_one(secici) if secici else None
        if bulunan is el:
            return secici
    return None


def _secici_yap(el):
    def parca(e):
        if e.get("id") and re.fullmatch(r"[A-Za-z][\w-]*", e["id"]):
            return f"#{e['id']}"
        siniflar = [c for c in e.get("class", []) if re.fullmatch(r"-?[A-Za-z_][\w-]*", c)]
        return e.name + "".join("." + c for c in siniflar[:3])
    parcalar, e = [], el
    while e is not None and getattr(e, "name", None) not in (None, "[document]", "html", "body"):
        parcalar.insert(0, parca(e))
        sec = " > ".join(parcalar)
        try:
            if parcalar[0].startswith("#") or len(e.find_parent("html").select(sec)) == 1:
                return sec
        except Exception:
            return None
        e = e.parent
    return " > ".join(parcalar) or None


def _sorgu_page_siz(sorgu):
    """Sorgu metninden yalnızca page parametresini atar; gerisine dokunmaz.
    Yeniden kodlamak '%20'yi '+' yapar ve MediaMarkt süzgeçleri bozulur."""
    return "&".join(x for x in sorgu.split("&") if x and x.split("=", 1)[0] != "page")


def sayfa_ekle(url, no):
    p = urlsplit(url)
    q = _sorgu_page_siz(p.query)
    return p._replace(query=(q + "&" if q else "") + f"page={no}").geturl()


def arama_bos_mu(sayfa):
    """Sayfa gerçekten 'sonuç yok' sayfası mı (bozuk/engelli sayfadan ayırmak için)."""
    soup = BeautifulSoup(sayfa, "html.parser")
    if soup.select_one('div[data-component-type="s-search-result"]'):
        return False
    metin = soup.get_text(" ", strip=True).lower()
    return ("sonuç bulunamadı" in metin or "eşleşen sonuç yok" in metin or "ürün bulunamadı" in metin
            or "hiçbir sonuç" in metin or "no results for" in metin)


def fiyat_bul(soup):
    """Sayfadaki asıl satış fiyatını (sepete ekle fiyatı) bulur."""
    for kapsam in ("#corePriceDisplay_desktop_feature_div", "#corePrice_desktop",
                   "#corePrice_feature_div", "#apex_desktop"):
        kutu = soup.select_one(kapsam)
        if not kutu:
            continue
        f = asil_fiyat(kutu)
        if f:
            return f
    for sec in ("#priceblock_dealprice", "#priceblock_ourprice", "#price_inside_buybox",
                "#newBuyBoxPrice", "#tp_price_block_total_price_ww .a-offscreen"):
        el = soup.select_one(sec)
        if el:
            f = fiyat_coz(el.get_text(strip=True))
            if f:
                return f
    for sec in ("input#priceValue", "input#attach-base-product-price",
                "input#twister-plus-price-data-price"):
        el = soup.select_one(sec)
        if el and el.get("value"):
            try:
                f = float(el["value"])
                if f > 0:
                    return f
            except ValueError:
                pass
    return None


def sayfa_coz(sayfa):
    """HTML -> {'baslik': str, 'fiyat': float|None}. Başlık yoksa ValueError."""
    soup = BeautifulSoup(sayfa, "html.parser")
    baslik = soup.select_one("#productTitle")
    if not baslik:
        raise ValueError("ürün sayfası tanınmadı (başlık bulunamadı)")
    fiyat = fiyat_bul(soup)
    stok_metni = " ".join(el.get_text(" ", strip=True).lower()
                          for el in soup.select("#availability, #outOfStock"))
    if soup.select_one("#outOfStock") or "mevcut değil" in stok_metni or "stokta yok" in stok_metni:
        fiyat = None
    return {"baslik": baslik.get_text(strip=True), "fiyat": fiyat}


# ---------------------------------------------------------------- ana sınıf
class Takip:
    def __init__(self):
        if not URUN_DOSYA.exists() and (KLASOR / "urunler.json").exists():
            shutil.copy(KLASOR / "urunler.json", URUN_DOSYA)   # ilk kurulum listesi
        self.ayar_yukle()
        self.durum = json_oku(DURUM_DOSYA, {})
        self.durum.setdefault("urunler", {})
        self.durum.setdefault("izleme", {})
        self.gecmis = json_oku(GECMIS_DOSYA, {})
        self.grup = None
        self.son_arama = 0
        self.arama_jitter = 1.0
        self.oturum = self.yeni_oturum()
        self.engel = False
        self.carpan = 1

    # -- dosyalar
    def ayar_yukle(self):
        self.ayar = {**VARSAYILAN, **json_oku(AYAR_DOSYA, {})}

    @property
    def chat_id(self):
        return str(self.ayar.get("telegram_chat_id") or self.durum.get("chat_id") or "")

    def urunler(self):
        return json_oku(URUN_DOSYA, [])

    def izlemeler(self):
        return json_oku(IZLEME_DOSYA, [])

    def kaydet(self):
        json_yaz(DURUM_DOSYA, self.durum)
        json_yaz(CEREZ_DOSYA, requests.utils.dict_from_cookiejar(self.oturum.cookies))

    def yeni_oturum(self, cerezli=True):
        o = requests.Session()
        if cerezli:
            o.cookies.update(json_oku(CEREZ_DOSYA, {}))
        o.headers.update({
            "User-Agent": self.ayar["user_agent"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.6,en;q=0.5",
            "Upgrade-Insecure-Requests": "1",
        })
        return o

    # -- telegram
    def tg(self, yontem, zaman_asimi=30, **veri):
        url = f"https://api.telegram.org/bot{self.ayar['telegram_token']}/{yontem}"
        r = requests.post(url, json=veri, timeout=zaman_asimi)
        cevap = r.json()
        if not cevap.get("ok"):
            raise RuntimeError(f"Telegram hatası: {cevap.get('description')}")
        return cevap["result"]

    def bildir(self, metin):
        for deneme in range(3):
            try:
                self.tg("sendMessage", chat_id=self.chat_id, text=metin,
                        parse_mode="HTML", disable_web_page_preview=True)
                return True
            except Exception as e:
                log.warning("Telegram gönderilemedi (%s), deneme %d", e, deneme + 1)
                time.sleep(5)
        return False

    # -- home assistant: rahatsız etme modunu aşan sesli (kritik) uyarı
    def alarm_cihazlari(self):
        if not HA_TOKEN:
            raise RuntimeError("sesli uyarı yalnızca Home Assistant uygulaması olarak çalışırken kullanılabilir")
        r = requests.get(f"{HA_API}/services", timeout=15,
                         headers={"Authorization": f"Bearer {HA_TOKEN}"})
        r.raise_for_status()
        cihazlar = sorted(ad for alan in r.json() if alan["domain"] == "notify"
                          for ad in alan["services"] if ad.startswith("mobile_app_"))
        secim = str(self.ayar.get("alarm_cihazi") or "").strip().lower()
        if secim:
            cihazlar = [c for c in cihazlar if secim in c]
        if not cihazlar:
            raise RuntimeError("Home Assistant'ta bildirim gönderilecek telefon bulunamadı")
        return cihazlar

    def kritik_uyari(self, baslik, metin, url=None):
        """Telefon(lar)a kritik uyarı yollar; gönderilen cihaz adlarını döndürür."""
        cihazlar = self.alarm_cihazlari()
        veri = {"push": {"sound": {"name": "default", "critical": 1, "volume": 1.0}}}
        if url:
            veri["url"] = url
        for c in cihazlar:
            r = requests.post(f"{HA_API}/services/notify/{c}", timeout=15,
                              headers={"Authorization": f"Bearer {HA_TOKEN}"},
                              json={"title": baslik, "message": metin, "data": veri})
            r.raise_for_status()
        return cihazlar

    # -- amazon
    def engeli_gec(self, sayfa, url):
        """Amazon'un 'Alışverişe devam et' ara sayfasını (resimli CAPTCHA içermeyen,
        yalnızca düğmeye basılması istenen sürüm) geçmeyi dener."""
        form = BeautifulSoup(sayfa, "html.parser").select_one('form[action*="validateCaptcha"]')
        if not form:
            return False
        girdiler = form.select("input[name]")
        if not girdiler or any(g.get("type", "text") != "hidden" for g in girdiler):
            return False   # elle çözülmesi gereken gerçek CAPTCHA
        try:
            time.sleep(random.uniform(2, 4))
            self.oturum.get(urljoin(url, form["action"]), timeout=25,
                            params={g["name"]: g.get("value", "") for g in girdiler},
                            headers={"Referer": url})
            time.sleep(random.uniform(2, 4))
            return True
        except Exception as e:
            log.warning("ara sayfa geçilemedi: %s", e)
            return False

    def getir(self, url, tekrar=True):
        r = self.oturum.get(url, timeout=25)
        sayfa = r.text
        if (r.status_code in (403, 429, 503) or "validateCaptcha" in sayfa
                or "challenge-platform" in sayfa or "cf-chl" in sayfa
                or "api-services-support@amazon.com" in sayfa):
            if tekrar and self.engeli_gec(sayfa, url):
                log.info("Amazon ara sayfası geçildi, yeniden deneniyor")
                return self.getir(url, tekrar=False)
            HATA_KLASOR.mkdir(parents=True, exist_ok=True)
            (HATA_KLASOR / "hata_captcha.html").write_text(
                f"<!-- HTTP {r.status_code} {url} -->\n{sayfa}", encoding="utf-8")
            raise Engellendi()
        if r.status_code == 404:
            raise ValueError("sayfa bulunamadı (404)")
        r.raise_for_status()
        return sayfa

    def urun_url(self, urun):
        return urun.get("url") or f"https://www.amazon.com.tr/dp/{urun['asin']}"

    def urun_oku(self, urun):
        if not urun.get("url"):
            return self.oku(urun["asin"])
        sayfa = self.getir(urun["url"])
        try:
            return genel_coz(sayfa, urun.get("secici"))
        except ValueError:
            HATA_KLASOR.mkdir(parents=True, exist_ok=True)
            host = urlsplit(urun["url"]).netloc.replace(":", "_")
            (HATA_KLASOR / f"hata_{host}.html").write_text(sayfa, encoding="utf-8")
            raise

    def oku(self, asin):
        sayfa = self.getir(f"https://www.amazon.com.tr/dp/{asin}")
        try:
            return sayfa_coz(sayfa)
        except ValueError:
            HATA_KLASOR.mkdir(parents=True, exist_ok=True)
            (HATA_KLASOR / f"hata_{asin}.html").write_text(sayfa, encoding="utf-8")
            raise

    def asin_bul(self, metin):
        u = re.search(r"https?://\S+", metin)
        if u and not re.search(r"amazon\.|amzn\.", urlsplit(u.group(0)).netloc, re.I):
            return None   # Amazon dışı link
        m = ASIN_RE.search(metin)
        if m:
            return m.group(1)
        if re.fullmatch(r"[A-Z0-9]{10}", metin.strip()):
            return metin.strip()
        u = re.search(r"https?://\S+", metin)   # amzn.eu gibi kısa linkler
        if u:
            r = self.oturum.get(u.group(0), timeout=25)
            m = ASIN_RE.search(r.url)
            if m:
                return m.group(1)
        return None

    def baglanti(self, asin):
        d = self.durum["urunler"].get(asin, {})
        url = d.get("url") or next((u["url"] for u in self.urunler()
                                    if u["asin"] == asin and u.get("url")), None) \
            or f"https://www.amazon.com.tr/dp/{asin}"
        ad = d.get("baslik") or (urlsplit(url).netloc if asin.startswith("web:") else asin)
        return f'<a href="{html.escape(url)}">{html.escape(kisalt(ad))}</a>'

    def hata(self, ad, etiket, d, neden):
        d["hata_sayisi"] = d.get("hata_sayisi", 0) + 1
        log.warning("%s okunamadı (%d. kez): %s", ad, d["hata_sayisi"], neden)
        if d["hata_sayisi"] >= self.ayar["hata_esigi"] and not d.get("hata_bildirildi"):
            if self.bildir(f"⚠️ {etiket}\n{d['hata_sayisi']} kezdir okunamıyor: "
                           f"{html.escape(neden)}\nDüzelince haber veririm."):
                d["hata_bildirildi"] = True

    def kontrol(self, urun):
        """Bir ürünü okur, gerekiyorsa bildirim yollar. Okunan fiyatı döndürür."""
        asin = urun["asin"]
        d = self.durum["urunler"].setdefault(asin, {})
        if urun.get("url"):
            d["url"] = urun["url"]
        try:
            s = self.urun_oku(urun)
        except Engellendi:
            if not urun.get("url"):
                self.engel = True
                self.oturum = self.yeni_oturum(cerezli=False)
            self.hata(asin, self.baglanti(asin), d, "site bot koruması (CAPTCHA / erişim engeli)")
            return None
        except Exception as e:
            self.hata(asin, self.baglanti(asin), d, str(e) or type(e).__name__)
            return None

        d["baslik"] = s["baslik"]
        if d.get("hata_bildirildi"):
            self.bildir(f"✅ {self.baglanti(asin)}\nTekrar okunabiliyor.")
        d.update(hata_sayisi=0, hata_bildirildi=False,
                 son_okuma=datetime.now().isoformat(timespec="seconds"))

        ilk = "stok" not in d
        eski, eski_stok, yeni = d.get("fiyat"), d.get("stok"), s["fiyat"]
        d["stok"] = yeni is not None
        if yeni is None:
            log.info("%s: stokta yok / satın alma fiyatı yok", asin)
            return None
        log.info("%s: %s", asin, tl(yeni))

        hedef = urun.get("hedef")
        ek = f"\n🎯 Hedefinizin ({tl(hedef)}) altında!" if hedef and yeni <= hedef else ""
        if not ilk:
            if not eski_stok:
                onceki = f" (son görülen: {tl(eski)})" if eski else ""
                self.bildir(f"📦 <b>Tekrar stokta</b>\n{self.baglanti(asin)}\n"
                            f"Fiyat: <b>{tl(yeni)}</b>{onceki}{ek}")
            elif eski and yeni < eski - max(self.ayar["min_dusus_tl"], 0.005):
                self.bildir(f"🔻 <b>Fiyat düştü</b>\n{self.baglanti(asin)}\n"
                            f"{tl(eski)} → <b>{tl(yeni)}</b>\n"
                            f"Fark: -{tl(eski - yeni)} (%{(eski - yeni) / eski * 100:.1f}){ek}")
            elif eski and yeni > eski and self.ayar["artis_bildir"]:
                self.bildir(f"🔺 Fiyat arttı\n{self.baglanti(asin)}\n{tl(eski)} → {tl(yeni)}")
        olagan = olagan_fiyat(d.setdefault("gunluk", {}), yeni, self.ayar["gecmis_gun"])
        alarm, oran = urun.get("alarm"), (olagan - yeni) / olagan * 100
        if alarm and oran >= alarm:
            if not d.get("alarm_fiyat") or yeni < d["alarm_fiyat"] - 0.005:
                d["alarm_fiyat"] = yeni
                try:
                    self.kritik_uyari(f"🚨 %{oran:.0f} indirim", f"{kisalt(s['baslik'], 60)}\n"
                                      f"{tl(olagan)} → {tl(yeni)}", self.urun_url(urun))
                    not_ = "Sesli uyarı gönderildi."
                except Exception as e:
                    log.warning("kritik uyarı gönderilemedi: %s", e)
                    not_ = f"Sesli uyarı GÖNDERİLEMEDİ: {html.escape(str(e))}"
                self.bildir(f"🚨 <b>Alarm: %{oran:.0f} indirim</b> (eşik %{alarm:g})\n{self.baglanti(asin)}\n"
                            f"Olağan fiyat {tl(olagan)} → <b>{tl(yeni)}</b>\n{not_}")
        else:
            d.pop("alarm_fiyat", None)
        d["fiyat"] = yeni
        d["en_dusuk"] = min(yeni, d.get("en_dusuk") or yeni)
        return yeni

    # -- arama izleme
    def arama_tara(self, iz):
        """İzlenen aramanın sonuç sayfalarını okur, ürün listesini döndürür."""
        return self._arama_tara(iz)

    def _sayfali_tara(self, iz, site):
        """Vatan ve MediaMarkt: ?page=N ile sayfa sayfa okur."""
        coz = vatan_coz if site == "vatan" else mm_coz
        sinir = int(iz.get("sayfa") or self.ayar[f"{site}_sayfa_siniri"])
        hepsi, toplam, no = {}, 1, 1
        while no <= min(toplam, sinir):
            sayfa = self.getir(iz["url"] if no == 1 else sayfa_ekle(iz["url"], no))
            try:
                urunler, toplam = coz(sayfa)
            except (ValueError, KeyError, TypeError):
                urunler = None
            bos = arama_bos_mu(sayfa) if site == "vatan" else urunler == []
            if no == 1 and not urunler and not (iz.get("yeni") and bos):
                HATA_KLASOR.mkdir(parents=True, exist_ok=True)
                (HATA_KLASOR / f"hata_{site}.html").write_text(sayfa, encoding="utf-8")
                raise ValueError("sayfada fiyatlı ürün bulunamadı")
            for u in urunler or []:
                hepsi.setdefault(u["asin"], u)
            if not urunler:
                break
            no += 1
            if no <= min(toplam, sinir):
                time.sleep(random.uniform(3, 6))
        return list(hepsi.values())

    def _arama_tara(self, iz):
        """İzlenen aramanın sonuç sayfalarını okur, ürün listesini döndürür."""
        site = site_bul(iz["url"])
        if site in ("vatan", "mediamarkt"):
            return self._sayfali_tara(iz, site)
        url, hepsi = iz["url"], {}
        for no in range(int(iz.get("sayfa") or self.ayar["arama_sayfa_siniri"])):
            sayfa = self.getir(url)
            urunler, url = arama_coz(sayfa)
            if no == 0 and not urunler and not (iz.get("yeni") and arama_bos_mu(sayfa)):
                HATA_KLASOR.mkdir(parents=True, exist_ok=True)
                (HATA_KLASOR / "hata_arama.html").write_text(sayfa, encoding="utf-8")
                raise ValueError("arama sayfasında fiyatlı ürün bulunamadı")
            for u in urunler:
                hepsi.setdefault(u["asin"], u)
            if not url:
                break
            time.sleep(random.uniform(4, 8))
        return list(hepsi.values())

    def arama_bildir(self, iz, baslik, urun_adi, detay, url):
        """İzleme bildirimi: Telegram mesajı, izlemede alarm açıksa sesli uyarı da.
        `detay` HTML'dir (kalın fiyat vb.)."""
        ek = ""
        if iz.get("alarm"):
            try:
                self.kritik_uyari(f"{baslik} · {iz['ad']}",
                                  f"{kisalt(urun_adi, 60)}\n{re.sub(r'<[^>]+>', '', detay)}", url)
            except Exception as e:
                log.warning("kritik uyarı gönderilemedi: %s", e)
                ek = f"\n⚠️ Sesli uyarı gönderilemedi: {html.escape(str(e))}"
        return self.bildir(f"<b>{html.escape(baslik)}</b> · {html.escape(iz['ad'])}\n"
                           f'<a href="{url}">{html.escape(kisalt(urun_adi))}</a>\n{detay}{ek}')

    def arama_degerlendir(self, iz, d, urunler):
        """Yeni çıkan ürünleri ve olağan fiyatına göre eşiği aşan düşüşleri bildirir."""
        simdi = datetime.now()
        sinir = (simdi - timedelta(days=int(self.ayar["gecmis_gun"]))).strftime("%Y-%m-%d")
        ilk = "gorulen" not in d
        gorulen = d.setdefault("gorulen", {})
        for u in urunler:
            url = u.get("url") or f"https://www.amazon.com.tr/dp/{u['asin']}"
            not_ = f" ({html.escape(u['not'], quote=False)})" if u.get("not") else ""
            g = self.gecmis.setdefault(u["asin"], {"gunluk": {}})
            g["baslik"], fiyat, gun = u["baslik"], u["fiyat"], g["gunluk"]
            olagan = olagan_fiyat(gun, fiyat, self.ayar["gecmis_gun"])
            oran = (olagan - fiyat) / olagan * 100
            g["son"] = fiyat
            son = gorulen.get(u["asin"])
            yeni_cikti = not ilk and (not son or simdi - datetime.fromisoformat(son) > timedelta(hours=6))
            gorulen[u["asin"]] = simdi.isoformat(timespec="seconds")
            if iz.get("yeni") and yeni_cikti:
                if self.arama_bildir(iz, "🆕 Yeni çıktı", u["baslik"], f"Fiyat: <b>{tl(fiyat)}</b>{not_}", url):
                    g["bildirilen"] = fiyat
                continue
            if iz.get("esik") and oran >= iz["esik"]:
                if not g.get("bildirilen") or fiyat < g["bildirilen"] - 0.005:
                    if self.arama_bildir(iz, f"🔥 %{oran:.0f} indirim", u["baslik"],
                                         f"Olağan fiyat {tl(olagan)} → <b>{tl(fiyat)}</b>{not_}", url):
                        g["bildirilen"] = fiyat
            elif not iz.get("yeni"):
                g.pop("bildirilen", None)
        eski = (simdi - timedelta(days=int(self.ayar["gecmis_gun"]))).isoformat()
        for asin in [a for a, z in gorulen.items() if z < eski]:
            del gorulen[asin]
        for asin in [a for a, g in self.gecmis.items()   # eski kayıtları buda
                     if not g["gunluk"] or max(g["gunluk"]) < sinir]:
            del self.gecmis[asin]
        for g in self.gecmis.values():
            for k in [k for k in g["gunluk"] if k < sinir]:
                del g["gunluk"][k]
        json_yaz(GECMIS_DOSYA, self.gecmis)

    def izleme_calistir(self, iz):
        """Bir izlemeyi tarar ve değerlendirir. Bulunan ürün sayısını ya da None döndürür."""
        d = self.durum["izleme"].setdefault(iz["url"], {})
        etiket = f'<a href="{html.escape(iz["url"])}">{html.escape(iz["ad"])} araması</a>'
        try:
            urunler = self.arama_tara(iz)
        except Engellendi:
            d["engel"] = True
            if site_bul(iz["url"]) == "amazon":
                self.engel = True
                self.oturum = self.yeni_oturum(cerezli=False)
            self.hata(iz["ad"], etiket, d, "site bot koruması (CAPTCHA / erişim engeli)")
            return None
        except Exception as e:
            self.hata(iz["ad"], etiket, d, str(e) or type(e).__name__)
            return None
        if d.get("hata_bildirildi"):
            self.bildir(f"✅ {etiket}\nTekrar okunabiliyor.")
        d.update(hata_sayisi=0, hata_bildirildi=False, adet=len(urunler),
                 en_ucuz=min((u["fiyat"] for u in urunler), default=0),
                 en_pahali=max((u["fiyat"] for u in urunler), default=0))
        log.info("arama '%s': %d ürün", iz["ad"], len(urunler))
        self.arama_degerlendir(iz, d, urunler)
        return len(urunler)

    def aramalari_tara(self):
        """Vakti gelen izlemeleri tarar. Her izlemenin kendi aralığı ve engel
        durumunda kendi geri çekilme çarpanı vardır."""
        for iz in self.izlemeler():
            d = self.durum["izleme"].setdefault(iz["url"], {})
            if time.time() < d.get("sonraki", 0):
                continue
            d["engel"] = False
            self.izleme_calistir(iz)
            d["carpan"] = min(d.get("carpan", 1) * 2, 8) if d.get("engel") else 1
            aralik = iz.get("aralik") or self.ayar["arama_araligi_sn"]
            d["sonraki"] = time.time() + aralik * d["carpan"] * random.uniform(0.85, 1.15)
            self.kaydet()
            self.bekle(random.uniform(3, 6))

    def izleme_listesi(self):
        izler = self.izlemeler()
        if not izler:
            return "İzlenen arama yok. Eklemek için: /izle &lt;arama linki&gt; [yüzde] [yeni] [alarm]"
        satirlar = []
        for i, iz in enumerate(izler, 1):
            d = self.durum["izleme"].get(iz["url"], {})
            durum = ("⚠️ okunamıyor" if d.get("hata_sayisi")
                     else f"{d['adet']} ürün" if "adet" in d else "henüz taranmadı")
            kurallar = []
            if iz.get("yeni"):
                kurallar.append("yeni çıkanı bildir")
            if iz.get("esik"):
                kurallar.append(f"%{iz['esik']:g}+ düşüşte bildir")
            if iz.get("alarm"):
                kurallar.append("🚨 sesli")
            kurallar.append(f"{(iz.get('aralik') or self.ayar['arama_araligi_sn']) // 60} dk'da bir")
            if iz.get("sayfa"):
                kurallar.append(f"{iz['sayfa']} sayfa")
            satirlar.append(f'{i}. <a href="{html.escape(iz["url"])}">{html.escape(iz["ad"])}</a>'
                            f" · {', '.join(kurallar)} · {durum}")
        return "\n".join(satirlar)

    # -- telegram komutları
    def liste_metni(self):
        urunler = self.urunler()
        if not urunler:
            return "Takip edilen ürün yok. Eklemek için: /ekle &lt;link&gt;"
        satirlar = []
        for i, u in enumerate(urunler, 1):
            d = self.durum["urunler"].get(u["asin"], {})
            if d.get("hata_sayisi"):
                fiyat = "⚠️ okunamıyor"
            elif d.get("stok"):
                fiyat = f"<b>{tl(d['fiyat'])}</b>"
            elif "stok" in d:
                fiyat = "stokta yok"
            else:
                fiyat = "henüz okunmadı"
            ek = f" · en düşük {tl(d['en_dusuk'])}" if d.get("en_dusuk") else ""
            ek += f" · hedef {tl(u['hedef'])}" if u.get("hedef") else ""
            ek += f" · 🚨 alarm %{u['alarm']:g}" if u.get("alarm") else ""
            satirlar.append(f"{i}. {self.baglanti(u['asin'])}\n    {fiyat}{ek}")
        return "\n".join(satirlar)

    def komut(self, metin):
        parca = metin.split()
        k = parca[0].split("@")[0].lower()
        urunler = self.urunler()
        if k in ("/liste", "/durum"):
            return self.liste_metni()
        if k == "/alarmtest":
            try:
                cihazlar = self.kritik_uyari("🚨 Deneme alarmı", "Fiyat takibi: sesli uyarı çalışıyor.")
            except Exception as e:
                return f"Sesli uyarı gönderilemedi: {html.escape(str(e))}"
            return "Sesli uyarı gönderildi: " + ", ".join(c.removeprefix("mobile_app_") for c in cihazlar)
        if k == "/alarm" and len(parca) >= 2 and parca[1].isdigit():
            no = int(parca[1])
            if not 1 <= no <= len(urunler):
                return "Bu numarada ürün yok. Numaralar için /liste"
            yuzde = fiyat_coz(parca[2].strip("%")) if len(parca) > 2 else None
            if yuzde and yuzde >= 100:
                return "Yüzde 1 ile 99 arasında olmalı. Örnek: /alarm 2 20"
            urunler[no - 1]["alarm"] = yuzde
            json_yaz(URUN_DOSYA, urunler)
            self.durum["urunler"].get(urunler[no - 1]["asin"], {}).pop("alarm_fiyat", None)
            ad = self.baglanti(urunler[no - 1]["asin"])
            return (f"🚨 Alarm kuruldu: {ad}\nOlağan fiyatına göre %{yuzde:g} ve üzeri düşerse "
                    "telefonunuz rahatsız etme modunda bile sesli uyarı verir." if yuzde
                    else f"Alarm kaldırıldı: {ad}")
        if k in ("/kod", "/dinleme", "/gruplar", "/grupekle", "/grupsil", "/kelime", "/kelimesil"):
            if not self.grup:
                return ("Grup dinleme kapalı. Açmak için Yapılandırma sekmesinde "
                        "<code>telegram_api_id</code>, <code>telegram_api_hash</code> ve "
                        "<code>telegram_telefon</code> alanlarını doldurup uygulamayı yeniden başlatın.")
            cevap = self.grup.komut(k, parca)
            if cevap:
                return cevap
        if k == "/izlemeler":
            return self.izleme_listesi()
        if k == "/izle" and len(parca) >= 2:
            url = arama_url_temizle(parca[1])
            if not url:
                return ("Bu link desteklenmiyor. Amazon.com.tr arama linki, Vatan Bilgisayar ya da "
                        "MediaMarkt kategori/arama linki gönderin (süzgeçleri seçtikten sonra "
                        "adres çubuğundaki link).")
            izler = self.izlemeler()
            if any(i["url"] == url for i in izler):
                return "Bu arama zaten izleniyor."
            esik, yeni, alarm, ad, aralik, sayfa_sayisi = None, False, False, [], None, None
            for p in parca[2:]:
                m = re.fullmatch(r"(\d+)\s*(dk|dakika|sn|saniye)", p.lower())
                ms = re.fullmatch(r"(\d+)\s*sayfa", p.lower())
                if ms:
                    sayfa_sayisi = int(ms.group(1))
                    if not 1 <= sayfa_sayisi <= 30:
                        return "Sayfa sayısı 1 ile 30 arasında olmalı. Örnek: /izle &lt;link&gt; 20sayfa"
                elif m:
                    aralik = int(m.group(1)) * (60 if m.group(2).startswith("d") else 1)
                    if aralik < 60:
                        return "Tarama aralığı en az 1 dakika olabilir. Örnek: /izle &lt;link&gt; 5dk"
                elif p.lower() == "yeni":
                    yeni = True
                elif p.lower() == "alarm":
                    alarm = True
                elif re.fullmatch(r"%?\d+([.,]\d+)?%?", p):
                    esik = fiyat_coz(p.strip("%"))
                else:
                    ad.append(p)
            if esik is None and not yeni:
                esik = 50
            if esik is not None and not 1 <= esik < 100:
                return "Yüzde 1 ile 99 arasında olmalı. Örnek: /izle &lt;link&gt; 50"
            iz = {"url": url, "ad": " ".join(ad) or arama_adi(url), "esik": esik,
                  "yeni": yeni, "alarm": alarm}
            if aralik:
                iz["aralik"] = aralik
            if sayfa_sayisi:
                iz["sayfa"] = sayfa_sayisi
            adet = self.izleme_calistir(iz)
            if adet is None:
                self.durum["izleme"].pop(url, None)
                return "Arama sayfası şu an okunamadı, eklenmedi. Birkaç dakika sonra tekrar deneyin."
            json_yaz(IZLEME_DOSYA, izler + [iz])
            self.kaydet()
            d = self.durum["izleme"][url]
            bulunan = (f"{adet} ürün bulundu ({tl(d['en_ucuz'])} – {tl(d['en_pahali'])}), kaydedildi."
                       if adet else "Şu an listede ürün yok.")
            kurallar = []
            if yeni:
                kurallar.append("listeye yeni bir ürün girince")
            if esik:
                kurallar.append(f"bir ürün olağan fiyatına göre %{esik:g} ve üzeri düşünce")
            sure = iz.get("aralik") or self.ayar["arama_araligi_sn"]
            bulunan += f" Yaklaşık {sure // 60} dakikada bir taranacak."
            return (f"👀 İzlemeye alındı: <b>{html.escape(iz['ad'])}</b>\n{bulunan}\n"
                    f"{' ya da '.join(kurallar).capitalize()} haber veririm"
                    + (" (🚨 sesli uyarıyla)." if alarm else "."))
        if k == "/izlesil" and len(parca) >= 2 and parca[1].isdigit():
            izler = self.izlemeler()
            no = int(parca[1])
            if not 1 <= no <= len(izler):
                return "Bu numarada izleme yok. Numaralar için /izlemeler"
            iz = izler.pop(no - 1)
            json_yaz(IZLEME_DOSYA, izler)
            self.durum["izleme"].pop(iz["url"], None)
            self.kaydet()
            return f"🗑 İzleme silindi: {html.escape(iz['ad'])}"
        if k == "/ekle" and len(parca) >= 2:
            hedef = fiyat_coz(parca[2]) if len(parca) > 2 else None
            asin = self.asin_bul(parca[1])
            if asin:
                urun = {"asin": asin, "hedef": hedef}
            elif re.match(r"https?://[^/\s]+\.[^/\s]+", parca[1]):
                url = parca[1].split("#")[0]
                asin = "web:" + hashlib.sha1(url.encode()).hexdigest()[:10]
                urun = {"asin": asin, "url": url, "hedef": hedef}
            else:
                return "Bu linkten ürün çıkaramadım. Ürün sayfasının tam linkini (https://…) gönderin."
            if any(u["asin"] == asin for u in urunler):
                return "Bu ürün zaten listede."
            json_yaz(URUN_DOSYA, urunler + [urun])
            fiyat = self.kontrol(urun)
            self.kaydet()
            d = self.durum["urunler"].get(asin, {})
            if fiyat:
                durum = f"Şu anki fiyat: <b>{tl(fiyat)}</b>"
            elif urun.get("url") and d.get("hata_sayisi"):
                no = len(urunler) + 1
                durum = ("⚠️ Bu sayfada fiyatı kendiliğimden bulamadım. Sayfada gördüğünüz fiyatı "
                         f"yazarsanız yerini öğrenirim: <code>/fiyat {no} 2999,00</code>")
            else:
                durum = "Şu an fiyat okunamadı / stokta yok."
            return f"➕ Eklendi: {self.baglanti(asin)}\n{durum}"
        if k == "/fiyat" and len(parca) >= 3 and parca[1].isdigit():
            no = int(parca[1])
            if not 1 <= no <= len(urunler):
                return "Bu numarada ürün yok. Numaralar için /liste"
            urun = urunler[no - 1]
            if not urun.get("url"):
                return "Amazon ürünlerinde buna gerek yok; fiyat kendiliğinden okunuyor."
            fiyat = fiyat_coz(" ".join(parca[2:]))
            if not fiyat:
                return "Fiyatı sayfada gördüğünüz gibi yazın. Örnek: <code>/fiyat 4 2.999,00</code>"
            try:
                sayfa = self.getir(urun["url"])
            except Engellendi:
                return "Site şu an erişimi engelliyor; biraz sonra tekrar deneyin."
            secici = fiyat_konumu_bul(sayfa, fiyat)
            if not secici:
                return (f"Sayfada {tl(fiyat)} yazan bir yer bulamadım. Fiyat sayfa açıldıktan sonra "
                        "tarayıcıda çalışan kodla yükleniyor olabilir; bu durumda bu siteyi izleyemem. "
                        "Fiyatı doğru yazdığınızdan da emin olun.")
            urun["secici"] = secici
            json_yaz(URUN_DOSYA, urunler)
            d = self.durum["urunler"].setdefault(urun["asin"], {})
            d.update(hata_sayisi=0, hata_bildirildi=False)
            okunan = self.kontrol(urun)
            self.kaydet()
            return (f"✅ Fiyatın yerini öğrendim: {self.baglanti(urun['asin'])}\n"
                    f"Okunan fiyat: <b>{tl(okunan) if okunan else '?'}</b>")
        if k in ("/sil", "/hedef") and len(parca) >= 2 and parca[1].isdigit():
            no = int(parca[1])
            if not 1 <= no <= len(urunler):
                return "Bu numarada ürün yok. Numaralar için /liste"
            u = urunler[no - 1]
            if k == "/sil":
                urunler.pop(no - 1)
                json_yaz(URUN_DOSYA, urunler)
                ad = self.baglanti(u["asin"])
                self.durum["urunler"].pop(u["asin"], None)
                self.kaydet()
                return f"🗑 Silindi: {ad}"
            u["hedef"] = fiyat_coz(parca[2]) if len(parca) > 2 else None
            json_yaz(URUN_DOSYA, urunler)
            return (f"🎯 Hedef {tl(u['hedef'])} olarak ayarlandı." if u["hedef"]
                    else "Hedef kaldırıldı.")
        return ("<b>Komutlar</b>\n"
                "/liste – ürünler ve güncel fiyatlar\n"
                "/ekle &lt;link&gt; [hedef fiyat] – ürün ekle (Amazon ya da herhangi bir sitenin ürün sayfası)\n"
                "/fiyat &lt;no&gt; &lt;fiyat&gt; – fiyatı bulunamayan sayfada fiyatın yerini öğret\n"
                "/sil &lt;no&gt; – ürünü çıkar\n"
                "/hedef &lt;no&gt; [fiyat] – hedef fiyat koy / kaldır\n"
                "/alarm &lt;no&gt; [yüzde] – sesli alarm kur / kaldır\n"
                "/alarmtest – sesli uyarıyı dene\n\n"
                "<b>Arama izleme</b> (indirim avı)\n"
                "/izle &lt;link&gt; [yüzde] [yeni] [alarm] [5dk] [20sayfa] – Amazon, Vatan ya da MediaMarkt listesi izle\n"
                "   yüzde: olağan fiyatına göre bu kadar düşeni bildir (varsayılan %50)\n"
                "   yeni: listeye yeni giren ürünü bildir · alarm: sesli uyarı · 5dk: tarama aralığı · "
                "20sayfa: okunacak sayfa sayısı\n"
                "/izlemeler – izlenen aramalar\n"
                "/izlesil &lt;no&gt; – izlemeyi kaldır\n\n" + GRUP_YARDIM)

    def bekle(self, sure):
        """`sure` saniye bekler; beklerken Telegram komutlarını dinler."""
        bitis = time.time() + sure
        while (kalan := bitis - time.time()) > 0:
            try:
                t = int(min(kalan, 25))
                gunceller = self.tg("getUpdates", zaman_asimi=t + 10, timeout=t,
                                    offset=self.durum.get("tg_offset"),
                                    allowed_updates=["message"])
            except Exception as e:
                log.debug("getUpdates: %s", e)
                time.sleep(min(kalan, 10))
                continue
            for g in gunceller:
                self.durum["tg_offset"] = g["update_id"] + 1
                m = g.get("message") or {}
                if str(m.get("chat", {}).get("id")) != self.chat_id:
                    continue   # yalnızca sahibinden komut kabul et
                if m.get("text"):
                    try:
                        cevap = self.komut(m["text"])
                    except Exception as e:
                        log.exception("komut hatası")
                        cevap = f"Komut işlenemedi: {html.escape(str(e))}"
                    self.bildir(cevap)
            if gunceller:
                self.kaydet()

    # -- döngü
    def gunluk_ozet(self):
        saat = str(self.ayar.get("gunluk_ozet") or "")
        if not re.fullmatch(r"\d\d:\d\d", saat):
            return   # kapalı
        simdi = datetime.now()
        bugun = simdi.strftime("%Y-%m-%d")
        if simdi.strftime("%H:%M") >= saat and self.durum.get("son_ozet") != bugun:
            if self.durum.get("son_ozet"):   # ilk gün başlangıç mesajı yeterli
                self.bildir("🗓 <b>Günlük özet</b> (sistem çalışıyor)\n" + self.liste_metni())
            self.durum["son_ozet"] = bugun
            self.kaydet()

    def calis(self):
        while not self.chat_id:   # ilk kurulum: sahibini bota yazdığı mesajdan tanı
            if not chat_id_bul(self):
                log.info("Telegram'da botunuza /start yazın; mesajınız bekleniyor...")
                time.sleep(5)
        if self.ayar.get("telegram_api_id") and self.ayar.get("telegram_api_hash"):
            self.grup = GrupDinleyici(self, GRUP_DOSYA, OTURUM_DOSYA, fiyat_coz)
            self.grup.baslat()
        ilk_tur, sonraki_tur = True, 0
        while True:
            self.ayar_yukle()
            if time.time() >= sonraki_tur:
                self.engel = False
                for urun in self.urunler():
                    self.kontrol(urun)
                    self.kaydet()
                    self.bekle(random.uniform(4, 10))
                # engellendiysek aralığı katlayarak aç (en çok 8 kat), düzelince normale dön
                self.carpan = min(self.carpan * 2, 8) if self.engel else 1
                sonraki_tur = time.time() + (self.ayar["kontrol_araligi_sn"] * self.carpan
                                             * random.uniform(0.8, 1.2))
                if ilk_tur:
                    ilk_tur = False
                    self.aramalari_tara()
                    self.bildir(f"✅ <b>Fiyat takibi başladı</b> – yaklaşık "
                                f"{self.ayar['kontrol_araligi_sn'] // 60 or 1} dakikada bir kontrol. "
                                f"Komutlar için /yardim\n\n{self.liste_metni()}")
            self.aramalari_tara()
            self.gunluk_ozet()
            self.bekle(5)

def chat_id_bul(t):
    """Bota yazılan son mesajdan chat_id'yi bulup kaydeder. Bulamazsa False."""
    try:
        gunceller = t.tg("getUpdates", timeout=0)
    except Exception as e:
        log.warning("Telegram'a ulaşılamadı: %s", e)
        return False
    idler = [g["message"]["chat"]["id"] for g in gunceller if "message" in g]
    if not idler:
        return False
    t.durum["chat_id"] = str(idler[-1])
    t.kaydet()
    log.info("chat_id bulundu ve kaydedildi: %s", idler[-1])
    return True


def test(t):
    satirlar = []
    for u in t.urunler():
        try:
            s = t.oku(u["asin"])
            sonuc = tl(s["fiyat"]) if s["fiyat"] else "stokta yok / fiyat yok"
            satir = f"{kisalt(s['baslik'], 50)}: {sonuc}"
        except Engellendi:
            satir = f"{u['asin']}: HATA - Amazon CAPTCHA gösterdi"
        except Exception as e:
            satir = f"{u['asin']}: HATA - {e}"
        print(satir)
        satirlar.append(html.escape(satir))
        time.sleep(random.uniform(3, 6))
    ok = t.bildir("🧪 <b>Deneme</b>\n" + "\n".join(satirlar))
    print("Telegram mesajı gönderildi." if ok else "Telegram mesajı GÖNDERİLEMEDİ.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--test", action="store_true", help="tek seferlik deneme")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        datefmt="%d.%m %H:%M:%S")
    t = Takip()
    if not t.ayar["telegram_token"]:
        sys.exit("Telegram token girilmemiş: uygulamanın Yapılandırma sekmesine "
                 "(ya da ayarlar.json dosyasına) telegram_token yazıp yeniden başlatın.")
    if args.test:
        if not t.chat_id and not chat_id_bul(t):
            sys.exit("chat_id bulunamadı: Telegram'da botunuza /start yazıp tekrar deneyin.")
        test(t)
    else:
        t.calis()


if __name__ == "__main__":
    main()
