# ÖH Dalga-20 — kulvar fea-cfd, aşama 1/1 bekçileri
"""D20 fea-cfd onarımlarının bekçileri (ÖK-05: her onarım ters-mutasyonla).

Kalemler:
  * **P6B2-02** — CFD profilinin KENDİ ``_basis`` metni ("Bartz ile sessizce
    değiştirme YASAK") köprünün künye sözlüğünde ad çakışması yüzünden
    SESSİZCE EZİLİYORDU. Ölçüm: docs/scofield/raw/OH/D20/fea-cfd/a1/
    once_p6b2_02.json ('sessiz' izi 0) ⟷ sonra_p6b2_02.json ('sessiz' 1).
  * **OH-D16-04 [F5]** — ürün ucunda duvar-çözümlü (y⁺ ≤ 1) ızgara seçeneği
    YOKTU; ``y_plus_target`` yalnız beyandı ve CFD→termal FEA köprüsü
    hiçbir ürün koşusunda açılamıyordu. Ölçüm: .../olcum_ohd16_04.json.

Bekçiler UCUZDUR: viskoz CFD koşumu (dakika sınıfı) bu dosyada KOŞULMAZ;
koşumun ölçümü kanıt dizinindeki json'lardadır. Burada sözleşmenin
kendisi kilitlenir — hangi fonksiyonun çağrıldığı, hangi girdinin
reddedildiği, hangi anahtarın taşındığı.
"""
import numpy as np
import pytest

import hrma.cfd.wall_output as wo
from hrma.fea.bridge import (PROFIL_KAYNAK_BEYAN_ANAHTARI,
                             extract_thermal_inputs)


# ===========================================================================
# Ortak fikstür — köprünün istediği EN AZ motor + CFD anahtar kümesiyle profil
# ===========================================================================

def _kontur():
    z = np.linspace(0.0, 0.30, 121)
    # Kosinüs geçişli yakınsak-ıraksak duvar (tests/cfd/conftest ile aynı aile;
    # oradan ithal EDİLMEZ — bu dosya tests/cfd paketine bağlı değildir).
    r = np.where(z < 0.12,
                 0.025 + 0.015 * (0.5 + 0.5 * np.cos(
                     np.pi * np.clip(z, 0.0, 0.12) / 0.12)),
                 0.025 + 0.015 * (0.5 - 0.5 * np.cos(
                     np.pi * np.clip(z - 0.12, 0.0, 0.18) / 0.18)))
    return z, r


@pytest.fixture(scope='module')
def motor():
    z, r = _kontur()
    return {
        'nozzle_contour': {
            'points': [[float(a), float(b)] for a, b in zip(z, r)],
            '_basis': 'analitik (D20 bekçi fikstürü)'},
        'structural_analysis': {
            'chamber_analysis': {'wall_thickness_used_mm': 3.0,
                                 'design_mode': 'verification_case'},
            'design_parameters': {'material': 'steel_4130'},
            'material_properties': {'yield_strength': 460e6}},
        'chamber_pressure': 40.0,
        'burn_time': 5.0,
    }


def _cfd_profili(y_plus=1.0):
    """``thermal_axial_profile``ın ANAHTAR KÜMESİYLE bir CFD profili."""
    zc = np.linspace(0.0, 0.30, 60)
    h = 900.0 + 2400.0 * np.exp(-zc / 0.02)
    return {
        'x_mm': (zc * 1000.0).tolist(),
        'h_g': h.tolist(),
        'T_recovery': (2600.0 * np.ones_like(zc)).tolist(),
        'q_w_W_m2': (h * 700.0).tolist(),
        'T_wall_K': (1900.0 * np.ones_like(zc)).tolist(),
        'n_stations': int(zc.size),
        'source': wo.THERMAL_PROFILE_SOURCE,
        't_aw_basis': wo.T_AW_BASIS_RECOVERY,
        'recovery_factor': 0.89,
        'recovery_regime': 'turbulent',
        'prandtl': 0.7,
        'solution_basis': {'converged': True,
                           'y_plus_achieved_max': y_plus},
        'wall_resolution': wo.wall_resolution_declaration(
            {'y_plus_achieved_max': y_plus}),
        '_basis': ('D20 bekçi fikstürü — BARTZ İLE DEĞİŞTİRME YASAĞI: bu '
                   "profil source='cfd_viscous' imiyle gelir ve biri "
                   'diğerinin yerine sessizce konmaz.'),
    }


def _metinleri_topla(nesne):
    """Paketteki TÜM dizgeleri (yol, metin) ikilisi olarak dolaşır."""
    yigin = [('', nesne)]
    while yigin:
        yol, x = yigin.pop()
        if isinstance(x, dict):
            for k, v in x.items():
                yigin.append((f'{yol}.{k}', v))
        elif isinstance(x, (list, tuple)):
            for i, v in enumerate(x[:200]):
                yigin.append((f'{yol}[{i}]', v))
        elif isinstance(x, str):
            yield yol, x


class TestP6B202ProfilBeyaniTuketiciyeUlasiyor:
    """CFD profilinin KENDİ beyanı köprü paketinde DURUR (ezilmez)."""

    def test_profilin_kendi_basisi_ADIYLA_tasiniyor(self, motor):
        p = _cfd_profili()
        ins = extract_thermal_inputs(motor, axial_profile=p)
        assert ins['status'] == 'ok', ins.get('reason')
        kunye = ins['_basis']['h_profili']['profil_kunyesi']
        assert PROFIL_KAYNAK_BEYAN_ANAHTARI in kunye, (
            'profilin kendi _basis metni künyede AD ile durmalı; ad '
            'çakışması sessiz düşmeye yol açıyordu (P6B2-02)')
        assert kunye[PROFIL_KAYNAK_BEYAN_ANAHTARI] == p['_basis'], (
            'taşınan metin profilin KENDİ metni olmalı, özeti değil')

    def test_sessizce_degistirme_YASAGI_pakette_gorunuyor(self, motor):
        """Ölçülen kusur: 'sessiz' izi 0 idi. Şimdi en az 1 olmalı."""
        ins = extract_thermal_inputs(motor, axial_profile=_cfd_profili())
        sessiz = [yol for yol, m in _metinleri_topla(ins)
                  if 'sessizce' in m.lower()]
        assert sessiz, (
            'CFD yolunun "biri diğerinin yerine sessizce konmaz" beyanı '
            'köprü paketinde HİÇ görünmüyor — tüketici sözleşmeyi '
            'okuyamaz (P6B2-02)')

    def test_kopru_kendi_beyani_AD_CAKISMASINI_soyluyor(self, motor):
        """Köprünün "her anahtar buradadır" cümlesi DOĞRU olmalı."""
        ins = extract_thermal_inputs(motor, axial_profile=_cfd_profili())
        kunye = ins['_basis']['h_profili']['profil_kunyesi']
        assert PROFIL_KAYNAK_BEYAN_ANAHTARI in kunye['_basis'], (
            'köprünün kendi beyanı, çakışan adı NEREYE taşıdığını '
            'söylemeli; söylemezse "her anahtar buradadır" cümlesi '
            'okuyucuyu yanıltır')

    def test_profil_anahtarlarindan_HICBIRI_dusmuyor(self, motor):
        """Dizi olmayan her profil anahtarı künyede bulunmalı."""
        p = _cfd_profili()
        ins = extract_thermal_inputs(motor, axial_profile=p)
        kunye = ins['_basis']['h_profili']['profil_kunyesi']
        beklenen = {(PROFIL_KAYNAK_BEYAN_ANAHTARI if k == '_basis' else k)
                    for k, v in p.items()
                    if k not in ('x_mm', 'h_g', 'T_recovery')
                    and not isinstance(v, (list, tuple))}
        assert beklenen <= set(kunye), (
            f'künyeden düşen anahtar(lar): {sorted(beklenen - set(kunye))}')


# ===========================================================================
# OH-D16-04 [F5] — duvar-çözümlü ızgara ÜRÜN SEÇENEĞİ
# ===========================================================================

class TestOHD1604DuvarCozumluUrunSecenegi:
    """/api/cfd/nozzle duvar-çözümlü ızgarayı KURABİLİYOR
    (yalnız beyan değil)."""

    @staticmethod
    def _yuk(**viskoz):
        z, r = _kontur()
        v = {'enabled': True, 'wall_thermal': 'isothermal',
             'T_wall_K': 1920.0, 'T_wall_source': 'bekçi fikstürü',
             'turbulence': 'none'}
        v.update(viskoz)
        return {
            'nozzle_contour': {
                'points': [[float(a), float(b)] for a, b in zip(z, r)]},
            'P0_Pa': 4.0e6, 'T0_K': 3200.0,
            'gamma': 1.2, 'R_J_per_kgK': 350.0,
            'P_ambient_Pa': 101325.0,
            'resolution': 'coarse',
            'viscous': v,
        }

    @pytest.fixture
    def istemci(self):
        from hrma.app import app
        app.config['TESTING'] = True
        return app.test_client()

    def test_cozucu_return_grid_ile_IZGARAYI_da_veriyor(self):
        """Sözleşme: çağıran çözümün KENDİ ızgarasını nesne olarak alır."""
        import inspect

        from hrma.cfd.steady import solve_with_y_plus_target
        imza = inspect.signature(solve_with_y_plus_target)
        assert 'return_grid' in imza.parameters, (
            'uç, duvar büyüklüklerini çözümün ızgarasıyla işlemek zorunda; '
            'kalınlığı beyandan okuyup ızgarayı yeniden kurmak sessiz '
            'kaymaya açıktır (OH-D16-04)')
        assert imza.parameters['return_grid'].default is False, (
            'varsayılan bugünkü imzayı korumalı'
        )

    def test_buyume_tavani_asilinca_KOSU_HARCANMADAN_reddedilir(
            self, istemci):
        """FAIL-CLOSED kapı: nj yetmiyorsa ıraksak alan yayımlanmaz.

        ÖLÇÜLDÜ (docs/scofield/raw/OH/D20/fea-cfd/a1/
        olcum_ohd16_04_tavan.json): y⁺ = 1 hedefi Δy₁ ≈ 7,56e-07 m ister;
        coarse (nj = 12) bunu q = 2,456 büyümeyle karşılamak zorunda ve
        onarımdan ÖNCE bu koşu 0,06 s'de ıraksayıp converged=False,
        y⁺ 'unmeasured' ile 200 dönüyordu (olcum_ohd16_04.json).
        """
        from hrma.cfd.grid_axisym import WALL_RESOLVED_GROWTH_RATIO_MAX

        r = istemci.post('/api/cfd/nozzle',
                         json=self._yuk(wall_resolved=True))
        assert r.status_code == 400, r.get_json()
        j = r.get_json()
        assert j['field'] == 'viscous.wall_resolved', j
        ol = j['measured']
        assert ol['growth_ratio_max'] > WALL_RESOLVED_GROWTH_RATIO_MAX
        assert ol['radial_layers_available'] == 12
        assert ol['radial_layers_required'] >= 49, (
            'gereken katman sayısı ÖLÇÜLEN sayıdır (48,25 → 49); '
            f"gelen {ol['radial_layers_required']}")
        assert ol['first_cell_target_m'] > 0.0
        # Sayı UYDURULMAZ: ön tahminin kendi künyesi de yanında durur.
        assert ol['pre_estimate']['y_plus_target'] == ol['y_plus_target']

    def test_wall_resolved_ISTENINCE_dongu_surucusu_cagriliyor(
            self, istemci, monkeypatch):
        """Kapı geçildiğinde uç y⁺ DÖNGÜSÜNÜ sürer — düz koşuyu değil.

        Çözücü koşumu dakika sınıfı olduğundan burada KOŞULMAZ: iki
        sürücü de sahte bir işaretle değiştirilir ve hangisinin çağrıldığı
        ölçülür. Büyüme tavanı bu testte BİLEREK gevşetilir (bu depodaki
        seviyelerin hiçbiri tavanı geçemiyor — kapının kendisi yukarıdaki
        bekçinin konusudur); ölçülen ÜRÜN davranışı
        docs/scofield/raw/OH/D20/fea-cfd/a1/olcum_ohd16_04.json'dadır.
        """
        import hrma.cfd.grid_axisym as ga
        import hrma.cfd.steady as steady
        cagrilar = []

        def sahte_dongu(*a, **kw):
            cagrilar.append(('dongu', kw.get('return_grid')))
            raise RuntimeError('BEKÇİ-DURDURUCU')

        def sahte_duz(*a, **kw):
            cagrilar.append(('duz', None))
            raise RuntimeError('BEKÇİ-DURDURUCU')

        monkeypatch.setattr(ga, 'WALL_RESOLVED_GROWTH_RATIO_MAX', 1.0e9)
        monkeypatch.setattr(steady, 'solve_with_y_plus_target', sahte_dongu)
        monkeypatch.setattr(steady, 'solve_steady_axisym', sahte_duz)

        r = istemci.post('/api/cfd/nozzle',
                         json=self._yuk(wall_resolved=True))
        assert r.status_code == 500, r.get_json()
        assert cagrilar == [('dongu', True)], (
            f'wall_resolved=true iken y⁺ döngüsü sürülmeli; çağrılan: '
            f'{cagrilar}')

    def test_wall_resolved_YOKKEN_bugunku_duz_kosu(self, istemci, monkeypatch):
        """Seçenek OPT-IN: istenmezse bugünkü yol BİT-AYNI kalır."""
        import hrma.cfd.steady as steady
        cagrilar = []

        def sahte_dongu(*a, **kw):
            cagrilar.append('dongu')
            raise RuntimeError('BEKÇİ-DURDURUCU')

        def sahte_duz(*a, **kw):
            cagrilar.append('duz')
            raise RuntimeError('BEKÇİ-DURDURUCU')

        monkeypatch.setattr(steady, 'solve_with_y_plus_target', sahte_dongu)
        monkeypatch.setattr(steady, 'solve_steady_axisym', sahte_duz)

        r = istemci.post('/api/cfd/nozzle', json=self._yuk())
        assert r.status_code == 500, r.get_json()
        assert cagrilar == ['duz']

    def test_adyabatik_duvarda_wall_resolved_ADIYLA_reddedilir(self, istemci):
        """FAIL-CLOSED: ön tahmin T_w ister; sessizce bir duvar sıcaklığı
        varsayılmaz."""
        yuk = self._yuk(wall_resolved=True)
        yuk['viscous']['wall_thermal'] = 'adiabatic'
        yuk['viscous'].pop('T_wall_K')
        yuk['viscous'].pop('T_wall_source')
        r = istemci.post('/api/cfd/nozzle', json=yuk)
        assert r.status_code == 400, r.get_json()
        j = r.get_json()
        assert j['field'] == 'viscous.wall_thermal', j
        assert 'wall_resolved' in j['message']

    def test_cozunmemis_hedef_wall_resolved_ile_BIRLIKTE_reddedilir(
            self, istemci):
        """y⁺ hedefi çözümlü bandın dışındaysa 'duvar-çözümlü' bir yalandır."""
        from hrma.app import CFD_Y_PLUS_WALL_RESOLVED

        yuk = self._yuk(wall_resolved=True,
                        y_plus_target=CFD_Y_PLUS_WALL_RESOLVED * 5.0)
        r = istemci.post('/api/cfd/nozzle', json=yuk)
        assert r.status_code == 400, r.get_json()
        assert r.get_json()['field'] == 'viscous.y_plus_target'

    def test_wall_resolved_bool_olmayan_deger_reddedilir(self, istemci):
        r = istemci.post('/api/cfd/nozzle',
                         json=self._yuk(wall_resolved='yes'))
        assert r.status_code == 400, r.get_json()
        assert r.get_json()['field'] == 'viscous.wall_resolved'
