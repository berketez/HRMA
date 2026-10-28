# -*- coding: utf-8 -*-
"""KU q3 bekçileri — kitap uyum hızlı düzeltmeleri (sıvı motor, çevrim,
turbopompa, lüle künyeleri; 6 Eki 2026, karar §28).

Kalemler: H-1 (K20), H-6 (KU-26; yalnız beyan), H-10 (KU-29 metin), H-14 (lre film
metni), KU-K1/K3/K5/K6 künyeleri ve KC-14/KC-16 beyanları. Hiçbir bekçi
yayımlanan bir SAYIYI kilitlemez; sayı-değişmezlik kanıtı yayın izidir
(docs/scofield/raw/OH/KU/h-q3/rapor.md). Her bekçinin ters mutasyonu
docs/scofield/raw/OH/KU/h-q3/mutasyon.md'de.
"""
import ast
import contextlib
import inspect
import io
import pathlib
import re

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]


def _kaynak(goreli):
    return (KOK / goreli).read_text(encoding='utf-8')


def _duz(metin):
    """Satır kırılımından bağımsız arama için: yorum satırı başlarındaki
    ``#`` işaretleri ve bütün boşluk dizileri tek boşluğa indirgenir."""
    metin = re.sub(r'\n[ \t]*#[ \t]?', ' ', metin)
    return re.sub(r'\s+', ' ', metin)


# ---------------------------------------------------------------------------
# H-1 (K20): itici bütçesi künyesi + 0,85 dolum kesri tek tanım
# ---------------------------------------------------------------------------

def _imza_varsayilanlari(goreli, sinif, yontem, arguman):
    agac = ast.parse(_kaynak(goreli))
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.ClassDef) and dugum.name == sinif:
            for f in dugum.body:
                if isinstance(f, ast.FunctionDef) and f.name == yontem:
                    adlar = [a.arg for a in f.args.args]
                    varsayilan = f.args.defaults
                    ofset = len(adlar) - len(varsayilan)
                    return varsayilan[adlar.index(arguman) - ofset]
    raise AssertionError(f'{sinif}.{yontem} bulunamadı')


@pytest.mark.parametrize('yontem', ['__init__', 'from_oxidizer_mass'])
def test_h1_dolum_kesri_imzada_ciplak_literal_degil(yontem):
    d = _imza_varsayilanlari('hrma/analysis/tank_blowdown.py',
                             'N2OTankBlowdown', yontem,
                             'liquid_fill_fraction')
    assert not (isinstance(d, ast.Constant)
                and isinstance(d.value, (int, float))), (
        f'N2OTankBlowdown.{yontem} imzasında çıplak literal '
        f'{getattr(d, "value", None)!r} geri geldi; tek tanım '
        'hybrid_rocket_engine.TANK_FILL_FRACTION_DEFAULT (KU H-1)')


def test_h1_dolum_kesri_tek_tanimdan_cozuluyor():
    from hrma.analysis import tank_blowdown as tb
    from hrma.engines.hybrid_rocket_engine import TANK_FILL_FRACTION_DEFAULT
    assert (tb.resolve_liquid_fill_fraction(
        tb.LIQUID_FILL_FRACTION_DEFAULT_SENTINEL)
        == TANK_FILL_FRACTION_DEFAULT)
    for yontem in (tb.N2OTankBlowdown.__init__,
                   tb.N2OTankBlowdown.from_oxidizer_mass):
        v = inspect.signature(yontem).parameters[
            'liquid_fill_fraction'].default
        assert v is tb.LIQUID_FILL_FRACTION_DEFAULT_SENTINEL
    # Varsayılan yol ile açık değer yolu AYNI tankı kurar (sayı değişmedi).
    a = tb.N2OTankBlowdown.from_oxidizer_mass(10.0, use_coolprop=False)
    b = tb.N2OTankBlowdown.from_oxidizer_mass(
        10.0, liquid_fill_fraction=TANK_FILL_FRACTION_DEFAULT,
        use_coolprop=False)
    assert a.V == b.V and a.m_l == b.m_l and a.m_v == b.m_v


def test_h1_acik_none_sessiz_varsayilana_dusmuyor():
    from hrma.analysis.tank_blowdown import N2OTankBlowdown
    with pytest.raises(TypeError):
        N2OTankBlowdown(0.03, liquid_fill_fraction=None,
                        use_coolprop=False)


def test_h1_rezerv_kunyesi_duzeldi():
    from hrma.engines import liquid_rocket_engine as lre
    assert 'Huzel & Huang Ch. 8' not in lre.TANK_RESERVE_BASIS
    assert 'Huzel & Huang Ch. 8' not in lre.TANK_ULLAGE_BASIS
    assert 'UNSOURCED' in lre.TANK_RESERVE_BASIS
    assert 'Eq. 8-1 p. 332' in lre.TANK_RESERVE_BASIS
    assert 'pp. 399-401' in lre.TANK_RESERVE_BASIS


# ---------------------------------------------------------------------------
# H-6 (KU-26): yalnız BEYAN — fail-closed onarımı devir (test_scofield_sivi
# :239-269 beklentisi kapanmayan çevrimde sayısal Δh ister; kulvar kuralı
# gereği değiştirilmedi). Sayılar DEĞİŞMEDİ.
# ---------------------------------------------------------------------------

def _motor(**ek):
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
    o = {'expansion_ratio': 20.0, 'burn_time': 60.0,
         'feed_system_type': 'turbopump', 'engine_cycle': 'gas_generator'}
    o.update(ek)
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        m = LiquidRocketEngine(thrust=100000.0, chamber_pressure=80.0,
                               mixture_ratio=2.6, fuel_type='rp1',
                               oxidizer_type='lox', overrides=o)
        m.calculate_performance()
    return m


def _turbin_karti(m, kapanmaz):
    if kapanmaz:
        m._solve_cycle_balance = (
            lambda *a, **k: {'status': 'failed', 'reason': 'test yaması'})
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        r = m._analyze_detailed_feed_system()
    return r['turbopump_analysis']['turbine']


def test_h6_yedek_gaz_beyani_kunyede():
    from hrma.engines import liquid_rocket_engine as lre
    b = lre.TURBINE_FALLBACK_GAS_BASIS
    assert 'UNSOURCED FALLBACK' in b
    assert 'SP-8110' in b and 'Table III' in b
    assert '1100 K' in b


def test_h6_kapanmayan_cevrim_karti_yedegi_soyler():
    from hrma.engines import liquid_rocket_engine as lre
    t = _turbin_karti(_motor(), kapanmaz=True)
    assert lre.TURBINE_FALLBACK_GAS_BASIS in t['model'], (
        'çevrim kapanmadığında kart yedek gazın kaynaksız olduğunu '
        'söylemiyor (KU-26 beyanı)')


def test_h6_kapanan_cevrimde_kart_cozumden():
    from hrma.engines import liquid_rocket_engine as lre
    m = _motor()
    t = _turbin_karti(m, kapanmaz=False)
    cyc = m._solve_cycle_balance()
    assert cyc.get('status') == 'converged'
    turb0 = cyc['shafts'][0]['turbine']
    assert t['inlet_temperature'] == pytest.approx(turb0['inlet_temp_K'])
    assert lre.TURBINE_FALLBACK_GAS_BASIS not in t['model']


# ---------------------------------------------------------------------------
# KU-K3 / KU-K1: çevrim ve turbopompa künyeleri
# ---------------------------------------------------------------------------

def test_k3_cevrimde_yanlis_sutton_tablosu_yok():
    k = _kaynak('hrma/engines/cycle_power_balance.py')
    # Yalnız eski künye BİÇİMİ aranır ("Sutton 9th ed. Table 10-3"); düzeltme
    # notları tabloyu Türkçe "Tablo 10-3" diye anar.
    assert 'Sutton 9th ed. Table 10-3' not in k
    assert 'PR 16.4' not in k
    assert 's.15-17' not in k


def test_k3_verim_bandi_hatasi_dogru_kaynagi_aniyor():
    from hrma.engines.cycle_power_balance import _eta_gate
    with pytest.raises(ValueError) as e:
        _eta_gate("eta_pump", 1.5)
    assert 'NASA SP-8109 Table I' in str(e.value)
    assert 'Table 10-3' not in str(e.value)


def test_k3_npsh_orani_kunyesi():
    from hrma.analysis import turbopump_sizing as tps
    assert '1.08-2.14' in tps.NPSH_MARGIN_FACTOR_SOURCE
    assert 'between 1.1 and 1.6' not in tps.NPSH_MARGIN_FACTOR_SOURCE


def test_k3_hiz_orani_alan_tanimi_beyanli():
    from hrma.analysis.turbopump_sizing import size_turbine
    r = size_turbine(shaft_speed_rpm=30000.0, power_W=2.0e5,
                     mass_flow_kg_s=0.5, efficiency=0.6)
    assert 'SP-8110 Sec. 2.1.3' in r['_basis']


def test_k1_psi_ve_kanat_kunyesi_ayrildi():
    from hrma.analysis import turbopump_sizing as tps
    assert 'Eq. 6-4, p. 189' in tps.HEAD_COEFF_SOURCE
    assert 'NOT an SP-125 value' in tps.HEAD_COEFF_SOURCE
    assert 'p. 209' in tps.BLADE_COUNT_SOURCE


# ---------------------------------------------------------------------------
# KC-14 beyanları: geçerlilik notları (sayı değişmez)
# ---------------------------------------------------------------------------

_POMPA = dict(mass_flow_kg_s=20.0, pressure_rise_Pa=60e5,
              density_kg_m3=1000.0, vapor_pressure_Pa=3e3,
              tank_pressure_Pa=4e5)


@pytest.mark.parametrize('devir', [20000.0, 30000.0, 40000.0, 50000.0,
                                   60000.0])
def test_kc14_ns_gelistirme_bolgesi_notu(devir):
    from hrma.analysis import turbopump_sizing as tps
    r = tps.size_pump(shaft_speed_rpm=devir, **_POMPA)
    ns = r['pump']['specific_speed_per_stage_us']
    var = any(v['status'] == 'development_pump_region'
              for v in r['validity'])
    beklenen = (tps.NS_CENTRIFUGAL_FLIGHT_PROVEN_MAX_US < ns
                <= tps.NS_CENTRIFUGAL_MAX_US)
    assert var == beklenen, (ns, r['validity'])


def test_kc14_ns_bolgesi_en_az_bir_vakada_ateslenir():
    from hrma.analysis import turbopump_sizing as tps
    r = tps.size_pump(shaft_speed_rpm=40000.0, **_POMPA)
    assert any(v['status'] == 'development_pump_region'
               for v in r['validity'])


def test_kc14_nss_40000_ustu_notu_ve_sayi_ayni():
    from hrma.analysis import turbopump_sizing as tps
    yok = tps.size_pump(**_POMPA)  # varsayılan hedef 30 000
    assert not any(v['status'] == 'above_recommended_practice'
                   for v in yok['validity'])
    var = tps.size_pump(target_suction_specific_speed_us=50000.0, **_POMPA)
    assert any(v['status'] == 'above_recommended_practice'
               for v in var['validity'])


def test_kc14_turbin_mimarisi_beyani():
    from hrma.analysis import turbopump_sizing as tps
    assert 'ARCHITECTURE DECLARATION' in tps.TURBINE_SOURCE
    assert 'velocity-compounded' in tps.TURBINE_SOURCE
    assert '2 % head-drop' in tps.NSS_SOURCE


# ---------------------------------------------------------------------------
# KU-K5 / KU-K6 / KC-16: soğutucu hız, lüle ve ayrılma künyeleri/beyanları
# ---------------------------------------------------------------------------

def test_k5_sogutucu_hiz_kunyesi():
    k = _kaynak('hrma/engines/liquid_rocket_engine.py')
    assert '30-60 m/s ortası' not in k
    assert '§3.1.1.5.3 s. 62' in k


def test_k6_rao_aci_sekli_dogru():
    k = _kaynak('hrma/engines/nozzle_design.py')
    assert 'Huzel & Huang, NASA SP-125, Fig. 4-15.' not in k
    assert 'Huzel & Huang Fig. 4-15' not in k
    assert '(NASA SP-125), Eş. 4-7 ve Fig. 4-15' not in k
    assert 'Şekil 4-14 (s. 91)' in k


def test_kc16_ayrilma_beyanlari():
    from hrma.flow.separation import SEPARATION_NOT_MODELLED as nm
    for anahtar in ('stark_criterion', 'separation_margin_band',
                    'hot_gas_conservatism', 'fss_rss_distinction'):
        assert anahtar in nm and nm[anahtar]
    assert 'RSS' in nm['fss_rss_distinction']
    assert 'π/(3·M_sep)' in nm['stark_criterion']
    assert 'SP-8120' in nm['separation_margin_band']


def test_kc16_ayrilma_beyanlari_cfd_ile_cakismiyor():
    from hrma.cfd import CFD_NOT_MODELLED
    from hrma.flow.separation import SEPARATION_NOT_MODELLED
    assert not set(SEPARATION_NOT_MODELLED) & set(CFD_NOT_MODELLED)


# ---------------------------------------------------------------------------
# H-14 (lre film metni) ve H-10 (RL10 ν genellemesi)
# ---------------------------------------------------------------------------

def test_h14_rp1_film_buharlasma_kredisi_metni():
    k = _kaynak('hrma/engines/liquid_rocket_engine.py')
    assert 'vaporization credit' not in k
    assert 'supercritical chamber pressure there is no separate' in k


def test_h10_rl10_genellemesi_kalkti():
    # Denetim şartı (6 Eki): negatif iddia satır kırılımından bağımsız.
    # Eski iddia yalnız TIRNAK içinde (tarihçe olarak) kalabilir.
    k = _duz(_kaynak('tests/test_turbopompa.py'))
    assert not re.search(
        r'(?<!")gerçek darbe türbinleri optimumun hemen altında çalışır', k)
    assert 'genelleme değildir' in k


# ---------------------------------------------------------------------------
# Denetim şartları turu (6 Eki 2026): Ş-1..Ş-3 ve bekçi boşlukları A1/H/I/J
# ---------------------------------------------------------------------------

def test_s1_sp8109_ns_kunyesi_basili_sayfa_7():
    """SP-8109 "450 to 2100 ... Mark 14 ... 3000" cümlesi PDF s. 19'da,
    basılı s. 7'dedir (PDF s. 18 altbilgisi 6, s. 20 altbilgisi 8)."""
    from hrma.analysis import turbopump_sizing as tps
    k = _duz(_kaynak('hrma/analysis/turbopump_sizing.py'))
    assert 'SP-8109 p. 8' not in k and 'SP-8109 s. 8' not in k
    assert 'SP-8109 p. 7' in tps.NS_SOURCE
    r = tps.size_pump(shaft_speed_rpm=40000.0, **_POMPA)
    notlar = [v['message'] for v in r['validity']
              if v['status'] == 'development_pump_region']
    assert notlar and all('SP-8109 p. 7' in n for n in notlar)


def test_s2_gg_hiz_orani_yorumu_dar():
    k = _duz(_kaynak('tests/test_turbopompa.py'))
    assert "GG türbinlerinin tasarım U/C0'ı 0,11-0,21'dir" not in k
    assert 'Mark 3/4 GG türbinleri 0,39-0,42' in k
    assert 's. 15: iki sıralı GG/tap-off 0,10-0,40' in k


def test_s3_film_ceket_butcesi_kunyesi_hh_ch4_degil():
    from hrma.engines import liquid_rocket_engine as lre
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        m = lre.LiquidRocketEngine(
            thrust=25000.0, chamber_pressure=50.0, mixture_ratio=2.6,
            fuel_type='rp1', oxidizer_type='lox', cooling_type='regenerative',
            overrides={'film_cooling_percent': 10.0})
        m.calculate_nozzle_geometry()
        c = m.calculate_cooling_requirements()
    b = _duz(c['coolant_flow_rate_basis'])
    assert 'upstream of the jacket (Huzel & Huang' not in b
    # v3.0.1 T-ÇAPA-B: V301/L-B SV-08 künyeyi yeniden yazdı (film çekirdeğe
    # EK; "HRMA accounting, not a Huzel & Huang Ch. 4 model"). Kütle
    # korunumu iddiası artık şu cümleyle söyleniyor (ölçüldü, 117d704da).
    assert 'jacket + film can never exceed the total fuel flow' in b
    assert 'not a Huzel & Huang Ch. 4 model' in b
    assert 'SP-125 Eq. 4-33, p. 115' in b
    k = _duz(_kaynak('hrma/engines/liquid_rocket_engine.py'))
    # Büyük kaynak dizgesinin pytest farkı basılmasın diye bool'a indirgenir.
    for eski in ('(enerji dengesi; Huzel & Huang Ch. 4 film soğutma',
                 'AYIRIR (Huzel & Huang Ch. 4)'):
        geri_geldi = eski in k
        assert not geri_geldi, f'eski K15 künyesi geri geldi: {eski!r}'


def test_a1_dolum_kesri_cozucusunde_sayisal_literal_yok():
    agac = ast.parse(_kaynak('hrma/analysis/tank_blowdown.py'))
    govde = [d for d in ast.walk(agac)
             if isinstance(d, ast.FunctionDef)
             and d.name == 'resolve_liquid_fill_fraction']
    assert len(govde) == 1
    sayilar = [d.value for d in ast.walk(govde[0])
               if isinstance(d, ast.Constant)
               and isinstance(d.value, (int, float))
               and not isinstance(d.value, bool)]
    assert not sayilar, (
        f'resolve_liquid_fill_fraction gövdesinde sayısal literal {sayilar}; '
        'değer yalnız TANK_FILL_FRACTION_DEFAULT tek tanımından gelir')


def test_h_turbin_kunyesinde_dogrulama_iddiasi_yok():
    from hrma.analysis import turbopump_sizing as tps
    assert 'validated against' not in _duz(tps.TURBINE_SOURCE)


def _belge_disi_dizgeler(goreli):
    agac = ast.parse(_kaynak(goreli))
    belge = set()
    for d in ast.walk(agac):
        if isinstance(d, (ast.Module, ast.ClassDef, ast.FunctionDef,
                          ast.AsyncFunctionDef)) and d.body:
            ilk = d.body[0]
            if isinstance(ilk, ast.Expr) and isinstance(ilk.value,
                                                        ast.Constant):
                belge.add(id(ilk.value))
    return [d.value for d in ast.walk(agac)
            if isinstance(d, ast.Constant) and isinstance(d.value, str)
            and id(d) not in belge]


def test_i_nf1d_yayimlanan_dizgelerde_hh_ch1_yok():
    """λ/sürtünme künyeleri (lambda_note, friction_basis, note) dahil
    nf1d'nin bütün yayımlanabilir dizgeleri; yorum ve docstring hariç."""
    for d in _belge_disi_dizgeler('hrma/analysis/nozzle_flow_1d.py'):
        assert 'Huzel & Huang Ch. 1' not in _duz(d), d[:120]


def test_j_yakinsak_aci_kunyesi_standart_hh_ch4_degil():
    from hrma.engines import liquid_rocket_engine as lre
    b = _duz(lre.CONVERGENT_HALF_ANGLE_BASIS)
    assert not ('standard' in b and 'Huzel & Huang Ch. 4' in b)
    assert 'p. 89' in b
