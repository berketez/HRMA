# -*- coding: utf-8 -*-
"""Fırlatma sahası küresi — gerçek tarayıcıda ÖLÇÜLMÜŞ dört kusurun kilidi.

Bulgular tahmin değil, Chrome'da ölçüldü. Her assert tek bir ölçümü kilitler;
düzeltme geri alınırsa ilgili test KIRILIR:

  1. renderer.outputEncoding yoktu. Dokular bilerek sRGB işaretleniyor
     (`tex.encoding = THREE.sRGBEncoding`), yani shader girişinde lineere
     çözülüyorlar; çıkışta geri kodlanmayınca kare gamma kadar karanlık
     kalıyordu (ölçülen luma medyanı 15,4; olması gereken 36,1). Aynı depoda
     motor_viz3d.js:1625 bunu doğru yapıyor — küre ondan sapmamalı.

  2. "Tüm Dünya" görünümü küreyi kırpıyordu: mesafe sabit 2,6R idi, kürenin
     açısal yarıçapı asin(100/260) = 22,62°, dikey yarı-FOV ise 19,00° →
     dikeyde %19 taşma. Mesafe artık en-boy oranına duyarlı globalViewDist()
     ile türetiliyor.

  3. GIBS karo kapısı hiç açılmıyordu: kapı ile "doku detayı yok" notu AYNI
     sabiti (TEXTURE_NOTE_ALT_M = 400 km) paylaşıyordu, oysa "Fly this site"
     kamerayı ~466 km'ye koyuyor → karo isteği 0. Kapı kendi sabitine
     (TILE_ACTIVE_ALT_M = 1500 km) taşındı; not eşiği 400 km'de KALMALI.

  4. Yanma sonu işaretçisi çözücü çıktısı değil, kullanıcının girdiği yanma
     süresinden türüyor. Etiket bunu söylemek zorunda (site.burnoutFromInput).

Bağımsız kod incelemesinden (2026-08-14) gelen üç kusur daha eklendi:

  5. Tuval saydam temizleniyordu -> arkadaki theme.css gövde süsü (16 uydurma
     yıldız + 3 nebula) gökyüzü sanılıyordu; üstelik ESO/Yale atfı gökyüzü hiç
     yüklenmeden de basılıyordu (yanlış beyan).
  6. _resize kullanıcının yakınlaşmasını siliyordu: _mode yalnız düğmelerle
     değişiyordu, tekerlek zoom'undan sonra ilk pencere boyutlaması kamerayı
     tüm-Dünya mesafesine fırlatıyordu.
  7. sRGB çıkışı düz malzeme renklerini açıyordu (0xff8c33 -> #ffc47c); HTML
     lejantı ham hex bastığı için sahne ile lejant uyuşmuyordu.

Testler kaynak-seviyesindedir (tarayıcı gerekmez); geometri iddiası ayrıca
globalViewDist fonksiyonu node ile izole çalıştırılarak sayısal doğrulanır.
"""

import json
import math
import pathlib
import re
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
GLOBE_JS = ROOT / 'hrma/static/js/launch_site_globe.js'
SITE_HTML = ROOT / 'hrma/templates/launch_site.html'
NODE = shutil.which('node')


def _globe_src():
    return GLOBE_JS.read_text(encoding='utf-8')


def _prototype_body(src, name):
    """LaunchSiteGlobe.prototype.<name> gövdesini kaba metin olarak döndürür."""
    marker = 'LaunchSiteGlobe.prototype.%s = function' % name
    assert marker in src, '%s bulunamadı' % marker
    tail = src.split(marker, 1)[1]
    nxt = tail.find('LaunchSiteGlobe.prototype.')
    return tail if nxt < 0 else tail[:nxt]


def _code_lines(text):
    """Tam satırlık `//` yorumlarını atar — iddiayı YORUMDAN değil KODDAN kurar."""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith('//') or s.startswith('*') or s.startswith('/*'):
            continue
        out.append(line.split('//', 1)[0])
    return '\n'.join(out)


# ---------------------------------------------------------------------------
# 1) sRGB çıkış kodlaması
# ---------------------------------------------------------------------------

def test_srgb_cikis_kodlamasi():
    """Dokular sRGB çözülüyorsa çıkış da sRGB kodlanmalı (karanlık kare kilidi)."""
    src = _globe_src()
    kod = _code_lines(src)
    assert re.search(r'renderer\.outputEncoding\s*=\s*THREE\.sRGBEncoding', kod), \
        'renderer.outputEncoding = THREE.sRGBEncoding yok — kare gamma kadar karanlık kalır'
    # Kusurun ön koşulu hâlâ geçerli mi: dokular gerçekten sRGB işaretleniyor mu?
    assert kod.count('tex.encoding = THREE.sRGBEncoding') >= 2, \
        'doku sRGB işaretlemesi kaybolmuş — bu testin dayanağı değişti, gözden geçir'


# ---------------------------------------------------------------------------
# 2) "Tüm Dünya" çerçevelemesi
# ---------------------------------------------------------------------------

def test_tum_dunya_sabit_mesafe_kalkti():
    """Kırpan sabit (2.6R) gitmiş ve yerine en-boy duyarlı fonksiyon gelmiş olmalı."""
    src = _globe_src()
    kod = _code_lines(src)
    assert 'GLOBE_R * 2.6' not in kod, \
        'kürenin %19 kırpıldığı sabit mesafe (GLOBE_R * 2.6) geri gelmiş'
    assert 'GLOBAL_DIST' not in kod, 'GLOBAL_DIST sabiti geri gelmiş'
    assert re.search(r'function\s+globalViewDist\s*\(', kod), 'globalViewDist tanımlı değil'


def test_tum_dunya_mesafesi_uc_yerde_de_kullaniliyor():
    """Başlangıç konumu, viewGlobe ve _resize aynı çerçeveleme kuralını kullanmalı."""
    src = _globe_src()
    kod = _code_lines(src)
    # tanım + üç çağrı
    assert kod.count('globalViewDist(') >= 4, \
        'globalViewDist çağrı sayısı beklenenden az (başlangıç/viewGlobe/_resize)'
    assert 'globalViewDist(camera)' in kod, 'başlangıç kamera konumu fonksiyonu kullanmıyor'
    assert 'globalViewDist(this.camera)' in _code_lines(_prototype_body(src, 'viewGlobe')), \
        'viewGlobe hâlâ sabit mesafe kullanıyor'
    resize = _code_lines(_prototype_body(src, '_resize'))
    assert 'globalViewDist(this.camera)' in resize, \
        '_resize en-boy oranı değişince global görünümü yeniden çerçevelemiyor'
    assert re.search(r"_mode\s*===\s*'global'", resize), \
        '_resize yeniden çerçevelemeyi global kipe koşullamıyor'
    assert resize.index('camera.aspect') < resize.index('globalViewDist'), \
        'mesafe, aspect güncellenmeden hesaplanıyor (eski en-boy oranıyla çerçeveler)'


@pytest.mark.skipif(NODE is None, reason='node bulunamadı')
@pytest.mark.parametrize('aspect', [0.6, 0.8, 1.0, 16 / 9.0, 21 / 9.0, 3.0])
def test_kure_cerceveye_sigiyor(aspect):
    """Ölçülen kusur: asin(R/d) > yarı-FOV → taşma. Yeni mesafede taşma olmamalı."""
    src = _globe_src()
    fn = re.search(r'function globalViewDist\(camera\) \{.*?\n    \}', src, re.S)
    assert fn, 'globalViewDist gövdesi ayıklanamadı'
    consts = []
    for name in ('GLOBE_R', 'CTRL_MAX_TARGET'):
        m = re.search(r'var %s = [^;]+;' % name, src)
        assert m, 'sabit bulunamadı: %s' % name
        consts.append(m.group(0))
    script = '\n'.join([
        'function deg2rad(d) { return d * Math.PI / 180.0; }',
        *consts,
        fn.group(0),
        'var cam = { fov: 38, aspect: %r };' % aspect,
        'process.stdout.write(JSON.stringify(globalViewDist(cam)));',
    ])
    r = subprocess.run([NODE], input=script, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[:800]
    dist = json.loads(r.stdout)

    half_v = math.radians(38) / 2
    half_h = math.atan(math.tan(half_v) * aspect)
    ang_r = math.asin(100.0 / dist)          # kürenin açısal yarıçapı (GLOBE_R = 100)
    assert ang_r < min(half_v, half_h), \
        'küre çerçeveyi taşıyor: asin(R/d)=%.2f° > yarı-FOV %.2f°' % (
            math.degrees(ang_r), math.degrees(min(half_v, half_h)))
    assert dist <= 600.0, 'mesafe OrbitControls üst sınırını (CTRL_MAX_TARGET) aşıyor'


# ---------------------------------------------------------------------------
# 3) GIBS karo kapısı
# ---------------------------------------------------------------------------

def test_karo_kapisi_kendi_sabitine_sahip():
    """Kapı 400 km'de kaldığı sürece 'Fly this site' (~466 km) hiç karo istemez."""
    src = _globe_src()
    kod = _code_lines(src)
    m = re.search(r'var TILE_ACTIVE_ALT_M = ([0-9.eE+]+);', kod)
    assert m, 'TILE_ACTIVE_ALT_M tanımlı değil'
    assert float(m.group(1)) > 466000.0, \
        'karo kapısı "Fly this site" kamera yüksekliğinin (~466 km) altında kalmış'

    govde = _code_lines(_prototype_body(src, '_updateTilePatch'))
    kapilar = [ln for ln in govde.splitlines() if 'camAltitudeM' in ln]
    assert kapilar, '_updateTilePatch içinde yükseklik kapısı bulunamadı'
    for ln in kapilar:
        assert 'TILE_ACTIVE_ALT_M' in ln, 'karo kapısı TILE_ACTIVE_ALT_M kullanmıyor: %s' % ln.strip()
        assert 'TEXTURE_NOTE_ALT_M' not in ln, \
            'karo kapısı yeniden uyarı notu eşiğine bağlanmış: %s' % ln.strip()


def test_not_esigi_400_kmde_kaldi():
    """Uyarı notu ile karo kapısı AYRI işler; not eşiği kaydırılmamalı."""
    src = _globe_src()
    kod = _code_lines(src)
    m = re.search(r'var TEXTURE_NOTE_ALT_M = ([0-9.eE+]+);', kod)
    assert m and float(m.group(1)) == 400000.0, 'TEXTURE_NOTE_ALT_M 400 km olmalı'
    scale = _code_lines(_prototype_body(src, 'getScaleInfo'))
    assert 'TEXTURE_NOTE_ALT_M' in scale, 'getScaleInfo not eşiğini kullanmıyor'
    assert 'TILE_ACTIVE_ALT_M' not in scale, \
        'not eşiği karo kapısına bağlanmış — iki iş yine tek sabite düşmüş'


# ---------------------------------------------------------------------------
# 4) Yanma sonu etiketinin dürüstlüğü
# ---------------------------------------------------------------------------

def test_burnout_etiketi_girdi_kaynagini_soyluyor():
    """burn_time GİRDİdir; işaretçi ölçülmüş olay sanılmasın diye etiketlenir.

    DAYANAK ASSERT'İ YORUMLA TATMİN OLUYORDU (hakem, 2026-08-14): aynı metin
    HTML'de hem gerçek atama satırında hem de bir açıklama yorumunda geçiyor;
    gerçek satır silindiğinde (işaretçi artık HİÇ çizilmiyorken) test yeşil
    kalıyordu. Artık satır başına çapalı ve noktalı virgülle biten GERÇEK
    ifade aranıyor — yorum içindeki geçiş bu deseni sağlamaz.
    """
    html = SITE_HTML.read_text(encoding='utf-8')
    assert 'site.burnoutFromInput' in html, \
        'yanma sonu etiketi girdi kaynağını beyan etmiyor'
    assert re.search(r'^\s*globe\.opts\.burnTime\s*=\s*body\.burn_time\s*;', html, re.M), \
        'burnTime artık girdiden gelmiyorsa bu testin dayanağı değişti, gözden geçir'
    m = re.search(r"e\.key === 'burnout'", html)
    assert m, 'beyan yalnız burnout olayına bağlanmamış'


# ---------------------------------------------------------------------------
# 5) Sahte CSS yıldız alanı (bağımsız inceleme, 2026-08-14)
# ---------------------------------------------------------------------------

def test_tuval_opak_temizleniyor():
    """Saydam tuval theme.css'in UYDURMA yıldızlarını gökyüzü diye gösteriyordu.

    theme.css `body` arka planı prosedürel gradyanlarla 16 yıldız + 3 nebula
    basar; launch_site.html'in satır içi `body` kuralı bağlantıdan ÖNCE geldiği
    için kaskadı kaybediyor. Tuval saydam olduğu sürece (setClearColor alfası 0)
    Samanyolu dokusu yüklenene kadar — yüklenemezse sürekli — ekranda görünen
    gökyüzü sahteydi ve kamerayla dönmüyordu.
    """
    kod = _code_lines(_globe_src())
    m = re.search(r'renderer\.setClearColor\(\s*0x[0-9a-fA-F]+\s*,\s*([0-9.]+)\s*\)', kod)
    assert m, 'setClearColor çağrısı bulunamadı'
    assert float(m.group(1)) == 1.0, (
        'Tuval saydam temizleniyor (alfa %s): arkadaki CSS yıldız alanı gökyüzü '
        'sanılır. Gökyüzü YALNIZ sahne içi gerçek varlıklardan gelmeli; hiçbiri '
        'yüklenemezse ekran siyah kalmalı.' % m.group(1))


def test_sahne_zemini_css_yildizlarini_ortuyor():
    """WebGL hiç başlamazsa (tuval yok) bile bu sayfada CSS yıldızları görünmesin."""
    html = SITE_HTML.read_text(encoding='utf-8')
    m = re.search(r'#ls-stage\s*\{[^}]*\}', html)
    assert m, '#ls-stage kuralı bulunamadı'
    assert 'background' in m.group(0), (
        '#ls-stage kendi koyu zeminini basmıyor; WebGL başlatılamadığında '
        'theme.css gövde süsü (sahte yıldızlar) sahne alanında görünür.')


def test_gokyuzu_atfi_sahne_yuklenmeden_gosterilmiyor():
    """ESO/Yale atfı ve epoch satırı KOŞULSUZ basılıyordu — yanlış beyan.

    Doku ve katalog zaman uyumsuz yüklenir ve ikisi de başarısız olabilir
    (çevrimdışı kurulum, eksik varlık). O durumda gökyüzü hiç çizilmezken
    "gökyüzü ESO panoramasıdır" demek kullanıcıyı yanıltır.
    """
    html = SITE_HTML.read_text(encoding='utf-8')
    assert 'id="ls-sky-attr"' in html, 'atıf div\'inin kimliği yok (gizlenemez)'
    for kimlik in ('ls-skynote', 'ls-sky-attr'):
        m = re.search(r'id="%s"[^>]*style="([^"]*)"' % kimlik, html)
        assert m and 'display:none' in m.group(1).replace(' ', ''), \
            '%s başlangıçta gizli değil — gökyüzü yokken de beyan basılır' % kimlik
    assert re.search(r'sky\.milkyWay', html) and re.search(r'sky\.starCount\s*>\s*0', html), (
        'Beyan sahnenin gerçek durumuna (Samanyolu mesh\'i ya da yıldız sayısı) '
        'bağlanmamış.')


# ---------------------------------------------------------------------------
# 6) Kullanıcı zoom'u ve lejant-sahne renk eşleşmesi (aynı inceleme)
# ---------------------------------------------------------------------------

def test_kullanici_etkilesimi_kipi_serbest_birakiyor():
    """_resize kullanıcının yakınlaşmasını siliyordu (regresyon).

    _mode yalnız viewGlobe/viewSite ile değişiyordu; açılıştaki 'global' kipte
    kullanıcı tekerlekle yakınlaşsa da kip aynı kalıyor ve herhangi bir pencere
    boyutlaması kamerayı tüm-Dünya mesafesine geri fırlatıyordu.
    """
    kod = _code_lines(_globe_src())
    assert re.search(r"addEventListener\(\s*'start'", kod), (
        "OrbitControls 'start' olayı dinlenmiyor; kullanıcı etkileşimi kipi "
        'serbest bırakmıyor.')
    assert re.search(r"_mode\s*=\s*'free'", kod), \
        "Kullanıcı etkileşiminde _mode 'free' yapılmıyor — _resize zoom'u siler."
    baglama = _code_lines(_prototype_body(_globe_src(), '_bindEvents'))
    assert re.search(r"addEventListener\(\s*'start'", baglama), \
        'Dinleyici olay bağlama fonksiyonunda (_bindEvents) kurulmuyor'


def test_duz_malzeme_renkleri_lineere_ceviriliyor():
    """Çıkış sRGB kodlanınca ham hex açılıyor; lejant CSS'i sRGB hex basıyor.

    Ölçülen: 0xff8c33 ekranda #ffc47c, 0x2dd4a8 ekranda #75ebd4. Lejant çipleri
    ve olay noktaları AYNI hex'i CSS ile bastığı için iki taraf tutmuyordu.
    Dokulara uygulanmaz (tex.encoding = sRGBEncoding zaten var) — bu yüzden
    yardımcı yalnız düz renkli malzemelerde geçmeli.
    """
    src = _globe_src()
    kod = _code_lines(src)
    assert re.search(r'function\s+srgb\s*\(\s*hex\s*\)', kod), \
        'srgb() yardımcısı yok; dönüşüm sekiz yerde elle yazılmış olabilir'
    assert 'convertSRGBToLinear' in kod, 'lineere çevirme çağrısı yok'
    roket = _code_lines(_prototype_body(src, '_buildFlightGeometry'))
    assert roket.count('srgb(') >= 5, (
        'Uçuş yolu/iz/yer izi çizgileri ve roket gövde/burun/kanat renkleri '
        'lineere çevrilmiyor (srgb() sayısı %d)' % roket.count('srgb('))
    olay = _code_lines(_prototype_body(src, '_buildEventMarkers'))
    assert re.search(r'color:\s*srgb\(\s*color\s*\)', olay), \
        'Olay işaretçisi rengi lineere çevrilmiyor — lejant noktasıyla uyuşmaz'
    marker = _code_lines(_prototype_body(src, '_buildMarker'))
    assert marker.count('srgb(') >= 2, \
        'Saha iğnesi ve halkası lineere çevrilmiyor'
