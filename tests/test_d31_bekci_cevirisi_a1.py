# -*- coding: utf-8 -*-
"""ÖH Dalga-31 · bekçi çevirisi · aşama 1 — OH-D17-14 kilit bekçisi.

Kalem OH-D17-14 şunu iddia ediyordu: ``tests/test_d16_kati_a1.py::
TestKirpmaKunyesiUctaBekcili`` EŞZAMANLI koşumda 3 kırmızı veriyor
(rapor edilen belirti: "kırpılmış satır eps 3,4858 / kırpılmamış 0 /
basis tek metin"), yalıtıkta 4/4 yeşil; sebebi ``/calculate_solid``
üstünde testler arası sızan paylaşılan durum/önbellek.

ÖLÇÜLDÜ (docs/scofield/raw/OH/D31/bekci-cevirisi/a1/once_ohd1714.json —
üreten betik aynı dizindeki ``olcum_ohd1714.py``):

  * tek süreçte 5 tekrar  -> tek sha256 (belirlenimli)
  * Pc=40 isteği ÖNCE koşarsa Pc=5 yanıtı BİT-AYNI (sıraya bağlı değil)
  * 12 iş parçacığı, karışık gövde -> 0 sapma, 0 değişmez ihlali
  * 3 eşzamanlı SÜREÇ -> 3 × 4/4 yeşil
  * 20 geçerli (yakıt × Pc) koşusu -> 0 değişmez ihlali

Rapor edilen belirti, bugünkü ürün kodunda YAPISAL olarak üretilemez:
``expansion_ratio_clamped`` satır başına ``|eps - eps_ham| > 1e-9``
ile çözülür, dolayısıyla kırpılmış satırın epsilon'u zorunlu olarak
bant kenarındadır (2,5 ya da 500) — "kırpılmış satır eps 3,4858"
ancak bayrak SATIR BAŞINA çözülmeyi bırakırsa (koşu boyunca yapışkan
hâle gelirse) mümkündür. Aşağıdaki üç sınıf tam da bunu kilitler:
kalem 'çürütüldü' diye kapanırken iddianın tarif ettiği kusur bir daha
sessizce giremesin.

Ters-mutasyon kanıtı: ``docs/scofield/raw/OH/D31/bekci-cevirisi/a1/
mutasyon_ohd1714.json`` — üç mutasyon, ürün dosyasının baytları geçici
değiştirilip geri yazılarak (md5 eşitliği doğrulanmış):

  M1 yapışkan bayrak      -> bu dosya 4 kırmızı, D16 bekçisi 3 kırmızı
                             (kalemin rapor ettiği belirtinin ta kendisi:
                             ``assert (3.4857751772293937 == 2.5 ± 2.5e-06``)
  M2 gövde-körü önbellek  -> bu dosya 1 kırmızı, D16 bekçisi KÖR (4 yeşil)
  M3 sıraya bağlı bant    -> bu dosya 3 kırmızı, D16 bekçisi KÖR (4 yeşil)
"""

import hashlib
import json
import threading
import warnings

import pytest

from hrma.app import app as flask_app


#: Ürünün yayımladığı kırpma bandı (hrma/engines/solid_rocket_engine.py,
#: ``calculate_altitude_performance``: ``max(2.5, min(epsilon_opt, 500))``).
BAND_ALT, BAND_UST = 2.5, 500.0

#: OH-D17-14'ün konusu olan bekçinin gövdesiyle AYNI taban
#: (tests/test_d16_kati_a1.py::UC_TABAN).
UC_TABAN = dict(motor_name='D16-KATI', propellant_type='apcp',
                grain_type='bates', chamber_pressure=40.0, thrust=5000.0,
                burn_time=3.0, chamber_diameter=100.0, grain_length=500.0,
                core_diameter=30.0, expansion_ratio=8.0)
#: ``TestKirpmaKunyesiUctaBekcili`` fikstürünün gövdesi.
BEKCI_GOVDE = dict(UC_TABAN, chamber_pressure=5.0, expansion_ratio=2.5)


@pytest.fixture(scope='module')
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        yield c


def _satirlar(istemci, govde):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        r = istemci.post('/calculate_solid', json=govde)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    ap = r.get_json()['altitude_performance']
    if isinstance(ap, dict):
        ap = ap['altitude_performance']
    assert isinstance(ap, list) and ap
    return ap


def _parmak_izi(satirlar):
    """Bekçinin okuduğu ÜÇ alanın (+ epsilon) kararlı özeti."""
    veri = [(s['altitude'], round(float(s['expansion_ratio']), 9),
             bool(s['expansion_ratio_clamped']),
             (None if s['expansion_ratio_uncapped'] is None
              else round(float(s['expansion_ratio_uncapped']), 6)),
             s['expansion_ratio_basis'][:24]) for s in satirlar]
    ham = json.dumps(veri, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(ham.encode('utf-8')).hexdigest()


def kunye_ihlalleri(satirlar):
    """Kırpma künyesinin SATIR BAŞINA çözülme değişmezleri.

    Döner: ihlal metinlerinin listesi (boş liste = künye tutarlı).
    Dört bağ ölçülür ve hepsi aynı yöne bakar:
      1. ``clamped`` ise epsilon bant KENARINDA olmalı (2,5 / 500),
      2. ``clamped`` ise ham (uncapped) değer VAR ve epsilon'dan farklı,
      3. ``clamped`` DEĞİLSE ham değer YOK ve epsilon bandın İÇİNDE,
      4. ``basis`` metni iki durumu AYIRIR ('clamped' / 'optimum').
    """
    ihlal = []
    for s in satirlar:
        etiket = s.get('altitude')
        for alan in ('expansion_ratio', 'expansion_ratio_clamped',
                     'expansion_ratio_uncapped', 'expansion_ratio_basis'):
            if alan not in s:
                ihlal.append('%s: %s alanı yok' % (etiket, alan))
        if ihlal:
            continue
        eps = float(s['expansion_ratio'])
        basis = s['expansion_ratio_basis']
        ham = s['expansion_ratio_uncapped']
        if s['expansion_ratio_clamped']:
            if not (abs(eps - BAND_ALT) < 1e-9 or abs(eps - BAND_UST) < 1e-9):
                ihlal.append('%s: kırpılmış ama eps=%.4f bant kenarında değil'
                             % (etiket, eps))
            if ham is None or abs(float(ham) - eps) <= 1e-9:
                ihlal.append('%s: kırpılmış ama ham değer yok/epsilon ile eşit'
                             % etiket)
            if 'clamped' not in basis:
                ihlal.append('%s: kırpılmış ama basis metni "clamped" demiyor'
                             % etiket)
        else:
            if ham is not None:
                ihlal.append('%s: kırpılmamış ama ham değer yayımlanıyor'
                             % etiket)
            if not (BAND_ALT - 1e-9 <= eps <= BAND_UST + 1e-9):
                ihlal.append('%s: kırpılmamış ama eps=%.4f bant dışı'
                             % (etiket, eps))
            if 'optimum' not in basis:
                ihlal.append('%s: kırpılmamış ama basis metni "optimum" demiyor'
                             % etiket)
    return ihlal


# ---------------------------------------------------------------------------
# OH-D17-14 · 1 — künye SATIR BAŞINA çözülür (yapışkan bayrak yasak)
# ---------------------------------------------------------------------------
class TestKirpmaKunyesiSatirBasinaCozulur:
    """Rapor edilen belirtinin ("kırpılmış satır eps 3,4858 / kırpılmamış 0 /
    basis tek metin") TEK üretilebilir sebebi, kırpma bayrağının satır
    başına değil KOŞU başına çözülmesidir: ilk satır 2,5'e kırpılınca
    bayrak yapışır ve sonraki satırlar da kırpılmış görünür. O zaman
    bant-içi bir satır (Pc=5, 10 km: eps 3,4858) 'kırpılmış' diye
    yayımlanır, kırpılmamış satır kalmaz ve basis tek metne düşer.

    Bu sınıf üç belirtiyi de aynı ölçümle kilitler ve bunu TEK bir köşede
    değil girdi uzayında (yakıt × kamara basıncı) yapar."""

    YAKITLAR = ('apcp', 'knsb', 'knsu', 'htpb')
    #: Uç bandı 5-200 bar (``_form_band_kapisi``); dışı 400 ile reddedilir.
    BASINCLAR = (5.0, 10.0, 40.0, 200.0)

    def test_bekcinin_kendi_kosesinde_ucgen_tutarli(self, client):
        satirlar = _satirlar(client, dict(BEKCI_GOVDE))
        assert kunye_ihlalleri(satirlar) == []
        # Rapor edilen belirtinin sayısal karşılığı: bu köşede hem
        # kırpılmış hem kırpılmamış satır VARDIR (ölçüldü: 5 / 3).
        kirpilan = [s for s in satirlar if s['expansion_ratio_clamped']]
        temiz = [s for s in satirlar if not s['expansion_ratio_clamped']]
        assert kirpilan and temiz, (len(kirpilan), len(temiz))
        assert len({s['expansion_ratio_basis'] for s in satirlar}) == 2

    def test_GIRDI_UZAYINDA_ucgen_bozulmuyor(self, client):
        bulgular = []
        for yakit in self.YAKITLAR:
            for pc in self.BASINCLAR:
                govde = dict(UC_TABAN, propellant_type=yakit,
                             chamber_pressure=pc, expansion_ratio=2.5)
                ihlal = kunye_ihlalleri(_satirlar(client, govde))
                if ihlal:
                    bulgular.append((yakit, pc, ihlal[:2]))
        assert bulgular == [], bulgular


# ---------------------------------------------------------------------------
# OH-D17-14 · 2 — yanıt istek SIRASINA bağlı değil
# ---------------------------------------------------------------------------
class TestKirpmaKunyesiIstekSirasinaBagliDegil:
    """Kalem "testler arası sızan paylaşılan durum/önbellek" diyordu.
    Dağıtılmış koşumda (``-n``) değişen şey sıradır: bekçi, aynı süreçte
    ÖNCE başka bir ``/calculate_solid`` isteği koşmuş bir işçiye düşebilir
    (bu dosyanın komşusu ``kati_yanit`` fikstürü Pc=40 ile tam bunu yapar).
    Yanıt sıraya bağlıysa bekçi yalıtıkta yeşil, sürüde kırmızı olur."""

    def test_yanit_ISTEGE_bagli_kalir_pc40_pc5_pc40(self, client):
        """Sıra: Pc=40 -> Pc=5 -> Pc=40. Paylaşılan bir yanıt önbelleği
        (ya da ilk koşuyu yapıştıran bir durum) olsaydı üç yanıttan en az
        biri KENDİ gövdesini değil öncekini anlatırdı."""
        a = _satirlar(client, dict(UC_TABAN))
        b = _satirlar(client, dict(BEKCI_GOVDE))
        c = _satirlar(client, dict(UC_TABAN))
        assert _parmak_izi(a) == _parmak_izi(c)      # sıra yanıtı kaydırmıyor
        assert _parmak_izi(a) != _parmak_izi(b)      # gövde yanıtı belirliyor
        # Deniz seviyesi satırı iki gövdeyi FİZİKSEL olarak ayırır: Pc=5'te
        # optimum genişleme 1,466 (< 2,5) olduğu için satır KIRPILIR; Pc=40'ta
        # 5,93 olduğu için kırpılmaz (ölçüldü: once_ohd1714.json).
        assert b[0]['expansion_ratio_clamped'] is True, b[0]
        assert a[0]['expansion_ratio_clamped'] is False, a[0]
        assert kunye_ihlalleri(a) == [] and kunye_ihlalleri(b) == []

    def test_ayni_istek_bes_kez_TEK_parmak_izi(self, client):
        izler = {_parmak_izi(_satirlar(client, dict(BEKCI_GOVDE)))
                 for _ in range(5)}
        assert len(izler) == 1, izler


# ---------------------------------------------------------------------------
# OH-D17-14 · 3 — eşzamanlı istekler birbirinin yanıtını kirletmiyor
# ---------------------------------------------------------------------------
class TestKirpmaKunyesiEszamanliIsteklerdeSapmaz:
    """Süreç içi eşzamanlılık: aynı Flask uygulamasına iki FARKLI gövde
    (Pc=5 ve Pc=40) aynı anda gider. Paylaşılan bir durum/önbellek olsaydı
    bir isteğin yanıtı ötekinin sayılarını taşırdı; kalemin tarif ettiği
    sızıntı tam olarak budur."""

    IS_PARCACIGI = 8

    def test_sekiz_is_parcacigi_kendi_referansindan_SAPMIYOR(self, client):
        ref = {'pc5': _parmak_izi(_satirlar(client, dict(BEKCI_GOVDE))),
               'pc40': _parmak_izi(_satirlar(client, dict(UC_TABAN)))}
        sonuc = [None] * self.IS_PARCACIGI
        kilit = threading.Lock()

        def _kos(i):
            ad = 'pc5' if i % 2 == 0 else 'pc40'
            govde = dict(BEKCI_GOVDE) if ad == 'pc5' else dict(UC_TABAN)
            try:
                with flask_app.test_client() as istemci:
                    satirlar = _satirlar(istemci, govde)
                kayit = (ad, _parmak_izi(satirlar), kunye_ihlalleri(satirlar))
            except Exception as exc:                    # noqa: BLE001
                kayit = (ad, 'HATA: %s' % exc, ['istek tamamlanmadı'])
            with kilit:
                sonuc[i] = kayit

        isler = [threading.Thread(target=_kos, args=(i,))
                 for i in range(self.IS_PARCACIGI)]
        for t in isler:
            t.start()
        for t in isler:
            t.join(timeout=180)
        sapan = [k for k in sonuc if k is None or k[1] != ref[k[0]]]
        assert sapan == [], sapan
        assert [k for k in sonuc if k[2]] == []
