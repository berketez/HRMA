# -*- coding: utf-8 -*-
"""ÖH Dalga-16 · kulvar hibrit · aşama 2 — onarım bekçileri.

Kapsanan kalemler:
  * B4-08 — türbin/pompa izentropik verim kapısı (η ∈ (0, 1]).
  * B4-09 — negatif pompa ΔP'nin sessiz sıfır güç ile 'converged' geçmesi.
  * OH-D15-05 — `design_gate_checks` defterinin uyarı paneline bağlanması.
  * OH-Z5-07 — quasi-1B ṁ çapraz denetiminin totolojik yaprağı + çözünürlük.

Her sınıf, onarım geri alındığında KIRMIZIYA dönecek biçimde yazıldı
(ters-mutasyon kanıtı: docs/scofield/raw/OH/D16/hibrit/a2/mutasyon.json).
"""
import contextlib
import io
import json
import math
import re
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
APP_JS = KOK / 'hrma' / 'static' / 'js' / 'app.js'

from hrma.engines import cycle_power_balance as cpb


def _coz(**kw):
    taban = dict(cycle_type='gas_generator', pc_bar=100.0, mdot_total=250.0,
                 mr=2.7, fuel='rp1', oxidizer='lox', tit_K=1000.0,
                 isp_main_s=300.0)
    taban.update(kw)
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        return cpb.solve_cycle(**taban)


# ===================================================================== B4-08
class TestB408TurbomakineVerimKapisi:
    """η > 1 termodinamiğin 2. yasasını ihlal eder; η <= 0 makine değildir."""

    def test_bant_sabiti_tek_kaynak(self):
        assert cpb.ETA_TURBOMACHINE_BAND == (0.0, 1.0)

    @pytest.mark.parametrize('eta', [5.0, 2.0, 1.0000001])
    def test_birden_buyuk_turbin_verimi_reddedilir(self, eta):
        with pytest.raises(ValueError) as exc:
            _coz(eta_turbine=eta)
        assert 'eta_turbine' in str(exc.value)

    @pytest.mark.parametrize('eta', [0.0, -0.5])
    def test_sifir_ve_negatif_turbin_verimi_reddedilir(self, eta):
        with pytest.raises(ValueError) as exc:
            _coz(eta_turbine=eta)
        assert 'eta_turbine' in str(exc.value)

    @pytest.mark.parametrize('eta', [float('nan'), float('inf'),
                                     float('-inf')])
    def test_sonlu_olmayan_turbin_verimi_reddedilir(self, eta):
        with pytest.raises(ValueError) as exc:
            _coz(eta_turbine=eta)
        assert 'eta_turbine' in str(exc.value)

    def test_sayi_olmayan_verim_reddedilir(self):
        with pytest.raises(ValueError) as exc:
            _coz(eta_turbine='yuksek')
        assert 'eta_turbine' in str(exc.value)

    @pytest.mark.parametrize('eta', [0.35, 0.65, 0.78, 1.0])
    def test_bant_ici_verim_gecer(self, eta):
        """Üst uç 1,0 DAHİLDİR (kayıpsız ideal makine matematiksel limit)."""
        sol = _coz(eta_turbine=eta)
        assert sol.converged is True
        assert sol.shafts[0]['turbine']['exit_temp_K'] > 0.0

    @pytest.mark.parametrize('alan', ['eta_pump_ox', 'eta_pump_fuel'])
    @pytest.mark.parametrize('eta', [5.0, 0.0, -0.3, float('nan')])
    def test_pompa_verimi_ayni_kapidan_gecer(self, alan, eta):
        with pytest.raises(ValueError) as exc:
            _coz(**{alan: eta})
        assert alan in str(exc.value)

    def test_pompa_verimi_kapisi_pressure_fed_dahil_her_cevrimde(self):
        """Kapı dallanmadan ÖNCE — pompasız çevrimde de sözleşme aynıdır."""
        with pytest.raises(ValueError):
            _coz(cycle_type='pressure_fed', eta_pump_ox=5.0,
                 tank_pressure_bar=200.0)

    @pytest.mark.parametrize('ct', ['tap_off', 'staged_combustion',
                                    'full_flow_staged_combustion'])
    def test_diger_cevrimlerde_de_reddedilir(self, ct):
        with pytest.raises(ValueError):
            _coz(cycle_type=ct, eta_turbine=5.0)

    def test_negatif_cikis_sicakligi_artik_uretilemez(self):
        """ÖLÇÜLDÜ (once.json): eta=5 -> exit_temp_K = -1194,64 K."""
        with pytest.raises(ValueError):
            _coz(eta_turbine=5.0)

    def test_varsayilan_secim_bozulmadi(self):
        """eta_turbine=None meşru girdidir: çevrim sınıfına göre seçilir."""
        acik = _coz(eta_turbine=None)
        kapali = _coz(cycle_type='staged_combustion', eta_turbine=None)
        assert acik.shafts[0]['turbine']['efficiency'] == \
            cpb.ETA_TURBINE_OPEN_DEFAULT
        assert kapali.shafts[0]['turbine']['efficiency'] == \
            cpb.ETA_TURBINE_CLOSED_DEFAULT


# ===================================================================== B4-09
class TestB409NegatifPompaDeltaP:
    """ΔP <= 0 olan pompa fiziksel değildir; güç 0 yazmak yalancı kapanmadır."""

    def test_pozitif_dp_hukmu_kazanilir(self):
        sol = _coz(pump_inlet_ox_bar=3.0, pump_inlet_fuel_bar=3.0)
        assert sol.converged is True
        assert sol.infeasible_pumps == []
        for p in sol.shafts[0]['pumps']:
            assert p['dp_feasible'] is True
            assert p['dp_bar'] > 0.0
            assert p['power_W'] > 0.0

    @pytest.mark.parametrize('p_in', [200.0, 300.0])
    def test_negatif_dp_cozumu_reddeder(self, p_in):
        """ÖLÇÜLDÜ (once.json): p_in=200 -> dp=-78 bar, güç 0 W, ama
        converged=True ve türbin debisi 0 kg/s (BEDAVA turbopompa)."""
        sol = _coz(pump_inlet_ox_bar=p_in, pump_inlet_fuel_bar=p_in)
        assert sol.converged is False
        assert 'power_balance' in sol.not_modelled
        assert len(sol.infeasible_pumps) == 2

    def test_ret_gerekcesi_veri_alani_olarak_yayimlanir(self):
        sol = _coz(pump_inlet_ox_bar=300.0, pump_inlet_fuel_bar=300.0)
        for p in sol.shafts[0]['pumps']:
            assert p['dp_feasible'] is False
            assert 'dp_infeasible_basis' in p
            assert 'not defined' in p['dp_infeasible_basis']
        for kayit in sol.infeasible_pumps:
            assert kayit['basis']
            assert kayit['dp_bar'] < 0.0

    def test_esit_basinc_da_olanaksizdir(self):
        """ΔP = 0 de bir pompa değildir — sınır dahil edilmez."""
        assert cpb._pump_dict('fuel', 1.0, 50.0, 50.0, 0.0, 0.75)[
            'dp_feasible'] is False
        assert cpb._pump_dict('fuel', 1.0, 50.0, 50.001, 1.0, 0.75)[
            'dp_feasible'] is True

    def test_hukum_to_dict_ile_disari_cikar(self):
        d = _coz(pump_inlet_ox_bar=300.0, pump_inlet_fuel_bar=300.0).to_dict()
        assert d['converged'] is False
        assert d['infeasible_pumps']

    @pytest.mark.parametrize('ct', ['staged_combustion',
                                    'full_flow_staged_combustion'])
    def test_kapali_cevrimlerde_saglikli_koşum_bozulmadi(self, ct):
        sol = _coz(cycle_type=ct)
        assert sol.infeasible_pumps == []


# ================================================================ OH-D15-05
class TestD1505TasarimKapisiPaneleBaglandi:
    """`design_gate_checks` defteri uyarı kanalına girer (kanal + KAPI)."""

    @staticmethod
    def _js_kos(kapilar, ekstra='{}'):
        src = APP_JS.read_text(encoding='utf-8')

        def al(ad):
            i = src.index('function ' + ad + '(')
            d = 0
            j = src.index('{', i)
            for k in range(j, len(src)):
                if src[k] == '{':
                    d += 1
                elif src[k] == '}':
                    d -= 1
                    if d == 0:
                        return src[i:k + 1]
            raise AssertionError('kapanmadi: ' + ad)

        # Tek giriş noktası: yardımcılar collectResultWarnings'in İÇİNDE
        # tanımlıdır (bkz. app.js'teki gerekçe — DOM'suz koşucular bu
        # fonksiyonu ad ad çekip tek başına çalıştırıyor).
        kod = al('collectResultWarnings')
        kod += ('\nconst _r = {motor: Object.assign('
                + ekstra + ', {design_gate_checks: '
                + json.dumps(kapilar) + '})};'
                '\nconsole.log(JSON.stringify(collectResultWarnings(_r)));')
        p = subprocess.run(['node'], input=kod, capture_output=True,
                           text=True, timeout=60)
        assert p.returncode == 0, p.stderr
        return json.loads(p.stdout.strip().splitlines()[-1])

    def test_app_js_kanali_okuyor(self):
        """ÖLÇÜLDÜ (once.json): app.js'te geçiş sayısı 0 idi."""
        src = APP_JS.read_text(encoding='utf-8')
        assert src.count('design_gate_checks') >= 2
        govde = re.search(r'function collectResultWarnings\(results\)\s*\{.*?\n\}',
                          src, re.S).group(0)
        assert 'design_gate_checks' in govde

    def test_bant_disi_hukum_panele_ulasir(self):
        cikti = self._js_kos([{
            'gate': 'c_star_efficiency_band', 'status': 'out_of_band',
            'quantity': 'eta_c_star', 'value': 0.3, 'band': [0.9, 0.97],
            'unit': '', 'basis': 'measured hybrid c* efficiency is 0.90-0.97.'}])
        assert len(cikti) == 1
        assert 'c_star_efficiency_band' in cikti[0]['message']
        assert 'OUT_OF_BAND' in cikti[0]['message']
        assert '0.3' in cikti[0]['message']
        assert '0.9-0.97' in cikti[0]['message']
        assert cikti[0]['message'].endswith(
            'measured hybrid c* efficiency is 0.90-0.97.')

    def test_pass_hukmu_uyari_olarak_basilmaz(self):
        cikti = self._js_kos([{
            'gate': 'c_star_plausibility', 'status': 'pass',
            'quantity': 'c_star_delivered', 'value': 1328.19,
            'band': [1100.0, 1700.0], 'unit': 'm/s', 'basis': 'x'}])
        assert cikti == []

    def test_limit_ve_kaynak_alanlari_tasinir(self):
        cikti = self._js_kos([{
            'gate': 'oxidizer_flux_flooding', 'status': 'out_of_band',
            'quantity': 'G_ox_design', 'value': 900.0, 'limit': 600.0,
            'unit': 'kg/m^2.s', 'source': 'initial_gox', 'basis': 'flooding.'}])
        m = cikti[0]['message']
        assert 'limit 600 kg/m^2.s' in m
        assert 'source: initial_gox' in m

    def test_yedek_hukmu_ne_istendi_ne_kullanildi_soyler(self):
        cikti = self._js_kos([{
            'gate': 'oxidizer_density_resolution', 'status': 'fallback',
            'quantity': 'oxidizer_liquid_density', 'requested': 'n2o4',
            'value': 745.0, 'used_instead': 'n2o', 'unit': 'kg/m^3',
            'basis': 'the density could not be resolved.'}])
        m = cikti[0]['message']
        assert 'used instead: n2o' in m
        assert 'FALLBACK' in m

    def test_onem_kazanilarak_basilir(self):
        """Kayıt kendi severity'sini yayımlamıyorsa kritik rozeti verilmez."""
        sade = self._js_kos([{'gate': 'g', 'status': 'clamped'}])
        assert sade[0]['severity'] == 'warning'
        kritik = self._js_kos([{'gate': 'g', 'status': 'clamped',
                                'severity': 'critical'}])
        assert kritik[0]['severity'] == 'critical'

    def test_defter_yoksa_kayit_uretilmez(self):
        src = APP_JS.read_text(encoding='utf-8')
        assert 'designGateChecksToWarnings' in src
        assert self._js_kos([]) == []

    def test_toplayici_kendi_kendine_yeterli(self):
        """REGRESYON BEKÇİSİ (12_kirmizi_tasnifi.json): yardımcılar modül
        düzeyine taşınırsa DOM'suz koşucular (test_d15_ui_paneller_a1.py'nin
        node kum havuzu) tanımsız ada başvurup ÇÖKER. Gövde kendi kendine
        yeterli olmalı."""
        src = APP_JS.read_text(encoding='utf-8')
        i = src.index('function collectResultWarnings(results)')
        d = 0
        j = src.index('{', i)
        for k in range(j, len(src)):
            if src[k] == '{':
                d += 1
            elif src[k] == '}':
                d -= 1
                if d == 0:
                    govde = src[i:k + 1]
                    break
        for ad in ('gateNumberText', 'designGateChecksToWarnings'):
            assert f'function {ad}(' in govde, (
                f'{ad} collectResultWarnings gövdesinin DIŞINDA — '
                'DOM\'suz koşucu çöker')

    def test_diger_kanallar_korunur(self):
        cikti = self._js_kos(
            [{'gate': 'g', 'status': 'clamped'}],
            ekstra='{warnings: [{code: "warn.hybrid.x", params: {}}]}')
        assert len(cikti) == 2
        assert cikti[0]['code'] == 'warn.hybrid.x'

    def test_yeni_i18n_anahtari_acilmadi(self):
        """Kulvar kısıtı: sözlükte olmayan anahtar kullanılamaz."""
        src = APP_JS.read_text(encoding='utf-8')
        govde = re.search(
            r'function designGateChecksToWarnings\(gates\)\s*\{.*?\n    \}',
            src, re.S).group(0)
        assert 'T(' not in govde
        assert 'warn.' not in govde


# ================================================================= OH-Z5-07
@pytest.fixture(scope='module')
def _hibrit_kosum():
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        m = HybridRocketEngine(thrust=3000.0, burn_time=8.0, of_ratio=2.5,
                               chamber_pressure=30.0, expansion_ratio=4.0,
                               fuel_type='htpb', oxidizer_type='n2o')
        r = m.calculate()
    return m, r


class TestZ507CaprazDenetimHukmu:
    """Totolojik yaprak künyelenir; CANLI artık yaprağına KAPI takılır."""

    def test_totolojik_yaprak_kendi_kunyesini_tasir(self, _hibrit_kosum):
        blok = _hibrit_kosum[1]['nozzle_flow_quasi1d']
        kunye = blok['mass_flow_rel_diff_basis']
        assert 'STRUCTURALLY CONSTANT' in kunye
        assert 'not an independent comparison' in kunye
        assert 'mass_flow_gas_model_rel_residual' in kunye

    def test_ozdeslik_gercekten_tutuyor(self, _hibrit_kosum):
        """ÖLÇÜLDÜ: beş çalışma noktasında da fark <= 3,5e-16.

        ÇEVRİLDİ — ÖH D18 fizik-a1 / F1 (B3-05). Özdeşliğin İKİNCİ defter
        terimi doğdu: manşet c* artık kayan-denge boğaz istasyonundan
        gelirken yarı-1B çözücü hâlâ kalorik mükemmel gazla çalışıyor,
        aradaki BİLİNEN oran ``mass_flow_c_star_model_ratio``. Ölçüldü:
        oran 1,003868, eski tek terimli beklenti 3,946e-03 açık veriyordu
        (kapı 'divergent' diyordu — açıklanabilir bir farka yanlış alarm).
        Özdeşlik artık eta·oran/C_D − 1'dir; oranın kendisi de yayımlanan
        iki c* yaprağından TÜRETİLEBİLİR olmalıdır (aşağıda denetleniyor).
        """
        from hrma.engines.hybrid_rocket_engine import (
            THROAT_DISCHARGE_COEFFICIENT)
        m, r = _hibrit_kosum
        blok = r['nozzle_flow_quasi1d']
        eta = 1.0 if m.eta_c_star is None else float(m.eta_c_star)
        oran = blok['mass_flow_c_star_model_ratio']
        elde = eta * oran / THROAT_DISCHARGE_COEFFICIENT - 1.0
        assert blok['mass_flow_expected_rel_diff'] == pytest.approx(elde,
                                                                    abs=1e-15)
        assert blok['mass_flow_rel_diff'] == pytest.approx(elde, abs=1e-12)
        # Oran uydurma değil: motorun taşıdığı iki c* değerinin bölümü.
        if isinstance(getattr(m, 'C_star_single_gamma', None), float):
            assert oran == pytest.approx(
                m.C_star_theoretical / m.C_star_single_gamma, rel=1e-12)

    def test_hukum_yaprak_olarak_yayimlanir(self, _hibrit_kosum):
        c = _hibrit_kosum[1]['nozzle_flow_quasi1d']['mass_flow_cross_check']
        assert set(c) >= {'status', 'residual', 'resolution',
                          'resolution_source', 'basis'}
        assert c['status'] in ('pass', 'divergent', 'not_applicable')

    def test_saglikli_kosum_gecer(self, _hibrit_kosum):
        c = _hibrit_kosum[1]['nozzle_flow_quasi1d']['mass_flow_cross_check']
        assert c['status'] == 'pass'
        assert abs(c['residual']) <= c['resolution']

    def test_cozunurluk_tabani_cozucunun_kendi_artigidir(self, _hibrit_kosum):
        """TEK KAYNAK: yeni bir eşik sabiti doğmadı."""
        blok = _hibrit_kosum[1]['nozzle_flow_quasi1d']
        c = blok['mass_flow_cross_check']
        assert c['resolution'] == abs(blok['mass_conservation_rel_residual'])
        assert 'mass_conservation_rel_residual' in c['resolution_source']

    def test_kunye_artik_fazla_iddiali_degil(self, _hibrit_kosum):
        """Eski metin 'sıfırdan her sapma gerçek ayrışmadır' diyordu; oysa
        çözücünün kendi artığı 2-4 mertebe daha büyük."""
        kunye = _hibrit_kosum[1]['nozzle_flow_quasi1d']['mass_flow_check_basis']
        assert 'any departure from zero is a real gas-model divergence' \
            not in kunye
        assert 'mass_flow_cross_check' in kunye
        assert 'not resolvable' in kunye

    @pytest.mark.parametrize('carpan,beklenen', [
        (1.05, 'divergent'), (0.95, 'divergent'),
        (1.001, 'divergent'), (1.0, 'pass')])
    def test_gaz_modeli_ayrisinca_hukum_doner(self, _hibrit_kosum, carpan,
                                             beklenen):
        """Kapının CANLI olduğunun kanıtı: gamma kaydırılınca hüküm döner.
        (ÖLÇÜLDÜ: gamma x1,05 -> artık 1,78e-02; taban 3,4e-16.)"""
        m, r = _hibrit_kosum
        br = dict(r)
        br['gamma'] = float(r['gamma']) * carpan
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            blok = m._nozzle_flow_block(br)
        assert blok['mass_flow_cross_check']['status'] == beklenen

    def test_molekul_agirligi_ayrismasi_da_gorunur(self, _hibrit_kosum):
        m, r = _hibrit_kosum
        br = dict(r)
        br['molecular_weight'] = float(r['molecular_weight']) * 1.05
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            blok = m._nozzle_flow_block(br)
        c = blok['mass_flow_cross_check']
        assert c['status'] == 'divergent'
        assert abs(c['residual']) > 1e-3

    def test_hukum_deftere_ve_dolayisiyla_panele_baglidir(self, _hibrit_kosum):
        """OH-D15-05 ile kesişim: ayrışma tespit edilirse kullanıcıya gider."""
        m, r = _hibrit_kosum
        defter = [g['gate'] for g in (r.get('design_gate_checks') or [])]
        assert 'nozzle_flow_gas_model_agreement' not in defter
        kaynak = (KOK / 'hrma' / 'engines'
                  / 'hybrid_rocket_engine.py').read_text(encoding='utf-8')
        assert "'gate': 'nozzle_flow_gas_model_agreement'" in kaynak
        assert "if _capraz.get('status') == 'divergent':" in kaynak

    def test_saglikli_kosumda_defter_kirletilmez(self, _hibrit_kosum):
        """'pass' hükmü uyarı üretmez — ÖK-22: sağlıklı envanter gevşemez."""
        r = _hibrit_kosum[1]
        for g in (r.get('design_gate_checks') or []):
            assert g['gate'] != 'nozzle_flow_gas_model_agreement'
