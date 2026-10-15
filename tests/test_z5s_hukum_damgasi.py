"""ÖH Z5S / PK6 — "hüküm damgası" paketinin bekçileri.

Bu dosya PK6'nın onardığı sekiz kalemin SÖZLEŞMESİNİ kilitler. Her iddia,
onarımın ölçülmüş gerçeğine bağlıdır ve kusur geri gelirse kırmızı olur.
Kapsanan kalemler:

* ``P11B5-02`` (KRİTİK) — radyasyon dengesi hükmü: uç ``unconservative:true``
  derken panel YEŞİL "WITHIN SERVICE LIMIT" basıyordu; ayrıca ihmalleri
  düzeltecek iki girdi (``view_factor``, ``q_gas_radiation_W_m2``) uçta
  beyaz listede olmadığı için SESSİZCE düşüyordu.
* ``P4B1-12`` — ``no_net_heating`` dalında yayımlanan üç akı birbirini
  tutmuyordu (kırpma konvektif terimin işaretini yutuyordu) ve gerekçe
  metni sayıların tersini söylüyordu.
* ``P4B1-14`` — aynı zarf ihlali iki yolda iki zıt damga alıyordu;
  ``model_valid`` hiçbir şey modellenmemişken YEŞİL kalıyordu.
* ``P4B1-15`` — ``stress_safety_factor`` adı kadar iddia taşımıyordu:
  ``pressure`` argümanı alınıp hiç okunmuyordu.
* ``P5B1-02`` — cidar sıcaklığı ALEVDEN değil malzemenin servis
  limitinden çıkıyordu (marj her malzemede tam 0,900000).
* ``P5B1-11`` — kütle hesabı değerlendirilen kapak kalınlığını okumuyordu.
* ``P5B1-17`` — ``safety_factor_is_tautological`` bayrağı kalın cidar
  rejiminde fazla iddia ediyordu.
* ``P5B1-21`` — cıvata yerleşimi hiç denetlenmiyordu.
"""
import io
import json
import re
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import pytest

from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
from hrma.analysis.structural_analysis import StructuralAnalyzer
from hrma.analysis.thermal_protection import ThermalProtectionAnalyzer

REPO_ROOT = Path(__file__).resolve().parents[1]
PANEL = REPO_ROOT / 'hrma' / 'static' / 'js' / 'panels' / 'protection_panel.js'

#: PK6 ölçüm noktaları — hepsi defterdeki savcı vakalarından alınmıştır.
REF_YAPISAL = {
    'chamber_pressure': 40.0, 'chamber_diameter': 0.1,
    'chamber_length': 0.5, 'throat_diameter': 0.02, 'burn_time': 10.0,
    'chamber_temperature': 3000.0,
}


def _sessiz(fn, *a, **kw):
    with redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


@pytest.fixture(scope='module')
def tp():
    return ThermalProtectionAnalyzer()


@pytest.fixture(scope='module')
def yapisal():
    return StructuralAnalyzer()


@pytest.fixture(scope='module')
def isi():
    return HeatTransferAnalyzer()


@pytest.fixture(scope='module')
def client():
    with redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


# ===========================================================================
# P11B5-02 (KRİTİK) — iyimser hüküm ekranda YEŞİL basılamaz
# ===========================================================================
class TestP11B5_02RadyasyonHukmu:

    RAD = {'mode': 'radiation_equilibrium', 'h_gas_W_m2K': 500.0,
           'T_recovery_K': 3000.0, 'material': 'niobium_c103'}

    def test_uc_iki_konservatif_girdiyi_gecirir(self, client):
        """``view_factor`` ve ``q_gas_radiation_W_m2`` artık uçtan geçer.

        ÖLÇÜLDÜ (taban df67bce): iki anahtar ``_TP_MODE_KEYS`` beyaz
        listesinde OLMADIĞI için uç onları sessizce düşürüyordu — iki
        istek BAYT-AYNI gövde üretiyordu (sha256 2c0acd888b0dbcb6). Bu,
        çekirdeğin "Supply view_factor and q_gas_radiation_W_m2 for a
        bounding estimate" cümlesini DİNLENEMEZ bir uyarıya çeviriyordu:
        kullanıcının ihmalleri kapatmasının yolu yoktu.
        """
        r1 = client.post('/api/thermal-protection', json=dict(self.RAD))
        r2 = client.post('/api/thermal-protection',
                         json=dict(self.RAD, view_factor=0.7,
                                   q_gas_radiation_W_m2=50000.0))
        assert r1.status_code == 200 and r2.status_code == 200
        j1, j2 = r1.get_json(), r2.get_json()

        assert j1['view_factor'] == pytest.approx(1.0)
        assert j1['q_gas_radiation_W_m2'] == pytest.approx(0.0)
        assert j2['view_factor'] == pytest.approx(0.7), (
            'uç view_factor girdisini hâlâ düşürüyor')
        assert j2['q_gas_radiation_W_m2'] == pytest.approx(50000.0), (
            'uç q_gas_radiation_W_m2 girdisini hâlâ düşürüyor')

        # İhmaller malzeme kararını DEĞİŞTİRİYOR: sayı 152 K oynuyor.
        assert j2['T_wall_eq_K'] > j1['T_wall_eq_K'] + 100.0, (
            f"ihmallerin bedeli ölçülemiyor: {j1['T_wall_eq_K']:.1f} K -> "
            f"{j2['T_wall_eq_K']:.1f} K")
        assert j1['unconservative'] is True
        assert j2['unconservative'] is False, (
            'iki girdi de verildiğinde hüküm hâlâ "iyimser" damgalı')
        assert j2['unconservative_note'] is None

    def test_panel_iyimser_hukumde_yesil_basmaz(self):
        """``renderRadiation`` iki dürüstlük alanını da OKUMALI.

        Kusur bir bekçi VARKEN doğmuştu, çünkü bekçi YÖNÜ yanlıştı
        (ileri yön: panelin okuduğu alan yükte var mı). Buradaki iddia
        panelin KAYNAĞINA bakar: ``unconservative`` okunuyor mu, ve
        sınırın altındaki bir sayı iyimserken 'ok' rengi basılıyor mu.
        """
        src = PANEL.read_text(encoding='utf-8')
        gövde_baslangic = src.index('function renderRadiation')
        gövde = src[gövde_baslangic:src.index('function render(',
                                              gövde_baslangic)]

        assert 'unconservative' in gövde, (
            'renderRadiation `unconservative` alanını hâlâ hiç anmıyor')
        assert 'unconservative_note' in gövde, (
            'renderRadiation `unconservative_note` alanını hiç anmıyor')

        # Hüküm rozeti: sınırın altında + iyimser -> 'ok' YASAK.
        assert re.search(r"uncons\s*\)?\s*\n?\s*[^\n]*'warn'", gövde) or (
            "'warn', uncNote" in gövde), (
            'iyimser hükümde uyarı rengi/ipucu üretilmiyor')
        # limitKind artık iki eksenli.
        assert re.search(r'function limitKind\(\s*within\s*,\s*\w+\s*\)', src), (
            'limitKind hâlâ tek eksenli (yalnız within_limit)')

    def test_limit_asiliyorsa_iyimserlik_rengi_iyilestirmez(self):
        """Sınır aşılmışsa renk 'err' kalır; iyimserlik onu yumuşatmaz."""
        src = PANEL.read_text(encoding='utf-8')
        gövde = src[src.index('function limitKind'):
                    src.index('// ---- Ablatif mod ----')]
        assert "if (!within) return 'err';" in gövde, (
            'limitKind sınır aşımında koşulsuz kırmızı basmıyor')


# ===========================================================================
# P4B1-12 — yayımlanan akılar kendi içinde kapanır, gerekçe sayıyı söyler
# ===========================================================================
class TestP4B1_12AkiTutarliligi:

    @staticmethod
    def _soguk(tp):
        """Gaz, yüzey sıcaklığının 916,5 K ALTINDA (savcının vakası)."""
        return tp.ablative_thickness(9.9e6, burn_time_s=50.0,
                                     h_gas_W_m2K=5.0e3,
                                     T_recovery_K=1133.53,
                                     gas_cp_J_kgK=2000.0)

    def test_konvektif_terim_isaretini_korur(self, tp):
        """``max(q_unblown, 0)`` kırpması KALKTI: işaret yayımlanıyor."""
        out = self._soguk(tp)
        beklenen = (5.0e3 * float(out['blowing_blockage'])
                    * (1133.53 - float(out['T_surface_K'])))
        assert beklenen < 0.0, 'düzenek bozuk: bu vakada terim negatif olmalı'
        assert out['q_conv_blocked_W_m2'] == pytest.approx(beklenen, rel=1e-9)
        # Defterin ölçümü −4.583,4 kW/m² idi (h·(T_r−T_s) tam sayısı);
        # bu depoda ψ = 1 ve T_s = 2050 K ile −4.582,35 kW/m² ölçülüyor.
        assert out['q_conv_blocked_W_m2'] / 1e3 == pytest.approx(-4582.35,
                                                                 abs=1.0)

    def test_ucu_yayimlanan_girdilerden_yeniden_kurulur(self, tp):
        """q_mean = max(q_conv − q_rerad, 0) — üçlü kapanmalı."""
        out = self._soguk(tp)
        net = out['q_conv_blocked_W_m2'] - out['q_reradiated_W_m2']
        assert out['q_mean_W_m2'] == pytest.approx(max(net, 0.0), abs=1e-6)

    def test_gerekce_denge_iddiasini_ancak_denge_varken_kurar(self, tp):
        """"Geldiği kadarını geri ışıyor" cümlesi ölçüye bağlandı."""
        out = self._soguk(tp)
        note = out['validity_note']
        assert note.startswith('NO NET HEATING')
        assert 're-radiates as much as' not in note, (
            'konvektif terim negatifken denge iddiası hâlâ basılıyor')
        assert 'BELOW the ablation temperature' in note
        assert 'REMOVES' in note

    def test_band_uyarisi_kosullu(self, tp):
        """CAUTION cümlesi SABİT metin değil; malzemenin bandına bağlı.

        Ölçüt uydurulmadı: uyarı, kurtarma sıcaklığı malzemenin KENDİ
        ``T_ablation_band_K`` bandının içindeyken verilir (o zaman band
        içinden başka bir T_s seçimi hükmü çevirebilir).
        """
        yakin = tp.ablative_thickness(9.9e6, burn_time_s=50.0,
                                      h_gas_W_m2K=1.0e3, T_recovery_K=2100.0,
                                      gas_cp_J_kgK=2000.0)   # band 1900-2300
        uzak = self._soguk(tp)                                # 1133,53 K
        assert yakin['validity_note'] != uzak['validity_note']
        assert 'CAUTION' in yakin['validity_note']
        assert 'CAUTION' not in uzak['validity_note']
        assert 'OUTSIDE the T_ablation_band_K' in uzak['validity_note']


# ===========================================================================
# P4B1-14 — tek damga, iki yol
# ===========================================================================
class TestP4B1_14TekDamga:

    def test_ayni_zarf_ihlali_ayni_damgayi_alir(self, tp):
        from hrma.data.materials_db import get_material
        rho = get_material('ablative')['density']
        eski = tp.ablative_thickness(0.6195e-3 * rho * 8.0e6,
                                     burn_time_s=300.0,
                                     station_radius_m=0.0496)
        yeni = tp.ablative_thickness(1.0e6, burn_time_s=100.0,
                                     h_gas_W_m2K=5.0e4, T_recovery_K=3500.0)
        assert eski['model_valid'] is False and yeni['model_valid'] is False
        assert eski['thickness_status'] == yeni['thickness_status'] \
            == 'NOT_MODELLED'
        assert eski['required_thickness_mm'] is None
        assert yeni['required_thickness_mm'] is None

    def test_modellenmemis_sonuc_yesil_damga_tasimaz(self, tp):
        """``no_net_heating``: kalınlık yok -> ``model_valid`` yeşil olamaz."""
        for out in (
                tp.ablative_thickness(9.9e6, burn_time_s=50.0,
                                      h_gas_W_m2K=1.0e3, T_recovery_K=2100.0,
                                      gas_cp_J_kgK=2000.0),
                TestP4B1_12AkiTutarliligi._soguk(tp)):
            assert out['thickness_status'] == 'NOT_MODELLED'
            assert out['model_valid'] is False
            assert out['required_thickness_mm'] is None

    def test_saglam_tasarim_hala_kalinlik_yayimlar(self, tp):
        """Kapı YALNIZ zarf dışında konuşur — sağlam vaka kırılmadı."""
        out = tp.ablative_thickness(2.0e6, burn_time_s=10.0,
                                    material='silica_phenolic')
        assert out['thickness_status'] == 'sized'
        assert out['model_valid'] is True
        assert out['required_thickness_mm'] > 0.0


# ===========================================================================
# P4B1-15 — stress_safety_factor adı kadar iddia taşır
# ===========================================================================
class TestP4B1_15GerilmeKatsayisi:

    MD = {'chamber_temperature': 3200, 'chamber_diameter': 0.1,
          'chamber_length': 0.5, 'burn_time': 10, 'mdot_total': 1.0}

    def _kos(self, isi, pc_bar):
        return _sessiz(isi.analyze_heat_transfer,
                       dict(self.MD, chamber_pressure=pc_bar),
                       material='steel_4130', wall_thickness=0.005,
                       cooling_type='regenerative')['safety_analysis']

    @pytest.mark.parametrize('pc_bar,hoop_MPa', [(20.0, 20.0), (100.0, 100.0),
                                                 (500.0, 500.0),
                                                 (2000.0, 2000.0)])
    def test_cember_terimi_katsayiya_giriyor(self, isi, pc_bar, hoop_MPa):
        """σ = p·r/t katsayıya SÜPERPOZE ediliyor (Barlow / Roark 13)."""
        s = self._kos(isi, pc_bar)
        assert s['pressure_hoop_stress_MPa'] == pytest.approx(hoop_MPa,
                                                              rel=1e-9)
        assert s['combined_stress_MPa'] == pytest.approx(
            s['thermal_stress'] + hoop_MPa, rel=1e-12)
        akma = s['thermal_stress_properties']['yield_strength_MPa']
        assert s['stress_safety_factor'] == pytest.approx(
            akma / s['combined_stress_MPa'], rel=1e-12)
        assert s['stress_safety_factor_scope'] == \
            'thermal_gradient_plus_pressure_hoop'

    def test_makas_kapandi(self, isi):
        """Yalnız-termal katsayı ARTIK yayımlanmıyor (iyimserlik bitti).

        Defterin ölçtüğü makas: %1,1 (20 bar) → %59,7 (2000 bar).
        """
        for pc in (20.0, 2000.0):
            s = self._kos(isi, pc)
            yalniz_termal = (
                s['thermal_stress_properties']['yield_strength_MPa']
                / s['thermal_stress'])
            assert s['stress_safety_factor'] < yalniz_termal, (
                f'Pc={pc:g} bar: katsayı hâlâ yalnız-termal kadar iyimser')

    def test_yaricap_yoksa_terim_uydurulmaz(self, isi):
        """Fail-closed: çember terimi kurulamıyorsa KÜNYE söyler."""
        s = isi._analyze_thermal_safety(
            900.0, {'name': 'steel_4130', 'allowable_temperature': 811.0,
                    'melting_point': 1700.0},
            0.005, 20.0e5, wall_delta_T=50.0)      # chamber_radius_m YOK
        assert s['stress_safety_factor_scope'] == 'thermal_gradient_only'
        assert s['pressure_hoop_stress_MPa'] == 0.0
        metin = s['stress_safety_factor_basis'].lower()
        assert 'thermal gradient only' in metin
        assert 'chamber_radius_m' in metin
        assert 'optimistic' in metin

    def test_basinc_argumani_gercekten_okunuyor(self):
        """Yapısal ölçüm (AST): ölü argüman kalmadı."""
        import ast
        kaynak = (REPO_ROOT / 'hrma' / 'analysis'
                  / 'heat_transfer_analysis.py')
        agac = ast.parse(kaynak.read_text(encoding='utf-8'))
        dugum = next(n for n in ast.walk(agac)
                     if isinstance(n, ast.FunctionDef)
                     and n.name == '_analyze_thermal_safety')
        okunan = {n.id for n in ast.walk(dugum)
                  if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        assert 'pressure' in okunan


# ===========================================================================
# P5B1-02 — servis sınırı ekseni ALEVİ görür
# ===========================================================================
class TestP5B1_02CidarSicakligi:

    @pytest.mark.parametrize('malzeme', ['steel_4130', 'aluminum_6061',
                                         'inconel_718'])
    def test_tahmin_alevi_izliyor(self, yapisal, malzeme):
        """1000 / 3000 / 10000 K aynı cidarı ÜRETEMEZ.

        Eski hâl (ölçüldü): üç alevde de peak 729,90 K ve
        thermal_margin_ratio TAM 0,900000 — yani sayı aleve değil
        malzemeye bakıyordu, termal UNSAFE bandı ölüydü.
        """
        okumalar = {}
        for T in (1000.0, 3000.0, 10000.0):
            sa = _sessiz(yapisal.analyze_structure,
                         dict(REF_YAPISAL, chamber_temperature=T),
                         material=malzeme,
                         design_pressure_factor=1.5)['safety_analysis']
            okumalar[T] = (sa['peak_wall_temperature_K'],
                           sa['thermal_margin_ratio'])
        assert okumalar[10000.0][0] > okumalar[1000.0][0] + 1.0, okumalar
        oranlar = {round(v[1], 6) for v in okumalar.values()}
        assert len(oranlar) == 3, (
            f'termal marj hâlâ sabit: {oranlar} (eski kusur: hep 0,900000)')

    def test_ust_sinir_kunyesi_adiyla_yaziliyor(self, yapisal):
        """Sayının ÜST SINIR olduğu beyan edilir (sahte ölçüm yasağı)."""
        sa = _sessiz(yapisal.analyze_structure, dict(REF_YAPISAL),
                     material='steel_4130',
                     design_pressure_factor=1.5)['safety_analysis']
        kunye = sa['peak_wall_temperature_basis']
        assert 'UPPER BOUND' in kunye
        assert 'not a realised temperature' in kunye
        assert sa['exceeds_max_service_temp_peak'] is True

    def test_olculmus_cidar_yolu_degismedi(self, yapisal):
        """Gerçek cidar sıcaklığı verildiğinde ÜST SINIR devreye girmez."""
        sa = _sessiz(yapisal.analyze_structure,
                     dict(REF_YAPISAL, wall_temperature_hot=860.0,
                          wall_temperature_cold=560.0),
                     material='steel_4130',
                     design_pressure_factor=1.5)['safety_analysis']
        assert sa['peak_wall_temperature_K'] == pytest.approx(860.0)
        assert 'measured wall temperature' in sa['peak_wall_temperature_basis']

    def test_sinirin_altindaki_alev_hukmu_kazanir(self, yapisal):
        """Asimetrik T_aw doktrini: üst sınır altındaysa SAFE kazanılır."""
        sa = _sessiz(yapisal.analyze_structure,
                     dict(REF_YAPISAL, chamber_temperature=500.0),
                     material='steel_4130',
                     design_pressure_factor=1.5)['safety_analysis']
        assert sa['thermal_margin_ratio'] < 0.70
        assert sa['exceeds_max_service_temp_peak'] is False


# ===========================================================================
# P5B1-11 — kütle değerlendirilen kapaktan
# ===========================================================================
class TestP5B1_11KapakKutlesi:

    @pytest.mark.parametrize('ince,kalin', [(0.002, 0.020), (0.002, 0.050)])
    def test_kapak_kalinligi_kutleye_iniyor(self, yapisal, ince, kalin):
        def _kos(t):
            r = _sessiz(yapisal.analyze_structure, dict(REF_YAPISAL),
                        design_safety_factor=3.0, actual_end_cap_thickness=t)
            return r['end_cap_analysis'], r['weight_analysis']

        ec_i, w_i = _kos(ince)
        ec_k, w_k = _kos(kalin)
        assert ec_i['design_mode'] == ec_k['design_mode'] == 'verify'
        assert w_i['end_cap_thickness_used_mm'] == pytest.approx(ince * 1e3)
        assert w_k['end_cap_thickness_used_mm'] == pytest.approx(kalin * 1e3)
        # Kütle kalınlıkla DOĞRU ORANTILI (aynı alan, aynı yoğunluk).
        assert w_k['end_caps_weight'] / w_i['end_caps_weight'] == \
            pytest.approx(kalin / ince, rel=1e-9)
        assert w_k['total_weight'] > w_i['total_weight']

    def test_kutle_kaleminin_kunyesi_var(self, yapisal):
        w = _sessiz(yapisal.analyze_structure, dict(REF_YAPISAL),
                    actual_end_cap_thickness=0.01)['weight_analysis']
        assert 'head_thickness_used_mm' in w['end_caps_weight_basis']
        assert w['total_weight'] == pytest.approx(
            w['chamber_weight'] + w['nozzle_weight'] + w['end_caps_weight'])


# ===========================================================================
# P5B1-17 — totoloji bayrağı adı kadar iddia taşır
# ===========================================================================
class TestP5B1_17TotolojiBayragi:

    def test_totolojik_isaretli_aday_tasarimla_hareket_etmez(self, yapisal):
        """Bir totoloji hareket edemez — bayrak artık keskin ölçütte."""
        d = _sessiz(yapisal.analyze_structure,
                    dict(REF_YAPISAL, chamber_pressure=40.0),
                    design_safety_factor=4.8)['safety_analysis']
        y = _sessiz(yapisal.analyze_structure,
                    dict(REF_YAPISAL, chamber_pressure=3000.0),
                    design_safety_factor=4.8)['safety_analysis']
        hd, hy = (d['safety_factor_is_tautological'],
                  y['safety_factor_is_tautological'])
        ortak = [ad for ad in hd if hd[ad] and hy.get(ad)]
        assert ortak, 'iki koşuda da işaretli aday yok — düzenek bozuk'
        for ad in ortak:
            a, b = d['safety_factors'][ad], y['safety_factors'][ad]
            if np.isfinite(a) and np.isfinite(b):
                assert abs(b - a) <= 1e-9 * max(1.0, abs(a)), (
                    f'"totolojik" işaretli {ad} tasarımla hareket ediyor: '
                    f'{a:.4f} -> {b:.4f}')

    def test_eski_soru_adiyla_duruyor(self, yapisal):
        """"Cidarı HRMA mı seçti?" sorusu KAYBOLMADI, adı düzeldi."""
        y = _sessiz(yapisal.analyze_structure,
                    dict(REF_YAPISAL, chamber_pressure=3000.0),
                    design_safety_factor=4.8)['safety_analysis']
        sized = y['safety_factor_station_sized_by_hrma']
        assert sized['chamber_hoop'] is True
        assert y['safety_factor_is_tautological']['chamber_hoop'] is False, (
            'hedefin ALTINA düşmüş bir sayı hâlâ "totolojik" damgalı')
        assert 'SHARP definition' in y['safety_factor_is_tautological_basis']

    def test_hukum_makinesi_fail_closed_kaldi(self, yapisal):
        """Z4 kazanımı KORUNUR: hüküm hâlâ boyutlandırma haritasını okur."""
        y = _sessiz(yapisal.analyze_structure,
                    dict(REF_YAPISAL, chamber_pressure=3000.0),
                    design_safety_factor=4.8)['safety_analysis']
        # Tüm istasyonlar HRMA tarafından boyutlandırıldı -> onay yok.
        assert all(y['safety_factor_station_sized_by_hrma'].values())
        assert y['status'] not in ('SAFE', 'ACCEPTABLE')


# ===========================================================================
# P5B1-21 — cıvata yerleşimi denetlenir
# ===========================================================================
class TestP5B1_21CivataYerlesimi:

    def test_civatalar_birbirine_girmiyor(self, yapisal):
        """Savcının vakası: Pc = 1000 bar, D = 400 mm (oran 0,884 idi).

        NOT — bu vaka MODÜL üstünden koşulur: /analyze_structural_safety
        ucu Pc > 500 bar'ı artık 422 ile reddediyor (başka bir paketin
        indirdiği tasarım bandı kapısı), yani defterdeki uç vakası ARTIK
        UÇTAN ERİŞİLEMEZ. Kusur modülde yaşıyordu ve orada ölçülür.
        """
        f = _sessiz(yapisal.analyze_structure,
                    dict(REF_YAPISAL, chamber_pressure=1000.0,
                         chamber_diameter=0.4))['fastener_analysis']
        assert f['bolt_spacing'] > f['required_bolt_diameter'], (
            f"aralık {f['bolt_spacing']:.3f} mm, gerekli çap "
            f"{f['required_bolt_diameter']:.3f} mm — cıvatalar giriyor")
        assert f['bolt_pitch_ratio'] > 1.0
        assert f['bolt_layout_interferes'] is False
        # Kalan yetmezlik SUSTURULMAZ: adım hâlâ pratiğin altında.
        assert f['bolt_layout_ok'] is False
        assert f['bolt_count_adjusted'] is True
        assert f['bolt_count_initial'] == 12 and f['num_bolts'] < 12

    def test_nominal_tasarim_dokunulmadi(self, yapisal):
        """Sığan desen DEĞİŞMEZ — nominal gövde bit-aynı kalır."""
        f = _sessiz(yapisal.analyze_structure,
                    dict(REF_YAPISAL))['fastener_analysis']
        assert f['bolt_count_adjusted'] is False
        assert f['num_bolts'] == f['bolt_count_initial']
        assert f['bolt_layout_ok'] is True
        assert f['bolt_pitch_ratio'] == pytest.approx(7.093, abs=0.01)

    def test_yerlesim_kunyesi_ve_uyarisi(self, yapisal):
        f = _sessiz(yapisal.analyze_structure,
                    dict(REF_YAPISAL, chamber_pressure=1000.0,
                         chamber_diameter=0.4))['fastener_analysis']
        assert f['bolt_min_pitch_factor'] == 2.5
        assert 'DECLARED' in f['bolt_layout_basis']
        # Yetmezlik ADIYLA yayımlanır. (Kodlu uyarı i18n sözlüğüne yeni bir
        # anahtar yazmayı gerektiriyor; sözlük bu paketin mülkü değil —
        # borç kodda adıyla kayıtlı, i18n dalgasına bırakıldı.)
        assert f['bolt_layout_status'] == 'BELOW_MINIMUM_PITCH'
        nominal = _sessiz(yapisal.analyze_structure,
                          dict(REF_YAPISAL))['fastener_analysis']
        assert nominal['bolt_layout_status'] == 'OK'

    def test_standart_boy_listesi_bosluklari_kapandi(self, yapisal):
        """M14 / M18 / M22 listeye girdi (defter P5B1-21)."""
        kaynak = (REPO_ROOT / 'hrma' / 'analysis'
                  / 'structural_analysis.py').read_text(encoding='utf-8')
        satir = next(l for l in kaynak.splitlines()
                     if 'standard_sizes = [' in l or
                     ('0.014' in l and '0.018' in l))
        for boy in ('0.014', '0.018', '0.022'):
            assert boy in satir or boy in kaynak, f'M{boy} listede yok'
