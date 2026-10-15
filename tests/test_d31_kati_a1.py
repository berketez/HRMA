# -*- coding: utf-8 -*-
"""ÖH Dalga-31 · kulvar kati · aşama a1 — KN-şeker ailesinin c* tabanı.

Kapsanan kalemler
-----------------
OH-D19-22  kndx/knsb X_p = 0,44 beyan ederken c*'ları tek-fazlı Eq. 3-32
           idealinin TA KENDİSİYDİ ('c_star_basis' = 'eq3-32'), yani sıfır
           sapma kanıt değil aritmetik artıktı. D31'de iki kaydın
           termokimyası knsu/sugar ile AYNI tabana (NASA CEA, iki-fazlı,
           Pc = 1000 psia, O/F = 65/35) taşındı.
P9B4-23    Aynı kökün aile görünümü: tek X_p (0,44) taşıyan beş kardeş
           kayıt İKİ ayrı hüküm sınıfına düşüyordu (knsu/sugar -%5,90;
           kndx/knsb/kner özdeşlikte). Onarımdan sonra dördü tek sınıfta;
           kner Berke'nin 14 Eyl onay satırının DIŞINDA olduğu için
           bilerek dokunulmadan bırakıldı ve bu dosya onun hâlâ ayrık
           olduğunu AÇIKÇA kilitler (sessiz kalmaz).

Kanıt paketi: docs/scofield/raw/OH/D31/kati/a1/ (cea_kosumu.py + cea_ham.json,
once_cstar.json / sonra_cstar.json, once_motor.json / sonra_motor.json,
capa_once.json / capa_sonra.json, mutasyon.json, rapor.md).
"""

import contextlib
import io
import json
import os

import pytest

from hrma.data.propellants_db import PROPELLANTS
from hrma.engines.solid_rocket_engine import (
    _c_star_basis_of_record,
    _c_star_identity_audit,
    _condensed_mass_fraction,
    _ideal_single_phase_c_star,
)
from tests.support.kanit import kanit_gerekli

#: Aynı kimyanın (KNO3/şeker 65/35) beş katalog kaydı.
SEKER_AILESI = ('kndx', 'knsb', 'knsu', 'sugar', 'kner')

#: Berke'nin 14 Eyl onay satırının kapsadığı iki kayıt.
ONARILAN = ('kndx', 'knsb')

#: Zaten CEA tabanında olan çapa kayıtları (onarımın referansı).
CAPA = ('knsu', 'sugar')


def _hukum(anahtar):
    rec = PROPELLANTS[anahtar]
    return _c_star_identity_audit(anahtar, rec['gamma'],
                                  rec['flame_temperature'],
                                  rec['molecular_weight'], rec['c_star'])


# =====================================================================
# OH-D19-22 — kaydın c*'ı artık kendi denetlediği özdeşlikten gelmiyor
# =====================================================================
class TestOHD1922CStarTabani:

    @pytest.mark.parametrize('yakit', ONARILAN)
    def test_taban_artik_eq3_32_degil(self, yakit):
        """KUSUR: 'c_star_basis' = 'eq3-32' iken denetim döngüseldi —
        sayı, sınandığı formülle ÜRETİLMİŞTİ."""
        rec = PROPELLANTS[yakit]
        assert rec['c_star_basis'] == 'cea', (
            f"{yakit}: c* tabanı 'eq3-32'e geri düşmüş; sıfır sapma o "
            f'hâlde kanıt değil aritmetik artıktır (OH-D19-22).')
        assert _c_star_basis_of_record(yakit, rec['c_star']) == 'cea'

    @pytest.mark.parametrize('yakit', ONARILAN)
    def test_hukum_iki_faz_acigini_tasiyor(self, yakit):
        """X_p > 0 beyan eden kayıt artık idealin ÖLÇÜLEBİLİR biçimde
        altında oturuyor ve hüküm bunu 'two_phase_explained' diyor."""
        h = _hukum(yakit)
        assert h['status'] == 'two_phase_explained', (yakit, h['status'])
        assert h['identity_is_independent'] is True
        # açık gerçek ve X_p ile sınırlı
        assert h['deviation_percent'] < -1.0, (yakit, h['deviation_percent'])
        assert abs(h['deviation_percent']) / 100.0 <= h[
            'condensed_mass_fraction']

    @pytest.mark.parametrize('yakit', ONARILAN)
    def test_c_star_ozdeslige_yapisik_degil(self, yakit):
        """TERS-MUTASYON ÇAPASI: kayıt c*'ı kendi (gamma, T_c, M)
        üçlüsünün Eq. 3-32 idealine TOLERANS İÇİNDE eşit OLMAMALI."""
        rec = PROPELLANTS[yakit]
        ideal = _ideal_single_phase_c_star(rec['gamma'],
                                           rec['flame_temperature'],
                                           rec['molecular_weight'])
        sapma = 100.0 * (rec['c_star'] - ideal) / ideal
        assert abs(sapma) > 1.0, (
            f'{yakit}: c* = {rec["c_star"]} yeniden Eq. 3-32 idealine '
            f'({ideal:.4f}) yapıştı, sapma {sapma:+.4f}% — kusur geri geldi.')


# =====================================================================
# P9B4-23 — aile içi iki-faz açığı tutarlılığı
# =====================================================================
class TestP9B423AileTutarliligi:

    def test_ailenin_X_p_si_tek(self):
        """Tutarsızlık iddiasının ön şartı: aynı yoğuşmuş kesir."""
        xler = {_condensed_mass_fraction(k)[0] for k in SEKER_AILESI}
        assert xler == {0.44}, xler

    def test_dort_kardes_tek_hukum_sinifinda(self):
        """KUSUR (once_cstar.json): aynı X_p, iki hüküm sınıfı —
        knsu/sugar 'two_phase_explained', kndx/knsb 'özdeşlikte'."""
        sinif = {k: _hukum(k)['status'] for k in ONARILAN + CAPA}
        assert set(sinif.values()) == {'two_phase_explained'}, sinif

    def test_iki_faz_acigi_kardesler_arasinda_yakin(self):
        """Aynı kimya + aynı X_p -> benzer açık. Ölçülen: knsu -%5,897,
        kndx -%5,926, knsb -%5,755. Bant, aile ortalamasının etrafında
        1 puanla sınırlı; bir kaydın tek başına sıfıra düşmesi (eski
        kusur) ya da uçması bu bekçiyi kırar."""
        acik = {k: _hukum(k)['deviation_percent'] for k in ONARILAN + CAPA}
        for k, v in acik.items():
            assert -8.0 < v < -3.0, (k, v, acik)
        yayilim = max(acik.values()) - min(acik.values())
        assert yayilim < 1.0, acik

    def test_kner_hala_ayrik_ve_bunu_ilan_ediyor(self):
        """FAIL-CLOSED: kner Berke'nin onay satırında YOK, bu yüzden
        sayısına dokunulmadı. Kayıt kendi zayıflığını ilan etmeye devam
        ediyor; sessizce 'onarılmış gibi' görünmüyor."""
        h = _hukum('kner')
        assert h['status'] == 'two_phase_record_single_phase_c_star'
        assert h['identity_is_independent'] is False
        assert PROPELLANTS['kner']['c_star_basis'] == 'eq3-32'
        assert 'single-phase upper bound' in h['basis']


# =====================================================================
# Kanıt paketi — sayılar dosyada DURUYOR mu (uydurma yasağı)
# =====================================================================
class TestKanitPaketi:

    KANIT = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'docs', 'scofield', 'raw', 'OH',
        'D31', 'kati', 'a1')

    def test_cea_kosumu_kanit_dizininde(self):
        for ad in ('cea_kosumu.py', 'cea_ham.json', 'once_cstar.json',
                   'sonra_cstar.json'):
            yol = os.path.join(self.KANIT, ad)
            assert os.path.isfile(kanit_gerekli(yol)), yol

    def test_katalog_sayilari_cea_kosumuyla_ayni(self):
        """TEK KAYNAK: katalogdaki dört alan, kanıt dizinindeki CEA
        koşumunun 1000 psia satırının YUVARLANMIŞ hâli olmalı. Elle
        oynanmış bir sayı buradan geçemez."""
        with io.open(kanit_gerekli(os.path.join(self.KANIT, 'cea_ham.json')),
                     encoding='utf-8') as f:
            ham = json.load(f)
        for yakit in ONARILAN:
            r = ham['kosumlar'][yakit]['1000_psia']
            rec = PROPELLANTS[yakit]
            assert rec['c_star'] == pytest.approx(r['c_star_m_s'], abs=0.05)
            assert rec['flame_temperature'] == pytest.approx(
                r['T_c_K'], abs=0.05)
            assert rec['molecular_weight'] == pytest.approx(
                r['M_g_mol'], abs=0.005)
            assert rec['gamma'] == pytest.approx(r['gamma'], abs=5e-5)

    def test_knsu_capasi_kosumu_dogruluyor(self):
        """Yöntemin ÇAPASI: aynı kart kurgusu, deponun hâlihazırda 'cea'
        diye beyan ettiği knsu dörtlüsünü %0,2'den iyi yeniden üretiyor.
        Üretemeseydi kndx/knsb sayısı yayımlanamazdı (fail-closed)."""
        with io.open(kanit_gerekli(os.path.join(self.KANIT, 'cea_ham.json')),
                     encoding='utf-8') as f:
            ham = json.load(f)
        r = ham['kosumlar']['knsu']['1000_psia']
        rec = PROPELLANTS['knsu']
        for alan, olculen in (('c_star', r['c_star_m_s']),
                              ('flame_temperature', r['T_c_K']),
                              ('molecular_weight', r['M_g_mol']),
                              ('gamma', r['gamma'])):
            bagil = abs(olculen - rec[alan]) / rec[alan]
            assert bagil < 2e-3, (alan, rec[alan], olculen, bagil)

    def test_kaynak_kunyesi_birincil_kaynagi_adiyla_aniyor(self):
        """SAHTE VERİ YASAĞI: değişen sayının künyesi, sayıyı nereden
        aldığını ADIYLA söylemeli."""
        for yakit in ONARILAN:
            k = PROPELLANTS[yakit]['source']
            assert 'CEA' in k, yakit
            assert 'thermo.inp' in k, yakit
            assert 'NIST' in k, yakit
            assert '1000 psia' in k, yakit


# =====================================================================
# Ürün yüzeyi — /calculate_solid hâlâ ayakta ve hüküm alanını yayımlıyor
# =====================================================================
@pytest.fixture(scope='module')
def _istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


class TestUrunYuzeyi:

    YUK = {'motor_name': 'D31-KATI', 'grain_type': 'bates',
           'chamber_pressure': 40.0, 'thrust': 5000.0, 'burn_time': 3.0,
           'chamber_diameter': 100.0, 'grain_length': 500.0,
           'core_diameter': 30.0, 'expansion_ratio': 8.0}

    @pytest.mark.parametrize('yakit', ONARILAN)
    def test_uc_hukum_alanini_cea_olarak_yayimliyor(self, _istemci, yakit):
        yuk = dict(self.YUK, propellant_type=yakit)
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                r = _istemci.post('/calculate_solid', json=yuk)
        assert r.status_code == 200, r.status_code
        j = r.get_json()
        a = j['c_star_identity_audit']
        assert a['record_c_star_basis'] == 'cea', (yakit, a)
        assert a['status'] == 'two_phase_explained', (yakit, a)
        # yayımlanan c* katalogla AYNI kaynaktan (tek kaynak)
        assert j['c_star'] == pytest.approx(PROPELLANTS[yakit]['c_star'])
