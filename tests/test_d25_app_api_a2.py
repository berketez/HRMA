# -*- coding: utf-8 -*-
"""ÖH D25 / app-api aşama-2 bekçisi — P16B3-02.

KALEM: "soğutma menüsündeki 5 seçenekten 4'ü modellenmiyor — sessizce
SOĞUTMASIZ sonuç, kullanıcının etiketi altında."

ÖLÇÜLEN KUSUR (``docs/scofield/raw/OH/D25/app-api/a2/once.json`` bölüm A,
taban ``cdf2106``; hibrit yük ``thrust=1000, Pc=20, O/F=6, N2O/HTPB``):
ürünün KENDİ soğutma sözlüğünden gelen dört kelime — ``ablative`` /
``film_cooling`` / ``radiative`` / ``dump_cooling``, yani ``liquid.html``
içindeki beş seçenekli soğutma menüsünün rejeneratif dışındaki dördü —
``/calculate`` ailesine gönderildiğinde HTTP 200 alıyor ve DOĞAL TAŞINIMIN
(soğutmasız) sayılarını yayımlıyordu::

    seçim         cooling_efficiency   required_cooling_area
    radial/spiral        0,9                0,2782 m²
    none                 0,3              445,05   m²
    ablative             0,3              445,05   m²   <-- 'none' fiziği
    film_cooling         0,3              445,05   m²   <-- 'none' fiziği
    radiative            0,3              445,05   m²   <-- 'none' fiziği
    dump_cooling         0,3              445,05   m²   <-- 'none' fiziği
    uydurma              0,3              445,05   m²   <-- 'none' fiziği

445,05 m², 0,2782 m²nin ~1600 katıdır; yanıt ise kullanıcının kelimesini
``design_warnings[].params.requested`` alanında geri okuyordu. Motor
kurucusu durumu yalnız UYARIYORDU (``warn.hybrid.cooling_type_unknown``) —
beyan bir çözüm değildir, çünkü sayı yine de yayımlanıyordu (doktrin 1).

ONARIM: ``hrma/app.py::_hibrit_sogutma_secimi`` — üç hibrit ucun
(``/calculate``, ``/api/quick-geometry``, ``/api/transient-analysis``)
girişinde beyaz-liste kapısı. Liste app.py'de YAZILMAZ; motorun tek tanım
noktası ``COOLING_CHANNEL_TO_TYPE``tan okunur (doktrin 4).

BU BEKÇİ NE KİLİTLER
  1. Dört ürün kelimesi + uydurma dize + sayı/bool/liste -> ADLI 4xx.
  2. Menünün üç seçeneği + doğrudan ısı-transferi terimleri -> geçer.
  3. "Gönderilmedi" (alan yok / '' / null) -> ürün varsayılanı, gövde
     açık ``none`` ile BİT-AYNI (çapa korunur).
  4. Beyaz liste TEK KAYNAKTAN gelir; ``or 'none'`` üçlü literali gitti.
  5. ``advanced.html`` menüsündeki her ``<option>`` motorun çözebildiği
     bir tiptir (şablon ⟷ kapı tutarlılığı; yeni seçenek eklenirse kırar).
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re

import pytest

from hrma.app import (
    HIBRIT_SOGUTMA_VARSAYILANI,
    _hibrit_sogutma_secimi,
    app as flask_app,
)
from hrma.analysis.heat_transfer_analysis import COOLING_DESIGN_DELTA_T
from hrma.engines.hybrid_rocket_engine import COOLING_CHANNEL_TO_TYPE

KOK = pathlib.Path(__file__).resolve().parents[1]


def _menu_secenekleri(sablon: str, alan_id: str):
    blok = re.search(
        r'<select[^>]*id\s*=\s*["\']%s["\'][^>]*>(.*?)</select>' % alan_id,
        sablon, re.S | re.I)
    if blok is None:
        return []
    return re.findall(r'<option[^>]*value\s*=\s*["\']([^"\']*)["\']',
                      blok.group(1), re.I)


#: Hibrit yükü — ölçüm betiğiyle BİREBİR aynı (once/sonra karşılaştırılabilir).
HIBRIT = {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
          'chamber_pressure': 20.0, 'fuel_type': 'htpb',
          'oxidizer_type': 'n2o'}

#: ``liquid.html`` soğutma menüsünün rejeneratif DIŞINDAKİ dört seçeneği.
#: Hibrit uçlarında bunların hiçbiri çözülemez; eskiden dördü de doğal
#: taşınımın sayılarını alıyordu.
URUN_SOZLUGUNDEN_COZULEMEYEN = ('ablative', 'film_cooling', 'radiative',
                                'dump_cooling')

#: Kapının reddetmesi gereken diğer girdiler. ``0`` bu alanda "otomatik"
#: demek DEĞİLDİR: sıvı sayfasının KANAL SAYISI alanıyla karışmış bir
#: değerdir (``liquid.html`` ``cooling_channels`` bir tamsayıdır).
DIGER_RET = ('uydurma', 0, 80, True, ['radial'], {'x': 1}, -1)

#: Kapının geçirmesi gereken girdiler: menünün üçü + motorun doğrudan
#: kabul ettiği ısı-transferi terimleri + yazım hoşgörüsü.
GECMESI_GEREKEN = tuple(COOLING_CHANNEL_TO_TYPE) + (
    'REGENERATIVE', ' spiral ', 'NONE')

#: Kapının bağlı olduğu üç hibrit uç.
UCLAR = ('/calculate', '/api/quick-geometry', '/api/transient-analysis')

#: Ürünün KENDİ kaynağından okunan varsayılan: ``advanced.html`` soğutma
#: menüsünün ilk ``<option>``ı. Bekçi beklenen değeri app.py'den ALMAZ —
#: alsaydı sabit kaydığında iki taraf birlikte kayar ve iddia totoloji
#: olurdu (ÖH D25 a2 ters-mutasyon M4 bunu ölçtü).
MENU_ILK_SECENEK = _menu_secenekleri(
    (KOK / 'hrma/templates/advanced.html').read_text(encoding='utf-8'),
    'cooling_channels')[0].strip().lower()

#: Soğutmasız (doğal taşınım) sınıfının ölçülen imzası — a2 ``once.json``
#: bölüm A: ``none`` seçimi eff = 0,3 ve A_gerekli = 445,05 m²; kanallı
#: seçim eff = 0,9 ve 0,2782 m².
SOGUTMASIZ_VERIM = 0.3
KANALLI_VERIM = 0.9


_COOLING_YOL = ('motor', 'heat_transfer_analysis', 'cooling_analysis')


@pytest.fixture(scope='module')
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        yield c



def _kod_dize_sabitleri(kaynak: str, aranan: str) -> int:
    """``kaynak`` içinde KOD olarak geçen ``aranan`` dize sabiti sayısı.

    Belge dizeleri (modül/sınıf/işlev docstring'leri) ve yorumlar sayılmaz;
    onlar ölçümü ve gerekçeyi anlatır, liste kopyası değildir.
    """
    import ast as _ast
    agac = _ast.parse(kaynak)
    belge = set()
    for dugum in _ast.walk(agac):
        govde = getattr(dugum, 'body', None)
        if isinstance(govde, list) and govde:
            ilk = govde[0]
            if (isinstance(ilk, _ast.Expr)
                    and isinstance(ilk.value, _ast.Constant)
                    and isinstance(ilk.value.value, str)):
                belge.add(id(ilk.value))
    return sum(1 for d in _ast.walk(agac)
               if isinstance(d, _ast.Constant) and isinstance(d.value, str)
               and aranan in d.value and id(d) not in belge)


def _cooling(govde):
    d = govde
    for parca in _COOLING_YOL:
        if not isinstance(d, dict):
            return {}
        d = d.get(parca) or {}
    return d if isinstance(d, dict) else {}


def _post(client, yol, **ek):
    return client.post(yol, json=dict(HIBRIT, **ek))


# ---------------------------------------------------------------------------
# 1. TANINMAYAN SEÇİM ARTIK SAYI YAYIMLAMIYOR
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('yol', UCLAR)
@pytest.mark.parametrize('secim', URUN_SOZLUGUNDEN_COZULEMEYEN)
def test_urun_sozlugunun_cozulemeyen_kelimesi_adiyla_reddedilir(
        client, yol, secim):
    """Kalemin ta kendisi: dört kelime de artık soğutmasız sayı ALMIYOR."""
    r = _post(client, yol, cooling_channels=secim)
    assert 400 <= r.status_code < 500, (
        f'{yol} + cooling_channels={secim!r} HTTP {r.status_code} döndü; '
        'tanınmayan soğutma seçimi için sayı yayımlanamaz')
    g = r.get_json()
    assert isinstance(g, dict)
    assert g.get('error') == 'unsupported_cooling_type', g.get('error')
    alanlar = g.get('invalid_fields') or []
    assert alanlar and alanlar[0].get('field') == 'cooling_channels', (
        f'ret hangi ALANIN sorunlu olduğunu söylemiyor: {alanlar}')
    assert alanlar[0].get('reason') == 'unsupported_value'
    # Reddin gövdesinde HİÇBİR soğutma sayısı olmamalı.
    assert not _cooling(g), 'ret gövdesinde soğutma analizi yayımlanmış'


@pytest.mark.parametrize('secim', DIGER_RET)
def test_sayi_bool_liste_ve_uydurma_dize_reddedilir(client, secim):
    r = _post(client, '/calculate', cooling_channels=secim)
    assert 400 <= r.status_code < 500, (
        f'cooling_channels={secim!r} HTTP {r.status_code} aldı')
    g = r.get_json() or {}
    assert g.get('error') == 'unsupported_cooling_type'
    assert (g.get('invalid_fields') or [{}])[0].get('field') == \
        'cooling_channels'


def test_ret_govdesi_python_ic_metni_sizdirmiyor(client):
    r = _post(client, '/calculate', cooling_channels='ablative')
    metin = r.get_data(as_text=True)
    for imza in ('Traceback', 'object has no attribute', "'NoneType'",
                 'unsupported operand type'):
        assert imza not in metin, f'ret gövdesine Python metni sızdı: {imza}'
    assert 'error_type' not in (r.get_json() or {})


# ---------------------------------------------------------------------------
# 2. MEŞRU SEÇİMLER KIPIRDAMADI
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('secim', GECMESI_GEREKEN)
def test_mesru_secim_gecer(client, secim):
    r = _post(client, '/calculate', cooling_channels=secim)
    assert r.status_code == 200, (
        f'meşru seçim {secim!r} HTTP {r.status_code} ile reddedildi')
    assert (r.get_json() or {}).get('error') != 'unsupported_cooling_type'


def test_menunun_uc_secenegi_iki_farkli_fizik_uretir(client):
    """Kapı, seçimlerin ETKİSİNİ silmedi: 'none' hâlâ soğutmasız."""
    yok = _cooling(_post(client, '/calculate',
                         cooling_channels='none').get_json())
    kanal = _cooling(_post(client, '/calculate',
                           cooling_channels='radial').get_json())
    assert yok.get('cooling_efficiency') == pytest.approx(SOGUTMASIZ_VERIM)
    assert kanal.get('cooling_efficiency') == pytest.approx(KANALLI_VERIM)
    a_yok = yok.get('required_cooling_area')
    a_kanal = kanal.get('required_cooling_area')
    assert a_yok and a_kanal and a_yok > 100 * a_kanal, (
        'soğutmasız ve kanallı seçimler artık ayrışmıyor: '
        f'{a_yok} / {a_kanal}')


# ---------------------------------------------------------------------------
# 3. "GÖNDERİLMEDİ" HÂLİ — ÇAPA KORUNUR
# ---------------------------------------------------------------------------

def _kanonik_sha(govde: dict, *, kunye_dusulsun: bool) -> str:
    """Yanıt ağacının kanonik sha256'sı (ham metin karşılaştırması YOK).

    ÖH D27 / fix-26b — YÖNTEM DEĞİŞİKLİĞİNİN SEBEBİ ÖLÇÜLDÜ. Bu uçların
    ``/calculate`` gövdesi **2,51 MB**tır. Eski iddia iki gövdeyi ham metin
    ``==`` ile karşılaştırıyordu; pytest başarısız bir ``==`` gördüğünde
    açıklamayı ``difflib`` ile üretir ve 2,5 MB × 2 dizgede bu, parametre
    başına ~40 dakika sürüyordu (taban kaydı-10 koşumu bu yüzden kesildi).
    Kıyas artık ayrıştırılmış ağacın kanonik serileştirmesinin sha256'sı
    üzerinden yapılır: aynı gücü taşır (bayt bayt eşitlik), sabit sürede
    biter ve fark çıkarsa YAPRAK LİSTESİ basılır, 2,5 MB metin değil.
    """
    kopya = dict(govde)
    if kunye_dusulsun:
        kopya.pop('defaults_applied', None)
    ham = json.dumps(kopya, sort_keys=True, ensure_ascii=False,
                     separators=(',', ':'), default=repr)
    return hashlib.sha256(ham.encode('utf-8')).hexdigest()


def _yapraklar_d25(dugum, yol=''):
    if isinstance(dugum, dict):
        for k, v in dugum.items():
            yield from _yapraklar_d25(v, f'{yol}.{k}' if yol else k)
    elif isinstance(dugum, list):
        for i, v in enumerate(dugum):
            yield from _yapraklar_d25(v, f'{yol}[{i}]')
    else:
        yield yol, dugum


@pytest.mark.parametrize('yama', [{}, {'cooling_channels': ''},
                                  {'cooling_channels': None},
                                  {'cooling_channels': '   '}])
def test_gonderilmeyen_alan_urun_varsayilanina_duser(client, yama):
    """Alan yok / boş / null -> menünün ilk seçeneği.

    Gövde, ``defaults_applied`` KÜNYESİ DIŞINDA bit-aynı; künye ise tam
    olarak ``cooling_channels`` kaydıdır.

    ÖH D27 / fix-26b — KUSURU KORUYAN BEKÇİ ÇEVRİLDİ. Eski iddia
    "gövde açık ``none`` ile BİT-AYNI" diyordu. O iddia D26 / sivi a1
    (``84f57626``, P16B3-02 KALAN) ile BİLEREK geçersiz kılındı: ÖK-19
    gereği artık alan gönderilmediğinde yanıt ``defaults_applied``
    künyesini taşıyor — "cooling_channels gönderilmedi, oda SOĞUTMASIZ
    çözüldü, bu bir sonuç değil varsayımdır". Yani bekçi, ürünün
    kazandığı DÜRÜSTLÜĞÜ eski sessizliğinde kilitliyordu; kırmızısı bir
    gerileme değil, kilidin kendisiydi.

    ÖLÇÜLDÜ (taban ``8abbe822``, ``fix26/b/olcum_once.json`` K10; dört
    yamanın dördü de aynı): açık gövde 2.512.197 bayt, künyeli gövde
    2.512.654 bayt; ağaç farkı TAM OLARAK dört yapraktır —
    ``defaults_applied[0]`` kaydının ``field`` / ``reason`` / ``value`` /
    ``message`` alanları. Ortak yaprakların HİÇBİRİNDE değer farkı yok
    (0 fark), yani fizik ve sayılar bit-aynı kaldı. Dört yamanın gövdesi
    birbiriyle de sha256 olarak birebir aynıdır.

    İDDİA ZAYIFLAMADI, YERİ DEĞİŞTİ: künye dışı gövde hâlâ bit-aynı
    aranıyor (kanonik sha256), üstüne künyenin KENDİSİ de tam olarak
    sınanıyor — açık seçimde künye BOŞ, gönderilmediğinde tek kayıt ve o
    kaydın alanı ``cooling_channels``, sebebi ``not_supplied``, değeri
    ürün varsayılanı. Eski hâlde künye hiç ölçülmüyordu.
    """
    assert HIBRIT_SOGUTMA_VARSAYILANI == MENU_ILK_SECENEK, (
        f'uç varsayılanı {HIBRIT_SOGUTMA_VARSAYILANI!r}, menünün ilk '
        f'seçeneği {MENU_ILK_SECENEK!r} — "gönderilmedi" hâli kullanıcının '
        'gördüğünden BAŞKA bir fizik uygular')
    acik = client.post('/calculate',
                       json=dict(HIBRIT, cooling_channels=MENU_ILK_SECENEK))
    ornek = client.post('/calculate', json=dict(HIBRIT, **yama))
    assert ornek.status_code == 200, ornek.get_data(as_text=True)[:200]
    acik_g, ornek_g = acik.get_json(), ornek.get_json()

    # (1) KÜNYE DIŞINDA BİT-AYNI. Fark çıkarsa 2,5 MB metin değil, ayrışan
    #     yaprakların ADI basılır (difflib tuzağına girilmez).
    if (_kanonik_sha(ornek_g, kunye_dusulsun=True)
            != _kanonik_sha(acik_g, kunye_dusulsun=True)):
        a = dict(_yapraklar_d25({k: v for k, v in acik_g.items()
                                 if k != 'defaults_applied'}))
        b = dict(_yapraklar_d25({k: v for k, v in ornek_g.items()
                                 if k != 'defaults_applied'}))
        tek_taraf = sorted(set(a) ^ set(b))
        deger = sorted(k for k in set(a) & set(b) if a[k] != b[k])
        raise AssertionError(
            f'{yama!r} açık {MENU_ILK_SECENEK!r} ile künye dışında '
            'bit-aynı DEĞİL — çapa kaydı ve mevcut istemciler etkilenir.\n'
            f'  yalnız bir tarafta: {tek_taraf[:20]}\n'
            f'  değeri farklı: {deger[:20]}')

    # (2) KÜNYENİN KENDİSİ: açıkta bu ALAN yok, gönderilmediğinde tek ve
    #     adlı.
    #
    # ÖH D32 / OH-D31-13 — BEKÇİ İKİNCİ KEZ ÇEVRİLDİ (gerekçeli). Eski
    # iddia "künye TAM OLARAK bir kayıttır" diyordu ve bu, ucun geri kalan
    # 18 ÖK-21 alanındaki SESSİZLİĞİNİ kilitliyordu: ``l_star``,
    # ``tank_pressure``, ``oxidizer_temp`` vb. uç varsayılanları
    # uygulanıyor ama künyede ANILMIYORDU (ölçüldü:
    # ``D32/app-api-uc/a1/once.json`` K2 — künyede anılan alan sayısı 1,
    # sessiz yedek 23). Kilidin kendisi, docstring'in anlattığı fix-26b
    # çevirisinin aynısıdır: iddia ZAYIFLAMADI, ALANA BAĞLANDI —
    # ``cooling_channels`` künyesi hâlâ tam olarak bir kez ve aynı
    # alanlarla aranıyor; kardeş alanların künyesi artık serbesttir.
    _acik_kunye = [k.get('field') for k in
                   (acik_g.get('defaults_applied') or [])]
    assert 'cooling_channels' not in _acik_kunye, (
        'kullanıcı seçimi AÇIKÇA gönderildiği hâlde uç "varsayılana '
        f'düştüm" künyesi yayımlıyor: {acik_g.get("defaults_applied")!r}')
    kunye = [k for k in (ornek_g.get('defaults_applied') or [])
             if k.get('field') == 'cooling_channels']
    assert len(kunye) == 1, (
        f'{yama!r}: ÖK-19 künyesi cooling_channels için tam olarak bir '
        f'kayıt olmalı, gelen: '
        f'{[k.get("field") for k in (ornek_g.get("defaults_applied") or [])]}')
    kayit = kunye[0]
    assert kayit.get('field') == 'cooling_channels', kayit
    assert kayit.get('reason') == 'not_supplied', kayit
    assert kayit.get('value') == HIBRIT_SOGUTMA_VARSAYILANI, kayit
    assert 'cooling_channels' in str(kayit.get('message') or ''), (
        'künye mesajı hangi alanın varsayıldığını yazmıyor: '
        f'{kayit.get("message")!r}')

    # (3) Fizik çapası: varsayılan SOĞUTMASIZ sınıftır; sessizce kanallı
    #     soğutmaya kaydırılırsa kullanıcı istemediği bir ceketin
    #     sayılarını görür (ters-mutasyon M4).
    assert _cooling(ornek_g).get('cooling_efficiency') == \
        pytest.approx(SOGUTMASIZ_VERIM), (
            'alan gönderilmediğinde soğutmasız sınıf uygulanmıyor')


def test_yardimci_dogrudan_da_ayni_sozlesmeyi_tutar():
    """Kapı gövdesi uç dışında da sınanır (üç uç aynı işlevi çağırır).

    ``jsonify`` uygulama bağlamı ister; bağlam AÇIKÇA kurulur ki test tek
    başına koşulduğunda da (``pytest -k``) aynı sonucu versin.
    """
    with flask_app.app_context():
        deger, ret = _hibrit_sogutma_secimi({})
        assert ret is None and deger == HIBRIT_SOGUTMA_VARSAYILANI
        deger, ret = _hibrit_sogutma_secimi({'cooling_channels': 'spiral'})
        assert ret is None and deger == 'spiral'
        deger, ret = _hibrit_sogutma_secimi({'cooling_channels': 'ablative'})
        assert deger is None and ret is not None and ret[1] == 422


# ---------------------------------------------------------------------------
# 4. TEK KAYNAK — LİSTE app.py'DE YAZILI DEĞİL
# ---------------------------------------------------------------------------

def test_izin_verilen_degerler_motorun_tek_tanim_noktasindan_gelir(client):
    r = _post(client, '/calculate', cooling_channels='ablative')
    izin = (r.get_json() or {}).get('invalid_fields', [{}])[0].get(
        'allowed_values')
    assert izin == list(COOLING_CHANNEL_TO_TYPE), (
        'kapı beyaz listeyi motordan okumuyor (kopya liste tehlikesi): '
        f'{izin}')


def test_app_py_ucluk_or_none_literalini_tasimiyor():
    """Doktrin 4: aynı varsayılan üç uçta elle yazılıydı; artık tek yerde."""
    kaynak = (KOK / 'hrma/app.py').read_text(encoding='utf-8')
    assert "data.get('cooling_channels') or 'none'" not in kaynak, (
        "üçlü ``or 'none'`` literali geri geldi — varsayılan "
        'HIBRIT_SOGUTMA_VARSAYILANI sabitinden okunmalı')
    assert kaynak.count('HIBRIT_SOGUTMA_VARSAYILANI = ') == 1
    # Beyaz liste app.py'de yeniden YAZILMAMALI. Ölçüm AST üzerinden
    # yapılır: yorum ve belge dizeleri sayılmaz, yalnız KOD'da geçen
    # ``'spiral'`` dize sabiti sayılır (``radial`` enjektör
    # ``secondary_holes`` alanında da geçtiği için ölçüt spiraldir).
    assert _kod_dize_sabitleri(kaynak, 'spiral') == 0, (
        'app.py kodunda soğutma seçeneği literali var — liste motorda '
        'tek tanımlı olmalı')


def test_kapi_uc_hibrit_ucta_da_bagli():
    """Üç uç de yardımcıyı çağırmalı (biri unutulursa delik açılır)."""
    kaynak = (KOK / 'hrma/app.py').read_text(encoding='utf-8')
    cagri = kaynak.count('= _hibrit_sogutma_secimi(')
    assert cagri == len(UCLAR), (
        f'kapı {len(UCLAR)} uçta beklenirken {cagri} çağrı bulundu')
    assert kaynak.count('cooling_type=cooling_secimi,') == len(UCLAR)


# ---------------------------------------------------------------------------
# 5. ŞABLON ⟷ KAPI TUTARLILIĞI (kalemin "menü" ayağı)
# ---------------------------------------------------------------------------

def test_hibrit_menusunun_her_secenegi_motorda_cozuluyor():
    """Menüye motorun çözemediği bir seçenek eklenirse bu bekçi kırar.

    Kalemin başlığı ("menüdeki N seçenekten M'i modellenmiyor") tam olarak
    bu tutarsızlıktır; kapı onu 4xx'e çevirir ama ÜRÜN menüsünde ölü bir
    seçenek durmamalıdır — kullanıcı seçebildiği bir şeyin reddedilmesini
    görmemeli.
    """
    sablon = (KOK / 'hrma/templates/advanced.html').read_text(
        encoding='utf-8')
    secenekler = _menu_secenekleri(sablon, 'cooling_channels')
    assert secenekler, 'advanced.html soğutma menüsü bulunamadı'
    cozulemeyen = [s for s in secenekler
                   if s.strip().lower() not in COOLING_CHANNEL_TO_TYPE]
    assert not cozulemeyen, (
        f'hibrit soğutma menüsünde motorun çözemediği seçenek(ler): '
        f'{cozulemeyen}')
    assert secenekler[0].strip().lower() == HIBRIT_SOGUTMA_VARSAYILANI, (
        f'uç varsayılanı {HIBRIT_SOGUTMA_VARSAYILANI!r} menünün ilk '
        f'seçeneği {secenekler[0]!r} değil — "gönderilmedi" hâli '
        'kullanıcının gördüğünden başka bir fizik uygular')


def test_hibrit_menusunun_cozumu_isi_modulunde_de_tanimli():
    """Menü -> ısı-transferi tipi zinciri sonuna kadar çözülebilmeli.

    ÖLÇÜLDÜ (a2 ``once.json`` bölüm C): ısı modülü yalnız
    ``natural`` / ``forced`` / ``regenerative`` çözer. Hibrit menüsünün
    üç seçeneği de bu kümeye düşer; ``liquid.html``in beş seçenekli
    menüsünün DÖRDÜ düşmez — bu bekçi kaymayı yakalar.
    """
    sablon = (KOK / 'hrma/templates/advanced.html').read_text(
        encoding='utf-8')
    for secenek in _menu_secenekleri(sablon, 'cooling_channels'):
        tip = COOLING_CHANNEL_TO_TYPE[secenek.strip().lower()]
        assert tip in COOLING_DESIGN_DELTA_T, (
            f'{secenek!r} -> {tip!r} ısı modülünde çözülemiyor; '
            'soğutmasız fiziğe düşerdi')
