"""Bebek-Scofield sıvı motor bekçileri (A2 — F1-1, F1-2, F5-3, F5-4).

Bulgu sicili: docs/scofield-bebek-2026-08-17.md. Dört kusur da aynı
sınıftandı: iki parça tek başına doğru, aralarındaki sözleşme yanlış.

Ölçülen kusurlar (öncesi → sonrası):

* F1-2 — tank basıncı marjı YALNIZ oksitleyici basma basıncına bakıyordu;
  rejeneratif ΔP taşıyan yakıt gereksinimi bağlayıcıyken işaret ters
  dönüyordu. Ölçüm (25 kN LOX/RP-1, Pc=70 bar, pressure_fed, tank 95 bar):
  yayımlanan +4,402 bar ⟷ çevrim çözücüsü −3,576 bar + critical
  ``warn.cycle.pressure_fed_infeasible``. Sonrası: marj çevrim çözümünün
  KENDİSİNDEN okunur (tek kaynak), motor kapısı da aynı marjdan ateşler.

* F1-1 — ``_apply_cycle_accounting`` ölü koddu: başlık Isp'si (277,449 s)
  ile yakınsamış çevrim çözümünün motor Isp'si (274,034 s; kayıp 3,415 s)
  aynı yanıtta beyansız çelişiyordu. Sonrası: ilişki
  ``cycle_isp_accounting`` bloğunda adıyla ve ölçülen farkla yayımlanır;
  blok motorun GERÇEK ``_cycle_isp_applied`` durumundan türediği için beyan
  davranıştan kopamaz.

* F5-3 — aynı turbopompanın türbin gücü iki değerle yayımlanıyordu:
  kullanıcıya 169,55 kW (= 110,21/0,65 — pompa mil gücü türbin verimine
  BÖLÜNMÜŞ), çevrim kapanışında 110,21 kW. Mil dengesinde türbin mil gücü
  pompa mil gücüne EŞİTTİR (çevrim çözücüsünün kapattığı özdeşlik; verim
  gaz debisi boyutlandırmasına girer, mil gücünü büyütmez). Sonrası: tek
  değer, her yayın noktasında aynı.

* F5-4 — aynı kanal devresi için iki çelişen çıktı kümesi (toplu Bartz
  zinciri 52,15 MW/m² / çıkış 820,0 K ⟷ istasyon marşı 10,95 MW/m² /
  421,9 K) beyansız yan yana duruyordu. Sonrası: fark
  ``channel_circuit_reconciliation`` bloğunda adıyla ölçülür; hangi kümenin
  fiziksel denge olduğu ENERJİ DENGESİYLE karara bağlanır (marşın kendi
  kapanışı ṁ·c̄p·ΔT = ∮q dA ölçülü; tasarım-cidar akısı için gereken film
  ΔT'si kanalların verebileceğiyle kıyaslanır).

Motor koşuları pahalıdır (~3-5 s); iki koşu modül kapsamında paylaşılır.
"""

import pytest

# Form varsayılanları ve koşucu TEK kaynaktan (deponun kendi deseni:
# tests.test_cfd_alan_koprusu -> test_cfd_endpoint ithali gibi).
from tests.test_liquid_real_inputs import FORM_DEFAULTS, run_engine


# ---------------------------------------------------------------------------
# Paylaşılan koşular
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def gg():
    """Gaz jeneratörü çevrimi (RP-1/LOX, rejeneratif): F1-1, F5-3, F5-4."""
    return run_engine(dict(FORM_DEFAULTS))


@pytest.fixture(scope='module')
def exp_kapanmayan():
    """Expander + RP-1: çevrim KAPANMAZ (not_converged) — türbin kartının
    yedek (çevrimsiz) yolunu görünür kılar. Converged yolda kart çevrim
    kapanışıyla ezildiği için F5-3'ün ikinci ``/η`` kopyası ancak burada
    ısırılabilir (ölçüldü: mutasyonla 64,15 kW → 98,69 kW)."""
    return run_engine(dict(FORM_DEFAULTS, engine_cycle='expander'))


@pytest.fixture(scope='module')
def pf():
    """Basınç beslemeli, yakıt tarafı bağlayıcı senaryo (F1-2 ölçüm vakası).

    Pc=70 bar + 20 bar enjektör ΔP + rejeneratif ceket ΔP'siyle yakıt
    gereksinimi (~98,6 bar) oksitleyicininkini (~90,6 bar) aşar; 95 bar tank
    tam ikisinin ARASINDADIR — eski formülün işareti burada ters dönüyordu.
    """
    return run_engine(dict(FORM_DEFAULTS, engine_cycle='pressure_fed',
                           feed_pressure=95),
                      thrust=25000, chamber_pressure=70, mixture_ratio=2.3)


def _cyc(result):
    return result['detailed_feed_system']['engine_cycle_solution']


# ---------------------------------------------------------------------------
# F1-2 — tank basıncı marjı tek kaynaktan ve doğru taraftan
# ---------------------------------------------------------------------------

class TestF12TankMarji:
    def test_marj_cevrim_cozumunun_kendisidir(self, pf):
        """Yayımlanan marj = çevrim çözücüsünün marjı (bit düzeyinde)."""
        _, res = pf
        dfs = res['detailed_feed_system']
        cyc = _cyc(res)
        assert cyc.get('tank_pressure_margin_bar') is not None, (
            'senaryo ön koşulu: çevrim çözümü marj yayımlamalı')
        assert dfs['tank_pressure_margin_bar'] == \
            cyc['tank_pressure_margin_bar']
        assert 'single source' in dfs['tank_pressure_margin_basis']

    def test_marj_yakit_tarafini_gorur_ve_isaret_dogru(self, pf):
        """Kusurun kendisi: yakıt bağlayıcıyken eski formül + verirdi.

        Mutasyon kanıtı: marj ``tank − ox basma basıncı``na geri dönerse
        (eski satır) burada +4,4 bar civarı POZİTİF çıkar ve iki assert
        birden kırılır.
        """
        _, res = pf
        dfs = res['detailed_feed_system']
        cyc = _cyc(res)
        req_ox = cyc['required_tank_pressure_ox_bar']
        req_fuel = cyc['required_tank_pressure_fuel_bar']
        tank = dfs['tank_pressure_bar']
        # Senaryo ön koşulları — bunlar kırılırsa bekçi kör kalır, sessiz
        # geçmek yerine adıyla söylenir.
        assert req_fuel > req_ox, (
            'senaryo ön koşulu bozuldu: yakıt gereksinimi artık bağlayıcı '
            f'değil (req_fuel={req_fuel:.2f} <= req_ox={req_ox:.2f}); '
            'bekçi senaryosunu güncelle')
        assert req_ox < tank < req_fuel, (
            'senaryo ön koşulu bozuldu: tank basıncı iki gereksinimin '
            f'arasında değil (req_ox={req_ox:.2f}, tank={tank}, '
            f'req_fuel={req_fuel:.2f}); bekçi senaryosunu güncelle')
        marj = dfs['tank_pressure_margin_bar']
        # Doğru tanım: tank − max(req_ox, req_fuel); bu vakada NEGATİF.
        assert marj == pytest.approx(tank - max(req_ox, req_fuel),
                                     rel=1e-12)
        assert marj < 0.0
        # Eski (yanlış taraf) formülün değeri farklı ve POZİTİF olurdu.
        assert marj != pytest.approx(tank - req_ox, abs=1e-6)

    def test_marj_negatifse_motor_da_uyarir(self, pf):
        """Kapı da tek kaynaktan: çözücü critical derken motor susamaz."""
        _, res = pf
        cyc_codes = [w.get('code') for w in (_cyc(res).get('warnings') or [])
                     if isinstance(w, dict)]
        assert 'warn.cycle.pressure_fed_infeasible' in cyc_codes
        eng_warns = [w for w in res['input_warnings']
                     if isinstance(w, dict)
                     and w.get('code') == 'warn.liquid.pressure_fed_tank_too_low']
        assert eng_warns, (
            'çevrim çözücüsü critical infeasible derken motor seviyesinde '
            'pressure_fed_tank_too_low uyarısı yok — eski kapı yalnız '
            'oksitleyiciye bakıyordu, bu kusurun ta kendisi')
        # Uyarının bildirdiği gereksinim bağlayıcı (yakıt) taraf olmalı.
        req_fuel = _cyc(res)['required_tank_pressure_fuel_bar']
        assert eng_warns[0]['params']['required_bar'] == \
            pytest.approx(round(req_fuel, 1))


# ---------------------------------------------------------------------------
# F5-3 — türbin gücü tek değer, mil dengesiyle
# ---------------------------------------------------------------------------

class TestF53TurbinGucu:
    def test_turbin_gucu_her_yayin_noktasinda_ayni(self, gg):
        """169,55 ⟷ 110,21 çelişkisi: artık TEK değer."""
        _, res = gg
        cyc = _cyc(res)
        assert cyc.get('status') == 'converged', 'senaryo ön koşulu'
        cyc_kw = cyc['turbine_power_total_W'] / 1e3
        yayinlar = {
            'turbopump_system.turbine_power':
                res['turbopump_system']['turbine_power'],
            'detailed_feed_system.turbopump_analysis.turbine.power_output':
                res['detailed_feed_system']['turbopump_analysis'][
                    'turbine']['power_output'],
            'feed_system.turbopump.turbine.power':
                res['feed_system']['turbopump']['turbine']['power'],
        }
        for ad, deger in yayinlar.items():
            assert deger == pytest.approx(cyc_kw, rel=1e-9), (
                f'{ad} = {deger} != çevrim kapanışı {cyc_kw} — aynı '
                'turbopompa yine iki sayıyla anlatılıyor')

    def test_mil_dengesi_ozdesligi(self, gg):
        """Enerji dengesi: türbin mil gücü ≡ pompa mil gücü.

        Mutasyon kanıtı: ``/ eta_turbine`` geri gelirse yayımlanan güç
        pompa toplamının 1/0,65 katına çıkar ve burada kırılır.
        """
        _, res = gg
        cyc = _cyc(res)
        # Çözücünün kendi kapanışı (özdeşliğin kaynağı).
        assert cyc['turbine_power_total_W'] == \
            pytest.approx(cyc['pump_power_total_W'], rel=1e-9)
        # Yayımlanan türbin gücü pompa toplamına eşit — verime bölünmemiş.
        tps = res['turbopump_system']
        pompa_toplam = tps['total_pump_power']
        assert tps['turbine_power'] == pytest.approx(pompa_toplam, rel=1e-9)
        # Verim hâlâ yayımlanıyor (gaz debisi boyutlandırması için) ama mil
        # gücünü şişirmiyor.
        turb = res['detailed_feed_system']['turbopump_analysis']['turbine']
        assert 'shaft power balance' in turb['power_output_basis']

    def test_cevrim_kapanmayinca_da_mil_dengesi(self, exp_kapanmayan):
        """İkinci ``/η`` kopyasının bekçisi: çevrimsiz yedek yol.

        Converged yolda türbin kartı çevrim kapanışıyla ezilir; kopya kusur
        ancak çevrim KAPANMADIĞINDA görünür. Ölçülen (expander+RP-1,
        not_converged): pompalar 64,15 kW iken mutasyonlu kart 98,69 kW
        (=64,15/0,65) yayımlıyordu.
        """
        _, res = exp_kapanmayan
        cyc = _cyc(res)
        assert cyc.get('status') != 'converged', (
            'senaryo ön koşulu bozuldu: expander+RP-1 çevrimi artık '
            'kapanıyor; bekçiye yeni bir kapanmayan senaryo gerek')
        ta = res['detailed_feed_system']['turbopump_analysis']
        pompa_toplam = (ta['oxidizer_pump']['design_power']
                        + ta['fuel_pump']['design_power'])
        turb = ta['turbine']
        assert turb['power_output'] == pytest.approx(pompa_toplam, rel=1e-9)
        # Gaz debisi boyutlandırması: ṁ = P_mil/(Δh·η) — verim TAM BİR kez.
        eta = turb['efficiency'] / 100.0
        assert turb['mass_flow_rate'] == pytest.approx(
            turb['power_output'] * 1e3 / (turb['specific_work_J_kg'] * eta),
            rel=1e-9)


# ---------------------------------------------------------------------------
# F1-1 — başlık Isp'si ↔ çevrim çözümü ilişkisi beyanlı
# ---------------------------------------------------------------------------

class TestF11CevrimIspBeyani:
    def test_beyan_blogu_var_ve_olculu(self, gg):
        _, res = gg
        acc = res.get('cycle_isp_accounting')
        assert isinstance(acc, dict), (
            'cycle_isp_accounting bloğu yok — başlık Isp\'si ile çevrim '
            'çözümü yine beyansız çelişiyor (F1-1)')
        cyc = _cyc(res)
        assert cyc.get('status') == 'converged', 'senaryo ön koşulu'
        assert acc['status'] == 'reconciled'
        assert acc['engine_isp_sl_s'] == cyc['isp_engine_sl_s']
        assert acc['isp_loss_sl_s'] == cyc['isp_loss_sl_s']
        assert acc['headline_minus_engine_sl_s'] == pytest.approx(
            acc['headline_isp_sl_s'] - acc['engine_isp_sl_s'], rel=1e-12)
        # Açık çevrimde kayıp gerçek ve pozitif olmalı (ölçülen ~3,4 s).
        assert acc['isp_loss_sl_s'] > 0.0

    def test_beyan_davranistan_kopamaz(self, gg):
        """Kaybı sessizce uygulamak da, beyanı çürütmek de kırmızıdır.

        Blok ``_cycle_isp_applied`` durumundan türediği için üç hâl de
        kilitli: (a) uygulanmadıysa başlık ANA ODA Isp'sinin ta kendisidir;
        (b) uygulandıysa başlık motor Isp'sidir; (c) motor nesnesinin
        durumu ile bloğun beyanı aynıdır.
        """
        engine, res = gg
        acc = res['cycle_isp_accounting']
        cyc = _cyc(res)
        assert acc['applied'] == bool(getattr(engine, '_cycle_isp_applied',
                                              False))
        assert acc['headline_isp_sl_s'] == pytest.approx(
            res['isp_sea_level'], rel=1e-12)
        if not acc['applied']:
            # Başlık, beyan edilen kaynağın (ana oda zinciri) KENDİSİ olmalı.
            assert res['isp_sea_level'] == pytest.approx(
                cyc['isp_main_sl_s'], rel=1e-12), (
                'başlık Isp\'si ne ana oda değeri ne motor değeri — kayıp '
                'sessizce/yarım uygulanmış (F1-1 geri geldi)')
            assert 'NOT subtracted' in acc['headline_isp_basis']
        else:
            assert res['isp_sea_level'] == pytest.approx(
                cyc['isp_engine_sl_s'], rel=1e-3), (
                'blok applied=True diyor ama başlık motor Isp\'si değil')

    def test_kapali_cevrimde_kayip_sifir_beyani(self, pf):
        """Basınç beslemeli: kayıp tanım gereği 0 ve blok bunu söyler."""
        _, res = pf
        acc = res.get('cycle_isp_accounting')
        assert isinstance(acc, dict)
        if acc['status'] == 'reconciled':
            assert acc['isp_loss_sl_s'] == 0.0


# ---------------------------------------------------------------------------
# F5-4 — aynı kanal devresi: fark adıyla, hüküm enerji dengesiyle
# ---------------------------------------------------------------------------

class TestF54KanalDevresi:
    def test_mutabakat_blogu_iki_kumeyi_adiyla_yayimlar(self, gg):
        _, res = gg
        tp = res['thermal_protection']
        assert 'station_march' in tp, 'senaryo ön koşulu: RP-1 marşı koşmalı'
        rec = tp.get('channel_circuit_reconciliation')
        assert isinstance(rec, dict), (
            'channel_circuit_reconciliation yok — aynı devrenin iki çıktı '
            'kümesi yine beyansız yan yana (F5-4)')
        bulk, march = rec['bulk_chain'], rec['station_march']
        # Kimlik: blok, başlıktaki sayıların TA KENDİSİNİ mutabık kılar.
        assert bulk['peak_heat_flux_MW_m2'] == \
            pytest.approx(tp['heat_flux'], rel=1e-12)
        assert bulk['coolant_exit_temperature_K'] == \
            pytest.approx(tp['coolant_exit_temperature'], rel=1e-12)
        assert bulk['temperature_rise_K'] == \
            pytest.approx(tp['temperature_rise'], rel=1e-12)
        assert bulk['pressure_drop_bar'] == \
            pytest.approx(tp['pressure_drop'], rel=1e-12)
        sm = tp['station_march']
        assert march['peak_heat_flux_MW_m2'] == \
            pytest.approx(sm['peak_heat_flux_MW_m2'], rel=1e-12)
        assert march['coolant_exit_temperature_K'] == \
            pytest.approx(sm['coolant_exit_temperature_K'], rel=1e-12)
        assert march['pressure_drop_bar'] == \
            pytest.approx(sm['coolant_pressure_drop_bar'], rel=1e-12)
        # Oran, bloğun kendi satırlarından türetilmiş olmalı (kimlik).
        assert rec['peak_flux_ratio_bulk_over_march'] == pytest.approx(
            bulk['peak_heat_flux_MW_m2'] / march['peak_heat_flux_MW_m2'],
            rel=1e-12)

    def test_enerji_dengesi_olculu_ve_hukum_tutarli(self, gg):
        """Hüküm ölçümden: marş kendi dengesini kapatır, hüküm ondan türer."""
        _, res = gg
        rec = res['thermal_protection']['channel_circuit_reconciliation']
        eb = rec['march_energy_balance']
        # Marşın kendi enerji dengesi ÖLÇÜLÜ kapalı: ṁ·c̄p·ΔT = ∮q dA.
        assert eb['relative_gap'] is not None and eb['relative_gap'] < 1e-6
        assert eb['mdot_cp_dT_kW'] == pytest.approx(
            eb['integral_q_dA_kW'], rel=1e-6)
        # Taşınabilirlik hükmü kendi sayılarıyla tutarlı olmalı.
        gereken = rec['design_flux_film_dt_required_K']
        mevcut = rec['design_film_dt_available_K']
        assert rec['design_flux_supportable_by_channels'] == (
            gereken is not None and gereken <= mevcut)
        if not rec['design_flux_supportable_by_channels']:
            assert 'station_march' in rec['verdict']

    def test_baslik_alanlari_model_adini_soyler(self, gg):
        """Çıplak akı/ΔT/çıkış sayıları hangi cidar kapanışından, yazmalı."""
        _, res = gg
        tp = res['thermal_protection']
        for alan in ('heat_flux_basis', 'temperature_rise_basis',
                     'coolant_exit_temperature_basis', 'pressure_drop_basis'):
            assert alan in tp, f'{alan} yok — sayı yine beyansız'
            assert ('design wall temperature' in tp[alan]
                    or 'station march' in tp[alan]), tp[alan]
        # RP-1 çözülmemiş zincirde beyan mutabakat bloğuna işaret etmeli.
        if 'design wall temperature' in tp['heat_flux_basis']:
            assert 'channel_circuit_reconciliation' in tp['heat_flux_basis']
