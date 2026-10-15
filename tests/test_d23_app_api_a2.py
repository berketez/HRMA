"""ÖH Dalga-23 · app-api · aşama-2 bekçileri — defter **P13B4-12**.

Kalem (D22 DEVİR, orta): *"Bekçi yalnız import satırının METNİNİ arıyor:
dosya ``safe_name``'i import edip hiç çağırmasa yeşil; elle liste 2 dosya,
22 indirme noktasının hepsi ``app.py``'de ve kapsam dışı."*

Kalemin kalan gövdesi ÖK-20 / P16 ADIM 3'tü: ``input_guard``'ın DEĞER
kapısını uç katmanına bağlamak. Aşağıdaki bekçiler o kapsamı DAVRANIŞLA
kilitler — envanter sayımı (``test_v262_release_gate.py``
:class:`TestInputGuardCagriEnvanteri`) kapının KAÇ yerde takılı olduğunu
söyler, buradaki testler kapının GERÇEKTEN kapandığını söyler.

Ölçüm (taban ``ef527ae`` -> bu ağaç; 22 uç × 39 alan-vaka × 4 düşman değer
= 156 vaka, ``docs/scofield/raw/OH/D23/app-api/a2/{once,sonra}_supurme.json``):

=================================  =====  =====
ölçüt                              ÖNCE   SONRA
=================================  =====  =====
fail-closed (4xx)                    106    144
fail-open (2xx, düşman değerle)       46      8
ham çöküş (5xx)                        4      0
alanı ADIYLA anan 4xx                 48    104
=================================  =====  =====

Kalan 8 vaka ``chart_title`` ve ``filename`` alanlarıdır: ikisi de SERBEST
METİN ve ``input_guard.text`` sözleşmesi gereği ``str()`` ile çevirir
(uzunluk sınırı gelir, TİP reddi gelmez). Bu bilinen sınır burada da
yazılıdır — bekçi onu kusur diye saklamaz, ölçer.
"""

import json

import pytest

from hrma.app import app
from hrma.utils import input_guard


@pytest.fixture()
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _govde(r):
    return r.get_data(as_text=True)


# ---------------------------------------------------------------------------
# 1. Ortak yardımcı: DEĞER kapısı deponun TEK kaynağıdır
# ---------------------------------------------------------------------------

class TestJsonFloatTekKaynak:
    """``_json_float`` artık kapının kendisi değil, kapıya AÇILAN kapıdır.

    Bu yardımcı ``app.py``'de 60 okumanın altında duruyordu ve elle yazılmış
    üçüncü bir kopyaydı: ``float(True) == 1.0`` geçiyor, ``float('NaN')``
    geçiyordu. Gövdesi ``input_guard.num``'a devredildi.
    """

    def test_bool_artik_sayi_sayilmiyor(self):
        from hrma.app import _json_float
        with pytest.raises(ValueError) as exc:
            _json_float({'x': True}, 'x')
        assert 'x' in str(exc.value)

    def test_sonlu_olmayan_reddediliyor(self):
        from hrma.app import _json_float
        for bozuk in ('NaN', 'Infinity', '-Infinity'):
            with pytest.raises(ValueError):
                _json_float({'x': bozuk}, 'x')

    def test_cozulebilen_deger_bit_ayni(self):
        """Onarım hiçbir GEÇERLİ sayıyı değiştirmez (çapa şartı)."""
        from hrma.app import _json_float
        for ham, beklenen in ((0, 0.0), ('12.5', 12.5), (-3, -3.0),
                              (1e9, 1e9)):
            assert _json_float({'x': ham}, 'x') == beklenen
        assert _json_float({}, 'x') is None
        assert _json_float({'x': None}, 'x') is None
        assert _json_float({'x': ''}, 'x') is None

    def test_hata_sinifi_valueerror_soyundan(self):
        """Uçların ``except (ValueError, KeyError) -> 400`` dalı DEĞİŞMEDİ."""
        assert issubclass(input_guard.InputError, ValueError)


# ---------------------------------------------------------------------------
# 2. Uç davranışı — ölçülen fail-open delikleri kapandı
# ---------------------------------------------------------------------------

class TestUcKapisiFailClosed:
    """Taban ölçümünde HTTP 2xx dönen düşman girdiler artık 4xx.

    Her satırın kanıtı ``once_supurme.json`` içindedir; parametre listesi
    ölçümün kendisinden çıkarılmıştır (uydurma vaka yok).
    """

    #: (uç, taban gövde, alan) — taban ölçümünde 2xx ya da 5xx veren vakalar
    VAKALAR = [
        ('/api/altitude-to-pressure', {'altitude': 1000}, 'altitude'),
        ('/api/burn-rate/resolve',
         {'propellant': 'kndx', 'pressure_bar': 40}, 'pressure_bar'),
        ('/api/oxidizer-properties',
         {'oxidizer_type': 'n2o', 'temperature': 293.15}, 'temperature'),
        ('/api/get-fuel-properties',
         {'fuel_type': 'htpb', 'temperature': 298.15}, 'temperature'),
        ('/api/chemical-species',
         {'species_name': 'CO2', 'temperature': 2000}, 'temperature'),
        ('/api/quick-geometry',
         {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
          'chamber_pressure': 30, 'chamber_temperature': 3000}, 'gamma'),
        ('/api/quick-geometry',
         {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
          'chamber_pressure': 30, 'chamber_temperature': 3000},
         'contraction_ratio'),
        ('/api/thermal-protection',   # OH-D29-13: takma yol silindi
         {'mode': 'ablative', 'q_net_W_m2': 1e6, 'burn_time_s': 10,
          'material': 'carbon_phenolic', 'q_star_MJ_kg': 5.0},
         'q_star_MJ_kg'),
        ('/api/water-hammer',
         {'line_length_m': 3.0, 'line_id_mm': 20.0, 'wall_thickness_mm': 1.5,
          'working_pressure_bar': 40.0, 'mdot_kg_s': 2.0}, 'line_id_mm'),
        ('/api/regen-cooling',
         {'chamber_pressure': 30, 'chamber_temperature': 3000,
          'throat_diameter': 0.05, 'n_channels': 64, 'n_stations': 40},
         'n_channels'),
        ('/analyze_structural_safety',
         {'chamber_pressure': 30, 'chamber_diameter': 0.1,
          'chamber_length': 0.5, 'throat_diameter': 0.03, 'burn_time': 10,
          'thrust': 1000, 'chamber_temperature': 3000}, 'thrust'),
        # ÖH D32 (OH-D31-14): zorunlu dört alan (Tc, gamma, MW, P_amb)
        # tabana eklendi — değerleri ucun kanonik tablosundan, yani
        # yayımlanan sayı DEĞİŞMEDİ. Vakanın konusu (düşman
        # ``chamber_diameter`` değerinin ADIYLA reddi) etkilenmedi; eksik
        # taban olmasaydı ret artık önce "motoru tarif et" derdi.
        ('/api/flow-analysis',
         {'fidelity': 'fast', 'chamber_pressure': 30, 'of_ratio': 6.0,
          'chamber_temperature': 3000.0, 'gamma': 1.2,
          'molecular_weight': 24.0, 'ambient_pressure': 101325.0,
          # ÖH D33-2 / app-api-uc a1 (OH-D32-13): lüle geometrisi de tabana
          # eklendi. Değer, ucun EskİDEN SESSİZCE uyguladığı ε=4'tür, yani
          # yayımlanan sayı DEĞİŞMEDİ — yalnız gövde artık onu açıkça
          # söylüyor. Eksik geometri olmasaydı ret "önce lüleyi tarif et"
          # derdi ve vakanın konusu (düşman ``chamber_diameter`` değerinin
          # ADIYLA reddi) ölçülemezdi.
          'expansion_ratio': 4.0,
          'throat_diameter': 0.03, 'chamber_diameter': 0.1},
         'chamber_diameter'),
    ]

    DUSMAN = [True, 'NaN', 'Infinity', 'yirmi']

    @pytest.mark.parametrize('uc,taban,alan', VAKALAR,
                             ids=[f'{u}:{a}' for u, _t, a in VAKALAR])
    def test_dusman_deger_4xx_ve_alan_adiyla(self, client, uc, taban, alan):
        for deger in self.DUSMAN:
            govde = dict(taban)
            govde[alan] = deger
            r = client.post(uc, json=govde)
            metin = _govde(r)
            assert 400 <= r.status_code < 500, (
                '%s %s=%r -> HTTP %d (fail-open ya da ham çöküş). '
                'Kapı sökülmüş olabilir. Gövde: %s'
                % (uc, alan, deger, r.status_code, metin[:200]))
            assert alan in metin, (
                '%s %s=%r reddedildi ama alanı ADIYLA anmıyor — kullanıcı '
                'hangi kutuyu düzelteceğini göremez. Gövde: %s'
                % (uc, alan, deger, metin[:200]))

    def test_paket_ucu_bozuk_motor_verisiyle_dosya_uretmez(self, client):
        """``/api/generate-complete-package`` kapısı PAKETTEN ÖNCE konuşur.

        Taban ölçümü: ``motor_data.chamber_pressure`` / ``total_impulse``
        dört düşman değerin dördünde de HTTP 200 ile paketin İÇİNE giriyordu
        (motor sınıfı ve özet tablosu bu iki sayıdan doğar).
        """
        for alan in ('chamber_pressure', 'total_impulse'):
            for deger in self.DUSMAN:
                md = {'motor_name': 'T', 'motor_type': 'hybrid',
                      'chamber_pressure': 30, 'total_impulse': 10000}
                md[alan] = deger
                r = client.post('/api/generate-complete-package', json={
                    'motor_data': md,
                    'package_options': {'include_cad': False,
                                        'include_openrocket': False,
                                        'include_analysis': False,
                                        'include_manufacturing': False}})
                assert r.status_code == 422, (
                    'motor_data.%s=%r -> HTTP %d' % (alan, deger,
                                                     r.status_code))
                assert alan in _govde(r)

    def test_gecerli_govde_hala_gecer(self, client):
        """Kapı SAĞLIKLI istekleri kesmiyor (yanlış alarm kapısı).

        Fail-closed bir kapının tek gerçek sınavı budur: kusurlu girdiyi
        reddederken doğru girdiyi de reddediyorsa onarım değil, arıza olur.
        """
        r = client.post('/api/altitude-to-pressure', json={'altitude': 1000})
        assert r.status_code == 200
        govde = json.loads(_govde(r))
        assert govde['pressure_bar' if 'pressure_bar' in govde
                     else 'pressure'] is not None
        r = client.post('/api/burn-rate/resolve',
                        json={'propellant': 'kndx', 'pressure_bar': 40})
        assert r.status_code == 200

    def test_sifir_varsayilana_dusmez(self, client):
        """``0`` ile "verilmedi" ayrımı uç katmanında da korunuyor.

        ``input_guard``'ın kurucu ilkesi budur; kapı uca taşınırken
        kaybolmadığı burada ölçülür: ``altitude=0`` deniz seviyesidir,
        varsayılan da 0'dır — ama ``altitude=-100`` (Lut Gölü) gönderildiğinde
        yanıtın onu KULLANDIĞI görülmelidir.
        """
        r = client.post('/api/altitude-to-pressure', json={'altitude': -100})
        assert r.status_code == 200
        assert json.loads(_govde(r))['altitude'] == -100


# ---------------------------------------------------------------------------
# 3. Kapsam kilidi — kapı uçlardan sökülemez
# ---------------------------------------------------------------------------

class TestKapsamKilidi:
    """Envanterin UÇ ekseni. Sayı kilidi ``test_v262_release_gate.py``de."""

    #: Aşama-2'de kapı takılan 22 uç işlevi (ölçüldü, ``sonra_p13b4_12.json``
    #: C bölümü). Biri kapıyı bırakırsa bu liste kırmızıya döner.
    KAPILI_ISLEVLER = {
        'advanced_performance_analysis', 'altitude_to_pressure',
        'analyze_safety', 'analyze_structural_safety',
        'analyze_thermal_safety', 'api_burn_rate_resolve',
        'calculate_liquid', 'export_cad_files', 'export_chart_as_pdf',
        'export_xlsx', 'flow_analysis', 'generate_complete_design_package',
        'get_chemical_species', 'get_fuel_properties',
        'get_live_oxidizer_properties', 'get_propellant_properties',
        'kinetic_efficiency_analysis', 'quick_geometry',
        'regen_cooling_analysis', 'thermal_protection_analysis',
        'uncertainty_analysis', 'water_hammer_api',
    }

    def test_yirmi_iki_uc_kapiyi_hala_cagiriyor(self):
        import ast
        import pathlib
        kok = pathlib.Path(__file__).resolve().parent.parent
        agac = ast.parse((kok / 'hrma' / 'app.py').read_text(encoding='utf-8'))
        dogrudan, modul_adlari = {}, set()
        for n in ast.walk(agac):
            if isinstance(n, ast.ImportFrom):
                if n.module == 'hrma.utils.input_guard':
                    for a in n.names:
                        dogrudan[a.asname or a.name] = a.name
                elif n.module == 'hrma.utils':
                    for a in n.names:
                        if a.name == 'input_guard':
                            modul_adlari.add(a.asname or a.name)
        deger = ('num', 'integer', 'choice', 'text')
        kapili = set()
        for n in ast.walk(agac):
            if not isinstance(n, ast.FunctionDef):
                continue
            for c in ast.walk(n):
                if not isinstance(c, ast.Call):
                    continue
                f = c.func
                ad = None
                if isinstance(f, ast.Name) and f.id in dogrudan:
                    ad = dogrudan[f.id]
                elif (isinstance(f, ast.Attribute)
                      and isinstance(f.value, ast.Name)
                      and f.value.id in modul_adlari):
                    ad = f.attr
                if ad in deger:
                    kapili.add(n.name)
        eksik = self.KAPILI_ISLEVLER - kapili
        assert not eksik, (
            '%s işlevleri input_guard DEĞER kapısını artık ÇAĞIRMIYOR — '
            'ÖK-20/ADIM 3 kapsamı sökülmüş (P13B4-12).' % sorted(eksik))

    def test_flow_analysis_sessiz_yutma_geri_gelmedi(self):
        """``except (TypeError, ValueError): pass`` deseni geri konamaz.

        Taban ``ef527ae``'de ``/api/flow-analysis`` çözülemeyen
        ``chamber_diameter`` değerini sessizce YUTUYORDU: dört düşman
        değerin dördü de HTTP 200 dönüyor, kullanıcı gönderdiği çapın hiç
        kullanılmadığını göremiyordu (doktrin 1: sessiz yedek YASAK).
        """
        import pathlib
        kok = pathlib.Path(__file__).resolve().parent.parent
        metin = (kok / 'hrma' / 'app.py').read_text(encoding='utf-8')
        # ÖH D32 (D31 dersi 22 — KESİK DİLİM): pencere ``i + 8000`` idi ve
        # fonksiyona yorum eklendikçe ölçtüğü kodu kapsam DIŞINDA bırakıp
        # sessizce yeşile dönebiliyordu. Dilim artık fonksiyonun GERÇEK
        # sonuna bağlı ve okunan alanın dilimin İÇİNDE olduğu ölçülüyor.
        i = metin.find('def flow_analysis(')
        assert i > 0
        j = metin.find('\n@app.route(', i)
        assert j > i, 'flow_analysis sonu bulunamadı'
        govde = metin[i:j]
        assert "data.get('chamber_diameter')" in govde, (
            'bekçi ölçtüğü kodu kaybetti — dilim fonksiyonu kapsamıyor')
        assert "float(data.get('chamber_diameter'))" not in govde, (
            'ham float() geri gelmiş — sessiz yutma deseninin kökü budur')
