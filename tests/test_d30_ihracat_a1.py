# -*- coding: utf-8 -*-
"""OH D30 / ihracat a1 bekcileri — OH-D29-09 + S1-05, OH-D29-04, OH-D29-10.

Olcum betigi ve once/sonra sayilari:
``docs/scofield/raw/OH/D30/ihracat/a1/`` (olcum.py, once_taban.json,
sonra.json, mutasyon.json).

Dugum adlari ASCII'dir (D27 dersi 10: homoglif tarayicisi depo genelinde).
"""
import contextlib
import io
import json
import os
import re

import pytest

from hrma.app import app

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: D29 app-api-uc a2 K5'in ihracat ailesi — olcut degistirilmedi.
IHRACAT_UCLARI = (
    '/api/export-stl', '/api/export-dxf', '/api/export-step',
    '/api/export-drawings-pdf', '/api/export-complete-zip',
    '/api/export-stl-zip', '/api/export-eng', '/api/export-openrocket',
    '/api/export-simulation', '/api/export-cad',
)

#: D29 K5'in "saglikli" govdesi (AYNEN). Bu govde STL'e ``port_diameter``,
#: STEP'e yapisal cidar borclu oldugu icin iki ucta da 422 alir — kalemin
#: konusu bu reddin NE SOYLEDIGIDIR, reddin kendisi degil.
SAGLIKLI = {
    'motor_name': 'AILE', 'chamber_diameter': 0.1, 'chamber_length': 0.5,
    'throat_diameter': 0.03, 'exit_diameter': 0.08, 'nozzle_length': 0.2,
    'wall_thickness': 0.005, 'thrust': 1000.0, 'burn_time': 10.0,
    'total_impulse': 10000.0, 'propellant_mass': 4.0, 'total_mass': 10.0,
}

KOD_DESENI = re.compile(r'^[a-z][a-z0-9_]*$')


@pytest.fixture(scope='module')
def istemci():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _post(istemci, yol, govde):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            cevap = istemci.post(yol, json=govde)
    try:
        return cevap, cevap.get_json()
    except Exception:  # pragma: no cover - govde JSON degilse
        return cevap, None


def _adlandirilmis_yollar(govde):
    """Reddin makine-okur olarak ADLANDIRDIGI alan yollari."""
    yollar = []
    if not isinstance(govde, dict):
        return yollar
    for k in (govde.get('invalid_fields') or []):
        if isinstance(k, dict) and isinstance(k.get('field'), str):
            yollar.append(k['field'])
    for f in (govde.get('missing_fields') or []):
        if isinstance(f, str):
            yollar.append(f)
    return sorted(set(yollar))


class TestOHD2909AileRetKodu:
    """S1-05 / OH-D29-09 (a): ret govdesinde ``error`` MAKINE-OKUR koddur.

    OLCULDU (taban ab7cf68b, once_taban.json K1): ailenin 32 ret hucresinin
    30'u kod, 2'si (``/api/export-stl``, bos ve saglikli govde) Ingilizce
    CUMLE yayimliyordu. Ayni alani bir ucta kod bir ucta cumle olarak okuyan
    istemci ya cumleye desen yazar ya da hepsini duser.
    """

    GOVDELER = {
        'saglikli': {'motor_data': dict(SAGLIKLI)},
        'bos': {},
        'motor_data_liste': {'motor_data': [1, 2, 3]},
        'motor_data_metin': {'motor_data': 'abc'},
    }

    @pytest.mark.parametrize('yol', IHRACAT_UCLARI)
    @pytest.mark.parametrize('etiket', sorted(GOVDELER))
    def test_ret_govdesinde_error_kod_biciminde(self, istemci, yol, etiket):
        cevap, govde = _post(istemci, yol, dict(self.GOVDELER[etiket]))
        if cevap.status_code < 400:
            pytest.skip('bu hucre kabul ediliyor; ret sozlesmesi konu disi')
        assert isinstance(govde, dict), (yol, etiket)
        kod = govde.get('error')
        assert kod, (yol, etiket, govde)
        assert KOD_DESENI.match(str(kod)), (
            'error alani makine-okur kod olmali, cumle degil: '
            f'{yol} [{etiket}] -> {kod!r}')

    def test_export_stl_cumlesi_message_alaninda_KORUNDU(self, istemci):
        """Kullaniciya donuk Ingilizce metin SILINMEDI, tasindi."""
        cevap, govde = _post(istemci, '/api/export-stl',
                             {'motor_data': dict(SAGLIKLI)})
        assert cevap.status_code == 422
        assert govde['error'] == 'incomplete_export_geometry'
        assert 'Cannot export STL' in govde['message']
        # Kardes bekcilerin (test_stl_export_fail_closed, test_faz5_app_export,
        # test_d15/d17/d21_app_api_*) okudugu alan DEGISMEDI.
        assert govde['status'] == 'incomplete_geometry'
        assert govde['missing_fields'] == ['port_diameter']
        assert govde['motor_type'] == 'hybrid'

    def test_export_stl_invalid_fields_gerekce_ve_gondereni_tasir(
            self, istemci):
        cevap, govde = _post(istemci, '/api/export-stl',
                             {'motor_data': dict(SAGLIKLI)})
        kunye = govde['invalid_fields']
        assert [k['field'] for k in kunye] == ['port_diameter']
        assert kunye[0]['reason'] == 'not_supplied'
        assert kunye[0]['submitted'] is None
        # SIFIR "verilmedi" ile ayni kefededir ama AYNI SEY DEGILDIR:
        # kunye gonderilen sifiri geri gosterir.
        _, sifirli = _post(istemci, '/api/export-stl',
                           {'motor_data': dict(SAGLIKLI, port_diameter=0)})
        assert sifirli['invalid_fields'][0]['reason'] == (
            'zero_not_manufacturable')
        assert sifirli['invalid_fields'][0]['submitted'] == 0


class TestOHD2909StepAlaniAdiylaVerir:
    """S1-05 / OH-D29-09 (b): ``/api/export-step`` reddi ALANI ADIYLA verir.

    OLCULDU (taban ab7cf68b, once_taban.json K1 EYLEM turu): govde makine-okur
    SIFIR alan adi tasidigi icin "reddin adlandirdigini doldur, yeniden
    gonder" turu 422'de KILITLI kaliyordu; ayni tur ``/api/export-stl``
    uzerinde tek adimda 200'e cikiyordu.
    """

    def test_step_reddi_makine_okur_alan_adlandirir(self, istemci):
        cevap, govde = _post(istemci, '/api/export-step',
                             {'motor_data': dict(SAGLIKLI)})
        assert cevap.status_code == 422
        assert govde['error'] == 'incomplete_export_inputs'
        kunye = govde['invalid_fields']
        assert kunye, 'ret hicbir alan adlandirmiyor'
        for k in kunye:
            assert KOD_DESENI.match(k['reason']), k
            assert isinstance(k['field'], str) and k['field'], k

    def test_step_cidar_yollari_SEMA_TABLOSUNDAN_turetilir(self, istemci):
        """Kabul yollari elle yazilmis olsaydi dorduncu sema onu bayatlatirdi."""
        from hrma.export.cad_visualization import CHAMBER_WALL_SCHEMAS
        beklenen = [f'structural_analysis.{blok}.{anahtar}'
                    for blok, kullanilan, onerilen, _y in CHAMBER_WALL_SCHEMAS
                    for anahtar in (kullanilan, onerilen)]
        _, govde = _post(istemci, '/api/export-step',
                         {'motor_data': dict(SAGLIKLI)})
        kunye = govde['invalid_fields'][0]
        assert kunye['accepted_paths'] == beklenen
        assert kunye['field'] == beklenen[0]
        assert kunye['reason'] == 'not_supplied'
        # Uc sema da temsil edilir (hibrit / kati / sivi).
        for blok in ('chamber_analysis', 'case_analysis', 'chamber_structure'):
            assert any(blok in y for y in kunye['accepted_paths']), blok


def _saglikli_kamara_sf(cidar_mm):
    """SAGLIKLI kamarasının ``cidar_mm`` cidarındaki emniyet katsayısı.

    ÖH V3 CAD A1 · H5 — bağımsız kâhin (dışa aktarım kod yolu değil): kalın
    cidarlı silindirin iç yüzündeki tepe çember gerilmesi (Lamé,
    Roark/Shigley) σ = P·(r_o² + r_i²)/(r_o² − r_i²). r_i gövdenin kendi
    ``chamber_diameter`` alanından; P = 20 bar, bu dosyada SAGLIKLI gövdesine
    verilen işletme basıncı (``chamber_pressure=20.0``); akma dayanımı yapısal
    modülün varsayılan malzemesi steel_4130'un oda sıcaklığı kaydı
    (``materials_db``, 460 MPa). 5 mm cidarda SF ≈ 21,9.
    """
    from hrma.data.materials_db import get_material
    kamara_basinci_pa = 20e5
    r_i = 1000.0 * SAGLIKLI['chamber_diameter'] / 2.0
    r_o = r_i + cidar_mm
    tepe_cember_pa = (kamara_basinci_pa * (r_o ** 2 + r_i ** 2)
                      / (r_o ** 2 - r_i ** 2))
    return get_material('steel_4130')['yield_strength'] / tepe_cember_pa


class TestOHD2909ReddinYoluIZLENEBILIR:
    """S1-05 kalan yari: ret EYLEME DONUSTURULEBILIR mi.

    Kalemin urun sorusu "iki uc neden 422 veriyor" degil (gereksinim farki
    mesrudur), "reddi okuyan istemci 200'e cikabiliyor mu"dur.
    """

    DOLGU = {
        'port_diameter': 0.04,
        'structural_analysis.chamber_analysis.wall_thickness_used_mm': 5.0,
        'structural_analysis.chamber_analysis.recommended_thickness': 5.0,
    }
    # ÖH V3 CAD A1 · H5 — ÇEVRİLDİ (12 Eki 2026, ana model izni, dört koşul;
    # rapor docs/scofield/raw/OH/V3/cad-duzeltme/rapor.md "Bölüm T"). Karar
    # §28-21 (i): imalat emniyet kapısı SF'siz basınç taşıyan parçanın
    # STEP'ini reddeder ve reddi bu yolu ``invalid_fields``ta ADLANDIRIR;
    # yol DOLGU'da yoktu, istemci 422'de kalıyordu. Değer, aynı DOLGU'nun
    # yazdığı cidardaki SF'dir (kâhin: ``_saglikli_kamara_sf``).
    DOLGU['structural_analysis.chamber_analysis.safety_factor_total'] = (
        _saglikli_kamara_sf(
            DOLGU['structural_analysis.chamber_analysis.wall_thickness_used_mm']))

    @staticmethod
    def _yaz(hedef, yol, deger):
        parcalar = yol.split('.')
        d = hedef
        for p in parcalar[:-1]:
            d = d.setdefault(p, {})
        d[parcalar[-1]] = deger

    @pytest.mark.parametrize('uc', ['/api/export-stl', '/api/export-step'])
    def test_reddin_adlandirdigi_yolu_dolduran_govde_200_alir(
            self, istemci, uc):
        motor = dict(SAGLIKLI)
        gorulen = []
        for _ in range(4):
            cevap, govde = _post(istemci, uc, {'motor_data': motor})
            if cevap.status_code == 200:
                break
            yollar = _adlandirilmis_yollar(govde)
            gorulen.append((cevap.status_code, yollar))
            assert yollar, (
                f'{uc}: ret hicbir yol adlandirmiyor, istemci 422 de KILITLI '
                f'-> {govde}')
            dolduruldu = False
            for y in yollar:
                for anahtar, deger in self.DOLGU.items():
                    if anahtar == y or anahtar.endswith('.' + y):
                        self._yaz(motor, anahtar, deger)
                        dolduruldu = True
            assert dolduruldu, (
                f'{uc}: adlandirilan yollarin hicbiri doldurulabilir degil '
                f'-> {yollar}')
        assert cevap.status_code == 200, (uc, gorulen)
        assert len(cevap.get_data()) > 1000, uc


class TestOHD2904Changelog2627:
    """OH-D29-04: 2.6.27 kaydi kirici degisiklikleri ADIYLA yaziyor mu.

    Olcut: istemcinin GREPLEYECEGI kimlik (alan adi ya da gerekce kodu)
    hem EN hem TR blogunda gecmeli. OLCULDU (taban ab7cf68b): bes konunun
    besi de iki blokta da YOKTU.
    """

    KONULAR = {
        'mass_breakdown_yalniz_kutle': ('mass_breakdown', 'geometry_summary',
                                        'material_summary'),
        'ambient_temp_bant_disi': ('ambient_temperature',),
        'planar_grain_basinc_bandi': ('planar',
                                      'chamber_pressure_out_of_range'),
        'hibrit_tnt_esdegeri': ('hybrid_oxidizer_tnt_equivalent',),
        'dort_422_kapisi': ('invalid_safety_factor',
                            'invalid_ambient_temperature'),
        'ihracat_ret_sozlesmesi': ('incomplete_export_geometry',
                                   'invalid_fields', 'accepted_paths'),
    }

    @staticmethod
    def _kayit():
        with open(os.path.join(KOK, 'hrma', 'data', 'changelog.json'),
                  encoding='utf-8') as fh:
            veri = json.load(fh)
        # karar §28-19/§28-46: yayımlanmamış 2.6.27 kaydı 3.0.0 adıyla çıkar.
        kayit = next((s for s in veri['versions']
                      if s.get('version') == '3.0.0'), None)
        assert kayit is not None, '3.0.0 kaydı yok'
        return kayit

    @pytest.mark.parametrize('dil', ['notes_en', 'notes_tr'])
    @pytest.mark.parametrize('konu', sorted(KONULAR))
    def test_konu_iki_dilde_de_adiyla_geciyor(self, dil, konu):
        metin = self._kayit()[dil]
        for imza in self.KONULAR[konu]:
            assert imza in metin, f'{dil} bloğunda "{imza}" yok ({konu})'

    def test_tnt_sayilari_URUNUN_kendi_ciktisiyla_ayni(self):
        """Kaydin yazdigi sayi kodun urettigiyle bagli — bayatlarsa KIRMIZI."""
        from hrma.analysis.safety_analysis import (
            hybrid_oxidizer_tnt_equivalent)
        metin = self._kayit()['notes_en']
        for oksitleyici in ('n2o', 'h2o2'):
            deger = round(hybrid_oxidizer_tnt_equivalent(oksitleyici), 3)
            assert f'`hybrid_{oksitleyici}` = {deger:.3f}' in metin, (
                oksitleyici, deger)

    def test_tasinan_alan_adlari_GERCEKTEN_yeni_adreste(self):
        """Kaydin adlandirdigi yeni adres uruende var mi (yalan kayit yok)."""
        from hrma.export.cad_visualization import MotorCADDesigner
        motor = dict(SAGLIKLI, chamber_pressure=20.0, structural_analysis={
            'chamber_analysis': {'wall_thickness_used_mm': 5.0,
                                 'recommended_thickness': 7.5,
                                 'design_mode': 'verify'}})
        with contextlib.redirect_stdout(io.StringIO()):
            ozet = MotorCADDesigner()._generate_cad_performance_summary(motor)
        geo = ozet['geometry_summary']
        for alan in ('wall_thickness_mm', 'wall_thickness_source',
                     'wall_thickness_recommended_mm', 'wall_thickness_note'):
            assert alan in geo, alan
        # ...ve eski adreste KOPYA yok (kayit "kopya birakilmadi" diyor).
        assert not [a for a in ozet['mass_breakdown'] if 'wall_thickness' in a]


class TestOHD2910CidarKunyesiIkiAdres:
    """OH-D29-10: ayni cidar gercegi iki adreste — yon tarifi + baglama.

    OLCULDU (taban ab7cf68b, once_taban.json K3): dort cift x uc sema = 12
    ciftin 12'si DEGERCE ESIT (ayrisma yok, cunku ikisi de
    ``_chamber_wall_design``ten besleniyor) ama iki adresin hicbiri otekini
    ANMIYORDU ve adlar bire bir tutmuyor (``wall_thickness`` <->
    ``wall_thickness_mm``).
    """

    SEMALAR = {
        'hibrit': {'chamber_analysis': {'wall_thickness_used_mm': 5.0,
                                        'recommended_thickness': 7.5,
                                        'design_mode': 'verify'}},
        'kati': {'case_analysis': {'wall_thickness_mm': 4.0,
                                   'recommended_wall_thickness_mm': 6.0}},
        'sivi': {'chamber_structure': {'wall_thickness': 3.0,
                                       'required_wall_thickness': 3.0}},
    }
    CIFTLER = (('wall_thickness', 'wall_thickness_mm'),
               ('wall_thickness_source', 'wall_thickness_source'),
               ('wall_thickness_recommended', 'wall_thickness_recommended_mm'),
               ('wall_thickness_note', 'wall_thickness_note'))

    @staticmethod
    def _uret(struct):
        from hrma.export.cad_visualization import MotorCADDesigner
        motor = dict(SAGLIKLI, chamber_pressure=20.0,
                     structural_analysis=struct)
        tasarimci = MotorCADDesigner()
        with contextlib.redirect_stdout(io.StringIO()):
            ciz = tasarimci._generate_technical_drawings(motor)['chamber']
            ozet = tasarimci._generate_cad_performance_summary(motor)
        return ciz, ozet['geometry_summary']

    @pytest.mark.parametrize('sema', sorted(SEMALAR))
    def test_iki_adres_AYRISAMAZ(self, sema):
        ciz, geo = self._uret(self.SEMALAR[sema])
        for cizim_alani, ozet_alani in self.CIFTLER:
            assert ciz[cizim_alani] == geo[ozet_alani], (
                f'{sema}: {cizim_alani} != {ozet_alani}')

    @pytest.mark.parametrize('sema', sorted(SEMALAR))
    def test_cizim_kardes_adresi_ADIYLA_aniyor(self, sema):
        ciz, _ = self._uret(self.SEMALAR[sema])
        kunye = ciz['wall_thickness_basis']
        assert 'MILLIMETRES' in kunye, 'birim yazili degil'
        assert '_chamber_wall_design' in kunye, 'tek kaynak anilmiyor'
        assert 'performance_summary.geometry_summary' in kunye

    @pytest.mark.parametrize('sema', sorted(SEMALAR))
    def test_yon_tarifi_ANDIGI_ANAHTARLAR_kardeste_gercekten_var(self, sema):
        """Yon tarifi bayatlarsa KIRMIZI: andigi her anahtar kardeste olmali."""
        ciz, geo = self._uret(self.SEMALAR[sema])
        kunye = ciz['wall_thickness_basis']
        anilan = re.findall(r'\.?(wall_thickness[a-z_]*)', kunye)
        kardeste_anilan = {a for a in anilan if a in
                           ('wall_thickness_mm', 'wall_thickness_source',
                            'wall_thickness_recommended_mm',
                            'wall_thickness_note')}
        assert kardeste_anilan == {'wall_thickness_mm', 'wall_thickness_source',
                                   'wall_thickness_recommended_mm',
                                   'wall_thickness_note'}, kardeste_anilan
        for a in kardeste_anilan:
            assert a in geo, f'yon tarifi bayat: {a} kardeste yok'
        # ...ve bu sozlukteki kendi adlari da gercekten burada.
        for a in ('wall_thickness', 'wall_thickness_as_designed',
                  'wall_thickness_recommended'):
            assert a in ciz, a

    def test_SAYI_KOPYALANMADI(self):
        """Yon tarifi bir ADRES tarifidir; icine sayi gomulmez."""
        ciz, _ = self._uret(self.SEMALAR['hibrit'])
        kunye = ciz['wall_thickness_basis']
        assert not re.search(r'\d+\.\d+', kunye), kunye
