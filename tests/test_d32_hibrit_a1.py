"""ÖH D32 · hibrit a1 — dört kalemin bekçisi.

Ölçümler: ``docs/scofield/raw/OH/D32/hibrit/a1/once.json`` -> ``sonra.json``
(taban ``dd1dcddc``, ORTAK taban ağacı).

OH-B1-05   ONARILDI (D31'in ödemediği KAYNAK EŞLEŞMESİ ayağı). Yanlılık
           uyarısı, üç HTPB/N₂O kampanyasından türetilmiş bandı,
           ``oxidizer_type`` NE OLURSA OLSUN aynı gövdeyle yayımlıyordu.
           ÖLÇÜLDÜ (once.json ``C``): n2o/lox/h2o2 üçünde de uyarı VAR ve
           üçünde de bandın hangi zarfta ölçüldüğünü söyleyen alan YOK. Yani
           N₂O ile ölçülmüş bir yanlılık, LOX koşusunda o koşuya aitmiş gibi
           duruyordu. Kodun kendi ASTRA notu (hybrid_rocket_engine.py:493)
           bunu zaten yasaklıyordu, fakat kural yalnız YORUMDA duruyordu.
           Onarım katsayıya DOKUNMAZ, bandı DEĞİŞTİRMEZ, bandı SUSTURMAZ —
           yalnız zarfı ve bu koşunun zarf içinde olup olmadığını söyler.
OH-D26-04  D31 DEVRİ — motor ayağı D31'de kapandı (NOT_MODELLED makine-okur
           beyan); buradaki bekçiler o beyanın ÇÜRÜMESİNİ engeller. Kalan
           yarı bu dalgada AÇILMADI: menü birleştirme/etiket D32
           arayuz-panel (OH-D31-04), Dean sayısı modeli + dört girdi 2.7
           fizik (ÖK-06).
P12bB3-02  D31 DEVRİ — dört yakıtın adlandırılmış red gerekçesi D31'de
           kapandı; buradaki bekçiler gerekçelerin tekrar tek genel metne
           çökmesini engeller. Kalan yarı AÇILMADI: al2o3 seçicisi +
           ölü paneller D32 arayuz-panel (OH-D31-05), carbon kaynak borcu
           ve mixture/custom şema sözleşmesi 2.7.
OH-D31-10  ENGELLİ (borç imi) — kusur ÖLÇÜLDÜ ama kaynağı BU KULVARIN
           SAHASINDA DEĞİL: ``/calculate`` reddin gerekçesini
           ``not_a_number`` (hrma/validation/motor_validation.py:483,722),
           ``/calculate_liquid`` ise AYNI tel biçimi için
           ``not_a_json_number`` (hrma/app.py) diye yayımlıyor.
           motor_validation.py D32'de app-api-dogrulama kulvarında
           DEĞİŞİYOR (kardeş dal ölçümü, rapor.md §kardes_dal), bu yüzden
           dokunulmadı; kusur xfail(strict) imiyle görünür tutuldu.
"""

import contextlib
import io

import pytest

from hrma.engines.hybrid_rocket_engine import (
    COOLING_CHANNEL_TO_TYPE,
    COOLING_CHANNEL_GEOMETRY_SELECTIONS,
    COOLING_GEOMETRY_EQUIVALENCE,
    HTPB_COEFF_DB_BIAS_PCT,
    HTPB_INDEPENDENT_CAMPAIGNS,
    HTPB_INDEPENDENT_CAMPAIGN_BIAS_BAND_PCT,
    HTPB_INDEPENDENT_CAMPAIGN_OXIDIZERS,
    HybridRocketEngine,
)

TEMEL = dict(of_ratio=2.5, chamber_pressure=20, atmospheric_pressure=1.0,
             fuel_type='htpb', oxidizer_type='n2o', thrust=1000,
             burn_time=10)


def _kos(**kw):
    ayar = dict(TEMEL)
    ayar.update(kw)
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        motor = HybridRocketEngine(**ayar)
        return motor, motor.calculate()


def _uyari(sonuc, kod):
    for u in (sonuc.get('warnings') or []):
        if isinstance(u, dict) and u.get('code') == kod:
            return u
    return None


def _bias_params(oxidizer):
    _, sonuc = _kos(oxidizer_type=oxidizer)
    u = _uyari(sonuc, 'warn.hybrid.htpb_coeff_bias')
    assert u is not None, (
        'warn.hybrid.htpb_coeff_bias %r koşusunda hiç ateşlenmedi; bu bekçi '
        'uyarının VARLIĞINI değil KAPSAMINI ölçer.' % oxidizer)
    return u.get('params') or {}


def _yapraklar(x, yol=''):
    if isinstance(x, dict):
        for k in sorted(x, key=str):
            yield from _yapraklar(x[k], '%s.%s' % (yol, k))
    elif isinstance(x, (list, tuple)):
        for i, v in enumerate(x):
            yield from _yapraklar(v, '%s[%d]' % (yol, i))
    else:
        yield yol, repr(x)


# ---------------------------------------------------------------------------
# OH-B1-05 — ONARIM: bandın OKSİTLEYİCİ ZARFI adıyla çıkar
# ---------------------------------------------------------------------------
class TestOhB105OksitleyiciZarfi:
    """Yayımlanan yanlılık bandı, ölçüldüğü zarfın dışında 'eşleşiyor'
    diye okunamaz."""

    def test_zarf_kampanya_kayitlarindan_turetilir(self):
        """Zarf ELLE yazılmaz (doktrin 4): kampanya kayıtlarından türetilir."""
        beklenen = tuple(sorted(
            {k['oxidizer'] for k in HTPB_INDEPENDENT_CAMPAIGNS}))
        assert HTPB_INDEPENDENT_CAMPAIGN_OXIDIZERS == beklenen

    def test_kampanya_govdesinin_tamami_n2o_astra_sarti(self):
        """ASTRA (14 Eyl): yayımlanan gövdenin her satırı HTPB/N₂O olmalı.

        Zilliac & Karabeyoglu 2006 Tablo 2 satırları OKSİJEN deneyleridir;
        beyana sızarlarsa bu bekçi kırmızıya döner.
        """
        assert HTPB_INDEPENDENT_CAMPAIGN_OXIDIZERS == ('n2o',)
        for kampanya in HTPB_INDEPENDENT_CAMPAIGNS:
            assert kampanya['oxidizer'] == 'n2o', kampanya

    def test_n2o_kosusunda_zarf_eslesiyor(self):
        p = _bias_params('n2o')
        assert p['run_oxidizer'] == 'n2o'
        assert p['campaign_scope_match'] is True
        assert p['campaign_scope_reason'] is None

    @pytest.mark.parametrize('oxidizer', ['lox', 'h2o2'])
    def test_zarf_disi_kosuda_eslesme_yalani_yok(self, oxidizer):
        """ÖLÇÜLEN KUSUR (once.json C): lox ve h2o2 koşularında N₂O bandı,
        zarfı söylenmeden yayımlanıyordu."""
        p = _bias_params(oxidizer)
        assert p['run_oxidizer'] == oxidizer
        assert p['campaign_scope_match'] is False
        gerekce = p['campaign_scope_reason']
        assert isinstance(gerekce, str) and gerekce
        # Gerekçe hem zarfı hem koşuyu ADIYLA söylemeli — genel metin yetmez.
        assert 'n2o' in gerekce
        assert oxidizer in gerekce

    @pytest.mark.parametrize('oxidizer', ['n2o', 'lox', 'h2o2'])
    def test_zarf_alanlari_her_kosuda_var(self, oxidizer):
        """Alanlar YALNIZ eşleşmeyen koşuda değil, HER koşuda bulunur:
        tüketici alanın yokluğunu 'eşleşiyor' diye okuyamamalı."""
        p = _bias_params(oxidizer)
        for alan in ('run_oxidizer', 'campaign_oxidizer_scope',
                     'campaign_scope_match', 'campaign_scope_reason'):
            assert alan in p, alan
        assert tuple(p['campaign_oxidizer_scope']) == (
            HTPB_INDEPENDENT_CAMPAIGN_OXIDIZERS)

    @pytest.mark.parametrize('oxidizer', ['n2o', 'lox', 'h2o2'])
    def test_katsayi_ve_bant_DEGISMEDI(self, oxidizer):
        """Onarım bir BEYAN onarımıdır: hiçbir sayı değişmez, bant susmaz.

        Ölçülen (once.json ⟷ sonra.json C): eski alanların hepsi bit-aynı.
        """
        p = _bias_params(oxidizer)
        assert p['bias_pct'] == HTPB_COEFF_DB_BIAS_PCT == -39.5
        assert tuple(p['independent_campaign_bias_band_pct']) == (
            HTPB_INDEPENDENT_CAMPAIGN_BIAS_BAND_PCT) == (-50.6, -41.8)
        assert p['reconciled'] is False
        # Bant zarf dışında da YAYIMLANIR (susturmak, yürürlükteki katsayının
        # ölçülmüş yanlılığını gizlemek olurdu) — yalnız 'bu koşuya ait'
        # diye okunamaz.
        assert p['independent_pool_points'] == 46


# ---------------------------------------------------------------------------
# OH-D26-04 — D31 DEVRİ: beyanın çürümesini engelleyen gerileme kalkanı
# ---------------------------------------------------------------------------
class TestOhD2604KanalGeometrisiBeyani:

    def test_denklik_sinifi_esplemeden_turetilir(self):
        beklenen = {
            sinif: tuple(sorted(
                k for k in COOLING_CHANNEL_GEOMETRY_SELECTIONS
                if COOLING_CHANNEL_TO_TYPE[k] == sinif))
            for sinif in sorted(set(COOLING_CHANNEL_TO_TYPE.values()))
        }
        beklenen = {k: v for k, v in beklenen.items() if v}
        assert COOLING_GEOMETRY_EQUIVALENCE == beklenen

    def test_radial_ve_spiral_ayni_sinifa_duser(self):
        assert COOLING_CHANNEL_TO_TYPE['radial'] == 'regenerative'
        assert COOLING_CHANNEL_TO_TYPE['spiral'] == 'regenerative'

    @pytest.mark.parametrize('secim,es', [('radial', 'spiral'),
                                          ('spiral', 'radial')])
    def test_beyan_not_modelled_ve_esini_adiyla_soyler(self, secim, es):
        _, sonuc = _kos(cooling_type=secim)
        blok = sonuc.get('cooling_channel_geometry')
        assert blok is not None, (
            'cooling_channel_geometry bloğu yanıtta YOK — D31 beyanı çürümüş.')
        assert blok['requested'] == secim
        assert blok['resolved_class'] == 'regenerative'
        assert blok['modelled'] is False
        assert blok['status'] == 'NOT_MODELLED'
        assert es in tuple(blok['indistinguishable_from'])
        # Eksik girdiler ADIYLA durur: 2.7 fizik dalgasının kapsamı budur.
        assert len(blok['missing_inputs_for_geometry_model']) == 4

    def test_uyari_makine_okur_alani_tasiyor(self):
        _, sonuc = _kos(cooling_type='radial')
        u = _uyari(sonuc, 'warn.hybrid.cooling_channels_assumed')
        assert u is not None
        p = u['params']
        assert p['geometry_modelled'] is False
        assert p['resolved_class'] == 'regenerative'
        assert 'spiral' in tuple(p['indistinguishable_from'])

    def test_fizik_yapragi_farki_sifir_kalir(self):
        """ÖLÇÜLDÜ (once.json A): radial ⟷ spiral 37.374 ortak yaprağın
        yalnız 18'inde ayrışıyor ve 18'i de KELİMENİN echo'su.

        Bu bekçi kalemi kapatmaz — kalemin GEREKÇESİNİ canlı tutar. Fizik
        yaprağı ayrışmaya başlarsa (2.7'de Dean modeli gelirse) burası
        kırmızıya döner ve beyan güncellenmek ZORUNDA kalır.
        """
        _, r = _kos(cooling_type='radial')
        _, s = _kos(cooling_type='spiral')
        ry, sy = dict(_yapraklar(r)), dict(_yapraklar(s))
        farkli = sorted(k for k in (set(ry) & set(sy)) if ry[k] != sy[k])
        echo = ('geometry', 'requested', 'indistinguishable_from')
        fizik = [k for k in farkli if not any(e in k for e in echo)]
        assert fizik == [], (
            'Kanal geometrisi artık bir FİZİK yaprağını değiştiriyor: %s. '
            'OH-D26-04 beyanı (NOT_MODELLED) artık doğru DEĞİL.' % fizik[:10])


# ---------------------------------------------------------------------------
# P12bB3-02 — D31 DEVRİ: red gerekçeleri tek genel metne çökmesin
# ---------------------------------------------------------------------------
class TestP12bB302YakitRedGerekceleri:

    @pytest.mark.parametrize('yakit,gerekce', [
        ('al2o3', 'not_a_fuel'),
        ('carbon', 'no_peer_reviewed_correlation'),
        ('mixture', 'no_request_contract'),
        ('custom', 'no_request_contract'),
    ])
    def test_red_gerekcesi_adiyla_durur(self, yakit, gerekce):
        from hrma.engines.combustion_analysis import (
            HYBRID_FUEL_REJECTION_REASONS)
        kayit = HYBRID_FUEL_REJECTION_REASONS.get(yakit)
        assert kayit is not None, (
            '%s için adlandırılmış red gerekçesi YOK — D31 onarımı çürümüş.'
            % yakit)
        # Kayıt (reason, explanation) çiftidir.
        assert kayit[0] == gerekce
        # Açıklama GENEL metin olamaz: reddin NEDEN'ini anlatmalı.
        assert isinstance(kayit[1], str) and len(kayit[1]) > 60

    def test_uc_ayri_gerekce_sinifi_korunur(self):
        """D31 ÖNCESİ ölçüm: ayrı gerekçe sayısı 1 (dördü de aynı metin)."""
        from hrma.engines.combustion_analysis import (
            HYBRID_FUEL_REJECTION_REASONS)
        sinif = {HYBRID_FUEL_REJECTION_REASONS[y][0]
                 for y in ('al2o3', 'carbon', 'mixture', 'custom')}
        # D31 ÖNCESİ bu küme tek elemanlıydı.
        assert len(sinif) == 3
        assert sinif == {'not_a_fuel', 'no_peer_reviewed_correlation',
                         'no_request_contract'}

    def test_hicbir_yakit_sessizce_ACILMADI(self):
        """Doktrin 1: kaynak borcu ödenmeden yakıt açılmaz."""
        from hrma.engines.combustion_analysis import (
            SUPPORTED_HYBRID_FUEL_KEYS)
        for kapali in ('al2o3', 'carbon', 'mixture', 'custom'):
            assert kapali not in SUPPORTED_HYBRID_FUEL_KEYS, kapali


# ---------------------------------------------------------------------------
# OH-D31-10 — KAPANDI (ÖH D32 fix-35d): tel biçimi reddi TEK gerekçe kodu
# ---------------------------------------------------------------------------
class TestOhD3110TelBicimiGerekceKodu:
    """Aynı kural, aynı hüküm, İKİ AYRI makine-okur kod.

    ÖLÇÜLDÜ (``once.json`` D, taban ``dd1dcddc``) — sayı-benzeri DİZE:

        POST /calculate         {chamber_pressure: '20.0'} -> 400
            invalid_fields[0].reason == 'not_a_number'
        POST /calculate_liquid  {chamber_pressure: '100'}  -> 400
            invalid_fields[0].reason == 'not_a_json_number'

    Hüküm AYNI (ikisi de reddediyor, kanon budur), fakat ``reason`` üzerinden
    dallanan bir tüketici tek kural için İKİ kod görüyor. Tek kaynak
    ``hrma/utils/input_guard.is_json_number`` ve kanonik ad
    ``not_a_json_number``dır.

    BORÇ İMİ KALKTI (ÖH D32 fix-35d, 15 Eylül 2026 — ana model hükmü).
    Hibrit a1 bu kalemi ENGELLİ bırakmıştı, çünkü ``not_a_number`` kodunu
    üreten yer ``hrma/validation/motor_validation.py`` (:483, :722) ve o
    dosya D32'de app-api-dogrulama kulvarının sahasındaydı. Kulvar kapandı
    ve kanon karara bağlandı: tel-biçimi reddinin adı MERKEZİN adıdır
    (``input_guard.is_json_number`` -> ``not_a_json_number``); ``bool``
    kendi adıyla (``boolean_is_not_a_number``); sonlu olmayan SAYI
    ``not_finite``. ``not_a_number`` bu kapıda EMEKLİDİR. Onarım
    ``hrma/app.py::_collect_unphysical_fields`` ve adı geçen iki
    ``motor_validation`` satırında yapıldı; ``strict=True`` imi kalktığı
    için bekçi artık GERÇEKTEN yeşildir, sessizce yeşile dönmüş değildir.
    """

    def test_iki_calculate_ucu_ayni_gerekce_kodunu_yayimlar(self):
        import contextlib as _c
        import io as _io
        with _c.redirect_stdout(_io.StringIO()):
            from hrma.app import app
        app.config['TESTING'] = True
        istemci = app.test_client()

        # ROTA LİTERALİ (ÖH D32 fix-35d): eski gövde rotayı İÇ İÇE bir
        # yardımcının PARAMETRESİNDEN alıyordu (``_kod(yol, yuk)``). Uç
        # envanteri (OH-D23-12) modül düzeyi yardımcıların parametrelerini
        # çağrı yerindeki literallere bağlayabiliyor ama fonksiyon İÇİNDE
        # tanımlanan yardımcıyı çözemiyor; çağrı 'çözülemeyen rota' olarak
        # sayılıyor ve ÖLÇÜLDÜ ki tavan bu yüzden 39'dan 40'a çıkmıştı
        # (taban ``dd1dcddc`` 39 ile YEŞİL). Tavan GEVŞETİLMEDİ; çağrı
        # literal yazıldı, böylece bu bekçinin kilitlediği iki uç envanterde
        # görünür.
        def _kod(yanit, yol):
            assert yanit.status_code == 400, (yol, yanit.status_code)
            alanlar = (yanit.get_json() or {}).get('invalid_fields') or []
            assert alanlar, yol
            return alanlar[0].get('reason')

        with _c.redirect_stdout(_io.StringIO()), \
                _c.redirect_stderr(_io.StringIO()):
            y_hibrit = istemci.post('/calculate', json={
                'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
                'chamber_pressure': '20.0', 'fuel_type': 'htpb',
                'oxidizer_type': 'n2o'})
            y_sivi = istemci.post('/calculate_liquid', json={
                'motor_name': 'X', 'thrust': 10000.0, 'burn_time': 30.0,
                'chamber_pressure': '100', 'mixture_ratio': 2.2,
                'fuel_type': 'rp1', 'oxidizer_type': 'lox',
                'expansion_ratio': 12.0})
        hibrit = _kod(y_hibrit, '/calculate')
        sivi = _kod(y_sivi, '/calculate_liquid')
        assert hibrit == sivi == 'not_a_json_number', (hibrit, sivi)
