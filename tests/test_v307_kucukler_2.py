# -*- coding: utf-8 -*-
"""V307/KÜÇÜKLER-2 bekçileri (18 Kas 2026) — KÜÇÜKLER kalem 7 ve 8 (b)(c)
devirleri. Kanıt: docs/scofield/raw/OH/V307/kucukler-2/RAPOR.md.

Bu dosya FİZİĞİ ve SÖZLEŞMEYİ kilitler, bugünkü çıktıyı değil. Hiçbir test
docs/ kanıtına, tarayıcıya ya da yalnız macOS'a bağlı değildir (CI'da koşar).
"""
import pathlib
import re

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'


def _oku(p):
    return pathlib.Path(p).read_text(encoding='utf-8')


def _sozluk_degeri(dosya, anahtar):
    """i18n dosyasındaki EN ve TR değer (sırayla). Bulunamazsa []."""
    s = _oku(dosya)
    return re.findall(r"'" + re.escape(anahtar) + r"':\s*'((?:[^'\\]|\\.)*)'", s)


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    return app.test_client()


# ---------------------------------------------------------------- kalem 1
# /api/regen-cooling: fizik dışı / okunamayan oda sıcaklığı adlı 422
# (eskiden 400 + çözücünün ya da okuyucunun ham cümlesi).

REGEN_GOVDE = {
    'chamber_pressure': 50.0, 'chamber_temperature': 3400.0,
    'throat_diameter': 0.05, 'expansion_ratio': 8.0, 'gamma': 1.2,
    'molecular_weight': 22.0, 'coolant': 'rp1', 'coolant_mdot': 2.0,
    'coolant_inlet_temp': 300.0, 'coolant_inlet_pressure': 60.0,
    'n_channels': 80, 'channel_width': 2.0, 'channel_height': 3.0,
    'wall_thickness': 1.0, 'wall_material': 'cucrzr',
}


#: V307/ORTAM-TEK (kalem 2): okunamayan değerin nedeni artık gerekçe
#: KANONUNDAN (``app._kanonik_gerekce``; emekli ``not_a_finite_number`` adı
#: ``test_d33_app_api_uc_a1::TestOHD3215GerekceKanonu`` ile ret gövdesinde
#: yasak). Ölçüm: docs/scofield/raw/OH/V307/ortam-tek/olcum/k2_{once,sonra}.json.
@pytest.mark.parametrize('deger,neden', [
    (-3000.0, 'out_of_range'), (0.0, 'out_of_range'),
    ('NaN', 'not_a_json_number'), ('Infinity', 'not_a_json_number'),
    ('abc', 'not_a_json_number'), (True, 'boolean_is_not_a_number'),
])
def test_k1_rejen_fizik_disi_sicaklik_adli_422(istemci, deger, neden):
    r = istemci.post('/api/regen-cooling',
                     json=dict(REGEN_GOVDE, chamber_temperature=deger))
    assert r.status_code == 422
    j = r.get_json()
    assert j['error'] == 'invalid_regen_input'
    assert [(f['field'], f['reason'], f['unit']) for f in j['invalid_fields']] \
        == [('chamber_temperature', neden, 'K')]
    # Çözücünün / okuyucunun ham cümlesi kullanıcıya inmez.
    assert 'must be positive [K]' not in str(j)
    assert 'must be a number' not in str(j)


def test_k1_rejen_saglikli_govde_200_ve_eksik_alan_adli_422(istemci):
    ok = istemci.post('/api/regen-cooling', json=REGEN_GOVDE)
    assert ok.status_code == 200
    assert ok.get_json()['status'] == 'success'
    govde = dict(REGEN_GOVDE)
    govde.pop('chamber_temperature')
    r = istemci.post('/api/regen-cooling', json=govde)
    # V307/ORTAM-TEK (kalem 2; bu dosyanın AÇIK 1'i): eksik sıcaklık artık
    # 400 + ham cümle değil, aynı ailenin adlı 422'si
    # (``incomplete_regen_input`` + ``missing_fields``).
    assert r.status_code == 422
    j = r.get_json()
    assert j['error'] == 'incomplete_regen_input'
    assert j['missing_fields'] == ['chamber_temperature']


def test_k1_guverte_kodu_taniyor_tr_en():
    src = _oku(JS / 'analysis_dock.js')
    assert "invalid_regen_input: 'dock.err.invalidRegenInput'" in src
    en, tr = _sozluk_degeri(JS / 'i18n_common.js', 'dock.err.invalidRegenInput')
    assert en != tr
    assert re.search('[çğıİöşüÇĞÖŞÜ]', tr)
    # EN sözlük metni güvertenin İngilizce yedeğiyle aynı cümle.
    yedek = re.search(r"invalid_regen_input:\s*\n\s*'([^']*)'\s*\n\s*\+\s*'([^']*)'",
                      src)
    assert yedek and (yedek.group(1) + yedek.group(2)) == en


# ---------------------------------------------------------------- kalem 2
# Gizli 3000 K yedekleri. Ulaşan yol (performans figürleri): zorunlu alan +
# motor tohumu + adlı ret. Ulaşmayan yollar: from_motor_data adlı ret;
# nozzle_design eski varsayılanı (yalnız testler ulaşıyor) adıyla beyanlı.

FIGUR_TAM = {'throat_area': 0.0004, 'expansion_ratio': 6.0, 'gamma': 1.18,
             'molecular_weight': 22.0, 'chamber_pressure': 35.0,
             'chamber_temperature': 3100.0, 'burn_time': 10.0}


@pytest.mark.parametrize('tur', ['nozzle_mach', 'heat_flux'])
def test_k2_figur_sicakliksiz_adli_422_sicaklikli_200(istemci, tur):
    govde = {k: v for k, v in FIGUR_TAM.items() if k != 'chamber_temperature'}
    r = istemci.post('/api/advanced-performance-analysis',
                     json=dict(govde, analysis_type=tur))
    assert r.status_code == 422
    j = r.get_json()
    assert j['error'] == 'incomplete_figure_input'
    assert [list(x) for x in j['missing_fields']] == [['chamber_temperature']]
    assert 'plot_data' not in j
    ok = istemci.post('/api/advanced-performance-analysis',
                      json=dict(FIGUR_TAM, analysis_type=tur))
    assert ok.status_code == 200
    assert 'Tc = 3000 K' not in ok.get_json()['plot_data']


@pytest.mark.parametrize('deger', [None, -3000.0, 0.0])
def test_k2_figur_modulu_sicakligi_varsaymaz(deger):
    from hrma.visualization import visualization as viz
    assert not hasattr(viz, 'NOZZLE_FIG_DEFAULT_TC_K')
    cd = dict(FIGUR_TAM)
    if deger is None:
        cd.pop('chamber_temperature')
    else:
        cd['chamber_temperature'] = deger
    with pytest.raises(ValueError, match='chamber_temperature'):
        viz._nozzle_fig_motor_data(cd)


def test_k2_performans_paneli_sicaklik_zorunlu_ve_motor_tohumlu():
    src = _oku(JS / 'panels' / 'performance_panel.js')
    zorunlu = re.search(r'const PERF_REQUIRED = \[([^\]]*)\]', src)
    assert zorunlu and "'chamber_temperature'" in zorunlu.group(1)
    assert re.search(r'chamber_temperature:\s*m\.chamber_temperature', src)


@pytest.mark.parametrize('modul,sinif,ek', [
    ('nozzle_flow_1d', 'NozzleFlow1D', {}),
    ('regen_cooling', 'RegenCooling',
     dict(coolant='water', coolant_mdot=4.0, coolant_inlet_temp=300.0,
          coolant_inlet_pressure=40e5, n_channels=50,
          channel_width=1.5e-3, channel_height=3e-3, wall_thickness=1e-3)),
])
@pytest.mark.parametrize('deger', [None, -3000.0, 'NaN'])
def test_k2_from_motor_data_sicakligi_varsaymaz(modul, sinif, ek, deger):
    import importlib
    cls = getattr(importlib.import_module('hrma.analysis.' + modul), sinif)
    md = {'chamber_pressure': 20.0, 'gamma': 1.2, 'molecular_weight': 24.0,
          'throat_diameter': 0.02, 'expansion_ratio': 5.0}
    if deger is not None:
        md['chamber_temperature'] = deger
    with pytest.raises(ValueError, match='chamber_temperature'):
        cls.from_motor_data(md, **ek)
    # Sıcaklık verilince değer aynen kullanılır.
    nesne = cls.from_motor_data(dict(md, chamber_temperature=3200.0), **ek)
    assert nesne.chamber_temperature == 3200.0


def test_k2_lule_eski_varsayilani_adiyla_beyanli():
    from hrma.engines.nozzle_design import NozzleDesigner
    eski = NozzleDesigner().design_nozzle(0.001, 10.0, 40.0, 1.01325, 'bell')
    assert 'T_chamber = 3000 K' in eski['performance']['legacy_defaults_applied']
    # Ürün yolu (hibrit motor gamma / R / T_c'yi geçirir): anahtar yok.
    tam = NozzleDesigner().design_nozzle(0.001, 10.0, 40.0, 1.01325, 'bell',
                                         gamma=1.2, R_specific=350.0,
                                         T_chamber=3300.0)
    assert 'legacy_defaults_applied' not in tam['performance']
    kaynak = _oku(KOK / 'hrma' / 'engines' / 'hybrid_rocket_engine.py')
    assert 'T_chamber=self.T_c' in kaynak


# ---------------------------------------------------------------- kalem 3
# KARŞILAŞTIRMA figürü: Isp ekseni ve Isp taşıyan panelin başlığı tasarım
# ortamını panelin ekran satırıyla AYNI ifadeyle yazar (istekteki ortam
# kaydından; kayıt yoksa figür bugünküyle aynı).

KARSI = {'motor_configs': {
    'A': {'thrust': 1000.0, 'isp': 250.0, 'total_impulse': 5000.0, 'total_mass': 10.0},
    'B': {'thrust': 1200.0, 'isp': 240.0, 'total_impulse': 6000.0, 'total_mass': 12.0}}}


def _fig_metinleri(plot):
    import json as _json
    fig = _json.loads(plot) if isinstance(plot, str) else plot
    basliklar = [a.get('text') for a in fig['layout'].get('annotations', [])]
    eksenler = [v['title']['text'] for k, v in fig['layout'].items()
                if k.startswith('yaxis') and isinstance(v, dict) and v.get('title')]
    return basliklar, eksenler


@pytest.mark.parametrize('ortam,etiket', [
    ({'mode': 'sea_level'}, 'sea level'),
    ({'mode': 'vacuum'}, 'vacuum'),
    ({'mode': 'altitude', 'altitude_m': 20000, 'pressure_bar': 0.05529},
     '20000 m design altitude (0.0553 bar)'),
    ({'mode': 'pressure', 'pressure_bar': 0.5}, '0.5000 bar design ambient'),
])
def test_k3_karsilastirma_isp_ekseni_ve_basligi_ortami_yazar(istemci, ortam, etiket):
    r = istemci.post('/api/comparative-analysis',
                     json=dict(KARSI, design_ambient=ortam))
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    basliklar, eksenler = _fig_metinleri(r.get_json()['plot'])
    assert eksenler.count('Isp (s)<br>' + etiket) == 2       # çubuk + saçılım
    assert 'Isp Comparison<br>' + etiket in basliklar
    # Ortama bağlı olmayan eksenler ve itki paneli değişmez.
    assert 'Thrust (N)' in eksenler and 'Thrust Comparison' in basliklar


def test_k3_ortam_kaydi_yoksa_figur_bugunku_gibi(istemci):
    from hrma.visualization.visualization import create_comparative_analysis_plot
    r = istemci.post('/api/comparative-analysis', json=KARSI)
    assert r.status_code == 200
    assert r.get_json()['plot'] == create_comparative_analysis_plot(
        KARSI['motor_configs'])
    assert '<br>' not in ''.join(_fig_metinleri(r.get_json()['plot'])[1])


@pytest.mark.parametrize('ortam,alan', [
    ({'mode': 'warp'}, 'design_ambient.mode'),
    ({'mode': 'pressure'}, 'design_ambient.pressure_bar'),
    ({'mode': 'altitude', 'pressure_bar': 0.2}, 'design_ambient.altitude_m'),
    ({'mode': 'pressure', 'pressure_bar': -1.0}, 'design_ambient.pressure_bar'),
    ({'mode': 'pressure', 'pressure_bar': 'NaN'}, 'design_ambient.pressure_bar'),
    ({'mode': 'vacuum', 'gizli': 1}, 'design_ambient.gizli'),
    ('vacuum', 'design_ambient'),
])
def test_k3_ortam_kaydi_beyaz_liste_adli_422(istemci, ortam, alan):
    r = istemci.post('/api/comparative-analysis',
                     json=dict(KARSI, design_ambient=ortam))
    assert r.status_code == 422
    j = r.get_json()
    assert j['error'] == 'invalid_comparative_input'
    assert alan in [f['field'] for f in j['invalid_fields']]


def test_k3_etiket_ekran_satiriyla_ayni_ifade_tr_en():
    """Sunucu etiketi = panelin panel.ambient.* EN metni; i18n_charts TR
    deseni = aynı anahtarın TR metni (ondalık virgül istemcide)."""
    from hrma.visualization.visualization import design_ambient_label
    common = JS / 'i18n_common.js'
    en_aP, tr_aP = _sozluk_degeri(common, 'panel.ambient.altitudeP')
    en_p, tr_p = _sozluk_degeri(common, 'panel.ambient.pressure')
    en_v, tr_v = _sozluk_degeri(common, 'panel.ambient.vacuum')
    en_ds, tr_ds = _sozluk_degeri(common, 'panel.comparative.ambientSeaLevel')
    assert design_ambient_label(
        {'mode': 'altitude', 'altitude_m': 20000.0, 'pressure_bar': 0.0553}) \
        == en_aP.replace('{h}', '20000').replace('{p}', '0.0553')
    assert design_ambient_label({'mode': 'pressure', 'pressure_bar': 0.5}) \
        == en_p.replace('{p}', '0.5000')
    assert design_ambient_label({'mode': 'vacuum'}) == en_v
    assert design_ambient_label({'mode': 'sea_level'}) == en_ds
    charts = _oku(JS / 'i18n_charts.js')
    assert "'vacuum': '%s'" % tr_v in charts and "'sea level': '%s'" % tr_ds in charts
    assert ("'$1 m tasarım irtifası ($2 bar)'" in charts
            and tr_aP == '{h} m tasarım irtifası ({p} bar)')
    assert "'$1 bar tasarım ortamı'" in charts and tr_p == '{p} bar tasarım ortamı'


def test_k3_panel_ortam_kaydini_govdeye_adiyla_koyar():
    src = _oku(JS / 'panels' / 'comparative_panel.js')
    assert 'govde.design_ambient = AMBK.record(ortakOrtam)' in src
    assert 'body: JSON.stringify(govde)' in src
    # Karışık ortamda kayıt gönderilmez (ortama bağlı metrikler de gitmez).
    assert re.search(r'if \(!ortamKarisik && ortamlilar\.length && AMBK', src)


# ---------------------------------------------------------------- kalem 4
# PERFORMANS 3B yüzey künyesi: taban Isp'nin tasarım ortamını söyler
# (panelin tohumu; isteğe bağlı kayıt) ve ucun geçirmediği ε artık geçer.

YUZEY = {'analysis_type': '3d_surface', 'fuel_type': 'htpb',
         'oxidizer_type': 'N2O', 'chamber_pressure': 30.0,
         'optimal_of_ratio': 6.0, 'base_isp': 230.0, 'expansion_ratio': 16.0,
         'grid_n': 3}


def _kunye(istemci, govde):
    import json as _json
    r = istemci.post('/api/advanced-performance-analysis', json=govde)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    fig = _json.loads(r.get_json()['plot_data'])
    haclar = [t['hovertemplate'] for t in fig['data']
              if t.get('type') == 'scatter3d' and 'Design' in str(t.get('name'))]
    notlar = ' '.join(a.get('text') or '' for a in fig['layout'].get('annotations', []))
    # V307/GRAFİK-BİRİM (kalem 4): not artık madde madde SARILI ('<br>' +
    # iki boşluklu devam satırı). Sarma metni değiştirmez; satır kırılımı
    # tek boşluğa indirilip AYNI ifade aranır.
    notlar = notlar.replace('<br>  ', ' ')
    return haclar, notlar


def test_k4_yuzey_kunyesi_ortami_ve_genlesme_oranini_yazar(istemci):
    haclar, notlar = _kunye(istemci, dict(
        YUZEY, design_ambient={'mode': 'altitude', 'altitude_m': 20000,
                               'pressure_bar': 0.05529}))
    assert len(haclar) == 1
    beklenen = ('230.0 s at expansion ratio 16.00, design ambient: '
                '20000 m design altitude (0.0553 bar)')
    assert beklenen in haclar[0]
    assert '(expansion ratio not reported)' not in haclar[0]
    # Taban uyuşmazlığı notu da aynı ifadeyi taşır (hover açılmadan görünür).
    assert beklenen in notlar


def test_k4_kayit_yoksa_ortam_yazilmaz(istemci):
    haclar, notlar = _kunye(istemci, dict(YUZEY))
    assert 'design ambient' not in haclar[0] and 'design ambient' not in notlar
    assert 'at expansion ratio 16.00' in haclar[0]


def test_k4_gecersiz_ortam_kaydi_adli_422(istemci):
    r = istemci.post('/api/advanced-performance-analysis',
                     json=dict(YUZEY, design_ambient={'mode': 'pressure'}))
    assert r.status_code == 422
    j = r.get_json()
    assert j['error'] == 'invalid_figure_input'
    assert [f['field'] for f in j['invalid_fields']] == ['design_ambient.pressure_bar']


def test_k4_panel_tohum_isp_ortamini_adiyla_gonderir():
    src = _oku(JS / 'panels' / 'performance_panel.js')
    assert 'record: ortamKaydi' in src
    assert 'payload.design_ambient = ortamKaydi(tabanIspOrtami)' in src
    assert 'if (tabanIspTohumdaMi(payload.base_isp))' in src
    assert 'tabanIspTohumu = (sug.base_isp !== undefined) ? sug.base_isp : null;' in src
    karsi = _oku(JS / 'panels' / 'comparative_panel.js')
    assert 'govde.design_ambient = AMBK.record(ortakOrtam)' in karsi
    assert 'function ortamKaydi' not in karsi          # tek kaynak
