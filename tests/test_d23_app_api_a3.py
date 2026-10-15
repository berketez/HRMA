# -*- coding: utf-8 -*-
"""ÖH D23 · app-api · aşama-3 — P15B3-09 bekçisi.

Kalem: ``tools/wiring_map.py`` sabit çıktı yapraklarının bir bölümünü
sınıflandıramıyor ve gerekçesi *"neden sabit oldugu bilinmiyor"*; aralarında
``weld_efficiency``, ``line_length_m``, ``q_star_mj_kg`` gibi TASARIM
PARAMETRESİ adları var (P15 savcı raporu §1.4 B3, kalem B3-09).

Ölçüm (bu dalganın tabanı ``ef527ae``, üç sayfanın gerçek sarsımı —
``docs/scofield/raw/OH/D23/app-api/a3/once_p15b3_09.json`` ⟶
``sonra_p15b3_09.json``):

    SINIFLANDIRILMAMIŞ (katlanmış)  96 -> 57   (ham 216 -> 171)
      hibrit 25 -> 19 · katı 25 -> 0 · sıvı 46 -> 38

Kapanan 39 yaprağın dağılımı: 31 ``sablon_koru`` (yaprak SABİT DEĞİL, güçlü
sarsımda oynuyor), 4 ``girdi_yankisi`` (alt-çözümlemenin kendi girdisi,
formda karşılığı yok), 4 gerçek beyan (``q_star_mj_kg``: kardeş ``source``
alanı sayının bandını ve kaynağını BİREBİR yazıyor).

Bu bekçi üç şeyi tutar:

1. Kazanılan sınıflandırmalar (yıldız yazımı, erime kanıtı, girdi yankısı).
2. AKLAMA SINIRLARI — kanıt yoksa hüküm yok; ad formda varsa aklama yok;
   ``c*`` geçen bir metin ``star`` grenini aklayamaz (bu son kural, aynı
   onarımın ilk sürümünde ÖLÇÜLEN bir yanlış aklamanın regresyon bekçisidir).
3. "Açıklandı" ≠ "temiz": giriş sayfası açık hesap doluyken sayfayı temiz
   ilan edemez.
"""
from __future__ import annotations

import io
import json
import pathlib
import sys

import pytest
from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parents[1]
for _p in (str(KOK), str(KOK / 'tools')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import sabit_siniflandirma as ss                              # noqa: E402
import sabit_tarayici                                         # noqa: E402
import wiring_map                                             # noqa: E402


# ---------------------------------------------------------------------------
# Gerçek ölçümden alınmış yaprak blokları (değerler taban koşumundan)
# ---------------------------------------------------------------------------

#: ``.motor.thermal_protection.chamber_liner`` bloğunun ilgili yaprakları.
QSTAR_BLOK = {
    '.tp.chamber_liner.q_star_mj_kg': 8.0,
    '.tp.chamber_liner.heat_flux_kw_m2': 758.1095765574759,
    '.tp.chamber_liner.recession_rate_mm_s': 0.0,
    '.tp.chamber_liner.design_margin': 1.5,
    '.tp.chamber_liner.emissivity': 0.9,
    '.tp.chamber_liner.blowing_blockage': 1.0,
    '.tp.chamber_liner.blowing_gas_fraction': 0.5,
    '.tp.chamber_liner.blowing_lambda': 0.4,
    '.tp.chamber_liner.burn_time_s': 10.0,
    '.tp.chamber_liner.q_net_kw_m2': 0.0,
    '.tp.chamber_liner.source': (
        "Q* 8-12 MJ/kg literature band, NASA SP-8093 class silica-phenolic "
        "ablatives; Sutton & Biblarz 9th ed. Ch. 8.5."),
}

#: ``.throat_sizing.reference_case`` — yıldız GRENİ (``star``) ve blok
#: beyanındaki ``c*`` formülü. İkisi aynı metinde buluşuyor.
_RC = '.throat_sizing.reference_case.'
STAR_GREN_BLOK = {
    # Blok GERÇEK boyutunda kurulur (17 sayısal yaprak): küçük-blok
    # muafiyeti burada ateşlenmez, sınanan şey GÜÇLÜ daldır.
    _RC + 'chamber_diameter_mm': 100.0,
    _RC + 'chamber_pressure_bar': 40.0,
    _RC + 'core_diameter_mm': 30.0,
    _RC + 'grain_length_mm': 500.0,
    _RC + 'old_criterion_peak_over_design_percent.star': 70.6,
    _RC + 'old_criterion_peak_over_design_percent.bates': 0.6,
    _RC + 'old_criterion_peak_over_design_percent.finocyl': 87.2,
    _RC + 'old_criterion_peak_over_design_percent.slotted': 7.6,
    _RC + 'old_criterion_peak_over_design_percent.wagon_wheel': 112.4,
    _RC + 'old_criterion_peak_over_initial_thrust.star': 1.78,
    _RC + 'old_criterion_peak_over_initial_thrust.bates': 1.01,
    _RC + 'old_criterion_peak_over_initial_thrust.finocyl': 1.96,
    _RC + 'old_criterion_peak_over_initial_thrust.slotted': 1.08,
    _RC + 'old_criterion_peak_over_initial_thrust.wagon_wheel': 2.24,
    _RC + 'propellant_type': 'apcp',
    _RC + 'measured_on': '2026-09-01',
    '.throat_sizing.reference_case.basis': (
        'Peak chamber pressure of the SAME reference motor when the throat '
        'is sized by the old t = 0 criterion (A_t = rho_p*Ab(0)*r(Pc)*c*'
        '/(Pc*1e5)), expressed as the percentage above the entered chamber '
        'pressure. These are reference-case numbers, not a property of your '
        'motor.'),
}

#: Alt-çözümlemenin girdi yankısı (sıvı sayfası, ölçülen değerler).
GIRDI_YANKISI_BLOK = {
    '.pt.fuel_tank.pressure_vessel.inputs.weld_efficiency': 1.0,
    '.pt.fuel_tank.pressure_vessel.inputs.temperature_K': 293.15,
    '.pt.fuel_tank.pressure_vessel.inputs.inner_diameter_mm': 859.87,
    '.fs.valve_feedline.fuel_line.line.inputs.line_length_m': 2.5,
}

#: Sıvı sayfasının gerçek taban yükünde BULUNMAYAN adlar (ölçüldü:
#: ``erime_liquid.json::taban_anahtarlar``, 83 anahtar).
SIVI_ANAHTAR_ORNEGI = ('chamber_pressure', 'thrust', 'of_ratio',
                       'fuel_type', 'mixture_ratio', 'nozzle_material')


class TestYildizYazimi:
    """``Q*`` ⟷ ``q_star``: aynı sayı, iki yazım. Eşleşme KAZANILIR."""

    def test_qstar_beyani_artik_eslesiyor(self):
        yol = '.tp.chamber_liner.q_star_mj_kg'
        sinif, gerekce = ss.siniflandir(yol, QSTAR_BLOK[yol], QSTAR_BLOK)
        assert sinif == 'beyanli', (sinif, gerekce)
        assert 'source' in gerekce

    def test_guclu_dal_kullanildi_zayif_muafiyet_degil(self):
        """Aklama JETON eşleşmesinden gelmeli, küçük-blok muafiyetinden değil."""
        dal: list = []
        yol = '.tp.chamber_liner.q_star_mj_kg'
        ss._kardes_beyan_var(yol, QSTAR_BLOK, dal)
        assert dal and dal[-1] == '5a:jeton-eslesti', dal

    def test_yildiz_greni_c_yildizi_metniyle_AKLANMAZ(self):
        """``c*`` geçen formül, ``star`` GRENİNİ aklamaz (regresyon).

        Bu onarımın ilk sürümü ``Q*`` -> ``Q_star`` çeviriyordu; jetonlayıcı
        tek harflik ``q``yu düşürünce geriye çıplak ``star`` kalıyor ve
        blok beyanındaki ``c*`` yıldız grenini "beyanlı" yapıyordu. ÖLÇÜLDÜ
        (katı sayfası, iki yaprak). Çeviri tek jetona (``cstar``) indirildi.
        """
        yol = _RC + 'old_criterion_peak_over_design_percent.star'
        sinif, gerekce = ss.siniflandir(yol, STAR_GREN_BLOK[yol],
                                        STAR_GREN_BLOK)
        assert sinif == 'SINIFLANDIRILMAMIS', (sinif, gerekce)

    def test_jeton_normalizasyonu_iki_tarafi_ayni_yere_indiriyor(self):
        assert 'qstar' in ss._jetonlar('q_star_mj')
        assert 'qstar' in ss._jetonlar('Q* 8-12 MJ/kg')
        assert 'star' not in ss._jetonlar('Q* 8-12 MJ/kg')
        assert ss._jetonlar('star') == {'star'}


class TestErimeKaniti:
    """Eriyen yaprak SABİT DEĞİLDİR — ve bu bir aklama değildir."""

    YOL = '.motor.combustion_stability.lfi.delay_constant_c_prime'
    YAPRAKLAR = {YOL: 0.0032, '.motor.combustion_stability.lfi.other': 1.0}

    def test_kanitsiz_hukum_yok(self):
        sinif, _g = ss.siniflandir(self.YOL, 0.0032, self.YAPRAKLAR)
        assert sinif == 'SINIFLANDIRILMAMIS'

    def test_eriyen_yaprak_sablon_koru_ve_anahtari_adiyla_yaziyor(self):
        kanit = {'erime': {self.YOL: {'anahtar': 'plate_thickness',
                                      'deger': 20.0, 'taban_deger': 3.0}},
                 'payload_anahtarlari': ('thrust',)}
        sinif, gerekce = ss.siniflandir(self.YOL, 0.0032, self.YAPRAKLAR,
                                        kanit)
        assert sinif == 'sablon_koru', (sinif, gerekce)
        assert 'plate_thickness' in gerekce
        assert 'SABIT DEGIL' in gerekce

    def test_sablon_koru_AKLAMA_DEGIL(self):
        assert 'sablon_koru' in ss.ACIK_HESAP_SINIFLARI
        kanit = {'erime': {self.YOL: {'anahtar': 'k', 'deger': 1,
                                      'taban_deger': 2}},
                 'payload_anahtarlari': ('thrust',)}
        ozet = ss.siniflandir_hepsi([self.YOL], self.YAPRAKLAR, kanit)
        assert [k['yol'] for k in ozet['acik_hesap']] == [self.YOL]


class TestGirdiYankisi:
    """``....inputs.<ad>`` — formda karşılığı YOKSA açıklanır, VARSA açılmaz."""

    YOL = '.pt.fuel_tank.pressure_vessel.inputs.weld_efficiency'
    HAT = '.fs.valve_feedline.fuel_line.line.inputs.line_length_m'

    def test_weld_efficiency_aciklaniyor(self):
        kanit = {'erime': {}, 'payload_anahtarlari': SIVI_ANAHTAR_ORNEGI}
        sinif, gerekce = ss.siniflandir(self.YOL, 1.0, GIRDI_YANKISI_BLOK,
                                        kanit)
        assert sinif == 'girdi_yankisi', (sinif, gerekce)
        assert 'inputs' in gerekce

    def test_line_length_aciklaniyor(self):
        kanit = {'erime': {}, 'payload_anahtarlari': SIVI_ANAHTAR_ORNEGI}
        sinif, _g = ss.siniflandir(self.HAT, 2.5, GIRDI_YANKISI_BLOK, kanit)
        assert sinif == 'girdi_yankisi'

    def test_ad_formda_VARSA_aklama_yok(self):
        """Form alanı var ve yaprak donmuşsa bu aklama değil KUSURDUR."""
        kanit = {'erime': {},
                 'payload_anahtarlari': SIVI_ANAHTAR_ORNEGI
                 + ('feed_line_length_m',)}
        sinif, _g = ss.siniflandir(self.HAT, 2.5, GIRDI_YANKISI_BLOK, kanit)
        assert sinif == 'SINIFLANDIRILMAMIS'

    def test_anahtar_olculmediyse_hukum_yok(self):
        """Fail-closed: hangi anahtarların sarsıldığı bilinmiyorsa aklama yok."""
        kanit = {'erime': {}, 'payload_anahtarlari': ()}
        sinif, _g = ss.siniflandir(self.YOL, 1.0, GIRDI_YANKISI_BLOK, kanit)
        assert sinif == 'SINIFLANDIRILMAMIS'

    def test_inputs_dugumu_disi_aklanmaz(self):
        yapraklar = {'.fs.valve_feedline.fuel_line.extra_loss_coefficient': 0.0}
        kanit = {'erime': {}, 'payload_anahtarlari': SIVI_ANAHTAR_ORNEGI}
        sinif, _g = ss.siniflandir(
            '.fs.valve_feedline.fuel_line.extra_loss_coefficient', 0.0,
            yapraklar, kanit)
        assert sinif == 'SINIFLANDIRILMAMIS'


class SahteYanit:
    def __init__(self, govde):
        self.status_code = 200
        self._govde = govde

    def get_json(self):
        return self._govde


class SahteIstemci:
    """Tek anahtara duyarlı sahte uç: ``sabit_tarayici.tara`` için."""

    ANAHTAR = 'chamber_pressure'

    def post(self, _ep, json=None, headers=None):
        yuk = json or {}
        pc = yuk.get(self.ANAHTAR)
        return SahteYanit({'a': {'canli': 1.0 + float(pc or 0.0),
                                 'donuk': 7.0}})


class SahteRapor:
    def __init__(self, sabitler):
        self.constant_outputs = list(sabitler)


class TestTarayiciKanitiYayimliyor:
    """``tara`` eriyen yaprakların ADINI ve onları oynatan sarsımı döndürür."""

    @pytest.fixture(scope='class')
    def sonuc(self):
        from tests.support import shake
        return sabit_tarayici.tara(
            'solid', SahteIstemci(), wiring_map, shake, io.StringIO(),
            report=SahteRapor(['.a.canli', '.a.donuk']))

    def test_eriyen_yapraklar_adiyla_donuyor(self, sonuc):
        assert sonuc['eriyen_yapraklar'] == ['.a.canli']
        assert sonuc['eriyen'] == 1

    def test_eriyen_kaynak_sarsimi_adiyla_tasiyor(self, sonuc):
        kaynak = sonuc['eriyen_kaynak']['.a.canli']
        assert kaynak['anahtar'] == SahteIstemci.ANAHTAR
        assert 'taban_deger' in kaynak and 'deger' in kaynak

    def test_taban_anahtarlari_yayimlaniyor(self, sonuc):
        assert SahteIstemci.ANAHTAR in sonuc['taban_anahtarlar']
        assert len(sonuc['taban_anahtarlar']) > 10

    def test_wiring_map_kaniti_ceviriyor(self, sonuc):
        erime = {'olculdu': True, 'kaynak': sonuc['eriyen_kaynak'],
                 'anahtarlar': sonuc['taban_anahtarlar']}
        kanit = wiring_map.erime_kaniti(erime)
        assert kanit['erime']['.a.canli']['anahtar'] == SahteIstemci.ANAHTAR
        assert SahteIstemci.ANAHTAR in kanit['payload_anahtarlari']

    def test_olculmemis_erime_kanit_uretmez(self):
        assert wiring_map.erime_kaniti(None) is None
        assert wiring_map.erime_kaniti({'olculdu': False}) is None


class SahteHaritaRaporu:
    """``build_index``in okuduğu alanları taşıyan asgari rapor."""

    def __init__(self, sabitler, yapraklar):
        self.live_inputs = {'thrust': ['.a.canli']}
        self.dead_inputs = {}
        self.echo_only_inputs = {}
        self.unmeasurable = {}
        self.declared_but_live = {}
        self.constant_outputs = list(sabitler)
        self.baseline_leaves = dict(yapraklar)


class TestGirisSayfasiHukmu:
    """"Açıklandı" ≠ "temiz": açık hesap rozeti yutamaz."""

    YOL = '.a.donuk'

    def _index(self, erime):
        rep = SahteHaritaRaporu([self.YOL], {self.YOL: 7.0})
        return wiring_map.build_index(
            [('solid', pathlib.Path('wiring_map_solid.html'), rep)],
            '2026-09-05 00:00', {'solid': erime})

    def test_acik_hesap_varken_temiz_denmiyor(self):
        html = self._index({'olculdu': True, 'toplam': 1, 'eriyen': 1,
                            'yuzde': 100.0, 'deneme': 1,
                            'kaynak': {self.YOL: {'anahtar': 'thrust',
                                                  'deger': 2.0,
                                                  'taban_deger': 1.0}},
                            'anahtarlar': ['thrust']})
        assert 'açık hesap' in html
        assert '>temiz<' not in html

    def test_acik_hesap_sayisi_yayimlaniyor(self):
        html = self._index({'olculdu': True, 'toplam': 1, 'eriyen': 1,
                            'yuzde': 100.0, 'deneme': 1,
                            'kaynak': {self.YOL: {'anahtar': 'thrust',
                                                  'deger': 2.0,
                                                  'taban_deger': 1.0}},
                            'anahtarlar': ['thrust']})
        assert 'toplam açık hesap' in html


class TestOlcumKaydi:
    """Kanıt dosyaları duruyor ve sayıları raporla aynı."""

    KANIT = KOK / 'docs' / 'scofield' / 'raw' / 'OH' / 'D23' / 'app-api' / 'a3'

    def test_once_sonra_sayilari(self):
        once = json.loads((kanit_gerekli(self.KANIT / 'once_p15b3_09.json'))
                          .read_text(encoding='utf-8'))
        sonra = json.loads((kanit_gerekli(self.KANIT / 'sonra_p15b3_09.json'))
                           .read_text(encoding='utf-8'))
        assert once['toplam']['siniflandirilmamis_katlanmis'] == 96
        assert sonra['toplam']['siniflandirilmamis_katlanmis'] == 57
        # Sabit yaprak SAYISI değişmedi: onarım sınıflandırmayı düzeltti,
        # ölçümü zayıflatmadı (P10B4-07 tuzağı).
        assert (once['toplam']['katlanmis_sabit']
                == sonra['toplam']['katlanmis_sabit'] == 406)
