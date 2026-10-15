# -*- coding: utf-8 -*-
"""ÖH D32 · arayuz-panel · aşama 1/2 — bekçiler.

Her sınıf, ``docs/scofield/raw/OH/D32/arayuz-panel/a1/once.json`` ile
ÖLÇÜLMÜŞ bir kusuru gördüğü ters-mutasyonla kanıtlanmıştır
(``mutasyon.py`` / ``mutasyon.json``).

Kapsanan kalemler:
  * P5B4-18   — `kN(null)` "0.00 kN" basıyordu (Fable TOPLU ŞART)
  * OH-D31-07 — kısmi tarama kolunda `Number(x) || 0` sıfır uyduruyordu
  * OH-D31-18 — `#ffb347` amber tokene çekildi (değer değişmedi)
  * OH-D31-05 — `al2o3` seçeneği + iki ölü alt panel söküldü
  * P12bB4-07 — §14.1 başlığındaki kazanılmamış "NASA SP-125" künyesi
  * P12bS1-01 — ÖK-21 çift-katman kümesi gerileme kilidi (kısmen)
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
TPL = KOK / 'hrma' / 'templates'
JS = KOK / 'hrma' / 'static' / 'js'
CSS = KOK / 'hrma' / 'static' / 'css'

SAYI = r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?'
RE_SCRIPT = re.compile(r'<script\b(?![^>]*\bsrc\s*=)[^>]*>(.*?)</script>',
                       re.S | re.I)

node_gerekli = pytest.mark.skipif(shutil.which('node') is None,
                                  reason='node yok')


def _oku(p):
    return Path(p).read_text(encoding='utf-8')


def _satirici(metin):
    return [m.group(1) for m in RE_SCRIPT.finditer(metin)]


def _govde(metin, ad):
    """``function ad(`` gövdesini (imza dâhil) parantez sayımıyla çıkar."""
    for blok in _satirici(metin):
        i = blok.find('function %s(' % ad)
        if i < 0:
            continue
        j = blok.find('{', i)
        derinlik, k = 0, j
        while k < len(blok):
            if blok[k] == '{':
                derinlik += 1
            elif blok[k] == '}':
                derinlik -= 1
                if derinlik == 0:
                    return blok[i:k + 1]
            k += 1
    return ''


def _node(kod, tmp_path):
    yol = tmp_path / 'h.js'
    yol.write_text(kod, encoding='utf-8')
    c = subprocess.run(['node', str(yol)], capture_output=True, text=True,
                       timeout=120)
    assert c.returncode == 0, c.stderr[-1500:]
    return json.loads(c.stdout)


# ======================================================================
# P5B4-18 (Fable TOPLU ŞART) — kN sarmalayıcısı null'dan sıfır üretmez
# ======================================================================
class TestP5B418GimbalKnKapisi:
    """ÖLÇÜLDÜ (once.json · M2): `kN(null)` → "0.00 kN".

    Sebep JS'in kendisi: `null / 1000 === 0`, yani hrmaFmt'e SAYI gidiyor
    ve onun '—' sözleşmesi hiç devreye girmiyordu. Uç halka momentini
    kazanmadığında üç cıvata alanını NULL yayımlar ve durumu
    `bolts.moment_induced_loads_status = 'not_evaluated'` ile beyan eder
    (hrma/analysis/gimbal_mount.py:768, :805); panel o beyanı bir TASARIM
    YÜKÜNE ("0,00 kN") çeviriyordu.
    """

    #: Ucun halka momenti kazanılmadığında NULL yayımladığı alanlar.
    NULL_ALANLARI = (
        'moment_induced_max_N',
        'max_tension_if_axial_is_tensile_N',
        'max_tension_if_axial_is_compressive_N',
    )

    @pytest.fixture(scope='class')
    def govde(self):
        g = _govde(_oku(TPL / 'liquid.html'), 'renderGimbalResult')
        assert g, 'renderGimbalResult bulunamadı'
        return g

    def _kn(self, govde):
        i = govde.find('const kN = function')
        assert i >= 0, 'kN sarmalayıcısı bulunamadı'
        derinlik, j = 0, govde.index('{', i)
        for k in range(j, len(govde)):
            if govde[k] == '{':
                derinlik += 1
            elif govde[k] == '}':
                derinlik -= 1
                if derinlik == 0:
                    return govde[i:k + 2]
        raise AssertionError('kN gövdesi kapanmadı')

    def test_kn_sayisal_olmayan_girdiyi_bolmez(self, govde):
        """Statik kapı: bölme SAYI kapısının ARKASINDA olmalı."""
        kn = self._kn(govde)
        assert "typeof v === 'number'" in kn, (
            'kN sarmalayıcısında sayı kapısı yok — `null / 1000 === 0` '
            'yeniden "0.00 kN" basar (P5B4-18 yeniden açıldı): %s' % kn)
        # Kapı bölmeyi GERÇEKTEN koruyor mu: `v / 1000` kapının sağında.
        kapi = kn.index("typeof v === 'number'")
        bolme = kn.index('v / 1000')
        assert bolme > kapi, (
            'bölme sayı kapısından ÖNCE yapılıyor; kapı kusuru görmez')

    def test_uc_null_alanlarini_hala_yayimliyor(self):
        """Kapının koruduğu sözleşme ucun kendi sözleşmesidir."""
        g = _oku(KOK / 'hrma' / 'analysis' / 'gimbal_mount.py')
        for alan in self.NULL_ALANLARI:
            assert re.search(
                r"'%s':\s*\(?\s*\n?\s*None if halka_momenti_kazanilmadi"
                % re.escape(alan), g), (
                '%s artık halka momenti kazanılmadığında None dönmüyor; '
                'panel kapısının dayandığı sözleşme değişti' % alan)
        assert "'moment_induced_loads_status': (" in g

    def test_moment_turevli_satirlar_hala_kN_ile_basiliyor(self, govde):
        """Kapı DOĞRU yerde: üç null alanı gerçekten `kN()`'den geçiyor."""
        basilan = set(re.findall(r'kN\(d\.bolts\.(\w+)\)', govde))
        eksik = [a for a in self.NULL_ALANLARI if a not in basilan]
        assert not eksik, (
            'şu alanlar artık kN() sarmalayıcısından geçmiyor, kapı onları '
            'korumuyor: %s' % eksik)

    @node_gerekli
    def test_canli_kn_davranisi(self, govde, tmp_path):
        """Canlı ölçüm: null → '—', sayı → değişmeden aynı sayı."""
        o = _node("""
'use strict';
function hrmaFmt(v, dec, unit) {
    if (typeof v !== 'number' || !isFinite(v)) return '\\u2014';
    const s = v.toFixed(dec != null ? dec : 1);
    return unit ? (s + ' ' + unit) : s;
}
%s
process.stdout.write(JSON.stringify({
    bos: kN(null), tanimsiz: kN(undefined), nan: kN(NaN),
    dize: kN('13937'), sayi: kN(13937.128436), sifir: kN(0)
}));
""" % self._kn(govde), tmp_path)
        assert o['bos'] == '\u2014', (
            'kN(null) hâlâ sayı basıyor: %r (P5B4-18)' % o['bos'])
        assert o['tanimsiz'] == '\u2014'
        assert o['nan'] == '\u2014'
        assert o['dize'] == '\u2014', 'dize girdiden sayı türetiliyor'
        # GERİLEME KİLİDİ: gerçek sayı yolu değişmedi.
        assert o['sayi'] == '13.94 kN'
        # Ucun GERÇEKTEN hesapladığı sıfır beyan edilmeye devam eder.
        assert o['sifir'] == '0.00 kN'


# ======================================================================
# OH-D31-07 — parametrik kısmi kol da fail-closed
# ======================================================================
class TestOHD3107ParametrikSayaclar:
    """ÖLÇÜLDÜ (once.json · M5): üç sayaç da `Number(x) || 0` idi.

    fix-34b KESİK kolu `sayac()` ile fail-closed'a çevirmiş, kardeş
    KISMİ kol "en küçük hunk" kuralıyla dışarıda kalmıştı: uç
    `points_requested`i yayımlamazsa ekranda "1 of 0 sweep points could
    not be computed" yazıyordu.
    """

    @pytest.fixture(scope='class')
    def adv(self):
        return _oku(TPL / 'advanced.html')

    def test_uydurma_sifir_ikamesi_kalmadi(self, adv):
        kalan = re.findall(
            r'Number\(\s*results\.(points_\w+)\s*\)\s*\|\|\s*0', adv)
        assert not kalan, (
            'tarama sayaçlarında uydurma sıfır geri geldi: %s (OH-D31-07)'
            % sorted(set(kalan)))

    def test_sayac_tek_kaynak(self, adv):
        """`sayac` sözleşmesi bir kez tanımlı (iki kol ORTAK kullanır)."""
        n = len(re.findall(r'const sayac\s*=', adv))
        assert n == 1, (
            'sayac sözleşmesi %d kez tanımlı — kollar ayrışabilir (TEK '
            'KAYNAK)' % n)
        assert "const sayac = (v) => (isFiniteNum(v) ? v : '?');" in adv

    def test_dusen_esigi_uydurma_sifira_dusmuyor(self, adv):
        assert re.search(
            r'const dusen = isFiniteNum\(results\.points_failed\)', adv), (
            '`dusen` eşiği hâlâ sayısal ikameyle kuruluyor')

    @node_gerekli
    def test_canli_sayac_sozlesmesi(self, tmp_path):
        """Uç alanları hiç yayımlamazsa ekranda '?' olur, 0 DEĞİL."""
        o = _node("""
'use strict';
function isFiniteNum(x) { return typeof x === 'number' && isFinite(x); }
const sayac = (v) => (isFiniteNum(v) ? v : '?');
function kol(results) {
    const dusen = isFiniteNum(results.points_failed)
        ? results.points_failed : null;
    const istenen = sayac(results.points_requested);
    const basarili = sayac(results.points_succeeded);
    return { dusen: dusen, istenen: istenen, basarili: basarili,
             kismi_kol: (dusen > 0) };
}
process.stdout.write(JSON.stringify({
    bos: kol({}),
    null_alan: kol({ points_failed: null, points_requested: null,
                     points_succeeded: null }),
    dize: kol({ points_failed: '1', points_requested: '10' }),
    gercek: kol({ points_failed: 1, points_requested: 10,
                  points_succeeded: 9 })
}));
""", tmp_path)
        for ad in ('bos', 'null_alan', 'dize'):
            o2 = o[ad]
            assert o2['istenen'] == '?', (
                '%s: istenen uyduruldu: %r' % (ad, o2['istenen']))
            assert o2['basarili'] == '?', (
                '%s: basarili uyduruldu: %r' % (ad, o2['basarili']))
            assert o2['kismi_kol'] is False, (
                '%s: "düşen nokta var" iddiası kazanılmadan kuruldu' % ad)
        # GERİLEME KİLİDİ: gerçek sayılarda davranış değişmedi.
        assert o['gercek'] == {'dusen': 1, 'istenen': 10, 'basarili': 9,
                               'kismi_kol': True}


# ======================================================================
# OH-D31-18 — amber ailesinin üçüncü değeri token katmanında
# ======================================================================
class TestOHD3118AmberTokeni:
    """ÖLÇÜLDÜ (once.json · M6): `#ffb347` üç yerde ÇIPLAK sabitti.

    Token RENK DEĞERİNİ DEĞİŞTİRMEZ; yalnız değerin TEK KAYNAĞINI kurar.
    İki `SOURCE_COLORS` tablosu `var()` kullanamaz (değerler canvas
    `fillStyle`ına ve `new THREE.Color(...)`a gidiyor, ikisi de CSS
    değişkeni çözmez), bu yüzden aynalar tokenin değerine BURADA
    kilitlenir.
    """

    AD = 'hd-amber-source'
    DEGER = '#ffb347'
    #: Tokeni `var()` ile okuyamayan, değeri elde taşıyan aynalar.
    AYNALAR = ('hrma/static/js/motor_viz3d.js',
               'hrma/static/js/analysis_dock.js')

    def _token(self, rel):
        m = re.search(r'--%s:\s*(#[0-9a-fA-F]{6})\s*;' % self.AD, _oku(KOK / rel))
        assert m, '--%s %s içinde tanımlı değil' % (self.AD, rel)
        return m.group(1).lower()

    def test_token_iki_css_dosyasinda_ayni_degerle(self):
        t = self._token('hrma/static/css/theme.css')
        h = self._token('hrma/static/css/hd_doc.css')
        assert t == h == self.DEGER, (
            'amber kaynak tokeni ayrıştı ya da değeri değişti: theme=%s '
            'hd_doc=%s (RENK DEĞERİ DEĞİŞMEZ kuralı)' % (t, h))

    def test_aynalar_tokenin_degerinde(self):
        """İki SOURCE_COLORS tablosu tokenden sessizce sapamaz."""
        token = self._token('hrma/static/css/theme.css')
        for rel in self.AYNALAR:
            s = _oku(KOK / rel)
            m = re.search(r'assumed:\s*\'(#[0-9a-fA-F]{6})\'', s)
            assert m, '%s: SOURCE_COLORS.assumed bulunamadı' % rel
            assert m.group(1).lower() == token, (
                '%s: SOURCE_COLORS.assumed (%s) `--%s` tokeninden (%s) '
                'ayrıştı' % (rel, m.group(1), self.AD, token))

    def test_ciplak_sabit_yalniz_iki_beyanli_aynada(self):
        """Tokene bağlanmamış `#ffb347` YALNIZ iki aynanın `assumed:` satırında.

        DİKKAT (D31 dersi 20 / sahte yeşil): ilk yazımda iddia "kalan
        geçişlerin DOSYALARI iki aynadan ibaret" idi; ters mutasyon
        (``mutasyon.json`` · OH-D31-18/ciplak-sabit) bunun KÖR olduğunu
        gösterdi — aynı dosyaya çıplak bir CSS dizesi geri konunca bekçi
        YEŞİL kalıyordu. İddia artık SATIRIN KENDİSİNİ ölçer: çıplak kalan
        her geçiş `assumed: '#ffb347'` tablo satırı olmak ZORUNDA.
        """
        kalan = []
        for p in sorted((KOK / 'hrma').rglob('*')):
            if not p.is_file() or p.suffix not in ('.js', '.css', '.html'):
                continue
            blok = False
            for no, satir in enumerate(_oku(p).splitlines(), 1):
                sr = satir.strip()
                if blok:
                    if '*/' in sr:
                        blok = False
                    continue
                if sr.startswith('/*') and '*/' not in sr:
                    blok = True
                    continue
                if self.DEGER not in satir:
                    continue
                if sr.startswith(('//', '*', '<!--', '/*')):
                    continue
                temiz = re.sub(r'var\(\s*--hd-[a-z0-9-]+\s*,\s*%s\s*\)'
                               % self.DEGER, '', satir)
                temiz = re.sub(r'--%s\s*:\s*%s\s*;' % (self.AD, self.DEGER),
                               '', temiz)
                if self.DEGER in temiz:
                    kalan.append((str(p.relative_to(KOK)), no, sr))

        aykiri = [(f, n, t) for f, n, t in kalan
                  if f not in self.AYNALAR
                  or not re.match(r"assumed:\s*'%s',?" % self.DEGER, t)]
        assert not aykiri, (
            'tokene bağlanmamış çıplak %s: %s — CSS dizesi olan her geçiş '
            '`var(--%s, %s)` ile yazılmalı; elde taşınabilen TEK istisna '
            'canvas/THREE aynalarının `assumed:` tablo satırıdır'
            % (self.DEGER, aykiri, self.AD, self.DEGER))
        assert sorted(f for f, _n, _t in kalan) == sorted(self.AYNALAR), (
            'iki ayna da tabloyu taşımıyor (ya da biri kayboldu): %s'
            % sorted({f for f, _n, _t in kalan}))


# ======================================================================
# OH-D31-05 — al2o3 seçeneği + iki ölü alt panel söküldü
# ======================================================================
class TestOHD3105OluYakitYuzeyi:
    """Berke karar dosyası §7 (a). ÖLÇÜLDÜ (once.json · M4).

    `al2o3` bir VERİ eksikliği değil, KATEGORİ hatasıdır: alüminyum oksit
    yakıt değildir, uç onu `not_a_fuel` ile reddediyor. `mixture`/`custom`
    panelleri ise HİÇBİR yoldan açılamıyordu (ikisi de `disabled`).
    """

    @pytest.fixture(scope='class')
    def adv(self):
        return _oku(TPL / 'advanced.html')

    def _secici(self, adv):
        m = re.search(r'<select id="fuel_type".*?</select>', adv, re.S)
        assert m, '#fuel_type seçicisi bulunamadı'
        return re.findall(r'<option value="([^"]+)"([^>]*)>', m.group(0))

    def test_al2o3_secicide_yok(self, adv):
        anahtarlar = [v for v, _ in self._secici(adv)]
        assert 'al2o3' not in anahtarlar, (
            'al2o3 seçiciye geri döndü — yakıt DEĞİL (kategori hatası), '
            'uç `not_a_fuel` ile reddediyor (OH-D31-05)')

    def test_sunulan_her_yakit_cozucunun_yakitidir(self, adv):
        """Karşı yön: söküm doğru yakıtları düşürmedi."""
        from hrma.engines.combustion_analysis import (
            SUPPORTED_HYBRID_FUEL_KEYS)
        destekli = set(SUPPORTED_HYBRID_FUEL_KEYS)
        secenekler = self._secici(adv)
        sunulan = {v for v, r in secenekler
                   if not re.search(r'\bdisabled\b', r)}
        assert sunulan == destekli, (
            'seçici ile çözücü ayrıştı; yalnız seçicide: %s, yalnız '
            'çözücüde: %s' % (sorted(sunulan - destekli),
                              sorted(destekli - sunulan)))

    def test_olu_alt_paneller_sokuldu(self, adv):
        for eid in ('custom_fuel_mixture', 'custom_fuel_config'):
            assert 'id="%s"' % eid not in adv, (
                '#%s geri geldi — erişilemez ölü girdi yüzeyi (OH-D31-05)'
                % eid)
        assert not re.search(r'id="mixture_\w+"', adv), (
            'karışım yüzde alanları geri geldi'
        )

    def test_yakit_kolu_sokulen_paneli_hic_okumuyor(self, adv):
        """ÇEVRİLDİ (ÖH D33-KOLAY · OH-D32-11) — DAHA SIKI ölçüt.

        ESKİ SÖZLEŞME: ``customConfig.style`` / ``customMixture.style``
        satırlarının en az ikişer kez ve `if (…)` koruması ardında
        bulunması. O ölçüt sökülen panellerin OKUNMAYA devam etmesini şart
        koşuyordu: iki ``getElementById`` her çağrıda null dönüyor, dört
        koruma hiçbir zaman girilmiyordu — ölü kodun kendisi kilitliydi ve
        hayalet alan envanteri 2 -> 4 şişiyordu (ölçüm: raw/OH/D33/
        arayuz-panel/a1/once.json · M1).

        YENİ SÖZLEŞME: sökülen paneller HİÇ okunmaz. Kalemin koruduğu
        davranış (P17B4-01: 'custom'/'mixture' seçiliyken paylaşılan
        alanlar EZİLMEZ) erken dönüşle kilitli kalır ve aşağıdaki canlı
        node bekçisiyle ayrıca ölçülür.
        """
        g = _govde(adv, 'updateFuelConfig')
        assert g, 'updateFuelConfig bulunamadı'
        # Künye yorumları kusurun kendisini ALINTILIYOR; bekçi KODU ölçer.
        kod = '\n'.join(l for l in g.splitlines()
                        if not l.strip().startswith('//'))
        for eid in ('custom_fuel_config', 'custom_fuel_mixture'):
            assert eid not in kod, (
                'sökülen panel yine okunuyor (hayalet alan): %s' % eid)
        for ad in ('customConfig', 'customMixture'):
            assert ad not in kod, (
                '%s değişkeni geri geldi: ölü panelin okunması' % ad)
        # P17B4-01 kazanımı: iki yakıt tipi de ERKEN DÖNER.
        for tip in ("'custom'", "'mixture'"):
            assert tip in kod, 'erken dönüş kolu kayboldu: %s' % tip
        assert re.search(r"fuelType === 'custom'[\s\S]{0,200}?return;", kod), (
            'custom kolu artık erken dönmüyor: paylaşılan alanlar ezilir')

    @node_gerekli
    def test_canli_yakit_kolu_atmiyor_ve_alan_ezmiyor(self, adv, tmp_path):
        """Canlı: 'mixture'/'custom' geri yüklenirse kol ÖLMEZ.

        Ve paylaşılan alanlar (P17B4-01 kazanımı) EZİLMEZ.
        """
        g = _govde(adv, 'updateFuelConfig')
        o = _node("""
'use strict';
const alanlar = {
    fuel_type: { value: '' },
    fuel_density: { value: '920' },
    regression_a: { value: '3.68e-5' },
    regression_n: { value: '0.555' }
};
const document = { getElementById: (id) => alanlar[id] || null,
                   querySelectorAll: () => [] };
function showMessage() {}
function i18nText(k, f) { return f; }
function i18nFmt(k, p, f) { return f; }
function updateMixtureDensity() { throw new Error('erisilemez olmali'); }
%s
async function kos() {
    const out = {};
    for (const y of ['mixture', 'custom', 'htpb']) {
        alanlar.fuel_type.value = y;
        alanlar.fuel_density.value = '920';
        alanlar.regression_a.value = '3.68e-5';
        try {
            await updateFuelConfig();
            out[y] = { atti: false, yogunluk: alanlar.fuel_density.value };
        } catch (e) {
            out[y] = { atti: true, hata: String(e && e.message) };
        }
    }
    process.stdout.write(JSON.stringify(out));
}
kos();
""" % g, tmp_path)
        for y in ('mixture', 'custom'):
            assert o[y]['atti'] is False, (
                '%s kolu panel yokken düştü: %s' % (y, o[y].get('hata')))
            assert o[y]['yogunluk'] == '920', (
                '%s kolu paylaşılan fuel_density alanını ezdi: %s '
                '(P17B4-01)' % (y, o[y]['yogunluk']))
        # GERİLEME KİLİDİ: desteklenen yakıt hâlâ alanları dolduruyor.
        assert o['htpb']['atti'] is False
        assert float(o['htpb']['yogunluk']) == 920.0, (
            'desteklenen yakıtta varsayılan yoğunluk doldurma bozuldu: %r'
            % o['htpb']['yogunluk'])


# ======================================================================
# P12bB4-07 — §14.1 başlığındaki kazanılmamış standart künyesi
# ======================================================================
class TestP12bB407KazanilmamisKunye:
    """ÖLÇÜLDÜ (once.json · M3): künye hem şablonda hem sözlükte vardı.

    Ürünün çizdiği yüzey SP-125'ten değil, kimyasal denge çözücüsünden
    düğüm düğüm gelir; §14 girişinin kendisi "hiçbir standarda uygunluk
    beyanı değildir" diyor.
    """

    def test_sablon_basligi_kunyesiz(self):
        m = re.search(r'data-i18n="fx\.s14_1\.h">([^<]*)<',
                      _oku(TPL / 'formulas.html'))
        assert m, 'fx.s14_1.h başlığı bulunamadı'
        assert 'SP-125' not in m.group(1), (
            'kazanılmamış standart künyesi şablona geri döndü: %s'
            % m.group(1))

    def test_sozluk_iki_dilde_kunyesiz(self):
        metinler = re.findall(r"'fx\.s14_1\.h':\s*'([^']*)'",
                              _oku(JS / 'i18n_formulas.js'))
        assert len(metinler) == 2, (
            'fx.s14_1.h iki dilde tanımlı değil: %s' % metinler)
        for t in metinler:
            assert 'SP-125' not in t, (
                'kazanılmamış künye sözlüğe geri döndü: %s' % t)

    def test_gercek_kaynak_beyani_duruyor(self):
        """Künye düştü diye KAYNAK BEYANI düşmedi (fail-closed değil, dürüst)."""
        fx = _oku(TPL / 'formulas.html')
        m = re.search(r'data-i18n="fx\.s14_1\.desc">([^<]*)<', fx)
        assert m, 'fx.s14_1.desc açıklaması bulunamadı'
        assert 'illustrative' in m.group(1), (
            'kutuların "yalnız örnekleme" beyanı kayboldu')
        assert 'formula-illustrative' in fx


# ======================================================================
# P12bS1-01 (kısmen) — ÖK-21 çift-katman kümesi gerileme kilidi
# ======================================================================
class TestP12bS101CiftKatmanGerilemesi:
    """Bu dalgada KAPANMADI (uç kapısı ölçümü app-api-uc'de).

    Ölçülen taban (once.json · M1, taban ağacı dd1dcddc):
    advanced 49 / liquid 48 / solid 63 = 160 çift-katman alan.
    Bu aşamada advanced.html'den 6 alan (ölü karışım paneli) DÜŞTÜ.
    Bekçinin işi: küme BÜYÜMESİN — yeni bir alan hem `value="X"` hem
    `|| X` ile eklenirse kırmızıya döner.
    """

    #: sonra.json · M1 (bu aşamadan SONRA ölçülen küme büyüklükleri)
    TAVAN = {'advanced.html': 43, 'liquid.html': 48, 'solid.html': 63}

    def _cift_katman(self, ad):
        t = _oku(TPL / ad)
        vals = {}
        for m in re.finditer(r'<input\b[^>]*>', t):
            e = m.group(0)
            i = re.search(r'\bid\s*=\s*"([^"]+)"', e)
            v = re.search(r'\bvalue\s*=\s*"(%s)"' % SAYI, e)
            if i and v:
                vals[i.group(1)] = v.group(1)
        kalan = set()
        for aid in vals:
            if re.search(
                    r"getElementById\(\s*['\"]%s['\"]\s*\)[^;\n]{0,160}"
                    r"\|\|\s*%s" % (re.escape(aid), SAYI), t):
                kalan.add(aid)
        return kalan

    @pytest.mark.parametrize('ad', sorted(TAVAN))
    def test_kume_buyumedi(self, ad):
        simdi = self._cift_katman(ad)
        assert len(simdi) <= self.TAVAN[ad], (
            '%s çift-katman kümesi büyüdü: %d > %d — yeni alan hem '
            'value="X" hem `|| X` ile eklenmiş (ÖK-21, P12bS1-01)'
            % (ad, len(simdi), self.TAVAN[ad]))

    def test_sokulen_karisim_alanlari_geri_gelmedi(self):
        simdi = self._cift_katman('advanced.html')
        geri = sorted(a for a in simdi if a.startswith('mixture_'))
        assert not geri, (
            'ölü karışım panelinin çift-katman alanları geri döndü: %s'
            % geri)
