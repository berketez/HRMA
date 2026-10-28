"""ÖH Dalga-18 · sıvı kulvarı · aşama 1 — onarım bekçileri.

Her sınıf TEK kalemi tutar. İddialar ters-mutasyonla ölçülmüştür
(``docs/scofield/raw/OH/D18/sivi/a1/mutasyon.json``): onarım geçici olarak
geri alındığında ilgili testler KIRMIZI olur.

Kalemler
--------
OH-Z5-01  (Fable-D16 ŞART) ``T_recovery_basis`` ve
          ``gas_side_coefficient_chamber_basis`` ``cooling_system.
          wall_temperature_source``a bağlı DEĞİLDİ: cidar 1B süperkritik
          marşla ÇÖZÜLDÜĞÜNDE bile künye 'bu koşumun Bartz kamara
          katsayısını döndürür' diyordu — oysa o dalda akı marşın ısı
          payından, cidar marşın TEPE değerinden gelir.
P3B2-07   Sapma verimi λ aynı yanıtta ÜÇ değer (0,985000 uygulanan /
          0,994508 nozzle_angles / 0,982963 irtifa döngüsü).
P3B2-08   Yanma verimi aynı yanıtta 0,98 (enjektör tipinden uydurma) ⟷
          1,000 (teslim zinciri) ve iki çelişik künye.
P3B2-09   Düşük Pc'de ε sessizce 2,5 tabanına kırpılıyor; 'OPTIMIZED /
          pe = pa' iddiası ayakta kalıyor, çıkış basıncı iki değer.
P3B2-10   Film + rejeneratif soğutucu debisi toplamı yakıtın %120'si.
P3B2-11   Lüle içi statik sıcaklık için beyansız uydurma sabit
          (T/T_c = 1/(1+(γ-1)·0,1·ln(A/A_t))) + 'Upstream of throat'
          etiketli hiç çalışmayan dal.
P3B2-12   Isp, C_F ve c* ders kitabı özdeşliğini %2,0408 ile tutmuyor;
          uzlaştıran C_D = 0,98 yanıtta hiç yayımlanmıyor.
P3B3-07   Pompa kartı kendi içinde tutarsız: design_power, aynı karttaki
          H/η/Q'dan çıkan güçle %24,77 uyuşmuyor.
P3B3-08   Reddedilen ``turbopump_efficiency`` girdisi çıktıda 'user input'
          künyesiyle duruyor.
P3B3-09   Besleme hattının itici cinsi YOĞUNLUKTAN tahmin ediliyor
          (``'oxidizer' if density > 900 else 'fuel'``); yoğunluğu 900'ün
          üstündeki bir yakıtta çap oksitleyici yoğunluğuyla seçiliyor.
"""
import math

import pytest

from hrma.constants import LAMBDA_BELL
from hrma.engines.liquid_rocket_engine import (
    BURN_TIME_DEFAULT_S,
    EXPANSION_RATIO_SOLVER_MAX,
    EXPANSION_RATIO_SOLVER_MIN,
    LiquidRocketEngine,
)

G0 = 9.80665


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _yuk(**ek):
    # ÖH D36 / LU-1 (ÇEVRİLEN BEKÇİ, onemli2-sivi a2): ``/calculate_liquid``
    # yanma süresini ``max_burn_duration`` alanından okur; aşağıdaki
    # ``burn_time`` anahtarını HİÇ okumaz (ölçüldü: yanıtın künyesi LU-1
    # öncesinde 'assumed 300 s burn' idi). Motor artık süre varsaymadığı
    # için tank kartı ``not_modelled`` dönüyor ve pompa güç özdeşliği ile
    # hat yoğunluğu bekçileri (3 düğüm) yoğunluğu TANK KARTINDAN okuduğu
    # için ``KeyError`` ile düşüyordu. Süre motorun kendi sabitinden AÇIKÇA
    # verilir (sayı burada yazılmaz): sayılar LU-1 öncesiyle birebir aynı.
    y = {
        'motor_name': 'D18-SIVI-A1', 'thrust': 25000.0, 'burn_time': 30.0,
        'max_burn_duration': BURN_TIME_DEFAULT_S,
        'chamber_pressure': 60.0, 'mixture_ratio': 2.3,
        'fuel_type': 'rp1', 'oxidizer_type': 'lox',
        'cooling_type': 'regenerative',
    }
    y.update(ek)
    return y


def _post(client, **ek):
    r = client.post('/calculate_liquid', json=_yuk(**ek))
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def taban(client):
    """RP-1/LOX 25 kN Pc=60 rejeneratif — cidar VARSAYIM (marşsız)."""
    return _post(client)


@pytest.fixture(scope='module')
def marsli(client):
    """ŞART fikstürü: methane/LOX 25 kN Pc=100 rejeneratif — cidar ÇÖZÜLÜR."""
    return _post(client, chamber_pressure=100.0, fuel_type='methane',
                 mixture_ratio=3.4)


# ---------------------------------------------------------------------------
# OH-Z5-01 — Fable-D16 ŞART
# ---------------------------------------------------------------------------
class TestZ501KunyelerCidarKaynaginaBagli:

    def test_marssiz_kosumda_T_recovery_sonlu_pozitif_DEGER(self, taban):
        """ŞART (3): yolun VARLIĞI değil, sonlu pozitif DEĞER sayılır."""
        gaz = taban['heat_transfer_analysis']['gas_side_analysis']
        t_rec = gaz.get('T_recovery_K')
        assert isinstance(t_rec, (int, float)) and not isinstance(t_rec, bool)
        assert math.isfinite(t_rec) and t_rec > 0.0, (
            f'T_recovery yayımlanmıyor ya da sayı değil: {t_rec!r}')
        assert t_rec == pytest.approx(taban['chamber_temperature'], rel=1e-12)

    def test_T_recovery_kaynagi_cidar_kaynagini_izler(self, taban, marsli):
        """ŞART (1): künye ``wall_temperature_source``a BAĞLI."""
        for yanit, beklenen in ((taban, 'assumed'), (marsli, 'solved')):
            htx = yanit['heat_transfer_analysis']
            assert htx['wall_analysis']['wall_temperature_solved'] is (
                beklenen == 'solved')
            assert htx['gas_side_analysis']['T_recovery_source'] == beklenen

    def test_marsli_kunye_marsin_T_aw_zincirini_soyler(self, marsli):
        """ŞART (1): marşlı koşumda künye T_aw(x) marşını anmalı."""
        basis = marsli['heat_transfer_analysis']['gas_side_analysis'][
            'T_recovery_basis']
        assert 'march' in basis.lower(), basis
        assert 'T_aw' in basis, basis

    def test_marsli_kosumda_kamara_katsayisi_yayimlanmaz(self, marsli):
        """ŞART (1+2): çözülmüş cidarda katsayı NOT_PUBLISHED."""
        gaz = marsli['heat_transfer_analysis']['gas_side_analysis']
        assert gaz['gas_side_coefficient_chamber_status'] == 'NOT_PUBLISHED'
        assert gaz['gas_side_coefficient_chamber'] is None

    def test_marsli_kunye_Bartz_kamara_iddiasi_tasimaz(self, marsli):
        """ŞART (2): çözülmüş cidarda 'Bartz kamara katsayısı' iddiası YOK."""
        gaz = marsli['heat_transfer_analysis']['gas_side_analysis']
        basis = str(gaz['gas_side_coefficient_chamber_basis'])
        assert 'Bartz chamber coefficient' not in basis, basis
        assert 'march' in basis.lower(), basis

    def test_marsli_etkin_katsayi_AYRI_adla_durur(self, marsli):
        """Sayı kaybolmuyor: etkin katsayı kendi adıyla ve künyesiyle."""
        gaz = marsli['heat_transfer_analysis']['gas_side_analysis']
        etkin = gaz['gas_side_effective_chamber_coefficient_if_march']
        assert isinstance(etkin, float) and etkin > 0.0
        assert 'EFFECTIVE' in gaz[
            'gas_side_effective_chamber_coefficient_if_march_basis']

    def test_marssiz_kosumda_kamara_katsayisi_yayimlanir(self, taban):
        """Varsayım cidarda katsayı Bartz'tır ve YAYIMLANIR (kazanım korunur)."""
        gaz = taban['heat_transfer_analysis']['gas_side_analysis']
        assert gaz['gas_side_coefficient_chamber_status'] == 'PUBLISHED'
        assert gaz['gas_side_coefficient_chamber'] > 0.0
        assert 'Bartz chamber coefficient' in gaz[
            'gas_side_coefficient_chamber_basis']

    def test_kamara_h_gas_Bartz_alan_bandinda(self, taban):
        """ŞART (3): totolojiden çık — oran Bartz (A_t/A_c)^0,9·σ bandında.

        Bartz eksenel ölçeklemesi h(x) = h_boğaz·(A_t/A)^0,9 ve σ hazne ile
        boğazda farklıdır; oran σ_kamara/σ_boğaz payıyla alan oranının
        etrafındadır. Bant ±%20 alınır (σ oranı ölçüldü ~1,02).
        """
        htx = taban['heat_transfer_analysis']
        gaz = htx['gas_side_analysis']
        h_c = gaz['gas_side_coefficient_chamber']
        h_t = gaz['gas_side_coefficient_throat']
        assert h_c and h_t
        # V301/L-KARBON (26 Eki): LOX/RP-1 karbon birikimi uygulandığında
        # iki yayımlanan katsayı TOPLAM iletkenliktir, h_gc = 1/(1/h_g + R_d)
        # (SP-125 Eş. 4-18). Bartz alan ölçeklemesi h_g üzerindedir; R_d
        # yayımlanan dirençlerle (cooling_system.carbon_deposit) çıkarılır.
        # Birikim yoksa R_d = 0 ve iddia eskisiyle aynıdır (bant aynı).
        cd = taban['cooling_system'].get('carbon_deposit') or {}
        if cd.get('applied'):
            h_c = 1.0 / (1.0 / h_c - cd['resistance_chamber_m2K_W'])
            h_t = 1.0 / (1.0 / h_t - cd['resistance_throat_m2K_W'])
        d_c = taban['cooling_system']['chamber_diameter'] / 1000.0   # m
        d_t = taban['nozzle_angles']['throat_diameter_mm'] / 1000.0  # m
        alan_orani = (d_t / d_c) ** 2
        beklenen = alan_orani ** 0.9
        assert h_c / h_t == pytest.approx(beklenen, rel=0.20), (
            f'h_kamara/h_boğaz={h_c / h_t:.5f} Bartz alan ölçeklemesinin '
            f'(A_t/A_c)^0.9={beklenen:.5f} bandının dışında')


# ---------------------------------------------------------------------------
# P3B2-07 — sapma verimi λ TEK kaynak
# ---------------------------------------------------------------------------
class TestP3B207SapmaVerimiTekKaynak:

    def test_nozzle_angles_lambda_uygulanan_lambda_ile_ayni(self, taban):
        lam = taban['nozzle_angles']['divergence_efficiency']
        assert lam == pytest.approx(float(LAMBDA_BELL), rel=1e-12), (
            'Yayımlanan λ, çan konturunda GEÇERSİZ konik bağıntıdan '
            'geliyor; uygulanan λ ile ayrışmış.')
        assert taban['nozzle_angles']['lambda_divergence_applied'] == (
            pytest.approx(lam, rel=1e-12))

    def test_lambda_kunyesi_kontur_adini_tasir(self, taban):
        src = taban['nozzle_angles']['divergence_efficiency_source']
        assert src and 'bell' in src.lower()

    def test_verim_dokumu_ayni_lambdayi_kullanir(self, taban):
        eb = taban['efficiency_breakdown']['efficiency_breakdown']
        assert eb['divergence_loss'] == pytest.approx(
            float(LAMBDA_BELL) * 100.0, rel=1e-12)

    def test_irtifa_satiri_nozul_tipinden_bagimsiz_15_derece_KULLANMAZ(
            self, client, taban):
        """İrtifa döngüsünün λ'sı konturla DEĞİŞMELİ.

        Kusur hâlinde döngü sabit 15° konik λ'sını (0,982963) kullanıyordu
        ve konik ⟷ çan koşumları aynı çıkıyordu.
        """
        konik = _post(client, nozzle_type='conical')
        lam_bell = taban['nozzle_angles']['divergence_efficiency']
        lam_konik = konik['nozzle_angles']['divergence_efficiency']
        assert lam_bell != pytest.approx(lam_konik, rel=1e-9)
        # İrtifa satırının η_lüle ORANI λ oranının ta kendisi olmalı:
        # η = λ·η_sınır·η_ısı·η_kinetik ve diğer üç terim iki konturda
        # neredeyse aynıdır (yalnız boğaz Reynolds'u ~%0,1 kayar; ölçüldü:
        # λ oranı 1,0020724 ⟷ η oranı 1,0020720). Döngü sabit 15° konik λ
        # kullansaydı η oranı 1'e (yalnız sınır tabaka farkına) düşerdi.
        n_bell = taban['altitude_performance'][0]['nozzle_efficiency']
        n_konik = konik['altitude_performance'][0]['nozzle_efficiency']
        assert n_bell / n_konik == pytest.approx(lam_bell / lam_konik,
                                                 rel=1e-5), (
            f'η_lüle oranı {n_bell / n_konik:.7f}, λ oranı '
            f'{lam_bell / lam_konik:.7f} — irtifa döngüsü nozul tipinden '
            'BAĞIMSIZ bir λ kullanıyor.')

    def test_ad_deger_sozlesmesi_yazili(self, taban):
        """İki blok aynı anahtar adını taşıyor; hangisinin ne olduğu yazılı."""
        eb = taban['efficiency_breakdown']
        assert 'EFFICIENCY' in eb['efficiency_breakdown_unit']
        assert 'loss' in eb['loss_breakdown_unit']
        for k, v in eb['loss_breakdown'].items():
            assert v + eb['efficiency_breakdown'][k] == pytest.approx(
                100.0, abs=1e-9)


# ---------------------------------------------------------------------------
# P3B2-08 — yanma verimi TEK kaynak
# ---------------------------------------------------------------------------
class TestP3B208YanmaVerimiTekKaynak:

    def test_enjektor_ve_yanma_bloklari_ayni_degeri_yayimlar(self, taban):
        enj = taban['injection_system']['combustion_efficiency']
        yanma = taban['combustion_analysis']['combustion_analysis'][
            'combustion_efficiency']
        assert enj == pytest.approx(yanma / 100.0, rel=1e-12), (
            f'injection_system {enj} ⟷ combustion_analysis {yanma}% — aynı '
            'büyüklük iki değer taşıyor.')

    def test_kunye_de_tektir(self, taban):
        a = taban['injection_system']['combustion_efficiency_source']
        b = taban['combustion_analysis']['combustion_analysis'][
            'combustion_efficiency_source']
        assert a == b, f'İki çelişik künye: {a!r} ⟷ {b!r}'
        assert 'estimated from the injector type' not in a, (
            'Enjektör tipinden uydurulan yanma verimi geri gelmiş.')

    def test_birim_sozlesmesi_yazili(self, taban):
        assert taban['injection_system'][
            'combustion_efficiency_unit'] == 'fraction'
        assert taban['injector_design'][
            'combustion_efficiency_unit'] == 'fraction'
        assert taban['combustion_analysis']['combustion_analysis'][
            'combustion_efficiency_unit'] == 'percent'

    def test_kullanici_girdisi_her_iki_blogu_da_surukler(self, client):
        y = _post(client, combustion_efficiency=93.0)
        assert y['injection_system']['combustion_efficiency'] == (
            pytest.approx(0.93, rel=1e-9))
        assert y['combustion_analysis']['combustion_analysis'][
            'combustion_efficiency'] == pytest.approx(93.0, rel=1e-9)
        assert 'user input' in y['injection_system'][
            'combustion_efficiency_source']


# ---------------------------------------------------------------------------
# P3B2-09 — ε taban kırpması
# ---------------------------------------------------------------------------
class TestP3B209GenislemeTabanKirpmasi:

    @pytest.fixture(scope='class')
    def kirpilmis(self, client):
        """Pc=10 bar: arayüzün KABUL ETTİĞİ alt sınır; taban ısırıyor."""
        return _post(client, thrust=5000.0, chamber_pressure=10.0)

    def test_kirpma_olgusu_yayimlanir(self, kirpilmis):
        na = kirpilmis['nozzle_angles']
        assert na['expansion_ratio_clamp'] == 'floor'
        unc = na['expansion_ratio_unclamped']
        assert isinstance(unc, float) and unc < EXPANSION_RATIO_SOLVER_MIN
        assert na['expansion_ratio'] == pytest.approx(
            EXPANSION_RATIO_SOLVER_MIN, rel=1e-12)

    def test_ambient_matched_iddiasi_dusurulur(self, kirpilmis):
        ds = kirpilmis['design_summary']
        metinler = ' '.join(str(x) for x in
                            (ds.get('optimizations_applied') or []))
        assert 'ambient-matched optimum' not in metinler, (
            'Kırpılmış lüle hâlâ "pe = pa optimumunda seçildi" diyor.')
        assert ds['status'] != 'OPTIMIZED'
        assert any('bound by the solver' in str(x)
                   for x in (ds.get('status_basis') or []))

    def test_cikis_basinci_TEK(self, kirpilmis):
        """İki çıkış basıncı (P_atm ataması ⟷ izentropik) kalmamalı."""
        a = kirpilmis['nozzle_angles']['exit_pressure_bar']
        b = kirpilmis['altitude_performance'][0]['exit_pressure_bar']
        assert a == pytest.approx(b, rel=1e-9), (
            f'nozzle_angles {a} ⟷ irtifa tablosu {b}')

    def test_kirpma_kunyesi_alan_adiyla_ve_sayiyla_konusur(self, kirpilmis):
        """Kullanıcı uyarısı i18n engeliyle eklenemedi (rapora yazıldı);
        kırpma yine de ADIYLA, SAYIYLA ve GEREKÇEYLE yayımlanır."""
        na = kirpilmis['nozzle_angles']
        src = na['expansion_ratio_source']
        assert 'NOT ' in src and 'ambient-matched' in src, src
        gerekce = ' '.join(str(x) for x in
                           kirpilmis['design_summary']['status_basis'])
        assert f"{na['expansion_ratio_unclamped']:.5f}" in gerekce
        assert 'pe != pa' in gerekce

    def test_kirpilmayan_kosumda_iddia_KORUNUR(self, taban):
        ds = taban['design_summary']
        assert taban['nozzle_angles']['expansion_ratio_clamp'] is None
        assert ds['status'] == 'OPTIMIZED'

    def test_esikler_tek_tanimli(self):
        assert EXPANSION_RATIO_SOLVER_MIN == 2.5
        assert EXPANSION_RATIO_SOLVER_MAX == 1000.0


# ---------------------------------------------------------------------------
# P3B2-10 — film + ceket bütçesi
# ---------------------------------------------------------------------------
class TestP3B210FilmCeketButcesi:

    @pytest.mark.parametrize('pct', [0.0, 10.0, 20.0, 30.0])
    def test_ceket_arti_film_yakiti_asamaz(self, client, pct):
        y = _post(client, film_cooling_percent=pct)
        cs = y['cooling_system']
        toplam = cs['coolant_flow_rate'] + cs['film_cooling_flow']
        assert toplam <= y['fuel_flow'] * (1.0 + 1e-9), (
            f'film %{pct}: ceket+film {toplam:.6f} kg/s > yakıt '
            f'{y["fuel_flow"]:.6f} kg/s')
        assert cs['coolant_plus_film_fraction_of_fuel'] <= 1.0 + 1e-9

    def test_film_payi_ceketten_DUSULUR(self, client):
        """Kütle korunumu (P3B2-10) — L-B (v3.0.1, SV-08) modeliyle.

        ESKİ beklenti: ceket = yakıt − film (film ceketten DÜŞÜLÜYOR, ama
        aynı yakıt tamamen yanıyordu; ölçüldü: film %0/%10/%30'da toplam
        debi ve Isp bit-aynı). YENİ model (brif kararı): film yanmaz ve
        çekirdek yakıta EK olarak çekilir — yanan yakıt ceketten geçer, film
        ondan önce ayrılır. Ceket debisi film payıyla DEĞİŞMEZ; toplam yakıt
        debisi tam film kadar artar (ölçüm: L-B olcum_sonra.json).
        """
        y0 = _post(client, film_cooling_percent=0.0)
        y2 = _post(client, film_cooling_percent=20.0)
        film = y2['cooling_system']['film_cooling_flow']
        assert film > 0.0
        assert y2['cooling_system']['coolant_flow_rate'] == pytest.approx(
            y0['cooling_system']['coolant_flow_rate'], rel=1e-12)
        assert y2['fuel_flow'] == pytest.approx(y0['fuel_flow'] + film,
                                                rel=1e-12)
        assert film == pytest.approx(0.20 * y2['fuel_flow'], rel=1e-12)

    def test_ceket_debisinin_kunyesi_var(self, client):
        y = _post(client, film_cooling_percent=20.0)
        b = y['cooling_system']['coolant_flow_rate_basis']
        assert b and 'film' in b.lower()


# ---------------------------------------------------------------------------
# P3B2-11 — izentropik istasyon sıcaklığı
# ---------------------------------------------------------------------------
class TestP3B211IstasyonSicakligi:

    def test_izentropik_bagintisi_tek_kaynaktan(self):
        """T/T_0 = (1+(γ-1)/2·M²)^-1 ve M alan oranının uygun kökünden."""
        g = 1.2
        for ar, sup in ((1.0, True), (4.0, True), (4.0, False), (25.0, True)):
            t, m = LiquidRocketEngine._isentropic_static_temperature(
                3000.0, ar, g, supersonic=sup)
            assert t == pytest.approx(
                3000.0 / (1.0 + (g - 1.0) / 2.0 * m ** 2), rel=1e-12)
            assert LiquidRocketEngine._area_ratio_from_mach(m, g) == (
                pytest.approx(max(ar, 1.0), rel=1e-6))
            if sup:
                assert m >= 1.0 - 1e-9
            else:
                assert m <= 1.0 + 1e-9

    def test_uydurma_0_1_ln_profili_geri_gelmedi(self):
        """Kusur formülü ε=9,58'de T/T_c = 0,9634 veriyordu."""
        g = 1.1635
        t, _m = LiquidRocketEngine._isentropic_static_temperature(
            3600.0, 9.58, g, supersonic=True)
        assert t / 3600.0 < 0.70, (
            f'T/T_c = {t / 3600.0:.4f} — izentropik değil, uydurma '
            '0,1·ln profiline benziyor.')

    def test_yakinsak_koni_subsonik_iraksak_supersonik(self):
        g = 1.15
        t_sub, m_sub = LiquidRocketEngine._isentropic_static_temperature(
            3600.0, 8.0, g, supersonic=False)
        t_sup, m_sup = LiquidRocketEngine._isentropic_static_temperature(
            3600.0, 8.0, g, supersonic=True)
        assert m_sub < 1.0 < m_sup
        assert t_sub > t_sup, (
            'Aynı alan oranında subsonik kök süpersonik kökten SICAK olmalı; '
            'yakınsak koni ıraksak koniyle aynı sıcaklığı görüyor.')

    def test_istasyon_sicakligi_kunyeli(self, taban):
        b = taban['cooling_system']['nozzle_gas_temperature_basis']
        assert b and 'isentropic' in b.lower()
        assert 'subsonic' in b.lower() and 'supersonic' in b.lower()


# ---------------------------------------------------------------------------
# P3B2-12 — Isp / C_F / c* özdeşliği
# ---------------------------------------------------------------------------
class TestP3B212IspOzdesligi:

    def test_CD_bogaz_yayimlanir(self, taban):
        cd = taban['throat_discharge_coefficient']
        assert isinstance(cd, float) and 0.70 <= cd <= 1.0
        assert taban['throat_discharge_coefficient_basis']

    def test_ozdeslik_kapanir(self, taban):
        ident = taban['isp_identity']
        assert ident['status'] == 'CLOSED', ident
        assert abs(ident['residual_pct']) < 1e-6

    def test_ozdeslik_yayimlanan_uc_sayiyla_kurulabilir(self, taban):
        """Kullanıcı yalnız yayımlanan yapraklarla özdeşliği kurabilmeli."""
        isp = taban['isp_sea_level']
        cstar = taban['c_star']
        cf = None
        for row in taban['altitude_performance']:
            if row.get('altitude') == 0:
                cf = row['thrust_coefficient']
                break
        cd = taban['throat_discharge_coefficient']
        assert cf is not None
        assert isp == pytest.approx(cf * cstar / (G0 * cd), rel=1e-6)

    def test_CD_kunyesi_ozdesligi_anlatir(self, taban):
        b = taban['throat_discharge_coefficient_basis']
        assert 'C_F' in b and 'c_star' in b


# ---------------------------------------------------------------------------
# P3B3-07 — pompa kartı kendi içinde kapanır
# ---------------------------------------------------------------------------
class TestP3B307PompaKartiKapanir:

    @pytest.fixture(scope='class')
    def staged(self, client):
        return _post(client, thrust=250000.0, chamber_pressure=150.0,
                     engine_cycle='staged_combustion')

    @pytest.mark.parametrize('pompa', ['oxidizer_pump', 'fuel_pump'])
    def test_guc_ozdesligi_kapanir(self, staged, pompa):
        kart = staged['detailed_feed_system']['turbopump_analysis'][pompa]
        rho_yolu = ('oxidizer_tank' if pompa == 'oxidizer_pump'
                    else 'fuel_tank')
        rho = staged['propellant_tanks'][rho_yolu]['propellant_data'][
            'density']
        hesap = (rho * G0 * kart['total_head_m']
                 * kart['volumetric_flow_m3_s']
                 / (kart['design_efficiency'] / 100.0) / 1000.0)
        assert hesap == pytest.approx(kart['design_power'], rel=1e-9), (
            f'{pompa}: kart kapanmıyor — rho*g*H_toplam*Q/eta {hesap:.3f} kW '
            f'⟷ design_power {kart["design_power"]:.3f} kW')
        assert abs(kart['power_identity_residual_pct']) < 1e-6

    def test_tek_kademe_bası_ile_toplam_bas_ayri_adla(self, staged):
        kart = staged['detailed_feed_system']['turbopump_analysis'][
            'oxidizer_pump']
        assert kart['total_head_m'] != pytest.approx(kart['design_head'],
                                                     rel=1e-6), (
            'Bu koşumda çevrim ölçeklemesi var; toplam bas tek kademe '
            'basıyla aynı olamaz.')
        assert kart['cycle_power_to_single_stage_ratio'] != pytest.approx(
            1.0, rel=1e-6)
        assert 'SINGLE-STAGE' in kart['design_head_role']

    def test_olceklemesiz_pompada_iki_bas_ayni(self, client):
        """Çevrim ölçeklemesi yoksa kart zaten kapalı olmalı."""
        y = _post(client, thrust=25000.0, engine_cycle='gas_generator')
        kart = y['detailed_feed_system']['turbopump_analysis']['fuel_pump']
        assert kart['total_head_m'] == pytest.approx(kart['design_head'],
                                                     rel=1e-12)
        assert kart['cycle_power_to_single_stage_ratio'] == pytest.approx(
            1.0, rel=1e-12)


# ---------------------------------------------------------------------------
# P3B3-08 — reddedilen girdiye sahip çıkılmaz
# ---------------------------------------------------------------------------
class TestP3B308ReddedilenPompaVerimi:

    # v3.0.1 (26 Eki, L-A ⟷ L-B birleşmesi): bant dışı / sayı olmayan girdi
    # artık motor kurulmadan 422 ``input_not_accepted`` alır (L-A SV-01:
    # "200 + sessizce başka değer" yolu kapandı). Eski beklenti (200 +
    # 'REJECTED' künyesi + 75 varsayılanıyla yayımlanan tasarım) o yolu
    # kilitliyordu. Testin konusu aynen korunur, daha sıkı biçimde:
    # reddedilen değer hiçbir yerde kullanıcı girdisi sayılmaz, çünkü tasarım
    # hiç yayımlanmaz ve alan adıyla reddedilir. Ölçüm (main 4441eebff):
    # 150 → out_of_accepted_range, 5 → out_of_accepted_range,
    # 'abc' → not_a_number; 80 → 200.
    @pytest.mark.parametrize('deger,neden', [
        (150.0, 'out_of_accepted_range'), (5.0, 'out_of_accepted_range'),
        ('abc', 'not_a_number')])
    def test_reddedilen_girdi_user_input_kunyesi_almaz(self, client, deger,
                                                       neden):
        r = client.post('/calculate_liquid', json=_yuk(
            engine_cycle='gas_generator', turbopump_efficiency=deger))
        assert r.status_code == 422, r.get_data(as_text=True)[:400]
        j = r.get_json()
        assert j['error'] == 'input_not_accepted'
        alanlar = {f['field']: f['reason'] for f in j['invalid_fields']}
        assert alanlar.get('turbopump_efficiency') == neden, alanlar
        assert 'detailed_feed_system' not in j, (
            'reddedilen girdiyle tasarım yayımlanmamalı')

    def test_kabul_edilen_girdi_kunyesini_KORUR(self, client):
        y = _post(client, engine_cycle='gas_generator',
                  turbopump_efficiency=80.0)
        kart = y['detailed_feed_system']['turbopump_analysis']['fuel_pump']
        assert kart['efficiency_source'].startswith('user input')
        assert kart['design_efficiency'] == pytest.approx(80.0, rel=1e-9)

    def test_girdi_yoksa_varsayilan_kunyesi(self, client):
        y = _post(client, engine_cycle='gas_generator')
        kart = y['detailed_feed_system']['turbopump_analysis']['fuel_pump']
        assert kart['efficiency_source'] == (
            'default best-efficiency-point value')


# ---------------------------------------------------------------------------
# P3B3-09 — hat cinsi TAHMİN EDİLMEZ
# ---------------------------------------------------------------------------
class TestP3B309HatCinsiArguman:

    @pytest.fixture(scope='class')
    def agir_yakit(self, client):
        """MMH/N2O4 + fuel_density 1004 (>900): tahmin dalını ısırır."""
        return _post(client, thrust=150000.0, chamber_pressure=80.0,
                     fuel_type='mmh', oxidizer_type='n2o4',
                     fuel_density=1004.0, cooling_type='ablative')

    def test_hat_cinsi_yayimlanir_ve_dogrudur(self, agir_yakit):
        pd = agir_yakit['feed_system']['pressure_drops']
        assert pd['fuel_line']['line_propellant_side'] == 'fuel'
        assert pd['oxidizer_line']['line_propellant_side'] == 'oxidizer'

    def test_yakit_hatti_YAKIT_yogunlugundan_secilir(self, agir_yakit):
        """Çap seçiminin hedef hızı, YAYIMLANAN hızla tutmalı.

        Kusur hâlinde çap oksitleyici yoğunluğuyla seçiliyor, hız ise
        yakıt yoğunluğuyla yeniden hesaplanıyordu: seçim ölçütü ile
        yayımlanan sayı iki farklı akışkandan geliyordu.
        """
        fl = agir_yakit['feed_system']['pressure_drops']['fuel_line']
        rho = agir_yakit['propellant_tanks']['fuel_tank'][
            'propellant_data']['density']
        d = fl['line_diameter_mm'] / 1000.0
        mdot = agir_yakit['fuel_flow']
        v = mdot / (rho * math.pi * d ** 2 / 4.0)
        assert v == pytest.approx(fl['line_velocity_m_s'], rel=1e-9)
        lo, hi = fl['line_velocity_band_m_s']
        assert lo <= v <= hi, (
            f'Yakıt hattı hızı {v:.3f} m/s bandın ({lo}-{hi}) dışında — çap '
            'yanlış akışkanın yoğunluğuyla seçilmiş.')

    def test_cins_argumani_dogrulanir(self, taban, client):
        """Tanınmayan cins SESSİZCE 'fuel' sayılmaz."""
        from hrma.engines import liquid_rocket_engine as lre
        with pytest.raises(ValueError):
            lre.LiquidRocketEngine._line_pressure_drops(
                object.__new__(lre.LiquidRocketEngine),
                1.0, 1000.0, 1e-3, 5.0, 'gizemli')
