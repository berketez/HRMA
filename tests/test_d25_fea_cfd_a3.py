# tests/test_d25_fea_cfd_a3.py
"""ÖH D25 · fea-cfd · aşama-3 bekçileri.

Kalemler: P6B4-10, -11, -12, -13, -14, -15 (hrma/stability/**) ve
P8B1-02, -04, -05, -06, -07 (hrma/fea/**).

Her sınıf ters-mutasyonla kırmızıya döndürülmüştür; kanıt
``docs/scofield/raw/OH/D25/fea-cfd/a3/mutasyon.json``.
"""
import math

import numpy as np
import pytest

from hrma.fea import mesh_axisym as MA
from hrma.fea import structural_axisym as SA
from hrma.fea import thermal_axisym as TA
from hrma.stability import chamber as CH
from hrma.stability import chug as CG
from hrma.stability import damping as DM
from hrma.stability import hybrid_lfi as LFI
from hrma.stability import response as RS
from hrma.stability.fuel_thermal import compare_with_propellant_database


# ==========================================================================
# P6B4-10 — katsayı özdeşliği: metin ARTIK ölçülen sayıyı söylüyor
# ==========================================================================
class TestP6B410KatsayiOzdesligi:

    def _rapor(self):
        return LFI.assess_hybrid_lfi(
            'n2o', grain_length_m=0.60, chamber_pressure_Pa=3.0e6,
            oxidizer_flux_kg_m2_s=180.0, of_ratio=6.0)

    def test_ozdeslik_artigi_HESAPLANIYOR_ve_sifir_DEGIL(self):
        """0,2341 ile 0,48/2,050 BİT-AYNI DEĞİL; artık ölçülür."""
        bolum = (LFI.LFI_FREQUENCY_DELAY_COEFFICIENT
                 / LFI.LFI_DELAY_CONSTANT_C_PRIME)
        assert LFI.LFI_COEFFICIENT_FROM_DELAY == bolum
        assert LFI.LFI_COEFFICIENT != bolum, (
            "kalemin çekirdeği: iki sayı EŞİT DEĞİL")
        beklenen = abs(LFI.LFI_COEFFICIENT - bolum) / bolum
        assert LFI.LFI_COEFFICIENT_IDENTITY_RESIDUAL_REL == beklenen
        assert 1.9e-4 < beklenen < 2.0e-4       # ölçüldü: 1,9792e-04

    def test_metin_TAM_ESITLIK_IDDIA_ETMIYOR(self):
        metin = self._rapor()['coefficient_identity']
        assert f'{LFI.LFI_COEFFICIENT} = ' not in metin, (
            "eski metin '0.2341 = 0.48/2.05' diyordu — ölçümle yanlış")
        assert 'NOT bit-identical' in metin
        assert 'as PRINTED' in metin

    def test_artik_ve_tolerans_YAYIMLANIYOR(self):
        r = self._rapor()
        assert r['coefficient_identity_residual_rel'] == \
            LFI.LFI_COEFFICIENT_IDENTITY_RESIDUAL_REL
        assert r['coefficient_identity_tol_rel'] == \
            LFI.LFI_COEFFICIENT_IDENTITY_TOL_REL
        assert r['coefficient_from_delay'] == LFI.LFI_COEFFICIENT_FROM_DELAY
        # basım yuvarlaması artığı KAPSIYOR (yoksa modül yüklenmezdi)
        assert (LFI.LFI_COEFFICIENT_IDENTITY_RESIDUAL_REL
                <= LFI.LFI_COEFFICIENT_IDENTITY_TOL_REL)

    def test_IKI_frekans_yolu_da_yayimlaniyor_ve_farki_ARTIGA_ESIT(self):
        r = self._rapor()
        f15 = r['frequency_hz']
        f7 = r['frequency_via_delay_hz']
        assert f7 == (LFI.LFI_FREQUENCY_DELAY_COEFFICIENT
                      / r['boundary_layer_delay_s'])
        assert f15 != f7, "iki yol ölçümde ayrışıyor"
        # iki yolun bağıl farkı = katsayı artığı (tam özdeşlik)
        # ÖH D28 / OH-Z5-02: ``pytest.approx(rel=1e-12)`` SIKILAŞTIRILDI.
        # Eski tolerans "tam özdeşlik" diyen yorumu YALANLIYORDU: ölçülen
        # sapma 4,2e-13 ile bandın hemen altındaydı, yani ürün aynı
        # büyüklüğü iki FARKLI sayı olarak basarken bekçi sessizdi. Yaprak
        # artık tek kaynaktan geldiği için karşılaştırma BİT-AYNI olabilir.
        assert (r['frequency_paths_rel_diff']
                == LFI.LFI_COEFFICIENT_IDENTITY_RESIDUAL_REL)
        assert r['frequency_paths_rel_diff'] == LFI.LFI_FREQUENCY_PATHS_REL_DIFF

    def test_tolerans_basili_ONDALIKTAN_turetiliyor(self):
        assert LFI.LFI_COEFFICIENT_IDENTITY_TOL_REL == (
            0.5 * 10.0 ** (-LFI.LFI_COEFFICIENT_PRINTED_DECIMALS)
            / LFI.LFI_COEFFICIENT_FROM_DELAY)


# ==========================================================================
# P6B4-11 — damping_budget ad çakışması FAIL-CLOSED
# ==========================================================================
class TestP6B411SonumAdCakismasi:

    def test_ayni_ad_iki_kez_REDDEDILIYOR(self):
        terms = [{'term': 'nozzle', 'damping_1_s': -78.5224},
                 {'term': 'nozzle', 'damping_1_s': -160.2445}]
        with pytest.raises(ValueError) as exc:
            DM.damping_budget(terms)
        m = str(exc.value)
        assert 'nozzle' in m and 'twice' in m
        assert '-78.5224' in m and '-160.2445' in m, (
            "hata iki değeri de adıyla söylemeli")

    def test_bosluk_farkiyla_cakisan_ad_da_REDDEDILIYOR(self):
        with pytest.raises(ValueError):
            DM.damping_budget({'nozzle': -1.0, ' nozzle ': -2.0})

    def test_farkli_adlar_TOPLANMAYA_devam_ediyor(self):
        b = DM.damping_budget([
            {'term': 'nozzle_entrance', 'damping_1_s': -78.5224},
            {'term': 'nozzle_exit', 'damping_1_s': -160.2445}])
        assert len(b['terms']) == 2
        assert b['total_damping_1_s'] == pytest.approx(-238.7669, abs=1e-9)

    def test_imza_kumesi_TEK_KAYNAK(self):
        b = DM.damping_budget({'nozzle': -1.0})
        assert DM.DAMPING_BUDGET_SIGNATURE_KEYS.issubset(b.keys())
        assert RS._DAMPING_BUDGET_KEYS is DM.DAMPING_BUDGET_SIGNATURE_KEYS


# ==========================================================================
# P6B4-12 — ÇEVRİLDİ (ÖH D26 / fea-cfd a3): sınadığı fonksiyon KALKTI
#
# Bu blok ``hrma.stability.response.critical_response_table``in künyeli
# kapısını sınıyordu (D25 onarımı: tek bütçe ⇄ mod başına eşleme ayrımı
# artık damping_budget()in TAM imzasına bakıyor). Onarım DOĞRUYDU ve
# imza sözleşmesi yaşıyor (aşağıdaki TestP6B412ImzaTekKaynak bloğu onu
# hâlâ sınıyor).
#
# Kalemin İKİNCİ yarısı ürün yüzeyiydi: ÖLÇÜLDÜ (D26 a3, once_a3.json)
# fonksiyonun ürün tüketicisi SIFIRDI (hrma/ altında, stability paketi
# dışında hiçbir atıf yok; motorlar mod tablosunu kendileri kurup
# critical_response_real çağırıyor). Ana model hükmü: tüketici
# bağlanamıyorsa ölü kod KALDIRILIR, testleri de. Fonksiyon kalktığı
# için bu beş bekçinin sınayacak bir şeyi yok; SÖKÜLDÜLER.
#
# Yerine geçen bekçi: tests/test_d26_fea_cfd_a3.py::
#   TestP6B412OluYuzeyKalkti — yüzeyin geri gelmediğini ve imza
#   sözleşmesinin (DAMPING_BUDGET_SIGNATURE_KEYS) yaşadığını sınar.
# ==========================================================================

# ==========================================================================
# P6B4-13 — künye sayaçları CANLI
# ==========================================================================
class TestP6B413KunyeSayaclariCanli:

    def test_sayac_kunyesi_yayimlaniyor(self):
        s = compare_with_propellant_database()['summary']
        assert 'COUNTED LIVE' in s['counter_basis']
        assert s['db_cp_k_fields_present'] > 0

    def test_alan_basina_kunye_eklenince_sayac_YUKSELIYOR(self, monkeypatch):
        """Sabit 0 olsaydı bu test kırmızı olurdu — sayaç ölçüm mü?"""
        import hrma.data.propellant_database as PDB
        onceki = compare_with_propellant_database()['summary']
        gercek_init = PDB.PropellantDatabase.__init__

        def yamali(self, *a, **kw):
            gercek_init(self, *a, **kw)
            if 'htpb' in self.database:
                self.database['htpb'] = dict(self.database['htpb'])
                self.database['htpb']['specific_heat_source'] = 'X 2020 s.5'
                self.database['htpb']['specific_heat_T_ref_K'] = 298.15

        monkeypatch.setattr(PDB.PropellantDatabase, '__init__', yamali)
        sonra = compare_with_propellant_database()['summary']
        assert (sonra['db_cp_k_fields_with_field_level_citation']
                == onceki['db_cp_k_fields_with_field_level_citation'] + 1)
        assert (sonra['db_cp_k_fields_with_reference_temperature']
                == onceki['db_cp_k_fields_with_reference_temperature'] + 1)

    def test_blok_basina_source_alan_kunyesi_SAYILMIYOR(self):
        s = compare_with_propellant_database()
        # HTPB'nin blok etiketi var ama alan künyesi yok
        assert s['rows']['htpb']['db_source_label']
        assert s['rows']['htpb']['db_specific_heat_citation_key'] is None


# ==========================================================================
# P6B4-14 — _RT_IDENTITY_BASIS artık ÖLÜ DEĞİL
# ==========================================================================
class TestP6B414RTOzdesligiYayimda:

    def _d(self):
        return CH.chamber_time_constant(l_star_m=1.0, c_star_m_s=1500.0,
                                        gamma=1.2)

    def test_kunye_YAYIMLANIYOR(self):
        d = self._d()
        assert d['rt_identity_basis'] == CH._RT_IDENTITY_BASIS
        assert 'algebraic twin' in d['rt_identity_basis']

    def test_ozdeslik_OLCULUYOR_ve_tutuyor(self):
        d = self._d()
        assert d['rt_corresponding_m2_s2'] == CH.rt_from_cstar(1500.0, 1.2)
        assert d['tau_c_via_rt_s'] == pytest.approx(d['tau_c_s'], rel=1e-12)
        assert d['tau_c_route_rel_diff'] < 1e-12

    def test_tau_c_from_volume_de_kunyeyi_TASIYOR(self):
        d = CH.tau_c_from_volume(chamber_volume_m3=0.004,
                                 throat_area_m2=0.0028,
                                 c_star_m_s=1500.0, gamma=1.2)
        assert 'rt_identity_basis' in d
        assert d['tau_c_route_rel_diff'] < 1e-12


# ==========================================================================
# P6B4-15 — çözülemeyen kökün VAKA-ÖZEL gerekçesi
# ==========================================================================
class TestP6B415CozulemeyenKokGerekcesi:

    def _tf(self):
        return CG.feed_inertance_time_constant(
            line_length_m=1.2, line_area_m2=1.2e-4,
            mass_flow_kg_s=0.9, dp_injector_Pa=6.0e5)

    def test_null_donen_her_nokta_GEREKCE_tasiyor(self):
        tf = self._tf()
        null_sayisi = 0
        for j in np.linspace(0.05, 0.60, 21):
            for tau in np.linspace(1.0e-4, 6.0e-3, 21):
                r = CG.assess_chug(float(j), float(tau), tau_c_s=2.0e-3,
                                   tau_f_s=tf)
                if r['growth_rate_1_s'] is None or r['frequency_hz'] is None:
                    null_sayisi += 1
                    assert r['root_not_resolved_reason'], (
                        f"gerekçesiz null: J={j}, tau={tau}")
                else:
                    assert r['root_not_resolved_reason'] is None
        assert null_sayisi > 0, "tarama en az bir çözülemeyen nokta içermeli"

    def test_gerekce_VAKA_OZEL_sayilari_tasiyor(self):
        tf = self._tf()
        ornek = None
        for j in np.linspace(0.05, 0.60, 21):
            for tau in np.linspace(1.0e-4, 6.0e-3, 21):
                r = CG.assess_chug(float(j), float(tau), tau_c_s=2.0e-3,
                                   tau_f_s=tf)
                if r['root_not_resolved_reason']:
                    ornek = r
                    break
            if ornek:
                break
        m = ornek['root_not_resolved_reason']
        assert 'continuation step' in m or 'dominant root' in m
        assert 'tau/tau_c' in m or 'neutral-crossing' in m

    def test_cozulen_noktada_diagnostics_BOS(self):
        tani = {}
        kok = CG.chug_rightmost_root(0.30, 1.0e-3, 2.0e-3, 0.0,
                                     diagnostics=tani)
        assert kok is not None
        assert tani == {}


# ==========================================================================
# P8B1-02 — üretilen dış zincirin taban garantisi ÖLÇÜLÜP kapıya bağlandı
# ==========================================================================
def _kontur_ve_taban():
    """Konkav vadi TAŞIYAN kontur (kademeli genişleme, iki omuz).

    Omuzlar dış yüzeyde tabanaltı konkav köşe üretir; taban ölçümü ancak
    konkav tepe VARSA anlamlıdır. Taban 19,4249 mm, gerçek hibrit motorun
    ölçülen cidar kalınlığıdır (P8B1-02 ölçümü).
    """
    z = np.linspace(0.0, 1.00, 41)
    r = np.full_like(z, 0.050)
    r[(z > 0.30) & (z < 0.70)] = 0.075
    return np.stack([z, r], axis=1), 0.0194249


class TestP8B102OrnekTabanKapisi:

    def test_meta_ORAN_ve_KAPI_alanlarini_tasiyor(self):
        kontur, t = _kontur_ve_taban()
        m = MA.build_wall_mesh(kontur, t, n_axial=64, n_radial=4)
        tb = m.meta['dis_yuzey_egrilik_tabani']
        assert tb['dis_egri_ornek_taban_orani'] is not None
        assert tb['ornek_taban_kapisi'] in (True, False)
        assert tb['ornek_taban_pay'] == MA.OUTER_FLOOR_SAMPLE_TOL

    def test_oran_OLCUMDEN_geliyor(self):
        kontur, t = _kontur_ve_taban()
        m = MA.build_wall_mesh(kontur, t, n_axial=64, n_radial=4)
        tb = m.meta['dis_yuzey_egrilik_tabani']
        assert tb['dis_egri_ornek_taban_orani'] == pytest.approx(
            tb['dis_egri_min_konkav_yaricap_m']
            / tb['outer_curvature_floor_m'], rel=1e-12)

    def test_basis_metni_ARTIK_yanlis_iddia_ETMIYOR(self):
        kontur, t = _kontur_ve_taban()
        m = MA.build_wall_mesh(kontur, t, n_axial=64, n_radial=4)
        b = m.meta['dis_yuzey_egrilik_tabani']['_basis']
        assert 'Köşe düzeltme penceresi geometrik olduğundan' not in b, (
            "ölçümle çürütülmüş iddia (örnek hep tabanın üstünde) geri "
            "gelmiş")
        assert 'ornek_taban_kapisi' in b
        assert '0,1675' in b, "na = 1024 ölçümü künyede adıyla durmalı"

    def test_ince_turda_garanti_OLCUMLE_DUSUYOR(self):
        """İnce turda taban garantisi ölçümle geçersiz — bayrak False.

        ÖH D27 a1 YARGISI (OH-D25-28): bu bekçi HAM ÖRNEKLEMENİN kusurunu
        ölçer. İç kontur köşe tabanı ürün varsayılanı olunca kademeli
        genişlemenin omuz köşeleri mesh kurulmadan önce yuvarlanıyor ve
        na = 256'da örnek/taban oranı 0,23532 → 0,99970'e çıkıyor, yani
        garanti ARTIK DÜŞMÜYOR (ölçüm: docs/scofield/raw/OH/D27/fea-cfd/
        a1/sonra_a1.json §G3). Kusur ölçümü YALITILDI (tol = 0) ve ürün
        yolundaki iyileşme ayrıca kilitlendi; eşik gevşetilmedi.
        """
        kontur, t = _kontur_ve_taban()
        ince = MA.build_wall_mesh(kontur, t, n_axial=256, n_radial=4,
                                  inner_kink_tol_rad=0.0)
        tb = ince.meta['dis_yuzey_egrilik_tabani']
        assert tb['ornek_taban_kapisi'] is False
        assert tb['dis_egri_ornek_taban_orani'] < 0.5
        assert SA._ornek_taban_kapisi_gecti(ince) is False
        # KISMEN: ölçüm yayımlanır, yakınsama hükmüne BUGÜN bağlanmaz
        beyan = SA._geometri_kapisi_beyani(ince)
        assert beyan['ornek_taban_kapisi'] is False
        assert beyan['ornek_taban_orani'] < 0.5
        # ÜRÜN YOLU (taban AÇIK): aynı ince turda garanti SAĞLANIYOR.
        urun = MA.build_wall_mesh(kontur, t, n_axial=256, n_radial=4)
        tbu = urun.meta['dis_yuzey_egrilik_tabani']
        assert tbu['ornek_taban_kapisi'] is True, (
            'iç köşe tabanı açıkken ince turda örnek-taban garantisi hâlâ '
            f"düşüyor: {tbu['dis_egri_ornek_taban_orani']}")
        assert (tbu['dis_egri_ornek_taban_orani']
                > tb['dis_egri_ornek_taban_orani'])
        assert SA._ornek_taban_kapisi_gecti(urun) is True

    def test_kaba_turda_kapi_GECIYOR(self):
        kontur, t = _kontur_ve_taban()
        m = MA.build_wall_mesh(kontur, t, n_axial=64, n_radial=4)
        assert SA._ornek_taban_kapisi_gecti(m) is True

    def test_alan_yoksa_kapi_UYGULANMIYOR(self):
        class SahteMesh:
            meta = {}
        assert SA._ornek_taban_kapisi_gecti(SahteMesh()) is True


# ==========================================================================
# P8B1-04 — hacimsel kilitlenme: beyan + FAIL-CLOSED eşik
# ==========================================================================
class TestP8B104HacimselKilitlenme:

    def _mesh(self):
        kontur = np.stack([np.linspace(0.0, 0.20, 21),
                           np.full(21, 0.050)], axis=1)
        return MA.build_wall_mesh(kontur, 0.005, n_axial=20, n_radial=4)

    def test_esigin_ustunde_EMNIYET_HUKMU_VERILMIYOR(self):
        r = SA.solve_pressure(
            self._mesh(),
            SA.Material(E=6.0e6, nu=0.4995, yield_strength=1.0e6),
            inner_pressure=1.0e6)
        assert r.min_safety_factor is None, (
            "kilitlenen formülasyondan emniyet katsayısı yayımlanmaz")
        m = r.meta['safety_factor_durumu']
        assert 'kilitlenme' in m.lower() or 'KİLİTLENİR' in m
        assert 'P8B1-04' in m
        # ölçülen hata her koşumun künyesinde adıyla durur
        k = r.meta['hacimsel_kilitlenme']
        assert (k['olculen_hata_lame_analitigine_karsi']['0.4995']
                ['maks_vM_yuzde'] == pytest.approx(-60.45))

    def test_alanlar_YINE_donuyor(self):
        """Hükümsüz tüketiciler (tane görselleştirmesi) çalışmaya devam."""
        r = SA.solve_pressure(
            self._mesh(),
            SA.Material(E=6.0e6, nu=0.4995, yield_strength=1.0e6),
            inner_pressure=1.0e6)
        assert r.max_von_mises_nodal > 0.0
        assert np.all(np.isfinite(r.displacement))

    def test_esik_TEK_KAYNAK_ve_deger(self):
        assert SA.Q4_LOCKING_NU_MAX == 0.495
        r = SA.solve_pressure(
            self._mesh(),
            SA.Material(E=6.0e6, nu=SA.Q4_LOCKING_NU_MAX,
                        yield_strength=1.0e6),
            inner_pressure=1.0e6)
        assert r.min_safety_factor is None

    def test_urun_malzemeleri_HUKUM_ALIYOR(self):
        for nu in (0.27, 0.29, 0.30, 0.33, 0.49):
            r = SA.solve_pressure(
                self._mesh(),
                SA.Material(E=2.0e11, nu=nu, yield_strength=2.5e8),
                inner_pressure=1.0e6)
            assert r.min_safety_factor is not None and \
                math.isfinite(r.min_safety_factor)

    def test_kilitlenme_BEYANI_sonucta_yayimlaniyor(self):
        kontur = np.stack([np.linspace(0.0, 0.20, 21),
                           np.full(21, 0.050)], axis=1)
        mesh = MA.build_wall_mesh(kontur, 0.005, n_axial=20, n_radial=4)
        r = SA.solve_pressure(
            mesh, SA.Material(E=2.0e11, nu=0.3, yield_strength=2.5e8),
            inner_pressure=1.0e6)
        k = r.meta['hacimsel_kilitlenme']
        assert k['nu_ust_siniri'] == SA.Q4_LOCKING_NU_MAX
        assert '0.4995' in k['olculen_hata_lame_analitigine_karsi']
        assert (k['olculen_hata_lame_analitigine_karsi']['0.4995']
                ['maks_vM_yuzde'] == pytest.approx(-60.45))
        assert any('kilitlenme' in x for x in r.meta['not_modelled'])

    def test_lame_hatasi_esigin_ALTINDA_kabul_edilebilir(self):
        """ν = 0,49'da kilitlenme payı ayrıklaştırma tabanının mertebesinde."""
        a, b, p, E = 0.05, 0.08, 10.0e6, 6.0e6
        kontur = np.array([[0.0, a], [0.20, a]])
        mesh = MA.build_wall_mesh(kontur, b - a, 16, 4, offset_mode="radial")
        hata = {}
        for nu in (0.30, 0.49):
            A = p * a ** 2 / (b ** 2 - a ** 2)
            B = p * a ** 2 * b ** 2 / (b ** 2 - a ** 2)
            sr, st = A - B / a ** 2, A + B / a ** 2
            sz = nu * (sr + st)
            vm_a = float(SA.von_mises(np.array([sz, sr, st, 0.0])))
            r = SA.solve_pressure(
                mesh, SA.Material(E=E, nu=nu, yield_strength=1.0e6), p,
                axial_fix="both_ends")
            hata[nu] = 100.0 * (r.max_von_mises - vm_a) / vm_a
        # taban −9,51 %, ν = 0,49 −14,98 % (ölçüldü) → pay ~5,5 puan
        assert abs(hata[0.49] - hata[0.30]) < 10.0


# ==========================================================================
# P8B1-05 — yuvarlanan-top penceresi SINIRLI
# ==========================================================================
class TestP8B105TopPenceresiSiniri:

    def test_sinir_asilinca_FAIL_CLOSED_ValueError(self, monkeypatch):
        """Kapı, sınırın KENDİSİ küçültülerek UCUZ sınanır.

        Gerçek sınırla (262.144) sınamak, kapı KALKTIĞINDA O(m²) hesabı
        fiilen başlatır ve süreci öldürür — kalemin kusuru tam olarak
        budur. Bu yüzden sınır geçici olarak 128'e çekilir: kapı VARSA
        ValueError, YOKSA çağrı mikrosaniyede döner ve test kırmızıya
        düşer. Sınırın GERÇEK değeri ayrı testte pinlenir.
        """
        monkeypatch.setattr(MA, 'CLOSING_BALL_WINDOW_MAX', 128)
        F = np.zeros(64)
        dz = 1.0e-4
        radius = dz * 200          # m = 200 > 128
        with pytest.raises(ValueError) as exc:
            MA._rolling_ball_closing(F, dz, radius)
        m = str(exc.value)
        assert 'CLOSING_BALL_WINDOW_MAX' in m
        assert 'O(m^2)' in m
        assert 'silently clipped' in m
        assert 'm = ceil(radius/dz) = 200' in m

    def test_sinir_altinda_CALISMAYA_devam(self):
        F = np.zeros(256)
        dz = 1.0e-3
        H = MA._rolling_ball_closing(F, dz, 0.05)
        assert H.shape == F.shape
        assert np.all(H >= F - 1e-15)

    def test_gercek_motor_girdisi_sinirin_COK_ALTINDA(self):
        kontur, t = _kontur_ve_taban()
        m = MA.build_wall_mesh(kontur, t, n_axial=64, n_radial=4)
        tb = m.meta['dis_yuzey_egrilik_tabani']
        dz = tb['kapama_olcumu']['izgara_adimi_m']
        pencere = math.ceil(tb['outer_curvature_floor_m'] / dz)
        assert pencere < MA.CLOSING_BALL_WINDOW_MAX / 100

    def test_sinir_sabiti_TANIMLI(self):
        assert MA.CLOSING_BALL_WINDOW_MAX == 4 * MA.CLOSING_GRID_MAX_POINTS


# ==========================================================================
# P8B1-06 — mutlak sıfır altı sıcaklık FAIL-CLOSED
# ==========================================================================
def _termal_mesh():
    kontur = np.stack([np.linspace(0.0, 0.10, 17),
                       np.full(17, 0.030)], axis=1)
    return MA.build_wall_mesh(kontur, 0.004, n_axial=16, n_radial=4)


class TestP8B106FizikselligeKapi:

    def test_mutlak_sifir_altina_inen_alan_REDDEDILIYOR(self):
        mesh = _termal_mesh()
        mat = TA.ThermalMaterial(rho=7850.0, cp=460.0, k=45.0, name='celik')
        with pytest.raises(RuntimeError) as exc:
            TA.solve_transient_auto(
                mesh, mat, t_end=5.0,
                inner_bc=TA.HeatFluxBC(q=-2.0e6),
                outer_bc=TA.AmbientBC(h=10.0, T_ambient=293.15,
                                      emissivity=0.0),
                T_initial=293.15)
        m = str(exc.value)
        assert 'FİZİKSEL OLMAYAN SICAKLIK ALANI' in m
        assert 'mutlak sıfırın' in m
        assert 'P8B1-06' in m

    def test_isimali_uc_vaka_da_REDDEDILIYOR(self):
        mesh = _termal_mesh()
        mat = TA.ThermalMaterial(rho=7850.0, cp=460.0, k=45.0, name='celik')
        with pytest.raises(RuntimeError):
            TA.solve_transient_auto(
                mesh, mat, t_end=5.0,
                inner_bc=TA.HeatFluxBC(q=-1.0e9),
                outer_bc=TA.AmbientBC(h=10.0, T_ambient=293.15,
                                      emissivity=0.3),
                T_initial=293.15)

    def test_hata_DUGUM_ve_ZAMAN_soyluyor(self):
        mesh = _termal_mesh()
        mat = TA.ThermalMaterial(rho=7850.0, cp=460.0, k=45.0, name='celik')
        with pytest.raises(RuntimeError) as exc:
            TA.solve_transient_auto(
                mesh, mat, t_end=5.0,
                inner_bc=TA.HeatFluxBC(q=-2.0e6),
                outer_bc=TA.AmbientBC(h=10.0, T_ambient=293.15,
                                      emissivity=0.3),
                T_initial=293.15)
        m = str(exc.value)
        assert 'düğüm' in m and 't = ' in m and 'K' in m

    def test_fiziksel_isitma_kosumu_YESIL_kalıyor(self):
        mesh = _termal_mesh()
        mat = TA.ThermalMaterial(rho=7850.0, cp=460.0, k=45.0, name='celik')
        r = TA.solve_transient_auto(
            mesh, mat, t_end=2.0,
            inner_bc=TA.ConvectionBC(h=2000.0, T_inf=1800.0),
            outer_bc=TA.AmbientBC(h=10.0, T_ambient=293.15, emissivity=0.3),
            T_initial=293.15)
        assert float(np.min(r.T_history)) > 0.0
        assert r.peak_wall_T > 293.15


# ==========================================================================
# P8B1-07 — p = 0'da inf emniyet katsayısı ve taşma uyarısı YOK
# ==========================================================================
def _yuksuz():
    kontur = np.stack([np.linspace(0.0, 0.20, 21),
                       np.full(21, 0.050)], axis=1)
    mesh = MA.build_wall_mesh(kontur, 0.005, n_axial=20, n_radial=4)
    mat = SA.Material(E=2.0e11, nu=0.3, yield_strength=2.5e8, name='celik')
    return mesh, mat


class TestP8B107SifirYukEmniyetKatsayisi:

    def test_min_safety_factor_INF_DEGIL_None(self):
        mesh, mat = _yuksuz()
        r = SA.solve_pressure(mesh, mat, inner_pressure=0.0)
        assert r.max_von_mises_nodal == 0.0
        assert r.min_safety_factor is None, (
            "yüksüz koşumda 'sonsuz emniyet' yayımlanmaz")

    def test_json_gecerli(self):
        """Yüksüz emniyet katsayısı JSON'a KAYIPSIZ geçer (``null``).

        ÖH D26 fix-25a — bu testin gövdesi İDDİASIZDI: ``allow_nan=False``,
        ``inf``/``nan`` gelseydi ValueError atacağı için niyet doğruydu ama
        ölçüt YAZILMAMIŞTI; sonuç boş/None gelse de test yeşil kalırdı.
        Dört bekçi (P13B2-10'un iki tavanı, OH-D23-01 hizalaması, OH-D24-04
        kredi kaynağı) bu TEK testi adıyla gösterdi. Onarım tavanları değil
        testi düzeltir: üretilen dize artık okunuyor ve geri çözülüp değerin
        ``None`` olarak KORUNDUĞU sınanıyor.
        """
        import json
        mesh, mat = _yuksuz()
        r = SA.solve_pressure(mesh, mat, inner_pressure=0.0)
        # inf/nan olsaydı allow_nan=False burada ValueError atardı
        dize = json.dumps({'min_safety_factor': r.min_safety_factor},
                          allow_nan=False)
        assert json.loads(dize) == {'min_safety_factor': None}, dize
        assert 'Infinity' not in dize and 'NaN' not in dize, dize

    def test_overflow_UYARISI_yok(self):
        import warnings
        mesh, mat = _yuksuz()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            SA.solve_pressure(mesh, mat, inner_pressure=0.0)
        assert not [x for x in w if 'overflow' in str(x.message)]

    def test_durum_BEYAN_ediliyor(self):
        mesh, mat = _yuksuz()
        r = SA.solve_pressure(mesh, mat, inner_pressure=0.0)
        d = r.meta['safety_factor_durumu']
        assert 'VERİLMEDİ' in d and 'yüksüz' in d and 'P8B1-07' in d
        assert r.meta['safety_factor_sonsuz_dugum'] == \
            r.meta['safety_factor_dugum_sayisi']

    def test_yuklu_kosum_DEGISMEDI(self):
        mesh, mat = _yuksuz()
        r = SA.solve_pressure(mesh, mat, inner_pressure=5.0e6)
        assert r.min_safety_factor is not None
        assert math.isfinite(r.min_safety_factor)
        # solve_pressure hüküm sayısını ASME lineerleştirmesinden verir
        # (OH-D24-01, aşama-1); burada yalnız SONLU ve pozitif olduğu
        # doğrulanır — P8B1-07 yalnız SIFIR YÜK vakasını değiştirdi.
        assert r.min_safety_factor > 0.0
        assert r.meta.get('safety_factor_durumu') is None
