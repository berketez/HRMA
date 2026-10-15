"""ÖH Z5S / S2 — ÇIPLAK ``float()`` VE ``data[...]`` KÖKÜNÜN BEKÇİLERİ.

KAPATILAN SINIF
---------------
Alan düzeyindeki İSTEMCİ hatasının SUNUCU ARIZASINA (HTTP 500) çevrilmesi ve
yanıt gövdesine Python istisna metninin sızması. Hiçbiri sunucu arızası
değildi: bir sayı alanına ``null``, ``""``, ``"yirmi"``, ``[1]`` ya da ``true``
gelmişti.

ÖLÇÜM (27 Ağu 2026, S1-sonrası taban ``app.py`` md5
``91fc6eb1c4576555fce36969005a5ebb``; 44 vaka —
``docs/scofield/raw/OH/Z5S/s2/once_supurme.json`` ⟷ ``sonra_supurme.json``)::

    HTTP 500                          22  ->  0
    gövdede Python istisna metni      25  ->  0
    alan adı taşıyan 4xx               3  -> 26

Kök TEK bir kalıptı ve iki dalı vardı:

1. ``float(data.get(k, VARSAYILAN))`` — anahtar GÖNDERİLMİŞ ama değeri
   ``null``/``""`` ise ``data.get`` varsayılanı değil o ``null``'ı döndürür,
   ``float(None)`` patlar. Yani alan HİÇ gönderilmezse sağlıklı çalışan
   istek, alan BOŞ gönderilince 500 alıyordu. Bu bir ÜRÜN YOLUDUR:
   ``hrma/templates/advanced.html`` içindeki ``numById()`` boş form alanı
   için açıkça ``null`` gönderir.
2. ``data[k]`` — anahtar hiç yoksa çıplak ``KeyError``; gövdeye Python
   anahtar adı ve ``error_type: "KeyError"`` sızıyordu.

BU DOSYANIN KİLİTLEDİĞİ KALEMLER
--------------------------------
* **S1-06** (kök) — AST ölçümü: sahiplenilen sekiz uçta doğrudan
  ``data[...]`` indekslemesi 17 -> 9, çıplak ``float(...)`` çağrısı 28 -> 3
  (``once_ast.json`` ⟷ ``sonra_ast.json``). Kalan indekslemelerin hepsi bir
  ``if data.get(...) is not None`` kapısının ARDINDA; bekçi bunu ölçüyor.
* **P16B3-19** — ham 500 envanteri: ``/api/analysis/wall-profile``,
  ``/api/trajectory-analysis``, ``/api/flow-analysis``,
  ``/api/transient-analysis`` uçlarında 21 vakanın tamamı adlandırılmış 4xx.
  (Aynı envanterin ``/analyze_safety`` ve ``/analyze_thermal_safety``
  ayakları ÖLÇÜMDE ZATEN KAPALI çıktı — Z3/Z4'ün kapıları; bekçi bu
  kapalılığı da kilitler ki geri gitmesin.)
* **P16B1-50** — ``/calculate``: ``chamber_pressure`` anahtarı hiç
  gönderilmezse motor 20 bar ile TAM hesap yapıp enjektör kurulumunda
  ``{'error': "'chamber_pressure'", 'error_type': 'KeyError'}`` ile
  çöküyordu. Artık enjektör motorun KULLANDIĞI basıncı okur.
* **P7B1-11** — ``/api/transient-analysis``: ``tank_temperature``/
  ``liquid_fill_fraction`` açık ``null``.
* **P7B1-14** — ``/api/injector-design``: ``mdot_ox='iki'`` ->
  ``"'<=' not supported between instances of 'str' and 'int'"``.
* **P7B4-06** — ``/api/flow-analysis``: alanın YOKLUĞU ile AÇIK ``null``
  farklı davranıyordu (biri 200, diğeri 500).
* **P16B3-17** — ``null``/``""`` kapıyı "verilmedi" diye geçip varsayılana
  DÜŞMÜYORDU. Aynı kök; artık düşüyor ve düşüş BEYAN EDİLİYOR.

SÖZLEŞME (bekçilerin ölçtüğü üç şart)
-------------------------------------
a. HTTP sınıfı 4xx (5xx değil),
b. gövdede makine-okur ALAN ADI var,
c. gövdede Python istisna metni / tip adı / ``error_type`` YOK.

Ayrıca: geçersiz girdiye kapı konurken GEÇERLİ gövdenin yanıtı BİT-AYNI
kalmalı. Bu, ayrı bir kanıt zinciriyle ölçüldü
(``capa_bit_ayni.json``: S1-sonrası taban ters-değiştirmeyle yeniden kurulup
md5'i BİREBİR doğrulandı, sonra 14 çapa koşumu iki tabana karşı koşuldu —
1.535.583 karakterlik hibrit ``/calculate`` yanıtı dahil 14/14 bit-aynı) ve
bu dosyanın son sınıfı o çapanın YAŞAYAN kısmını taşır.
"""

import json

import pytest

from hrma.app import (
    _INJECTOR_NUMERIC_SPEC_FIELDS,
    _MISSING,
    _RequestFieldError,
    _flow_float,
    _request_number,
    app as flask_app,
)

# Python'un / NumPy'ın iç metinlerinin imzaları. Hiçbiri bir istemci
# hatasının gövdesinde görünmemeli.
PYTHON_SIZINTISI = (
    'float() argument',
    'int() argument',
    'could not convert string to float',
    'object has no attribute',
    'not supported between instances',
    'unsupported operand type',
    'Traceback',
    "'NoneType'",
    'ufunc ',
    'float division by zero',
)

# Yanıtın alanı ADLANDIRDIĞINI gösteren kanallar (biri yeterli).
ALAN_KANALLARI = ('invalid_fields', 'missing_fields', 'fields_involved',
                  'field', 'inputs_treated_as_absent')


@pytest.fixture(scope='module')
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        yield c


def _govde_metni(resp):
    return resp.get_data(as_text=True)


def _alan_adli(body):
    return isinstance(body, dict) and any(body.get(k) for k in ALAN_KANALLARI)


def _sozlesme(resp, *, beklenen_alan=None):
    """(a) 4xx, (b) alan adlı, (c) Python metni yok — üçünü birden ölçer."""
    metin = _govde_metni(resp)
    assert 400 <= resp.status_code < 500, (
        f'istemci hatası {resp.status_code} ile döndü (4xx olmalı); '
        f'gövde: {metin[:200]}')
    body = resp.get_json()
    assert isinstance(body, dict), f'gövde JSON sözlüğü değil: {metin[:200]}'
    assert _alan_adli(body), (
        f'yanıt hangi ALANIN sorunlu olduğunu söylemiyor: {metin[:300]}')
    for imza in PYTHON_SIZINTISI:
        assert imza not in metin, (
            f'gövdeye Python iç metni sızdı ({imza!r}): {metin[:300]}')
    assert 'error_type' not in body, (
        'yanıt Python istisna TİP ADINI yayımlıyor (error_type): '
        f'{metin[:300]}')
    if beklenen_alan is not None:
        assert beklenen_alan in metin, (
            f"sorunlu alan {beklenen_alan!r} yanıtta adlandırılmamış: "
            f'{metin[:300]}')


# ---------------------------------------------------------------------------
# 0. ORTAK YARDIMCININ KENDİ SÖZLEŞMESİ (S1-06 kökü)
# ---------------------------------------------------------------------------
class TestOrtakOkuyucu:
    """``_request_number``: "anahtar yok" ile "değeri null" AYRI okunmalı."""

    def test_anahtar_yoksa_varsayilan(self):
        assert _request_number({}, 'x', 7.0) == 7.0

    def test_acik_null_da_varsayilana_duser(self):
        """P7B4-06/P16B3-17'nin ta kendisi: ikisi AYNI sonucu vermeli."""
        assert _request_number({'x': None}, 'x', 7.0) == 7.0
        assert _request_number({'x': ''}, 'x', 7.0) == 7.0
        assert _request_number({'x': '   '}, 'x', 7.0) == 7.0

    def test_dusus_beyan_edilir(self):
        """Varsayılana düşmek SESSİZ olmaz."""
        log = []
        _request_number({'x': None}, 'x', 7.0, absent_log=log)
        assert log == ['x']
        # Anahtar hiç yoksa beyan da YOK (uydurma beyan üretilmez).
        log2 = []
        _request_number({}, 'x', 7.0, absent_log=log2)
        assert log2 == []

    def test_varsayilani_olmayan_alan_uydurulmaz(self):
        assert _request_number({'x': None}, 'x') is None
        log = []
        _request_number({'x': None}, 'x', absent_log=log)
        assert log == [], 'varsayılan yokken "varsayılana düşüldü" denemez'

    def test_bool_sayi_degildir(self):
        """``float(True) == 1.0``: bayrak sessizce 1 birime dönüşemez."""
        with pytest.raises(_RequestFieldError) as exc:
            _request_number({'x': True}, 'x', 7.0)
        assert exc.value.record['reason'] == 'not_a_number'
        assert exc.value.record['field'] == 'x'

    @pytest.mark.parametrize('deger', ['yirmi', [1], {'a': 1}])
    def test_sayi_olmayan_reddedilir(self, deger):
        with pytest.raises(_RequestFieldError) as exc:
            _request_number({'x': deger}, 'x', 7.0)
        assert exc.value.record['reason'] == 'not_a_number'

    @pytest.mark.parametrize('deger', [float('nan'), float('inf')])
    def test_sonlu_olmayan_reddedilir(self, deger):
        with pytest.raises(_RequestFieldError) as exc:
            _request_number({'x': deger}, 'x')
        assert exc.value.record['reason'] == 'not_finite'

    def test_sayi_benzeri_dize_KABUL_EDILIR(self):
        """Bugün de kabul ediliyor; burada reddetmek ÜRÜN davranışını
        değiştirirdi (form değeri gönderen sayfalar var)."""
        assert _request_number({'x': '20'}, 'x') == 20.0

    def test_istisna_metninde_deger_kirpilir(self):
        """Uzun gövde yanıta olduğu gibi kopyalanmaz."""
        exc = _RequestFieldError('x', 'not_a_number', 'A' * 5000)
        assert len(exc.record['value']) < 200

    def test_flow_float_de_ayni_ayrimi_yapar(self):
        """``_flow_float`` P7B4-06'nın tam kökü — aynı sözleşme."""
        assert _flow_float({}, 'x', 7.0) == 7.0
        assert _flow_float({'x': None}, 'x', 7.0) == 7.0
        assert _flow_float({'x': ''}, 'x', 7.0) == 7.0
        assert _flow_float({'x': None}, 'x') is None
        with pytest.raises(ValueError):
            _flow_float({'x': 'yirmi'}, 'x', 7.0)

    def test_missing_nobetcisi_ayri_bir_nesnedir(self):
        """``_MISSING`` hiçbir JSON değerine eşit olmamalı; yoksa "anahtar
        yok" ile "değeri şu" ayrımı yine silinir."""
        for deger in (None, '', 0, False, [], {}):
            assert _MISSING is not deger
            assert _MISSING != deger


# ---------------------------------------------------------------------------
# 1. P7B4-06 + P16B3-17 — ALANIN YOKLUĞU ⟷ AÇIK null (uçtan)
# ---------------------------------------------------------------------------
#: Uçların BUGÜN kabul ettiği en küçük tam yükler. Taban yükü eksik kalırsa
#: uç kendi fail-closed kapısına takılır ve aşağıdaki iddialar alanın DEĞİL
#: kapının davranışını ölçer — ÖH D15'te tam bu yüzden 8/13 vaka sessizce
#: ``skip`` oluyordu (defter OH-Z5-15 ŞART'ı + OH-D16-15).
WALL_PROFILE_TAM = {'chamber_pressure': 20, 'chamber_temperature': 3000,
                    'chamber_diameter': 0.1, 'chamber_length': 0.5,
                    'burn_time': 10, 'mdot_total': 1.0}
#: ``/api/trajectory-analysis`` aracın kendisini ister (ÖH D15 / P7B3-17:
#: uydurma 50 kg / Cd 0,5 / 0,1 m² roketi söküldü).
TRAJECTORY_TAM = {'thrust': 1000, 'burn_time': 10, 'initial_mass': 50.0,
                  'final_mass': 25.0, 'drag_coefficient': 0.5,
                  'reference_area': 0.1}
#: ``/api/transient-analysis`` blowdown koşumu (``S2_HIBRIT_ISTEK`` ailesi).
TRANSIENT_TAM = {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
                 'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
                 'feed_mode': 'blowdown', 'tank_temperature': 290.0,
                 'liquid_fill_fraction': 0.8}


def _tabansiz(taban, alan):
    """Taban yükünden sınanan alanı çıkarır.

    "Alan yok" hâlinin gerçekten YOKLUK olması gerekir; taban yükü alanı
    zaten taşıyorsa ``yok`` isteği aslında "değer verildi" isteğidir.
    """
    return {k: v for k, v in taban.items() if k != alan}


#: (uç, alan, taban, hüküm) — dördüncü sütun bu alanın BUGÜN hangi dürüstlük
#: kanalıyla korunduğunu söyler. ÖH D17 (bekci-cevirisi a1) ölçümü, kanıt
#: ``docs/scofield/raw/OH/D17/bekci-cevirisi/a1/once_ohz515b.json``:
#:
#: ``'beyan'``
#:     Alanın BELGELENMİŞ varsayılanı var; varsayılana düşüş yanıtta
#:     ``inputs_treated_as_absent`` listesinde ADIYLA ilan edilir. (10 vaka)
#: ``'kunye'``
#:     Sayı varsayılan DEĞİL, gövdedeki başka girdilerden TÜRETİLİR ve
#:     türetimin dayanağı ``<alan>_basis`` künyesiyle yayımlanır. (1 vaka:
#:     ``isp`` — kütle bütçesinden ``m_p / t_b``.)
#: ``'fail_closed'``
#:     Alanın varsayılanı YOKTUR; verilmezse uç 422 ile reddeder ve alanı
#:     ``missing_fields`` içinde adıyla ister. (2 vaka: wall-profile
#:     ``chamber_pressure`` — Bartz kütle akısı; trajectory
#:     ``drag_coefficient`` — aracın kendisi.)
#:
#: HİÇBİR vaka ``skip`` değildir: üç hükümden biri her vakada MECBURİDİR.
#: Dördüncü bir davranış ("200 döndü ama ne beyan ne künye var") sessiz
#: düşüştür ve bekçi onu KIRMIZI verir.
#: ÖH D27 / app-api a3 (OH-D26-20) — BEŞ AKIŞ SATIRININ TABANI ÇEVRİLDİ.
#: Satırlar ``taban={}`` kullanıyordu; ``{}`` artık 422 alıyor (hiçbir şey
#: söylemeyen istekten quasi-1D motor üretilmez — ölçüm ``a3/once.json``
#: K5). Bekçinin İDDİASI ("yokluk = açık null = boş dize") DEĞİŞMEDİ ve
#: aynen sınanmaya devam ediyor; yalnız MEŞRU bir tabanın üstünde
#: sınanıyor. Taban, sınanan alanı İÇERMEYEN en küçük geçerli gövdedir.
#: ÖH D32 / arayuz-panel a2 (OH-D31-14) — TABAN İKİNCİ KEZ TAZELENDİ,
#: DÖRT SATIRIN HÜKMÜ SERTLEŞTİ. D27'nin ``{'fidelity': 'fast'}`` tabanı
#: motorun HİÇBİR alanını taşımıyordu ve kapı alan-alan indiği için artık
#: 422 alıyor (ölçüm: ``D32/arayuz-panel/a2/sonra.json`` K2). Bekçinin
#: İDDİASI ("yokluk = açık null = boş dize") DEĞİŞMEDİ — üç biçim hâlâ
#: aynı durum kodunu alıyor (K1: 18/18 aynı) — yalnız MEŞRU bir tabanın
#: üstünde sınanıyor. Zorunlu dört alanın hükmü ``beyan`` -> ``fail_closed``
#: oldu: bu KOLAYA değil ZORA geçiştir (aşağıdaki dağılım kilidi zaten
#: tersini yasaklıyor), çünkü o alanların artık varsayılanı yoktur.
FLOW_YOKLUK_TABANI = {
    'chamber_pressure': 20.0, 'chamber_temperature': 3000.0, 'gamma': 1.2,
    'molecular_weight': 24.0, 'throat_diameter': 0.02,
    'ambient_pressure': 101325.0, 'expansion_ratio': 4.0,
    'fidelity': 'fast',
}

YOKLUK_NULL_CIFTLERI = [
    ('/api/flow-analysis', 'chamber_pressure',
     _tabansiz(FLOW_YOKLUK_TABANI, 'chamber_pressure'), 'fail_closed'),
    ('/api/flow-analysis', 'chamber_temperature',
     _tabansiz(FLOW_YOKLUK_TABANI, 'chamber_temperature'), 'fail_closed'),
    ('/api/flow-analysis', 'ambient_pressure',
     _tabansiz(FLOW_YOKLUK_TABANI, 'ambient_pressure'), 'fail_closed'),
    ('/api/flow-analysis', 'n_stations',
     dict(FLOW_YOKLUK_TABANI), 'beyan'),
    ('/api/flow-analysis', 'gamma',
     _tabansiz(FLOW_YOKLUK_TABANI, 'gamma'), 'fail_closed'),
    ('/api/analysis/wall-profile', 'chamber_pressure',
     _tabansiz(WALL_PROFILE_TAM, 'chamber_pressure'), 'fail_closed'),
    ('/api/analysis/wall-profile', 'wall_thickness',
     WALL_PROFILE_TAM, 'beyan'),
    ('/api/analysis/wall-profile', 'n_stations', WALL_PROFILE_TAM, 'beyan'),
    ('/api/analysis/wall-profile', 'ambient_temp', WALL_PROFILE_TAM, 'beyan'),
    ('/api/trajectory-analysis', 'isp', TRAJECTORY_TAM, 'kunye'),
    ('/api/trajectory-analysis', 'drag_coefficient',
     _tabansiz(TRAJECTORY_TAM, 'drag_coefficient'), 'fail_closed'),
    ('/api/transient-analysis', 'tank_temperature', TRANSIENT_TAM, 'beyan'),
    ('/api/transient-analysis', 'liquid_fill_fraction',
     TRANSIENT_TAM, 'beyan'),
]

#: Hüküm dağılımı ÖLÇÜLDÜ; tabloda bir vaka sessizce hükümsüz kalırsa
#: (ör. birisi ``'beyan'``ı ``'kunye'``ye çevirip iddiayı zayıflatırsa)
#: aşağıdaki bekçi bunu görür.
#: ÖH D32 (OH-D31-14): akış ucunun dört zorunlu alanı ``beyan``dan
#: ``fail_closed``a geçti (10/1/2 -> 6/1/6).
YOKLUK_NULL_HUKUM_DAGILIMI = {'beyan': 6, 'kunye': 1, 'fail_closed': 6}


def _kunye_ara(govde, ad):
    """Yanıt ağacında ``ad`` anahtarını arar; (yol, metin) çiftleri döner."""
    bulunan = []
    if isinstance(govde, dict):
        for anahtar, deger in govde.items():
            if anahtar == ad and isinstance(deger, str) and deger.strip():
                bulunan.append((anahtar, deger))
            bulunan.extend(_kunye_ara(deger, ad))
    elif isinstance(govde, list):
        for oge in govde:
            bulunan.extend(_kunye_ara(oge, ad))
    return bulunan


class TestYoklukIleAcikNullAyni:
    """P7B4-06 / P16B3-17 — ``{}`` ile ``{'k': null}`` AYNI hükmü almalı."""

    @pytest.mark.parametrize('yol,alan,taban,hukum', YOKLUK_NULL_CIFTLERI,
                             ids=[f'{y}:{a}' for y, a, _, _ in
                                  YOKLUK_NULL_CIFTLERI])
    def test_ayni_hukum(self, client, yol, alan, taban, hukum):
        yok = client.post(yol, json=dict(taban))
        null = client.post(yol, json=dict(taban, **{alan: None}))
        bos = client.post(yol, json=dict(taban, **{alan: ''}))
        assert yok.status_code == null.status_code == bos.status_code, (
            f'{yol} alanı {alan}: yokluk={yok.status_code} '
            f'null={null.status_code} boş={bos.status_code} — üçü de aynı '
            'olmalı ("açık null = verilmedi")')
        assert null.status_code < 500, (
            f'{yol} alanı {alan} açık null ile {null.status_code} verdi')

    @pytest.mark.parametrize('yol,alan,taban,hukum', YOKLUK_NULL_CIFTLERI,
                             ids=[f'{y}:{a}' for y, a, _, _ in
                                  YOKLUK_NULL_CIFTLERI])
    def test_dusus_sessiz_degil(self, client, yol, alan, taban, hukum):
        """Verilmeyen alan SESSİZ kalamaz: beyan, künye ya da ret.

        ÇEVİRİ (ÖH D17 / bekci-cevirisi a1 — defter OH-Z5-15 ŞART'ı ve
        OH-D16-15). Bu bekçinin eski hâli ``status != 200`` görünce
        ``pytest.skip`` ediyordu ve 13 vakanın 8'i KALICI olarak atlanıyordu
        (4 wall-profile + 2 trajectory + 2 transient). Atlama bir hüküm
        değildir: bekçi fiilen boşalmıştı, çünkü taban yükleri PK5/D15'te
        konan fail-closed kapılarından ÖNCEYE aitti ve uç 422/400 dönüyordu.

        İki onarım birden yapıldı (ŞART iki şık öneriyordu, ikisi de
        uygulandı):

        1. Taban yükleri TAZELENDİ — ``WALL_PROFILE_TAM`` (zorunlu altı
           alan), ``TRAJECTORY_TAM`` (araç dörtlüsü), ``TRANSIENT_TAM``
           (blowdown koşumu). Sınanan alan tabandan ``_tabansiz`` ile
           çıkarılır, böylece "yokluk" gerçekten yokluktur.
        2. ``skip`` yerine BEYANLI HÜKÜM — tablonun dördüncü sütunu her
           vakanın hangi dürüstlük kanalıyla korunduğunu söyler ve bekçi
           TAM O KANALI sınar.

        ÖLÇÜLDÜ (betik ``olcum_ohz515b.py`` -> ``once_ohz515b.json``):
        13 vakanın 13'ü sınıflandırıldı — 10 ``beyan``, 1 ``kunye``
        (``trajectory_data.motor_data.isp_basis`` = "derived from the mass
        budget actually integrated (m_p / t_b)"), 2 ``fail_closed``
        (wall-profile ``chamber_pressure`` -> 422
        ``incomplete_wall_profile_input``; trajectory ``drag_coefficient``
        -> 422 ``missing_vehicle_parameters``). ``skip`` sayısı 8 -> 0.
        Üç istek (yokluk / null / boş dize) 13 vakanın hepsinde aynı durum
        kodunu veriyor.
        """
        r = client.post(yol, json=dict(taban, **{alan: None}))
        govde = r.get_json() or {}
        assert hukum in ('beyan', 'kunye', 'fail_closed'), (
            f'{yol}:{alan} için tanımsız hüküm {hukum!r} — tabloda hüküm '
            'sütunu üç değerden biri olmak zorunda')

        if hukum == 'fail_closed':
            # Varsayılanı OLMAYAN alan: uç sayı uydurmaz, alanı adıyla ister.
            assert r.status_code == 422, (
                f'{yol}: {alan} verilmeden {r.status_code} döndü — '
                'varsayılanı olmayan alan için hüküm kazanılmadan '
                'yayımlanıyor')
            eksik = govde.get('missing_fields') or []
            assert alan in eksik, (
                f'{yol}: {alan} reddedildi ama ADIYLA istenmiyor; '
                f'missing_fields={eksik!r}')
            assert govde.get('error'), (
                f'{yol}: {alan} reddi adlandırılmamış (error alanı boş)')
            return

        assert r.status_code == 200, (
            f'{yol}: {alan} için tabloda {hukum!r} yazıyor ama uç '
            f'{r.status_code} döndü — taban yükü bayatlamış ya da hüküm '
            'sütunu güncellenmemiş (eski bekçi burada sessizce skip ederdi)')

        if hukum == 'kunye':
            # Sayı varsayılan değil, TÜRETİLMİŞ: dayanağı yayımlanmalı.
            kunyeler = _kunye_ara(govde, f'{alan}_basis')
            assert kunyeler, (
                f'{yol}: {alan} türetildi ama {alan}_basis künyesi '
                'yayımlanmıyor — türetim sessiz')
            metin = kunyeler[0][1]
            assert alan in metin or 'not supplied' in metin, (
                f'{yol}: {alan}_basis künyesi türetimin neden yapıldığını '
                f'söylemiyor: {metin!r}')
            return

        beyan = govde.get('inputs_treated_as_absent')
        assert beyan and alan in beyan, (
            f'{yol}: {alan} sessizce varsayılana düştü; '
            f'inputs_treated_as_absent={beyan!r}')

    def test_hicbir_vaka_hukumsuz_kalmadi(self):
        """Tablo boşalamaz: 13 vakanın hüküm dağılımı çivilenmiştir.

        ÖH D17 / OH-D16-15. ``skip``in yerine gelen "beyanlı hüküm" ancak
        hükümler sayılabildiği sürece bir kilittir. Biri vakayı tablodan
        düşürür ya da zor bir hükmü (``fail_closed``) kolayına
        (``beyan``) çevirirse bu bekçi kırmızı verir.
        """
        sayim = {}
        for _yol, _alan, _taban, hukum in YOKLUK_NULL_CIFTLERI:
            sayim[hukum] = sayim.get(hukum, 0) + 1
        assert sayim == YOKLUK_NULL_HUKUM_DAGILIMI, (
            f'hüküm dağılımı değişti: {sayim} != '
            f'{YOKLUK_NULL_HUKUM_DAGILIMI}')
        assert len(YOKLUK_NULL_CIFTLERI) == sum(
            YOKLUK_NULL_HUKUM_DAGILIMI.values()) == 13

    def test_taban_yuku_sinanan_alani_tasimaz(self):
        """"Yokluk" gerçekten yokluk olmalı.

        Taban yükü sınanan alanı zaten taşıyorsa ``yok`` isteği aslında
        "değer verildi" isteğidir ve ``test_ayni_hukum`` yanlış şeyi ölçer.
        ``fail_closed`` vakalarında bu ayrım hükmün KENDİSİDİR.
        """
        for yol, alan, taban, hukum in YOKLUK_NULL_CIFTLERI:
            if hukum == 'fail_closed':
                assert alan not in taban, (
                    f'{yol}: {alan} fail_closed sınanıyor ama taban yükü '
                    'alanı zaten taşıyor — yokluk ölçülemez')

    def test_saglikli_yolda_beyan_alani_HIC_YOK(self, client):
        """Sağlıklı gövde BİT-AYNI kalır: uydurma alan eklenmez."""
        # ÖH D32 (OH-D31-14): "sağlıklı gövde" artık motorun ALTI zorunlu
        # alanını da taşıyan gövdedir; eksik üçü (Tc, MW, P_amb) eklendi ve
        # değerleri ucun kanonik tablosundan alındı, yani YAYIMLANAN SAYI
        # DEĞİŞMEDİ (eskiden aynı üç sayı sessizce varsayılıyordu).
        r = client.post('/api/flow-analysis',
                        json={'chamber_pressure': 20.0, 'gamma': 1.2,
                              'chamber_temperature': 3000.0,
                              'molecular_weight': 24.0,
                              'ambient_pressure': 101325.0,
                              'throat_diameter': 0.02, 'expansion_ratio': 4.0,
                              'fidelity': 'fast'})
        assert r.status_code == 200
        assert 'inputs_treated_as_absent' not in r.get_json()


# ---------------------------------------------------------------------------
# 2. P16B3-19 — HAM 500 ENVANTERİ (ölçülen 21 vakanın tamamı)
# ---------------------------------------------------------------------------
#: Ölçümde 500 üreten ya da aynı sınıfa giren vakalar. ``beklenen_alan``
#: verilmişse yanıt o alanı adıyla anmalı.
HAM_500_ENVANTERI = [
    # /api/analysis/wall-profile (ölçümde 8/8 vaka HTTP 500 idi)
    ('/api/analysis/wall-profile', {'chamber_pressure': 'yirmi'},
     'chamber_pressure'),
    ('/api/analysis/wall-profile', {'chamber_temperature': [1]},
     'chamber_temperature'),
    ('/api/analysis/wall-profile', {'chamber_diameter': [0.1]},
     'chamber_diameter'),
    ('/api/analysis/wall-profile', {'chamber_length': True},
     'chamber_length'),
    ('/api/analysis/wall-profile', {'mdot_total': 'bir'}, 'mdot_total'),
    ('/api/analysis/wall-profile', {'wall_thickness': 'ince'},
     'wall_thickness'),
    ('/api/analysis/wall-profile', {'n_stations': 'kirk'}, 'n_stations'),
    ('/api/analysis/wall-profile', {'ambient_temp': 'sicak'}, 'ambient_temp'),
    ('/api/analysis/wall-profile', {'burn_time': {'a': 1}}, 'burn_time'),
    # /api/trajectory-analysis (ölçümde 8/8 vaka HTTP 500 idi)
    ('/api/trajectory-analysis',
     {'thrust': 1000, 'burn_time': 10, 'initial_mass': 'elli'},
     'initial_mass'),
    ('/api/trajectory-analysis',
     {'thrust': 1000, 'burn_time': 10, 'final_mass': [25]}, 'final_mass'),
    ('/api/trajectory-analysis',
     {'thrust': 1000, 'burn_time': 10, 'reference_area': [1]},
     'reference_area'),
    ('/api/trajectory-analysis',
     {'thrust': 1000, 'burn_time': 10, 'drag_coefficient': 'az'},
     'drag_coefficient'),
    ('/api/trajectory-analysis', {'thrust': 'bin', 'burn_time': 10},
     'thrust'),
    ('/api/trajectory-analysis', {'thrust': 1000, 'burn_time': 'on'},
     'burn_time'),
    ('/api/trajectory-analysis',
     {'thrust': 1000, 'burn_time': 10, 'total_impulse': 'cok'},
     'total_impulse'),
    ('/api/trajectory-analysis',
     {'thrust': 1000, 'burn_time': 10, 'isp': 'iki yuz'}, 'isp'),
    ('/api/trajectory-analysis',
     {'thrust': 1000, 'burn_time': 10, 'launch_angle': 'dik'},
     'launch_angle'),
    ('/api/trajectory-analysis',
     {'thrust': 1000, 'burn_time': 10, 'wind_speed': [3]}, 'wind_speed'),
    # /api/flow-analysis
    ('/api/flow-analysis', {'chamber_pressure': 'yirmi'}, 'chamber_pressure'),
    ('/api/flow-analysis', {'n_stations': 'kirk'}, 'n_stations'),
    ('/api/flow-analysis', {'gamma': [1.2]}, 'gamma'),
    # /api/transient-analysis
    ('/api/transient-analysis',
     {'thrust': 1000, 'burn_time': 10, 'tank_temperature': [1, 2]},
     'tank_temperature'),
    ('/api/transient-analysis',
     {'thrust': 1000, 'burn_time': 10, 'liquid_fill_fraction': 'yarim'},
     'liquid_fill_fraction'),
    # /api/launch-site/resolve — sınıf 400'dü ama gövde Python metniydi
    ('/api/launch-site/resolve', {'latitude': 'kirk', 'longitude': 30},
     'latitude'),
    ('/api/launch-site/resolve', {'latitude': [40], 'longitude': 30},
     'latitude'),
    ('/api/launch-site/resolve',
     {'latitude': 40, 'longitude': 30, 'elevation_m': 'yuz'}, 'elevation_m'),
    ('/api/launch-site/resolve',
     {'latitude': 40, 'longitude': 30, 'temperature_k': [288]},
     'temperature_k'),
    # /analyze_safety ve /analyze_thermal_safety — ÖLÇÜMDE ZATEN KAPALI
    # (Z3/Z4 kapıları). Bekçi geri gitmelerini engeller.
    ('/analyze_safety',
     {'propellant_mass': 'on', 'motor_type': 'hybrid'}, None),
    ('/analyze_thermal_safety', {'chamber_temperature': 'sicak'},
     'chamber_temperature'),
    ('/analyze_thermal_safety', {'wall_thickness': [1]}, 'wall_thickness'),
]


class TestHam500Envanteri:
    """P16B3-19 — istemci girdisi ASLA 5xx + Python metni üretmemeli."""

    @pytest.mark.parametrize(
        'yol,govde,alan', HAM_500_ENVANTERI,
        ids=[f'{y}:{list(g)[-1]}' for y, g, _ in HAM_500_ENVANTERI])
    def test_adli_4xx(self, client, yol, govde, alan):
        _sozlesme(client.post(yol, json=govde), beklenen_alan=alan)


# ---------------------------------------------------------------------------
# 3. P7B1-14 — /api/injector-design tip kapısı
# ---------------------------------------------------------------------------
class TestEnjektorTipKapisi:

    S2_INJ_TABAN = {'motor_type': 'hybrid', 'injector_type': 'showerhead',
             'mdot_ox': 1.2, 'Pc_bar': 20.0, 'rho_ox': 780.0}

    @pytest.mark.parametrize('alan,deger', [
        ('mdot_ox', 'iki'),
        ('mdot_ox', [1, 2]),
        ('mdot_ox', True),
        ('Pc_bar', 'yirmi'),
        ('Pc_bar', {'bar': 20}),
        ('rho_ox', 'yogun'),
        ('l_over_d', [4]),
        ('T_ox_K', 'soguk'),
        ('dp_ratio_ox', 'az'),
    ])
    def test_sayi_olmayan_spec_alani_adli_422(self, client, alan, deger):
        r = client.post('/api/injector-design',
                        json=dict(self.S2_INJ_TABAN, **{alan: deger}))
        assert r.status_code == 422, (
            f'{alan}={deger!r} -> {r.status_code} '
            f'(gövde: {_govde_metni(r)[:200]})')
        _sozlesme(r, beklenen_alan=alan)
        assert r.get_json()['error'] == 'invalid_injector_input'

    def test_ret_hesabi_BASLATMAZ(self, client):
        """Fail-closed: geçersiz tipte hiçbir tasarım alanı üretilmez."""
        r = client.post('/api/injector-design',
                        json=dict(self.S2_INJ_TABAN, mdot_ox='iki'))
        assert 'design' not in r.get_json()

    def test_None_cozucunun_kendi_400une_gider(self, client):
        """Kapı YALNIZ tip ekseninde; "verilmedi" hükmü çözücünündür."""
        r = client.post('/api/injector-design',
                        json=dict(self.S2_INJ_TABAN, mdot_ox=None))
        assert r.status_code == 400, _govde_metni(r)[:200]

    def test_gecerli_govde_hala_tasarim_uretir(self, client):
        r = client.post('/api/injector-design',
                        json=dict(self.S2_INJ_TABAN, fluid_ox='generic',
                                  dp_ratio_ox=0.2, l_over_d=4.0))
        assert r.status_code == 200, _govde_metni(r)[:300]
        assert r.get_json()['status'] == 'success'

    def test_cd_kapinin_DISINDA(self, client):
        """``cd``nin kendi adlandırılmış reddi zaten var; kopyalanmadı."""
        assert 'cd' not in _INJECTOR_NUMERIC_SPEC_FIELDS

    def test_liste_uc_uc_esler(self):
        """Liste ölçümle çıkarıldı; boş ya da bozuk kalmasın."""
        assert len(_INJECTOR_NUMERIC_SPEC_FIELDS) >= 20
        assert 'mdot_ox' in _INJECTOR_NUMERIC_SPEC_FIELDS
        assert 'Pc_bar' in _INJECTOR_NUMERIC_SPEC_FIELDS


# ---------------------------------------------------------------------------
# 4. P16B1-50 — /calculate: chamber_pressure iki farklı okunuyordu
# ---------------------------------------------------------------------------
S2_HIBRIT_ISTEK = {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
                'fuel_type': 'htpb', 'oxidizer_type': 'n2o'}


class TestHaznePressureTekOkuma:

    @pytest.fixture(scope='class')
    def yanit_anahtarsiz(self, client):
        """``chamber_pressure`` anahtarı HİÇ gönderilmeyen koşum."""
        return client.post('/calculate', json=dict(S2_HIBRIT_ISTEK))

    def test_keyerror_gitti(self, yanit_anahtarsiz):
        metin = _govde_metni(yanit_anahtarsiz)
        assert 'KeyError' not in metin, (
            'çıplak data[...] geri geldi: ' + metin[:200])
        assert yanit_anahtarsiz.status_code == 200, metin[:300]

    def test_error_type_alani_yok(self, yanit_anahtarsiz):
        """P16B1-30 sınıfı: 4xx içinde gizli Python tip adı."""
        body = yanit_anahtarsiz.get_json()
        assert 'error_type' not in body

    def test_motor_ile_enjektor_AYNI_basinci_gorur(self, yanit_anahtarsiz):
        """Kusurun özü: motor 20 bar ile hesaplayıp enjektöre başka bir
        okuma veriyordu. İkisi tek kaynaktan gelmeli."""
        body = yanit_anahtarsiz.get_json()
        motor = body.get('motor') or {}
        assert motor.get('chamber_pressure') == pytest.approx(20.0), (
            'motorun kullandığı varsayılan hazne basıncı değişmiş: '
            f"{motor.get('chamber_pressure')!r}")

    def test_alan_gonderildiginde_o_deger_kullanilir(self, client):
        r = client.post('/calculate', json=dict(S2_HIBRIT_ISTEK,
                                                chamber_pressure=35.0))
        assert r.status_code == 200
        assert (r.get_json()['motor']['chamber_pressure']
                == pytest.approx(35.0))

    def test_kaynak_kodunda_ciplak_indeksleme_kalmadi(self):
        """Kalemi yeniden açacak SATIRIN kendisi bekçili.

        Ölçüt AST'tir, metin araması DEĞİL: kusurun gerekçesini anlatan
        yorum satırı ``data['chamber_pressure']`` dizesini alıntılıyor ve
        metin araması onu kusur sanardı (bekçi kendi belgesini kırar).
        """
        import ast
        import inspect

        from hrma.app import calculate
        govde = ast.parse(inspect.getsource(calculate).lstrip())
        indeksler = [
            d.slice.value for d in ast.walk(govde)
            if isinstance(d, ast.Subscript)
            and isinstance(d.value, ast.Name) and d.value.id == 'data'
            and isinstance(d.slice, ast.Constant)
            and isinstance(d.slice.value, str)]
        assert 'chamber_pressure' not in indeksler, (
            f'çıplak data[...] geri geldi: {indeksler}')
        assert 'chamber_pressure_input' in inspect.getsource(calculate)
        # P16B1-50'nin İKİZİ (S1-06): ``injector_type`` bu uçta sekiz yerde
        # ``data.get(..., 'showerhead')`` ile okunurken bir yerde
        # indeksleniyordu (yedek enjektör çizimi dalı). Anahtar bu uçta
        # zorunlu değil; birincil çizim de düşerse ham KeyError çıkardı.
        assert 'injector_type' not in indeksler, (
            f'çıplak data[...] geri geldi: {indeksler}')

    def test_calculate_hicbir_ciplak_indeks_birakmadi(self):
        """Uçta kalan tüm ``data[...]`` okumaları sayılır ve sıfır olmalı."""
        import ast
        import inspect

        from hrma.app import calculate
        govde = ast.parse(inspect.getsource(calculate).lstrip())
        kalan = sorted(
            d.slice.value for d in ast.walk(govde)
            if isinstance(d, ast.Subscript)
            and isinstance(d.value, ast.Name) and d.value.id == 'data'
            and isinstance(d.slice, ast.Constant)
            and isinstance(d.slice.value, str))
        assert kalan == [], f'/calculate içinde çıplak indeksleme: {kalan}'


# ---------------------------------------------------------------------------
# 5. S1-06 — KÖKÜN KENDİSİ: kaç çıplak çağrı kaldı?
# ---------------------------------------------------------------------------
#: Bu pakette sahiplenilen uçlar. Ölçüm (``once_ast.json``):
#: ``data[...]`` 17, çıplak ``float(...)`` 28.
S2_UCLARI = ('analyze_wall_profile', 'trajectory_analysis',
             'transient_analysis', 'injector_design_api', 'flow_analysis',
             'launch_site_resolve')


def _ast_sayimi(adlar):
    import ast
    import inspect

    import hrma.app as app_modulu

    kaynak = inspect.getsource(app_modulu)
    agac = ast.parse(kaynak)
    sayim = {}
    for dugum in ast.walk(agac):
        if not isinstance(dugum, ast.FunctionDef) or dugum.name not in adlar:
            continue
        indeks = ciplak = 0
        for alt in ast.walk(dugum):
            if (isinstance(alt, ast.Subscript)
                    and isinstance(alt.value, ast.Name)
                    and alt.value.id == 'data'
                    and isinstance(alt.slice, ast.Constant)
                    and isinstance(alt.slice.value, str)):
                indeks += 1
            if (isinstance(alt, ast.Call) and isinstance(alt.func, ast.Name)
                    and alt.func.id in ('float', 'int')
                    and any(isinstance(a, ast.Call)
                            and isinstance(a.func, ast.Attribute)
                            and a.func.attr == 'get' for a in alt.args)):
                ciplak += 1
        sayim[dugum.name] = {'data_indeks': indeks, 'ciplak_donusum': ciplak}
    return sayim


class TestKokTemizligi:
    """S1-06 — ``float(data.get(...))`` kalıbı bu uçlarda YENİDEN doğmasın."""

    #: ÖLÇÜLEN ARTIK — ARTIK **SIFIR** (ÖH D23 / app-api a2, defter
    #: P13B4-12 · ÖK-20 ADIM 3). Eski değer ``{'flow_analysis': 1}``
    #: idi ve kendi notu şunu diyordu: *"Bu SESSİZ ATLAMA ayrı bir kusur
    #: sınıfıdır (bu paketin kalemi değil) ve onarımı 200 dönen bir gövdeyi
    #: 4xx'e çevireceği için buraya alınmadı — devir notu olarak kayıtlı."*
    #: O devir D23 aşama-2'de kapatıldı: ``flow_analysis``teki
    #: ``try/except (TypeError, ValueError): pass`` söküldü ve okuma
    #: ``input_guard.num``a bağlandı. Ölçüldü (``once_supurme.json`` ->
    #: ``sonra_supurme.json``): ``chamber_diameter`` için dört düşman
    #: değerin dördü de HTTP 200 iken artık dördü de 422 + alan adı.
    #: Bekçi SIKILAŞTIRILDI (gevşetilmedi): artık tek bir çıplak dönüşüm
    #: bile kırmızıdır.
    OLCULEN_ARTIK = {}

    def test_ciplak_donusum_artigi_buyumedi(self):
        sayim = _ast_sayimi(S2_UCLARI)
        assert set(sayim) == set(S2_UCLARI), (
            f'uç adı değişmiş, bekçi kör kaldı: {sorted(sayim)}')
        kirli = {ad: s['ciplak_donusum'] for ad, s in sayim.items()
                 if s['ciplak_donusum']}
        assert kirli == self.OLCULEN_ARTIK, (
            'çıplak float(data.get(...)) / int(data.get(...)) kalıbı '
            f'değişti: {json.dumps(kirli, ensure_ascii=False)} '
            f'(ölçülen artık: {self.OLCULEN_ARTIK})')

    @pytest.mark.parametrize('deger', ['yirmi', [1], True])
    def test_kalan_artik_5xx_URETEMEZ(self, client, deger):
        """Artık kapılıdır: davranış ölçülür, satır sayılmaz."""
        r = client.post('/api/flow-analysis',
                        json={'chamber_diameter': deger, 'fidelity': 'fast'})
        assert r.status_code < 500, _govde_metni(r)[:200]

    def test_dogrudan_indeksleme_kalmadi(self):
        """Kalan indekslemeler ölçüldü: yalnız ``analyze_wall_profile``
        (``nozzle_type``) ve ``injector_design_api`` (``motor_results``) —
        ikisi de bir ``if data.get(...)`` kapısının ARDINDA."""
        sayim = _ast_sayimi(S2_UCLARI)
        toplam = sum(s['data_indeks'] for s in sayim.values())
        assert toplam <= 2, (
            'doğrudan data[...] indekslemesi çoğaldı (ölçülen taban 2): '
            f'{json.dumps(sayim, ensure_ascii=False)}')


# ---------------------------------------------------------------------------
# 6. GEÇERLİ GÖVDE DAVRANIŞI — kapılar hesabı bozmadı
# ---------------------------------------------------------------------------
class TestGecerliGovdeKorundu:
    """``capa_bit_ayni.json``'daki 14 çapanın yaşayan çekirdeği.

    Tam bit-aynılık kanıtı ayrı zincirdedir (S1-sonrası taban ters
    değiştirmeyle yeniden kurulup md5'i doğrulandı; 14/14 bit-aynı). Burada
    kalıcı bekçi olarak SAYILARIN kendisi çivileniyor: kapı eklemek hiçbir
    hesabı kaydırmamalı.
    """

    def test_flow_analysis_bogaz_sayilari(self, client):
        # ÖH D32 (OH-D31-14): ``ambient_pressure`` gövdeye eklendi — zorunlu
        # altı alanın altıncısı. Değer ucun kanonik tablosundan (101 325 Pa),
        # yani sayı DEĞİŞMEDİ; eskiden aynı sayı sessizce varsayılıyordu.
        r = client.post('/api/flow-analysis',
                        json={'chamber_pressure': 20.0,
                              'chamber_temperature': 3000.0, 'gamma': 1.2,
                              'molecular_weight': 24.0,
                              'ambient_pressure': 101325.0,
                              'throat_diameter': 0.02,
                              'expansion_ratio': 4.0, 'fidelity': 'fast'})
        assert r.status_code == 200
        akis = r.get_json()['flow']
        # Aynı istek, alanlar açık ``null`` ile "boş bırakılmış" hâlde de
        # AYNI sayıyı vermeli (yokluk ⟷ null ⟷ değer aynı yola çıkar).
        r2 = client.post('/api/flow-analysis',
                         json={'chamber_pressure': 20.0,
                               'chamber_temperature': 3000.0, 'gamma': 1.2,
                               'molecular_weight': 24.0,
                               'ambient_pressure': 101325.0,
                               'throat_diameter': 0.02,
                               'expansion_ratio': 4.0, 'fidelity': 'fast',
                               'separation_factor': None,
                               'wall_temperature': None})
        akis2 = r2.get_json()['flow']
        assert json.dumps(akis, sort_keys=True, default=str) == \
            json.dumps(akis2, sort_keys=True, default=str), (
                'açık null gönderilen alan varsayılana düşmedi — sayılar '
                'kaydı')

    def test_wall_profile_bos_govde_fail_closed(self, client):
        """Boş gövde hüküm ÜRETMEZ; eksik alanlar ADIYLA söylenir.

        ÇEVİRİ (ÖH D15 / bekci-cevirisi, defter OH-Z5-15). Bu bekçinin eski
        hâli ``{}`` gövdesinin HTTP 200 dönmesini ve modül varsayılanlarıyla
        dolmasını SÖZLEŞME yapıyordu. P4B1-02'nin kusur tanımı tam olarak
        buydu ("boş gövde {} de aynı şekilde 200 dönüyor"): sekiz zorunlu
        girdi verilmemişken uç, uydurulmuş bir cidar profili yayımlıyordu.
        PK5 paketi ucu fail-closed yaptı ve kırılmayı beyan etti; sınıfın
        adı ("geçerli gövde korundu") artık ön koşulunu karşılamadığı için
        bekçi burada ÇEVRİLİYOR: sözleşme 200 değil 422'dir.

        ÖLÇÜLDÜ (bu depo, çeviriden önce — betik:
        ``docs/scofield/raw/OH/D15/bekci-cevirisi/a1/olcum_wallprofile.py``):
        ``{}`` -> 422 ``incomplete_wall_profile_input``, ``missing_fields``
        sekiz ad taşıyor (chamber_pressure, chamber_temperature,
        chamber_diameter, chamber_length, burn_time, throat_diameter,
        throat_area, mdot_total). Sekiz alanın her biri tek tek eksik ya da
        açık ``null`` bırakıldığında da 422 dönüyor (yokluk ⟷ null aynı
        hüküm).
        """
        bos = client.post('/api/analysis/wall-profile', json={})
        assert bos.status_code == 422, (
            f'boş gövde {bos.status_code} döndü — hüküm kazanılmadan '
            'yayımlanıyor')
        govde = bos.get_json()
        assert govde.get('error') == 'incomplete_wall_profile_input', (
            f"hata kodu {govde.get('error')!r} — eksik girdi ADIYLA "
            'söylenmiyor')
        eksikler = govde.get('missing_fields') or []
        assert eksikler, 'hangi alanların eksik olduğu söylenmiyor'
        # Sayı uydurulmadığının kilidi: reddedilen istekte profil YOK.
        assert 'wall_profile' not in govde, (
            'uç hem reddediyor hem profil yayımlıyor')

    def test_wall_profile_gecerli_govde_varsayilanlarla_ayni(self, client):
        """Sınıfın asıl iddiası: kapı eklemek hiçbir hesabı kaydırmamalı.

        Zorunlu sekiz alan verildiğinde, İSTEĞE BAĞLI alanların açıkça
        yazılması sonucu değiştirmemeli (beyan edilmiş varsayılanlar).
        Bu, eski bekçinin ``boş gövde == tam gövde`` iddiasının fail-closed
        kapıdan SONRA hayatta kalan hâlidir.

        ÖLÇÜLDÜ (çeviriden önce): iki yanıt da 200 ve ``wall_profile``
        serileştirmesi bit-aynı (6.832 bayt ⟷ 6.832 bayt).
        """
        zorunlu = {'chamber_pressure': 20, 'chamber_temperature': 3000,
                   'chamber_diameter': 0.1, 'chamber_length': 0.5,
                   'burn_time': 10, 'mdot_total': 1.0}
        istege_bagli = {'material': 'steel', 'wall_thickness': 0.005,
                        'n_stations': 40, 'ambient_temp': 293.15,
                        'cooling_type': 'natural'}
        sade = client.post('/api/analysis/wall-profile', json=dict(zorunlu))
        acik = client.post('/api/analysis/wall-profile',
                           json=dict(zorunlu, **istege_bagli))
        assert sade.status_code == acik.status_code == 200
        assert (json.dumps(sade.get_json()['wall_profile'], sort_keys=True,
                           default=str)
                == json.dumps(acik.get_json()['wall_profile'], sort_keys=True,
                              default=str)), (
            'isteğe bağlı alanlar açıkça yazılınca sayılar kaydı — '
            'varsayılan beyanı ile gerçek yol ayrışmış')

    def test_transient_gecerli_kosum_hala_egri_uretir(self, client):
        r = client.post('/api/transient-analysis',
                        json=dict(S2_HIBRIT_ISTEK, feed_mode='blowdown',
                                  tank_temperature=290.0,
                                  liquid_fill_fraction=0.8))
        assert r.status_code == 200, _govde_metni(r)[:300]
        gecici = r.get_json()['transient']
        assert len(gecici['time']) > 1
        assert 'inputs_treated_as_absent' not in r.get_json()

    def test_launch_site_gecerli_kosum(self, client):
        r = client.post('/api/launch-site/resolve',
                        json={'latitude': 39.9, 'longitude': 32.85,
                              'use_online': False})
        assert r.status_code == 200
        saha = r.get_json()['site']
        # Z1'de çivilenmiş sözleşme: standart g HER ZAMAN 9,80665.
        assert saha['gravity_standard_m_s2'] == pytest.approx(9.80665)
        assert saha['gravity_local_m_s2'] != saha['gravity_standard_m_s2']

    def test_trajectory_gecerli_kosum(self, client):
        """ÖH D15 / P7B3-18 — GÖVDE DÜZELTİLDİ (bekçi çevrildi).

        Eski gövde ``isp=200`` ile ``m_i-m_f = 25 kg``ı BİRLİKTE
        gönderiyordu ve bu ikisi aynı yanmayı iki farklı şekilde tarif
        ediyor: 1000 N x 10 s / (200 s x 9,80665) = **5,099 kg** yakıt,
        kütle bütçesi ise **25 kg** — 4,9 KAT fark. Uç bunu 200 ile
        çözüyordu, çünkü ``isp`` yalnız yanıtta yankılanan bir sayıydı;
        çözücü yörüngeyi 25 kg'dan entegre ediyor, ekranda ise
        ``F/(Isp.g0)`` ile hesaplanmış BAŞKA bir debi yazıyordu. Yani bu
        test "geçerli koşum" adı altında ÇELİŞKİLİ bir gövdenin kabul
        edilmesini KİLİTLİYORDU.

        Çeviri: gövdedeki isp, kütle bütçesiyle tutarlı değere alındı
        (25 kg / 10 s = 2,5 kg/s -> Isp = 1000/(2,5 x 9,80665) = 40,79 s).
        Ucun asıl sözleşmesi (200 + itki/impuls yankısı) AYNEN sınanmaya
        devam eder; ayrıca çelişkili gövdenin artık REDDEDİLDİĞİ de
        sınanır — kilit iki yönlü olsun diye.
        """
        isp_tutarli = 1000.0 / ((50 - 25) / 10.0 * 9.80665)
        r = client.post('/api/trajectory-analysis',
                        json={'thrust': 1000, 'burn_time': 10,
                              'initial_mass': 50, 'final_mass': 25,
                              'drag_coefficient': 0.5, 'reference_area': 0.1,
                              'isp': isp_tutarli})
        assert r.status_code == 200, _govde_metni(r)[:300]
        motor = r.get_json()['engine_data']
        assert motor['thrust'] == pytest.approx(1000.0)
        assert motor['total_impulse'] == pytest.approx(10000.0)
        assert 'inputs_treated_as_absent' not in r.get_json()
        # TERS YÖN: eski çelişkili gövde artık sessizce çözülmez.
        celiskili = client.post('/api/trajectory-analysis',
                                json={'thrust': 1000, 'burn_time': 10,
                                      'initial_mass': 50, 'final_mass': 25,
                                      'drag_coefficient': 0.5,
                                      'reference_area': 0.1, 'isp': 200.0})
        assert celiskili.status_code == 422
        assert (celiskili.get_json()['error']
                == 'inconsistent_propellant_budget')
