# -*- coding: utf-8 -*-
"""ÖH D35 / onemli-pdf-guvenlik a1 — OH-ON-06 + OH-ON-07 davranış bekçileri.

Kanıt: ``docs/scofield/raw/OH/D35/onemli-pdf-guvenlik/a1/`` (once.json,
sonra.json, mutasyon.json, kanit_paketi.md).

Bekçilerin KONUSU
-----------------
OH-ON-06  Belgenin güvenlik bölümü, kullanıcının HİÇ vermediği bir itici
          kimliğinden patlayıcı sınıfı / TNT eşdeğeri / tahliye mesafesi
          yayımlamaz; kimlik kazanıldıysa EKRANLA AYNI sayıyı yayımlar.
OH-ON-07  Belgenin güvenlik bölümü Python sözlük ``repr``i basmaz, sayıları
          ekran basamak kuralıyla kısaltır ve dayanak cümlesini bölüm
          başına bir kez yazar.

Ters mutasyon: ``docs/scofield/raw/OH/D35/onemli-pdf-guvenlik/a1/mutasyon.py``
varsayılanları ve eski satır üreticisini geri koyar; bu dosyadaki bekçiler
o hâlde KIRMIZI yanar (ölçüldü — ``mutasyon.json``).
"""
import math
import os
import re
import subprocess
import tempfile

import pytest

from hrma.analysis.safety_analysis import SafetyAnalyzer
from hrma.export import pdf_safety
from hrma.export.pdf_generator import PDFReportGenerator

PDFTOTEXT = '/opt/homebrew/bin/pdftotext'

#: Zorunlu dörtlüsü çözülmüş, kimliği ``injector_design_detail``te duran
#: hibrit motor — ÖLÇÜLMÜŞ yük şekli (``once.json`` K0: gerçek
#: ``/calculate`` yanıtının ``motor`` sözlüğü bu yolları taşıyor).
HIBRIT_MOTOR_DATA = {
    'chamber_pressure': 30.0,
    'chamber_diameter': 0.12990938145592826,
    'propellant_mass': 13.59674741958306,
    'chamber_wall_policy': {'wall_thickness_m': 0.024847193113908518},
    'injector_design_detail': {'motor_type': 'hybrid'},
    'combustion_analysis': {'inputs': {'oxidizer_type': 'n2o'}},
}

#: Aynı motorun KİMLİKSİZ hâli — hiçbir yolda motor tipi ya da tabulated
#: bir itici sınıfı yok.
KIMLIKSIZ_MOTOR_DATA = {
    'chamber_pressure': 30.0,
    'chamber_diameter': 0.12990938145592826,
    'propellant_mass': 13.59674741958306,
    'chamber_wall_policy': {'wall_thickness_m': 0.024847193113908518},
}


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _uc_patlayici(istemci, **kimlik):
    govde = {
        'chamber_pressure': HIBRIT_MOTOR_DATA['chamber_pressure'],
        'chamber_diameter': HIBRIT_MOTOR_DATA['chamber_diameter'],
        'wall_thickness': HIBRIT_MOTOR_DATA[
            'chamber_wall_policy']['wall_thickness_m'],
        'propellant_mass': HIBRIT_MOTOR_DATA['propellant_mass'],
    }
    govde.update(kimlik)
    yanit = istemci.post('/analyze_safety', json=govde)
    assert yanit.status_code == 200, yanit.get_data(as_text=True)[:400]
    veri = yanit.get_json()
    return veri, ((veri.get('safety_analysis') or {}).get(
        'explosive_hazards') or {})


# ===========================================================================
# OH-ON-06 — KAZANILMAYAN KİMLİKTEN HÜKÜM ÇIKMAZ
# ===========================================================================
class TestOHON06FailClosed:
    """Sınıf kazanılmadıysa patlayıcı ekseni ADIYLA geri çekilir."""

    def test_kimliksiz_istek_TNT_YAYIMLAMAZ(self, istemci):
        """ÖLÇÜLEN KUSUR: bu istek sınıf ``composite``, çarpan 0,42 ve
        5,7106 kg TNT alıyordu — sayı yalnız ``propellant_type``ın
        ``'composite'`` varsayılanından geliyordu."""
        veri, patlayici = _uc_patlayici(istemci)
        assert patlayici.get('explosive_class') is None, (
            'kimlik verilmeden patlayıcı sınıfı yayımlandı: %r'
            % patlayici.get('explosive_class'))
        assert patlayici.get('tnt_equivalent_kg') is None
        assert 'blast_distances' not in patlayici, (
            'sınıf kazanılmadan tahliye mesafesi yayımlandı')
        assert 'qd_requirements' not in patlayici

    def test_geri_cekme_NEDENI_ADIYLA_yazilir(self, istemci):
        _veri, patlayici = _uc_patlayici(istemci)
        gerekce = patlayici.get('explosive_verdict_withheld_because')
        assert isinstance(gerekce, str) and gerekce.strip(), (
            'eksen sessizce düştü — geri çekme gerekçesi yok')
        assert 'motor_type' in gerekce and 'propellant_type' in gerekce, (
            'gerekçe hangi alanın eksik olduğunu ADIYLA söylemiyor: %s'
            % gerekce)

    def test_kosulsuz_sartlar_YUTULMAZ_esige_bagli_olanlar_cekilir(
            self, istemci):
        """Geri çekmenin bedeli KAZANILMIŞ içeriği yutmak değildir.

        Depolama/taşıma listelerinin koşulsuz maddeleri ne TNT eşdeğerine
        ne de itici kimliğine bakar; yayımlanırlar. Eşiğe bağlı maddeler
        (magazin/QD yerleşimi, Sınıf 1 güzergâhı) ölçülemeyen bir
        karşılaştırmaya dayandığı için çekilir — 'eşiğin altında' diye
        sessizce geçilmez.
        """
        _veri, patlayici = _uc_patlayici(istemci)
        depo = patlayici.get('storage_requirements') or []
        tasima = patlayici.get('transport_requirements') or []
        assert 'Segregate oxidizer and fuel storage' in depo
        assert 'Transport per ADR/DOT dangerous goods rules' in tasima
        assert not [m for m in depo if 'magazine' in m], depo
        assert not [m for m in tasima if 'Class 1 explosives' in m], tasima
        assert patlayici.get('requirements_scope')

    def test_kazanilmayan_eksen_PUANLANMAZ(self, istemci):
        """Ölçülemeyen tehlike 'düşük risk' diye puanlanamaz: eski kod
        eksik TNT'yi 0 kg sayıp patlayıcı eksenine 2,0 (en düşük)
        yazıyordu."""
        veri, _p = _uc_patlayici(istemci)
        risk = (veri.get('safety_analysis') or {}).get(
            'risk_assessment') or {}
        assert risk.get('individual_risks', {}).get('explosive') is None
        assert 'explosive' in (risk.get('risks_not_evaluated') or [])

    def test_uc_200_doner_kardes_eksenler_HUKUM_VERIR(self, istemci):
        """OH-D30-11'in 422 denemesi ölçümle geri alınmıştı: patlayıcı
        ekseni çözülemediğinde başka eksende KAZANILMIŞ hüküm
        esirgenmez."""
        veri, _p = _uc_patlayici(istemci)
        assert veri.get('status') == 'success'
        analiz = veri.get('safety_analysis') or {}
        assert (analiz.get('structural_safety') or {}), (
            'patlayıcı ekseni geri çekilince yapısal eksen de kayboldu'
        )

    def test_varsayilan_beyani_ARTIK_YALAN_SOYLEMEZ(self, istemci):
        """Uç, uygulamadığı bir varsayılanı 'uygulandı' diye saymaz."""
        veri, _p = _uc_patlayici(istemci)
        applied = veri.get('defaults_applied') or []
        assert 'propellant_type' not in applied
        assert 'motor_type' not in applied


class TestOHON06KimlikKazanilinca:
    """Kimlik kazanıldıysa sınıf motor tipinden + oksitleyiciden türer."""

    def test_hibrit_n2o_kendi_sinifini_alir(self, istemci):
        _veri, patlayici = _uc_patlayici(
            istemci, motor_type='hybrid', oxidizer_type='n2o')
        assert patlayici.get('explosive_class') == 'hybrid_n2o', (
            'N2O hibrit sınıfı çözülmedi: %r'
            % patlayici.get('explosive_class'))
        assert patlayici.get('tnt_equivalent_kg') is not None

    def test_kati_apcp_KOMPOZIT_alir_hibrit_almaz(self, istemci):
        """OH-D30-11 ölçümü: ``propellant_type='apcp'`` motor tipi
        verilmeden HİBRİT N2O sınıfını alıyordu."""
        _veri, patlayici = _uc_patlayici(
            istemci, motor_type='solid', propellant_type='apcp')
        assert patlayici.get('explosive_class') == 'composite'

    def test_apcp_motor_tipi_YOKKEN_hibrit_sinifi_ALMAZ(self, istemci):
        _veri, patlayici = _uc_patlayici(istemci, propellant_type='apcp')
        assert patlayici.get('explosive_class') != 'hybrid_n2o', (
            'katı bir yakıt adı, verilmemiş bir motor tipinin hibrit '
            'sınıfını aldı (OH-D30-11 kusuru geri geldi)')


class TestOHON06EkranBelgeEsitligi:
    """OH-D33-17 emsali GENİŞLETİLDİ: aynı motor, aynı sayı."""

    def test_belge_ile_ekran_AYNI_sinifi_ve_TNTyi_yayimlar(self, istemci):
        safety, kunye = pdf_safety.build_pdf_safety(HIBRIT_MOTOR_DATA, {})
        assert safety is not None, (
            'belge güvenlik yükü üretilemedi: %r' % kunye)
        belge = safety.get('explosive_hazards') or {}
        _veri, ekran = _uc_patlayici(
            istemci, motor_type='hybrid', oxidizer_type='n2o')
        assert belge.get('explosive_class') == ekran.get('explosive_class')
        assert belge.get('tnt_equivalent_kg') == pytest.approx(
            ekran.get('tnt_equivalent_kg'), rel=1e-12), (
            'AYNI motor için belge ile ekran farklı TNT eşdeğeri yayımlıyor'
        )

    def test_belge_motor_tipini_GERCEK_degerle_cozer(self):
        """ÖLÇÜLEN KUSUR: künye ``motor type = None`` diyordu; ürün tipi
        ``injector_design_detail.motor_type``ta yazılı olduğu hâlde."""
        _s, kunye = pdf_safety.build_pdf_safety(HIBRIT_MOTOR_DATA, {})
        cozulen = kunye.get('inputs_resolved') or {}
        assert 'motor_type' in cozulen, (
            'belge motor tipini çözemedi: %r' % cozulen)
        assert (kunye.get('defaults_applied') or {}).get(
            'motor_type') is None

    def test_kimliksiz_yukte_belge_de_GERI_CEKER(self):
        safety, _k = pdf_safety.build_pdf_safety(KIMLIKSIZ_MOTOR_DATA, {})
        assert safety is not None, 'kimliksiz yükte hiç hüküm üretilmedi'
        belge = safety.get('explosive_hazards') or {}
        assert belge.get('tnt_equivalent_kg') is None
        assert belge.get('explosive_verdict_withheld_because')


class TestOHON06YanginEkseni:
    """Yangın sınıfı da yanlış motor sınıfına göre basılmaz."""

    def test_kimliksiz_yukte_yangin_sinifi_UYDURULMAZ(self):
        r = SafetyAnalyzer().analyze_comprehensive_safety(
            {'chamber_pressure': 30.0, 'chamber_diameter': 0.13,
             'wall_thickness': 0.0248, 'chamber_temperature': 3000.0},
            13.6)
        yangin = (r.get('fire_hazards') or {}).get('fire_classification')
        assert 'solid propellant fire' not in str(yangin), (
            'kimliksiz motor KATI itici yangını ilan edildi: %r' % yangin)

    def test_hibrit_kimlikli_yukte_yangin_sinifi_HIBRIT(self):
        r = SafetyAnalyzer().analyze_comprehensive_safety(
            {'chamber_pressure': 30.0, 'chamber_diameter': 0.13,
             'wall_thickness': 0.0248, 'chamber_temperature': 3000.0},
            13.6, motor_type='hybrid', oxidizer_type='n2o')
        yangin = (r.get('fire_hazards') or {}).get('fire_classification')
        assert 'Class A fuel grain' in str(yangin), yangin


# ===========================================================================
# OH-ON-07 — BELGE HAM SÖZLÜK DÖKMEZ
# ===========================================================================
#: Python sözlük ``repr``inin imzası.
REPR_IMZASI = "{'"
#: 10+ ondalık basamak taşıyan sayı (16 haneli float repr).
UZUN_ONDALIK = re.compile(r'\d+\.\d{10,}')
#: Ölçülen bölüm sınırı (``once.json``/``sonra.json`` ile AYNI kural).
BOLUM_SONU = 'Motor Configuration'


def _guvenlik_kesiti(metin):
    bas = metin.find('Safety Assessment')
    if bas < 0:
        bas = metin.find('Hazard details')
    if bas < 0:
        return metin
    son = metin.find(BOLUM_SONU, bas)
    return metin[bas:son] if son > bas else metin[bas:]


@pytest.fixture(scope='module')
def guvenlik_metni(istemci):
    if not os.path.exists(PDFTOTEXT):
        pytest.skip('pdftotext kurulu değil: %s' % PDFTOTEXT)
    safety, _k = pdf_safety.build_pdf_safety(HIBRIT_MOTOR_DATA, {})
    assert safety is not None
    yanit = istemci.post('/api/export-pdf/summary', json={
        'motor_data': HIBRIT_MOTOR_DATA,
        'analysis_results': {'safety': safety}})
    assert yanit.status_code == 200, yanit.get_data(as_text=True)[:300]
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as fh:
        fh.write(yanit.get_data())
        yol = fh.name
    try:
        cikti = subprocess.run([PDFTOTEXT, '-layout', yol, '-'],
                               capture_output=True, text=True, timeout=120)
    finally:
        os.unlink(yol)
    return _guvenlik_kesiti(cikti.stdout)


class TestOHON07BelgeMetni:
    def test_ham_sozluk_repri_BASILMAZ(self, guvenlik_metni):
        """ÖLÇÜLEN KUSUR (``once.json`` K2): kesitte ``{'`` imzası 30 kez
        geçiyordu; belge ``blast distances — lethal: {'distance_m': ...}``
        yazıyordu."""
        assert guvenlik_metni, 'güvenlik bölümü belgede hiç yok'
        sayi = guvenlik_metni.count(REPR_IMZASI)
        assert sayi == 0, (
            'güvenlik bölümünde %d adet Python sözlük dökümü var' % sayi)

    def test_onalti_basamakli_ondalik_BASILMAZ(self, guvenlik_metni):
        """ÖLÇÜLEN KUSUR: 17 adet 10+ basamaklı sayı (ör. ölümcül mesafe
        ``4.914408842346228`` m)."""
        uzunlar = UZUN_ONDALIK.findall(guvenlik_metni)
        assert not uzunlar, (
            'ekran basamak kuralı uygulanmamış sayılar: %r' % uzunlar[:6])

    def test_dayanak_cumlesi_BOLUM_BASINA_BIR_KEZ(self, guvenlik_metni):
        """ÖLÇÜLEN KUSUR: aynı Kinney-Graham dayanağı 4 kez tekrar
        ediyordu (her aşırı-basınç seviyesinin altında bir kez)."""
        tekrar = guvenlik_metni.count('Free-air spherical TNT')
        assert tekrar <= 1, (
            'dayanak cümlesi %d kez tekrar ediyor' % tekrar)

    def test_patlama_mesafeleri_HALA_BASILIYOR(self, guvenlik_metni):
        """Fail-closed'ın bedeli alan YUTMAK olamaz: biçim düzeldi diye
        ölçü kaybolmamalı."""
        assert 'blast distances' in guvenlik_metni
        assert 'lethal' in guvenlik_metni
        assert 'distance m' in guvenlik_metni


class TestOHON07BasamakKurali:
    def test_rapor_basamagi_EKRANLA_AYNI(self):
        """TEK KAYNAK (doktrin 4): rapor kendi basamak sayısını icat
        etmez, güvertenin ÖLÇÜLMÜŞ ``DOCK_SIGFIG``ını kullanır."""
        yol = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), 'hrma', 'static', 'js',
            'analysis_dock.js')
        kaynak = open(yol, encoding='utf-8').read()
        m = re.search(r'const\s+DOCK_SIGFIG\s*=\s*(\d+)\s*;', kaynak)
        assert m, 'analysis_dock.js DOCK_SIGFIG bulunamadı'
        assert PDFReportGenerator.REPORT_SIGFIG == int(m.group(1)), (
            'rapor basamağı ekran basamağından ayrıştı: %s vs %s'
            % (PDFReportGenerator.REPORT_SIGFIG, m.group(1)))

    def test_ic_ice_sozluk_ALT_SATIRA_acilir(self):
        satirlar = PDFReportGenerator._hazard_lines({
            'blast_distances': {
                'lethal': {'distance_m': 4.914408842346228,
                           'overpressure_kpa': 100.0,
                           'basis': 'Free-air spherical TNT (test)'}}})
        metin = '\n'.join(satirlar)
        assert REPR_IMZASI not in metin, metin
        assert not UZUN_ONDALIK.findall(metin), metin
        assert 'distance m: 4.91441' in metin, metin
        assert metin.count('Free-air spherical TNT (test)') == 1, metin

    def test_NaN_kisaltilmaz_kusur_GORUNUR_kalir(self):
        satirlar = PDFReportGenerator._hazard_lines(
            {'x': float('nan'), 'y': float('inf')})
        metin = '\n'.join(satirlar)
        assert 'nan' in metin.lower() and 'inf' in metin.lower(), metin

    def test_bool_sayi_SAYILMAZ(self):
        satirlar = PDFReportGenerator._hazard_lines({'flag': True})
        assert 'True' in '\n'.join(satirlar)


# ===========================================================================
# Ana model, birleşme denetimi (22 Eyl) — SIVI kimliği iç içe yolda
# ===========================================================================
#: ÖLÇÜLDÜ (örnek sıvı koşumu, /calculate_liquid yanıtı): motor tipi
#: ``injection_system.injector_design_detail.motor_type = 'liquid'`` yolunda;
#: ``propellant_name`` bir görüntü etiketi ("RP-1/LOX (Kerosene/Liquid
#: Oxygen)") ve tabulated sınıf DEĞİL. Düz yol tablosu bunu görmüyor, belge
#: sıvı motorun patlayıcı eksenini "kimlik çözülemedi" diye geri çekiyordu.
SIVI_MOTOR_DATA = {
    'chamber_pressure': 70.0,
    'chamber_diameter': 0.10944,
    'propellant_mass': 40.0,
    'chamber_wall_policy': {'wall_thickness_m': 0.005},
    'propellant_name': 'RP-1/LOX (Kerosene/Liquid Oxygen)',
    'fuel_type': 'rp1', 'oxidizer_type': 'lox',
    'injection_system': {'injector_design_detail': {'motor_type': 'liquid'}},
}


class TestSiviKimligiIcIceYoldan:
    def test_yol_tablosu_ic_ice_sivi_yolunu_tasir(self):
        yollar = [y for y, _v in pdf_safety.SAFETY_CONTEXT_SOURCES['motor_type']]
        assert 'md:injection_system.injector_design_detail.motor_type' in yollar
        assert 'ar:injection_system.injector_design_detail.motor_type' in yollar

    def test_sivi_belgesi_liquid_biprop_sinifini_KAZANIR(self):
        safety, kunye = pdf_safety.build_pdf_safety(SIVI_MOTOR_DATA, {})
        assert safety is not None
        belge = safety.get('explosive_hazards') or {}
        assert belge.get('explosive_class') == 'liquid_biprop', belge
        assert belge.get('tnt_equivalent_kg'), belge
        assert not belge.get('explosive_verdict_withheld_because'), belge
        assert 'motor_type' in (kunye.get('inputs_resolved') or {})

    def test_kimliksiz_sivi_gorunumu_etiketle_sinif_KAZANMAZ(self):
        """Yalnız görüntü etiketi (propellant_name) ile sınıf uydurulmaz."""
        md = dict(SIVI_MOTOR_DATA); md.pop('injection_system'); md.pop('fuel_type'); md.pop('oxidizer_type')
        safety, _k = pdf_safety.build_pdf_safety(md, {})
        belge = (safety or {}).get('explosive_hazards') or {}
        assert belge.get('tnt_equivalent_kg') is None
        assert belge.get('explosive_verdict_withheld_because')
