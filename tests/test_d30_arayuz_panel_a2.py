# -*- coding: utf-8 -*-
"""OH D30 · arayuz-panel · asama 2/3 — bekci.

Her sinif bir onarim kalemini ters-mutasyonla kanitlanmis bicimde tutar.
Olculer ILISKI olcusudur (sayi mandali degil): "su ad su bolgede gecmeli",
"su dal su cagriyi yapmali", "su saf islev su girdide su rengi DONDURMEZ".
Saf JS islevleri Node ile GERCEKTEN kosturulur (test_marginKind), boylece
bekci metnin degil DAVRANISIN bekcisidir.
"""
import json
import os
import re
import subprocess

import pytest
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = os.path.join(KOK, 'hrma', 'static', 'js')
KANIT = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'D30',
                     'arayuz-panel')


def oku(*parca):
    with open(os.path.join(KOK, *parca), encoding='utf-8') as f:
        return f.read()


def capa_govdeleri():
    """a1 capasindaki GERCEK uc yanitlari (uc motor /calculate)."""
    yol = os.path.join(KANIT, 'a1', 'capa_sonra.json')
    if not os.path.exists(kanit_gerekli(yol)):
        pytest.skip('a1 capa ciktisi yok')
    with open(kanit_gerekli(yol), encoding='utf-8') as f:
        return json.load(f)['A_gecerli_govde']


def derin_ara(d, ad, derinlik=0):
    """<ad> anahtarini herhangi bir derinlikte ara; deger listesi don."""
    out = []
    if derinlik > 7:
        return out
    if isinstance(d, dict):
        for k, v in d.items():
            if k == ad:
                out.append(v)
            out += derin_ara(v, ad, derinlik + 1)
    elif isinstance(d, list) and d:
        out += derin_ara(d[0], ad, derinlik + 1)
    return out


def node_kos(kaynak):
    """Saf JS parcasini Node ile kosturup JSON sonucu don."""
    node = subprocess.run(['node'], input=kaynak, capture_output=True,
                          text=True, timeout=60)
    assert node.returncode == 0, node.stderr
    return json.loads(node.stdout.strip())


def islev_govdesi(metin, ad):
    """Suslu parantez derinligiyle <ad> islevinin govdesini cikar."""
    m = re.search(r'function\s+' + re.escape(ad) + r'\s*\([^)]*\)\s*\{', metin)
    assert m, 'islev bulunamadi: ' + ad
    i = m.end() - 1
    derinlik = 0
    for j in range(i, len(metin)):
        if metin[j] == '{':
            derinlik += 1
        elif metin[j] == '}':
            derinlik -= 1
            if derinlik == 0:
                return metin[m.start():j + 1]
    raise AssertionError('govde kapanmadi: ' + ad)


class TestP11B2_18KacissizSunucuMetni:
    """app.js `l_star_note` kacissiz innerHTML'e giriyordu."""

    def test_ham_enterpolasyon_kalmadi(self):
        s = oku('hrma', 'static', 'js', 'app.js')
        assert '${motorData.l_star_note}' not in s, (
            'sunucu metni kacissiz sablona gomulmus')

    def test_kacis_gercekten_uygulaniyor(self):
        s = oku('hrma', 'static', 'js', 'app.js')
        govde = islev_govdesi(s, 'lStarRow')
        assert 'escNote(motorData.l_star_note)' in govde
        # kacis islevi ucunu de kapsar (kardes yayicilarin deseni)
        assert re.search(r"escNote\s*=.*?&amp;.*?&lt;.*?&gt;", govde, re.S)

    def test_davranis_node_ile(self):
        """Kacis islevi GERCEKTEN kosturulur: `<b>` biciimlenmemeli."""
        s = oku('hrma', 'static', 'js', 'app.js')
        govde = islev_govdesi(s, 'lStarRow')
        # NOT: `[^;]+` ile kesilemez — kacis dizgilerinin KENDISI ';'
        # tasir (`&amp;`). Bildirim son `.replace` cagrisiyla biter.
        m = re.search(r"const escNote = .*?\.replace\(/>/g, '&gt;'\);",
                      govde, re.S)
        assert m
        cikti = node_kos(
            m.group(0)
            + "console.log(JSON.stringify(escNote('<b>&x</b>')));")
        assert '<b>' not in cikti and '&lt;b&gt;' in cikti


class TestOHD1927NegatifOnbellekLRU:
    """Dusen karo girdisi LRU'da tazelenmiyordu; ilk budanan o oluyordu."""

    def test_failed_dalinda_touch_var(self):
        s = oku('hrma', 'static', 'js', 'launch_site_globe.js')
        govde = islev_govdesi(s, '') if False else s
        # retryAt kapisinin ELSE dali (geri cekilme penceresi ICINDE)
        m = re.search(r'if \(performance\.now\(\) >= entry\.retryAt\) \{'
                      r'(.*?)\} else \{(.*?)\n\s*\}', govde, re.S)
        assert m, 'negatif onbellek dali bulunamadi'
        assert 'this._touchTile(key);' in m.group(2), (
            'geri cekilme penceresindeki girdi LRU\'da tazelenmiyor')

    def test_yeniden_istek_hala_kapali(self):
        """Tazeleme dali yeni yukleme BASLATMAMALI (kapi yukaridaki dalda)."""
        s = oku('hrma', 'static', 'js', 'launch_site_globe.js')
        m = re.search(r'if \(performance\.now\(\) >= entry\.retryAt\) \{'
                      r'(.*?)\} else \{(.*?)\n\s*\}', s, re.S)
        assert '_buildTilePatch' not in m.group(2)


class TestP11B3_26OluMerkezHesabi:
    """Tane gorunumu eleman merkezlerini uretip hic tuketmiyordu."""

    def test_tane_gorunumu_merkez_uretmiyor(self):
        s = oku('hrma', 'static', 'js', 'fea_panel.js')
        grain = islev_govdesi(s, 'buildGrainViewModel')
        assert 'elementCentres(' not in grain, (
            'tane gorunumu hala olu merkez hesabi yapiyor')

    def test_yapisal_gorunum_merkezi_koruyor(self):
        """Sokum YAPISAL gorunume sicramamali (orada tuketicisi var)."""
        s = oku('hrma', 'static', 'js', 'fea_panel.js')
        yapisal = islev_govdesi(s, 'buildViewModel')
        assert 'centres: elementCentres(mesh)' in yapisal
        for tuketici in ('badElementsTrace', 'qualityFigure'):
            assert 'vm.centres' in islev_govdesi(s, tuketici)


class TestP11B4_15KazanilmamisYesil:
    """Otomatik boyutlandirmada burst margin karti YESIL basiliyordu."""

    def _marginKind(self):
        s = oku('hrma', 'static', 'js', 'panels', 'vessel_panel.js')
        return islev_govdesi(s, 'marginKind')

    def test_auto_sized_yesil_vermez(self):
        """Node ile GERCEK kosum: 1.20 auto-sized -> 'ok' DEGIL."""
        sonuc = node_kos(
            self._marginKind()
            + "console.log(JSON.stringify({"
              "auto120: marginKind(1.20, true),"
              "el120: marginKind(1.20, false),"
              "auto119: marginKind(1.19, true),"
              "auto099: marginKind(0.99, true),"
              "yok: marginKind(null, true)}));")
        assert sonuc['auto120'] != 'ok', (
            'boyutlandiricinin hedefinin geri okumasi yesil basiliyor')
        # Elle verilen cidarda hukum KAZANILMISTIR - yesil kalmali
        assert sonuc['el120'] == 'ok'
        # Olumsuz dallar auto-sized'da da aynen basilir (bilgi kaybi yok)
        assert sonuc['auto119'] == 'warn'
        assert sonuc['auto099'] == 'err'
        assert sonuc['yok'] == 'dim'

    def test_esik_sayisi_gevsetilmedi(self):
        g = self._marginKind()
        assert 'm < 1.0' in g and 'm < 1.2' in g

    def test_kart_auto_sized_bayragini_tasiyor(self):
        s = oku('hrma', 'static', 'js', 'panels', 'vessel_panel.js')
        assert s.count('marginKind(d.burst_margin, d.auto_sized)') == 2, (
            'iki kart da auto_sized bayragini tasimali')


class TestP11B5_20SunucuUyarisi:
    """Uyari ham cumle olarak rozet hapina basiliyor, ceviriden gecmiyordu."""

    def test_ham_yayici_kalmadi(self):
        s = oku('hrma', 'static', 'js', 'transient_panel.js')
        assert "forEach(w => { html += badge(w, 'warn'); })" not in s

    def test_ceviri_kanali_ve_tam_metin(self):
        s = oku('hrma', 'static', 'js', 'transient_panel.js')
        govde = re.search(r'const uyariRozeti = function \(ham\) \{(.*?)\n'
                          r'        \};', s, re.S)
        assert govde, 'uyariRozeti yayicisi yok'
        g = govde.group(1)
        assert 'window.SRV' in g, 'sunucu metni ceviri kanalindan gecmiyor'
        # Tam metin ipucunda durur: bilgi KAYBI olmamali
        assert re.search(r"badge\(kisa, 'warn', metin\)", s)

    def test_kirpma_davranisi_node_ile(self):
        s = oku('hrma', 'static', 'js', 'transient_panel.js')
        m = re.search(r'const uyariRozeti = function \(ham\) \{.*?\n        \};',
                      s, re.S)
        kaynak = ("var cagrilan=null;"
                  "function badge(t,k,ipucu){cagrilan={t:t,k:k,ipucu:ipucu};"
                  "return '';}"
                  + m.group(0).replace('window.SRV', 'global.SRV')
                  + "uyariRozeti('Chugging is likely in this configuration; "
                    "the feed pressure drop is below the injector stiffness "
                    "threshold and the chamber may couple with the line.');"
                    "console.log(JSON.stringify(cagrilan));")
        sonuc = node_kos(kaynak)
        assert len(sonuc['t']) <= 80, 'hap hala tam cumle tasiyor'
        assert len(sonuc['ipucu']) > len(sonuc['t']), 'tam metin kaybolmus'


class TestP11B4_19UQKunyesi:
    """Ornekleyici / surum / dagilim tanimlari ekrana hic cikmiyordu."""

    def test_kunye_kartlari_var(self):
        s = oku('hrma', 'static', 'js', 'panels', 'uncertainty_panel.js')
        g = islev_govdesi(s, 'samplerCards')
        assert 'data.sampler' in g and 'data.uq_version' in g

    def test_fail_closed_alan_yoksa_kart_yok(self):
        s = oku('hrma', 'static', 'js', 'panels', 'uncertainty_panel.js')
        g = islev_govdesi(s, 'samplerCards')
        assert re.search(r'if \(data\.sampler\)', g)
        assert re.search(r'if \(data\.uq_version\)', g)
        assert "'—'" not in g, 'kunye eksikken tire ile doldurulmus'

    def test_dagilim_tablosu_ucun_alanlarini_basiyor(self):
        s = oku('hrma', 'static', 'js', 'panels', 'uncertainty_panel.js')
        g = islev_govdesi(s, 'distributionsHtml')
        for alan in ('inputs_used', 'dist_label', 'source_note', 'applies_to'):
            assert alan in g, 'kunye alani basilmiyor: ' + alan

    def test_ozet_seridi_kunye_kartlarini_cagiriyor(self):
        """Kartlar TANIMLI olmasi yetmez — ozet seridine BAGLI olmali."""
        s = oku('hrma', 'static', 'js', 'panels', 'uncertainty_panel.js')
        g = islev_govdesi(s, 'summaryCards')
        assert 'samplerCards(data)' in g, (
            'kunye kartlari kosu ozetine bagli degil')

    def test_render_kunyeyi_cagiriyor(self):
        s = oku('hrma', 'static', 'js', 'panels', 'uncertainty_panel.js')
        g = islev_govdesi(s, 'render')
        assert 'distributionsHtml(data)' in g
        assert 'summaryCards(data)' in g

    def test_uc_kunyeyi_gercekten_yayimliyor(self):
        """Panel var olmayan alani beklemesin: uc sozlesmesi dogrulanir."""
        s = oku('hrma', 'app.py')
        for alan in ("'sampler': result['sampler']",
                     "'uq_version': result['uq_version']",
                     "'inputs_used': result['inputs_used']"):
            assert alan in s, 'uc kunye alani yayimlamiyor: ' + alan


class TestP11B5_18KutleOkuyucusu:
    """BEST EFFICIENCY uc tipte de oluydu: kutle anahtari hic tutmuyordu."""

    def test_gercek_kutle_yollari_baglandi(self):
        s = oku('hrma', 'static', 'js', 'panels', 'comparative_panel.js')
        g = islev_govdesi(s, 'currentMetrics')
        for yol in ('design_summary.key_dimensions.total_mass_kg',
                    'design_summary.masses.total_mass_kg',
                    'engine_mass_estimate'):
            assert yol in g, 'kutle yolu bagli degil: ' + yol

    def test_kutle_kapsamiyla_birlikte_tasiniyor(self):
        s = oku('hrma', 'static', 'js', 'panels', 'comparative_panel.js')
        g = islev_govdesi(s, 'currentMetrics')
        assert 'out.total_mass_scope = massScope;' in g
        assert re.search(r"if \(totalMass != null\) \{", g)

    def test_karisik_kapsamda_kutle_gonderilmez(self):
        s = oku('hrma', 'static', 'js', 'panels', 'comparative_panel.js')
        g = islev_govdesi(s, 'runComparison')
        assert 'kutleKapsamiKarisik' in g
        assert re.search(r"if \(kutleKapsamiKarisik && k === 'total_mass'\)"
                         r" return;", g), (
            'karisik kapsamda kutle hala gonderiliyor')

    def test_kart_nedeni_beyan_ediyor(self):
        s = oku('hrma', 'static', 'js', 'panels', 'comparative_panel.js')
        assert 'bestEfficiencyScopeTip' in s

    def test_yollar_gercek_uc_govdesinde_tutuyor(self):
        """Yollar UYDURULMADI: uc motorun GERCEK yanitinda okunur."""
        g = capa_govdeleri()
        beklenen = {
            'A1_hibrit_calculate':
                ('motor', 'design_summary', 'key_dimensions', 'total_mass_kg'),
            'A2_kati_calculate_solid':
                ('design_summary', 'masses', 'total_mass_kg'),
            'A3_sivi_calculate_liquid': ('engine_mass_estimate',),
        }
        for motor, yol in beklenen.items():
            cur = g[motor]['maskeli_govde']
            for p in yol:
                assert isinstance(cur, dict) and p in cur, (
                    motor + ' kutle yolu tutmuyor: ' + '.'.join(yol))
                cur = cur[p]


class TestOHD2106SozlukYuku:
    """505 KB sozluk sayfa acilisinda indiriliyordu."""

    def test_launch_site_acilista_yuklemiyor(self):
        s = oku('hrma', 'templates', 'launch_site.html')
        assert '<script src="/static/js/i18n_common.js"></script>' not in s

    def test_update_check_talep_uzerine_yukluyor(self):
        s = oku('hrma', 'static', 'js', 'update_check.js')
        g = islev_govdesi(s, 'sozlukHazir')
        assert 'i18n_common.js' in g
        # OH-UC-13 (D33-2): "ikinci kez yukleme kapisi" eskiden
        # `document.querySelector('script[src*=...]')` idi ve KUSURUN
        # kendisiydi — etiketin varligi sozlugun HAZIR oldugu anlamina
        # gelmiyor, `force` akisindaki ikinci cagri kendi etiketini gorup
        # erken donuyordu (pencere Ingilizce cizilmisti; olcum
        # docs/scofield/raw/OH/D33-2/altyapi/a1/). Kapi artik DURUMA bagli:
        # sozluk gercekten elde mi (I18N.has) ve inen bir istek var mi.
        assert 'sozlukYuklu()' in g, 'hazir olma olcutu sozluge sorulmuyor'
        assert 'SOZLUK_KUYRUK' in g, 'ikinci kez yukleme kapisi yok'
        assert 'onerror' in g, 'sozluk gelmezse pencere acilmali (yedek metin)'

    def test_pencere_sozlugu_bekliyor(self):
        s = oku('hrma', 'static', 'js', 'update_check.js')
        assert re.search(r'sozlukHazir\(function \(\) \{\s*'
                         r'if \(document\.getElementById\(.hrma-update-modal.\)\)'
                         r' return;\s*buildModal\(info\);', s)

    def test_anahtar_ailesi_gercekten_bu_sozlukte(self):
        """Bayat yorumun iddiasi (i18n_shell) olculerek yanlislandi."""
        uc = oku('hrma', 'static', 'js', 'update_check.js')
        anah = sorted(set(re.findall(r"T[F]?\(\s*'([\w.]+)'", uc)))
        common = oku('hrma', 'static', 'js', 'i18n_common.js')
        shell = oku('hrma', 'static', 'js', 'i18n_shell.js')
        c = sum(1 for a in anah if ("'" + a + "'") in common)
        sh = sum(1 for a in anah if ("'" + a + "'") in shell)
        assert c > sh, ('update.* ailesi i18n_common\'da yasiyor; '
                        'talep uzerine yukleme bu yuzden gerekli')


class TestP11B3_27KunyeAlanlari:
    """Kunye/tanim alanlari hicbir panelde okunmuyordu (kismi onarim)."""

    def test_node_order_tasiniyor(self):
        s = oku('hrma', 'static', 'js', 'fea_panel.js')
        g = islev_govdesi(s, 'buildViewModel')
        assert 'node_order: mesh.node_order || null' in g

    def test_node_order_ekranda(self):
        s = oku('hrma', 'static', 'js', 'fea_panel.js')
        assert 'vm.mesh_info.node_order || undefined' in s, (
            'sira sozlesmesi ekrana cikmiyor')

    def test_uc_alani_yayimliyor(self):
        assert "'node_order':" in oku('hrma', 'app.py')


class TestP11B4_30SiviMNCurutmesi:
    """Kalem: "M_N sivi yanitinda hic yayimlanmiyor" — OLCUMLE CURUTULDU."""

    def test_sivi_yaniti_M_N_yayimliyor(self):
        g = capa_govdeleri()
        sivi = g['A3_sivi_calculate_liquid']['maskeli_govde']
        deger = derin_ara(sivi, 'mean_flow_mach_M_N')
        assert deger, 'sivi yanitinda M_N yok'
        assert float(str(deger[0]).strip("'")) > 0

    def test_panel_sivi_yolunu_taniyor(self):
        s = oku('hrma', 'static', 'js', 'panels', 'stability_panel.js')
        g = re.search(r'nozzle_entrance_mach: \[(.*?)\],', s, re.S)
        assert g
        assert 'combustion_analysis.stability_analysis.acoustic_modes' in g.group(1)
        assert 'mean_flow_mach_M_N' in g.group(1)

    def test_kiraci_uc_tipte_de_cozulur(self):
        """Dort zorunlu alanin hepsi sivi govdesinde bulunur."""
        g = capa_govdeleri()
        sivi = g['A3_sivi_calculate_liquid']['maskeli_govde']
        for alan in ('sound_speed_m_s', 'mean_flow_mach_M_N'):
            assert derin_ara(sivi, alan), 'sivida cozulemeyen alan: ' + alan


class TestP11B5_19ErozyonBloklari:
    """Kalem: "erosion/flow_separation panelde hic gecmiyor" — D27'de onarilmis."""

    def test_erozyon_blogu_panelde(self):
        s = oku('hrma', 'static', 'js', 'transient_panel.js')
        assert 'const ero = tr.erosion;' in s
        assert 'badgeErosionNoSamples' in s, 'fail-closed dali yok'

    def test_ayrilma_blogu_panelde(self):
        s = oku('hrma', 'static', 'js', 'transient_panel.js')
        assert 'const fsep = tr.flow_separation;' in s
        assert 'badgeSeparationUnknown' in s, 'fail-closed dali yok'

    def test_uc_bu_bloklari_yayimliyor(self):
        s = oku('hrma', 'analysis', 'transient_ballistics.py')
        assert "'erosion': {" in s and "'flow_separation': {" in s
