# -*- coding: utf-8 -*-
"""ÖH D21 / fea-cfd aşama-1 bekçileri.

Her bekçi ters-mutasyonla kırmızı görülmüştür; kanıt
``docs/scofield/raw/OH/D21/fea-cfd/a1/mutasyon.json``.

Kapsanan kalemler:
  OH-D17-24  create_showerhead_with_tooltips: ``n_holes`` bildirilmediğinde
             20 delik uyduruluyordu (ölçüldü: 20 iz + 31 anotasyon).
  P13B2-04   create_pintle_cross_section: imkânsız gövde/pintle/gap üçlüsü
             sessizce onarılıp çiziliyordu (ölçüldü: 4 iz, 19 anotasyon,
             0 uyarı; etikette D_outer 30,0 mm, çizilen 57,5 mm).
  OH-D17-02  3B başarım yüzeyinde tasarım-noktası kapısı ızgara örneğinin
             maksimumuna kuruluydu; aralığın içinde 1,63 s daha yükseğini
             çözen bir tavan varken yüzeyin ALTINDAKİ nokta reddediliyordu.
"""

import json

import pytest

from hrma.visualization.visualization import (
    PERF_SURFACE_OF_RANGE,
    PERF_SURFACE_PC_RANGE_BAR,
    _isp_surface_ceiling_cached,
    _isp_surface_solve_cached,
    _resolve_surface_propellant,
    create_chamber_pressure_mixture_ratio_3d_surface,
    create_pintle_cross_section,
    create_showerhead_with_tooltips,
)


def _fig(ham):
    return json.loads(ham) if isinstance(ham, str) else ham


def _delik_izleri(fig):
    return [t for t in fig.get('data', [])
            if str(t.get('name') or '').startswith('Hole ')]


def _anotasyon_metni(fig):
    return ' '.join(
        str(a.get('text') or '')
        for a in (fig.get('layout', {}).get('annotations', []) or []))


# ===================================================================
# OH-D17-24 — delik sayısı uydurulmaz
# ===================================================================
class TestOHD1724DelikSayisiUydurulmaz:

    @pytest.mark.parametrize('veri', [
        {'hole_diameter': 1.5, 'plate_thickness': 3.0},   # anahtar hiç yok
        {'n_holes': None, 'hole_diameter': 1.5},          # açıkça None
        {'n_holes': '', 'hole_diameter': 1.5},            # boş metin
        {'n_holes': 0, 'hole_diameter': 1.5},             # sıfır
    ])
    def test_sayi_yoksa_delik_cizilmez(self, veri):
        fig = _fig(create_showerhead_with_tooltips(veri))
        assert _delik_izleri(fig) == [], (
            'delik sayısı bildirilmediği hâlde yüz yerleşimi çizildi — '
            'çizilen her işaret "burada delik var" iddiasıdır')

    def test_sayi_yoksa_kunye_sayi_iddia_etmez(self):
        fig = _fig(create_showerhead_with_tooltips({'hole_diameter': 1.5}))
        metin = _anotasyon_metni(fig)
        assert 'Hole count: not reported' in metin, (
            'eksik delik sayısı künyede ADIYLA söylenmeli')
        assert 'Total Area' not in metin, (
            'toplam orifis alanı delik sayısına bağlıdır; sayı yokken '
            'yayımlanamaz')
        assert '20 Holes' not in metin

    def test_sayi_yoksa_delik_basi_debi_yayimlanmaz(self):
        ham = create_showerhead_with_tooltips(
            {'hole_diameter': 1.5, 'mdot_ox': 1.0})
        assert ' g/s' not in ham, (
            'delik başı debi = toplam debi / delik sayısı; sayı yokken '
            'bölümün paydası uydurulmuş olur')
        # Toplam debi çözücünün kendi sayısıdır, yayımlanmaya devam eder
        assert 'kg/s' in ham

    @pytest.mark.parametrize('n', [1, 7, 20, 37])
    def test_sayi_varsa_aynen_cizilir(self, n):
        fig = _fig(create_showerhead_with_tooltips(
            {'n_holes': n, 'hole_diameter': 1.5}))
        assert len(_delik_izleri(fig)) == n
        assert 'Hole count: not reported' not in _anotasyon_metni(fig)


# ===================================================================
# P13B2-04 — imkânsız enjektör geometrisi çizilmez
# ===================================================================
class TestP13B204ImkansizPintleGeometrisi:

    @pytest.mark.parametrize('d_out,d_pin,gap', [
        (30.0, 40.0, 5.0),    # rapordaki üçlü: gövde anülüsten küçük
        (50.0, 40.0, 5.0),    # sınır: gövde et kalınlığı tam sıfır
        (49.9, 40.0, 5.0),
    ])
    def test_tutarsiz_uclu_reddedilir(self, d_out, d_pin, gap):
        with pytest.raises(ValueError) as ex:
            create_pintle_cross_section({'outer_diameter': d_out,
                                         'pintle_diameter': d_pin,
                                         'gap': gap})
        m = str(ex.value)
        # Ret gerekçesi ÜÇ SAYIYI da söylemeli (beyansız ret kabul edilmez)
        assert f'{d_out:.3f}' in m
        assert f'{d_pin:.3f}' in m
        assert f'{gap:.3f}' in m

    def test_saglikli_uclu_cizilmeye_devam_eder(self):
        fig = _fig(create_pintle_cross_section(
            {'outer_diameter': 60.0, 'pintle_diameter': 40.0, 'gap': 5.0}))
        govde = [t for t in fig['data']
                 if str(t.get('name') or '') == 'Injector Body']
        assert govde, 'sağlıklı geometri çizilmeli'
        ys = [abs(v) for v in (govde[0].get('y') or []) if v is not None]
        # Çizilen dış yarıçap kullanıcının verdiği çapla AYNI olmalı
        assert abs(max(ys) - 30.0) < 1e-9

    @pytest.mark.parametrize('veri', [
        {},                                   # hiçbir sayı yok
        {'pintle_diameter': 40.0},            # yalnız biri
        {'gap': 5.0},
        {'outer_diameter': 30.0, 'gap': 5.0},  # üçü birden değil
    ])
    def test_sematik_yol_dokunulmadan_kalir(self, veri):
        """Üç sayının üçü birden gelmediyse ret KAPISI ÇALIŞMAZ: orada
        sayılar zaten yalnız çizim ölçeğidir ve 'schematic' diye beyan
        edilir (P8B4-18 sözleşmesi)."""
        fig = _fig(create_pintle_cross_section(veri))
        assert len(fig.get('data', [])) >= 4


# ===================================================================
# OH-D17-02 — tavan ızgara örneğinin maksimumu değildir
# ===================================================================
class TestOHD1702TaramaTavani:

    @staticmethod
    def _anahtar():
        fuel, ox, _ = _resolve_surface_propellant(
            {'fuel_type': 'htpb', 'oxidizer_type': 'lox'})
        pc_lo, pc_hi = PERF_SURFACE_PC_RANGE_BAR
        of_lo, of_hi = PERF_SURFACE_OF_RANGE
        return (frozenset(dict(fuel).items()), ox, float(pc_lo),
                float(pc_hi), float(of_lo), float(of_hi), 7)

    def test_tavan_izgara_maksimumunun_ustunde(self):
        import numpy as np
        k = self._anahtar()
        ISP, _f, _e = _isp_surface_solve_cached(*k)
        izgara = float(np.nanmax(ISP))
        tavan, pc, of, ek, incelendi = _isp_surface_ceiling_cached(*k)
        # ÖLÇÜLDÜ (taban 35aa279): ızgara 308,3834 s ⟷ tavan 310,0149 s
        assert incelendi is True
        assert tavan > izgara, (tavan, izgara)
        assert tavan - izgara > 1.0, (
            f'ölçülen fark 1,63 s idi; şimdi {tavan - izgara:.4f} s')
        assert ek > 0, 'inceltme gerçekten çözücü çağırmalı'
        # Dönen nokta aralığın İÇİNDE ve gerçekten çözülmüş olmalı
        assert k[2] <= pc <= k[3]
        assert k[4] <= of <= k[5]

    def test_tavan_asla_izgaranin_altina_dusmez(self):
        import numpy as np
        k = self._anahtar()
        ISP, _f, _e = _isp_surface_solve_cached(*k)
        tavan, _pc, _of, _ek, _r = _isp_surface_ceiling_cached(*k)
        assert tavan >= float(np.nanmax(ISP))

    def test_tavanin_altindaki_tasarim_noktasi_cizilir(self):
        """Izgara maksimumu ile gerçek tavan ARASINDAKİ nokta yüzeyin
        ALTINDADIR; eski kapı onu 'yüzeyin üstünde' diye reddediyordu."""
        import numpy as np
        k = self._anahtar()
        ISP, _f, _e = _isp_surface_solve_cached(*k)
        izgara = float(np.nanmax(ISP))
        tavan, _pc, _of, _ek, _r = _isp_surface_ceiling_cached(*k)
        ara_isp = (izgara + tavan) / 2.0
        fig = _fig(create_chamber_pressure_mixture_ratio_3d_surface({
            'fuel_type': 'htpb', 'oxidizer_type': 'lox', 'grid_n': 7,
            'base_isp': ara_isp, 'optimal_of_ratio': 2.4,
            'optimal_chamber_pressure': 100.0}))
        adlar = [str(t.get('name') or '') for t in fig.get('data', [])]
        assert any('Design point' in a for a in adlar), (
            f'Isp {ara_isp:.4f} s ızgara maksimumunun ({izgara:.4f}) '
            f'üstünde ama gerçek tavanın ({tavan:.4f}) ALTINDA — '
            'nokta çizilmeliydi')
        assert 'is above the highest Isp' not in _anotasyon_metni(fig)

    def test_tavanin_gercekten_ustundeki_nokta_hala_reddedilir(self):
        """Kapı gevşetilmedi: tavanın üstündeki nokta hâlâ çizilmez."""
        k = self._anahtar()
        tavan, _pc, _of, _ek, _r = _isp_surface_ceiling_cached(*k)
        fig = _fig(create_chamber_pressure_mixture_ratio_3d_surface({
            'fuel_type': 'htpb', 'oxidizer_type': 'lox', 'grid_n': 7,
            'base_isp': tavan + 25.0, 'optimal_of_ratio': 2.4,
            'optimal_chamber_pressure': 100.0}))
        adlar = [str(t.get('name') or '') for t in fig.get('data', [])]
        assert not any('Design point' in a for a in adlar)
        assert 'is above the highest Isp' in _anotasyon_metni(fig)
