# -*- coding: utf-8 -*-
"""ÖH Dalga-23 / ihracat aşama-1 bekçileri.

Her bekçi ters-mutasyonla kırmızıya çevrildiği ölçülerek yazıldı; kanıt
``docs/scofield/raw/OH/D23/ihracat/a1/mutasyon.json``.

Kalemler: P9B5-14, P9B5-17, P9B5-18, P9B5-19, P9B5-26, P9B5-27, P9B5-28,
P16B2-10, P17B2-08, P17B3-05, OH-D21-04.
"""
import math

import pytest

from hrma.importers import motor_file, ork_import


# ===========================================================================
# P9B5-26 — .ork: eksik ``tipchord`` SESSİZCE 0 OLMAZ (ONARIM)
# ===========================================================================
_ORK = """<?xml version="1.0" encoding="UTF-8"?>
<openrocket version="1.9"><rocket><name>t</name><subcomponents><stage>
<name>Sustainer</name><subcomponents>
<nosecone><name>Nose</name><length>0.20</length><aftradius>0.04</aftradius>
<thickness>0.002</thickness>{NOSE}</nosecone>
<bodytube><name>Body</name><length>1.00</length><radius>0.04</radius>
<thickness>0.002</thickness>{BODY}<subcomponents>
<trapezoidfinset><name>Fins</name><fincount>3</fincount>
<rootchord>0.20</rootchord>{TIP}<height>0.10</height>
{SWEEP}<thickness>0.003</thickness>
<material type="bulk" density="1850">CF</material>
<position type="bottom">0.0</position></trapezoidfinset>
</subcomponents></bodytube>
</subcomponents></stage></subcomponents></rocket></openrocket>"""

_MAT = '<material type="bulk" density="1600">GFRP</material>'
_TIP = '<tipchord>0.10</tipchord>'
_SWEEP = '<sweeplength>0.05</sweeplength>'


def _ork(nose=_MAT, body=_MAT, tip=_TIP, sweep=_SWEEP):
    return ork_import.parse_ork(
        _ORK.format(NOSE=nose, BODY=body, TIP=tip, SWEEP=sweep)
        .encode('utf-8'))


def _kutle(sonuc):
    return sum(float(c.get('mass_kg') or 0.0)
               for c in (sonuc.get('components') or []))


class TestP9B5_26EksikTipChord:
    """Yamuk kanadın zorunlu ölçüsü eksikse sayı UYDURULMAZ."""

    def test_tam_geometri_kanadi_esler(self):
        r = _ork()
        assert 'error' not in r
        assert 'Fins' in {c['name'] for c in r['components']}
        assert _kutle(r) == pytest.approx(1.115909, abs=1e-5)

    def test_tipchord_eksikse_kanat_takimi_atlanir_ve_ADIYLA_bildirilir(self):
        """ÖLÇÜLDÜ (taban ef527ae): tip 0,0 uyduruluyor, kütle -%7,46,
        ``warnings`` tip chord'u HİÇ anmıyordu."""
        r = _ork(tip='')
        assert 'error' not in r
        uyarilar = r['warnings']
        eslesen = [w for w in uyarilar if 'tipchord' in w]
        assert eslesen, (
            'Eksik tipchord adıyla bildirilmeli; uyarılar: %r' % uyarilar)
        assert 'incomplete geometry' in eslesen[0]
        # Uydurma ölçü YOK: kanat takımı kütle listesine de girmez.
        assert 'Fins' not in {c['name'] for c in r['components']}
        # ...ve atlandığı ``skipped`` defterinde de durur.
        atlanan = (r.get('mapping_report') or {}).get('skipped') or []
        assert any('tipchord' in s for s in atlanan), atlanan

    def test_sweeplength_eksikse_kanat_KORUNUR_kardes_davranis_bozulmadi(self):
        """``sweeplength`` isteğe bağlı yerleşim ölçüsüdür: alan boş kalır,
        kanat atlanmaz. P9B5-26 onarımı bu kardeş dalı DEĞİŞTİRMEMELİ."""
        r = _ork(sweep='')
        assert 'error' not in r
        assert 'Fins' in {c['name'] for c in r['components']}
        assert any('sweep length missing' in w for w in r['warnings'])

    def test_kok_kiris_eksikse_de_ADIYLA_bildirilir(self):
        r = _ork()
        govde = _ORK.format(NOSE=_MAT, BODY=_MAT, TIP=_TIP, SWEEP=_SWEEP) \
            .replace('<rootchord>0.20</rootchord>', '')
        r2 = ork_import.parse_ork(govde.encode('utf-8'))
        assert any('rootchord' in w for w in r2['warnings']), r2['warnings']


# ===========================================================================
# P9B5-17 — .ork: malzeme yoğunluğu eksikse SESSİZ DÜŞME YOK (ÇÜRÜTME KİLİDİ)
# ===========================================================================
class TestP9B5_17MalzemeYogunluguEksik:
    """Taban ``ef527ae``de zaten onarılmıştı; bekçi geri gidişi engeller."""

    def test_govde_malzemesizken_kutle_dususu_ADIYLA_bildirilir(self):
        tam = _ork()
        eksik = _ork(body='')
        assert 'error' not in eksik
        # Kütle gerçekten düşüyor (uydurma yoğunluk KONMUYOR)...
        assert _kutle(eksik) < _kutle(tam)
        # ...ama sessiz değil: bileşen adıyla ve gerekçesiyle bildiriliyor.
        assert eksik['warnings'] != []
        assert any("'Body'" in w and 'mass could not be estimated' in w
                   for w in eksik['warnings']), eksik['warnings']
        assert 'Body' not in {c['name'] for c in eksik['components']}


# ===========================================================================
# P9B5-18 — .rse: BEŞ beyanın hepsi çapraz denetlenir (ONARIM)
# ===========================================================================
def _rse(itot='1000', avg='500', peak='700', burn='2.0', isp='145.6',
         propwt='700'):
    return """<engine-database><engine-list>
<engine code="T1" mfg="X" dia="54" len="410" initWt="1200" propWt="{PW}"
 delays="0" Type="reload" Itot="{IT}" avgThrust="{AV}" peakThrust="{PK}"
 burn-time="{BT}" Isp="{IS}">
<data>
<eng-data t="0.0" f="0.0" m="700" cg="205"/>
<eng-data t="0.5" f="600" m="520" cg="205"/>
<eng-data t="1.0" f="600" m="350" cg="205"/>
<eng-data t="1.5" f="600" m="180" cg="205"/>
<eng-data t="2.0" f="0.0" m="0" cg="205"/>
</data></engine></engine-list></engine-database>""".format(
        IT=itot, AV=avg, PK=peak, BT=burn, IS=isp, PW=propwt)


def _rse_motor(**kw):
    r = motor_file.parse_rse(_rse(**kw))
    assert 'error' not in r, r
    return r['motors'][0]


class TestP9B5_18BeyanCaprazDenetimi:
    """.rse'nin beyan ettiği 5 özetin HEPSİ eğriyle karşılaştırılır."""

    ETIKETLER = ('total impulse', 'peak thrust', 'average thrust',
                 'burn time', 'specific impulse')

    @staticmethod
    def _uyarilanlar(motor):
        w = ' | '.join(motor['warnings']).lower()
        return {e for e in TestP9B5_18BeyanCaprazDenetimi.ETIKETLER if e in w}

    def test_bes_beyan_da_ayristiriliyor(self):
        dec = _rse_motor()['meta']['declared']
        assert set(dec) == {'total_impulse_ns', 'avg_thrust_n',
                            'peak_thrust_n', 'burn_time_s', 'isp_s'}

    def test_ortalama_itki_celiskisi_UYARIR(self):
        """ÖLÇÜLDÜ (taban): beyan 500,0 / eğriden 461,5 (-%7,7) — UYARI YOKTU."""
        assert 'average thrust' in self._uyarilanlar(_rse_motor())

    def test_yanma_suresi_celiskisi_UYARIR(self):
        """Eğriden 1,95 s; %5'i aşan bir beyanla karşılaştırılmalı."""
        assert 'burn time' in self._uyarilanlar(_rse_motor(burn='3.0'))

    def test_ozgul_impuls_celiskisi_UYARIR(self):
        """I_sp eğriden I_tot/(m_yakıt·g_0) ile hesaplanır (g_0 tek kaynak)."""
        from hrma.constants import G_0
        m = _rse_motor()
        beklenen = m['computed']['total_impulse_ns'] / (0.700 * G_0)
        assert m['computed']['isp_s'] == pytest.approx(beklenen, rel=1e-12)
        assert 'specific impulse' in self._uyarilanlar(m)

    def test_dort_etiket_de_ayni_koşumda_gorunur(self):
        assert self._uyarilanlar(_rse_motor()) >= {
            'total impulse', 'peak thrust', 'average thrust',
            'specific impulse'}

    def test_tutarli_dosya_HIC_celiski_uyarisi_vermez(self):
        """Yanlış pozitif kapısı: eğriyle uyumlu beyanlar sessiz kalmalı."""
        m = _rse_motor(itot='900', avg='461.5', peak='600', burn='1.95',
                       isp='131.1')
        assert self._uyarilanlar(m) == set()

    def test_yakit_kutlesi_yoksa_Isp_UYDURULMAZ_ama_sessiz_de_kalmaz(self):
        """Fail-closed: yerine geçecek kütle varsayılmaz, eksiklik söylenir."""
        m = _rse_motor(propwt='0')
        assert 'isp_s' not in m['computed']
        assert any('could not be cross-checked' in w for w in m['warnings'])


# ===========================================================================
# P9B5-19 — RASP .eng: kütle birimi / zarf yoğunluğu denetimi (ONARIM)
# ===========================================================================
_ENG = ';test\n{HDR}\n0.1 500\n0.5 500\n1.0 0\n'


def _eng(hdr):
    m = motor_file.parse_eng(_ENG.format(HDR=hdr))
    assert 'error' not in m, m
    return m


def _yogunluk_uyarisi(motor):
    return [w for w in motor['warnings'] if 'mean density' in w]


class TestP9B5_19ZarfYogunlugu:
    """Başlık kütlesi birimini beyan etmez; fizik-dışı yoğunluk susturulmaz."""

    def test_18x70_mm_govdeye_3_7_kg_UYARIR(self):
        """ÖLÇÜLDÜ (taban): ima edilen yoğunluk 235 785 kg/m³, uyarı YOKTU."""
        m = _eng('M1 18 70 0 3.7 4.2 HRMA')
        uyari = _yogunluk_uyarisi(m)
        assert uyari, m['warnings']
        assert 'GRAMS' in uyari[0]
        # Değer DEĞİŞTİRİLMEZ (dönüşüm yapılmaz).
        assert m['meta']['loaded_mass_kg'] == 4.2
        assert m['meta']['prop_mass_kg'] == 3.7

    def test_gram_yazilmis_kilogram_alani_UYARIR(self):
        m = _eng('M1 54 410 0 700 1200 HRMA')
        assert _yogunluk_uyarisi(m), m['warnings']

    def test_makul_motor_SESSIZ_kalir(self):
        """Yanlış pozitif kapısı: 54x410 mm / 1,2 kg -> 1278 kg/m³."""
        m = _eng('M1 54 410 0 0.700 1.200 HRMA')
        assert _yogunluk_uyarisi(m) == []

    def test_band_fiziksel_sinirlarin_disina_konmus(self):
        alt, ust = motor_file.MOTOR_ENVELOPE_DENSITY_PLAUSIBLE_KG_M3
        assert alt < 1.225, 'alt sınır deniz seviyesi havasının ALTINDA olmalı'
        assert ust > 19300, 'üst sınır tungstenin (19300) ÜSTÜNDE olmalı'

    def test_eksik_olcu_denetimi_SESSIZCE_TAMAMLAMAZ(self):
        """Geometri/kütle eksikse denetim yapılmaz — uydurma tamamlama yok."""
        assert motor_file._envelope_density_warning(
            {'diameter_mm': None, 'length_mm': 410.0,
             'loaded_mass_kg': 1.2}) is None
        assert motor_file._envelope_density_warning(
            {'diameter_mm': 54.0, 'length_mm': 410.0,
             'loaded_mass_kg': None}) is None


# ===========================================================================
# P9B5-14 — NASA doğrulayıcı: Pc ölçeklemesi YOK SAYILMAZ (ÇÜRÜTME KİLİDİ)
# ===========================================================================
class TestP9B5_14PcOlceklemesi:
    """Eşik D22'de (P9B5-13) söküldü; bekçi geri gelmesini engeller."""

    @staticmethod
    def _v():
        from hrma.data.nasa_realtime_validator import NASARealtimeValidator
        return NASARealtimeValidator()

    def test_oda_basinci_hukmu_degistirir(self):
        """ÖLÇÜLDÜ: Pc 204 -> %70,71 sapma, Pc 20 -> %46,55 (ikisi de 🔴)."""
        v = self._v()
        ref = v.nasa_motors['F-1']
        dt, F = ref['throat_diameter_mm'], ref['thrust_sl_N']
        r204 = v.validate_motor_calculation('F-1', dt, thrust_N=F,
                                            chamber_pressure_bar=204.0)
        r20 = v.validate_motor_calculation('F-1', dt, thrust_N=F,
                                           chamber_pressure_bar=20.0)
        assert r204['error_percent'] == pytest.approx(70.7128, abs=1e-3)
        assert r20['error_percent'] == pytest.approx(46.5478, abs=1e-3)
        for r in (r204, r20):
            assert r['color'] == '🔴'
            assert r['status'].startswith('DEVIATION > 15%')

    def test_referans_noktasi_ozdesliktir(self):
        v = self._v()
        ref = v.nasa_motors['F-1']
        r = v.validate_motor_calculation(
            'F-1', ref['throat_diameter_mm'], thrust_N=ref['thrust_sl_N'],
            chamber_pressure_bar=ref['chamber_pressure_bar'])
        assert r['nasa_reference_mm'] == pytest.approx(
            ref['throat_diameter_mm'], rel=1e-12)

    def test_kucuk_itki_bandinda_da_olcekleme_SUREKLI(self):
        """Eski %10'luk eşiğin iki yanı: SIÇRAMA olmamalı.

        ÖLÇÜLDÜ (D22 öncesi taban): itki oranı 1,0999 -> 914,400 mm,
        1,1001 -> 959,074 mm; itki %0,02 değişince boğaz %4,886 sıçrıyordu.
        d_t ∝ sqrt(F) sürekli olduğu için beklenen bağıl değişim itkinin
        bağıl değişiminin YARISIDIR (%0,0091).
        """
        v = self._v()
        ref = v.nasa_motors['F-1']
        dt, F = ref['throat_diameter_mm'], ref['thrust_sl_N']
        a = v.validate_motor_calculation('F-1', dt, thrust_N=F * 1.0999)
        b = v.validate_motor_calculation('F-1', dt, thrust_N=F * 1.1001)
        bagil = abs(b['nasa_reference_mm'] - a['nasa_reference_mm']) \
            / a['nasa_reference_mm']
        beklenen = 0.5 * (1.1001 / 1.0999 - 1.0)
        assert bagil == pytest.approx(beklenen, rel=1e-3), (
            'sqrt(F) sürekliliği bozuldu: bağıl sıçrama %.6f%%' % (bagil * 100))
        assert bagil < 1e-3, 'eski %4,886 sıçraması geri gelmiş olamaz'


# ===========================================================================
# P9B5-27 / P9B5-28 — oksitleyici kimliği ve viskozite (ÇÜRÜTME KİLİDİ)
# ===========================================================================
class TestP9B5_27OksitleyiciAdiBosluk:
    def test_bosluklu_ad_ayni_yogunlugu_verir(self):
        from hrma.data.external_data_fetcher import ExternalDataFetcher
        f = ExternalDataFetcher()
        d = [f.fetch_nist_oxidizer_properties(a, 293.15, 50.0)['density']
             for a in ('n2o', ' n2o ', '  N2O\t', 'N2O')]
        assert all(x == pytest.approx(d[0], rel=1e-15) for x in d), d

    def test_tanimsiz_ad_SESSIZCE_n2o_olmaz(self):
        from hrma.data.external_data_fetcher import normalize_oxidizer
        assert normalize_oxidizer('   ') is None
        assert normalize_oxidizer(None) is None
        assert normalize_oxidizer(' n2o ') == 'n2o'


class TestP9B5_28ViskoziteNone:
    def test_none_viskozite_cokmez_ve_kokenini_soyler(self):
        from hrma.utils.injector_design import InjectorDesign
        d = InjectorDesign(mdot_ox=1.0, chamber_pressure=30,
                           oxidizer_viscosity=None, tank_pressure=50,
                           oxidizer_temp=293.15, oxidizer_type='n2o')
        assert math.isfinite(d.mu_ox) and d.mu_ox > 0
        assert 'NIST' in d.viscosity_basis


# ===========================================================================
# P17B2-08 / P16B2-10 — malzeme adı çözümü (ÇÜRÜTME KİLİDİ + FAIL-CLOSED)
# ===========================================================================
class TestP17B2_08MalzemeAdEsleme:
    def test_steel_304_ile_ss_304_AYNI_kayda_cozulur(self):
        from hrma.data import materials_db as mdb
        assert mdb.ALIASES['steel_304'] == 'ss_304'
        assert mdb.get_material('steel_304') == mdb.get_material('ss_304')

    def test_guverte_varsayilanlarinin_hepsi_cozulur(self):
        from hrma.data.materials_db import get_material
        for ad in ('steel_4130', 'steel_304', 'steel_316', 'stainless_304'):
            assert get_material(ad)['yield_strength'] > 0


class TestP16B2_10CozulemeyenMalzeme:
    """Çözülemeyen ad BAŞKA bir malzemeye SESSİZCE düşmez (fail-closed)."""

    def test_phenolic_uydurma_bir_kayda_cozulmez(self):
        from hrma.data.materials_db import get_material
        with pytest.raises((KeyError, ValueError)):
            get_material('phenolic')

    def test_hata_mesaji_bilinen_adlari_sayar(self):
        from hrma.data.materials_db import get_material
        try:
            get_material('phenolic')
        except (KeyError, ValueError) as exc:
            assert 'ss_304' in str(exc) and 'ablative' in str(exc)
        else:
            pytest.fail('fail-closed bekleniyordu')


# ===========================================================================
# P17B3-05 — NIST yoklaması ERİŞİLEBİLİRLİKTİR, KÖKEN DEĞİLDİR (ONARIM)
# ===========================================================================
class TestP17B3_05KunyeKokeni:
    @staticmethod
    def _durum(monkeypatch, basarili):
        from hrma.data import database_integrations as di
        mgr = di.DatabaseManager()

        def sahte(_compound):
            if basarili:
                return {'status': 'success'}
            raise RuntimeError('network down')

        monkeypatch.setattr(mgr.nist, 'get_compound_properties', sahte)
        return mgr.test_connections()

    def test_erisilebilir_yoklama_KOKEN_IDDIA_ETMEZ(self, monkeypatch):
        n = self._durum(monkeypatch, True)['nist']
        assert n['status'] == 'connected'
        assert n['supplies_calculation_data'] is False
        assert 'REACHABILITY ONLY' in n['message']

    def test_erisilemez_yoklamada_da_koken_alani_KORUNUR(self, monkeypatch):
        n = self._durum(monkeypatch, False)['nist']
        # v3.0.1 K (Berke ek maddesi): erişilemeyen yoklama 'error' değil
        # ADIYLA 'not_connected' (bağlanamadı) yayımlar.
        assert n['status'] == 'not_connected'
        assert n['connection'] == 'not_connected'
        assert n['data_parsed'] is False
        assert n['supplies_calculation_data'] is False

    def test_hesabin_gercek_kaynagi_aga_CIKMIYOR(self):
        """Künyenin dayanağı: sayıları veren modül ağa çıkmadığını beyan eder."""
        from hrma.data.external_data_fetcher import MAKES_NETWORK_CALLS
        assert MAKES_NETWORK_CALLS is False


# ===========================================================================
# OH-D21-04 — regresyon çiftinin künyesi kaydın KENDİSİNDE (ONARIM)
# ===========================================================================
class TestOHD21_04RegresyonKunyesi:
    def test_abs_ile_htpb_ciftinin_AYNI_olmasi_beyan_edilir(self):
        """ÖLÇÜLDÜ (taban): iki yakıt birebir (3,68e-05, 0,555) taşıyor ve
        ürünün yayımladığı kayıtta ödünç olduğunu söyleyen alan YOKTU."""
        from hrma.data.propellant_database import PropellantDatabase
        db = PropellantDatabase().database
        assert (db['abs']['regression_a'], db['abs']['regression_n']) == \
               (db['htpb']['regression_a'], db['htpb']['regression_n'])
        assert db['abs']['regression_is_independent'] is False
        assert 'BORROWED' in db['abs']['regression_basis']
        assert 'Whitmore' in db['abs']['regression_source']

    def test_bagimsiz_olcumler_boyle_isaretli(self):
        from hrma.data.propellant_database import PropellantDatabase
        db = PropellantDatabase().database
        for ad in ('htpb', 'paraffin', 'pe', 'pmma'):
            assert db[ad]['regression_is_independent'] is True, ad
            assert db[ad]['regression_source']

    def test_her_katsayi_ciftinin_bir_kunyesi_VAR(self):
        from hrma.data.propellant_database import (
            HYBRID_REGRESSION_COEFFICIENTS, HYBRID_REGRESSION_SOURCES)
        assert set(HYBRID_REGRESSION_SOURCES) == \
               set(HYBRID_REGRESSION_COEFFICIENTS)

    def test_dogrulanmamis_yakitlar_UYDURMA_kaynak_TASIMAZ(self):
        from hrma.data.propellant_database import HYBRID_REGRESSION_SOURCES
        for ad in ('pla', 'carbon', 'aluminum', 'al2o3'):
            k = HYBRID_REGRESSION_SOURCES[ad]
            assert k['citation'] is None and k['independent'] is False
            assert 'UNVALIDATED' in k['basis']

    def test_sayilar_DEGISMEDI(self):
        """Künye onarımı SAYIYA dokunmaz (taban ef527ae değerleri)."""
        from hrma.data.propellant_database import (
            HYBRID_REGRESSION_COEFFICIENTS as C)
        assert C['htpb'] == {'a': 3.68e-5, 'n': 0.555}
        assert C['abs'] == {'a': 3.68e-5, 'n': 0.555}
        assert C['paraffin'] == {'a': 1.17e-4, 'n': 0.62}
        assert C['pe'] == {'a': 4.19e-5, 'n': 0.498}
        assert C['pmma'] == {'a': 2.11e-5, 'n': 0.615}
