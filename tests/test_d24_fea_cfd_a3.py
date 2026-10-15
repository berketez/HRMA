"""ÖH Dalga-24 · kulvar fea-cfd · aşama 3 — bekçiler.

Kalemler: P6B3-06, P6B3-07, P6B3-10, P6B3-11, P6B3-12, P6B3-14, P6B3-15,
P17B1-17, OH-D19-15 (çürütüldü → gerileme bekçisi), OH-D19-28 (asıl
fikstür tests/test_d15_fea_viz_a3.py'de; buradan işaret edilir).

Her bekçi ters-mutasyonla kırmızı görüldü:
docs/scofield/raw/OH/D24/fea-cfd/a3/mutasyon.json
"""
import json
import re
from pathlib import Path

import numpy as np
import pytest

from hrma.cfd import separation as S
from hrma.cfd.grid_axisym import (DEFAULT_RADIAL_STRETCH,
                                  RADIAL_UNIFORM_REL_TOL, WallCollar,
                                  build_grid_from_wall, build_nozzle_grid,
                                  collar_weights, radial_geometry_block,
                                  radial_nodes, wall_node_normals)

KOK = Path(__file__).resolve().parents[1]
GRID_PY = KOK / 'hrma' / 'cfd' / 'grid_axisym.py'
SEP_PY = KOK / 'hrma' / 'cfd' / 'separation.py'


def _gercek_duvar(ni):
    """Duvar dizileri [m] — ürünün kendi kontur örnekleyicisinden."""
    from hrma.engines.nozzle_design import sample_nozzle_inner_contour
    pts = np.asarray(sample_nozzle_inner_contour({})[0], dtype=float)
    z_mm = np.linspace(pts[0, 0], pts[-1, 0], ni + 1)
    return z_mm * 1e-3, np.interp(z_mm, pts[:, 0], pts[:, 1]) * 1e-3


# =====================================================================
# P6B3-06 — docstring GERÇEK varsayılanı söyler (sabitle bağlı)
# =====================================================================
class TestP6B306DocstringVarsayilani:

    def test_build_grid_from_wall_docstringi_SABITIN_degerini_yaziyor(self):
        ds = build_grid_from_wall.__doc__
        assert f"= '{DEFAULT_RADIAL_STRETCH}'" in ds, (
            'docstring gerdirme varsayılanını sabitin GERÇEK değeriyle '
            f'yazmıyor (sabit {DEFAULT_RADIAL_STRETCH!r}); künye ile kod '
            'ayrışmış demektir')

    def test_docstring_BASKA_bir_aileyi_varsayilan_ILAN_ETMIYOR(self):
        """Asıl kusur buydu: sabit 'tanh' iken künye 'geometric' diyordu."""
        ds = build_grid_from_wall.__doc__
        for aile in ('geometric', 'tanh', 'uniform'):
            if aile == DEFAULT_RADIAL_STRETCH:
                continue
            assert f"('{aile}' varsayılan" not in ds, (
                f'{aile!r} varsayılan ilan edilmiş ama sabit '
                f'{DEFAULT_RADIAL_STRETCH!r}')

    def test_radial_nodes_docstringi_de_ayni_sabiti_gosteriyor(self):
        assert f"= '{DEFAULT_RADIAL_STRETCH}'" in radial_nodes.__doc__


# =====================================================================
# P6B3-10 — skaler r_wall BEYAN EDİLEN istisnayı fırlatır
# =====================================================================
class TestP6B310SkalerDuvarYaricapi:

    @pytest.mark.parametrize('r_w', [0.05, np.float64(0.05),
                                     np.array(0.05)])
    def test_skaler_r_wall_ValueError_verir_IndexError_DEGIL(self, r_w):
        with pytest.raises(ValueError) as e:
            radial_nodes(8, r_w, first_cell_m=0.02)
        assert 'sessiz düzgüne düşme YOK' in str(e.value), (
            'beyan edilen gerekçe çağırana ULAŞMIYOR — mesaj kurulurken '
            '0 boyutlu diziyi indislemek IndexError fırlatıyordu')

    def test_skaler_ve_1B_ayni_gerekceyi_verir(self):
        with pytest.raises(ValueError) as e_s:
            radial_nodes(8, 0.05, first_cell_m=0.02)
        with pytest.raises(ValueError) as e_v:
            radial_nodes(8, np.array([0.05]), first_cell_m=0.02)
        assert str(e_s.value) == str(e_v.value)

    def test_saglikli_skaler_koşum_calisiyor(self):
        """Kapı sağlıklı skaler girdiyi ENGELLEMEZ (ÖK-22)."""
        R, beyan = radial_nodes(8, 0.05, first_cell_m=1e-4)
        assert R.shape == (9,)
        assert R[0] == 0.0 and R[-1] == pytest.approx(0.05)
        assert beyan['family'] == DEFAULT_RADIAL_STRETCH


# =====================================================================
# P6B3-11 — kesirli SAYI sessizce kırpılmaz
# =====================================================================
class TestP6B311SessizKirpmaYok:

    @staticmethod
    def _duvar(ni=32):
        z = np.linspace(0.0, 0.30, ni + 1)
        return z, 0.05 - 0.035 * np.exp(-((z - 0.10) / 0.035) ** 2)

    def test_radial_nodes_nj_kesirli_reddedilir(self):
        z, r = self._duvar()
        with pytest.raises(ValueError, match='TAM SAYI'):
            radial_nodes(2.7, r)

    def test_build_grid_from_wall_nj_kesirli_reddedilir(self):
        z, r = self._duvar()
        with pytest.raises(ValueError, match='TAM SAYI'):
            build_grid_from_wall(z, r, 2.7)

    def test_build_nozzle_grid_ni_kesirli_reddedilir(self):
        z, r = self._duvar(40)
        kontur = [(float(a * 1e3), float(b * 1e3)) for a, b in zip(z, r)]
        with pytest.raises(ValueError, match='TAM SAYI'):
            build_nozzle_grid(kontur, 8.9, 6)

    def test_collar_weights_kesirli_reddedilir(self):
        with pytest.raises(ValueError, match='TAM SAYI'):
            collar_weights(6.8, 2, 2)
        with pytest.raises(ValueError, match='TAM SAYI'):
            collar_weights(8, 2.5, 2)
        with pytest.raises(ValueError, match='TAM SAYI'):
            collar_weights(8, 2, 2.5)

    def test_axial_indices_kesirli_reddedilir(self):
        z, r = self._duvar()
        g = build_grid_from_wall(z, r, 6)
        with pytest.raises(ValueError, match='TAM SAYI'):
            radial_geometry_block(g, axial_indices=[0.0, 1.9])

    def test_kirpma_hangi_izgaraya_dustugunu_MESAJDA_soyler(self):
        z, r = self._duvar()
        with pytest.raises(ValueError) as e:
            build_grid_from_wall(z, r, 2.7)
        assert 'nj = 2' in str(e.value), str(e.value)
        assert 'BAŞKA' in str(e.value)

    def test_TAM_SAYI_degerli_float_KABUL_EDILIR(self):
        """Kapı sağlıklı envanteri daraltmaz (ÖK-22): 6.0 tam sayıdır."""
        z, r = self._duvar()
        g = build_grid_from_wall(z, r, 6.0)
        assert g.nj == 6
        blok = radial_geometry_block(g, axial_indices=[0.0, 1.0])
        assert blok['shape'][0] == 2

    def test_bool_nj_reddedilir(self):
        z, r = self._duvar()
        with pytest.raises(ValueError, match='doğruluk değeri'):
            build_grid_from_wall(z, r, True)


# =====================================================================
# P6B3-14 — açıortay kısalması ÖLÇÜLÜP yayımlanıyor
# =====================================================================
class TestP6B314AciortayKisalmasi:

    @staticmethod
    def _bagimsiz_policizgi_eksikligi(z, r, d1):
        """Bekçinin KENDİ ölçümü (ürün kodunu çağırmaz)."""
        n_node, _ = wall_node_normals(z, r)
        P = np.stack([z, r], axis=-1) + d1 * n_node
        A = np.stack([z[:-1], r[:-1]], axis=-1)
        AB = np.stack([np.diff(z), np.diff(r)], axis=-1)
        L2 = np.einsum('ij,ij->i', AB, AB)
        en_kisa = np.empty(P.shape[0])
        for i in range(P.shape[0]):
            t = np.clip(np.einsum('ij,ij->i', P[i] - A, AB) / L2, 0.0, 1.0)
            f = (P[i] - A) - t[:, None] * AB
            en_kisa[i] = float(np.min(np.hypot(f[:, 0], f[:, 1])))
        return float(np.max((d1 - en_kisa) / d1))

    def test_beyan_policizgi_eksikligini_YAYIMLIYOR(self):
        z, r = _gercek_duvar(192)
        g = build_grid_from_wall(z, r, 48, first_cell_m=1.0e-5,
                                 wall_collar=WallCollar())
        y = g.wall_collar
        for alan in ('first_cell_polyline_m_min', 'first_cell_polyline_m_max',
                     'first_cell_polyline_deficit_rel_max',
                     'wall_turn_angle_max_deg'):
            assert alan in y, f'{alan} yayımlanmıyor'

    def test_yayimlanan_eksiklik_BAGIMSIZ_olcumle_ayni(self):
        """Yayımlanan sayı kopya değil, yeniden hesaplanabilir olmalı."""
        z, r = _gercek_duvar(192)
        g = build_grid_from_wall(z, r, 48, first_cell_m=1.0e-5,
                                 wall_collar=WallCollar())
        elde = g.wall_collar['first_cell_polyline_deficit_rel_max']
        assert elde == pytest.approx(
            self._bagimsiz_policizgi_eksikligi(z, r, 1.0e-5), rel=1e-6)

    def test_eksiklik_NORMAL_IZDUSUMUNDEN_cok_daha_buyuk(self):
        """Kalemin ta kendisi: normal izdüşümü kısalmayı GÖREMEZ.

        Ölçüldü (gerçek kontur 192×48, d1 = 10 µm): izdüşüm eksikliği
        8,00e-13 (kayan nokta gürültüsü), poliçizgi eksikliği 9,52e-04
        — 119 kat. Eski künye 8e-6 yazıp "beyanda yayımlanıyor" diyordu.
        """
        z, r = _gercek_duvar(192)
        d1 = 1.0e-5
        g = build_grid_from_wall(z, r, 48, first_cell_m=d1,
                                 wall_collar=WallCollar())
        y = g.wall_collar
        izdusum_eksik = (d1 - y['first_cell_normal_m_min']) / d1
        policizgi_eksik = y['first_cell_polyline_deficit_rel_max']
        assert izdusum_eksik < 1e-9, izdusum_eksik
        assert policizgi_eksik > 1e-4, policizgi_eksik
        assert policizgi_eksik / max(izdusum_eksik, 1e-300) > 1e6

    def test_donus_acisi_KUNYEDEKI_0_46_dereceden_cok_buyuk(self):
        z, r = _gercek_duvar(192)
        g = build_grid_from_wall(z, r, 48, first_cell_m=1.0e-5,
                                 wall_collar=WallCollar())
        assert g.wall_collar['wall_turn_angle_max_deg'] == pytest.approx(
            10.4936, abs=1e-3)

    def test_kunye_ARTIK_yanlis_iddiada_bulunmuyor(self):
        ds = wall_node_normals.__doc__
        assert "Δα = 0,46°'de bağıl 8e-6 — ölçüldü ve beyanda" not in ds
        assert 'first_cell_polyline_deficit_rel_max' in ds, (
            'künye ölçümün YAYIMLANDIĞI alanı adıyla göstermeli')


# =====================================================================
# P6B3-15 — gürültü künyesi IZGARA ADIYLA ve BANTLA
# =====================================================================
class TestP6B315GurultuKunyesi:

    def _kunye(self):
        m = GRID_PY.read_text(encoding='utf-8')
        return m.split('RADIAL_UNIFORM_REL_TOL = ')[0][-2200:]

    def test_kunye_IZGARA_ADI_yaziyor(self):
        k = self._kunye()
        for ad in ('60×12', '512×256'):
            assert ad in k, f'{ad} ızgarası künyede adıyla yok'

    def test_kunye_EN_KOTU_payi_da_yaziyor(self):
        """Tek ızgaranın payı (2,7e6) tek başına künye olamaz."""
        k = self._kunye()
        assert '1,22e5' in k, (
            'en kötü ölçülen pay künyede yok — okuyucu payın ızgarayla '
            '22 kat düştüğünü göremez')

    @pytest.mark.parametrize('ni,nj,bekle', [(60, 12, 3.660e-15),
                                             (512, 256, 8.223e-14)])
    def test_kunyedeki_sapmalar_URUNDEN_yeniden_olculebilir(self, ni, nj,
                                                            bekle):
        z, r = _gercek_duvar(ni)
        g = build_grid_from_wall(z, r, nj)
        R_col = 0.5 * (g.R[:-1, :] + g.R[1:, :])
        dr = np.diff(R_col, axis=-1)
        sapma = float(np.max(np.abs(dr - dr[:, :1]) / dr[:, :1]))
        assert sapma == pytest.approx(bekle, rel=5e-3)
        assert RADIAL_UNIFORM_REL_TOL / sapma > 1e5

    def test_esik_iki_rejimi_hala_AYIRIYOR(self):
        z, r = _gercek_duvar(512)
        g = build_grid_from_wall(z, r, 256)
        assert radial_geometry_block(g)['radial_uniform'] is True
        g2 = build_grid_from_wall(z, r, 256, first_cell_m=1.0e-5)
        assert radial_geometry_block(g2)['radial_uniform'] is False


# =====================================================================
# P6B3-07 — hemfikirlik KAZANILMADAN yayımlanmaz
# =====================================================================
class TestP6B307Hemfikirlik:

    @staticmethod
    def _yok_hepsi():
        return {ad: S._empty_member(ad, 'test', 'ölçüm için yok')
                for ad in S.SEPARATION_CRITERIA}

    def test_hicbir_uye_hukum_vermediginde_unanimous_None(self):
        sp = S._criteria_spread(self._yok_hepsi())
        assert sp['members_available_count'] == 0
        assert sp['unanimous'] is None, (
            'hiçbir ölçüt konuşmamışken "ölçütler hemfikir" hükmü '
            'yayımlanıyor')
        assert '2' in sp['unanimous_basis']

    def test_TEK_uye_hukum_verdiginde_de_unanimous_None(self):
        k = self._yok_hepsi()
        k[S.CRITERION_SUMMERFIELD] = S._empty_member(
            S.CRITERION_SUMMERFIELD, 'empirical_wall_pressure')
        sp = S._criteria_spread(k)
        assert sp['members_available_count'] == 1
        assert sp['unanimous'] is None

    def test_IKI_uye_ayni_yonde_ise_unanimous_True(self):
        """Kapı sağlıklı hükmü boğmaz (ÖK-22)."""
        k = self._yok_hepsi()
        for ad in (S.CRITERION_SUMMERFIELD, S.CRITERION_SCHMUCKER):
            k[ad] = S._empty_member(ad, 'empirical_wall_pressure')
        sp = S._criteria_spread(k)
        assert sp['members_available_count'] == 2
        assert sp['unanimous'] is True

    def test_IKI_uye_celisirse_unanimous_False(self):
        k = self._yok_hepsi()
        for ad in (S.CRITERION_SUMMERFIELD, S.CRITERION_SCHMUCKER):
            k[ad] = S._empty_member(ad, 'empirical_wall_pressure')
        k[S.CRITERION_SUMMERFIELD]['separated'] = True
        sp = S._criteria_spread(k)
        assert sp['unanimous'] is False

    def test_unanimous_basis_hukum_veren_uye_SAYISINI_yaziyor(self):
        sp = S._criteria_spread(self._yok_hepsi())
        assert f'0/{len(S.SEPARATION_CRITERIA)}' in sp['unanimous_basis']


# =====================================================================
# P6B3-12 — margin_min TEK büyüklük taşır
# =====================================================================
class TestP6B312MarginTekBuyukluk:

    @staticmethod
    def _yapisik():
        n = 40
        z = np.linspace(0.0, 0.2, n)
        p = np.linspace(2.0e6, 3.0e5, n)
        tau = np.linspace(900.0, 237.0, n)
        return z, p, tau

    def test_semada_margin_kind_ve_basis_var(self):
        bos = S._empty_member('x', 'y')
        assert 'margin_kind' in bos and 'margin_basis' in bos

    def test_esik_uyesinin_margini_p_bolu_esik(self):
        z, p, _ = self._yapisik()
        m = S._threshold_member('summerfield', p, z, 5, 3.3e5, 0.15)
        assert m['margin_kind'] == 'wall_pressure_over_threshold'
        assert m['margin_min'] == pytest.approx(0.90909, rel=1e-4)
        assert m['separated'] is True
        assert '1' in m['margin_basis']

    def test_CFD_uyesinde_margin_min_UYDURULMUYOR(self):
        """Kalemin ta kendisi: yapışık koşuda 0,2636 yayımlanıyordu."""
        z, p, tau = self._yapisik()
        m = S._tau_wall_member({'viscous': {'wall_shear_Pa': tau,
                                            'wall_z_m': z}}, p, z, 5, 0.15)
        assert m['separated'] is False
        assert m['margin_min'] is None, (
            'eşiği SIFIR olan üyede p/eşik margin\'i tanımsızdır; buraya '
            'min(τ)/maks|τ| yazmak aynı anahtarda ikinci bir büyüklük '
            'yayımlamaktır ve "1\'in altı = ayrıldı" diye okunur')
        assert m['margin_basis'] is not None

    def test_CFD_uyesinin_kendi_payi_KENDI_adiyla_yayimlaniyor(self):
        z, p, tau = self._yapisik()
        m = S._tau_wall_member({'viscous': {'wall_shear_Pa': tau,
                                            'wall_z_m': z}}, p, z, 5, 0.15)
        assert m['tau_wall_min_over_max_abs'] == pytest.approx(0.29699,
                                                               rel=1e-4)
        assert m['tau_wall_margin_critical_value'] == 0.0

    def test_YAPISIK_kosuda_1_altindaki_sayi_AYRILDI_diye_okunamaz(self):
        """Yan yana okunabilirlik sınavı: kritik değerler ayrışıyor."""
        z, p, tau = self._yapisik()
        cfd = S._tau_wall_member({'viscous': {'wall_shear_Pa': tau,
                                              'wall_z_m': z}}, p, z, 5, 0.15)
        esik = S._threshold_member('summerfield', p, z, 5, 3.3e5, 0.15)
        # ikisi de "1'in altında" ama biri ayrıldı biri ayrılmadı
        assert cfd['tau_wall_min_over_max_abs'] < 1.0
        assert esik['margin_min'] < 1.0
        assert cfd['separated'] is False and esik['separated'] is True
        # ...ve margin_min ARTIK tek kurala uyuyor: yalnız eşik üyesinde
        # doludur, ve orada < 1 gerçekten ayrılma demektir.
        assert cfd['margin_min'] is None

    def test_ayrik_kosuda_da_margin_min_bos(self):
        n = 40
        z = np.linspace(0.0, 0.2, n)
        p = np.linspace(2.0e6, 3.0e5, n)
        tau = np.linspace(900.0, -300.0, n)
        m = S._tau_wall_member({'viscous': {'wall_shear_Pa': tau,
                                            'wall_z_m': z}}, p, z, 5, 0.15)
        assert m['separated'] is True
        assert m['margin_min'] is None
        assert m['tau_wall_min_over_max_abs'] < 0.0


# =====================================================================
# P17B1-17 — "köşe tekilliği borcu kapandı" YANLIŞ iddiası
# =====================================================================
class TestP17B117BorcKapandi:
    """ÖH D26 fix-25b — BEKÇİ GEREKÇELİ ÇEVRİLDİ (kalem OH-D24-01 / P17B1-17).

    Bu sınıf D24'te "borç KAPANMADI" diye yazılmıştı ve o gün DOĞRUYDU.
    D25 fea-cfd a1 (4732efb, kalem OH-D24-01) borcu gerçekten kapattı:
    yakınsama kapısı artık ASME BPVC VIII-2 Bölüm 5 / Ek 5-A ile
    LİNEERLEŞTİRİLMİŞ ``P_L+P_b`` gerilmesini ölçüyor. Eski kapı bunun
    yanında ham düğüm tepesini (ASME "F") de şart koşuyordu; o büyüklük
    kontur köşelerindeki zayıf tekillik yüzünden h → 0 iken TANIM GEREĞİ
    yakınsamaz (gözlenen mertebe p ≈ 0,12; 16.384 elemanda hâlâ %4,0/tur)
    ve ASME Tablo 5.6 tepeyi plastik çökme hükmünden zaten DIŞLAR.

    KAPI GEVŞETİLMEDİ — ölçtüğü büyüklük düzeltildi. Tolerans D24'ten
    ÖNCE konmuş değeriyle aynı: ``DEFAULT_REFINE_TOL = 0.01`` (%1),
    67ac180'den beri değişmedi (``git log -S`` ile doğrulandı, D25 bu
    satıra dokunmadı). D24'ün kırmızı vakası 2 kN'de bağıl değişimi
    %3,91'den %0,267'ye düşürdü: AYNI tolerans, 14,6 kat daha iyi sayı.

    Bekçi artık borcun AÇIK olduğunu değil KAPALI kaldığını savunur:
    borç yeniden açılırsa (üç vakadan biri yayımlanan kipte yakınsamayı
    kaybederse) kırmızı verir. İddia ZAYIFLAMADI, güçlendi — eskiden tek
    vakanın DÜŞTÜĞÜ ölçülüyordu, şimdi üç vakanın da GEÇTİĞİ.
    """

    #: D24'ün ölçtüğü üç sıvı vakası (thrust N, Pc bar, ε). Kapanış
    #: iddiası bu ÜÇÜ için birden kurulur; D24'te 1'i geçip 2'si düşüyordu.
    VAKALAR = ((25000.0, 70.0, 12.0), (2000.0, 15.0, 5.0),
               (1000.0, 10.0, 4.0))

    def test_test_fea_panel_docstringi_ARTIK_kapandi_DIYOR(self):
        m = (KOK / 'tests' / 'test_fea_panel.py').read_text(encoding='utf-8')
        assert 'KÖŞE TEKİLLİĞİ BORCU KAPANDI' in m, (
            'künye borcun kapandığını söylemeli — canlı ölçüm (bu sınıf) '
            'üç vakanın üçünde de yayımlanan kipin yakınsadığını gösteriyor')
        assert 'KÖŞE TEKİLLİĞİ BORCU KAPANMADI' not in m, (
            'künye hâlâ borcu AÇIK ilan ediyor; ölçüm bunu çürütüyor')
        # Kapanış kazanılmış olmalı: künye kapıyı DEĞİL büyüklüğü
        # düzelttiğimizi söylemeli (tolerans gevşetmesi gizlenemesin).
        assert 'DEFAULT_REFINE_TOL = 0.01' in m, (
            'künye toleransın DEĞİŞMEDİĞİNİ kayda geçirmeli')

    def test_sivi_yapisal_koprusu_UC_VAKADA_DA_YAKINSIYOR(self):
        """Borcun kapalı KALDIĞININ canlı ölçümü (OH-D24-01 / P17B1-17).

        D24'te 25 kN geçiyor, 2 kN ve 1 kN düşüyordu (``converged_
        yayimlanan_kip = False``). Üçü de yayımlanan kipte yakınsamalı;
        biri gerilerse borç yeniden açılmış demektir.
        """
        from hrma.app import app
        from hrma.fea.bridge import run_structural_from_motor
        app.config['TESTING'] = True
        c = app.test_client()
        yakinsayan = []
        for thrust, pc, er in self.VAKALAR:
            sivi = c.post('/calculate_liquid', json={
                'motor_name': 'P17B117', 'thrust': thrust,
                'burn_time': 30.0, 'chamber_pressure': pc,
                'mixture_ratio': 2.2, 'fuel_type': 'rp1',
                'oxidizer_type': 'lox',
                'expansion_ratio': er}).get_json()
            h = run_structural_from_motor(sivi)['meta']['hukum']
            yakinsayan.append(h['converged_yayimlanan_kip'] is True)
            etiket = f'{thrust / 1000.0:g} kN / {pc:g} bar / eps={er:g}'
            assert h['converged_birincil_kip'] is True, (
                f'{etiket}: birincil kip yakınsamadı')
            # ÇEVRİLDİ (OH-D25-28 / OH-D24-01, ÖH D27 a1) — GEREKÇE ÖLÇÜLDÜ.
            # İç kontur köşe tabanı ürün varsayılanı olunca 1 kN vakasında
            # 'converged_yayimlanan_kip' False'a döndü. ÖLÇÜM (docs/scofield/
            # raw/OH/D27/fea-cfd/a1/sivi_merdiven.json) bunun bir GERİLEME
            # DEĞİL, kapalı kipteki "yakınsadı"nın YANILSAMA olduğunu
            # gösteriyor — hüküm büyüklüğünün na = 32→512 merdiveni:
            #   KAPALI: 3,64905 → 3,64603 → 3,63177 → 3,62283 → 3,62313e7 Pa
            #           (32→64 farkı %0,083; "yakınsadı" GÖRÜNÜR ama değer
            #            limitten %0,7 uzakta — sabit köşe iki kaba mesh'te
            #            de bire bir kopyalandığı için sayı YAPAY olarak
            #            duruyor)
            #   AÇIK:   3,01331 → 3,31683 → 3,51959 → 3,59486 → 3,61636e7 Pa
            #           (%10,07 → %6,11 → %2,14 → %0,60 — MONOTON, O(h),
            #            AYNI limite gidiyor)
            # Yani geometri doğru; eksik olan köprünün inceltme SÜRÜCÜSÜNÜN
            # birincil kipe göre durup yayımlanan kipi izlememesidir. Ürün
            # bu vakada FAIL-CLOSED davranıyor: hüküm ADLI gerekçeyle geri
            # çekiliyor, sayı sessizce basılmıyor. Bekçi artık bu BAĞI
            # savunuyor — gevşemedi, yeri değişti: yayımlanan kip
            # yakınsamadıysa hüküm VERİLEMEZ.
            if h['converged_yayimlanan_kip'] is not True:
                assert h['verildi'] is False, (
                    f'{etiket}: yayımlanan kip yakınsamadığı hâlde hüküm '
                    'VERİLDİ — fail-closed bağı kopmuş')
                assert 'yayimlanan_kip_yakinsamadi' in \
                    h['geri_cekme_gerekceleri'], (
                    f'{etiket}: gerekçe ADSIZ')
                assert h['min_safety_factor'] is not None, (
                    f'{etiket}: sayı SİLİNMEZ (P17B1-02 sözleşmesi)')
            else:
                assert h['converged'] is True, (
                    f'{etiket}: köprü hükmü converged=False')
        # ÖH D28 / OH-D27-05 — İDDİA GERİ SIKILAŞTIRILDI: 2 -> 3.
        # D27 bu satırı "en az ikisi" diye GEVŞETMİŞTİ, çünkü 1 kN vakası
        # yayımlanan kipte yakınsamayı kaybediyordu. D28'de KUSUR ONARILDI
        # (inceltme sürücüsü artık yayımlanan kipi de izliyor,
        # ``solve_with_refinement(ek_kip=...)``) ve ölçüm bunu gösteriyor
        # (docs/scofield/raw/OH/D28/fea-cfd/a1/{once,sonra}_d2705.json):
        #   1 kN: yayımlanan kip rel_change %10,07 -> %0,162 (tol %1),
        #         converged_yayimlanan_kip False -> True, mesh 64x4 -> 1024x4
        #   2 kN: %0,167 -> %0,046, mesh 1024x4 -> 2048x4
        #   25 kN: yayımlanan kip = birincil kip (ek kip yok), DEĞİŞMEDİ
        # Tolerans DEĞİŞMEDİ (DEFAULT_REFINE_TOL = 0,01); kapı gevşetilmedi,
        # sürücü doğru sayıyı izlemeye başladı.
        assert all(yakinsayan), (
            f'yayımlanan kipte yakınsayan vaka sayısı {sum(yakinsayan)} < 3 '
            '— OH-D27-05 onarımı gerilemiş olabilir (sürücü yayımlanan kipi '
            'izlemiyor)')


# =====================================================================
# OH-D19-15 — ÇÜRÜTÜLDÜ (tabanda zaten onarılı) → gerileme bekçisi
# =====================================================================
class TestOHD1915TrimeshReprSizmiyor:

    def test_json_safe_cad_design_ag_nesnesini_YANITA_KOYMAZ(self):
        """Ucuz kanıt: sanitize edici repr yerine ÖLÇÜLEN künye koyar."""
        import trimesh

        from hrma.export.cad_visualization import json_safe_cad_design
        m = trimesh.creation.cylinder(radius=0.05, height=0.2)
        cikti = json_safe_cad_design({'assembly_meshes': [('Chamber', m)]})
        assert 'assembly_meshes' not in cikti
        ozet = cikti['assembly_mesh_summary']
        assert ozet[0]['name'] == 'Chamber'
        assert ozet[0]['vertex_count'] == len(m.vertices)
        assert ozet[0]['face_count'] == len(m.faces)
        ham = json.dumps(cikti, default=str)
        assert '<trimesh.' not in ham

    def test_hibrit_calculate_govdesinde_trimesh_repr_YOK(self):
        """ÖLÇÜLDÜ (taban 88a29d3): 0 kez. Kalem bu yüzden çürütüldü."""
        from hrma.app import app
        app.config['TESTING'] = True
        c = app.test_client()
        r = c.post('/calculate', json={
            'motor_name': 'D24A3H', 'thrust': 5000.0, 'burn_time': 10.0,
            'chamber_pressure': 30.0, 'of_ratio': 6.0,
            'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
            'expansion_ratio': 8.0, 'l_star': 1.0})
        assert r.status_code == 200
        assert r.get_data(as_text=True).count('<trimesh.') == 0
        cd = r.get_json()['cad_design']
        assert 'assembly_meshes' not in cd
        assert cd['assembly_mesh_summary'][0]['vertex_count'] > 0


# =====================================================================
# OH-D19-28 — asıl fikstür test_d15_fea_viz_a3.py'de; burada işaret
# =====================================================================
def test_OHD1928_ayrisan_kip_fiksturu_YERINDE():
    m = (KOK / 'tests' / 'test_d15_fea_viz_a3.py').read_text(encoding='utf-8')
    assert 'test_AYRISAN_kipte_yayimlanan_kip_yakinsamasi_GERCEKTEN_olculuyor' \
        in m
    assert re.search(r'"thrust":\s*2000\.0', m), (
        'ayrışan fikstürün çalışma noktası kaybolmuş')
