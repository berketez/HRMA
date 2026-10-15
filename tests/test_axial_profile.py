"""
Eksenel ısı profili testleri (Dalga 2, 2026-07-14).

Kapsam:
  1. HeatTransferAnalyzer.analyze_axial_profile fizik kuralları:
     - tüm diziler eşit uzunlukta ve n_stations'a uyar,
     - alan oranı A/A_t >= 1, minimumu (=1) tam boğaz istasyonunda,
     - Mach monotonik artar; boğazda 1, öncesi subsonik, sonrası süpersonik,
     - her istasyon izantropik alan-Mach bağıntısını sağlar (rezidü kontrolü),
     - q ve h_g maksimumu boğazda (Bartz (A_t/A)^0.9 alan terimi),
     - kurtarma sıcaklığı Tc'yi aşmaz; denge cidar T fiziksel bantta,
     - rejeneratif soğutma doğal soğutmadan daha soğuk cidar verir.
  2. POST /api/analysis/wall-profile endpoint'i (test_client — port YOK):
     200 + şema + dizi uzunlukları + boğaz fiziği + varsayılanlarla çalışma.
"""

import warnings

import numpy as np
import pytest

warnings.filterwarnings('ignore')

from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer

# Gerçekçi hibrit motor girdisi (N2O/HTPB sınıfı): 30 bar, 3200 K,
# d_t=30 mm, d_e=90 mm (eps=9). Testler boyunca TEK ortak girdi.
MOTOR_DATA = {
    'chamber_pressure': 30.0,       # bar
    'chamber_temperature': 3200.0,  # K
    'gamma': 1.22,
    'molecular_weight': 26.0,       # g/mol
    'mdot_total': 2.0,              # kg/s
    'chamber_diameter': 0.10,       # m
    'chamber_length': 0.40,         # m
    'burn_time': 8.0,               # s
    'throat_diameter': 0.03,        # m
    'exit_diameter': 0.09,          # m
}

N_STATIONS = 40

PROFILE_ARRAY_KEYS = ('x_mm', 'area_ratio', 'mach', 'h_g', 'q_MW',
                      'T_wall_eq', 'T_recovery')


@pytest.fixture(scope='module')
def analyzer():
    return HeatTransferAnalyzer()


@pytest.fixture(scope='module')
def profile(analyzer):
    return analyzer.analyze_axial_profile(MOTOR_DATA, n_stations=N_STATIONS)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


class TestProfileSchema:
    def test_all_arrays_same_length(self, profile):
        lengths = {key: len(profile[key]) for key in PROFILE_ARRAY_KEYS}
        assert len(set(lengths.values())) == 1, f"uzunluklar eşit değil: {lengths}"
        assert lengths['x_mm'] == N_STATIONS

    def test_required_scalar_meta(self, profile):
        assert profile['x_throat_mm'] > 0
        assert profile['x_exit_mm'] > profile['x_throat_mm']
        assert 0 < profile['throat_index'] < N_STATIONS - 1

    def test_n_stations_respected(self, analyzer):
        p = analyzer.analyze_axial_profile(MOTOR_DATA, n_stations=25)
        assert len(p['x_mm']) == 25
        assert len(p['q_MW']) == 25

    def test_x_monotonic_increasing(self, profile):
        x = np.asarray(profile['x_mm'])
        assert np.all(np.diff(x) > 0)
        assert x[0] == pytest.approx(0.0)
        assert x[-1] == pytest.approx(profile['x_exit_mm'])

    def test_all_values_finite(self, profile):
        for key in PROFILE_ARRAY_KEYS:
            arr = np.asarray(profile[key], dtype=float)
            assert np.all(np.isfinite(arr)), f"{key} sonlu olmayan değer içeriyor"


class TestProfilePhysics:
    def test_area_ratio_min_one_at_throat(self, profile):
        eps = np.asarray(profile['area_ratio'])
        ti = profile['throat_index']
        assert np.all(eps >= 1.0)
        assert eps[ti] == pytest.approx(1.0)
        assert int(np.argmin(eps)) == ti

    def test_exit_area_ratio_matches_geometry(self, profile):
        # eps_exit = (d_e/d_t)^2 = 9
        expected = (MOTOR_DATA['exit_diameter'] / MOTOR_DATA['throat_diameter']) ** 2
        assert profile['area_ratio'][-1] == pytest.approx(expected, rel=1e-6)

    def test_mach_unity_at_throat(self, profile):
        ti = profile['throat_index']
        assert profile['mach'][ti] == pytest.approx(1.0, abs=1e-6)

    def test_mach_branches(self, profile):
        mach = np.asarray(profile['mach'])
        ti = profile['throat_index']
        assert np.all(mach[:ti] < 1.0), "konverjan subsonik olmalı"
        assert np.all(mach[ti + 1:] > 1.0), "diverjan süpersonik olmalı"

    def test_mach_monotonic_nondecreasing(self, profile):
        mach = np.asarray(profile['mach'])
        assert np.all(np.diff(mach) >= -1e-9)

    def test_isentropic_area_mach_residual(self, profile):
        # Her istasyon A/A* bağıntısını sağlamalı (çözücü tutarlılığı).
        gamma = MOTOR_DATA['gamma']
        eps = np.asarray(profile['area_ratio'])
        mach = np.asarray(profile['mach'])
        exponent = (gamma + 1.0) / (2.0 * (gamma - 1.0))
        eps_from_mach = (1.0 / mach) * (
            (2.0 / (gamma + 1.0)) * (1.0 + (gamma - 1.0) / 2.0 * mach ** 2)
        ) ** exponent
        assert np.allclose(eps_from_mach, eps, rtol=1e-6)

    def test_heat_flux_peaks_at_throat(self, profile):
        # NOT (ÖH FAZ B-4/P2, defter P4B1-03): bu bekçi yalnız TEPE KONUMUNU
        # ölçer. Aynı boğazın akısı ürün içinde iki ayrı kanaldan yayımlanır
        # (throat-analizi ⟷ eksenel profil) ve ikisi ayrışır; o eksen kardeş
        # bekçidedir: ``test_throat_heat_flux_agrees_with_throat_analysis``.
        q = np.asarray(profile['q_MW'])
        ti = profile['throat_index']
        assert int(np.argmax(q)) == ti, "q maksimumu boğazda olmalı"
        assert np.all(q > 0)

    # ÇEVİRİ (ÖH D15 birleşme düzeltmesi) — BORÇ İMİ KALKTI.
    # Bu bekçi P4B1-03 borcunu xfail(strict) ile taşıyordu;
    # imin kendi metni "onarım gelince bu im KALKAR" diyordu.
    # Kusur ÖH Z5S / PK5 (ısı-soğutma kulvarı) tarafından
    # ONARILDI, dolayısıyla im BAYATLADI: birleşik ağaçta test
    # GEÇİYOR ve strict im XPASS ile kırmızı veriyordu. İm
    # kaldırıldı; iddia artık CANLI bekçidir — onarım geri
    # alınırsa burası kırmızı verir.
    #
    # ÜRÜNDEKİ KANIT: hrma/analysis/heat_transfer_analysis.py:887
    # "TASARIM AKISI — TEK TANIM NOKTASI (ÖH Z5S / PK5, P4B1-03)";
    # :1806 throat_heat_flux tek tanımdan, :1543 referans soğutulmuş
    # cidar tek tanım noktası
    #
    # KALKAN İMİN GEREKÇESİ (kayıt için): ÖH defter P4B1-03 — aynı
    # boğaz, aynı koşu, İKİ tasarım akısı. analyze_heat_transfer
    # gaz-tarafı akıyı Tw_ref = 1073 K'de kuruyor
    # (heat_transfer_analysis.py:1431-1453), analyze_axial_profile
    # ise kendi cidar dengesinde çözüyor; ayrıca radyasyon terimi
    # iki farklı gazda hesaplanıyor (:1439-1451 ⟷ :1232-1247). Bu
    # fikstürde ölçülen: gas_side_analysis.throat_heat_flux 17,7935
    # MW/m² ⟷ profil q_MW[boğaz] 18,7961 MW/m² (%5,63). İki değer
    # İKİ AYRI tüketici kümesine gidiyor (PDF + 3B görselleştirme ⟷
    # /api/analysis/wall-profile → termal FEA). Onarım gelince bu im
    # KALKAR.
    def test_throat_heat_flux_agrees_with_throat_analysis(self, analyzer,
                                                          profile):
        """Aynı boğazın tasarım akısı tek bir sayı olmalı.

        Bu bekçi HANGİ kanalın doğru olduğuna hükmetmez (Tw_ref = 1073 K mi,
        cidar dengesinden çözülen T_wall mü; hangi radyasyon gazı) — yalnız
        aynı fiziksel büyüklüğün aynı koşuda iki değer YAYIMLAYAMAYACAĞINI
        söyler. Modülün kendi docstring'i de (:1120-1121) 'throat-analiziyle
        AYNI korelasyon ve gaz özellikleri' diyor; iddia o künyenin
        davranıştaki karşılığıdır.
        """
        full = analyzer.analyze_heat_transfer(MOTOR_DATA)
        q_throat_full = full['gas_side_analysis']['throat_heat_flux']   # W/m²
        q_throat_profile = profile['q_MW'][profile['throat_index']] * 1e6
        assert q_throat_profile == pytest.approx(q_throat_full, rel=0.01), (
            f'boğaz tasarım akısı iki kanalda ayrışıyor: throat-analizi '
            f'{q_throat_full / 1e6:.4f} MW/m² ⟷ eksenel profil '
            f'{q_throat_profile / 1e6:.4f} MW/m² (sapma '
            f'%{100.0 * abs(q_throat_profile / q_throat_full - 1):.2f})')

    def test_bartz_coefficient_peaks_at_throat(self, profile):
        h = np.asarray(profile['h_g'])
        ti = profile['throat_index']
        assert int(np.argmax(h)) == ti
        assert np.all(h > 0)
        # Boğaz katsayısı hazne çıkışındakinden belirgin büyük olmalı
        # (Bartz alan terimi (A_t/A)^0.9)
        assert h[ti] > 2.0 * h[0]

    def test_recovery_temperature_physical(self, profile):
        taw = np.asarray(profile['T_recovery'])
        tc = MOTOR_DATA['chamber_temperature']
        assert np.all(taw <= tc + 1e-6), "kurtarma sıcaklığı Tc'yi aşamaz"
        assert np.all(taw > 0.8 * tc), "kurtarma sıcaklığı Tc mertebesinde kalmalı"
        # M arttıkça Taw düşer (r < 1): çıkışta boğazdan düşük olmalı
        assert taw[-1] < taw[profile['throat_index']]

    def test_equilibrium_wall_temperature_band(self, profile):
        tw = np.asarray(profile['T_wall_eq'])
        taw = np.asarray(profile['T_recovery'])
        assert np.all(tw >= 293.15 - 1e-6)
        assert np.all(tw <= taw + 1e-6), "denge cidar T kurtarma T'yi aşamaz"

    def test_regenerative_cooling_cools_wall(self, analyzer):
        p_nat = analyzer.analyze_axial_profile(
            MOTOR_DATA, n_stations=N_STATIONS, cooling_type='natural')
        p_reg = analyzer.analyze_axial_profile(
            MOTOR_DATA, n_stations=N_STATIONS, cooling_type='regenerative')
        ti = p_nat['throat_index']
        assert p_reg['T_wall_eq'][ti] < p_nat['T_wall_eq'][ti], (
            "rejeneratif soğutma boğaz cidarını doğal soğutmadan soğuk tutmalı")

    # ÇEVİRİ (ÖH D15 birleşme düzeltmesi) — BORÇ İMİ KALKTI.
    # Bu bekçi P4B1-03 borcunu xfail(strict) ile taşıyordu;
    # imin kendi metni "onarım gelince bu im KALKAR" diyordu.
    # Kusur ÖH Z5S / PK5 (ısı-soğutma kulvarı) tarafından
    # ONARILDI, dolayısıyla im BAYATLADI: birleşik ağaçta test
    # GEÇİYOR ve strict im XPASS ile kırmızı veriyordu. İm
    # kaldırıldı; iddia artık CANLI bekçidir — onarım geri
    # alınırsa burası kırmızı verir.
    #
    # ÜRÜNDEKİ KANIT: hrma/analysis/heat_transfer_analysis.py:1661
    # "gaz-yanı katsayı artık TASARIM AKISININ ... "; :1730 "h_g'nin
    # hangi cidar sıcaklığında kurulduğu ARTIK ..."; :1781 referans
    # cidar TEK TANIM NOKTASINDAN
    #
    # KALKAN İMİN GEREKÇESİ (kayıt için): ÖH defter P4B1-03 — aynı
    # boğazın gaz-yanı katsayısı iki değerle yayımlanıyor:
    # _calculate_heat_transfer_coefficients h_g'yi wall_guess =
    # min(0,5·Tc, max_service·0,8) ile
    # (heat_transfer_analysis.py:1342-1350), eksenel profil ise
    # kendi cidar dengesiyle çözüyor. Bu fikstürde ölçülen: 8.105,45
    # ⟷ 8.824,91 W/m²K (%8,88). Modül aynı kusuru denge-cidarı
    # dalında F116 ile kapatmış (:1463-1478), tasarım akısı dalında
    # kapatmamış. Onarım gelince bu im KALKAR.
    def test_throat_hg_consistent_with_throat_analysis(self, analyzer, profile):
        """Boğaz Bartz katsayısı iki kanalda aynı sayı olmalı.

        DÜZELTME (ÖH FAZ B-4/P2): bu bekçinin eski hâli ``rel=0.25``
        toleransı ve "yalnız sigma için kullanılan referans cidar sıcaklığı
        farkı kadar sapabilir" yorumuyla tutarsızlığı AÇIKÇA kutsuyordu —
        ölçülen %8,88 sapma o bantta rahatça geçiyor, yani bekçi kusuru
        göremez hâlde yazılmıştı. Tolerans, iki kanalın AYNI korelasyondan
        çıktığı yolundaki ürün künyesinin (:1120-1121) izin verdiği tek
        şeye, sayısal gürültüye indirildi. Hangi cidar sıcaklığının doğru
        referans olduğuna bu bekçi HÜKMETMEZ.
        """
        full = analyzer.analyze_heat_transfer(MOTOR_DATA)
        h_throat_full = full['heat_transfer_coefficients']['gas_side']
        h_throat_profile = profile['h_g'][profile['throat_index']]
        assert h_throat_profile == pytest.approx(h_throat_full, rel=0.01), (
            f'boğaz h_g iki kanalda ayrışıyor: throat-analizi '
            f'{h_throat_full:.2f} W/m²K ⟷ eksenel profil '
            f'{h_throat_profile:.2f} W/m²K (sapma '
            f'%{100.0 * abs(h_throat_profile / h_throat_full - 1):.2f})')


class TestWallProfileEndpoint:
    # Termal panel formuyla aynı çekirdek alanlar (/analyze_thermal_safety)
    PAYLOAD = {
        'chamber_pressure': 30.0,
        'chamber_temperature': 3200.0,
        'chamber_diameter': 0.10,
        'chamber_length': 0.40,
        'burn_time': 8.0,
        'mdot_total': 2.0,
        'material': 'steel_4130',
        'wall_thickness': 0.006,
        'cooling_type': 'natural',
        # panel currentResults'tan tamamlar:
        'throat_diameter': 0.03,
        'exit_diameter': 0.09,
        'gamma': 1.22,
        'molecular_weight': 26.0,
        'n_stations': 40,
    }

    def test_endpoint_returns_200_with_schema(self, client):
        r = client.post('/api/analysis/wall-profile', json=self.PAYLOAD)
        assert r.status_code == 200
        j = r.get_json()
        assert j['status'] == 'success'
        profile = j['wall_profile']
        for key in ('x_mm', 'area_ratio', 'mach', 'h_g', 'q_MW', 'T_wall_eq'):
            assert key in profile, f"şemada eksik anahtar: {key}"
            assert isinstance(profile[key], list)
        lengths = {len(profile[k]) for k in
                   ('x_mm', 'area_ratio', 'mach', 'h_g', 'q_MW', 'T_wall_eq')}
        assert lengths == {40}

    def test_endpoint_physics_throat_peak(self, client):
        r = client.post('/api/analysis/wall-profile', json=self.PAYLOAD)
        profile = r.get_json()['wall_profile']
        q = profile['q_MW']
        ti = profile['throat_index']
        assert int(np.argmax(np.asarray(q))) == ti
        assert profile['mach'][ti] == pytest.approx(1.0, abs=1e-6)
        # Boğaz konumu işaretçisi frontend için mm cinsinden gelir
        assert profile['x_mm'][ti] == pytest.approx(profile['x_throat_mm'])

    # ÇEVİRİ (ÖH D15 birleşme düzeltmesi) — BORÇ İMİ KALKTI.
    # Bu bekçi P4B1-02 borcunu xfail(strict) ile taşıyordu;
    # imin kendi metni "onarım gelince bu im KALKAR" diyordu.
    # Kusur ÖH Z5S / PK5 (ısı-soğutma kulvarı) tarafından
    # ONARILDI, dolayısıyla im BAYATLADI: birleşik ağaçta test
    # GEÇİYOR ve strict im XPASS ile kırmızı veriyordu. İm
    # kaldırıldı; iddia artık CANLI bekçidir — onarım geri
    # alınırsa burası kırmızı verir.
    #
    # ÜRÜNDEKİ KANIT: hrma/app.py:13357 "ÖH Z5S / PK5 (P4B1-02) —
    # GİRDİ KAPILARI. Bu uçta kapı HİÇ YOKTU."; :13447 "ya reddet ya
    # söyle" ayağı; :13485 modül varsayılanları ADIYLA ilan ediliyor
    #
    # KALKAN İMİN GEREKÇESİ (kayıt için): ÖH defter P4B1-02 —
    # /api/analysis/wall-profile'da girdi kapısı HİÇ yok
    # (app.py:7500-7575): kardeş uç /analyze_thermal_safety'nin iki
    # kapısı (_collect_unphysical_fields,
    # _withhold_unevaluated_thermal_verdict) burada yok, modül kendi
    # 20.0/3000/1.0 varsayılanlarıyla çözüyor
    # (heat_transfer_analysis.py:1144-1154). Ölçülen: eksik geometri
    # → HTTP 200 + tam görünümlü profil, yanıtta hangi girdinin
    # varsayıldığını söyleyen TEK alan yok (gövde yalnız {status,
    # wall_profile}); boş gövde {} de aynı şekilde 200 dönüyor.
    # Deponun koruması yalnız istemcide:
    # thermal_fea_panel.js:946-950 "would silently substitute
    # defaults... so it is not called". Onarım gelince bu im KALKAR.
    def test_endpoint_declares_substituted_defaults(self, client):
        """Eksik girdi ya reddedilir ya da YERİNE KONAN ilan edilir.

        DÜZELTME (ÖH FAZ B-4/P2): bu bekçinin eski hâli
        (``test_endpoint_defaults_when_minimal_payload``) "Yalnız çekirdek
        alanlar — geometri backend varsayılanlarından çözülür" yorumuyla
        sessiz varsayılan ikamesini SÖZLEŞME yapıyordu; uca kapı ekleyen her
        onarım o bekçiyi kırardı. İddia deponun kendi sağlıklı desenine
        çevrildi: ``inputs_not_used`` / ``warn.liquid.input_field_not_read``
        ailesinde olduğu gibi, uydurulan sayı ya hiç uydurulmaz (4xx) ya da
        ADIYLA ilan edilir.
        """
        eksik = {'chamber_pressure': 25.0, 'chamber_temperature': 3000.0,
                 'mdot_total': 1.5}
        r = client.post('/api/analysis/wall-profile', json=eksik)
        if r.status_code != 200:
            assert 400 <= r.status_code < 500, (
                f'beklenmeyen HTTP {r.status_code}')
            return                       # fail-closed: kabul

        j = r.get_json()
        beyan = [k for k in j
                 if any(im in k.lower() for im in
                        ('default', 'assumed', 'substitut', 'missing',
                         'not_used', 'not_read', 'warn', 'inputs'))]
        assert beyan, (
            'eksik geometriyle 200 dönüldü ve yanıt hangi girdinin '
            f'varsayıldığını söylemiyor (gövde anahtarları: {sorted(j)}); '
            'boğaz çapı, çıkış çapı, gamma ve molekül ağırlığı sessizce '
            'uyduruldu')

    # ÇEVİRİ (ÖH D15 birleşme düzeltmesi) — BORÇ İMİ KALKTI.
    # Bu bekçi P4B1-02'nin FİZİK ayağını xfail(strict) ile taşıyordu;
    # imin kendi metni "onarım gelince bu im KALKAR" diyordu. Kusur
    # ÖH Z5S / PK5 (ısı-soğutma kulvarı) tarafından ONARILDI — kardeş
    # ayağı (test_endpoint_declares_substituted_defaults) bu dalgada
    # zaten çevrildi; aynı kalemin iki ayağından birini canlı bırakıp
    # ötekini borç iminde tutmak tutarsız olurdu.
    #
    # ÜRÜNDEKİ KANIT: hrma/app.py:13357 "ÖH Z5S / PK5 (P4B1-02) — GİRDİ
    # KAPILARI. Bu uçta kapı HİÇ YOKTU." Uç artık fizik dışı alanı ADIYLA
    # reddediyor; ÖLÇÜLDÜ (1 Eylül 2026, bu depo):
    #   chamber_temperature=-3000 → HTTP 422 invalid_wall_profile_input
    #       invalid_fields=[{field: chamber_temperature,
    #                        reason: must_be_positive, value: -3000.0}]
    #   chamber_pressure=-60      → HTTP 422, aynı biçim
    #   wall_thickness=-0.01      → HTTP 422, aynı biçim
    # Testin kendi sözleşmesi 4xx'i "fail-closed: kabul" sayar, o yüzden
    # üç parametre de yeşil.
    #
    # KALKAN İMİN GEREKÇESİ (kayıt için): ÖH defter P4B1-02 — aynı
    # kapısızlığın FİZİK ekseni: ölçülen chamber_temperature=−3000 → HTTP
    # 200 ve T_wall_eq −530,13..−504,23 K (MUTLAK SIFIRIN ALTINDA) +
    # T_recovery −2.896,37 K + q_MW 40/40 null; chamber_pressure=−60 →
    # 200 + "cidar ortamda kalır" (293,15 K) + uydurma boğaz 0,03 m;
    # wall_thickness=−0,01 → 200 + wall_thickness_mm = −10,0. Bu profil
    # thermal_fea_panel.js:979-985 üzerinden AYNEN /api/fea/thermal'a
    # h(z) sınır koşulu olarak geçiyor. Onarım gelince bu im KALKAR.
    @pytest.mark.parametrize('ad,ek', [
        ('negatif_hazne_sicakligi', {'chamber_temperature': -3000.0}),
        ('negatif_hazne_basinci', {'chamber_pressure': -60.0}),
        ('negatif_cidar_kalinligi', {'wall_thickness': -0.01}),
    ])
    def test_endpoint_rejects_unphysical_inputs(self, client, ad, ek):
        """Fizik dışı girdiden profil yayımlanmaz.

        Sözleşme deponun kendi desenidir: kardeş uç
        ``/analyze_thermal_safety`` fizik dışı alanı ADIYLA toplayıp hükmü
        geri çeker (``_collect_unphysical_fields``,
        ``_withhold_unevaluated_thermal_verdict``); bu uç aynı şemayı
        kullandığını BELGELİYOR (app.py:7507) ama kapıların hiçbirini
        almamış.
        """
        r = client.post('/api/analysis/wall-profile',
                        json=dict(self.PAYLOAD, **ek))
        if r.status_code != 200:
            assert 400 <= r.status_code < 500
            return                       # fail-closed: kabul

        j = r.get_json()
        assert j['status'] == 'success'          # ön koşul: uç 200 + başarı
        profile = j['wall_profile']

        # (i) "Başarılı" bir profil çözülemeyen istasyon yayımlayamaz.
        for anahtar in ('q_MW', 'h_g', 'T_wall_eq', 'T_recovery'):
            bos = [i for i, v in enumerate(profile[anahtar])
                   if v is None or not np.isfinite(float(v))]
            assert not bos, (
                f'{ad}: status=success ama {anahtar} dizisinin '
                f'{len(bos)}/{len(profile[anahtar])} istasyonu '
                'çözülememiş (None/NaN) — çözülemeyen girdi başarı diye '
                'yayımlanıyor')

        # (ii) Yayımlanan sıcaklıklar mutlak sıcaklıktır.
        for anahtar in ('T_wall_eq', 'T_recovery'):
            kotu = [v for v in profile[anahtar] if v is not None and v <= 0.0]
            assert not kotu, (
                f'{ad}: {anahtar} mutlak sıfırın altında değer yayımlıyor '
                f'(ör. {kotu[:3]}) — HTTP 200')

        # (iii) Geometri künyesi de fizikseldir.
        assert profile['wall_thickness_mm'] > 0.0, (
            f"{ad}: wall_thickness_mm = {profile['wall_thickness_mm']}")
        assert profile['throat_diameter_m'] is not None, (
            f'{ad}: boğaz çapı çözülememiş ama profil yayımlanıyor')

    def test_endpoint_respects_n_stations(self, client):
        payload = dict(self.PAYLOAD, n_stations=60)
        r = client.post('/api/analysis/wall-profile', json=payload)
        assert r.status_code == 200
        assert len(r.get_json()['wall_profile']['x_mm']) == 60

    def test_endpoint_no_plot_keys(self, client):
        # Sözleşme: endpoint grafik ÇİZMEZ — Plotly/plot anahtarı dönmez.
        r = client.post('/api/analysis/wall-profile', json=self.PAYLOAD)
        j = r.get_json()
        assert 'plot' not in j and 'plot_json' not in j
        assert 'plot' not in j['wall_profile']
