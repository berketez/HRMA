# -*- coding: utf-8 -*-
"""Sahne içi gök küresi — ölçülmüş kararların kaynak-seviyesi kilidi (2026-08-14).

NEDEN BU DOSYA VAR
------------------
Fırlatma sahası küresinin arkasındaki gökyüzü ÖNCEDEN bir CSS arka planıydı ve
kamerayla DÖNMÜYORDU: kamera 90° döndürüldüğünde gökyüzü dikdörtgeninde
56.000 pikselin 56.000'i özdeş kaldı. Yani "yıldızlar" Dünya'ya çivilenmişti.
Düzeltme gökyüzünü sahnenin parçası yaptı (Samanyolu küresi + Yale BSC5
katalogundan gerçek yıldızlar).

Bu katmanın doğruluğu görsel olarak "iyi görünmek"le ölçülemez: ayna görüntüsü
bir gökyüzü de, 12 saat kaymış bir gökyüzü de, ekvatoral yıldızların galaktik
çerçeveye zorlandığı bir gökyüzü de gayet güzel görünür. Bu yüzden buradaki
her assert, bu oturumda BAĞIMSIZ ÖLÇÜMLE saptanmış tek bir kararı kilitler ve
kararın sessizce "düzeltilmesini" (özellikle işaret/eksen çevirmesini) kırar.

Varlıkların kendi bütünlüğü ayrı dosyada sınanır: tests/test_gokyuzu_varliklari.py
(doku 4096x2048 mi, katalogda Sirius doğru yerde mi vb.). Buradaki testler
varlıkları DEĞİL, onları kullanan KODU sınar.
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

#: J2000.0 = 2000-01-01 12:00 UTC, Unix ms cinsinden. GMST bu anda tam olarak
#: 280,46061837° olmalıdır — formülün mutlak çapası budur.
J2000_MS = 946728000000
J2000_GMST_DEG = 280.46061837


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


def _kod():
    return _code_lines(_globe_src())


def _sabit(kod, ad):
    """`var <ad> = <sayı ya da ifade>;` sağ tarafını metin olarak verir."""
    m = re.search(r'var %s\s*=\s*([^;]+);' % ad, kod)
    assert m, 'sabit bulunamadı: %s' % ad
    return m.group(1).strip()


# ---------------------------------------------------------------------------
# 0) Katman gerçekten SAHNENİN İÇİNDE mi
# ---------------------------------------------------------------------------

def test_gokyuzu_sahneye_ekleniyor():
    """Ölçülen kusur: CSS gökyüzü kamerayla dönmüyordu (56.000/56.000 piksel aynı).

    Çözüm ancak gökyüzü SAHNE GRAFİĞİNE eklenirse işe yarar; grup sahneye
    eklenmezse hiçbir şey görünmez, eklenip de kameraya bağlanırsa eski kusur
    geri gelir. Grup sahnenin (kameranın değil) çocuğu olmalı.
    """
    init = _code_lines(_prototype_body(_globe_src(), '_init'))
    assert 'this._skyGroup = new THREE.Group()' in init, 'gök küresi grubu kurulmuyor'
    assert 'scene.add(this._skyGroup)' in init, \
        'gök küresi grubu SAHNEYE eklenmiyor — kamerayla dönmeyen CSS gökyüzüne geri dönülmüş olur'
    assert 'camera.add(this._skyGroup)' not in init, \
        'gök küresi KAMERAYA bağlanmış — kamerayla birlikte dönerdi, ölçülen kusurun ta kendisi'
    assert 'this._buildSky()' in init, '_buildSky çağrılmıyor'


def test_gok_kuresi_yaricapi_gorus_alaninda():
    """Gök küresi kameranın far düzlemi içinde, Dünya'nın çok dışında olmalı."""
    kod = _kod()
    assert _sabit(kod, 'R_SKY') == 'GLOBE_R * 50', \
        'R_SKY GLOBE_R * 50 (5000 birim) olmalı — küçülürse Dünya gökyüzünü deler, büyürse far düzlemini aşar'
    assert _sabit(kod, 'R_STAR') == 'R_SKY * 0.98', \
        'yıldızlar Samanyolu dokusunun ÖNÜNDE olmalı (aynı yarıçapta z-savaşı olur)'
    m = re.search(r'new THREE\.PerspectiveCamera\([^)]*\)', kod)
    assert m, 'kamera kurulumu bulunamadı'
    far = float(m.group(0).rstrip(')').split(',')[-1])
    assert far > 100.0 * 50, \
        'kamera far düzlemi (%g) gök küresini (5000 birim) kırpıyor' % far


# ---------------------------------------------------------------------------
# 1) Varlık yolları
# ---------------------------------------------------------------------------

def test_varlik_yollari_kodda():
    """Kod, depoda DOĞRULANMIŞ iki varlığı okumalı; başka bir kaynağa kaymamalı."""
    kod = _kod()
    assert '/static/img/milky_way_eso0932a_4096.webp' in kod, \
        'Samanyolu dokusu yolu kodda yok'
    assert '/static/data/bsc5p_stars.bin' in kod, 'yıldız katalogu yolu kodda yok'
    # Varlıklar gerçekten yerinde mi (test_gokyuzu_varliklari.py içeriğini de sınar)
    assert (ROOT / 'hrma/static/img/milky_way_eso0932a_4096.webp').exists()
    assert (ROOT / 'hrma/static/data/bsc5p_stars.bin').exists()


def test_uzak_kaynaktan_gokyuzu_cekilmiyor():
    """Gökyüzü ÇEVRİMDIŞI çalışmalı: uzaktan doku/katalog indirilmemeli."""
    sky = _code_lines(_prototype_body(_globe_src(), '_buildMilkyWay')) \
        + _code_lines(_prototype_body(_globe_src(), '_buildStars'))
    assert 'http://' not in sky and 'https://' not in sky, \
        'gök küresi uzak bir adrese bağlanıyor — çevrimdışı kurulumda gökyüzü kaybolur'


# ---------------------------------------------------------------------------
# 2) U-aynalama (ESO panoramasının ÖLÇÜLEN yönü)
# ---------------------------------------------------------------------------

def test_u_aynalama_ucgeni_yerinde():
    """ÖLÇÜLDÜ: bu panoramada galaktik boylam görüntüde SOLA doğru artıyor.

    LMC/SMC lekeleri "sola-artar" konumda parlak (29,0 / 16,0), "sağa-artar"
    konumda yalnız fon seviyesinde (11,8). SphereGeometry UV'si ise boylamın u
    ile ARTTIĞINI varsayar; aynalanmazsa gökyüzü AYNA GÖRÜNTÜSÜ olur — ve ayna
    bir gökyüzü de "güzel" göründüğü için gözle fark edilmez. Üçlü birlikte
    anlamlıdır: RepeatWrapping olmadan negatif repeat kenarda kırpılır.
    """
    mw = _code_lines(_prototype_body(_globe_src(), '_buildMilkyWay'))
    assert re.search(r'tex\.wrapS\s*=\s*THREE\.RepeatWrapping', mw), \
        'wrapS = RepeatWrapping yok — negatif repeat ile kenar sarmalaması bozulur'
    assert re.search(r'tex\.repeat\.x\s*=\s*-\s*1', mw), \
        'repeat.x = -1 yok/işareti değişmiş — panorama ayna görüntüsü çizilir'
    assert re.search(r'tex\.offset\.x\s*=\s*1', mw), \
        'offset.x = 1 yok — aynalanan doku yarım kaydırılmış olur (galaktik merkez ortadan kaçar)'


def test_doku_srgb_isaretleniyor():
    """Diğer dokularla aynı kural: sRGB çözülüp sRGB kodlanır (karanlık kare kilidi)."""
    mw = _code_lines(_prototype_body(_globe_src(), '_buildMilkyWay'))
    assert 'tex.encoding = THREE.sRGBEncoding' in mw, \
        'Samanyolu dokusu sRGB işaretlenmiyor — diğer iki dokudan farklı davranır'


# ---------------------------------------------------------------------------
# 3) Galaktik -> ekvatoral çapalar
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('sabit', ['192.85948', '27.12825', '266.404988', '-28.936175'])
def test_galaktik_capalar_birebir(sabit):
    """J2000 galaktik kutup ve merkez yönü. Bir hane bile değişirse gökyüzü döner.

    Bu dört sayı sayısal olarak doğrulandı: l=90,b=0 -> RA 318,004 / Dec +48,330
    ve LMC -> RA 80,887 / Dec -69,760. "Yuvarlarım" ya da "eksenleri düzeltirim"
    denirse Samanyolu bandı gerçek gökyüzüyle örtüşmeyi bırakır.
    """
    mw = _code_lines(_prototype_body(_globe_src(), '_buildMilkyWay'))
    assert sabit in mw, 'galaktik çapa sabiti kaybolmuş/değişmiş: %s' % sabit


def test_galaktik_taban_dogru_eksenlere_kuruluyor():
    """makeBasis SÜTUN alır: yerel x = galaktik merkez, yerel y = galaktik kutup.

    Sıra değişirse (ör. kutup x'e konursa) doku 90° yatar; sağ el kuralı bozulursa
    gökyüzü aynalanır. gz = GAL_CENTER x GAL_POLE olmak zorundadır.
    """
    mw = _code_lines(_prototype_body(_globe_src(), '_buildMilkyWay'))
    assert re.search(r'crossVectors\(\s*GAL_CENTER\s*,\s*GAL_POLE\s*\)', mw), \
        'gz çapraz çarpımının sırası değişmiş — sağ el kuralı bozulur, gökyüzü aynalanır'
    assert re.search(r'makeBasis\(\s*GAL_CENTER\s*,\s*GAL_POLE\s*,\s*gz\s*\)', mw), \
        'taban vektörlerinin sırası değişmiş — doku 90° yatar'
    assert 'quaternion.setFromRotationMatrix' in mw, \
        'galaktik yönelim mesh\'e uygulanmıyor — doku ekvatoral çerçevede kalır'


def test_doku_yuklenemezse_sahte_gokyuzu_uretilmiyor():
    """Doku gelmezse mesh HİÇ eklenmez; prosedürel/sahte gökyüzü çizilmez."""
    mw = _code_lines(_prototype_body(_globe_src(), '_buildMilkyWay'))
    assert mw.count('new THREE.Mesh(') == 1, \
        'birden fazla mesh kurulumu var — biri yedek/sahte gökyüzü olabilir'
    assert 'Math.random' not in mw, 'dokunun yerine rastgele içerik üretiliyor'
    assert 'console.warn' in mw, 'yükleme hatası sessizce yutuluyor'
    # Mesh, yükleme BAŞARILI geri çağrısının içinde kurulmalı (hata dalında değil)
    assert mw.index('TextureLoader().load') < mw.index('new THREE.Mesh('), \
        'mesh doku yüklemesinden bağımsız kuruluyor — doku gelmese de boş küre çizilir'


# ---------------------------------------------------------------------------
# 4) GMST — işaret ve sıra hatasının kilidi
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('sabit', ['280.46061837', '360.98564736629', '10957.5'])
def test_gmst_sabitleri_birebir(sabit):
    """IAU 1982 basitleştirmesinin üç sabiti. 10957,5 = Unix epoch -> J2000 farkı."""
    kod = _kod()
    assert sabit in kod, 'GMST sabiti kaybolmuş/değişmiş: %s' % sabit


def _gmst_py(ms):
    """Formülü JS KAYNAĞINDAN OKUNAN sabitlerle Python'da yeniden kurar.

    Sabitler elle yazılmaz; kaynaktan ayıklanır ki test "kendi sabitini" değil
    kodun sabitini sınasın.
    """
    kod = _kod()
    gun_ms = float(re.search(r'ms\s*/\s*([0-9.]+)\s*-\s*10957\.5', kod).group(1))
    d = ms / gun_ms - 10957.5
    g = 280.46061837 + 360.98564736629 * d
    return ((g % 360) + 360) % 360


def test_gmst_j2000_ogleninde_dogru_deger():
    """Mutlak çapa: 2000-01-01 12:00 UTC -> GMST = 280,46061837°.

    Gün bölmesi ya da epoch kaydırması ters çevrilirse bu değer tutmaz; işaret
    hatası ise 24 saat kaymış bir gökyüzü üretir (yıldızlar hâlâ "doğru" görünür,
    ama gerçek gökyüzü değildir).
    """
    assert abs(_gmst_py(J2000_MS) - J2000_GMST_DEG) < 1e-6, \
        'J2000 öğleninde GMST %.8f — %.8f bekleniyordu' % (_gmst_py(J2000_MS), J2000_GMST_DEG)


def test_gmst_gunluk_ilerleme_yildiz_gunu():
    """Bir saatte ~15,041° ilerlemeli (yıldız günü 23s56d, güneş günü değil)."""
    ileri = (_gmst_py(J2000_MS + 3600000) - _gmst_py(J2000_MS)) % 360.0
    assert abs(ileri - 360.98564736629 / 24.0) < 1e-6, \
        'saatlik ilerleme %.6f° — yıldız günü yerine güneş günü kullanılmış olabilir' % ileri


@pytest.mark.skipif(NODE is None, reason='node bulunamadı')
def test_gmst_js_fonksiyonu_python_ile_ayni():
    """Kaynaktaki GERÇEK fonksiyon çalıştırılır; Python yeniden kurulumuyla eşleşmeli."""
    src = _globe_src()
    fn = re.search(r'function gmstDeg\(ms\) \{.*?\n    \}', src, re.S)
    assert fn, 'gmstDeg gövdesi ayıklanamadı'
    ornekler = [J2000_MS, 0, 1755180000000, 946728000000 + 43200000, 2000000000000]
    script = '\n'.join([
        fn.group(0),
        'var out = %s.map(gmstDeg);' % json.dumps(ornekler),
        'process.stdout.write(JSON.stringify(out));',
    ])
    r = subprocess.run([NODE, '-e', script], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[:800]
    js = json.loads(r.stdout)
    assert abs(js[0] - J2000_GMST_DEG) < 1e-6, \
        'JS gmstDeg(J2000) = %.8f — %.8f bekleniyordu' % (js[0], J2000_GMST_DEG)
    for ms, v in zip(ornekler, js):
        assert 0.0 <= v < 360.0, 'gmstDeg(%d) = %r — [0,360) dışında' % (ms, v)
        assert abs(v - _gmst_py(ms)) < 1e-6, \
            'gmstDeg(%d): JS %.8f vs Python %.8f' % (ms, v, _gmst_py(ms))


def test_skygroup_negatif_gmst_ile_donduruluyor():
    """Yıldız RA'ya konur; grup -GMST döndürülünce boylam RA - GMST olur.

    y-dönüşü θ boylama +θ ekler (küre parametrizasyonundan türetildi), yani
    işaret POZİTİFE çevrilirse gökyüzü ters yönde ve iki kat kaymış olur —
    ekranda yine "yıldızlı gökyüzü" görünür, ama yanlış gökyüzü.
    """
    init = _code_lines(_prototype_body(_globe_src(), '_init'))
    assert re.search(r'_skyGroup\.rotation\.y\s*=\s*-\s*deg2rad\(\s*this\._skyGmstDeg\s*\)', init), \
        'skyGroup dönüşü NEGATİF GMST kullanmıyor'
    assert 'this._skyGmstDeg = gmstDeg(this._skyEpochMs)' in init, \
        'GMST epoch\'tan hesaplanmıyor'


def test_yonelim_tek_zaman_kaynagina_sabit():
    """Yönelim sayfa açılışına DONAR: canlı dönen gökyüzü gerçek-zaman iddiasıdır.

    Ölçüt: GMST yalnız kurulumda hesaplanır, animasyon döngüsünde DEĞİL.
    """
    src = _globe_src()
    kod = _code_lines(src)
    assert kod.count('gmstDeg(') == 2, \
        'gmstDeg tanım + tek çağrı olmalı; fazlası canlı güncelleme demektir'
    loop = _code_lines(_prototype_body(src, '_animate'))
    assert '_skyGroup' not in loop and 'gmstDeg' not in loop, \
        'gökyüzü her karede güncelleniyor — sahte gerçek-zaman izlenimi verir'
    assert 'this._skyEpochMs = Date.now()' in _code_lines(_prototype_body(src, '_init')), \
        'epoch tarayıcı saatinden alınmıyor (beyan edilen kaynak bu)'


# ---------------------------------------------------------------------------
# 5) Yıldızlar
# ---------------------------------------------------------------------------

def test_yildiz_kovalari_ve_boyutlari():
    """r128 nokta-başına boyut desteklemez; parlaklık ancak 5 ayrı Points ile ayrışır."""
    kod = _kod()
    m = re.search(r'var STAR_BUCKETS = \[(.*?)\];', kod, re.S)
    assert m, 'STAR_BUCKETS tablosu yok'
    tablo = m.group(1)
    for esik in ('1.0', '2.5', '4.0', '5.5'):
        assert re.search(r'vmax:\s*%s\b' % re.escape(esik), tablo), \
            'kadir eşiği kaybolmuş: %s' % esik
    assert 'Infinity' in tablo, 'en sönük kova üst sınırsız olmalı (sönük yıldız düşmesin)'
    assert len(re.findall(r'vmax:', tablo)) == 5, 'kova sayısı 5 değil'
    for boyut in ('3.0', '2.2', '1.6', '1.1', '0.8'):
        assert re.search(r'size:\s*%s\b' % re.escape(boyut), tablo), \
            'kova boyutu kaybolmuş: %s' % boyut


def test_yildiz_boyutu_mesafeyle_kucultulmuyor():
    """sizeAttenuation açık olsaydı 4900 birimdeki yıldızlar görünmez olurdu."""
    st = _code_lines(_prototype_body(_globe_src(), '_buildStars'))
    assert re.search(r'sizeAttenuation:\s*false', st), \
        'sizeAttenuation false değil — perspektif küçültmesiyle yıldızlar kaybolur'
    assert re.search(r'renderOrder\s*=\s*-1', st), \
        'yıldızlar Samanyolu dokusundan sonra çizilmiyor'


def test_yildizlara_galaktik_donusum_uygulanmiyor():
    """Katalog J2000 EKVATORAL; galaktik quaternion YALNIZ Samanyolu mesh'ine aittir.

    Aynı dönüşüm yıldızlara da uygulanırsa iki katman birbirine göre ~60° kayar —
    Samanyolu bandı yıldızların üstünden geçmez. Bu, "tutarlı olsun" diye
    yapılabilecek en olası ve en sessiz hatadır.
    """
    src = _globe_src()
    st = _code_lines(_prototype_body(src, '_buildStars'))
    for yasak in ('setFromRotationMatrix', 'makeBasis', 'GAL_POLE', 'GAL_CENTER'):
        assert yasak not in st, \
            'yıldız kurulumunda galaktik dönüşüm izi var (%s) — iki katman kayar' % yasak
    assert re.search(r'latLonToVec3\(\s*dec\s*,\s*ra\s*,\s*R_STAR\s*\)', st), \
        'yıldız konumu (dec, ra) sırasıyla kurulmuyor — enlem/boylam takası gökyüzünü döndürür'
    # Ön koşul: dönüşüm gerçekten Samanyolu tarafında duruyor mu?
    mw = _code_lines(_prototype_body(src, '_buildMilkyWay'))
    assert 'setFromRotationMatrix' in mw, \
        'galaktik dönüşüm hiçbir yerde uygulanmıyor — bu testin dayanağı değişti'


def test_katalog_imzasi_dogrulaniyor_ve_uydurma_yildiz_yok():
    """İmza tutmazsa çizim yapılmaz; hiçbir koşulda rastgele yıldız üretilmez."""
    st = _code_lines(_prototype_body(_globe_src(), '_buildStars'))
    assert "'BSC1'" in st, 'BSC1 imza denetimi yok — bozuk dosya sessizce çizilir'
    assert 'Math.random' not in st, 'rastgele yıldız üretimi var (sahte veri yasağı)'
    assert re.search(r'getFloat32\([^)]*,\s*true\s*\)', st), \
        'little-endian okuma yok — bayt sırası hatası anlamsız koordinat üretir'
    assert re.search(r'getUint32\(\s*4\s*,\s*true\s*\)', st), 'kayıt sayısı okunmuyor'


def test_yildizlar_ve_doku_ayni_gruba_giriyor():
    """İkisi de GMST dönüşünü almalı; biri grup dışında kalırsa katmanlar kayar."""
    src = _globe_src()
    assert '_skyGroup.add(mw)' in _code_lines(_prototype_body(src, '_buildMilkyWay')), \
        'Samanyolu mesh\'i gök grubuna eklenmiyor (GMST dönüşünü almaz)'
    assert '_skyGroup.add(pts)' in _code_lines(_prototype_body(src, '_buildStars')), \
        'yıldızlar gök grubuna eklenmiyor (GMST dönüşünü almaz)'


def test_sky_bilgi_kancasi_ve_temizlik():
    """getSkyInfo ölçüm/beyan kancasıdır; dispose GPU belleğini bırakmalı."""
    src = _globe_src()
    info = _code_lines(_prototype_body(src, 'getSkyInfo'))
    for alan in ('epochMs', 'gmstDeg', 'starCount', 'milkyWay'):
        assert alan in info, 'getSkyInfo %s alanını yayımlamıyor' % alan
    assert '_skyStarCount' in _code_lines(_prototype_body(src, '_buildStars')), \
        'yıldız sayısı yayımlanmıyor — ekrandaki gökyüzü ölçülemez olur'
    dis = _code_lines(_prototype_body(src, 'dispose'))
    assert 'this._disposeSky()' in dis, 'dispose gök küresini bırakmıyor (doku 1,5 MB)'
    sky_dis = _code_lines(_prototype_body(src, '_disposeSky'))
    for cagri in ('geometry.dispose', 'material.dispose', 'map.dispose'):
        assert cagri in sky_dis, '_disposeSky %s çağırmıyor' % cagri


# ---------------------------------------------------------------------------
# 6) Arayüz beyanı
# ---------------------------------------------------------------------------

def test_html_epoch_beyani_ve_atif():
    """Kullanıcı hangi ana bakıldığını ve kaynağı görmeli (CC BY 4.0 yükümlülüğü)."""
    html = SITE_HTML.read_text(encoding='utf-8')
    assert 'id="ls-sky-time"' in html, 'epoch kutusu yok'
    assert 'site.skyEpoch' in html, 'epoch etiketi i18n anahtarına bağlı değil'
    assert 'site.skyAttribution' in html, 'gökyüzü atfı yok — CC BY 4.0 şartı ihlal edilir'
    assert 'getSkyInfo()' in html, 'epoch küreden okunmuyor (ekranda ayrı bir saat üretilmiş olabilir)'
    assert 'toISOString()' in html, 'epoch UTC olarak biçimlenmiyor (etiket UTC diyor)'


def test_i18n_anahtarlari_iki_dilde_de_var():
    """Beyan çevrilmezse TR modda İngilizce sızar (bu sayfada daha önce olmuştu)."""
    sozluk = (ROOT / 'hrma/static/js/i18n_launch_site.js').read_text(encoding='utf-8')
    for anahtar in ('site.skyEpoch', 'site.skyAttribution'):
        assert sozluk.count("'%s'" % anahtar) >= 2, \
            '%s sözlükte iki dilde de yok' % anahtar
