# -*- coding: utf-8 -*-
"""ÖH Dalga-27 — katı kulvarı, aşama 2 bekçileri.

Kapsanan kalemler (ölçüm: ``docs/scofield/raw/OH/D27/kati/a2/{once,sonra}.json``,
ters-mutasyon: aynı dizinde ``mutasyon.json``):

* **OH-D26-15** — ``SolidRocketEngine._estimate_throat_diameter`` boğaz alanı
  sıfır/negatif çıktığında sessizce 0,015 m (15 mm) döndürüyordu. Çözücünün
  "boyutlandıramadım" hükmünün üstüne yazılan bu sayıyı aynı dosyada 11 çağrı
  yeri okuyor; aralarında imalata giden ``cad_design.nozzle_design.
  throat_diameter`` de var. OH-D25-10 (sessiz 1-500 mm kelepçesi) kardeşidir.
* **P13B4-03** (bekçi-kırmızı, borç imi kalktı) — ``QSHODBandRecord``ın künye
  zarfı (``record_id`` / ``record_confidence`` / ``record_confidence_note`` /
  ``retrieved``) bandı ÇAĞIRAN verdiğinde yayımlanan gövdeye hiç girmiyordu.
* **OH-D26-06** — ``/calculate_solid`` ``defaults_applied`` düz ad listesi
  yayımlıyordu; kardeş ``/calculate_liquid`` ÖK-19 künye sözlüğü. Düz listede
  UYGULANAN SAYI hiç yayımlanmıyordu.

Bekçilerin altın değerleri üründen İTHAL EDİLMEZ: kural ya bağımsız
hesaplanır (boğaz çapı ``_design_throat_area``dan yeniden kurulur) ya da iki
katmanın birbirine eşitliği çakılır (künye ⟷ kaydın kendi ``as_dict``i).
"""
import ast
import contextlib
import io
import pathlib

import numpy as np
import pytest

from hrma.engines.solid_rocket_engine import (
    SolidGeometryError,
    SolidRocketEngine,
)
from hrma.stability import bands as bands_mod

KOK = pathlib.Path(__file__).resolve().parents[1]
MOTOR_KAYNAK = KOK / 'hrma' / 'engines' / 'solid_rocket_engine.py'
APP_KAYNAK = KOK / 'hrma' / 'app.py'
FAZB_BEKCI = KOK / 'tests' / 'test_fazb_serilestirici_esligi.py'

#: Sağlıklı referans gövde — üç kalemde de "bozulmadı" çapası budur.
# V301/K-A (22 Eki): eski çapa A_p/A_t = 0,947'lik boğulan portlu varsayılan motoru kilitliyordu.
# Çekirdek örnek motorun TEK tanımından (30 -> 48 mm).
from hrma.engines.solid_rocket_engine import (  # noqa: E402
    SOLID_DEFAULT_GEOMETRY_MM as _KA_GEOMETRI)
SAGLAM = dict(chamber_diameter=100, grain_length=500,
              core_diameter=_KA_GEOMETRI['core_diameter'],
              chamber_pressure=40)


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


def _motor(**ov):
    kur = dict(SAGLAM)
    kur.update(ov)
    return SolidRocketEngine(**kur)


def _fonksiyon_dugumu(agac, ad):
    bulunan = [d for d in ast.walk(agac)
               if isinstance(d, ast.FunctionDef) and d.name == ad]
    assert len(bulunan) == 1, f'{ad!r} kaynakta {len(bulunan)} kez tanımlı'
    return bulunan[0]


@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


# ===========================================================================
# OH-D26-15 — A_t <= 0 sessiz 15 mm yedeği
# ===========================================================================
class TestOHD2615BogazYedegiSokuldu:
    """Boyutlandırılamayan boğaz ADIYLA reddedilir (Doktrin 1)."""

    def _sifir_alanli_motorlar(self):
        """A_t = 0 üreten ÜÇ bağımsız yol (biri bile kalsa kusur sürüyor).

        Üçü de ``_design_throat_detail_uncached``ın ``bos`` dalına girer:
        ikisi ``en_iyi_alan <= 0`` (A_gerek her örnekte sıfır), biri boş web
        taraması (``w_max <= 0``). Yollar bilerek AYRI kökten seçildi —
        tek bir kurgunun tesadüfi sonucu olmadığı görünsün.
        """
        motorlar = {}
        for ad, alan in (('c_star_sifir', 'c_star'), ('rho_p_sifir', 'rho_p')):
            eng = _motor()
            setattr(eng, alan, 0.0)
            eng._design_throat_memo = None
            motorlar[ad] = eng
        eng = _motor(grain_type='end_burner')
        eng.L_grain = 0.0
        eng._burn_area_scan_memo = None
        eng._design_throat_memo = None
        motorlar['bos_web_taramasi'] = eng
        return motorlar

    def test_on_kosul_cozucu_gercekten_boyutlandiramiyor(self):
        """Boş-geçme koruması: kusurun ön koşulu bu koşumda VAR mı?"""
        for ad, eng in self._sifir_alanli_motorlar().items():
            A_t, _ = _sessiz(eng._design_throat_area)
            assert float(A_t) == 0.0, (
                f'{ad}: çözücü sıfır alan üretmiyor, bekçi vakumda koşuyor '
                f'(A_t = {A_t!r})')

    def test_sessiz_yedek_yerine_adiyla_ret(self):
        """0,015 m sessizce dönmüyor; ret alan ADIYLA ve gerekçeyle geliyor."""
        for ad, eng in self._sifir_alanli_motorlar().items():
            with pytest.raises(SolidGeometryError) as tutulan:
                _sessiz(eng._estimate_throat_diameter)
            kunye = tutulan.value.kunye
            assert kunye['field'] == 'throat_area', ad
            assert kunye['reason'] == 'throat_not_sizable', ad
            assert kunye['motor_form'] == 'solid', ad
            assert kunye['unit'] == 'm^2', ad
            # Ret metni SAYI UYDURMADIĞINI da söylemeli (beyan ≠ çözüm
            # değil; burada beyan REDDİN kendisidir).
            assert 'fallback' in str(tutulan.value).lower(), ad

    def test_uydurma_capi_hicbir_tuketici_gormuyor(self):
        """15 mm'lik yedek artık HİÇBİR yayımlanan sayıya dönüşemiyor.

        Kusurun zararı dönüş değerinde değil, onu okuyan 11 çağrı yerinde
        idi: ``_throat_exceeds_case`` kapısı da o çağrılardan biridir ve
        eskiden uydurma çapla "gövdeye sığıyor" hükmü veriyordu.
        """
        for ad, eng in self._sifir_alanli_motorlar().items():
            with pytest.raises(SolidGeometryError):
                _sessiz(eng._throat_exceeds_case)

    def test_ciplak_sayisal_donus_kaynaktan_kalkti(self):
        """AST: metodun gövdesinde çıplak sayısal ``return`` yok."""
        agac = ast.parse(MOTOR_KAYNAK.read_text(encoding='utf-8'))
        govde = _fonksiyon_dugumu(agac, '_estimate_throat_diameter')
        ciplak = [(d.lineno, d.value.value) for d in ast.walk(govde)
                  if isinstance(d, ast.Return)
                  and isinstance(d.value, ast.Constant)
                  and isinstance(d.value.value, (int, float))
                  and not isinstance(d.value.value, bool)]
        assert not ciplak, (
            f'sessiz sayısal yedek geri kondu: {ciplak}')
        assert any(isinstance(d, ast.Raise) for d in ast.walk(govde)), (
            'çözülemeyen boğaz için ret yolu yok — fail-closed kapı düştü')

    def test_saglikli_motor_capi_DEGISMEDI(self):
        """Çapa: sağlıklı gövdede çap çözücünün alanından birebir kurulur."""
        eng = _motor()
        A_t, _ = _sessiz(eng._design_throat_area)
        cd = getattr(eng, 'discharge_coeff', 1.0)
        A_geom = A_t / cd if 0.0 < cd < 1.0 else A_t
        beklenen = 2.0 * float(np.sqrt(A_geom / np.pi))
        assert beklenen > 0.0, 'referans gövde sıfır alan veriyor'
        assert float(_sessiz(eng._estimate_throat_diameter)) == pytest.approx(
            beklenen, rel=1e-12)


# ===========================================================================
# P13B4-03 — kayıt künyesi ÇAĞIRAN bandı yolunda da yayımlanır
# ===========================================================================
class TestP13B403KayitKunyesi:

    def _kayit(self):
        dolu = sorted(
            (k for k in bands_mod.QSHOD_BAND_RECORDS.values()
             if isinstance(k, bands_mod.QSHODBandRecord)),
            key=lambda k: k.record_id)
        assert dolu, 'bands.QSHOD_BAND_RECORDS içinde dolu kayıt kalmamış'
        return dolu[0]

    def _blok(self, band):
        motor = object.__new__(SolidRocketEngine)
        motor.combustion_response_band = band
        motor.propellant_thermal_diffusivity_m2_s = 1.5e-7
        motor.rho_p = 1750.0
        motor.T_c = 295.0
        motor.P_c = 50.0
        akustik = {'modes': [{'label': 'L1', 'frequency_hz': 500.0,
                              'indices': {'tangential_m': 0, 'radial_n': 0,
                                          'longitudinal_q': 1}}]}
        egri = {'burn_area': [0.5, 0.4], 'mass_flow': [4.375, 4.0]}
        return _sessiz(motor._qshod_band_block, akustik, egri)

    def test_cagiran_bandi_verdiginde_kunye_yayimlaniyor(self):
        """Kaydın bandı elden verilse de künye zarfı gövdede duruyor."""
        kayit = self._kayit()
        blok = self._blok(kayit.band)
        assert blok['status'] == 'modelled', blok
        kaynak = blok['band_source']
        assert kaynak['status'] == 'caller_supplied', (
            'bu bekçi ÇAĞIRAN yolunu sınamalı; katalog yoluna düştü')
        assert 'record' in kaynak, (
            'çağıran yolunda kaydın künye zarfı yayımlanmıyor (P13B4-03)')
        # Değerler kaydın KENDİ serileştiricisiyle birebir eşit olmalı;
        # bekçi altın değeri elle yazmaz (bayatlama yasağı).
        assert kaynak['record'] == kayit.as_dict()
        for ad in ('record_id', 'record_confidence',
                   'record_confidence_note', 'retrieved'):
            assert kaynak['record'][ad] == kayit.as_dict()[ad], ad

    def test_eslesme_gerekcesi_beyan_ediliyor(self):
        """Künyenin NASIL iliştirildiği de yayımlanır (beyan boş değil)."""
        kayit = self._kayit()
        kaynak = self._blok(kayit.band)['band_source']
        gerekce = kaynak.get('record_match_basis') or ''
        assert len(gerekce) >= 60, (
            f'eşleşme beyanı yok/kısa: {gerekce!r}')
        assert 'identity' in gerekce.lower()

    def test_katalog_yolu_kunyeyi_KAYBETMEDI(self):
        """D22 (P6B4-08) ile bağlanan katalog yolu bozulmadı."""
        eng = _motor(propellant_type='apcp')
        band, kunye = _sessiz(eng._qshod_band_from_catalog)
        assert band is not None and kunye['status'] == 'resolved'
        for ad in ('record_id', 'record_confidence',
                   'record_confidence_note', 'retrieved'):
            assert ad in kunye['record'], ad

    def test_katalogda_olmayan_band_KUNYE_UYDURMUYOR(self):
        """Fail-closed: tabloya ait olmayan band künye zarfı taşımaz."""
        from hrma.stability.response import QSHODBand
        kayit = self._kayit()
        ham = kayit.band.as_dict()
        sentetik = QSHODBand(**{ad: ham[ad] for ad in QSHODBand.__slots__
                                if ad in ham})
        kaynak = self._blok(sentetik)['band_source']
        assert 'record' not in kaynak, (
            'katalog kaydı OLMAYAN banda künye iliştirilmiş — uydurma künye '
            'kaynaksız sayıdan beter (kullanıcı güven derecesini yanlış '
            'kayda bağlar)')
        assert 'record_match_basis' not in kaynak

    def test_eslesme_DEGERLE_degil_kimlikle_kuruluyor(self):
        """Sayısal olarak eşit ama BAŞKA bir band, kaydın künyesini almaz.

        Bu, bir öncekinin daha keskin hâlidir: sentetik band kaydın
        değerlerinin AYNISINI taşır. Eşleşme değer benzerliğine kaysaydı
        bu koşum yanlış künye yayımlardı.
        """
        from hrma.stability.response import QSHODBand
        kayit = self._kayit()
        ham = kayit.band.as_dict()
        ikiz = QSHODBand(**{ad: ham[ad] for ad in QSHODBand.__slots__
                            if ad in ham})
        assert ikiz.as_dict() == ham, 'ikiz band kaydın değerlerini taşımıyor'
        assert ikiz is not kayit.band
        assert SolidRocketEngine._qshod_record_for_band(ikiz) is None
        assert SolidRocketEngine._qshod_record_for_band(kayit.band) is kayit

    def test_borc_imleri_KALKTI(self):
        """P13B4-03'ün iki xfail(strict) borç imi kaynakta kalmadı."""
        metin = FAZB_BEKCI.read_text(encoding='utf-8')
        assert 'ÖH defter P13B4-03' not in metin, (
            'P13B4-03 borç imi hâlâ duruyor; ürün onarıldıysa im XPASS '
            'üretir ve süiti kırar')


# ===========================================================================
# OH-D26-06 — /calculate_solid defaults_applied künye biçimi
# ===========================================================================
#: ÖK-19 künye sözlüğünün alanları — sıvı ucun YAYIMLADIĞI kümeden
#: ölçülerek doğrulanır (elle liste değil; aşağıdaki eşitlik iddiası).
OK19_KUNYE_ALANLARI = {'field', 'value', 'reason', 'applied_by', 'message'}


class TestOHD2606VarsayilanKunyesi:

    def _ogretici(self, istemci, uc):
        r = _sessiz(istemci.post, uc, json={'use_tutorial_defaults': True})
        assert r.status_code == 200, (uc, r.status_code)
        return r.get_json() or {}

    def test_kati_uc_kunye_SOZLUGU_yayimliyor(self, istemci):
        """Düz ad listesi bitti: her öğe alan + DEĞER + gerekçe taşıyor.

        ÖH D37 A1a uc-kapi (OH-D32-02 kanonik künye; ana model kararı,
        rapor ``docs/scofield/raw/OH/A1a/uc-kapi/a1/rapor.md`` §1.5) —
        BEKÇİ ÇEVRİLDİ, gerekçesi: eski ölçü öğretici kipte HER künyenin
        ``reason == 'tutorial_default'`` olmasıydı; bu, öğretici tablonun
        DIŞINDAKİ alanların (motor kurucusunda okunan yedi çift-katman
        alanı) sessizliğine dayanıyordu. Kanonik künye o alanları ADIYLA
        ``endpoint_default`` diye sayıyor — öğretici senaryo girdisi
        DEĞİLLER. Künye gerekçesi artık ALANA bağlıdır: öğretici tablodaki
        alan ``tutorial_default``, kanonik tablodaki alan
        ``endpoint_default``; iki tablonun dışında künye YOK. Korunan niyet
        (sözlük biçimi, değer, ``applied_by``) aynen ölçülür.
        """
        from hrma.app import (SOLID_ENDPOINT_DEFAULTS,
                              _KATI_KANONIK_VARSAYILAN_OKUYUCULARI)
        ogretici_alanlari = set(SOLID_ENDPOINT_DEFAULTS)
        kanonik_alanlari = set(_KATI_KANONIK_VARSAYILAN_OKUYUCULARI)
        assert not ogretici_alanlari & kanonik_alanlari, (
            'bir alan iki tabloda birden: künye gerekçesi belirsiz — '
            f'{sorted(ogretici_alanlari & kanonik_alanlari)}')
        govde = self._ogretici(istemci, '/calculate_solid')
        uygulanan = govde['defaults_applied']
        assert uygulanan, 'öğretici kipte varsayılan beyan edilmiyor'
        assert all(isinstance(x, dict) for x in uygulanan), (
            f'katı uç hâlâ düz ad listesi yayımlıyor: {uygulanan}')
        gerekce = {}
        for kunye in uygulanan:
            assert set(kunye) == OK19_KUNYE_ALANLARI, kunye
            if kunye['field'] in ogretici_alanlari:
                assert kunye['reason'] == 'tutorial_default', kunye
            else:
                assert kunye['field'] in kanonik_alanlari, (
                    f"{kunye['field']}: öğretici de kanonik de olmayan alan "
                    'künyede')
                assert kunye['reason'] == 'endpoint_default', kunye
            gerekce[kunye['field']] = kunye['reason']
            assert kunye['applied_by'] == 'calculate_solid endpoint'
            assert kunye['value'] is not None, (
                f"{kunye['field']}: künye 'varsayılan uygulandı' diyor ama "
                'UYGULANAN SAYIYI söylemiyor')
        assert 'tutorial_default' in gerekce.values(), (
            'öğretici kipte öğretici senaryo girdisi beyan edilmiyor: '
            f'{gerekce}')

    def test_iki_ucta_AYNI_bicim(self, istemci):
        """Biçim birliği ölçülür: katı ⟷ sıvı künye alan kümeleri eşit."""
        kati = self._ogretici(istemci, '/calculate_solid')['defaults_applied']
        sivi = self._ogretici(istemci,
                              '/calculate_liquid')['defaults_applied']
        assert {tuple(sorted(k)) for k in kati} == {
            tuple(sorted(k)) for k in sivi}, (
            'iki uç aynı adı iki biçimde yayımlıyor — beyanı okuyan her '
            'tüketici uca göre dallanmak zorunda kalır')

    def test_kunye_degeri_COZUCUYE_GIDEN_sayidir(self, istemci):
        """Beyan ile gerçek örtüşür: künyedeki değer motorun gördüğü değer.

        (ÖH Z5S dersi: "varsayılan uygulandı" diyen künyenin çözücüye
        BAŞKA bir sayı göndermesi, beyanın kendisini yalana çevirir.)
        """
        govde = self._ogretici(istemci, '/calculate_solid')
        kunye = {k['field']: k['value'] for k in govde['defaults_applied']}
        assert 'chamber_diameter' in kunye, kunye
        sonuc = govde.get('results', govde)
        yayimlanan = (sonuc.get('chamber_diameter_mm')
                      or sonuc.get('motor_geometry', {}).get(
                          'chamber_diameter_mm'))
        if yayimlanan is not None:
            assert float(yayimlanan) == pytest.approx(
                float(kunye['chamber_diameter']), rel=1e-9), (
                'künye bir sayı diyor, yayımlanan geometri başka bir sayı')

    def test_varsayilan_YOKSA_alan_hic_yazilmiyor(self, istemci):
        """Çapa: beyan, GERÇEKTEN gönderilmeyen alanla sınırlı kalır.

        ÖH D31 / P12bB2-06 (ÖK-21 uç ayağı) — BEKÇİ ÇEVRİLDİ, gerekçesi:
        eski sürüm ``'defaults_applied' not in govde`` diyordu ve yükü
        ``SAGLAM + propellant_type`` idi; o yük ``grain_type``ı HİÇ
        GÖNDERMİYOR, uç ise onu kendi varsayılanına (``'bates'``)
        düşürüyor. Yani bekçi, "gönderilmeyen alan sessizce dolar"
        kusurunun ta kendisini kilitliyordu (ÖK-05'in tersi). Ölçüm:
        ``docs/scofield/raw/OH/D31/app-api-uc/a1/once.json`` K2 —
        tam yükte ``defaults_applied`` yoktu ve sayfanın 70 ``|| SAYI``
        ikamesi sökülünce kullanıcı hangi sayının kendi verisi olmadığını
        yanıttan okuyamayacaktı.

        Bekçinin KORUNAN niyeti: gövde beyanla ŞİŞMEZ — beyan yalnız
        istekte GERÇEKTEN bulunmayan alanı anar, ve öğretici kolu
        tetiklenmez. Bu sürüm onu ilişki olarak ölçer.
        """
        istek = dict(SAGLAM, propellant_type='apcp')
        r = _sessiz(istemci.post, '/calculate_solid', json=istek)
        assert r.status_code == 200
        govde = r.get_json() or {}
        assert govde.get('input_source') != 'tutorial_defaults'
        for kunye in (govde.get('defaults_applied') or []):
            assert kunye['field'] not in istek, (
                kunye['field'] + ' istekte GELDIGI halde varsayilan '
                'uygulandi diye beyan edilmis')
            assert kunye['reason'] == 'endpoint_default'

    def test_kunye_TEK_kurucudan_geliyor(self):
        """AST: uç, künyeyi elle kurmuyor; tek kurucuyu çağırıyor."""
        agac = ast.parse(APP_KAYNAK.read_text(encoding='utf-8'))
        govde = _fonksiyon_dugumu(agac, 'calculate_solid')
        cagri = [d for d in ast.walk(govde)
                 if isinstance(d, ast.Call) and isinstance(d.func, ast.Name)
                 and d.func.id == '_tutorial_default_kunyeleri']
        # ÖH D31 / P12bB2-06 — BEKÇİ ÇEVRİLDİ, gerekçesi: ölçü SAYIYDI
        # (``len(cagri) == 1``), oysa kilitlenmek istenen şey TEK KURUCU
        # (uç künyeyi ELLE kurmasın). D31'de ikinci bir KOL doğdu
        # (öğretici kip ⟷ uç varsayılanı) ve ikisi de AYNI kurucuyu
        # çağırıyor; sayı ölçüsü doğru onarımı kırmızıya düşürüyordu.
        # Ölçü artık ilişkidir: en az bir çağrı VAR ve uç içinde künye
        # sözlüğü elle kurulmuyor.
        assert cagri, 'künye kurucusu /calculate_solid içinden hiç çağrılmıyor'
        _elle = [d for d in ast.walk(govde)
                 if isinstance(d, ast.Dict)
                 and {k.value for k in d.keys
                      if isinstance(k, ast.Constant)}
                 >= {'field', 'reason', 'applied_by'}]
        assert not _elle, (
            'uç, künye sözlüğünü elle kuruyor; tek kurucu ihlal edildi')
        # ...ve kurucu gerçekten modül düzeyinde tanımlı olmalı.
        _fonksiyon_dugumu(agac, '_tutorial_default_kunyeleri')


# ===========================================================================
# Bu dosyanın kendi dürüstlüğü
# ===========================================================================
def test_bu_dosyada_iddiasiz_test_yok():
    """ÖH OH-D23-01 kuralı: her test en az bir iddia taşır."""
    agac = ast.parse(pathlib.Path(__file__).read_text(encoding='utf-8'))
    iddiasiz = [d.name for d in ast.walk(agac)
                if isinstance(d, ast.FunctionDef)
                and d.name.startswith('test_')
                and not any(isinstance(x, (ast.Assert, ast.Raise))
                            for x in ast.walk(d))
                and not any(isinstance(x, ast.withitem)
                            for x in ast.walk(d))]
    assert not iddiasiz, f'iddiasız test(ler): {iddiasiz}'
