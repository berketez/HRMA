"""3B sahnenin FOTOGERÇEKÇİ sunum katmanı — RENDER_QUALITY bekçileri (B7).

Bu dosya motor_viz3d.js'in *fiziksel kalite* katmanını sınar: malzeme
parametreleri, ışık dengesi, gölge kadrajı/keskinliği ve kalite kipi
bağlantısı. Sahnenin KİMLİĞİ (neon jant ışıkları, HUD, çipler, ton
eşleme) bilerek DIŞARIDA tutulur ve burada ayrıca DONDURULUR.

Ölçüm (2026-08-18, düzeltmeden önce — gerçek Three.js r128 ile kurulan
malzeme nesneleri ve gölge kamerası okunarak):

  1) Gölge kamerası ±L kare frustumla kuruluyordu (L = motorun TAM boyu)
     ve `near` hiç ayarlanmıyordu (r128 varsayılanı 0,5; far = 6·L).
     Varsayılan hibritte (L=1670 mm, R=65 mm) teksel 2·L/2048 = 1,631 mm.
     Oysa model ışık düzlemine izdüşünce yarı genişlik 599 / yarı yükseklik
     528 mm yer kaplıyor — dokunun ~%88'i boşa gidiyordu.
  2) bias = 0 ve normalBias = 0 (r128 varsayılanları): eğri metal yüzeyde
     kendi kendine gölgeleme (akne) riski hiç ele alınmamıştı.
  3) Altı malzeme (grain, grainCut, liner, linerCut, oring, orifice)
     `envMapIntensity` alanını hiç yazmıyordu ⇒ r128 varsayılanı 1,0 ile
     ortam haritasını TAM alıyorlardı; açıkça yazılmış dokuz malzemenin
     hepsi ≤0,75 ve her kesit yüzü 0,2 idi.
  4) Fırçalanmış metal dokusunun anizotropik süzmesi 1 (kapalı) idi;
     minFilter ölçüldü = 1008 (LinearMipmapLinear), yani mipmap zinciri
     zaten kuruluyordu — siyirma açısında iz gereksiz bulanıklaşıyordu.
  5) Işık düzeni iki kaynaktı (key 0,95 + hemi 0,55); yönlü dolgu yoktu.
  6) Beş donanım mesh'i (kapak cıvatası, soğutma kanalı, pintle gövdesi,
     ateşleyici, lüle cıvatası) gölge ATIYOR ama ALMIYORDU.

Bekçilerin çoğu metin taraması DEĞİL ölçümdür: paketlenmiş gerçek
three-0.128.0.min.js node içinde yüklenir, `createMaterials` kaynaktan
çıkarılıp çalıştırılır ve ORTAYA ÇIKAN malzeme nesneleri okunur; gölge
kadrajı ise saf `shadowFrustumFit` çalıştırılıp köşeler Python'da
BAĞIMSIZ izdüşürülerek sınanır.
"""

import json
import math
import pathlib
import re
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
VIZ_JS = ROOT / 'hrma/static/js/motor_viz3d.js'
THREE_VENDOR = ROOT / 'hrma/static/vendor/three-0.128.0.min.js'
NODE = shutil.which('node')

pytestmark = pytest.mark.skipif(NODE is None, reason='node bulunamadi')

# Teşhis senaryosu: varsayılan hibrit tasarımın kadraj büyüklükleri
# (tests/test_viz3d_gorsel_kalite.py ile AYNI ölçüler).
L_DEFAULT = 1670.0
R_DEFAULT = 65.0

# Düzeltmeden ÖNCEKİ gölge kuralı (yukarıdaki 1. ölçüm) — karşılaştırma
# tabanı. Üretim kodunda artık yok, burada yalnız "ne kadar iyileşti"
# sorusunun cevabı için duruyor.
OLD_SHADOW_HALF = L_DEFAULT      # ±L kare frustum
OLD_SHADOW_MAP = 2048
OLD_TEXEL_MM = 2 * OLD_SHADOW_HALF / OLD_SHADOW_MAP     # 1,6309 mm

# Literatür bandı (gerçek zamanlı gölge haritalama pratiği): ortografik
# gölge kamerasında sabit derinlik bias'ı bu aralıkta tutulur.
BIAS_BAND = (-5e-4, -1e-4)


# ---------------------------------------------------------------------------
# Kaynak çıkarımı + node koşumu
# ---------------------------------------------------------------------------

def _source():
    return VIZ_JS.read_text(encoding='utf-8')


def _extract(func_name, source=None):
    """motor_viz3d.js icinden tek bir fonksiyonu izole cikarir."""
    src = source if source is not None else _source()
    start = src.index('function %s(' % func_name)
    depth, idx = 0, start
    while idx < len(src):
        if src[idx] == '{':
            depth += 1
        elif src[idx] == '}':
            depth -= 1
            if depth == 0:
                return src[start:idx + 1]
        idx += 1
    raise AssertionError('%s kapanmiyor' % func_name)


def _extract_method(name):
    """MotorScene.prototype.<name> govdesini cikarir."""
    src = _source()
    marker = 'MotorScene.prototype.%s = function' % name
    start = src.index(marker)
    depth, idx, seen = 0, src.index('{', start), False
    while idx < len(src):
        if src[idx] == '{':
            depth += 1
            seen = True
        elif src[idx] == '}':
            depth -= 1
            if seen and depth == 0:
                return src[start:idx + 1]
        idx += 1
    raise AssertionError('%s kapanmiyor' % name)


def _var_block(name):
    """`var AD = { ... };` bildirimini sus parantez esleyerek cikarir."""
    src = _source()
    start = src.index('var %s = ' % name)
    idx = src.index('{', start)
    depth = 0
    while idx < len(src):
        if src[idx] == '{':
            depth += 1
        elif src[idx] == '}':
            depth -= 1
            if depth == 0:
                return src[start:idx + 2]   # kapanis ';' dahil
        idx += 1
    raise AssertionError('%s kapanmiyor' % name)


def _run(script):
    # Betik stdin ile verilir (argv tavani: tests/test_node_cagri_sozlesmesi.py)
    result = subprocess.run([NODE], input=script, capture_output=True,
                            text=True, timeout=120)
    assert result.returncode == 0, result.stderr[:1200]
    return json.loads(result.stdout)


def _emit(prelude, expr):
    return _run(prelude + '\nprocess.stdout.write(JSON.stringify(%s));\n' % expr)


def _pure_prelude():
    """Golge kadraji saf fonksiyonlari + bagli tablolar (THREE'siz)."""
    return '\n'.join([
        _var_block('RENDER_QUALITY'),
        _var_block('EXPLODE_OFFSETS'),
        re.search(r'var FLOOR_DROP_RATIO = [^;]+;', _source()).group(0),
        _extract('floorYMm'),
        _extract('shadowFrustumFit'),
        _extract('shadowAxisHalfMm'),
    ])


def _three_prelude(extra_funcs=()):
    """GERCEK r128 + kanvas kokunu (canvas) sahte olan node kabugu."""
    head = """
global.self = global;
const THREE = require(%s);
global.THREE = THREE;
function _ctx() {
    return { fillStyle: '', fillRect() {},
             createLinearGradient() { return { addColorStop() {} }; },
             createRadialGradient() { return { addColorStop() {} }; } };
}
global.document = { createElement() {
    return { width: 0, height: 0, getContext() { return _ctx(); } }; } };
""" % json.dumps(str(THREE_VENDOR))
    parts = [head, _var_block('RENDER_QUALITY')]
    for fn in ('makeCanvas', 'brushedTexture', 'createMaterials') + tuple(extra_funcs):
        parts.append(_extract(fn))
    return '\n'.join(parts)


def _build_materials(max_aniso=16):
    """createMaterials'i GERCEK three r128 ile calistirip nesneleri okur."""
    expr = """(function () {
        var mats = createMaterials(%s);
        var out = {};
        Object.keys(mats).forEach(function (k) {
            var m = mats[k];
            out[k] = { type: m.type, color: '0x' + m.color.getHexString(),
                       metalness: m.metalness, roughness: m.roughness,
                       envMapIntensity: m.envMapIntensity, side: m.side,
                       bump: !!m.bumpMap, roughMap: !!m.roughnessMap,
                       bumpScale: m.bumpMap ? m.bumpScale : null,
                       clearcoat: m.clearcoat === undefined ? null : m.clearcoat,
                       ccRough: m.clearcoatRoughness === undefined
                                ? null : m.clearcoatRoughness,
                       aniso: m.bumpMap ? m.bumpMap.anisotropy : null,
                       minFilter: m.bumpMap ? m.bumpMap.minFilter : null };
        });
        return out;
    })()""" % ('undefined' if max_aniso is None else repr(max_aniso))
    return _emit(_three_prelude(), expr)


#: ``/`` karakterinden ONCE gelen son anlamli karakter bu kumedeyse, o ``/``
#: bir DUZENLI IFADE literalini acar; degilse bolme islecidir. (Deyim
#: konumunda regex, deger konumunda bolme -- JS'in klasik ayrimi.)
_REGEX_ONCESI = set('(,=:[!&|?{};+-*%~^<>') | {'\n'}
#: Ayni ayrimin anahtar-sozcuk ayagi: ``return /re/`` bir regex'tir.
_REGEX_ONCESI_SOZCUK = (
    'return', 'typeof', 'instanceof', 'in', 'of', 'new', 'delete', 'void',
    'case', 'do', 'else', 'yield', 'await', 'throw',
)


def _regex_konumu(js, i, son_anlamli):
    """``js[i] == '/'`` bir regex mi aciyor, yoksa bolme islecimi?"""
    if js[i + 1:i + 2] in ('/', '*'):
        return False                            # yorum; cagrilmadan once elenir
    if son_anlamli in _REGEX_ONCESI:
        return True
    if son_anlamli.isalnum() or son_anlamli in ('_', '$', ')', ']', '"', "'"):
        # Deger konumu -> bolme. Tek istisna anahtar sozcukler: `return /re/`.
        sozcuk = re.search(r'([A-Za-z_$]+)\s*$', js[max(0, i - 24):i])
        return bool(sozcuk and sozcuk.group(1) in _REGEX_ONCESI_SOZCUK)
    return True


def _strip_comments(js):
    """// ve /* */ yorumlarini + dize/sablon/regex literallerini atar.

    OH D33 / OH-UC-19 -- AYIKLAYICI KORDU, ONARILDI. OLCULDU (a1/once.json
    OH-UC-19, taban 56f88e70): eski govde ``motor_viz3d.js``in 290.650
    baytindan yalniz 66.614'unu birakiyordu -- dosyanin **%77'sini**
    yutuyordu. Sebep tek satirda gorulur (motor_viz3d.js:2535)::

        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');

    ``/"/g`` bir DUZENLI IFADE literalidir; eski govde icindeki ``"``
    karakterini dize baslangici sanip kapanis tirnagini 476 bayt oteden
    buluyordu. Kayan pencere bir daha hizalanmadi: zincirin sonunda tek bir
    sahte "dize" 70.423 bayt kodu yutuyordu.

    Olculen sonuc: ``new THREE.Mesh(Standard|Physical)Material`` dosyada 4
    kez gecerken ayiklanmis metinde **0**, ``castShadow = true`` 8 kez
    gecerken **0** gorunuyordu; iki bekci (``TestMalzeme``,
    ``TestKipVeKontakt``) bu yuzden HEAD'de KIRMIZIYDI. Urun kusursuzdu --
    kirmizi ayiklayicinin kendisiydi (``hrma/static/js/motor_viz3d.js`` bu
    kulvarda SALT OKUR'dur; tek bayti degismedi).

    Govde artik dort literal turunu de tanir: ``'...'``, ``"..."``, sablon
    (backtick) ve ``/regex/flags``. Regex ile bolme ayrimi
    :data:`_REGEX_ONCESI` / :data:`_REGEX_ONCESI_SOZCUK` ile yapilir.
    """
    out, i, n = [], 0, len(js)
    son_anlamli = '\n'          # regex/bolme ayrimi icin son anlamli karakter
    while i < n:
        two = js[i:i + 2]
        if two == '//':
            j = js.find('\n', i)
            i = n if j < 0 else j
        elif two == '/*':
            j = js.find('*/', i + 2)
            i = n if j < 0 else j + 2
        elif js[i] in ('"', "'", '`'):
            q, i = js[i], i + 1
            while i < n and js[i] != q:
                i += 2 if js[i] == '\\' else 1
            i += 1
            out.append('""')
            son_anlamli = '"'
        elif js[i] == '/' and _regex_konumu(js, i, son_anlamli):
            i += 1                                  # acilis '/'
            sinif = False
            while i < n:
                c = js[i]
                if c == '\\':
                    i += 2
                    continue
                if c == '[':
                    sinif = True
                elif c == ']':
                    sinif = False
                elif c == '/' and not sinif:
                    i += 1
                    break
                elif c == '\n':                     # kapanmayan regex -> dur
                    break
                i += 1
            while i < n and js[i].isalpha():        # bayraklar (g, i, m, u, y)
                i += 1
            out.append('/RE/')
            son_anlamli = ')'
        else:
            out.append(js[i])
            if not js[i].isspace():
                son_anlamli = js[i]
            i += 1
    return ''.join(out)


def _numeric_literals(js):
    """Yorumsuz/dizesiz koddaki sayisal literaller (0x... dahil)."""
    code = _strip_comments(js)
    return re.findall(r'(?<![\w.])(0x[0-9a-fA-F]+|\d+\.\d+|\.\d+|\d+)', code)


# ===========================================================================
# 1) TEK KAYNAK — sayısal parametre yalnız RENDER_QUALITY'de
# ===========================================================================

class TestTekKaynak:

    def test_malzeme_fabrikasi_literalsiz(self):
        """createMaterials tek bir sayi yazmaz: hepsi tablodan gelir."""
        govde = _extract('createMaterials')
        lits = _numeric_literals(govde)
        assert lits == [], (
            'createMaterials icinde tablo disi literal: %s' % lits)
        assert 'RENDER_QUALITY.materials' in govde

    def test_malzeme_tablosu_tam(self):
        """Her malzeme kaydinda renk/metalness/roughness/envMapIntensity VAR.

        Ölçüm: eksik `envMapIntensity` sessizce r128 varsayilani 1,0 olur —
        eski kusurun ta kendisi. Alan zorunlu tutulur.
        """
        spec = _emit(_three_prelude(), 'RENDER_QUALITY.materials')
        assert len(spec) == 16
        for ad, kayit in spec.items():
            for alan in ('color', 'metalness', 'roughness', 'envMapIntensity'):
                assert alan in kayit, '%s.%s eksik' % (ad, alan)
            assert 0.0 <= kayit['envMapIntensity'] <= 0.75, (
                '%s ortam haritasini tam aliyor (%.2f) — metaller <=0,75'
                % (ad, kayit['envMapIntensity']))

    def test_golge_uygulamasi_literalsiz(self):
        """_applyShadowFit sayisal karar vermez (0/1 disinda literal yok)."""
        govde = _extract_method('_applyShadowFit')
        lits = [x for x in _numeric_literals(govde) if x not in ('0', '1')]
        assert lits == [], '_applyShadowFit icinde literal: %s' % lits
        assert 'RENDER_QUALITY.shadow' in govde
        assert 'RENDER_QUALITY.lights' in govde

    def test_isik_rigi_literalsiz(self):
        """Üç nokta düzeni (hemi + key + fill) tablodan kurulur.

        Kapsam BİLEREK dar: jant/yanma ışıkları kimliktir, ayrı bekçide
        dondurulur (test_kimlik_isiklari_dondu).
        """
        src = _source()
        bas = src.index('var LI = RENDER_QUALITY.lights;')
        son = src.index('this._rimCyan = new THREE.PointLight')
        blok = src[bas:son]
        lits = _numeric_literals(blok)
        assert lits == [], 'ısık rigi icinde literal: %s' % lits
        for alan in ('hemiSky', 'hemiGround', 'hemiIntensity', 'keyColor',
                     'keyIntensity', 'fillIntensity'):
            assert 'LI.' + alan in blok, '%s tablodan okunmuyor' % alan

    def test_patlatma_ofsetleri_tek_kaynak(self):
        """_applyExplode kendi sayisini yazmaz; tablo golge kadrajiyla ortak."""
        govde = _extract_method('_applyExplode')
        lits = _numeric_literals(govde)
        assert lits == [], '_applyExplode icinde ofset literali: %s' % lits
        assert 'EXPLODE_OFFSETS' in govde
        assert 'EXPLODE_OFFSETS' in _extract('shadowAxisHalfMm')

    def test_zemin_yuksekligi_tek_kaynak(self):
        """Zemin y'si floorYMm'den: golge duzlemi ve golge kamerasi ayni deger."""
        src = _source()
        assert src.count('FLOOR_DROP_RATIO') == 2, (
            'zemin orani kopyalanmis olabilir')
        assert 'floorYMm(this.dims.rcOut + this.dims.flangeLip)' in src
        assert 'floorYMm(R)' in _extract_method('_applyShadowFit')


# ===========================================================================
# 2) MALZEME — gerçek r128 ile kurulup ÖLÇÜLEN değerler
# ===========================================================================

# Kimlik + kasit kilidi. Renk/metalness/roughness/side DEĞİŞMEDİ (ölçüldü:
# düzeltme öncesi nesnelerle birebir); envMapIntensity ve casing tipi
# BİLEREK değişti (bkz. modül açıklaması, madde 3 ve clearcoat gerekçesi).
BEKLENEN_MALZEME = {
    'casing':      ('MeshPhysicalMaterial', '0x9fabbc', 0.72, 0.42, 0.70, 0),
    'casingCut':   ('MeshStandardMaterial', '0xc3ccd8', 0.15, 0.90, 0.20, 2),
    'nozzle':      ('MeshStandardMaterial', '0x525c68', 0.78, 0.38, 0.75, 0),
    'nozzleCut':   ('MeshStandardMaterial', '0x76818f', 0.10, 0.95, 0.20, 2),
    'graphite':    ('MeshStandardMaterial', '0x23262a', 0.42, 0.78, 0.50, 0),
    'graphiteCut': ('MeshStandardMaterial', '0x393e45', 0.10, 0.95, 0.20, 2),
    'grain':       ('MeshStandardMaterial', '0x6d4326', 0.00, 0.94, 0.45, 0),
    'grainCut':    ('MeshStandardMaterial', '0x936243', 0.00, 1.00, 0.20, 2),
    'liner':       ('MeshStandardMaterial', '0x23282e', 0.05, 0.90, 0.40, 0),
    'linerCut':    ('MeshStandardMaterial', '0x3a4046', 0.00, 1.00, 0.20, 2),
    'injector':    ('MeshStandardMaterial', '0xb08d57', 0.85, 0.38, 0.65, 0),
    'injectorCut': ('MeshStandardMaterial', '0xd2b184', 0.20, 0.85, 0.20, 2),
    'bolt':        ('MeshStandardMaterial', '0x343b44', 0.85, 0.40, 0.60, 0),
    'steel':       ('MeshStandardMaterial', '0x6f7883', 0.90, 0.32, 0.70, 0),
    'oring':       ('MeshStandardMaterial', '0x121417', 0.00, 0.97, 0.35, 0),
    'orifice':     ('MeshStandardMaterial', '0x10151a', 0.20, 0.80, 0.35, 0),
}


class TestMalzeme:

    def test_kurulan_malzemeler_donduruldu(self):
        """16 malzeme, ayni adlar/sira, ölçülen renk-metal-pürüz-side."""
        mats = _build_materials()
        assert list(mats) == list(BEKLENEN_MALZEME)
        for ad, (tip, renk, met, rough, env, side) in BEKLENEN_MALZEME.items():
            m = mats[ad]
            assert m['type'] == tip, ad
            assert m['color'] == renk, ad
            assert m['metalness'] == pytest.approx(met), ad
            assert m['roughness'] == pytest.approx(rough), ad
            assert m['envMapIntensity'] == pytest.approx(env), ad
            assert m['side'] == side, ad

    def test_yalnız_kasa_kaplamali(self):
        """Clearcoat PAHALIDIR (PHYSICAL gölgelendirici): tek malzemede."""
        mats = _build_materials()
        fiziksel = [k for k, v in mats.items()
                    if v['type'] == 'MeshPhysicalMaterial']
        assert fiziksel == ['casing']
        cc = mats['casing']['clearcoat']
        assert 0.15 <= cc <= 0.25, 'kaplama bandi disinda: %r' % cc
        assert 0.0 < mats['casing']['ccRough'] < 1.0

    def test_vendor_clearcoat_destekliyor(self):
        """r128 paketinde clearcoat gerçekten var (API doğrulamasi)."""
        vendor = THREE_VENDOR.read_text(encoding='utf-8', errors='ignore')
        for api in ('MeshPhysicalMaterial', 'clearcoatRoughness',
                    'MAX_TEXTURE_MAX_ANISOTROPY_EXT'):
            assert api in vendor, 'three r128 paketinde %s yok' % api
        # MeshPhysicalMaterial, MeshStandardMaterial mirasini korur ⇒
        # scene.environment ve CAD malzeme kisicisi aynen calisir.
        miras = _emit(_three_prelude(),
                      'new THREE.MeshPhysicalMaterial({}).isMeshStandardMaterial')
        assert miras is True

    def test_anizotropi_surucu_tavaniyla_kisilir(self):
        """Fırça izi süzmesi: min(tablo, sürücü) — sürücü yoksa 1."""
        tavan = _emit(_three_prelude(), 'RENDER_QUALITY.texture.brushedAnisotropy')
        assert tavan > 1
        assert _build_materials(16)['casing']['aniso'] == tavan
        assert _build_materials(2)['casing']['aniso'] == 2
        assert _build_materials(None)['casing']['aniso'] == 1
        # mipmap zinciri kurulu olmasa anizotropik süzme anlamsizdi
        assert _build_materials(16)['casing']['minFilter'] == 1008

    def test_isikli_malzeme_kapisiz_kanal_yok(self):
        """Her PBR yüzey malzemesi createMaterials'tan çikar.

        İstisna KAPALI liste: isı haritasi ikizi (vertexColors) — o bir VERİ
        katmanidir, kendi bekçileri vardir. Yeni bir istisna eklenirse bu
        bekçi kirmizi olur.
        """
        src = _strip_comments(_source())
        govde = _extract('createMaterials')
        isili = [m.start() for m in re.finditer(
            r'new THREE\.Mesh(Standard|Physical)Material', src)]
        fabrika_ic = len(re.findall(
            r'new THREE\.Mesh(?:Standard|Physical)Material', govde))
        assert fabrika_ic == 2, 'fabrika iki dal kullanir (standard/physical)'
        isi_govde = _extract_method('_applyHeatMap')
        isi_ic = len(re.findall(
            r'new THREE\.Mesh(?:Standard|Physical)Material', isi_govde))
        assert isi_ic == 2, 'isı haritasi ikizi degismis'
        assert len(isili) == fabrika_ic + isi_ic, (
            'RENDER_QUALITY disinda isikli malzeme kurulmus (kapisiz kanal)')


# ===========================================================================
# 3) IŞIK DENGESİ — bütçe korunumu + kimlik
# ===========================================================================

class TestIsik:

    def _lights(self):
        return _emit(_three_prelude(), 'RENDER_QUALITY.lights')

    def test_yayinik_butce_korundu(self):
        """key + hemi + fill = eski key + hemi = 1,50 (poz kaymasin)."""
        li = self._lights()
        toplam = li['keyIntensity'] + li['hemiIntensity'] + li['fillIntensity']
        assert toplam == pytest.approx(li['diffuseBudget'], abs=1e-12)
        assert li['diffuseBudget'] == pytest.approx(0.95 + 0.55, abs=1e-12), (
            'eski bütçe (key 0,95 + hemi 0,55) degismis')

    def test_key_fill_orani_sinematografik_bantta(self):
        li = self._lights()
        oran = li['keyIntensity'] / li['fillIntensity']
        assert 2.0 <= oran <= 4.0, 'key/fill orani %.2f (2:1..4:1 disinda)' % oran

    def test_dolgu_golge_atmaz_ve_renk_jetonu_ortak(self):
        """İkinci gölge seti sahte kontak üretir; dolgu rengi = gökyüzü."""
        src = _source()
        blok = src[src.index('var fill = new THREE.DirectionalLight'):
                   src.index('this._rimCyan = new THREE.PointLight')]
        assert 'fill.castShadow = false' in blok
        assert 'new THREE.DirectionalLight(LI.hemiSky, LI.fillIntensity)' in blok

    def test_kimlik_isiklari_dondu(self):
        """Neon jant + yanma isiklari AYNEN: renk ve yoğunluk literalleri."""
        src = _source()
        for satir in (
                'this._rimCyan = new THREE.PointLight(0x00e5ff, 0.55, 0, 2);',
                'this._rimOrange = new THREE.PointLight(0xff7a1a, 0.15, 0, 2);',
                'this._combLight = new THREE.PointLight(0xff8c33, 0, 0, 2);',
                'this._exitLight = new THREE.PointLight(0xffb066, 0, 0, 2);'):
            assert satir in src, 'kimlik isigi degismis: %s' % satir
        # CAD çikisinda jant yoğunluklarinin geri yükleme varsayilanlari
        assert 's.rimCyan : 0.55' in src and 's.rimOrange : 0.15' in src

    def test_ton_esleme_ve_golge_tipi_kilitli(self):
        """Kimlik: ACES + poz 1,1 + PCFSoft + sRGB cikis — dokunulmadi."""
        src = _source()
        assert 'THREE.ACESFilmicToneMapping' in src
        assert re.search(r'toneMappingExposure\s*=\s*1\.1', src)
        assert 'this.renderer.shadowMap.type = THREE.PCFSoftShadowMap' in src
        assert 'this.renderer.outputEncoding = THREE.sRGBEncoding' in src
        assert 'this.scene.background = new THREE.Color(0x070d17)' in src


# ===========================================================================
# 4) GÖLGE KADRAJI — bağımsız izdüşümle kırpılma kanıtı
# ===========================================================================

def _fit(explode=0.0, map_size=None, L=L_DEFAULT, R=R_DEFAULT):
    pre = _pure_prelude()
    ms = map_size if map_size is not None else _emit(
        pre, 'RENDER_QUALITY.shadow.mapSizeHigh')
    expr = ("shadowFrustumFit(shadowAxisHalfMm(%r, %r), %r, floorYMm(%r), "
            "{x: %r, y: %r, z: %r}, %d, RENDER_QUALITY.shadow.fitMargin)"
            % (L, explode, R, R,
               L * 0.8, L * 1.1, L * 0.7, ms))
    return _emit(pre, expr)


def _light_basis(pos):
    """three.js lookAt(origin) kuralinin BAGIMSIZ Python kurulumu."""
    d = math.sqrt(sum(c * c for c in pos))
    z = [c / d for c in pos]
    xl = math.hypot(z[2], z[0])
    x = [z[2] / xl, 0.0, -z[0] / xl]
    y = [z[1] * x[2] - z[2] * x[1],
         z[2] * x[0] - z[0] * x[2],
         z[0] * x[1] - z[1] * x[0]]
    return x, y, z, d


def _corners(half_axis, r):
    return [(sx * half_axis, sy * r, sz * r)
            for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]


class TestGolgeKadraji:

    def test_kadraj_hicbir_koseyi_kirpmaz(self):
        """Model köşeleri VE zemine düşen gölgeleri frustum icinde.

        İzdüşüm burada Python'da SIFIRDAN kurulur (JS'ten kopya degil).
        """
        pos = (L_DEFAULT * 0.8, L_DEFAULT * 1.1, L_DEFAULT * 0.7)
        x, y, z, dist = _light_basis(pos)
        floor_y = -R_DEFAULT * 1.9
        for f in (0.0, 0.5, 1.0):
            fit = _fit(explode=f)
            half_axis = L_DEFAULT * (0.5 + 0.48 * f)
            for p in _corners(half_axis, R_DEFAULT):
                u = sum(p[i] * x[i] for i in range(3))
                v = sum(p[i] * y[i] for i in range(3))
                w = dist - sum(p[i] * z[i] for i in range(3))
                assert abs(u) <= fit['halfW'] + 1e-9, (f, p, u)
                assert abs(v) <= fit['halfH'] + 1e-9, (f, p, v)
                assert fit['near'] <= w <= fit['far'], (f, p, w)
                # köşenin zemine düşen gölgesi de kadrajda olmali
                s = (p[1] - floor_y) / z[1]
                fp = (p[0] - s * z[0], floor_y, p[2] - s * z[2])
                wf = dist - sum(fp[i] * z[i] for i in range(3))
                assert fit['near'] <= wf <= fit['far'], (f, p, wf)

    def test_kadraj_bos_dokuyu_bitirdi(self):
        """Yarı boyutlar ESKİ ±L kuralindan belirgin küçük (bos doku)."""
        fit = _fit()
        assert fit['halfW'] < 0.45 * OLD_SHADOW_HALF
        assert fit['halfH'] < 0.40 * OLD_SHADOW_HALF
        # kadraj hâlâ modeli kapsiyor: yari boy izdusumunden buyuk
        assert fit['halfW'] > 0.30 * L_DEFAULT

    def test_teksel_kazanci_olculdu(self):
        """HQ tekseli eski 1,63 mm'den en az 3 kat ince."""
        fit = _fit()
        assert fit['texelW'] < OLD_TEXEL_MM / 3.0
        assert fit['texelH'] < OLD_TEXEL_MM / 3.0
        # patlatilmis (en genis) hâlde bile eski kuraldan iyi
        patlak = _fit(explode=1.0)
        assert patlak['texelW'] < OLD_TEXEL_MM

    def test_perf_kipi_gölgeyi_ucuzlatir_ama_bozmaz(self):
        """1024 doku (1/16 bellek) ile teksel eski 2048 kuralindan iyi."""
        boy = _emit(_pure_prelude(),
                    '[RENDER_QUALITY.shadow.mapSizePerf, '
                    'RENDER_QUALITY.shadow.mapSizeHigh]')
        assert boy[0] < OLD_SHADOW_MAP < boy[1]
        perf = _fit(map_size=boy[0])
        assert perf['texelW'] <= OLD_TEXEL_MM
        assert perf['texelH'] <= OLD_TEXEL_MM

    def test_bias_bandi_ve_tureviligi(self):
        """bias dünya ölçüsünden türetilir ve literatür bandina oturur."""
        for f in (0.0, 1.0):
            for ms in (1024, 4096):
                fit = _fit(explode=f, map_size=ms)
                assert BIAS_BAND[0] <= fit['bias'] <= BIAS_BAND[1], (f, ms, fit)
                # bias = -biasDepthMm / (far - near) — bagimsiz yeniden hesap
                mm = _emit(_pure_prelude(), 'RENDER_QUALITY.shadow.biasDepthMm')
                assert fit['bias'] == pytest.approx(
                    -mm / (fit['far'] - fit['near']), rel=1e-12)
                # normalBias = katsayi × en KABA teksel
                kat = _emit(_pure_prelude(),
                            'RENDER_QUALITY.shadow.normalBiasTexels')
                assert fit['normalBias'] == pytest.approx(
                    kat * max(fit['texelW'], fit['texelH']), rel=1e-12)

    def test_near_uzaklik_far_sirali(self):
        """Eski kod near'i hic ayarlamiyordu (varsayilan 0,5)."""
        fit = _fit()
        assert 0 < fit['near'] < fit['dist'] < fit['far']
        assert fit['near'] > 1.0, 'near hâlâ varsayilan yakinliginda'
        assert fit['far'] < L_DEFAULT * 6, 'far eski (6·L) kuralindan dar olmali'

    def test_patlatilmis_parcalar_kadrajda(self):
        """En uzağa giden parça (EXPLODE_OFFSETS max) f=1'de kadraj icinde."""
        ofsetler = _emit(_pure_prelude(), 'EXPLODE_OFFSETS')
        enBuyuk = max(abs(v) for v in ofsetler.values())
        fit = _fit(explode=1.0)
        pos = (L_DEFAULT * 0.8, L_DEFAULT * 1.1, L_DEFAULT * 0.7)
        x, y, _z, _d = _light_basis(pos)
        for ad, off in ofsetler.items():
            # parçanin en uç köşesi: eksende ofset + yari boy, radyal R
            for sx in (-1, 1):
                p = (off * L_DEFAULT + sx * L_DEFAULT * 0.5, R_DEFAULT, R_DEFAULT)
                u = sum(p[i] * x[i] for i in range(3))
                v = sum(p[i] * y[i] for i in range(3))
                assert abs(u) <= fit['halfW'] + 1e-9, (ad, u)
                assert abs(v) <= fit['halfH'] + 1e-9, (ad, v)
        assert enBuyuk == pytest.approx(0.48)


# ===========================================================================
# 5) KALİTE KİPİ + KONTAKT
# ===========================================================================

class TestKipVeKontakt:

    def test_kalite_kipi_golgeye_bagli(self):
        """setQuality gölge dokusunu da degistirir (eskiden sabitti)."""
        govde = _extract_method('setQuality')
        assert '_applyShadowFit' in govde
        assert '_perfMode' in _extract_method('_applyShadowFit')

    def test_mapsize_degisimi_eski_hedefi_atar(self):
        """r128 gölge hedefini YALNIZ map===null iken kurar — vendor kaniti."""
        vendor = THREE_VENDOR.read_text(encoding='utf-8', errors='ignore')
        assert re.search(r'if\(null===\w+\.map\)', vendor), (
            'r128 golge hedefi kurulum kosulu degismis')
        govde = _extract_method('_applyShadowFit')
        i_dispose = govde.index('key.shadow.map.dispose()')
        i_null = govde.index('key.shadow.map = null')
        i_set = govde.index('key.shadow.mapSize.set')
        assert i_dispose < i_null < i_set, (
            'mapSize eski hedef atilmadan degistirilirse sessizce yok sayilir')

    def test_golge_kadraji_uc_yerden_tazelenir(self):
        """Kadraj bayatlamasin: geometri, patlatma ve kalite kipi."""
        src = _source()
        assert src.count('_applyShadowFit()') >= 3
        for metot in ('_fitCamera', '_applyExplode', 'setQuality'):
            assert '_applyShadowFit()' in _extract_method(metot), metot

    def test_atan_her_mesh_golge_de_alir(self):
        """Ölçüm: 5 donanim mesh'i gölge ATIP ALMIYORDU (yüzen parça hissi).

        Bilinçli istisna: kesit kapaklari (cap) — kesit yüzü düz ve
        gölgelenirse kesit okunmaz olur; ikisi de false yazilidir.
        """
        src = _strip_comments(_source())
        atan = set(re.findall(r'(\w+)\.castShadow = true', src))
        alan = set(re.findall(r'(\w+)\.receiveShadow = true', src))
        # 'key' bir IŞIK (gölge atar, almaz); 'shadowPlane' gölge yakalayici
        # zemin (alir, atmaz). Ikisi disinda kümeler ESIT olmali.
        assert 'key' in atan and 'key' not in alan
        assert 'shadowPlane' in alan and 'shadowPlane' not in atan
        assert (atan - {'key'}) == (alan - {'shadowPlane'}), (
            'gölge atan ama almayan mesh var: %s'
            % sorted((atan - {'key'}) - alan))
        # A1a sahne-sahte-veri (CM-S1): tabandaki 6 adın ikisi (ateşleyici
        # 'ig', lüle cıvatası 'bolt') KESİRLE çizilen parçalardı ve söküldü;
        # kalan 4 ad: tane/katı 'mesh', kapak cıvatası 'cbolt' (yalnız
        # yayımlanan delik + künyeyle), soğutma kanalı 'chMesh', pintle 'post'.
        assert len(atan - {'key'}) >= 4, 'gölge atan mesh sayisi dustu'
        assert '.castShadow = false' in src and '.receiveShadow = false' in src

    def test_gercek_isik_nesnesine_uygulanir(self):
        """_applyShadowFit'in KENDİSİ gerçek r128 ışığı üzerinde koşturulur.

        Kaynak taramasi degil davranis ölçümü: ışık konumu, gölge kamerasi
        alanlari, bias'lar ve kalite kipi geçişinde doku atma.
        """
        govde = _extract_method('_applyShadowFit')
        pre = '\n'.join([
            _three_prelude()[:_three_prelude().index('function makeCanvas')],
            _var_block('EXPLODE_OFFSETS'),
            re.search(r'var FLOOR_DROP_RATIO = [^;]+;', _source()).group(0),
            _extract('floorYMm'), _extract('shadowFrustumFit'),
            _extract('shadowAxisHalfMm'),
            govde.replace('MotorScene.prototype._applyShadowFit = function',
                          'var applyShadowFit = function') + ';',
        ])
        expr = """(function () {
            var key = new THREE.DirectionalLight(0xffffff, 1)
            var fill = new THREE.DirectionalLight(0xffffff, 1)
            var sahne = { _keyLight: key, _fillLight: fill,
                          _totalLen: %r, _explodeF: 0, _perfMode: false,
                          dims: { rcOut: %r, flangeLip: 0 } }
            var hq = applyShadowFit.call(sahne)
            var sc = key.shadow.camera
            var ilk = { mapSize: key.shadow.mapSize.x,
                        left: sc.left, right: sc.right, top: sc.top,
                        bottom: sc.bottom, near: sc.near, far: sc.far,
                        bias: key.shadow.bias, normalBias: key.shadow.normalBias,
                        keyPos: [key.position.x, key.position.y, key.position.z],
                        fillPos: [fill.position.x, fill.position.y, fill.position.z],
                        fit: hq }
            // Patlatilmis görünüm: kadraj GENISLEMELI (yoksa uzaga giden
            // parçanin gölgesi kirpilir)
            sahne._explodeF = 1
            var patlak = applyShadowFit.call(sahne)
            var patlakSag = key.shadow.camera.right
            sahne._explodeF = 0
            applyShadowFit.call(sahne)
            // Kalite kipi degisimi: once doku kurulmus gibi davran
            var atildi = false
            key.shadow.map = { dispose: function () { atildi = true } }
            sahne._perfMode = true
            var perf = applyShadowFit.call(sahne)
            return { ilk: ilk, perfMapSize: key.shadow.mapSize.x,
                     atildi: atildi, mapNull: key.shadow.map === null,
                     perfTexel: perf.texelW, patlak: patlak,
                     patlakSag: patlakSag, kapaliSag: ilk.right }
        })()""" % (L_DEFAULT, R_DEFAULT)
        r = _emit(pre, expr)
        ilk, fit = r['ilk'], r['ilk']['fit']
        assert ilk['mapSize'] == 4096
        assert ilk['right'] == pytest.approx(fit['halfW'])
        assert ilk['left'] == pytest.approx(-fit['halfW'])
        assert ilk['top'] == pytest.approx(fit['halfH'])
        assert ilk['bottom'] == pytest.approx(-fit['halfH'])
        assert ilk['near'] == pytest.approx(fit['near'])
        assert ilk['far'] == pytest.approx(fit['far'])
        assert ilk['bias'] == pytest.approx(fit['bias'])
        assert ilk['normalBias'] == pytest.approx(fit['normalBias'])
        # ışık konumu tablodan (keyDir/fillDir × toplam boy)
        assert ilk['keyPos'] == pytest.approx(
            [L_DEFAULT * 0.8, L_DEFAULT * 1.1, L_DEFAULT * 0.7])
        assert ilk['fillPos'][0] < 0 < ilk['fillPos'][1], 'dolgu karsi yönden'
        # patlatma kadraja BAGLI: aynı sahne f=1'de genisler ve saf
        # fonksiyonun f=1 çiktisiyla birebir ayni
        beklenen = _fit(explode=1.0)
        assert r['patlak']['halfW'] == pytest.approx(beklenen['halfW'])
        assert r['patlakSag'] == pytest.approx(beklenen['halfW'])
        assert r['patlakSag'] > r['kapaliSag'] * 1.5
        # kalite kipi: doku küçülür ve ESKİ hedef gerçekten atilir
        assert r['perfMapSize'] == 1024
        assert r['atildi'] is True and r['mapNull'] is True
        assert r['perfTexel'] > fit['texelW']

    def test_zemin_golge_alir_ve_opaklik_tablodan(self):
        govde = _extract_method('_buildMotor')
        assert 'shadowPlane.receiveShadow = true' in govde
        assert 'RENDER_QUALITY.shadow.floorOpacity' in govde
        # Zemin opakligi DEGISMEDI: fon 0x070d17 üzerinde siyah gölge
        # farki zaten <=7/255 — kontakt hissi öz-gölgeden gelir (rapor).
        assert _emit(_pure_prelude(),
                     'RENDER_QUALITY.shadow.floorOpacity') == 0.32
