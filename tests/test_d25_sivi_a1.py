"""ÖH Dalga-25 · sıvı kulvarı a1 — mutasyon kanıtlı bekçiler.

Ölçüm: ``docs/scofield/raw/OH/D25/sivi/a1/once.json`` (taban ağacı,
``cdf2106``) ⟷ ``sonra.json`` (bu ağaç), betik ``olcum.py``; ters mutasyonlar
``mutasyon.py`` / ``mutasyon.json``.

Kilitlenen üç ürün onarımı
--------------------------

**OH-D24-12 — pompa kartı özdeşliğinin dördüncü çarpanı.**
``detailed_feed_system.turbopump_analysis.*_pump`` kartı ``P = ρ·g·H·Q/η``
özdeşliğini yayımlıyor (``power_identity_kW``, ``power_identity_residual_pct``)
ama ρ'yu yayımlamıyordu. ÖLÇÜLDÜ (``once.json`` ``OH-D24-12``): dört kartın
hiçbirinde adında ``dens`` geçen tek bir alan yok
(``ozdeslik_disaridan_kurulabiliyor: false``). Sonuç: kalan **yapı gereği**
sıfır (aynı ρ hem özdeşliğin kurucusu hem denetçisi) ve kartı okuyanın elinde
bağımsız denetim kalmıyordu — D19 bekçisi bile ρ'yu geri çözmek zorunda
kalmıştı. Bugün kart ``fluid_density_kg_m3`` + ``fluid_density_source``
yayımlıyor ve özdeşlik kartın DIŞINDAN kuruluyor (ölçüldü: fark %0,0).

**OH-D24-13 — üç sessiz ``except Exception``.**
ÖLÇÜLDÜ (``once.json`` ``OH-D24-13.taninmayan_banana``, 25 kN/60 bar,
``injector_type='banana'``): (a) besleme bütçesinin enjektör kalemi 13,2 bar
iken sessizce **0,0 bar** oluyor, oksitleyici toplamı 15,7314 → 2,5314 bara
düşüyordu — o toplam pompa basma basıncını sürer; (b) ``_injector_detail()``
15 alan yerine sessizce ``None`` döndürüyordu; (c) üretim kartının kritik
tolerans listesi beş özellikten **üçe** iniyor, düşen iki enjektör orifisi
(2,449 mm / 2,494 mm) için tek bir künye bile konmuyordu. Üçünde de hata YOK,
uyarı YOK. Bugün kapı hataları adıyla yükseliyor.

**OH-D24-14 — türbin verimi bandı tek kaynak.**
Motor bandı kendi literalleriyle ikinci kez, üstelik FARKLI sınırlarla
yazıyordu (``0,0 < eta <= 1,0`` ⟷ ``TURBINE_EFFICIENCY_VALID = (0,10, 1,00)``).
ÖLÇÜLDÜ (``once.json`` ``OH-D24-14``, 250 kN/150 bar staged, çevrim verimi
0,05'e çekildi): motor değeri KABUL ediyor, sonra boyutlandırma modülü
reddediyor, türbin kartı ``not_computed`` oluyor ve gerekçe suçu
boyutlandırmaya atıyordu (``turbine_efficiency_source`` = ``None``, yani
sayının çevrimden geldiği hiçbir yerde yazmıyordu).
"""

import contextlib
import io
import os
import tempfile

import pytest

from hrma.analysis.turbopump_sizing import TURBINE_EFFICIENCY_VALID
from hrma.constants import G_0
from hrma.engines.liquid_rocket_engine import (
    LiquidRocketEngine,
    UnsupportedInjectorTypeError,
)
from tests.support.kanit import kanit_gerekli

TABAN_YUK = {
    'motor_name': 'D25-SIVI', 'thrust': 25000.0, 'burn_time': 30.0,
    'chamber_pressure': 60.0, 'mixture_ratio': 2.3,
    'fuel_type': 'rp1', 'oxidizer_type': 'lox', 'nozzle_type': 'bell_80',
}


@pytest.fixture(scope='module')
def istemci():
    ud = os.path.join(tempfile.gettempdir(), 'hrma-d25-sivi-a1')
    os.makedirs(ud, exist_ok=True)
    os.environ['HRMA_USER_DATA_DIR'] = ud
    os.environ['HRMA_HEADLESS'] = '1'
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _cagir(istemci, yuk):
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        r = istemci.post('/calculate_liquid', json=yuk)
    return r.status_code, r.get_json()


def _iz(d, *yol):
    for p in yol:
        if not isinstance(d, dict):
            return None
        d = d.get(p)
    return d


def _motor(injector_type='impinging', thrust=25000.0,
           chamber_pressure=60.0, **kw):
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        m = LiquidRocketEngine(thrust=thrust,
                               chamber_pressure=chamber_pressure,
                               mixture_ratio=2.3, fuel_type='rp1',
                               oxidizer_type='lox',
                               injector_type=injector_type, **kw)
        m.calculate_performance()
    return m


# =====================================================================
# OH-D24-12 — özdeşlik kartın DIŞINDAN kurulabilir
# =====================================================================
@pytest.mark.parametrize('cevrim', ['staged_combustion', 'gas_generator'])
@pytest.mark.parametrize('pompa', ['oxidizer_pump', 'fuel_pump'])
def test_oh_d24_12_pompa_karti_yogunlugu_yayimlar(istemci, cevrim, pompa):
    """ρ kartta; P = ρ·g·H·Q/η geri çözüm YAPMADAN kapanır."""
    st, j = _cagir(istemci, dict(TABAN_YUK, thrust=250000.0,
                                 chamber_pressure=150.0,
                                 engine_cycle=cevrim))
    assert st == 200
    p = _iz(j, 'detailed_feed_system', 'turbopump_analysis', pompa) or {}
    assert p, f'{pompa} kartı yok'
    rho = p.get('fluid_density_kg_m3')
    assert isinstance(rho, (int, float)) and rho > 0, (
        f'{pompa}: kart akışkan yoğunluğunu yayımlamıyor — özdeşliğin dört '
        'çarpanından biri eksik, kalan yapı gereği sıfır çıkar '
        f'(ölçüm: once.json OH-D24-12.{cevrim}); kartta bulunan: '
        + repr(sorted(k for k in p if 'dens' in str(k).lower())))
    # Künye: sayının NEREDEN geldiği yazılı olmalı.
    kunye = str(p.get('fluid_density_source') or '')
    assert len(kunye) >= 10, f'{pompa}: yoğunluk künyesiz ({kunye!r})'
    # Özdeşlik yalnız KARTIN alanlarıyla kurulur (geri çözüm yok).
    H = float(p['total_head_m'])
    Q = float(p['volumetric_flow_m3_s'])
    eta = float(p['design_efficiency']) / 100.0
    P = float(p['design_power'])
    disaridan = float(rho) * G_0 * H * Q / eta / 1000.0
    assert disaridan == pytest.approx(P, rel=1e-9), (
        f'{pompa}: kartın kendi alanlarından çıkan güç {disaridan:.6f} kW, '
        f'yayımlanan design_power {P:.6f} kW')
    # ρ fiziksel bir sıvı yoğunluğu olmalı (uydurma sayı değil).
    assert 100.0 < float(rho) < 2500.0


def test_oh_d24_12_yogunluk_motorun_tek_kaynagiyla_ayni(istemci):
    """Kart, motorun ``_propellant_density`` kaynağından SAPMAZ."""
    m = _motor()
    st, j = _cagir(istemci, dict(TABAN_YUK, thrust=250000.0,
                                 chamber_pressure=150.0,
                                 engine_cycle='staged_combustion'))
    assert st == 200
    for pompa, rol in (('oxidizer_pump', 'oxidizer'), ('fuel_pump', 'fuel')):
        p = _iz(j, 'detailed_feed_system', 'turbopump_analysis', pompa) or {}
        rho_kart = float(p['fluid_density_kg_m3'])
        rho_motor, kaynak = m._propellant_density(rol)
        assert rho_kart == pytest.approx(float(rho_motor), rel=1e-12), (
            f'{pompa}: kart {rho_kart} kg/m³ derken motorun tek yoğunluk '
            f'kaynağı {rho_motor} kg/m³ diyor — aynı yanıtta iki gerçek')
        assert kaynak in str(p.get('fluid_density_source'))


# =====================================================================
# OH-D24-13 — kapı hatası hiçbir yardımcı yolda yutulmaz
# =====================================================================
def test_oh_d24_13_besleme_dp_zinciri_kapi_hatasini_yutmaz():
    """Tanınmayan tipte enjektör kalemi sessizce 0,0 bara düşmez."""
    m = _motor()
    m.injector_type = 'banana'
    with pytest.raises(UnsupportedInjectorTypeError):
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            m._calculate_feed_system_pressure_drops()


def test_oh_d24_13_besleme_dp_karti_kaleminin_kunyesi_var():
    """Sağlıklı yolda kalem HESAPLANDIĞINI söyler (sessiz sıfır ayrımı)."""
    m = _motor()
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        drops = m._calculate_feed_system_pressure_drops()
    kunye = str(drops.get('injector_drop_basis') or '')
    assert kunye.startswith('computed:'), (
        'enjektör kalemi hesaplandığında künye "computed:" ile başlamalı — '
        'yoksa okuyan, sıfırın hesap mı beyan mı olduğunu ayıramaz; '
        f'bulunan: {kunye!r}')
    assert float(drops['injector']) > 0.0


def test_oh_d24_13_enjektor_ayrintisi_kapi_hatasini_yutmaz():
    """``_injector_detail`` sessizce None dönmez (15 alan -> None idi)."""
    m = _motor()
    m.injector_type = 'banana'
    m._injector_detail_memo = None
    with pytest.raises(UnsupportedInjectorTypeError):
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            m._injector_detail()


def test_oh_d24_13_uretim_karti_kapi_hatasini_yutmaz():
    """Kritik tolerans listesi sessizce eksilmez (5 özellik -> 3 idi)."""
    m = _motor()
    m.injector_type = 'banana'
    with pytest.raises(UnsupportedInjectorTypeError):
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            m._analyze_manufacturing_requirements()


def test_oh_d24_13_uretim_karti_eksiksizken_bunu_soyler():
    """Sağlıklı yolda liste tam ve 'hiçbir girdi düşmedi' yazılı."""
    m = _motor()
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        kart = m._analyze_manufacturing_requirements()
    tol = kart['critical_tolerances']
    assert tol['withheld_inputs'] == []
    assert str(tol['withheld_inputs_basis']).strip()
    ozellikler = set(tol['features'])
    assert {'fuel_injector_orifice', 'oxidizer_injector_orifice'} <= ozellikler


# =====================================================================
# OH-D24-14 — türbin verimi bandı TEK kaynak
# =====================================================================
def test_oh_d24_14_band_motorda_yeniden_yazilmamis():
    """Kural iki yerde yazılamaz: motor bandı modülden TÜKETİR."""
    yol = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'hrma', 'engines',
        'liquid_rocket_engine.py')
    kaynak = open(yol, encoding='utf-8').read()
    assert 'TURBINE_EFFICIENCY_VALID' in kaynak, (
        'motor türbin verimi bandını turbopump_sizing modülünden ithal '
        'etmiyor — band ikinci kez yazılmış olabilir')
    assert '0.0 < eta_cyc <= 1.0' not in kaynak, (
        'çevrim türbin verimi ön süzgeci hâlâ kendi literal bandını '
        'kullanıyor (0,0 < eta <= 1,0); modülün bandı (0,10, 1,00) ile '
        'ayrışır')


def _cevrim_yamali_motor(eta):
    """Gerçek (yakınsamış) çevrim çözümünün türbin verimi ``eta`` yapılır."""
    import copy
    m0 = _motor(thrust=250000.0, chamber_pressure=150.0,
                overrides={'engine_cycle': 'staged_combustion'})
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        gercek = m0._solve_cycle_balance()
    assert gercek.get('status') == 'converged' and gercek.get('shafts')
    yama = copy.deepcopy(gercek)
    yama['shafts'][0].setdefault('turbine', {})['efficiency'] = eta
    m = _motor(thrust=250000.0, chamber_pressure=150.0,
               overrides={'engine_cycle': 'staged_combustion'})
    m._solve_cycle_balance = lambda: yama
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        res = m._analyze_detailed_feed_system()
    return (res.get('turbopump_sizing') or {}).get('turbine') or {}


def test_oh_d24_14_band_disi_cevrim_verimi_adiyla_reddedilir():
    """0,05 kabul edilip modüle gönderilmez; red künyesi ÇEVRİMİ gösterir."""
    t = _cevrim_yamali_motor(0.05)
    assert t.get('status') == 'not_computed'
    kunye = str(t.get('turbine_efficiency_source') or '')
    assert kunye.startswith('REJECTED'), (
        'bandın dışındaki çevrim verimi reddedildiğinde künye bunu '
        f'söylemeli; bulunan: {kunye!r}')
    assert 'cycle power balance' in kunye, (
        'red künyesi sayının ÇEVRİMDEN geldiğini söylemeli — eski hâlinde '
        'gerekçe suçu boyutlandırma modülüne atıyordu')
    assert str(TURBINE_EFFICIENCY_VALID) in kunye, (
        'red künyesi hangi bandın uygulandığını yazmalı')
    # Sessiz ikame yok: motor varsayılanı türbin verimi diye yayımlanmaz.
    assert t.get('turbine_efficiency') is None


def test_oh_d24_14_band_icindeki_cevrim_verimi_kullanilmaya_devam_eder():
    """Sağlıklı yol değişmez: 0,50 kabul, türbin boyutlanır, künye çevrim."""
    t = _cevrim_yamali_motor(0.50)
    assert t.get('status') == 'modelled'
    assert float(t['turbine_efficiency']) == pytest.approx(0.50)
    assert 'cycle power balance' in str(t.get('turbine_efficiency_source'))


def test_oh_d24_14_band_sinirlari_modulun_bandi():
    """Alt sınır tam bandın kenarında kabul edilir (kapsayıcı karşılaştırma)."""
    lo, hi = TURBINE_EFFICIENCY_VALID
    t = _cevrim_yamali_motor(lo)
    assert t.get('status') == 'modelled', (
        f'bandın alt kenarı ({lo}) reddedilmemeli — modül onu kabul ediyor')
    assert float(t['turbine_efficiency']) == pytest.approx(lo)


# =====================================================================
# ŞART kalemleri (kanıt hijyeni) — belgeye konan düzeltmenin bekçisi
# =====================================================================
_D19 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))), 'docs', 'scofield', 'raw', 'OH', 'D19')


def test_p15b1_03_sart_rapor_kaynaksiz_sayilari_tasimaz():
    """D19 tablosu artık once.json'un kendi sayılarını yazıyor."""
    rapor = open(kanit_gerekli(os.path.join(_D19, 'sivi', 'a1', 'rapor.md')),
                 encoding='utf-8').read()
    for kaynaksiz in ('0,10732149994056926', '999,9991012444566'):
        assert rapor.count(kaynaksiz) <= 1, (
            f'{kaynaksiz} rapor gövdesinde hâlâ ÖLÇÜM değeri gibi duruyor; '
            'yalnız DÜZELTME notunda, düzeltilen sayı olarak geçmeli')
    assert '0,058125500045907955' in rapor and '900,0004864033605' in rapor
    assert 'DÜZELTME (ÖH D25' in rapor


def test_p3b3_07_sart_kanit_kaynagi_dogru_bildirilir():
    """'once/sonra (aynı)' iddiası düzeltilmiş, gerçek kaynak yazılı."""
    rapor = open(kanit_gerekli(os.path.join(_D19, 'sivi', 'a1', 'rapor.md')),
                 encoding='utf-8').read()
    assert 'olcum.py bu alanları' in rapor, (
        'P3B3-07 kanıt kaynağı düzeltmesi raporda yok')
    import json
    d = json.load(open(kanit_gerekli(os.path.join(
        _D19, 'oturum-devri', 'd19_raporlar', 'sivi_a1.json')),
        encoding='utf-8'))
    kalem = next(k for k in d['kalemler'] if k['id'] == 'P3B3-07')
    assert not kalem['olcum'].startswith('once/sonra (aynı)'), (
        "sivi_a1.json 'olcum' metni hâlâ kanıtı JSON'a dayandırıyor")
    assert 'KAYDETMEDİ' in kalem['olcum']
