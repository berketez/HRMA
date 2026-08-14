# -*- coding: utf-8 -*-
"""Fırlatma sahası küresi — roket modeli, yönelimi ve yay çerçevelemesi (2026-08-14).

NEDEN BU DOSYA VAR
------------------
Küre üzerinde "roket" diye hareket eden şey 12x12 segmentli BEYAZ BİR KÜREYDİ:
yönü yoktu, biçimi yoktu, ekranda ayırt edilemez bir benekti. İkinci kusur
çerçevelemedeydi: viewSite() kamera mesafesini en az 10 sahne birimine (637 km)
zorluyordu, oysa gerçek ölçekte 15,7 km'lik bir sondaj yayı yalnızca 0,247
birimdir — üç olay işaretçisi (kalkış / yanma sonu / apoje) ~10 piksellik tek bir
kümede üst üste biniyordu (ölçüldü).

Düzeltmenin YÖNÜ de kilitlenmelidir, yoksa "görünsün" diye ölçek abartılır:
çözüm rakımı şişirmek DEĞİL, kamerayı yaya göre çerçevelemektir. Bu yüzden
buradaki testler hem yeni geometrinin varlığını hem de tabanın yalnızca uçuş
varken gevşediğini sınar; ayrıca yayın ekranda kapladığı oran, yorumdan değil
kaynaktaki SAYILARDAN (GLOBE_R, R_EARTH_M, kamera FOV) yeniden hesaplanır.

Sahte egzoz kilidi ayrı bir amaca hizmet eder: çözücü egzoz akısı üretmiyor, o
yüzden alev/duman çizilmesi veri değil dekor olurdu.

SONRAKİ DÜZELTME (bağımsız inceleme, 2026-08-14): buradaki ölçek bekçisi ham
`k = 0,006` sayısını kilitliyordu ve YANLIŞ ŞEYİ koruyordu. Ekranda kaplanan
oran uzanım·k çarpımıdır; eski benek 2,00 birim uzanımlıyken yeni siluet 0,87
olduğu için aynı k ile işaretçi 13,9 px'ten 6,1 px'e DÜŞÜYORDU. Bekçi artık
sayıyı değil İDDİAYI kilitliyor: görünür uzanım eski beneğinkinin altına
inemez, ama sembol de devleşemez (k ≤ 0,03).
"""

import math
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
GLOBE_JS = ROOT / 'hrma/static/js/launch_site_globe.js'


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


def _build_body():
    """_buildFlightGeometry gövdesi (yorumsuz).

    _buildEventMarkers AYRI bir prototip fonksiyonudur, bu yüzden gövde onun
    başlangıcında biter: olay işaretçilerinin kendi küreleri buraya karışmaz.
    """
    return _code_lines(_prototype_body(_globe_src(), '_buildFlightGeometry'))


def _roket_blogu():
    """Yalnızca ROKET kurulum bloğu.

    Sınırlar: `var rk = new THREE.Group` ile başlar, `_seekFraction` çağrısında
    biter. Blok bulunamıyorsa roket tek bir Mesh'e geri döndürülmüş demektir —
    o zaten kusurun kendisidir, bu yüzden burada patlar.
    """
    body = _build_body()
    i = body.find('var rk = new THREE.Group')
    assert i >= 0, (
        'Roket bir THREE.Group olarak kurulmalı (burun + gövde + kanatlar); '
        'tek parça Mesh bulundu -> beyaz küreye geri dönülmüş olabilir.')
    j = body.find('_seekFraction', i)
    assert j > i, 'roket bloğunun sonu (_seekFraction çağrısı) bulunamadı'
    return body[i:j]


def _sabit(src, isim):
    m = re.search(r'var\s+%s\s*=\s*([0-9.]+)\s*;' % isim, src)
    assert m, '%s sabiti kaynakta bulunamadı' % isim
    return float(m.group(1))


def _fov():
    """Kameranın dikey görüş açısı [derece] — ekran oranı hesabı için."""
    m = re.search(r'new\s+THREE\.PerspectiveCamera\(\s*([0-9.]+)\s*,', _globe_src())
    assert m, 'kamera FOV değeri bulunamadı'
    return float(m.group(1))


def _roket_dikey_uzanim(blok):
    """Roket silüetinin DİKEY uzanımı [sahne birimi], KAYNAKTAKİ sayılardan.

    Yorumdan okunmaz, geometri çağrılarından türetilir:
      gövde : CylinderGeometry(r, r, H, seg), merkez body.position.y
      burun : ConeGeometry(r, Hn, seg),       merkez nose.position.y -> tepe +Hn/2
      kanat : BoxGeometry(w, Hf, d),          merkez fin.position.set(_, y, _)
    Uzanım = en yüksek üst uç - en alçak alt uç. Geometri değişirse bu sayı da
    değişir; ekran oranı iddiası böylece kaynağa bağlı kalır.
    """
    def num(pat, ne):
        m = re.search(pat, blok)
        assert m, '%s kaynakta bulunamadı' % ne
        return [float(g) for g in m.groups()]

    (h_govde,) = num(r'CylinderGeometry\s*\(\s*[0-9.]+\s*,\s*[0-9.]+\s*,\s*([0-9.]+)\s*,',
                     'gövde silindirinin yüksekliği')
    (y_govde,) = num(r'body\.position\.y\s*=\s*(-?[0-9.]+)', 'gövde y konumu')
    (h_burun,) = num(r'ConeGeometry\s*\(\s*[0-9.]+\s*,\s*([0-9.]+)\s*,', 'burun konisi yüksekliği')
    (y_burun,) = num(r'nose\.position\.y\s*=\s*(-?[0-9.]+)', 'burun y konumu')
    (h_kanat,) = num(r'BoxGeometry\s*\(\s*[0-9.]+\s*,\s*([0-9.]+)\s*,', 'kanat yüksekliği')
    (y_kanat,) = num(r'fin\.position\.set\([^,]+,\s*(-?[0-9.]+)\s*,', 'kanat y konumu')

    ust = max(y_govde + h_govde / 2.0, y_burun + h_burun / 2.0, y_kanat + h_kanat / 2.0)
    alt = min(y_govde - h_govde / 2.0, y_burun - h_burun / 2.0, y_kanat - h_kanat / 2.0)
    return ust - alt


# ---------------------------------------------------------------------------
# Kalem 1 — roket artık beyaz küre değil
# ---------------------------------------------------------------------------

def test_roket_beyaz_kure_degil():
    """12x12 segmentli birim küre roket kurulumundan KALKMIŞ olmalı.

    Kusur buydu: `new THREE.SphereGeometry(1, 12, 12)` + düz beyaz malzeme.
    Kontrol _buildFlightGeometry ile sınırlı; olay işaretçilerinin küreleri
    başka bir fonksiyondadır ve onlara karışılmaz.
    """
    body = _build_body()
    assert not re.search(r'SphereGeometry\s*\(\s*1\s*,\s*12\s*,\s*12\s*\)', body), (
        'Roket yine 12x12 birim küre olarak kuruluyor — hareket eden şey '
        '"roket" değil ayırt edilemez bir benek olur.')
    assert '0xffffff' not in body, (
        'Roketin düz beyaz malzemesi geri gelmiş görünüyor; gövde/burun/kanat '
        'renkleri tema ile uyumlu olmalı.')


def test_olay_isaretcileri_kurcalanmadi():
    """Regex'in kapsamı doğru daraltılmış mı: olay küreleri (1, 14, 14) DURUYOR.

    Bu assert bir "kaçak düzeltme" tuzağını kapatır: yukarıdaki testi geçmenin
    kolay ama yanlış yolu, olay işaretçilerini de silmek ya da segment sayısını
    oynatmaktır.
    """
    ev = _code_lines(_prototype_body(_globe_src(), '_buildEventMarkers'))
    assert re.search(r'SphereGeometry\s*\(\s*1\s*,\s*14\s*,\s*14\s*\)', ev), (
        'Olay işaretçilerinin birim küresi (1, 14, 14) kaybolmuş — roket '
        'düzeltmesi kapsam dışına taşmış.')


def test_roket_govde_burun_kanat_geometrileri():
    """Silueti üç parça kurar: koni (burun) + silindir (gövde) + kutu (kanat)."""
    blok = _roket_blogu()
    assert re.search(r'ConeGeometry\s*\(\s*0\.10\s*,\s*0\.30\s*,\s*12\s*\)', blok), \
        'Burun konisi ConeGeometry(0.10, 0.30, 12) olmalı (tepe y=+0,50).'
    assert re.search(
        r'CylinderGeometry\s*\(\s*0\.10\s*,\s*0\.10\s*,\s*0\.70\s*,\s*12\s*\)', blok), \
        'Gövde CylinderGeometry(0.10, 0.10, 0.70, 12) olmalı (merkez y=0).'
    assert re.search(
        r'BoxGeometry\s*\(\s*0\.016\s*,\s*0\.22\s*,\s*0\.16\s*\)', blok), \
        'Kanatlar ince kutu BoxGeometry(0.016, 0.22, 0.16) olmalı.'


def test_toplam_yukseklik_bir_birim():
    """Siluet parçaları birleşik olsun diye uçlar tutarlı: toplam ~1 birim.

    Gövde 0,70 (merkez 0) -> [-0,35 , +0,35]; koni 0,30, merkezi +0,35 -> tepe
    +0,50. Yani burun ucu ile gövde dibi arası 0,85, kanat dibiyle birlikte
    ~1 birim. Bu sayıların kaynakta durduğunu yukarıdaki test kilitliyor;
    burada tutarlılığı aritmetikle doğruluyoruz.
    """
    blok = _roket_blogu()
    m = re.search(r'nose\.position\.y\s*=\s*([0-9.]+)', blok)
    assert m, 'burun konisinin y konumu bulunamadı'
    koni_merkez = float(m.group(1))
    tepe = koni_merkez + 0.30 / 2.0
    assert abs(tepe - 0.50) < 1e-9, (
        'Burun tepesi y=+0,50 olmalı, hesaplanan %.3f — gövdeyle (üst uç +0,35) '
        'birleşmiyorsa siluet kopuk görünür.' % tepe)


def test_kanatlar_dongude_kuruluyor():
    """Dört kanat DÖNGÜYLE kurulur; dört kopya blok yazılmaz."""
    blok = _roket_blogu()
    assert re.search(r'for\s*\(\s*var\s+fi\s*=\s*0\s*;\s*fi\s*<\s*4\s*;', blok), \
        'Kanatlar 4 adımlı bir for döngüsüyle kurulmalı.'
    assert blok.count('BoxGeometry') == 1, (
        'BoxGeometry %d kez geçiyor — kanatlar kopyala-yapıştır dört blok '
        'hâline gelmiş.' % blok.count('BoxGeometry'))
    assert re.search(r'Math\.PI\s*/\s*2', blok), \
        'Kanat açıları 90°lik adımlarla (Math.PI/2) dağıtılmalı.'


def test_roket_ekranda_eski_benekten_kucuk_degil():
    """Roket sembolü ekranda ESKİ BEYAZ BENEKTEN küçük olmamalı (ölçüldü).

    Bu test daha önce ham `0.006` sayısını kilitliyordu ve YANLIŞ ŞEYİ koruyordu:
    ekran oranı sabit değil, uzanım·k çarpımıdır (mesafeden bağımsız; kamera
    mesafesi _updateScalables'ta ölçeğe zaten giriyor). Eski benek 2,00 birim
    uzanımlıydı, yeni siluet 0,87 — k korunduğunda 800 px tuvalde 13,9 px'lik
    benek 6,1 px'e DÜŞÜYORDU, yani düzeltilmek istenen kusur kötüleşiyordu.

    Kilitlenen iddia artık şu: görünür uzanım (uzanım·k) eski beneğinkinden
    (2,00 · 0,006 = 0,0120) küçük olamaz. Üst sınır da var — sembol devleşip
    altındaki yolu/olay noktalarını örtmesin diye k ≤ 0,03.
    """
    body = _build_body()
    m = re.search(r'_registerScalable\s*\(\s*rk\s*,\s*([0-9.]+)\s*\)', body)
    assert m, (
        'Roketin ekran-sabit ölçek kaydı (_registerScalable(rk, k)) yok — model '
        'sahne birimiyle sabit boyuta düşmüş olabilir (yakın zoomda dev, uzakta '
        'görünmez).')
    k = float(m.group(1))
    uzanim = _roket_dikey_uzanim(_roket_blogu())
    gorunur = uzanim * k
    eski = 2.0 * 0.006          # eski beyaz küre: çap 2,0 birim, k = 0,006

    # Bilgi amaçlı piksel karşılığı (800 px yükseklikli tuval):
    pay = 2.0 * math.tan(math.radians(_fov()) / 2.0)
    px = 800.0 * gorunur / pay
    assert gorunur >= eski, (
        'Roket sembolü ekranda eski beyaz benekten KÜÇÜK: uzanım %.3f · k=%.4f '
        '= %.5f < %.5f (800 px tuvalde %.1f px < 13,9 px). Siluet ayırt '
        'edilemez — kusur düzelmedi, kötüleşti.' % (uzanim, k, gorunur, eski, px))
    assert k <= 0.03, (
        'Ekran-sabit ölçek katsayısı k=%.4f çok büyük: sembol yolu ve olay '
        'noktalarını örter. Roket bir İŞARETÇİDİR, ölçek iddiası taşımaz.' % k)


def test_sahte_egzoz_yok():
    """Alev/egzoz/duman ÇİZİLMEZ: çözücüde egzoz verisi yok."""
    blok = _roket_blogu().lower()
    for ad in ('flame', 'exhaust', 'plume', 'smoke'):
        assert ad not in blok, (
            'Roket bloğunda "%s" geçiyor — çözücü egzoz akısı üretmiyor, '
            'çizilen her şey veriden gelmeli.' % ad)


def test_grup_geometrisi_temizlikte_serbest_birakiliyor():
    """Roket Group olduğu için dispose ağaç boyunca (traverse) yapılmalı.

    Aksi hâlde `c.geometry` bir Group'ta undefined olur ve rakım abartması her
    değiştiğinde (setExaggeration -> _rebuildFromFlight) koni/silindir/kanat
    tamponları sızar.
    """
    clr = _code_lines(_prototype_body(_globe_src(), 'clearFlightPath'))
    assert 'traverse' in clr and 'geometry.dispose' in clr, (
        'clearFlightPath alt ögeleri gezip serbest bırakmıyor; roket artık bir '
        'Group ve geometrisi alt ögelerde.')


def test_temizlik_listeden_children0_ile_kaldiriyor():
    """Öge listeden ÖNCE pop edilirse remove() parent'ı boşaltmaz (sessiz sızıntı).

    Ölçülen davranış: `children.pop()` ögeyi diziden çıkarır, ardından gelen
    `remove(c)` onu listede bulamaz ve `c.parent` DOLU kalır. Hemen aşağıdaki
    _scalables süzgeci ("parent'ı kalmayanları at") tam da o koşula dayandığı
    için hiç iş yapmaz: her uçuşta roket + olay işaretçileri listede birikir ve
    _updateScalables her karede ölü nesneleri ölçeklemeye devam eder.
    Bu bekçi olmadan düzeltme sessizce geri alınabiliyordu (hakem mutasyon B:
    pop()'a dönüldü, 74 test yeşil kaldı).
    """
    clr = _code_lines(_prototype_body(_globe_src(), 'clearFlightPath'))
    assert 'children.pop()' not in clr, (
        'clearFlightPath yine children.pop() kullanıyor; remove() ögeyi listede '
        'bulamaz, parent boşalmaz ve _scalables süzgeci ölür.')
    assert re.search(r'children\[0\]', clr), (
        'Silinecek öge listenin BAŞINDAN okunmalı (children[0]); while döngüsü '
        'remove() ile ilerler.')
    assert re.search(r'\.remove\(\s*c\s*\)', clr), \
        'Öge gruptan remove(c) ile çıkarılmıyor — parent bağı kopmaz.'
    assert re.search(r'this\._scalables\s*=\s*this\._scalables\.filter', clr) \
        and 's.obj.parent' in clr, (
        '_scalables süzgeci (parent\'ı kalmayanları at) kaybolmuş; ölçeklenebilir '
        'işaretçi listesi her uçuşta büyür.')


# ---------------------------------------------------------------------------
# Kalem 2 — yol teğetine yönelim
# ---------------------------------------------------------------------------

def test_nokta_bazli_tegetler_kuruluyor():
    """_pathTangents merkezi farkla kurulur (uç-uç tek teğet yönelim için yetmez)."""
    body = _build_body()
    assert 'this._pathTangents = new Array(n)' in body, \
        '_pathTangents dizisi _buildFlightGeometry içinde kurulmalı.'
    assert 'Math.max(ti - 1, 0)' in body and 'Math.min(ti + 1, n - 1)' in body, (
        'Teğet merkezi fark P[i+1]-P[i-1] ile alınmalı; uçlarda tek yanlı '
        'farka düşmeli (kırpma bunu sağlar).')
    assert 'prevTan' in body, (
        'Sıfır uzunluklu fark (ardışık özdeş nokta) durumunda bir önceki teğet '
        'taşınmalı — normalize(0) NaN yönelim üretir.')
    assert re.search(r'else\s+tan\.copy\(this\._pathPoints\[ti\]\)\.normalize\(\)', body), (
        'İlk noktada teğet de yoksa yüzey normali kullanılmalı: roket kalkışta '
        'dik durur.')


def test_tegetler_temizlikte_null_lanir():
    """clearFlightPath _pathTangents'ı da bırakmalı (diğer _path* alanlarıyla birlikte)."""
    clr = _code_lines(_prototype_body(_globe_src(), 'clearFlightPath'))
    assert re.search(r'this\._pathTangents\s*=\s*null', clr), (
        '_pathTangents temizlenmiyor: yeni uçuş eskisinden kısa olduğunda '
        '_seekTime eski diziden okur (indis taşması / yanlış yönelim).')


def test_seektime_yonelim_uyguluyor():
    """Konumdan sonra quaternion setFromUnitVectors ile teğete oturtulur."""
    body = _code_lines(_prototype_body(_globe_src(), '_seekTime'))
    assert 'setFromUnitVectors' in body, \
        '_seekTime roketi yol teğetine döndürmüyor — burun yönü rastgele kalır.'
    assert re.search(r'this\._rocket\.quaternion\.copy', body), \
        'Hesaplanan yönelim roket grubuna yazılmalı.'
    assert re.search(r'\.lerp\(this\._pathTangents\[j\]\s*,\s*a\)', body), (
        'Teğet, konumla AYNI i/j çifti ve aynı a katsayısıyla karıştırılmalı; '
        'yoksa yönelim konumun gerisinde/ilerisinde kalır.')


def test_seektime_kare_basi_allokasyon_yapmiyor():
    """_seekTime her karede çağrılır: yönelim için çöp üretilmemeli."""
    body = _code_lines(_prototype_body(_globe_src(), '_seekTime'))
    assert 'new THREE.Quaternion().setFromUnitVectors' not in body, (
        'Her karede yeni Quaternion ayrılıyor — geçici nesneler yeniden '
        'kullanılmalı (_orient).')
    assert 'this._orient' in body, \
        'Yönelim geçicileri örnek başına bir kez kurulan _orient içinde tutulmalı.'


# ---------------------------------------------------------------------------
# Kalem 3 — viewSite yay çerçevesi
# ---------------------------------------------------------------------------

def test_viewsite_tabani_ucusa_bagli():
    """Taban YALNIZ uçuş varken 0,03R'ye iner; uçuşsuz dal 0,1R kalır."""
    vs = _code_lines(_prototype_body(_globe_src(), 'viewSite'))
    m = re.search(
        r'var\s+floor\s*=\s*\(?\s*this\._flight\s*\?\s*GLOBE_R\s*\*\s*0\.03\s*:\s*'
        r'GLOBE_R\s*\*\s*0\.1\s*\)?\s*;', vs)
    assert m, (
        'viewSite tabanı uçuş varlığına bağlı değil. Beklenen: '
        'floor = this._flight ? GLOBE_R*0.03 : GLOBE_R*0.1 — uçuş yokken saha '
        'coğrafyası bağlamı için eski 0,1R korunur.')
    assert re.search(r'clamp\(\s*dist\s*,\s*floor\s*,\s*GLOBE_R\s*\*\s*2\.5\s*\)', vs), \
        'clamp hâlâ sabit tabanı kullanıyor; hesaplanan floor bağlanmamış.'


def test_takip_kipi_tabani_degismedi():
    """_seekTime'ın follow kipi zaten 0,03R tabanlıydı — ona dokunulmadı."""
    body = _code_lines(_prototype_body(_globe_src(), '_seekTime'))
    assert re.search(r'GLOBE_R\s*\*\s*0\.03\s*,\s*GLOBE_R\s*\*\s*1\.0', body), \
        'Takip kipindeki clamp(…, 0,03R, 1,0R) sınırları değişmiş.'


def test_yay_ekranda_kayda_deger_yer_kapliyor():
    """Sayısal kilit: 15,7 km'lik yay yeni tabanda ekranın %8'inden fazlası.

    Oranlar YORUMDAN değil kaynaktaki sabitlerden yeniden hesaplanır:
    yay_birim = 15.700 m / (R_EARTH_M / GLOBE_R), ekran yüksekliği = 2·d·tan(FOV/2).
    Eski taban (10 birim) aynı yayı %5'in altında bırakıyordu — kusur buydu.
    """
    src = _globe_src()
    globe_r = _sabit(src, 'GLOBE_R')
    r_earth = _sabit(src, 'R_EARTH_M')
    m = re.search(r'new\s+THREE\.PerspectiveCamera\(\s*([0-9.]+)\s*,', src)
    assert m, 'kamera FOV değeri bulunamadı'
    fov = float(m.group(1))
    yarim = math.radians(fov) / 2.0

    m_per_unit = r_earth / globe_r
    yay = 15700.0 / m_per_unit                      # ~0,247 sahne birimi

    eski = yay / (2.0 * (globe_r * 0.1) * math.tan(yarim))
    yeni = yay / (2.0 * (globe_r * 0.03) * math.tan(yarim))
    assert eski < 0.05, (
        'Eski taban beklenenden geniş çerçevelemiyor (%.4f); testin başvurduğu '
        'kusur artık farklı — sayıları yeniden ölç.' % eski)
    assert yeni > 0.08, (
        'Yeni tabanda yay ekran yüksekliğinin yalnızca %%%.1f\'i; işaretçiler '
        'yine üst üste biner.' % (100.0 * yeni))
    assert yeni / eski > 3.0, \
        'Kazanç 3 kattan az (%.2f); taban gevşetmesi etkisiz kalmış.' % (yeni / eski)


def test_olcek_abartilarak_cozulmedi():
    """Çözüm kamera mesafesinde: rakım abartması VARSAYILAN KAPALI kalmalı."""
    src = _globe_src()
    assert re.search(r'this\._exaggerate\s*=\s*1\.0', src), (
        'Rakım abartması varsayılan olarak 1,0 (kapalı) olmalı; yayı görünür '
        'kılmak için ölçek şişirilmiş olabilir.')
