# -*- coding: utf-8 -*-
"""ÖH D25 · arayuz aşama-2 bekçileri.

Her sınıf BİR kalemin onarımını kilitler. Bekçiler ters-mutasyonla
sınandı (docs/scofield/raw/OH/D25/arayuz/a2/mutasyon.json): onarım
geçici olarak geri alındığında ilgili test KIRMIZI olur.

Ölçüm betiği ve önce/sonra sayıları:
    docs/scofield/raw/OH/D25/arayuz/a2/{olcum.py,once.json,sonra.json}
"""
import json
import pathlib
import re
import subprocess

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
PANELS = JS / 'panels'
SABLON = KOK / 'hrma' / 'templates'


def _oku(p):
    return p.read_text(encoding='utf-8')


def _node():
    import shutil
    return shutil.which('node')


needs_node = pytest.mark.skipif(_node() is None, reason='node yok')


# ===========================================================================
# OH-D20-10 — panel.cfd TR sözlüğünde 'ARTIK' teknik adı
# ===========================================================================
class TestOhD2010CfdTerimi:
    """EN 'IMBALANCE' ⟷ TR 'ARTIK' değildir.

    ÖLÇÜLDÜ (once.json): panel.cfd.badgeMass/badgeEnergy/badgeViscousEnergy
    TR karşılıkları 'KÜTLE ARTIĞI' / 'ENERJİ ARTIĞI' idi; EN karşılıkları
    MASS/ENERGY IMBALANCE. Aynı sözlükte badgeEnergyEulerForm 'KALINTI'
    (residual) diyor — yani İKİ AYRI büyüklük (dengesizlik ve artık) TR'de
    tek sözcüğe düşüyordu.
    """

    ANAHTARLAR = ('panel.cfd.badgeMass', 'panel.cfd.badgeEnergy',
                  'panel.cfd.badgeViscousEnergy')

    def test_tr_dengesizlik_diyor_artik_demiyor(self):
        src = _oku(JS / 'i18n_common.js')
        for anahtar in self.ANAHTARLAR:
            tr = re.findall(r"'%s':\s*'([^']*)'" % re.escape(anahtar), src)
            assert len(tr) == 2, (anahtar, len(tr))   # EN + TR
            trmetin = tr[1]
            assert 'ARTIĞI' not in trmetin, (anahtar, trmetin)
            assert 'DENGESİZLİĞİ' in trmetin, (anahtar, trmetin)

    def test_en_imbalance_bozulmadi(self):
        src = _oku(JS / 'i18n_common.js')
        for anahtar in self.ANAHTARLAR:
            en = re.findall(r"'%s':\s*'([^']*)'" % re.escape(anahtar), src)[0]
            assert 'IMBALANCE' in en, (anahtar, en)


# ===========================================================================
# P4B3-21 (Fable-D19 ŞARTI) + OH-D24-15 — ikinci apoje rozeti
# ===========================================================================
class TestP4B321OhD2415ApojeRozeti:
    """AYNI kusurun iki kimliği; tek onarım.

    ÖLÇÜLDÜ (once.json): sixdof_panel.js ikinci apoje rozeti
    ``badge('SITE ' + … + ' m ASL → APOGEE ' + … + ' km MSL')`` biçiminde
    İngilizce SABİT dizeydi (duz_dize_badge_SITE = 1, i18n anahtarı = 0);
    kardeş rozet (badgeApogee) zaten TF()'ten geçiyordu.
    """

    def test_duz_dize_kalmadi(self):
        assert "badge('SITE '" not in _oku(JS / 'sixdof_panel.js')

    def test_tf_anahtariyla_veriliyor(self):
        src = _oku(JS / 'sixdof_panel.js')
        assert "TF('sixdof.badgeApogeeMsl'" in src

    def test_anahtar_en_ve_tr_sozlukte(self):
        src = _oku(JS / 'i18n_common.js')
        deger = re.findall(r"'sixdof\.badgeApogeeMsl':\s*'([^']*)'", src)
        assert len(deger) == 2, len(deger)
        assert '{m}' in deger[0] and '{km}' in deger[0]
        assert '{m}' in deger[1] and '{km}' in deger[1]
        # TR gerçekten Türkçe olmalı (İngilizce kopya i18n borcudur).
        assert deger[1] != deger[0]
        assert 'TEPE NOKTASI' in deger[1]


# ===========================================================================
# OH-D24-05 — PA_PER_BAR tek kaynak
# ===========================================================================
class TestOhD2405BirimTekKaynak:
    """ÖLÇÜLDÜ (once.json): PA_PER_BAR = 1e5 DÖRT JS dosyasında ayrı ayrı
    tanımlıydı (fea_panel, motor_viz_deck, panels/cfd_panel,
    transient_panel) ve paylaşılan bir JS sabit modülü yoktu.
    """

    TUKETICILER = ('fea_panel.js', 'motor_viz_deck.js', 'transient_panel.js',
                   'panels/cfd_panel.js')

    def test_ortak_modul_var_ve_tanim_tek(self):
        modul = JS / 'units_constants.js'
        assert modul.exists()
        src = _oku(modul)
        # Künye metnindeki alıntı sayı TANIMI değildir: kod satırı sayılır.
        kod = re.findall(r'^\s*(?:const|var|let)\s+PA_PER_BAR\s*=\s*1e5\s*;',
                         src, re.M)
        assert len(kod) == 1, kod

    def test_tuketicilerde_yerel_tanim_yok(self):
        for rel in self.TUKETICILER:
            src = _oku(JS / rel)
            assert not re.search(r'(?:const|var|let)\s+PA_PER_BAR\s*=\s*1e5',
                                 src), rel
            assert 'units_constants' in src, rel

    def test_depoda_tek_tanim(self):
        tanimli = []
        for yol in JS.rglob('*.js'):
            if re.search(r'(?:const|var|let)\s+PA_PER_BAR\s*=\s*1e5',
                         _oku(yol)):
                tanimli.append(yol.name)
        assert tanimli == ['units_constants.js'], tanimli

    @pytest.mark.parametrize('sablon', ('advanced.html', 'liquid.html',
                                        'solid.html'))
    def test_sablon_ortak_modulu_once_yukluyor(self, sablon):
        src = _oku(SABLON / sablon)
        i = src.find('/static/js/units_constants.js')
        assert i != -1, sablon
        for tuketici in ('/static/js/fea_panel.js',
                         '/static/js/transient_panel.js',
                         '/static/js/motor_viz_deck.js',
                         '/static/js/panels/cfd_panel.js'):
            j = src.find(tuketici)
            if j != -1:
                assert i < j, (sablon, tuketici)

    @needs_node
    def test_modul_node_altinda_sayiyi_veriyor(self, tmp_path):
        betik = tmp_path / 'k.js'
        betik.write_text(
            "const m = require(%s);\n"
            "process.stdout.write(JSON.stringify("
            "[m.UNITS.PA_PER_BAR, m.requirePaPerBar()]));\n"
            % json.dumps(str(JS / 'units_constants.js')), encoding='utf-8')
        p = subprocess.run([_node(), str(betik)], capture_output=True,
                           text=True, timeout=60)
        assert p.returncode == 0, p.stderr[-1500:]
        assert json.loads(p.stdout) == [1e5, 1e5]

    @needs_node
    def test_modul_yoksa_yedek_sayi_uydurulmuyor(self, tmp_path):
        """FAIL-CLOSED: eksik modül sessiz bir varsayılana DÜŞMEZ."""
        betik = tmp_path / 'k2.js'
        betik.write_text(
            "const m = require(%s);\n"
            "m.UNITS.PA_PER_BAR = null;\n"
            "let hata = null;\n"
            "try { m.requirePaPerBar(); } catch (e) { hata = e.message; }\n"
            "process.stdout.write(JSON.stringify(hata));\n"
            % json.dumps(str(JS / 'units_constants.js')), encoding='utf-8')
        p = subprocess.run([_node(), str(betik)], capture_output=True,
                           text=True, timeout=60)
        assert p.returncode == 0, p.stderr[-1500:]
        mesaj = json.loads(p.stdout)
        assert mesaj and 'PA_PER_BAR' in mesaj, mesaj


# ===========================================================================
# OH-D24-08 — flow_panel ölü dalı + sunucu gerekçesi
# ===========================================================================
class TestOhD2408AyrilmaDali:
    """ÖLÇÜLDÜ (once.json): D19 (P15B4-09) sonrası çözücü Summerfield
    ölçütünü ŞOK dalından ÖNCE değerlendiriyor ve ölçüt sağlanan her vaka
    REGIME_SEPARATED'a düşüyor; ``_solve_separation`` her zaman bir sözlük
    döndürdüğü için ``regime['separation']`` DOLU geliyor. Panelin
    ``else if (separation_expected && separation_criterion_met)`` dalı bu
    yüzden ULAŞILAMAZDI — ve ucun kendi gerekçe cümlesi
    (``separation_expected_because``) YALNIZ o ölü dalda basıldığı için
    ekrana HİÇ çıkmıyordu.
    """

    def test_olu_dal_kaldirildi(self):
        src = _oku(PANELS / 'flow_panel.js')
        assert not re.search(
            r'else if \(regime\.separation_expected\s*\n?\s*'
            r'&& regime\.separation_criterion_met\)', src)

    def test_sunucu_gerekcesi_canli_dalda(self):
        """Gerekçe artık ULAŞILABİLİR dalda basılıyor (eskiden ölü daldaydı).

        Zincir: alan -> değişken -> canlı dalın gövdesi. Üçünden biri
        koparsa ucun cümlesi yine ekrana çıkmaz.
        """
        src = _oku(PANELS / 'flow_panel.js')
        assert ('const sepNeden = regime.separation_expected_because;' in src)
        i = src.find('if (regime.separation) {')
        j = src.find('} else if (regime.separation_criterion_met', i)
        assert i != -1 and j > i, (i, j)
        canli = src[i:j]
        assert 'sepNeden' in canli
        assert 'sepEsc(sepNeden)' in canli

    def test_sozlesme_kapisi_fail_closed(self):
        """Değişmez bozulursa panel SESSİZ kalmaz, istasyon UYDURMAZ."""
        src = _oku(PANELS / 'flow_panel.js')
        assert 'panel.nzl.separationContract' in src
        i18n = _oku(JS / 'i18n_common.js')
        assert i18n.count("'panel.nzl.separationContract':") == 2

    def test_sunucu_degismezi_hala_geciyor(self):
        """Dalın ölü olmasının SEBEBİ ürünün kendi kodunda durmalı."""
        py = _oku(KOK / 'hrma' / 'analysis' / 'nozzle_flow_1d.py')
        assert re.search(r'elif\s+separation_criterion_met\s*:', py)
        assert re.search(
            r"if\s+regime\['type'\]\s*==\s*self\.REGIME_SEPARATED\s*:\s*\n\s*"
            r"separation\s*=\s*self\._solve_separation", py)


# ===========================================================================
# P11B2-13 — "hangi girdi varsayılana düştü" beyanı
# ===========================================================================
class TestP11B213VarsayilanBeyani:
    """ÖLÇÜLDÜ (once.json): çözücü listeyi ÜÇ yerde yayımlıyor
    (motor.defaults_used, motor.fallbacks_used, design_summary.*) ama
    app.js dosyasında ``defaults_used`` dizesi HİÇ geçmiyordu (0).
    """

    def test_app_js_beyani_okuyor(self):
        src = _oku(JS / 'app.js')
        assert 'defaults_used' in src
        assert 'fallbacks_used' in src
        assert 'defaultsDeclarationBlock' in src

    def test_iki_cikis_yolunda_da_basiliyor(self):
        """HUD'lu ve HUD'suz yol — biri düşerse beyan kaybolur."""
        src = _oku(JS / 'app.js')
        assert src.count('defaultsDeclarationBlock(motorData, results)') == 3

    def test_liste_bossa_serit_basilmiyor(self):
        """Boş şerit de bir iddiadır: 'varsayılan yok' demek olurdu."""
        src = _oku(JS / 'app.js')
        i = src.find('function defaultsDeclarationBlock')
        j = src.find('\n}\n', i)
        govde = src[i:j]
        assert ("if (varsayilan.length === 0 && yedek.length === 0) return '';"
                in govde)

    def test_anahtarlar_en_ve_tr_sozlukte(self):
        i18n = _oku(JS / 'i18n_common.js')
        for anahtar in ('app.defaults.title', 'app.fallbacks.title'):
            assert i18n.count("'%s':" % anahtar) == 2, anahtar


# ===========================================================================
# P11B2-14 — PDF yedeği metin raporun uyarı kanalları
# ===========================================================================
class TestP11B214MetinRaporuKanallari:
    """ÖLÇÜLDÜ (once.json): rapor gövdesi YALNIZ ``inj.warnings``
    taşıyordu (taşınan kanal 1, ekranda 5). Yani PDF alınamadığında
    kullanıcının eline geçen tek belge KRİTİK hükümleri düşürülmüş
    oluyordu.
    """

    def _govde(self):
        src = _oku(JS / 'app.js')
        m = re.search(r'let report = T\(.app\.txt\.title.*?'
                      r'downloadBlobAs\(new Blob\(\[report\]', src, re.S)
        assert m, 'metin rapor gövdesi bulunamadı'
        return m.group(0)

    def test_cozucu_kanallari_rapora_giriyor(self):
        """Yorumda ADI geçmesi yetmez: ÇAĞRI gövdede olmalı.

        (Ters mutasyon dersi: ilk hâl ``'collectResultWarnings' in govde``
        diyordu ve çağrı sökülünce bile ÜSTTEKİ YORUM sayesinde yeşil
        kalıyordu — bekçi kusuru göremiyordu.)
        """
        govde = self._govde()
        kodsuz = re.sub(r'//[^\n]*', '', govde)
        assert re.search(r'collectResultWarnings\s*\(\s*currentResults\s*\)',
                         kodsuz), 'toplayıcı ÇAĞRISI rapor gövdesinde yok'
        # Toplayıcının taşıdığı kanallar ürünün kendi kodunda durmalı.
        app = _oku(JS / 'app.js')
        i = app.find('function collectResultWarnings')
        j = app.find('\n}\n', i)
        toplayici = app[i:j]
        for kanal in ('motor.warnings', 'input_warnings',
                      'injector', 'design_gate_checks'):
            assert kanal in toplayici, kanal

    def test_kritik_uyarilar_ayri_baslikta(self):
        govde = self._govde()
        assert 'critical_warnings' in govde
        assert 'app.txt.criticalWarnings' in govde

    def test_olagan_dogrulama_uyarilari_da_var(self):
        assert 'regular_warnings' in self._govde()

    def test_hic_uyari_yoksa_sessiz_kalmiyor(self):
        assert 'app.txt.noWarnings' in self._govde()

    def test_toplayici_cokerse_eksiklik_yaziliyor(self):
        assert 'app.txt.warnCollectFailed' in self._govde()

    def test_anahtarlar_en_ve_tr_sozlukte(self):
        i18n = _oku(JS / 'i18n_common.js')
        for anahtar in ('app.txt.criticalWarnings', 'app.txt.noWarnings',
                        'app.txt.warnCollectFailed'):
            assert i18n.count("'%s':" % anahtar) == 2, anahtar


# ===========================================================================
# P11B2-10 — E3 değer kaynağı sınıflandırıcısının ürün tüketicisi
# ===========================================================================
SINIF_CAGRI_RE = re.compile(r'source\s*\.\s*(?:of|cell|kindOfText)\s*\(')


class TestP11B210SiniflandiriciBagli:
    """ÖLÇÜLDÜ (once.json): 16 panelin 13'ü ucun beyan alanlarını
    (``*_basis`` / ``*_source`` / ``*_status``) OKUYOR — toplam 81 ayrı
    alan adı — ama sınıflandırıcıyı (``U.source.of/cell/kindOfText``)
    çağıran panel sayısı 0'dı: katman ölüydü, damgalar elle konuyordu.
    """

    def _bagli_paneller(self):
        out = []
        for yol in sorted(PANELS.glob('*.js')):
            if SINIF_CAGRI_RE.search(_oku(yol)):
                out.append(yol.name)
        return out

    def test_en_az_bir_urun_tuketicisi_var(self):
        """Kalemin çekirdek iddiası: katman ÖLÜ olmamalı."""
        assert self._bagli_paneller(), (
            'hiçbir panel değer kaynağı sınıflandırıcısını çağırmıyor — '
            'E3 katmanı yine ölü')

    def test_thermal_paneli_ucun_beyanindan_siniflandiriyor(self):
        src = _oku(PANELS / 'thermal_panel.js')
        assert 'U.source.of(' in src
        # Damga ELLE konmuyor: hüküm ucun kendi metninden çıkıyor.
        i = src.find('const hsInfo')
        j = src.find('const hsChip', i)
        assert i != -1 and j > i
        govde = src[i:j]
        assert 'heat_sink_delta_T_basis' not in govde  # değişkenden geçer
        assert 'basis: hsBasis' in govde and 'source: hsSource' in govde

    def test_flow_paneli_rejim_beyanini_siniflandiriyor(self):
        src = _oku(PANELS / 'flow_panel.js')
        assert 'U.source.of(' in src
        assert 'separation_expected_because' in src

    def test_beyansiz_alana_cip_basilmiyor(self):
        """Beyan yoksa 'hesaplandı' iddiası üretilmez (fail-closed)."""
        src = _oku(PANELS / 'flow_panel.js')
        assert 'if (sepInfo.declared) sepChip = U.source.chip(sepInfo);' in src

    @needs_node
    def test_siniflandirici_ucun_metnini_dogru_okuyor(self, tmp_path):
        """Pano fonksiyonu node'da koşturulur: gerçek beyan cümleleri."""
        dock = JS / 'analysis_dock.js'
        betik = tmp_path / 'sinif.js'
        betik.write_text(
            "const fs = require('fs'); const vm = require('vm');\n"
            "const el = () => ({ style:{}, dataset:{}, setAttribute(){},"
            " getAttribute(){return null;}, appendChild(){},"
            " querySelector(){return null;}, querySelectorAll(){return [];},"
            " addEventListener(){}, innerHTML:'', textContent:'' });\n"
            "const sandbox = { console, JSON, Math, Number, String, Boolean,"
            " Array, Object, RegExp, Error, isFinite, parseFloat, parseInt,"
            " setTimeout, clearTimeout, document: { body: el(),"
            " createElement: el, getElementById(){return null;},"
            " querySelector(){return null;}, querySelectorAll(){return [];},"
            " addEventListener(){} } };\n"
            "sandbox.window = sandbox; sandbox.globalThis = sandbox;\n"
            "vm.createContext(sandbox);\n"
            "vm.runInContext(fs.readFileSync(%s,'utf8'), sandbox,"
            " { filename: 'analysis_dock.js' });\n"
            "const S = sandbox.window.AnalysisDock.ui.source;\n"
            "const out = {\n"
            "  bos: S.kindOfText(''),\n"
            "  kullanici: S.kindOfText('user input (tank_temperature)'),\n"
            "  varsayim: S.kindOfText("
            "'thermal_protection module default 293,15 K'),\n"
            "  modellenmedi: S.kindOfText('not modelled'),\n"
            "  beyansiz: S.of({}, 'x', { value: 3 }).declared,\n"
            "  beyanli: S.of({ x: 3, x_source: 'user_override' }, 'x').kind,\n"
            "  sayisiz: S.of({ x: null }, 'x').kind\n"
            "};\n"
            "process.stdout.write(JSON.stringify(out));\n"
            % json.dumps(str(dock)), encoding='utf-8')
        p = subprocess.run([_node(), str(betik)], capture_output=True,
                           text=True, timeout=120)
        assert p.returncode == 0, p.stderr[-2000:]
        out = json.loads(p.stdout)
        assert out['bos'] is None
        assert out['kullanici'] == 'user'
        assert out['varsayim'] == 'assumed'
        assert out['modellenmedi'] == 'missing'
        assert out['beyansiz'] is False
        assert out['beyanli'] == 'user'
        assert out['sayisiz'] == 'missing'
