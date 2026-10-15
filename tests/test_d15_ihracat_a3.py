"""ÖH Dalga-15 · kulvar **ihracat** · aşama 3 — onarım bekçileri.

Kapsanan kalemler (kaynak: ``docs/scofield/raw/P09/{B2,B3,B4}-rapor.md``,
ölçüm ``docs/scofield/raw/OH/D15/ihracat/a3/{once,sonra}.json``):

* P9B2-26  NEGATİF tank çapı → fail-closed (ÇÜRÜTÜLDÜ; kapı bir daha açılmasın)
* P9B3-05  termal KRİTİK hüküm PDF'e iniyor
* P9B3-11  .eng zarf ⟷ kütle tutarlılığı (ima edilen bulk yoğunluk kapısı)
* P9B3-12  iki kuru kütlenin uzlaştırması ÜRÜN YOLUNDA basılıyor
* P9B3-13  emniyet çizicisi çok panelli figürü reddediyor, açıklamaları çiziyor
* P9B3-14  .ork örnek yapı sayıları BEYANLI ve kullanıcı değeriyle ezilebilir
* P9B3-26  çözücünün BEYAN blokları PDF'e iniyor
* P9B4-01  RocketCEA ft/s + Rankine → SI (üretici + paket anlık görüntüsü)
* P9B4-05  PubChem kimlik kapısı çevrimdışı kayda da uygulanıyor
* P9B4-07  N2O yoğunluğu (ÇÜRÜTÜLDÜ; 1220 kanalı bir daha açılmasın)
* P9B4-08  kriyojenik DBTT hükmü takma adla TERSİNE dönmüyor

Her bekçi ters-mutasyonla kırmızı görüldü; kanıt
``docs/scofield/raw/OH/D15/ihracat/a3/mutasyon.json``.
"""
import contextlib
import io
import json
import math
import os
import sys

import pytest
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if KOK not in sys.path:
    sys.path.insert(0, KOK)

P09 = os.path.join(KOK, 'docs', 'scofield', 'raw', 'P09', 'cikti')
SNAPSHOT = os.path.join(KOK, 'hrma', 'data', 'offline_snapshot.json')

R_U = 8314.462618  # J/(kmol*K)


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _motor(ad):
    with open(kanit_gerekli(os.path.join(P09, f'motor_{ad}.json')), encoding='utf-8') as fh:
        return json.load(fh)


@pytest.fixture(scope='module')
def hibrit():
    return _motor('hybrid')


@pytest.fixture(scope='module')
def kati():
    return _motor('solid')


@pytest.fixture(scope='module')
def sivi():
    return _motor('liquid')


@pytest.fixture(scope='module')
def anlik_goruntu():
    with open(SNAPSHOT, encoding='utf-8') as fh:
        return json.load(fh)


def _pdf_metni(istemci, motor_data, analysis_results):
    r = _sessiz(istemci.post, '/api/export-pdf/complete',
                json={'motor_data': motor_data,
                      'analysis_results': analysis_results})
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    ham = r.get_data()
    assert ham[:4] == b'%PDF'
    from pypdf import PdfReader
    rd = PdfReader(io.BytesIO(ham))
    return '\n'.join((p.extract_text() or '') for p in rd.pages)


@pytest.fixture(scope='module')
def hibrit_pdf_metni(istemci, hibrit):
    md = {
        'motor_name': 'D15-A3-HIBRIT',
        'motor_type': 'hybrid',
        'chamber_pressure': hibrit.get('chamber_pressure'),
        'thrust': hibrit.get('thrust'),
        'heat_transfer_analysis': hibrit.get('heat_transfer_analysis'),
        'structural_analysis': hibrit.get('structural_analysis'),
    }
    return _pdf_metni(istemci, md, hibrit)


# =====================================================================
# P9B2-26 — NEGATİF/SIFIR tank ölçüsüyle imalat paketi ÜRETİLMEZ
# (kalem ölçümle ÇÜRÜTÜLDÜ: kapı zaten kapalıydı; bekçi kapıyı kilitler)
# =====================================================================
def _tank_govdesi(cap_mm, boy_mm=800.0):
    def _tank(d):
        return {
            'dimensions': {'diameter': d, 'length': boy_mm,
                           'wall_thickness': 3.0},
            'structural': {'material': 'Al 2024-T3',
                           'pressure_rating': 60.0, 'safety_factor': 2.0},
            'internal_structures': {
                'slosh_baffles': {'count': 2, 'outer_diameter': abs(d) * 0.95,
                                  'inner_diameter': abs(d) * 0.3,
                                  'thickness': 2.0, 'hole_diameter': 10.0,
                                  'open_area_ratio': 0.3,
                                  'material': 'Al 2024-T3', 'spacing': 250.0},
                'anti_vortex_device': {
                    'diameter': abs(d) * 0.3, 'height': 40.0,
                    'vane_count': 4, 'vane_thickness': 2.0,
                    'material': 'Al 2024-T3'},
            },
        }
    return {'tank_data': {'oxidizer_tank': _tank(cap_mm),
                          'fuel_tank': _tank(cap_mm)}}


class TestB226NegatifTank:
    """Ölçüldü (once.json): negatif çap ve sıfır boy 422 alıyor."""

    def test_negatif_cap_422_ve_alan_adi(self, istemci):
        r = _sessiz(istemci.post, '/export_tank_cad',
                    json=_tank_govdesi(-743.7556))
        assert r.status_code == 422
        j = r.get_json()
        assert j['error'] == 'invalid_tank_data'
        alanlar = {(p['field'], p['reason']) for p in j['invalid_fields']}
        assert ('oxidizer_tank.dimensions.diameter', 'not_positive') in alanlar
        assert ('fuel_tank.dimensions.diameter', 'not_positive') in alanlar

    def test_sifir_boy_422(self, istemci):
        r = _sessiz(istemci.post, '/export_tank_cad',
                    json=_tank_govdesi(743.7556, boy_mm=0.0))
        assert r.status_code == 422
        alanlar = {p['field'] for p in r.get_json()['invalid_fields']}
        assert 'oxidizer_tank.dimensions.length' in alanlar

    def test_saglikli_tank_hala_paket_uretiyor(self, istemci):
        """ÖK-22: sağlıklı envanter gevşetilmez — 200 ve dolu ZIP."""
        r = _sessiz(istemci.post, '/export_tank_cad',
                    json=_tank_govdesi(743.7556))
        assert r.status_code == 200
        assert r.get_data()[:2] == b'PK'
        assert len(r.get_data()) > 10000


# =====================================================================
# P9B3-05 — termal KRİTİK hüküm PDF'e iniyor
# =====================================================================
class TestB305TermalHukum:

    def test_cozucu_hukmu_gercekten_kritik(self, hibrit):
        """Fikstür doğrulaması: bekçi gerçek bir kritik vakaya bakıyor."""
        hta = hibrit['heat_transfer_analysis']
        assert hta['gas_side_analysis']['wall_temperature_unphysical'] is True
        assert hta['safety_analysis']['melting_safety_factor'] < 1.0
        assert hta['safety_analysis']['risk_level'] == 'HIGH'

    def test_pdf_ergime_hukmunu_basiyor(self, hibrit_pdf_metni):
        alt = hibrit_pdf_metni.lower()
        assert 'unphysical' in alt
        assert 'melting' in alt
        assert 'critical' in alt

    def test_pdf_ergime_emniyet_katsayisini_basiyor(self, hibrit_pdf_metni):
        assert 'Melting Safety Factor' in hibrit_pdf_metni

    def test_pdf_termal_risk_seviyesini_basiyor(self, hibrit_pdf_metni):
        assert 'Thermal Risk Level' in hibrit_pdf_metni

    def test_besleyici_termal_hukmu_tasiyor(self, hibrit):
        from hrma.app import _build_pdf_analysis_sections
        out = _build_pdf_analysis_sections(
            {'heat_transfer_analysis': hibrit['heat_transfer_analysis']},
            hibrit)
        assert out['thermal']['wall_temperature_unphysical'] is True
        assert out['thermal']['melting_safety_factor'] < 1.0
        assert out['thermal']['risk_level'] == 'HIGH'


# =====================================================================
# P9B3-26 — çözücünün BEYAN blokları PDF'e iniyor
# =====================================================================
class TestB326CozucuBeyanlari:

    def test_besleyici_beyan_blogunu_kuruyor(self, hibrit):
        from hrma.app import _build_pdf_analysis_sections
        out = _build_pdf_analysis_sections({}, hibrit)
        beyan = out['solver_declarations']
        assert len(beyan['not_modelled']) == 6
        assert 'feed_system' in beyan['not_modelled']
        kodlar = {w.get('code') for w in beyan['warnings']}
        assert 'warn.hybrid.htpb_coeff_bias' in kodlar
        assert 'burn_time_basis' in beyan['basis_notes']
        assert 'l_star_note' in beyan['basis_notes']

    def test_pdf_modellenmedi_listesini_basiyor(self, hibrit_pdf_metni):
        assert 'not modelled' in hibrit_pdf_metni.lower()
        assert 'Declarations Made By This Analysis' in hibrit_pdf_metni

    def test_pdf_basis_metinlerini_basiyor(self, hibrit_pdf_metni):
        assert 'burn time basis' in hibrit_pdf_metni.lower()
        assert 'l star note' in hibrit_pdf_metni.lower()

    def test_pdf_olculmus_sapma_uyarisini_basiyor(self, hibrit_pdf_metni):
        assert 'htpb_coeff_bias' in hibrit_pdf_metni


# =====================================================================
# P9B3-11 — .eng zarfı ile yüklü itici kütlesi tutarlı olmalı
# =====================================================================
class TestB311EngYogunlukKapisi:

    def test_imkansiz_yogunluk_reddediliyor(self, kati):
        """ÇEVRİLDİ (ÖH D15 birleşme etkileşimi, 1 Eylül 2026).

        Bu bekçi ``sivi`` fikstürünün REDDEDİLMESİNİ şart koşuyordu. Kapı
        RASP zarfını (KAMARA) tank içeriğiyle karşılaştırıyordu; kendi ret
        gerekçesi de "ikisi aynı hacme ait DEĞİLDİR" diyordu. Birleşmede
        ölçüldü:

          * Kapıyı geçebilmek için sıvı motorun RASP boy alanının **40,86 m**
            olması gerekiyordu — gerçek kamara boyunun 584 katı, dosyanın
            kendi fiziksel boy bandının (50 mm - 5 m) 8 katı dışında. Yani
            kapıyı HİÇBİR sıvı motor geçemezdi: fizik denetimi değil, sıvı
            `.eng` ihracatının toptan kaldırılmasıydı.
          * Bedeli ölçüldü: 15 kazanılmış bekçi kırmızıya döndü (kasa çapı =
            STEP çapı P17S1-01'in 7'si, `test_unit_contract`in 5'i,
            `TestEngInertMassDeclaration`ın 3'ü).

        Kalemin ÖZÜ (imkânsız yoğunluklu bir motor satırı yazılmaz) AYNEN
        korunuyor, eşik de aynı tek kaynaktan (3.000 kg/m3). Değişen tek şey
        kapının hangi hacme sorduğu: zarf iticiyi tutuyorsa zarfa, çözücü
        ayrı tank yayımlıyorsa BEYAN EDİLEN tank hacmine.

        Bu bekçi artık kapının FAIL-CLOSED ayağını, zarfın gerçekten iticiyi
        tuttuğu bir motorda ölçer: katı motorun kütlesi 1000x yapılır
        (gerçek kasa çapı, tank beyanı YOK) -> dosya YAZILMAZ.
        """
        from hrma.export.openrocket_integration import (
            OpenRocketExportDataError, OpenRocketExporter)
        ork = OpenRocketExporter()
        bozuk = dict(kati)
        assert 'propellant_tanks' not in bozuk, (
            'katı motor tank yayımlıyor — bu vaka zarf ayağını ölçemez')
        bozuk['propellant_mass_total'] = 1000.0 * float(
            ork.resolve_propellant_mass(kati)[0])
        with pytest.raises(OpenRocketExportDataError) as exc:
            _sessiz(ork.export_motor_file, bozuk)
        metin = str(exc.value)
        assert 'bulk propellant density' in metin
        assert 'propellant_mass_kg' in metin
        assert 'no motor file is written' in metin

    def test_ayri_tankli_motor_dosyayi_alir_ama_BEYANLA(self, sivi):
        """İkinci ayak: sıvı motor dosyayı alır, ayrışma SUSTURULMAZ.

        Susmak (birleşme öncesi davranış) da yazmamak (P9B3-11'in ilk hâli)
        da okuyanı yanıltıyordu. RASP biçiminde "itici başka yerde" diyecek
        bir alan yok; o yüzden ayrışma sayılarıyla yorum satırına yazılır ve
        OpenRocket'ın ağırlık merkezi/apoje hesabının bu dosyadan YANLIŞ
        çıkacağı ADIYLA söylenir.
        """
        from hrma.export.openrocket_integration import (
            OpenRocketExporter, PROPELLANT_DENSITY_MAX_KG_M3)
        ork = OpenRocketExporter()
        eng = _sessiz(ork.export_motor_file, sivi)
        assert ('WARNING: the loaded propellant is NOT inside the envelope'
                in eng), 'ayrışma sessizce geçiyor'
        assert 'OpenRocket places the loaded mass INSIDE the motor envelope' \
            in eng, 'okuyan, hesabın neden yanlış olacağını öğrenmiyor'
        assert 'propellant_tanks' in eng, 'hacmin künyesi yazılmıyor'

        # Beyan edilen hacim GERÇEKTEN ölçülmüş olmalı: aynı sayıyı burada
        # bağımsızca hesapla ve dosyadakiyle karşılaştır.
        hacim_m3, kunye = ork._declared_propellant_volume_m3(sivi)
        assert hacim_m3 is not None and kunye
        kutle = float(ork.resolve_propellant_mass(sivi)[0])
        rho = kutle / hacim_m3
        assert 0.0 < rho <= PROPELLANT_DENSITY_MAX_KG_M3, (
            f'tank hacmi de bandı aşıyor ({rho:.1f}) — bu vakada dosya '
            'YAZILMAMALIYDI')
        assert f'{rho:,.1f} kg/m3 in the declared tank volume' in eng, (
            'dosyadaki sayı bağımsız hesapla tutmuyor')

    def test_tanka_da_sigmayan_kutle_REDDEDILIR(self, sivi):
        """Fail-closed tank ayağı: tank hacmi de yetmiyorsa dosya yazılmaz."""
        from hrma.export.openrocket_integration import (
            OpenRocketExportDataError, OpenRocketExporter)
        ork = OpenRocketExporter()
        bozuk = json.loads(json.dumps(sivi))
        bozuk['propellant_mass_total'] = 1e6      # tanklar 1,2 m3
        with pytest.raises(OpenRocketExportDataError) as exc:
            _sessiz(ork.export_motor_file, bozuk)
        metin = str(exc.value)
        assert 'declared tank volume' in metin, metin[:300]
        assert 'still above the band' in metin

    def test_yer_tutucu_zarf_REDDETMEZ_ama_NOT_duser(self):
        """Üçüncü ayak: beyan edilmiş yer tutucu oranı iticiyi ölçmez.

        Yalın gövdede kasa çapı yoktur ve dosya boğaz çapını YER TUTUCU
        olarak yazdığını zaten söylüyor. O zarfla hesaplanan yoğunluk
        (21.221 kg/m3) yer tutucunun ölçüsüdür, iticinin değil; dosyayı
        reddetmek `test_unit_contract`in ve `TestEngInertMassDeclaration`ın
        kazanılmış iddialarını ölçülemez yapardı.
        """
        from hrma.export.openrocket_integration import OpenRocketExporter
        yalin = {'motor_name': 'BARE', 'thrust': 1000.0, 'burn_time': 5.0,
                 'propellant_mass_total': 2.0, 'throat_diameter': 0.02,
                 'chamber_length': 0.3, 'total_impulse': 5000.0}
        eng = _sessiz(OpenRocketExporter().export_motor_file, yalin)
        assert 'casing diameter NOT available' in eng
        assert 'That ratio measures the DECLARED PLACEHOLDER' in eng

    def test_saglikli_motorlar_hala_uretiliyor(self, hibrit, kati):
        """ÖK-22: fiziksel bantta kalan iki motor dosyayı almaya devam eder."""
        from hrma.export.openrocket_integration import OpenRocketExporter
        ork = OpenRocketExporter()
        for motor in (hibrit, kati):
            icerik = _sessiz(ork.export_motor_file, motor)
            satir = [s for s in icerik.splitlines()
                     if s.strip() and not s.startswith(';')][0]
            alan = satir.split()
            d, l, m = float(alan[1]), float(alan[2]), float(alan[4])
            hacim = math.pi / 4.0 * (d / 1000.0) ** 2 * (l / 1000.0)
            assert 0.0 < m / hacim <= 3000.0

    def test_yogunluk_ust_siniri_tek_kaynaktan(self):
        from hrma.data.propellants_db import PROPELLANT_DENSITY_RANGE_KG_M3
        from hrma.export.openrocket_integration import (
            PROPELLANT_DENSITY_MAX_KG_M3)
        assert PROPELLANT_DENSITY_MAX_KG_M3 == PROPELLANT_DENSITY_RANGE_KG_M3[1]

    def test_ima_edilen_yogunluk_hesabi(self):
        from hrma.export.openrocket_integration import OpenRocketExporter
        # Ø100 mm x 1000 mm zarf = 7,853982e-3 m^3; 7,853982 kg -> 1000 kg/m^3
        rho = OpenRocketExporter._eng_implied_bulk_density(
            100.0, 1000.0, 7.853981633974483)
        assert rho == pytest.approx(1000.0, rel=1e-12)
        assert OpenRocketExporter._eng_implied_bulk_density(
            None, 1000.0, 1.0) is None


# =====================================================================
# P9B3-12 — iki kuru kütlenin uzlaştırması ÜRÜN YOLUNDA basılıyor
# =====================================================================
class TestB312KuruKutleUzlastirmasi:

    @pytest.fixture(scope='class')
    def calculate_eng(self, istemci):
        r = _sessiz(istemci.post, '/calculate', json={
            'thrust': 2000, 'burn_time': 10, 'of_ratio': 6.0,
            'chamber_pressure': 20.0, 'fuel_type': 'htpb',
            'oxidizer_type': 'n2o'})
        assert r.status_code == 200
        return ((r.get_json().get('openrocket') or {}).get('eng_file')) or ''

    def test_urun_yolu_uzlastirmayi_basiyor(self, calculate_eng):
        assert 'two dry masses' in calculate_eng

    def test_otoriter_lule_kutlesi_adiyla_yaziliyor(self, calculate_eng):
        assert 'AUTHORITATIVE nozzle mass' in calculate_eng
        assert 'APPROXIMATION in the .eng total' in calculate_eng

    def test_iki_kuru_kutlenin_farki_sayiyla_yaziliyor(self, calculate_eng):
        satir = [s for s in calculate_eng.splitlines()
                 if 'difference =' in s]
        assert satir, calculate_eng
        assert '%' in satir[0]

    def test_cad_design_eng_uretecine_gecirilliyor(self, istemci):
        """Kök sebep bekçisi: sıra bozulursa uzlaştırma yine None döner."""
        from hrma.export.openrocket_integration import OpenRocketExporter
        r = _sessiz(istemci.post, '/calculate', json={
            'thrust': 2000, 'burn_time': 10, 'of_ratio': 6.0,
            'chamber_pressure': 20.0, 'fuel_type': 'htpb',
            'oxidizer_type': 'n2o'})
        j = r.get_json()
        motor = dict(j['motor'], cad_design=j['cad_design'])
        assert OpenRocketExporter.dry_mass_reconciliation(motor) is not None
        assert OpenRocketExporter.dry_mass_reconciliation(j['motor']) is None


# =====================================================================
# P9B3-13 — emniyet çizicisi: çok panel REDDİ + açıklama çizimi
# =====================================================================
def _cok_panelli_figur():
    return {
        'data': [
            {'type': 'scatter', 'x': [0, 1, 2], 'y': [1, 2, 3],
             'name': 'Isp', 'xaxis': 'x', 'yaxis': 'y'},
            {'type': 'scatter', 'x': [0, 1, 2], 'y': [10, 20, 30],
             'name': 'Thrust', 'xaxis': 'x2', 'yaxis': 'y2'},
        ],
        'layout': {'title': {'text': 'Altitude Performance'}},
    }


def _tek_panelli_figur(aciklamali=True):
    fig = {
        'data': [{'type': 'scatter', 'x': [0, 1, 2], 'y': [1, 2, 3],
                  'name': 'Thrust'}],
        'layout': {'title': {'text': 'Thrust'},
                   'xaxis': {'title': {'text': 't (s)'}},
                   'yaxis': {'title': {'text': 'F (N)'}}},
    }
    if aciklamali:
        fig['layout']['annotations'] = [
            {'text': 'eta_c* = 100.00% (theoretical equilibrium)',
             'x': 0.5, 'y': 0.95, 'xref': 'paper', 'yref': 'paper'},
            {'text': 'L_chamber = 959 mm', 'x': 1.0, 'y': 2.0,
             'xref': 'x', 'yref': 'y'},
        ]
        fig['layout']['shapes'] = [
            {'type': 'line', 'x0': 1, 'x1': 1, 'y0': 0, 'y1': 1,
             'yref': 'y domain', 'line': {'dash': 'dash', 'color': '#888888'}},
        ]
    return fig


class TestB313EmniyetCizicisi:

    def test_cok_panelli_figur_reddediliyor(self):
        from hrma.export.chart_render import matplotlib_png
        assert _sessiz(matplotlib_png, _cok_panelli_figur(), 900, 600) is None

    def test_ret_gerekcesi_adlandiriliyor(self):
        from hrma.export.chart_render import fallback_refusal_reason
        gerekce = fallback_refusal_reason(_cok_panelli_figur())
        assert gerekce is not None
        assert 'multi-panel' in gerekce

    def test_tek_panel_hala_ciziliyor(self):
        """ÖK-22: sadık çizilebilen figür reddedilmez."""
        from hrma.export.chart_render import (fallback_refusal_reason,
                                              matplotlib_png)
        fig = _tek_panelli_figur(aciklamali=False)
        assert fallback_refusal_reason(fig) is None
        png = _sessiz(matplotlib_png, fig, 900, 600)
        assert png and png[:4] == b'\x89PNG'

    def test_aciklamalar_artik_dusmuyor(self):
        """Açıklamalı ve açıklamasız PNG bayt bayt AYNI OLMAMALI."""
        from hrma.export.chart_render import matplotlib_png
        a = _sessiz(matplotlib_png, _tek_panelli_figur(True), 900, 600)
        b = _sessiz(matplotlib_png, _tek_panelli_figur(False), 900, 600)
        assert a is not None and b is not None
        assert a != b

    def test_twinx_cok_panel_sayilmiyor(self):
        """y2 (ikincil eksen) tek paneldir; reddedilmemeli."""
        from hrma.export.chart_render import fallback_refusal_reason
        fig = {'data': [
            {'type': 'scatter', 'x': [0, 1], 'y': [1, 2], 'yaxis': 'y'},
            {'type': 'scatter', 'x': [0, 1], 'y': [3, 4], 'yaxis': 'y2'}],
            'layout': {}}
        assert fallback_refusal_reason(fig) is None


# =====================================================================
# P9B3-14 — .ork örnek yapı sayıları BEYANLI
# =====================================================================
class TestB314OrkOrnekYapi:

    ARAC = {'name': 'BERKE-1', 'dry_mass': 12, 'diameter': 0.20,
            'length': 2.4, 'cd': 0.45, 'fin_count': 3}

    @pytest.fixture(scope='class')
    def ork_xml(self, kati):
        from hrma.export.openrocket_integration import OpenRocketExporter
        return _sessiz(OpenRocketExporter().create_ork_project_template,
                       kati, dict(self.ARAC))

    def test_ornek_yapi_beyani_basiliyor(self, ork_xml):
        assert 'EXAMPLE STRUCTURE' in ork_xml
        assert 'NOT your rocket' in ork_xml

    def test_beyan_uydurma_sayilari_adiyla_sayiyor(self, ork_xml):
        for alan in ('nose_length', 'fin_root_chord', 'mount_density',
                     'body_density', 'fin_sweep_angle'):
            assert alan in ork_xml, alan

    def test_beyan_neyi_etkiledigini_soyluyor(self, ork_xml):
        assert 'stability margin' in ork_xml
        assert 'centre of gravity' in ork_xml

    def test_kullanici_degeri_ornegi_eziyor(self, kati):
        from hrma.export.openrocket_integration import OpenRocketExporter
        xml = _sessiz(
            OpenRocketExporter().create_ork_project_template, kati,
            dict(self.ARAC, fin_root_chord=0.22, nose_material='Carbon'))
        assert '<rootchord>0.22</rootchord>' in xml
        assert '>Carbon<' in xml
        assert 'user input' in xml

    def test_ornek_tablosu_tek_kaynak(self):
        from hrma.export.openrocket_integration import (
            ORK_EXAMPLE_STRUCTURE, OpenRocketExporter)
        degerler, _ = OpenRocketExporter.resolve_ork_structure(None)
        assert set(degerler) == set(ORK_EXAMPLE_STRUCTURE)
        for ad, (varsayilan, _etiket) in ORK_EXAMPLE_STRUCTURE.items():
            assert degerler[ad] == varsayilan


# =====================================================================
# P9B4-01 — RocketCEA ft/s + Rankine → SI
# =====================================================================
def _cstar_ideal(gamma, mw, tc_K):
    g = float(gamma)
    gm = math.sqrt(g) * (2.0 / (g + 1.0)) ** ((g + 1.0) / (2.0 * (g - 1.0)))
    return math.sqrt(R_U / float(mw) * float(tc_K)) / gm


def _cea_bloklari(anlik_goruntu):
    for anahtar, kayit in sorted(anlik_goruntu['entries'].items()):
        veri = kayit.get('data') or {}
        for blok in (veri, veri.get('combustion_data')):
            if not isinstance(blok, dict) or 'c_star' not in blok:
                continue
            if 'RocketCEA' not in str(blok.get('source', '')):
                continue
            yield anahtar, blok


class TestB401CeaBirimleri:

    def test_anlik_goruntu_kayitlari_SI_ozdesligini_sagliyor(self,
                                                             anlik_goruntu):
        """Dış referans GEREKMEDEN: kaydın kendi (gamma, M, T_c, c*) dörtlüsü."""
        bloklar = list(_cea_bloklari(anlik_goruntu))
        assert len(bloklar) == 7
        for anahtar, blok in bloklar:
            ideal = _cstar_ideal(blok['gamma'], blok['molecular_weight'],
                                 blok['chamber_temperature'])
            sapma = abs(blok['c_star'] / ideal - 1.0) * 100.0
            assert sapma < 1.0, f'{anahtar}: SI özdeşliği %{sapma:.2f} sapıyor'

    def test_anlik_goruntu_birim_kunyesi_tasiyor(self, anlik_goruntu):
        for anahtar, blok in _cea_bloklari(anlik_goruntu):
            assert blok.get('c_star_units') == 'm/s', anahtar
            assert blok.get('chamber_temperature_units') == 'K', anahtar
            assert 'ft/s' in str(blok.get('unit_conversion_note')), anahtar

    def test_kayitlar_fiziksel_bantta(self, anlik_goruntu):
        """6270 K hiçbir kimyasal itki sisteminde ulaşılamaz."""
        for anahtar, blok in _cea_bloklari(anlik_goruntu):
            assert 800.0 < blok['c_star'] < 2600.0, anahtar
            assert 1500.0 < blok['chamber_temperature'] < 4500.0, anahtar

    def test_uretici_cevrimi_uyguluyor(self, monkeypatch):
        """DAVRANIŞ bekçisi: sahte RocketCEA İngiliz birimi verir, üretici SI yazar.

        Metin taraması yetmez (ölçüldü: import satırı adı barındırdığı için
        çarpan silinse bile metin bekçisi YEŞİL kalıyordu) — bu yüzden gerçek
        çağrı yolu sahte bir ``CEA_Obj`` ile koşturulur.
        """
        import types

        class _SahteCEA:
            def __init__(self, *a, **kw):
                pass

            def get_Chamber_MolWt_gamma(self, **kw):
                return (22.760747235967177, 1.1323723288170937)

            def get_Isp(self, **kw):
                return 300.0

            def get_Cstar(self, **kw):
                return 5831.338109641931   # ft/s

            def get_Tcomb(self, **kw):
                return 6270.470922754222   # Rankine

        sahte = types.ModuleType('rocketcea')
        alt = types.ModuleType('rocketcea.cea_obj')
        alt.CEA_Obj = _SahteCEA
        sahte.cea_obj = alt
        monkeypatch.setitem(sys.modules, 'rocketcea', sahte)
        monkeypatch.setitem(sys.modules, 'rocketcea.cea_obj', alt)

        from hrma.data.web_propellant_api import WebPropellantAPI
        api = WebPropellantAPI.__new__(WebPropellantAPI)
        r = _sessiz(api._use_rocketcea_library, 'rp1', 'lox', 20.0, 2.5)
        assert r['status'] == 'success'
        assert r['c_star'] == pytest.approx(1777.3918558188607, rel=1e-12)
        assert r['chamber_temperature'] == pytest.approx(
            3483.5949570856787, rel=1e-12)
        assert r['c_star_units'] == 'm/s'
        assert r['chamber_temperature_units'] == 'K'
        # Kaydın kendi iç tutarlılığı da SI'da sağlanmalı.
        ideal = _cstar_ideal(r['gamma'], r['molecular_weight'],
                             r['chamber_temperature'])
        assert abs(r['c_star'] / ideal - 1.0) < 0.01

    def test_carpanlar_tek_kaynaktan(self):
        from hrma.engines.cea_bridge import DEG_R_TO_K, FT_PER_S_TO_M_PER_S
        assert FT_PER_S_TO_M_PER_S == 0.3048
        assert DEG_R_TO_K == pytest.approx(5.0 / 9.0, rel=1e-15)


# =====================================================================
# P9B4-05 — PubChem kimlik kapısı çevrimdışı kayda da uygulanıyor
# =====================================================================
class TestB405PubchemKimlik:

    KIMLIGI_REDDEDILEN = ('htpb', 'rp1', 'paraffin', 'pmma', 'abs')

    def test_yanlis_kimlik_kayitlari_pakette_yok(self, anlik_goruntu):
        for ad in self.KIMLIGI_REDDEDILEN:
            assert f'pubchem:{ad}' not in anlik_goruntu['entries'], ad

    def test_karisimlar_kimlik_kapisinda(self):
        from hrma.data.open_source_propellant_api import (
            OpenSourcePropellantAPI)
        for ad in ('rp1', 'paraffin'):
            assert ad in OpenSourcePropellantAPI.PUBCHEM_POLYMER_DENY, ad

    def test_cevrimdisi_kayit_kapiyi_atlayamiyor(self, tmp_path):
        """Kullanıcı cache'ine yanlış kayıt konsa bile yayımlanmaz."""
        from hrma.data import offline_store
        from hrma.data.open_source_propellant_api import (
            OpenSourcePropellantAPI)
        api = OpenSourcePropellantAPI()
        anahtar = offline_store.make_key('pubchem', 'htpb')
        gercek_get_entry = offline_store.get_entry
        # ÖH D17 / P9B4-05 (Fable-D15 ŞART) — SAHTE KAYIT ARTIK GERÇEK
        # ŞEKİLDE. Bekçi eskiden ``get_entry``den HAM gövde döndürüyordu
        # ({'cid': ...}); oysa sözleşme ``{'data': ..., 'timestamp': ...,
        # 'age_seconds': ..., 'origin': ...}`` sarmalıdır ve
        # ``_depo_kaydini_yaslandir`` ham gövdeyi ``None``a çeviriyordu.
        # ÖLÇÜLDÜ (Fable-D15, bu dalgada yeniden): deny kapısı
        # ``if False`` ile SÖKÜLDÜĞÜNDE bile bu test YEŞİL kalıyordu —
        # yani kilitlediğini sandığı kapıyı hiç ölçmüyordu. Sarmal
        # düzeltilince mutasyon KIRMIZI oluyor (``mutasyon.py`` M4).
        sahte_kayit = {
            'data': {'cid': 53298156, 'formula': 'C21H17ClN4O',
                     'molecular_weight': '376.8', 'source': 'PubChem'},
            'timestamp': '2026-08-20T00:00:00',
            'age_seconds': 1000.0,
            'origin': 'user_cache',
        }
        offline_store.get_entry = lambda k: (
            dict(sahte_kayit, data=dict(sahte_kayit['data']))
            if k == anahtar else gercek_get_entry(k))
        try:
            # Ön koşul: sarmal GERÇEKTEN çözülüyor mu? Çözülmüyorsa test
            # yine yeşil olurdu ama hiçbir şeyi ölçmezdi (eski kusurun ta
            # kendisi). Kapının önündeki yaşlandırıcı sahte kaydı okumalı.
            from hrma.data.open_source_propellant_api import (
                _depo_kaydini_yaslandir)
            assert _depo_kaydini_yaslandir(
                dict(sahte_kayit, data=dict(sahte_kayit['data']))) is not None
            assert _sessiz(api.get_pubchem_properties, 'htpb') == {}
        finally:
            offline_store.get_entry = gercek_get_entry

    def test_saglikli_madde_hala_okunuyor(self):
        """ÖK-22: tekil bileşikler (lox, methane) kapıya takılmaz."""
        from hrma.data.open_source_propellant_api import (
            OpenSourcePropellantAPI)
        api = OpenSourcePropellantAPI()
        for ad in ('lox', 'methane'):
            kayit = _sessiz(api.get_pubchem_properties, ad)
            assert kayit.get('formula'), ad


# =====================================================================
# P9B4-07 — N2O yoğunluğu (ÇÜRÜTÜLDÜ; 1220 kanalı kilitlenir)
# =====================================================================
class TestB407N2OYogunlugu:

    def test_293K_doygun_sivi_degeri(self):
        from hrma.data.database_integrations import NistWebBookAPI
        r = NistWebBookAPI()._get_fallback_properties('N2O', 293.15)
        assert r['density'] == pytest.approx(785.10, rel=2e-3)
        assert 'density_source' in r

    def test_1220_bir_daha_donmuyor(self):
        from hrma.data.database_integrations import NistWebBookAPI
        api = NistWebBookAPI()
        for T in (184.7, 293.15, 298.15):
            rho = api._get_fallback_properties('N2O', T).get('density')
            assert rho is None or abs(rho - 1220.0) > 1.0, T

    def test_kardes_tablo_ile_uyumlu(self):
        """Aynı depoda aynı madde için iki değer dolaşmamalı."""
        from hrma.data.database_integrations import NistWebBookAPI
        from hrma.data.external_data_fetcher import (
            n2o_saturated_liquid_density)
        rho_tek_kaynak, _ = n2o_saturated_liquid_density(293.15)
        rho_api = NistWebBookAPI()._get_fallback_properties(
            'N2O', 293.15)['density']
        assert rho_api == pytest.approx(rho_tek_kaynak, rel=1e-12)


# =====================================================================
# P9B4-08 — kriyojenik DBTT hükmü takma adla TERSİNE dönmüyor
# =====================================================================
DBTT_CIFTLERI = [
    ('steel_4340', 'aisi_4340'),
    ('ss_17_4ph', 'stainless_17_4'),
    ('ss_17_4ph', '17-4ph'),
    ('molybdenum_tzm', 'tzm'),
]


class TestB408KriyojenikDbtt:

    @staticmethod
    def _hukum(istemci, malzeme):
        r = _sessiz(istemci.post, '/api/pressure-vessel-analysis', json={
            'meop_bar': 60, 'inner_diameter_mm': 150, 'wall_thickness_mm': 5,
            'temperature_K': 90, 'material': malzeme})
        assert r.status_code == 200, malzeme
        metin = r.get_data(as_text=True)
        return ('brittle fracture risk' in metin,
                'stay ductile when cold' in metin)

    @pytest.mark.parametrize('kanonik,takma', DBTT_CIFTLERI)
    def test_takma_ad_hukmu_cevirmiyor(self, istemci, kanonik, takma):
        assert self._hukum(istemci, kanonik) == self._hukum(istemci, takma)

    @pytest.mark.parametrize('kanonik,takma', DBTT_CIFTLERI)
    def test_iki_ad_da_gevrek_kirilma_uyariyor(self, istemci, kanonik, takma):
        for ad in (kanonik, takma):
            gevrek, sunek = self._hukum(istemci, ad)
            assert gevrek is True, ad
            assert sunek is False, ad

    def test_ymk_malzeme_hala_sunek_diyor(self, istemci):
        """ÖK-22: gerçekten sünek kalan aile için uyarı üretilmez."""
        gevrek, sunek = self._hukum(istemci, 'aluminum_6061')
        assert gevrek is False
        assert sunek is True

    def test_tanınmayan_ad_guvence_vermiyor(self, istemci):
        """Fail-closed: bilinmeyen malzeme 'soğukta sünek' güvencesi almaz."""
        r = _sessiz(istemci.post, '/api/pressure-vessel-analysis', json={
            'meop_bar': 60, 'inner_diameter_mm': 150, 'wall_thickness_mm': 5,
            'temperature_K': 90, 'material': 'boyle_bir_malzeme_yok'})
        metin = r.get_data(as_text=True)
        assert 'stay ductile when cold' not in metin

    def test_dbtt_kumesi_veri_katmaninda(self):
        from hrma.data.materials_db import DBTT_SENSITIVE, is_dbtt_sensitive
        assert 'steel_4340' in DBTT_SENSITIVE
        assert is_dbtt_sensitive('aisi_4340') is True
        assert is_dbtt_sensitive('aluminum_6061') is False
        assert is_dbtt_sensitive('boyle_bir_malzeme_yok') is None

    def test_tuketici_tek_kaynaktan_okuyor(self):
        from hrma.analysis.pressure_vessel import DBTT_SENSITIVE_MATERIALS
        from hrma.data.materials_db import DBTT_SENSITIVE
        assert DBTT_SENSITIVE_MATERIALS is DBTT_SENSITIVE
