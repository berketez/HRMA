"""ÖH Dalga-16 · kulvar fea-cfd · aşama 1 bekçileri.

Kapsanan kalemler (ölçüm: docs/scofield/raw/OH/D16/fea-cfd/a1/once.json ⟷
sonra.json, ters-mutasyon: .../mutasyon.py):

  P16B3-42  /api/cfd/nozzle fiziksel imkânsızlıkta pahalı koşu (P_ortam ≥ P0)
            + sayısal alanlarda bool tuzağı
  P6B2-01   çözünmemiş duvardan gelen h_g'nin FEA köprüsüne kapısız girmesi
  P6B3-01   boğulmamış rejimde uydurma süpersonik çekirdekten ayrılma hükmü
  OH-Z2-03  kapak formülü kopyasının bekçi içinde yaşaması

Bekçilerin HEPSİ ters-mutasyonla kırmızıya döndürülerek doğrulanmıştır.
"""
import time

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# P16B3-42 — /api/cfd/nozzle girdi kapıları
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


#: Ölçülen kusur koşusu 11,1 saniye sürüyordu (once.json K1). Kapı çalışıyorsa
#: yanıt çözücüye HİÇ girmez; bu tavan makine hızından bağımsız olarak
#: "tam CFD koşusu YAPILMADI" der (en yavaş ölçülen kusur koşusunun onda biri).
_KOSU_YAPILMADI_TAVANI_S = 2.0

_KONTUR = {'points': [[0.0, 0.05], [0.05, 0.03], [0.08, 0.02],
                      [0.14, 0.03], [0.20, 0.04]]}
_TABAN = {'nozzle_contour': _KONTUR, 'P0_Pa': 2.0e6, 'T0_K': 3000.0,
          'gamma': 1.2, 'R_J_per_kgK': 320.0, 'P_ambient_Pa': 101325.0,
          'resolution': 'coarse'}


class TestP16B3_42CfdLuleGirdiKapisi:

    @pytest.mark.parametrize('p_ortam', [2.0e6, 5.0e6])
    def test_ortam_basinci_oda_basincindan_kucuk_olmali(self, istemci,
                                                        p_ortam):
        """P_ortam ≥ P0 iken lüleden akış YOKTUR: koşu başlamadan reddedilir.

        ÖLÇÜLDÜ (once.json K1): P_ortam = 5e6 > P0 = 2e6 gövdesi HTTP 200 +
        11,08 s + 152 658 baytlık sayı + ``separation.separated = True``
        üretiyordu — var olmayan bir akışın ayrılma hükmü. Kardeş uç
        ``/api/flow-analysis`` aynı vakayı 0,0 saniyede 400 ile reddediyor
        (K3); iki ucun aynı fiziksel imkânsızlığa aynı cevabı vermesi
        sözleşmedir.
        """
        t0 = time.perf_counter()
        r = istemci.post('/api/cfd/nozzle', json=dict(_TABAN,
                                                      P_ambient_Pa=p_ortam))
        sure = time.perf_counter() - t0
        assert r.status_code == 400, (
            f'P_ortam = {p_ortam:g} Pa >= P0 = {_TABAN["P0_Pa"]:g} Pa iken '
            f'uç {r.status_code} döndü — akış olmayan bir lüle çözüldü')
        j = r.get_json() or {}
        assert j.get('field') == 'P_ambient_Pa', j
        assert sure < _KOSU_YAPILMADI_TAVANI_S, (
            f'red {sure:.2f} s sürdü: kapı çözücüden SONRA çalışıyor, '
            f'pahalı koşu yine harcandı')

    @pytest.mark.parametrize('alan', ['P0_Pa', 'T0_K', 'gamma',
                                      'R_J_per_kgK', 'P_ambient_Pa'])
    def test_bool_sayisal_alan_olarak_kabul_edilmez(self, istemci, alan):
        """``True`` bir basınç/sıcaklık değildir — ``float(True)`` = 1,0.

        ÖLÇÜLDÜ (once.json K2): ``P0_Pa = true`` gövdesi 1 Pa'lık bir kamara
        kurup HTTP 200 + 10,38 saniyelik tam CFD koşusu + 153 312 bayt sayı
        üretiyordu. Aynı uçtaki ``max_iterations`` kapısı bool'u zaten
        reddediyordu; disiplin sayısal alanların hepsine uygulanır.
        """
        t0 = time.perf_counter()
        r = istemci.post('/api/cfd/nozzle', json=dict(_TABAN, **{alan: True}))
        sure = time.perf_counter() - t0
        assert r.status_code == 400, (
            f'{alan} = True iken uç {r.status_code} döndü')
        j = r.get_json() or {}
        assert j.get('field') == alan, j
        # Uç 400'de kodu ``error``, insan metnini ``message`` alanında verir.
        assert 'boolean' in (j.get('message') or ''), j
        assert sure < _KOSU_YAPILMADI_TAVANI_S, (
            f'red {sure:.2f} s sürdü — koşu yine başlamış')

    def test_gecerli_govde_hala_kosuyor(self, istemci):
        """Kapı yalnız imkânsız vakayı keser: geçerli koşu 200 kalır."""
        r = istemci.post('/api/cfd/nozzle',
                         json=dict(_TABAN, max_iterations=600))
        assert r.status_code == 200, r.get_json()


# ---------------------------------------------------------------------------
# P6B2-01 — duvar çözünürlüğü hükmü ve FEA köprüsü kapısı
# ---------------------------------------------------------------------------

class TestP6B2_01DuvarCozunurlugu:

    def test_y_plus_kenarlari_TEK_KAYNAK_yapisal(self):
        """Uç ile köprü AYNI y⁺ kenarlarını kullanır (ikinci sayı yok).

        Kenarlar ``hrma/cfd/wall_output.py``te tanımlıdır; ``hrma/app.py``
        onları İTHAL eder. Bu bekçi kimlik (``is``) sınar: bir gün app.py'ye
        elle 1.0/30.0 yazılırsa değer eşit olurdu ama bağ kopardı.
        """
        from hrma import app as app_modulu
        from hrma.cfd import wall_output
        assert (app_modulu.CFD_Y_PLUS_WALL_RESOLVED
                is wall_output.Y_PLUS_WALL_RESOLVED)
        assert (app_modulu.CFD_Y_PLUS_LOG_LAYER
                is wall_output.Y_PLUS_LOG_LAYER)

    def test_duvar_cozunurlugu_modellenmeyenler_arasinda(self):
        """Baskın hata kaynağı ``not_modelled`` listesinde ADIYLA durur.

        ÖLÇÜLDÜ (once.json K4): liste ``radiation`` / ``wall_roughness`` /
        ``wall_temperature_coupling`` idi — ölçülen baskın hata kaynağı olan
        duvar çözünürlüğü listede YOKTU.
        """
        from hrma.cfd.wall_output import WALL_OUTPUT_NOT_MODELLED
        assert 'wall_resolution' in WALL_OUTPUT_NOT_MODELLED
        metin = WALL_OUTPUT_NOT_MODELLED['wall_resolution']
        assert 'y⁺' in metin and 'EMNİYETSİZ' in metin.upper()

    @pytest.mark.parametrize('y_max, beklenen_cozuldu, beklenen_rejim', [
        (0.82, True, 'wall_resolved'),
        (12.0, False, 'buffer_layer'),
        (268.86392134602016, False, 'log_layer'),   # ölçülen ürün koşusu
        (None, None, None),
    ])
    def test_cozunurluk_hukmu_olculen_y_plus_ten(self, y_max,
                                                 beklenen_cozuldu,
                                                 beklenen_rejim):
        from hrma.cfd.wall_output import wall_resolution_declaration
        hukum = wall_resolution_declaration({'y_plus_achieved_max': y_max})
        assert hukum['resolved'] is beklenen_cozuldu
        assert hukum['regime'] == beklenen_rejim
        assert hukum['y_plus_max'] == y_max

    def test_profil_cozunurluk_hukmunu_TASIYOR_yapisal(self):
        """``thermal_axial_profile`` çıktısı hükmü profille birlikte taşır.

        Uyarı eskiden yalnız uç yanıtının BAŞKA bir bloğundaydı
        (``viscous.y_plus_badge``); köprü payload'ı forward edildiğinde
        geride kalıyordu. Bu bekçi kaynak düzeyinde bağı sınar (viskoz koşu
        pahalıdır: ölçülen 23,3 s / koşu).
        """
        import ast
        import inspect

        from hrma.cfd import wall_output
        agac = ast.parse(inspect.getsource(wall_output.thermal_axial_profile))
        anahtarlar = {d.value for n in ast.walk(agac)
                      if isinstance(n, ast.Dict)
                      for d in n.keys
                      if isinstance(d, ast.Constant)
                      and isinstance(d.value, str)}
        assert 'wall_resolution' in anahtarlar, (
            'thermal_axial_profile çıktısı wall_resolution taşımıyor')


class TestP6B2_01KopruKapisi:
    """FEA köprüsü çözünmemiş duvardan gelen h_g'yi KABUL ETMEZ."""

    L_CONV, L_DIV = 0.12, 0.18
    R_CH, R_TH, R_EX = 0.040, 0.025, 0.040

    @classmethod
    def _yaricap(cls, z):
        z = np.asarray(z, dtype=float)
        conv = cls.R_TH + (cls.R_CH - cls.R_TH) * (
            0.5 + 0.5 * np.cos(np.pi * np.clip(z, 0.0, cls.L_CONV)
                               / cls.L_CONV))
        div = cls.R_TH + (cls.R_EX - cls.R_TH) * (
            0.5 - 0.5 * np.cos(np.pi * np.clip(z - cls.L_CONV, 0.0, cls.L_DIV)
                               / cls.L_DIV))
        return np.where(z < cls.L_CONV, conv, div)

    @pytest.fixture(scope='class')
    def motor_ve_profil(self):
        z = np.linspace(0.0, self.L_CONV + self.L_DIV, 41)
        r = self._yaricap(z)
        kontur = [[float(a), float(b)] for a, b in zip(z, r)]
        motor = {
            'nozzle_contour': {'points': kontur},
            'structural_analysis': {
                'chamber_analysis': {'wall_thickness_used_mm': 3.0,
                                     'design_mode': 'verification_case'},
                'design_parameters': {'material': 'steel_4130'},
                'material_properties': {'yield_strength': 460e6}},
            'chamber_pressure': 40.0,
            'burn_time': 5.0,
        }
        profil = {
            'x_mm': (z * 1000.0).tolist(),
            # h(z) tepesi boğazda (köprünün eksen kapısı bunu ister); bu bir
            # TEST FİKSTÜRÜDÜR, ürün sayısı değildir.
            'h_g': ((self.R_TH / r) ** 1.8 * 4000.0).tolist(),
            'T_recovery': np.full(z.shape, 2800.0).tolist(),
        }
        return motor, profil

    def test_cozunmemis_duvar_profili_REDDEDILIR(self, motor_ve_profil):
        """y⁺ = 268,86 olan ölçülmüş ürün koşusu fail-closed reddedilir."""
        from hrma.fea.bridge import (BRIDGE_STATUS_NOT_MODELLED,
                                     extract_thermal_inputs)
        motor, profil = motor_ve_profil
        kirli = dict(profil, wall_resolution={
            'resolved': False, 'y_plus_max': 268.86392134602016,
            'y_plus_wall_resolved_edge': 1.0, 'regime': 'log_layer'})
        cikti = extract_thermal_inputs(motor, axial_profile=kirli)
        assert cikti['status'] == BRIDGE_STATUS_NOT_MODELLED, (
            'çözünmemiş duvardan gelen h_g termal FEA sınır koşulu oldu')
        assert 'ÇÖZÜNMEMİŞ' in cikti['reason']
        assert '268' in cikti['reason'], (
            'gerekçe ÖLÇÜLEN y⁺ değerini taşımıyor')

    def test_olculemeyen_y_plus_de_REDDEDILIR(self, motor_ve_profil):
        """``resolved is None`` ("ölçülemedi") ile "çözüldü" bir tutulmaz."""
        from hrma.fea.bridge import (BRIDGE_STATUS_NOT_MODELLED,
                                     extract_thermal_inputs)
        motor, profil = motor_ve_profil
        kirli = dict(profil, wall_resolution={
            'resolved': None, 'y_plus_max': None,
            'y_plus_wall_resolved_edge': 1.0, 'regime': None})
        cikti = extract_thermal_inputs(motor, axial_profile=kirli)
        assert cikti['status'] == BRIDGE_STATUS_NOT_MODELLED

    def test_cozulmus_duvar_ve_blogu_olmayan_profil_KABUL_EDILIR(
            self, motor_ve_profil):
        """Kapı yalnız çözünmemiş duvarı keser.

        Duvar-çözümlü CFD profili (y⁺ ≤ 1) ve Bartz yolundan gelen
        bloksuz profil (``/api/analysis/wall-profile``; orada duvar
        çözünürlüğü diye bir kavram yoktur) etkilenmez.
        """
        from hrma.fea.bridge import BRIDGE_STATUS_OK, extract_thermal_inputs
        motor, profil = motor_ve_profil
        temiz = dict(profil, wall_resolution={
            'resolved': True, 'y_plus_max': 0.82,
            'y_plus_wall_resolved_edge': 1.0, 'regime': 'wall_resolved'})
        assert extract_thermal_inputs(
            motor, axial_profile=temiz)['status'] == BRIDGE_STATUS_OK
        assert extract_thermal_inputs(
            motor, axial_profile=dict(profil))['status'] == BRIDGE_STATUS_OK


# ---------------------------------------------------------------------------
# P6B3-01 — boğulmamış rejimde ayrılma hükmü
# ---------------------------------------------------------------------------

class TestP6B3_01RejimKapisi:

    def test_bogulmamis_rejimde_ayrilma_hukmu_VERILMEZ(self):
        """NPR = 1,005'te ayrılma hükmü ve uydurma çekirdek yayımlanmaz.

        ÖLÇÜLDÜ (once.json K5): P0 = 20 bar, Pa = 0,995·P0, ε = 6, γ = 1,2 →
        ``separated = True``, ``full_flow_exit.mach = 2,9173``. Yarı-1B
        çözümün kendi maks Mach'ı 0,72 idi: lülede hiçbir yerde ses-üstü
        akış yokken tam-akan süpersonik çekirdekten hüküm veriliyordu.
        """
        from hrma.flow.separation import assess_separation
        s = assess_separation(P0=20e5, Pa=0.995 * 20e5, gamma=1.2,
                              area_ratio_exit=6.0)
        assert s['separated'] is None, (
            'boğulmamış lülede ayrılma hükmü verildi')
        assert s['full_flow_exit'] is None, (
            'var olmayan süpersonik çekirdek yayımlandı')
        assert s['criteria'] == {}
        assert 'BOĞULMAMIŞ' in s['not_applicable_reason']

    @pytest.mark.parametrize('Pa, eps, beklenen', [
        (101325.0, 6.0, False),     # boğulmuş, adapte yakını → ayrılma yok
        (101325.0, 40.0, True),     # derin aşırı genleşme → ayrılma var
    ])
    def test_bogulmus_rejim_ETKILENMEZ(self, Pa, eps, beklenen):
        """Kapı yalnız boğulmamış bandı keser; boğulmuş hüküm aynen kalır."""
        from hrma.flow.separation import assess_separation
        s = assess_separation(P0=20e5, Pa=Pa, gamma=1.2,
                              area_ratio_exit=eps)
        assert s['separated'] is beklenen
        assert s['full_flow_exit'] is not None

    def test_bogulma_siniri_TEK_KAYNAKTAN_yapisal(self):
        """Birinci kritik ``quasi1d.critical_pressures``ten gelir."""
        import ast
        import inspect

        from hrma.flow import separation
        kaynak = inspect.getsource(separation.assess_separation)
        assert 'critical_pressures' in kaynak, (
            'boğulma sınırı modül içinde ikinci kez türetilmiş olabilir')
        agac = ast.parse(kaynak)
        sabitler = {n.value for n in ast.walk(agac)
                    if isinstance(n, ast.Constant)
                    and isinstance(n.value, float)}
        assert 1.772 not in sabitler and 1.8 not in sabitler, (
            'boğulma basınç oranı elle yazılmış bir sabite düşmüş')


# ---------------------------------------------------------------------------
# OH-Z2-03 — kapak formülü kopyası bekçinin içinde yaşamıyor
# ---------------------------------------------------------------------------

class TestOHZ2_03KapakFormuluKopyasi:

    def test_bekci_urunun_cozumleyicisini_cagiriyor_yapisal(self):
        """``test_faz5_cizim_birim.py`` yedek formülün KOPYASINI taşımaz.

        Kopya iki şeyi bozuyordu: sabitler ikinci kez tanımlanıyordu
        (tek kaynak ``cad_visualization.CAP_FALLBACK_*``) ve kopya yalnız
        YEDEK dalı tanıdığı için katı/sıvı bir gün ``end_cap_analysis``
        yayımlarsa bekçi KUSURSUZ üründe kırmızıya dönerdi.
        """
        import pathlib

        kaynak = (pathlib.Path(__file__).parent
                  / 'test_faz5_cizim_birim.py').read_text(encoding='utf-8')
        govde = kaynak.split(
            'def test_dxf_axial_span_matches_the_step_solid', 1)[1]
        govde = govde.split('\n    @pytest.fixture', 1)[0]
        assert '_front_cap_design' in govde, (
            'bekçi ürünün kapak çözümleyicisini çağırmıyor')
        assert 'min(max(1.6 * wall_mm' not in govde, (
            'yedek kapak formülünün kopyası hâlâ testin içinde')

    def test_yedek_sabitler_tek_yerde(self):
        """Sabitlerin adlandırılmış tek tanımı üründe durur."""
        from hrma.export import cad_visualization as cv
        assert cv.CAP_FALLBACK_WALL_MULTIPLIER == 1.6
        assert cv.CAP_FALLBACK_MIN_MM == 8.0
        assert cv.CAP_FALLBACK_RADIUS_FRACTION == 0.3
        # Çözümleyici yedek dalda TAM olarak bu sabitlerden hesaplar.
        beklenen = min(max(1.6 * 5.0, 8.0), 0.3 * 50.0 + 8.0)
        assert cv._front_cap_design(
            {}, wall_mm=5.0, bore_radius_mm=50.0)['thickness_mm'] == beklenen
