"""Üye olunan Telegram gruplarını kullanıcının kendi hesabıyla dinler.

Seçilen gruplarda, tanımlanan kelimelerin hepsini içeren bir mesaj gelince
telefona sesli (kritik) uyarı ve bota bildirim gönderir. Hiçbir gruba yazmaz.
"""
import asyncio
import hashlib
import html
import json
import logging
import queue
import re
import threading
import time
from pathlib import Path

log = logging.getLogger("grup")

FIYAT_RE = re.compile(r"(?:₺\s*([\d.,]+))|(?:([\d][\d.,]*)\s*(?:tl|₺|try)\b)", re.I)
URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")


def normalle(metin):
    """Büyük/küçük harf ve Türkçe i/ı/İ/I farkını yok sayar."""
    m = (metin or "").replace("İ", "i").replace("I", "i").lower().replace("ı", "i")
    return re.sub(r"\s+", " ", m)


def kelime_deseni(kelime):
    """Kelimenin bir kelime başında geçmesini arayan desen. Harften rakama ya da
    rakamdan harfe geçiş de kelime başı sayılır: 'iphone' ve '16', 'iphone16' içinde
    bulunur; 'ram' ise 'program' içinde bulunmaz."""
    k = normalle(kelime)
    if not k:
        return None
    if k[0].isdigit():
        once = r"(?<!\d)"
    elif re.match(r"[^\W\d_]", k[0]):
        once = r"(?<![^\W\d_])"     # önünde harf olmasın
    else:
        once = ""                     # '+', '#' gibi işaretle başlıyorsa sınır aranmaz
    return re.compile(once + re.escape(k))


def kelime_gecer(kelime, normal_metin):
    d = kelime_deseni(kelime)
    return bool(d and d.search(normal_metin))


def kural_gruplari(metin):
    """'/kelime' argümanlarını virgüllerden kurallara böler. Rakamlar arasındaki virgül
    (ör. '<1.299,90') bölmez. Her grup: (kelimeler, en_cok metni | None)."""
    gruplar = []
    for parca in re.split(r"(?<!\d),|,(?!\d)", metin):
        kelimeler, en_cok = [], None
        for p in parca.split():
            if p.startswith("<"):
                en_cok = p[1:]
            else:
                kelimeler.append(p)
        if kelimeler or en_cok:
            gruplar.append((kelimeler, en_cok))
    return gruplar


def json_oku(dosya, varsayilan):
    try:
        return json.loads(Path(dosya).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return varsayilan


def json_yaz(dosya, veri):
    dosya = Path(dosya)
    gecici = dosya.with_suffix(".tmp")
    gecici.write_text(json.dumps(veri, ensure_ascii=False, indent=2), encoding="utf-8")
    gecici.replace(dosya)


class GrupDinleyici:
    def __init__(self, takip, ayar_dosya, oturum_dosya, fiyat_coz):
        self.t = takip
        self.ayar_dosya = Path(ayar_dosya)
        self.oturum_dosya = Path(oturum_dosya)
        self.fiyat_coz = fiyat_coz
        self.ayarlar = json_oku(self.ayar_dosya, {"gruplar": [], "kurallar": []})
        self.kod_kuyrugu = queue.Queue()
        self.loop = None
        self.client = None
        self.durum = "başlamadı"
        self.son_liste = []          # /gruplar komutunun son listesi
        self.son_alarmlar = {}       # aynı mesajın farklı gruplardan tekrarını engeller

    # ------------------------------------------------------------ ayarlar
    def kaydet(self):
        json_yaz(self.ayar_dosya, self.ayarlar)

    def eslesen_kural(self, metin):
        n = normalle(metin)
        fiyatlar = []
        for m in FIYAT_RE.finditer(metin or ""):
            f = self.fiyat_coz(m.group(1) or m.group(2))
            if f and f >= 10:
                fiyatlar.append(f)
        for kural in self.ayarlar["kurallar"]:
            if not all(kelime_gecer(k, n) for k in kural["kelimeler"]):
                continue
            if kural.get("en_cok") and fiyatlar and min(fiyatlar) > kural["en_cok"]:
                continue
            return kural
        return None

    @staticmethod
    def kural_metni(kural):
        s = " + ".join(kural["kelimeler"])
        if kural.get("en_cok"):
            f = kural["en_cok"]
            ham = f"{f:,.0f}" if float(f).is_integer() else f"{f:,.2f}"
            s += f" (en çok {ham.replace(',', '#').replace('.', ',').replace('#', '.')} TL)"
        return s

    # ------------------------------------------------------------ çalışma
    def baslat(self):
        threading.Thread(target=self._calis, daemon=True, name="grup").start()

    def _calis(self):
        while True:
            try:
                if asyncio.run(self._ana()) == "dur":
                    return
            except Exception as e:
                log.exception("grup dinleme hatası")
                self.durum = f"hata: {e}"
            self.loop = self.client = None
            time.sleep(60)   # bağlantı koptuysa bir dakika sonra yeniden bağlan

    async def _ana(self):
        from telethon import TelegramClient, errors, events
        from telethon.sessions import StringSession

        a = self.t.ayar
        oturum = self.oturum_dosya.read_text().strip() if self.oturum_dosya.exists() else ""
        client = TelegramClient(StringSession(oturum), int(a["telegram_api_id"]),
                                str(a["telegram_api_hash"]))
        await client.connect()
        if not await client.is_user_authorized():
            if await self._giris(client, errors) == "dur":
                await client.disconnect()
                return "dur"
            self.oturum_dosya.write_text(client.session.save())
            self.oturum_dosya.chmod(0o600)
        self.loop, self.client = asyncio.get_running_loop(), client
        client.add_event_handler(self._mesaj, events.NewMessage(incoming=True))
        client.add_event_handler(self._mesaj, events.MessageEdited(incoming=True))
        ilk = self.durum == "başlamadı" or self.durum.startswith("giriş")
        self.durum = "çalışıyor"
        log.info("grup dinleme çalışıyor")
        if ilk:
            await asyncio.to_thread(self.t.bildir, "👂 <b>Grup dinleme açık.</b>\n" + self.ozet())
        await client.run_until_disconnected()

    async def _giris(self, client, errors):
        tel = str(self.t.ayar.get("telegram_telefon") or "").replace(" ", "")
        if not tel:
            self.durum = "telefon numarası girilmemiş"
            await asyncio.to_thread(self.t.bildir, "Grup dinleme için Yapılandırma sekmesindeki "
                                    "<code>telegram_telefon</code> alanına numaranızı (+90...) yazıp "
                                    "uygulamayı yeniden başlatın.")
            return "dur"
        self.durum = "giriş kodu bekleniyor"
        await client.send_code_request(tel)
        bildir = lambda m: asyncio.to_thread(self.t.bildir, m)
        await bildir("🔐 <b>Grup dinleme için Telegram hesabınıza giriş gerekiyor.</b>\n"
                     "Telegram'ın gönderdiği giriş kodunu, rakamların arasına tire koyarak yazın:\n"
                     "<code>/kod 1-2-3-4-5</code>\n"
                     "Kodu tiresiz yazarsanız Telegram güvenlik gereği kodu geçersiz sayar.")
        while True:
            kod = await asyncio.to_thread(self.kod_kuyrugu.get)
            try:
                await client.sign_in(tel, kod)
                break
            except errors.SessionPasswordNeededError:
                sifre = self.t.ayar.get("telegram_2fa_sifre")
                if not sifre:
                    self.durum = "iki adımlı doğrulama şifresi girilmemiş"
                    await bildir("Hesabınızda iki adımlı doğrulama açık. Yapılandırma sekmesindeki "
                                 "<code>telegram_2fa_sifre</code> alanına şifrenizi yazıp uygulamayı "
                                 "yeniden başlatın.")
                    return "dur"
                try:
                    await client.sign_in(password=sifre)
                    break
                except errors.PasswordHashInvalidError:
                    self.durum = "iki adımlı doğrulama şifresi hatalı"
                    await bildir("İki adımlı doğrulama şifresi hatalı. Yapılandırma'da düzeltip "
                                 "uygulamayı yeniden başlatın.")
                    return "dur"
            except errors.PhoneCodeInvalidError:
                await bildir("Kod hatalı. Tekrar yazın: <code>/kod 1-2-3-4-5</code>")
            except errors.PhoneCodeExpiredError:
                await client.send_code_request(tel)
                await bildir("Kodun süresi dolmuş, yeni kod gönderildi. Rakamların arasına tire "
                             "koyarak yazın: <code>/kod 1-2-3-4-5</code>")
        self.durum = "giriş yapıldı"
        return None

    def calistir(self, coro, zaman=60):
        if not self.loop or self.durum != "çalışıyor":
            coro.close()
            raise RuntimeError(f"grup dinleme hazır değil ({self.durum})")
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(zaman)

    # ------------------------------------------------------------ mesajlar
    async def _mesaj(self, olay):
        if olay.chat_id not in {g["id"] for g in self.ayarlar["gruplar"]}:
            return
        metin = olay.raw_text or ""
        kural = self.eslesen_kural(metin)
        if not kural:
            return
        linkler = URL_RE.findall(metin)
        for ent in getattr(olay.message, "entities", None) or []:
            if getattr(ent, "url", None):
                linkler.append(ent.url)
        urun_link = next((l for l in linkler if re.search(r"amazon\.|amzn\.", l)), None) or \
            (linkler[0] if linkler else None)
        sohbet = await olay.get_chat()
        kullanici = getattr(sohbet, "username", None)
        if kullanici:
            mesaj_link = f"https://t.me/{kullanici}/{olay.id}"
        else:
            mesaj_link = f"https://t.me/c/{str(olay.chat_id).removeprefix('-100')}/{olay.id}"
        grup_adi = getattr(sohbet, "title", None) or str(olay.chat_id)
        await asyncio.to_thread(self.alarm, grup_adi, metin, kural, urun_link, mesaj_link)

    def alarm(self, grup_adi, metin, kural, urun_link, mesaj_link):
        anahtar = hashlib.sha1(normalle(urun_link or metin[:300]).encode()).hexdigest()
        simdi = time.time()
        self.son_alarmlar = {k: v for k, v in self.son_alarmlar.items() if simdi - v < 600}
        if anahtar in self.son_alarmlar:
            return False   # aynı fırsat başka gruptan / düzenlemeyle tekrar geldi
        self.son_alarmlar[anahtar] = simdi
        log.info("grup alarmı: %s / %s", grup_adi, self.kural_metni(kural))
        try:
            self.t.kritik_uyari(f"🚨 {' '.join(kural['kelimeler'])}",
                                f"{grup_adi}: {metin[:160]}", urun_link or mesaj_link)
            not_ = ""
        except Exception as e:
            log.warning("kritik uyarı gönderilemedi: %s", e)
            not_ = f"\n⚠️ Sesli uyarı gönderilemedi: {html.escape(str(e))}"
        linkler = []
        if urun_link:
            linkler.append(f'<a href="{html.escape(urun_link)}">Ürüne git</a>')
        linkler.append(f'<a href="{html.escape(mesaj_link)}">Mesaja git</a>')
        self.t.bildir(f"🚨 <b>Grup alarmı</b> · {html.escape(grup_adi)}\n"
                      f"Kural: {html.escape(self.kural_metni(kural))}\n\n"
                      f"{html.escape(metin[:700])}\n\n" + " · ".join(linkler) + not_)
        return True

    # ------------------------------------------------------------ komutlar
    def ozet(self):
        g = "\n".join(f"{i}. {html.escape(x['ad'])}" for i, x in enumerate(self.ayarlar["gruplar"], 1))
        k = "\n".join(f"{i}. {html.escape(self.kural_metni(x))}"
                      for i, x in enumerate(self.ayarlar["kurallar"], 1))
        return (f"Durum: {self.durum}\n\n<b>Dinlenen gruplar</b>\n{g or 'yok – /gruplar ile seçin'}\n\n"
                f"<b>Alarm kelimeleri</b>\n{k or 'yok – /kelime ile ekleyin'}")

    def komut(self, k, parca):
        if k == "/kod":
            kod = re.sub(r"\D", "", " ".join(parca[1:]))
            if not kod:
                return "Örnek: <code>/kod 1-2-3-4-5</code>"
            if self.durum != "giriş kodu bekleniyor":
                return "Şu an giriş kodu beklenmiyor."
            self.kod_kuyrugu.put(kod)
            return "Kod alındı, giriş deneniyor…"
        if k == "/dinleme":
            return self.ozet()
        if k == "/gruplar":
            filtre = normalle(" ".join(parca[1:]))

            async def listele():
                return [(d.id, d.name) async for d in self.client.iter_dialogs()
                        if (d.is_group or d.is_channel) and filtre in normalle(d.name)]
            self.son_liste = self.calistir(listele())[:40]
            if not self.son_liste:
                return "Grup bulunamadı."
            dinlenen = {g["id"] for g in self.ayarlar["gruplar"]}
            return ("<b>Gruplarınız</b> (✅ = dinleniyor)\n" +
                    "\n".join(f"{i}. {'✅ ' if gid in dinlenen else ''}{html.escape(ad)}"
                              for i, (gid, ad) in enumerate(self.son_liste, 1)) +
                    "\n\nEklemek için: <code>/grupekle 3</code> (birden çok: <code>/grupekle 3 7</code>)"
                    "\nAramak için: <code>/gruplar fırsat</code>")
        if k == "/grupekle":
            if not self.son_liste:
                return "Önce /gruplar yazın."
            eklenen = []
            for p in parca[1:]:
                if p.isdigit() and 1 <= int(p) <= len(self.son_liste):
                    gid, ad = self.son_liste[int(p) - 1]
                    if all(g["id"] != gid for g in self.ayarlar["gruplar"]):
                        self.ayarlar["gruplar"].append({"id": gid, "ad": ad})
                        eklenen.append(ad)
            self.kaydet()
            return ("➕ Dinlemeye alındı: " + ", ".join(html.escape(a) for a in eklenen)) if eklenen \
                else "Eklenecek yeni grup yok. Numaralar için /gruplar"
        if k == "/grupsil" and len(parca) >= 2 and parca[1].isdigit():
            no = int(parca[1])
            if not 1 <= no <= len(self.ayarlar["gruplar"]):
                return "Bu numarada grup yok. Numaralar için /dinleme"
            g = self.ayarlar["gruplar"].pop(no - 1)
            self.kaydet()
            return f"🗑 Dinleme bırakıldı: {html.escape(g['ad'])}"
        if k == "/kelime" and len(parca) >= 2:
            ornek = ("Örnek: <code>/kelime iphone depo</code>\n"
                     "Birden çok kural için virgülle ayırın: <code>/kelime ssd, iphone 16, ddr5</code>")
            gruplar = kural_gruplari(" ".join(parca[1:]))
            if not gruplar or any(not kel for kel, _ in gruplar):
                return "Her kuralda en az bir kelime olmalı.\n" + ornek
            eklenen, zaten = [], []
            for kelimeler, en_cok in gruplar:
                kural = {"kelimeler": kelimeler, "en_cok": self.fiyat_coz(en_cok) if en_cok else None}
                anahtar = ([normalle(x) for x in kural["kelimeler"]], kural["en_cok"])
                if any(([normalle(x) for x in v["kelimeler"]], v.get("en_cok")) == anahtar
                       for v in self.ayarlar["kurallar"] + eklenen):
                    zaten.append(kural)
                    continue
                eklenen.append(kural)
            self.ayarlar["kurallar"] += eklenen
            if eklenen:
                self.kaydet()
            satirlar = []
            if eklenen:
                satirlar.append(("🔔 Alarm kuralı eklendi" if len(eklenen) == 1 else
                                 f"🔔 {len(eklenen)} alarm kuralı eklendi") + ":")
                satirlar += [f"• <b>{html.escape(self.kural_metni(x))}</b>" for x in eklenen]
            if zaten:
                satirlar.append("Zaten vardı: " + ", ".join(html.escape(self.kural_metni(x)) for x in zaten))
            if eklenen:
                satirlar.append("Dinlenen gruplarda bir kuralın kelimelerinin hepsi kelime başında "
                                "geçen bir mesaj gelince sesli uyarı alırsınız.")
            return "\n".join(satirlar)
        if k == "/kelimesil" and len(parca) >= 2 and parca[1].isdigit():
            no = int(parca[1])
            if not 1 <= no <= len(self.ayarlar["kurallar"]):
                return "Bu numarada kural yok. Numaralar için /dinleme"
            kural = self.ayarlar["kurallar"].pop(no - 1)
            self.kaydet()
            return f"🗑 Kural silindi: {html.escape(self.kural_metni(kural))}"
        return None


YARDIM = ("<b>Grup dinleme</b>\n"
          "/dinleme – durum, dinlenen gruplar ve kelimeler\n"
          "/gruplar [ara] – Telegram gruplarınızı listele\n"
          "/grupekle &lt;no&gt; – listedeki grubu dinlemeye al\n"
          "/grupsil &lt;no&gt; – grubu dinlemekten çıkar\n"
          "/kelime &lt;kelimeler&gt; [&lt;fiyat], … – alarm kuralı ekle (virgül = ayrı kural)\n"
          "/kelimesil &lt;no&gt; – kuralı sil")
