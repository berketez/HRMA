# -*- coding: utf-8 -*-
"""ÖH Dalga-26 / kulvar **arayuz**, aşama 3/4 — bekçiler.

Kapsanan defter kalemleri (11):

* **P11B3-19** uzun koşumda İPTAL DÜĞMESİ yoktu (zaman aşımı P17B4-07'de
  gelmişti); ölçülen viskoz koşu 72,3 s, ucun cüzdanı 382,4 s'e çıkıyor ve
  kullanıcının tek çıkışı sayfayı yenilemekti.
* **P11B3-20** yapısal NOT_MODELLED dalında ``fea.notes`` ve ``fea.warning``
  görünüm modeline alınıp hiç basılmıyordu; kardeş tane paneli basıyordu.
* **P11B3-21** her iki FEA panelinde ``mesh.meta`` alınıp basılmıyordu; blok
  dış yüzeyin DEĞİŞTİRİLDİĞİNİ ve cidarın yer yer kalınlaştığını beyan eder.
* **P11B3-23** tane panelinde ``fields.max_principal_pa`` hiç okunmuyordu.
* **P11B3-24** CFD görünüm modeli ``section_average`` / ``transport`` /
  ``boundary_viscous_flux`` bloklarını kuruyor, hiçbirini basmıyordu.
* **P11B4-01** panel TEKİL ``warning``ı okuyor, uç ÇOĞUL ``warnings``
  listesini de gönderiyordu — her koşumda bir uyarı yutuluyordu.
* **P11B4-02** "VERDICT ISSUED" yalnız ``design_basis.verdict``e bakıyordu;
  ``safety_analysis.status = NOT_EVALUATED`` iken de yeşil/nötr "ISSUED"
  basılıyor, gerekçe listesi hiç okunmuyordu.
* **P11B4-07** ``RISK: NOT_EVALUATED`` KIRMIZI, ``STRUCTURE: NOT_EVALUATED``
  CYAN basılıyordu — aynı olgu, iki renk.
* **P11B4-08** SF renk eşiği çıplak ``sf < required`` idi; ekranda aynı sayı
  (4.00) bir satırda turuncu, diğerinde yeşil çıkıyordu (4,4e-16 fark).
* **P11B4-10** ayrılma bloğunun nominal/kötü-durum çifti panelde tekilleşiyor;
  dört alan hiç okunmuyordu.
* **P11B4-17** dağılımı OLMAYAN çıktı (σ = 0) "P50 [P5, P95] güven bandı"
  kartı olarak basılıyor ve histogram seçicisine giriyordu.

Yöntem: davranış iddiaları GERÇEK RENDER altında ölçülür (node + P11B4
taklit DOM'u ``docs/scofield/raw/P11/B4-repro-03.js``); kanal/kapı
iddiaları kaynak sözleşmesiyle kilitlenir. Ham kanıt ve önce/sonra
sayılar: ``docs/scofield/raw/OH/D26/arayuz/a3/``.
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
PANELS = JS / 'panels'
HARNESS = KOK / 'docs' / 'scofield' / 'raw' / 'P11' / 'B4-repro-03.js'

NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(
    NODE is None,
    reason='node kurulu değil — panelleri GERÇEK render altında ölçen '
           'bekçiler koşamaz (kurulum: `brew install node`)')

KIRMIZI = 'var(--hd-red'
CYAN = 'var(--hd-cyan'

_BLOK = re.compile(r'/\*.*?\*/', re.S)
_SATIR = re.compile(r'^[ \t]*(?://|//:).*$', re.M)


def govde(yol):
    """Yorumları sökülmüş JS gövdesi — bekçi yalnız ÇALIŞAN koda bakar."""
    metin = yol.read_text(encoding='utf-8')
    return _SATIR.sub('', _BLOK.sub('', metin))


def kos(cfg):
    """Taklit DOM'da paneli GERÇEKTEN render eder."""
    p = subprocess.run([NODE, kanit_gerekli(str(HARNESS))], input=json.dumps(cfg),
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-2000:]
    return json.loads(p.stdout)


# ===========================================================================
# P11B3-19 — İPTAL DÜĞMESİ
# ===========================================================================
class TestP11B319IptalDugmesi:
    """Kullanıcı başlattığı koşumu DURDURABİLMELİ."""

    def test_yapisal_ve_tane_kosumunda_iptal_kanali_var(self):
        s = govde(JS / 'fea_panel.js')
        assert 'new AbortController' in s, (
            'fea_panel.js hiçbir koşumu iptal edemiyor: AbortController yok')
        assert re.search(r'function\s+kosumuIptalEt', s), (
            'iptal işleyicisi yok')
        # Düğme HER İKİ koşumda da kurulmalı (yapısal + tane).
        assert 'fea_cancel' in s and 'grainfea_cancel' in s, (
            'iki koşumun ikisinde de iptal düğmesi olmalı')
        # Sinyal fetch çağrılarına GERÇEKTEN bağlanmalı.
        assert s.count("kosumSinyali('structural')") == 1
        assert s.count("kosumSinyali('grain')") == 1

    def test_termal_kosumunda_iptal_kanali_var(self):
        s = govde(JS / 'thermal_fea_panel.js')
        assert 'new AbortController' in s
        assert re.search(r'function\s+kosumuIptalEt', s)
        assert 'fea_t_cancel' in s
        assert s.count("signal: kosumSinyali(),") == 1
        # İKİ ADIMLI koşum TEK sinyal taşır: iptal ikinci adımı da durdurur.
        assert 'signal: aktifSinyal || zamanAsimiSinyali(),' in s, (
            'ikinci adım kendi sinyalini kurarsa iptal onu durduramaz')

    def test_kullanici_iptali_zaman_asimindan_AYRI_beyan_edilir(self):
        """İptal bir arıza değildir ve arıza cümlesiyle anlatılamaz."""
        for yol, anahtar in ((JS / 'fea_panel.js', 'fea.cancelled'),
                             (JS / 'fea_panel.js', "GL('cancelled'"),
                             (JS / 'thermal_fea_panel.js', 'feaT.cancelled')):
            s = govde(yol)
            assert anahtar in s, (
                '%s: kullanıcı iptali için AYRI metin yok (zaman aşımı '
                'cümlesi kullanıcının kendi kararını arıza gibi anlatır)'
                % yol.name)

    def test_sure_siniri_hala_TEK_kaynaktan(self):
        """P17B4-07'nin tek-kaynak kilidi iptal eklenirken bozulmadı."""
        s = govde(JS / 'fea_panel.js')
        assert s.count('const ISTEK_ZAMAN_ASIMI_MS = 180000') == 1
        t = govde(JS / 'thermal_fea_panel.js')
        assert '180000' not in t, (
            'termal panel süre sınırını İKİNCİ kez yazmamalı — '
            'window.HRMA_ISTEK_ZAMAN_ASIMI_MS tek kaynaktır')


# ===========================================================================
# P11B3-20 — NOT_MODELLED dalında notes/warning
# ===========================================================================
class TestP11B320NotModelledDetay:

    def test_yapisal_dal_notlari_ve_uyariyi_basiyor(self):
        s = govde(JS / 'fea_panel.js')
        assert re.search(r'function\s+notModelledDetay', s)
        # Yapısal NOT_MODELLED çipi detayı GERÇEKTEN çağırmalı (tanım
        # satırının kendisi çağrı sayılmaz — çapa çip ifadesidir).
        assert '[missing, vm.reason, notModelledDetay(vm)]' in s
        assert 'vm.notes' in s, 'notes görünüm modelinden okunmuyor'

    @node_gerekli
    def test_notlar_ve_uyari_render_ciktisinda(self):
        """Uç NOT_MODELLED derse eksik alanın GEREKÇESİ de ekrana iner."""
        vm = kos({
            'panelId': '__yok__',
            'panelFiles': ['hrma/static/js/fea_panel.js'],
            'evalFn': (
                "return window.FeaPanel.buildViewModel({"
                " status: 'not_modelled', missing: ['cidar kalınlığı'],"
                " reason: 'FEA girdisi çıkarılamadı',"
                " notes: {cidar: 'cidar alanı boş geldi'},"
                " warning: {code: 'warn.fea.inputs_missing', params: {}}"
                "});"),
        })['evaled']
        assert vm['mode'] == 'not_modelled'
        assert vm['notes'] == {'cidar': 'cidar alanı boş geldi'}
        assert vm['warning']['code'] == 'warn.fea.inputs_missing'


# ===========================================================================
# P11B3-21 — mesh.meta (dış yüzey DEĞİŞTİRİLDİ beyanı)
# ===========================================================================
class TestP11B321MeshMeta:

    @pytest.mark.parametrize('ad', ['fea_panel.js', 'thermal_fea_panel.js'])
    def test_iki_panel_de_dis_yuzey_beyanini_okuyor(self, ad):
        s = govde(JS / ad)
        assert 'dis_yuzey_egrilik_tabani' in s, (
            '%s ağ üreticisinin geometri beyanını hiç anmıyor' % ad)
        assert re.search(r'function\s+disYuzeyBeyani', s)
        assert 'kalinlik_sapma_orani' in s
        assert 'duzeltilen_istasyon' in s

    @pytest.mark.parametrize('ad', ['fea_panel.js', 'thermal_fea_panel.js'])
    def test_beyan_ROZET_katinda_da_var(self, ad):
        """Katlanmış künyede kalan beyan görünmez (P11B3-15 dersi)."""
        s = govde(JS / ad)
        onek = 'fea' if ad == 'fea_panel.js' else 'feaT'
        assert "badge(TF('%s.badgeOuterModified'," % onek in s, (
            '%s: geometri değişikliği yalnız künyede kalıyor' % ad)

    @pytest.mark.parametrize('ad', ['fea_panel.js', 'thermal_fea_panel.js'])
    def test_alan_yoksa_iddia_yok(self, ad):
        """Fail-closed: meta gelmezse hiçbir cümle uydurulmaz."""
        s = govde(JS / ad)
        m = re.search(r'function disYuzeyBeyani\(meta\) \{(.{0,240})', s, re.S)
        assert m and 'return null' in m.group(1)


# ===========================================================================
# P11B3-23 — max_principal_pa
# ===========================================================================
class TestP11B323MaksAsalGerilme:

    def test_panel_alani_okuyor_ve_rozette_basiyor(self):
        s = govde(JS / 'fea_panel.js')
        assert 'max_principal_pa' in s, (
            'tane paneli kopma ölçütünün doğal büyüklüğünü hiç okumuyor')
        assert 'badgeMaxPrincipal' in s

    @node_gerekli
    def test_yayimlanan_diziden_TEPE_deger_gelir(self):
        """Sayı türetilmez: ucun dizisinin maksimumu, Pa→MPa."""
        vm = kos({
            'panelId': '__yok__',
            'panelFiles': ['hrma/static/js/fea_panel.js'],
            'evalFn': (
                "var mesh = {nodes: [[0,0],[1,0],[1,1],[0,1]],"
                " elems: [[0,1,2,3]], node_index_grid: [[0,3],[1,2]],"
                " n_nodes: 4, n_elems: 1, n_theta: 1, n_radial: 1};"
                "return window.GrainFeaPanel.buildViewModel({"
                " status: 'ok', mesh: mesh,"
                " fields: {von_mises_pa: [1,2,3,4],"
                "          max_principal_pa: [1e6, 7.5e6, 3e6, 2e6]},"
                " bore: {}, scalars: {}, convergence: {}"
                "}).scalars;"),
        })['evaled']
        assert vm['max_principal_max_mpa'] == pytest.approx(7.5)

    @node_gerekli
    def test_dizi_yoksa_UYDURULMAZ(self):
        vm = kos({
            'panelId': '__yok__',
            'panelFiles': ['hrma/static/js/fea_panel.js'],
            'evalFn': (
                "var mesh = {nodes: [[0,0],[1,0],[1,1],[0,1]],"
                " elems: [[0,1,2,3]], node_index_grid: [[0,3],[1,2]],"
                " n_nodes: 4, n_elems: 1, n_theta: 1, n_radial: 1};"
                "return window.GrainFeaPanel.buildViewModel({"
                " status: 'ok', mesh: mesh,"
                " fields: {von_mises_pa: [1,2,3,4]},"
                " bore: {}, scalars: {}, convergence: {}"
                "}).scalars;"),
        })['evaled']
        assert vm['max_principal_max_mpa'] is None


# ===========================================================================
# P11B3-24 — CFD'nin üç ölü bloğu
# ===========================================================================
class TestP11B324OluBloklar:

    def test_uc_blok_da_basiliyor(self):
        s = govde(PANELS / 'cfd_panel.js')
        for fn in ('transportHtml', 'boundaryFluxHtml', 'sectionAverageFigure'):
            assert re.search(r'function\s+%s' % fn, s), (
                '%s yok — blok hâlâ ölü katman' % fn)
        # Kurulan blok GERÇEKTEN çağrılmalı (tanım yetmez — a1 dersi).
        assert 'transportHtml(v)' in s
        assert 'boundaryFluxHtml(v)' in s
        assert 'sectionAverageFigure(vm)' in s

    @node_gerekli
    def test_render_uc_blogun_alanlarini_ekrana_koyuyor(self):
        cikti = kos({
            'panelId': '__yok__',
            'panelFiles': ['hrma/static/js/panels/cfd_panel.js'],
            'dataInline': {
                'cfd': {
                    'section_average': {
                        'z_m': [0.0, 0.1, 0.2], 'mach': [0.2, 1.0, 2.4],
                        'pressure_Pa': [5e6, 3e6, 8e5],
                        '_basis': 'Hacim ağırlıklı kolon ortalaması.',
                    },
                    'viscous': {
                        'enabled': True,
                        'transport': {'viscosity_law_source': 'Sutherland',
                                      'prandtl': 0.72},
                        'boundary_viscous_flux': {
                            'inlet_energy_W': 1234.5,
                            'outlet_energy_W': -987.6,
                            'inlet_axial_force_N': 3.21,
                            'outlet_axial_force_N': -1.23},
                        'wall': {}, 'y_plus': {},
                    },
                },
            },
            'evalFn': (
                "var root = document.createElement('div');"
                "window.CfdPanel._render(body, root);"
                "function metin(n){ var s = String(n.innerHTML || '');"
                " (n.children||[]).forEach(function(c){ s += metin(c); });"
                " return s; }"
                "return {html: metin(root),"
                " plots: (window.__plots||[]).map(function(p){return p.id;})};"),
        })['evaled']
        html = cikti['html']
        assert 'viscosity_law_source' in html, 'taşınım künyesi ekranda yok'
        assert 'inlet_energy_W' in html, 'sınır viskoz akısı ekranda yok'
        assert any(str(i).startswith('cfd_secavg_') for i in cikti['plots']), (
            'kolon ortalaması profili çizilmiyor: %r' % (cikti['plots'],))


# ===========================================================================
# P11B4-01 / -02 / -07 / -08 — yapısal panel
# ===========================================================================
def _yapisal_yuk(status='NOT_EVALUATED', verdict='issued'):
    return {
        'structural_analysis': {
            'safety_analysis': {
                'status': status, 'risk_level': status,
                'minimum_safety_factor': None,
                'verdict_withheld_reasons': ['stations_not_verified'],
                'recommendations': [],
            },
            'buckling_analysis': {},
            'fatigue_analysis': {},
            'fastener_analysis': {
                'warning': None,
                'warnings': [{'code': 'warn.structural.'
                                      'fastener_preload_not_modeled',
                              'params': {'module': 'bolted_joint'},
                              'severity': 'warning'}],
            },
            'end_cap_analysis': {}, 'material_properties': {},
            'design_parameters': {}, 'weight_analysis': {},
            'chamber_analysis': {},
        },
        'design_basis': {'verdict': verdict},
    }


@node_gerekli
class TestYapisalPanelHukumleri:

    def _render(self, yuk):
        return kos({
            'panelId': 'structural',
            'panelFiles': ['hrma/static/js/panels/structural_panel.js'],
            'dataInline': yuk,
        })

    def test_p11b4_01_cogul_warnings_yutulmuyor(self):
        r = self._render(_yapisal_yuk())
        assert r['error'] is None, r['error']
        assert 'fastener_preload_not_modeled' in r['html'], (
            'ÇOĞUL warnings listesi hâlâ yutuluyor')

    def test_p11b4_02_hukum_geri_cekildiyse_ISSUED_basilmaz(self):
        r = self._render(_yapisal_yuk())
        assert 'VERDICT ISSUED' not in r['text'], (
            'STRUCTURE: NOT_EVALUATED ile yan yana "VERDICT ISSUED" '
            'basılıyor — ekran kendi kendisiyle çelişiyor')
        assert 'VERDICT WITHHELD' in r['text']

    def test_p11b4_02_gerekce_ekranda(self):
        r = self._render(_yapisal_yuk())
        assert 'stations_not_verified' in r['html'], (
            'hüküm geri çekildi ama gerekçe hiç basılmıyor')

    def test_p11b4_02_hukum_verildiginde_ISSUED_geri_gelir(self):
        """Ölçüt gevşetilmedi: gerçek hüküm hâlâ ISSUED basılır."""
        r = self._render(_yapisal_yuk(status='SAFE'))
        assert 'VERDICT ISSUED' in r['text']

    def test_p11b4_07_ayni_olgu_ayni_renk(self):
        r = self._render(_yapisal_yuk())
        html = r['html']
        rozetler = re.findall(
            r'color:(var\(--hd-[a-z]+)[^;]*;[^<]*"[^>]*>\s*'
            r'(STRUCTURE|RISK): NOT_EVALUATED', html)
        renkler = {ad: renk for renk, ad in rozetler}
        assert set(renkler) == {'STRUCTURE', 'RISK'}, (
            'iki rozet de basılmalı: %r' % (rozetler,))
        assert renkler['STRUCTURE'] == renkler['RISK'], (
            'aynı olgu iki renkte: %r' % (renkler,))
        assert KIRMIZI not in renkler['RISK'], (
            'kazanılmamış hüküm KIRMIZI (en yüksek risk) basılamaz')

    def test_p11b4_07_gercek_yuksek_risk_hala_kirmizi(self):
        """Ölçüt gevşetilmedi."""
        r = self._render(_yapisal_yuk(status='HIGH'))
        assert re.search(r'color:var\(--hd-red[^;]*;[^<]*"[^>]*>\s*RISK: HIGH',
                         r['html']), 'gerçek yüksek risk kırmızı kalmalı'


class TestP11B408KayanNoktaEsigi:

    def test_bagil_tolerans_TEK_yerde(self):
        s = govde(PANELS / 'structural_panel.js')
        assert s.count('const SF_RENK_BAGIL_TOLERANS') == 1
        assert 'sf < required' not in s, (
            'çıplak karşılaştırma geri geldi — renk yine kayan nokta '
            'gürültüsüne oturur')

    @node_gerekli
    def test_ayni_sayi_ayni_renk(self):
        """4,0 ile 4,0 − 4,4e-16 AYNI rengi almalı (ölçülen kusur)."""
        e = kos({
            'panelId': '__yok__',
            'panelFiles': ['hrma/static/js/panels/structural_panel.js'],
            'evalFn': (
                "var P = window.StructuralPanel._sfKind;"
                "return {tam: P(4.0, 4.0, false),"
                " gurultulu: P(4.0 - 4.4e-16, 4.0, false),"
                " gercek_eksik: P(3.5, 4.0, false),"
                " akma_alti: P(0.9, 4.0, false),"
                " totolojik: P(4.0, 4.0, true)};"),
        })['evaled']
        assert e['tam'] == 'ok'
        assert e['gurultulu'] == e['tam'], (
            'ekranda aynı görünen sayı iki renkte: %r' % (e,))
        # Ölçüt GEVŞEMEDİ: gerçek eksiklik hâlâ turuncu, akma altı kırmızı,
        # totolojik sayı hâlâ sönük.
        assert e['gercek_eksik'] == 'warn'
        assert e['akma_alti'] == 'err'
        assert e['totolojik'] == 'dim'

    @node_gerekli
    def test_tolerans_muhendislik_farkini_YUTMUYOR(self):
        """Tolerans yalnız ikili gösterim artığını yutar."""
        e = kos({
            'panelId': '__yok__',
            'panelFiles': ['hrma/static/js/panels/structural_panel.js'],
            'evalFn': (
                "var P = window.StructuralPanel._sfKind;"
                "var t = window.StructuralPanel._SF_RENK_BAGIL_TOLERANS;"
                "return {tolerans: t, binde_bir: P(3.996, 4.0, false),"
                " sinir_ustu: P(4.0 - 4.0 * t * 10, 4.0, false)};"),
        })['evaled']
        assert e['tolerans'] <= 1e-6, (
            'tolerans mühendislik farkını yutacak kadar büyük: %r'
            % (e['tolerans'],))
        assert e['binde_bir'] == 'warn'
        assert e['sinir_ustu'] == 'warn'

    @node_gerekli
    def test_risk_kapisi_ile_durum_kapisi_NOT_EVALUATED_da_ayni(self):
        e = kos({
            'panelId': '__yok__',
            'panelFiles': ['hrma/static/js/panels/structural_panel.js'],
            'evalFn': (
                "var S = window.StructuralPanel;"
                "return {durum: S._statusKind('NOT_EVALUATED'),"
                " risk: S._riskKind('NOT_EVALUATED'),"
                " risk_high: S._riskKind('HIGH'),"
                " risk_low: S._riskKind('LOW'),"
                " risk_medium: S._riskKind('MEDIUM')};"),
        })['evaled']
        assert e['durum'] == e['risk'] == 'info'
        assert e['risk_high'] == 'err'
        assert e['risk_low'] == 'ok'
        assert e['risk_medium'] == 'warn'


# ===========================================================================
# P11B4-10 — ayrılma çifti
# ===========================================================================
class TestP11B410AyrilmaCifti:

    def test_dort_alan_da_okunuyor(self):
        s = govde(PANELS / 'joint_panel.js')
        for alan in ('separated_nominal_preload', 'margin_nominal',
                     'separation_load_per_bolt_nominal_N'):
            assert alan in s, '%s hâlâ okunmuyor' % alan
        assert 'sep.margin' in s

    @node_gerekli
    def test_render_nominal_ve_yonetici_sayilari_YAN_YANA_basiyor(self):
        r = kos({
            'panelId': 'joint',
            'panelFiles': ['hrma/static/js/panels/joint_panel.js'],
            'dataInline': {'joint': {
                'separation': {
                    'separated': True, 'separated_nominal_preload': False,
                    'separation_load_per_bolt_N': 12000.0,
                    'separation_load_per_bolt_nominal_N': 16000.0,
                    'margin': 0.87, 'margin_nominal': 1.16,
                },
                'safety_factors': {}, 'loads': {}, 'preload': {},
                'bolt': {}, 'stiffness': {}, 'warnings': [],
                'assumptions': [],
            }},
        })
        assert r['error'] is None, r['error']
        t = r['text']
        assert '12.00' in t and '16.00' in t, (
            'nominal ve yönetici ayrılma yükü YAN YANA basılmalı: %s' % t[:400])
        assert '0.870' in t and '1.160' in t, (
            'nominal ve yönetici marj YAN YANA basılmalı')
        assert 'YES' in t and 'no' in t, (
            'iki ön-yükteki ayrılma bayrağı ayrı ayrı okunmalı')


# ===========================================================================
# P11B4-17 — dağılımı olmayan çıktı
# ===========================================================================
def _uq_yuk():
    return {
        'status': 'ok', 'level': 'fast', 'n_samples': 64,
        'failed_samples': 0, 'seed': 42, 'timing_s': 1.0,
        'outputs': {
            'thrust': {'nominal': 1000.0, 'mean': 1000.0, 'std': 25.0,
                       'p5': 960.0, 'p50': 1000.0, 'p95': 1040.0,
                       'histogram': {'edges': [0, 1, 2], 'counts': [1, 2]}},
            'expansion_ratio': {'nominal': 8.0, 'mean': 8.0, 'std': 0.0,
                                'p5': 8.0, 'p50': 8.0, 'p95': 8.0,
                                'histogram': {'edges': [0, 1], 'counts': [64]}},
        },
    }


@node_gerekli
class TestP11B417DejenereCikti:

    def _render(self):
        return kos({
            'panelId': 'uncertainty',
            'panelFiles': ['hrma/static/js/panels/uncertainty_panel.js'],
            'dataInline': _uq_yuk(),
        })

    def test_sigma_sifir_cikti_BAND_karti_olarak_basilmaz(self):
        r = self._render()
        assert r['error'] is None, r['error']
        assert 'data-uq-degenerate="1"' in r['html'], (
            'σ = 0 çıktısı hâlâ güven bandı kartı olarak basılıyor')
        # Dağılımı OLAN çıktı band kartını korur.
        assert '[960' in r['text'] or '960' in r['text']

    def test_dejenere_cikti_histogram_secicisine_GIRMEZ(self):
        r = kos({
            'panelId': '__yok__',
            'panelFiles': ['hrma/static/js/panels/uncertainty_panel.js'],
            'dataInline': _uq_yuk(),
            'evalFn': ("return window.UncertaintyPanel._selectableKeys(body);"),
        })
        assert r['evaled'] == ['thrust'], (
            'dağılımı olmayan çıktı seçiciye giriyor: %r' % (r['evaled'],))

    def test_kapi_ucun_kendi_alanindan(self):
        s = govde(PANELS / 'uncertainty_panel.js')
        assert re.search(r'function\s+dagilimVar', s)
        assert 'o.std' in s, 'kapı ucun kendi σ alanından okumalı'
