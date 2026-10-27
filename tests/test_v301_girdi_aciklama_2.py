"""v3.0.1 N-girdi-2 bekçisi — hesap sonrası paneller, şablon yörünge/paraşüt alanları,
katı seçiciler, hibrit 3B tasarım kaydırıcıları, proje/ayarlar/hata bildir pencereleri
ve ana sayfa dil seçicisi: her girdinin yanında açıklama.

Berke (26 Eki 2026): "Her bir inputun yanında açıklaması olmalı, istisnasız."

Ölçümün (docs/scofield/raw/OH/V301/girdi-aciklama/ikinci/olcum2.py) STATİK eşdeğeri:
  (a) her kontrolün işaretlemesinde ipucu anahtarı LİTERAL olarak durur ve ortak
      bileşenle (HRMAHelp) ya da şablon desenle (.tooltip-text[data-i18n]) basılır;
  (b) her anahtar ilgili sözlükte EN ve TR bloklarında tanımlı, dolu, TR İngilizce
      kopya değil;
  (c) 6-DOF alan tanımlarının HEPSİ `help` taşır; etiket metni iç <span>'da çevrilir
      (label'daki data-i18n ipucunu silerdi);
  (d) kayıtlı Chromium ölçümü: kapsamda açıklamasız kontrol 0.
Ters mutasyon RAPOR.md'de.
"""
import json
import pathlib
import re

import pytest

from tests.support.kanit import kanit_gerekli, kanit_yolu

ROOT = pathlib.Path(__file__).resolve().parents[1]
JS = ROOT / 'hrma' / 'static' / 'js'
TPL = ROOT / 'hrma' / 'templates'
KANIT = kanit_yolu('docs/scofield/raw/OH/V301/girdi-aciklama/ikinci')


def oku(p):
    return pathlib.Path(p).read_text(encoding='utf-8')


#: dosya → (sözlük dosyası, [ipucu anahtarları]) — anahtarlar kaynakta LİTERAL aranır.
KAYNAK_ANAHTARLARI = {
    JS / 'sixdof_panel.js': ('i18n_common.js', [
        'sixdof.help.bodyD', 'sixdof.help.bodyL', 'sixdof.help.noseL', 'sixdof.help.noseType',
        'sixdof.help.finCount', 'sixdof.help.finRoot', 'sixdof.help.finTip', 'sixdof.help.finSpan',
        'sixdof.help.finSweep', 'sixdof.help.finPos', 'sixdof.help.dryMass', 'sixdof.help.propMass',
        'sixdof.help.cd0', 'sixdof.help.wind', 'sixdof.help.windDir', 'sixdof.help.elev',
        'sixdof.help.azimuth', 'sixdof.help.rail', 'sixdof.help.thrust', 'sixdof.help.burn',
        'sixdof.help.useCurve', 'sixdof.help.thrustSource', 'sixdof.help.motorSelect',
        'sixdof.help.modeSimple', 'sixdof.help.modeComponent', 'sixdof.help.compName',
        'sixdof.help.compMass', 'sixdof.help.compX', 'sixdof.help.compProp']),
    JS / 'fea_panel.js': ('i18n_common.js', ['panel.fea.help.showMesh', 'panel.fea.help.qualityMetric',
                                             'panel.grain.help.outer', 'panel.grain.help.core',
                                             'panel.grain.help.pc', 'panel.grain.help.length']),
    JS / 'panels' / 'cfd_panel.js': ('i18n_common.js', [
        'panel.cfd.help.' + k for k in ('P0', 'T0', 'gamma', 'R', 'Pamb', 'Pb', 'k', 'resolution',
                                        'viscousMode', 'turbulence', 'Twall')]),
    JS / 'panels' / 'stability_panel.js': ('i18n_common.js', [
        'panel.stab.help.' + k for k in ('soundSpeed', 'chamberLength', 'gamma', 'machN', 'J', 'tau',
                                         'tauC', 'tauF', 'feedLen', 'feedDia', 'feedArea', 'feedMdot',
                                         'feedDp', 'feedRho')]),
    JS / 'motor_viz_deck.js': ('i18n_common.js', ['viz.help.deckDch', 'viz.help.deckLen',
                                                  'viz.help.deckEps', 'viz.help.timeline']),
    JS / 'step_import_ui.js': ('i18n_common.js', ['stepimp.help.solids', 'stepimp.help.suggestion']),
    TPL / 'launch_site.html': ('i18n_launch_site.js', [
        'site.help.' + k for k in ('lat', 'lon', 'vehicleSource', 'project', 'vThrust', 'vBurnTime',
                                   'vPropMass', 'vInertMass', 'bodyDia', 'bodyLen', 'dryMass', 'cd0',
                                   'finCount', 'finSpan', 'windSpeed', 'windDir', 'elev', 'azim',
                                   'presets', 'online', 'time', 'exaggerate', 'follow', 'tileNetwork')]),
    JS / 'thermal_fea_panel.js': ('i18n_common.js', ['panel.feaT.help.ambient', 'panel.feaT.help.showMesh']),
    JS / 'project_bar.js': ('i18n_common.js', ['proj.help.name', 'proj.help.desc']),
    JS / 'settings_panel.js': ('i18n_shell.js', [
        'shell.bug.help.title', 'shell.bug.help.what', 'shell.bug.help.expected',
        'shell.bug.help.steps', 'shell.bug.help.diagnostics', 'shell.bug.help.previewTitle',
        'shell.bug.help.body', 'shell.bug.help.url']),
    TPL / 'solid.html': ('i18n_pages.js', [
        'solid.ui.initial_wet_mass_kg_help', 'solid.ui.final_dry_mass_kg_help',
        'solid.ui.drag_coefficient_help', 'solid.ui.reference_area_m2_help',
        'solid.ui.parachute_area_m2_help', 'solid.ui.parachute_cd_help',
        'solid.ui.parachute_deploy_delay_s_help', 'solid.ui.family_help',
        'solid.ui.structural_material_catalogue_apply_to_help']),
    TPL / 'liquid.html': ('i18n_pages.js', ['liq.ui.drag_coefficient_help',
                                            'liq.ui.reference_area_m2_help']),
    TPL / 'advanced.html': ('i18n_advanced.js', [
        'adv.tip.vizDesignDch', 'adv.tip.vizDesignLstar', 'adv.tip.vizDesignEps',
        'adv.tip.vizTimeline']),
    TPL / 'index.html': ('i18n.js', ['lang.help']),
}

#: şablon kontrolü → ipucu anahtarı: kontrolü saran kapta (label / div) dolu balon.
SABLON_KONTROLLERI = {
    'solid.html': {'traj_initial_mass': 'solid.ui.initial_wet_mass_kg_help',
                   'traj_final_mass': 'solid.ui.final_dry_mass_kg_help',
                   'traj_drag_coeff': 'solid.ui.drag_coefficient_help',
                   'traj_ref_area': 'solid.ui.reference_area_m2_help',
                   'parachute_area': 'solid.ui.parachute_area_m2_help',
                   'parachute_cd': 'solid.ui.parachute_cd_help',
                   'parachute_deploy_delay': 'solid.ui.parachute_deploy_delay_s_help'},
    'liquid.html': {'traj_drag_coeff': 'liq.ui.drag_coefficient_help',
                    'traj_ref_area': 'liq.ui.reference_area_m2_help'},
}


def _sozluk_metin(ad):
    """Node'a bağlı kalmadan yedek: anahtarın dosyada iki kez (EN + TR) geçtiği metinler."""
    s = oku(JS / ad)
    out = {}
    for m in re.finditer(r"^\s*'([^']+)'\s*:\s*'((?:[^'\\]|\\.)*)'\s*,?\s*$", s, re.M):
        out.setdefault(m.group(1), []).append(m.group(2))
    return out


@pytest.mark.parametrize('dosya', sorted(KAYNAK_ANAHTARLARI, key=str), ids=lambda p: p.name)
def test_ipucu_anahtari_kaynakta_literal(dosya):
    src = oku(dosya)
    _, anahtarlar = KAYNAK_ANAHTARLARI[dosya]
    eksik = [k for k in anahtarlar if ("'%s'" % k) not in src and ('"%s"' % k) not in src]
    assert not eksik, (dosya.name, eksik)


@pytest.mark.parametrize('dosya', sorted(KAYNAK_ANAHTARLARI, key=str), ids=lambda p: p.name)
def test_ipucu_anahtari_en_ve_tr_sozlukte_dolu_ve_cevrilmis(dosya):
    sozluk, anahtarlar = KAYNAK_ANAHTARLARI[dosya]
    d = _sozluk_metin(sozluk)
    for k in anahtarlar:
        v = d.get(k, [])
        assert len(v) == 2, (sozluk, k, 'EN + TR iki blokta birer kez olmalı', len(v))
        en, tr = v
        assert len(en.strip()) > 20 and len(tr.strip()) > 20, (k, 'metin boş/kısa')
        assert en != tr, (k, 'TR İngilizce kopya')
        assert re.search(r'[çğıöşüÇĞİÖŞÜ]', tr), (k, 'TR metinde Türkçe harf yok')


def test_altidof_her_alan_ipucu_tasir_ve_etiket_ici_spanda_cevrilir():
    src = oku(JS / 'sixdof_panel.js')
    i = src.index('const FIELDS = [')
    j = src.index('];', i)
    alanlar = re.findall(r"\{ id: '(sd_[a-z_0-9]+)'([^\n]*)", src[i:j])
    assert len(alanlar) >= 20, len(alanlar)
    eksik = [fid for fid, govde in alanlar if "help: 'sixdof.help." not in govde]
    assert not eksik, eksik
    # fieldHtml: ipucu etiketin içinde, data-i18n iç <span>'da
    g = src[src.index('function fieldHtml(f)'):]
    g = g[:g.index('\n    }\n')]
    assert "helpHtml(f.help)" in g
    assert "'<label><span'" in g, 'etiket metni iç span\'da çevrilmiyor (data-i18n label\'da ipucunu siler)'
    # yardımcı ortak bileşeni kullanır
    h = src[src.index('function helpHtml(key)'):]
    h = h[:h.index('\n    }\n')]
    assert 'window.HRMAHelp.html(key' in h


def test_altidof_bilesen_tablosu_hucreleri_aciklamali():
    src = oku(JS / 'sixdof_panel.js')
    for sinif, k in (('sd-c-name', 'compName'), ('sd-c-mass', 'compMass'),
                     ('sd-c-x', 'compX'), ('sd-c-prop', 'compProp')):
        i = src.index('class="%s"' % sinif)
        parca = src[i:i + 260]
        assert "compTitle('sixdof.help.%s')" % k in parca, sinif
        assert "helpHtml('sixdof.help.%s')" % k in src, ('sütun başlığı ipucu', k)
    ct = src[src.index('function compTitle(key)'):]
    ct = ct[:ct.index('\n    }\n')]
    assert 'data-i18n-title' in ct and 'title=' in ct


@pytest.mark.parametrize('sablon', sorted(SABLON_KONTROLLERI))
def test_sablon_kontrolu_kabinda_dolu_balon(sablon):
    s = oku(TPL / sablon)
    for kid, anahtar in SABLON_KONTROLLERI[sablon].items():
        i = s.index('id="%s"' % kid)
        bas = s.rindex('<label', 0, i)
        parca = s[bas:i]
        m = re.search(r'class="tooltip-text"[^>]*data-i18n="([^"]+)">([^<]{20,})<', parca)
        assert m, (sablon, kid, 'kapta balon yok')
        assert m.group(1) == anahtar, (sablon, kid, m.group(1))


SAHA_KONTROLLERI = ['ls-lat', 'ls-lon', 'ls-vehicle-source', 'ls-project', 'ls-v-thrust', 'ls-v-burntime',
                    'ls-v-propmass', 'ls-v-inertmass', 'ls-a-bodydia', 'ls-a-bodylen', 'ls-a-drymass',
                    'ls-a-cd0', 'ls-a-fincount', 'ls-a-finspan', 'ls-a-windspeed', 'ls-a-winddir',
                    'ls-a-elev', 'ls-a-azim', 'ls-presets', 'ls-online', 'ls-time', 'ls-exagg',
                    'ls-follow', 'ls-tile-network']


def test_firlatma_sahasi_her_kontrolun_kabinda_balon():
    """Kap: kontrolü saran en yakın .ls-field / label.ls-check / label.ls-hint / .ls-player;
    sonu kontrolden sonraki ilk </label> ya da </div>."""
    s = oku(TPL / 'launch_site.html')
    baslar = ('<div class="ls-field"', '<label class="ls-check">', '<label class="ls-hint"',
              '<div class="ls-player">')
    eksik = []
    for kid in SAHA_KONTROLLERI:
        i = s.index('id="%s"' % kid)
        bas = max(s.rfind(b, 0, i) for b in baslar)
        assert bas >= 0, kid
        son = min(x for x in (s.find('</label>', i), s.find('</div>', i)) if x > 0)
        if not re.search(r'class="tooltip-text"[^>]*data-i18n="site\.help\.[A-Za-z0-9]+"', s[bas:son]):
            eksik.append(kid)
    assert not eksik, eksik


def test_kati_secicilerin_yaninda_balon():
    s = oku(TPL / 'solid.html')
    for kid, anahtar in (('propellant_family_filter', 'solid.ui.family_help'),
                         ('material_catalog_target', 'solid.ui.structural_material_catalogue_apply_to_help')):
        i = s.index('<select id="%s"' % kid)
        bas = s.rindex('<div class="catalog-toolbar">', 0, i)
        assert 'data-i18n="%s"' % anahtar in s[bas:i], kid


def test_hibrit_tasarim_kaydiricilari_ve_zaman_cizgisi_aciklamali():
    s = oku(TPL / 'advanced.html')
    for kid, anahtar in (('viz_ds_dch', 'adv.tip.vizDesignDch'), ('viz_ds_lstar', 'adv.tip.vizDesignLstar'),
                         ('viz_ds_eps', 'adv.tip.vizDesignEps')):
        i = s.index('id="%s"' % kid)
        bas = s.rindex('<div class="viz-dctrl">', 0, i)
        assert 'data-i18n="%s"' % anahtar in s[bas:i], kid
    i = s.index('id="viz_slider"')
    son = s.index('</div>', i)
    assert 'data-i18n="adv.tip.vizTimeline"' in s[i:son]


def test_fea_isil_enjektor_kontrolleri_ipucu_basar():
    fea = oku(JS / 'fea_panel.js')
    for kid, k in (('fea_show_mesh', 'panel.fea.help.showMesh'), ('fea_metric', 'panel.fea.help.qualityMetric'),
                   ('grainfea_show_mesh', 'panel.fea.help.showMesh')):
        i = fea.index('id="%s"' % kid)
        bas = fea.rindex('<label', 0, i)
        son = fea.index('</label>', i)
        assert "yardimHtml('%s')" % k in fea[bas:son], kid
    t = oku(JS / 'thermal_fea_panel.js')
    for kid, k in (('fea_t_ambient', 'panel.feaT.help.ambient'), ('fea_t_show_mesh', 'panel.feaT.help.showMesh')):
        i = t.index('id="%s"' % kid)
        bas = t.rindex('<label', 0, i)
        son = t.index('</label>', i)
        assert "yardimHtml('%s')" % k in t[bas:son], kid
    inj = oku(JS / 'injector_panel.js')
    i = inj.index('id="inj_n2o"')
    assert 'data-i18n-title="inj.helpN2o"' in inj[i:i + 200]


def test_pencereler_ipucu_basar():
    pb = oku(JS / 'project_bar.js')
    assert "window.HRMAHelp.attach(label, 'proj.help.name', T('proj.help.name'" in pb
    assert "window.HRMAHelp.attach(descLabel, 'proj.help.desc'" in pb
    sp = oku(JS / 'settings_panel.js')
    for k in ('shell.bug.help.title', 'shell.bug.help.what', 'shell.bug.help.expected',
              'shell.bug.help.steps', 'shell.bug.help.previewTitle', 'shell.bug.help.url'):
        assert re.search(r"fieldLabel\([^;]*'%s'\)" % re.escape(k), sp), k
    for kap, k in (('diagRow', 'shell.bug.help.diagnostics'), ('langRow', 'shell.settings.languageDesc'),
                   ('autoRow', 'shell.settings.autoCheckDesc')):
        assert "yardim(%s, '%s')" % (kap, k) in sp, kap
    # ortak bileşen pencere betiklerinden ÖNCE yüklenir
    for sablon, sonraki in (('index.html', 'project_bar.js'), ('formulas.html', 'settings_panel.js'),
                            ('launch_site.html', 'settings_panel.js')):
        s = oku(TPL / sablon)
        a = s.index('<script src="/static/js/field_help.js"></script>')
        b = s.index('<script src="/static/js/%s"></script>' % sonraki)
        assert a < b, sablon


@pytest.mark.parametrize('dil', ['tr', 'en'])
def test_kayitli_son_olcum_kapsamda_aciklamasiz_yok(dil):
    yol = kanit_gerekli(KANIT / ('son_olcum_%s.json' % dil))
    d = json.loads(pathlib.Path(yol).read_text(encoding='utf-8'))
    for ad, dd in d['sayfalar'].items():
        for an in ('once', 'sonra'):
            if an not in dd:
                continue
            acik = [x['id'] or x['cls'] for x in dd[an]['girdi']
                    if not (x['tooltip'] or x['title'] or x['help'])]
            assert not acik, (dil, ad, an, acik)
