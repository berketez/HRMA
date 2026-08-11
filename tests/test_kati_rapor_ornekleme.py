"""Katı motor RAPOR katmanı bekçileri (v2.6.27 · B2).

Bu dosya katı motorun ÇÖZÜMÜNÜ değil, çözümün kullanıcıya nasıl ANLATILDIĞINI
sınar. Dört kusur sınıfı kapatıldı; her biri aşağıda ölçülen kanıtıyla
kilitlenir.

1. **Biçim sınıflandırması tepeyi görmüyordu** (``_classify_thrust_curve``).
   Eski kural yalnız ilk 10 ve son 10 örneğin ortalamasını karşılaştırıyordu.
   ÖLÇÜLDÜ (APCP, D_kamara = 100 mm, D_çekirdek = 30 mm, L = 500 mm, 40 bar):

   =========== ============= ==========================================
   grain       eski etiket   eğrinin gerçeği
   =========== ============= ==========================================
   star        'Regressive'  3252 N -> 5812 N (x1,79), tepe yanmanın %70'inde
   wagon_wheel 'Regressive'  4161 N -> 10458 N (x2,51), tepe %19'da
   finocyl     'Progressive' 2147 N -> 4423 N -> 2690 N, tepe %41'de
   =========== ============= ==========================================

   Üçünde de bildirilen biçim eğrinin biçimi DEĞİLDİ ve tepeli eğriler için
   bir sınıf hiç yoktu.

2. **``thrust_stability`` alt sınırsızdı.** ``100 - CV*100`` tanımı CV > 1
   olunca negatife geçiyordu; ÖLÇÜLDÜ: slotted grainde **-1,44 %**
   (wagon_wheel 5,45; star 28,12). Kullanıcı yüzde birimli bir panelde
   negatif "kararlılık" görüyordu.

3. **Yayımlanan itki eğrisinin tavanı yoktu.** Çözücü adımı dt = 0,01 s
   sabit olduğu için dizi saniyede 100 nokta taşıyor ve yanma süresiyle
   sınırsız büyüyordu. ÖLÇÜLDÜ (JSON gövdesi): bates L = 500 mm -> 487
   nokta / 47,2 KB (yanıtın %37'si); **end_burner L = 500 mm -> 6157 nokta /
   519,4 KB (yanıtın %87'si)**.

4. **Yapısal emniyet katsayısı totolojikti.** Kullanıcı cidar vermezse
   ``_case_design`` cidarı ``t = P*r/(sigma_y/SF)`` ile boyutlandırıyor,
   ``_calculate_structural_analysis`` ise ``SF = sigma_y/(P*r/t)`` diyordu:
   cebirsel olarak SF_hedef'in kendisi. ÖLÇÜLDÜ: Pc = 40 / 80 / 150 bar'da
   SF = 3,000000 (altı basamak aynı) iken cidar 2,400 / 4,800 / 9,000 mm.
   Aynı totoloji kap onayına da geçiyordu: ``vessel_status = 'PASS'``.

Bu dosyadaki ``monkeypatch`` sahteleri test altyapısıdır (kullanıcıya
gösterilen veri değildir).
"""

import numpy as np
import pytest

import hrma.engines.solid_rocket_engine as solid_mod
from hrma.engines.solid_rocket_engine import SolidRocketEngine

#: Bütün ölçümlerin alındığı referans geometri (dosya başındaki tablo).
TABAN = dict(propellant_type='apcp', chamber_diameter=100.0,
             grain_length=500.0, core_diameter=30.0, chamber_pressure=40)

#: Deponun desteklediği grain tipleri (motorun kendi hata metninden).
GRAIN_TIPLERI = ('bates', 'star', 'wagon_wheel', 'finocyl', 'slotted',
                 'end_burner')


def motor(grain_type='bates', **kw):
    params = dict(TABAN)
    params.update(kw)
    return SolidRocketEngine(grain_type=grain_type, **params)


@pytest.fixture(scope='module')
def egriler():
    """Her grain tipi için (motor, tam çözünürlüklü eğri) — bir kez çözülür."""
    out = {}
    for gt in GRAIN_TIPLERI:
        m = motor(gt)
        out[gt] = (m, m.calculate_thrust_curve())
    return out


# ---------------------------------------------------------------------------
# 1) Biçim sınıflandırması
# ---------------------------------------------------------------------------
def test_tepeli_egri_artik_kendi_sinifini_aliyor(egriler):
    """star / wagon_wheel / finocyl: önce tırmanan, sonra düşen eğriler.

    Eski kural bunlara 'Regressive' / 'Progressive' diyordu. Yeni sınıf
    tepenin VARLIĞINI söyler.
    """
    for gt in ('star', 'wagon_wheel', 'finocyl'):
        m, c = egriler[gt]
        rapor = m._thrust_shape_report(c['thrust'], c['time'])
        assert rapor['shape'] == \
            solid_mod.SOLID_THRUST_SHAPE_PROGRESSIVE_REGRESSIVE, (
            f'{gt}: {rapor["shape"]}')
        # Sınıf, ölçülerle DOĞRULANABİLİR olmalı: tepe açılış platosunun
        # belirgin üstünde ve pencerenin içinde.
        assert rapor['peak_over_mean'] > 1.0
        assert 0.0 < rapor['peak_time_fraction'] <= \
            solid_mod.SOLID_THRUST_SHAPE_PEAK_INTERIOR_MAX


def test_tepesiz_azalan_egriler_regresif_kaliyor(egriler):
    """bates ve slotted tepe YAPMIYOR: sınıf regresif olmalı.

    Yeni sınıfın her eğriyi 'tepeli' göstermediğinin bekçisi. (slotted'ın
    tepesi açılış platosunun yalnız %8,7 üstünde — nötr bandın içinde.)
    """
    for gt in ('bates', 'slotted'):
        m, c = egriler[gt]
        rapor = m._thrust_shape_report(c['thrust'], c['time'])
        assert rapor['shape'] == solid_mod.SOLID_THRUST_SHAPE_REGRESSIVE, (
            f'{gt}: {rapor["shape"]}')
        assert rapor['end_plateau_N'] < rapor['start_plateau_N']


def test_uc_yakan_grain_notr(egriler):
    """end_burner sabit alanla yanar: nötr sınıfın canlı olduğunun kanıtı."""
    m, c = egriler['end_burner']
    rapor = m._thrust_shape_report(c['thrust'], c['time'])
    assert rapor['shape'] == solid_mod.SOLID_THRUST_SHAPE_NEUTRAL
    assert rapor['peak_over_mean'] == pytest.approx(1.0, abs=1e-6)
    assert rapor['min_over_mean'] == pytest.approx(1.0, abs=1e-6)


def test_eski_kural_bu_sentetik_egriyi_kaciriyordu():
    """Doğrudan kusurun kendisi: uçları eşit, ortası tepeli eğri.

    Eski kural (ilk 10 ortalaması vs son 10 ortalaması) bu eğriye 'Neutral'
    derdi; oysa itki ortada üç katına çıkıyor.
    """
    t = np.linspace(0.0, 10.0, 1001)
    F = 1000.0 + 2000.0 * np.sin(np.pi * t / 10.0)   # 1000 -> 3000 -> 1000
    m = motor()
    eski = ('Progressive' if np.mean(F[-10:]) > np.mean(F[:10]) * 1.1
            else 'Regressive' if np.mean(F[-10:]) < np.mean(F[:10]) * 0.9
            else 'Neutral')
    assert eski == 'Neutral', 'kusurun yeniden üretimi'
    rapor = m._thrust_shape_report(F, t)
    assert rapor['shape'] == \
        solid_mod.SOLID_THRUST_SHAPE_PROGRESSIVE_REGRESSIVE
    assert rapor['peak_time_fraction'] == pytest.approx(0.5, abs=0.02)


def test_sonuna_kadar_tirmanan_egri_progresif():
    """Tepe pencerenin SONUNDAYSA eğri hâlâ tırmanıyordur — 'Progressive'."""
    t = np.linspace(0.0, 10.0, 1001)
    F = 1000.0 + 200.0 * t                      # 1000 -> 3000, tepe sonda
    rapor = motor()._thrust_shape_report(F, t)
    assert rapor['shape'] == solid_mod.SOLID_THRUST_SHAPE_PROGRESSIVE
    assert rapor['peak_time_fraction'] > \
        solid_mod.SOLID_THRUST_SHAPE_PEAK_INTERIOR_MAX


def test_sinif_ornek_araligindan_bagimsiz():
    """Zaman ağırlıklı tanım: aynı eğri, iki farklı örnek sıklığı, aynı sınıf.

    Eski kural 'ilk 10 / son 10 ÖRNEK' diyordu, yani kararı çözücü adımına
    bağlıyordu.
    """
    m = motor()
    for n in (201, 1001, 5001):
        t = np.linspace(0.0, 10.0, n)
        F = 1000.0 + 2000.0 * np.sin(np.pi * t / 10.0)
        assert m._classify_thrust_curve(F, t) == \
            solid_mod.SOLID_THRUST_SHAPE_PROGRESSIVE_REGRESSIVE, n


def test_karar_verilemeyen_egride_sinif_uydurulmuyor():
    """Örnek yetmiyorsa sınıf UYDURULMAZ (varsayılan 'Neutral' basılmaz)."""
    m = motor()
    for veri in ([], [0.0], [0.0, 0.0, 0.0], [5.0, 5.0]):
        rapor = m._thrust_shape_report(np.asarray(veri, dtype=float))
        assert rapor['shape'] == solid_mod.SOLID_THRUST_SHAPE_UNDETERMINED
        assert rapor['peak_over_mean'] is None
        assert rapor['window_mean_thrust_N'] is None


def test_belirlenemeyen_sinif_arayuze_ingilizce_sozcuk_gondermiyor():
    """'Undetermined' kullanıcıya BASILMAZ; alan None döner.

    solid.html'in dürüst biçimlendiricisi (fmtTextField) boş alanda
    yerelleştirilmiş 'not classified' yazıp gerekçeyi ``<key>_basis``ten
    okur. Sınıfın kendisi makine okuyucusu için blokta kalır.
    """
    m = motor()
    c = m.calculate_thrust_curve()
    bozuk = dict(c)
    # Hiç pozitif itki yok -> biçim kararlaştırılamaz (dizi boyları korunur).
    bozuk['thrust'] = np.zeros_like(np.asarray(c['thrust'], dtype=float))
    blok = m._calculate_detailed_analysis(bozuk)['thrust_profile_analysis']
    assert blok['thrust_curve_type'] is None
    assert blok['thrust_curve_shape']['shape'] == \
        solid_mod.SOLID_THRUST_SHAPE_UNDETERMINED
    # missingReason'ın okuduğu ad: '<key>_basis'
    assert blok['thrust_curve_type_basis']
    assert 'no class is invented' in blok['thrust_curve_type_basis']


def test_rapor_sinifi_gerekcesiyle_yayimliyor(egriler):
    """Etiketin yanında onu doğrulayan ÖLÇÜLER de yayımlanmalı."""
    m, c = egriler['star']
    blok = m._calculate_detailed_analysis(c)['thrust_profile_analysis']
    shape = blok['thrust_curve_shape']
    assert blok['thrust_curve_type'] == shape['shape']
    for alan in ('peak_over_mean', 'min_over_mean', 'peak_time_fraction',
                 'start_plateau_N', 'end_plateau_N', 'window_mean_thrust_N',
                 'window_duration_s', 'window_samples'):
        assert shape[alan] is not None, alan
    assert '5%' in shape['criterion'] and 'time-weighted' in shape['criterion']
    assert shape['time_basis'] == 'solver_time_samples'


# ---------------------------------------------------------------------------
# 2) İtki kararlılığı
# ---------------------------------------------------------------------------
def test_kararlilik_hicbir_grainde_negatif_degil(egriler):
    """Kusurun kendisi: slotted grainde ölçülen -1,44 % bir daha çıkmamalı."""
    for gt, (m, c) in egriler.items():
        blok = m._calculate_detailed_analysis(c)['thrust_profile_analysis']
        assert blok['thrust_stability'] >= 0.0, (
            f'{gt}: thrust_stability = {blok["thrust_stability"]}')
        assert blok['thrust_stability'] <= 100.0, gt


def test_kirpilan_deger_bilgi_kaybetmiyor(egriler):
    """slotted'da CV %100'ü aşıyor: kırpma OLDUĞU ve GERÇEK genlik yazılmalı."""
    m, c = egriler['slotted']
    blok = m._calculate_detailed_analysis(c)['thrust_profile_analysis']
    assert blok['thrust_stability'] == 0.0
    assert blok['thrust_stability_was_clamped'] is True
    # Kırpılmamış büyüklük adıyla durur ve gerçekten 100'ün üstündedir.
    assert blok['thrust_variation_coefficient_percent'] > 100.0
    # Beyan, 0'ın ne demek olduğunu söylemeli.
    assert 'clamped' in blok['thrust_stability_basis']
    assert 'thrust_variation_coefficient_percent' in \
        blok['thrust_stability_basis']


def test_kirpma_gerekmeyen_grainde_tanim_degismiyor(egriler):
    """CV < %100 iken alan eski tanımıyla birebir aynı kalır (regresyon)."""
    m, c = egriler['bates']
    blok = m._calculate_detailed_analysis(c)['thrust_profile_analysis']
    T = np.asarray(c['thrust'], dtype=float)
    beklenen = 100.0 - float(np.std(T) / np.mean(T) * 100.0)
    assert blok['thrust_stability'] == pytest.approx(beklenen, rel=1e-12)
    assert blok['thrust_stability_was_clamped'] is False


def test_ortalama_itki_sifirsa_sayi_uretilmiyor():
    """CV tanımsızsa (ortalama <= 0) alan None olur — 100 ya da 0 basılmaz."""
    m = motor()
    c = m.calculate_thrust_curve()
    bozuk = dict(c)
    bozuk['thrust'] = np.zeros_like(np.asarray(c['thrust'], dtype=float))
    blok = m._calculate_detailed_analysis(bozuk)['thrust_profile_analysis']
    assert blok['thrust_stability'] is None
    assert blok['thrust_variation_coefficient_percent'] is None


# ---------------------------------------------------------------------------
# 3) Yayımlanan eğrinin seyreltilmesi
# ---------------------------------------------------------------------------
def test_uzun_yanmada_yayimlanan_dizi_tavani_asmiyor():
    """ÖLÇÜLEN kusur: end_burner 61,6 s'de 6157 nokta / 519 KB yayımlıyordu."""
    m = motor('end_burner')
    sonuc = m.calculate_performance()
    ornekleme = sonuc['thrust_curve']['sampling']
    assert ornekleme['points_computed'] > 5000, (
        'senaryo geçerliliğini yitirdi: çözücü artık bu kadar nokta üretmiyor')
    assert ornekleme['points_published'] <= \
        solid_mod.SOLID_THRUST_CURVE_MAX_POINTS + 2
    assert ornekleme['decimated'] is True
    assert len(sonuc['thrust_curve']['time']) == ornekleme['points_published']


def test_cozucu_adimi_degismedi():
    """Seyreltme YAYIN katmanındadır: integrasyon çözünürlüğü korunur."""
    m = motor('end_burner')
    c = m.calculate_thrust_curve()
    assert c['time_step_s'] == pytest.approx(0.01)
    assert len(c['time']) > 5000, 'çözücü tam çözünürlükte kalmalı'
    sonuc = m.calculate_performance()
    assert sonuc['thrust_curve']['sampling']['solver_time_step_s'] == \
        pytest.approx(0.01)


def test_seyreltme_tepeyi_ve_uclari_koruyor():
    """Tepe itki, tepe basınç ve iki uç ÖRNEK BİREBİR yayımlanmalı."""
    for gt in ('end_burner', 'wagon_wheel', 'star'):
        m = motor(gt)
        tam = m.calculate_thrust_curve()
        yayin = m.calculate_performance()['thrust_curve']
        assert max(yayin['thrust']) == float(np.max(tam['thrust'])), gt
        assert max(yayin['pressure']) == float(np.max(tam['pressure'])), gt
        assert yayin['time'][0] == float(tam['time'][0]), gt
        assert yayin['time'][-1] == float(tam['time'][-1]), gt
        assert yayin['thrust'][-1] == float(tam['thrust'][-1]), gt


def test_yayimlanan_diziler_hizali():
    """Beş dizi AYNI indeks kümesinden gelir; hizasız eğri okunamaz."""
    yayin = motor('end_burner').calculate_performance()['thrust_curve']
    n = len(yayin['time'])
    for ad in ('thrust', 'pressure', 'burn_area', 'mass_flow'):
        assert len(yayin[ad]) == n, ad
    assert all(b >= a for a, b in zip(yayin['time'], yayin['time'][1:])), \
        'zaman artan olmalı'


def test_turetilmis_buyuklukler_tam_cozumden_geliyor():
    """Toplam impuls ve ortalama itki seyreltmeden ETKİLENMEZ.

    Bekçinin ölçüsü: değerler tam çözünürlüklü eğrinin trapez integraliyle
    birebir aynı olmalı (yayımlanan diziden hesaplansalardı sapacaklardı).
    """
    for gt in ('end_burner', 'bates'):
        m = motor(gt)
        tam = m.calculate_thrust_curve()
        sonuc = m.calculate_performance()
        beklenen = float(np.trapz(tam['thrust'], tam['time']))
        assert sonuc['total_impulse'] == pytest.approx(beklenen, rel=1e-12), gt
        assert sonuc['average_thrust'] == pytest.approx(
            beklenen / float(tam['time'][-1]), rel=1e-12), gt


def test_kisa_egri_hic_seyreltilmiyor():
    """Tavanın altındaki eğri BİREBİR yayımlanır (gereksiz kayıp yok)."""
    # İnce web (D_çekirdek = 70 mm) -> t_b = 1,96 s -> 198 örnek.
    m = motor('bates', core_diameter=70.0)
    tam = m.calculate_thrust_curve()
    n = len(tam['time'])
    assert n <= solid_mod.SOLID_THRUST_CURVE_MAX_POINTS, (
        f'senaryo geçersiz: {n} nokta zaten tavanın üstünde')
    yayin = m.calculate_performance()['thrust_curve']
    assert yayin['sampling']['decimated'] is False
    assert yayin['thrust'] == [float(v) for v in tam['thrust']]


def test_sabit_adimin_kacirdigi_tepe_korunuyor():
    """Doğrudan kusur: tek örneklik iğne tepe, düz stride ile kaybolur."""
    n = 1000
    F = np.full(n, 100.0)
    F[501] = 5000.0                     # tek stride (n // 400 = 2) atlar
    stride = max(1, n // solid_mod.SOLID_THRUST_CURVE_MAX_POINTS)
    assert 501 % stride != 0, 'senaryo kurulumu: düz stride bu indeksi atlar'
    idx = SolidRocketEngine._decimate_curve_indices(F)
    assert 501 in set(idx.tolist())
    assert float(np.max(F[idx])) == 5000.0


def test_kritik_anlar_zorunlu_tasiniyor():
    """Ayrılma / boğulma kaybı / tükeniş örnekleri seyreltmede düşemez."""
    n = 2000
    F = np.linspace(1000.0, 900.0, n)         # düz eğri: hiçbir kova onları seçmez
    P = np.linspace(40.0, 39.0, n)
    kritik = [317, 1234, 1999]
    idx = set(SolidRocketEngine._decimate_curve_indices(
        F, P, keep=kritik).tolist())
    for i in kritik:
        assert i in idx, i
    # Aralık dışı / None girdiler sessizce atılır, çökme olmaz.
    idx2 = SolidRocketEngine._decimate_curve_indices(
        F, P, keep=[None, -5, 10 ** 6])
    assert idx2.size > 0


def test_ayrilmanin_ilk_ani_yayimlanan_egride_var():
    """Uyarı 'şu anda ayrıldı' diyorsa eğri o anı GÖSTEREBİLMELİ."""
    m = motor('wagon_wheel')
    tam = m.calculate_thrust_curve()
    t_sep = tam.get('separated_from_t')
    assert t_sep is not None, 'senaryo geçersiz: bu geometride ayrılma yok'
    yayin = m.calculate_performance()['thrust_curve']
    assert any(abs(t - float(t_sep)) < 1e-9 for t in yayin['time'])


def test_ornekleme_blogu_kendini_beyan_ediyor():
    yayin = motor('end_burner').calculate_performance()['thrust_curve']
    o = yayin['sampling']
    assert o['points_published'] < o['points_computed']
    assert o['max_points'] == solid_mod.SOLID_THRUST_CURVE_MAX_POINTS
    assert 'solver time step is UNCHANGED' in o['basis']
    assert 'FULL-resolution' in o['basis']


# ---------------------------------------------------------------------------
# 4) Yapısal totoloji ve kazanılmamış kap onayı
# ---------------------------------------------------------------------------
def test_cidar_verilmeyince_emniyet_katsayisi_girdinin_ekosu():
    """KUSURUN KANITI: üç basınçta cidar değişiyor, SF birebir sabit."""
    goruldu = {}
    for pc in (40, 80, 150):
        m = motor(chamber_pressure=pc)
        ca = m._calculate_structural_analysis()['case_analysis']
        goruldu[pc] = (ca['wall_thickness_mm'], ca['safety_factor'])
        assert ca['design_mode'] == 'size'
        assert ca['safety_factor_is_tautological'] is True
        assert ca['wall_thickness_source'] == 'sized_by_hrma'
        # SF, tasarım hedefinin ta kendisi:
        assert ca['safety_factor'] == pytest.approx(
            ca['design_safety_factor'], rel=1e-9)
    kalinliklar = {v[0] for v in goruldu.values()}
    katsayilar = {round(v[1], 9) for v in goruldu.values()}
    assert len(kalinliklar) == 3, 'senaryo geçersiz: cidar değişmiyor'
    assert len(katsayilar) == 1, (
        'totoloji ortadan kalktıysa bu bekçi güncellenmeli: '
        f'{goruldu}')


def test_boyutlandirma_modunda_hukum_dogrulama_diye_sunulmuyor():
    ca = motor()._calculate_structural_analysis()['case_analysis']
    metin = ca['safety_factor_basis']
    assert 'NOT a verification' in metin
    assert 'read back' in metin
    assert 'case_thickness' in metin


def test_kullanici_cidari_verince_hukum_gercekten_kazaniliyor():
    """Doğrulama yolu canlı: SF artık hedefin ekosu DEĞİL."""
    m = motor(overrides={'case_thickness': 6.0})
    ca = m._calculate_structural_analysis()['case_analysis']
    assert ca['design_mode'] == 'verify'
    assert ca['safety_factor_is_tautological'] is False
    assert ca['wall_thickness_source'] == 'user_supplied'
    assert ca['wall_thickness_mm'] == pytest.approx(6.0)
    assert ca['safety_factor'] != pytest.approx(ca['design_safety_factor'])
    assert 'verified against' in ca['safety_factor_basis']


def test_kazanilmamis_kap_onayi_geri_cekiliyor():
    """ÖLÇÜLEN kusur: cidar verilmeden dört basınçta da vessel_status='PASS'."""
    for pc in (20, 40, 70, 100):
        m = motor(chamber_pressure=pc)
        ps = m._calculate_safety_analysis(
            m.calculate_thrust_curve())['pressure_safety']
        assert ps['vessel_status'] == 'NOT_EVALUATED', pc
        assert ps['vessel_status_is_tautological'] is True
        assert ps['wall_thickness_source'] == 'sized_by_hrma'
        assert 'not an independent verification' in ps['vessel_status_basis']
        # Sayılar SİLİNMEZ — gerçekten hesaplandılar.
        assert ps['burst_pressure_bar'] > 0
        assert ps['case_wall_thickness_mm'] > 0


def test_kullanici_cidariyla_kap_hukmu_veriliyor():
    m = motor(overrides={'case_thickness': 6.0})
    ps = m._calculate_safety_analysis(
        m.calculate_thrust_curve())['pressure_safety']
    assert ps['vessel_status'] not in (None, 'NOT_EVALUATED')
    assert ps['vessel_status_is_tautological'] is False
    assert ps['wall_thickness_source'] == 'user_supplied'
    assert 'evaluation of that wall' in ps['vessel_status_basis']


def test_uyari_susturulmuyor_yalniz_onay_geri_cekiliyor(monkeypatch):
    """Kural ONAYA uygulanır. 'MARGINAL'/'FAIL' bir tehlike bildirimidir.

    Boyutlandırma yolu doğası gereği hep 'PASS' ürettiği için uyarı senaryosu
    kap çözücüsü sahtelenerek kurulur (pytest sahtesi — test altyapısı).
    """
    from hrma.analysis import pressure_vessel as pv_mod

    class _SahteKap:
        def analyze(self, **kw):
            return {'actual_burst_pressure_bar': 55.0, 'status': 'MARGINAL',
                    'warnings': ['sahte uyarı']}

    monkeypatch.setattr(pv_mod, 'PressureVesselAnalyzer', _SahteKap)
    m = motor()
    ps = m._calculate_safety_analysis(
        m.calculate_thrust_curve())['pressure_safety']
    assert ps['vessel_status'] == 'MARGINAL', (
        'kazanılmamış ONAY geri çekilir, UYARI çekilmez')
    assert ps['vessel_status_is_tautological'] is True


def test_uc_katmani_ile_ayni_cevap_veriliyor():
    """Motor kapısı ile A3'ün uç kapısı ÇELİŞMEZ (iki kez uygulanınca da).

    ``/calculate_solid`` yanıtı motorun beyanını taşımalı; iki kapının
    üst üste çalışması sonucu değiştirmemeli.
    """
    from hrma.app import app
    from tests.support import shake

    app.config['TESTING'] = True
    with app.test_client() as c:
        resp = c.post('/calculate_solid', headers=shake.HEADERS, json={
            'chamber_pressure': 40, 'propellant_type': 'apcp',
            'chamber_diameter': 100, 'grain_length': 500,
            'core_diameter': 30})
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    ps = resp.get_json()['safety_analysis']['pressure_safety']
    assert ps['vessel_status'] == 'NOT_EVALUATED'
    assert ps['vessel_status_is_tautological'] is True
    assert ps['wall_thickness_source'] == 'sized_by_hrma'
