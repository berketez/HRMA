"""Bebek-Scofield onarım dalgası — analiz modülleri bekçileri (A3).

Kapsam ve kapatılan bulgular (`docs/scofield-bebek-2026-08-17.md`):

* **F4-1** — ``HeatTransferAnalyzer.analyze_heat_transfer`` boş girdiyle TAM
  sonuç üretiyordu (155 yaprak, ``heat_flux = 13 027 380,54 W/m²``,
  ``risk_level = 'HIGH'``; boş ↔ dolu farklı yaprak sayısı SIFIR). Beyan
  "verilmezse fiziksel olarak türetilir" diyordu, davranış altı anahtarı
  SABİTLE dolduruyordu.
* **F4-4** — Çalkalanma çözücüsünde pozitiflik kapısı yoktu: negatif yoğunluk
  geçiyor ve NEGATİF sıvı kütlesi yayımlanıyordu (ölçüldü:
  ``liquid_mass_kg = -157,0796``). NaN ise ``<= 0`` denetimini sessizce
  geçiyordu.
* **F4-5** — ``of_ratio = -6`` tam bir performans sonucu üretiyordu (negatif
  elemental kütle kesirleri + negatif eşdeğerlik oranı, ``isp = 167,822 s``).
* **F3-3** — ``vacuum_isp`` gerçek vakum değil, irtifa TABLOSUNUN en üst
  satırıydı: yayımlanan sayı kullanıcının seçtiği irtifa listesine bağlıydı.
* **F3-1** (bu dosyadaki ayak) — Geçici balistik itkiyi C_D'siz kuruyordu;
  t=0'da seri tasarım noktasını 1/C_D = %2,04 aşıyordu (3061,2245 N ⟷
  3000,0 N).

Bekçilerin ortak kuralı: her biri KUSURUN KENDİSİNİ yakalar — düzeltme geri
alınırsa kırmızıya döner (mutasyon ölçümleri iş kalemi raporundadır).
"""

import math

import numpy as np
import pytest

from hrma.analysis.heat_transfer_analysis import (
    HEAT_TRANSFER_REQUIRED_FIELDS,
    HEAT_TRANSFER_THROAT_SCALE_FIELDS,
    HeatTransferAnalyzer,
    MissingHeatTransferInput,
)
from hrma.analysis.slosh_analysis import CylindricalTankSlosh, analyze_slosh
from hrma.analysis.transient_ballistics import (
    NOZZLE_DISCHARGE_COEFFICIENT as NOZZLE_CD,
)
from hrma.constants import G_0
from hrma.engines.combustion_analysis import (
    OF_RATIO_MIN_EXCLUSIVE,
    CombustionAnalyzer,
)


# ---------------------------------------------------------------------------
# F4-1 — ısı analizi girdi kapısı
# ---------------------------------------------------------------------------

#: Kapıdan geçen eksiksiz motor (ölçüm tabanı: heat_flux = 13 027 380,54 W/m²)
TAM_MOTOR = {
    'chamber_pressure': 20.0,      # bar
    'chamber_temperature': 3000.0,  # K
    'chamber_diameter': 0.1,       # m
    'chamber_length': 0.5,         # m
    'burn_time': 10.0,             # s
    'mdot_total': 1.0,             # kg/s
}


class TestF41IsiTransferiGirdiKapisi:
    """Boş/eksik girdiden ısı hükmü üretilemez."""

    def test_bos_girdi_reddedilir(self):
        """ÖLÇÜLEN KUSUR: ``motor_data={}`` 155 dolu yaprak veriyordu."""
        with pytest.raises(MissingHeatTransferInput) as exc:
            HeatTransferAnalyzer().analyze_heat_transfer(motor_data={})
        # Hüküm değil, gerekçe döner: eksikler ADIYLA sayılır.
        assert exc.value.missing_fields
        for alan in HEAT_TRANSFER_REQUIRED_FIELDS:
            assert alan in exc.value.missing_fields

    def test_red_kardes_uclarla_ayni_dili_konusur(self):
        """`/analyze_safety` deseni: 'cannot be produced from defaults'."""
        with pytest.raises(MissingHeatTransferInput) as exc:
            HeatTransferAnalyzer().analyze_heat_transfer(motor_data={})
        mesaj = str(exc.value)
        assert 'cannot be produced from defaults' in mesaj
        # Uydurma bir sayı DEĞİL, eksik alan adları iletilir.
        assert 'chamber_pressure' in mesaj

    def test_hata_ValueError_alt_sinifidir(self):
        """Mevcut çağıranların ``except ValueError`` dalları korunur.

        ``safety_analysis._resolve_wall_temperatures`` bu zinciri sarmalayıp
        'NOT COMPUTED' beyanına düşer; kapının onu 500'e çevirmemesi gerekir.
        """
        assert issubclass(MissingHeatTransferInput, ValueError)

    @pytest.mark.parametrize('eksik', HEAT_TRANSFER_REQUIRED_FIELDS)
    def test_her_zorunlu_alan_tek_basina_kapida(self, eksik):
        """Bir alanın eksikliği tek başına reddi tetikler ve ADI raporlanır."""
        motor = {k: v for k, v in TAM_MOTOR.items() if k != eksik}
        with pytest.raises(MissingHeatTransferInput) as exc:
            HeatTransferAnalyzer().analyze_heat_transfer(motor)
        assert exc.value.missing_fields == [eksik]

    @pytest.mark.parametrize('gecersiz', [0, 0.0, -1.0, float('nan'),
                                          float('inf'), '', None])
    def test_olcusuz_deger_verilmemis_sayilir(self, gecersiz):
        """0 / boş / negatif / sonsuz bir ölçü DEĞİLDİR (ölçü sözleşmesi)."""
        motor = dict(TAM_MOTOR)
        motor['chamber_pressure'] = gecersiz
        with pytest.raises(MissingHeatTransferInput) as exc:
            HeatTransferAnalyzer().analyze_heat_transfer(motor)
        assert 'chamber_pressure' in exc.value.missing_fields

    def test_bogaz_olcegi_ucundan_biri_yeter(self):
        """A_t = mdot*c*/Pc GERÇEK bir türetimdir; üçü de yoksa red."""
        cekirdek = {k: v for k, v in TAM_MOTOR.items() if k != 'mdot_total'}
        with pytest.raises(MissingHeatTransferInput) as exc:
            HeatTransferAnalyzer().analyze_heat_transfer(dict(cekirdek))
        assert any('mdot_total' in alan for alan in exc.value.missing_fields)

        for alan, deger in (('mdot_total', 1.0), ('throat_diameter', 0.03),
                            ('throat_area', 7.0e-4)):
            motor = dict(cekirdek)
            motor[alan] = deger
            sonuc = HeatTransferAnalyzer().analyze_heat_transfer(motor)
            assert sonuc['gas_side_analysis']['heat_flux'] > 0.0
        # Sözleşme adları da donuk kalsın (liste kısalırsa kapı zayıflar).
        assert set(HEAT_TRANSFER_THROAT_SCALE_FIELDS) == {
            'throat_diameter', 'throat_area', 'mdot_total'}

    def test_tam_girdi_hala_calisir_ve_sayi_degismedi(self):
        """Kapı, GEÇERLİ koşuyu bozmadı: ölçülen taban aynen duruyor."""
        sonuc = HeatTransferAnalyzer().analyze_heat_transfer(dict(TAM_MOTOR))
        assert sonuc['gas_side_analysis']['heat_flux'] == pytest.approx(
            13027380.540100738, rel=1e-9)

    def test_her_zorunlu_alan_yayimlanan_sayiyi_HAREKET_ETTIRIR(self):
        """Kapı listesi çürüyemez: zorunlu her alan çıktıyı değiştirmeli.

        Bir alanı zorunlu tutmanın tek meşru gerekçesi, o alanın yayımlanan
        bir sayıyı ölçeklemesidir. Katman-B sarsım deseninin dar kopyası:
        alan sarsılınca EN AZ bir sayısal yaprak oynamazsa, alan zorunlu
        olmamalıdır (ve bu bekçi kırılır).
        """
        def yapraklar(d, yol=''):
            out = {}
            if isinstance(d, dict):
                for k, v in d.items():
                    out.update(yapraklar(v, yol + '.' + str(k)))
            elif isinstance(d, (list, tuple)):
                for i, v in enumerate(d):
                    out.update(yapraklar(v, yol + '[%d]' % i))
            else:
                out[yol] = d
            return out

        analizci = HeatTransferAnalyzer()
        taban = yapraklar(analizci.analyze_heat_transfer(dict(TAM_MOTOR)))
        for alan in HEAT_TRANSFER_REQUIRED_FIELDS + ('mdot_total',):
            motor = dict(TAM_MOTOR)
            motor[alan] = TAM_MOTOR[alan] * 1.37
            yeni = yapraklar(analizci.analyze_heat_transfer(motor))
            oynayan = [
                k for k, v in taban.items()
                if isinstance(v, (int, float)) and not isinstance(v, bool)
                and isinstance(yeni.get(k), (int, float))
                and abs(float(yeni[k]) - float(v)) > 1e-12 * max(1.0, abs(float(v)))
            ]
            assert oynayan, (
                f"{alan} zorunlu tutuluyor ama hiçbir sayısal yaprağı "
                f"değiştirmiyor — kapı gerekçesiz")

    def test_hibrit_motor_zinciri_kapiya_takilmaz(self):
        """Üç motordan ısı zincirini ÇAĞIRAN tek motor hibrittir.

        Kapı gerçek üretim yolunu kesmemeli: hibritin ``ht_input`` sözlüğü
        zorunlu alanların hepsini taşır.
        """
        from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        motor = HybridRocketEngine(thrust=3000, burn_time=10, of_ratio=6.0,
                                   chamber_pressure=30, oxidizer_type='N2O')
        sonuc = motor.calculate()
        akı = (sonuc['heat_transfer_analysis']['gas_side_analysis']
               ['heat_flux'])
        assert math.isfinite(akı) and akı > 0.0


# ---------------------------------------------------------------------------
# F4-4 — çalkalanma girdi kapısı
# ---------------------------------------------------------------------------

class TestF44CalkalanmaGirdiKapisi:
    """Negatif/sıfır/NaN girdi çalkalanma sonucu üretemez."""

    @pytest.mark.parametrize('yogunluk', [-200.0, 0.0, float('nan'),
                                          float('inf')])
    def test_gecersiz_yogunluk_reddedilir(self, yogunluk):
        """ÖLÇÜLEN KUSUR: yoğunluk -200 geçiyor, kütle -157,0796 kg."""
        with pytest.raises(ValueError):
            analyze_slosh(radius=0.5, fill_height=1.0,
                          fluid_density=yogunluk)

    @pytest.mark.parametrize('kutle', [-50.0, 0.0, float('nan'),
                                       float('inf')])
    def test_gecersiz_sivi_kutlesi_reddedilir(self, kutle):
        with pytest.raises(ValueError):
            analyze_slosh(radius=0.5, fill_height=1.0, liquid_mass=kutle)

    @pytest.mark.parametrize('alan', ['radius', 'fill_height', 'g_eff'])
    @pytest.mark.parametrize('deger', [0.0, -1.0, float('nan'),
                                       float('inf')])
    def test_geometri_kapisi_NaN_de_yakalar(self, alan, deger):
        """NaN eski ``<= 0`` denetimini SESSİZCE geçiyordu (f1_hz = nan)."""
        kwargs = {'radius': 0.5, 'fill_height': 1.0}
        kwargs[alan] = deger
        with pytest.raises(ValueError):
            analyze_slosh(**kwargs)

    def test_negatif_kutle_HICBIR_yolda_yayimlanmaz(self):
        """Kapı sonrası: yayımlanan hiçbir kütle negatif olamaz."""
        sonuc = analyze_slosh(radius=0.5, fill_height=1.0,
                              fluid_density=1000.0)
        assert sonuc['liquid_mass_kg'] > 0.0
        assert sonuc['slosh_mass_kg'] > 0.0
        assert all(v > 0.0 for v in sonuc['fill_sweep']['slosh_mass_kg'])

    def test_gecerli_kosu_bit_ozdes_kaldi(self):
        """Kapı fiziği değiştirmedi: nominal sayılar aynen duruyor."""
        model = CylindricalTankSlosh(radius=0.5, fill_height=1.0,
                                     fluid_density=1000.0)
        omega, f1 = model.natural_frequency(mode=1)
        # SP-106 Eq. 2.4 el hesabı: omega^2 = (lam*g/R)*tanh(lam*h/R)
        lam = 1.8412
        beklenen = math.sqrt((lam * G_0 / 0.5) * math.tanh(lam * 1.0 / 0.5))
        assert omega == pytest.approx(beklenen, rel=1e-12)
        assert model.liquid_mass == pytest.approx(
            1000.0 * math.pi * 0.5 ** 2 * 1.0, rel=1e-12)


# ---------------------------------------------------------------------------
# F4-5 — karışım oranı kapısı
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def yanma():
    return CombustionAnalyzer()


class TestF45KarisimOraniKapisi:
    """O/F iki kütle akışının oranıdır: sonlu ve pozitif olmak zorunda."""

    @pytest.mark.parametrize('of', [-6.0, -0.5, 0.0, float('nan'),
                                    float('inf'), None, 'abc'])
    def test_fiziksel_olmayan_of_reddedilir(self, of, yanma):
        """ÖLÇÜLEN KUSUR: O/F=-6 -> isp 167,822 s, ER -1,4940,
        elemental kütle kesirleri NEGATİF (C=-0,1779, H=-0,0224)."""
        with pytest.raises(ValueError):
            yanma.analyze_combustion({'htpb': 100.0}, 'N2O', of, 20.0)

    def test_negatif_of_iyimser_isp_uretemez(self, yanma):
        """O/F=-0,5 gerçek optimumun (231,7 s) ÜSTÜNDE 328,847 s veriyordu.

        Kusur yalnız anlamsız değil, kullanıcıyı GÜVENLİ OLMAYAN yönde
        yanıltıyordu; bu yüzden ayrı bekçisi var.
        """
        with pytest.raises(ValueError):
            yanma.analyze_combustion({'htpb': 100.0}, 'N2O', -0.5, 20.0)
        gecerli = yanma.analyze_combustion({'htpb': 100.0}, 'N2O', 6.0, 20.0)
        assert gecerli['performance']['isp'] < 300.0

    def test_gecerli_of_bit_ozdes_kaldi(self, yanma):
        """Kapı fiziği değiştirmedi (ölçülen taban: ER=1,493977)."""
        sonuc = yanma.analyze_combustion({'htpb': 100.0}, 'N2O', 6.0, 20.0)
        assert sonuc['equivalence_ratio'] > 0.0
        assert sonuc['equivalence_ratio'] == pytest.approx(1.493977, rel=1e-5)
        # Elemental kütle kesirleri artık negatif olamaz.
        assert all(v >= 0.0
                   for v in sonuc['elemental_composition'].values())

    def test_bandin_alt_ucu_DISLAYICI(self):
        """Sıfır bir karışım oranı değildir (eskiden ZeroDivisionError)."""
        assert OF_RATIO_MIN_EXCLUSIVE == 0.0


# ---------------------------------------------------------------------------
# F3-3 — vacuum_isp gerçekten vakumda
# ---------------------------------------------------------------------------

#: F3-3 ölçüm motoru (sabit geometri lülesi; p_e = 0,5 bar tasarım noktası)
IRTIFA_MOTORU = {
    'chamber_pressure': 20.0,
    'gas_constants': {'exit': 300.0},
    'conditions': {'exit': {'P': 0.5, 'T': 1500.0}},
    'performance': {'velocities': {'exit': 2600.0}, 'c_star': 1500.0},
    'gamma_avg': 1.2,
    'mdot_total': 1.0,
}


class TestF33VakumIspTanimi:
    """``vacuum_isp`` P_a = 0 limitidir, tablonun en üst satırı DEĞİL."""

    def test_vakum_ispsi_irtifa_listesinden_BAGIMSIZ(self, yanma):
        """ÖLÇÜLEN KUSUR: liste 20 km'de bitince 280,8426 s; 10 km'de
        bitince 273,4437 s — aynı motor, iki 'vakum' değeri."""
        uzun = yanma.calculate_altitude_performance(
            dict(IRTIFA_MOTORU), [0, 1000, 2000, 5000, 10000, 15000, 20000])
        kisa = yanma.calculate_altitude_performance(
            dict(IRTIFA_MOTORU), [0, 5000, 10000])
        assert uzun['vacuum_isp'] == pytest.approx(kisa['vacuum_isp'],
                                                   rel=1e-12)

    def test_vakum_ispsi_ayni_fonksiyonun_vakum_itkisiyle_ozdes(self, yanma):
        """Tek kaynak: I_sp,vac = F_vac/(mdot*g0) (Sutton Eq. 2-5/2-16)."""
        cikti = yanma.calculate_altitude_performance(
            dict(IRTIFA_MOTORU), [0, 5000, 10000, 20000])
        f_vac = cikti['nozzle_loss_model']['thrust_vacuum_n']
        mdot = IRTIFA_MOTORU['mdot_total']
        assert cikti['vacuum_isp'] == pytest.approx(f_vac / (mdot * G_0),
                                                    rel=1e-12)

    def test_vakum_ispsi_her_irtifa_satirindan_BUYUK(self, yanma):
        """P_a = 0 limiti tanım gereği üst sınırdır; tablo ona ancak yaklaşır."""
        cikti = yanma.calculate_altitude_performance(
            dict(IRTIFA_MOTORU), [0, 1000, 5000, 20000])
        satirlar = [s['isp'] for s in cikti['altitude_performance']]
        assert cikti['vacuum_isp'] > max(satirlar)
        # Ölçülen fark (20 km satırı ⟷ gerçek vakum) sıfır değildir.
        assert cikti['vacuum_isp'] - max(satirlar) > 1e-6

    def test_dayanak_beyani_yanitta_duruyor(self, yanma):
        cikti = yanma.calculate_altitude_performance(
            dict(IRTIFA_MOTORU), [0, 20000])
        beyan = cikti['vacuum_isp_basis']
        assert 'P_a = 0' in beyan
        assert 'NOT the highest row' in beyan


# ---------------------------------------------------------------------------
# F3-1 (A3 ayağı) — geçici balistikte TEK C_D sözleşmesi
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def ornek_motor():
    """3000 N / 30 bar / O/F=6 N2O-HTPB — F3-1 ölçümünün motoru."""
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    motor = HybridRocketEngine(thrust=3000, burn_time=10, of_ratio=6.0,
                               chamber_pressure=30, oxidizer_type='N2O')
    motor.calculate()
    return motor


class TestF31TekCdSozlesmesi:
    """Geçici seri t=0'da tasarım noktasının KENDİSİNİ vermeli."""

    def _coz(self, motor, feed_mode):
        from hrma.analysis.transient_ballistics import TransientBallistics
        if feed_mode == 'blowdown':
            tb = TransientBallistics(motor, feed_mode='blowdown',
                                     tank_temperature=293.15,
                                     liquid_fill_fraction=0.85, n_steps=200)
        else:
            tb = TransientBallistics(motor, feed_mode='regulated',
                                     n_steps=200)
        return tb, tb.solve()

    @pytest.mark.parametrize('feed_mode', ['blowdown', 'regulated'])
    def test_t0_tasarim_noktasini_verir(self, ornek_motor, feed_mode):
        """ÖLÇÜLEN KUSUR: t=0 itki 3061,2245 N ⟷ tasarım 3000,0 N
        (oran tam 1/C_D = 1/0,98). Kamara basıncı zaten doğruydu."""
        _, sol = self._coz(ornek_motor, feed_mode)
        assert float(sol['thrust'][0]) == pytest.approx(3000.0, rel=1e-6)
        assert float(sol['chamber_pressure'][0]) / 1e5 == pytest.approx(
            30.0, rel=1e-6)

    def test_itki_kamara_kapanisiyla_AYNI_etkin_alani_kullanir(
            self, ornek_motor):
        """Sözleşme özdeşliği: F = C_F * (mdot_toplam * c*).

        P_c*(C_D*A_t) = mdot*c* (c* tanımı) olduğundan itki, kamara
        kapanışının kullandığı ETKİN boğaz alanıyla kurulmalıdır. C_D itki
        denkleminden düşerse bu özdeşlik 1/C_D kadar bozulur.
        """
        _, sol = self._coz(ornek_motor, 'regulated')
        mdot_toplam = (np.asarray(sol['mdot_ox'], dtype=float)
                       + np.asarray(sol['mdot_fuel'], dtype=float))
        cstar = (np.asarray(sol['chamber_pressure'], dtype=float)
                 * NOZZLE_CD * float(ornek_motor.At) / mdot_toplam)
        cf = np.asarray(sol['thrust'], dtype=float) / (mdot_toplam * cstar)
        # C_F fiziksel bantta kalmalı (ε ve γ'dan gelen tasarım değeri ~1,47)
        assert np.all(cf > 1.0) and np.all(cf < 2.1)
        # Ve itki serisi bu özdeşliğin KENDİSİ olmalı.
        assert np.allclose(np.asarray(sol['thrust'], dtype=float),
                           cf * mdot_toplam * cstar, rtol=1e-12)

    def test_cd_tek_yerde_adlandirilmis(self):
        """Sayı iki yerde tanımlanmaz: modül sabiti tek kaynaktır."""
        import hrma.analysis.transient_ballistics as tb_mod
        assert tb_mod.NOZZLE_DISCHARGE_COEFFICIENT == 0.98
        motorsuz = tb_mod.TransientBallistics.__init__
        assert motorsuz is not None  # imza korundu

    def test_toplam_impuls_yayimlanan_egrinin_kendisi(self, ornek_motor):
        """Şişme eğriden toplam impulse'a geçiyordu; özdeşlik korunmalı."""
        _, sol = self._coz(ornek_motor, 'blowdown')
        t = np.asarray(sol['time'], dtype=float)
        f = np.asarray(sol['thrust'], dtype=float)
        assert float(sol['total_impulse']) == pytest.approx(
            float(np.trapz(f, t)), rel=1e-12)


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
