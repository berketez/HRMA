"""ÖH Dalga-17 · sıvı kulvarı a1 — mutasyon kanıtlı bekçiler.

Kapsanan kalemler (ölçüm: ``docs/scofield/raw/OH/D17/sivi/a1/once.json`` ⟷
``sonra.json``, betik ``olcum.py``):

* **P3B1-11** — yerleşik itici tablosu araması harf/boşluk duyarlıydı:
  ``('METHANE','LOX')`` tabloda bulunamayıp "tablo dışı çift" dalına
  düşüyordu (``propellant_name`` 'METHANE/LOX', performans referansı
  başka zincirden).
* **P3B1-12** — ``injector_type`` girdi kapısı YOKTU: 'banana' HTTP 200
  alıp yanıtta yayımlanıyordu (kardeş alan ``cooling_type`` 422 veriyor).
* **P3B2-06** — aynı manifolda iki çap: beyansız 2,5×d_eş kaba kuralı
  ⟷ devre modelinin çözdüğü ``manifold.d_mm``.
* **P3B3-06 (Fable-D15 ŞART) / OH-D16-08** — ``TANK_CRYO_SUITABLE_MATERIALS``
  elle yazılmış ikinci listeydi ve ``materials_db.DBTT_SENSITIVE`` ile
  çelişiyordu ('ss_17_4ph' hem duyarlı hem "uygun").
* **OH-D16-05** — ``discharge_coefficient`` alanına iki uçta iki sözleşme:
  ``/calculate`` 422 ile reddederken ``/calculate_liquid`` 200 veriyordu.
* **P6B4-01** — chug çevrimi İSTENEN L*'ı tüketiyordu; τ_c üç farklı
  itkide bit-aynı çıkıyordu.
"""

import contextlib
import io
import json
import math
import os
import tempfile

import pytest

from hrma.data import materials_db
from hrma.engines.injector_design import USER_CD_RANGE
from hrma.engines.liquid_rocket_engine import (
    COOLING_TYPES_RECOGNISED,
    INJECTOR_TYPES_RECOGNISED,
    INJECTOR_TYPE_CIRCUIT_MODEL,
    INJECTOR_TYPE_DP_FRACTION,
    LIQUID_PROPELLANT_REFERENCE_TABLE,
    LiquidRocketEngine,
    TANK_CRYO_NOT_DBTT_EXCLUDED,
    TANK_CRYO_SCREENING_BASIS,
    TANK_CRYO_SUITABLE_MATERIALS,
)
from tests.support.kanit import kanit_gerekli

TABAN_YUK = {
    'motor_name': 'D17-SIVI', 'thrust': 25000.0, 'burn_time': 30.0,
    'chamber_pressure': 60.0, 'mixture_ratio': 2.2,
    'fuel_type': 'rp1', 'oxidizer_type': 'lox', 'expansion_ratio': 12.0,
}


@pytest.fixture(scope='module')
def istemci():
    os.environ.setdefault('HRMA_USER_DATA_DIR',
                          tempfile.mkdtemp(prefix='hrma-d17-sivi-'))
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _cagir(istemci, yol, yuk):
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        r = istemci.post(yol, json=yuk)
    try:
        j = r.get_json()
    except Exception:                                   # pragma: no cover
        j = None
    return r.status_code, (j if isinstance(j, dict) else {})


def _motor(**kw):
    ayar = dict(thrust=25000.0, chamber_pressure=60.0, mixture_ratio=2.2,
                fuel_type='rp1', oxidizer_type='lox')
    ayar.update(kw)
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        return LiquidRocketEngine(**ayar)


def _iz(d, *yol):
    for k in yol:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


# =====================================================================
# P3B1-11 — tablo araması harf/boşluk duyarlı olamaz
# ÖLÇÜLDÜ: ('methane','lox') tabloda VAR, ('METHANE','LOX') YOK; büyük
# harfli istek propellant_name 'METHANE/LOX' ile tablo dışı dala düşüyordu.
# =====================================================================
@pytest.mark.parametrize('f_ham,o_ham', [
    ('METHANE', 'LOX'), ('Methane', 'Lox'), ('  methane  ', ' lox '),
    ('RP1', 'LOX'), ('rp1', 'LOX'),
])
def test_p3b1_11_itici_adi_kanonik_saklanir(f_ham, o_ham):
    """Motorun sakladığı ad kanoniktir; tablo anahtarı ıskalanamaz."""
    e = _motor(fuel_type=f_ham, oxidizer_type=o_ham)
    assert e.fuel_type == f_ham.strip().lower()
    assert e.oxidizer_type == o_ham.strip().lower()
    # Kanonik ikili tabloda bulunmalı (bu çiftlerin hepsi tablo kaydı).
    assert (e.fuel_type, e.oxidizer_type) in LIQUID_PROPELLANT_REFERENCE_TABLE


def test_p3b1_11_buyuk_harf_tablo_dalini_iskalayamaz():
    """Aynı fiziksel çift, iki yazım biçimi, TEK sonuç."""
    kucuk = _motor(fuel_type='methane', oxidizer_type='lox')
    buyuk = _motor(fuel_type='METHANE', oxidizer_type='LOX')
    assert buyuk.propellant_name == kucuk.propellant_name, (
        'büyük harfli istek tablo kaydını ıskalayıp ayrı bir isim üretti: '
        f'{buyuk.propellant_name!r} != {kucuk.propellant_name!r}')
    assert float(buyuk.rho_fuel) == pytest.approx(float(kucuk.rho_fuel),
                                                  rel=1e-12)
    assert getattr(buyuk, 'combustion_data_source', None) == \
        getattr(kucuk, 'combustion_data_source', None)


def test_p3b1_11_kanoniklestirme_dize_olmayani_bozmaz():
    """Kapı uçtadır: dize olmayan/boş değer DEĞİŞTİRİLMEDEN geçer."""
    assert LiquidRocketEngine._canonical_propellant_key(None) is None
    assert LiquidRocketEngine._canonical_propellant_key(7) == 7
    assert LiquidRocketEngine._canonical_propellant_key('   ') == '   '


# =====================================================================
# P3B1-12 — injector_type girdi kapısı
# ÖLÇÜLDÜ: injector_type='banana' -> HTTP 200, yanıtta yayımlanıyor.
# =====================================================================
def test_p3b1_12_taninmayan_enjektor_tipi_reddedilir(istemci):
    st, j = _cagir(istemci, '/calculate_liquid',
                   dict(TABAN_YUK, injector_type='banana'))
    assert st == 422, f'tanınmayan enjektör tipi HTTP {st} aldı'
    alanlar = j.get('invalid_fields') or []
    assert any(a.get('field') == 'injector_type' for a in alanlar), (
        'red ADLI değil: invalid_fields içinde injector_type yok')
    hedef = next(a for a in alanlar if a.get('field') == 'injector_type')
    assert hedef.get('value') == 'banana'
    assert list(hedef.get('allowed_values') or []) == \
        list(INJECTOR_TYPES_RECOGNISED)


@pytest.mark.parametrize('tip', list(INJECTOR_TYPES_RECOGNISED))
def test_p3b1_12_taninan_tipler_gecer(istemci, tip):
    st, _ = _cagir(istemci, '/calculate_liquid',
                   dict(TABAN_YUK, injector_type=tip))
    assert st == 200, f'tanınan enjektör tipi {tip!r} reddedildi ({st})'


@pytest.mark.parametrize('bos', [None, ''])
def test_p3b1_12_gonderilmeyen_alan_kapiyi_tetiklemez(istemci, bos):
    st, _ = _cagir(istemci, '/calculate_liquid',
                   dict(TABAN_YUK, injector_type=bos))
    assert st == 200


def test_p3b1_12_beyaz_liste_ikinci_kez_yazilmamis():
    """Küme TÜRETİLİR: ΔP/Pc tablosuyla ayrışamaz (tek kaynak)."""
    assert INJECTOR_TYPES_RECOGNISED == tuple(INJECTOR_TYPE_CIRCUIT_MODEL)
    # Kardeş alanın deseniyle aynı: cooling_type de tablodan türetiliyor.
    assert len(COOLING_TYPES_RECOGNISED) >= 5
    # ΔP/Pc tablosu AYRI bir tablodur (dört tip); kapı ONU değil devre
    # modelinin yönlendirme tablosunu okur — iki tablo karıştırılmaz.
    assert set(INJECTOR_TYPE_DP_FRACTION) <= set(INJECTOR_TYPE_CIRCUIT_MODEL)


def test_p3b1_12_form_secenekleri_kapidan_gecer():
    """Kapı ÜRÜNÜ KIRMAMALI: liquid.html'in sunduğu her seçenek tanınır."""
    import os
    import re as _re
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    yol = os.path.join(kok, 'hrma', 'templates', 'liquid.html')
    with open(yol, encoding='utf-8') as fh:
        metin = fh.read()
    blok = _re.search(r'<select id="injector_type">(.*?)</select>', metin,
                      _re.S)
    assert blok, 'liquid.html injector_type seçicisi bulunamadı'
    secenekler = _re.findall(r'<option value="([^"]+)"', blok.group(1))
    assert secenekler, 'seçici boş'
    eksik = [s for s in secenekler if s not in INJECTOR_TYPES_RECOGNISED]
    assert eksik == [], (
        f'form şu seçenekleri sunuyor ama uç kapısı reddediyor: {eksik}')


# =====================================================================
# P3B2-06 — aynı manifolda TEK çap
# ÖLÇÜLDÜ (25 kN/60 bar): rapor 24,93 / 34,00 mm (2,5×d_eş kaba kuralı)
# ⟷ devre modeli 31,54 / 43,00 mm.
# =====================================================================
def test_p3b2_06_manifold_capi_modul_cozumunun_kendisidir(istemci):
    st, j = _cagir(istemci, '/calculate_liquid', TABAN_YUK)
    assert st == 200
    r = j.get('results') or j
    kaba = _iz(r, 'injector_design') or {}
    detay = _iz(r, 'injection_system', 'injector_design_detail') or {}
    assert detay.get('status') == 'success', 'devre modeli çözmedi'
    ciftler = [('fuel_manifold_diameter_mm', 'fuel_circuit'),
               ('oxidizer_manifold_diameter_mm', 'ox_circuit')]
    for anahtar, devre in ciftler:
        modul = _iz(detay, devre, 'manifold', 'd_mm')
        assert isinstance(modul, (int, float))
        assert anahtar in kaba, f'{anahtar} yayımlanmadı'
        assert float(kaba[anahtar]) == pytest.approx(float(modul), rel=1e-9), (
            f'{anahtar}: rapor {kaba[anahtar]} ⟷ modül {modul} — aynı '
            'manifold için iki çap')
    assert 'injector circuit model' in str(kaba.get('manifold_diameter_basis'))


def test_p3b2_06_kaba_kural_kodda_kalmadi():
    """2,5×d_eş + 10/12 mm taban kuralı motordan KALKMIŞ olmalı."""
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    yol = os.path.join(kok, 'hrma', 'engines', 'liquid_rocket_engine.py')
    with open(yol, encoding='utf-8') as fh:
        metin = fh.read()
    for desen in ("max(10.0, np.sqrt(injector['fuel_injection_area']",
                  "max(12.0, np.sqrt(injector['ox_injection_area']"):
        assert desen not in metin, f'kaba kural hâlâ kodda: {desen}'


def test_p3b2_06_modul_cozmezse_sayi_uydurulmaz():
    """Fail-closed: çözüm yoksa çap YAYIMLANMAZ, künye nedenini söyler."""
    e = _motor()
    blok = e._manifold_diameter_report({'injector_design_detail':
                                        {'status': 'failed'}})
    assert 'fuel_manifold_diameter_mm' not in blok
    assert 'oxidizer_manifold_diameter_mm' not in blok
    assert 'NOT PUBLISHED' in blok['manifold_diameter_basis']


# =====================================================================
# P3B3-06 (Fable-D15 ŞART) + OH-D16-08 — kriyojenik tarama TEK KAYNAK
# ÖLÇÜLDÜ: 'ss_17_4ph' elle yazılmış kümede "uygun", materials_db'de
# DBTT-duyarlı — aynı depoda iki karşıt güvenlik hükmü.
# =====================================================================
def test_p3b3_06_kume_materials_db_ile_celismez():
    celisen = sorted(ad for ad in TANK_CRYO_NOT_DBTT_EXCLUDED
                     if materials_db.is_dbtt_sensitive(ad) is not False)
    assert celisen == [], (
        f'kriyojenik küme materials_db ile çelişiyor: {celisen}')


def test_p3b3_06_eski_ad_ayni_nesne():
    """D15 bekçilerinin ithal ettiği ad korunur (tek küme, iki ad)."""
    assert TANK_CRYO_SUITABLE_MATERIALS is TANK_CRYO_NOT_DBTT_EXCLUDED


def test_p3b3_06_17_4ph_lh2_tanki_fail_alir():
    """Fable ŞART'ının istediği vaka: martenzitik çelik LH2 tankı geçemez."""
    e = _motor(fuel_type='lh2', mixture_ratio=6.0, chamber_pressure=200)
    tar = e._tank_cryo_screening('ss_17_4ph', 'lh2', 'fuel_tank')
    assert tar['verdict'] == 'fail', (
        "17-4PH martenzitik çeliktir; materials_db onu DBTT-duyarlı sayar "
        "ama kriyojenik tank taraması 'pass' veriyordu")
    kodlar = {w['code'] for w in e.design_warnings}
    assert 'warn.liquid.tank_material_not_cryogenic' in kodlar


@pytest.mark.parametrize('mal,beklenen', [
    ('ss_316', 'pass'), ('aluminum_6061', 'pass'), ('inconel_718', 'pass'),
    ('ss_17_4ph', 'fail'), ('steel', 'fail'), ('steel_4340', 'fail'),
    ('niobium_c103', 'fail'), ('molybdenum_tzm', 'fail'),
])
def test_p3b3_06_hukum_dbtt_tek_kaynagindan_gelir(mal, beklenen):
    e = _motor(fuel_type='lh2', mixture_ratio=6.0)
    assert e._tank_cryo_screening(mal, 'lh2', 'fuel_tank')['verdict'] == \
        beklenen


def test_p3b3_06_taninmayan_malzeme_fail_closed():
    """Ad çözülemiyorsa hüküm KAZANILMAMIŞTIR: 'pass' da 'fail' da uydurma."""
    e = _motor(fuel_type='lh2', mixture_ratio=6.0)
    tar = e._tank_cryo_screening('unobtanium_x9', 'lh2', 'fuel_tank')
    assert tar['verdict'] == 'unresolved'
    assert 'not a materials_db record' in tar['basis']
    kodlar = {w['code'] for w in e.design_warnings}
    assert 'warn.liquid.tank_material_not_cryogenic' in kodlar


def test_p3b3_06_kunye_ti_alasimlarini_fcc_diye_anmaz():
    """Ti-6Al-4V ve Ti Grade-2 HMK/YMK değil HSP'dir (Fable ŞART)."""
    assert 'face-centred-cubic set' not in TANK_CRYO_SCREENING_BASIS
    assert 'hexagonal close-packed' in TANK_CRYO_SCREENING_BASIS
    assert 'is_dbtt_sensitive' in TANK_CRYO_SCREENING_BASIS


# =====================================================================
# OH-D16-05 — aynı alana iki sözleşme olamaz
# ÖLÇÜLDÜ: Cd = 1,05 / -0,3 / 0 / 'abc' -> /calculate 422 (4/4),
# /calculate_liquid 200 (4/4).
# =====================================================================
@pytest.mark.parametrize('cd', [1.05, -0.3, 0.0, 'abc', 2.0, float('nan')])
def test_ohd1605_bant_disi_cd_iki_ucta_da_reddedilir(istemci, cd):
    yuk_l = dict(TABAN_YUK, discharge_coefficient=cd)
    st_l, j_l = _cagir(istemci, '/calculate_liquid', yuk_l)
    assert st_l == 422, f'/calculate_liquid Cd={cd!r} için HTTP {st_l}'
    alanlar = j_l.get('invalid_fields') or []
    assert any(a.get('field') == 'discharge_coefficient' for a in alanlar), (
        'red ADLI değil')
    st_h, _ = _cagir(istemci, '/calculate', {
        'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
        'chamber_pressure': 20.0, 'fuel_type': 'htpb',
        'oxidizer_type': 'n2o', 'discharge_coefficient': cd})
    assert st_h == st_l, (
        f'aynı alan iki uçta iki sözleşme: /calculate {st_h} ⟷ '
        f'/calculate_liquid {st_l}')


@pytest.mark.parametrize('cd', [USER_CD_RANGE[0], 0.75, USER_CD_RANGE[1]])
def test_ohd1605_bant_ici_cd_gecer(istemci, cd):
    st, _ = _cagir(istemci, '/calculate_liquid',
                   dict(TABAN_YUK, discharge_coefficient=cd))
    assert st == 200, f'bant içi Cd={cd} reddedildi ({st})'


@pytest.mark.parametrize('bos', [None, ''])
def test_ohd1605_gonderilmeyen_cd_kapiyi_tetiklemez(istemci, bos):
    st, _ = _cagir(istemci, '/calculate_liquid',
                   dict(TABAN_YUK, discharge_coefficient=bos))
    assert st == 200


def test_ohd1605_bant_ikinci_kez_yazilmamis(istemci):
    """Red gövdesindeki bant, deponun TEK Cd tanımından gelmeli."""
    _, j = _cagir(istemci, '/calculate_liquid',
                  dict(TABAN_YUK, discharge_coefficient=1.05))
    hedef = next(a for a in j['invalid_fields']
                 if a['field'] == 'discharge_coefficient')
    assert (hedef['min'], hedef['max']) == tuple(USER_CD_RANGE)


# =====================================================================
# P6B4-01 — chug çevrimi ÇİZİLEN L*'ı tüketir
# ÖLÇÜLDÜ: τ_c 25 kN / 250 kN / 1 MN üç koşuda bit-aynı 0,001596822 s;
# çizilen L* 1,200 / 3,472 / 5,743 m (+%189, +%379).
# =====================================================================
@pytest.mark.parametrize('itki', [25000.0, 250000.0, 1000000.0])
def test_p6b401_chug_cizilen_l_stari_tuketir(istemci, itki):
    st, j = _cagir(istemci, '/calculate_liquid',
                   dict(TABAN_YUK, thrust=itki))
    assert st == 200
    r = j.get('results') or j
    cizilen = _iz(r, 'cooling_system', 'l_star')
    dongu = _iz(r, 'combustion_analysis', 'stability_analysis',
                'chug_loop') or {}
    kullanilan = _iz(dongu, 'chamber_time_constant', 'l_star_m')
    assert isinstance(cizilen, (int, float))
    assert isinstance(kullanilan, (int, float)), 'chug çevrimi koşmadı'
    assert float(kullanilan) == pytest.approx(float(cizilen), rel=1e-9), (
        f'{itki:g} N: chug τ_c {kullanilan} m L* ile kuruldu, hazne '
        f'{cizilen} m çiziyor')


def test_p6b401_tau_c_itkiyle_degisir(istemci):
    """τ_c ÇİZİLEN L*'ı tüketmeli — ama L* artık itkiyle BÜYÜMÜYOR.

    ÖH D18 fizik-a2 (F2 ≡ OH-D15-01) ÇEVİRİSİ. Bu bekçi "τ_c üç itkide
    bit-aynı OLAMAZ" diyordu ve gerekçesi "hazne büyüdükçe kalış süresi
    artar" idi. O gerekçe, D15'in ``l_star_unreachable`` KAÇIŞ YOLUNA
    dayanıyordu: sabit ε_c = 12,25 ile koni taban L*'ı yutuyor, yayımlanan
    L* motor büyüdükçe şişiyordu (25 kN 1,200 m → 250 kN 3,472 m → 1 MN
    5,743 m). Yani test, kusurun YAN ÜRÜNÜNÜ "doğru davranış" diye
    kilitliyordu — L* bir TASARIM GİRDİSİDİR, itkinin fonksiyonu değil
    (Huzel & Huang SP-125 Tablo 4-1 itici çiftine göre verir, itkiye göre
    değil).

    D18/F2 sonrası ε_c boğaz çapından geliyor, kaçış yolu hiç ateşlemiyor
    ve aynı itici çiftinde üç itkide de L* AYNI — dolayısıyla τ_c de aynı.
    Kalemin GERÇEK iddiası (τ_c çizilen L*'ı tüketir, istenen değil) zaten
    ``test_p6b401_chug_cizilen_l_stari_tuketir`` tarafından ölçülüyor;
    burada iddia "L* değişirse τ_c onunla değişir" biçimine taşındı ve
    L* AÇIKÇA değiştirilerek sınanıyor.
    """
    sabit = []
    for itki in (25000.0, 250000.0, 1000000.0):
        _, j = _cagir(istemci, '/calculate_liquid',
                      dict(TABAN_YUK, thrust=itki))
        r = j.get('results') or j
        sabit.append(_iz(r, 'combustion_analysis', 'stability_analysis',
                         'chug_loop', 'chamber_time_constant', 'tau_c_s'))
    assert all(isinstance(x, (int, float)) for x in sabit)
    # Aynı itici çiftinde L* itkiden bağımsız -> τ_c de bağımsız olmalı.
    assert len(set(round(float(x), 9) for x in sabit)) == 1, (
        f'τ_c üç itkide farklı: {sabit} — L* itkinin fonksiyonu olmuş, '
        'yani kaçış yolu geri gelmiş olabilir')

    # L* GERÇEKTEN değişince τ_c onunla gitmeli (kanal canlı mı?).
    degisken = []
    for l_star in (0.8, 1.2, 1.8):
        _, j = _cagir(istemci, '/calculate_liquid',
                      dict(TABAN_YUK, characteristic_length=l_star))
        r = j.get('results') or j
        degisken.append(_iz(r, 'combustion_analysis', 'stability_analysis',
                            'chug_loop', 'chamber_time_constant', 'tau_c_s'))
    assert all(isinstance(x, (int, float)) for x in degisken)
    assert len(set(round(float(x), 12) for x in degisken)) == 3, (
        f'τ_c üç L*ta aynı: {degisken} — istenen L* tüketilmiyor')
    assert degisken[0] < degisken[1] < degisken[2], (
        f'τ_c L* büyüdükçe artmalı: {degisken}')


def test_p6b401_chug_cizilen_l_stari_KAYNAKTA_tuketir():
    """ÖH D21 bekci-cevirisi a1 (OH-D19-13) — AYIRT EDİCİ KİLİT.

    Kalem: "P6B4-01 bekçisi main'de ayırt edici değil: ``l_star_m=
    self._l_star()`` mutasyonu D17 ağacında 2/4, main'de 0/4 kırmızı."
    ÖLÇÜLDÜ ve DOĞRULANDI (``docs/scofield/raw/OH/D21/bekci-cevirisi/a1/
    mutasyon.json`` ``OH-D19-13``): aynı mutasyonla bu dosyanın altı
    P6B4-01 testinin **0'ı** kırmızıya döndü.

    KÖK SEBEP (ölçüldü, ``once_dinamik.json`` ``OH-D19-13``): D18 fizik-a2
    (F2) sonrası ÇİZİLEN L* ile İSTENEN L* her ulaşılabilir yükte
    BİT-AYNI —
      varsayılan  : çizilen 1,145 m  (SP-125 çift bandı orta noktası)
      L* = 0,8 m  : çizilen 0,8 m
      L* = 1,8 m  : çizilen 1,8 m
      itki 1 MN   : çizilen 1,145 m  (L* artık itkinin fonksiyonu değil)
    Yani iki kanal SAYISAL olarak ayırt edilemez hâle geldi; sayıya bakan
    hiçbir bekçi bu mutasyonu göremez. Kalemin iddiası (çizilen tüketilir,
    istenen değil) o yüzden YAPISAL olarak kilitlenir: çağrı yerinin
    ÇİZİLEN değişkeni geçirdiği kaynaktan okunur. Ters-mutasyon bunu
    kırmızıya döndürür — kanal yeniden ``self._l_star()``a bağlanırsa
    bekçi susmaz.
    """
    import inspect

    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine

    kaynak = inspect.getsource(LiquidRocketEngine)
    i = kaynak.index("'stability_analysis': self._stability_assessment(")
    cagri = kaynak[i:kaynak.index(')', kaynak.index('residence_time_s=', i))]
    assert 'l_star_m=l_star_achieved' in cagri, (
        'chug/kararlılık bloğu ÇİZİLEN L* değişkenini (l_star_achieved) '
        'artık geçirmiyor; çağrı: ' + cagri[-220:])
    assert 'self._l_star()' not in cagri, (
        'kararlılık bloğuna İSTENEN L* (self._l_star()) geçiriliyor — '
        'P6B4-01 kusuru geri gelmiş. Bu iki kanal bugün sayısal olarak '
        'ayırt edilemiyor (çizilen ≡ istenen), o yüzden kilit yapısaldır.')


def test_p6b401_olcum_dosyalari_duruyor():
    """Kalemin sayısı raporda değil KANITTA durur (ÖNCE ÖLÇ kuralı)."""
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    diz = os.path.join(kok, 'docs', 'scofield', 'raw', 'OH', 'D17',
                       'sivi', 'a1')
    for ad in ('once.json', 'sonra.json'):
        yol = os.path.join(diz, ad)
        assert os.path.exists(kanit_gerekli(yol)), f'kanıt yok: {yol}'
        with open(kanit_gerekli(yol), encoding='utf-8') as fh:
            veri = json.load(fh)
        assert 'P6B4-01' in veri and 'OH-D16-05' in veri


def test_p6b401_matematiksel_yon_dogru():
    """τ_c = L*/(c*·Γ²): L* büyüdükçe τ_c BÜYÜR (yön kontrolü)."""
    from hrma.stability.chamber import chamber_time_constant
    kucuk = chamber_time_constant(l_star_m=1.2, c_star_m_s=1800.0, gamma=1.2)
    buyuk = chamber_time_constant(l_star_m=3.472, c_star_m_s=1800.0,
                                  gamma=1.2)
    assert buyuk['tau_c_s'] > kucuk['tau_c_s']
    assert math.isfinite(buyuk['tau_c_s'])
