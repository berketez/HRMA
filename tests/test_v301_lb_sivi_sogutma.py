# -*- coding: utf-8 -*-
"""V301 / L-B — sıvı soğutma: cidar sıcaklığı (SV-05), film soğutma (SV-08),
teknik PDF termal + enjektör bölümü (SV-14).

Kanıt dizini: docs/scofield/raw/OH/V301/kati-sivi/L-B/ (RAPOR.md, önce/sonra
ölçümü, ters mutasyon sonuçları). Yük, A-sivi denetiminin Playwright'la
aldığı GERÇEK form yüküdür (``yuk_form_en.json``) + itki 10 kN, Pc 100 bar,
O/F 2,5 — ölçüm betiğiyle (``olcum.py``) aynı.
"""
import contextlib
import io
import json
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
KANIT = KOK / 'docs' / 'scofield' / 'raw' / 'OH' / 'V301' / 'kati-sivi' / 'L-B'
FORM = {k: v for k, v in json.loads(
    (KANIT / 'yuk_form_en.json').read_text(encoding='utf-8')).items()
    if v is not None}
LB_ZORUNLU_ALANLAR = {'thrust': 10000, 'chamber_pressure': 100, 'mixture_ratio': 2.5}
SIL = object()

LB_VAKALARI = {
    'varsayilan': {},
    'cidar2': dict(chamber_wall_thickness=2),
    'ablatif': dict(cooling_type='ablative'),
    'film_tip_sil': dict(cooling_type='film_cooling',
                         film_cooling_percent=SIL),
    'film_tip0': dict(cooling_type='film_cooling', film_cooling_percent=0),
    'film_tip10': dict(cooling_type='film_cooling', film_cooling_percent=10),
    'regen_film10': dict(film_cooling_percent=10),
}

#: Rejeneratif varsayılanda performans sayıları DEĞİŞMEMELİ (önce ölçümü,
#: taban b07272a71: olcum_once.json ``varsayilan``).
ONCE_VARSAYILAN = {'isp_sea_level': 244.8633520002479,
                   'total_mass_flow': 4.164429689653583}


def _yuk(ez):
    d = dict(FORM)
    d.update(LB_ZORUNLU_ALANLAR)
    for k, v in ez.items():
        if v is SIL:
            d.pop(k, None)
        else:
            d[k] = v
    return d


@pytest.fixture(scope='module')
def yanit():
    from hrma.app import app
    out = {}
    with app.test_client() as c:
        for ad, ez in LB_VAKALARI.items():
            with contextlib.redirect_stdout(io.StringIO()):
                r = c.post('/calculate_liquid', json=_yuk(ez))
            assert r.status_code == 200, (ad, r.get_data(as_text=True)[:300])
            out[ad] = r.get_json()
    return out


def _kodlar(y, sev=None):
    return [w.get('code') for w in (y.get('input_warnings') or [])
            if isinstance(w, dict) and (sev is None or w.get('severity') == sev)]


# ---------------------------------------------------------------------------
# SV-05 — hedef ⟷ çözülen cidar sıcaklığı
# ---------------------------------------------------------------------------
class TestSV05Cidar:

    def test_ince_cidarda_cozulen_ve_hedef_ayri_hukum_asildi(self, yanit):
        y = yanit['cidar2']
        cs, tp = y['cooling_system'], y['thermal_protection']
        tepe = tp['station_march']['peak_wall_temperature_K']
        assert cs['wall_temperature_solved_K'] == pytest.approx(tepe,
                                                                rel=1e-12)
        assert cs['wall_temperature_target_K'] == pytest.approx(800.0)
        assert cs['wall_temperature_solved_status'] == 'SOLVED'
        assert tepe > 800.0
        assert cs['wall_temperature_limit_status'] == 'EXCEEDED'
        assert cs['wall_temperature_solved_source'].startswith('solved')

    def test_cozum_yoksa_hukum_not_evaluated(self, yanit):
        for ad in ('varsayilan', 'ablatif', 'film_tip10'):
            cs = yanit[ad]['cooling_system']
            assert cs['wall_temperature_solved_K'] is None, ad
            assert cs['wall_temperature_limit_status'] == 'NOT_EVALUATED', ad
            assert cs['wall_temperature_not_solved_reason'], ad
            assert cs['wall_temperature_not_solved_code'], ad

    def test_yapi_hukmu_cozulen_sicaklikta_ve_geri_cekilir(self, yanit):
        y = yanit['cidar2']
        st = y['structural_analysis']['chamber_structure']
        tepe = y['thermal_protection']['station_march'][
            'peak_wall_temperature_K']
        assert st['wall_temperature'] == pytest.approx(tepe, rel=1e-12)
        assert st['wall_temperature_solved'] is True
        assert st['wall_temperature_design_target_K'] == pytest.approx(800.0)
        # Erime üstü: geçerlilik ölçütü hükmü geri çeker.
        assert st['model_validity_limit_exceeded'] is True
        assert st['verdict_withheld'] is True
        assert st['verdict_assumption'] is None

    def test_yapi_hukmu_varsayimsa_beyanli(self, yanit):
        st = yanit['varsayilan']['structural_analysis']['chamber_structure']
        assert st['wall_temperature_solved'] is False
        assert st['wall_temperature_source'].startswith('ASSUMPTION')
        assert 'not a solved result' in st['verdict_assumption']
        assert st['wall_temperature'] == pytest.approx(800.0)

    def test_marsin_kritik_hukmu_kok_uyarilarda(self, yanit):
        # V301/L-KARBON (26 Eki): LOX/RP-1 karbon birikimi (SP-125 Şk. 4-25)
        # artık marşta. Bu vakada (SS304, 2 mm) birikimin altındaki metal
        # 1564 K: erimenin (1673 K) ALTINDA, iznin (1073 K) üstünde ->
        # nominal hüküm 'solved_wall_above_allowable'. Erime hükmü birikimin
        # DÖKÜLDÜĞÜ yerel cidara taşındı (SP-8087 §3.4.1; 3084 K) ve kök
        # uyarıya marş notu koduyla, marşın kendi cümlesiyle iner. Eski
        # beklenti 'solved_wall_above_melting' (birikimsiz model) idi.
        y = yanit['cidar2']
        sm = y['thermal_protection']['station_march']
        kritik = _kodlar(y, 'critical')
        assert 'warn.liquid.solved_wall_above_allowable' in kritik
        assert 'warn.liquid.wall_temp_limit_exceeded' in kritik
        kayit = [w for w in y['input_warnings']
                 if w.get('code') == 'warn.liquid.solved_wall_above_allowable'][0]
        assert kayit['params']['solved_K'] == pytest.approx(
            round(sm['peak_wall_temperature_K'], 1))
        dokulme = [w for w in y['input_warnings']
                   if w.get('code') == 'warn.liquid.regen_march_note'
                   and w.get('severity') == 'critical']
        assert len(dokulme) == 1
        assert dokulme[0]['params']['detail'].startswith(
            'CRITICAL: where the carbon deposit spalls')
        assert sm['carbon_deposit']['spalled_above_melting'] is True

    def test_tek_sogutucu_cikis_sicakligi_mars(self, yanit):
        y = yanit['cidar2']
        cs, tp = y['cooling_system'], y['thermal_protection']
        sm = tp['station_march']
        assert cs['coolant_exit_temperature'] == pytest.approx(
            sm['coolant_exit_temperature_K'], rel=1e-12)
        assert tp['coolant_exit_temperature'] == pytest.approx(
            sm['coolant_exit_temperature_K'], rel=1e-12)
        bulk = tp['channel_circuit_reconciliation']['bulk_chain']
        assert cs['coolant_exit_temperature_bulk_estimate_K'] == \
            pytest.approx(bulk['coolant_exit_temperature_K'], rel=1e-12)
        assert cs['coolant_exit_temperature'] == pytest.approx(
            cs['coolant_inlet_temperature'] + cs['coolant_temperature_rise'],
            rel=1e-12)

    def test_regen_varsayilan_performansi_degismedi(self, yanit):
        y = yanit['varsayilan']
        for alan, deger in ONCE_VARSAYILAN.items():
            assert y[alan] == pytest.approx(deger, rel=1e-12), alan


# ---------------------------------------------------------------------------
# SV-08 — film soğutma
# ---------------------------------------------------------------------------
class TestSV08Film:

    def test_film_tipinde_ceket_yayimlanmaz(self, yanit):
        cs = yanit['film_tip10']['cooling_system']
        assert cs['regenerative_jacket_status'] == 'NOT_APPLICABLE'
        for alan in ('coolant_flow_rate', 'cooling_pressure_drop',
                     'coolant_exit_temperature', 'coolant_velocity',
                     'channel_width_mm'):
            assert cs[alan] is None, alan
        assert cs['cooling_channels'] == 0
        assert yanit['film_tip10']['thermal_protection'][
            'coolant_circuit_status'] == 'no_cooling_channels'

    @pytest.mark.parametrize('ad', ['film_tip10', 'regen_film10'])
    def test_film_debisi_performanstan_dusulur(self, yanit, ad):
        y0, y = yanit['varsayilan'], yanit[ad]
        perf = y['cooling_system']['film_cooling']['performance']
        f = 0.10
        assert perf['status'] == 'APPLIED'
        # Çekirdek değişmez; film çekirdek yakıta EK: f = film / toplam yakıt.
        assert perf['core_mass_flow_kg_s'] == pytest.approx(
            y0['total_mass_flow'], rel=1e-12)
        assert perf['film_coolant_flow_kg_s'] == pytest.approx(
            f * y['fuel_flow'], rel=1e-12)
        assert y['total_mass_flow'] == pytest.approx(
            y0['total_mass_flow'] + perf['film_coolant_flow_kg_s'],
            rel=1e-12)
        oran = perf['core_mass_flow_kg_s'] / y['total_mass_flow']
        assert y['isp_sea_level'] == pytest.approx(
            y0['isp_sea_level'] * oran, rel=1e-12)
        assert y['isp_sea_level'] < y0['isp_sea_level']
        # İtki sabit: F = ṁ_toplam·Isp_teslim·g0 = ṁ_çekirdek·Isp_çekirdek·g0.
        assert y['total_mass_flow'] * y['isp_sea_level'] == pytest.approx(
            y0['total_mass_flow'] * y0['isp_sea_level'], rel=1e-12)

    def test_film_tipi_sifir_film_adli_kritik_uyari(self, yanit):
        assert 'warn.liquid.film_cooling_type_without_film' in _kodlar(
            yanit['film_tip0'], 'critical')
        perf = yanit['film_tip0']['cooling_system']['film_cooling'][
            'performance']
        assert perf['status'] == 'NO_FILM_FLOW'

    def test_film_tipi_alan_yoksa_beyanli_yuzde5(self, yanit):
        film = yanit['film_tip_sil']['cooling_system']['film_cooling']
        assert film['film_cooling_percent'] == pytest.approx(5.0)
        assert film['film_cooling_percent_source'].startswith('not supplied')
        assert film['performance']['status'] == 'APPLIED'


# ---------------------------------------------------------------------------
# SV-14 — teknik PDF termal + enjektör bölümü
# ---------------------------------------------------------------------------
def _hikaye_metni(hikaye):
    parcalar = []
    for o in hikaye:
        if hasattr(o, 'text'):
            parcalar.append(str(o.text))
        hucreler = getattr(o, '_cellvalues', None)
        if hucreler:
            for satir in hucreler:
                parcalar.append(' | '.join(str(h) for h in satir))
    return '\n'.join(parcalar)


class TestSV14Pdf:

    def test_termal_bolum_cozulen_hedef_ve_erime_hukmu(self, yanit):
        from hrma.export.pdf_generator import PDFReportGenerator
        y = yanit['cidar2']
        g = PDFReportGenerator()
        metin = _hikaye_metni(g._create_liquid_thermal_section(
            y, {'motor_type': 'liquid'}))
        assert 'Thermal Protection and Cooling' in metin
        assert 'liner failure' in metin
        tepe = y['cooling_system']['wall_temperature_solved_K']
        assert 'Hot-wall temperature, SOLVED (peak) | %.0f | K' % tepe in metin
        assert 'Hot-wall temperature TARGET (max_wall_temp) | 800 | K' in metin
        assert 'Wall temperature limit check | EXCEEDED' in metin

    def test_termal_bolum_cozum_yoksa_uydurmaz(self, yanit):
        from hrma.export.pdf_generator import PDFReportGenerator
        metin = _hikaye_metni(PDFReportGenerator()._create_liquid_thermal_section(
            yanit['varsayilan'], {'motor_type': 'liquid'}))
        assert 'Hot-wall temperature, SOLVED (peak) | not published' in metin
        assert 'NOT_EVALUATED' in metin

    def test_film_ve_enjektor_bolumu(self, yanit):
        from hrma.export.pdf_generator import PDFReportGenerator
        g = PDFReportGenerator()
        y = yanit['film_tip10']
        metin = _hikaye_metni(g._create_liquid_thermal_section(
            y, {'motor_type': 'liquid'}))
        assert 'Film Cooling' in metin
        kayip = y['cooling_system']['film_cooling']['performance'][
            'isp_loss_pct']
        assert 'Isp loss charged for the film | %.2f | %%' % kayip in metin
        enj = _hikaye_metni(g._create_liquid_injector_section(
            y, {'motor_type': 'liquid'}))
        assert 'Injector' in enj
        assert 'Fuel injector pressure drop | %.2f | bar' % y[
            'injection_system']['fuel_pressure_drop'] in enj

    def test_hibrit_yanitta_sivi_bolumu_basilmaz(self):
        from hrma.export.pdf_generator import PDFReportGenerator
        g = PDFReportGenerator()
        assert g._create_liquid_thermal_section(
            {'thermal_protection': {}}, {'motor_type': 'hybrid'}) == []
        assert g._create_liquid_injector_section(
            {'injection_system': {}}, {'motor_type': 'hybrid'}) == []


# ---------------------------------------------------------------------------
# Ekran: kart ve panel tohumu çözülen değeri kullanır; film ipucu
# ---------------------------------------------------------------------------
def _oku(yol):
    return (KOK / yol).read_text(encoding='utf-8')


def test_sogutma_karti_cozulen_sicakligi_basar():
    html = _oku('hrma/templates/liquid.html')
    assert 'cooling_system.wall_temperature_hot, 0)' not in html
    assert 'coolCs.wall_temperature_solved_K' in html
    assert 'coolCs.wall_temperature_target_K' in html


def test_panel_tohumu_cozulen_sicaklik():
    js = _oku('hrma/static/js/analysis_dock.js')
    m = re.search(r"liquid:\s*\{\s*hot:\s*'([^']+)',\s*cold:\s*'([^']+)',"
                  r"\s*source:\s*'([^']+)'", js)
    assert m, 'sıvı cidar sıcaklığı yolları bulunamadı'
    assert m.groups() == ('cooling_system.wall_temperature_solved_K',
                          'cooling_system.wall_temperature_solved_cold_K',
                          'cooling_system.wall_temperature_solved_source')
    assert 'user input' in js.split('function wallTempSourceIsSolved')[1][:600]


def test_film_ipucu_en_tr():
    html = _oku('hrma/templates/liquid.html')
    assert 'data-i18n="liq.ui.film_cooling_tip"' in html
    js = _oku('hrma/static/js/i18n_pages.js')
    degerler = re.findall(r"'liq\.ui\.film_cooling_tip':\s*'((?:[^'\\]|\\.)*)'",
                          js)
    assert len(degerler) == 2, degerler
    en, tr = degerler
    for metin in (en, tr):
        assert '30' in metin and '5' in metin
    assert any(h in tr for h in 'çğıöşüÇĞİÖŞÜ')
