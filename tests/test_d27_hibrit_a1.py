# -*- coding: utf-8 -*-
"""ÖH D27 / hibrit aşama-1 bekçileri — P13B4-04 ve OH-D26-05.

Ölçüm ve kanıt: ``docs/scofield/raw/OH/D27/hibrit/a1/`` (``olcum.py``,
``once.json``, ``sonra.json``, ``mutasyon*.json``, ``rapor.md``).

KALEM 1 — P13B4-04 (D26 DEVİR, bekci-kirmizi)
---------------------------------------------
ÖLÇÜLDÜ (taban ``709a235e``, ``once.json`` K1): tankın adım durumu
(``N2OTankBlowdown._pack_state``) **8** anahtar üretiyor ve içlerinde
``vapor_model_valid`` VAR; hibrit motorun blowdown bloğu
(``HybridRocketEngine._tank_blowdown_block``, ``status='modelled'``)
**40** anahtar yayımlıyor ve bayrak İÇLERİNDE YOK. Yani çözücü dürüst bir
zarf bayrağı kuruyor, serileştirici onu düşürüyordu: programatik tüketici
yayımlanan P(t)/T(t) örneklerinin fiziksel çözüm mü yoksa kenetlenmiş zarf
kenarı mı olduğunu hiçbir ALANDAN okuyamıyordu (tek kanal uyarı METNİYDİ).
Bekçi borcu ``tests/test_fazb_serilestirici_esligi.py`` içinde
``xfail(strict)`` imiyle duruyordu.

SONRA (``sonra.json`` K1): blok **43** anahtar; ``vapor_model_valid``,
``tank_saturation_band_clamped`` ve ``tank_model_envelope_basis``
yayımlanıyor, değerler tankın KENDİ nesnesinden okunuyor (tek kaynak).
Borç imi kaldırıldı.

Onarım bayrağı taşımakla yetinmedi. ÖLÇÜLDÜ (zarf taraması): bu blokta
``vapor_model_valid`` YAPISAL OLARAK True'dur — ``TransientBallistics.
solve`` yürüyüşü ``tank.phase == 'vapor'`` olduğu anda kırılır, hiçbir
buhar adımı integre edilmez, dolayısıyla üçlü nokta tabanı (182,33 K /
87,84 kPa, NIST WebBook) buradan ateşlenemez. Ateşlenebilen zarf doygunluk
bandı kenetlenmesidir (240-306 K tablosu): Pc = 8 bar / 245 K tankta 208
örneğin **70**'i banda kenetli, nominal 20 bar / 293,15 K'de **0**.
Sessiz bir "hep doğru" bayrak olmayan bir kapıyı varmış gibi gösterirdi;
künye bunu adıyla söyler ve ateşlenebilen zarfın kendi DEĞER kanalı var.

KALEM 2 — OH-D26-05 (hüküm bulgusu)
------------------------------------
ÖLÇÜLDÜ (``once.json`` K2; gövde ``thrust=1000 N, burn_time=10 s,
Pc=20 bar, O/F=6, HTPB/N2O``): ``/api/transient-analysis`` ucuna
``cooling_channels`` = ``none`` / ``radial`` / ``spiral`` /
``regenerative`` gönderen DÖRT istek BİT-AYNI yanıt alıyordu — 3.238
yaprakta **0** fark, dördünün de sha256'sı
``bb3a4576d73f723095b67d79806ba2a2f05c901704a55e4294eb8cca7482d53e``.
Kullanıcı rejeneratif soğutmalı motor tarif ediyor, soğutmasız motorun
eğrisini alıyor ve yanıtta bunu söyleyen tek yaprak bulunmuyordu.
(Kardeş uçlarda alan CANLIDIR: aynı gövde ``/calculate``te 460,
``/api/quick-geometry``de 153 yaprak oynatıyor — ÖH D26 / P16B3-02.)

Onarım doktrin-1'dir (fail-closed): alan artık ADIYLA reddedilir
(HTTP 422, ``unread_field``) ve okunduğu kardeş uç gösterilir. Alan HİÇ
gönderilmediğinde davranış BİT-AYNI kalır (``sonra.json``: sha256
``a6c3f7372fe3037f18d0d3145cd17b25615dbee2365b07d1d8f88b5abcbf617c``,
tabanla eşit) ve ÖH D26'nın ``defaults_applied`` künyesi aynen doğar.
"""
import contextlib
import io
import os
import sys

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if KOK not in sys.path:                                   # pragma: no cover
    sys.path.insert(0, KOK)

from hrma.app import app as flask_app                     # noqa: E402
from hrma.engines.hybrid_rocket_engine import (           # noqa: E402
    HybridRocketEngine, COOLING_CHANNEL_TO_TYPE, TANK_FILL_FRACTION_DEFAULT,
    TANK_BLOWDOWN_N_STEPS, TANK_TEMPERATURE_DEFAULT_K)

#: Ölçüm betiğiyle BİREBİR aynı gövde (once/sonra kıyaslanabilir olsun).
HIBRIT = {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
          'chamber_pressure': 20.0, 'fuel_type': 'htpb',
          'oxidizer_type': 'n2o'}


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


@pytest.fixture(scope='module')
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        yield c


#: Blok koşusunun taban parametreleri (üstüne yazılabilir).
_MOTOR_TABANI = dict(thrust=1000, burn_time=10, of_ratio=6.0,
                     chamber_pressure=20.0, fuel_type='htpb',
                     oxidizer_type='n2o', expansion_ratio=8,
                     atmospheric_pressure=1.0)


def _blok(**ek):
    """Gerçek bir hibrit koşusunun 'modelled' blowdown bloğu."""
    m = _sessiz(HybridRocketEngine, **dict(_MOTOR_TABANI, **ek))
    _sessiz(m.calculate)
    return _sessiz(m._tank_blowdown_block)


# ===========================================================================
# KALEM 1 — P13B4-04: zarf bayrağı artık DEĞER kanalı
# ===========================================================================
class TestP13B404ZarfBayragiYayimlaniyor:

    def test_bayrak_gercek_kosuda_blokta_var(self):
        """Kalemin ta kendisi: bayrak yayımlanan blokta ALAN olarak var."""
        b = _blok()
        assert b['status'] == 'modelled', b.get('reason')
        assert 'vapor_model_valid' in b, (
            'P13B4-04 geri açılmış: blowdown bloğu zarf bayrağını yeniden '
            f'yutuyor (anahtarlar: {sorted(b)})')
        assert isinstance(b['vapor_model_valid'], bool), (
            'bayrak bool DEĞİL — programatik kapı kurulabilmesi için '
            f'tip sabit olmalı: {type(b["vapor_model_valid"]).__name__}')

    def test_bayrak_tankin_kendi_nesnesinden_okunuyor(self):
        """Tek kaynak: blok bayrağı yeniden TÜRETMİYOR, tanktan okuyor.

        İKİ AYAKLIDIR ve ikinci ayak ÖLÇÜLEREK eklendi. Koşum ayağı tek
        başına YETMİYOR: ters-mutasyon M2 (``'vapor_model_valid': True``)
        ilk turda YEŞİL geçti, çünkü bayrak bu blokta yapısal olarak
        True'dur (yürüyüş sıvı bitince kırılır) ve sabit ile canlı okuma
        aynı sayıyı verir. Bu yüzden ikinci ayak KAYNAK ayağıdır: değerin
        bir SABİT değil, tank nesnesinden okunan bir ifade olduğu AST ile
        zorlanır. Sabit yazılırsa iddia kırmızı verir (M2 yeniden koşuldu).
        """
        import ast
        yol = os.path.join(KOK, 'hrma', 'engines', 'hybrid_rocket_engine.py')
        agac = ast.parse(open(yol, encoding='utf-8').read())
        bulunan = {}
        for dugum in ast.walk(agac):
            if not isinstance(dugum, ast.Dict):
                continue
            for k, v in zip(dugum.keys, dugum.values):
                if (isinstance(k, ast.Constant)
                        and k.value in ('vapor_model_valid',
                                        'tank_saturation_band_clamped')):
                    bulunan[k.value] = v
        for ad in ('vapor_model_valid', 'tank_saturation_band_clamped'):
            v = bulunan.get(ad)
            assert v is not None, f'{ad} ürün kaynağında yayımlanmıyor'
            assert not isinstance(v, ast.Constant), (
                f'{ad} SABİT yazılmış: değer tankın kendi durumundan '
                'okunmuyor, uydurma bir sabit yayımlanıyor (doktrin 4/6)')
            nitelikler = {d.attr for d in ast.walk(v)
                          if isinstance(d, ast.Attribute)}
            assert 'tank' in nitelikler, (
                f'{ad} değeri tank nesnesinden okunmuyor: {ast.dump(v)[:120]}')

        from hrma.analysis.transient_ballistics import TransientBallistics
        m = _sessiz(HybridRocketEngine, **_MOTOR_TABANI)
        _sessiz(m.calculate)
        b = _sessiz(m._tank_blowdown_block)
        # Bloğun kullandığı çözücü kurulumunun AYNISI (aynı parametreler).
        tb = _sessiz(TransientBallistics, m, feed_mode='blowdown',
                     tank_temperature=(m.tank_temperature
                                       if m.tank_temperature is not None
                                       else TANK_TEMPERATURE_DEFAULT_K),
                     liquid_fill_fraction=TANK_FILL_FRACTION_DEFAULT,
                     n_steps=TANK_BLOWDOWN_N_STEPS)
        _sessiz(tb.solve)
        assert b['vapor_model_valid'] is bool(tb.tank.vapor_model_valid)
        assert b['tank_saturation_band_clamped'] is bool(tb.tank.out_of_band)

    def test_ateslenebilen_zarf_gercekten_atesleniyor(self):
        """``tank_saturation_band_clamped`` YAŞAYAN bir kapı mı?

        ÖLÇÜLDÜ: nominal (20 bar / 293,15 K) koşuda kenetlenme YOK; düşük
        basınç + soğuk tank (8 bar / 245 K) koşusunda tankın 240-306 K
        doygunluk bandı tabanına kenetlenen örnekler var (208 örneğin
        70'i). İki koşu AYNI alanda FARKLI değer vermezse kanal bir
        uydurma sabittir, kapı değil.
        """
        nominal = _blok()
        assert nominal['tank_saturation_band_clamped'] is False, (
            'nominal koşu artık bant kenetlemesi bildiriyor — ölçüm zemini '
            'değişmiş (once.json zarf taraması)')
        soguk = _blok(chamber_pressure=8.0, burn_time=30.0,
                      tank_temperature=245.0)
        assert soguk['status'] == 'modelled', soguk.get('reason')
        assert soguk['tank_saturation_band_clamped'] is True, (
            'soğuk/düşük basınç koşusunda bant kenetlemesi bildirilmiyor: '
            'zarf kanalı yalnız "hep False" veren ölü bir alan')
        # Zarf ihlali METİN kanalında da durmaya devam eder (iki kanal
        # birbirini kapatmaz).
        assert any('MODEL BAND' in u for u in soguk['warnings']), (
            'bant kenetlemesinin uyarı metni koptu')

    def test_kunye_bayragin_neyi_garanti_ettigini_soyluyor(self):
        """Künye "hep doğru" bayrağı canlı alarm gibi göstermiyor."""
        kunye = _blok()['tank_model_envelope_basis']
        for parca in ('oxidizer_depleted', 'triple point', '240-306 K',
                      'NIST WebBook'):
            assert parca in kunye, (
                f'zarf künyesi {parca!r} demiyor — bayrağın neyi garanti '
                'ettiği ve hangi zarfın ateşlenebildiği okunamıyor')

    def test_borc_imi_kalkti(self):
        """P13B4-04 xfail(strict) borç imi gerçekten söküldü mü?"""
        import ast
        yol = os.path.join(KOK, 'tests',
                           'test_fazb_serilestirici_esligi.py')
        agac = ast.parse(open(yol, encoding='utf-8').read())
        for dugum in ast.walk(agac):
            if not (isinstance(dugum, ast.FunctionDef)
                    and dugum.name == 'test_s2_blowdown_adim_durumu_alan_'
                                      'esligi'):
                continue
            assert not dugum.decorator_list, (
                'S2 alan-eşliği iddiası hâlâ imli — P13B4-04 borcu '
                'kapanmadı')
            return
        raise AssertionError('S2 alan-eşliği iddiası bulunamadı')


# ===========================================================================
# KALEM 2 — OH-D26-05: soğutma seçimi bu uçta ADIYLA reddediliyor
# ===========================================================================
class TestOHD2605SogutmaSecimiYutulmuyor:

    @pytest.mark.parametrize('secim', sorted(COOLING_CHANNEL_TO_TYPE))
    def test_tanimli_secim_adiyla_reddediliyor(self, client, secim):
        """Kalemin ta kendisi: alan artık sessizce yutulmuyor."""
        r = client.post('/api/transient-analysis',
                        json=dict(HIBRIT, cooling_channels=secim))
        assert r.status_code == 422, (
            f'cooling_channels={secim!r} HTTP {r.status_code} aldı; yayımlanan '
            'hiçbir sayıya girmeyen alan kabul edilemez (doktrin 1)')
        g = r.get_json() or {}
        assert g.get('error') == 'unread_field', g.get('error')
        alanlar = g.get('invalid_fields') or []
        assert alanlar and alanlar[0].get('field') == 'cooling_channels', (
            f'ret hangi ALANIN sorunlu olduğunu söylemiyor: {alanlar}')
        assert alanlar[0].get('reason') == 'field_not_read'
        # Okunduğu kardeş uç gösterilmeli (çıkmaz sokak bırakılmaz).
        assert '/calculate' in str(alanlar[0].get('use_instead'))
        # Ret gövdesinde EĞRİ olmamalı: reddedilen istek için integrasyon
        # başlatılmaz.
        assert 'transient' not in g and 'design_point' not in g

    def test_ret_govdesi_gonderilen_degeri_yankiliyor(self, client):
        """İki farklı seçim iki farklı ret gövdesi verir (yankı canlı)."""
        a = client.post('/api/transient-analysis',
                        json=dict(HIBRIT, cooling_channels='radial'))
        b = client.post('/api/transient-analysis',
                        json=dict(HIBRIT, cooling_channels='regenerative'))
        assert a.get_data(as_text=True) != b.get_data(as_text=True), (
            'iki farklı soğutma seçimi hâlâ BİT-AYNI yanıt veriyor — '
            'OH-D26-05 geri açılmış')

    @pytest.mark.parametrize('bos', [None, '', '   '])
    def test_gonderilmeyen_alan_capayi_bozmuyor(self, client, bos):
        """Alan yok / boş / null -> davranış BİT-AYNI, künye aynen doğar."""
        taban = client.post('/api/transient-analysis', json=dict(HIBRIT))
        assert taban.status_code == 200, taban.get_data(as_text=True)[:200]
        ornek = client.post('/api/transient-analysis',
                            json=dict(HIBRIT, cooling_channels=bos))
        assert ornek.status_code == 200, ornek.get_data(as_text=True)[:200]
        assert ornek.get_data(as_text=True) == taban.get_data(as_text=True), (
            f'{bos!r} "gönderilmedi" sayılmıyor — çapa ve mevcut istemciler '
            'etkilenir')
        kunyeler = (taban.get_json() or {}).get('defaults_applied') or []
        assert any(k.get('field') == 'cooling_channels' for k in kunyeler), (
            'ÖH D26 / P16B3-02 künyesi kayboldu: kabul artık beyan '
            'edilmiyor (ÖK-19)')

    def test_taninmayan_kelime_hala_kardes_cevabini_aliyor(self, client):
        """Yeni kapı beyaz liste kapısını GÖLGELEMEDİ (sıralama çapası)."""
        r = client.post('/api/transient-analysis',
                        json=dict(HIBRIT, cooling_channels='ablative'))
        assert r.status_code == 422
        assert (r.get_json() or {}).get('error') == 'unsupported_cooling_type'

    def test_kardes_uclarda_alan_hala_canli(self, client):
        """Kapı yalnız BU uçta: ``/calculate`` seçimi okumaya devam eder."""
        yok = client.post('/calculate',
                          json=dict(HIBRIT, cooling_channels='none'))
        kanal = client.post('/calculate',
                            json=dict(HIBRIT, cooling_channels='radial'))
        assert yok.status_code == 200 and kanal.status_code == 200
        assert yok.get_data(as_text=True) != kanal.get_data(as_text=True), (
            '/calculate soğutma seçimini artık okumuyor — kapı yanlış uca '
            'kurulmuş')

    def test_urun_sayfasi_bu_alani_bu_uca_gondermiyor(self):
        """ÖK-22 çapası: kapı sağlıklı envanteri daraltmıyor.

        ``transient_panel.js`` gövdeyi ``collectMotorParams()`` ile kurar;
        o toplayıcıda ``cooling_channels`` YOKTUR. Alan oraya eklenirse
        bu iddia kırmızı verir ve kapı ile ürün birlikte gözden geçirilir.
        """
        yol = os.path.join(KOK, 'hrma', 'static', 'js',
                           'transient_panel.js')
        metin = open(yol, encoding='utf-8').read()
        govde = metin.split('function collectMotorParams')[-1]
        govde = govde.split('function panelHtml')[0]
        assert 'cooling_channels' not in govde, (
            'transient panel artık cooling_channels gönderiyor: yeni kapı '
            'ürün yolunu 422 yapar — kapı ile panel birlikte ele alınmalı')
