"""ÖH D27 / app-api aşama-2 bekçileri — OH-D25-23 (bandın TEK adı).

Kalem (D26 DEVİR, D25 fix-23 raporundan): *"6-DOF reddi ``allowed_range``,
2B reddi ``accepted_range`` adıyla yayımlıyor — aynı kavram iki ad
(paylaşımlı ``_collect_unphysical_fields``)"*.

**ÖLÇÜM** (``docs/scofield/raw/OH/D27/app-api/a2/once.json``, taban
``8f083ca0`` + D27 a1):

* K1 statik — ``hrma/app.py`` canlı satırlarında ``'allowed_range'`` **4**
  (``:2344``, ``:2426``, ``:3487``, ``:16079``), ``'allowed_range_m'`` **1**
  (``:16375``), ``'accepted_range'`` **17**.
* K2/K3 dinamik — süpürülen 9 ret gövdesinin **7'si** bant yayımlıyor ve
  bunların **6'sı eski adı** kullanıyordu; yalnız ``/calculate`` kanonu
  basıyordu. Dolaşımdaki benzersiz bant adı sayısı **3**
  (``allowed_range``, ``allowed_range_m``, ``accepted_range``).
* K4 tüketici — ürün yüzünde (``templates`` + ``static`` + ``electron``)
  eski adın **0** tüketicisi var; bedeli TESTLER ödüyordu: 14 satır eski
  adı okuyor, ``tests/test_d24_app_api_a1.py:314`` iki anahtarı da
  denemek zorunda kalıyordu (``.get('accepted_range') or
  .get('allowed_range')``).
* K5 kanon gerekçesi — ölçülen: ``accepted_range`` künye ailesiyle
  (``accepted_range_text``, ``accepted_range_exclusive``,
  ``canonical_range``) yayımlanan addır; eski adın künye kardeşi yoktur.

**ONARIM:** kanon = ``accepted_range``; 5 üretici/tüketici sitesi ve 9
bekçi satırı AYNI commit'te çevrildi. D26'nın engeli (kardeş dal
``tests/test_d16_yapisal_sistem_a1.py``ye dokunuyordu) D27'de kalktı;
ölçüldü: ``a2/kardes_dal.json`` — 11 kardeş dalın hiçbiri ne o dosyaya ne
``allowed_range`` satırlarına dokunuyor.

Ters-mutasyon: ``docs/scofield/raw/OH/D27/app-api/a2/mutasyon.json``.
"""
import ast
import contextlib
import io
import re
import sys
import tokenize
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
APP_KAYNAK = (KOK / 'hrma' / 'app.py').read_text(encoding='utf-8')
sys.path.insert(0, str(KOK / 'tests'))

#: Kanonik kök ad ve ürün yüzünde meşru olan tek ailesi.
KANON = 'accepted_range'
ESKI = 'allowed_range'


@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _post(istemci, yol, yuk):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            r = istemci.post(yol, json=yuk)
    try:
        j = r.get_json()
    except Exception:
        j = None
    return r.status_code, (j if isinstance(j, dict) else {})


def _canli(ad):
    """D26 a3 K8 betiğiyle BİREBİR aynı desen (sayılar kıyaslanabilsin).

    Yorum satırları sayılmaz: kapanış notu eski adı TARİHSEL ölçüm olarak
    kaynakta taşıyor, o bir üretici değildir.
    """
    return len([r for r in APP_KAYNAK.split('\n')
                if "'%s'" % ad in r and not r.lstrip().startswith('#')])


def _bant_adlari(kayit):
    """Bir ``invalid_fields`` kaydındaki bant anahtarları (künye ekleri hariç)."""
    return {k for k in kayit
            if re.search(r'range', k)
            and not k.endswith(('_text', '_exclusive', '_source'))
            and k not in ('canonical_range',)}


def _canli_kod_satirlari(yol):
    """Dosyanın satırları; YORUM ve KÜNYE (docstring) gövdeleri boşaltılmış.

    Satır numaraları korunur, böylece bulgular dosyadaki gerçek satırı
    gösterir.

    NEDEN yalnız yorum + künye, "bütün dizeler" DEĞİL: aranan şey bir dize
    SABİTİDİR (``'allowed_range'``). Bütün ``STRING`` belirteçlerini
    boşaltan bir tarama, ölçtüğü şeyi de siler ve HER ZAMAN yeşil kalır —
    bu ters-mutasyonla ölçüldü (``a2/mutasyon.json`` M6, ilk tur: hoşgörü
    geri kondu, bekçi yine de YEŞİL kaldı). Künye ile canlı kodu ayıran
    şey belirteç TÜRÜ değil, dizenin ifade DEYİMİ olarak tek başına
    durmasıdır; o yüzden künyeler ``ast`` ile bulunur.
    """
    ham = yol.read_text(encoding='utf-8', errors='ignore')
    satirlar = ham.split('\n')
    try:
        agac = ast.parse(ham)
    except SyntaxError:
        return satirlar
    bosalt = set()
    for dugum in ast.walk(agac):
        # Tek başına duran dize deyimi = künye/blok yorum.
        if isinstance(dugum, ast.Expr) and isinstance(
                dugum.value, ast.Constant) and isinstance(
                    dugum.value.value, str):
            bosalt.update(range(dugum.lineno,
                                (dugum.end_lineno or dugum.lineno) + 1))
    try:
        with open(yol, 'rb') as f:
            for bel in tokenize.tokenize(f.readline):
                if bel.type == tokenize.COMMENT:
                    bosalt.add(bel.start[0])
    except (tokenize.TokenError, SyntaxError, IndentationError):
        pass
    for no in bosalt:
        i = no - 1
        if 0 <= i < len(satirlar):
            satirlar[i] = ''
    return satirlar


P16_TABAN = {'burn_time': 10, 'mdot_ox': 1.9,
             'port_diameter_initial': 0.03, 'fuel_type': 'htpb'}

HIBRIT = {'motor_type': 'hybrid', 'thrust': 1000, 'burn_time': 10,
          'of_ratio': 6.0, 'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
          'chamber_pressure': 20.0}

#: Ölçümde (K2) bant yayımladığı GÖRÜLEN uçlar; her biri kanona bağlanır.
BANT_YAYIMLAYAN_UCLAR = [
    ('six_dof__cd0', '/api/six-dof-analysis',
     {'mass': 10, 'thrust': 1000, 'burn_time': 10, 'cd0': 1e9}, 'cd0'),
    ('regression__burn_time', '/api/regression-analysis',
     {'motor_data': dict(P16_TABAN, burn_time=1e9)}, 'burn_time'),
    ('regression__port_ilk', '/api/regression-analysis',
     {'motor_data': dict(P16_TABAN, port_diameter_initial=1e9)},
     'port_diameter_initial'),
    ('thermal__chamber_pressure', '/analyze_thermal_safety',
     {'chamber_pressure': 1e9, 'chamber_temperature': 3000,
      'chamber_diameter': 0.1, 'wall_thickness': 0.005,
      'material_type': 'steel'}, 'chamber_pressure'),
    ('calculate__hibrit', '/calculate',
     dict(HIBRIT, burn_time=1e9), 'burn_time'),
]


# ---------------------------------------------------------------------------
# 1. STATİK — eski adın canlı üreticisi kalmadı
# ---------------------------------------------------------------------------
class TestOHD2523StatikKanon:
    """K1'in kapanışı: 4 + 1 site sıfıra indi, kanon 17'den 21+'e çıktı."""

    def test_eski_adin_canli_uretici_sayisi_sifir(self):
        assert _canli(ESKI) == 0, (
            'eski bant adı canlı koda geri döndü (ölçüm: D26 a3 K8 = 4 '
            'site); aynı kavram yine iki adla yayımlanıyor')

    def test_eski_adin_birim_kardesi_de_sifir(self):
        assert _canli(ESKI + '_m') == 0, (
            '``allowed_range_m`` geri döndü; ``_m`` bir birim ekidir, '
            'ayrı bir KÖK ad değildir')

    def test_kanon_devralinan_siteleri_tasiyor(self):
        # 17 kanonik + 4 devralınan = en az 21 (yastıksız alt sınır).
        assert _canli(KANON) >= 21, (
            'kanonik ad azaldı: çevrilen 4 site kanona geçmemiş olabilir')

    def test_kapanis_gerekcesi_kaynakta_adiyla_yazili(self):
        """Engel notu kapanış notuyla değişti; sonraki dalga körlemesine

        gelmesin diye kanonun GEREKÇESİ kaynakta durur."""
        assert 'OH-D25-23 · KAPANDI' in APP_KAYNAK
        assert 'OH-D25-23 · ENGELLİ (kardeş dal)' not in APP_KAYNAK


# ---------------------------------------------------------------------------
# 2. DİNAMİK — her ret gövdesi TEK adı yayımlar
# ---------------------------------------------------------------------------
class TestOHD2523UrunYuzundeTekAd:

    @pytest.mark.parametrize('etiket,yol,yuk,alan', BANT_YAYIMLAYAN_UCLAR,
                             ids=[u[0] for u in BANT_YAYIMLAYAN_UCLAR])
    def test_uc_kanonik_adi_yayimlar(self, istemci, etiket, yol, yuk, alan):
        kod, govde = _post(istemci, yol, yuk)
        assert kod in (400, 422), (etiket, kod, govde)
        kayit = [k for k in (govde.get('invalid_fields') or [])
                 if isinstance(k, dict) and k.get('field') == alan]
        assert kayit, (etiket, govde)
        adlar = _bant_adlari(kayit[0])
        assert adlar == {KANON}, (
            '%s bandı kanondan başka adla yayımlıyor: %r' % (etiket, adlar))

    def test_alti_dof_ile_2b_kardesi_ARTIK_ayni_adi_kullaniyor(self,
                                                               istemci):
        """Kalemin TAM METNİ bu iki ucun ayrışmasıydı — tek testte kilit."""
        _, alti = _post(istemci, '/api/six-dof-analysis',
                        {'mass': 10, 'thrust': 1000, 'burn_time': 10,
                         'cd0': 1e9})
        _, hib = _post(istemci, '/calculate', dict(HIBRIT, burn_time=1e9))
        a = [k for k in (alti.get('invalid_fields') or [])
             if k.get('field') == 'cd0']
        h = [k for k in (hib.get('invalid_fields') or [])
             if isinstance(k, dict) and k.get('field') == 'burn_time']
        assert a and h, (alti, hib)
        assert _bant_adlari(a[0]) == _bant_adlari(h[0]) == {KANON}

    def test_dolasimdaki_benzersiz_bant_adi_TEK(self, istemci):
        """K3'ün kapanışı: ölçümde 3 olan küme 1'e iner.

        ``_m`` birim varyantı ayrı ölçülür (aşağıdaki testte), çünkü o
        kaydın bandı metre, tepe değeri milimetredir."""
        kume = set()
        for etiket, yol, yuk, _alan in BANT_YAYIMLAYAN_UCLAR:
            _kod, govde = _post(istemci, yol, yuk)
            for kayit in (govde.get('invalid_fields') or []):
                if isinstance(kayit, dict):
                    kume |= _bant_adlari(kayit)
        assert kume == {KANON}, (
            'aynı kavram hâlâ birden çok adla dolaşıyor: %r' % sorted(kume))

    def test_turetilen_geometri_kaydi_kanonun_birim_kardesini_kullanir(
            self, istemci):
        kod, govde = _post(istemci, '/api/regression-analysis',
                           {'motor_data': dict(P16_TABAN, regression_a=1e9)})
        assert kod == 422, govde
        assert govde['error'] == 'regression_geometry_out_of_range'
        kayit = govde['invalid_fields'][0]
        assert _bant_adlari(kayit) == {KANON + '_m'}, kayit
        assert ESKI + '_m' not in kayit


# ---------------------------------------------------------------------------
# 3. SAYI DEĞİŞMEDİ — bu bir AD onarımıdır, bant onarımı değil
# ---------------------------------------------------------------------------
class TestOHD2523SayilarBitAyni:
    """Ad çevrildi; yayımlanan SAYILAR deponun kanonik tablosundan gelmeye

    devam ediyor. Bu bekçi, "adı düzeltirken bandı da oynattık" kazasını
    yakalar (D26 dersi 8: tolerans/tavan BÜYÜTÜLMEZ)."""

    def test_alti_dof_bandi_hala_cozucu_tablosundan(self, istemci):
        from hrma.validation.motor_validation import motor_validator
        _, govde = _post(istemci, '/api/six-dof-analysis',
                         {'mass': 10, 'thrust': 1000, 'burn_time': 10,
                          'cd0': 1e9})
        kayit = [k for k in govde['invalid_fields']
                 if k.get('field') == 'cd0'][0]
        assert kayit[KANON][0] == 0.0
        assert kayit[KANON][1] > 0

    def test_regresyon_bandi_hala_kanonik_tablodan(self, istemci):
        from hrma.validation.motor_validation import motor_validator
        ust = float(motor_validator.limits['burn_time']['max'])
        _, govde = _post(istemci, '/api/regression-analysis',
                         {'motor_data': dict(P16_TABAN, burn_time=1e9)})
        kayit = [k for k in govde['invalid_fields']
                 if k['field'] == 'burn_time'][0]
        assert kayit[KANON][1] == pytest.approx(ust)

    def test_turetilen_geometri_bandi_hala_kanonik_tablodan(self, istemci):
        from hrma.validation.motor_validation import motor_validator
        bant = motor_validator.limits['port_diameter']
        _, govde = _post(istemci, '/api/regression-analysis',
                         {'motor_data': dict(P16_TABAN, regression_a=1e9)})
        kayit = govde['invalid_fields'][0]
        assert kayit[KANON + '_m'] == [float(bant['min']),
                                       float(bant['max'])]

    def test_saglikli_govdeler_BIT_AYNI_kalir(self, istemci):
        """Kapı değişmedi: bandın İÇİ hâlâ 200."""
        assert _post(istemci, '/api/regression-analysis',
                     {'motor_data': dict(P16_TABAN)})[0] == 200
        assert _post(istemci, '/calculate', dict(HIBRIT))[0] == 200


# ---------------------------------------------------------------------------
# 4. İÇ TÜKETİCİ — ``_ust_sinir_ihlalleri`` kanonu okur
# ---------------------------------------------------------------------------
class TestOHD2523IcTuketici:
    """D26'da onarımı ENGELLEYEN yol tam olarak buydu: paylaşımlı kapının

    çıktısı ``_ust_sinir_ihlalleri`` üzerinden ``/api/regression-analysis``e
    ve üç ``/analyze_*`` ucuna gidiyor. Üretici ile tüketici AYNI commit'te
    çevrilmezse burası ``KeyError`` verir."""

    def test_ust_sinir_suzgeci_kanonik_anahtari_okur(self):
        from hrma.app import _ust_sinir_ihlalleri
        kayitlar = _ust_sinir_ihlalleri({'chamber_pressure': 1e9},
                                        ('chamber_pressure',))
        assert kayitlar, 'üst sınır süzgeci ihlali göremedi'
        assert KANON in kayitlar[0], kayitlar[0]
        assert ESKI not in kayitlar[0]

    def test_paylasimli_kapi_ve_suzgeci_ayni_anahtarda_bulusur(self):
        """Üretici ile tüketicinin ad sözleşmesi TEK yerde tutulur."""
        from hrma.app import _collect_unphysical_fields, _ust_sinir_ihlalleri
        ham = _collect_unphysical_fields({'a': 7.0}, ranges={'a': (0.0, 5.0)})
        assert _bant_adlari(ham[0]) == {KANON}
        suzulmus = _ust_sinir_ihlalleri({'chamber_pressure': 1e9},
                                        ('chamber_pressure',))
        assert _bant_adlari(suzulmus[0]) == _bant_adlari(ham[0])

    def test_cozulen_geometri_kunyesi_de_kanonda(self):
        from hrma.app import _cozulen_geometri_ihlali
        from hrma.validation.motor_validation import motor_validator
        ust = float(motor_validator.limits['chamber_diameter']['max'])
        kayit = _cozulen_geometri_ihlali({'chamber_diameter': ust * 1e3})
        assert kayit, 'türetilmiş geometri kapısı ihlali göremedi'
        assert _bant_adlari(kayit) == {KANON}
        assert kayit['derived'] is True


# ---------------------------------------------------------------------------
# 5. TÜKETİCİ BEDELİ — "iki anahtarı da dene" hoşgörüsü kalktı
# ---------------------------------------------------------------------------
class TestOHD2523HosgoruKalkti:
    """K4'ün kapanışı. Hoşgörü kalırsa ayrışma geri geldiğinde SESSİZ

    kalırdı — kusurun kendisi zaten tüketiciye yüklenen bu bedeldi."""

    def test_testlerde_iki_anahtar_hosgorusu_kalmadi(self):
        """Tarama YALNIZ CANLI KOD üstünde: yorumlar ve dizeler (docstring)

        ayıklanır. Gerekçe: bu dosyanın kendi künyesi kusuru ADIYLA
        anlatıyor (ölçümün metni), o bir tüketici değildir — metni
        saymak ölçümü kendi kendine kırmızı yapardı."""
        bulgu = []
        for dosya in sorted((KOK / 'tests').glob('*.py')):
            satirlar = _canli_kod_satirlari(dosya)
            for i, satir in enumerate(satirlar):
                if "'%s'" % ESKI not in satir:
                    continue
                pencere = ' '.join(satirlar[max(0, i - 1):i + 2])
                if KANON in pencere and ' or ' in pencere:
                    bulgu.append('%s:%d' % (dosya.name, i + 1))
        assert bulgu == [], (
            'tüketici hâlâ iki anahtarı da deniyor: %r' % bulgu)

    def test_urun_yuzunde_eski_adin_tuketicisi_yok(self):
        """Ölçülmüştü (K4): 0. Bir gün arayüz eski adı okumaya başlarsa

        bu bekçi kırmızı olur — ad ayrışması ürün yüzünden geri giremez."""
        sayi = 0
        for dizin in ('hrma/templates', 'hrma/static', 'electron'):
            yol = KOK / dizin
            if not yol.exists():
                continue
            for dosya in yol.rglob('*'):
                if dosya.is_file() and dosya.suffix in ('.html', '.js',
                                                        '.css', '.json'):
                    sayi += dosya.read_text(encoding='utf-8',
                                            errors='ignore').count(ESKI)
        assert sayi == 0, 'ürün yüzü eski bant adını okuyor (%d geçiş)' % sayi
