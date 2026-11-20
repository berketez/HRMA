"""V307 / KATI-DOĞRULAMA faz 2 bekçileri.

Kalem 1 (S1): emniyet sınırında duran yanma SONUÇ ÜRETMEZ; Monte Carlo
örneklemi sıfır performansla kirlenmez. Ölçüm ve gerekçe:
docs/scofield/raw/OH/V307/kati-dogrulama/RAPOR.md (faz 2).
"""
import math

import numpy as np
import pytest

from hrma.engines import solid_rocket_engine as sre
from hrma.engines.solid_rocket_engine import SolidRocketEngine


def _kappa_sabit_bogaz(erozif_k):
    """Kappa KSB-002 donanımı: boğaz 12,7 mm'ye SABİT (donanım yolu)."""
    e = SolidRocketEngine(
        grain_type='bates', propellant_type='knsb', chamber_diameter=55.9,
        grain_length=408.0, core_diameter=19.05, chamber_pressure=68.94757,
        overrides={'n_segments': 4, 'density': 1680.2,
                   'erosive_k': erozif_k, 'erosive_k_override': True})
    e.pin_throat_area(math.pi / 4 * 0.0127 ** 2)
    return e


class TestEmniyetSiniriAdliRet:
    def test_sinirda_duran_yanma_sonuc_uretmez(self):
        r = _kappa_sabit_bogaz(0.25).calculate_performance()
        assert 'error' in r, 'emniyet sınırında duran koşu sonuç yayımladı'
        assert r['status'] == sre.DESIGN_STATUS_NOT_CONVERGED
        assert r['solver_diagnostics']['termination_reason'] == 'safety_limit'
        assert r['error_i18n']['code'] == 'warn.solid.safety_limit_termination'
        # Performans alanları YOK: kesik eğri motor sonucu diye okunamaz.
        for alan in ('burn_time', 'specific_impulse', 'isp_sea_level',
                     'total_impulse', 'thrust_curve', 'cad_design'):
            assert alan not in r, alan
        tani = r['truncated_burn_diagnostic_only']
        assert tani['sample_count'] >= 1
        assert tani['max_chamber_pressure_bar'] > (
            sre.SOLID_SIMULATION_PRESSURE_LIMIT_BAR)

    def test_sinirin_altindaki_kosu_etkilenmez(self):
        r = _kappa_sabit_bogaz(0.0615).calculate_performance()
        assert 'error' not in r
        assert r['solver_diagnostics']['termination_reason'] == 'web_exhausted'
        assert r['burn_time'] > 1.0 and r['isp_sea_level'] > 100.0
        assert max(r['thrust_curve']['pressure']) < (
            sre.SOLID_SIMULATION_PRESSURE_LIMIT_BAR)

    def test_hata_metni_siniri_sabitten_okur(self):
        r = _kappa_sabit_bogaz(0.25).calculate_performance()
        assert f'{sre.SOLID_SIMULATION_PRESSURE_LIMIT_BAR:g} bar' in r['error']
        assert f'{sre.SOLID_SIMULATION_TIME_LIMIT_S:g} s' in r['error']
        assert (r['solver_diagnostics']['safety_limit_pressure_bar']
                == sre.SOLID_SIMULATION_PRESSURE_LIMIT_BAR)


class TestMonteCarloOrneklemiBozulmaz:
    """Form 500 bar'a kadar tasarım basıncı kabul eder; 480 bar'da parti
    saçılımı örneklemlerin bir kısmını sınırın üstüne taşır."""

    @pytest.fixture(scope='class')
    def mc(self):
        e = SolidRocketEngine(
            grain_type='bates', propellant_type='apcp', chamber_diameter=100.0,
            grain_length=500.0, core_diameter=40.0, chamber_pressure=480.0)
        nominal = e.calculate_performance()
        assert 'error' not in nominal
        return nominal, e.run_monte_carlo(
            n_samples=sre.SOLID_MC_SAMPLE_BAND[0], seed=42)

    def test_sinirda_duran_ornekler_sayilir(self, mc):
        _, sonuc = mc
        assert sonuc['n_safety_limit_runs'] > 0, (
            'vaka artık sınırı aşmıyor; bekçi başka bir şeyi ölçüyor olurdu')
        assert sonuc['n_failed_runs'] >= sonuc['n_safety_limit_runs']
        assert str(sonuc['n_safety_limit_runs']) in sonuc['failed_runs_basis']

    def test_istatistige_sifir_performans_girmez(self, mc):
        nominal, sonuc = mc
        assert min(sonuc['histograms']['isp']) > 0.8 * nominal['specific_impulse']
        assert sonuc['isp']['p5'] > 0.8 * nominal['specific_impulse']
        assert sonuc['burn_time']['p5'] > 0.5 * nominal['burn_time']
        assert len(sonuc['histograms']['isp']) == (
            sonuc['n_samples'] - sonuc['n_failed_runs'])

    def test_sonucsuz_ornek_basarisizlik_sayilir(self, mc):
        _, sonuc = mc
        ust = 100.0 * (1.0 - sonuc['n_failed_runs'] / sonuc['n_samples'])
        assert sonuc['success_rate_percent'] <= round(ust, 1) + 1e-9


# ---------------------------------------------------------------------------
# Kalem 2-4: kıyas donanımla, NASA BATES kayıtları, itici ailesi, KSB kapsamı
# ---------------------------------------------------------------------------
import copy
import json
from pathlib import Path

from hrma.validation import record_adapters as ra
from hrma.validation.correlation_runner import (
    propellant_family_of, run_correlation)
from hrma.validation.experiment_db import ensure_valid_record

_KATI = (Path(__file__).resolve().parents[1] / "hrma" / "data"
         / "validation_records" / "solid")
NASA_IDLER = tuple(f"sol-nasa1979-bates-e{n}" for n in
                   (1453, 1455, 1484, 1491, 1472, 1473))


def _kayit(test_id):
    yol = _KATI / f"{test_id}.json"
    with open(yol, encoding="utf-8") as f:
        rec = json.load(f)
    ensure_valid_record(rec, path=yol)
    return rec


class TestPinExpansionRatio:
    def _motor(self):
        return SolidRocketEngine(
            grain_type='bates', propellant_type='apcp', chamber_diameter=100.0,
            grain_length=500.0, core_diameter=40.0, chamber_pressure=40.0)

    def test_sabitlenen_oran_yayimlanir(self):
        e = self._motor()
        serbest = float(e._estimate_expansion_ratio())
        e.pin_expansion_ratio(11.0)
        assert e._estimate_expansion_ratio() == 11.0
        assert e.calculate_performance()['expansion_ratio'] == pytest.approx(11.0)
        e.pin_expansion_ratio(None)
        assert float(e._estimate_expansion_ratio()) == serbest

    @pytest.mark.parametrize("kotu", [float('nan'), float('inf'), 1.0, -3.0])
    def test_gecersiz_oran_reddedilir(self, kotu):
        with pytest.raises(ValueError):
            self._motor().pin_expansion_ratio(kotu)


class TestNasaBatesKayitlari:
    @pytest.mark.parametrize("tid", NASA_IDLER)
    def test_kayit_semadan_gecer_ve_turetilenler_isaretli(self, tid):
        rec = _kayit(tid)
        assert rec["geometry"]["grain_dimensions_derived"] is True
        assert "TÜRETİLDİ" in rec["geometry"]["grain_dimensions_note"]
        assert "TÜRETİLDİ" in rec["propellants"]["thermo_equivalent_note"]
        assert rec["propellants"]["propellant_family"] in (
            "an_ap_al_htpb", "an_hmx_ap_al_htpb")
        assert rec["propellants"]["hrma_propellant_key"] is None
        # Web süresi ve etki süresi AYRI ölçüm; etki süresi daha uzun.
        m = rec["measured"]
        assert m["action_time_s"] > m["web_burn_time_s"]
        # Yüklenen kütle girdidir (tane ölçüsü ondan türetildi).
        assert "propellant_mass_kg" in rec["inputs"]
        assert not any(k.startswith("propellant_mass_kg") for k in m)

    def test_e1484_kendi_iticisiyle_kosar_ve_es_tanimla_skorlanir(self):
        rec = _kayit("sol-nasa1979-bates-e1484")
        sonuc = run_correlation(records=[rec])
        rr = sonuc["records"][0]
        assert rr["status"] == "ok", rr.get("reason")
        s = rr["scores"]
        assert s["web_burn_time"]["status"] == "scored"
        assert s["web_burn_time"]["error_pct"] == pytest.approx(-9.7, abs=1.0)
        # Faz 3 (B1): kaydın egzoz Al2O3 kesri (0,283) iki fazlı tahmine
        # girer; Isp sapması +8,47 -> +4,23 (tolerans aynı).
        assert s["isp"]["error_pct"] == pytest.approx(4.2, abs=1.0)
        assert s["chamber_pressure_peak"]["error_pct"] == pytest.approx(4.4, abs=1.0)
        # Etki süresi için HRMA tahmini yok; web süresi varken çapraz kıyas da yok.
        assert s["action_time"]["status"] == "no_prediction"
        assert ra.SOLID_CROSS_DEFINITION_TIME not in s
        # c* kaydın girdisidir (kuramsal değer); skorlanmaz.
        assert s["c_star"]["status"] == "no_prediction"
        assert s["total_impulse"]["status"] == "skipped_derived"

    def test_eksik_itici_ozelligi_kosmaz(self):
        rec = copy.deepcopy(_kayit("sol-nasa1979-bates-e1484"))
        del rec["propellants"]["burn_rate_exponent"]
        sonuc = ra.adapt_record(rec)
        assert sonuc["status"] == "insufficient_inputs"
        assert "hrma_propellant_key" in sonuc["missing"]

    @pytest.mark.parametrize("tid", ["sol-aedc1974-fw4s-ra307",
                                     "sol-marmureanu2014-s5k-293k"])
    def test_kismi_kayit_kosmaz(self, tid):
        rec = _kayit(tid)
        assert "kismi_kayit_kosmaz" in rec["tags"]
        assert ra.adapt_record(rec)["status"] == "insufficient_inputs"


class TestIticiAilesiAyrimi:
    def test_aile_cozumu(self):
        assert propellant_family_of(_kayit("sol-nakka2000-kappa-kdx002")) == "sugar"
        assert propellant_family_of(_kayit("sol-nasa1979-bates-e1484")) == "an_ap_al_htpb"
        assert propellant_family_of(_kayit("sol-nasa1979-bates-e1472")) == "an_hmx_ap_al_htpb"
        assert propellant_family_of({"motor_type": "hybrid", "propellants": {"fuel": "htpb"}}) is None
        assert propellant_family_of({"motor_type": "solid", "propellants": {"propellant": "x"}}) == "unclassified"

    def test_hicbir_hucre_aileleri_karistirmaz(self):
        kayitlar = [_kayit(t) for t in ("sol-nasa1979-bates-e1484",
                                        "sol-nasa1979-bates-e1491",
                                        "sol-nasa1979-bates-e1472",
                                        "sol-nakka2000-kappa-kdx002")]
        aile = {r["test_id"]: propellant_family_of(r) for r in kayitlar}
        st = run_correlation(records=kayitlar)["statistics"]
        hucreler = st["cells"] + st["low_confidence_cells"]
        assert hucreler
        kimlikler = set()
        for c in hucreler:
            assert {aile[e["test_id"]] for e in c["entries"]} == {c["propellant_family"]}
            kimlik = (c["motor_type"], c["propellant_family"], c["quantity"], c["confidence_band"])
            assert kimlik not in kimlikler
            kimlikler.add(kimlik)
        isp = [c for c in st["cells"] if c["quantity"] == "isp"]
        assert {c["propellant_family"] for c in isp} == {"an_ap_al_htpb", "an_hmx_ap_al_htpb"}
        assert {c["n"] for c in isp} == {2, 1}


# ---------------------------------------------------------------------------
# Kalem 6-7: teslim performansının dayanağı (sayı değişmez, beyan eklenir)
# ---------------------------------------------------------------------------
import re

_I18N = Path(__file__).resolve().parents[1] / "hrma" / "static" / "js" / "i18n_common.js"
_KOD_2FAZ_YOK = 'warn.solid.delivered_isp_excludes_two_phase_loss'


def _kndx(**ov):
    return SolidRocketEngine(
        grain_type='bates', propellant_type='kndx', chamber_diameter=56.2,
        grain_length=386.0, core_diameter=19.05, chamber_pressure=76.5,
        overrides=ov or None).calculate_performance()


def _apcp(**ov):
    return SolidRocketEngine(
        grain_type='bates', propellant_type='apcp', chamber_diameter=100.0,
        grain_length=500.0, core_diameter=40.0, chamber_pressure=40.0,
        overrides=ov or None).calculate_performance()


class TestTeslimPerformansiDayanagi:
    def test_kn_seker_iki_fazli_kayip_icermedigini_soyler(self):
        r = _kndx()
        uyari = [w for w in r['warnings'] if w['code'] == _KOD_2FAZ_YOK]
        assert len(uyari) == 1
        w = uyari[0]
        assert w['params'] == {'condensed_percent': 44.0,
                               'window_low_percent': 0.0,
                               'window_high_percent': 40.0}
        metin = w['fallback'].format(**w['params'])
        assert 'do NOT include the two-phase' in metin
        assert 'cannot be calculated' in metin
        assert 'does not mean the loss is zero' in metin
        # Kullanıcı metninde ham anahtar / durum kodu yok.
        assert not re.search(r'[a-z]+_[a-z_]+', metin), metin
        b = r['delivered_performance_basis']['two_phase_loss']
        assert b['applied_to_isp'] is False and b['calculable'] is False
        assert b['module_loss_percent'] is None
        assert 'not a zero loss' in b['basis']

    def test_pencere_icinde_bu_uyari_yok_ve_tani_sayisi_gorunur(self):
        r = _apcp()
        assert not [w for w in r['warnings'] if w['code'] == _KOD_2FAZ_YOK]
        b = r['delivered_performance_basis']['two_phase_loss']
        # Faz 3 (B1): pencere içinde tahmin UYGULANIR.
        assert b['calculable'] is True and b['applied_to_isp'] is True
        assert b['applied_source'] == 'module_estimate'
        assert b['applied_loss_percent'] == pytest.approx(
            r['two_phase_loss']['two_phase_loss_pct'])
        assert b['module_loss_percent'] == pytest.approx(
            r['two_phase_loss']['two_phase_loss_pct'])

    def test_kullanici_iki_faz_girdisi_varken_beyan_degisir(self):
        r = _kndx(two_phase_loss=0.90)
        assert not [w for w in r['warnings'] if w['code'] == _KOD_2FAZ_YOK]
        assert r['delivered_performance_basis']['two_phase_loss']['applied_to_isp'] is True
        assert r['isp_sea_level'] == pytest.approx(0.90 * _kndx()['isp_sea_level'], rel=1e-9)

    def test_yanma_verimi_varsayim_olarak_ayri_gorunur(self):
        b = _apcp()['delivered_performance_basis']['combustion_efficiency']
        assert b['value'] == 1.0
        assert b['source'] == 'assumed_default_not_verified'
        assert b['verified'] is False
        assert 'assumption, not a verified value' in b['basis']
        k = _apcp(combustion_efficiency=0.95)['delivered_performance_basis']['combustion_efficiency']
        assert k['value'] == 0.95 and k['source'] == 'user_input'
        assert k['verified'] is False

    def test_lule_tablosu_iki_fazli_kaybi_icermez_beyani(self):
        b = _apcp()['delivered_performance_basis']['nozzle_efficiency_table']
        assert b['includes_two_phase_loss'] is False
        assert 'SP-8039' in b['basis'] and 'Fig. 8' in b['basis']

    def test_uyari_metni_en_ve_tr(self):
        kaynak = _I18N.read_text(encoding='utf-8')
        satirlar = [s for s in kaynak.splitlines() if f"'{_KOD_2FAZ_YOK}'" in s]
        assert len(satirlar) == 2, 'EN ve TR metni birer kez olmalı'
        en, tr = satirlar
        assert 'do NOT include' in en and 'İÇERMEZ' in tr
        yer_tutucu = re.compile(r'\{(\w+)\}')
        assert set(yer_tutucu.findall(en)) == set(yer_tutucu.findall(tr)) == {
            'condensed_percent', 'window_low_percent', 'window_high_percent'}
        assert 'uydur' not in tr.lower() and 'invent' not in en.lower()


# ---------------------------------------------------------------------------
# Faz 3 — B1: pencere içindeki alüminyumlu kompozitte iki fazlı kayıp uygulanır
# ---------------------------------------------------------------------------
import shutil
import subprocess

_KOK = Path(__file__).resolve().parents[1]
_JS = _KOK / "hrma" / "static" / "js"
_SOLID_HTML = _KOK / "hrma" / "templates" / "solid.html"


def _motor(itici, **kw):
    taban = dict(chamber_diameter=290.0, grain_length=514.0,
                 core_diameter=198.0, chamber_pressure=38.0)
    ov = kw.pop('overrides', None)
    taban.update(kw)
    return SolidRocketEngine(grain_type='bates', propellant_type=itici,
                             overrides=ov, **taban)


def _tva(r):
    return r['detailed_analysis']['performance_metrics']['theoretical_vs_actual_isp']


class TestB1IkiFazliKayipUygulanir:
    @pytest.fixture(scope='class')
    def apcp(self):
        return _motor('apcp').calculate_performance()

    def test_uygulanan_carpan_yayimlanan_kayba_esit(self, apcp):
        blok = apcp['two_phase_loss']
        assert blok['status'] == 'computed'
        assert blok['applied_to_isp'] is True
        assert blok['two_phase_correction_status'] == sre.TWO_PHASE_STATUS_MODULE_APPLIED
        assert blok['two_phase_correction_verified'] is False
        kayip = blok['two_phase_loss_pct']
        assert kayip == pytest.approx(4.19, abs=0.05)
        assert blok['applied_efficiency'] == pytest.approx(1.0 - kayip / 100.0, rel=1e-12)
        tva = _tva(apcp)
        assert tva['two_phase_efficiency_applied'] == pytest.approx(1.0 - kayip / 100.0, rel=1e-12)
        assert tva['nozzle_efficiency_applied'] == pytest.approx(
            0.985 * (1.0 - kayip / 100.0), rel=1e-12)
        assert apcp['isp_sea_level'] == pytest.approx(226.14, abs=0.05)

    def test_ayni_carpani_kullanici_girerse_ayni_sonuc(self, apcp):
        """Çift sayım bekçisi: modülün çarpanını kullanıcı girdisi olarak
        vermek AYNI sonucu verir (kullanıcı girdisi modülün yerine geçer)."""
        eta = apcp['two_phase_loss']['applied_efficiency']
        kul = _motor('apcp', overrides={'two_phase_loss': eta}).calculate_performance()
        assert kul['two_phase_loss']['applied_to_isp'] is False
        assert _tva(kul)['two_phase_applied_source'] == 'user_input'
        for alan in ('isp_sea_level', 'isp_vacuum', 'total_impulse',
                     'average_thrust', 'max_thrust', 'burn_time'):
            assert kul[alan] == pytest.approx(apcp[alan], rel=1e-9), alan

    def test_kullanici_girdisi_modulun_yerine_gecer(self, apcp):
        kul = _motor('apcp', overrides={'two_phase_loss': 0.98}).calculate_performance()
        assert _tva(kul)['nozzle_efficiency_applied'] == pytest.approx(0.985 * 0.98, rel=1e-12)
        assert kul['isp_sea_level'] > apcp['isp_sea_level']
        assert not [w for w in kul['warnings']
                    if w['code'] == 'warn.solid.two_phase_estimate_applied']

    def test_basinc_ve_sure_degismez(self, apcp):
        """Kayıp yalnız itki katsayısına girer: basınç eğrisi ve süre aynı."""
        kul = _motor('apcp', overrides={'two_phase_loss': 0.90}).calculate_performance()
        assert kul['burn_time'] == apcp['burn_time']
        assert list(kul['thrust_curve']['pressure']) == list(apcp['thrust_curve']['pressure'])
        oran = np.array(apcp['thrust_curve']['thrust']) / np.array(kul['thrust_curve']['thrust'])
        assert np.allclose(oran, apcp['two_phase_loss']['applied_efficiency'] / 0.90, rtol=1e-9)

    def test_bilgi_kaydi_tek_ve_uyari_degil(self, apcp):
        kayit = [w for w in apcp['warnings']
                 if w['code'] == 'warn.solid.two_phase_estimate_applied']
        assert len(kayit) == 1 and kayit[0]['severity'] == 'info'
        assert not [w for w in apcp['warnings']
                    if w['code'].startswith('warn.solid.two_phase_correction_unverified')]
        metin = kayit[0]['fallback'].format(**kayit[0]['params'])
        assert 'include a two-phase' in metin and 'NASA SP-8039' in metin
        assert not re.search(r'[a-z]+_[a-z_]+', metin), metin

    @pytest.mark.parametrize('itici', ['htpb_ap_al', 'pban_ap_al'])
    def test_diger_aluminyumlu_katalog_iticileri(self, itici):
        r = _motor(itici).calculate_performance()
        assert r['two_phase_loss']['applied_to_isp'] is True
        assert 3.0 < r['two_phase_loss']['two_phase_loss_pct'] < 5.0

    @pytest.mark.parametrize('itici,durum', [
        ('apcp_nonaluminized', sre.TWO_PHASE_STATUS_ZERO),
        ('double_base', sre.TWO_PHASE_STATUS_ZERO),
        ('kndx', sre.TWO_PHASE_STATUS_OUT_OF_ENVELOPE),
        ('knsb', sre.TWO_PHASE_STATUS_OUT_OF_ENVELOPE),
    ])
    def test_pencere_disi_ve_yogun_fazsiz_iticide_uygulanmaz(self, itici, durum):
        r = _motor(itici).calculate_performance()
        assert r['two_phase_loss']['applied_to_isp'] is False
        assert r['two_phase_loss']['two_phase_correction_status'] == durum
        assert _tva(r)['two_phase_efficiency_applied'] == 1.0

    def test_kucuk_bogazda_uygulanmaz_ve_soylenir(self):
        """Boğaz 25,4 mm'nin altında: korelasyon sayı üretmez, çarpan girmez,
        'hesaplanamadı' beyanı ve eski uyarı kalır."""
        r = SolidRocketEngine(grain_type='bates', propellant_type='apcp',
                              chamber_diameter=54.0, grain_length=300.0,
                              core_diameter=20.0, chamber_pressure=50.0).calculate_performance()
        assert r['throat_diameter'] < 25.4
        blok = r['two_phase_loss']
        assert blok['status'] == 'OUT_OF_PUBLISHED_RANGE'
        assert blok['applied_to_isp'] is False
        assert _tva(r)['two_phase_efficiency_applied'] == 1.0
        b = r['delivered_performance_basis']['two_phase_loss']
        assert b['calculable'] is False and b['applied_to_isp'] is False
        assert 'NOT CALCULABLE for this motor' in b['basis']
        assert [w for w in r['warnings']
                if w['code'] == 'warn.solid.two_phase_correction_unverified_no_estimate']

    def test_tahmin_donanim_degisince_yeniden_hesaplanir(self):
        e = _motor('apcp')
        ilk = e._two_phase_module_state()['loss_percent']
        assert e._two_phase_module_state()['loss_percent'] == ilk
        e.pin_throat_area(1.5 * math.pi / 4 * (e._estimate_throat_diameter()) ** 2)
        assert e._two_phase_module_state()['loss_percent'] != pytest.approx(ilk, rel=1e-6)

    # ------------------------------------------------------------------
    # KARAR 0 (b) (ana model, 16-17 Kas 2026): istek lüle ya da kinetik verim
    # taşıyorsa yerleşik iki fazlı tahmin UYGULANMAZ. Ölçüm (faz 3,
    # olcum/f3_sayfa_verimi.json): katı sayfası form varsayılanlarını
    # (0,95 / 0,97 / 0,95) her koşuda gönderir; yerleşik tahmin üstüne
    # binince Isp / kuramsal 0,875 -> 0,841 (NASA BATES ölçülen 0,882-0,926):
    # kayıp iki kez sayılıyordu.
    #   Eski beklenti (faz 3): form verimleriyle applied_to_isp True +
    #   'request_efficiencies_overlap_two_phase_estimate' işareti.
    #   Yeni beklenti: applied_to_isp False, neden adıyla, tahmin teşhis
    #   olarak yayımlanır; sayfa sayıları 3.0.6 ile aynı.
    # ------------------------------------------------------------------
    SAYFA_VERIMLERI = {'nozzle_efficiency': 0.95, 'kinetic_efficiency': 0.97,
                       'combustion_efficiency': 0.95}

    def test_form_verimleri_tablo_diye_yayimlanmaz(self):
        """Gönderilen nozul verimi tablo değerinin yerine geçer; blok
        kaynağını adıyla söyler."""
        r = _motor('apcp', overrides=dict(self.SAYFA_VERIMLERI)).calculate_performance()
        b = r['delivered_performance_basis']
        assert b['nozzle_efficiency_table']['source'] == 'request_field'
        assert b['nozzle_efficiency_table']['value'] == 0.95
        assert b['nozzle_efficiency_table']['includes_two_phase_loss'] is None
        assert b['kinetic_efficiency'] == {'value': 0.97, 'source': 'request_field'}
        assert b['combustion_efficiency']['source'] == 'user_input'
        assert 'request_efficiencies_overlap_two_phase_estimate' not in b
        temiz = _motor('apcp').calculate_performance()['delivered_performance_basis']
        assert temiz['nozzle_efficiency_table']['source'] == 'propellant_table'
        assert temiz['kinetic_efficiency']['source'] == 'not_applied'
        assert temiz['two_phase_loss']['not_applied_reason'] is None
        assert temiz['two_phase_loss']['applied_to_isp'] is True

    def test_sayfa_verimleriyle_yerlesik_tahmin_uygulanmaz(self, apcp):
        """Çift sayım yok: itki katsayısına giren çarpan yalnız form
        verimleridir; tahmin teşhis olarak, nedeniyle yayımlanır."""
        r = _motor('apcp', overrides=dict(self.SAYFA_VERIMLERI)).calculate_performance()
        assert _tva(r)['nozzle_efficiency_applied'] == pytest.approx(0.95 * 0.97, rel=1e-12)
        assert _tva(r)['two_phase_efficiency_applied'] == 1.0
        blok = r['two_phase_loss']
        assert blok['applied_to_isp'] is False
        assert blok['status'] == 'computed'
        assert blok['two_phase_correction_status'] == sre.TWO_PHASE_STATUS_NOT_APPLIED
        assert 'NOT applied' in blok['two_phase_correction_status_basis']
        assert 'count that loss twice' in blok['two_phase_correction_status_basis']
        b = r['delivered_performance_basis']['two_phase_loss']
        assert b['applied_to_isp'] is False and b['applied_source'] is None
        assert b['not_applied_reason'] == 'request_efficiency_supplied'
        # tutulan tahmin = aynı motorun lüle / kinetik verim göndermeyen
        # yolda UYGULADIĞI tahmin (yanma verimi c*'ı değiştirdiği için kıyas
        # aynı yanma verimiyle yapılır: 4,19 -> 4,21)
        es = _motor('apcp', overrides={'combustion_efficiency': 0.95}).calculate_performance()
        assert b['not_applied_estimate_percent'] == pytest.approx(
            es['delivered_performance_basis']['two_phase_loss']['applied_loss_percent'],
            rel=1e-12)
        assert b['not_applied_estimate_percent'] == pytest.approx(
            blok['two_phase_loss_pct'], rel=1e-12)
        assert b['basis'].startswith('NOT APPLIED')
        assert not [w for w in r['warnings']
                    if w['code'] == 'warn.solid.two_phase_estimate_applied']
        assert [w for w in r['warnings']
                if w['code'] == 'warn.solid.two_phase_correction_unverified']

    def test_sayfa_yolu_isp_orani_cift_sayim_tasimaz(self, apcp):
        """Isp oranı: (form verimli) / (tablo verimli + tahmin) =
        yanma verimi etkisi dışında 0,95·0,97 / (0,985·(1 − kayıp)).
        Yanma verimi Isp'ye c* üzerinden girmediği (Isp = C_F·c*/g0, c*
        çarpanı aynı oranda) için oran ayrıca 0,95 taşır."""
        r = _motor('apcp', overrides={'nozzle_efficiency': 0.95,
                                      'kinetic_efficiency': 0.97}).calculate_performance()
        kayip = apcp['delivered_performance_basis']['two_phase_loss']['applied_loss_percent']
        beklenen = (0.95 * 0.97) / (0.985 * (1.0 - kayip / 100.0))
        gercek = (_tva(r)['nozzle_efficiency_applied']
                  / _tva(apcp)['nozzle_efficiency_applied'])
        assert gercek == pytest.approx(beklenen, rel=1e-12)

    @pytest.mark.parametrize('ov', [
        {'nozzle_efficiency': 0.985},      # tabloyla aynı sayı bile olsa girdi girdidir
        {'cf_efficiency': 0.96},
        {'kinetic_efficiency': 0.97},
    ])
    def test_tek_verim_girdisi_de_tahminin_yerine_gecer(self, ov):
        r = _motor('apcp', overrides=dict(ov)).calculate_performance()
        assert r['two_phase_loss']['applied_to_isp'] is False
        assert _tva(r)['two_phase_efficiency_applied'] == 1.0
        assert (r['delivered_performance_basis']['two_phase_loss']['not_applied_reason']
                == 'request_efficiency_supplied')

    def test_kinetik_verim_tam_bir_ise_tahmin_uygulanir(self, apcp):
        """Değer ölçütü: 1,0 çarpanı etkisizdir, tablo lüle verimi
        kullanılır; tahmin uygulanır ve sayı alan göndermeyen yolla aynıdır."""
        r = _motor('apcp', overrides={'kinetic_efficiency': 1.0}).calculate_performance()
        assert r['two_phase_loss']['applied_to_isp'] is True
        assert r['specific_impulse'] == apcp['specific_impulse']

    def test_yalniz_yanma_verimi_girdisi_tahmini_durdurmaz(self):
        """Yanma (c*) verimi lüle kaybı değildir; tahmin uygulanmaya devam eder."""
        r = _motor('apcp', overrides={'combustion_efficiency': 0.95}).calculate_performance()
        assert r['two_phase_loss']['applied_to_isp'] is True
        assert (r['delivered_performance_basis']['two_phase_loss']['not_applied_reason']
                is None)

    def test_kullanici_iki_faz_katsayisi_form_verimleriyle_birlikte_uygulanir(self):
        ov = dict(self.SAYFA_VERIMLERI, two_phase_loss=0.96)
        r = _motor('apcp', overrides=ov).calculate_performance()
        assert _tva(r)['two_phase_efficiency_applied'] == 0.96
        assert _tva(r)['nozzle_efficiency_applied'] == pytest.approx(
            0.95 * 0.97 * 0.96, rel=1e-12)
        b = r['delivered_performance_basis']['two_phase_loss']
        assert b['applied_source'] == 'user_input' and b['not_applied_reason'] is None

    def test_yogun_fazsiz_iticide_form_verimi_neden_uretmez(self):
        """Tahmin zaten yoksa 'istek verimi yüzünden uygulanmadı' denmez."""
        r = _motor('apcp_nonaluminized',
                   overrides=dict(self.SAYFA_VERIMLERI)).calculate_performance()
        b = r['delivered_performance_basis']['two_phase_loss']
        assert b['not_applied_reason'] is None
        assert b['not_applied_estimate_percent'] is None
        assert r['two_phase_loss']['two_phase_correction_status'] == sre.TWO_PHASE_STATUS_ZERO

    def test_lule_tablosu_kunyesi_olcumle_birlikte(self, apcp):
        b = apcp['delivered_performance_basis']['nozzle_efficiency_table']
        assert b['value'] == 0.985 and b['includes_two_phase_loss'] is False
        for parca in ('0.979', 'NASA-CR-158815', '0.945', '0.943'):
            assert parca in b['basis'], parca


class TestB1DogrulamaKayitlari:
    def test_yogun_faz_kesri_kayittan_sabitlenir(self):
        rec = _kayit("sol-nasa1979-bates-e1484")
        sonuc = ra.adapt_record(rec)
        assert any("egzoz Al2O3 kesriyle (0.283)" in n for n in sonuc["adapter_notes"])

    def test_sabitleme_kapisi(self):
        e = _motor('apcp')
        for kotu in (float('nan'), -0.1, 1.0, 2.0):
            with pytest.raises(ValueError):
                e.pin_condensed_mass_fraction(kotu, 'test')
        e.pin_condensed_mass_fraction(0.283, 'test')
        assert e._two_phase_condensed_fraction()[0] == 0.283
        e.pin_condensed_mass_fraction(None, 'test')
        assert e._two_phase_condensed_fraction()[0] == pytest.approx(0.3401, abs=1e-3)

    def test_nasa_ailesinde_isp_sapmasi_daraldi(self):
        kayitlar = [_kayit(t) for t in NASA_IDLER]
        st = run_correlation(records=kayitlar)["statistics"]
        isp = {c["propellant_family"]: c for c in st["cells"] if c["quantity"] == "isp"}
        # Faz 2 (B1 öncesi): +9,57 (n 4) ve +11,94 (n 2). Tolerans ±1,0.
        assert isp["an_ap_al_htpb"]["bias_pct"] == pytest.approx(5.0, abs=1.0)
        assert isp["an_hmx_ap_al_htpb"]["bias_pct"] == pytest.approx(7.25, abs=1.0)
        # Süre ve basınç değişmez (kayıp yalnız itki katsayısında).
        sure = {c["propellant_family"]: c for c in st["cells"] if c["quantity"] == "web_burn_time"}
        assert sure["an_ap_al_htpb"]["bias_pct"] == pytest.approx(-4.83, abs=0.05)


class TestB1ArayuzEtiketleri:
    def test_yeni_durum_kodunun_etiketi_her_sozlukte(self):
        ortak = (_JS / "i18n_common.js").read_text(encoding='utf-8')
        rapor = (_JS / "i18n_report.js").read_text(encoding='utf-8')
        for anahtar, kaynak in (("'common.code.module_estimate_applied'", ortak),
                                ("'solidtp.status.module_estimate_applied'", ortak),
                                ("'warn.solid.two_phase_estimate_applied'", ortak),
                                ("'report.value.module_estimate_applied'", rapor)):
            assert kaynak.count(anahtar) == 2, anahtar   # EN + TR
        assert "module_estimate_applied: 'common.code.module_estimate_applied'" in (
            _JS / "analysis_dock.js").read_text(encoding='utf-8')
        html = _SOLID_HTML.read_text(encoding='utf-8')
        assert "case 'module_estimate_applied':" in html

    def test_yeni_tr_metinlerde_tek_terim_nozul(self):
        for dosya, onek in (("i18n_common.js", "'warn.solid.two_phase_estimate_applied'"),
                            ("i18n_common.js", "'warn.solid.delivered_isp_excludes_two_phase_loss'"),
                            ("i18n_pages.js", "'solid.basis."),
                            ("i18n_pages.js", "'solid.js.mc_safety_limit_runs'")):
            for satir in (_JS / dosya).read_text(encoding='utf-8').splitlines():
                if onek in satir:
                    assert 'lüle' not in satir.lower(), satir[:80]

    def test_dayanak_notu_anahtarlari_en_ve_tr(self):
        sayfa = (_JS / "i18n_pages.js").read_text(encoding='utf-8')
        html = _SOLID_HTML.read_text(encoding='utf-8')
        anahtarlar = set(re.findall(r"TF?\('(solid\.basis\.[a-z_]+)'", html))
        assert len(anahtarlar) >= 10
        yer = re.compile(r'\{(\w+)\}')
        for a in sorted(anahtarlar):
            satirlar = [s for s in sayfa.splitlines() if f"'{a}':" in s]
            assert len(satirlar) == 2, a
            assert set(yer.findall(satirlar[0])) == set(yer.findall(satirlar[1])), a

    @pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
    def test_dayanak_notu_gercek_sonucla_cizilir(self, tmp_path):
        """solid.html'deki not işlevi sökülüp node'da GERÇEK çözücü
        sonuçlarıyla çalıştırılır: üç durum üç ayrı cümle üretir; blok
        yoksa hiçbir şey çizilmez."""
        html = _SOLID_HTML.read_text(encoding='utf-8')
        bas = html.index('        function deliveredBasisNoteHtml(results) {')
        son = html.index('        function renderDeliveredBasisNote(results) {')
        govdeler = {
            'apcp': _motor('apcp').calculate_performance()['delivered_performance_basis'],
            'kndx': _motor('kndx').calculate_performance()['delivered_performance_basis'],
            'kul': _motor('apcp', overrides={'two_phase_loss': 0.97, 'combustion_efficiency': 0.95}
                          ).calculate_performance()['delivered_performance_basis'],
            'db': _motor('double_base').calculate_performance()['delivered_performance_basis'],
            # Katı sayfasının HER koşuda gönderdiği form varsayılanları.
            'sayfa': _motor('apcp', overrides={'nozzle_efficiency': 0.95, 'kinetic_efficiency': 0.97,
                                               'combustion_efficiency': 0.95}
                            ).calculate_performance()['delivered_performance_basis'],
        }
        betik = tmp_path / "not.js"
        betik.write_text(
            "const T = (k, y) => y;\n"
            "const TF = (k, d, y) => y.replace(/\\{(\\w+)\\}/g, (m, a) => String(d[a]));\n"
            "const fmtNum = (v, n) => Number(v).toFixed(n);\n"
            + html[bas:son]
            + "\nconst g = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));\n"
            "const cikti = {};\n"
            "for (const k of Object.keys(g)) cikti[k] = deliveredBasisNoteHtml({delivered_performance_basis: g[k]});\n"
            "cikti.bos = deliveredBasisNoteHtml({});\n"
            "console.log(JSON.stringify(cikti));\n", encoding='utf-8')
        veri = tmp_path / "govde.json"
        veri.write_text(json.dumps(govdeler), encoding='utf-8')
        p = subprocess.run(["node", str(betik), str(veri)], capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, p.stderr
        c = json.loads(p.stdout)
        assert c['bos'] == ''
        assert 'applied, built-in estimate' in c['apcp'] and '4.19' in c['apcp']
        assert 'assumed default, not verified' in c['apcp']
        assert 'cannot be calculated' in c['kndx'] and 'not a zero loss' in c['kndx']
        assert 'applied from the factor you entered' in c['kul'] and '3.00' in c['kul']
        assert 'value from the form, not verified' in c['kul']
        # Form verimleri tablo değerinin yerine geçer: "tablo" denmez, kinetik
        # verim de görünür ve yerleşik tahminle üst üste binme söylenir.
        assert 'Nozzle efficiency 0.950: value from the form' in c['sayfa']
        assert 'Nozzle table efficiency' not in c['sayfa']
        assert 'Kinetic efficiency 0.970' in c['sayfa']
        # KARAR 0 (b): form verimleri varken yerleşik tahmin uygulanmaz; not
        # bunu, tutulan tahminin sayısıyla söyler (eski beklenti: 'üst üste
        # biniyor, kendi katsayınızı girin' uyarısı).
        # V307/ONARIM-İTKİ-B (M7-ITKI-3): not artık tahmini TUTAN alanları
        # formdaki adlarıyla sayar (eski metin "the nozzle or kinetic
        # efficiency comes from the form" ve "Clear both fields" Cf alanını
        # adlandırmıyordu; mühendis turu K8). Kural (KARAR 0 (b)) aynı.
        uygulanmadi = 'is not applied, because these form fields carry an efficiency'
        assert uygulanmadi in c['sayfa'] and 'built-in estimate (4.21 %)' in c['sayfa']
        assert 'carry an efficiency: Nozzle Efficiency ηn, Kinetic Efficiency.' in c['sayfa']
        assert 'applied, built-in estimate' not in c['sayfa']
        assert uygulanmadi not in c['apcp'] and uygulanmadi not in c['kul']
        assert 'no condensed phase' in c['db']
        for html_parca in c.values():
            assert 'undefined' not in html_parca and 'NaN' not in html_parca

    def test_korelasyon_paneli_kapsam_disi_katmani_ve_aileyi_cizer(self):
        panel = (_JS / "panels" / "correlation_panel.js").read_text(encoding='utf-8')
        assert "['out_of_scope', 'panel.correlation.layerOutOfScope'" in panel
        assert 'data-propellant-family' in panel
        ortak = (_JS / "i18n_common.js").read_text(encoding='utf-8')
        for a in ('panel.correlation.layerOutOfScope', 'panel.correlation.layerOutOfScopeNote',
                  'panel.correlation.familyTip', 'panel.correlation.family.sugar',
                  'panel.correlation.family.an_ap_al_htpb'):
            assert ortak.count(f"'{a}':") == 2, a
