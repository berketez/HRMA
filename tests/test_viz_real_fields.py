"""Görselleştirme alanları GERÇEKTEN hesaplanıyor mu? (2026-07-19 denetimi)

Berke kuralı: hiçbir panel kaldırılmayacak, hepsi gerçek hesapla beslenecek.
Bu dosya, denetimde bulunan uydurma alanların geri gelmesini engeller:

  1. "Combustion Efficiency" göstergesi HER koşuda %95 idi
     (`combustion_data.get('combustion_efficiency', 0.95)` — çözücü bu
     anahtarı hiç üretmiyor).
  2. Nozul Mach konturu uydurma bir alan yasası + ıraksayan Newton
     iterasyonundan geliyordu (M ~ 2000 gibi imkânsız değerler).
  3. Cidar ısı akısı alanı Bartz'ı hiç görmüyordu; sabit bir tabana keyfi
     Gauss + üstel çarpanlar ve 5 MW/m² üstüne "termal kaçış" x1.5
     uygulanıyordu.
  4. Pc x O/F Isp yüzeyi termokimya çözmüyor, sabit base_isp'yi uydurma
     şekil fonksiyonlarıyla çarpıyordu (base_isp 2x -> yüzey tam 2x).

Ölçüt her testte aynı: GİRDİYİ DEĞİŞTİR, ÇIKTININ DEĞİŞTİĞİNİ GÖSTER.
"""

import json
import warnings

import numpy as np
import pytest

warnings.filterwarnings('ignore')

from hrma.engines.combustion_analysis import CombustionAnalyzer
from hrma.visualization.visualization import (
    create_combustion_analysis_plots,
    create_nozzle_mach_area_ratio_contour,
    create_wall_heat_flux_waterfall_plot,
    create_chamber_pressure_mixture_ratio_3d_surface,
    create_showerhead_with_tooltips,
    create_swirl_injector,
    create_improved_motor_cross_section,
)
from hrma.visualization.advanced_results import create_cea_style_results


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------

def _fig(js):
    assert isinstance(js, str), 'figür üreticisi JSON string döndürmeli'
    return json.loads(js)


def _traces(fig, **match):
    out = []
    for tr in fig['data']:
        if all(tr.get(k) == v for k, v in match.items()):
            out.append(tr)
    return out


def _z(trace):
    """z ızgarasını float diziye çevirir (None -> NaN)."""
    return np.array([[np.nan if v is None else v for v in row]
                     for row in trace['z']], dtype=float)


@pytest.fixture(scope='module')
def analyzer():
    return CombustionAnalyzer(memoize=True)


NOZZLE_INPUT = {'throat_area': 0.001, 'nozzle_length': 0.1,
                'expansion_ratio': 16}

HEAT_INPUT = {'burn_time': 30, 'chamber_length': 0.5, 'nozzle_length': 0.1,
              'base_heat_flux': 2e6, 'critical_heat_flux': 4.0,
              'throat_area': 0.001, 'expansion_ratio': 16,
              'chamber_pressure': 30.0}


# ---------------------------------------------------------------------------
# (a) Yanma verimi göstergesi girdiye göre DEĞİŞİR
# ---------------------------------------------------------------------------

def test_yanma_verimi_gostergesi_of_ile_degisir(analyzer):
    values = []
    for of in (3.0, 6.0, 9.0):
        res = analyzer.analyze_combustion({'htpb': 100.0}, 'N2O', of, 20.0)
        fig = _fig(create_combustion_analysis_plots(res))
        gauges = _traces(fig, type='indicator')
        assert gauges, 'verim göstergesi paneli kaldırılmış olamaz'
        values.append(gauges[0]['value'])
    assert len(set(round(v, 6) for v in values)) == len(values), (
        f'Yanma verimi göstergesi O/F ile degismiyor: {values} '
        '(eski surum her kosuda %95 gosteriyordu)')
    assert all(0.0 < v <= 100.0 for v in values), values
    # Eski sabit deger geri gelmemeli
    assert not all(abs(v - 95.0) < 1e-9 for v in values)


def test_yanma_panosunun_bos_ceyrekleri_gercek_veriyle_dolar(analyzer):
    res = analyzer.analyze_combustion({'htpb': 100.0}, 'N2O', 6.0, 20.0)
    fig = _fig(create_combustion_analysis_plots(res))

    bars = _traces(fig, type='bar')
    assert bars, 'denge bilesimi cubuklari cizilmeli (cozucu compositions)'
    assert len(bars[0]['x']) >= 3
    assert all(0.0 < y <= 1.0 for y in bars[0]['y'])

    temps = [t for t in fig['data']
             if t.get('name') == 'Temperature' and t.get('type') == 'scatter']
    assert temps, 'istasyon sicakliklari cizilmeli (cozucu conditions)'
    ys = temps[0]['y']
    assert len(ys) == 3 and ys[0] > ys[1] > ys[2], (
        f'Chamber > Throat > Exit beklenir: {ys}')


def test_of_taramasi_gercek_denge_cozumu(analyzer):
    res = analyzer.analyze_combustion({'htpb': 100.0}, 'N2O', 6.0, 20.0)
    prop = {'fuel_composition': {'htpb': 100.0}, 'oxidizer_type': 'N2O',
            'chamber_pressure': 20.0, 'analyzer': analyzer}
    fig = _fig(create_combustion_analysis_plots(res, propellant=prop))
    sweep = [t for t in fig['data'] if t.get('name') == 'Isp vs O/F']
    assert sweep, 'O/F taramasi cizilmeli'
    isp = sweep[0]['y']
    assert len(isp) >= 5 and max(isp) > min(isp) + 5.0, isp


def test_of_taramasi_kimlik_yoksa_uydurmaz(analyzer):
    """Propellant kimligi HICBIR yoldan bilinmiyorsa parabol UYDURULMAZ.

    2026-07-22 guncellemesi: analyze_combustion artik kosunun girdi kimligini
    sonuca 'inputs' blogu olarak yaziyor ve figur, cagiran ayrica kimlik
    gecirmediginde taramayi ORADAN kuruyor (app.py cagrilari kimlik
    tasimiyordu; ceyrek bu yuzden sahada HEP bos kaliyordu). Dolayisiyla
    kimliksizlik senaryosu artik 'inputs' blogunun da bulunmadigi durumdur —
    eski/eksik sozluk. Uydurma yasagi orada aynen gecerlidir.
    """
    res = analyzer.analyze_combustion({'htpb': 100.0}, 'N2O', 6.0, 20.0)
    kimliksiz = {k: v for k, v in res.items() if k != 'inputs'}
    fig = _fig(create_combustion_analysis_plots(kimliksiz))
    assert not [t for t in fig['data'] if t.get('name') == 'Isp vs O/F']
    notes = ' '.join(a.get('text', '') for a in fig['layout']['annotations'])
    assert 'not available' in notes


def test_of_taramasi_kimlik_cozucu_ciktisindan_kurulur(analyzer):
    """Cagiran kimlik gecirmese bile cozucu ciktisindaki 'inputs' yeter.

    Saha bulgusu (2026-07-22): /calculate ve /calculate_advanced figure
    kimlik gecirmiyordu; panel 'not available' notuyla bos kaliyordu.
    """
    res = analyzer.analyze_combustion({'htpb': 100.0}, 'N2O', 6.0, 20.0)
    assert res.get('inputs', {}).get('oxidizer_type') == 'N2O'
    fig = _fig(create_combustion_analysis_plots(res))
    sweep = [t for t in fig['data'] if t.get('name') == 'Isp vs O/F']
    assert sweep, 'kimlik cozucu ciktisindan kurulmaliydi'
    assert len(sweep[0]['y']) >= 5


# ---------------------------------------------------------------------------
# (b) Mach profili: yakinsakta M<1, bogazda ~1, iraksakta M>1
# ---------------------------------------------------------------------------

def test_mach_profili_fiziksel_daldadir():
    fig = _fig(create_nozzle_mach_area_ratio_contour(NOZZLE_INPUT))
    cont = _traces(fig, type='contour')
    assert cont, 'Mach konturu paneli kaldirilmis olamaz'
    z = _z(cont[0])
    center = z[z.shape[0] // 2]          # eksen cizgisi (r = 0)
    assert np.isfinite(center).all()

    i_throat = int(np.argmin(np.abs(center - 1.0)))
    assert abs(center[i_throat] - 1.0) < 1e-6, center[i_throat]
    assert (center[:i_throat] < 1.0).all(), 'yakinsak bolge subsonik olmali'
    assert (center[i_throat + 1:] > 1.0).all(), 'iraksak bolge supersonik olmali'
    assert np.all(np.diff(center) > 0), 'M eksende monoton artmali'


def test_mach_cikisi_analitik_izentropik_cozumle_uyusur():
    from scipy.optimize import brentq
    gamma = 1.20                       # figurun belgeli varsayimi
    eps = NOZZLE_INPUT['expansion_ratio']

    def area_ratio(m):
        return (1.0 / m) * ((2.0 / (gamma + 1.0))
                            * (1.0 + (gamma - 1.0) / 2.0 * m * m)
                            ) ** ((gamma + 1.0) / (2.0 * (gamma - 1.0)))

    expected = brentq(lambda m: area_ratio(m) - eps, 1.0001, 20.0)
    fig = _fig(create_nozzle_mach_area_ratio_contour(NOZZLE_INPUT))
    center = _z(_traces(fig, type='contour')[0])
    center = center[center.shape[0] // 2]
    assert abs(float(center[-1]) - expected) < 0.02, (
        f'cikis Mach {center[-1]:.3f} != izentropik {expected:.3f} '
        '(eski surum ~2000 kat sapiyordu)')
    assert float(np.nanmax(center)) < 20.0, 'fiziksel olmayan Mach degeri'


def test_mach_konturu_genisleme_oranina_duyarli():
    exits, walls = [], []
    for eps in (8, 16, 40):
        payload = dict(NOZZLE_INPUT, expansion_ratio=eps)
        fig = _fig(create_nozzle_mach_area_ratio_contour(payload))
        center = _z(_traces(fig, type='contour')[0])
        exits.append(float(np.nanmax(center[center.shape[0] // 2])))
        wall = [t for t in fig['data'] if t.get('name') == 'Nozzle wall'][0]
        walls.append(max(wall['y']))
    assert exits[0] < exits[1] < exits[2], exits
    # Duvar artik gercek yaricapa olceklenir (eski surum +-50 mm sabitti)
    assert walls[0] < walls[1] < walls[2], walls


def test_mach_konturu_varsayimlari_baslikta_bildirir():
    fig = _fig(create_nozzle_mach_area_ratio_contour(NOZZLE_INPUT))
    title = fig['layout']['title']['text']
    assert 'Assumed' in title, 'verilmeyen gaz hali ETIKETLENMELI'
    assert 'NASA-STD-5012' not in title, (
        'uygulanmayan standart referansi geri gelmis')


# ---------------------------------------------------------------------------
# (c) Isi akisi: Pc ile olceklenir ve bogazda tepe yapar
# ---------------------------------------------------------------------------

def _design_flux(fig):
    line = [t for t in fig['data']
            if str(t.get('name', '')).startswith('Design flux')]
    assert line, 'Bartz tasarim akisi cizgisi cizilmeli'
    return np.asarray(line[0]['y'], float), np.asarray(line[0]['z'], float)


def test_isi_akisi_bogazda_tepe_yapar():
    fig = _fig(create_wall_heat_flux_waterfall_plot(HEAT_INPUT))
    x_mm, q = _design_flux(fig)
    throat = [t for t in fig['data'] if t.get('name') == 'Throat station'][0]
    x_throat = throat['y'][0]
    assert abs(float(x_mm[int(np.argmax(q))]) - float(x_throat)) < 5.0, (
        'maksimum aki bogaz istasyonunda olmali')
    assert float(np.max(q)) > float(q[0]) * 1.5


def test_isi_akisi_oda_basinciyla_olceklenir():
    peaks = {}
    for pc in (15.0, 30.0, 60.0):
        fig = _fig(create_wall_heat_flux_waterfall_plot(
            dict(HEAT_INPUT, chamber_pressure=pc)))
        peaks[pc] = float(np.max(_design_flux(fig)[1]))
    assert peaks[15.0] < peaks[30.0] < peaks[60.0], peaks
    # Bartz: h_g ~ Pc^0.8 -> tepe aki orani (60/15)^0.8 = 3.03
    ratio = peaks[60.0] / peaks[15.0]
    assert 2.7 < ratio < 3.4, f'Bartz Pc^0.8 olcegi beklenir, oran {ratio:.2f}'


def test_isi_akisi_zamanla_azalir_ve_kacis_carpani_yok():
    fig = _fig(create_wall_heat_flux_waterfall_plot(
        dict(HEAT_INPUT, cooling_type='regenerative', material='copper')))
    surf = [t for t in fig['data'] if t.get('type') == 'surface'
            and str(t.get('name', '')).startswith('Convective')]
    assert surf, 'hesaplanan aki yuzeyi kaldirilmis olamaz'
    z = _z(surf[0])
    row = z[int(np.nanargmax(z[:, 0]))]
    row = row[np.isfinite(row)]
    assert np.all(np.diff(row) <= 1e-9), (
        'cidar isindikca q_conv AZALIR; eski surum %50 artiriyordu')
    names = ' '.join(str(t.get('name', '')) for t in fig['data'])
    assert 'Runaway' not in names and 'runaway' not in names


def test_isi_akisi_geometri_yoksa_uydurmaz():
    """app.py bugun bogaz geometrisi gecirmiyor: panel KALIR, aki UYDURULMAZ."""
    fig = _fig(create_wall_heat_flux_waterfall_plot(
        {'burn_time': 30, 'chamber_length': 0.5, 'nozzle_length': 0.1,
         'base_heat_flux': 2e6, 'critical_heat_flux': 4.0}))
    assert not [t for t in fig['data']
                if str(t.get('name', '')).startswith('Convective')]
    text = ' '.join(a.get('text', '') for a in fig['layout']['annotations'])
    assert 'not available' in text
    # Kullanicinin girdigi referans duzlemleri KALIR (girdi olarak etiketli)
    names = [str(t.get('name', '')) for t in fig['data']]
    assert any('input' in n for n in names), names


# ---------------------------------------------------------------------------
# (d) 3D Isp yuzeyi yakit ciftine gore degisir, base_isp ile olceklenmez
# ---------------------------------------------------------------------------

def _surface_z(engine_data):
    fig = _fig(create_chamber_pressure_mixture_ratio_3d_surface(engine_data))
    surf = _traces(fig, type='surface')
    assert surf, 'Isp yuzeyi paneli kaldirilmis olamaz'
    return _z(surf[0])


def test_isp_yuzeyi_yakit_ciftine_gore_degisir():
    base = {'base_isp': 300, 'optimal_of_ratio': 3.5,
            'optimal_chamber_pressure': 50, 'oxidizer_type': 'N2O'}
    z_htpb = _surface_z(dict(base, fuel_type='htpb'))
    z_paraffin = _surface_z(dict(base, fuel_type='paraffin'))
    z_lox = _surface_z(dict(base, fuel_type='pmma', oxidizer_type='LOX'))
    assert np.isfinite(z_htpb).any()
    assert not np.allclose(z_htpb, z_paraffin, equal_nan=True), (
        'yuzey yakit kimyasini gormeli')
    assert not np.allclose(z_htpb, z_lox, equal_nan=True), (
        'yuzey oksitleyiciyi gormeli')


def test_isp_yuzeyi_base_isp_ile_olceklenmez():
    base = {'optimal_of_ratio': 3.5, 'optimal_chamber_pressure': 50,
            'fuel_type': 'htpb', 'oxidizer_type': 'N2O'}
    z1 = _surface_z(dict(base, base_isp=300))
    z2 = _surface_z(dict(base, base_isp=600))
    assert np.allclose(z1, z2, equal_nan=True), (
        'base_isp yuzeyi olcekliyor — eski uydurma davranis geri gelmis')


def test_isp_yuzeyi_o_f_ile_tepe_yapar():
    z = _surface_z({'fuel_type': 'htpb', 'oxidizer_type': 'N2O',
                    'base_isp': 300, 'optimal_of_ratio': 3.5,
                    'optimal_chamber_pressure': 50})
    col = z[:, -1]                       # en yuksek Pc sutunu, O/F boyunca
    col = col[np.isfinite(col)]
    assert len(col) >= 5
    assert int(np.argmax(col)) not in (0,), (
        'O/F ekseninde ic bir optimum beklenir')


# ---------------------------------------------------------------------------
# Enjektor alanlari: delik basi debi, swirl olculeri, pintle geometrisi
# ---------------------------------------------------------------------------

def test_delik_basi_debi_gercek_debiden_gelir():
    import re
    for mdot, n in ((0.5, 20), (1.2, 20), (5.0, 73)):
        fig = _fig(create_showerhead_with_tooltips(
            {'n_holes': n, 'hole_diameter': 1.5, 'exit_velocity': 30,
             'mdot_ox': mdot}))
        hover = [t['hovertemplate'] for t in fig['data']
                 if 'hovertemplate' in t and 'Mass flow' in t['hovertemplate']]
        assert hover
        got = float(re.search(r'Mass flow: ([\d.]+) g/s', hover[0]).group(1))
        assert abs(got - mdot / n * 1000.0) < 0.01, (got, mdot, n)


def test_delik_basi_debi_yoksa_sayi_uydurmaz():
    import re
    fig = _fig(create_showerhead_with_tooltips(
        {'n_holes': 20, 'hole_diameter': 1.5}))
    hover = [t['hovertemplate'] for t in fig['data']
             if 'hovertemplate' in t and 'Mass flow' in t['hovertemplate']][0]
    assert 'not available' in hover
    assert re.search(r'Mass flow: [\d.]+ g/s', hover) is None


def test_plaka_capi_sabit_100mm_degil():
    fig_a = _fig(create_showerhead_with_tooltips(
        {'n_holes': 20, 'hole_diameter': 1.5, 'chamber_diameter': 0.15}))
    fig_b = _fig(create_showerhead_with_tooltips(
        {'n_holes': 20, 'hole_diameter': 1.5, 'chamber_diameter': 0.30}))

    def plate(fig):
        tr = [t for t in fig['data'] if t.get('name') == 'Injector plate'][0]
        return max(tr['x'])

    assert abs(plate(fig_a) - 75.0) < 0.1
    assert abs(plate(fig_b) - 150.0) < 0.1

    fig_c = _fig(create_showerhead_with_tooltips(
        {'n_holes': 20, 'hole_diameter': 1.5}))
    hov = [t for t in fig_c['data']
           if t.get('name') == 'Injector plate'][0]['hovertemplate']
    assert 'not reported' in hov, 'olculemeyen cap sayi olarak SUNULMAZ'


def test_swirl_cikis_orifisi_gercek_alandan_gelir():
    import re
    from hrma.utils.injector_design import InjectorDesign
    seen = []
    for mdot in (0.5, 3.0):
        inj = InjectorDesign(mdot_ox=mdot, chamber_pressure=20.0,
                             injector_type='swirl')
        inj.set_swirl_params()
        res = inj.calculate()
        fig = _fig(create_swirl_injector(res))
        texts = [a.get('text', '') for a in fig['layout']['annotations']]
        match = [re.search(r'd_exit = ([\d.]+) mm', t) for t in texts]
        match = [m for m in match if m]
        assert match, texts
        got = float(match[0].group(1))
        expected = 2.0 * np.sqrt(res['exit_orifice_area'] / np.pi)
        assert abs(got - expected) < 0.02, (got, expected)
        seen.append(got)
    assert seen[0] != seen[1], (
        f'6 kat debide olcu ayni kalmis: {seen} (eski surum hep 10.5 mm)')


def test_swirl_bildirilmeyen_olculer_not_reported_der():
    """v2.6.26 guncellemesi: swirl oda capi ARTIK GERCEKTEN hesaplaniyor.

    Eski surumde cozucu D_chamber uretmiyordu ve figur durustce
    'not reported' diyordu; bu test o davranisi kilitliyordu. v2.6.26'da
    swirl_chamber_diameter kullanici girdisinden ya da varsayilan
    SWIRL_CHAMBER_D_RATIO·d_o oranindan hesaplanip kaynagiyla birlikte
    (swirl_chamber_d_source: user/default_ratio) raporlaniyor — yani
    'not reported' demek artik YANLIS olurdu. Test yeni gercege gore
    guncellendi; hala bildirilmeyen D_outer icin eski kontrol KORUNDU.
    """
    from hrma.utils.injector_design import (InjectorDesign,
                                            SWIRL_CHAMBER_D_RATIO)
    inj = InjectorDesign(mdot_ox=1.0, chamber_pressure=20.0,
                         injector_type='swirl')
    inj.set_swirl_params()
    res = inj.calculate()
    fig = _fig(create_swirl_injector(res))
    texts = ' '.join(a.get('text', '') for a in fig['layout']['annotations'])
    # Govde disi capi hala modellenmiyor: durust kalmali
    assert 'D_outer: not reported' in texts

    # Oda capi: kullanici girmedi -> varsayilan oran, kaynagi soyleniyor
    assert res['swirl_chamber_d_source'] == 'default_ratio'
    d_ch = res['swirl_chamber_diameter']
    assert d_ch == pytest.approx(
        SWIRL_CHAMBER_D_RATIO * res['exit_orifice_diameter']), (
        'varsayilan oda capi SWIRL_CHAMBER_D_RATIO·d_o olmali')
    assert 'D_chamber: not reported' not in texts, (
        'oda capi hesaplanirken figur hala "not reported" diyor')
    assert f'D_chamber = {d_ch:.1f} mm' in texts, (
        'figur cozucunun gercek oda capini gostermiyor: %s' % texts[:200])

    # Kullanici cap girerse kaynak 'user' olur ve figur O degeri basar
    inj2 = InjectorDesign(mdot_ox=1.0, chamber_pressure=20.0,
                          injector_type='swirl')
    inj2.set_swirl_params(chamber_diameter=40.0)
    res2 = inj2.calculate()
    assert res2['swirl_chamber_d_source'] == 'user'
    assert res2['swirl_chamber_diameter'] == pytest.approx(40.0)
    fig2 = _fig(create_swirl_injector(res2))
    texts2 = ' '.join(a.get('text', '') for a in fig2['layout']['annotations'])
    assert 'D_chamber = 40.0 mm' in texts2


def test_pintle_kesiti_cozucu_geometrisini_okur():
    import re
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    motor = HybridRocketEngine(thrust=2000, burn_time=10, of_ratio=6.0,
                               chamber_pressure=20.0,
                               injector_type='pintle').calculate()
    geo = (motor.get('injector_design_detail') or {}).get('pintle_geometry')
    assert geo, 'cozucu pintle geometrisi uretmeli'
    fig = _fig(create_improved_motor_cross_section(motor))
    hover = ' '.join(str(t.get('hovertext', '')) for t in fig['data'])
    d_shown = float(re.search(r'D_pintle: ([\d.]+) mm', hover).group(1))
    gap_shown = float(re.search(r'Gap: ([\d.]+) mm', hover).group(1))
    assert abs(d_shown - geo['d_pintle_mm']) < 0.02, (d_shown, geo)
    assert abs(gap_shown - geo['annulus_gap_mm']) < 0.002, (gap_shown, geo)


# ---------------------------------------------------------------------------
# CEA tarzi tablo: vakum sutunu duz carpan degil
# ---------------------------------------------------------------------------

def test_vakum_sutunu_isp_orani_ile_tutarli():
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    motor = HybridRocketEngine(thrust=2000, burn_time=10, of_ratio=6.0,
                               chamber_pressure=20.0).calculate()
    text = create_cea_style_results(motor)

    def row(label):
        line = [ln for ln in text.splitlines() if ln.startswith(label)][0]
        return [float(v) for v in line.split()[len(label.split()):][:2]]

    isp_sl, isp_vac = row('Specific Impulse')
    f_sl, f_vac = row('Thrust')
    cf_sl, cf_vac = row('Cf')
    ratio = isp_vac / isp_sl
    assert abs(f_vac / f_sl - ratio) < 1e-3, (
        f'itki orani {f_vac / f_sl:.4f} != Isp orani {ratio:.4f} '
        '(eski surum duz x1.15 kullaniyordu)')
    assert abs(cf_vac / cf_sl - ratio) < 1e-3
    assert abs(ratio - 1.15) > 1e-3, 'sabit 1.15 carpani geri gelmis'
    assert 'Vacuum column basis' in text


def test_propellant_kimligi_sabit_yazilmaz():
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    motor = HybridRocketEngine(thrust=2000, burn_time=10, of_ratio=6.0,
                               chamber_pressure=20.0).calculate()
    motor['fuel_type'] = 'paraffin'
    motor['oxidizer_type'] = 'lox'
    text = create_cea_style_results(motor)
    assert '  Fuel Type: PARAFFIN' in text
    assert '  Oxidizer: LOX' in text

    motor.pop('fuel_type')
    motor.pop('oxidizer_type')
    text2 = create_cea_style_results(motor)
    assert '  Oxidizer: NOT REPORTED' in text2, 'sabit N2O geri gelmis'


# ---------------------------------------------------------------------------
# 3D motor gorseli gercek konturu kullanir
# ---------------------------------------------------------------------------

def test_3d_motor_nozulu_gercek_konturdan():
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    from hrma.visualization.visualization import create_3d_motor_visualization
    spans = []
    for noz in ('conical', 'bell'):
        motor = HybridRocketEngine(thrust=2000, burn_time=10, of_ratio=6.0,
                                   chamber_pressure=20.0,
                                   nozzle_type=noz).calculate()
        fig = _fig(create_3d_motor_visualization(motor))
        nozzle = [t for t in fig['data'] if t.get('name') == 'Nozzle'][0]
        z = np.asarray(nozzle['z'], float)
        spans.append(float(z.max() - z.min()))
    assert spans[0] != spans[1], (
        f'nozul boyu tipe gore degismeli: {spans} (eski surum hep 100 mm)')
    assert all(abs(s - 100.0) > 1.0 for s in spans)


# ---------------------------------------------------------------------------
# (e) Hicbir figur JSON'unda bdata blogu yok
# ---------------------------------------------------------------------------

def test_hicbir_figurde_bdata_yok(analyzer):
    res = analyzer.analyze_combustion({'htpb': 100.0}, 'N2O', 6.0, 20.0)
    payloads = [
        create_combustion_analysis_plots(res),
        create_nozzle_mach_area_ratio_contour(NOZZLE_INPUT),
        create_wall_heat_flux_waterfall_plot(HEAT_INPUT),
        create_wall_heat_flux_waterfall_plot({'burn_time': 30}),
        create_chamber_pressure_mixture_ratio_3d_surface(
            {'fuel_type': 'htpb', 'oxidizer_type': 'N2O', 'base_isp': 300,
             'optimal_of_ratio': 3.5, 'optimal_chamber_pressure': 50,
             'grid_n': 3}),
        create_showerhead_with_tooltips(
            {'n_holes': 20, 'hole_diameter': 1.5, 'mdot_ox': 1.0}),
    ]
    for js in payloads:
        assert isinstance(js, str)
        assert 'bdata' not in js, (
            'binary plotly blogu vendor plotly.js 1.58.5 ile cizilemez')
        json.loads(js)
