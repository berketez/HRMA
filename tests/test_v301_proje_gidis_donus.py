"""V301/HİBRİT-DIŞA — proje kaydet → yeniden aç → yükle GİDİŞ-DÖNÜŞ bekçisi.

Sınıf (S1, veri kaybı): kayıtlı projedeki bir alan yüklemede kaybolursa
Hesapla gövdesinde o anahtar ya yoktur ya başka değerdedir ve sunucu kendi
varsayılanını uygular — kullanıcı kendi sayısını girdiğini sanır, başka bir
motoru hesaplar. ÖLÇÜLDÜ (28 Eki, kök): ``/api/projects/load`` yanıtı Flask
``jsonify`` ile anahtarları ALFABETİK sıralı döndürür; ``restoreFields``
alanları bu sırayla yazar. Hibritte ``hole_diameter_min/max`` <
``injector_type`` olduğundan önce delik çapları yazılıyor, ardından enjektör
tipinin ``change`` olayı ``updateInjectorParams()`` ile parametre alanlarını
BOŞ yeniden kuruyordu (``element_pairs``, ``impingement_angle``,
``annular_gap``, ``coaxial_inner_flow_fraction`` aynı sınıf).

Bekçi (üç tasarım sayfası: hibrit, katı, sıvı): sayfadaki her düzenlenebilir
form alanına sınır içi ve o anki değerden FARKLI bir değer girilir → Hesapla
gövdesi yakalanır (istek kesilir, hesap koşmaz) → proje sayfanın kendi kayıt
yüküyle kaydedilir → sayfa ``?project=`` ile yeniden açılır → (3 s
sonra) her kayıtlı alan aynı VE Hesapla gövdesi kaydetmeden önceki gövdeyle
aynı. Senaryolar: seçiciler varsayılanda; her seçici bir sonraki seçenekte;
hibritte beş enjektör tipinin her biri.

Sunucu: worktree kökünden ``HRMA_PORT`` (varsayılan 8833) — proje deposu
kalıcı çalışma dizininde (kullanıcının proje dizinine yazılmaz). Tarayıcı:
Playwright headless, 3B kapalı (ORTAK). Kanıt: ``GIDIS_DONUS_KANIT=1`` ile
``docs/scofield/raw/OH/V301/hibrit-disa/olcum/gidis_donus_<senaryo>.json``.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
import urllib.request

import pytest

pytestmark = pytest.mark.kabul_ui

ROOT = pathlib.Path(__file__).resolve().parents[1]
PORT = int(os.environ.get('GIDIS_DONUS_PORT', '8833'))
URL = 'http://127.0.0.1:%d' % PORT
CALISMA = pathlib.Path(os.path.expanduser(
    os.environ.get('GIDIS_DONUS_CALISMA',
                   '~/HRMA-calisma/2026-10-28/HIBRIT-DISA')))
KANIT = ROOT / 'docs' / 'scofield' / 'raw' / 'OH' / 'V301' / 'hibrit-disa' / 'olcum'
# Tarayıcı yolu/bayrakları ve sayfa → Hesapla işlevi KABUL'ün tek tanımından;
# hesap ucu üründen (Fırlatma Sahası aynı eşlemeyle hesaplar).
from tests.test_v301_kabul_ui import KABUL_CHROME_YOLU, ARGS, KABUL_SAYFA_ISLEVI  # noqa: E402
from hrma.analysis.flight_vehicle import CALCULATION_ENDPOINTS  # noqa: E402

#: motor_type -> (sayfa yolu, Hesapla işlevi, hesap ucu)
GD_SAYFA = {mt: (yol, islev, CALCULATION_ENDPOINTS[mt])
            for mt, (yol, islev) in KABUL_SAYFA_ISLEVI.items()}

#: Hibrit enjektör tipleri (``#injector_type`` seçenekleri).
HIBRIT_ENJEKTORLER = ('showerhead', 'pintle', 'swirl', 'impingement', 'coaxial')

#: senaryo adı -> (motor_type, seçici kipi, zorlanan seçiciler)
GD_SENARYOLARI = {
    'hybrid-varsayilan': ('hybrid', 'default', {}),
    'hybrid-sonraki': ('hybrid', 'next', {}),
    'solid-varsayilan': ('solid', 'default', {}),
    'solid-sonraki': ('solid', 'next', {}),
    'liquid-varsayilan': ('liquid', 'default', {}),
    'liquid-sonraki': ('liquid', 'next', {}),
}
for _tip in HIBRIT_ENJEKTORLER:
    GD_SENARYOLARI['hybrid-enj-' + _tip] = ('hybrid', 'default', {'injector_type': _tip})

#: Sayfadaki bütün alanlara değer yazan betik. Proje şeridinin kaydettiği
#: kök kümesiyle aynı dışlama (dinamik paneller, dil seçici); yalnız
#: KULLANICININ yazabildiği alanlar değişir (disabled/readonly değil).
JS_DOLDUR = r"""
(args) => {
  // project_bar.js DYNAMIC_ROOTS ile aynı küme (kaydedilmeyen kökler)
  const DYN = '#analysisDock, #sixDofPanel, #injectorPanel, '
            + '#hrmaProjectBar, #hrmaProjectModal';
  const disari = (el) => (el.closest && el.closest(DYN)) || el.id === 'langSelect';
  const yay = (el) => {
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
  };
  const degisen = [];
  // 1) seçiciler (yapıyı kurarlar): önce zorlananlar, sonra DOM sırası
  Object.keys(args.zorla || {}).forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.value = args.zorla[id]; yay(el); degisen.push(id);
  });
  if (args.kip === 'next') {
    Array.from(document.querySelectorAll('select[id]')).forEach((el) => {
      if (disari(el) || el.disabled || (args.zorla || {})[el.id] !== undefined) return;
      const ops = Array.from(el.options).filter(o => !o.disabled);
      if (ops.length < 2) return;
      const i = ops.findIndex(o => o.value === el.value);
      el.value = ops[(i + 1) % ops.length].value; yay(el); degisen.push(el.id);
    });
  }
  // 2) yazılabilir girdiler (seçicilerin kurduğu alanlar dahil)
  let sira = 0;
  Array.from(document.querySelectorAll('input[id], textarea[id]')).forEach((el) => {
    if (disari(el) || el.disabled || el.readOnly) return;
    const tip = (el.getAttribute('type') || 'text').toLowerCase();
    if (['file', 'button', 'submit', 'radio', 'hidden', 'range', 'color'].includes(tip)) return;
    sira += 1;
    if (tip === 'checkbox') { el.checked = !el.checked; yay(el); degisen.push(el.id); return; }
    if (tip === 'number') {
      const mn = parseFloat(el.getAttribute('min')), mx = parseFloat(el.getAttribute('max'));
      const st = parseFloat(el.getAttribute('step'));
      const simdi = parseFloat(el.value);
      let v;
      if (isFinite(mn) && isFinite(mx) && mx > mn) {
        v = mn + (mx - mn) * 0.37;
        if (isFinite(simdi) && Math.abs(v - simdi) < 1e-12) v = mn + (mx - mn) * 0.61;
      } else if (isFinite(simdi) && simdi !== 0) {
        v = simdi * 1.07;
        if (isFinite(mx) && v > mx) v = simdi * 0.93;
        if (isFinite(mn) && v < mn) v = simdi * 1.03;
      } else {
        v = (isFinite(mn) ? mn : 0) + 0.7 + 0.1 * (sira % 7);
      }
      if (isFinite(st) && st >= 1) {
        v = Math.round(v);
        if (isFinite(simdi) && v === simdi) v += 1;
        if (isFinite(mx) && v > mx) v = Math.max(isFinite(mn) ? mn : v - 2, simdi - 1);
      }
      v = Number(v.toPrecision(4));
      el.value = String(v); yay(el); degisen.push(el.id); return;
    }
    el.value = String(el.value || '') + ' gd' + sira; yay(el); degisen.push(el.id);
  });
  return degisen;
}
"""

#: Kayıt: sayfanın KENDİ kayıt yükü (proje şeridinin apiSave'i ile aynı).
JS_KAYDET = r"""
async (ad) => {
  const r = await fetch('/api/projects/save', {method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name: ad, payload: HRMAProjectBar._buildPayload(ad),
                          overwrite: true})});
  return {durum: r.status, govde: await r.json()};
}
"""


def _hazir_mi(url):
    try:
        with urllib.request.urlopen(url + '/', timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


@pytest.fixture(scope='module')
def sunucu():
    """Port doluysa (kulvarın kendi sunucusu) onu kullanır; boşsa açar."""
    if _hazir_mi(URL):
        yield URL
        return
    depo = CALISMA / ('gd-projeler-%d' % os.getpid())
    if depo.exists():
        shutil.rmtree(depo)
    depo.mkdir(parents=True)
    env = dict(os.environ, HRMA_PORT=str(PORT), BROWSER='echo',
               HRMA_PROJECTS_DIR=str(depo), PYTHONDONTWRITEBYTECODE='1')
    for k in ('OMP_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS',
              'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        env.setdefault(k, '2')
    env.setdefault('MPLBACKEND', 'Agg')
    gunluk = open(CALISMA / ('gd-sunucu-%d.log' % PORT), 'w')
    proc = subprocess.Popen([sys.executable, '-m', 'hrma.run'], cwd=str(ROOT),
                            env=env, stdout=gunluk, stderr=subprocess.STDOUT)
    try:
        bitis = time.time() + 90
        while time.time() < bitis and not _hazir_mi(URL):
            assert proc.poll() is None, 'sunucu açılırken düştü: ' + gunluk.name
            time.sleep(0.5)
        assert _hazir_mi(URL), 'sunucu 90 s içinde yanıt vermedi'
        yield URL
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        gunluk.close()


@pytest.fixture(scope='module')
def tarayici():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=KABUL_CHROME_YOLU, args=ARGS)
        try:
            yield b
        finally:
            b.close()


def _hesapla_govdesi(sayfa, sunucu, mt):
    """Hesapla'ya basılır; hesap isteği KESİLİR (hesap koşmaz), gövde döner.

    Hibrit Hesapla gövdeyi ``getFormData()`` ile kurar ve göndermeden ÖNCE
    sayfa doğrulayıcısından geçirir; bekçinin yazdığı değerler bandın
    dışına düşüp istek hiç çıkmazsa gövde AYNI kurucudan okunur (Hesapla'nın
    ilk satırı) — kaynağı sonuçta yazılır."""
    _, islev, uc = GD_SAYFA[mt]
    yakalanan = []

    def kes(route, request):
        try:
            yakalanan.append(request.post_data_json)
        except Exception:
            yakalanan.append(request.post_data)
        route.abort()
    sayfa.route(sunucu + uc, kes)
    try:
        sayfa.evaluate("(f) => { window.__gdBitti = false; Promise.resolve()"
                       ".then(() => window[f]()).catch(() => {})"
                       ".finally(() => { window.__gdBitti = true; }); }", islev)
        bitis = time.time() + 8
        while not yakalanan and time.time() < bitis:
            sayfa.wait_for_timeout(200)
        sayfa.wait_for_function('() => window.__gdBitti === true', timeout=30000)
    finally:
        sayfa.unroute(sunucu + uc)
    if yakalanan:
        return yakalanan[0], 'hesapla'
    if mt == 'hybrid':
        return sayfa.evaluate('() => JSON.parse(JSON.stringify(getFormData()))'), \
            'getFormData'
    return None, None


def _sayfa_ac(tarayici, sunucu, mt, proje=None):
    yol = GD_SAYFA[mt][0]
    sayfa = tarayici.new_page(viewport={'width': 1440, 'height': 900})
    sayfa.set_default_timeout(30000)
    sayfa.on('dialog', lambda d: d.dismiss())
    sayfa.goto(sunucu + yol + ('?project=' + urllib.request.quote(proje) if proje else ''))
    sayfa.wait_for_load_state('networkidle')
    sayfa.wait_for_function('window.HRMAProjectBar && HRMAProjectBar._state')
    if proje:
        sayfa.wait_for_function('HRMAProjectBar._state.name === ' + json.dumps(proje))
    return sayfa


def _normal(govde):
    """Köken damgası kayıttan sonra 'project_file' olur (beyanlı, doğru):
    gövde karşılaştırmasında 'user' ile eşlenir. Başka hiçbir şey değişmez."""
    if isinstance(govde, dict):
        out = {}
        for k, v in govde.items():
            if (k == 'source' or k.endswith('_source')) and v == 'project_file':
                v = 'user'
            out[k] = _normal(v)
        return out
    if isinstance(govde, list):
        return [_normal(x) for x in govde]
    return govde


def gidis_donus(tarayici, sunucu, senaryo):
    """Bir senaryonun gidiş-dönüşü; kayıp/sapma listeleri döner."""
    mt, kip, zorla = GD_SENARYOLARI[senaryo]
    ad = 'gd-' + senaryo
    sayfa = _sayfa_ac(tarayici, sunucu, mt)
    try:
        sayfa.wait_for_timeout(800)
        degisen = sayfa.evaluate(JS_DOLDUR, {'kip': kip, 'zorla': zorla})
        sayfa.wait_for_timeout(1200)
        govde_once, kaynak_once = _hesapla_govdesi(sayfa, sunucu, mt)
        sayfa.wait_for_timeout(500)
        kayit = sayfa.evaluate(JS_KAYDET, ad)
        alan_once = sayfa.evaluate('(a) => HRMAProjectBar._buildPayload(a).inputs', ad)
    finally:
        sayfa.close()
    assert kayit['durum'] == 200, kayit
    sayfa = _sayfa_ac(tarayici, sunucu, mt, ad)
    try:
        alan_hemen = sayfa.evaluate('(a) => HRMAProjectBar._buildPayload(a).inputs', ad)
        sayfa.wait_for_timeout(3000)
        alan_sonra = sayfa.evaluate('(a) => HRMAProjectBar._buildPayload(a).inputs', ad)
        govde_sonra, kaynak_sonra = _hesapla_govdesi(sayfa, sunucu, mt)
    finally:
        sayfa.close()
    f0, f1, f3 = (alan_once.get('fields') or {}), (alan_hemen.get('fields') or {}), \
        (alan_sonra.get('fields') or {})
    alan_kaybi = {k: {'kayit': f0[k], 'hemen': f1.get(k, '<yok>'),
                      '3_s': f3.get(k, '<yok>')}
                  for k in sorted(f0) if f0[k] != f1.get(k, '<yok>')
                  or f0[k] != f3.get(k, '<yok>')}
    fazla_alan = sorted(set(f3) - set(f0))
    g0, g1 = _normal(govde_once or {}), _normal(govde_sonra or {})
    govde_farki = {k: {'once': g0.get(k, '<yok>'), 'sonra': g1.get(k, '<yok>')}
                   for k in sorted(set(g0) | set(g1)) if g0.get(k, '<yok>') != g1.get(k, '<yok>')}
    diger = {k: {'once': alan_once.get(k), 'sonra': alan_sonra.get(k)}
             for k in ('dynamic', 'ui_state', 'dock_overrides')
             if alan_once.get(k) != alan_sonra.get(k)}
    sonuc = {'senaryo': senaryo, 'motor_type': mt, 'degisen_alan_sayisi': len(degisen),
             'kayitli_alan_sayisi': len(f0), 'govde_anahtar_sayisi': len(g0),
             'govde_yakalandi': [govde_once is not None, govde_sonra is not None],
             'govde_kaynagi': [kaynak_once, kaynak_sonra],
             'alan_kaybi': alan_kaybi, 'fazla_alan': fazla_alan,
             'govde_farki': govde_farki, 'diger_farki': diger}
    if os.environ.get('GIDIS_DONUS_KANIT') == '1':
        # Kanıt dizinine YAZMA kanit_cikti kapısından (docs'suz yayın dalında
        # kapı dışı okuma 0 olmalı; T-ÇAPA-C2 deseni, test_v301_kabul.py).
        from tests.support.kanit import kanit_cikti
        ek = os.environ.get('GIDIS_DONUS_EK', '')
        hedef = kanit_cikti(KANIT / ('gidis_donus_%s%s.json' % (senaryo, ek)))
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_text(
            json.dumps(dict(sonuc, govde_once=govde_once, alanlar=f0),
                       indent=1, ensure_ascii=False, default=str), encoding='utf-8')
    return sonuc


@pytest.mark.parametrize('senaryo', sorted(GD_SENARYOLARI))
def test_proje_gidis_donus_alan_ve_govde_ayni(tarayici, sunucu, senaryo):
    s = gidis_donus(tarayici, sunucu, senaryo)
    assert all(s['govde_yakalandi']), ('Hesapla gövdesi yakalanamadı', s['govde_yakalandi'])
    assert s['degisen_alan_sayisi'] >= 10, ('bekçi alanlara yazamadı', s['degisen_alan_sayisi'])
    assert not s['alan_kaybi'], ('S1 veri kaybı: kayıtlı alan yüklemede değişti',
                                 s['alan_kaybi'])
    assert not s['govde_farki'], ('S1: Hesapla gövdesi kayıttan önce ve yüklemeden '
                                  'sonra farklı', s['govde_farki'])
    assert not s['diger_farki'], s['diger_farki']
