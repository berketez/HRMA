"""ÖH Dalga-19 · sıvı kulvarı a1 — mutasyon kanıtlı bekçiler.

Ölçüm: ``docs/scofield/raw/OH/D19/sivi/a1/once.json`` ⟷ ``sonra.json``,
betik ``olcum.py``; ters mutasyonlar ``mutasyon.py`` / ``mutasyon.json``.

İki tür bekçi var:

**(A) ONARIM bekçisi.** Bu dalgada kapatılan kusuru kilitler.

* **P3B1-12 (Fable-D17 ŞARTI)** — ``calculate_injector_design`` içindeki
  ``UnsupportedInjectorTypeError`` genel ``except Exception``e YUTULUYORDU.
  Ölçüldü (``once.json`` ``P3B1-12.dogrudan_motor``): doğrudan kurulan
  motorda ``injector_type='banana'`` hata vermeden **28 alanlık eksiksiz**
  enjektör tasarımı döndürüyor, ``injector_type: 'banana'`` diye
  yayımlanıyordu. D17'de kurulan "başka bir enjektörün tasarımı
  yayımlanmaz" kuralı yalnız uç kapısında geçerliydi.

**(B) GERİLEME bekçisi.** Kalem başlığı bu tabanda (60cd341) ÖLÇÜMLE
çürütüldü — kusur D15-D18 dalgalarında kapanmış ama **bekçisi yoktu**
(defterdeki her birinin "Bekçi boşluğu: test-yok" satırı vardı). Sessiz
geri dönüşü engelleyen kapanış bekçileri:

* **P15B1-03** — gaz jeneratörü kartı iki blokta bit-aynı, ``flow_fraction``
  iki blokta da YÜZDE ve çevrim çözümünün ``turbine_mdot_total_kg_s``
  değeriyle çapraz kapanıyor.
* **P3B2-07** — sapma verimi λ TEK değer (``LAMBDA_BELL``); iki kırılım
  bloğunun birim sözleşmesi beyanlı ve ``verim + kayıp = 100`` her anahtar
  için tutuyor.
* **P3B2-08** — yanma verimi tek kaynak (η_c*), iki blokta aynı sayı ve
  aynı künye, birimleri alanın yanında.
* **P3B2-09** — ε taban kırpması artık BEYANLI (``expansion_ratio_clamp``,
  ``expansion_ratio_unclamped``) ve kırpma bağladığında 'ambient-matched'
  iddiası düşüyor; çıkış basıncı tek değer.
* **P3B2-10** — rejeneratif + film debisi yakıtı AŞAMAZ.
* **P3B2-11** — lüle içi statik sıcaklık izentropik bağıntıdan çözülür;
  beyansız ``0,1·ln`` katsayısı kodda kalmamıştır.
* **P3B2-12** — Isp = C_F·c*/(g0·C_D) özdeşliği yayımlanır ve KAPALIDIR.
* **P3B3-07** — pompa kartı kendi içinde kapanır
  (``power_identity_residual_pct`` ≈ 0, ``total_head_m`` yayımlı).
* **P3B3-08** — REDDEDİLEN turbopump_efficiency künyesi kullanıcıyı
  göstermez.
"""

import contextlib
import io
import math
import os
import re
import tempfile

import pytest

from hrma.constants import G_0, LAMBDA_BELL
from hrma.engines.liquid_rocket_engine import (
    INJECTOR_TYPES_RECOGNISED,
    LiquidRocketEngine,
    UnsupportedInjectorTypeError,
)

TABAN_YUK = {
    'motor_name': 'D19-SIVI', 'thrust': 25000.0, 'burn_time': 30.0,
    'chamber_pressure': 60.0, 'mixture_ratio': 2.3,
    'fuel_type': 'rp1', 'oxidizer_type': 'lox', 'nozzle_type': 'bell_80',
}

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOTOR_KAYNAK = os.path.join(KOK, 'hrma', 'engines', 'liquid_rocket_engine.py')


@pytest.fixture(scope='module')
def istemci():
    os.environ.setdefault('HRMA_USER_DATA_DIR',
                          tempfile.mkdtemp(prefix='hrma-d19-sivi-'))
    os.environ.setdefault('HRMA_HEADLESS', '1')
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _cagir(istemci, yuk):
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        r = istemci.post('/calculate_liquid', json=yuk)
    try:
        j = r.get_json()
    except Exception:                                   # pragma: no cover
        j = None
    return r.status_code, (j if isinstance(j, dict) else {})


@pytest.fixture(scope='module')
def taban(istemci):
    st, j = _cagir(istemci, dict(TABAN_YUK))
    assert st == 200, f'taban koşusu HTTP {st}'
    return j


@pytest.fixture(scope='module')
def buyuk_staged(istemci):
    st, j = _cagir(istemci, dict(TABAN_YUK, thrust=250000.0,
                                 chamber_pressure=150.0,
                                 engine_cycle='staged_combustion'))
    assert st == 200, f'250 kN koşusu HTTP {st}'
    return j


def _iz(d, *yol):
    for k in yol:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _kaynak_kod_satirlari():
    """Modülün YORUM OLMAYAN satırları (kod-şekli bekçileri için)."""
    with open(MOTOR_KAYNAK, encoding='utf-8') as fh:
        for ham in fh:
            s = ham.split('#', 1)[0]
            if s.strip():
                yield s


# =====================================================================
# (A) P3B1-12 — Fable-D17 ŞARTI: motor katmanı da sessiz ikame yapamaz
# ÖLÇÜLDÜ (once.json): doğrudan kurulan motorda injector_type='banana'
# hatasız 28 alanlık tasarım döndürüyordu.
# =====================================================================
@pytest.fixture(scope='module')
def motor_kurulu():
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        m = LiquidRocketEngine(thrust=25000.0, chamber_pressure=60.0,
                               mixture_ratio=2.3, fuel_type='rp1',
                               oxidizer_type='lox',
                               injector_type='impinging')
        m.calculate_performance()
    return m


def test_p3b1_12_motor_katmani_taninmayan_tipte_tasarim_yayimlamaz(
        motor_kurulu):
    """Uç kapısını atlayan yolda da BAŞKA bir enjektörün tasarımı basılmaz."""
    motor_kurulu.injector_type = 'banana'
    try:
        with pytest.raises(UnsupportedInjectorTypeError) as bilgi:
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                motor_kurulu.calculate_injector_design()
        mesaj = str(bilgi.value)
        assert 'banana' in mesaj
        # Red ADLIDIR: tanınan kümeyi sayar, sessiz ikame yapmadığını yazar.
        for tip in INJECTOR_TYPES_RECOGNISED:
            assert tip in mesaj, f'red mesajı {tip!r} tipini saymıyor'
    finally:
        motor_kurulu.injector_type = 'impinging'


def test_p3b1_12_taninan_tip_motor_katmaninda_tasarim_uretir(motor_kurulu):
    """Kapı ÜRÜNÜ KIRMAZ: tanınan her tip motor katmanında da geçer."""
    for tip in INJECTOR_TYPES_RECOGNISED:
        motor_kurulu.injector_type = tip
        try:
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                d = motor_kurulu.calculate_injector_design()
            assert d.get('injector_type') == tip
            assert d.get('fuel_orifice_diameter', 0) > 0
        finally:
            motor_kurulu.injector_type = 'impinging'


# =====================================================================
# (A) P3B1-11 — Fable-D17 ŞARTI: boşluklu ad ÜRÜN DAVRANIŞI DEĞİŞTİ
# Taban (D17 öncesi) '  methane  ' için 400 veriyordu (motorun
# UnsupportedPropellantDensityError'ı; uç kapısı değil). Kanonikleştirme
# tablo kaydını bulduğu için artık 200 dönüyor ve kart kanoniktir.
# =====================================================================
def test_p3b1_11_bosluklu_ad_tablo_kaydini_bulur(istemci):
    st, j = _cagir(istemci, dict(TABAN_YUK, fuel_type='  methane  ',
                                 oxidizer_type=' lox '))
    assert st == 200, f'boşluklu itici adı HTTP {st} aldı (beklenen 200)'
    st2, j2 = _cagir(istemci, dict(TABAN_YUK, fuel_type='methane',
                                   oxidizer_type='lox'))
    assert st2 == 200
    assert j['propellant_name'] == j2['propellant_name']
    assert j['fuel_density'] == j2['fuel_density']
    assert 'Methane/LOX' in str(j['propellant_name'])


# =====================================================================
# (B) P15B1-03 — gaz jeneratörü kartı TEK kart
# =====================================================================
def test_p15b1_03_gaz_jeneratoru_karti_iki_blokta_bit_ayni(buyuk_staged):
    kaba = _iz(buyuk_staged, 'feed_system', 'turbopump') or {}
    det = _iz(buyuk_staged, 'detailed_feed_system',
              'turbopump_analysis') or {}
    for blok in ('gas_generator', 'turbine'):
        a, b = kaba.get(blok) or {}, det.get(blok) or {}
        assert a and b, f'{blok} bloğu bir kartta yok'
        ortak = sorted(set(a) & set(b))
        assert ortak, f'{blok} bloklarının ortak alanı yok'
        for alan in ortak:
            assert a[alan] == b[alan], (
                f'{blok}.{alan} iki kartta ayrışıyor: {a[alan]!r} ⟷ '
                f'{b[alan]!r}')


def test_p15b1_03_flow_fraction_birimi_beyanli_ve_yuzde(buyuk_staged):
    for yol in (('feed_system', 'turbopump'),
                ('detailed_feed_system', 'turbopump_analysis')):
        gg = _iz(buyuk_staged, *yol, 'gas_generator') or {}
        assert gg.get('flow_fraction_unit') == 'percent', (
            f'{yol} gas_generator.flow_fraction birimi beyansız')
        tur = _iz(buyuk_staged, *yol, 'turbine') or {}
        assert tur.get('efficiency_unit') == 'fraction'
        assert 0.0 < float(tur['efficiency']) <= 1.0, (
            'turbine.efficiency KESİR sözleşmesini bozuyor')


def test_p15b1_03_flow_fraction_cevrim_cozumuyle_kapaniyor(buyuk_staged):
    """Kart artık VARSAYIM değil: çevrim çözümünden geri hesaplanır."""
    gg = _iz(buyuk_staged, 'feed_system', 'turbopump',
             'gas_generator') or {}
    mdot_t = float(buyuk_staged['total_mass_flow'])
    mdot_turb = float(_iz(buyuk_staged, 'detailed_feed_system',
                          'engine_cycle_solution',
                          'turbine_mdot_total_kg_s'))
    beklenen = mdot_turb / mdot_t * 100.0
    assert gg['flow_fraction'] == pytest.approx(beklenen, rel=1e-9), (
        f"kart {gg['flow_fraction']} diyor, çevrim çözümü {beklenen}")
    assert 0.0 < float(gg['flow_fraction']) <= 100.0


def test_p15b1_03_flow_fraction_sabit_degil_cevrime_bagli(istemci,
                                                          buyuk_staged):
    """Eski kaba kart SABİT %5 idi (GAS_GENERATOR_FLOW_FRACTION).

    Kart artık çevrim çözümünden geliyorsa aynı motorun kademeli yanmalı
    ve gaz jeneratörlü çözümü FARKLI pay vermelidir (kademeli yanmada ön
    yakıcı bir iticinin neredeyse tamamını geçirir).
    """
    staged = float(_iz(buyuk_staged, 'feed_system', 'turbopump',
                       'gas_generator', 'flow_fraction'))
    st, j = _cagir(istemci, dict(TABAN_YUK, thrust=250000.0,
                                 chamber_pressure=150.0,
                                 engine_cycle='gas_generator'))
    assert st == 200
    gg = float(_iz(j, 'feed_system', 'turbopump', 'gas_generator',
                   'flow_fraction'))
    assert abs(staged - gg) > 1.0, (
        f'debi payı çevrimden bağımsız çıkıyor (staged {staged} ⟷ '
        f'gas_generator {gg}) — sabit karta dönmüş olabilir')
    assert not any(abs(x - 5.0) < 1e-9 for x in (staged, gg)), (
        'debi payı tam %5 — GAS_GENERATOR_FLOW_FRACTION sabiti geri gelmiş')


# =====================================================================
# (B) P3B2-07 — sapma verimi λ TEK değer
# =====================================================================
def test_p3b2_07_sapma_verimi_tek_deger(taban):
    na = taban['nozzle_angles']
    eb = taban['efficiency_breakdown']
    lam = float(na['divergence_efficiency'])
    assert lam == pytest.approx(float(LAMBDA_BELL), rel=1e-12), (
        'bell konturunda λ yayımlanan LAMBDA_BELL değil (konik formüle '
        'dönülmüş olabilir)')
    assert float(na['lambda_divergence_applied']) == pytest.approx(lam,
                                                                  rel=1e-12)
    assert float(_iz(eb, 'efficiency_breakdown', 'divergence_loss')) == \
        pytest.approx(lam * 100.0, rel=1e-9)
    assert float(_iz(eb, 'loss_breakdown', 'divergence_loss')) == \
        pytest.approx((1.0 - lam) * 100.0, abs=1e-9)
    assert 'LAMBDA_BELL' in str(na['divergence_efficiency_source'])


def test_p3b2_07_iki_kirilim_blogunun_sozlesmesi_beyanli(taban):
    """Aynı adı taşıyan iki blok: birimi beyanlı, toplamı 100."""
    eb = taban['efficiency_breakdown']
    e_birim = str(eb.get('efficiency_breakdown_unit') or '')
    k_birim = str(eb.get('loss_breakdown_unit') or '')
    assert 'EFFICIENCY' in e_birim, 'verim bloğunun birimi beyansız'
    assert 'loss' in k_birim, 'kayıp bloğunun birimi beyansız'
    verim, kayip = eb['efficiency_breakdown'], eb['loss_breakdown']
    assert set(verim) == set(kayip)
    for anahtar in verim:
        assert float(verim[anahtar]) + float(kayip[anahtar]) == \
            pytest.approx(100.0, abs=1e-6), (
            f'{anahtar}: verim+kayıp = '
            f'{float(verim[anahtar]) + float(kayip[anahtar])} ≠ 100')


# =====================================================================
# (B) P3B2-08 — yanma verimi TEK kaynak
# =====================================================================
def test_p3b2_08_yanma_verimi_tek_kaynak(taban):
    kesir = float(_iz(taban, 'injection_system', 'combustion_efficiency'))
    yuzde = float(_iz(taban, 'combustion_analysis', 'combustion_analysis',
                      'combustion_efficiency'))
    assert kesir == pytest.approx(yuzde / 100.0, rel=1e-12), (
        f'aynı büyüklük iki değer: {kesir} (kesir) ⟷ {yuzde} (yüzde)')
    assert float(_iz(taban, 'injector_design',
                     'combustion_efficiency')) == pytest.approx(kesir,
                                                                rel=1e-12)
    assert float(_iz(taban, 'efficiency_breakdown', 'efficiency_breakdown',
                     'combustion_incomplete')) == pytest.approx(yuzde,
                                                                rel=1e-12)
    k1 = str(_iz(taban, 'injection_system', 'combustion_efficiency_source'))
    k2 = str(_iz(taban, 'combustion_analysis', 'combustion_analysis',
                 'combustion_efficiency_source'))
    assert k1 == k2, f'aynı sayı iki künye taşıyor:\n  {k1}\n  {k2}'
    # Enjektör TİPİNDEN uydurulmuş bir η_c* geri gelemez.
    assert 'injector type' not in k1.lower() or 'NOT used' in k1
    assert _iz(taban, 'injection_system',
               'combustion_efficiency_unit') == 'fraction'
    assert _iz(taban, 'combustion_analysis', 'combustion_analysis',
               'combustion_efficiency_unit') == 'percent'


# =====================================================================
# (B) P3B2-09 — ε taban kırpması BEYANLI, 'ambient-matched' iddiası düşüyor
# Pc = 10 bar ürünün KABUL ETTİĞİ alt sınırdır (app.py 10-500).
# =====================================================================
@pytest.mark.parametrize('yakit,oksit', [('rp1', 'lox'), ('mmh', 'n2o4'),
                                         ('lh2', 'lox')])
def test_p3b2_09_taban_kirpmasi_beyanli(istemci, yakit, oksit):
    st, j = _cagir(istemci, dict(TABAN_YUK, thrust=5000.0,
                                 chamber_pressure=10.0,
                                 fuel_type=yakit, oxidizer_type=oksit))
    assert st == 200
    na = j['nozzle_angles']
    kirpma = na.get('expansion_ratio_clamp')
    ham = na.get('expansion_ratio_unclamped')
    assert ham is not None, 'kırpmasız optimum yayımlanmıyor'
    if kirpma == 'floor':
        assert float(ham) < float(j['expansion_ratio']), (
            'taban bağladı deniyor ama kırpmasız değer daha büyük')
        metin = ' '.join(str(x) for x in
                         (_iz(j, 'design_summary',
                              'optimizations_applied') or []))
        assert 'ambient-matched optimum (pe = pa)' not in metin, (
            'taban bağlıyken hâlâ pe = pa iddiası yayımlanıyor')
        temel = ' '.join(str(x) for x in
                         (_iz(j, 'design_summary', 'status_basis') or []))
        assert 'NOT ambient-matched' in temel, (
            'kırpmanın iddiayı düşürdüğü BEYAN EDİLMİYOR')
    else:
        assert float(ham) == pytest.approx(float(j['expansion_ratio']),
                                           rel=1e-9)


@pytest.mark.parametrize('yakit,oksit', [('rp1', 'lox'), ('mmh', 'n2o4')])
def test_p3b2_09_cikis_basinci_tek_deger(istemci, yakit, oksit):
    st, j = _cagir(istemci, dict(TABAN_YUK, thrust=5000.0,
                                 chamber_pressure=10.0,
                                 fuel_type=yakit, oxidizer_type=oksit))
    assert st == 200
    okumalar = [
        _iz(j, 'nozzle_angles', 'exit_pressure_bar'),
        _iz(j, 'nozzle_design', 'performance', 'exit_pressure'),
        _iz(j, 'altitude_performance', 0, 'exit_pressure_bar')
        if isinstance(j.get('altitude_performance'), list) else None,
    ]
    if isinstance(j.get('altitude_performance'), list) and \
            j['altitude_performance']:
        okumalar[2] = j['altitude_performance'][0].get('exit_pressure_bar')
    okumalar = [float(x) for x in okumalar if x is not None]
    assert len(okumalar) >= 2, 'çıkış basıncı tek yolda bile yayımlanmıyor'
    assert max(okumalar) - min(okumalar) < 1e-9, (
        f'çıkış basıncı aynı yanıtta ayrışıyor: {okumalar}')
    # P_e = P_atm ataması geri gelirse bu değer TAM 1,01325 olur.
    assert not any(abs(x - 1.01325) < 1e-9 for x in okumalar), (
        'çıkış basıncı ortam basıncına ATANMIŞ (hesap değil)')


# =====================================================================
# (B) P3B2-10 — rejeneratif + film debisi yakıtı AŞAMAZ
# =====================================================================
@pytest.mark.parametrize('film', [0, 10, 20, 30])
def test_p3b2_10_sogutucu_arti_film_yakiti_asamaz(istemci, film):
    st, j = _cagir(istemci, dict(TABAN_YUK, film_cooling_percent=film))
    assert st == 200
    cs = j['cooling_system']
    yakit = float(j['fuel_flow'])
    ceket = float(cs['coolant_flow_rate'])
    f_debi = float(cs.get('film_cooling_flow') or 0.0)
    assert ceket + f_debi <= yakit * (1.0 + 1e-9), (
        f'film %{film}: ceket {ceket} + film {f_debi} = {ceket + f_debi} > '
        f'yakıt {yakit}')
    assert float(cs['coolant_plus_film_flow_kg_s']) == pytest.approx(
        ceket + f_debi, rel=1e-9)
    assert float(cs['coolant_plus_film_fraction_of_fuel']) <= 1.0 + 1e-9
    if film > 0:
        assert f_debi > 0.0
        # Film payı ceketten DÜŞÜLÜR (üstüne eklenmez).
        assert ceket < yakit


# =====================================================================
# (B) P3B2-11 — lüle içi statik sıcaklık izentropik
# =====================================================================
def test_p3b2_11_lule_gaz_sicakligi_izentropik_beyanli(taban):
    temel = str(_iz(taban, 'cooling_system',
                    'nozzle_gas_temperature_basis') or '')
    assert 'isentropic' in temel.lower(), 'sürücü sıcaklık künyesiz'
    assert 'SUBSONIC' in temel and 'SUPERSONIC' in temel, (
        'yakınsak/ıraksak kök ayrımı beyan edilmiyor')
    assert 'T_aw' in temel


def test_p3b2_11_beyansiz_0_1_ln_katsayisi_kodda_yok():
    """Kod-şekli bekçisi: '0.1 · ln(A/A_t)' formu CANLI kodda olamaz."""
    desen = re.compile(r'0\.1\s*\*\s*np\.log|np\.log\s*\([^)]*\)\s*\*\s*0\.1')
    suclu = [s.strip() for s in _kaynak_kod_satirlari() if desen.search(s)]
    assert suclu == [], f'beyansız 0,1·ln sıcaklık formu geri gelmiş: {suclu}'


def test_p3b2_11_izentropik_cozucu_bogazda_dogru(motor_kurulu):
    """Boğazda T/T_c = 2/(γ+1); ε=9,58'de eski form 0,9634 veriyordu."""
    g = float(motor_kurulu.gamma)
    T_c = float(motor_kurulu.T_c)
    T_bogaz, M_bogaz = motor_kurulu._isentropic_static_temperature(
        T_c, 1.0, g, supersonic=True)
    assert M_bogaz == pytest.approx(1.0, abs=1e-6)
    assert T_bogaz / T_c == pytest.approx(2.0 / (g + 1.0), rel=1e-9)
    T_cikis, M_cikis = motor_kurulu._isentropic_static_temperature(
        T_c, 9.58, g, supersonic=True)
    assert M_cikis > 1.0
    assert T_cikis / T_c < 0.60, (
        f'ıraksak konide T/T_c = {T_cikis / T_c:.4f}; eski beyansız '
        f'0,1·ln formu 0,9634 veriyordu')


# =====================================================================
# (B) P3B2-12 — Isp = C_F·c*/(g0·C_D) özdeşliği KAPALI
# =====================================================================
def test_p3b2_12_isp_ozdesligi_yayimlanir_ve_kapali(taban):
    kimlik = taban['isp_identity']
    assert kimlik['status'] == 'CLOSED', kimlik
    assert abs(float(kimlik['residual_pct'])) < 1e-6
    cd = float(taban['throat_discharge_coefficient'])
    assert 0.70 <= cd <= 1.0
    assert str(taban['throat_discharge_coefficient_basis']).strip()
    # Özdeşliği KENDİM kuruyorum (yayımlanan üç sayı + C_D).
    cf = float(taban['altitude_performance'][0]['thrust_coefficient'])
    c_star = float(taban['c_star'])
    isp = float(taban['isp_sea_level'])
    assert isp == pytest.approx(cf * c_star / (G_0 * cd), rel=1e-9), (
        f'Isp {isp} ⟷ C_F·c*/(g0·C_D) {cf * c_star / (G_0 * cd)}')
    # C_D terimi OLMADAN tam 1/C_D kadar ıskalar — okuyucunun gördüğü fark.
    assert isp / (cf * c_star / G_0) == pytest.approx(1.0 / cd, rel=1e-9)


# =====================================================================
# (B) P3B3-07 — pompa kartı kendi içinde kapanır
# =====================================================================
@pytest.mark.parametrize('cevrim', ['staged_combustion', 'gas_generator'])
@pytest.mark.parametrize('pompa', ['oxidizer_pump', 'fuel_pump'])
def test_p3b3_07_pompa_karti_kendi_icinde_kapanir(istemci, cevrim, pompa):
    st, j = _cagir(istemci, dict(TABAN_YUK, thrust=250000.0,
                                 chamber_pressure=150.0,
                                 engine_cycle=cevrim))
    assert st == 200
    p = _iz(j, 'detailed_feed_system', 'turbopump_analysis', pompa) or {}
    assert p, f'{pompa} kartı yok'
    H = float(p['total_head_m'])
    Q = float(p['volumetric_flow_m3_s'])
    eta = float(p['design_efficiency']) / 100.0
    P = float(p['design_power'])
    assert float(p['power_identity_residual_pct']) == pytest.approx(0.0,
                                                                    abs=1e-6)
    assert float(p['power_identity_kW']) == pytest.approx(P, rel=1e-9)
    # Yoğunluk kartta yayımlanmıyor; özdeşliği ρ'yu geri çözerek kuruyorum.
    rho = P * 1000.0 * eta / (G_0 * H * Q)
    assert 100.0 < rho < 2500.0, (
        f'{pompa}: P=ρgHQ/η özdeşliğinden çıkan ρ={rho:.1f} kg/m³ fiziksel '
        f'değil — kartın alanları birbirini tutmuyor')
    assert str(p['total_head_basis']).strip()
    assert str(p['design_head_role']).strip()


# =====================================================================
# (B) P3B3-08 — REDDEDİLEN girdiye sahip çıkılmaz
# =====================================================================
@pytest.mark.parametrize('deger,neden', [(150, 'out_of_accepted_range'),
                                         (5, 'out_of_accepted_range'),
                                         ('abc', 'not_a_number')])
def test_p3b3_08_reddedilen_verim_kullanici_kunyesi_almaz(istemci, deger,
                                                          neden):
    """TERS KAPI (v3.0.1 T-ÇAPA-B): reddedilen verim artık hiçbir künyeye
    girmez çünkü tasarım HİÇ yayımlanmaz.

    Eski bekçi 200 + pompa künyesinde 'REJECTED' + %75 yedek verim
    bekliyordu. L-A (SV-02, tek bant kapısı; K-A "ana model kararı 3"):
    aralık dışı / okunamaz girdi yerleşik değerle değiştirilmez, adlı 422
    döner. Ölçüldü (taban 117d704da): 150 / 5 → ``out_of_accepted_range``,
    'abc' → ``not_a_number``; kabul aralığı 20-95 %. "Kullanıcı girdisi
    diye künyelenmez" iddiası en güçlü biçimiyle korunur: yayımlanan pompa
    kartı yok.
    """
    st, j = _cagir(istemci, dict(TABAN_YUK, thrust=250000.0,
                                 chamber_pressure=150.0,
                                 turbopump_efficiency=deger))
    assert st == 422, (st, str(j)[:300])
    assert j.get('error_code') == 'input_not_accepted'
    kayit = [f for f in (j.get('invalid_fields') or [])
             if f.get('field') == 'turbopump_efficiency']
    assert kayit, j.get('invalid_fields')
    assert kayit[0]['reason'] == neden
    assert 'turbopump_efficiency' in str(j.get('message'))
    assert _iz(j, 'detailed_feed_system', 'turbopump_analysis') is None


def test_p3b3_08_kabul_edilen_verim_kullaniciyi_gosterir(istemci):
    st, j = _cagir(istemci, dict(TABAN_YUK, thrust=250000.0,
                                 chamber_pressure=150.0,
                                 turbopump_efficiency=80))
    assert st == 200
    p = _iz(j, 'detailed_feed_system', 'turbopump_analysis',
            'oxidizer_pump') or {}
    assert float(p['design_efficiency']) == pytest.approx(80.0)
    assert str(p['efficiency_source']).startswith('user input')


def test_p3b3_08_girdi_yoksa_varsayilan_kunyesi(istemci):
    st, j = _cagir(istemci, dict(TABAN_YUK, thrust=250000.0,
                                 chamber_pressure=150.0))
    assert st == 200
    p = _iz(j, 'detailed_feed_system', 'turbopump_analysis',
            'oxidizer_pump') or {}
    kunye = str(p['efficiency_source'])
    assert 'default' in kunye and 'user input' not in kunye
    assert 'REJECTED' not in kunye
