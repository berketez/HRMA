"""Sıvı motor nozul çıkış şeması bekçisi — 3-B egzoz (plume) veri sözleşmesi.

TEŞHİS (3 Ağustos 2026): motor_viz3d.js ``readNozzleExit`` plume'u yalnız
GERÇEK çıkış büyüklükleriyle çizer ve şu adresleri okur:

    nozzle_design.performance.{exit_pressure, ambient_pressure, exit_mach}
    gamma, chamber_temperature                     (üst düzey)
    altitude_performance.altitude_performance[0].exit_velocity
        -> bulunamazsa nozzle_design.performance.exit_velocity (yedek adres)

Hibrit motor bu şemayı yayımlıyordu; sıvı motor AYNI büyüklükleri irtifa
tablosunun deniz seviyesi satırında zaten hesapladığı hâlde HİÇ
yayımlamıyordu — sıvı sayfasında egzozun hiç çizilmemesinin nedeni buydu.

Bu dosya düzeltmeyi üç yönden kilitler:

1. **Şema birebir mi** — sonuçtaki adlar, motor_viz3d.js kaynağının fiilen
   okuduğu adlarla İKİ YÖNLÜ doğrulanır (JS yeniden adlandırırsa da düşer).
2. **Fiziksel tutarlı mı** — exit_mach > 1, 0 < exit_pressure < P_c,
   çıkış hızı fiziksel bantta ve irtifa tablosunun deniz seviyesi
   satırıyla BİREBİR aynı (ikinci bir hesap kaynağı türememeli).
3. **Uydurma yok mu** — deniz seviyesi satırı çözülemezse alanlar null +
   NOT_MODELLED beyanı döner; sayı icat edilmez.

Motor DOĞRUDAN kurulur ve ağa çıkmaz: ``propellant_data`` enjekte edilir
(v2.5.0 çevrimdışı garantisi, mevcut sıvı testleriyle aynı desen).
"""

from __future__ import annotations

import contextlib
import io
import math
import re
import warnings
from pathlib import Path

import pytest

from hrma.engines.liquid_rocket_engine import LiquidRocketEngine

warnings.filterwarnings('ignore')

_ROOT = Path(__file__).resolve().parents[1]
_MOTOR_VIZ3D_JS = _ROOT / 'hrma' / 'static' / 'js' / 'motor_viz3d.js'

#: Ağ yok: motora boş ama VAR olan itici verisi enjekte edilir.
OFFLINE_PROPELLANTS = {'rp1': {}, 'lox': {}}

#: liquid.html varsayılanlarıyla uyumlu taban ezmeler
#: (test_liquid_declarations_v2626 ile aynı desen).
BASE_OVERRIDES = dict(
    fuel_density=810, oxidizer_density=1141, mixture_ratio=2.3,
    combustion_efficiency=97, engine_cycle='gas_generator', feed_pressure=105,
    generator_gas_temp=900, turbine_expansion_ratio=4,
    injector_type='impinging', injector_pressure_drop=20,
    discharge_coefficient=0.7, contraction_ratio=4,
    characteristic_length=1.2, chamber_material='inconel_718',
    cooling_type='regenerative', nozzle_expansion_ratio=12,
    nozzle_type='bell_80', safety_factor=2.5,
)

BASE_CTOR = dict(thrust=25000, chamber_pressure=70, mixture_ratio=2.3,
                 fuel_type='rp1', oxidizer_type='lox',
                 propellant_data=OFFLINE_PROPELLANTS)


@pytest.fixture(scope='module')
def motor_ve_sonuc():
    """Gerçek sıvı hesap: motor bol tanı çıktısı bastığından sessiz koşulur."""
    with contextlib.redirect_stdout(io.StringIO()):
        engine = LiquidRocketEngine(overrides=dict(BASE_OVERRIDES),
                                    **BASE_CTOR)
        return engine, engine.calculate_performance()


@pytest.fixture(scope='module')
def sonuc(motor_ve_sonuc):
    return motor_ve_sonuc[1]


@pytest.fixture(scope='module')
def js_kaynak():
    return _MOTOR_VIZ3D_JS.read_text(encoding='utf-8')


# ---------------------------------------------------------------------------
# readNozzleExit'in Python aynası — JS'in çözümleme SIRASI birebir taklit
# edilir ki "alan var" ile "JS onu gerçekten bulur" ayrışmasın.
# ---------------------------------------------------------------------------

def _num(value, default):
    """motor_viz3d.js ``num``: sonlu sayı değilse default."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    if not math.isfinite(value):
        return default
    return float(value)


def _read_nozzle_exit_gibi(md):
    """readNozzleExit (motor_viz3d.js:341+) alan çözümlemesinin aynası.

    Yalnız GİRDİ okuma/eleme kısmı taklit edilir (jet Mach'ı, şok hücresi
    gibi türetimler JS'in işi). Dönen sözlük: çözülen değerler veya None
    (JS'te ``return null`` == plume çizilmez).
    """
    nan = float('nan')
    nozzle = md.get('nozzle_design') or {}
    perf = nozzle.get('performance') or {}
    comb = md.get('combustion_analysis') or {}
    comp = {}
    if isinstance(comb, dict):
        comp = (comb.get('compositions') or {}).get('chamber') or {}

    pe = _num(perf.get('exit_pressure'), nan)
    pa = _num(perf.get('ambient_pressure'), nan)
    me = _num(perf.get('exit_mach'), nan)
    gamma = _num(comp.get('gamma'), _num(md.get('gamma'), nan))
    tc = _num(md.get('chamber_temperature'), nan)

    ve = nan
    alt = None
    alt_wrap = md.get('altitude_performance')
    if isinstance(alt_wrap, dict):
        alt = alt_wrap.get('altitude_performance')
    if isinstance(alt, list) and alt:
        ve = _num(alt[0].get('exit_velocity'), nan)
    if not math.isfinite(ve):
        ve = _num(perf.get('exit_velocity'), nan)

    if (not math.isfinite(pe) or not math.isfinite(pa)
            or not math.isfinite(me) or not math.isfinite(gamma)
            or not math.isfinite(ve) or pe <= 0 or pa <= 0
            or me <= 1 or ve <= 0):
        return None
    return {'pe': pe, 'pa': pa, 'me': me, 'gamma': gamma, 'tc': tc, 've': ve}


# ---------------------------------------------------------------------------
# 1) Şema: alanlar var ve adlar motor_viz3d.js'in okuduklarıyla birebir
# ---------------------------------------------------------------------------

class TestSema:

    def test_nozzle_design_performance_blogu_var(self, sonuc):
        assert 'nozzle_design' in sonuc, (
            'sıvı sonucunda nozzle_design yok — plume sözleşmesi yayımlanmıyor')
        perf = sonuc['nozzle_design'].get('performance')
        assert isinstance(perf, dict)
        for alan in ('exit_pressure', 'ambient_pressure', 'exit_mach',
                     'exit_velocity'):
            assert alan in perf, f'nozzle_design.performance.{alan} eksik'
            assert isinstance(perf[alan], float), (
                f'{alan} JSON-taşınabilir float olmalı, '
                f'{type(perf[alan]).__name__} bulundu')

    def test_ust_duzey_gamma_ve_oda_sicakligi(self, sonuc):
        """readNozzleExit'in üst düzey adresleri: md.gamma, md.chamber_temperature."""
        assert math.isfinite(float(sonuc['gamma']))
        assert 1.0 < float(sonuc['gamma']) < 2.0
        assert math.isfinite(float(sonuc['chamber_temperature']))
        assert 1000.0 < float(sonuc['chamber_temperature']) < 5000.0
        # Şok hücresi aralığı için md.exit_diameter (metre) de okunur.
        assert 0.0 < float(sonuc['exit_diameter']) < 10.0

    def test_js_kaynagi_ayni_adresleri_okuyor(self, js_kaynak):
        """İKİ YÖNLÜ kilit: JS yeniden adlandırırsa bu test de düşer.

        Sözleşmenin öteki ucu koddan doğrulanır — motor_viz3d.js fiilen bu
        adları okumuyorsa, motorun yayımladığı şema havada kalır.
        """
        beklenen = (
            'md.nozzle_design',
            'perf.exit_pressure',
            'perf.ambient_pressure',
            'perf.exit_mach',
            'perf.exit_velocity',
            'md.gamma',
            'md.chamber_temperature',
            'md.altitude_performance.altitude_performance',
            'alt[0].exit_velocity',
        )
        for erisim in beklenen:
            assert erisim in js_kaynak, (
                f'motor_viz3d.js artık `{erisim}` okumuyor — plume '
                f'sözleşmesi değişti, motor şeması onunla eşitlenmeli')

    def test_beyan_alanlari_var(self, sonuc):
        """Her yeni çıktı alanı _basis/_source beyanı taşır (uydurma yasağı)."""
        perf = sonuc['nozzle_design']['performance']
        for alan in ('exit_pressure', 'ambient_pressure', 'exit_mach',
                     'exit_velocity'):
            beyan = perf.get(alan + '_basis')
            assert isinstance(beyan, str) and beyan.strip(), (
                f'{alan}_basis beyanı eksik')
        assert isinstance(perf.get('exit_state_source'), str)
        assert isinstance(sonuc['nozzle_design'].get('schema_source'), str)


# ---------------------------------------------------------------------------
# 2) Fiziksel tutarlılık + tek doğruluk kaynağı
# ---------------------------------------------------------------------------

class TestFizik:

    def test_readnozzleexit_aynasi_plume_cizer(self, sonuc):
        """JS'in kendi eleme mantığından geçince plume ÇİZİLİR (null değil)."""
        cozum = _read_nozzle_exit_gibi(sonuc)
        assert cozum is not None, (
            'readNozzleExit aynası null döndü — sıvı sonucu plume '
            'sözleşmesini hâlâ karşılamıyor')
        # Sözleşme fiziği: ses üstü çıkış, oda basıncının altında statik basınç.
        assert cozum['me'] > 1.0
        assert 0.0 < cozum['pe'] < float(sonuc['chamber_pressure'])
        # Deniz seviyesi ortamı: ISA 0 m (bar).
        assert cozum['pa'] == pytest.approx(1.01325, rel=1e-3)
        # Çıkış hızı fiziksel bantta ve enerji üst sınırının altında:
        # v_e < sqrt(2·cp·Tc), cp = γR/(γ-1), R = R_u/mw (Sutton Eq. 3-16).
        assert 500.0 < cozum['ve'] < 6000.0
        gamma = float(sonuc['gamma'])
        r_gas = 8314.462618 / float(sonuc['molecular_weight'])
        cp = gamma * r_gas / (gamma - 1.0)
        v_max = math.sqrt(2.0 * cp * float(sonuc['chamber_temperature']))
        assert cozum['ve'] < v_max

    def test_deger_kaynagi_deniz_seviyesi_satiri(self, sonuc):
        """Blok yeni hesap TÜRETMEZ: irtifa tablosu satır 0 ile birebir aynı.

        İki kaynak ayrışırsa aynı yanıt aynı büyüklük için iki farklı sayı
        taşır (v2.6.26'da defalarca ölçülen kusur sınıfı).
        """
        satir = sonuc['altitude_performance'][0]
        assert satir['altitude'] == 0
        perf = sonuc['nozzle_design']['performance']
        assert perf['exit_pressure'] == pytest.approx(
            float(satir['exit_pressure_bar']), rel=1e-12)
        assert perf['ambient_pressure'] == pytest.approx(
            float(satir['pressure']), rel=1e-12)
        assert perf['exit_mach'] == pytest.approx(
            float(satir['exit_mach_number']), rel=1e-12)
        assert perf['exit_velocity'] == pytest.approx(
            float(satir['exit_velocity']), rel=1e-12)

    def test_exit_velocity_cozumu_deniz_seviyesine_iner(self, sonuc):
        """Madde 3 (uyum): JS'in ve-çözüm sırası deniz seviyesi hızına ulaşır.

        Sıvıda üst düzey altitude_performance DÜZ LİSTE kalmak zorunda
        (liquid.html ``results.altitude_performance.length``/``.map`` ile
        tüketiyor; sözlük-sarmalı yapmak o paneli kırar). readNozzleExit bu
        durum için yedek adres tanımlar: perf.exit_velocity. Hangi dal
        çalışırsa çalışsın çözülen hız deniz seviyesi satırınınki OLMALI.
        """
        cozum = _read_nozzle_exit_gibi(sonuc)
        assert cozum is not None
        assert cozum['ve'] == pytest.approx(
            float(sonuc['altitude_performance'][0]['exit_velocity']),
            rel=1e-12)

    def test_liquid_html_liste_sozlesmesi_bozulmadi(self, sonuc):
        """liquid.html'in tükettiği düz liste yapısı korunur (gerileme bekçisi)."""
        alt = sonuc['altitude_performance']
        assert isinstance(alt, list) and len(alt) > 0
        assert isinstance(alt[0], dict)
        assert math.isfinite(float(alt[0]['exit_velocity']))


# ---------------------------------------------------------------------------
# 3) Uydurma yasağı: satır çözülemezse null + NOT_MODELLED, sayı icat edilmez
# ---------------------------------------------------------------------------

class TestNotModelled:

    @pytest.mark.parametrize('bozuk_girdi', [
        [],                                            # tablo boş
        None,                                          # tablo yok
        [{'altitude': 5000}],                          # ilk satır DS değil
        [{'altitude': 0, 'exit_pressure_bar': float('nan'),
          'pressure': 1.01325, 'exit_mach_number': 3.2,
          'exit_velocity': 2500.0}],                   # değer sonlu değil
        [{'altitude': 0, 'pressure': 1.01325,
          'exit_mach_number': 3.2, 'exit_velocity': 2500.0}],  # alan eksik
    ])
    def test_cozulmeyen_satir_null_ve_beyanli(self, motor_ve_sonuc,
                                              bozuk_girdi):
        engine = motor_ve_sonuc[0]
        blok = engine._nozzle_exit_design_block(bozuk_girdi)
        perf = blok['performance']
        for alan in ('exit_pressure', 'ambient_pressure', 'exit_mach',
                     'exit_velocity'):
            assert perf[alan] is None, (
                f'{alan} uyduruldu: satır çözülemezken {perf[alan]!r} basıldı')
        assert 'NOT_MODELLED' in perf['exit_state_basis']
        # JS aynası: null alanlarla plume ÇİZİLMEZ (sahte alev yasak).
        md = {'nozzle_design': blok, 'gamma': 1.2,
              'chamber_temperature': 3400.0}
        assert _read_nozzle_exit_gibi(md) is None

    def test_gercek_kosuda_not_modelled_yok(self, sonuc):
        """Taban motor çözülür bir tasarım: NOT_MODELLED dalına düşmemeli."""
        perf = sonuc['nozzle_design']['performance']
        assert 'NOT_MODELLED' not in str(perf.get('exit_state_basis', ''))
