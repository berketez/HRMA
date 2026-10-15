"""OH-D31-10 — TEK KURAL, TEK GEREKÇE KODU (ÖH D32 fix-35d).

Bu dosya, ana modelin 15 Eylül 2026 hükmünü koda bağlar. Hüküm, ölçülmüş
bir ayrışmayı kapatır (``docs/scofield/raw/OH/D32/fix35/d/once_dort_uc.json``,
taban ``dd1dcddc``): AYNI istemci hatası, dört uç, farklı makine-okur ad.

ÖLÇÜLEN ÖNCE (taban ``dd1dcddc``)::

    uç                        '20.0' (dize)        NaN / inf        True
    /calculate                not_a_number         not_finite       not_a_number
    /calculate_liquid         not_a_json_number    out_of_range     boolean_is_...
    /calculate_solid          not_a_json_number    out_of_range     boolean_is_...
    /api/oxidizer-properties  HTTP 200 (!)         not_a_finite_..  not_a_finite_..

Yani ``reason`` üzerinden dallanan bir tüketici, TEK kural için üç ayrı kod
görüyordu; dahası bir uç tel biçimini hiç reddetmiyor, sayı üretiyordu.

KANON (hüküm)::

    bool                                  -> boolean_is_not_a_number
    JSON sayısı OLMAYAN değer             -> not_a_json_number
      (sayı-benzeri dize, liste, sözlük; tek kaynak
       ``hrma.utils.input_guard.is_json_number``)
    JSON sayısı AMA sonlu değil (NaN/inf) -> not_finite
    sonlu sayı, bandın dışında            -> out_of_range

``not_a_number`` bu ailede EMEKLİDİR.

KAPSAM DIŞI DEĞİL ARTIK — BİRLEŞTİ (ÖH D33-2 / app-api-uc a1, OH-D32-15):
``input_guard`` ``InputError`` ailesinin kendi adı ``not_a_finite_number``
idi ve depoda 6 uçta yayımlanıyordu; ``bool``, çevrilemez metin, ``NaN`` ve
``inf`` için AYNI TEK kodu basıyordu (ölçüm:
``docs/scofield/raw/OH/D33-2/app-api-uc/a1/once_gerekce_kanonu.json`` K3).
Altı uç da yukarıdaki kanona çevrildi; türetim tek kaynaktan yapılır
(``hrma/app.py::_kanonik_gerekce``). ``not_a_finite_number`` ve bileşik adı
``not_a_finite_number_or_out_of_range`` bu ailede EMEKLİDİR.

Düğüm adları bilerek ASCII'dir (ÖH D32 fix-35e dersi: Türkçe harfli test
adı iki envanter bekçisini yakar).
"""

import contextlib
import io

import pytest

from hrma.utils import input_guard


BOOLEAN = 'boolean_is_not_a_number'
TEL_BICIMI = 'not_a_json_number'
SONLU_DEGIL = 'not_finite'

#: Hibrit uç gövdesi — ``/calculate``.
HIBRIT = {'motor_type': 'hybrid', 'thrust': 1000, 'burn_time': 10,
          'of_ratio': 2.5, 'chamber_pressure': 20.0,
          'fuel_type': 'htpb', 'oxidizer_type': 'n2o'}
#: Sıvı uç gövdesi — ``/calculate_liquid``.
SIVI = {'thrust': 25000, 'chamber_pressure': 70, 'mixture_ratio': 2.5,
        'fuel_type': 'rp1', 'oxidizer_type': 'lox'}
#: Katı uç gövdesi — ``/calculate_solid``.
KATI = {'motor_name': 'S', 'propellant_type': 'apcp', 'grain_type': 'bates',
        'chamber_pressure': 40.0, 'thrust': 5000.0, 'burn_time': 3.0,
        'chamber_diameter': 100.0, 'grain_length': 500.0,
        'core_diameter': 30.0, 'expansion_ratio': 8.0}

UCLAR = (
    ('/calculate', HIBRIT, 'chamber_pressure'),
    ('/calculate_liquid', SIVI, 'chamber_pressure'),
    ('/calculate_solid', KATI, 'chamber_pressure'),
)


@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _gerekce(istemci, yol, govde):
    """(http, ilgili alanın reason kodu) — sessiz koşum.

    ROTA LİTERALİ BİLEREK AÇIK YAZILIDIR (ÖH D24 / OH-D23-12): uç envanteri
    testlerdeki ``.post()`` çağrılarını AST ile tarar ve rota bir
    DEĞİŞKENDEN geliyorsa çağrıyı göremez. Sözleşmesi yalnız testte yazılı
    bir uç böylece envantere hiç girmez (fail-open). Bu bekçi tam da üç
    ``/calculate*`` ucunun ret sözleşmesini kilitlediği için envanterde
    görünmesi gerekir; ``çözülemeyen rota çağrısı`` tavanı da
    büyütülmemelidir.
    """
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        if yol == '/calculate':
            yanit = istemci.post('/calculate', json=govde)
        elif yol == '/calculate_liquid':
            yanit = istemci.post('/calculate_liquid', json=govde)
        elif yol == '/calculate_solid':
            yanit = istemci.post('/calculate_solid', json=govde)
        else:
            raise AssertionError('bilinmeyen uc: %r' % (yol,))
    g = yanit.get_json() or {}
    kayitlar = [k for k in (g.get('invalid_fields') or [])
                if isinstance(k, dict)]
    return yanit.status_code, [k.get('reason') for k in kayitlar]


@pytest.mark.parametrize('yol,temel,alan', UCLAR)
@pytest.mark.parametrize('deger', ['20.0', 'abc', [1, 2]])
def test_wire_form_rejected_with_one_code(istemci, yol, temel, alan, deger):
    """JSON sayisi olmayan deger: uc ucta da AYNI ad."""
    http, kodlar = _gerekce(istemci, yol, dict(temel, **{alan: deger}))
    assert http == 400, (yol, deger, http)
    assert TEL_BICIMI in kodlar, (yol, deger, kodlar)


@pytest.mark.parametrize('yol,temel,alan', UCLAR)
def test_boolean_rejected_with_its_own_code(istemci, yol, temel, alan):
    """``True`` sayisal alanda kendi adiyla duser (float(True) == 1.0)."""
    http, kodlar = _gerekce(istemci, yol, dict(temel, **{alan: True}))
    assert http == 400, (yol, http)
    assert BOOLEAN in kodlar, (yol, kodlar)


@pytest.mark.parametrize('yol,temel,alan', UCLAR)
@pytest.mark.parametrize('deger', [float('nan'), float('inf')])
def test_non_finite_number_is_not_out_of_range(istemci, yol, temel, alan,
                                               deger):
    """NaN bir bandin DISINDA degildir; hicbir bantla karsilastirilamaz.

    Bu dugum, ``app.py::_form_band_kapisi``nin iki AYRI ret sebebini tek ada
    (``out_of_range``) toplamasini kapatir: kullaniciya "5-200 arasi bir sayi
    girin" demek NaN icin yanlis yonlendirmedir.
    """
    http, kodlar = _gerekce(istemci, yol, dict(temel, **{alan: deger}))
    assert http == 400, (yol, deger, http)
    assert SONLU_DEGIL in kodlar, (yol, deger, kodlar)
    assert 'out_of_range' not in kodlar, (yol, deger, kodlar)


def test_retired_code_is_not_published_by_the_shared_gate(istemci):
    """``not_a_number`` bu ailede EMEKLI: hicbir uc onu yayimlamaz."""
    gorulen = []
    for yol, temel, alan in UCLAR:
        for deger in ('20.0', 'abc', [1, 2], True, float('nan'),
                      float('inf')):
            _http, kodlar = _gerekce(istemci, yol,
                                     dict(temel, **{alan: deger}))
            if 'not_a_number' in kodlar:
                gorulen.append((yol, repr(deger)))
    assert not gorulen, (
        'emekli ad geri geldi: %s' % gorulen)


@pytest.mark.parametrize('deger,beklenen', [
    ('293.15', TEL_BICIMI),
    ('yirmi', TEL_BICIMI),
    (True, BOOLEAN),
])
def test_oxidizer_properties_rejects_wire_form(istemci, deger, beklenen):
    """Kardes dorduncu uc: tel bicimi ARTIK sayi uretmiyor (fail-closed).

    OLCULDU (``once_dort_uc.json``): ``temperature: '293.15'`` bu ucta HTTP
    **200** + yogunluk doner, kardes uc uc ayni tel bicimini reddederdi.
    """
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        yanit = istemci.post('/api/oxidizer-properties',
                             json={'oxidizer_type': 'n2o',
                                   'temperature': deger})
    assert yanit.status_code == 400, (deger, yanit.status_code)
    g = yanit.get_json() or {}
    kayit = (g.get('invalid_fields') or [{}])[0]
    assert kayit.get('field') == 'temperature', kayit
    assert kayit.get('reason') == beklenen, kayit


def test_oxidizer_properties_absent_temperature_is_bit_identical(istemci):
    """Kapi DAR: durum sorulmadiysa referans durumu mesrudur (bit-ayni)."""
    for govde in ({'oxidizer_type': 'lox'},
                  {'oxidizer_type': 'lox', 'temperature': None},
                  {'oxidizer_type': 'lox', 'temperature': ''}):
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            yanit = istemci.post('/api/oxidizer-properties', json=govde)
        assert yanit.status_code == 200, (govde, yanit.status_code)


def test_canonical_name_has_exactly_one_source():
    """Tel bicimi sorusunun yaniti TEK yerde yazilir (Doktrin 4)."""
    assert input_guard.is_json_number(20.0) is True
    assert input_guard.is_json_number('20.0') is False
    # ``bool``u is_json_number DA reddeder (numpy.bool_ deligi dahil);
    # kapilar yine de bool kolunu ONCE calistirir, cunku kullanicinin
    # yapmasi gereken farklidir ve ad ayri olmali.
    assert input_guard.is_json_number(True) is False
    assert input_guard.finite_number('20.0') == 20.0, (
        'finite_number AYRI bir soruyu yanitlar (okunabilir mi); iki soru '
        'karistirilirsa kanon yeniden ayrisir')
