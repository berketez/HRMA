# -*- coding: utf-8 -*-
"""ÖH Dalga-31 · kulvar ``arayuz-i18n`` · aşama 1 — bekçiler.

Her bekçi ters-mutasyonla (onarımı geçici geri al → KIRMIZI) kanıtlanmıştır;
kanıt ``docs/scofield/raw/OH/D31/arayuz-i18n/a1/mutasyon.json``.

Kapsanan kalemler
-----------------
* **OH-D30-10** — D30'un ``olcum_p12bb414.js`` süpürmesi ``launch_site.html``
  içindeki BİRLEŞTİRMELİ çağrıyı (``t('site.src.' + src, src)``) literal bir
  anahtar sanıyor, ``site.src.`` diye bir anahtar arıyor ve bulamayınca
  ``sozlukte_olmayan = 1`` yazıyordu. Hüküm-19 bunu ürün kusuru değil ÖLÇÜM
  ARTEFAKTI ilan etti. Artefaktı susturmak yetmez: susturulan yerde GERÇEK bir
  kusur sınıfı var — dinamik önekli çağrının AİLESİ eksikse ekranda ham anahtar
  görünür ve hiçbir literal tarama bunu göremez. Bu yüzden onarım, öneki ölçüm
  dışına atmak değil AİLE ÖLÇÜSÜNE çevirmektir ve bekçiler aileyi hem sözlük
  hem de KOŞULAN DEĞER tarafından kapatır.
* **P5B4-35** (KİLİDİ AÇILAN, Berke 14 Eyl — karar (a)) — karo künyesi metni
  depoda dört yerde yaşıyor. Karar: i18n GÖRÜNTÜNÜN TEK KAYNAĞIDIR
  (ÖH D21 / P12aB4-19 yürürlükte), ``launch_site.html`` gövdesi hidrasyon
  öncesi HUKUKİ EMNİYET YEDEĞİ olarak KALIR, ``tile_cache.LAYERS`` alanı da
  makine künyesidir; iki ayna bekçiyle kaynağa kilitlenir. D26'nın kilidi
  (``test_d26_arayuz_a2.py::TestP5B435AtifKopyalari``) yedeği ``sunucu in
  html`` ile, yani DOSYANIN HERHANGİ BİR YERİNDE arıyordu: metin dosyada
  başka bir yerde (örneğin bir yorumda) geçtiği sürece ``#ls-tile-attr``
  düğümünün gövdesi kaysa bile YEŞİL kalırdı. Buradaki bekçi düğüme çapalıdır.

Node çağrıları ``tests/test_node_cagri_sozlesmesi.py`` sözleşmesine uyar:
betik argv'ye DOSYA YOLU olarak verilir, gövdesi argv'ye gömülmez.
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest
from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
TPL = KOK / 'hrma' / 'templates'
KANIT = KOK / 'docs' / 'scofield' / 'raw' / 'OH' / 'D31' / 'arayuz-i18n' / 'a1'

NODE = shutil.which('node')
node_gerek = pytest.mark.skipif(NODE is None, reason='node kurulu değil')


def oku(p):
    return p.read_text(encoding='utf-8')


def _coz(kacisli):
    """Tek tırnaklı JS dizesindeki kaçışları çözer (\\u ve \\')."""
    def _u(m):
        return chr(int(m.group(1), 16))
    return re.sub(r'\\u([0-9a-fA-F]{4})', _u, kacisli).replace("\\'", "'")


def sozluk_bloklari(src):
    """``en:`` ve ``tr:`` blok gövdelerini döndürür (i18n dosya sözleşmesi)."""
    sinir = src.find('\n        tr: {')
    assert sinir > 0, 'tr bloğu bulunamadı'
    bas = src.find('\n        en: {')
    assert 0 <= bas < sinir, 'en bloğu bulunamadı'
    return src[bas:sinir], src[sinir:]


def nokta_anahtarli_sozluk(src, dil):
    en, tr = sozluk_bloklari(src)
    blok = en if dil == 'en' else tr
    return {
        k: _coz(v)
        for k, v in re.findall(r"'([\w.]+)'\s*:\s*'((?:[^'\\]|\\.)*)'", blok)
    }


# ===========================================================================
# OH-D30-10 — dinamik önekli i18n çağrısı: aile ölçüsü
# ===========================================================================
# ``launch_site.html``:
#     nameEl.textContent = name + ' (' + t('site.src.' + src, src) + ')';
# Burada ``'site.src.'`` bir ANAHTAR değil ÖNEKTİR. Literal tarayan bir ölçüm
# iki yönde de yanılır: (a) öneki eksik anahtar sayar (D30 artefaktı),
# (b) ailenin GERÇEKTEN eksik bir üyesini hiç göremez. İki bekçi ikisini de
# kapatır: birincisi aileyi sözlük tarafından, ikincisi KOŞULAN değer
# tarafından ölçer (D30 dersi 18: kullanıcının koştuğu yolu ölç).

ONEK_CAGRISI = re.compile(r"\bt\s*\(\s*'([\w.]+\.)'\s*\+")


def _dinamik_onekler(html):
    return sorted(set(ONEK_CAGRISI.findall(html)))


class TestOHD3010DinamikOnekAilesi:

    def test_sablon_dinamik_onek_tasiyor(self):
        """Bekçinin konusu var: en az bir birleştirmeli çağrı ölçülüyor.

        Çağrı literale çevrilirse bu test kırmızıya döner ve aşağıdaki iki
        bekçinin sessizce boş kümeye düşmesi (vakum yeşili) engellenir."""
        onekler = _dinamik_onekler(oku(TPL / 'launch_site.html'))
        assert 'site.src.' in onekler, (
            'launch_site.html içindeki dinamik önekli i18n çağrısı kayboldu: '
            f'bulunan önekler {onekler}')

    def test_her_dinamik_onek_ailesi_en_ve_tr_tam(self):
        """Önek ailesi boş ya da yarım olamaz — yarımsa ekranda ham anahtar."""
        html = oku(TPL / 'launch_site.html')
        src = oku(JS / 'i18n_launch_site.js')
        en = nokta_anahtarli_sozluk(src, 'en')
        tr = nokta_anahtarli_sozluk(src, 'tr')
        for onek in _dinamik_onekler(html):
            uyeler = sorted(
                {k for k in list(en) + list(tr)
                 if k.startswith(onek) and len(k) > len(onek)})
            assert uyeler, (
                f"'{onek}' öneki için i18n ailesi BOŞ — ekranda ham anahtar "
                'basılır (fail-closed değil, çirkin düşüş)')
            eksik = [k for k in uyeler if k not in en or k not in tr]
            assert not eksik, (
                f"'{onek}' ailesinin EN/TR karşılığı eksik üyeleri: {eksik}")

    def test_site_src_ailesi_kosulan_kaynak_degerlerini_kapsiyor(self):
        """Aile, ürünün GERÇEKTEN ürettiği ``source`` değerlerini kapsar.

        Değerler ezberden yazılmaz, iki koşulan yoldan okunur:
          * sunucu: ``/api/flight-vehicle`` uç gövdesindeki ``source == '…'``
            dalları (kabul edilen değerler; gerisi 400),
          * arayüz: ``launch_site.html``in kendi ``|| '…'`` yedeği.
        """
        app_src = oku(KOK / 'hrma' / 'app.py')
        bas = app_src.index("@app.route('/api/flight-vehicle'")
        son = app_src.index('@app.route(', bas + 10)
        govde = app_src[bas:son]
        sunucu = set(re.findall(r"source\s*==\s*'(\w+)'", govde))
        assert sunucu, '/api/flight-vehicle kolu `source` dalı taşımıyor'

        html = oku(TPL / 'launch_site.html')
        m = re.search(r"var src = \(v && v\.source\) \|\| '(\w+)';", html)
        assert m, 'launch_site.html araç kaynağı yedeği bulunamadı'
        kosulan = sunucu | {m.group(1)}

        i18n = oku(JS / 'i18n_launch_site.js')
        en = nokta_anahtarli_sozluk(i18n, 'en')
        tr = nokta_anahtarli_sozluk(i18n, 'tr')
        eksik = [d for d in sorted(kosulan)
                 if f'site.src.{d}' not in en or f'site.src.{d}' not in tr]
        assert not eksik, (
            'bu `source` değerleri ekrana ham anahtarla basılır (i18n '
            f'karşılığı yok): {eksik}; koşulan küme {sorted(kosulan)}')

    @node_gerek
    def test_olcum_betigi_onek_artefakti_uretmiyor(self):
        """OH-D30-10'un kendisi: süpürme betiği artık önek uydurmaz."""
        betik = KANIT / 'olcum_ohd3010.js'
        assert kanit_gerekli(betik).exists(), f'ölçüm betiği yok: {betik}'
        ph = subprocess.run([NODE, kanit_gerekli(str(betik)), str(KOK)],
                            capture_output=True, text=True, timeout=120)
        assert ph.returncode == 0, ph.stderr[-2000:]
        d = json.loads(ph.stdout)
        assert d['sozlukte_olmayan'] == 0, (
            'süpürme hâlâ sözlükte olmayan anahtar sayıyor: '
            f"{d['sozlukte_olmayan_anahtarlar']}")
        assert d['dinamik_onek_sayisi'] >= 1, (
            'betik dinamik öneki artık hiç görmüyor — ölçü kör kaldı')
        assert d['bozuk_aile_sayisi'] == 0, (
            f"eksik/boş önek ailesi: {d['bozuk_aileler']}")


# ===========================================================================
# P5B4-35 — karo künyesi: 1 kaynak + 2 bekçili ayna
# ===========================================================================
# Berke kararı (a): görüntünün TEK kaynağı i18n sözlüğüdür. Diğer iki kopya
# SİLİNMEZ çünkü farklı KİND'lerdir — biri hukuki emniyet yedeği (i18n
# yüklenmeden önce NASA GIBS atfı ekranda durmalıdır), diğeri API alanıdır
# (makine okunur sağlayıcı künyesi). Kararın bedeli: her ikisi de kaynağa
# KİLİTLİ olmalı, yoksa dört denetimsiz kopya geri gelir.

ATIF_DUGUMU = re.compile(
    r'<div id="ls-tile-attr"(?P<oz>[^>]*)>(?P<govde>.*?)</div>', re.S)


class TestP5B435KunyeAynasi:

    def _dugum(self):
        m = ATIF_DUGUMU.search(oku(TPL / 'launch_site.html'))
        assert m, 'launch_site.html içinde #ls-tile-attr düğümü yok'
        return m

    def _en_kunye(self, anahtar):
        en = nokta_anahtarli_sozluk(oku(JS / 'i18n_launch_site.js'), 'en')
        assert anahtar in en, f'i18n EN bloğunda {anahtar} yok'
        return en[anahtar]

    def test_yedek_govde_dugume_capali_ve_kaynakla_ayni(self):
        """D26 bekçisinin açığı: ``sunucu in html`` DÜĞÜME çapalı değildi.

        Metin dosyanın herhangi bir yerinde (yorumda bile) geçtiği sürece o
        bekçi yeşil kalır; düğümün gövdesi kayabilirdi. Burada gövde düğümden
        çıkarılır ve düğümün KENDİ ``data-i18n`` anahtarının EN değeriyle
        birebir karşılaştırılır."""
        m = self._dugum()
        oz = re.search(r'data-i18n="([\w.]+)"', m.group('oz'))
        assert oz, '#ls-tile-attr düğümünde data-i18n anahtarı yok'
        assert m.group('govde').strip() == self._en_kunye(oz.group(1)), (
            'hidrasyon öncesi yedek gövde i18n EN kaynağından AYRIŞTI:\n'
            f"  düğüm gövdesi : {m.group('govde').strip()!r}\n"
            f"  i18n EN       : {self._en_kunye(oz.group(1))!r}")

    def test_yedek_dugumun_rolu_ilan_edildi(self):
        """Yedeğin NEDEN durduğu şablonda yazılıdır (karar (a), ii).

        İlan olmadan bir sonraki okuyucu bu gövdeyi "üçüncü kopya" sanıp
        siler; NASA GIBS atfı bir lisans gereğidir ve i18n yüklenmeden önce
        ekranda durmalıdır."""
        html = oku(TPL / 'launch_site.html')
        bas = html.index('<div id="ls-tile-attr"')
        onsoz = html[max(0, bas - 1600):bas]
        assert 'P5B4-35' in onsoz and 'HUKUK' in onsoz.upper(), (
            '#ls-tile-attr gövdesinin "hukuki emniyet yedeği" rolü şablonda '
            'ilan edilmemiş (P5B4-35 karar (a), ii)')

    def test_api_alani_kunye_anahtariyla_kilitli(self):
        """``tile_cache.LAYERS`` künyesi makine alanıdır ve kaynağa kilitli.

        Kilit KATMAN BAŞINA kurulur, tek katmana sabitlenmez: yarın eklenen
        bir katman da ya i18n anahtarına eşit bir künye taşır ya da arayüze
        hiç sunulmaz (fail-closed, P5B4-29)."""
        from hrma.analysis import tile_cache
        for ad, cfg in tile_cache.LAYERS.items():
            anahtar = cfg.get('attribution_i18n_key')
            if anahtar:
                assert cfg.get('attribution') == self._en_kunye(anahtar), (
                    f"{ad}: API künyesi i18n EN kaynağından ayrıştı\n"
                    f"  tile_cache : {cfg.get('attribution')!r}\n"
                    f"  i18n EN    : {self._en_kunye(anahtar)!r}")
            else:
                assert not cfg.get('ui_offered'), (
                    f'{ad}: künye i18n anahtarı YOK ama katman arayüze '
                    'sunuluyor — künyesiz katman çizilemez (fail-closed)')

    def test_ekran_kaynagi_i18n_kalir(self):
        """P12aB4-19 tersine çevrilmedi: küre modülü künye METNİ yayımlamaz.

        Modül yalnız katman -> ANAHTAR eşlemesi taşır; İngilizce künye
        literali oraya geri konursa ekranın kaynağı i18n olmaktan çıkar."""
        globe = oku(JS / 'launch_site_globe.js')
        kunye = self._en_kunye('site.tileAttribution')
        assert kunye not in globe, (
            'launch_site_globe.js künye METNİNİ yeniden taşıyor — görüntünün '
            'tek kaynağı i18n olmalı (ÖH D21 / P12aB4-19)')
        assert "'site.tileAttribution'" in globe, (
            'küre modülünde katman -> künye anahtarı eşlemesi kayboldu')
