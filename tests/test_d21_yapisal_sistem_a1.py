"""ÖH Dalga-21 · yapisal-sistem · aşama 1 — mutasyon kanıtlı bekçiler.

Her sınıf tek bir defter kalemini kilitler. Ölçümler
``docs/scofield/raw/OH/D21/yapisal-sistem/a1/once.json`` (onarım öncesi) ve
``sonra.json`` (onarım sonrası) dosyalarındadır; ters-mutasyon kanıtı
``mutasyon.json``da.

Kapsanan kalemler:
  P5B4-17  tam strok kirişi 4*r*sin(d/2) -> 2*r*sin(d)
  P5B4-18  halka mesafesi 0 iken cıvata momenti beyansız 0,0 N
  P5B4-19  'tasarım yükü değildir' beyanı hep-ya-hiç
  P5B4-07  regresyon künyesi 'a = 0.0000' (9 katsayının 5'i aynı dize)
  P5B4-08  'ox' kipinde mdot_f = 0,0 kg/s ve G_fuel_exit = 0,0
  P5B4-24  karo önbelleği muhasebesi diskteki artığı görmüyor
  P5B1-10  burn_time ölü girdi + uydurma 10 s varsayılanı
  P7B3-23  dürüstlük kapısının kazanılmış sözleşmesi (regresyon kilidi)
  P5B4-06  port_diameter_initial = 0 -> 422 (D20 kapanışı ayakta mı)
  P5B4-09  bilinmeyen fuel_type -> 422 (Z5S kapanışı ayakta mı)
"""
import math
import os

import pytest

from hrma.analysis import gimbal_mount as gm
from hrma.analysis import tile_cache as tc
from hrma.analysis.regression_analysis import RegressionAnalyzer


# ===========================================================================
# P5B4-17 — tam strok kirişi
# ===========================================================================
class TestP5B417TamStrokKirisi:
    """Tam strok kirişi 2*delta merkez açısını gerer, iki kiriş toplamı değil."""

    @pytest.mark.parametrize('aci_deg', [1.0, 6.0, 15.0, 30.0, 45.0])
    def test_tam_strok_kirisi_kapali_formla_bireysel(self, aci_deg):
        r = 1.0
        s = gm.actuator_stroke(r, aci_deg)
        rad = math.radians(aci_deg)
        assert s['stroke_full_travel_chord_m'] == pytest.approx(
            2.0 * r * math.sin(rad), rel=1e-12), (
            'tam strok kirişi 2*r*sin(delta) olmalı; eski kod '
            '4*r*sin(delta/2) yazıyordu (45 derecede +%8,24)')

    @pytest.mark.parametrize('aci_deg', [1.0, 6.0, 15.0, 30.0, 45.0])
    def test_tam_strok_cifti_gercek_stroku_kusatir(self, aci_deg):
        """'_basis' metninin BRACKETS iddiası tam strok çiftinde de tutar."""
        s = gm.actuator_stroke(0.4, aci_deg)
        assert s['stroke_full_travel_chord_m'] <= \
            s['stroke_full_travel_arc_m'] * (1.0 + 1e-12), (
            'kiriş yaydan büyük çıktı — kuşatma iddiası çürük')

    def test_tam_strok_kirisi_tek_yonlunun_iki_kati_DEGIL(self):
        """Ters-mutasyon hedefi: 2*chord dönerse bu test kırmızı olur."""
        s = gm.actuator_stroke(1.0, 45.0)
        assert s['stroke_full_travel_chord_m'] < \
            2.0 * s['stroke_chord_m'] * (1.0 - 1e-6), (
            'tam strok yine tek yönlü kirişin iki katı — iki kiriş uç uca '
            'eklenirse kiriş değil kırık çizgi olur')

    def test_basis_metni_iddiayi_duzeltiyor(self):
        s = gm.actuator_stroke(1.0, 6.0)
        assert '2*r_a*sin(delta)' in s['_basis']


# ===========================================================================
# P5B4-18 — halka mesafesi 0 iken moment yükleri
# ===========================================================================
_GIMBAL_ORTAK = dict(thrust_N=800000.0, gimbal_angle_deg=6.0,
                     actuator_arm_m=1.2, thrust_offset_m=0.01,
                     bolt_circle_diameter_m=1.0, bolt_count=12)


class TestP5B418HalkaMomentiBeyani:
    def test_halka_mesafesi_sifirken_moment_yuku_yayimlanmaz(self):
        r = gm.analyze_gimbal_mount(ring_offset_m=0.0, **_GIMBAL_ORTAK)
        b = r['bolts']
        assert b['moment_induced_max_N'] is None, (
            'ring_offset_m = 0 iken "cıvatalar momentten 0,00 kN yük görüyor" '
            'kazanılmamış bir sayıdır — yayımlanmamalı')
        assert b['max_tension_if_axial_is_tensile_N'] is None
        assert b['max_tension_if_axial_is_compressive_N'] is None
        assert b['moment_induced_loads_status'] == 'not_evaluated'
        # Gerçekten hesaplanan paylar KALIR.
        assert b['axial_share_per_bolt_N'] > 0.0
        assert b['shear_per_bolt_N'] > 0.0

    def test_halka_mesafesi_sifirken_beyan_ve_uyari_var(self):
        r = gm.analyze_gimbal_mount(ring_offset_m=0.0, **_GIMBAL_ORTAK)
        alanlar = [v.get('field') for v in r['validity']]
        assert 'bending_moment_N_m' in alanlar, (
            'halka momenti sıfırken beyan yok — aktüatör kardeşinde var')
        assert any('ring bending moment' in w for w in r['warnings'])

    def test_halka_mesafesi_verilince_sayilar_geri_gelir(self):
        r = gm.analyze_gimbal_mount(ring_offset_m=0.4, **_GIMBAL_ORTAK)
        b = r['bolts']
        assert b['moment_induced_max_N'] == pytest.approx(
            4.0 * r['mount_ring']['bending_moment_N_m'] / (12 * 1.0),
            rel=1e-12)
        assert b['moment_induced_loads_status'] == 'computed'
        alanlar = [v.get('field') for v in r['validity']]
        assert 'bending_moment_N_m' not in alanlar


# ===========================================================================
# P5B4-19 — baskın terimin yokluğu her zaman beyanlı
# ===========================================================================
class TestP5B419BaskinTerimBeyani:
    def test_kaciklik_yokken_her_butcede_beyan_var(self):
        """Bütçe sıfır DEĞİLKEN de beyan çıkmalı (hep-ya-hiç kırıldı)."""
        for ek in ({}, {'bearing_friction_moment_N_m': 0.001},
                   {'duct_torsional_stiffness_N_m_rad': 25000.0}):
            out = gm.actuator_load(thrust_N=800000.0, gimbal_angle_deg=6.0,
                                   actuator_arm_m=1.2, **ek)
            alanlar = [v.get('field') for v in out['validity']]
            assert 'thrust_offset_m' in alanlar, (
                'thrust_offset_m = 0 iken baskın terimin yokluğu beyansız '
                'kaldı (ek girdi: %r)' % (ek,))
            assert any('thrust_offset_m is zero' in w
                       for w in out['warnings'])

    def test_mikro_moment_uyarisiz_yayimlanmiyor(self):
        """800 kN motorda 0,001 N.m'lik bütçe uyarısız geçemez."""
        out = gm.actuator_load(thrust_N=800000.0, gimbal_angle_deg=6.0,
                               actuator_arm_m=1.2,
                               bearing_friction_moment_N_m=0.001)
        assert out['actuator']['force_total_N'] < 1.0
        assert len(out['warnings']) >= 1, (
            'mikroskobik moment bütçesinden çıkan aktüatör kuvveti uyarısız')

    def test_kaciklik_verilince_beyan_dusuyor(self):
        out = gm.actuator_load(thrust_N=800000.0, gimbal_angle_deg=6.0,
                               actuator_arm_m=1.2, thrust_offset_m=0.01)
        alanlar = [v.get('field') for v in out['validity']]
        assert 'thrust_offset_m' not in alanlar
        assert out['warnings'] == []


# ===========================================================================
# P5B4-07 — regresyon künyesi
# ===========================================================================
_REG_GOVDE = dict(burn_time=10.0, mdot_ox=1.0, port_diameter_initial=0.03,
                  grain_length=0.5)


class TestP5B407KunyeKatsayisi:
    def test_hicbir_katsayi_sifir_diye_basilmiyor(self):
        ra = RegressionAnalyzer()
        for yakit in sorted(ra.fuel_properties):
            rd = ra.analyze_regression_vs_time(dict(_REG_GOVDE,
                                                    fuel_type=yakit))
            import json as _json
            baslik = _json.loads(
                ra.create_regression_plot(rd))['layout']['title']['text']
            assert 'a = 0.0000' not in baslik, (
                '%s künyesi katsayıyı 0.0000 diye basıyor (gerçek %r)'
                % (yakit, ra.fuel_properties[yakit]['a']))
            assert 'a = 0.0001' not in baslik

    def test_kunye_katalogdaki_her_katsayiyi_ayirt_ediyor(self):
        """Farklı (a, n) çifti -> farklı alt künye."""
        ra = RegressionAnalyzer()
        import json as _json
        alt = {}
        for yakit in sorted(ra.fuel_properties):
            rd = ra.analyze_regression_vs_time(dict(_REG_GOVDE,
                                                    fuel_type=yakit))
            baslik = _json.loads(
                ra.create_regression_plot(rd))['layout']['title']['text']
            alt[yakit] = baslik.split('<sub>')[-1]
        for x in sorted(ra.fuel_properties):
            for y in sorted(ra.fuel_properties):
                if x >= y:
                    continue
                ax = (ra.fuel_properties[x]['a'], ra.fuel_properties[x]['n'])
                ay = (ra.fuel_properties[y]['a'], ra.fuel_properties[y]['n'])
                if ax == ay:
                    # ÖH D31 / OH-D21-04 — MUAFİYET KURALA ÇEVRİLDİ.
                    # Eski satır ``continue`` idi: birebir aynı çifti taşıyan
                    # iki yakıt sorgusuz muaftı. Bu tam olarak "kusuru
                    # koruyan bekçi" desenidir — bugünkü abs ⟷ htpb ikizliği
                    # (3,68e-05 / 0,555) bu muafiyetin altında GÖRÜNMÜYORDU
                    # ve biri sessizce üçüncü bir ikiz eklese test yine
                    # yeşil kalırdı.
                    # Yeni kural: ikizlik YASAK DEĞİL, KÜNYESİZ ikizlik
                    # yasak. Aynı çifti taşıyan iki yakıttan en az birinin
                    # künyesi ``independent: False`` demeli — yani hangisinin
                    # ödünç aldığı kayıtta yazmalı.
                    from hrma.data.propellant_database import (
                        HYBRID_REGRESSION_SOURCES)
                    eksik = [ad for ad in (x, y)
                             if ad not in HYBRID_REGRESSION_SOURCES]
                    assert not eksik, (
                        '%s ile %s birebir aynı (a, n) çiftini taşıyor ama '
                        '%r künye tablosunda YOK: ödünç mü, bağımsız mı '
                        'izlenemiyor.' % (x, y, eksik))
                    odunc = [ad for ad in (x, y)
                             if not HYBRID_REGRESSION_SOURCES[ad][
                                 'independent']]
                    assert odunc, (
                        '%s ile %s birebir aynı (a, n) çiftini taşıyor ve '
                        'İKİSİNİN de künyesi "independent: True" diyor. En '
                        'az biri ötekinden ödünç almıştır; künyesi bunu '
                        'söylemeli (HYBRID_REGRESSION_SOURCES). Kaynaklı, '
                        'bağımsız ikinci bir ölçüm girildiyse çiftlerin '
                        'birebir aynı kalması beklenmez.' % (x, y))
                    continue
                assert alt[x] != alt[y], (
                    '%s ile %s farklı katsayı taşıyor ama künyeleri aynı: %r'
                    % (x, y, alt[x]))

    def test_kunye_akı_tabanini_yaziyor(self):
        ra = RegressionAnalyzer()
        import json as _json
        rd = ra.analyze_regression_vs_time(dict(_REG_GOVDE,
                                                fuel_type='paraffin'))
        baslik = _json.loads(
            ra.create_regression_plot(rd))['layout']['title']['text']
        assert 'r = a*G^n' in baslik


# ===========================================================================
# P5B4-08 — 'ox' kipinde yakıt debisi
# ===========================================================================
_OX_ORTAK = dict(a=3.68e-05, n=0.555, G_ox=350.0, rho_f=920.0,
                 port_diameter=0.03, grain_length=0.5)


class TestP5B408OxKipiYakitDebisi:
    def test_ox_kipinde_mdot_f_sifir_degil(self):
        reg = RegressionAnalyzer.regression_rate(flux_mode='ox', **_OX_ORTAK)
        beklenen = (_OX_ORTAK['rho_f'] * math.pi
                    * _OX_ORTAK['port_diameter'] * _OX_ORTAK['grain_length']
                    * reg['r_dot'])
        assert reg['mdot_f'] == pytest.approx(beklenen, rel=1e-12), (
            "'ox' kipinde yakıt debisi hâlâ 0,0 — yanan grain yakıt "
            'üretmiyor görünüyor')
        assert reg['mdot_f'] > 0.0

    def test_ox_kipinde_G_fuel_exit_sifir_degil(self):
        reg = RegressionAnalyzer.regression_rate(flux_mode='ox', **_OX_ORTAK)
        A = math.pi * (_OX_ORTAK['port_diameter'] / 2.0) ** 2
        assert reg['G_fuel_exit'] == pytest.approx(reg['mdot_f'] / A,
                                                   rel=1e-12)
        assert reg['G_fuel_exit'] > 0.0

    def test_ox_kipinde_aki_tabani_DEGISMIYOR(self):
        """Tanı sayıları akı tabanına karışmaz: G = G_ox, G_fuel = 0."""
        reg = RegressionAnalyzer.regression_rate(flux_mode='ox', **_OX_ORTAK)
        assert reg['G_fuel'] == 0.0
        assert reg['G_total'] == pytest.approx(_OX_ORTAK['G_ox'], rel=1e-15)
        assert reg['flux_used'] == pytest.approx(_OX_ORTAK['G_ox'], rel=1e-15)
        assert reg['r_dot'] == pytest.approx(
            _OX_ORTAK['a'] * _OX_ORTAK['G_ox'] ** _OX_ORTAK['n'], rel=1e-12)

    def test_geometri_yoksa_sifir_uydurulmaz(self):
        reg = RegressionAnalyzer.regression_rate(
            a=_OX_ORTAK['a'], n=_OX_ORTAK['n'], G_ox=_OX_ORTAK['G_ox'],
            flux_mode='ox')
        assert reg['mdot_f'] is None
        assert reg['G_fuel_exit'] is None
        assert 'not computed' in reg['mdot_f_basis']


# ===========================================================================
# P5B4-24 — karo önbelleği muhasebesi
# ===========================================================================
@pytest.fixture
def karo_kok(tmp_path, monkeypatch):
    kok = tmp_path / 'karolar'
    d = kok / 'bluemarble' / 'default' / '0' / '0'
    d.mkdir(parents=True)
    (d / '0.jpg').write_bytes(b'x' * 26)
    (d / '1.jpg').write_bytes(b'x' * 26)
    (d / 'yarim.tmp').write_bytes(b'y' * 500000)
    monkeypatch.setattr(tc, 'tiles_root', lambda: str(kok))
    return kok


def _disk_bayt(kok):
    t = 0
    for dp, _dn, fs in os.walk(str(kok)):
        for f in fs:
            t += os.path.getsize(os.path.join(dp, f))
    return t


class TestP5B424OnbellekMuhasebesi:
    def test_cache_status_disk_kullanimini_soyluyor(self, karo_kok):
        st = tc.cache_status()
        assert st['bytes'] == _disk_bayt(karo_kok), (
            'cache_status.bytes diskteki artığı görmüyor (ölçüm: 52 <-> '
            '500.052 bayt)')
        assert st['tiles'] == 2
        assert st['stale_bytes'] == 500000 and st['stale_files'] == 1

    def test_cache_clear_artigi_da_siliyor(self, karo_kok):
        cl = tc.cache_clear()
        assert cl['cleared'] == 2
        assert cl['cleared_stale'] == 1
        assert cl['bytes_freed'] == 500052
        assert _disk_bayt(karo_kok) == 0, (
            "cache_clear 'cleared: 2' deyip yarım megabaytlık .tmp'yi "
            'diskte bıraktı')
        assert tc.cache_status()['bytes'] == 0

    def test_cap_artigi_supuruyor(self, karo_kok, monkeypatch):
        """400 MB cap DİSK kullanımının capıdır."""
        monkeypatch.setattr(tc, 'TILE_CACHE_MAX_BYTES', 1000)
        monkeypatch.setattr(tc, '_LRU_LOW_WATER', 0.8)
        tc._enforce_cap(str(karo_kok))
        assert _disk_bayt(karo_kok) <= 1000, (
            'cap aşılmasına rağmen artık süpürülmedi — cap disk kullanımını '
            'sınırlamıyor')
        # Artık önce gider: karolar hâlâ sunulabilir durumda.
        assert tc.cache_status()['tiles'] == 2


# ===========================================================================
# P5B1-10 — burn_time ölü girdi
# ===========================================================================
@pytest.fixture
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


_YAPISAL_GOVDE = {'chamber_pressure': 50, 'chamber_diameter': 0.15,
                  'chamber_length': 0.5, 'throat_diameter': 0.03,
                  'material': 'steel_4130', 'wall_thickness': 0.005}


class TestP5B110BurnTimeOluGirdi:
    def test_tuketilmeyen_alan_adiyla_beyan_ediliyor(self, client):
        r = client.post('/analyze_structural_safety',
                        json=dict(_YAPISAL_GOVDE, burn_time=10.0))
        assert r.status_code == 200
        j = r.get_json()
        assert 'burn_time' in (j.get('inputs_not_consumed') or {}), (
            'burn_time doğrulanıyor ama hesaba girmiyor; yanıt bunu '
            'söylemiyor')
        assert 'design_cycles' in j['inputs_not_consumed']['burn_time'][
            'reason']

    def test_uydurma_10_s_varsayilani_kalkti(self, client):
        r = client.post('/analyze_structural_safety', json=_YAPISAL_GOVDE)
        assert r.status_code == 200
        j = r.get_json()
        assert 'burn_time' not in (j.get('defaults_applied') or []), (
            "burn_time için 'varsayılan uygulandı' deniyor ama uygulanan "
            'değer hiçbir yere gitmiyor')
        assert j['inputs_not_consumed']['burn_time']['submitted'] is False

    def test_kapi_GEVSEMEDI(self, client):
        """ÖK-22: sağlıklı envanter gevşetilemez."""
        for kotu in (0, -5, 1000.0):
            r = client.post('/analyze_structural_safety',
                            json=dict(_YAPISAL_GOVDE, burn_time=kotu))
            assert r.status_code == 422, (
                'burn_time = %r artık reddedilmiyor — kapı gevşetilmiş'
                % (kotu,))

    def test_yanma_suresi_sonucu_degistirmiyor_ve_bu_beyanli(self, client):
        """Ölü girdi olduğu ölçülür VE yanıtta yazılıdır."""
        imza = set()
        for tb in (0.5, 10.0):
            j = client.post('/analyze_structural_safety',
                            json=dict(_YAPISAL_GOVDE, burn_time=tb)
                            ).get_json()
            fa = j['structural_analysis']['fatigue_analysis']
            imza.add((round(fa['fatigue_safety_factor'], 12),
                      fa['design_cycles']))
            assert 'burn_time' in j['inputs_not_consumed']
        assert len(imza) == 1


# ===========================================================================
# P7B3-23 — dürüstlük kapısının kazanılmış sözleşmesi (regresyon kilidi)
# ===========================================================================
class TestP7B323DurustlukKapisi:
    @pytest.mark.parametrize('cidar_mm', [5.0, 25.0, 45.0])
    def test_manset_sayisi_hedefin_geri_okunmasiysa_ADIYLA_yaziliyor(
            self, client, cidar_mm):
        j = client.post('/analyze_structural_safety', json={
            'chamber_pressure': 40, 'chamber_diameter': 0.1,
            'chamber_length': 0.5, 'throat_diameter': 0.02,
            'burn_time': 10, 'material': 'steel_4130',
            'wall_thickness': cidar_mm / 1000.0}).get_json()
        sa = j['structural_analysis']['safety_analysis']
        # Manşet 4,0'da çakılı (lüle + kapak boyutlandırılmış) — bu sayının
        # ölçüm OLMADIĞI yanıtta üç ayrı alanda yazılı olmalı.
        assert sa['minimum_safety_factor_is_tautological'] is True
        assert set(sa['stations_reading_back_target']) == {'end_cap',
                                                           'nozzle'}
        assert sa['status'] == 'NOT_EVALUATED'
        assert j['design_basis']['verdict'] == 'withheld'
        # Kazanılmış sayı AYRI alanda ve cidarla birlikte HAREKET ediyor.
        assert sa['minimum_earned_safety_factor'] > sa[
            'minimum_safety_factor']

    def test_kazanilmis_sf_cidarla_artiyor(self, client):
        deger = []
        for cidar_mm in (5.0, 25.0, 45.0):
            j = client.post('/analyze_structural_safety', json={
                'chamber_pressure': 40, 'chamber_diameter': 0.1,
                'chamber_length': 0.5, 'throat_diameter': 0.02,
                'burn_time': 10, 'material': 'steel_4130',
                'wall_thickness': cidar_mm / 1000.0}).get_json()
            sa = j['structural_analysis']['safety_analysis']
            deger.append(sa['minimum_earned_safety_factor'])
        assert deger[0] < deger[1] < deger[2], (
            'kazanılmış emniyet katsayısı cidarla artmıyor — doğrulama '
            'kanalı kopmuş')

    def test_is_verification_kapsamiyla_birlikte_yayimlaniyor(self, client):
        j = client.post('/analyze_structural_safety', json={
            'chamber_pressure': 40, 'chamber_diameter': 0.1,
            'chamber_length': 0.5, 'throat_diameter': 0.02,
            'burn_time': 10, 'material': 'steel_4130',
            'wall_thickness': 0.025}).get_json()
        db = j['design_basis']
        assert db['is_verification'] is True
        assert db['is_verification_scope'] == 'chamber wall thickness', (
            "'this result is a verification' kapsamsız yayımlanıyor — "
            'P7B3-23 çelişkisi geri gelmiş')


# ===========================================================================
# P5B4-06 / P5B4-09 — önceki dalgaların kapanışı ayakta mı
# ===========================================================================
class TestOncekiKapanislar:
    @pytest.mark.parametrize('deger', [0, -0.03])
    def test_p5b406_port_capi_sifir_veya_negatif_422(self, client, deger):
        r = client.post('/api/regression-analysis', json={'motor_data': {
            'fuel_type': 'htpb', 'burn_time': 10.0, 'mdot_ox': 1.0,
            'port_diameter_initial': deger, 'grain_length': 0.5}})
        assert r.status_code == 422
        j = r.get_json()
        assert any(f['field'] == 'port_diameter_initial'
                   for f in j['invalid_fields'])
        assert 'division by zero' not in r.get_data(as_text=True)

    @pytest.mark.parametrize('ad', ['al2o3', 'pla', 'carbon', 'aluminum',
                                    'peynir'])
    def test_p5b409_bilinmeyen_yakit_sessizce_htpb_olmuyor(self, client, ad):
        r = client.post('/api/regression-analysis', json={'motor_data': {
            'fuel_type': ad, 'burn_time': 10.0, 'mdot_ox': 1.0,
            'port_diameter_initial': 0.03, 'grain_length': 0.5}})
        assert r.status_code == 422
        assert r.get_json()['error'] == 'unresolved_fuel_type'
        assert 'HTPB' not in str(r.get_json().get('regression_data'))
