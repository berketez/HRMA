"""ÖH Dalga-16 / kulvar termo-ucus, aşama a1 — onarım bekçileri.

Kapsam (defter kimlikleri):
  * **P16B3-14** — ``/api/trajectory-analysis`` çözücünün DOĞRU reddini
    HTTP 500'e çeviriyor ve traceback'i stdout'a basıyordu.
  * **OH-D15-08** / **P12bB2-09** — düzlemsel çözücü ``motor_data['thrust']``i
    SKALER okuyordu; uç itki eğrisini görmüyordu.
  * **OH-D15-09** — P4B1-15 ürün onarımı indi ama bekçisinin borç imi
    (``xfail(strict=True)``) kaldırılmadığı için üç test imsiz kırmızıydı.

Her iddia onarım ÖNCESİ ölçülmüş bir sayıya dayanır; sayılar
``docs/scofield/raw/OH/D16/termo-ucus/a1/once.json`` içindedir. Bekçilerin
ters-mutasyonla kırmızıya döndüğü ``mutasyon.py`` ile tescillenmiştir.
"""
import io
import contextlib

import pytest

from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
from hrma.analysis.trajectory_analysis import (
    TrajectoryAnalyzer, TrajectoryInputError, normalize_thrust_curve)


ARAC = {'initial_mass': 50.0, 'final_mass': 35.0,
        'drag_coefficient': 0.5, 'reference_area': 0.01}

#: Tepe/ortalama = 3,0 olan gerçek bir eğri. Katı motorun ilerleyen tanesi
#: bu biçimdedir; wagon_wheel tanesinde ölçülen oran 3,7117'dir (P12bB2-09).
EGRI_T = [0.0, 1.0, 2.0, 4.0, 8.0]
EGRI_F = [12000.0, 12000.0, 4000.0, 2000.0, 1000.0]
EGRI = {'time': EGRI_T, 'thrust': EGRI_F}
#: trapz(F, t) el hesabı: 12000 + 8000 + 6000 + 6000 = 32000 N·s
EGRI_IMPULS = 32000.0
EGRI_ORTALAMA = 4000.0         # I / 8 s  ->  tepe/ortalama = 3,0


@pytest.fixture
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _sessiz_post(client, yol, yuk):
    """İsteği koşar ve STDOUT'a ne basıldığını da döndürür."""
    tampon = io.StringIO()
    with contextlib.redirect_stdout(tampon):
        r = client.post(yol, json=yuk)
    return r, tampon.getvalue()


# ===================================================================== #
# P16B3-14 — çözücünün doğru reddi DOĞRU kodla taşınır                  #
# ===================================================================== #

class TestCozucuReddi422:
    """ÖLÇÜLDÜ (once.json K1, taban 6fde52b): üç sarsımda da HTTP **500** +
    stdout'a 1.133-1.141 baytlık TAM traceback; gövdede alan adı yok, yalnız
    Türkçe istisna metni (İngilizce API'de). Sağlıklı istekte bile 546 bayt
    hata ayıklama çıktısı akıyordu."""

    @pytest.mark.parametrize('sarsim,alan,gerekce', [
        ({'thrust': -1000.0, 'burn_time': 8.0}, 'thrust', 'must_be_positive'),
        ({'thrust': 5000.0, 'burn_time': -10.0}, 'burn_time',
         'must_be_positive'),
        ({'thrust': 5000.0, 'burn_time': 8.0, 'final_mass': -10.0},
         'final_mass', 'must_be_positive'),
    ])
    def test_gecersiz_girdi_422_ve_alan_adiyla(self, client, sarsim, alan,
                                               gerekce):
        r, cikti = _sessiz_post(client, '/api/trajectory-analysis',
                                dict(ARAC, **sarsim))
        assert r.status_code == 422, (
            f'istemci hatası {r.status_code} ile taşınıyor; çözücünün reddi '
            f'sunucu arızası gibi görünüyor (ölçülen taban: 500)')
        j = r.get_json()
        assert j['error'] == 'invalid_trajectory_input'
        adlar = [k['field'] for k in j['invalid_fields']]
        assert alan in adlar, (
            f'gövde {adlar} diyor; kullanıcının DÜZELTECEĞİ alan {alan!r}')
        kayit = next(k for k in j['invalid_fields'] if k['field'] == alan)
        assert kayit['reason'] == gerekce
        assert 'Traceback (most recent call last)' not in cikti, (
            'istemci hatasında tam traceback stdout\'a basılıyor')

    def test_saglikli_istek_stdout_a_hicbir_sey_basmaz(self, client):
        r, cikti = _sessiz_post(client, '/api/trajectory-analysis',
                                dict(ARAC, thrust=5000.0, burn_time=8.0))
        assert r.status_code == 200
        # Ölçülen taban: 546 bayt ("About to call calculate_trajectory…",
        # sözlük anahtar dökümleri). Kardeş kalem P17B3-01 aynı sunucuda
        # stdout sarmalayıcısının kalıcı bozulmasını ölçtü.
        assert cikti == '', (
            f'sağlıklı yolda {len(cikti)} bayt hata ayıklama çıktısı: '
            f'{cikti[:200]!r}')

    def test_sifir_itki_eksik_degil_gecersizdir(self, client):
        """0 ile 'verilmedi' ASLA karıştırılmaz (deponun kendi ilkesi).

        Ölçülen taban: ``thrust: 0`` -> 422 ``missing_fields: ['thrust']``.
        Alan GÖNDERİLMİŞTİ; kullanıcı var olan bir alanı 'eksik' diye
        arıyordu. Kapı sınıfı değişmez (ikisi de 422, yörünge yok)."""
        r = client.post('/api/trajectory-analysis',
                        json=dict(ARAC, thrust=0, burn_time=8.0))
        assert r.status_code == 422
        j = r.get_json()
        assert j['error'] == 'invalid_trajectory_input', (
            f"gerekçe {j.get('error')!r}; 0 gönderilmiş bir değerdir, "
            f'eksik alan değil')
        assert j['invalid_fields'][0]['field'] == 'thrust'
        assert j['invalid_fields'][0]['reason'] == 'must_be_positive'

    def test_anahtar_hic_yoksa_hala_missing_fields(self, client):
        """Karşı yön: gerçekten VERİLMEYEN alan 'eksik' kalmalı."""
        r = client.post('/api/trajectory-analysis',
                        json=dict(ARAC, burn_time=8.0))
        assert r.status_code == 422
        assert r.get_json()['error'] == 'missing_fields'


# ===================================================================== #
# OH-D15-08 / P12bB2-09 — çözücü itki EĞRİSİNİ görür                    #
# ===================================================================== #

class TestItkiEgrisi:
    """ÖLÇÜLDÜ (once.json K2, taban): ``thrust_curve`` adı
    ``trajectory_analysis.py`` kaynağında 0 kez geçiyordu ve tepe/ortalama
    oranı 3,0 olan eğri gönderildiğinde apoje, aynı ortalamanın
    dikdörtgeniyle BİREBİR aynıydı (11.854,442870053985 m; bağıl fark 0,0)."""

    def test_egri_ucusu_degistirir(self, client):
        r_skaler = client.post('/api/trajectory-analysis',
                               json=dict(ARAC, thrust=EGRI_ORTALAMA,
                                         burn_time=8.0))
        r_egri = client.post('/api/trajectory-analysis',
                             json=dict(ARAC, thrust=EGRI_ORTALAMA,
                                       burn_time=8.0, thrust_curve=EGRI))
        assert r_skaler.status_code == 200 and r_egri.status_code == 200

        def _apoje(r):
            return (r.get_json()['trajectory_data']['performance']
                    ['trajectory_metrics']['max_altitude'])

        a, b = _apoje(r_skaler), _apoje(r_egri)
        assert abs(b - a) / a > 1e-6, (
            f'aynı ORTALAMA itkinin dikdörtgeni ({a:.6f} m) ile tepe/ortalama '
            f'{max(EGRI_F) / EGRI_ORTALAMA:.4g} olan gerçek eğri ({b:.6f} m) '
            f'aynı yörüngeyi veriyor: uç eğriyi görmüyor')

    def test_egri_kunyesi_yayimlanir(self, client):
        r = client.post('/api/trajectory-analysis',
                        json=dict(ARAC, thrust=EGRI_ORTALAMA, burn_time=8.0,
                                  thrust_curve=EGRI))
        ti = r.get_json()['trajectory_data'].get('thrust_input')
        assert ti is not None, (
            'yörünge eğriden entegre edildi ama yanıt bunu söylemiyor')
        assert ti['source'] == 'thrust_curve'
        assert ti['points'] == len(EGRI_T)
        assert ti['total_impulse_Ns'] == pytest.approx(EGRI_IMPULS, rel=1e-12)
        assert ti['average_thrust_N'] == pytest.approx(EGRI_ORTALAMA,
                                                       rel=1e-12)
        assert ti['peak_to_average_ratio'] == pytest.approx(
            max(EGRI_F) / EGRI_ORTALAMA, rel=1e-12)

    def test_yayimlanan_debi_kunyesi_egriyle_duzelir(self, client):
        """Tek yanıtta iki farklı debi olamaz (P7B3-18'in dersi).

        Eğri verildiğinde çözücü ṁ(t) entegre eder; yanıttaki skaler
        ``mass_flow_rate`` ORTALAMADIR ve künyesi bunu söylemek zorundadır.
        Eğri yokken künye eskisi gibi kalır."""
        r = client.post('/api/trajectory-analysis',
                        json=dict(ARAC, thrust_curve=EGRI))
        md = r.get_json()['trajectory_data']['motor_data']
        assert 'AVERAGE mass flow' in md['mass_flow_rate_basis'], (
            f"künye {md['mass_flow_rate_basis'][:80]!r} — çözücü değişken "
            f'debi entegre ederken sabit debi vaat ediyor')
        r2 = client.post('/api/trajectory-analysis',
                         json=dict(ARAC, thrust=EGRI_ORTALAMA, burn_time=8.0))
        md2 = r2.get_json()['trajectory_data']['motor_data']
        assert md2['mass_flow_rate_basis'].startswith(
            'propellant_mass_total / burn_time')

    def test_egri_yokken_kunye_eklenmez(self, client):
        """Skaler yolun çıktı sözleşmesi bit-aynı kalır (regresyon kilidi)."""
        r = client.post('/api/trajectory-analysis',
                        json=dict(ARAC, thrust=EGRI_ORTALAMA, burn_time=8.0))
        assert 'thrust_input' not in r.get_json()['trajectory_data']

    def test_kalkis_itki_agirlik_orani_tepeden_okunur(self):
        """T/W bir KALKIŞ büyüklüğüdür; ortalama itki onu 3 kat küçültürdü."""
        cozucu = TrajectoryAnalyzer()
        cozucu.set_vehicle_parameters(mass_dry=35.0, diameter=0.1128,
                                      drag_coefficient=0.5)
        cozucu.set_thrust_curve(EGRI)
        md = {'thrust': EGRI_ORTALAMA, 'burn_time': 8.0,
              # ÖH D23 / P4B3-24 — tutarsız 'isp' kaldırıldı (bekçi çevirisi): yük
              # yanmayı iki kez ve iki farklı biçimde tarif ediyordu; çözücü artık
              # çelişkiyi reddediyor. Isp bir GİRDİ değil, entegre edilen impuls
              # bütçesinin türevidir ve anahtar yokken ondan türetilir — bu bekçinin
              # ölçtüğü sayıların hiçbiri değişmez (ölçüldü: isp 220/1/1e9 -> apoje
              # BİT-AYNI, once.json P4B3_24).
              'total_impulse': EGRI_IMPULS,
              'mass_flow_rate': 15.0 / 8.0, 'propellant_mass_total': 15.0}
        with contextlib.redirect_stdout(io.StringIO()):
            r = cozucu.calculate_trajectory(md, {'launch_angle': 85.0})
        tw = r['performance']['motor_performance']['thrust_to_weight_ratio']
        beklenen = EGRI_F[0] / (50.0 * cozucu.g_surface)
        assert tw == pytest.approx(beklenen, rel=1e-12), (
            f'T/W {tw:.4f}; kalkışta itki {EGRI_F[0]:g} N iken ortalamadan '
            f'({EGRI_ORTALAMA:g} N) hesaplanmış görünüyor')

    def test_yakit_itkiyle_orantili_harcanir(self):
        """∫ṁ dt = m_p TAM olmalı: eğri kütle bütçesini bozmaz."""
        cozucu = TrajectoryAnalyzer()
        cozucu.set_vehicle_parameters(mass_dry=35.0, diameter=0.1128,
                                      drag_coefficient=0.5)
        cozucu.set_thrust_curve(EGRI)
        import numpy as np
        with contextlib.redirect_stdout(io.StringIO()):
            pf = cozucu._calculate_powered_flight(
                EGRI_ORTALAMA, 8.0, 50.0, 15.0, np.radians(85.0), 0.0,
                0.01, (0.0, 0.0), thrust_curve=cozucu._thrust_curve)
        # Güçlü fazın SON kütlesi kuru kütleye oturmalı: ṁ(t) itkiyle
        # orantılı ama integrali TAM m_p etmeli (yakıt ne eksik ne fazla).
        son_kutle = pf['final_state'][4]
        assert son_kutle == pytest.approx(35.0, abs=1e-4), (
            f'yanma sonu kütle {son_kutle:.6f} kg; kuru kütle 35,0 kg — '
            f'eğri yolunda kütle bütçesi kapanmıyor')

    @pytest.mark.parametrize('bozuk,gerekce', [
        ({'time': [0.0], 'thrust': [100.0]}, 'too_few_points'),
        ({'time': [0.0, 1.0], 'thrust': [100.0]}, 'length_mismatch'),
        ({'time': [0.0, 1.0], 'thrust': [100.0, float('nan')]}, 'not_finite'),
        ({'time': [1.0, 0.0], 'thrust': [100.0, 100.0]},
         'time_not_increasing'),
        ({'time': [0.0, 1.0], 'thrust': [100.0, -5.0]}, 'negative_thrust'),
    ])
    def test_bozuk_egri_422_ile_reddedilir(self, client, bozuk, gerekce):
        """Bozuk eğri ham 500 değil, adlandırılmış 422 üretir."""
        r, cikti = _sessiz_post(client, '/api/trajectory-analysis',
                                dict(ARAC, thrust=1000.0, burn_time=8.0,
                                     thrust_curve=bozuk))
        assert r.status_code == 422, f'{r.status_code} — ham sunucu hatası'
        j = r.get_json()
        assert j['invalid_fields'][0]['field'] == 'thrust_curve'
        assert j['invalid_fields'][0]['reason'] == gerekce
        assert 'Traceback (most recent call last)' not in cikti

    def test_yalniz_egri_gonderilebilir(self, client):
        """Panel skaler ortalama göndermek ZORUNDA değil: eğri yeter.

        P12bB2-09'un onarım yolu tam olarak budur — şablon tek skaler
        ``average_thrust`` yerine çözücünün yayımladığı gerçek eğriyi
        gönderebilmeli ve uç ondan itki/süreyi TÜRETMELİ (uydurmadan)."""
        r = client.post('/api/trajectory-analysis',
                        json=dict(ARAC, thrust_curve=EGRI))
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        ti = r.get_json()['trajectory_data']['thrust_input']
        assert ti['burn_time_s'] == pytest.approx(EGRI_T[-1], rel=1e-12)
        assert ti['average_thrust_N'] == pytest.approx(EGRI_ORTALAMA,
                                                       rel=1e-12)

    def test_egri_ile_celisen_skaler_reddedilir(self, client):
        """Aynı yanmayı iki yoldan tarif eden çelişki fail-closed."""
        r = client.post('/api/trajectory-analysis',
                        json=dict(ARAC, thrust=EGRI_ORTALAMA, burn_time=30.0,
                                  thrust_curve=EGRI))
        assert r.status_code == 422
        j = r.get_json()
        assert j['error'] == 'inconsistent_thrust_input'
        assert j['invalid_fields'][0]['field'] == 'burn_time'

    def test_normalizer_kardes_sozlesmeyi_uygular(self):
        """t[0] > 0 ise başa (0, F[0]) eklenir — 6-DOF ile aynı kural."""
        t, F, imp = normalize_thrust_curve({'time': [1.0, 2.0],
                                            'thrust': [10.0, 20.0]})
        assert list(t) == [0.0, 1.0, 2.0]
        assert list(F) == [10.0, 10.0, 20.0]
        assert imp == pytest.approx(10.0 + 15.0, rel=1e-12)
        with pytest.raises(TrajectoryInputError):
            normalize_thrust_curve({'time': [0.0, 1.0],
                                    'thrust': [0.0, 0.0]})


# ===================================================================== #
# OH-D15-09 — P4B1-15 onarımı ÜRÜNDE duruyor (bekçisi imsiz değil)      #
# ===================================================================== #

class TestGerilmeEmniyetKatsayisiCemberTerimi:
    """ÖLÇÜLDÜ (once.json K3): dört basınçta da ``pressure_hoop_stress_MPa``
    p·r/t el hesabıyla birebir ve ``stress_safety_factor`` =
    akma/(σ_th+σ_hoop). Yalnız-termal katsayı Pc 2000 bar'da %59,7 iyimser
    olurdu (0,1372684 ⟷ 0,0859636)."""

    @pytest.mark.parametrize('pc_bar', [20.0, 100.0, 500.0, 2000.0])
    def test_sf_birlesik_gerilmeden_turetilir(self, pc_bar):
        cap_m, cidar_m = 0.1, 0.005
        md = {'chamber_pressure': pc_bar, 'chamber_temperature': 3200,
              'chamber_diameter': cap_m, 'chamber_length': 0.5,
              'burn_time': 10, 'mdot_total': 1.0}
        with contextlib.redirect_stdout(io.StringIO()):
            s = HeatTransferAnalyzer().analyze_heat_transfer(
                md, material='steel_4130', wall_thickness=cidar_m,
                cooling_type='regenerative')['safety_analysis']
        hoop = (pc_bar * 1e5) * (cap_m / 2.0) / cidar_m / 1e6
        assert s['pressure_hoop_stress_MPa'] == pytest.approx(hoop, rel=1e-12), (
            'çember gerilmesi p·r/t değil')
        birlesik = s['thermal_stress'] + hoop
        akma = s['thermal_stress_properties']['yield_strength_MPa']
        assert s['stress_safety_factor'] == pytest.approx(akma / birlesik,
                                                          rel=1e-12), (
            f"stress_safety_factor {s['stress_safety_factor']:.7f} "
            f'yayımlanıyor; birleşik gerilmeden (σ_th {s["thermal_stress"]:.4f} '
            f'+ σ_hoop {hoop:.4f} MPa) türetilse {akma / birlesik:.7f} olurdu')
        assert s['stress_safety_factor_scope'] == \
            'thermal_gradient_plus_pressure_hoop'

    def test_borc_imi_geri_konmadi(self):
        """Bu bekçi ailesinin ``xfail(strict)`` borç imi geri gelmemeli.

        OH-D15-09'un kökü buydu: ürün onarımı indi, im kalmadı ve üç test
        XPASS(strict) = KIRMIZI olarak imsiz durdu (ölçüldü: e88d096 ve
        6fde52b). İm geri konarsa onarım kilidi kaybolur."""
        import ast
        import pathlib
        kaynak = (pathlib.Path(__file__).resolve().parent
                  / 'test_v252_physics.py')
        agac = ast.parse(kaynak.read_text(encoding='utf-8'))
        sinif = next(n for n in ast.walk(agac)
                     if isinstance(n, ast.ClassDef)
                     and n.name == 'TestThermalStressFromMaterial')
        imli = [n.name for n in sinif.body
                if isinstance(n, ast.FunctionDef)
                and any('xfail' in ast.unparse(d) for d in n.decorator_list)]
        assert imli == [], (
            f'P4B1-15 bekçilerinde borç imi var: {imli}; ürün onarımı indi, '
            f'im XPASS(strict) ile testi kırmızı yapar')
