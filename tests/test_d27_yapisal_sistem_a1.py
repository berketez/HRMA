# -*- coding: utf-8 -*-
"""ÖH D27 · yapisal-sistem · aşama 1 — bekçiler.

TEK KALEM: **P5B3-16** (D26 DEVİR, hüküm-15 ŞART AYNEN).

Kusur ``docs/scofield/raw/OH/D27/yapisal-sistem/a1/once.json`` içinde
SAYIYLA ölçüldü: ``expulsion_efficiency`` (boşaltma verimi η) modülün iki
dalında İKİ AYRI ÇIPLAK SAYIYLA yazılıydı —
``autogenous_pressurant`` 0,95, ``regulated_pressurant`` 1,0; ortak sabit
YOKTU (``kaynakta_atama_sayisi = 0``, AST ``ciplak_sayi_imza_sayisi = 2``).
Doktrin 4 (TEK KAYNAK) ihlali olmasının yanında FİZİKSEL bir kusurdur:
regüle dalı örtük olarak "tank yüklenen iticinin %100'ünü teslim eder"
diyordu, yani gaz envanteri ve şişe hacmi 1/0,95 = %5,263 EKSİK
boyutlanıyordu.

Onarım: tek sabit ``EXPULSION_EFFICIENCY_DEFAULT = 0.95`` (literatür
çıpası Huzel & Huang Böl. 5 uygulama bandı 0,90-0,99; Sutton & Biblarz
9. baskı Böl. 6), iki imza da ONU okur, geçerlilik kapısı
``EXPULSION_EFFICIENCY_VALID`` (0,50-1,00) aynen korunur.

Ters-mutasyon kanıtı: ``mutasyon.json`` (aynı dizin).
"""
import ast
import inspect
import pathlib

import pytest

from hrma.analysis import pressurant_sizing as PS
from hrma.analysis.pressurant_sizing import (EXPULSION_EFFICIENCY_DEFAULT,
                                             EXPULSION_EFFICIENCY_VALID,
                                             autogenous_pressurant,
                                             regulated_pressurant)
from tests.support.kanit import kanit_gerekli

KAYNAK = pathlib.Path(PS.__file__).read_text(encoding='utf-8')

#: Ölçüm gövdeleri — ``once.json`` ile BİREBİR aynı girdiler.
REG_TABAN = dict(propellant_volume=0.5, tank_pressure=30.0e5, gas='helium')
AUTO_TABAN = dict(propellant_volume=0.5, tank_pressure=30.0e5,
                  propellant='lox')

#: D26 çıpası: regüle gövdesi η = 1,0 ile (taban 7751531 / 709a235e).
#: ÖH D27 onarımından sonra varsayılan gövde bunun TAM OLARAK 1/η katıdır.
D26_CIPASI = {
    'isothermal': 2.4632561940010134,
    'adiabatic': 5.261057881774493,
    'delivered': 3.149732040049564,
    'bottle_m3': 0.16394736645480523,
}
#: Autogenous gövdesi onarımdan ETKİLENMEZ (varsayılanı zaten 0,95'ti).
AUTO_CIPASI_KG = 24.310198128114745


def _imza_varsayilani_AST(fonksiyon_adi):
    """İmzadaki varsayılanın AST düğümünü döndürür (Name mi Constant mı)."""
    agac = ast.parse(KAYNAK)
    for d in ast.walk(agac):
        if not isinstance(d, ast.FunctionDef) or d.name != fonksiyon_adi:
            continue
        args = d.args.args + d.args.kwonlyargs
        defs = ([None] * (len(d.args.args) - len(d.args.defaults))
                + list(d.args.defaults) + list(d.args.kw_defaults))
        for a, v in zip(args, defs):
            if a.arg == 'expulsion_efficiency':
                return v
    raise AssertionError(
        f'{fonksiyon_adi} imzasında expulsion_efficiency YOK')


class TestP5B316OrtakVarsayilan:
    """P5B3-16 — boşaltma veriminin TEK varsayılanı (hüküm-15 ŞART)."""

    def test_ortak_sabit_VAR_ve_TEK_KEZ_yazili(self):
        """ÖLÇÜLDÜ: önce ``kaynakta_atama_sayisi = 0`` (sabit yoktu)."""
        assert hasattr(PS, 'EXPULSION_EFFICIENCY_DEFAULT'), (
            'ortak varsayılan sabiti yok — sayı imzalarda kopyalanıyor')
        assert PS.EXPULSION_EFFICIENCY_DEFAULT == 0.95
        assert KAYNAK.count('EXPULSION_EFFICIENCY_DEFAULT = ') == 1, (
            'sabit birden fazla kez atanmış (Doktrin 4 ihlali)')

    def test_varsayilan_GECERLILIK_bandinin_icinde(self):
        """Varsayılan ile band iki AYRI sabittir; varsayılan bandı ihlal
        ederse modülün kendi sağlıklı çağrısı reddedilirdi."""
        lo, hi = EXPULSION_EFFICIENCY_VALID
        assert lo <= EXPULSION_EFFICIENCY_DEFAULT <= hi
        assert EXPULSION_EFFICIENCY_DEFAULT != hi, (
            '1,0 kesrin fiziksel TAVANIDIR, tasarım varsayılanı değil')

    @pytest.mark.parametrize('fonksiyon_adi', ['regulated_pressurant',
                                               'autogenous_pressurant'])
    def test_IMZA_ciplak_sayi_degil_SABIT_ADI_okur(self, fonksiyon_adi):
        """ASIL BEKÇİ (AST). ÖLÇÜLDÜ: önce iki imza da ÇIPLAK SAYI
        taşıyordu (regüle 1,0 / autogenous 0,95); şimdi ikisi de ortak
        sabitin ADINI okur. Bir dal sabitten koparılıp sayı yeniden
        yazılırsa bu düğüm kırmızı olur."""
        dugum = _imza_varsayilani_AST(fonksiyon_adi)
        assert isinstance(dugum, ast.Name), (
            f'{fonksiyon_adi} varsayılanı çıplak sayı '
            f'({ast.dump(dugum)}) — ortak sabit okunmuyor')
        assert dugum.id == 'EXPULSION_EFFICIENCY_DEFAULT'

    def test_IKI_DAL_da_ayni_varsayilani_calistiriyor(self):
        """ÖLÇÜLDÜ: önce ``iki_dal_ayni_mi = false`` (1,0 ve 0,95)."""
        varsayilanlar = {
            ad: inspect.signature(fn).parameters[
                'expulsion_efficiency'].default
            for ad, fn in (('regulated', regulated_pressurant),
                           ('autogenous', autogenous_pressurant))}
        assert varsayilanlar['regulated'] == varsayilanlar['autogenous']
        assert varsayilanlar['regulated'] is EXPULSION_EFFICIENCY_DEFAULT

    def test_LITERATUR_kunyesi_sabitin_yaninda(self):
        """Sayı KALİBRASYON değil, adı geçen bir kaynağa dayanır."""
        yer = KAYNAK.index('EXPULSION_EFFICIENCY_DEFAULT = ')
        kunye = KAYNAK[max(0, yer - 4000):yer]
        for parca in ('Huzel & Huang', 'Sutton & Biblarz', '0,90-0,99',
                      'Böl. 5'):
            assert parca in kunye, f'künyede eksik: {parca}'
        assert '709a235e' in kunye, 'ölçüm tabanı künyede yok'


class TestP5B316ReguleGovdesi:
    """Onarımın ürün etkisi: regüle gövdesi TAM OLARAK 1/η katına çıkar."""

    def test_varsayilan_govde_D26_cipasinin_1_bolu_eta_kati(self):
        """ÖLÇÜLDÜ (once/sonra.json): iso 2,4632561940010134 ->
        2,5929012568431715 kg; şişe 0,16394736645480523 ->
        0,17257617521558447 m3."""
        r = regulated_pressurant(**REG_TABAN)
        eta = EXPULSION_EFFICIENCY_DEFAULT
        assert r['expulsion_efficiency'] == eta
        assert r['swept_volume_m3'] == pytest.approx(
            REG_TABAN['propellant_volume'] / eta, rel=1e-12)
        assert r['isothermal']['gas_mass_kg'] == pytest.approx(
            D26_CIPASI['isothermal'] / eta, rel=1e-12)
        assert r['adiabatic']['gas_mass_kg'] == pytest.approx(
            D26_CIPASI['adiabatic'] / eta, rel=1e-12)
        assert r['recommended_delivered_mass_kg'] == pytest.approx(
            D26_CIPASI['delivered'] / eta, rel=1e-12)
        assert r['storage']['bottle_water_volume_m3'] == pytest.approx(
            D26_CIPASI['bottle_m3'] / eta, rel=1e-12)

    def test_sapma_SADECE_eta_kaynakli_ILISKI(self):
        """İlişki bekçisi (sayı bekçisi değil): η = 1,0 AÇIKÇA verilince
        gövde D26 çıpasına geri döner, yani onarım η dışında hiçbir şeyi
        oynatmadı."""
        eta1 = regulated_pressurant(expulsion_efficiency=1.0, **REG_TABAN)
        vars_ = regulated_pressurant(**REG_TABAN)
        assert eta1['isothermal']['gas_mass_kg'] == pytest.approx(
            D26_CIPASI['isothermal'], rel=1e-12)
        assert eta1['storage']['bottle_water_volume_m3'] == pytest.approx(
            D26_CIPASI['bottle_m3'], rel=1e-12)
        oran = 1.0 / EXPULSION_EFFICIENCY_DEFAULT
        for yol in (('isothermal', 'gas_mass_kg'),
                    ('adiabatic', 'gas_mass_kg'),
                    ('storage', 'bottle_water_volume_m3')):
            assert vars_[yol[0]][yol[1]] == pytest.approx(
                oran * eta1[yol[0]][yol[1]], rel=1e-12), yol

    def test_model_notu_supurulen_hacmi_ADIYLA_soyluyor(self):
        """Sapma BEYANLIDIR (Doktrin 1: künye gerçeği söyler)."""
        not_ = regulated_pressurant(**REG_TABAN)['model_note']
        assert 'eta_ex' in not_
        assert 'V_p/eta_ex' in not_

    def test_AUTOGENOUS_govdesi_BIT_AYNI_kaldi(self):
        """Onarım yalnız regüle dalını oynattı; kardeş dalın varsayılanı
        zaten 0,95'ti, gövdesi kıl payı değişmemeli."""
        a = autogenous_pressurant(**AUTO_TABAN)
        assert a['status'] == 'ok'
        assert a['gas_mass_kg'] == pytest.approx(AUTO_CIPASI_KG, rel=1e-12)


class TestP5B316BandKapisiKorundu:
    """ŞART: kapı AYNEN korunur — varsayılan değişimi kapıyı gevşetmez."""

    BAND_DISI = [1.5, 10.0, 0.01, 0.4999, 0.0, -0.5,
                 float('inf'), float('nan')]

    @pytest.mark.parametrize('eta', BAND_DISI)
    def test_regule_band_disini_ADIYLA_reddeder(self, eta):
        with pytest.raises(ValueError) as ex:
            regulated_pressurant(expulsion_efficiency=eta, **REG_TABAN)
        lo, hi = EXPULSION_EFFICIENCY_VALID
        assert 'expulsion_efficiency' in str(ex.value)
        assert f'[{lo}, {hi}]' in str(ex.value)

    #: Autogenous dalında ``eta <= 0`` ondan ÖNCEKİ pozitiflik kapısına
    #: takılır ("girdi pozitif olmalı"), band kapısına hiç ulaşmaz. Bu
    #: D20'den beri böyledir ve ÖLÇÜLDÜ (``once.json`` ``band_kapisi``:
    #: iki değer de ``error``); bu kalemin konusu değildir, o yüzden alan
    #: adı yalnız band kapısının gördüğü değerlerde aranır.
    BAND_DISI_POZITIF = [1.5, 10.0, 0.01, 0.4999,
                         float('inf'), float('nan')]

    @pytest.mark.parametrize('eta', BAND_DISI_POZITIF)
    def test_autogenous_band_disini_ADIYLA_reddeder(self, eta):
        r = autogenous_pressurant(**dict(AUTO_TABAN,
                                         expulsion_efficiency=eta))
        assert r['status'] == 'error'
        assert 'expulsion_efficiency' in r['reason']
        assert 'gas_mass_kg' not in r

    @pytest.mark.parametrize('eta', [0.0, -0.5])
    def test_autogenous_sifir_ve_alti_pozitiflik_kapisinda_kalir(self, eta):
        r = autogenous_pressurant(**dict(AUTO_TABAN,
                                         expulsion_efficiency=eta))
        assert r['status'] == 'error'
        assert 'gas_mass_kg' not in r

    @pytest.mark.parametrize('eta', [0.50, 0.90, 0.95, 1.00])
    def test_bandin_ICI_iki_dalda_da_gecer(self, eta):
        r = regulated_pressurant(expulsion_efficiency=eta, **REG_TABAN)
        assert r['expulsion_efficiency'] == pytest.approx(eta)
        a = autogenous_pressurant(**dict(AUTO_TABAN,
                                         expulsion_efficiency=eta))
        assert a['status'] == 'ok'


class TestP5B316UcBosaltmaVeriminiIfadeEdebiliyor:
    """Modülde parametre var, UÇTA yoktu: aynı kusurun bir kat yukarısı.

    ÖLÇÜLDÜ (``capa_once.json`` B1): ``POST /api/pressurant-sizing``
    regüle dalı ``expulsion_efficiency`` alanını hiç okumuyordu, yani
    kullanıcı yalnız modül varsayılanını alabiliyordu (autogenous dalı
    aynı alanı D23'ten beri geçiriyor).
    """

    @pytest.fixture(scope='class')
    def istemci(self):
        from hrma.app import app
        app.config['TESTING'] = True
        return app.test_client()

    YUK = {'mode': 'regulated', 'propellant_volume': 0.5,
           'tank_pressure': 30.0}

    def test_uc_varsayilani_modulun_ORTAK_sabiti(self, istemci):
        r = istemci.post('/api/pressurant-sizing', json=self.YUK)
        assert r.status_code == 200
        p = r.get_json()['pressurant']
        assert p['expulsion_efficiency'] == pytest.approx(
            EXPULSION_EFFICIENCY_DEFAULT, rel=1e-12)
        assert p['isothermal']['gas_mass_kg'] == pytest.approx(
            D26_CIPASI['isothermal'] / EXPULSION_EFFICIENCY_DEFAULT,
            rel=1e-9)

    def test_uc_verilen_etayi_GERCEKTEN_uyguluyor(self, istemci):
        taban = istemci.post('/api/pressurant-sizing',
                             json=self.YUK).get_json()['pressurant']
        acik = istemci.post('/api/pressurant-sizing',
                            json=dict(self.YUK, expulsion_efficiency=0.60)
                            ).get_json()['pressurant']
        assert acik['expulsion_efficiency'] == pytest.approx(0.60)
        oran = EXPULSION_EFFICIENCY_DEFAULT / 0.60
        assert acik['isothermal']['gas_mass_kg'] == pytest.approx(
            oran * taban['isothermal']['gas_mass_kg'], rel=1e-12)
        assert acik['storage']['bottle_water_volume_m3'] == pytest.approx(
            oran * taban['storage']['bottle_water_volume_m3'], rel=1e-12)

    @pytest.mark.parametrize('eta', [1.5, 0.01, -0.5])
    def test_uc_band_disini_400_ile_ADIYLA_reddeder(self, istemci, eta):
        """FAIL-CLOSED: sayı uydurulmaz, alan adıyla ret."""
        r = istemci.post('/api/pressurant-sizing',
                         json=dict(self.YUK, expulsion_efficiency=eta))
        assert r.status_code == 400
        govde = r.get_json()
        assert govde['status'] == 'error'
        assert 'expulsion_efficiency' in govde['error']
        assert 'pressurant' not in govde
class TestP5B316EnvanterTazelendi:
    """P13 parmak-izi envanterinin YAN ETKİSİ, dürüstçe kapatıldı.

    ``test_pressurant.py`` içindeki helyum el-hesabı çıpası türetimle
    yeniden yazılınca envanterdeki (``docs/scofield/raw/P13/
    parmak_izi_kunye.json``) kaydın ``src_line`` metni dosyada
    kalmadı ve ``test_d23_bekci_cevirisi_a1.py::...::
    test_tasinmis_capa_sayisi_buyumuyor`` 14 -> 15 ile kırmızıya döndü.
    ÖLÇÜLDÜ: taban ağacında taşınmış = 14, bende = 15, **fark tek kayıt**.

    Tavan BÜYÜTÜLMEDİ (ÖK-22 / D26 dersi 8): bekçinin kendi hata
    metninin dediği yapıldı ve o TEK kayıt tazelendi (``line`` 106 -> 129,
    ``src_line`` yeni çıpa satırı, ``expected_src``/``expected_val``
    türetilmiş değere çekildi). Bu düğüm tazelemenin ayakta kaldığını
    mandallar: kayıt dosyada bulunmalı ve yerel ``#`` künyesi olmalı.
    """

    KAYIT_TESTFN = 'test_helium_isothermal_hand_calc'

    def _kayit(self):
        import json
        kok = pathlib.Path(__file__).resolve().parents[1]
        ham = json.loads((kanit_gerekli(kok / 'docs' / 'scofield' / 'raw' / 'P13'
                          / 'parmak_izi_kunye.json')).read_text(
                              encoding='utf-8'))
        adaylar = [k for k in ham if k['testfn'] == self.KAYIT_TESTFN]
        assert len(adaylar) == 1, adaylar
        return kok, adaylar[0]

    def test_tazelenen_kayit_dosyada_BULUNUYOR(self):
        kok, kayit = self._kayit()
        satirlar = (kok / kayit['file']).read_text(
            encoding='utf-8').splitlines()
        hedef = kayit['src_line'].strip()
        assert any(s.strip() == hedef for s in satirlar), (
            'envanter kaydı yine taşındı: %s' % hedef)

    def test_tazelenen_kayitin_YEREL_kunyesi_var(self):
        """Ölçütün kendisi: çapanın 3 satırlık penceresinde ``#`` künye."""
        import re as _re
        kok, kayit = self._kayit()
        satirlar = (kok / kayit['file']).read_text(
            encoding='utf-8').splitlines()
        hedef = kayit['src_line'].strip()
        i = [j for j, s in enumerate(satirlar) if s.strip() == hedef][0]
        pencere = '\n'.join(satirlar[max(0, i - 2):i + 1])
        assert _re.search(r'#\s*\S', pencere), (
            'tazelenen çapa künyesizleşti — yerelsiz sayısı büyür')
