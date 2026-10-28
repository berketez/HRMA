# -*- coding: utf-8 -*-
"""ÖH Dalga-17 / termo-ucus a1 bekçileri.

Her sınıf tek bir defter kalemini kilitler. Sayılar
``docs/scofield/raw/OH/D17/termo-ucus/a1/{once,sonra}.json`` koşumundan
gelir; ters mutasyon kanıtı ``mutasyon.json`` altındadır.
"""
import contextlib
import io

import numpy as np
import pytest
from tests.support.platform_capa import capa_rel

from hrma.analysis.heat_transfer_analysis import (
    DEFAULT_X_CO2, DEFAULT_X_H2O, HeatTransferAnalyzer,
    radiation_composition_source, resolve_radiation_composition)
from hrma.analysis.nozzle_flow_1d import NozzleFlow1D
from hrma.analysis.six_dof_trajectory import BarrowmanAero, SixDOFTrajectory
from hrma.analysis.trajectory_analysis import (
    LIFTOFF_ALTITUDE_EPS_M, TrajectoryAnalyzer, TrajectoryInputError,
    normalize_thrust_curve)


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


_MD_ISI = {'chamber_pressure': 60.0, 'chamber_temperature': 3400.0,
           'chamber_diameter': 0.15, 'chamber_length': 0.5,
           'burn_time': 20.0, 'mdot_total': 8.0}

_MD_YORUNGE = {'thrust': 3000.0, 'burn_time': 5.0,
               'propellant_mass_total': 10.0, 'total_impulse': 15000.0,
               # ÖH D23 / P4B3-24 — tutarsız 'isp' kaldırıldı (bekçi çevirisi): yük
               # yanmayı iki kez ve iki farklı biçimde tarif ediyordu; çözücü artık
               # çelişkiyi reddediyor. Isp bir GİRDİ değil, entegre edilen impuls
               # bütçesinin türevidir ve anahtar yokken ondan türetilir — bu bekçinin
               # ölçtüğü sayıların hiçbiri değişmez (ölçüldü: isp 220/1/1e9 -> apoje
               # BİT-AYNI, once.json P4B3_24).
               }


def _cozucu(**ek):
    ta = TrajectoryAnalyzer()
    ta.set_vehicle_parameters(mass_dry=20.0, diameter=0.15,
                              drag_coefficient=0.5, length=2.5)
    return ta


def _aero():
    return BarrowmanAero(body_diameter=0.15, nose_length=0.4, body_length=2.5,
                         nose_type='ogive', fin_count=4, fin_root_chord=0.15,
                         fin_tip_chord=0.075, fin_span=0.1, fin_sweep=0.05)


# ---------------------------------------------------------------- P4B1-10
class TestP4B110KompozisyonKokeni:
    """Fable-D15 ŞARTı: köken etiketi DEĞER eşitliğinden değil, motor_data'da
    ANAHTARIN verilmiş olmasından kurulur.

    ÖLÇÜLDÜ (once.json K1): ``x_H2O = DEFAULT_X_H2O`` AÇIKÇA verildiğinde
    etiket 'module default … no x_H2O/x_CO2 was supplied' diyordu — iki
    yanlış köken (yalnız-x_H2O vakası dâhil). sonra.json: 0.
    """

    def test_verilen_deger_varsayilana_esit_olsa_bile_koken_cagirandir(self):
        md = dict(_MD_ISI)
        md.update({'x_H2O': DEFAULT_X_H2O, 'x_CO2': DEFAULT_X_CO2})
        gs = _sessiz(HeatTransferAnalyzer().analyze_heat_transfer,
                     md)['gas_side_analysis']
        assert gs['radiation_composition_source'] == \
            'caller supplied x_H2O / x_CO2'
        assert gs['radiation_x_H2O'] == pytest.approx(DEFAULT_X_H2O)

    def test_hic_verilmediginde_modul_varsayilani_denir(self):
        gs = _sessiz(HeatTransferAnalyzer().analyze_heat_transfer,
                     dict(_MD_ISI))['gas_side_analysis']
        assert 'module default' in gs['radiation_composition_source']
        assert 'no x_H2O/x_CO2 was supplied' in \
            gs['radiation_composition_source']

    def test_yalniz_biri_verildiginde_etiket_ikisini_de_adiyla_soyler(self):
        md = dict(_MD_ISI)
        md['x_H2O'] = DEFAULT_X_H2O
        gs = _sessiz(HeatTransferAnalyzer().analyze_heat_transfer,
                     md)['gas_side_analysis']
        kaynak = gs['radiation_composition_source']
        assert 'caller supplied x_H2O' in kaynak
        assert 'module default' in kaynak and 'x_CO2' in kaynak
        # "ikisini de sen verdin" demiyor
        assert kaynak != 'caller supplied x_H2O / x_CO2'

    def test_acik_None_cokme_degil_adli_varsayilandir(self):
        """Taban bu gövdede TypeError atıyordu (once.json K1)."""
        md = dict(_MD_ISI)
        md['x_H2O'] = None
        gs = _sessiz(HeatTransferAnalyzer().analyze_heat_transfer,
                     md)['gas_side_analysis']
        assert gs['radiation_x_H2O'] == pytest.approx(DEFAULT_X_H2O)
        assert 'module default' in gs['radiation_composition_source']

    def test_koken_etiketi_tek_tanim_noktasindan(self):
        assert radiation_composition_source(True, True) == \
            'caller supplied x_H2O / x_CO2'
        assert 'module default' in radiation_composition_source(False, False)
        x, y, kaynak = resolve_radiation_composition({'x_CO2': 0.02})
        assert (x, y) == (DEFAULT_X_H2O, 0.02)
        assert kaynak == radiation_composition_source(False, True)

    def test_eksenel_profil_ayni_cozucuyu_kullanir(self):
        """İki yol AYNI okumayı kullanır (ikinci kural yazılmadı).

        Künye ``thermal_fea/wall_profile`` bloğuna KONMAZ: o bloğu hiçbir
        panel okumuyor ve alan oraya konunca ters-yön dürüstlük borcu
        büyüyor (ölçüldü: tests/test_wave4b_contract.py::
        TestTersYonBorcEnvanteri). Bu bekçi kesirlerin gerçekten profile
        girdiğini kilitler.
        """
        md = dict(_MD_ISI)
        md.update({'x_H2O': 0.60, 'x_CO2': 0.0})
        p1 = _sessiz(HeatTransferAnalyzer().analyze_axial_profile, md,
                     n_stations=11)
        p2 = _sessiz(HeatTransferAnalyzer().analyze_axial_profile,
                     dict(_MD_ISI), n_stations=11)
        assert p1['q_MW'][0] != pytest.approx(p2['q_MW'][0], rel=1e-9)
        assert 'radiation_composition_source' not in p1


# ---------------------------------------------------------------- P15B4-09
class TestP15B409SokBandindaAyrilmaHukmu:
    """İki ürün ucu aynı fiziksel soruya TERS cevap veremez.

    ÖLÇÜLDÜ (D17 once.json K2): P_c = 10 bar, eps = 25, deniz seviyesi ->
    rejim 'normal_shock_in_nozzle', ``separation = None`` (uç "ayrılma yok"
    diyor) ama çözücünün KENDİ Summerfield ölçütü sağlanıyor
    (P_e = 3804,28 Pa < 0,40 x 101325 = 40530 Pa) ve yapışık akışın itkisi
    1297,01 N olarak yayımlanıyordu.

    ÖH D19 — BEKÇİ ÇEVRİLDİ (kusuru koruyordu). D17'de ÖK-06 kilidi
    yüzünden yalnız HÜKÜM düzeltilmiş, SAYI bilerek dokunulmadan
    bırakılmıştı; ``test_hukum_sayilardan_bagimsiz_yayimlanir`` tam olarak
    "yapışık şok itkisi HÂLÂ yayımlanıyor" hâlini kilitliyordu — yani
    kalemin ayakta kalan yarısını koruyordu. ÖK-06 D19 fizik kulvarı için
    kalktı: merdivende Summerfield ölçütü artık normal-şok dalının
    ÖNÜNDE, ölçütün sağlandığı her vaka 'separated'a düşüyor,
    ``separation`` doluyor ve itki ayrılma düzleminden hesaplanıyor.
    Bu sınıf artık YENİ sözleşmeyi kilitler; D17'nin getirdiği alanlar
    (``separation_expected``, ``separation_station_summerfield``,
    ``separation_expected_because``) aynen yerinde durur ve hâlâ
    sınanır. Ayrıntılı ölçüm: tests/test_d19_fizik_a1.py.
    """

    @staticmethod
    def _coz(pc, pa, eps):
        nf = NozzleFlow1D(chamber_pressure=pc, chamber_temperature=3400.0,
                          throat_diameter=0.10, expansion_ratio=eps,
                          gamma=1.20, molecular_weight=22.0,
                          ambient_pressure=pa)
        return _sessiz(nf.solve)

    @pytest.mark.parametrize('pc,eps', [(10e5, 25.0), (8e5, 40.0)])
    def test_sok_bandinda_ayrilma_hukmu_yayimlanir(self, pc, eps):
        r = self._coz(pc, 101325.0, eps)
        reg = r['regime']
        # ÖH D19: etiket artık ölçütten TÜREİYOR, onunla çelişemez.
        assert reg['separation_criterion_met'] is True
        assert reg['type'] == NozzleFlow1D.REGIME_SEPARATED
        assert reg['separation_expected'] is True
        # Ayrılma düzlemi AYNI Summerfield çözücüsünden
        ist = reg['separation_station_summerfield']
        assert ist['station_x_mm'] > 0.0
        assert ist['area_ratio'] > 1.0
        # ...ve itki zincirinin okuduğu alanla AYNI çözüm (tek kaynak).
        assert reg['separation'] is not None
        assert ist['area_ratio'] == reg['separation']['area_ratio']
        assert 'separation_expected_because' in reg
        assert '/api/cfd/nozzle' in reg['separation_expected_because']

    @pytest.mark.parametrize('pc,eps', [(10e5, 25.0), (8e5, 40.0)])
    def test_hukum_ve_sayi_artik_ayni_akisi_tarif_eder(self, pc, eps):
        """ÖH D19: D17'nin AÇILMAYAN yarısı kapandı.

        ESKİ bekçi (``test_hukum_sayilardan_bagimsiz_yayimlanir``)
        "sayılar HÂLÂ yayımlanıyor" diyordu — o sayı yapışık normal-şok
        çözümünün itkisiydi ve ölçüt ayrılmayı söylerken gerçekleşmeyen
        bir akışı tarif ediyordu. Artık itki ayrılma düzleminden gelir:
        ``performance.exit`` süpersonik kalır (yapışık şok çözümünde
        ses-altına düşüyordu) ve ``normal_shock`` bloğu koşulmaz.
        """
        r = self._coz(pc, 101325.0, eps)
        assert r['performance']['thrust_N'] is not None
        assert r['performance']['thrust_N'] > 0.0
        assert r['regime']['normal_shock'] is None
        assert r['performance']['exit']['mach'] > 1.0
        assert r['regime']['separation_expected'] is True
        assert 'does not describe' not in \
            r['regime']['separation_expected_because']
        assert 'SEPARATION IS EXPECTED AND MODELLED' in \
            r['regime']['separation_expected_because']
        # Sınır tabakası ÖLÇÜLEN cidar sürtünme kuvveti geri çekilmedi
        assert r['losses']['friction_drag_integral_bl_N'] > 0.0

    def test_ayrilma_rejimi_ve_saglikli_hal_degismedi(self):
        """Regresyon kilidi: zaten ayrık/az-genişlemiş hâller BİT-AYNI.

        Onarım YALNIZ eski şok bandını taşır; ölçütü zaten sağlayan
        (70 bar, deniz seviyesi) ve hiç sağlamayan (70 bar, ~vakum)
        vakaların itkisi D17'deki sayıyla birebir aynıdır.
        """
        ayr = self._coz(70e5, 101325.0, 25.0)
        assert ayr['regime']['type'] == NozzleFlow1D.REGIME_SEPARATED
        # ÖH D19: ``separation_expected`` artık ölçütün KENDİSİ, dolayısıyla
        # zaten ayrık olan bu vakada da True (D17'de yalnız SHOCK rejiminde
        # True idi). İtki DEĞİŞMEDİ — hüküm alanının tanımı değişti.
        assert ayr['regime']['separation_expected'] is True
        assert ayr['performance']['thrust_N'] == pytest.approx(
            85140.7095933834, rel=1e-9)
        vak = self._coz(70e5, 1.0, 25.0)
        assert vak['regime']['separation_criterion_met'] is False
        assert vak['regime']['separation_expected'] is False
        assert vak['performance']['thrust_N'] == pytest.approx(
            101290.12353112774, rel=1e-9)


# --------------------------------------------------- OH-D16-11 / OH-D15-08
class TestOHD1611CalculateItkiEgrisi:
    """``/calculate`` yörüngesi motorun KENDİ itki eğrisini kullanmalı.

    ÖLÇÜLDÜ (once.json K3): yanıt 201 noktalı bir ``motor.thrust_curve``
    taşıyor, düzlemsel çözücü D16'dan beri eğri okuyabiliyor ama
    ``/calculate`` yolu eğriyi VERMİYORDU: ``trajectory.thrust_input``
    anahtarı yok, apoje 5656,753350 m (dikdörtgen profil). SONRA: künye
    var, apoje 5635,498188 m.
    """

    @pytest.fixture(scope='class')
    def yanit(self):
        from hrma.app import app
        app.config['TESTING'] = True
        c = app.test_client()
        # ÖH 15 Eki (ana model): ölçüm koşulu AÇIKÇA — apoje çapası
        # (6481,69696338075 m) kamara malzemesi 4130 iken ölçüldü; HB10
        # hibrit varsayılanını 304'e çevirince (14 Eki, main) aynı gövde
        # kalınlaşan cidar/ağırlaşan kuru kütleyle 5957,62 m verdi. Malzeme
        # burada sabitlenir; çapa ve tolerans DEĞİŞMEDİ (birebir döndüğü
        # ölçüldü — neden yalnız varsayılan).
        r = _sessiz(c.post, '/calculate', json={
            'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
            'chamber_pressure': 20.0, 'fuel_type': 'htpb',
            'oxidizer_type': 'n2o', 'chamber_material': 'steel_4130'})
        assert r.status_code == 200
        return r.get_json()

    def test_yorunge_egriden_entegre_edilir(self, yanit):
        """ÖH D21 bekci-cevirisi a1 (OH-D19-25) — BOŞ İDDİA KALDIRILDI.

        ESKİ satır ``assert 'AVERAGE' not in ki['basis'].upper() or True``
        ``or True`` yüzünden HER ZAMAN doğruydu (ölçüldü,
        ``once_statik.json`` ``OH-D19-25``: dosyadaki tek boş iddia).
        ``or True`` kaldırılsa KIRMIZI olurdu, çünkü künye 'average'
        sözcüğünü AÇIKLAYICI cümlede taşıyor (ölçüldü,
        ``once_dinamik.json``: "… A single average thrust would flatten
        the peak and change the flight."). Yani dize araması iddiayı
        yanlış yerde arıyordu: künyenin ortalamayı REDDETTİĞİ cümle,
        aramanın "ortalama kullanıldı" kanıtı sayılıyordu.

        Yerine künyenin GERÇEKTEN taahhüt ettiği sözleşme kilitleniyor:
        yörünge itki-zaman EĞRİSİNDEN entegre edildi ve yayımlanan
        toplam impuls o eğrinin kendi (yamuk) integralidir. Dikdörtgen
        profile dönüş bu iddiayı kıramaz-değil, KIRAR.
        """
        traj = yanit['trajectory']
        ki = traj['thrust_input']
        assert ki['source'] == 'thrust_curve'
        assert ki['points'] == 201
        assert 'thrust-time curve' in ki['basis'], (
            f"künye eğriden entegrasyonu söylemiyor: {ki['basis'][:200]!r}")
        assert ki['peak_to_average_ratio'] > 1.0
        # Tepe ≠ ortalama: tek bir ortalama itkiye düşülmedi.
        assert ki['peak_thrust_N'] > ki['average_thrust_N']
        # Toplam impuls EĞRİNİN KENDİ integrali (bağımsız yamuk kuralı).
        egri = yanit['motor']['thrust_curve']
        t, f = egri['time'], egri['thrust']
        yamuk = sum(0.5 * (f[i] + f[i + 1]) * (t[i + 1] - t[i])
                    for i in range(len(t) - 1))
        assert ki['total_impulse_Ns'] == pytest.approx(yamuk, rel=1e-6), (
            f"yayımlanan toplam impuls {ki['total_impulse_Ns']!r}, eğrinin "
            f"yamuk integrali {yamuk!r} — yörünge eğriden entegre "
            f"edilmiyor olabilir")
        # NOT (ölçüldü): ``average_thrust_N * burn_time_s`` toplam
        # impulsun TANIMI olduğu için o çapa totolojiktir — yazıldı,
        # koşuldu (9969,304331 ≡ 9969,304331) ve KALDIRILDI. Dikdörtgen
        # profile dönüşü yakalayan gerçek çapa yukarıdaki yamuk
        # integralidir: eğri düzleştirilirse integral değişir.

    def test_egri_motorun_kendi_egrisidir(self, yanit):
        egri = yanit['motor']['thrust_curve']
        ki = yanit['trajectory']['thrust_input']
        assert ki['points'] == len(egri['time'])
        assert ki['peak_thrust_N'] == pytest.approx(max(egri['thrust']),
                                                    rel=1e-9)

    def test_dikdortgen_profil_apojesi_artik_yayimlanmiyor(self, yanit):
        apoje = (yanit['trajectory']['performance']['trajectory_metrics']
                 ['max_altitude'])
        # ÇAPA YENİLENDİ (ÖH D18 fix-9, 2 Eyl 2026): 5635,498188 → 5631,279779 m
        # (−%0,0749). Değiştiren D18 fizik-a1 (B3-05/B3-02, 779a1c6): hibrit
        # istasyonları kayan-dengeye taşındı → c* −%0,0772, ṁ +%0,0773, toplam
        # impuls +%0,0228; 201 noktalı itki eğrisi (OH-D16-11'in yayımladığı
        # gerçek profil) o kadar kaydı, apoje de onunla. Dikdörtgen-profil
        # apojesinin ARTIK yayımlanmadığı iddiası değişmedi.
        # fix-12: 5631,279779 → 5630,874187 m (−%0,0072) — D19 hibrit B3-12 (bkz. üst not).
        # fix-14 (4 Eyl 2026): 5630,874187 → 5452,670083 m (−%3,16) — D20 fizik-c B1-12
        # (34ab8b9): manşet Isp −%2,36 (kayıp kümesi), toplam impuls onunla düştü;
        # 03_capa_kiyas.txt atıflı, taban kaydı-5 (main b613b2b) ölçümü.
        # fix-15 (4 Eyl 2026): 5452,670083 → 5452,386763 m (−5,2e-5) — D21 hibrit a1 P15B1-04
        # (676a2a5, λ tek kaynak); capa_fark_ozet.json atıflı, main 7776bfb ölçümü.
        # fix-18 (4 Eyl 2026): 5452,386763 → 5497,979838 m (+%0,84) — D22 hibrit a1 (60509f2):
        # OH-D21-03 gerçekleşen L* sabit-noktası + OH-D21-02 transient C_F kayıp kümesi;
        # capa_kiyas.json atıflı, main 2e60b9a ölçümü.
        # ÖH D24 / termo-ucus a2 (P4B3-22) — ÇAPA YENİLENDİ (bekçinin
        # SORUSU değişmedi: dikdörtgen profilin apojesi yayımlanmıyor mu).
        # ÖLÇÜLDÜ: 5497,979838462876 -> 5547,248337693673 (+49,27 m,
        # +%0,896). Sebep TÜRETİLİR: /calculate artık motorun kendi
        # yayımladığı çıkış alanını (``motor_results['exit_area']``) yörünge
        # çözücüsüne geçiriyor, yani güçlü faz itkisi
        # F(h) = F_ref + (P_ref - P_amb(h))*A_e ile irtifayla telafi
        # ediliyor (Sutton & Biblarz, Böl. 3). P_amb yükseldikçe düştüğü
        # için ek impuls POZİTİFTİR ve apoje YÜKSELİR — işaret beklendiği
        # gibi. Önceki sayı, itkiyi yanma boyunca deniz seviyesinde sabit
        # tutan modele aitti (kalem P4B3-22: vakumda +%14,2 eksik itki).
        # V3 yapi-sf (7 Eki 2026) — ÇAPA YENİLENDİ: 5547,248337693673 ->
        # 6585,288902718078 m (+%18,7). Sebep TÜRETİLİR: kuru kütle dökümünün
        # lüle kalemi kamara kütlesinin %30'u (4,2408 kg) idi; artık çizilen
        # katının kütlesi (0,080702 kg, CAD kütle dökümüyle bit-eşit) — kuru
        # kütle 18,5003 -> 14,3401 kg. Kâhin (docs/scofield/raw/OH/V3/
        # yapi-sf/kanit/07_apoje_capa_kahini.py): TABAN ağacında (main
        # 393960ce) yörünge çözücüsü değişmeden, yalnız lüle kalemi tabanın
        # KENDİ CAD kütlesine (0,08070226335623068) sabitlenince apoje
        # 6585,288902718078 m — bağıl fark 0. Değişim yalnız kütle
        # girdisindendir; bekçinin sorusu (dikdörtgen profil apojesi
        # yayımlanmıyor) değişmedi.
        # ÇAPA YENİLENDİ — kitap p1a B16 (karar §28-18 (a)): N₂O 293,15 K
        # doymuş SIVI giriş entalpisi. Kâhin: CEA kök denetimi
        # (docs/scofield/raw/OH/KITAP/p1a/kanit/tur2b/kahin_cea.json) +
        # önce/sonra (p1a rapor §12). Tolerans DEĞİŞMEDİ.
        #   apoje 5547,248337693673 -> 5449,479310908362 m (−%1,76)
        # BİRLEŞİK ÇAPA — V3 yapi-sf 3. tur Ş2-1 (12 Eki 2026; karar §28-37;
        # yapi-sf ⟷ B16 birleşimi, main a6c7e755): iki etki BİRLİKTE.
        #   5449,479310908362 (main, B16) / 6585,288902718078 (yapi-sf) ->
        #   6481,69696338075 m.
        # Kâhin (docs/scofield/raw/OH/V3/yapi-sf/kanit/
        # 12_apoje_capa_kahini_birlesik.py, .json): TABAN ağacında (main
        # a6c7e755; B16 içinde, bu dalın değişikliği yok) yörünge ve motor
        # çözücüsü değişmeden, yalnız kuru kütlenin lüle kalemi tabanın
        # KENDİ CAD kütle dökümündeki çizilen lüleye (0,08104782685280955 kg)
        # sabitlenince apoje 6481,69696338075 m; birleşik ağaçla bağıl fark
        # 0. Denetçinin birleşik ağaç ölçümüyle (6481,69696338075 m) aynı.
        # Tolerans DEĞİŞMEDİ; bekçinin sorusu değişmedi.
        # v3.0.0 (15 Eki) — çapa darwin/arm64'te ölçüldü; CI linux/x86_64'te
        # AYNI kod 1,8e-6 bağıl sapma verdi (koşum 38770162288, ODE).
        # Tolerans referans platformda aynen; başkasında 1e-5.
        # V301/UÇUŞ C-24 (27 Eki) — ÇAPA ÖLÇÜMLE YENİLENDİ: 6481,69696338075
        # -> 14599,14805824316 m. Kayma ZİNCİRİ main ilk-ebeveyn commit'lerinde
        # ölçüldü (git archive + bu düğüm; docs/scofield/raw/OH/V301/ucus/
        # RAPOR.md §C-24):
        #   a0dca0dc0^1 6481,697 -> a0dca0dc0 (19 Eki, v301/port-kamara:
        #     yanma sonu port grain dış çapına ulaşır, kaynaksız
        #     D_ch = 1,5·√N·… söküldü) 15081,555 m — motor küçüldü/hafifledi;
        #   77d64c641 (26 Eki, H-termal: cidar üç bölge) 16300,040 m;
        #   74b55500a (26 Eki, H-PANEL: η_c* 0,89 kaynaklı varsayılan)
        #     14599,148 m.
        # Bu istek ARAÇ GİRDİSİ TAŞIMAZ: yörünge motoru tek başına uçurur
        # (kuru kütle = motor atıl alt sınırı 0,9448 kg, çap = kasa 57,4 mm,
        # Cd 0,5; vehicle_parameters). Bağımsız 1-B nokta kütle kâhini
        # (c24_apoje_kahin.py: aynı kütle/alan/Cd/impuls, sabit itki, ISA)
        # ≈ 16,4 km verir — mertebe aynı (−%11 fark kâhinin sabit itki /
        # telafisiz / sabit Cd basitliğinden). Eski 6,48 km çapası 14,34 kg'lık
        # ESKİ (aşırı büyük kamaralı) motora aitti. Bekçinin sorusu
        # (dikdörtgen profil apojesi yayımlanmıyor) DEĞİŞMEDİ; tolerans aynı.
        assert apoje == pytest.approx(14599.14805824316,
                                      rel=capa_rel(1e-6, 1e-5))
        assert apoje != pytest.approx(5656.753349589398, rel=1e-6)


class TestOHD1611TekKaynakEgriSozlesmesi:
    """6-DOF doğrulama zinciri ``normalize_thrust_curve``in İKİNCİ KOPYASIYDI.

    Kopya artan-olmayan zamanı, negatif itkiyi ve sıfır impulsü KABUL
    ediyordu; kardeşi reddediyor. Artık tek kural kümesi var.
    """

    @pytest.mark.parametrize('egri,gerekce', [
        ({'time': [0.0, 1.0, 0.5], 'thrust': [10.0, 10.0, 10.0]},
         'time_not_increasing'),
        ({'time': [0.0, 1.0], 'thrust': [10.0, -5.0]}, 'negative_thrust'),
        ({'time': [0.0, 1.0], 'thrust': [0.0, 0.0]}, 'zero_impulse'),
        # ÖH D18 / OH-D15-08 ŞART (Fable-D16 termo-ucus): negatif zaman
        # kapısı ``normalize_thrust_curve``e kondu; tek kaynak olduğu için
        # ret 6-DOF tarafına da inmeli. Bu parametre o inişi kilitler.
        ({'time': [-0.1, 0.0, 1.0], 'thrust': [0.0, 100.0, 100.0]},
         'negative_time'),
    ])
    def test_bozuk_egri_6dof_tarafinda_da_reddedilir(self, egri, gerekce):
        with pytest.raises(TrajectoryInputError) as exc:
            SixDOFTrajectory(aero=_aero(), dry_mass=20.0,
                             propellant_mass=10.0, thrust_curve=egri)
        alanlar = [p['field'] for p in exc.value.problems]
        sebepler = [p['reason'] for p in exc.value.problems]
        assert alanlar == ['thrust_curve']
        assert sebepler == [gerekce]

    def test_atilan_hata_hala_ValueError_turevidir(self):
        """Eski ``ValueError`` yakalayan çağıranların davranışı değişmez."""
        assert issubclass(TrajectoryInputError, ValueError)
        with pytest.raises(ValueError):
            SixDOFTrajectory(aero=_aero(), dry_mass=20.0,
                             propellant_mass=10.0,
                             thrust_curve={'time': [0.0], 'thrust': [1.0]})

    def test_saglikli_egri_iki_cozucude_ayni_normalize_edilir(self):
        egri = {'time': [0.5, 1.0, 2.0], 'thrust': [100.0, 300.0, 50.0]}
        t, F, imp = normalize_thrust_curve(egri)
        s = SixDOFTrajectory(aero=_aero(), dry_mass=20.0,
                             propellant_mass=10.0, thrust_curve=egri)
        assert np.allclose(s._t_thrust, t)
        assert np.allclose(s._F_thrust, F)
        assert s._impulse == pytest.approx(imp, rel=0, abs=0)
        assert t[0] == 0.0            # geç başlayan eğri başa taşınır


# ---------------------------------------------------------------- P4B3-12
class TestP4B312DurustlukAlanlariDusurulmez:
    """Çözücünün ürettiği hüküm-nitelendiricileri uç gövdesinde durmalı.

    ÖLÇÜLDÜ (once.json K4, ``t_max = 3 s``): çözücü dört alan üretiyor,
    yanıt DÖRDÜNÜ DE düşürüyordu; ``max_speed = 288,167 m/s`` bir tepe
    gibi okunuyordu (gerçekte alt sınır).
    """

    GOVDE = {'body_diameter': 0.15, 'body_length': 2.5, 'nose_length': 0.4,
             'dry_mass': 20.0, 'propellant_mass': 10.0, 'cd0': 0.5,
             'thrust': 3000.0, 'burn_time': 5.0, 'rail_length': 5.0,
             't_max': 3.0}

    @pytest.fixture(scope='class')
    def istemci(self):
        from hrma.app import app
        app.config['TESTING'] = True
        return app.test_client()

    def test_kesilen_kosumda_alt_sinir_damgasi_gorunur(self, istemci):
        r = _sessiz(istemci.post, '/api/six-dof-analysis', json=self.GOVDE)
        assert r.status_code == 200
        s = r.get_json()['summary']
        assert s['peak_values_are_lower_bounds'] is True
        assert s['t_max_s'] == pytest.approx(3.0)
        assert s['apogee'] is None
        assert s['max_speed'] == pytest.approx(288.16739076563454, rel=1e-6)

    def test_cozucu_hukmu_yanitta_ADIYLA_durur(self, istemci):
        """Kalemin ``converged``/``solver_message`` ayağı ÖLÇÜMLE geçersiz.

        İkisi de yayımlanıyor — ``stability_basis`` bloğunda, kardeşi
        ``thermal_basis`` ile aynı yerde. Özete kopyalamak
        ``tests/test_z5s_hukum_kanali.py::
        test_kunye_UST_SEVIYEDE_ozet_kumesi_borcu_buyutmuyor`` ile kilitli
        yerleşimi bozar ve ters-yön borç envanterini büyütür; o yüzden
        bekçi yerleşimi de kilitler.
        """
        r = _sessiz(istemci.post, '/api/six-dof-analysis', json=self.GOVDE)
        j = r.get_json()
        kunye = j['stability_basis']
        assert kunye['solver_converged'] is True
        assert isinstance(kunye['solver_message'], str)
        assert kunye['solver_message']
        assert 'converged' not in j['summary']
        assert 'solver_message' not in j['summary']

    def test_saglikli_kosumda_kesilme_alanlari_ICAT_EDILMEZ(self, istemci):
        govde = dict(self.GOVDE)
        govde['t_max'] = 200.0
        r = _sessiz(istemci.post, '/api/six-dof-analysis', json=govde)
        s = r.get_json()['summary']
        assert 'peak_values_are_lower_bounds' not in s
        assert 't_max_s' not in s
        assert s['apogee'] is not None


# ---------------------------------------------------------------- P4B3-13
class TestP4B313KalkmayanArac:
    """Rampadan hiç kalkmayan araç bir uçuş sonucu üretmez.

    ÖLÇÜLDÜ (once.json K5): T/W = 0,3399 -> ``apogee = 0,0``,
    ``stable = True``, kalkışa dair tek alan yok.
    """

    @staticmethod
    def _coz(thrust, t_max=20.0):
        s = SixDOFTrajectory(aero=_aero(), dry_mass=20.0,
                             propellant_mass=10.0, thrust=thrust,
                             burn_time=5.0, cd0=0.5, rail_length=5.0)
        return _sessiz(s.solve, t_max=t_max)

    def test_kalkmayan_aracta_hukum_yayimlanmaz(self):
        r = self._coz(100.0)
        assert r['lifted_off'] is False
        assert r['apogee'] is None
        assert r['apogee_time'] is None
        assert r['stable'] is None
        assert r['thrust_to_weight_at_ignition'] == pytest.approx(
            0.3399054043259761, rel=1e-9)
        assert 'NO LIFTOFF' in r['apogee_withheld_because']

    def test_saf_geometri_korunur(self):
        r = self._coz(100.0)
        for ad in ('static_margin_full', 'static_margin_empty', 'x_cp',
                   'cn_alpha'):
            assert r[ad] is not None

    def test_kalkan_arac_bit_ayni_kalir(self):
        r = self._coz(3000.0, t_max=200.0)
        assert r['lifted_off'] is True
        assert r['stable'] is True
        assert 'apogee_withheld_because' not in r
        assert r['apogee'] == pytest.approx(4863.34220545963, rel=1e-6)

    def test_kalkis_esigi_tek_kaynaktan(self):
        """İki modül aynı eşiği kullanır (ikinci sayı tanımlanmaz)."""
        import hrma.analysis.six_dof_trajectory as sd
        assert sd.LIFTOFF_ALTITUDE_EPS_M is LIFTOFF_ALTITUDE_EPS_M

    def test_uc_kalkis_hukmunu_gecirir(self):
        from hrma.app import app
        app.config['TESTING'] = True
        r = _sessiz(app.test_client().post, '/api/six-dof-analysis', json={
            'body_diameter': 0.15, 'body_length': 2.5, 'nose_length': 0.4,
            'dry_mass': 20.0, 'propellant_mass': 10.0, 'cd0': 0.5,
            'thrust': 100.0, 'burn_time': 5.0, 'rail_length': 5.0,
            't_max': 20.0})
        s = r.get_json()['summary']
        assert s['lifted_off'] is False
        assert s['apogee'] is None and s['stable'] is None
        assert 'NO LIFTOFF' in s['apogee_withheld_because']


# ---------------------------------------------------------------- P4B3-14
class TestP4B314RuzgarBoyutu:
    """Düzlemsel çözücü rüzgârın çapraz bileşenini TAŞIYAMAZ; sessiz kalamaz.

    ÖLÇÜLDÜ (once.json K6): 15 m/s / 90° -> menzil 735,3229283656398 m,
    rüzgârsız koşum 735,3229283656397 m (1 ULP) — rüzgârın TAMAMI düşüyor
    ve hiçbir alan bunu söylemiyordu.
    """

    def test_capraz_bilesen_olculur_ve_beyan_edilir(self):
        w = TrajectoryAnalyzer._wind_components(15.0, np.radians(90.0))
        assert w['in_plane_component_m_s'] == pytest.approx(0.0, abs=1e-12)
        assert w['cross_plane_component_m_s'] == pytest.approx(-15.0)
        assert w['cross_plane_modelled'] is False
        assert w['cross_plane_significant'] is True
        assert 'PLANAR' in w['basis']
        assert '/api/six-dof-analysis' in w['basis']

    def test_duzlem_ici_bilesen_ile_entegre_edilen_ayni_kaynaktan(self):
        for deg in (0.0, 45.0, 137.0):
            rad = np.radians(deg)
            vx, vz = TrajectoryAnalyzer._wind_vector(15.0, rad)
            w = TrajectoryAnalyzer._wind_components(15.0, rad)
            assert w['in_plane_component_m_s'] == vx
            # ÖH D24 / termo-ucus a2 (OH-Z5-02) — BEKÇİ ÇEVRİLDİ.
            # Eski satır ``assert w['vertical_component_m_s'] == vz`` idi ve
            # bir UYDURMA SABİTİ sözleşme diye kilitliyordu: ``vz`` HER
            # ÇAĞRIDA 0,0'dır çünkü ``_wind_vector`` düşey bileşeni
            # hesaplamaz, yatay rüzgâr KABULÜNÜ uygular. Beş (hız, yön)
            # çiftinde ölçüldü (a2/once.json K6): değer hep 0,0.
            # ``test_field_wiring_layer_b::test_no_fabricated_constant_outputs``
            # yaprağı bu yüzden sayıyordu. Sayı kalktı, KABUL yayımlanıyor.
            assert vz == 0.0, 'yatay rüzgâr kabulü değişmiş'
            assert 'vertical_component_m_s' not in w
            assert w['vertical_component_modelled'] is False

    def test_90_derece_kosumunda_menzil_alt_sinir_damgali(self):
        ta = _cozucu()
        r = _sessiz(ta.calculate_trajectory, dict(_MD_YORUNGE),
                    {'launch_angle': 85.0, 'wind_speed': 15.0,
                     'wind_direction': 90.0})
        tm = r['performance']['trajectory_metrics']
        assert tm['range_distance_is_lower_bound'] is True
        assert 'IN-PLANE range only' in tm['range_distance_basis']
        assert r['wind_model']['cross_plane_dropped'] is True

    def test_duzlem_ici_ruzgar_alt_sinir_DEGILDIR(self):
        """Gürültü tabanı: sin(180°) = −1,22e−16 hüküm üretmez."""
        for deg in (0.0, 180.0):
            ta = _cozucu()
            r = _sessiz(ta.calculate_trajectory, dict(_MD_YORUNGE),
                        {'launch_angle': 85.0, 'wind_speed': 15.0,
                         'wind_direction': deg})
            tm = r['performance']['trajectory_metrics']
            assert 'range_distance_is_lower_bound' not in tm
            assert r['wind_model']['cross_plane_significant'] is False

    def test_ruzgarsiz_kosum_bit_ayni(self):
        ta = _cozucu()
        # ÖH D22 / OH-D18-05: menzil iniş NOKTASIDIR, yani bir kurtarma
        # sistemi ister. 735,32… sayısı eskiden modül sabitinden gelen
        # 2,0 m²'lik uydurma paraşütle üretiliyordu; alan artık AÇIKÇA
        # isteniyor ve sayı BİT-AYNI kalıyor (regresyon kilidi korundu).
        # Kardeş TestP4B315InisHiziDatumu bu dosyada zaten aynı deseni
        # kullanıyor (paraşüt üçlüsünü açıkça gönderiyor).
        r = _sessiz(ta.calculate_trajectory, dict(_MD_YORUNGE),
                    {'launch_angle': 85.0, 'wind_speed': 0.0,
                     'parachute_area': 2.0})
        tm = r['performance']['trajectory_metrics']
        # v3.0.0 (15 Eki) — çapa darwin/arm64'te ölçüldü; CI linux/x86_64'te
        # AYNI kod 3,6e-7 bağıl sapma verdi (koşum 38770162288, ODE).
        # Tolerans referans platformda aynen; başkasında 1e-6.
        assert tm['range_distance'] == pytest.approx(735.3229283656397,
                                                     rel=capa_rel(1e-9, 1e-6))
        assert 'range_distance_is_lower_bound' not in tm


# ---------------------------------------------------------------- P4B3-15
class TestP4B315InisHiziDatumu:
    """Ortalama iniş hızının payı ve paydası AYNI datumdan olmalı.

    ÖLÇÜLDÜ (once.json K7): saha 1500 m -> yayımlanan 16,836785 m/s,
    saha datumuyla gerçek 13,117193 m/s (+%28,36). Deniz seviyesinde iki
    sayı birebir aynıdır.
    """

    @staticmethod
    def _kos(kot):
        ta = _cozucu()
        return _sessiz(ta.calculate_trajectory, dict(_MD_YORUNGE),
                       {'launch_angle': 88.0, 'launch_altitude': kot,
                        'parachute_area': 2.0, 'parachute_cd': 1.4,
                        'parachute_deploy_delay': 1.0})

    def test_saha_kotunda_hiz_saha_datumundan(self):
        r = self._kos(1500.0)
        rec = r['recovery']
        apoje = r['performance']['trajectory_metrics']['max_altitude']
        beklenen = (apoje - 1500.0) / rec['descent_duration_s']
        assert rec['mean_descent_rate_m_s'] == pytest.approx(beklenen,
                                                             rel=1e-12)
        assert rec['mean_descent_rate_m_s'] == pytest.approx(13.11719258630117,
                                                             rel=1e-6)
        assert rec['ground_level_m'] == pytest.approx(1500.0)
        assert rec['descent_height_m'] == pytest.approx(apoje - 1500.0,
                                                        rel=1e-12)
        assert '1500' in rec['mean_descent_rate_basis']

    def test_deniz_seviyesinde_bit_ayni(self):
        r = self._kos(0.0)
        rec = r['recovery']
        # v3.0.0 (15 Eki) — çapa darwin/arm64'te ölçüldü; CI linux/x86_64'te
        # AYNI kod 3,9e-8 bağıl sapma verdi (koşum 38770162288, ODE).
        # Tolerans referans platformda aynen; başkasında 1e-6.
        assert rec['mean_descent_rate_m_s'] == pytest.approx(
            12.012425595851562, rel=capa_rel(1e-9, 1e-6))

    def test_datum_apojenin_ustunde_ise_sayi_uydurulmaz(self):
        """Yükseklik pozitif değilse hız YAYIMLANMAZ (sıfır/negatif değil)."""
        ta = _cozucu()
        ta.ground_level_m = 99999.0
        ozet = ta._recovery_summary(
            {'time': np.array([0.0, 1.0])},
            {'time': np.array([0.0, 1.0]), 'position_z': np.array([0.0, 10.0])},
            {'recovery_deployed': True, 'landing_time': 5.0,
             'parachute_deploy_delay_s': 1.0},
            {})
        assert ozet['mean_descent_rate_m_s'] is None
        assert ozet['descent_height_m'] == pytest.approx(10.0 - 99999.0)
