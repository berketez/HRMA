# -*- coding: utf-8 -*-
"""ÖH D33-KOLAY · arayuz-panel · aşama-2 bekçileri.

Kalemler ve ölçüm dosyaları — ``docs/scofield/raw/OH/D33/arayuz-panel/a2/``
(``once.json`` / ``sonra.json`` / ``mutasyon.json``):

* **P11B5-14** (ŞART) — kırpılan istasyon notu: sayım ölçütü kördü
  (``a2/once.json`` K1: gerçek okuma satırı silindiğinde ham geçiş 3 -> 2,
  eşik hâlâ sağlanıyor). Burada notun node altında GERÇEKTEN üretildiği
  ölçülür; sayım ayağı ``tests/test_d27_arayuz_a4.py``de yorum+dize
  ayıklanmış hâle çevrildi.
* **P12aB4-17 / OH-UC-14** (ŞART + yeni) — ``bindState`` çıktısını
  "öznitelik var mı" ile ölçen her bekçi, D24'ün ``UNRECOGNIZED_STATE``
  yedeğinden sonra KÖRDÜR (K2: gerileme ikizinde truthiness 0, merdiven 2
  sözcük yakalıyor). Ölçüt merdiven ÜYELİĞİNE bağlandı.
* **OH-UC-02** (yeni) — ``solid.html`` ``#ambient_temp`` bandı kanondan
  ayrışmıştı (K3: form 200-350 K, kanon 180-340 K; formun kabul ettiği
  340-350 K aralığını uç REDDEDİYOR, kapının kabul ettiği 180-200 K'i form
  reddediyordu).
* **OH-UC-15** (yeni) — ``blowdown_panel.js`` FLAG_FIELDS / CUTOFF_FIELDS
  tablolarının BİRİNCİ sütunu (rozette basılan ad) bekçisizdi (K4:
  birinci sütunu okuyucuya bağlayan bekçi sayısı 0).
* **OH-D32-14** (yeni) — ``advanced.html`` ``#swirl_angle`` bandı ve
  ön-dolgusu ürünün kendi Giffen-Muraszew zarfının DIŞINDAYDI (K5: zarf
  3,7-71,2°, form 45-90°, ön-dolgu 90° -> 71,2°ye kırpılıyordu).
* **P12bB4-12** (ŞART) — ``formulas.html`` §13.2: ürünün koşmadığı iki
  literatür ifadesi normal ``formula-box`` olarak duruyor, ürünün gerçekten
  değerlendirdiği bağıntı sayfada hiç görünmüyordu (K6).
"""
import json
import os
import re
import shutil
import subprocess

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = os.path.join(KOK, 'hrma', 'static', 'js')
TPL = os.path.join(KOK, 'hrma', 'templates')

NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node kurulu değil')


def _oku(*parca):
    with open(os.path.join(KOK, *parca), encoding='utf-8') as f:
        return f.read()


def _html_yorumsuz(s):
    return re.sub(r'<!--.*?-->', '', s, flags=re.S)


def _input_ozniteligi(src, fid):
    m = re.search(r'<input\b[^>]*\bid="%s"[^>]*>' % re.escape(fid), src)
    assert m, '#%s alanı bulunamadı — şablon yeniden düzenlenmiş' % fid
    tag = m.group(0)

    def al(ad):
        g = re.search(r'\b%s="([^"]*)"' % ad, tag)
        return g.group(1) if g else None
    return {'value': al('value'), 'min': al('min'), 'max': al('max'),
            'step': al('step')}


def _node_kos(tmp_path, betik, *argv, ortam=None):
    yol = tmp_path / 'kos.js'
    yol.write_text(betik, encoding='utf-8')
    p = subprocess.run([NODE, str(yol)] + list(argv), capture_output=True,
                       text=True, timeout=180,
                       env=dict(os.environ, **(ortam or {})))
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout.strip().splitlines()[-1])


# ===========================================================================
# P11B5-14 — kırpılan istasyon notu GERÇEKTEN üretiliyor mu?
# ===========================================================================
COOLING_JS = os.path.join(JS, 'panels', 'cooling_panel.js')


def _notlar_blogu():
    """``cooling_panel.js`` içindeki notlar bloğunu ayıklar.

    Şekli değişirse bekçi SESSİZ kalmaz: eşleşme yoksa assert kırmızıdır.
    """
    src = _oku('hrma', 'static', 'js', 'panels', 'cooling_panel.js')
    m = re.search(r'\n        const notlar = \[\];\n(.*?)\n'
                  r'        if \(notlar\.length\) \{', src, re.S)
    assert m, ('notlar bloğu bulunamadı — cooling_panel.js yeniden '
               'düzenlenmiş, bekçi ölçümü bayatladı')
    return m.group(1)


class TestP11B514KirpilanIstasyonNotu:
    """ŞARTIN TERCİH EDİLEN AYAĞI: not node altında üretiliyor mu?"""

    @node_gerekli
    @pytest.mark.parametrize('kirpilan', [0, 3, 7])
    def test_kirpilan_sayisi_notta_gercekten_basiliyor(self, tmp_path,
                                                       kirpilan):
        """SIFIR da bir cevaptır ve söylenir (panelin kendi künyesi).

        ÖLÇÜLDÜ (``a2/once.json`` K1): eski sayım ölçütü okuma satırı
        silinse bile yeşil kalıyordu (ham geçiş 3 -> 2, eşik 2). Burada
        ölçülen şey METİN DEĞİL, üretilen notun kendisidir.
        """
        betik = (
            'const notlar_disari = [];\n'
            'const U = { fmt: function (v, d) {\n'
            '    return Number.isFinite(Number(v))'
            ' ? Number(v).toFixed(d) : "\\u2014"; } };\n'
            'const cooling = { summary: { property_table_clamped_stations: '
            + str(kirpilan) + ' } };\n'
            'const sm = cooling.summary;\n'
            '        const notlar = [];\n'
            + _notlar_blogu() + '\n'
            'process.stdout.write(JSON.stringify({notlar: notlar}));\n')
        out = _node_kos(tmp_path, betik)
        aday = [n for n in out['notlar']
                if 'property_table_clamped_stations' in n]
        assert len(aday) == 1, (
            'kırpılan istasyon notu üretilmiyor (kirpilan=%s): kullanıcı '
            'bant dışına düşüp kenara kırpılmış istasyonları ölçülmüş '
            'sanır. Üretilen notlar: %s' % (kirpilan, out['notlar']))
        assert re.search(r'=\s*%d\b' % kirpilan, aday[0]), (
            'not üretildi ama SAYI ekrana çıkmıyor: %r' % aday[0])

    @node_gerekli
    def test_alan_yayimlanmadiysa_not_uydurulmuyor(self, tmp_path):
        """Fail-closed: uç alanı yayımlamadıysa 0 UYDURULMAZ, not yoktur."""
        betik = (
            'const U = { fmt: function (v, d) {\n'
            '    return Number.isFinite(Number(v))'
            ' ? Number(v).toFixed(d) : "\\u2014"; } };\n'
            'const cooling = { summary: {} };\n'
            'const sm = cooling.summary;\n'
            '        const notlar = [];\n'
            + _notlar_blogu() + '\n'
            'process.stdout.write(JSON.stringify({notlar: notlar}));\n')
        out = _node_kos(tmp_path, betik)
        assert not [n for n in out['notlar']
                    if 'property_table_clamped_stations' in n], (
            'uç alanı yayımlamadığı hâlde not basılıyor — sayı uydurma')


# ===========================================================================
# P12aB4-17 / OH-UC-14 — hüküm sözcüğü merdiven sınıfına düşüyor mu?
# ===========================================================================
HUD_HARNESS = r"""
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
const JSDIR = process.argv[2];
const GERILEME = process.argv[3] === '1';
let src = fs.readFileSync(path.join(JSDIR, 'hud.js'), 'utf8');
if (GERILEME) {
    /* GERİLEME İKİZİ — STATE_MAP D21 öncesi ÜÇ sözcüğe geriletilir.
       Ürün dosyasına DOKUNULMAZ: kaynak yalnız bellekte değiştirilir. */
    src = src.replace(/var STATE_MAP = \{[\s\S]*?\};/,
        "var STATE_MAP = { SAFE: 'safe', MARGINAL: 'marginal', "
        + "UNSAFE: 'unsafe' };");
}
function elem() {
    const a = {};
    return { setAttribute(k, v) { a[k] = String(v); },
             removeAttribute(k) { delete a[k]; },
             getAttribute(k) { return (k in a) ? a[k] : null; } };
}
const sandbox = { console: { log() {}, warn() {}, error() {} },
                  document: { querySelectorAll() { return []; } } };
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(src, sandbox, { filename: 'hud.js' });
const esl = {};
for (const s of JSON.parse(process.env.HRMA_SOZCUKLER)) {
    const el = elem();
    sandbox.HRMAHud.bindState(el, s);
    esl[s] = el.getAttribute('data-state');
}
console.log(JSON.stringify({ eslesme: esl }));
"""


def _backend_hukum_sozcukleri():
    """``structural_analysis.py``nin ÜRETEBİLDİĞİ hüküm sözcükleri."""
    src = _oku('hrma', 'analysis', 'structural_analysis.py')
    merdiven = re.search(r'STRUCTURAL_RISK_LADDER = \((.*?)\)\n', src, re.S)
    assert merdiven, 'STRUCTURAL_RISK_LADDER bulunamadı'
    soz = set(re.findall(r"'([A-Z_]+)',\s*'[A-Z ]+'\)", merdiven.group(1)))
    soz.add(re.search(r"STRUCTURAL_RISK_TOP = \('([A-Z]+)'", src).group(1))
    soz.add(re.search(r"STRUCTURAL_VERDICT_NOT_EVALUATED = '([A-Z_]+)'",
                      src).group(1))
    return soz


def _merdiven_siniflari():
    """TEK KAYNAK: ``hud.js`` STATE_MAP'in DEĞERLERİ."""
    hud = _oku('hrma', 'static', 'js', 'hud.js')
    m = re.search(r'var STATE_MAP = \{([^}]*)\}', hud)
    assert m, 'STATE_MAP bulunamadı'
    return set(re.findall(r":\s*'([a-z-]+)'", m.group(1)))


class TestOHUC14KorBekciSinifi:
    """`bindState` çıktısı ÜYELİKLE ölçülür, varlıkla değil."""

    @node_gerekli
    def test_bes_hukum_sozcugu_de_merdiven_sinifina_dusuyor(self, tmp_path):
        soz = sorted(_backend_hukum_sozcukleri())
        merdiven = _merdiven_siniflari()
        out = _node_kos(tmp_path, HUD_HARNESS, JS, '0',
                        ortam={'HRMA_SOZCUKLER': json.dumps(soz)})
        disarida = {s: v for s, v in out['eslesme'].items()
                    if v not in merdiven}
        assert not disarida, (
            'backend bu sözcükleri üretiyor ama hud.js onları merdivenin '
            'bir sınıfına koymuyor — kart hükmün rengini almaz: %s'
            % sorted(disarida.items()))

    @node_gerekli
    def test_gerileme_ikizi_merdiven_olcutuyle_YAKALANIYOR(self, tmp_path):
        """OH-UC-14'ün ÖZÜ: ölçüt körlüğü yapısal olarak kapandı mı?

        ÖLÇÜLDÜ (``a2/once.json`` K2): STATE_MAP D21 öncesi üç sözcüğe
        geriletildiğinde ``UNRECOGNIZED_STATE`` yedeği yüzünden öznitelik
        BOŞ KALMIYOR ('unrecognized' yazılıyor); "öznitelik var mı"
        ölçütü 0, merdiven üyeliği ölçütü 2 sözcük yakalıyor.

        Bu test ikizi koşturur ve merdiven ölçütünün gerilemeyi GERÇEKTEN
        gördüğünü sınar — yani kör ölçüt geri gelirse bu düğüm anlamsız
        değil, ÖLÇÜLEBİLİR kalır.
        """
        soz = sorted(_backend_hukum_sozcukleri())
        merdiven = _merdiven_siniflari()
        out = _node_kos(tmp_path, HUD_HARNESS, JS, '1',
                        ortam={'HRMA_SOZCUKLER': json.dumps(soz)})
        truthiness = [s for s, v in out['eslesme'].items() if not v]
        uyelik = sorted(s for s, v in out['eslesme'].items()
                        if v not in merdiven)
        assert truthiness == [], (
            'gerileme ikizinde öznitelik boş kalıyor — D24 yedeği '
            'sökülmüş, ölçüm bayatladı: %s' % truthiness)
        assert len(uyelik) >= 2, (
            'merdiven ölçütü gerilemeyi göremiyor (%s) — ikiz artık '
            'gerileme üretmiyor, bekçi anlamsızlaştı' % uyelik)

    def test_tanimsiz_kovasi_merdivenle_cakismiyor(self):
        """Nötr kova bir merdiven sınıfı OLAMAZ; olsaydı ölçüt yine kördü."""
        hud = _oku('hrma', 'static', 'js', 'hud.js')
        m = re.search(r"var UNRECOGNIZED_STATE = '([a-z-]+)';", hud)
        assert m, 'UNRECOGNIZED_STATE tanımı bulunamadı'
        assert m.group(1) not in _merdiven_siniflari(), (
            'sözlük dışı kova (%r) merdiven sınıflarından birine eşitlenmiş '
            '— tanınmayan sözcüğe güvenlik sınıfı UYDURULUR' % m.group(1))

    def test_d21_bekcisi_truthiness_olcutunu_birakti(self):
        """P12aB4-17 ŞARTI: ölçüt 'öznitelik boş mu' olarak geri dönemez."""
        t = _oku('tests', 'test_d21_electron_a1.py')
        assert "if v not in merdiven]" in t, (
            'D21 bekçisi merdiven üyeliği ölçütünü kaybetti')
        assert "items() if not v]" not in t, (
            'D21 bekçisi kör truthiness ölçütüne geri döndü '
            '(UNRECOGNIZED_STATE yedeği onu boş küme üretir yapar)')


# ===========================================================================
# OH-UC-02 — solid.html #ambient_temp bandı ⟷ kanon
# ===========================================================================
class TestOHUC02OrtamSicakligiBandi:
    """Sayfanın reklam ettiği bant, ucun KABUL ETTİĞİ bant olmalı."""

    @staticmethod
    def _band():
        from hrma.constants import AMBIENT_TEMPERATURE_BAND_K
        return AMBIENT_TEMPERATURE_BAND_K

    def test_form_bandi_kanonla_ayni(self):
        """ÖLÇÜLDÜ (``a2/once.json`` K3): form 200-350, kanon 180-340.

        Sayı burada YAZILMAZ — ``hrma.constants``tan okunur (Doktrin 4).
        """
        alt, ust = self._band()
        oz = _input_ozniteligi(_oku('hrma', 'templates', 'solid.html'),
                               'ambient_temp')
        assert float(oz['min']) == float(alt), (
            '#ambient_temp alt ucu kanondan ayrı: form %s, kanon %s — '
            'kapının KABUL ETTİĞİ %s-%s K aralığını tarayıcı reddediyor'
            % (oz['min'], alt, alt, oz['min']))
        assert float(oz['max']) == float(ust), (
            '#ambient_temp üst ucu kanondan ayrı: form %s, kanon %s — '
            'kullanıcı %s-%s K yazıyor, form kabul ediyor, uç REDDEDİYOR'
            % (oz['max'], ust, ust, oz['max']))

    def test_formun_izin_verdigi_uclar_kapidan_geciyor(self):
        """Formun sunduğu en küçük ve en büyük sayı gerçekten kabul edilmeli."""
        from hrma.validation.motor_validation import motor_validator as MV
        oz = _input_ozniteligi(_oku('hrma', 'templates', 'solid.html'),
                               'ambient_temp')
        for uc in (float(oz['min']), float(oz['max'])):
            mesaj, _ = MV._bant_sorunlari({'ambient_temp': uc})
            assert not mesaj, (
                'form %s K değerine izin veriyor ama uç reddediyor: %s'
                % (uc, mesaj))

    def test_kapinin_reddettigi_deger_formda_da_ulasilamaz(self):
        """Üst ucun BİR ADIM ötesi hem kapıda hem formda reddedilmeli."""
        from hrma.validation.motor_validation import motor_validator as MV
        oz = _input_ozniteligi(_oku('hrma', 'templates', 'solid.html'),
                               'ambient_temp')
        ust = float(oz['max'])
        disari = ust + float(oz['step'] or 1)
        mesaj, _ = MV._bant_sorunlari({'ambient_temp': disari})
        assert mesaj, (
            '%s K kapıdan geçiyor — form üst ucu kapıdan DAR, sayfa '
            'kullanıcıya geçerli bir aralığı yasaklıyor' % disari)
        assert disari > ust, 'form üst ucu kapıdan gevşek'

    def test_on_dolgu_bandin_icinde(self):
        oz = _input_ozniteligi(_oku('hrma', 'templates', 'solid.html'),
                               'ambient_temp')
        v = float(oz['value'])
        assert float(oz['min']) <= v <= float(oz['max']), (
            'ön-dolgu %s kendi bandının dışında — sayfa açılır açılmaz '
            'alan geçersiz' % v)


# ===========================================================================
# OH-UC-15 — blowdown tablolarının BİRİNCİ sütunu
# ===========================================================================
BLOWDOWN_JS = os.path.join(JS, 'blowdown_panel.js')

BLOWDOWN_TABLO_HARNESS = r"""
'use strict';
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
function tablo(ad) {
    const i = src.indexOf('const ' + ad + ' = [');
    if (i < 0) return null;
    let d = 0, j = src.indexOf('[', i), k = j;
    for (; k < src.length; k++) {
        if (src[k] === '[') d++;
        else if (src[k] === ']') { d--; if (!d) break; }
    }
    return src.slice(j, k + 1);
}
const out = {};
for (const ad of ['FLAG_FIELDS', 'CUTOFF_FIELDS']) {
    const g = tablo(ad);
    if (!g) { out[ad] = null; continue; }
    const t = eval('(' + g + ')');
    /* Okuyucuya, HER alan adı için kendi adını döndüren bir vekil verilir:
       okuyucu `bd.X` okuyorsa geri gelen değer 'X' olur. Böylece birinci
       sütunun (rozette basılan ad) İKİNCİ sütunla (gerçekten okunan alan)
       aynı olup olmadığı ÖLÇÜLEBİLİR. */
    const bd = new Proxy({}, { get: (o, p) => String(p) });
    out[ad] = t.map(r => ({ basilan_ad: r[0], okunan_alan: r[1](bd) }));
}
console.log(JSON.stringify(out));
"""


class TestOHUC15BlowdownTabloBirinciSutunu:
    """Rozette basılan ad, GERÇEKTEN okunan alanın adı olmalı."""

    @pytest.fixture(scope='class')
    def tablolar(self, tmp_path_factory):
        if NODE is None:
            pytest.skip('node kurulu değil')
        return _node_kos(tmp_path_factory.mktemp('bd'),
                         BLOWDOWN_TABLO_HARNESS, BLOWDOWN_JS)

    def test_basilan_ad_okunan_alanla_ayni(self, tablolar):
        """ÖLÇÜLDÜ (``a2/once.json`` K4): bu bağı ölçen bekçi sayısı 0'dı.

        OH-D28-03 bekçileri üç şeyi ölçüyordu: alanın AÇIK erişimle
        okunduğunu, ``typeof`` kapılarının durduğunu ve rozetin
        ``b.field + ...`` biçimini. Hiçbiri birinci sütunu ikinciye
        BAĞLAMIYORDU: okuyucu komşu alana kaydırılsa rozet yanlış adı
        doğru değerle basar, kullanıcı hangi alanı okuduğunu bilemezdi.
        """
        kopuk = []
        for ad, satirlar in sorted(tablolar.items()):
            assert satirlar, '%s tablosu bulunamadı — panel yeniden yazılmış' % ad
            for s in satirlar:
                if s['basilan_ad'] != s['okunan_alan']:
                    kopuk.append('%s: rozet %r basıyor ama %r okuyor'
                                 % (ad, s['basilan_ad'], s['okunan_alan']))
        assert not kopuk, (
            'rozetin adı ile okuduğu alan ayrışmış: %s' % kopuk)

    def test_basilan_adlar_ucun_YAYIMLADIGI_alanlar(self, tablolar):
        """Uydurma alan adı basılamaz: her ad ucun sözlüğünde olmalı."""
        uc = _oku('hrma', 'engines', 'hybrid_rocket_engine.py')
        eksik = []
        for ad, satirlar in sorted(tablolar.items()):
            for s in satirlar:
                if ("'%s':" % s['basilan_ad']) not in uc:
                    eksik.append('%s: %s' % (ad, s['basilan_ad']))
        assert not eksik, (
            'panel ucun YAYIMLAMADIĞI alan adlarını rozete basıyor — '
            'kullanıcı var olmayan bir sözleşme alanı görür: %s' % eksik)

    def test_tablo_satir_sayisi_tavani_altinda_dusmedi(self, tablolar):
        """OH-D28-03'ün kapattığı yedi alan geri düşemez (mandal)."""
        toplam = sum(len(v or []) for v in tablolar.values())
        assert toplam >= 7, (
            'FLAG_FIELDS + CUTOFF_FIELDS satır sayısı 7 tabanının altına '
            'düştü (%d) — OH-D28-03 kapsamı geriledi' % toplam)


# ===========================================================================
# OH-D32-14 — #swirl_angle ⟷ Giffen-Muraszew zarfı
# ===========================================================================
class TestOHD3214SwirlAciZarfi:
    """Form, çözücünün çözemeyeceği bir hedefi SUNAMAZ."""

    @staticmethod
    def _zarf():
        from hrma.utils.injector_design import (_SWIRL_THETA_MIN_DEG,
                                                _SWIRL_THETA_MAX_DEG)
        return float(_SWIRL_THETA_MIN_DEG), float(_SWIRL_THETA_MAX_DEG)

    @staticmethod
    def _oz():
        return _input_ozniteligi(_oku('hrma', 'templates', 'advanced.html'),
                                 'swirl_angle')

    def test_form_ust_ucu_zarfin_disina_cikmiyor(self):
        """ÖLÇÜLDÜ (``a2/once.json`` K5): form 45-90°, zarf 3,7-71,2°.

        step=5 ile ulaşılabilen 10 değerin 4'ü (75, 80, 85, 90) zarf
        dışındaydı: çözücü onları SESSİZCE 71,2°ye kırpıp uyarıya
        yazıyordu. Kırpma bir çözüm değildir (Doktrin 1) — form o
        değerleri hiç sunmamalı.
        """
        alt, ust = self._zarf()
        oz = self._oz()
        assert float(oz['max']) <= ust, (
            '#swirl_angle üst ucu (%s°) Giffen-Muraszew zarfının (%s°) '
            'dışında: form çözülemeyen bir hedef sunuyor ve çözücü onu '
            'sessizce kırpıyor' % (oz['max'], ust))
        assert float(oz['min']) >= alt, (
            '#swirl_angle alt ucu (%s°) zarfın (%s°) altında' % (oz['min'], alt))

    def test_on_dolgu_zarfin_icinde(self):
        """ÖLÇÜLDÜ: ön-dolgu 90° idi ve zarfın EN UZAK dışındaydı.

        Alana hiç dokunmayan her kullanıcı kırpılmış bir hedefle
        hesaplıyordu.
        """
        alt, ust = self._zarf()
        v = self._on_dolgu_ya_da_cozucu_varsayilani()
        assert alt <= v <= ust, (
            'ön-dolgu %s° zarfın (%s-%s°) dışında: alana dokunmayan '
            'kullanıcı kırpılmış hedefle hesaplar' % (v, alt, ust))

    @classmethod
    def _on_dolgu_ya_da_cozucu_varsayilani(cls):
        """V301/E2: alan artık ÖN-DOLU DEĞİL (boş = devrenin hedefi, beyanlı;
        ``defaults_applied`` ``swirl_angle`` künyesi). Alana dokunmayan
        kullanıcının hesapladığı açı devrenin varsayılan hedefidir; iddia
        (zarfın ve bandın içinde) o sayıya uygulanır — gevşetilmedi."""
        oz = cls._oz()
        if oz.get('value') not in (None, ''):
            return float(oz['value'])
        import inspect
        from hrma.engines import injector_design as eid
        kaynak = inspect.getsource(eid.design_injector)
        m = re.search(r"theta_t = sw_in\.get\('theta_target_deg', ([0-9.]+)\)",
                      kaynak)
        assert m, 'devrenin varsayılan hedef açısı bulunamadı'
        return float(m.group(1))

    def test_on_dolgu_kendi_bandinin_icinde(self):
        oz = self._oz()
        v = self._on_dolgu_ya_da_cozucu_varsayilani()
        assert float(oz['min']) <= v <= float(oz['max']), (
            'ön-dolgu kendi min/max bandının dışında — sayfa açılır açılmaz '
            'alan geçersiz')

    def test_ipucu_zarfin_SAYILARINI_dogru_soyluyor(self):
        """İpucu bandı reklam ediyorsa sayılar kanondan gelmeli (Doktrin 4).

        ``test_d15_sablonlar_a3::test_b1_10_ipucu_bandi_uc_bandiyla_ayni``
        emsali: sayfanın reklam ettiği uç, çözücünün kabul ettiği uç olmalı.
        """
        alt, ust = self._zarf()
        for kaynak in (_oku('hrma', 'templates', 'advanced.html'),
                       _oku('hrma', 'static', 'js', 'i18n_advanced.js')):
            m = re.search(r'solvable envelope is ([0-9.]+)-([0-9.]+) degrees',
                          kaynak) or re.search(
                r'çözülebilir zarf ([0-9.]+)-([0-9.]+) derecedir', kaynak)
            assert m, 'ipucu zarfı adıyla söylemiyor'
            assert (float(m.group(1)), float(m.group(2))) == (alt, ust), (
                'ipucu bayat bir zarf reklam ediyor: %s-%s, çözücü %s-%s'
                % (m.group(1), m.group(2), alt, ust))

    def test_etiket_urunun_OKUDUGU_buyuklugu_soyluyor(self):
        """Etiket "teğetsel giriş açısı" diyordu; kablo hedef sprey YARI açısı.

        ÖLÇÜLDÜ: ``app.py`` alanı ``target_half_angle`` olarak geçiriyor
        (``set_swirl_params(..., target_half_angle=...)``), yani okunan
        büyüklük sprey konisinin yarı açısıdır. 90° "tam teğetsel giriş"
        olarak anlamlıdır ama bir sprey YARI açısı olarak çözülemez —
        ön-dolgunun 90 olmasının kökü bu ad karışıklığıydı.
        """
        adv = _html_yorumsuz(_oku('hrma', 'templates', 'advanced.html'))
        m = re.search(r'data-i18n="adv\.inj\.tangentialEntryAngleDegrees">'
                      r'([^<]*)<', adv)
        assert m, 'swirl açısı etiketi bulunamadı'
        etiket = m.group(1).lower()
        assert 'half-angle' in etiket or 'yarı açı' in etiket, (
            'etiket ürünün okuduğu büyüklüğü söylemiyor: %r — alan '
            'target_half_angle olarak geçiriliyor' % m.group(1))
        # Kablo gerçekten hedef yarı açı mı? (beyan bayatlayamaz)
        app = _oku('hrma', 'app.py')
        # ÖH D33-2 / app-api-uc a1 (OH-D33-07): uç, alanı artık bir ARA
        # DEĞİŞKENE okuyor (``_swirl_theta``) çünkü aynı değer önce zarf
        # kapısından geçiyor; tek satırlık eski desen bu yüzden eşleşmiyor.
        # İDDİA DEĞİŞMEDİ: ``swirl_angle`` hâlâ hedef YARI AÇI olarak
        # geçiriliyor — iki halka da ölçülüyor, kablo kopamaz.
        assert re.search(r"_swirl_theta = _uc_yedegi\('swirl_angle'\)", app), (
            'swirl_angle artık uçta okunmuyor — etiket ve bant ölçümü '
            'bayatladı')
        assert re.search(r'target_half_angle=_swirl_theta', app), (
            'swirl_angle artık target_half_angle olarak geçirilmiyor — '
            'etiket ve bant ölçümü bayatladı')


# ===========================================================================
# P12bB4-12 — §13.2: ürünün koşmadığı formül KUTU olarak sunulmuyor
# ===========================================================================
def _bolum_13_2():
    f = _html_yorumsuz(_oku('hrma', 'templates', 'formulas.html'))
    i = f.index('fx.s13_2.h')
    j = f.index('fx.s13_3.h')
    return f[i:j]


class TestP12bB412IkiFazKutusu:
    """ŞART: ya kutu ürünün modelini gösterir, ya φ/ξ ayrışık bloğa taşınır."""

    def test_urun_modelinin_KENDISI_kutuda(self):
        """ÖLÇÜLDÜ (``a2/once.json`` K6): ``urun_modeli_kutuda`` = false.

        Bölümdeki iki kutunun ikisi de literatürdü; ürünün gerçekten
        değerlendirdiği bağıntı sayfada HİÇ yoktu, yalnız beyan
        metninin içinde düz yazı olarak geçiyordu.
        """
        b = _bolum_13_2()
        kutular = re.findall(r'<div class="formula-box">\s*(\$[^<]*)', b)
        assert kutular, '§13.2 vurgulu kutusunu kaybetti'
        urun = [k for k in kutular
                if 'K \\cdot \\beta \\cdot g(x)' in k and 'g(x)' in k]
        assert urun, (
            'ürünün koştuğu bağıntı (100·K·β·g(x)) vurgulu bir kutuda '
            'değil — kullanıcı elle denetleyebileceği tek ifadeyi göremiyor. '
            'Bulunan kutular: %s' % kutular)

    def test_literatur_kutulari_vurgusuz(self):
        """φ ve ξ taşıyan kutular ``formula-illustrative`` olmalı."""
        b = _bolum_13_2()
        for divi in re.findall(r'<div class="([^"]*)"[^>]*>\s*(\$[^<]*)', b):
            sinif, mat = divi
            if '\\phi' in mat or '\\xi' in mat:
                assert 'formula-illustrative' in sinif, (
                    'ürünün KOŞMADIĞI ifade hesaplanan bağıntılarla aynı '
                    'ağırlıkta kutu olarak duruyor: %r (%s)' % (mat[:60], sinif))

    def test_beyan_literatur_kutularindan_ONCE(self):
        """P12bB4-07 (§14.1) emsali: iddia beyandan sonra gelmez."""
        b = _bolum_13_2()
        beyan = b.find('fx.s13_2.literature_note')
        kutu = b.find('formula-illustrative')
        assert beyan >= 0, '§13.2 literatür beyanı yok'
        assert kutu >= 0, '§13.2 vurgusuz kutusu yok'
        assert beyan < kutu, (
            'literatür beyanı kutulardan SONRA geliyor — gözle okuma sırası '
            'iddiayı önce, çürütmesini sonra veriyor')

    def test_vurgusuzluk_kurali_formula_box_TAN_SONRA(self):
        """Kaynak sırası, ayrışmanın tek koşuludur.

        ÖLÇÜLDÜ: ``.formula-illustrative`` ``.formula-box``tan ÖNCE
        tanımlıydı; ``.formula-box``un ``border`` KISA YAZIMI eşit
        özgüllükte sonra geldiği için kesikli sol çizgiyi siliyordu.
        """
        f = _oku('hrma', 'templates', 'formulas.html')
        i = f.index('.formula-box {')
        j = f.index('.formula-illustrative {')
        assert j > i, (
            '.formula-illustrative yeniden .formula-box ÖNÜNE alınmış — '
            '`border` kısa yazımı kesikli sol çizgiyi siler, vurgusuzluk '
            'yalnız opaklığa iner')

    def test_beyan_iki_dilde_tanimli(self):
        sozluk = _oku('hrma', 'static', 'js', 'i18n_formulas.js')
        assert sozluk.count("'fx.s13_2.literature_note':") == 2, (
            'yeni beyan anahtarı EN+TR olarak tam iki kez bulunmalı')

    def test_urun_hala_phi_xi_KOSMUYOR(self):
        """Beyan bayatlayamaz: ürün φ/ξ'ye geçerse düzen yalana döner."""
        kaynak = _oku('hrma', 'analysis', 'two_phase_loss.py')
        for ad in ('phi', 'xi'):
            n = len(re.findall(r'(?<![A-Za-z0-9_])' + ad + r'(?![A-Za-z0-9_])',
                               kaynak))
            assert n == 0, (
                'ürün artık %r kullanıyor (%d kez) — §13.2 düzenini ve '
                'beyanını güncelle' % (ad, n))

    def test_kutudaki_model_URUNUN_bagintisiyla_ayni(self):
        """Kutu, ``two_phase_loss.py``nin gerçekten yazdığı bağıntı olmalı."""
        kaynak = _oku('hrma', 'analysis', 'two_phase_loss.py')
        assert 'loss_pct = 100.0 * k_central * beta * size_factor' in kaynak, (
            'ürünün kayıp bağıntısı değişti — §13.2 kutusu bayatladı')
        assert 'size_factor = 2.0 * stokes_ratio / (1.0 + stokes_ratio)' \
            in kaynak, 'g(x) = 2x/(1+x) şekli değişti — kutuyu güncelle'
