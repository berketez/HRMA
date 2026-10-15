"""Playwright ``Page`` ikizi — ``tools/browser_harness/tur.py`` için.

Neden bu dosya var
------------------
ÖH · defter **P10B3-02**. Turun HÜKÜM katmanı (``denetimler.py``) yıllardır
tarayıcısız sınanıyordu; ÜRÜNE DOKUNAN ölçüm katmanı (``tur.py``) ise
sınanmıyordu, çünkü ``SayfaGezgini`` canlı bir Playwright ``Page`` nesnesi
istiyor. Sonuç: turun adım SIRASI, istisna dalları, hesapsız sayfa dalı ve
rapor gövdesi hiçbir testte çalışmıyordu; kusur ancak 12 dakikalık canlı
turda görülebiliyordu. D21/D22/D23'te bu kalem "sahte sayfa iskelesi
gerekiyor" gerekçesiyle ertelendi. Bu dosya o iskeledir.

İkizin sözleşmesi (fail-closed)
-------------------------------
* ``evaluate``/``wait_for_function`` **TANINMAYAN** bir betik metni alırsa
  ``BilinmeyenBetik`` yükseltir. ``tur.py``ye yeni bir ``JS_*`` sabiti
  eklenirse bekçi sessizce yeşil kalmaz, KIRMIZI yanar ve senaryoya
  eklenmeyi ister.
* İkiz hiçbir sayı UYDURMAZ: ``evaluate`` cevapları senaryodan gelir ve
  varsayılan senaryo ``docs/scofield/raw/OH/Z5/denetim/tur/tour_report.json``
  dosyasındaki **CANLI TUR ÖLÇÜMLERİNİN** yeniden oynatımıdır.
* Her çağrı ``gunluk`` listesine yazılır; testler adım SIRASINI bunun
  üzerinden sınar (ör. FEA → Merkez → sayfa metni → yerleşim).

İkizin sınırı (dürüstlük notu)
------------------------------
Bu ikiz tarayıcı SADAKATİNİ kanıtlamaz — ``JS_*`` gövdelerinin gerçek DOM'da
ne döndürdüğünü değil, ``tur.py``nin o dönüşlerle NE YAPTIĞINI sınar.
Tarayıcı sadakati canlı turun (P17B1-15) işidir.
"""

from __future__ import annotations

import io
import json
import pathlib
import zlib
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from tools.browser_harness import tur
from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parents[2]

#: Canlı turun kaydı — ikizin ``evaluate`` cevaplarının kaynağı.
CANLI_TUR_RAPORU = KOK / 'docs/scofield/raw/OH/Z5/denetim/tur/tour_report.json'

#: ÖH D24 / P17B1-15 — 5 Eylül 2026 canlı turu (sistem Chrome 152.0.7977.82).
#:
#: Ağustos (Z5) turu üç sayfayı da TEK kiracıyla (``cfd``) gezmişti; D23+D24
#: Analiz Merkezi tanımına ``acoustic_modes`` ve ``combustion_stability``
#: kiracılarını ekleyince oynatma katmanının elinde o kiracılar için HİÇ
#: ölçüm kalmadı. Bu kayıt o boşluğu GERÇEK ölçümle doldurur.
#:
#: Yalnız ``merkez.kiracilar`` bindirilir; ekran görüntüsü/yerleşim/FEA
#: ölçümleri Z5 kaydında BIRAKILIR. Sebebi ölçülmüştür: 5 Eylül turu
#: ``tam_sayfa_goruntusu`` ve ``yerlesim_metin_ortusmesi`` denetimlerinde
#: KIRMIZI (bkz. kosum.log) — bunlar başka kulvarların açık kalemleridir ve
#: bu kulvarın oynatma bekçilerini ilgilendirmez. Uydurma yok: bindirilen
#: her kiracı ölçümü turun kendi raporundan gelir.
D24_TUR_RAPORU = (KOK / 'docs/scofield/raw/OH/D24/altyapi/a2/tur_p17b115'
                  / 'tour_report.json')


def _d24_kiracilari(sayfa_adi: str) -> Dict[str, Any]:
    """5 Eylül turunun bir sayfa için ölçtüğü Merkez kiracıları."""
    if not kanit_gerekli(D24_TUR_RAPORU).exists():
        return {}
    ham = json.loads(kanit_gerekli(D24_TUR_RAPORU).read_text(encoding='utf-8'))
    for sayfa in ham.get('sayfalar', []):
        if sayfa.get('ad') == sayfa_adi:
            merkez = (sayfa.get('olcumler') or {}).get('merkez') or {}
            return dict(merkez.get('kiracilar') or {})
    return {}


def _kiracilari_bindir(sayfa_adi: str,
                       olcumler: Dict[str, Any]) -> Dict[str, Any]:
    """Z5 ölçümüne D24 turunun EKSİK kiracılarını bindirir.

    FAIL-CLOSED: Z5'te zaten ölçülmüş bir kiracının değeri EZİLMEZ; yalnız
    kaydı hiç olmayan kiracı eklenir. Böylece eski bekçilerin dayandığı
    sayılar yerinde kalır, yeni kiracılar da uydurulmadan gerçek ölçümle
    beslenir.
    """
    yeni = _d24_kiracilari(sayfa_adi)
    if not yeni:
        return olcumler
    olcumler = dict(olcumler)
    merkez = dict(olcumler.get('merkez') or {})
    kiracilar = dict(merkez.get('kiracilar') or {})
    for ad, deger in yeni.items():
        kiracilar.setdefault(ad, deger)
    if kiracilar:
        merkez['kiracilar'] = kiracilar
        olcumler['merkez'] = merkez
    return olcumler


#: ``JS_FEA_PANEL_DURUMU``nun döndürdüğü alanlar (tur.py:355-383). Kayıtlı
#: rapordaki blok bunlara EK olarak ``tur.py``nin kendi eklediği alanları da
#: taşır (``asama``, ``basladi``, ``kosum_s``…); yeniden oynatımda onlar
#: ATILIR, yoksa turun kendi çıktısı ona girdi diye geri verilmiş olurdu.
FEA_JS_ALANLARI = ('panel', 'api', 'panel_var', 'panel_gorunur', 'api_var',
                   'yuk_var', 'yuk_ozeti', 'mesgul', 'cip_metni', 'rozetler',
                   'rozet_sayisi', 'cizimler', 'panel_plotly_kap_sayisi')

#: ``JS_MERKEZ_KIRACI``nın döndürdüğü alanlar (tur.py:568-585).
MERKEZ_KIRACI_JS_ALANLARI = ('kok_var', 'kok_gorunur', 'gecmis_uzunlugu',
                             'son_kosum', 'yuk', 'cizimler', 'cizim_sayisi',
                             'rozetler', 'rozet_sayisi', 'durum_metni', 'metin')


def _yalniz(kaynak: Optional[Dict[str, Any]],
            alanlar: Sequence[str]) -> Dict[str, Any]:
    """Kayıttan YALNIZ sayfa içi betiğin ürettiği alanları süzer."""
    kaynak = kaynak or {}
    return {a: kaynak[a] for a in alanlar if a in kaynak}


class BilinmeyenBetik(AssertionError):
    """``tur.py`` senaryoda tanımsız bir ``JS_*`` sabitini koşturdu."""


class SahteZamanAsimi(Exception):
    """Playwright ``TimeoutError`` ikizi — bekleme koşulu tutmadı."""


def _js_adlari() -> Dict[str, str]:
    """``JS_*`` sabit metni → sabit adı. İkizin tek çözümleme tablosu."""
    return {getattr(tur, ad): ad for ad in dir(tur)
            if ad.startswith('JS_') and isinstance(getattr(tur, ad), str)}


# ---------------------------------------------------------------------------
# Olay ikizleri
# ---------------------------------------------------------------------------

class SahteKonsolIletisi:
    def __init__(self, tip: str, metin: str, konum: Any = None):
        self.type = tip
        self.text = metin
        self.location = konum


class SahteCevap:
    """HTTP cevabı ikizi. ``durum_patlar`` ile ``status`` okuması patlar."""

    def __init__(self, durum: int, url: str, durum_patlar: bool = False):
        self._durum = durum
        self.url = url
        self._patlar = durum_patlar

    @property
    def status(self) -> int:
        if self._patlar:
            raise RuntimeError('cevap kapandı')
        return self._durum


# ---------------------------------------------------------------------------
# PNG üretimi — ikizin ekran görüntüsü GERÇEK bayt üretir
# ---------------------------------------------------------------------------

def _png_uret(genislik: int, yukseklik: int, renk: Tuple[int, int, int, int],
              dolu_oran: float = 0.0, dokulu: bool = True) -> bytes:
    """Bağımlılıksız, geçerli bir RGBA PNG üretir.

    ``dolu_oran`` kadar satır "çizili" boyanır; böylece
    ``denetimler.piksel_olcumu`` GERÇEK bir görüntü üzerinde çalışır.
    ``dokulu=True`` çizili bölgeye belirlenimci bir doku serper (entropi
    eşiğini geçen bir sahne gibi); ``dokulu=False`` DÜZ blok bırakır —
    turun "yer tutucu blok" dalını sınamak için.
    """
    dolu_satir = int(yukseklik * max(0.0, min(1.0, dolu_oran)))
    ham = bytearray()
    for y in range(yukseklik):
        ham.append(0)  # filtre baytı
        if y >= dolu_satir:
            ham.extend(bytes(renk) * genislik)
            continue
        if not dokulu:
            ham.extend(bytes((240, 200, 80, 255)) * genislik)
            continue
        satir = bytearray()
        for x in range(genislik):
            t = (x * 37 + y * 61) % 251
            satir.extend((t, (t * 5 + 13) % 251, (t * 11 + 71) % 251, 255))
        ham.extend(satir)

    def parca(tur_: bytes, veri: bytes) -> bytes:
        golge = tur_ + veri
        return (len(veri).to_bytes(4, 'big') + golge
                + zlib.crc32(golge).to_bytes(4, 'big'))

    ihdr = (genislik.to_bytes(4, 'big') + yukseklik.to_bytes(4, 'big')
            + bytes((8, 6, 0, 0, 0)))
    return (b'\x89PNG\r\n\x1a\n' + parca(b'IHDR', ihdr)
            + parca(b'IDAT', zlib.compress(bytes(ham), 6))
            + parca(b'IEND', b''))


def veri_url(genislik: int = 96, yukseklik: int = 72,
             dolu_oran: float = 0.45, dokulu: bool = True) -> str:
    """Tuval anlık görüntüsü ikizi — ``data:image/png;base64,...``."""
    import base64
    ham = _png_uret(genislik, yukseklik, (0, 0, 0, 0), dolu_oran, dokulu)
    return 'data:image/png;base64,' + base64.b64encode(ham).decode('ascii')


# ---------------------------------------------------------------------------
# Locator ikizi
# ---------------------------------------------------------------------------

class SahteYerlestirici:
    """``Page.locator()`` dönüşü. ``first``/``nth``/``count``/``click``…"""

    def __init__(self, sayfa: 'SahteSayfa', secici: str,
                 dizin: Optional[int] = None):
        self.sayfa = sayfa
        self.secici = secici
        self.dizin = dizin

    # -- seçim --------------------------------------------------------
    @property
    def first(self) -> 'SahteYerlestirici':
        return SahteYerlestirici(self.sayfa, self.secici, 0)

    def nth(self, i: int) -> 'SahteYerlestirici':
        return SahteYerlestirici(self.sayfa, self.secici, i)

    # -- ölçüm --------------------------------------------------------
    def count(self) -> int:
        self.sayfa.gunluk.append(('count', self.secici))
        return int(self.sayfa.senaryo.secici_sayilari.get(self.secici, 0))

    def is_visible(self) -> bool:
        self.sayfa.gunluk.append(('is_visible', self._ad()))
        hata = self.sayfa.senaryo.gorunurluk_hatalari.get(self._ad())
        if hata is not None:
            raise hata
        gorunur = self.sayfa.senaryo.gorunurluk
        if self._ad() in gorunur:
            return bool(gorunur[self._ad()])
        return bool(gorunur.get(self.secici, self.count() > 0))

    # -- eylem --------------------------------------------------------
    def click(self) -> None:
        self.sayfa.gunluk.append(('click', self._ad()))
        hata = self.sayfa.senaryo.tiklama_hatalari.get(self._ad())
        if hata is not None:
            raise hata
        tepki = self.sayfa.senaryo.tiklama_tepkileri.get(self._ad())
        if tepki is not None:
            tepki(self.sayfa)

    def wait_for(self, state: str = 'visible', timeout: float = 0) -> None:
        self.sayfa.gunluk.append(('locator_wait_for', self._ad(), state))
        hata = self.sayfa.senaryo.bekleme_hatalari.get(self._ad())
        if hata is not None:
            raise hata

    # -- kanıt --------------------------------------------------------
    def screenshot(self, path: str = '', **_) -> bytes:
        """``Locator.screenshot`` ikizi — BAYT döner (ÖH D27 / OH-D25-02a).

        Beyan edilen tuvalin pikselleri ``toDataURL`` ile değil ELEMAN
        ekran görüntüsüyle okunuyor (WebGL tuvalinde ``toDataURL`` boş
        gelir; bkz. ``tur.JS_BEYANLI_TUVAL`` notu), ikizin de o yüzeyi
        taşıması gerekir. Üretilen PNG senaryodan gelir: boyut ve doluluk
        ``Senaryo.eleman_png`` alanında AÇIKÇA verilir, gizli varsayılan
        yoktur.
        """
        self.sayfa.gunluk.append(('locator_screenshot', self._ad()))
        hata = self.sayfa.senaryo.eleman_goruntusu_hatalari.get(self._ad())
        if hata is not None:
            raise hata
        gen, yuk, dolu = self.sayfa.senaryo.eleman_png
        baytlar = _png_uret(gen, yuk, (18, 20, 26, 255), dolu)
        if path:
            with open(path, 'wb') as f:
                f.write(baytlar)
        return baytlar

    def _ad(self) -> str:
        return (self.secici if self.dizin in (None, 0)
                else '%s#%d' % (self.secici, self.dizin))


# ---------------------------------------------------------------------------
# Senaryo + Page ikizi
# ---------------------------------------------------------------------------

class Senaryo:
    """İkizin cevap tablosu. Her alan AÇIKÇA verilir; sessiz varsayılan yok."""

    def __init__(self,
                 js_cevaplari: Optional[Dict[str, Any]] = None,
                 secici_sayilari: Optional[Dict[str, int]] = None,
                 gorunurluk: Optional[Dict[str, bool]] = None,
                 bekleme_sonuclari: Optional[Dict[str, Any]] = None,
                 tiklama_hatalari: Optional[Dict[str, Exception]] = None,
                 gorunurluk_hatalari: Optional[Dict[str, Exception]] = None,
                 bekleme_hatalari: Optional[Dict[str, Exception]] = None,
                 tiklama_tepkileri: Optional[Dict[str, Callable]] = None,
                 js_hatalari: Optional[Dict[str, Exception]] = None,
                 goto_hatasi: Optional[Exception] = None,
                 ag_sessizligi_hatasi: Optional[Exception] = None,
                 ekran_goruntusu_hatasi: Optional[Exception] = None,
                 konsol_iletileri: Sequence[SahteKonsolIletisi] = (),
                 sayfa_hatalari: Sequence[Any] = (),
                 cevaplar: Sequence[SahteCevap] = (),
                 ekran_png: Tuple[int, int] = (1280, 3400),
                 eleman_png: Tuple[int, int, float] = (1600, 946, 0.61),
                 eleman_goruntusu_hatalari: Optional[Dict[str, Exception]] = None):
        self.js_cevaplari = dict(js_cevaplari or {})
        self.secici_sayilari = dict(secici_sayilari or {})
        self.gorunurluk = dict(gorunurluk or {})
        self.bekleme_sonuclari = dict(bekleme_sonuclari or {})
        self.tiklama_hatalari = dict(tiklama_hatalari or {})
        self.gorunurluk_hatalari = dict(gorunurluk_hatalari or {})
        self.bekleme_hatalari = dict(bekleme_hatalari or {})
        self.tiklama_tepkileri = dict(tiklama_tepkileri or {})
        self.js_hatalari = dict(js_hatalari or {})
        self.goto_hatasi = goto_hatasi
        self.ag_sessizligi_hatasi = ag_sessizligi_hatasi
        self.ekran_goruntusu_hatasi = ekran_goruntusu_hatasi
        self.konsol_iletileri = list(konsol_iletileri)
        self.sayfa_hatalari = list(sayfa_hatalari)
        self.cevaplar = list(cevaplar)
        self.ekran_png = ekran_png
        #: ÖH D27 / OH-D25-02(a) — beyanlı tuvalin ELEMAN görüntüsü:
        #: (genişlik, yükseklik, doluluk). Varsayılan, canlı ölçümün
        #: kendisidir: ``/launch-site`` küresi 1600x946 ve %61,4 dolu
        #: (docs/scofield/raw/OH/D27/altyapi/a1/sonra_canli.json).
        self.eleman_png = eleman_png
        self.eleman_goruntusu_hatalari = dict(eleman_goruntusu_hatalari or {})


class SahteSayfa:
    """Playwright ``Page`` ikizi.

    ``tur.SayfaGezgini``nin kullandığı YÜZEYİN tamamı: ``on``, ``goto``,
    ``wait_for_load_state``, ``evaluate``, ``wait_for_function``,
    ``wait_for_timeout``, ``locator``, ``screenshot``.
    """

    def __init__(self, senaryo: Senaryo):
        self.senaryo = senaryo
        self.gunluk: List[tuple] = []
        self.dinleyiciler: Dict[str, List[Callable]] = {}
        self.evaluate_cagrilari: List[Tuple[str, Any]] = []
        self._adlar = _js_adlari()

    # -- olaylar ------------------------------------------------------
    def on(self, olay: str, isleyici: Callable) -> None:
        self.dinleyiciler.setdefault(olay, []).append(isleyici)
        self.gunluk.append(('on', olay))

    def _olaylari_ates(self) -> None:
        for ileti in self.senaryo.konsol_iletileri:
            for i in self.dinleyiciler.get('console', []):
                i(ileti)
        for hata in self.senaryo.sayfa_hatalari:
            for i in self.dinleyiciler.get('pageerror', []):
                i(hata)
        for cevap in self.senaryo.cevaplar:
            for i in self.dinleyiciler.get('response', []):
                i(cevap)

    # -- gezinme ------------------------------------------------------
    def goto(self, url: str, wait_until: str = '', timeout: float = 0):
        self.gunluk.append(('goto', url))
        if self.senaryo.goto_hatasi is not None:
            raise self.senaryo.goto_hatasi
        self._olaylari_ates()
        return None

    def wait_for_load_state(self, state: str = 'load', timeout: float = 0):
        self.gunluk.append(('wait_for_load_state', state))
        if self.senaryo.ag_sessizligi_hatasi is not None:
            raise self.senaryo.ag_sessizligi_hatasi

    def wait_for_timeout(self, ms: float) -> None:
        self.gunluk.append(('wait_for_timeout', ms))

    # -- betik --------------------------------------------------------
    def _ad_coz(self, betik: str) -> str:
        ad = self._adlar.get(betik)
        if ad is None:
            raise BilinmeyenBetik(
                'tur.py senaryoda tanımsız bir betik koşturdu (ilk 120 '
                'karakter): %r' % (betik[:120],))
        return ad

    def evaluate(self, betik: str, arg: Any = None) -> Any:
        ad = self._ad_coz(betik)
        self.gunluk.append(('evaluate', ad))
        self.evaluate_cagrilari.append((ad, arg))
        hata = self.senaryo.js_hatalari.get(ad)
        if hata is not None:
            raise hata
        if ad not in self.senaryo.js_cevaplari:
            raise BilinmeyenBetik('senaryoda %s cevabı yok' % ad)
        cevap = self.senaryo.js_cevaplari[ad]
        return cevap(arg) if callable(cevap) else cevap

    def wait_for_function(self, betik: str, arg: Any = None,
                          timeout: float = 0) -> Any:
        ad = self._ad_coz(betik) if betik in self._adlar else betik
        self.gunluk.append(('wait_for_function', ad))
        if ad in self.senaryo.bekleme_hatalari:
            raise self.senaryo.bekleme_hatalari[ad]
        if ad in self.senaryo.bekleme_sonuclari:
            sonuc = self.senaryo.bekleme_sonuclari[ad]
            return sonuc(arg) if callable(sonuc) else sonuc
        return True

    # -- öğe ----------------------------------------------------------
    def locator(self, secici: str) -> SahteYerlestirici:
        self.gunluk.append(('locator', secici))
        return SahteYerlestirici(self, secici)

    # -- kanıt --------------------------------------------------------
    def screenshot(self, path: str = '', full_page: bool = False) -> None:
        self.gunluk.append(('screenshot', path, full_page))
        if self.senaryo.ekran_goruntusu_hatasi is not None:
            raise self.senaryo.ekran_goruntusu_hatasi
        gen, yuk = self.senaryo.ekran_png
        with open(path, 'wb') as f:
            f.write(_png_uret(gen, yuk, (18, 20, 26, 255), 0.4))

    # -- test yardımcıları --------------------------------------------
    def adimlar(self, tip: str) -> List[tuple]:
        return [k for k in self.gunluk if k[0] == tip]

    def betik_sirasi(self) -> List[str]:
        return [k[1] for k in self.gunluk
                if k[0] in ('evaluate', 'wait_for_function')]


# ---------------------------------------------------------------------------
# Tarayıcı / bağlam / playwright ikizleri (``turu_kos`` için)
# ---------------------------------------------------------------------------

class SahteBaglam:
    def __init__(self, tarayici: 'SahteTarayici', **kw):
        self.tarayici = tarayici
        self.acilis = kw
        self.kapandi = False

    def new_page(self):
        return self.tarayici.sayfa_uret()

    def close(self):
        self.kapandi = True
        self.tarayici.gunluk.append(('baglam_kapandi',))


class SahteTarayici:
    def __init__(self, sayfa_uretici: Callable[[], SahteSayfa],
                 surum: str = '999.0.0-ikiz'):
        self.sayfa_uret = sayfa_uretici
        self.version = surum
        self.baglamlar: List[SahteBaglam] = []
        self.gunluk: List[tuple] = []
        self.kapandi = False

    def new_context(self, **kw):
        b = SahteBaglam(self, **kw)
        self.baglamlar.append(b)
        self.gunluk.append(('baglam_acildi', kw))
        return b

    def close(self):
        self.kapandi = True


class SahteChromium:
    """``pw.chromium`` ikizi. ``acilabilir_kanallar`` dışındakiler patlar."""

    def __init__(self, tarayici_uretici: Callable[[], SahteTarayici],
                 acilabilir_kanallar: Sequence[Optional[str]] = ('',)):
        self._uret = tarayici_uretici
        self.acilabilir = set(acilabilir_kanallar)
        self.denemeler: List[Dict[str, Any]] = []

    def launch(self, **kw):
        kanal = kw.get('channel', '')
        self.denemeler.append(dict(kw))
        if kanal not in self.acilabilir:
            raise RuntimeError('kanal açılamadı: %r' % (kanal or '(paketli)',))
        return self._uret()


class SahtePlaywright:
    def __init__(self, chromium: SahteChromium):
        self.chromium = chromium
        self.kapandi = False

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.kapandi = True
        return False


def sahte_sync_playwright(chromium: SahteChromium) -> Callable[[], SahtePlaywright]:
    def fabrika():
        return SahtePlaywright(chromium)
    return fabrika


# ---------------------------------------------------------------------------
# CANLI TUR YENİDEN OYNATIMI
# ---------------------------------------------------------------------------

def canli_olcumler(sayfa_adi: str = 'hybrid',
                   zorunlu: bool = True) -> Dict[str, Any]:
    """Kayıtlı canlı turdan bir sayfanın HAM ölçümlerini okur.

    Uydurulmuş sayı yok: değerler 2026 Ağustos canlı turunun raporundan
    gelir (``docs/scofield/raw/OH/Z5/denetim/tur/tour_report.json``). O tur
    yalnız HESAPLI üç sayfayı gezmişti; hesapsız sayfalar için
    ``zorunlu=False`` ile boş ölçüm dönebilir (o sayfalarda ölçülecek
    3B/FEA/Merkez zaten YOKTUR).
    """
    ham = json.loads(kanit_gerekli(CANLI_TUR_RAPORU).read_text(encoding='utf-8'))
    for sayfa in ham.get('sayfalar', []):
        if sayfa.get('ad') == sayfa_adi:
            return _kiracilari_bindir(sayfa_adi, sayfa.get('olcumler', {}))
    if zorunlu:
        raise AssertionError('canlı tur raporunda %r sayfası yok' % sayfa_adi)
    return {}


def canli_senaryo(sayfa_adi: str = 'hybrid', **degistir) -> Senaryo:
    """Canlı turun ölçümlerini oynatan tam senaryo (mutlu yol).

    ``degistir`` ile herhangi bir alan üzerine yazılabilir; böylece kusur
    dalları (patlayan panel, kurulmayan sahne…) aynı tabandan türetilir.
    """
    from tools.browser_harness import esikler, sayfalar

    tanim = sayfalar.SAYFALAR[sayfa_adi]
    olcum = canli_olcumler(sayfa_adi, zorunlu=tanim.hesap_var)
    fea = olcum.get('fea') or {}
    merkez = olcum.get('merkez') or {}
    kiracilar = merkez.get('kiracilar') or {}

    def fea_cevabi(arg):
        for t in tanim.fea_panelleri:
            if arg and arg.get('panel') == t.panel_kimligi:
                return _yalniz(fea.get(t.ad), FEA_JS_ALANLARI)
        return {}

    # ÖH D24 / P17B1-15 — KİRACI AYRIMI, seçiciyle DEĞİL tıklanan satırla.
    #
    # ÖLÇÜLDÜ: ``acoustic_modes`` ile ``combustion_stability`` AYNI çizim ve
    # rozet seçicisini paylaşır (``[data-stab-plot]`` / ``[data-stab-badge]``)
    # — ikisi de tek bir kararlılık görüntüleyicisine basar. Eski eşleme
    # yalnız seçiciye bakıyordu, dolayısıyla İKİNCİ kiracı her zaman
    # BİRİNCİnin ölçümünü alıyordu; bu yüzden ``/hybrid`` mutlu yol
    # bekçisinden çıkarılmıştı ve kiracı eklenen her sayfa aynı duvara
    # çarpıyordu.
    #
    # Ürünün kendi davranışı taklit ediliyor: tur bir kiracıyı koşturmadan
    # ÖNCE onun SATIRINA tıklar, görüntüleyici de o satırın çıktısını
    # gösterir. İkiz artık son tıklanan satırı hatırlıyor.
    secili = {'ad': None}

    def satir_tepkisi(kiraci_adi):
        def tepki(_sayfa):
            secili['ad'] = kiraci_adi
        return tepki

    def kiraci_cevabi(arg):
        if not arg:
            return {}
        adaylar = [k for k in tanim.merkez_kiracilari
                   if arg.get('cizim_secici') == k.cizim_secicisi]
        if not adaylar:
            return {}
        secim = adaylar[0]
        if len(adaylar) > 1:
            for k in adaylar:
                if k.ad == secili['ad']:
                    secim = k
                    break
        return _yalniz(kiracilar.get(secim.ad), MERKEZ_KIRACI_JS_ALANLARI)

    js = {
        'JS_VIZ_DURUMU': dict(olcum.get('viz') or {}),
        'JS_SAHNE_KURULDU': True,
        'JS_OYNAT': True,
        'JS_TUVAL': {'kaynak': 'MotorViz3D.snapshot()', 'veri_url': veri_url()},
        # ÖH D27 / OH-D25-02(a): beyanlı tuvalin KİMLİĞİ. Sayılar canlı
        # ölçümden gelir (``/launch-site`` küresi 1600x946; kanıt
        # docs/scofield/raw/OH/D27/altyapi/a1/sonra_canli.json), pikseller
        # eleman ekran görüntüsünden okunur.
        'JS_BEYANLI_TUVAL': {'tuval_genislik': 1600, 'tuval_yukseklik': 946,
                             'ekran_genislik': 1600, 'ekran_yukseklik': 945},
        'JS_SAYFA_METNI': 'Hybrid Rocket Motor Analysis — chamber pressure 25 bar',
        'JS_YERLESIM': dict(olcum.get('yerlesim') or {}),
        'JS_FEA_PANEL_DURUMU': fea_cevabi,
        'JS_MERKEZ_CERCEVE': dict(merkez.get('cerceve') or {}),
        'JS_MERKEZ_GECMIS_UZUNLUGU': 0,
        'JS_MERKEZ_KIRACI': kiraci_cevabi,
    }
    sayilar = {tanim.hesapla_secici: 1,
               'button.viz-play': 1,
               '#' + esikler.MERKEZ_KOSUM_DUGMESI_KIMLIGI: 1}
    gorunur = {tanim.hesapla_secici: True, 'button.viz-play': True}
    for t in tanim.fea_panelleri:
        sayilar[t.kosum_secicisi] = 1
        gorunur[t.kosum_secicisi] = True
    for k in tanim.merkez_kiracilari:
        sayilar[k.satir_secicisi] = 1
        gorunur[k.satir_secicisi] = True

    tiklama_tepkileri = {k.satir_secicisi: satir_tepkisi(k.ad)
                         for k in tanim.merkez_kiracilari}

    varsayilan = dict(js_cevaplari=js, secici_sayilari=sayilar,
                      gorunurluk=gorunur,
                      tiklama_tepkileri=tiklama_tepkileri)
    for anahtar, deger in degistir.items():
        if anahtar in ('js_cevaplari', 'secici_sayilari', 'gorunurluk'):
            birlesik = dict(varsayilan[anahtar])
            birlesik.update(deger)
            varsayilan[anahtar] = birlesik
        else:
            varsayilan[anahtar] = deger
    return Senaryo(**varsayilan)
