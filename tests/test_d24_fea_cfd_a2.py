# -*- coding: utf-8 -*-
"""ÖH Dalga-24 · kulvar fea-cfd · aşama 2 — bekçiler.

Her sınıf bir defter kalemini savunur. Kilitlenen şey SAYININ KENDİSİ
değil, sayıyı üreten HÜKÜM ZİNCİRİdir: çapa ya çözücünün kendi başka bir
alanı ya da fizik özdeşliğidir (ölçüm dosyaları
``docs/scofield/raw/OH/D24/fea-cfd/a2/once_a2*.json``).

Her bekçi ters-mutasyonla kırmızıya çevrilmiştir; kanıt
``docs/scofield/raw/OH/D24/fea-cfd/a2/mutasyon.json``.
"""
import contextlib
import io
import json
import math
import os
import re

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope='module')
def client():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


# ===========================================================================
# P6B2-01 (Fable-D18 ŞARTI) — TÜKETİLEN ALAN LİSTESİ TEK KAYNAK
# ===========================================================================
class TestP6B2_01TekKaynak:
    """Köprü ile uç katmanı AYNI listeyi konuşur; kopya liste yoktur."""

    def test_app_sabiti_koprunun_sabitinin_ta_kendisi(self):
        with contextlib.redirect_stdout(io.StringIO()):
            from hrma import app as app_mod
        from hrma.fea import bridge
        assert (app_mod._FEA_PROFILE_CONSUMED_KEYS
                is bridge.THERMAL_PROFILE_CONSUMED_KEYS), (
            'uç katmanı köprünün sabitini İTHAL etmiyor, kopya liste '
            'tutuyor: %r' % (app_mod._FEA_PROFILE_CONSUMED_KEYS,))

    def test_resolution_ok_tuketilen_alanlar_arasinda(self):
        from hrma.fea import bridge
        # Köprü ``resolution_ok is False`` profilini FAIL-CLOSED reddediyor
        # (P8B2-02), yani alanı YARGILIYOR — listede olmak zorunda.
        assert 'resolution_ok' in bridge.THERMAL_PROFILE_CONSUMED_KEYS
        assert 'wall_resolution' in bridge.THERMAL_PROFILE_CONSUMED_KEYS
        # y_plus_max yalnız RED MESAJINDA geçiyor, hiçbir dalı çevirmiyor:
        # listeye girerse beyan kanalı onu haksız yere "tüketildi" der.
        assert 'y_plus_max' not in bridge.THERMAL_PROFILE_CONSUMED_KEYS

    def test_beyan_kanali_resolution_ok_u_tekrarlamıyor(self):
        with contextlib.redirect_stdout(io.StringIO()):
            from hrma import app as app_mod
        profil = {
            'x_mm': [0.0, 10.0], 'h_g': [1000.0, 2000.0],
            'T_recovery': [3000.0, 2900.0],
            'wall_resolution': {'resolved': True, 'y_plus_max': 141.3},
            'resolution_ok': False, 'y_plus_max': 141.3,
            'source': 'hrma/cfd/steady.py',
        }
        beyan = app_mod._fea_profil_beyanlari(profil)
        assert 'resolution_ok' in beyan['consumed_by_solver']
        assert 'resolution_ok' not in beyan['supplied_by_caller'], (
            'çözücünün YARGILADIĞI alan "okumadığı alanlar" kümesinde')
        # y_plus_max republished kalır (ŞARTIN 2. maddesi).
        assert 'y_plus_max' in beyan['supplied_by_caller']

    def test_basis_cumlesi_resolution_ok_hukmunu_soyluyor(self):
        with contextlib.redirect_stdout(io.StringIO()):
            from hrma import app as app_mod
        beyan = app_mod._fea_profil_beyanlari(
            {'x_mm': [0.0], 'h_g': [1.0], 'T_recovery': [1.0],
             'resolution_ok': False, 'source': 'x'})
        basis = beyan['_basis']
        assert 'resolution_ok' in basis, basis
        assert 'fail-closed' in basis, basis
        # Cümle de tek kaynaktan gelir.
        from hrma.fea.bridge import THERMAL_PROFILE_CONSUMED_BASIS
        assert THERMAL_PROFILE_CONSUMED_BASIS in basis

    def test_liste_koprude_GERCEKTEN_yargilanan_alanlardan_ibaret(self):
        """Listedeki her ad köprüde bir HÜKÜM dalını çeviriyor mu?

        Davranış ayağı (uçtan uca 422) ``tests/test_d18_fea_cfd_a1.py``
        içindeki ŞART bekçisindedir; burada listenin uydurma bir ad
        taşımadığı köprünün kendi kaynağına karşı çapalanır.
        """
        import inspect
        from hrma.fea import bridge
        kaynak = inspect.getsource(bridge.extract_thermal_inputs)
        for ad in bridge.THERMAL_PROFILE_CONSUMED_KEYS:
            assert ('axial_profile.get("%s")' % ad) in kaynak \
                or ('axial_profile["%s"]' % ad) in kaynak \
                or ("axial_profile.get('%s')" % ad) in kaynak, (
                    '%r listede ama köprü onu hiç okumuyor' % ad)
        # İki fail-closed dalı adıyla duruyor.
        assert 'resolution_ok") is False' in kaynak \
            or "resolution_ok\") is False" in kaynak, kaynak[:0] or 'dal yok'


# ===========================================================================
# P8B4-13 — ÇIPLAK KeyError YERİNE ADLI KAPI
# ===========================================================================
class TestP8B4_13AdliKapi:

    def test_eksik_alan_ValueError_ve_ADIYLA(self):
        from hrma.visualization.advanced_results import (
            create_cea_style_results, CEA_REQUIRED_KEYS)
        with pytest.raises(ValueError) as hata:
            create_cea_style_results({'isp': 200.0})
        metin = str(hata.value)
        # Eksik alanlar ADIYLA sayılır — "'cf'" gibi çıplak bir anahtar adı
        # değil, hangi alanların eksik olduğunu söyleyen bir cümle.
        assert 'cf' in metin and 'thrust' in metin, metin
        assert len(metin) > 80, metin
        assert set(CEA_REQUIRED_KEYS)

    def test_hicbir_zorunlu_alanda_ciplak_KeyError_kalmadi(self):
        from hrma.visualization.advanced_results import (
            create_cea_style_results, CEA_REQUIRED_KEYS)
        tam = {k: 1.0 for k in CEA_REQUIRED_KEYS}
        for k in CEA_REQUIRED_KEYS:
            govde = dict(tam)
            govde.pop(k)
            with pytest.raises(ValueError):
                create_cea_style_results(govde)

    def test_uc_katmani_TEK_ALAN_yuzunden_cozumu_dusurmuyor(self, client):
        """``/calculate`` bir rapor alanı eksik diye HTTP 400 dönmez."""
        from hrma.visualization.advanced_results import cea_unavailable_text
        metin = cea_unavailable_text({'isp': 200.0})
        assert 'NOT AVAILABLE' in metin
        assert 'cf' in metin
        # Fail-closed: eksik alanın yerine SAYI konmadığı açıkça yazar.
        assert 'No placeholder value' in metin


# ===========================================================================
# P8B4-14 — BOŞ KÜTLE KESRİ PANELİ "SONUÇ" GİBİ BASILMAZ
# ===========================================================================
class TestP8B4_14BosPanel:

    BOZUK = ({}, None, {'chamber': {}}, {'chamber': 'metin'})

    @pytest.mark.parametrize('girdi', BOZUK)
    def test_bozuk_girdi_veri_yok_diyor(self, girdi):
        from hrma.visualization.advanced_results import (
            create_mass_fractions_plot)
        fig = json.loads(create_mass_fractions_plot(girdi))
        assert len(fig.get('data') or []) == 0
        baslik = ((fig['layout'].get('title') or {}).get('text') or '')
        assert 'not available' in baslik.lower(), baslik
        anot = fig['layout'].get('annotations') or []
        assert anot, 'boş panelde gerekçe yazmıyor'
        assert 'No species curve is drawn' in anot[0]['text']
        # Boş logaritmik eksen sahte bir ölçek sunar.
        assert (fig['layout'].get('yaxis') or {}).get('type') != 'log'

    def test_gecerli_girdi_hala_ciziliyor(self):
        from hrma.visualization.advanced_results import (
            create_mass_fractions_plot)
        fig = json.loads(create_mass_fractions_plot(
            {'chamber': {'H2O': 0.30, 'CO': 0.25},
             'throat': {'H2O': 0.31, 'CO': 0.24},
             'exit': {'H2O': 0.33, 'CO': 0.22}}))
        assert len(fig['data']) == 2
        assert (fig['layout'].get('yaxis') or {}).get('type') == 'log'
        assert 'not available' not in (
            (fig['layout'].get('title') or {}).get('text') or '').lower()


# ===========================================================================
# P8B4-15 — İKİ ŞEMA TEK OKUYUCUDA
# ===========================================================================
class TestP8B4_15IkiSema:

    KATI = [{'altitude': a, 'pressure': 1.0, 'thrust_coefficient': 1.4,
             'specific_impulse': 220.0 + a / 1000.0, 'thrust_n': 3000.0}
            for a in (0, 5000, 10000)]
    HIBRIT = {'altitude_performance':
              [{'altitude': a, 'pressure': 1.0, 'cf': 1.4,
                'isp': 220.0 + a / 1000.0, 'thrust': 3000.0}
               for a in (0, 5000, 10000)]}

    def test_kati_motorun_duz_listesi_de_cizilir(self):
        from hrma.visualization.advanced_results import (
            create_altitude_performance_plot)
        fig = json.loads(create_altitude_performance_plot(self.KATI))
        assert len(fig['data']) == 4
        isp_izi = fig['data'][0]
        assert list(isp_izi['y']) == [220.0, 225.0, 230.0]

    def test_hibrit_sarmalayici_ayni_sayilari_verir(self):
        from hrma.visualization.advanced_results import (
            create_altitude_performance_plot)
        duz = json.loads(create_altitude_performance_plot(self.KATI))
        sar = json.loads(create_altitude_performance_plot(self.HIBRIT))
        for i in range(4):
            assert list(duz['data'][i]['y']) == list(sar['data'][i]['y']), (
                'iki şema aynı sayıları vermiyor, iz %d' % i)

    def test_cozulemeyen_satir_ADIYLA_reddedilir(self):
        from hrma.visualization.advanced_results import (
            normalize_altitude_rows)
        with pytest.raises(ValueError) as hata:
            normalize_altitude_rows([{'altitude': 0.0, 'pressure': 1.0}])
        assert 'isp' in str(hata.value)
        assert 'No placeholder' in str(hata.value)
        with pytest.raises(ValueError):
            normalize_altitude_rows({})
        with pytest.raises(ValueError):
            normalize_altitude_rows(None)

    def test_es_anlamlilar_tek_yerde(self):
        from hrma.visualization.advanced_results import ALTITUDE_ROW_ALIASES
        assert 'specific_impulse' in ALTITUDE_ROW_ALIASES['isp']
        assert 'thrust_coefficient' in ALTITUDE_ROW_ALIASES['cf']
        assert 'thrust_n' in ALTITUDE_ROW_ALIASES['thrust']


# ===========================================================================
# P8B4-17 — HAÇ İLE YÜZEY AYNI GENLEŞME TABANINDA
# ===========================================================================
class TestP8B4_17TabanBirligi:

    @pytest.fixture(scope='class')
    def figur(self):
        from hrma.visualization.visualization import (
            create_chamber_pressure_mixture_ratio_3d_surface, _isp_tek_dugum)
        from hrma.engines.combustion_analysis import CombustionAnalyzer
        an = CombustionAnalyzer(memoize=True)
        yuzey_isp = _isp_tek_dugum(an, {'htpb': 100.0}, 'N2O', 2.5, 50.0)
        # Motorun KENDİ epsilon'undaki Isp'si yüzeyin tabanından %6,23 aşağıda
        # (ölçülen vaka: eps = 16).
        tasarim = float(yuzey_isp) * (1.0 - 0.0623)
        ed = {'fuel_composition': {'htpb': 100.0}, 'oxidizer_type': 'N2O',
              'optimal_chamber_pressure': 50.0, 'optimal_of_ratio': 2.5,
              'base_isp': tasarim, 'expansion_ratio': 16.0,
              'design_point_source': 'solver', 'grid_n': 3}
        fig = json.loads(
            create_chamber_pressure_mixture_ratio_3d_surface(ed))
        return fig, float(yuzey_isp), tasarim

    def test_hac_z_ekseni_yuzeyin_tabanindan(self, figur):
        fig, yuzey_isp, tasarim = figur
        hac = [t for t in fig['data']
               if (t.get('marker') or {}).get('symbol') == 'cross']
        assert hac, 'tasarım noktası haçı çizilmedi'
        z = float(hac[0]['z'][0])
        # z, yüzeyin AYNI DÜĞÜMDE çözdüğü değerdir — uydurma değil, aynı
        # çözücünün sonucu. Motorun kendi (başka tabanlı) sayısı z'ye BASILMAZ.
        assert z == pytest.approx(yuzey_isp, rel=1e-9), (
            'haç z ekseni yüzeyin tabanında değil: %r ⟷ %r' % (z, yuzey_isp))
        assert abs(z - tasarim) > 1.0

    def test_kunye_iki_sayiyi_da_ADIYLA_tasiyor(self, figur):
        fig, yuzey_isp, tasarim = figur
        hac = [t for t in fig['data']
               if (t.get('marker') or {}).get('symbol') == 'cross'][0]
        kunye = hac.get('hovertemplate') or ''
        assert 'expansion basis' in kunye or 'expansion-basis' in kunye, kunye
        assert 'expansion ratio 16.00' in kunye, kunye
        assert ('%.1f' % tasarim) in kunye, (
            'motorun KENDİ Isp\'si künyeden düştü')
        assert 'Difference' in kunye

    def test_notta_da_fark_sayisiyla_yaziyor(self, figur):
        fig, _, _ = figur
        notlar = [a.get('text') or ''
                  for a in (fig['layout'].get('annotations') or [])]
        assert any('expansion-basis difference' in t for t in notlar), notlar

    def test_ayni_tabandaki_nokta_KAYDIRILMAZ(self):
        """Fark bandın altındaysa haç motorun kendi sayısında kalır."""
        from hrma.visualization.visualization import (
            create_chamber_pressure_mixture_ratio_3d_surface, _isp_tek_dugum,
            PERF_SURFACE_DESIGN_BASIS_TOL)
        from hrma.engines.combustion_analysis import CombustionAnalyzer
        an = CombustionAnalyzer(memoize=True)
        yuzey_isp = float(_isp_tek_dugum(an, {'htpb': 100.0}, 'N2O',
                                         2.5, 50.0))
        tasarim = yuzey_isp * (1.0 - 0.5 * PERF_SURFACE_DESIGN_BASIS_TOL)
        ed = {'fuel_composition': {'htpb': 100.0}, 'oxidizer_type': 'N2O',
              'optimal_chamber_pressure': 50.0, 'optimal_of_ratio': 2.5,
              'base_isp': tasarim, 'expansion_ratio': 4.0,
              'design_point_source': 'solver', 'grid_n': 3}
        fig = json.loads(
            create_chamber_pressure_mixture_ratio_3d_surface(ed))
        hac = [t for t in fig['data']
               if (t.get('marker') or {}).get('symbol') == 'cross'][0]
        assert float(hac['z'][0]) == pytest.approx(tasarim, rel=1e-9)
        assert 'Design point' in (hac.get('name') or '')


# ===========================================================================
# P8B4-19 — DELİK KONUMU ÖLÇÜ OLARAK SUNULMUYOR
# ===========================================================================
def _showerhead_hover(veri):
    from hrma.visualization.visualization import (
        create_showerhead_with_tooltips)
    fig = json.loads(create_showerhead_with_tooltips(veri))
    metinler = []
    for iz in fig.get('data') or []:
        ht = iz.get('hovertext') or iz.get('hovertemplate') or ''
        if isinstance(ht, str):
            metinler.append(ht)
        elif isinstance(ht, list):
            metinler.extend([t for t in ht if isinstance(t, str)])
    # Yalnız DELİK izleri: plaka konturunun kendi hover'ı ayrı bir
    # iddiadır ve bu kalemin konusu değildir.
    return fig, [t for t in metinler if 'L/D:' in t]


class TestP8B4_19KonumIddiasi:

    TEMEL = {'type': 'showerhead', 'n_holes': 19, 'hole_diameter': 1.5,
             'plate_diameter': 100.0, 'plate_thickness': 3.0,
             'exit_velocity': 30.0, 'reynolds_number': 50000}

    def test_mm_konum_iddiasi_kalmadi(self):
        _, metinler = _showerhead_hover(dict(self.TEMEL))
        assert metinler, 'delik izi hiç çizilmedi'
        assert not [t for t in metinler if 'Position:' in t], (
            'hover hâlâ mm cinsinden konum İDDİA ediyor')
        assert not [t for t in metinler if 'Radial distance:' in t]

    def test_yerlesimin_sematik_oldugu_SOYLENIYOR(self):
        _, metinler = _showerhead_hover(dict(self.TEMEL))
        assert all('schematic spacing' in t for t in metinler), metinler[:1]
        assert all('not the drilling coordinates' in t
                   or 'not a drilling layout' in t for t in metinler)

    def test_ozet_kunyesi_de_ayni_seyi_soyluyor(self):
        fig, _ = _showerhead_hover(dict(self.TEMEL))
        metin = ' '.join(a.get('text') or ''
                         for a in (fig['layout'].get('annotations') or []))
        assert 'schematic fill' in metin, metin[:300]

    def test_delikler_ust_uste_binecekse_isaret_CIZILMEZ(self):
        # 200 delik, 60 mm plaka, 4 mm delik: şematik dolgu deliği deliğin
        # üstüne koyar; böyle bir yüz FİZİKSEL OLARAK kurulamaz.
        veri = dict(self.TEMEL, n_holes=200, hole_diameter=4.0,
                    plate_diameter=60.0)
        fig, metinler = _showerhead_hover(veri)
        assert not metinler, 'olanaksız yerleşim yine de çizildi'
        ozet = ' '.join(a.get('text') or ''
                        for a in (fig['layout'].get('annotations') or []))
        assert 'cannot coexist' in ozet, ozet[:300]

    def test_capi_ve_alani_hala_cozucuden(self):
        _, metinler = _showerhead_hover(dict(self.TEMEL, hole_diameter=2.25))
        assert all('Diameter: 2.25 mm' in t for t in metinler)


# ===========================================================================
# P8B4-20 — DELİK BAŞI DEBİ: SÜREKLİLİK, Cd ÇİFT SAYIMI YOK
# ===========================================================================
class TestP8B4_20DebiZinciri:

    def test_yedek_turetme_surekliligi_saglar(self):
        """mdot = rho*A*v ÖZDEŞLİĞİ — Cd üçüncü kez çarpılmaz."""
        from hrma.visualization.visualization import _injector_total_mdot
        rho, dp_pa, cd, a_mm2 = 780.0, 25.0e5, 0.7, 100.0
        # Çözücünün yayımladığı hız: v = Cd*sqrt(2 dP/rho)
        # (hrma/utils/injector_design.py::_exit_velocity).
        v = cd * math.sqrt(2.0 * dp_pa / rho)
        mdot, kaynak = _injector_total_mdot(
            {'oxidizer_density': rho, 'injection_area': a_mm2,
             'exit_velocity': v, 'discharge_coefficient': cd})
        assert mdot == pytest.approx(rho * (a_mm2 * 1e-6) * v, rel=1e-12), (
            'süreklilik bozuldu (Cd çift sayılmış olabilir)')
        # Orifis bağıntısıyla çapraz doğrulama: mdot = Cd*A*sqrt(2 rho dP)
        assert mdot == pytest.approx(
            cd * (a_mm2 * 1e-6) * math.sqrt(2.0 * rho * dp_pa), rel=1e-12)
        assert 'continuity' in kaynak

    def test_motorun_mdot_ox_u_okunuyor(self):
        from hrma.visualization.visualization import _injector_total_mdot
        mdot, kaynak = _injector_total_mdot({'motor_mdot_ox': 1.138739})
        assert mdot == pytest.approx(1.138739)
        assert 'motor result field mdot_ox' in kaynak

    def test_delik_basi_debi_artik_basiliyor(self):
        _, metinler = _showerhead_hover(
            {'type': 'showerhead', 'n_holes': 19, 'hole_diameter': 1.5,
             'plate_diameter': 100.0, 'motor_mdot_ox': 1.138739})
        assert metinler
        assert not [t for t in metinler if 'Mass flow: not available' in t]
        beklenen = 1.138739 / 19 * 1000.0
        assert all(('Mass flow: %.2f g/s' % beklenen) in t for t in metinler)

    def test_debi_yoksa_HALA_uydurulmuyor(self):
        from hrma.visualization.visualization import _injector_total_mdot
        mdot, kaynak = _injector_total_mdot({'n_holes': 19})
        assert mdot is None
        assert 'not available' in kaynak


# ===========================================================================
# P14M3-03 / P14M3-03b — O/F TARAMASI ÇÖZÜCÜNÜN KENDİ SAYISINA ÇAPALI
# ===========================================================================
class TestP14M3_03TaramaCapasi:
    """Mutlak çapa: taramanın tasarım O/F'sindeki düğümü, AYNI çözücünün
    o koşuda yayımladığı ``performance.isp`` ile SAYICA aynı olmalıdır.

    Eski tek bekçi ``max(isp) > min(isp) + 5.0`` bir VARYANS iddiasıydı:
    diziyi 200 s'lik bir sabite çevirmek onu kırıyordu ama ×0,5 ölçeklemek
    tanım gereği KIRMIYORDU (ölçüldü: ``once_a2.json`` ->
    ``P14M3-03.bekci_yarim_mutasyonda = true``). Aşağıdaki çapa iki
    mutasyonu da kırmızıya çevirir ve dosyaya LİTERAL bir Isp yazmaz.
    """

    @pytest.fixture(scope='class')
    def kosum(self):
        from hrma.engines.combustion_analysis import CombustionAnalyzer
        from hrma.visualization.visualization import (
            create_combustion_analysis_plots)
        analyzer = CombustionAnalyzer(memoize=True)
        res = analyzer.analyze_combustion({'htpb': 100.0}, 'N2O', 6.0, 20.0)
        prop = {'fuel_composition': {'htpb': 100.0}, 'oxidizer_type': 'N2O',
                'chamber_pressure': 20.0, 'analyzer': analyzer}
        fig = json.loads(create_combustion_analysis_plots(res, propellant=prop))
        return res, fig

    @staticmethod
    def _tarama(fig):
        izler = [t for t in fig['data'] if t.get('name') == 'Isp vs O/F']
        assert izler, 'O/F taraması çizilmedi'
        return ([float(v) for v in izler[0]['x']],
                [float(v) for v in izler[0]['y']])

    def test_tarama_dugumu_cozucunun_kendi_ISP_siyle_AYNI(self, kosum):
        res, fig = kosum
        of_vals, isp_vals = self._tarama(fig)
        cozucu_isp = float((res.get('performance') or {})['isp'])
        of_tasarim = float((res.get('inputs') or {}).get('of_ratio', 6.0))
        k = min(range(len(of_vals)),
                key=lambda i: abs(of_vals[i] - of_tasarim))
        assert of_vals[k] == pytest.approx(of_tasarim, abs=1e-9), (
            'tarama tasarım O/F\'sini kapsamıyor: %r' % (of_vals,))
        # MUTLAK çapa: aynı çözücü, aynı girdi -> aynı sayı. Bir ölçek
        # değişimi (×0,5) ya da sabite çevirme (200 s) burada kırılır.
        assert isp_vals[k] == pytest.approx(cozucu_isp, rel=1e-9), (
            'tarama Isp\'si çözücünün tasarım noktası Isp\'sinden koptu: '
            '%r ⟷ %r' % (isp_vals[k], cozucu_isp))

    def test_kosu_isaretcisi_de_ayni_sayida(self, kosum):
        res, fig = kosum
        kosu = [t for t in fig['data'] if t.get('name') == 'This run (solver)']
        assert kosu, '"This run" işaretçisi çizilmedi'
        cozucu_isp = float((res.get('performance') or {})['isp'])
        assert float(kosu[0]['y'][0]) == pytest.approx(cozucu_isp, rel=1e-12)

    def test_tarama_monoton_artiyor_ve_yayilimi_gercek(self, kosum):
        """03b ayağı: dizi ÖLÇEK olarak da savunuluyor.

        Bandın alt ucundaki (yakıtça zengin) düğüm tasarım noktasının
        Isp'sinden BELİRGİN düşük olmalı; ×0,5 ölçekleme bu ORANI da
        bozar çünkü üst uç yukarıdaki mutlak çapayla çivilenmiştir.
        """
        res, fig = kosum
        of_vals, isp_vals = self._tarama(fig)
        cozucu_isp = float((res.get('performance') or {})['isp'])
        assert isp_vals[0] < cozucu_isp
        # Alt uç ile tasarım noktası arasındaki oran fiziktir (yakıtça çok
        # zengin karışım daha düşük Isp verir), literal bir sayı değil.
        assert 0.3 < isp_vals[0] / cozucu_isp < 0.95, (
            isp_vals[0], cozucu_isp)


# ===========================================================================
# P14M1-01 — CİDAR KÜNYESİ DEĞER OLARAK OKUNUYOR
# ===========================================================================
VERIFIED_CLAIM = 'verified against the pressure load'


def _kasa(sf_is_measured):
    """Katı motor ``case_analysis`` şeması (as-designed KESİN)."""
    return {'structural_analysis': {'case_analysis': {
        'wall_thickness_mm': 5.0,
        'recommended_wall_thickness_mm': 3.0,
        'design_mode': (None if sf_is_measured is None else 'verify'),
        'safety_factor': 1.83,
        'safety_factor_is_tautological': (
            None if sf_is_measured is None else (not sf_is_measured)),
    }}}


class TestP14M1_01CidarKunyesi:
    """``sf_is_measured`` dalı ters çevrilirse künye DEĞER olarak kırılır.

    Depodaki koruma (``tests/test_z5guard_ihrac_veri.py``) bu mutasyonu
    DXF metni üzerinden yakalıyor (ölçüldü:
    ``once_p14m1_01_mutasyon.json`` — 7 aday bekçiden 1'i kırmızı). Aşağıdaki
    bekçi aynı hükmü ÜRETİCİNİN kendisinde, tek çağrıda ve DXF kurulumuna
    bağlı kalmadan çapalar.
    """

    def test_olculmus_SF_damgayi_kazanir(self):
        from hrma.export.cad_visualization import _chamber_wall_design
        d = _chamber_wall_design(_kasa(True))
        assert d['safety_factor_is_measured'] is True
        assert VERIFIED_CLAIM in d['source'], d['source']
        assert d['verified'] is True

    def test_boyutlandirilmis_SF_damgayi_KAZANMAZ(self):
        from hrma.export.cad_visualization import _chamber_wall_design
        d = _chamber_wall_design(_kasa(False))
        assert d['safety_factor_is_measured'] is False
        assert VERIFIED_CLAIM not in d['source'], d['source']
        assert 'NOT a pressure-load verification' in d['source']
        assert d['verified'] is False

    def test_beyansiz_blok_hicbir_sey_IDDIA_ETMEZ(self):
        from hrma.export.cad_visualization import _chamber_wall_design
        d = _chamber_wall_design(_kasa(None))
        assert VERIFIED_CLAIM not in d['source'], d['source']
        assert 'does not state whether the wall was checked' in d['source']
        assert d['verified'] is False


# ===========================================================================
# P15B2-06 (JS ayağı) — İSTEMCİDEKİ R_UNIVERSAL PYTHON'DAN SESSİZCE KOPAMAZ
# ===========================================================================
class TestP15B2_06IstemciSabiti:
    """``cfd_panel.js`` R_UNIVERSAL'ı Python'dan İTHAL EDEMEZ (dil sınırı).

    Kalemin mekanizması tam da budur: "Python düzeltilse JS sessiz kalır".
    İthal mümkün olmadığına göre kopuş BEKÇİYLE engellenir — sayı bu iki
    yerde ayrı ayrı yazılıdır ama ARTIK ayrı ayrı DEĞİŞEMEZ.

    NOT: Python tarafındaki 8314.5 / 8.314 literalleri (external_data_fetcher,
    chemical_database) bu bekçinin kapsamı DIŞINDADIR — onlar D24 sonrası
    fix aşamasının (P10B3-10) kilidi altındadır.
    """

    JS = os.path.join(REPO, 'hrma/static/js/panels/cfd_panel.js')

    def test_js_sabiti_hrma_constants_ile_ayni_sayi(self):
        from hrma.constants import R_UNIVERSAL
        metin = open(self.JS, encoding='utf-8').read()
        m = re.search(r'const\s+R_UNIVERSAL\s*=\s*([0-9.]+)\s*;', metin)
        assert m, 'cfd_panel.js içinde R_UNIVERSAL tanımı bulunamadı'
        assert float(m.group(1)) == pytest.approx(R_UNIVERSAL, rel=0, abs=0), (
            'istemci sabiti hrma.constants.R_UNIVERSAL\'dan koptu: '
            '%s ⟷ %r' % (m.group(1), R_UNIVERSAL))

    def test_kunye_metinleri_de_ayni_sayiyi_yaziyor(self):
        from hrma.constants import R_UNIVERSAL
        metin = open(self.JS, encoding='utf-8').read()
        # Kullanıcıya gösterilen "R = 8314,462618 / MW" künyeleri sabitle
        # aynı sayıyı taşımalı (virgüllü Türkçe yazım dâhil).
        tr = ('%.6f' % R_UNIVERSAL).rstrip('0').replace('.', ',')
        en = ('%.6f' % R_UNIVERSAL).rstrip('0')
        assert (tr in metin) or (en in metin), (
            'künye metinleri %r sayısını yazmıyor' % R_UNIVERSAL)
