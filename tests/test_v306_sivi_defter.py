# -*- coding: utf-8 -*-
"""V306/SIVI-DEFTER-HATA bekçileri (3.0.6 bakım hattı, 4 Kas 2026).

Düzeltilen hata: açık çevrimli (gaz jeneratörü / tap-off) sıvı motorda aynı
başlık debisi bir yerde ODA debisi (boğaz boyutlandırması), başka yerde
POMPALANAN TOPLAM (çevrim çözücüsü) sayılıyordu. Kanıt ve ölçümler:
docs/scofield/raw/OH/V306/sivi-defter/RAPOR.md (bu dosya kanıtı OKUMAZ;
beklenen değerler bağımsız yeniden kurulumdur).
"""
import math

import pytest


# ---------------------------------------------------------------------------
# Kalem 8 — rejeneratif sözde-kritik önbelleği sıra bağımsız
# ---------------------------------------------------------------------------
def test_k8_sozde_kritik_kova_degeri_ilk_basinca_bagli_degil(monkeypatch):
    """Önce (CI-SÜREÇ kalem 6 ölçümü): 60,24 bar sorulduktan sonra 60,00 bar
    için 199,722 K dönüyordu (temiz hesap 199,584 K). Sonra: kovanın değeri
    kova merkezinde, hangi basınç önce gelirse gelsin aynı."""
    from hrma.analysis import regen_cooling as rc
    akiskan = 'Methane'
    monkeypatch.setattr(rc, '_PSEUDOCRITICAL_CACHE', {})
    temiz = rc.pseudocritical_temperature(akiskan, 60.00e5)
    monkeypatch.setattr(rc, '_PSEUDOCRITICAL_CACHE', {})
    rc.pseudocritical_temperature(akiskan, 60.24e5)
    sonra = rc.pseudocritical_temperature(akiskan, 60.00e5)
    assert sonra == temiz
    # Kova içindeki her basınç aynı (merkez) değeri alır; merkez 60,00 bar.
    monkeypatch.setattr(rc, '_PSEUDOCRITICAL_CACHE', {})
    assert rc.pseudocritical_temperature(akiskan, 59.80e5) == temiz


def test_k8_mars_onbellek_gecmisinden_bagimsiz(monkeypatch):
    """CI-SÜREÇ senaryo E: kovalar kova İÇİNDE kaydırılmış basınçlarla
    doldurulup marş yeniden çözülünce sonuç bit-aynı kalmalı (önce bağıl
    5,9e-7 farklıydı)."""
    from hrma.analysis import regen_cooling as rc
    from tests.test_regen_cooling_supercritical import make_methane
    monkeypatch.setattr(rc, '_PSEUDOCRITICAL_CACHE', {})
    a = make_methane().solve()['summary']
    kovalar = sorted(k[1] for k in rc._PSEUDOCRITICAL_CACHE)
    assert kovalar, 'marş sözde-kritik sıcaklığı hiç sormadı'
    monkeypatch.setattr(rc, '_PSEUDOCRITICAL_CACHE', {})
    for kova in kovalar:
        rc.pseudocritical_temperature(
            'Methane', kova * rc.PSEUDOCRITICAL_CACHE_BIN_PA + 0.2e5)
    b = make_methane().solve()['summary']
    for alan in ('max_wall_hot_K', 'total_heat_W', 'coolant_exit_temp_K',
                 'total_pressure_drop_bar', 'fin_area_ratio_max'):
        assert a[alan] == b[alan], alan
    assert math.isfinite(a['max_wall_hot_K'])


# ---------------------------------------------------------------------------
# Ortak: gerçek sayfa gövdesi (/calculate_liquid, Flask test istemcisi)
# ---------------------------------------------------------------------------
G0 = 9.80665


def _post(govde):
    import contextlib
    import io
    import warnings
    from hrma.app import app
    app.config['TESTING'] = True
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()), \
            warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with app.test_client() as c:
            r = c.post('/calculate_liquid', json=govde)
    return r.status_code, (r.get_json() or {})


def _sayfa(**ek):
    from tests.support.kabul_sayfa_yukleri import SAYFA_YUKLERI
    g = dict(SAYFA_YUKLERI['liquid'])
    g.update(ek)
    g['include_plots'] = False
    return g


@pytest.fixture(scope='module')
def sivi_gg():
    kod, j = _post(_sayfa())
    assert kod == 200, str(j)[:400]
    # Sayfa gövdesi gaz jeneratörü çevrimidir (çevrim çözümü bunu söyler).
    assert _cyc(j)['engine_cycle'] == 'gas_generator'
    return j


def _cyc(j):
    return j['detailed_feed_system']['engine_cycle_solution']


# ---------------------------------------------------------------------------
# Kalem 2 — K5 debi defteri bağlandı
# ---------------------------------------------------------------------------
def test_k2_bogazdan_gecen_ana_oda_debisidir(sivi_gg):
    """Önce (taban dcf589ea9, örnek LOX/RP-1 25 kN GG): boğaz C_D·Pc·A_t/c*
    = 9,915018 = başlık total_mass_flow, çevrim ana oda 9,710033 + türbin
    0,204985. Sonra: boğaz = çevrimin ana oda debisi; toplam = ana oda +
    türbin."""
    j = sivi_gg
    d = j['mass_flow_ledger']
    cyc = _cyc(j)
    assert d['status'] == 'open_cycle_closed'
    assert cyc['status'] == 'converged'
    ana = cyc['main_chamber']['mdot_kg_s']
    # yayımlanan boğaz çapı, Pc, c*, C_D ile BAĞIMSIZ yeniden kurulum
    at = math.pi * float(j['throat_diameter']) ** 2 / 4.0
    bogaz = (j['throat_discharge_coefficient'] * j['chamber_pressure'] * 1e5
             * at / j['c_star'])
    assert bogaz == pytest.approx(ana, rel=1e-9)
    assert d['throat_mass_flow_kg_s'] == pytest.approx(ana, rel=1e-12)
    assert d['main_chamber_mass_flow_kg_s'] == pytest.approx(ana, rel=1e-12)
    assert d['turbine_mass_flow_kg_s'] == cyc['turbine_mdot_total_kg_s']
    assert d['total_propellant_mass_flow_kg_s'] == pytest.approx(
        ana + cyc['turbine_mdot_total_kg_s'], rel=1e-12)
    assert j['total_mass_flow'] == d['total_propellant_mass_flow_kg_s']
    assert cyc['mdot_total_pumped_kg_s'] == j['total_mass_flow']
    # türbin debisi gerçekten düşülmüş (bağlanmamış defterde pay 1,0 idi)
    assert ana < j['total_mass_flow'] * (1.0 - 1e-3)


def test_k2_motor_isp_toplam_debiden_bolusum_pompalardan(sivi_gg):
    j = sivi_gg
    assert j['isp_sea_level'] == pytest.approx(
        j['thrust'] / (j['total_mass_flow'] * G0), rel=1e-12)
    acc = j['cycle_isp_accounting']
    assert acc['applied'] is True
    assert acc['headline_isp_sl_s'] == pytest.approx(acc['engine_isp_sl_s'],
                                                     rel=1e-10)
    pompa = {p['propellant']: p['mdot_kg_s']
             for p in _cyc(j)['shafts'][0]['pumps']}
    assert j['oxidizer_flow'] == pytest.approx(pompa['oxidizer'], rel=1e-12)
    assert j['fuel_flow'] == pytest.approx(pompa['fuel'], rel=1e-12)
    assert j['oxidizer_flow'] + j['fuel_flow'] == pytest.approx(
        j['total_mass_flow'], rel=1e-12)
    # GG yakıtça zengin: pompalanan O/F ana O/F'in altında
    assert j['oxidizer_flow'] / j['fuel_flow'] < j['mixture_ratio']
    ds = j['design_summary']['masses']
    assert ds['propellant_mass_kg'] == pytest.approx(
        j['total_mass_flow'] * ds['burn_time_s'], rel=1e-12)


@pytest.mark.parametrize('cevrim', ['pressure_fed', 'staged_combustion',
                                    'expander'])
def test_k2_kapali_ve_basinc_beslemelide_defter_calismaz(cevrim):
    """Türbin gazı ana odaya dönen ya da türbinsiz çevrimde defter yok:
    blok yayımlanmaz, boğaz toplam debiyi geçirir (bit-aynılık kanıtı
    RAPOR'da md5 ile)."""
    ek = {'engine_cycle': cevrim}
    if cevrim == 'pressure_fed':
        ek['feed_pressure'] = 90
    if cevrim == 'expander':
        ek.update(fuel_type='lh2', mixture_ratio=6.0)
    kod, j = _post(_sayfa(**ek))
    assert kod == 200, str(j)[:300]
    assert 'mass_flow_ledger' not in j
    assert j['cycle_isp_accounting']['applied'] is False
    at = math.pi * float(j['throat_diameter']) ** 2 / 4.0
    bogaz = (j['throat_discharge_coefficient'] * j['chamber_pressure'] * 1e5
             * at / j['c_star'])
    assert bogaz == pytest.approx(j['total_mass_flow'], rel=1e-9)


# ---------------------------------------------------------------------------
# Kalem 3 — defterin açtığı beş tutarsızlık
# ---------------------------------------------------------------------------
def test_k3i_irtifa_tablosu_cf_ana_odanin_motor_itkisi_ayri(sivi_gg):
    j = sivi_gg
    at = math.pi * float(j['throat_diameter']) ** 2 / 4.0
    pc_pa = j['chamber_pressure'] * 1e5
    satirlar = j['altitude_performance']
    for s in satirlar:
        if s.get('thrust') is None:
            continue
        assert s['thrust_coefficient'] == pytest.approx(
            s['thrust_main_chamber'] / (pc_pa * at), rel=1e-9)
        assert s['thrust'] == pytest.approx(
            s['thrust_main_chamber'] + s['thrust_turbine_exhaust'],
            rel=1e-12)
        assert s['specific_impulse'] == pytest.approx(
            s['thrust'] / (j['total_mass_flow'] * G0), rel=1e-12)
        # hiçbir satır vakum kartını aşmaz
        assert s['specific_impulse'] <= j['isp_vacuum'] * (1 + 1e-12)
    s0 = satirlar[0]
    assert s0['altitude'] == 0
    assert s0['thrust'] == pytest.approx(j['thrust'], rel=1e-9)
    # Isp özdeşliği ana odanın: C_F·c*/(g0·C_D) = ana oda Isp'si
    kim = j['isp_identity']
    assert kim['status'] == 'CLOSED'
    assert kim['isp_sea_level_s'] == pytest.approx(
        j['mass_flow_ledger']['main_chamber_isp_sea_level_s'], rel=1e-12)
    assert abs(kim['residual_pct']) < 1e-9


def test_k3ii_yakit_pompa_cikisi_iki_panelde_tek_sayi(sivi_gg):
    """Önce (taslak): çevrim 76,594 ⟷ besleme paneli 77,057 bar."""
    j = sivi_gg
    dr = j['feed_system']['pressure_drops']
    assert _cyc(j)['pump_discharge_fuel_bar'] == pytest.approx(
        dr['pump_discharge_pressure_fuel'], rel=1e-12)
    assert _cyc(j)['pump_discharge_ox_bar'] == pytest.approx(
        dr['pump_discharge_pressure_ox'], rel=1e-12)


def test_k3iii_sigmayan_kanal_uyarisi_bir_kez_ve_son_durumun_sayisiyla():
    """Önce (taslak): warn.liquid.cooling_channels_exceed_fit_limit iki kez
    (c_ref 95,3 ⟷ 95,0 mm). Sonra: bir kez, yayımlanan boğazın sayısıyla."""
    kod, d = _post(dict(thrust=10000, chamber_pressure=100, mixture_ratio=2.5,
                        fuel_type='rp1', oxidizer_type='lox',
                        cooling_channels=80))
    assert kod == 200, str(d)[:300]
    assert d['mass_flow_ledger']['status'] == 'open_cycle_closed'
    fit = d['cooling_system']['channel_count_fit']
    uy = [w for w in d['input_warnings']
          if w.get('code') == 'warn.liquid.cooling_channels_exceed_fit_limit']
    assert len(uy) == 1
    assert uy[0]['params']['c_ref_mm'] == pytest.approx(
        fit['reference_circumference_mm'], abs=0.05)
    # genel: açık çevrimde aynı kodlu iki geometri/soğutma kaydı kalmaz
    kodlar = [w.get('code') for w in d['input_warnings']
              if isinstance(w, dict)]
    assert len(kodlar) == len(set(kodlar)), kodlar


def test_k3iv_metan_marsi_yayimlanan_bogazda_ve_sayisi_sinirli(monkeypatch):
    """Önce (taslak): metan rejeneratif marşı istek başına 5 kez kuruluyor ve
    kurulumların hangisinin yayımlandığı belli değildi. Sonra: iç geçişler
    marşı yeniden çözmez; marş yalnız boğaz değişince yeniden çözülür ve
    YAYIMLANAN marş (sonuncusu) yayımlanan boğazda kurulmuştur."""
    import hrma.analysis.regen_cooling as rcmod
    kurulan = []
    asil = rcmod.RegenCooling

    class Casus(asil):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            kurulan.append(self)
    monkeypatch.setattr(rcmod, 'RegenCooling', Casus)
    kod, d = _post(dict(thrust=10000, chamber_pressure=100, mixture_ratio=3.2,
                        fuel_type='methane', oxidizer_type='lox',
                        chamber_wall_thickness=1.0))
    assert kod == 200, str(d)[:300]
    fp = d['mass_flow_ledger']['fixed_point']
    assert len(kurulan) == fp['jacket_solves']
    assert len(kurulan) <= 4   # ölçüldü: döngü kazancı ~8e-5
    son = kurulan[-1]
    assert son.throat_diameter == pytest.approx(
        float(d['throat_diameter']), rel=1e-12)
    # bütün kurulumlar aynı cidarla (sessiz cidar denemesi yok)
    assert len({k.wall_thickness for k in kurulan}) == 1
    # Çevrim, YAYIMLANAN marşın ceket ΔP'siyle kapanmış olmalı: yakıt pompa
    # çıkışı (çevrim) = besleme bütçesi (ceket kalemi = yayımlanan ΔP).
    dr = d['feed_system']['pressure_drops']
    assert dr['fuel_line']['regen_jacket'] == \
        d['cooling_system']['cooling_pressure_drop']
    assert _cyc(d)['pump_discharge_fuel_bar'] == pytest.approx(
        dr['pump_discharge_pressure_fuel'], rel=1e-12)


def test_k3v_turbin_karti_defterden_sonra_kademe_sayisini_tasir(sivi_gg):
    tp = sivi_gg['detailed_feed_system']['turbopump_analysis']
    boy = sivi_gg['detailed_feed_system']['turbopump_sizing']['turbine']
    assert boy['status'] == 'modelled'
    assert tp['turbine']['stage_count'] == boy['stage_count']
