"""ÖH Dalga-27 · electron a1 — OH-D26-18 bekçileri.

KALEM
-----
**OH-D26-18** (OH-B3-02 dağıtımının electron payı, defter P13B4-01):
``/api/update/check`` yanıtı ``source`` alanını yayımlıyor —
``"api"`` (GitHub Releases API'si), ``"page"`` (API'ye ulaşılamayınca
devreye giren YEDEK sayfa okuması) ya da ``None`` — ama ne
``settings_panel.js`` ne ``update_check.js`` onu basıyordu.

ÖLÇÜLDÜ (``docs/scofield/raw/OH/D27/electron/a1/once.json`` -> ``sonra.json``;
gerçek iki betiği asgari bir DOM ikizinde koşturan ``kabuk_iskele.js``,
iki dil, yedi senaryo):

======================================  =====  =====
ölçüt                                   önce   sonra
======================================  =====  =====
kaynak beyanı (ayarlar penceresi)         0      1
kaynak beyanı (güncelleme penceresi)      0      1
API yolu ile YEDEK yol ekranda ayrılıyor  yok    var
sunucu alanı hiç göndermezse beyan        yok    var
``source`` panellerin okuma envanterinde  yok    var
======================================  =====  =====

Yani kullanıcı "yeni sürüm var" / "güncelsiniz" cümlesinin GitHub API'sinden
mi yoksa yedek sayfa okumasından mı geldiğini göremiyordu; iki yolun ekran
çıktısı BİRBİRİNİN AYNIsıydı.

Bu bekçi kaynak metnini DEĞİL ürünün çıktısını sınar: ikizde asıl
``settings_panel.js`` / ``update_check.js`` koşar, ``/api/update/check``
yanıtı senaryodan gelir ve ekrana basılan metinler toplanır.

Ham kanıt: ``docs/scofield/raw/OH/D27/electron/a1/``
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess

import pytest
from tests.support.kanit import kanit_gerekli

REPO = pathlib.Path(__file__).resolve().parents[1]
JS = REPO / 'hrma' / 'static' / 'js'
KANIT = REPO / 'docs' / 'scofield' / 'raw' / 'OH' / 'D27' / 'electron' / 'a1'
ISKELE = KANIT / 'kabuk_iskele.js'
SENARYO = KANIT / 'senaryolar.json'
NODE = shutil.which('node')

needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

#: Kullanıcının GÖRDÜĞÜ yüzeyler: ayarlar penceresi (köprülü ve köprüsüz)
#: ve güncelleme penceresi/bildirimi.
YUZEYLER = ('ayarlar', 'ayarlar_koprusuz', 'pencere')


def _iskele(dil='en', js_kok=None):
    res = subprocess.run(
        [NODE, kanit_gerekli(str(ISKELE)), str(js_kok or JS), kanit_gerekli(str(SENARYO)), dil],
        capture_output=True, text=True, timeout=300)
    assert res.returncode == 0, res.stderr[-3000:]
    return json.loads(res.stdout.strip().splitlines()[-1])


@pytest.fixture(scope='module')
def ekran():
    if NODE is None:
        pytest.skip('node kurulu değil')
    return {dil: _iskele(dil) for dil in ('en', 'tr')}


def _metinler(ekran, dil, yuzey, senaryo):
    blok = ekran[dil][yuzey][senaryo]
    assert not blok.get('hata'), blok['hata']
    return [m['metin'] for m in blok['metinler']]


def _beyan(ekran, dil, yuzey, senaryo):
    """Kaynağı ADLANDIRAN satır(lar) — anahtarı ``update.source*``."""
    blok = ekran[dil][yuzey][senaryo]
    assert not blok.get('hata'), blok['hata']
    return [m['metin'] for m in blok['metinler']
            if (m.get('anahtar') or '').startswith('update.source')]


# ===========================================================================
# OH-D26-18 — sürüm bilgisinin kaynağı ekranda
# ===========================================================================
class TestOHD2618KaynakBeyani:
    """Ekran, sürüm iddiasının DAYANAĞINI söylüyor mu?"""

    @needs_node
    @pytest.mark.parametrize('yuzey', YUZEYLER)
    @pytest.mark.parametrize('dil', ('en', 'tr'))
    @pytest.mark.parametrize('senaryo', [
        'api_guncelleme_var', 'sayfa_guncelleme_var',
        'api_guncel', 'sayfa_guncel',
        'kaynak_null', 'alan_hic_yok', 'bilinmeyen_kod'])
    def test_her_yanitta_kaynak_beyani_var(self, ekran, dil, yuzey, senaryo):
        """ÖNCE (once.json): yedi senaryonun HİÇBİRİNDE beyan yoktu (0).

        Beyan KOŞULSUZdur: yanıt geldiği sürece satır basılır."""
        beyanlar = _beyan(ekran, dil, yuzey, senaryo)
        assert beyanlar, (
            '%s/%s/%s: sürüm bilgisinin kaynağı ekranda hiç söylenmiyor'
            % (dil, yuzey, senaryo))

    @needs_node
    @pytest.mark.parametrize('yuzey', YUZEYLER)
    @pytest.mark.parametrize('dil', ('en', 'tr'))
    @pytest.mark.parametrize('cift', [
        ('api_guncelleme_var', 'sayfa_guncelleme_var'),
        ('api_guncel', 'sayfa_guncel')])
    def test_api_yolu_ile_yedek_yol_ekranda_ayriliyor(self, ekran, dil,
                                                      yuzey, cift):
        """Kusurun TAM tanımı: iki yolun ekran çıktısı aynıydı.

        ÖNCE (once.json): ``ayirt_guncelleme_var`` ve ``ayirt_guncel``
        üç yüzeyde de ``false``. Tek bir sabit cümle basmak bu bekçiyi
        geçemez — ayrım İSTENİR."""
        api, sayfa = cift
        assert (_metinler(ekran, dil, yuzey, api)
                != _metinler(ekran, dil, yuzey, sayfa)), (
            '%s/%s: GitHub API yolu ile YEDEK sayfa okuması ekranda '
            'birbirinden ayrılmıyor' % (dil, yuzey))

    @needs_node
    @pytest.mark.parametrize('yuzey', YUZEYLER)
    @pytest.mark.parametrize('dil', ('en', 'tr'))
    def test_alan_hic_gelmezse_sessiz_kalinmiyor(self, ekran, dil, yuzey):
        """FAIL-CLOSED: sunucu ``source``u HİÇ göndermezse (eski ya da
        aracılı sunucu) blok sessizce boş kalmaz, durum söylenir."""
        beyanlar = _beyan(ekran, dil, yuzey, 'alan_hic_yok')
        assert beyanlar, (
            '%s/%s: alan gelmediğinde ekran susuyor (sağır blok)'
            % (dil, yuzey))
        # Sessizce "API'den geldi" DENMEZ: bilinen yolların cümlesi olamaz.
        api = _beyan(ekran, dil, yuzey, 'api_guncelleme_var')
        sayfa = _beyan(ekran, dil, yuzey, 'sayfa_guncelleme_var')
        assert beyanlar != api and beyanlar != sayfa, (
            '%s/%s: alan yokken bilinen bir yol UYDURULUYOR' % (dil, yuzey))

    @needs_node
    @pytest.mark.parametrize('dil', ('en', 'tr'))
    def test_taninmayan_kod_uydurulmadan_gosteriliyor(self, ekran, dil):
        """Sunucu bu sürümün tanımadığı bir kod bildirirse anlamı
        UYDURULMAZ; kod olduğu gibi ekrana gelir (SAHTE VERİ YASAĞI)."""
        for yuzey in YUZEYLER:
            beyanlar = _beyan(ekran, dil, yuzey, 'bilinmeyen_kod')
            assert beyanlar, '%s/%s: bilinmeyen kod için beyan yok' % (dil, yuzey)
            assert any('mirror' in m for m in beyanlar), (
                '%s/%s: sunucunun bildirdiği kod ekranda geçmiyor: %s'
                % (dil, yuzey, beyanlar))

    @needs_node
    def test_beyan_ceviriliyor(self, ekran):
        """Beyan İngilizce sabit değil: TR kipinde Türkçe basılıyor."""
        for yuzey in YUZEYLER:
            en = _beyan(ekran, 'en', yuzey, 'api_guncelleme_var')
            tr = _beyan(ekran, 'tr', yuzey, 'api_guncelleme_var')
            assert en and tr and en != tr, (
                '%s: kaynak beyanı çevrilmiyor (en=%s, tr=%s)'
                % (yuzey, en, tr))


class TestOHD2618TekKaynak:
    """Sözlük İKİ dosyada yazılmaz (doktrin 4)."""

    def test_kod_cumle_sozlugu_yalniz_update_checkte(self):
        """Kod -> cümle eşlemesi ``update_check.js``tedir; ayarlar paneli
        köprüden okur. Panelde ikinci bir tablo doğarsa iki metin zamanla
        ayrışır.

        Ölçüt KODdur, yorum değil: kusurun anlatıldığı yorum bloğunda
        ``"api" | "page"`` geçiyor ve bu bir sözlük DEĞİL. Yorumlar
        ``test_i18n_common.strip_comments`` ile düşülür (ikinci bir
        ayıklayıcı yazılmaz)."""
        from tests.test_i18n_common import strip_comments
        ham = (JS / 'settings_panel.js').read_text(encoding='utf-8')
        panel = strip_comments(ham)
        assert 'window.HRMAUpdateSource' in panel, (
            'ayarlar paneli köprüyü kullanmıyor')
        for kod in ("'api'", '"api"', "'page'", '"page"'):
            assert kod not in panel, (
                'ayarlar paneline ikinci bir kaynak sözlüğü yazılmış: %s' % kod)

    def test_kopru_veri_ad_alaninda(self):
        """``hrma*`` (küçük harf) ön eki MENÜDEN çağrılan EYLEM köprüleri
        içindir (bkz. tests/test_d24_altyapi_a2.py: menüden çağrılmayan
        ``hrma*`` köprüsü kalmaz). Bu köprü veri/sözlük köprüsüdür, o yüzden
        ``HRMA*`` ad alanında durur — ``HRMABugReport``/``HRMA_SHELL_NAV``
        ile aynı desen."""
        kaynak = (JS / 'update_check.js').read_text(encoding='utf-8')
        assert 'window.HRMAUpdateSource = sourceNote;' in kaynak
        assert 'window.hrmaUpdateSource' not in kaynak


class TestOHD2618BorcImiKalkti:
    """wave4b borç imi ödendi — blok artık CANLI bekçi."""

    def test_settings_update_imi_kaldirildi(self):
        """İm dururken kusur kapansa bile XPASS(strict) süiti kırardı;
        im kalkınca aynı satır kusur GERİ GELİRSE kırmızı verir."""
        from tests import test_wave4b_contract as w4b
        assert 'settings/update' not in w4b.TERS_BORCLU_BLOKLAR, (
            'ödenmiş borç imi hâlâ duruyor')

    def test_odenen_borc_satiri_dustu(self):
        from tests import test_wave4b_contract as w4b
        borc = w4b.TestTersYonBorcEnvanteri.DURUSTLUK_BORCU
        assert 'settings/update' not in borc, (
            'ödenmiş borç satırı envanterde bırakılmış — aynı körlüğü '
            'ileride affeder')

    def test_source_panellerin_okuma_envanterinde(self):
        """Sözleşmenin KENDİ ölçütü (önce: yok)."""
        from tests import test_wave4b_contract as w4b
        envanter = w4b._okuma_envanteri('settings_panel.js', 'update_check.js')
        assert 'source' in envanter


class TestOHD2618KanitHizali:
    """Rapordaki sayılar kanıt dosyalarıyla aynı olmalı."""

    def test_once_sonra_kaydi_var_ve_yonu_dogru(self):
        once = json.loads((kanit_gerekli(KANIT / 'once.json')).read_text(encoding='utf-8'))
        sonra = json.loads((kanit_gerekli(KANIT / 'sonra.json')).read_text(encoding='utf-8'))
        assert once['sozlesme']['envanter_source_okunuyor'] is False
        assert sonra['sozlesme']['envanter_source_okunuyor'] is True
        assert once['sozlesme']['borc_imi_duruyor'] is True
        assert sonra['sozlesme']['borc_imi_duruyor'] is False
        for dil in ('en', 'tr'):
            for yuzey in YUZEYLER:
                o = once['canli'][dil][yuzey]
                s = sonra['canli'][dil][yuzey]
                assert o['ayirt_guncelleme_var'] is False
                assert o['ayirt_guncel'] is False
                assert s['ayirt_guncelleme_var'] is True
                assert s['ayirt_guncel'] is True
                assert o['api_guncelleme_var']['kaynak_beyani_sayisi'] == 0
                assert s['api_guncelleme_var']['kaynak_beyani_sayisi'] >= 1
