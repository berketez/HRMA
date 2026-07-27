"""Katı motor tasarım noktası testleri (2026-07-19).

Bulgu: /calculate_solid ucuna hedef itki (thrust) ve yanma süresi (burn_time)
gönderiliyordu ama motor bunları HİÇ okumuyordu — çıktı yalnız geometri
girdilerinden (chamber_diameter / grain_length / core_diameter) üretiliyordu.
2000 N / 5 s istenen bir koşu 12 kN tepe / 2.02 s ile dönüyordu ve hiçbir yerde
hedefin uygulanmadığı söylenmiyordu.

Bu dosya üç şeyi kilitler:
  1. Hedef verildiğinde grain gerçekten hedefe göre boyutlandırılır
     (ortalama itki ve süre toleransı SOLID_DESIGN_POINT['tolerance']).
  2. Boyutlandırılan BATES/end-burner eğrisi makul düzdür (tepe/ortalama).
  3. Hedef fiziksel olarak ulaşılamıyorsa motor SESSİZCE yanlış sayı
     üretmez — açık uyarı kaydı ve design_point.achieved=False döner.
     (v2.6.2 D-track: uyarılar artık sabit metin değil {code, params,
     severity} kaydıdır; dil frontend'e taşındı. Testler metin yerine KOD
     sınar — çeviri değişse bile bekçi ayakta kalır.)

Ayrıca hedef verilmediğinde davranışın birebir eskisi gibi kaldığı
(geometri girdisi tek belirleyici) doğrulanır — korelasyon doğrulama yolu
bu daldan geçtiği için bu regresyon koruması kritiktir.
"""

import numpy as np
import pytest

from hrma.engines.solid_rocket_engine import (
    SOLID_DESIGN_POINT,
    SolidRocketEngine,
)

TOL = SOLID_DESIGN_POINT['tolerance']

# Tasarım noktası boyutlandırmasının BATES zarfı içinde kalan hedefleri.
# (Zarf: F >= 3*pi*r^3*rho*CF*c*  * t^2 — hızlı yanan APCP'de 50 bar'da
#  uzun süre + düşük itki BATES ile fiziksel olarak mümkün DEĞİLDİR.)
BATES_FEASIBLE = [
    (20000.0, 4.0),
    (50000.0, 6.0),
    (10000.0, 5.0),
    (30000.0, 3.0),
]

# BATES zarfının DIŞINDA kalan referans hedef (tek tanım noktası — üç ayrı
# dürüstlük testi bu çifti kullanır).
#
# 2026-07-25 (F024 düzeltmesi sonrası yeniden çapalandı): eskiden 2000 N / 5 s
# idi. O çift, kurucunun MPa tabanlı a = 0.005 varsayılanıyla (r ≈ 19.7 mm/s
# @ 50 bar) zarf dışındaydı. F024 varsayılanı merkezi katalog değerine
# (a = 0.0022334, r ≈ 8.8 mm/s @ 50 bar) çekince aynı hedef ULAŞILABİLİR
# hâle geldi — web 98 mm'den 44 mm'ye indi, yığın küçüldü, yanan yüzey
# 2000 N'e sığdı. Test artık DÜZELTİLMİŞ yanma hızıyla zarf dışında kalan
# çifti kullanır: 2000 N / 10 s → web 88 mm (eski senaryonun web'ine denk).
# Sınanan davranış (uydurma yerine dürüst rapor) aynen korunur.
BATES_INFEASIBLE = (2000.0, 10.0)

# Sigara yanması her hedefi tutturur (yanan yüzey sabit, profil nötr).
END_BURNER_TARGETS = [
    (1000.0, 2.0),
    (2000.0, 5.0),
    (10000.0, 5.0),
    (5000.0, 8.0),
]


def _engine(**overrides):
    base = dict(grain_type='bates', propellant_type='apcp',
                chamber_pressure=50)
    for key in ('grain_type', 'propellant_type', 'chamber_pressure'):
        if key in overrides:
            base[key] = overrides.pop(key)
    return SolidRocketEngine(overrides=overrides, **base)


def _codes(warnings):
    """Uyarı kayıtlarının kod kümesi ({code, params, severity} sözleşmesi)."""
    return {w['code'] for w in (warnings or [])}


def _params(warnings, code):
    """Verilen kodun params sözlüğü (yoksa KeyError ile testi düşürür)."""
    for w in (warnings or []):
        if w['code'] == code:
            return w['params']
    raise KeyError(f'{code} uyarısı üretilmedi: {[w["code"] for w in warnings]}')


def _curve_stats(engine):
    curve = engine.calculate_thrust_curve()
    thrust = np.asarray(curve['thrust'], dtype=float)
    assert thrust.size > 0, 'itki eğrisi boş döndü'
    return {
        'mean': float(thrust.mean()),
        'peak': float(thrust.max()),
        'burn_time': float(curve['time'][-1]),
    }


# ---------------------------------------------------------------------------
# 1) Hedef tutturma
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('thrust, burn_time', BATES_FEASIBLE)
def test_bates_hits_design_point(thrust, burn_time):
    """Zarf içindeki hedef, ortalama itki ve sürede %10 içinde tutturulur."""
    eng = _engine(thrust=thrust, burn_time=burn_time)
    dp = eng.design_point
    assert dp is not None and dp['sizing_applied'] is True
    assert dp['achieved'] is True, dp

    stats = _curve_stats(eng)
    assert abs(stats['mean'] / thrust - 1.0) <= TOL, stats
    assert abs(stats['burn_time'] / burn_time - 1.0) <= TOL, stats
    # design_point raporu eğriyle tutarlı olmalı (rapor-model kopukluğu yok)
    assert dp['achieved_average_thrust_N'] == pytest.approx(
        stats['mean'], rel=1e-6)
    assert dp['achieved_burn_time_s'] == pytest.approx(
        stats['burn_time'], rel=1e-6)


@pytest.mark.parametrize('thrust, burn_time', END_BURNER_TARGETS)
def test_end_burner_hits_design_point(thrust, burn_time):
    """Sigara yanması hedefi çok dar bir bantta tutturur (sabit yüzey)."""
    eng = _engine(grain_type='end_burner', thrust=thrust,
                  burn_time=burn_time)
    assert eng.design_point['achieved'] is True, eng.design_point
    stats = _curve_stats(eng)
    assert abs(stats['mean'] / thrust - 1.0) <= TOL
    assert abs(stats['burn_time'] / burn_time - 1.0) <= TOL


def test_design_point_scales_with_target():
    """Hedef itki 5 kat artınca üretilen motor da ölçeklenmeli.

    Bug'ın imzası tam tersiydi: hedef ne olursa olsun çıktı AYNI kalıyordu.
    """
    small = _engine(thrust=10000.0, burn_time=4.0)
    large = _engine(thrust=50000.0, burn_time=4.0)
    ratio = _curve_stats(large)['mean'] / _curve_stats(small)['mean']
    assert 4.0 < ratio < 6.0, ratio
    assert large.D_chamber > small.D_chamber


def test_design_point_scales_with_burn_time():
    """Süre hedefi 2 katına çıkınca yanma süresi de yaklaşık 2 katına çıkmalı."""
    short = _engine(thrust=30000.0, burn_time=3.0)
    long_ = _engine(thrust=30000.0, burn_time=6.0)
    ratio = (_curve_stats(long_)['burn_time']
             / _curve_stats(short)['burn_time'])
    assert 1.7 < ratio < 2.3, ratio


# ---------------------------------------------------------------------------
# 2) Eğri şekli: nötr aile makul düz olmalı
# ---------------------------------------------------------------------------

PEAK_TO_MEAN_LIMIT = 1.3


@pytest.mark.parametrize('thrust, burn_time', BATES_FEASIBLE)
def test_sized_bates_curve_is_reasonably_flat(thrust, burn_time):
    """Orta-web nötr BATES ailesinde tepe/ortalama < 1.3 olmalı.

    Regresif/progresif davranış grain geometrisinden gelmeli; boyutlandırma
    kazayla tepeli bir motor üretmemeli.
    """
    stats = _curve_stats(_engine(thrust=thrust, burn_time=burn_time))
    assert stats['peak'] / stats['mean'] < PEAK_TO_MEAN_LIMIT, stats


@pytest.mark.parametrize('thrust, burn_time', END_BURNER_TARGETS)
def test_sized_end_burner_is_neutral(thrust, burn_time):
    """Sigara yanmasında yüzey sabit → eğri neredeyse tam düz."""
    stats = _curve_stats(_engine(grain_type='end_burner', thrust=thrust,
                                 burn_time=burn_time))
    assert stats['peak'] / stats['mean'] < 1.05, stats


# ---------------------------------------------------------------------------
# 3) Segment sayısı ve yakıt tutarlılığı
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('n_seg', [1, 2, 3])
def test_segment_count_is_honoured_when_locked(n_seg):
    """Kullanıcı segment sayısı verdiyse boyutlandırma onu KİLİTLER."""
    eng = _engine(thrust=50000.0, burn_time=5.0, grain_count=n_seg)
    assert eng._bates_segment_count() == n_seg
    if eng.design_point.get('sizing_applied'):
        assert eng.design_point['segments'] == n_seg


def test_n_segments_alias_is_read():
    """'n_segments' API adı da segment sayısını belirlemeli (eskiden yok sayılıyordu)."""
    eng = SolidRocketEngine(grain_type='bates', propellant_type='apcp',
                            overrides={'n_segments': 7})
    assert eng._bates_segment_count() == 7
    # form alanı önceliklidir
    eng2 = SolidRocketEngine(grain_type='bates', propellant_type='apcp',
                             overrides={'n_segments': 7, 'grain_count': 3})
    assert eng2._bates_segment_count() == 3


@pytest.mark.parametrize('propellant', ['apcp', 'knsb', 'kndx', 'knsu'])
def test_design_point_consistent_across_propellants(propellant):
    """Farklı yakıtlarda da hedef tutturulmalı (yoğunluk/c* değişse bile)."""
    eng = _engine(propellant_type=propellant, grain_type='end_burner',
                  thrust=5000.0, burn_time=4.0)
    assert eng.design_point['achieved'] is True, (propellant,
                                                  eng.design_point)
    stats = _curve_stats(eng)
    assert abs(stats['mean'] / 5000.0 - 1.0) <= TOL
    assert abs(stats['burn_time'] / 4.0 - 1.0) <= TOL


def test_sized_motor_mass_matches_impulse():
    """Toplam impulse = m_p * Isp * g0 — boyutlandırma kütle korunumunu bozmaz."""
    eng = _engine(thrust=30000.0, burn_time=4.0)
    res = eng.calculate_performance()
    recomputed = (res['propellant_mass'] * res['isp_sea_level']
                  * eng.g0)
    assert recomputed == pytest.approx(res['total_impulse'], rel=1e-6)


# ---------------------------------------------------------------------------
# 4) Dürüstlük: ulaşılamayan hedef sessizce yutulmaz
# ---------------------------------------------------------------------------

def test_infeasible_bates_target_reports_instead_of_pretending():
    """Zarf dışı senaryo: 2000 N / 10 s / APCP / 50 bar / BATES.

    Bu hedef BATES zarfının DIŞINDADIR (50 bar'da APCP 8.8 mm/s geriler →
    10 s için 88 mm web; o webteki en küçük yığının uç yüzeyleri bile
    2000 N'in izin verdiğinden fazla alan üretir). Motor bunu uydurmak
    yerine söylemek zorundadır.

    Hedef çifti BATES_INFEASIBLE'da; oradaki not yeniden çapalama gerekçesini
    (F024 yanma hızı varsayılanı düzeltmesi) açıklar.
    """
    eng = _engine(thrust=BATES_INFEASIBLE[0], burn_time=BATES_INFEASIBLE[1])
    dp = eng.design_point
    assert dp is not None
    assert dp['achieved'] is False
    assert dp['sizing_applied'] is False
    assert eng.design_warnings, 'ulaşılamayan hedef sessizce yutuldu'
    assert 'warn.solid.bates_envelope' in _codes(eng.design_warnings)
    # Geometri girdisine dönülmüş olmalı (uydurma boyut yok)
    assert eng.D_chamber == pytest.approx(0.100)
    assert eng.L_grain == pytest.approx(0.500)
    assert eng.D_core == pytest.approx(0.030)


def test_infeasible_note_is_actionable_and_self_consistent():
    """Uyarıda verilen minimum itki gerçekten ulaşılabilir olmalı.

    Değer artık metinden sökülmez; ``options`` içindeki
    ``warn.solid.opt_raise_thrust`` kaydının parametresinden okunur.
    """
    eng = _engine(thrust=BATES_INFEASIBLE[0], burn_time=BATES_INFEASIBLE[1])
    params = _params(eng.design_warnings, 'warn.solid.bates_envelope')
    options = {o['code']: o['params'] for o in params['options']}
    assert 'warn.solid.opt_lower_chamber_pressure' in options
    assert 'warn.solid.opt_select_end_burner' in options
    f_min = float(options['warn.solid.opt_raise_thrust']
                  ['min_average_thrust_N'])
    better = _engine(thrust=f_min * 1.05, burn_time=BATES_INFEASIBLE[1])
    assert better.design_point['sizing_applied'] is True, better.design_point


def test_star_grain_target_is_not_silently_ignored():
    """Boyutlandırma desteklenmeyen grain tipinde açık uyarı verilir."""
    eng = _engine(grain_type='star', thrust=5000.0, burn_time=3.0)
    assert eng.design_warnings
    assert eng.design_warnings[0]['code'] == 'warn.solid.sizing_unsupported_grain'
    assert eng.design_warnings[0]['params']['grain_type'] == 'star'
    # geometri değişmemiş olmalı
    assert eng.D_chamber == pytest.approx(0.100)


def test_warnings_are_language_free_records():
    """Kullanıcıya görünen uyarılar backend'de DİLSİZ olmalı (D-track).

    Eskiden bu test metinlerin İngilizce + emojisiz olduğunu sınıyordu;
    artık backend hiç metin üretmiyor, yalnız {code, params, severity}
    kaydı üretiyor. Bekçi: şema geçerliliği + kod ad alanı + params
    içinde serbest metin (dil) taşınmaması.
    """
    engines = [
        _engine(thrust=BATES_INFEASIBLE[0],
                burn_time=BATES_INFEASIBLE[1]),           # zarf dışı
        _engine(),                                        # ham geometri
        _engine(grain_type='star', thrust=5000.0, burn_time=3.0),
    ]
    records = []
    for eng in engines:
        res = eng.calculate_performance()
        records.extend(res.get('design_warnings') or [])
    assert records, 'hiç uyarı üretilmedi'
    _assert_valid_warning_records(records)


def _assert_valid_warning_records(records):
    """{code, params, severity} sözleşmesini özyinelemeli doğrular."""
    for rec in records:
        assert isinstance(rec, dict), rec
        assert set(rec) == {'code', 'params', 'severity'}, rec
        assert isinstance(rec['code'], str) and rec['code'].startswith(
            'warn.solid.'), rec
        assert rec['code'].isascii(), rec
        assert rec['severity'] in ('critical', 'warning', 'info'), rec
        assert isinstance(rec['params'], dict), rec
        for key, value in rec['params'].items():
            if key == 'options':
                _assert_valid_warning_records(value)
                continue
            # Sayı, bool, None serbest; string yalnız KİMLİK alanlarında
            # (grain_type, material) — cümle taşımamalı.
            if isinstance(value, str):
                assert ' ' not in value.strip(), (
                    f'{rec["code"]}.{key} serbest metin taşıyor: {value!r}')


# ---------------------------------------------------------------------------
# 5) Sağlık uyarıları: geometri girdisiyle koşulan motorlar
# ---------------------------------------------------------------------------

def test_default_geometry_flags_choked_port_and_erosive_flux():
    """Varsayılan 100/500/30 mm geometrisi 50 bar'da yapılabilir DEĞİL.

    12 kN tepe / 2 s yanma bir hesap hatası değil, port alanının boğaz
    alanından küçük olmasının (A_port/A_t = 0.45) ve G ~ 7000 kg/m2s
    erozif rejiminin sonucudur — kullanıcı bunu görmelidir.
    """
    res = _engine().calculate_performance()
    codes = _codes(res.get('design_warnings'))
    assert 'warn.solid.port_to_throat_low' in codes
    assert 'warn.solid.initial_mass_flux_high' in codes


def test_healthy_sized_motor_has_no_port_warning():
    """İyi boyutlandırılmış motorda port uyarısı çıkmamalı (uyarı gürültü değil)."""
    res = _engine(grain_type='end_burner', thrust=5000.0,
                  burn_time=4.0).calculate_performance()
    assert 'warn.solid.port_to_throat_low' not in _codes(
        res.get('design_warnings'))


# ---------------------------------------------------------------------------
# 6) Regresyon koruması: hedef yoksa davranış birebir eski
# ---------------------------------------------------------------------------

def test_no_target_means_no_sizing():
    """Hedef verilmeyen çağrıda geometri ve eğri dokunulmadan kalır.

    Sayısal çapa 2026-07-25'te YENİDEN ÖLÇÜLDÜ (F024 düzeltmesi). Eski
    değerler (tepe 12060.6 N, süre 2.024960 s) kurucunun MPa tabanlı
    a = 0.005 varsayılanının çıktısıydı; o katsayı bar ile değerlendirildiği
    için yanma hızı 10^0.35 = 2.2387 kat şişiyordu. Varsayılan merkezi
    kataloğa (a = 0.0022334, APCP) çekilince aynı koşu 5008.16 N tepe /
    4.487814 s verdi.

    Teyit (aşağıdaki ikinci blok): aynı motor ``burn_rate_a=0.005`` ile
    kurulduğunda tepe itki ve boğaz alanı SON BASAMAĞINA KADAR eski değere
    döner (12060.600863912117 N; A_t = 0.0015761860795333138 m²). Yanma
    süresi 2.024959740 -> 2.024973188 s, yani 1.3e-5 s (%0.00066) kayar;
    bu F179'un artığıdır (koşu boyunca ``current_temp += 0.001*dt`` diye
    kaynaksız bir sahte ısınma vardı, kaldırıldı). 2.02 s'lik koşuda 0.002 K
    demek; σp = 0.0042 /K ile 8e-6 göreli yanma hızı — ölçülen kaymanın
    büyüklüğüyle uyumlu. Sonuç: eğri yolunda F024 dışında regresyon yok.
    """
    eng = _engine()
    assert eng.design_point is None
    assert eng.D_chamber == pytest.approx(0.100)
    assert eng.L_grain == pytest.approx(0.500)
    assert eng.D_core == pytest.approx(0.030)
    stats = _curve_stats(eng)
    # 2026-07-25 ölçümü (F024 sonrası katalog yanma hızı) — sabit referans
    assert stats['peak'] == pytest.approx(5008.16, rel=1e-3)
    # v2.5.2 (Codex bulgusu): yanma suresi ve impuls son integrasyon adimini
    # atliyordu — ornekler t ilerlemeden once saklaniyor, son web artisindan
    # sonraki araligi trapz disarida birakiyordu. Terminal tukenis ornegi
    # eklendikten sonra sure yarim adim uzadi. Bu kapanis davranisi hâlâ
    # yerinde; asagidaki deger onun F024 sonrasi karsiligidir.
    assert stats['burn_time'] == pytest.approx(4.487814, abs=1e-5)

    # F024'un tek suclu oldugunun bekcisi: eski (hatali) katsayiyla eski
    # sayilar geri gelmeli (docstring'deki olcume bak).
    legacy = SolidRocketEngine(grain_type='bates', propellant_type='apcp',
                               chamber_pressure=50, burn_rate_a=0.005)
    legacy_curve = legacy.calculate_thrust_curve()
    legacy_peak = float(np.asarray(legacy_curve['thrust']).max())
    assert legacy_peak == pytest.approx(12060.600863912117, rel=1e-12)
    assert float(legacy_curve['throat_area']) == pytest.approx(
        0.0015761860795333138, rel=1e-12)
    # F179 artigi: sure 1.3e-5 s kayar, bu yuzden tolerans 1e-4 s
    assert float(legacy_curve['time'][-1]) == pytest.approx(
        2.024960, abs=1e-4)


def test_thrust_coefficient_matches_curve():
    """_thrust_coefficient itki eğrisiyle AYNI CF'i vermeli (tek tanım noktası)."""
    eng = _engine()
    curve = eng.calculate_thrust_curve()
    A_t = curve['throat_area']
    p0 = float(curve['pressure'][0])
    f0 = float(curve['thrust'][0])
    assert eng._thrust_coefficient(p0) == pytest.approx(
        f0 / (p0 * 1e5 * A_t), rel=1e-9)


def test_endpoint_reports_design_point():
    """/calculate_solid çıktısında tasarım noktası raporu yer almalı.

    ``burn_rate_a`` 2026-07-25'te AÇIKÇA gönderilir. Eskiden gönderilmiyordu
    ve test app.py'nin ``data.get('burn_rate_a', 0.005)`` yedeğine yaslanmış
    oluyordu — yani F024'te düzeltilen MPa tabanlı katsayının kendisine.
    Bekçi, uç noktanın varsayılanına değil motorun davranışına bakmalı;
    o varsayılan düzeltilince test sessizce kırılmasın diye katsayı istekte
    veriliyor.
    """
    from hrma.app import app
    from hrma.engines.solid_rocket_engine import (
        DEFAULT_BURN_RATE_A, DEFAULT_BURN_RATE_N,
    )

    base = {'chamber_pressure': 50, 'propellant_type': 'apcp',
            'burn_rate_a': DEFAULT_BURN_RATE_A,
            'burn_rate_n': DEFAULT_BURN_RATE_N}
    client = app.test_client()
    resp = client.post('/calculate_solid', json=dict(
        base, thrust=BATES_INFEASIBLE[0], burn_time=BATES_INFEASIBLE[1],
        grain_type='bates'))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['design_point']['achieved'] is False
    assert data['design_warnings']

    resp2 = client.post('/calculate_solid', json=dict(
        base, thrust=2000, burn_time=5, grain_type='end_burner'))
    data2 = resp2.get_json()
    assert data2['design_point']['achieved'] is True
    assert data2['average_thrust'] == pytest.approx(2000.0, rel=TOL)
    assert data2['burn_time'] == pytest.approx(5.0, rel=TOL)
