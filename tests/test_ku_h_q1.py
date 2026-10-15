"""KU h-q1 — kitap uyum hızlı düzeltmeleri: termokimya, API alanları, formül sayfası.

Kalemler (KARS-S kitap uyum girdisi, 6 Eki 2026):

* **H-2 / B17** — ``/api/oxidizer-properties`` N₂O ΔfH işareti (−82,05 →
  +82,05, gaz 298,15 K) tek kaynaktan; LOX 0,0 kaydının durum etiketi.
* **H-3 / B18** — katalogdaki N₂O buhar basıncı elle yazılı 5,15 MPa
  değil, hâl denkleminden türetilir; ``vapor_pressure`` tek birim (Pa) ve
  beyanlı; birimi kanıtlanamayan API sayısı yayımlanmaz.
* **H-5 / K2b-10** — ``web_propellant_api``deki RocketCEA'da olmayan
  'H2O2_98' kart adı deponun tek eşlemesine bağlandı; 'h2o2'nin %100 karta
  bağlı olduğu yanıtta yazılır.
* **H-13 / KU-33** — formül sayfası (çekim kaybı sin θ, v_orbit aralığı,
  kademe kütle tanımı, Tsiolkovsky açıklaması) + ölü ``species_data``
  yorumu.
* **H-14 / K** — FAC docstring'i; Back künyesi (JPL TR 32-415 Rev. 1).

Ağ KAPALI: her test ``socket`` bağlantısını reddeder (fail-closed ölçüm).
Kaynak okuyan bekçiler dosyayı AST/düz metin olarak okur.
"""
import ast
import contextlib
import io
import math
import re
import socket
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _ag_kapali(monkeypatch):
    def _ret(*a, **k):
        raise OSError('test_ku_h_q1: ağ kapalı')
    monkeypatch.setattr(socket.socket, 'connect', _ret)
    monkeypatch.setattr(socket, 'create_connection', _ret)


@pytest.fixture(scope='module')
def uygulama():
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            from hrma import app as app_modulu
    app_modulu.app.config['TESTING'] = True
    return app_modulu


def _post(app_modulu, yol, yuk):
    istemci = app_modulu.app.test_client()
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            r = istemci.post(yol, json=yuk)
    return r.status_code, (r.get_json() or {})


# ---------------------------------------------------------------------------
# H-2 / B17
# ---------------------------------------------------------------------------
class TestH2OksitleyiciEntalpisi:
    def test_n2o_dfh_pozitif_ve_tek_kaynak(self, uygulama):
        from hrma.data import propellant_database as pdb
        from hrma.engines.combustion_analysis import CombustionAnalyzer
        kod, govde = _post(uygulama, '/api/oxidizer-properties',
                           {'oxidizer_type': 'n2o', 'temperature': 293.15})
        assert kod == 200
        p = govde['properties']
        # İşaret: N₂O → N₂ + ½O₂ ekzotermik; JANAF/CEA/çözücü hepsi pozitif.
        assert p['enthalpy_formation'] > 0.0
        assert p['enthalpy_formation'] == (
            pdb.N2O_ENTHALPY_FORMATION_GAS_298K_KJ_MOL)
        assert p['enthalpy_formation_state'] == (
            pdb.N2O_ENTHALPY_FORMATION_STATE)
        assert 'gas' in p['enthalpy_formation_state']
        assert '298.15' in p['enthalpy_formation_state']
        # Katalog kaydı da aynı adı okur.
        assert pdb.propellant_db.get_propellant_properties(
            'n2o')['heat_of_formation'] == p['enthalpy_formation']
        # Yanma çözücüsünün (henüz bağlanmamış) kopyası ayrışırsa kırmızı.
        with contextlib.redirect_stdout(io.StringIO()):
            ca = CombustionAnalyzer()
        assert ca.propellant_specs['n2o']['enthalpy_formation'] == (
            p['enthalpy_formation'])

    def test_lox_0_gaz_referansi_diye_etiketli(self, uygulama):
        kod, govde = _post(uygulama, '/api/oxidizer-properties',
                           {'oxidizer_type': 'lox', 'temperature': 90.0})
        assert kod == 200
        p = govde['properties']
        # Sayı DEĞİŞMEDİ (hesaba girmeyen alan); etiket durumu söyler.
        assert p['enthalpy_formation'] == 0.0
        etiket = p['enthalpy_formation_state']
        assert 'gas' in etiket and 'NOT the liquid' in etiket


# ---------------------------------------------------------------------------
# H-3 / B18
# ---------------------------------------------------------------------------
class TestH3BuharBasinci:
    def test_katalog_n2o_buhar_basinci_hal_denkleminden(self, uygulama):
        from hrma.analysis.tank_blowdown import N2OSaturation
        from hrma.data.open_source_propellant_api import (
            OpenSourcePropellantAPI)
        from hrma.data.propellant_database import propellant_db
        kayit = propellant_db.get_propellant_properties('n2o')
        T_ref = OpenSourcePropellantAPI.DEFAULT_STORAGE_STATE[
            'NitrousOxide']['T']
        assert kayit['vapor_pressure_reference_temperature_K'] == T_ref
        assert kayit['vapor_pressure'] == pytest.approx(
            N2OSaturation().psat(T_ref), rel=1e-12)
        # Kardeş uç aynı durumda (293,15 K) aynı EOS değerini yayımlıyor.
        assert kayit['vapor_pressure'] == pytest.approx(
            uygulama._OXIDIZER_STATIC_PROPS['n2o']['vapor_pressure_20c'],
            rel=1e-4)
        assert 'N2OSaturation' in kayit['vapor_pressure_source']
        # Elle yazılmış sayı kayıtta durmuyor (kaynak metni).
        ham = propellant_db.database['n2o']
        assert 'vapor_pressure' not in ham

    def test_katalog_buhar_basinclari_pa_buyuklugunde(self):
        """Katalog kayıtları Pa yazar: kPa/MPa ile yazılmış bir sayı
        (eski rp1 0,7 kPa, eski n2o 5,15 MPa) 10 Pa'nın altında kalırdı."""
        from hrma.data.propellant_database import propellant_db
        bulunan = 0
        for ad in sorted(propellant_db.database):
            kayit = propellant_db.get_propellant_properties(ad) or {}
            if kayit.get('vapor_pressure') is None:
                continue
            bulunan += 1
            assert kayit['vapor_pressure'] >= 10.0, (ad, kayit['vapor_pressure'])
        assert bulunan >= 2   # n2o (türetilen) + rp1

    @pytest.mark.parametrize('ad,tur', [('n2o', 'oxidizer'),
                                        ('n2o', 'hybrid_oxidizer'),
                                        ('n2o', None),
                                        ('rp1', 'liquid_fuel')])
    def test_uc_vapor_pressure_tek_birim_pa(self, uygulama, ad, tur):
        from hrma.data.propellant_database import VAPOR_PRESSURE_UNIT
        yuk = {'propellant_name': ad}
        if tur is not None:
            yuk['propellant_type'] = tur
        kod, govde = _post(uygulama, '/api/get-propellant-properties', yuk)
        assert kod == 200
        p = govde.get('properties', govde)
        assert p.get('vapor_pressure') is not None
        assert p.get('vapor_pressure_unit') == VAPOR_PRESSURE_UNIT == 'Pa'

    def test_n2o_iki_dal_ayni_buyuklukte(self, uygulama):
        """Birim karışması (MPa ⟷ Pa, 10⁶ kat) bir daha giremez."""
        degerler = []
        for tur in ('oxidizer', 'hybrid_oxidizer'):
            _, govde = _post(uygulama, '/api/get-propellant-properties',
                             {'propellant_name': 'n2o',
                              'propellant_type': tur})
            degerler.append(govde.get('properties', govde)['vapor_pressure'])
        oran = degerler[0] / degerler[1]
        # İki dal farklı sıcaklıkta (298,15 ⟷ 293,15 K) — %12 fark beklenir,
        # 10⁶ kat değil.
        assert 0.5 < oran < 2.0

    def test_birimi_kanitlanamayan_api_sayisi_yayimlanmaz(self, uygulama,
                                                          monkeypatch):
        # CoolProp kanıtı yoksa (ör. ağ yolundaki PubChem sayısı) birim
        # varsayılmaz ve sayı yayımlanmaz.
        monkeypatch.setattr(uygulama, '_coolprop_state',
                            lambda *a, **k: {})
        kod, govde = _post(uygulama, '/api/get-propellant-properties',
                           {'propellant_name': 'n2o',
                            'propellant_type': 'oxidizer'})
        assert kod == 200
        p = govde.get('properties', govde)
        assert 'vapor_pressure' not in p
        assert 'vapor_pressure_unit' not in p
        assert p.get('vapor_pressure_withheld_reason')
        # Yerel kaydın künye alanları, ezilmiş (ve düşmüş) sayıya
        # künye basmaz.
        assert 'vapor_pressure_reference_temperature_K' not in p


# ---------------------------------------------------------------------------
# H-5 / K2b-10
# ---------------------------------------------------------------------------
class TestH5PeroksitKarti:
    def test_web_api_h2o2_var_olan_karta_bagli(self):
        from hrma.data.web_propellant_api import web_api
        from hrma.engines import cea_bridge
        with contextlib.redirect_stdout(io.StringIO()):
            out = web_api._use_rocketcea_library('rp1', 'h2o2', 100.0, 7.0)
        assert out.get('status') == 'success', out
        assert out['oxidizer_card'] == cea_bridge.OX_CARD_MAP['h2o2']
        assert '100 wt%' in out['oxidizer_card_note']
        # Aynı kart, aynı kütüphane: kardeş yol ile aynı T_c.
        r = cea_bridge.get_combustion_properties('rp1', 'h2o2', 100.0, 7.0)
        assert out['chamber_temperature'] == pytest.approx(r['tc_k'],
                                                           rel=1e-3)

    def test_cea_bridge_yanitinda_kart_beyani(self):
        from hrma.engines import cea_bridge
        r = cea_bridge.get_combustion_properties('rp1', 'h2o2', 68.95, 7.0)
        v = r['validity']
        assert v['oxidizer_card'] == 'H2O2'
        assert '100 wt%' in v['oxidizer_card_note']
        assert 'NOT rocket-grade' in v['oxidizer_card_note']
        # Beyanı olmayan kartta alan yok (varsayılan çiftler değişmez).
        r2 = cea_bridge.get_combustion_properties('rp1', 'lox', 68.95, 2.5)
        assert 'oxidizer_card_note' not in r2['validity']


# ---------------------------------------------------------------------------
# H-13 / KU-33 — formül sayfası, i18n, ölü sözlük
# ---------------------------------------------------------------------------
def _sayfa():
    return (KOK / 'hrma/templates/formulas.html').read_text(encoding='utf-8')


def _sozluk():
    return (KOK / 'hrma/static/js/i18n_formulas.js').read_text(
        encoding='utf-8')


def _bolum(metin, bas, son):
    i = metin.index(bas)
    return metin[i:metin.index(son, i)]


_UST = str.maketrans('⁰¹²³⁴⁵⁶⁷⁸⁹', '0123456789')


class TestH13FormulSayfasi:
    def test_cekim_kaybi_ve_twr_sin_theta(self):
        s93 = _bolum(_sayfa(), 'data-i18n="fx.s9_3.h"', 'data-i18n="fx.s9_4.h"')
        s95 = _bolum(_sayfa(), 'data-i18n="fx.s9_5.h"', '</table>')
        for blok in (s93, s95):
            assert '\\cos(\\theta)' not in blok
        assert '\\sin(\\theta)' in s93
        assert '\\sin(\\theta)' in s95
        assert 'fx.ann.theta_from_horizontal' in s93

    def test_v_orbit_araligi_kendi_r_ve_mu_degerinden(self):
        s92 = _bolum(_sayfa(), 'data-i18n="fx.s9_2.h"', 'data-i18n="fx.s9_3.h"')
        mu = float(re.search(r'\\mu = GM = ([\d.]+) \\times 10\^\{(\d+)\}',
                             s92).expand(r'\1e\2'))
        r_satir = re.search(r'fx\.var\.orbital_radius">[^<]*</td><td>m</td>'
                            r'<td>([^<]+)</td>', s92).group(1)
        r_min, r_max = (float(x.replace('×10', 'e').translate(_UST))
                        for x in r_satir.split('-'))
        v_satir = re.search(r'fx\.var\.orbital_velocity">[^<]*</td>'
                            r'<td>m/s</td><td>([^<]+)</td>', s92).group(1)
        v_alt, v_ust = (float(x) for x in v_satir.split('-'))
        # √(μ/r): sayfanın kendi r aralığından, 10 m/s yuvarlamayla.
        assert v_ust == pytest.approx(math.sqrt(mu / r_min), abs=10.0)
        assert v_alt == pytest.approx(math.sqrt(mu / r_max), abs=10.0)
        # Kurtulma hızı ayrı satırdadır; dairesel hız aralığına girmez.
        assert v_ust < 11000.0

    def test_kademe_kutle_orani_tanimli(self):
        s94 = _bolum(_sayfa(), 'data-i18n="fx.s9_4.h"', 'data-i18n="fx.s9_5.h"')
        for parca in ('m_{0,i}', 'm_{b,i}', 'm_{0,i+1} = m_{b,i} - m_{s,i}',
                      '\\prod_{i=1}^{n} MR_i'):
            assert parca in s94, parca
        assert 'm_{i-1}' not in s94

    def test_tsiolkovsky_aciklamasi_ters_degil(self):
        sozluk = _sozluk()
        assert ('small improvements in specific impulse or mass ratio '
                'provide significant') not in sozluk
        assert 'küçük iyileştirmelerin önemli performans' not in sozluk
        assert 'only logarithmically with mass ratio' in sozluk
        assert 'kütle oranıyla ise yalnız logaritmik' in sozluk
        assert ('only logarithmically with mass ratio'
                in _bolum(_sayfa(), 'data-i18n="fx.s9_1.desc"', '</span>'))

    def test_yeni_anahtarlar_en_tr_esit(self):
        sozluk = _sozluk()
        en = _bolum(sozluk, 'en: {', 'tr: {')
        tr = sozluk[sozluk.index('tr: {'):]
        for anahtar in ('fx.ann.theta_from_horizontal', 'fx.ann.stage_jettison',
                        'fx.var.stage_ignition_mass', 'fx.var.stage_burnout_mass',
                        'fx.var.stage_jettisoned_mass'):
            assert en.count(f"'{anahtar}'") == 1, anahtar
            assert tr.count(f"'{anahtar}'") == 1, anahtar
            assert f'data-i18n="{anahtar}"' in _sayfa(), anahtar

    def test_olu_species_data_okunmuyor_ve_jANAF_guncel_demiyor(self):
        yol = KOK / 'hrma/engines/combustion_analysis.py'
        kaynak = yol.read_text(encoding='utf-8')
        agac = ast.parse(kaynak)
        okuma = [n.lineno for n in ast.walk(agac)
                 if isinstance(n, ast.Attribute) and n.attr == 'species_data'
                 and isinstance(n.ctx, ast.Load)]
        assert okuma == [], okuma
        assert 'NIST-JANAF güncel değerleri' not in kaynak
        assert 'NIST 2023 değerleri' not in kaynak


# ---------------------------------------------------------------------------
# H-14 / K — beyan ve künye
# ---------------------------------------------------------------------------
class TestKunyeVeBeyan:
    def test_fac_docstring_kaybi_durgunluk_basincina_koyar(self):
        from hrma.engines import cea_bridge
        doc = cea_bridge._cea_obj.__wrapped__.__doc__
        assert 'DÜŞÜKTÜR ve gerçeğe daha yakındır' not in doc
        assert "Kayıp c*'ta DEĞİL" in doc

    def test_back_kunyesi_jpl_tr_32_415(self, uygulama):
        metin = uygulama.CFD_VISCOUS_VALIDATION_BASIS
        assert 'NASA TR 32-654' not in metin
        assert 'JPL Technical Report 32-415 Rev. 1' in metin
        # Uç sözleşmesi (tests/test_cfd_endpoint.py) bu dizgiyi arıyor.
        assert 'Back, Massier & Gier 1964' in metin
