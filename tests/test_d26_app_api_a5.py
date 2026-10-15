# -*- coding: utf-8 -*-
"""ÖH D26 / app-api aşama-5 bekçileri.

Kalemler:

* **P15B2-02** (yüksek, *bekçi-kırmızı*) — ``_mm_to_m`` adında İKİ tanım
  vardı ve aynı girdiye farklı karar veriyorlardı. Borç imi
  ``tests/test_flight_vehicle.py::test_ikiz_mm_to_m_ayni_sozlesmeyi_tasir``
  üstündeki ``xfail(strict=True)`` idi; bu aşamada kusur giderildi ve im
  kaldırıldı. Buradaki bekçiler ikizin bir daha AYRIŞMASINI değil,
  ayrışmanın MÜMKÜN OLMASINI (yani iki ayrı gövdenin yeniden yazılmasını)
  engeller.
* **P15B2-01** (orta) — fail-closed merkezin kapsamı. Bu aşamada mm→m
  ailesi merkeze bağlandı; bekçi durum adlarının merkezden GELDİĞİNİ
  (kopyalanmadığını) kilitler.
* **H1-Y3** (orta) — ``/calculate`` ``wall_thickness: 1`` → ``verdict:
  issued`` ama hükmün SONUCU söylenmiyordu (SF 0,5652 = hazne taşımıyor).
* **H1-Y4** (orta) — ``regression_a`` negatifken gerekçenin yanlış alanı
  suçladığı iddiası; bu tabanda ÖLÇÜMLE ÇÜRÜTÜLDÜ, bekçi geri gelmesini
  engeller.

Ölçüm ve kanıt: ``docs/scofield/raw/OH/D26/app-api/a5/``.
"""

import ast
import inspect
import os

import pytest

from hrma import app as A
from hrma.analysis import flight_vehicle as FV
from hrma.utils import input_guard


# ---------------------------------------------------------------------------
# Ortak yük — /calculate koşumları pahalıdır, modül başına bir kez alınır.
# ---------------------------------------------------------------------------
_HIBRIT = {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
           'chamber_pressure': 20.0, 'fuel_type': 'htpb',
           'oxidizer_type': 'n2o'}


@pytest.fixture(scope='module')
def istemci():
    A.app.config['TESTING'] = True
    return A.app.test_client()


@pytest.fixture(scope='module')
def yanit_cidar_1(istemci):
    """``wall_thickness = 1`` (mm) — H1-Y3'ün ölçtüğü tam gövde."""
    yuk = dict(_HIBRIT)
    yuk['wall_thickness'] = 1
    cevap = istemci.post('/calculate', json=yuk)
    assert cevap.status_code == 200, cevap.status_code
    return cevap.get_json()


# ===========================================================================
# P15B2-02 — İKİZ ``_mm_to_m`` SÖZLEŞMESİ TEK KAYNAKTAN
# ===========================================================================

#: Ayrışmayı ölçen girdi kümesi. ``5.0`` bilerek YOKTUR: app kolunun
#: varsayılanı 0,005 m olduğu için geçerli bir çevrim "reddedildi" sanılırdı.
_GIRDILER = [123.0, '250', 0.0, -5.0, -120.0, None, '', 'abc',
             float('nan'), float('inf'), True, False, [1, 2]]


def test_ikiz_mm_to_m_tek_karar_noktasindan_gecer():
    """İki ``_mm_to_m`` tanımı da merkezî kararı AYNEN taşımalı.

    Ölçülen kusur (taban 7751531): ``-120`` mm girdisi app kolunda
    reddedilirken (varsayılana düşer) flight_vehicle kolunda ``-0,12`` m
    olarak KABUL ediliyordu; 13 girdinin 3'ünde karar ayrışıyordu.
    """
    ayrisan = []
    for g in _GIRDILER:
        merkez_m, merkez_durum = input_guard.mm_to_m_read(g)
        fv_m = FV._mm_to_m(g)
        app_m, app_durum = A._mm_to_m_read(g)
        if fv_m != merkez_m and not (fv_m is None and merkez_m is None):
            ayrisan.append(('flight_vehicle', g, fv_m, merkez_m))
        if app_m != merkez_m and not (app_m is None and merkez_m is None):
            ayrisan.append(('app', g, app_m, merkez_m))
        if app_durum != merkez_durum:
            ayrisan.append(('app-durum', g, app_durum, merkez_durum))
    assert not ayrisan, 'merkezden ayrışan kararlar: %r' % (ayrisan,)


def test_negatif_ve_sifir_milimetre_iki_tarafta_da_reddedilir():
    """Bir kalınlık/boy negatif ya da sıfır olamaz — iki kolda da ölçü değildir."""
    for g in (0.0, -5.0, -120.0, 0, -1):
        assert FV._mm_to_m(g) is None, (
            'flight_vehicle._mm_to_m(%r) fiziksel olmayan ölçüyü geçirdi' % g)
        metre, durum = A._mm_to_m_read(g)
        assert metre is None and durum == input_guard.MM_NOT_POSITIVE, (
            'app._mm_to_m_read(%r) -> %r/%r' % (g, metre, durum))


def _tek_donusluk_govde_mu(fn, aranan):
    """Gövde TEK ``return`` mü ve içinde ``aranan`` adı geçiyor mu?

    "Tek kaynak" iddiası ancak gövde merkeze DEVREDİYORSA doğrudur; ikinci
    bir ``if`` zinciri yazıldığı anda sözleşme yeniden ayrışabilir.
    """
    agac = ast.parse(inspect.getsource(fn).lstrip())
    tanim = agac.body[0]
    govde = [d for d in tanim.body if not isinstance(d, ast.Expr)]
    if len(govde) != 1 or not isinstance(govde[0], ast.Return):
        return False
    return aranan in ast.dump(govde[0])


def test_iki_taraf_da_kendi_govdesini_yazmaz():
    """İkiz sözleşme yalnız merkeze DEVREDİLDİĞİ sürece tek kalır."""
    assert _tek_donusluk_govde_mu(A._mm_to_m_read, 'mm_to_m_read'), (
        'hrma/app.py:_mm_to_m_read merkeze devretmiyor — ikinci bir mm→m '
        'sözleşmesi yazılmış olabilir (defter P15B2-02)')
    assert _tek_donusluk_govde_mu(FV._mm_to_m, 'mm_to_m_read'), (
        'hrma/analysis/flight_vehicle.py:_mm_to_m merkeze devretmiyor '
        '(defter P15B2-02)')


def test_hrma_icinde_ucuncu_bir_mm_to_m_govdesi_yok():
    """Depoda mm→m kararını KENDİ yazan üçüncü bir tanım belirmesin."""
    kok = os.path.dirname(os.path.dirname(os.path.abspath(A.__file__)))
    suphe = []
    for dizin, _alt, dosyalar in os.walk(os.path.join(kok, 'hrma')):
        if '__pycache__' in dizin:
            continue
        for ad in sorted(dosyalar):
            if not ad.endswith('.py'):
                continue
            yol = os.path.join(dizin, ad)
            try:
                agac = ast.parse(open(yol, encoding='utf-8').read())
            except SyntaxError:                      # pragma: no cover
                continue
            for dugum in ast.walk(agac):
                if not isinstance(dugum, ast.FunctionDef):
                    continue
                if not dugum.name.startswith('_mm_to_m'):
                    continue
                govde = ast.dump(ast.Module(body=dugum.body, type_ignores=[]))
                if 'mm_to_m_read' not in govde:
                    suphe.append('%s:%d:%s' % (
                        os.path.relpath(yol, kok), dugum.lineno, dugum.name))
    assert not suphe, (
        'merkeze bağlı OLMAYAN mm→m tanımı: %r (defter P15B2-02 — karar '
        'hrma/utils/input_guard.mm_to_m_read içindedir)' % (suphe,))


# ===========================================================================
# P15B2-01 — FAIL-CLOSED MERKEZİN KAPSAMI
# ===========================================================================

def test_cidar_durum_adlari_merkezden_gelir():
    """``WALL_INPUT_*`` adları merkezin adlarıdır; ikinci kez YAZILMAZ."""
    esler = [
        ('WALL_INPUT_NOT_SUPPLIED', 'MM_NOT_SUPPLIED'),
        ('WALL_INPUT_OK', 'MM_OK'),
        ('WALL_INPUT_UNREADABLE', 'MM_UNREADABLE'),
        ('WALL_INPUT_NOT_POSITIVE', 'MM_NOT_POSITIVE'),
        ('WALL_INPUT_NOT_FINITE', 'MM_NOT_FINITE'),
    ]
    for app_ad, merkez_ad in esler:
        assert getattr(A, app_ad) == getattr(input_guard, merkez_ad)

    # Değer eşitliği yetmez: dize kopyası da eşit olurdu. Kaynakta atamanın
    # SAĞ tarafı merkezden okumalı.
    kaynak = open(inspect.getsourcefile(A), encoding='utf-8').read()
    agac = ast.parse(kaynak)
    atamalar = {}
    for dugum in agac.body:
        if isinstance(dugum, ast.Assign) and len(dugum.targets) == 1 \
                and isinstance(dugum.targets[0], ast.Name) \
                and dugum.targets[0].id.startswith('WALL_INPUT_'):
            atamalar[dugum.targets[0].id] = ast.dump(dugum.value)
    for app_ad, merkez_ad in esler:
        assert app_ad in atamalar, '%s modül seviyesinde tanımlı değil' % app_ad
        assert merkez_ad in atamalar[app_ad], (
            '%s merkezden okunmuyor, dize kopyası yazılmış (ÖK-04): %s'
            % (app_ad, atamalar[app_ad]))


def test_merkez_bool_ve_sonsuzu_reddeder():
    """Merkez kural ``input_guard.num`` ile aynı olmalı (üç kader tek kader)."""
    assert input_guard.mm_to_m_read(True) == (None, input_guard.MM_UNREADABLE)
    assert input_guard.mm_to_m_read(False) == (None, input_guard.MM_UNREADABLE)
    assert input_guard.mm_to_m_read([1, 2]) == (None,
                                                input_guard.MM_UNREADABLE)
    assert input_guard.mm_to_m_read(float('inf')) == (
        None, input_guard.MM_NOT_FINITE)
    assert input_guard.mm_to_m_read('5,0') == (None,
                                               input_guard.MM_UNREADABLE)
    assert input_guard.mm_to_m_read(250) == (0.25, input_guard.MM_OK)


# ===========================================================================
# H1-Y3 — VERİLEN HÜKÜM SONUCUNU SÖYLER
# ===========================================================================

def test_verilen_hukum_sonucunu_soyler(yanit_cidar_1):
    """``verdict: issued`` tek başına yayımlanamaz: sonucu da yazılmalı.

    Ölçülen kusur (taban 7751531): ``wall_thickness: 1`` gövdesinde
    ``structural_design_basis`` "this result is a verification" diyordu ve
    hükmün ne olduğunu söyleyen 0 yaprak taşıyordu; aynı yanıtın modülü
    ``status = UNSAFE`` / ``verdict_safety_factor = 0,5652`` diyordu.

    V3 yapi-sf 3. tur Ş2-2 — ÇEVİRİ (karar §28-37 seçenek (a); karar §28-24
    (C); dört koşul). Eski beklenti: hibrit 1 mm'de ``verdict == 'issued'``.
    (C) ile hibrit kamara, yapısal modelin geçerlilik sınırı dışında
    değerlendiriliyor (iç yüz ≈ 3221 K; steel_4130 erime 1705 K) ve oradan
    sayısal tasarım hükmü verilmiyor; dolayısıyla:
    (1) GEÇERLİLİK DIŞI (bu gövde): ``verdict == 'withheld'`` + gerekçe kodu,
        geri çekilen hükme sonuç YAMANMAZ, modülün UNSAFE uyarısı korunur.
        Kâhin: malzeme kaydı (erime/eğri sonu) ⟷ yayımlanan cidar sıcaklığı.
    (2) GEÇERLİLİK İÇİ (600/590 K, kullanıcı cidarı): H1-Y3 sözleşmesi
        AYNEN — verilen hüküm sonucunu söyler. Beyan, ``/calculate``'in
        kullandığı ``_motor_structural_design_basis`` ile gerçek yapısal
        modül sonucundan kurulur. Kâhin: malzeme kaydı (eğri içi).
    """
    from hrma.analysis.structural_analysis import (
        STRUCTURAL_MODEL_VALIDITY_WITHHELD_REASON)
    from tests.test_v3_yapi_sf import (
        DOGRULAMA_MALZEMESI, TEHLIKELI_CIDAR_M, gecerlilik_ici_dogrulama,
        malzeme_kaydina_gore_gecerlilik_disi)

    # (1) Geçerlilik dışı: hüküm geri çekilir, uyarı susturulmaz.
    yapisal = yanit_cidar_1['motor']['structural_analysis']
    assert malzeme_kaydina_gore_gecerlilik_disi(yapisal) is True
    beyan = yanit_cidar_1['structural_design_basis']
    assert beyan['verdict'] == 'withheld', beyan['verdict']
    assert STRUCTURAL_MODEL_VALIDITY_WITHHELD_REASON in beyan[
        'verdict_withheld_reasons'], beyan['verdict_withheld_reasons']
    assert 'verdict_outcome' not in beyan, (
        'geri çekilen hükme sonuç yamanmış: %r' % (beyan.get('verdict_outcome'),))
    assert yapisal['safety_analysis']['status'] == 'UNSAFE', (
        'geçerlilik dışı vakada uyarı susturuldu')

    # (2) Geçerlilik içi: verilen hüküm sonucunu söyler (H1-Y3 aynen).
    sonuc = gecerlilik_ici_dogrulama(TEHLIKELI_CIDAR_M)
    assert malzeme_kaydina_gore_gecerlilik_disi(sonuc) is False
    beyan = A._motor_structural_design_basis(
        {'structural_analysis': sonuc}, TEHLIKELI_CIDAR_M,
        DOGRULAMA_MALZEMESI)
    assert beyan['verdict'] == 'issued', beyan['verdict']
    modul = sonuc['safety_analysis']

    assert beyan.get('verdict_outcome') == modul.get('status')
    assert beyan.get('verdict_risk_level') == modul.get('risk_level')
    assert beyan.get('verdict_safety_factor') == modul.get(
        'verdict_safety_factor')
    assert beyan.get('verdict_outcome_source'), (
        'sonucun NEREDEN geldiği yazılmamış')
    assert str(beyan['verdict_outcome']) in (beyan.get('message') or ''), (
        'künye metni hükmün sonucunu söylemiyor: %r' % (beyan.get('message'),))


def test_tehlikeli_cidar_hukum_metninde_gorunur(yanit_cidar_1):
    """1 mm cidarın taşımadığı, beyan bloğunun KENDİSİNDEN okunabilmeli.

    V3 yapi-sf 3. tur Ş2-2 — ÇEVİRİ (karar §28-37 seçenek (a); dört koşul).
    Eski beklenti: hibrit 1 mm'de beyan ``verdict_safety_factor`` 0,5652 < 1
    ve ``verdict_outcome == 'UNSAFE'``. (C) ile geçerlilik dışı hibritte
    SAYISAL hüküm yok (sayı tanı amaçlı modülde kalır), tehlike ise modülün
    UNSAFE durumu ve hüküm gerekçesiyle görünür kalır. Tehlikeli cidarın
    beyan bloğundan okunması GEÇERLİLİK İÇİ bir vakada sınanır. Kâhin: ince
    cidar basınç hoop'u P_d·r/t > malzeme kaydının düşürülmemiş akması ⇒
    SF < 1 (``basinc_hoop_akmayi_asar``).
    """
    from hrma.analysis.structural_analysis import MODEL_VALIDITY_VERDICT_BASIS
    from tests.test_v3_yapi_sf import (
        DOGRULAMA_MALZEMESI, TEHLIKELI_CIDAR_M, basinc_hoop_akmayi_asar,
        gecerlilik_ici_dogrulama)

    # (1) Geçerlilik dışı hibrit: sayısal hüküm yok, uyarı korunur.
    beyan = yanit_cidar_1['structural_design_basis']
    modul = yanit_cidar_1['motor']['structural_analysis']['safety_analysis']
    assert beyan.get('verdict_safety_factor') is None
    assert modul['verdict_safety_factor'] is None
    assert modul['status'] == 'UNSAFE', modul['status']
    assert modul['minimum_safety_factor_verdict_basis'] == (
        MODEL_VALIDITY_VERDICT_BASIS)

    # (2) Geçerlilik içi tehlikeli cidar: sonuç beyan bloğunda okunur.
    assert basinc_hoop_akmayi_asar(TEHLIKELI_CIDAR_M) is True
    beyan = A._motor_structural_design_basis(
        {'structural_analysis': gecerlilik_ici_dogrulama(TEHLIKELI_CIDAR_M)},
        TEHLIKELI_CIDAR_M, DOGRULAMA_MALZEMESI)
    sf = beyan.get('verdict_safety_factor')
    assert isinstance(sf, float) and sf < 1.0, (
        '%g m cidar için hüküm emniyet katsayısı %r — kâhin SF < 1'
        % (TEHLIKELI_CIDAR_M, sf))
    assert beyan.get('verdict_outcome') == 'UNSAFE', beyan.get('verdict_outcome')


def test_modul_sonuc_yayimlamazsa_hukum_geri_cekilir():
    """Taşınacak sonuç yoksa "issued" yayımlanmaz (fail-closed)."""
    beyan = {'verdict': 'issued', 'verdict_withheld_reasons': [],
             'message': 'x'}
    A._carry_structural_verdict_outcome(beyan, {'safety_analysis': {}})
    assert beyan['verdict'] == 'withheld'
    assert 'structural_outcome_not_published' in beyan[
        'verdict_withheld_reasons']
    assert beyan['verdict_outcome'] is None

    beyan2 = {'verdict': 'issued', 'verdict_withheld_reasons': [],
              'message': 'x'}
    A._carry_structural_verdict_outcome(beyan2, {})
    assert beyan2['verdict'] == 'withheld'


def test_geri_cekilmis_hukme_sonuc_yamanmaz():
    """``withheld`` bir hükme sonuç eklenmez (kazanılmamış hüküm süslenmez)."""
    beyan = {'verdict': 'withheld', 'verdict_withheld_reasons': ['x'],
             'message': 'y'}
    A._carry_structural_verdict_outcome(
        beyan, {'safety_analysis': {'status': 'SAFE'}})
    assert 'verdict_outcome' not in beyan
    assert beyan['message'] == 'y'


# ===========================================================================
# H1-Y4 — NEGATİF ``regression_a`` KENDİ ADIYLA REDDEDİLİR
# ===========================================================================

@pytest.mark.parametrize('deger,gerekce', [
    (-3.68e-5, 'must_be_positive'),
    (0.0, 'must_be_positive'),
    (float('nan'), 'not_finite'),
])
def test_negatif_regresyon_katsayisi_kendi_adiyla_reddedilir(
        istemci, deger, gerekce):
    """Ret gerekçesi SUÇLU ALANI adıyla söylemeli (H1-Y4).

    Hakemin ölçtüğü hâlde (``05bc4ae``) gerekçe *"Missing required inputs:
    chamber_length"* diyordu — kullanıcı ``regression_a`` göndermişken.
    Bu tabanda kalem çürütüldü; bekçi eski davranışın geri gelmesini
    engeller.
    """
    yuk = dict(_HIBRIT)
    yuk['regression_a'] = deger
    cevap = istemci.post('/calculate', json=yuk)
    assert cevap.status_code == 400, cevap.status_code
    govde = cevap.get_json() or {}
    alanlar = govde.get('invalid_fields') or []
    adlar = [x.get('field') for x in alanlar]
    assert 'regression_a' in adlar, (
        'ret gerekçesi suçlu alanı adıyla söylemiyor: %r' % (govde,))
    kayit = [x for x in alanlar if x.get('field') == 'regression_a'][0]
    assert kayit.get('reason') == gerekce, kayit
    metin = ' '.join(govde.get('details') or [])
    assert 'regression_a' in metin, metin
    assert 'chamber_length' not in metin, (
        'gerekçe yanlış alanı suçluyor (H1-Y4): %r' % metin)
