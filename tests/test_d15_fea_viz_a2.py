"""ÖH Dalga-15 · kulvar fea-viz · aşama 2 — sekiz kalemin bekçisi.

Her sınıf BİR kalemdir. İddialar, onarımdan önce ölçülmüş sayılardan
gelir (kanıt: docs/scofield/raw/OH/D15/fea-viz/a2/once_*.json ⟷
sonra_*.json). Her bekçi ters mutasyonla KIRMIZI gösterilmiştir
(mutasyon.json) — yani kusur geri konduğunda test düşer.

Ölçülen taban (HEAD e88d096):
  P8B3-02  yapısal pano gerçek veride ``KeyError: 'cycles'`` ile ÇÖKÜYOR;
           boş sözlükle 0 iz. Gerçek SF sözlüğü safety_analysis.
           safety_factors'ta duruyor, panel oraya hiç bakmıyor.
  P8B3-04  ısı panosu ürün yolunda 200 dönüyor ama 0 iz / 0 not basıyor;
           dört başlık boş eksenlerin üstünde duruyor.
  P8B3-05  "Cooling Effectiveness" ekseni '%' derken seri 0-1 kesri
           (etiket .1% ile 30,0% yazarken eksen 0,3 gösteriyor).
  P8B3-06  Isp vs O/F taraması hep 1,0-6,0; O/F 8 ve 12 koşularında
           kullanıcının noktası grafiğin DIŞINDA, yıldız bandın ucunda.
  P8B3-17  besleme bütçesi yalnız oksitleyici hattını çiziyor ve bunu
           söylemiyor; 'Feed' çubuğu devresiz.
  P8B4-01  3B sahnedeki grain yarıçapı 42,500 mm sabit (çözücü 60,000).
  P8B4-11  aynı metinde tablo 3427 N ⟷ kart 3404 N (kart aslında 20 km).
  P8B4-16  sayısız istekte Pc 50 / O/F 3,5 / Isp 300 haçı "reported by
           the motor solver" künyesiyle basılıyor.
"""
import json
import math
import os
import re
import sys
import tempfile

import pytest

os.environ.setdefault('HRMA_USER_DATA_DIR',
                      tempfile.mkdtemp(prefix='d15-feaviz-a2-'))

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------- yardımcı
def _fig(js):
    return json.loads(js) if isinstance(js, str) else js


def _izler(f):
    return f.get('data') or []


def _ad(f, name):
    for t in _izler(f):
        if t.get('name') == name:
            return t
    return None


def _annotasyonlar(f):
    return [a.get('text', '') for a in ((f.get('layout') or {})
                                        .get('annotations') or [])]


def _notlar(f):
    """Figürün altındaki '- ...' beyan bloğunun satırları."""
    out = []
    for t in _annotasyonlar(f):
        if t and t.lstrip().startswith('-'):
            out.extend(s.strip() for s in t.split('<br>') if s.strip())
    return out


def _hucre(t):
    return (t.get('xaxis') or 'x', t.get('yaxis') or 'y')


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def yapisal_sonuc():
    from hrma.analysis.structural_analysis import StructuralAnalyzer
    return StructuralAnalyzer().analyze_structure(
        {'chamber_pressure': 30.0, 'chamber_diameter': 0.12,
         'chamber_length': 0.4, 'throat_diameter': 0.03,
         'exit_diameter': 0.08, 'thrust': 3000.0, 'burn_time': 10.0},
        material='steel_4130')


@pytest.fixture(scope='module')
def isi_sonuc():
    from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
    return HeatTransferAnalyzer().analyze_heat_transfer(
        {'chamber_pressure': 30.0, 'chamber_temperature': 3000.0,
         'chamber_diameter': 0.12, 'chamber_length': 0.4,
         'burn_time': 10.0, 'mdot_total': 1.2},
        material='steel', wall_thickness=0.005,
        cooling_type='regenerative')


@pytest.fixture(scope='module')
def hibrit_motor(client):
    r = client.post('/calculate', json={
        'motor_type': 'hybrid', 'thrust': 3000.0, 'burn_time': 40.0,
        'chamber_pressure': 20.0, 'of_ratio': 6.0, 'fuel_type': 'htpb',
        'oxidizer_type': 'n2o', 'initial_port_diameter': 0.05,
        'chamber_diameter_input': 120.0, 'l_star': 1.0,
        'expansion_ratio': 4.0, 'total_impulse': 120000.0,
        'include_plots': False, 'generate_cad': False,
        'calculate_trajectory': False,
        'include_combustion_analysis': False,
        'include_realtime_dashboard': False,
        'include_3d_visualization': False})
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()['motor']


@pytest.fixture(scope='module')
def sivi_motor(client):
    r = client.post('/calculate_liquid', json={
        'motor_name': 'D15-A2-SIVI', 'thrust': 10000.0, 'burn_time': 30.0,
        'chamber_pressure': 50.0, 'mixture_ratio': 2.3,
        'fuel_type': 'rp1', 'oxidizer_type': 'lox',
        'expansion_ratio': 12.0})
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    j = r.get_json()
    return j.get('motor') or j


# =========================================================== P8B3-02
class TestP8B302YapisalPanoCozucuyeBagli:
    """Pano çözücünün ÜRETTİĞİ alanlardan çiziliyor (ve çökmüyor)."""

    def test_gercek_veride_cokmuyor_ve_dort_ceyrek_dolu(self, yapisal_sonuc):
        from hrma.visualization.visualization import (
            create_structural_analysis_plots)
        # Taban: KeyError: 'cycles' -> figür hiç üretilemiyordu
        f = _fig(create_structural_analysis_plots(yapisal_sonuc))
        izler = _izler(f)
        assert len(izler) >= 4, [t.get('name') for t in izler]
        assert len({_hucre(t) for t in izler}) == 4, (
            'dört çeyreğin de izi olmalı: '
            + str(sorted({str(_hucre(t)) for t in izler})))

    def test_emniyet_katsayilari_cozucunun_sozlugunden(self, yapisal_sonuc):
        from hrma.visualization.visualization import (
            create_structural_analysis_plots)
        f = _fig(create_structural_analysis_plots(yapisal_sonuc))
        sf = _ad(f, 'Safety Factor (solver)')
        assert sf is not None, [t.get('name') for t in _izler(f)]
        gercek = yapisal_sonuc['safety_analysis']['safety_factors']
        assert len(sf['y']) == len(gercek)
        for beklenen in gercek.values():
            assert any(abs(v - beklenen) < 1e-9 for v in sf['y']), (
                f'{beklenen} panele girmemiş: {sf["y"]}')

    def test_istasyon_gerilmeleri_cozucunun_alanlarindan(self, yapisal_sonuc):
        from hrma.visualization.visualization import (
            create_structural_analysis_plots)
        f = _fig(create_structural_analysis_plots(yapisal_sonuc))
        st = _ad(f, 'Station stress')
        assert st is not None
        ch = yapisal_sonuc['chamber_analysis']
        assert any(abs(v - ch['hoop_stress']) < 1e-9 for v in st['y'])
        assert any(abs(v - ch['von_mises_stress']) < 1e-9 for v in st['y'])

    def test_sf_esigi_koddan_degil_veriden(self, yapisal_sonuc):
        """'Min SF: 2.0' SABİT çizgisi kalktı; hedef veriden okunuyor."""
        from hrma.visualization.visualization import (
            create_structural_analysis_plots)
        f = _fig(create_structural_analysis_plots(yapisal_sonuc))
        metin = json.dumps(f, ensure_ascii=False)
        assert 'Min SF: 2.0' not in metin
        hedef = yapisal_sonuc['chamber_analysis'][
            'design_safety_factor_target']
        assert f'Design target SF {hedef:g}' in metin

        # Hedef değişince çizgi de değişir (kod sabiti olsaydı değişmezdi)
        import copy
        mut = copy.deepcopy(yapisal_sonuc)
        mut['chamber_analysis']['design_safety_factor_target'] = 2.5
        f2 = _fig(create_structural_analysis_plots(mut))
        assert 'Design target SF 2.5' in json.dumps(f2, ensure_ascii=False)

    def test_hedef_yoksa_hukum_cizgisi_iddia_edilmez(self, yapisal_sonuc):
        import copy
        from hrma.visualization.visualization import (
            create_structural_analysis_plots)
        mut = copy.deepcopy(yapisal_sonuc)
        mut['chamber_analysis'].pop('design_safety_factor_target', None)
        f = _fig(create_structural_analysis_plots(mut))
        metin = json.dumps(f, ensure_ascii=False)
        assert 'Design target SF' not in metin
        assert any('threshold line is drawn' in n for n in _notlar(f))

    def test_bos_sozlukte_ceyrekler_beyan_ediyor(self):
        from hrma.visualization.visualization import (
            create_structural_analysis_plots)
        f = _fig(create_structural_analysis_plots({}))
        # Alt-panel BAŞLIKLARI (beyan bloğu değil): dördü de veri yokluğunu
        # söylemeli. Taban: dört başlık boş eksenlerin üstünde iddialı
        # duruyordu ("Stress Distribution", "Safety Factor Analysis",
        # "Wall Thickness Optimization", "Fatigue Analysis").
        basliklar = [t for t in _annotasyonlar(f)
                     if t and not t.lstrip().startswith('-')]
        assert len(basliklar) == 4, basliklar
        assert all('(not available)' in t for t in basliklar), basliklar
        assert len(_notlar(f)) >= 4, _notlar(f)


# =========================================================== P8B3-04
class TestP8B304IsiPanosuBeyanEdiyor:
    """Ürün yolunda pano ya veri çizer ya da NEDEN çizmediğini yazar."""

    @pytest.fixture(scope='class')
    def urun_figuru(self, client):
        r = client.post('/api/advanced-analysis', json={
            'motor_data': {'chamber_pressure': 30.0,
                           'chamber_temperature': 3000.0,
                           'chamber_diameter': 0.12, 'chamber_length': 0.4,
                           'burn_time': 10.0, 'mdot_total': 1.2},
            'analysis_types': ['heat_transfer'],
            'material_type': 'steel', 'wall_thickness': 0.005,
            'cooling_type': 'regenerative'})
        assert r.status_code == 200
        res = r.get_json()['results']
        return _fig(res['heat_transfer_plot']), res['heat_analysis']

    def test_urun_yolunda_iz_var(self, urun_figuru):
        f, _ha = urun_figuru
        # Taban ölçümü: 0 iz / 0 dolu hücre
        assert len(_izler(f)) >= 2, [t.get('name') for t in _izler(f)]
        assert len({_hucre(t) for t in _izler(f)}) >= 2

    def test_cidar_sicakligi_cozucunun_istasyonlarindan(self, urun_figuru):
        f, ha = urun_figuru
        iz = _ad(f, 'Wall Temperature (solver)')
        assert iz is not None, [t.get('name') for t in _izler(f)]
        assert any(abs(v - ha['wall_analysis']['inner_temperature']) < 1e-9
                   for v in iz['y'])
        assert any(abs(v - ha['wall_analysis']['outer_temperature']) < 1e-9
                   for v in iz['y'])

    def test_gerilme_ceyregi_cozucunun_bilesenlerinden(self, urun_figuru):
        f, ha = urun_figuru
        iz = _ad(f, 'Wall stress')
        assert iz is not None
        sa = ha['safety_analysis']
        assert any(abs(v - sa['combined_stress_MPa']) < 1e-9 for v in iz['y'])
        assert any(abs(v - sa['pressure_hoop_stress_MPa']) < 1e-9
                   for v in iz['y'])

    def test_bos_ceyrekler_basliginda_ve_notunda_beyan_ediliyor(
            self, urun_figuru):
        f, _ha = urun_figuru
        basliklar = ' '.join(_annotasyonlar(f))
        # Bu çözücü ne bölgesel soğutma etkinliği ne de zaman geçmişi üretir
        assert 'Cooling Effectiveness (not available)' in basliklar
        assert 'Temperature vs Time (not available)' in basliklar
        notlar = _notlar(f)
        assert any('Cooling effectiveness not available' in n for n in notlar)
        assert any('Temperature history not available' in n for n in notlar)

    def test_sinir_cizgisi_sabit_1073_degil_en_siki_alandan(self,
                                                            urun_figuru):
        """Eski kod ``heat_data.get('material_limit', 1073)`` yazıyordu."""
        f, ha = urun_figuru
        mp = ha['material_properties']
        beklenen = min(mp['allowable_temperature'], mp['max_service_temp'])
        metin = json.dumps(f, ensure_ascii=False)
        assert f'Allowable {beklenen:.0f} K' in metin, metin[:300]
        assert any('STRICTEST' in n for n in _notlar(f))

    def test_sinir_yoksa_uydurulmaz(self, isi_sonuc):
        import copy
        from hrma.visualization.visualization import (
            create_heat_transfer_plots)
        mut = copy.deepcopy(isi_sonuc)
        mut['material_properties'].pop('allowable_temperature', None)
        mut['material_properties'].pop('max_service_temp', None)
        f = _fig(create_heat_transfer_plots(mut))
        assert 'Allowable' not in json.dumps(f, ensure_ascii=False)
        assert any('not invented' in n for n in _notlar(f))


# =========================================================== P8B3-05
class TestP8B305SogutmaEtkinligiBirimi:
    """Eksen '%' diyorsa seri de yüzde olmalı (taban: 0,3 ⟷ '30,0%')."""

    def _panel(self, isi_sonuc, eff):
        from hrma.visualization.visualization import (
            create_heat_transfer_plots)
        veri = dict(isi_sonuc)
        veri['cooling_analysis'] = {
            'zones': ['Chamber', 'Throat', 'Nozzle'], 'effectiveness': eff}
        return _fig(create_heat_transfer_plots(veri))

    def test_kesir_verisi_yuzde_eksenine_uyarlanir(self, isi_sonuc):
        f = self._panel(isi_sonuc, [0.3, 0.45, 0.6])
        bar = _ad(f, 'Cooling Effectiveness')
        assert bar is not None
        assert bar['y'] == pytest.approx([30.0, 45.0, 60.0])
        assert bar['text'] == ['30.0%', '45.0%', '60.0%']
        eksen = None
        lay = f['layout']
        ax = 'yaxis' + (bar.get('yaxis', 'y')[1:] or '')
        eksen = (lay.get(ax) or {}).get('title', {}).get('text')
        assert eksen == 'Effectiveness (%)'
        # Eksen ile serinin BÜYÜKLÜĞÜ artık aynı mertebede
        assert max(bar['y']) > 1.0

    def test_eksik_alanda_sessiz_yedek_yok(self, isi_sonuc):
        """Taban: ``ca.get('cooling_efficiency', 0.8)`` -> %80 uyduruluyordu."""
        from hrma.visualization.visualization import (
            create_heat_transfer_plots)
        veri = dict(isi_sonuc)
        veri['cooling_analysis'] = {'zones': ['Chamber', 'Throat', 'Nozzle']}
        f = _fig(create_heat_transfer_plots(veri))
        assert _ad(f, 'Cooling Effectiveness') is None
        assert any('not available' in n for n in _notlar(f))
        assert '80.0%' not in json.dumps(f, ensure_ascii=False)


# =========================================================== P8B3-06
class TestP8B306TaramaKosuyaBagli:
    """Tarama bandı koşunun O/F'ini kapsar; nokta ve kenar beyan edilir."""

    @pytest.fixture(scope='class')
    def kosu(self):
        from hrma.engines.combustion_analysis import CombustionAnalyzer
        from hrma.visualization.visualization import (
            create_combustion_analysis_plots)
        cd = CombustionAnalyzer().analyze_combustion(
            {'htpb': 100.0}, 'n2o', 8.0, 20.0)
        return cd, _fig(create_combustion_analysis_plots(cd))

    def test_band_kullanicinin_of_ini_kapsiyor(self, kosu):
        _cd, f = kosu
        iz = _ad(f, 'Isp vs O/F')
        assert iz is not None
        # Taban ölçümü: her koşuda 1,0-6,0; O/F 8 dışarıda kalıyordu
        assert min(iz['x']) <= 8.0 <= max(iz['x']), (
            f"band {min(iz['x'])}-{max(iz['x'])} O/F 8'i kapsamıyor")
        assert max(iz['x']) > 6.0 + 1e-9

    def test_kosunun_kendi_noktasi_cozucunun_isp_siyle_isaretli(self, kosu):
        cd, f = kosu
        nokta = _ad(f, 'This run (solver)')
        assert nokta is not None, [t.get('name') for t in _izler(f)]
        assert nokta['x'][0] == pytest.approx(cd['inputs']['of_ratio'])
        assert nokta['y'][0] == pytest.approx(cd['performance']['isp'])

    def test_yildiz_artik_bandin_ucunda_degil(self, kosu):
        _cd, f = kosu
        iz = _ad(f, 'Isp vs O/F')
        yildiz = _ad(f, 'Sweep maximum')
        assert yildiz is not None
        # Taban: yıldız her koşuda bandın SON noktasında (O/F 6,0) duruyordu
        assert yildiz['x'][0] < max(iz['x']) - 1e-9, (
            'tepe hâlâ bandın kenarında')

    def test_tepe_kenardaysa_beyan_ediliyor(self):
        """Karşı kanıt: band gerçekten kenarla bitiyorsa not basılır."""
        from hrma.engines.combustion_analysis import CombustionAnalyzer
        from hrma.visualization.visualization import (
            create_combustion_analysis_plots)
        cd = CombustionAnalyzer().analyze_combustion(
            {'htpb': 100.0}, 'n2o', 1.5, 20.0)
        f = _fig(create_combustion_analysis_plots(cd))
        iz = _ad(f, 'Isp vs O/F')
        yildiz = _ad(f, 'Sweep maximum')
        if abs(yildiz['x'][0] - max(iz['x'])) < 1e-9 or \
                abs(yildiz['x'][0] - min(iz['x'])) < 1e-9:
            assert any('END of the swept band' in n for n in _notlar(f)), (
                'kenar tepesi beyan edilmedi')


# =========================================================== P8B3-17
class TestP8B317BeslemeButcesiIkiDevre:
    """Bütçe iki devreyi de ADIYLA gösterir (taban: yalnız oksitleyici)."""

    @pytest.fixture(scope='class')
    def paneller(self, sivi_motor):
        from hrma.visualization.visualization import _perf_panels_liquid
        return {p['title']: p for p in _perf_panels_liquid(
            sivi_motor, sivi_motor.get('injector_design') or {}) if p}

    def _cizim(self, panel):
        from plotly.subplots import make_subplots
        f = make_subplots(rows=1, cols=1, specs=[[dict(panel['spec'])]])
        panel['draw'](f, 1, 1)
        return json.loads(f.to_json())

    def test_butce_iki_devreyi_de_ciziyor(self, paneller, sivi_motor):
        panel = paneller.get('Feed System Pressure Budget (per circuit)')
        assert panel is not None, sorted(paneller)
        fd = self._cizim(panel)
        adlar = [t.get('name') for t in fd['data']]
        assert 'Oxidizer' in adlar and 'Fuel' in adlar, adlar
        drops = sivi_motor['feed_system']['pressure_drops']
        ox = _ad(fd, 'Oxidizer')
        fuel = _ad(fd, 'Fuel')
        for i, etiket in enumerate(ox['x']):
            # ÖH D22 / fea-cfd a2, P8B3-18: etiket artık dayandığı varsayımı
            # da taşıyabiliyor ("Filters (assumed K=10)"). Çözücü anahtarı
            # PARANTEZ ÖNCESİNDEN türetilir; testin ölçtüğü şey (çubuk
            # değerleri = çözücü sayıları) aynen korunur.
            anahtar = etiket.split('(')[0].strip().lower().replace(' ', '_')
            # V3.0.5 T-ÇAPA-C1: V301/L-E (ffcc018bb, NK-36) 'Cooling Jacket'
            # kalemini ekledi; etiketi çözücü anahtarından (regen_jacket)
            # türemez. Ceket yalnız yakıt hattındadır: oksitleyici
            # devresinde anahtar yok → o çubuk ÇİZİLMEZ (None, uydurma 0 yok).
            anahtar = {'cooling_jacket': 'regen_jacket'}.get(anahtar, anahtar)
            ox_beklenen = drops['oxidizer_line'].get(anahtar)
            if ox_beklenen is None:
                assert ox['y'][i] is None, (etiket, ox['y'][i])
            else:
                assert ox['y'][i] == pytest.approx(ox_beklenen)
            assert fuel['y'][i] == pytest.approx(
                drops['fuel_line'][anahtar])

    def test_yakit_hatti_gercekten_farkli(self, sivi_motor):
        """İki seri aynı sayı olsaydı 'iki devre' iddiası boş olurdu."""
        drops = sivi_motor['feed_system']['pressure_drops']
        assert drops['oxidizer_line']['filters'] != pytest.approx(
            drops['fuel_line']['filters'])

    def test_basinc_dagiliminda_devre_adi_yazili(self, paneller, sivi_motor):
        panel = paneller.get('Pressure Distribution')
        fd = self._cizim(panel)
        etiketler = fd['data'][0]['x']
        assert 'Feed (Ox)' in etiketler, etiketler
        assert 'Feed' not in etiketler, ('devresiz etiket geri gelmiş: '
                                         + str(etiketler))
        drops = sivi_motor['feed_system']['pressure_drops']
        if drops.get('pump_discharge_pressure_fuel') is not None:
            assert 'Feed (Fuel)' in etiketler, etiketler
            i = list(etiketler).index('Feed (Fuel)')
            assert fd['data'][0]['y'][i] == pytest.approx(
                drops['pump_discharge_pressure_fuel'])


# =========================================================== P8B4-01
class TestP8B401UcBoyutluGrain:
    """3B grain yarıçapı 2B kesitle TEK KAYNAKTAN gelir."""

    def _r_max(self, iz):
        best = 0.0
        for row_x, row_y in zip(iz['x'], iz['y']):
            for a, b in zip(row_x, row_y):
                best = max(best, math.hypot(a, b))
        return best

    def test_sahne_cozucunun_grain_dis_capina_esit(self, hibrit_motor):
        from hrma.visualization.visualization import (
            create_3d_motor_visualization, _cross_section_grain_annulus)
        f = _fig(create_3d_motor_visualization(hibrit_motor))
        grain = _ad(f, 'Fuel Grain')
        assert grain is not None
        rc_mm = hibrit_motor['chamber_diameter'] * 1000.0 / 2.0
        r_2b, _halka, kaynak = _cross_section_grain_annulus(
            hibrit_motor, rc_mm)
        assert kaynak == 'solver grain outer diameter'
        # Taban: sahne 42,500 mm, 2B 60,000 mm (-%29,2)
        assert self._r_max(grain) == pytest.approx(r_2b, rel=1e-9)

    def test_mutasyonda_sahne_kipirdiyor(self, hibrit_motor):
        import copy
        from hrma.visualization.visualization import (
            create_3d_motor_visualization)
        olculen = []
        for d_out in (60.0, 40.0, 20.0):
            m = copy.deepcopy(hibrit_motor)
            m.setdefault('grain_design', {})['grain_outer_diameter_mm'] = d_out
            f = _fig(create_3d_motor_visualization(m))
            olculen.append(self._r_max(_ad(f, 'Fuel Grain')))
        # Taban: 42,500 / 42,500 / 42,500 (SABİT)
        assert olculen == pytest.approx([30.0, 20.0, 10.0])

    def test_cozucu_cap_yayimlamiyorsa_grain_cizilmez(self, hibrit_motor):
        import copy
        from hrma.visualization.visualization import (
            create_3d_motor_visualization)
        m = copy.deepcopy(hibrit_motor)
        gd = m.get('grain_design') or {}
        gd.pop('grain_outer_diameter_mm', None)
        gd.pop('outer_diameter_mm', None)
        m['grain_design'] = gd
        f = _fig(create_3d_motor_visualization(m))
        assert _ad(f, 'Fuel Grain') is None
        assert any('not drawn' in n for n in _notlar(f)), _notlar(f)


# =========================================================== P8B4-11
class TestP8B411TekVakumItkisi:
    """Aynı metin tek vakum itkisi söyler; 20 km sayısı adıyla anılır."""

    @pytest.fixture(scope='class')
    def metin(self, hibrit_motor):
        from hrma.visualization.advanced_results import (
            create_cea_style_results)
        return create_cea_style_results(hibrit_motor)

    def _tablo_vakum(self, metin):
        satir = [ln for ln in metin.splitlines()
                 if ln.startswith('Thrust') and 'N' in ln][0]
        return float(satir.split()[2])

    def test_kart_ve_tablo_ayni_sayi(self, metin):
        kart = float(re.search(r'Vacuum Thrust: ([\d.]+) N', metin).group(1))
        # Taban: tablo 3427 ⟷ kart 3404 (23,0 N / %0,68 fark)
        assert kart == pytest.approx(self._tablo_vakum(metin), abs=0.5)

    def test_kart_vacuum_column_ile_ayni_kaynaktan(self, hibrit_motor, metin):
        from hrma.visualization.advanced_results import _vacuum_column
        sl_isp = hibrit_motor.get('sea_level_isp', hibrit_motor['isp'])
        tv, _cf, basis = _vacuum_column(hibrit_motor, sl_isp,
                                        hibrit_motor.get('vacuum_isp'))
        kart = float(re.search(r'Vacuum Thrust: ([\d.]+) N', metin).group(1))
        assert kart == pytest.approx(tv, abs=0.5)
        assert f'Vacuum thrust basis: {basis}' in metin

    def test_izgara_tavani_adiyla_ve_irtifasiyla(self, hibrit_motor, metin):
        """ÇEVRİLDİ — ÖH D17 / P8B4-11 ŞARTI + OH-D16-12.

        Bu bekçi KUSURU KORUYORDU: tavan satırının ``vacuum_thrust``
        alanını basmasını sözleşme yapıyordu. D15'te bu doğruydu —
        o gün ``vacuum_thrust`` ızgaranın son satırıydı. Sonra hibrit
        P1B3-01 üreticiyi onardı ve alan GERÇEK vakum limiti oldu
        (meta['thrust_vacuum_n']); ızgaranın ucu ``top_of_grid_thrust``
        alanına taşındı. Bekçi güncellenmeyince kartın kendi kendisiyle
        çelişmesini KİLİTLEDİ.

        ÖLÇÜLDÜ (docs/scofield/raw/OH/D17/fea-cfd/a1/once_P8B4-11.json,
        aynı hibrit vaka): vacuum_thrust 3427,4312 N ⟷ top_of_grid_thrust
        3404,3358 N (fark 23,0954 N). Taban metninde "Vacuum Thrust:"
        satırı da tavan satırı da 3427 N basıyordu ve tavan satırı bu
        sayı için "NOT the vacuum value" diyordu; dürüst ızgara ucu
        metinde HİÇ YOKTU.

        Çevrilen sözleşme: tavan satırı ÜRETİCİNİN IZGARA ALANLARINI
        basar (top_of_grid_thrust / top_of_grid_altitude_m) ve vakum
        değerinden AYRIŞIR.
        """
        ta = hibrit_motor['thrust_altitude_analysis']
        satir = [ln for ln in metin.splitlines()
                 if ln.startswith('Altitude-grid ceiling')]
        assert satir, metin[-1200:]
        assert f"{float(ta['top_of_grid_altitude_m']):.0f} m" in satir[0]
        assert f"{float(ta['top_of_grid_thrust']):.0f} N" in satir[0]
        assert 'NOT the vacuum value' in satir[0]
        # Kilit: tavan ≠ vakum. İki alan ayrıştığı sürece tavan satırı
        # vakum sayısını basamaz (kusurun yeniden girişi buradan olurdu).
        assert float(ta['top_of_grid_thrust']) != float(ta['vacuum_thrust'])
        assert f"{float(ta['vacuum_thrust']):.0f} N" not in satir[0]

    def test_metinde_tek_vakum_itkisi_sayisi(self, metin):
        assert len(set(re.findall(r'Vacuum Thrust: ([\d.]+) N', metin))) == 1


# =========================================================== P8B4-16
class TestP8B416TasarimNoktasiKaynagi:
    """Haç yalnız GÖNDERİLEN sayıyla çizilir ve künyesi kaynağı söyler."""

    def test_sayisiz_istekte_hac_cizilmez(self, client):
        r = client.post('/api/advanced-performance-analysis', json={
            'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
            'analysis_type': '3d_surface', 'grid_n': 3})
        assert r.status_code == 200
        f = _fig(r.get_json()['plot_data'])
        adlar = [str(t.get('name')) for t in _izler(f)]
        # Taban: Pc 50 / O/F 3,5 / Isp 300 haçı basılıyordu
        assert not any('Design point' in a for a in adlar), adlar
        assert 'reported by the motor solver' not in json.dumps(
            f, ensure_ascii=False)

    # ÇEVRİLDİ (ÖH D24 / fea-cfd a2, P8B4-17) — GEREKÇE:
    #
    # Aşağıdaki iki bekçi haçın İZ ADINI ve Z DEĞERİNİ kilitliyordu
    # (``'Design point (as supplied)'`` + ``z == base_isp``). Bu iki şey
    # P8B4-16'nın konusu DEĞİLDİR; P8B4-16'nın konusu "sayı gönderilmediyse
    # haç çizilmez, gönderildiyse künyesi KAYNAĞINI söyler"dir ve o konu
    # aşağıda AYNEN korunuyor.
    #
    # Z değerinin kilidi ise P8B4-17'de ölçülen kusuru KORUYORDU: yüzey her
    # zaman optimum/deniz seviyesi genleşmesiyle çözülüyor, gönderilen
    # ``base_isp`` ise motorun kendi genleşme oranından geliyor. İkisini
    # aynı z ekseninde eşitlemek, farklı tabanlardaki iki sayıyı
    # karşılaştırılabilir göstermek demekti (ölçüldü: eps = 16'da haç
    # yüzeyin %6,23 altında, docs/scofield/raw/OH/D24/fea-cfd/a2/
    # once_p8b4_17.json). Haç artık (Pc, O/F) konumunda kalır ve z olarak
    # AYNI ÇÖZÜCÜNÜN o düğümde çözdüğü değeri alır; gönderilen sayı
    # kaynağıyla birlikte künyede yaşamaya devam eder.
    #
    # Kilitlenen şey artık: haç ÇİZİLİYOR, konumu gönderilen (Pc, O/F),
    # künyesi gönderilen Isp'yi ve KAYNAĞINI ('AS SUPPLIED' ⟷ 'by the motor
    # solver') söylüyor.
    def test_gonderilen_sayi_kaynagiyla_etiketleniyor(self, client):
        r = client.post('/api/advanced-performance-analysis', json={
            'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
            'analysis_type': '3d_surface', 'grid_n': 3,
            'base_isp': 233.0, 'optimal_of_ratio': 6.2,
            'chamber_pressure': 31.0})
        f = _fig(r.get_json()['plot_data'])
        izler = [t for t in _izler(f)
                 if 'Design' in str(t.get('name'))]
        assert izler, [t.get('name') for t in _izler(f)]
        iz = izler[0]
        assert iz['x'][0] == pytest.approx(31.0)
        assert iz['y'][0] == pytest.approx(6.2)
        assert '233.0' in iz['hovertemplate'], iz['hovertemplate']
        assert 'AS SUPPLIED' in iz['hovertemplate']
        assert 'reported by the motor solver' not in iz['hovertemplate']

    def test_cozucu_beyani_gelirse_kunye_geri_gelir(self, client):
        r = client.post('/api/advanced-performance-analysis', json={
            'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
            'analysis_type': '3d_surface', 'grid_n': 3,
            'base_isp': 233.0, 'optimal_of_ratio': 6.2,
            'chamber_pressure': 31.0, 'design_point_source': 'solver'})
        f = _fig(r.get_json()['plot_data'])
        izler = [t for t in _izler(f)
                 if 'Design' in str(t.get('name'))]
        assert izler, [t.get('name') for t in _izler(f)]
        assert 'by the motor solver' in izler[0]['hovertemplate']
        assert 'AS SUPPLIED' not in izler[0]['hovertemplate']
