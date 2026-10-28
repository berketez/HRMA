"""V301/KABUL — baştan sona kabul testi (YAYIN KAPISI).

Berke (26 Eki 2026): **"bu test geçmeden yayın yok."**

Neden: 3.0.0'ın 10 haftalık doğrulaması kullanıcının gördüğü hataları
kaçırdı; testler kodun BUGÜNKÜ çıktısını kilitledi, kullanıcı yolculuğunu
ve paneller arası tutarlılığı ölçmedi (hafıza:
feedback-yayin-kapilari-v301). Bu dosya o yolculuğu üç örnek motor
(katı KNDX, sıvı LOX/RP-1, hibrit N2O/HTPB) için baştan sona yürür:

  K1  ana hesap: sayfanın gönderdiği yükle → 200, kritik yok, ret yok,
      beyansız ikame yok;
  K2  arayüzün o motor için çağırdığı panel uçları (güverte + Analiz
      Merkezi; yükler panellerin KENDİ JS kodundan) → 200, ret yok,
      kritik yok, panel isteği gönderebiliyor;
  K3  paneller arası aynı sayı (ana sonuç ⟷ panel ⟷ PDF ⟷ CAD);
  K4  dışa aktarım (PDF, STEP, STL, DXF, .eng, paket) → 200, boş değil,
      CAD sınır kutusu ⟷ yanıttaki ölçüler;
  K5  belirlenimcilik (aynı istek → bit-aynı) + önbellek bağımsızlığı
      (boş kullanıcı veri dizini → bit-aynı).

Kural (brif): xfail / skip / gevşek tolerans YOK. Kırmızı = ürün hatası;
düzeltmesi başka kulvarın. Her kırmızı RAPOR'da yeniden üretimi ve olası
sahibiyle: docs/scofield/raw/OH/V301/kabul/RAPOR.md.

Toleranslar (her karşılaştırmada beyanlı):
  * BIT — bit-aynı (belirlenimcilik, önbellek bağımsızlığı);
  * REL9 — bağıl 1e-9 (aynı büyüklüğün iki JSON yayımı);
  * YARIM_BASAMAK — yayımlanan metin yuvarlamasının yarım basamağı (PDF);
  * CAD — STEP/STL/DXF tessellation/biçim yuvarlaması: bağıl 1e-6.
"""

from __future__ import annotations

import json
import math
import os
import pathlib
import subprocess
import sys

import pytest

from tests.support import kabul

MOTORLAR = kabul.MOTORLAR

#: Aynı büyüklüğün iki JSON yayımı arasındaki tolerans (brif: bağıl 1e-9).
REL9 = 1e-9
#: CAD dosyası okuma toleransı (STEP B-spline/STL float32 yuvarlaması).
CAD_REL = 1e-6


# ---------------------------------------------------------------------------
# Fikstürler — her motor için ana hesap BİR kez (pahalı: hibrit ~5-10 s)
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    return app.test_client()


_HESAP = {}


def hesap(client, mt):
    """(yük, durum, gövde) — sayfanın Hesapla'da gönderdiği yükle."""
    if mt not in _HESAP:
        yuk = kabul.sayfa_yuku(mt)
        durum, govde, _ham, _tur = kabul.post(client, kabul.hesap_ucu(mt), yuk)
        _HESAP[mt] = (yuk, durum, govde)
    return _HESAP[mt]


def basarili_hesap(client, mt):
    yuk, durum, govde = hesap(client, mt)
    neden = kabul.ret_nedeni(durum, govde)
    assert neden is None, (
        f'{mt}: ana hesap reddedildi ({neden}) — bu düğüm ana hesabın '
        'sonucunu kullanır, önce K1 düzelmeli')
    return yuk, govde


@pytest.fixture(scope='module')
def malzeme_katalogu(client):
    resp = client.get('/api/materials', headers=kabul.headers())
    assert resp.status_code == 200
    return resp.get_json()


# ===========================================================================
# K1 — ana hesap
# ===========================================================================
@pytest.mark.parametrize('mt', MOTORLAR)
def test_k1_ana_hesap_200_ret_yok(client, mt):
    """Sayfanın yüküyle hesap ucu 200 döner, gövde ret işareti taşımaz."""
    _yuk, durum, govde = hesap(client, mt)
    assert kabul.ret_nedeni(durum, govde) is None, (
        f'{kabul.hesap_ucu(mt)}: {kabul.ret_nedeni(durum, govde)}')


@pytest.mark.parametrize('mt', MOTORLAR)
def test_k1_ana_hesap_kritik_bayrak_yok(client, mt):
    """Örnek motor kritik bayraksız açılır (kapı 2: 'model sınırı' kabul yok)."""
    _yuk, govde = basarili_hesap(client, mt)
    krit = kabul.kritikler(govde)
    assert not krit, (
        f'{mt} örneği {len(krit)} KRİTİK bayrakla açılıyor:\n'
        + '\n'.join('  %s %s @ %s' % (k['code'], json.dumps(k['params'],
                                                              ensure_ascii=False),
                                       k['paths'][0]) for k in krit))


@pytest.mark.parametrize('mt', MOTORLAR)
def test_k1_beyansiz_ikame_yok(client, mt):
    """Gönderilen sayı alanı yanıtta aynı adla başka değerle duruyorsa bu
    ``inputs_not_used``/``defaults_applied``/``unwired_inputs``/
    ``input_warnings`` ya da ``<alan>_basis/_source`` ile ADIYLA beyanlı."""
    yuk, govde = basarili_hesap(client, mt)
    ikame = kabul.sessiz_ikameler(mt, yuk, govde)
    assert not ikame, (
        f'{mt}: beyansız ikame (gönderilen ⟷ yanıttaki aynı ad): '
        + json.dumps(ikame, ensure_ascii=False))


# ===========================================================================
# K2 — arayüzün çağırdığı panel uçları (güverte + Analiz Merkezi)
# ===========================================================================
_PANEL = {}


def panel_sonuclari(client, mt, katalog):
    """Her uygulanabilir panel: (spec özeti, durum, gövde) listesi."""
    if mt in _PANEL:
        return _PANEL[mt]
    _yuk, govde = basarili_hesap(client, mt)
    harness = kabul.guverte_yukleri(mt, govde, katalog)
    satirlar = []
    for sp in harness['specs']:
        if not sp.get('applies', True):
            satirlar.append({'spec': sp, 'durum': None, 'govde': None,
                             'gonderilmez': 'uygulanmaz'})
            continue
        if sp.get('own_controls_only'):
            satirlar.append({'spec': sp, 'durum': None, 'govde': None,
                             'gonderilmez': 'kendi_denetimi'})
            continue
        engel = []
        if sp.get('missing'):
            engel.append('zorunlu alan boş: ' + ', '.join(sp['missing']))
        if sp.get('blocked'):
            engel.append('çözücü malzemesi seçici listesinde yok: '
                         + json.dumps(sp['blocked'], ensure_ascii=False))
        if sp.get('errors'):
            engel.append('panel JS hatası: ' + '; '.join(sp['errors']))
        if engel:
            satirlar.append({'spec': sp, 'durum': None, 'govde': None,
                             'gonderilmez': ' | '.join(engel)})
            continue
        durum, cevap, _ham, _tur = kabul.post(client, sp['endpoint'],
                                              sp['payload'])
        satirlar.append({'spec': sp, 'durum': durum, 'govde': cevap,
                         'gonderilmez': None})
    _PANEL[mt] = {'yukleme': harness['yukleme'], 'satirlar': satirlar}
    _kanit_yaz(mt, 'k2_paneller', _PANEL[mt])
    return _PANEL[mt]


def _kanit_yaz(mt, ad, veri):
    """KABUL_KANIT=1 iken ölçümü kanıt dizinine yaz (yalnız istenince)."""
    if os.environ.get('KABUL_KANIT') != '1':
        return

    def kisa(s):
        sp = s['spec']
        g = s['govde']
        return {'kind': sp.get('kind'), 'id': sp.get('id'),
                'endpoint': sp.get('endpoint'),
                'payload': sp.get('payload'),
                'suggested': sp.get('suggested'),
                'defaulted': sp.get('defaulted'),
                'fallback_sent': sp.get('fallback_sent'),
                'durum': s['durum'], 'gonderilmez': s['gonderilmez'],
                'ret': kabul.ret_nedeni(s['durum'], g) if s['durum'] else None,
                'kritik': kabul.kritikler(g) if isinstance(g, (dict, list)) else []}
    if ad == 'k2_paneller':
        veri = {'yukleme': veri['yukleme'],
                'satirlar': [kisa(s) for s in veri['satirlar']]}
    # T-ÇAPA-C2 (27 Eki): kanıt dizinine YAZMA kanit_cikti kapısından (kanıt
    # tarayıcısı: docs'suz yayın dalında kapı dışı G/Ç 0 olmalı).
    from tests.support.kanit import kanit_cikti
    hedef = kanit_cikti(kabul.KANIT / 'olcum' / f'{mt}_{ad}.json')
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(
        json.dumps(veri, indent=1, ensure_ascii=False, default=str),
        encoding='utf-8')


@pytest.mark.parametrize('mt', MOTORLAR)
def test_k2_panel_js_yuklenir(client, malzeme_katalogu, mt):
    """Sayfanın her script'i (şablon sırasıyla) hatasız yüklenir."""
    p = panel_sonuclari(client, mt, malzeme_katalogu)
    hatali = {f: d for f, d in p['yukleme'].items() if d != 'ok'}
    assert not hatali, f'{mt}: panel scriptleri yüklenemedi: {hatali}'


@pytest.mark.parametrize('mt', MOTORLAR)
def test_k2_paneller_istek_gonderebilir(client, malzeme_katalogu, mt):
    """Uygulanabilir her panel, örnek motorun sonucuyla isteği KURABİLİR
    (zorunlu alan boş / seçici çözücü malzemesini tanımıyor / JS hatası →
    arayüz istek göndermez ve kullanıcı paneli kullanamaz)."""
    p = panel_sonuclari(client, mt, malzeme_katalogu)
    kotu = ['%s %s (%s): %s' % (s['spec']['kind'], s['spec']['id'],
                                 s['spec']['endpoint'], s['gonderilmez'])
            for s in p['satirlar']
            if s['gonderilmez'] not in (None, 'uygulanmaz', 'kendi_denetimi')]
    assert not kotu, f'{mt}: paneller istek kuramıyor:\n  ' + '\n  '.join(kotu)


@pytest.mark.parametrize('mt', MOTORLAR)
def test_k2_paneller_200_ret_yok(client, malzeme_katalogu, mt):
    p = panel_sonuclari(client, mt, malzeme_katalogu)
    kotu = []
    for s in p['satirlar']:
        if s['durum'] is None:
            continue
        neden = kabul.ret_nedeni(s['durum'], s['govde'])
        if neden:
            kotu.append('%s %s %s → %s' % (s['spec']['kind'], s['spec']['id'],
                                           s['spec']['endpoint'], neden))
    assert not kotu, f'{mt}: panel uçları reddediyor:\n  ' + '\n  '.join(kotu)


@pytest.mark.parametrize('mt', MOTORLAR)
def test_k2_paneller_kritik_yok(client, malzeme_katalogu, mt):
    p = panel_sonuclari(client, mt, malzeme_katalogu)
    kotu = []
    for s in p['satirlar']:
        if s['durum'] != 200 or not isinstance(s['govde'], (dict, list)):
            continue
        for k in kabul.kritikler(s['govde']):
            kotu.append('%s %s → %s %s' % (
                s['spec']['id'], s['spec']['endpoint'], k['code'],
                json.dumps(k['params'], ensure_ascii=False)[:200]))
    assert not kotu, f'{mt}: panel yanıtlarında KRİTİK:\n  ' + '\n  '.join(kotu)


@pytest.mark.parametrize('mt', MOTORLAR)
def test_k2_merkez_secici_sessiz_varsayilan_yok(client, malzeme_katalogu, mt):
    """Analiz Merkezi seçicisi çözücünün değerini listede bulamazsa alanı
    DEĞİŞTİRMEZ ve istek panel varsayılanıyla GİDER (analysis_center.js
    applySuggestions; yalnız console.warn). Bu sessiz ikamedir."""
    p = panel_sonuclari(client, mt, malzeme_katalogu)
    kotu = ['%s: %s' % (s['spec']['id'], json.dumps(s['spec']['fallback_sent'],
                                                     ensure_ascii=False))
            for s in p['satirlar'] if s['spec'].get('fallback_sent')]
    assert not kotu, (f'{mt}: merkez seçicisi çözücü değerini düşürüp '
                      'varsayılanla gönderiyor: ' + '; '.join(kotu))


# ===========================================================================
# K4 — dışa aktarım
# ===========================================================================
_IHRAC = {}

#: ad -> beklenen içerik türü parçası
IHRAC_TURU = {'dxf': ('dxf', 'octet', 'text/plain', 'application/dxf'),
              'step': ('zip', 'step', 'octet'),
              'paket': ('zip',), 'cizim_pdf': ('pdf',), 'rapor_pdf': ('pdf',),
              'stl_step_zip': ('zip',), 'stl_zip': ('zip',),
              'eng': ('json',)}


def ihrac(client, mt, ad):
    anahtar = (mt, ad)
    if anahtar not in _IHRAC:
        yuk, govde = basarili_hesap(client, mt)
        yukler = kabul.ihrac_yukleri(mt, govde, yuk)
        uc, gov = yukler[ad]
        durum, js, ham, tur = kabul.post(client, uc, gov)
        _IHRAC[anahtar] = {'uc': uc, 'durum': durum, 'js': js, 'ham': ham,
                           'tur': tur}
    return _IHRAC[anahtar]


def _ihrac_parametreleri():
    out = []
    for mt in MOTORLAR:
        for ad in ('dxf', 'step', 'paket', 'cizim_pdf'):
            out.append((mt, ad))
        out.append((mt, {'hybrid': 'stl_zip'}.get(mt, 'stl_step_zip')))
        out.append((mt, 'rapor_pdf'))
    out.append(('solid', 'eng'))
    out.append(('hybrid', 'eng'))
    out.append(('liquid', 'eng'))      # V301/HİBRİT-DIŞA kalem 2
    return out


@pytest.mark.parametrize('mt,ad', _ihrac_parametreleri())
def test_k4_disa_aktarim_200_bos_degil(client, mt, ad):
    r = ihrac(client, mt, ad)
    assert r['durum'] == 200, (
        f'{mt}/{ad} {r["uc"]} → HTTP {r["durum"]}: '
        + (json.dumps(r['js'], ensure_ascii=False)[:600] if r['js'] is not None
           else r['ham'][:300].decode('utf-8', 'replace')))
    assert len(r['ham']) > 200, f'{mt}/{ad}: gövde {len(r["ham"])} bayt'
    if ad == 'eng':
        # /api/export-eng → 'content'; /api/export-openrocket (hibrit) →
        # 'eng_file_content' (app.py yanıt şemaları).
        icerik = ((r['js'] or {}).get('content')
                  or (r['js'] or {}).get('eng_file_content') or '')
        assert kabul.ret_nedeni(r['durum'], r['js']) is None, r['js']
        satir = [x for x in icerik.splitlines() if x.strip() and not x.startswith(';')]
        assert len(satir) > 3, f'{mt}/eng: .eng içeriği boş/eksik: {icerik[:300]!r}'
    assert any(p in r['tur'].lower() for p in IHRAC_TURU[ad]), (
        f'{mt}/{ad}: içerik türü {r["tur"]!r}')
    if 'zip' in r['tur'].lower():
        icerik = kabul.zip_icerigi(r['ham'])
        bos = [n for n, b in icerik.items() if len(b) == 0]
        assert icerik and not bos, f'{mt}/{ad}: boş zip girdileri {bos}'
        basarisiz = [n for n in icerik if 'FAILED' in n.upper()]
        manifest = [b for n, b in icerik.items() if 'manifest' in n.lower()]
        for m in manifest:
            metin = m.decode('utf-8', 'replace')
            assert '[FAILED]' not in metin, (
                f'{mt}/{ad}: paket MANIFEST başarısız kalem yazıyor: '
                + '\n'.join(s for s in metin.splitlines() if 'FAILED' in s))
        assert not basarisiz, f'{mt}/{ad}: {basarisiz}'


@pytest.mark.parametrize('mt', MOTORLAR)
def test_k4_paket_eng_dugmeyle_ayni(client, mt):
    """V301/HİBRİT-DIŞA (kalem 2): komple paketin .eng'i [OK] ve .eng
    düğmesinin dosyasıyla AYNI (yorum satırları hariç: başlık + itki
    eğrisi). ÖLÇÜLDÜ (hibrit-disa/olcum/sivi_paket_once.json): sıvı paket
    '[FAILED] .eng: propellant_mass' yazıyordu, düğme 200 veriyordu."""
    paket = ihrac(client, mt, 'paket')
    assert paket['durum'] == 200, paket['js']
    icerik = kabul.zip_icerigi(paket['ham'])
    eng = [b.decode('utf-8', 'replace') for n, b in icerik.items() if n.endswith('.eng')]
    manifest = [b.decode('utf-8', 'replace') for n, b in icerik.items() if 'manifest' in n.lower()]
    assert manifest and '[OK]     OpenRocket .eng' in manifest[0], manifest[:1]
    assert len(eng) == 1, sorted(icerik)
    dugme = ihrac(client, mt, 'eng')
    assert dugme['durum'] == 200, dugme['js']
    d_icerik = ((dugme['js'] or {}).get('content')
                or (dugme['js'] or {}).get('eng_file_content') or '')

    def veri(t):
        return [x.strip() for x in t.splitlines() if x.strip() and not x.startswith(';')]
    assert veri(eng[0])[1:] == veri(d_icerik)[1:], (
        f'{mt}: paket .eng itki eğrisi düğmeninkinden farklı')
    p_bas, d_bas = veri(eng[0])[0].split(), veri(d_icerik)[0].split()
    # Başlık: ad, çap, boy, gecikme, itici kütlesi, toplam kütle, üretici —
    # ad dışında hepsi aynı (paket dosya adını geometri bloğundan alır).
    assert p_bas[1:] == d_bas[1:], (p_bas, d_bas)


# ===========================================================================
# K5 — belirlenimcilik + önbellek bağımsızlığı
# ===========================================================================
@pytest.mark.parametrize('mt', MOTORLAR)
def test_k5_ayni_istek_bit_ayni(client, mt):
    """Aynı yük iki kez → kanonik JSON BIT-aynı (oynak alan listesi:
    kabul.OYNAK_ANAHTARLAR; liste dışı her fark bulgudur)."""
    yuk, govde = basarili_hesap(client, mt)
    durum2, govde2, _h, _t = kabul.post(client, kabul.hesap_ucu(mt), yuk)
    assert durum2 == 200
    a, b = kabul.kanonik(govde), kabul.kanonik(govde2)
    farklar = kabul.ilk_farklar(a, b)
    assert not farklar, f'{mt}: aynı istek farklı sonuç:\n  ' + '\n  '.join(farklar)


ONBELLEKSIZ_BETIK = r"""
import json, os, sys
sys.path.insert(0, os.environ['KABUL_KOK'])
from tests.support import kabul
from hrma.app import app
mt = sys.argv[1]
c = app.test_client()
yuk = kabul.sayfa_yuku(mt)
durum, govde, _h, _t = kabul.post(c, kabul.hesap_ucu(mt), yuk)
sys.stdout.write('\n@@KABUL@@' + json.dumps({'durum': durum, 'govde': govde}))
"""


def _soguk_hesap(mt, kullanici_dizini):
    """Ayrı süreçte (soğuk: süreç içi bellek yok) verilen kullanıcı veri
    dizini ile hesap. ``HRMA_USER_DATA_DIR`` ürünün kendi test kancasıdır
    (hrma/__init__.py ``_resolve_user_data_dir``; offline_store aynı
    sözleşme): itici önbelleği ``<dizin>/propellant_cache`` +
    ``propellant_cache.json`` orada aranır."""
    env = dict(os.environ)
    env['HRMA_USER_DATA_DIR'] = str(kullanici_dizini)
    env['KABUL_KOK'] = str(kabul.ROOT)
    for k in ('OMP_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS',
              'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        env.setdefault(k, '2')
    env.setdefault('MPLBACKEND', 'Agg')
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    proc = subprocess.run([sys.executable, '-c', ONBELLEKSIZ_BETIK, mt],
                          capture_output=True, text=True, timeout=240,
                          cwd=str(kabul.ROOT), env=env)
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(proc.stdout.split('\n@@KABUL@@', 1)[1])


@pytest.mark.parametrize('mt', MOTORLAR)
def test_k5_onbelleksiz_hesap_onbellekliyle_bit_ayni(client, mt):
    """Boş kullanıcı veri dizini (itici önbelleği YOK, soğuk süreç) ile
    hesap = bu süreçteki (önbellekli) hesap, BIT-aynı. CI ve paket
    önbelleksiz koşar: fark varsa kullanıcı ile CI farklı sayı görür."""
    _yuk, govde = basarili_hesap(client, mt)
    bos = kabul.CALISMA / ('onbelleksiz-%d-%s' % (os.getpid(), mt))
    if bos.exists():
        for f in sorted(bos.rglob('*'), reverse=True):
            f.unlink() if f.is_file() else f.rmdir()
    bos.mkdir(parents=True)
    soguk = _soguk_hesap(mt, bos)
    assert soguk['durum'] == 200, soguk['govde']
    farklar = kabul.ilk_farklar(kabul.kanonik(govde),
                                kabul.kanonik(soguk['govde']))
    yazilan = sorted(str(p.relative_to(bos)) for p in bos.rglob('*'))
    assert not farklar, (
        f'{mt}: önbelleksiz soğuk hesap ⟷ önbellekli hesap FARKLI '
        f'(boş dizine yazılanlar: {yazilan[:10]}):\n  ' + '\n  '.join(farklar))


# ===========================================================================
# K3 — paneller arası aynı sayı
# ===========================================================================
def _arac(client, mt):
    """Sayfanın hesap sonrası yayımladığı uçuş aracı (flight_handoff.js
    publish: source='results', motor_name = #motor_name)."""
    yuk, govde = basarili_hesap(client, mt)
    durum, js, _h, _t = kabul.post(client, '/api/flight-vehicle', {
        'source': 'results', 'motor_type': mt,
        'motor_name': yuk.get('motor_name'), 'results': govde})
    assert durum == 200, js
    return js['vehicle']


def _json_satirlari(mt, s, v):
    """Ana sonuç ⟷ tasarım özeti ⟷ motor_geometry ⟷ uçuş aracı (REL9)."""
    S = kabul.satir
    g = s.get('motor_geometry') or {}
    ds = s.get('design_summary') or {}
    kd = ds.get('key_dimensions') or {}
    ms = ds.get('masses') or {}
    if mt == 'solid':
        return [
            S('ortalama itki [N]', 'ana.average_thrust', s.get('average_thrust')),
            S('ortalama itki [N]', 'motor_geometry.thrust', g.get('thrust')),
            S('ortalama itki [N]', 'uçuş_aracı.thrust', v.get('thrust')),
            S('Isp deniz [s]', 'ana.specific_impulse', s.get('specific_impulse')),
            S('Isp deniz [s]', 'ana.isp_sea_level', s.get('isp_sea_level')),
            S('Isp deniz [s]', 'motor_geometry.isp', g.get('isp')),
            S('Pc [bar]', 'ana.chamber_pressure', s.get('chamber_pressure')),
            S('Pc [bar]', 'motor_geometry.chamber_pressure', g.get('chamber_pressure')),
            S('yanma süresi [s]', 'ana.burn_time', s.get('burn_time')),
            S('yanma süresi [s]', 'motor_geometry.burn_time', g.get('burn_time')),
            S('yanma süresi [s]', 'uçuş_aracı.burn_time', v.get('burn_time')),
            S('toplam impuls [N·s]', 'ana.total_impulse', s.get('total_impulse')),
            S('toplam impuls [N·s]', 'motor_geometry.total_impulse', g.get('total_impulse')),
            S('boğaz çapı [mm]', 'ana.throat_diameter', s.get('throat_diameter')),
            S('boğaz çapı [mm]', 'motor_geometry.throat_diameter×1000',
              (g.get('throat_diameter') or 0) * 1000),
            S('boğaz çapı [mm]', 'design_summary.key_dimensions.nozzle_throat_mm', kd.get('nozzle_throat_mm')),
            S('çıkış çapı [mm]', 'ana.exit_diameter', s.get('exit_diameter')),
            S('çıkış çapı [mm]', 'motor_geometry.exit_diameter×1000',
              (g.get('exit_diameter') or 0) * 1000),
            S('çıkış çapı [mm]', 'design_summary.key_dimensions.nozzle_exit_mm', kd.get('nozzle_exit_mm')),
            # V301/T-ÇAPA-D: FİZİK-2 kalem 6 (fe72e04b5) uçuş aracı zarfını
            # CAD'in tek tanımından kurar — boy KAPAKLI (key_dimensions
            # total_length_with_closure_mm), çap kasa ile ÇİZİLEN lüle dış
            # zarfının büyüğü (STEP ile K3 CAD düğümünde ölçülür). Kapaksız
            # boy ve kasa dış çapı ayrı büyüklüklerdir.
            S('toplam boy [mm]', 'design_summary.key_dimensions.total_length_mm', kd.get('total_length_mm')),
            S('kapaklı toplam boy [mm]', 'design_summary.key_dimensions.total_length_with_closure_mm',
              kd.get('total_length_with_closure_mm')),
            S('kapaklı toplam boy [mm]', 'uçuş_aracı.engine_length_m×1000', (v.get('engine_length_m') or 0) * 1000),
            S('kasa dış çapı [mm]', 'design_summary.key_dimensions.motor_outer_diameter_mm', kd.get('motor_outer_diameter_mm')),
            S('zarf dış çapı [mm]', 'uçuş_aracı.engine_od_m×1000', (v.get('engine_od_m') or 0) * 1000),
            S('itici kütlesi [kg]', 'ana.propellant_mass', s.get('propellant_mass')),
            S('itici kütlesi [kg]', 'design_summary.masses.propellant_mass_kg', ms.get('propellant_mass_kg')),
            S('itici kütlesi [kg]', 'motor_geometry.propellant_mass_total', g.get('propellant_mass_total')),
            S('itici kütlesi [kg]', 'uçuş_aracı.propellant_mass', v.get('propellant_mass')),
            S('kuru kütle [kg]', 'design_summary.masses.dry_mass_kg', ms.get('dry_mass_kg')),
            S('kuru kütle [kg]', 'uçuş_aracı.engine_inert_mass', v.get('engine_inert_mass')),
        ]
    if mt == 'liquid':
        return [
            S('itki [N]', 'ana.thrust', s.get('thrust')),
            S('itki [N]', 'motor_geometry.thrust', g.get('thrust')),
            S('itki [N]', 'uçuş_aracı.thrust', v.get('thrust')),
            S('Isp deniz [s]', 'ana.isp_sea_level', s.get('isp_sea_level')),
            S('Isp deniz [s]', 'motor_geometry.isp', g.get('isp')),
            S('Pc [bar]', 'ana.chamber_pressure', s.get('chamber_pressure')),
            S('Pc [bar]', 'motor_geometry.chamber_pressure', g.get('chamber_pressure')),
            S('kütle akışı [kg/s]', 'ana.total_mass_flow', s.get('total_mass_flow')),
            S('kütle akışı [kg/s]', 'ana.fuel_flow+oxidizer_flow',
              (s.get('fuel_flow') or 0) + (s.get('oxidizer_flow') or 0)),
            S('boğaz çapı [mm]', 'ana.throat_diameter_mm', s.get('throat_diameter_mm')),
            S('boğaz çapı [mm]', 'ana.throat_diameter×1000', (s.get('throat_diameter') or 0) * 1000),
            S('boğaz çapı [mm]', 'motor_geometry.throat_diameter×1000', (g.get('throat_diameter') or 0) * 1000),
            S('boğaz çapı [mm]', 'design_summary.key_dimensions.nozzle_throat_mm', kd.get('nozzle_throat_mm')),
            S('çıkış çapı [mm]', 'ana.exit_diameter_mm', s.get('exit_diameter_mm')),
            S('çıkış çapı [mm]', 'motor_geometry.exit_diameter×1000', (g.get('exit_diameter') or 0) * 1000),
            S('çıkış çapı [mm]', 'design_summary.key_dimensions.nozzle_exit_mm', kd.get('nozzle_exit_mm')),
            # V301/T-ÇAPA-D: uçuş aracı boyu kapaklı (FİZİK-2 kalem 6).
            S('kapaklı toplam boy [mm]', 'design_summary.key_dimensions.overall_length_with_closure_mm',
              kd.get('overall_length_with_closure_mm')),
            S('kapaklı toplam boy [mm]', 'uçuş_aracı.engine_length_m×1000', (v.get('engine_length_m') or 0) * 1000),
            S('toplam boy [mm]', 'design_summary.key_dimensions.overall_length_mm', kd.get('overall_length_mm')),
            S('toplam boy [mm]', 'kd.chamber+convergent+nozzle_length',
              (kd.get('chamber_length_mm') or 0) + (kd.get('convergent_length_mm') or 0)
              + (kd.get('nozzle_length_mm') or 0)),
            # V301/HİBRİT-DIŞA (kalem 3, ornek DEVİR 4): uçuş aracının
            # engine_inert_mass'ı sıvıda "motor kuru kütlesi" DEĞİL, UÇAN ATIL
            # kütledir (motor kuru + tank kuru yapısı + yüklenen − nominal
            # yedek itici; flight_vehicle._liquid_inert_mass, künye
            # engine_inert_mass_note; arayüz etiketi "Flying inert mass").
            # Eski satır iki farklı büyüklüğü aynı adla eşliyordu (76,77 ⟷
            # 156,31). Referans sonucun KENDİ alanlarından toplanır.
            S('motor kuru kütlesi [kg]', 'design_summary.masses.engine_mass_kg', ms.get('engine_mass_kg')),
            S('motor kuru kütlesi [kg]', 'uçuş_aracı.engine_inert_mass_note «engine dry mass»',
              kabul.not_kutlesi(v.get('engine_inert_mass_note'), 'engine dry mass'),
              sinif='YARIM', ond=3),
            S('uçan atıl kütle [kg]', 'engine_mass_kg + tank kuru yapısı + (yüklenen − nominal)',
              kabul.sivi_ucan_atil(s)),
            S('uçan atıl kütle [kg]', 'uçuş_aracı.engine_inert_mass', v.get('engine_inert_mass')),
        ]
    m = s.get('motor') or {}
    wa = (m.get('structural_analysis') or {}).get('weight_analysis') or {}
    return [
        S('itki [N]', 'motor.thrust', m.get('thrust')),
        S('itki [N]', 'uçuş_aracı.thrust', v.get('thrust')),
        S('yanma süresi [s]', 'motor.burn_time', m.get('burn_time')),
        S('yanma süresi [s]', 'uçuş_aracı.burn_time', v.get('burn_time')),
        S('Isp [s]', 'motor.isp', m.get('isp')),
        S('Isp [s]', 'motor.sea_level_isp', m.get('sea_level_isp')),
        S('boğaz çapı [mm]', 'motor.throat_diameter×1000', (m.get('throat_diameter') or 0) * 1000),
        S('boğaz çapı [mm]', 'design_summary.key_dimensions.nozzle_throat_diameter_mm', kd.get('nozzle_throat_diameter_mm')),
        S('çıkış çapı [mm]', 'motor.exit_diameter×1000', (m.get('exit_diameter') or 0) * 1000),
        S('çıkış çapı [mm]', 'design_summary.key_dimensions.nozzle_exit_diameter_mm', kd.get('nozzle_exit_diameter_mm')),
        # V301/T-ÇAPA-D: uçuş aracı boyu kapaklı (FİZİK-2 kalem 6).
        S('toplam boy [mm]', 'design_summary.key_dimensions.total_motor_length_mm', kd.get('total_motor_length_mm')),
        S('kapaklı toplam boy [mm]', 'design_summary.key_dimensions.total_motor_length_with_caps_mm',
          kd.get('total_motor_length_with_caps_mm')),
        S('kapaklı toplam boy [mm]', 'uçuş_aracı.engine_length_m×1000', (v.get('engine_length_m') or 0) * 1000),
        S('kuru kütle [kg]', 'design_summary.key_dimensions.dry_mass_estimate_kg', kd.get('dry_mass_estimate_kg')),
        S('kuru kütle [kg]', 'motor.structural_analysis.weight_analysis.total_weight', wa.get('total_weight')),
        S('kuru kütle [kg]', 'uçuş_aracı.engine_inert_mass', v.get('engine_inert_mass')),
    ]


@pytest.mark.parametrize('mt', MOTORLAR)
def test_k3_json_paneller_ayni_sayi(client, mt):
    """Ana sonuç ⟷ tasarım özeti ⟷ motor_geometry ⟷ uçuş aracı: aynı
    büyüklük aynı sayı (REL9). Satırlar ve sonuç RAPOR'da tablo olarak."""
    _yuk, s = basarili_hesap(client, mt)
    satirlar = _json_satirlari(mt, s, _arac(client, mt))
    _kanit_yaz(mt, 'k3_json', satirlar)
    kotu = kabul.k3_karsilastir(satirlar)
    assert not kotu, f'{mt}: aynı büyüklük farklı sayı:\n  ' + '\n  '.join(kotu)


@pytest.mark.parametrize('mt', MOTORLAR)
def test_k3_proje_ozeti_hesapla_ayni(client, mt):
    """Proje şeridi/liste kartının sayısı (örneğin results_summary'si) =
    kullanıcının Hesapla'da gördüğü sayı (yuvarlamanın yarım basamağı)."""
    _yuk, s = basarili_hesap(client, mt)
    ozet = kabul.ornek_belgesi(mt).get('results_summary') or {}
    ana = {'solid': {'peak_thrust_N': s.get('max_thrust'), 'isp_s': s.get('isp_sea_level'),
                     'chamber_pressure_bar': s.get('chamber_pressure'),
                     'burn_time_s': s.get('burn_time'), 'total_impulse_Ns': s.get('total_impulse')},
           'liquid': {'thrust_N': s.get('thrust'), 'isp_s': s.get('isp_sea_level'),
                      'isp_vacuum_s': s.get('isp_vacuum'),
                      'chamber_pressure_bar': s.get('chamber_pressure')},
           'hybrid': {k: (s.get('motor') or {}).get(a) for k, a in (
               ('thrust_N', 'thrust'), ('isp_s', 'isp'), ('chamber_pressure_bar', 'chamber_pressure'),
               ('burn_time_s', 'burn_time'), ('total_impulse_Ns', 'total_impulse'))}}[mt]
    satirlar = []
    for ad, anahtar, deger in kabul.ozet_satirlari(mt, ozet):
        satirlar.append(kabul.satir(ad, 'Hesapla (ana sonuç)', ana.get(anahtar)))
        satirlar.append(kabul.satir(ad, 'örnek.results_summary.' + anahtar, deger,
                                    'YARIM', 3))
    assert satirlar, f'{mt}: örnekte results_summary yok'
    _kanit_yaz(mt, 'k3_ozet', satirlar)
    kotu = kabul.k3_karsilastir(satirlar)
    assert not kotu, (f'{mt}: proje şeridi (results_summary) ⟷ Hesapla farklı — ÖRNEK '
                      'TAZELEMESİ BEKLİYOR (özet sayfanın gerçek yüküyle üretilmeli):\n  '
                      + '\n  '.join(kotu))


@pytest.mark.parametrize('mt', MOTORLAR)
def test_k3_rapor_pdf_ayni_sayi(client, mt):
    """Rapor PDF'inin (özet) metnindeki ana sayılar = yanıt (YARIM: PDF'in
    bastığı ondalık). Aynı PDF içinde aynı büyüklük iki sayıyla basılmaz."""
    _yuk, s = basarili_hesap(client, mt)
    r = ihrac(client, mt, 'rapor_pdf')
    assert r['durum'] == 200, f'{mt}: rapor PDF alınamadı (HTTP {r["durum"]}) — K4'
    metin = kabul.pdf_metni(r['ham'])
    S = kabul.satir

    def pdf(ad, etiket, desen=None):
        bul = (kabul.pdf_desen_sayisi(metin, desen) if desen
               else kabul.pdf_etiket_sayisi(metin, etiket))
        if bul is None:
            return S(ad, 'PDF "%s" (bulunamadı)' % (etiket or desen), None, 'YARIM', 0)
        return S(ad, 'PDF "%s"' % (etiket or desen), bul[0], 'YARIM', bul[1])
    if mt == 'solid':
        satirlar = [S('tepe itki [N]', 'ana.max_thrust', s.get('max_thrust')),
                    pdf('tepe itki [N]', 'Maximum Thrust'),
                    S('Isp [s]', 'ana.specific_impulse', s.get('specific_impulse')),
                    pdf('Isp [s]', 'Specific Impulse'),
                    S('Pc [bar]', 'ana.chamber_pressure', s.get('chamber_pressure')),
                    pdf('Pc [bar]', 'Chamber Pressure'),
                    S('yanma süresi [s]', 'ana.burn_time', s.get('burn_time')),
                    pdf('yanma süresi [s]', 'Burn Time'),
                    S('toplam impuls [N·s]', 'ana.total_impulse', s.get('total_impulse')),
                    pdf('toplam impuls [N·s]', 'Total Impulse'),
                    pdf('toplam impuls [N·s]', None, r'total impulse ns:\s*([0-9.]+)'),
                    S('boğaz çapı [mm]', 'ana.throat_diameter', s.get('throat_diameter')),
                    pdf('boğaz çapı [mm]', 'Throat Diameter'),
                    S('itici kütlesi [kg]', 'ana.propellant_mass', s.get('propellant_mass')),
                    pdf('itici kütlesi [kg]', 'Propellant Mass')]
    elif mt == 'liquid':
        satirlar = [S('itki [N]', 'ana.thrust', s.get('thrust')), pdf('itki [N]', 'Maximum Thrust'),
                    S('Isp [s]', 'ana.isp_sea_level', s.get('isp_sea_level')),
                    pdf('Isp [s]', 'Specific Impulse'),
                    S('Pc [bar]', 'ana.chamber_pressure', s.get('chamber_pressure')),
                    pdf('Pc [bar]', 'Chamber Pressure'),
                    S('boğaz çapı [mm]', 'ana.throat_diameter_mm', s.get('throat_diameter_mm')),
                    pdf('boğaz çapı [mm]', 'Throat Diameter'),
                    S('çıkış çapı [mm]', 'ana.exit_diameter_mm', s.get('exit_diameter_mm')),
                    pdf('çıkış çapı [mm]', 'Exit Diameter')]
    else:
        m = s.get('motor') or {}
        satirlar = [S('itki [N]', 'motor.thrust', m.get('thrust')), pdf('itki [N]', 'Maximum Thrust'),
                    S('Isp [s]', 'motor.isp', m.get('isp')), pdf('Isp [s]', 'Specific Impulse'),
                    S('Pc [bar]', 'motor.chamber_pressure', m.get('chamber_pressure')),
                    pdf('Pc [bar]', 'Chamber Pressure'),
                    S('toplam impuls [N·s]', 'motor.total_impulse', m.get('total_impulse')),
                    pdf('toplam impuls [N·s]', 'Total Impulse'),
                    pdf('toplam impuls [N·s]', None, r'total impulse ns:\s*([0-9.]+)'),
                    S('boğaz çapı [mm]', 'motor.throat_diameter×1000', (m.get('throat_diameter') or 0) * 1000),
                    pdf('boğaz çapı [mm]', 'Throat Diameter'),
                    S('çıkış çapı [mm]', 'motor.exit_diameter×1000', (m.get('exit_diameter') or 0) * 1000),
                    pdf('çıkış çapı [mm]', 'Exit Diameter')]
    _kanit_yaz(mt, 'k3_pdf', satirlar)
    kotu = kabul.k3_karsilastir(satirlar)
    assert not kotu, f'{mt}: rapor PDF ⟷ yanıt farklı:\n  ' + '\n  '.join(kotu)


@pytest.mark.parametrize('mt', MOTORLAR)
def test_k3_cad_olculeri_yanitla_ayni(client, mt):
    """STEP (OCC) ve STL sınır kutusu ⟷ yanıttaki boy ve dış çap (CAD:
    bağıl 1e-6). Eksen x = motor ekseni, x=0 kamara baş ucu (STEP
    çizimi); kapak x<0'da çizilir. Kıyaslanan: lüle arka ucu (max x) ⟷
    yayımlanan kapaksız toplam boy; kapaklı toplam boy (max x − min x) ⟷
    yayımlanan kapaklı boy (yoksa: yayımlanmıyor = bulgu); en büyük çap ⟷
    uçuş aracının gövde çapı (aracın sardığı zarf)."""
    _yuk, s = basarili_hesap(client, mt)
    r = ihrac(client, mt, 'step')
    assert r['durum'] == 200, (f'{mt}: STEP alınamadı (HTTP {r["durum"]}) — '
                               'K4 ile aynı kök; CAD ölçüsü karşılaştırılamıyor')
    icerik = kabul.zip_icerigi(r['ham'])
    montaj = [n for n in icerik if n.lower().endswith(('.step', '.stp')) and 'assembly' in n.lower()]
    assert montaj, f'{mt}: STEP paketinde montaj dosyası yok: {sorted(icerik)}'
    kutu = kabul.step_kutusu(icerik[montaj[0]], kabul.CALISMA / ('step-%d' % os.getpid()))
    stl_ad = {'hybrid': 'stl_zip'}.get(mt, 'stl_step_zip')
    rs = ihrac(client, mt, stl_ad)
    assert rs['durum'] == 200, f'{mt}: STL alınamadı (HTTP {rs["durum"]})'
    stl = kabul.zip_icerigi(rs['ham'])
    stl_montaj = [n for n in stl if n.lower().endswith('.stl') and 'assembly' in n.lower()]
    assert stl_montaj, f'{mt}: STL paketinde montaj yok: {sorted(stl)}'
    skutu = kabul.stl_kutusu(stl[stl_montaj[0]])
    v = _arac(client, mt)
    kd = (s.get('design_summary') or {}).get('key_dimensions') or {}
    boy = {'solid': kd.get('total_length_mm'), 'liquid': kd.get('overall_length_mm'),
           'hybrid': kd.get('total_motor_length_mm')}[mt]
    kapakli = {'solid': kd.get('total_length_with_closure_mm'),
               'liquid': kd.get('overall_length_with_closure_mm'),
               'hybrid': kd.get('total_motor_length_with_caps_mm')}[mt]
    S = kabul.satir
    cap_step = 2 * max(abs(kutu[0][1]), abs(kutu[1][1]), abs(kutu[0][2]), abs(kutu[1][2]))
    cap_stl = 2 * max(abs(skutu[0][1]), abs(skutu[1][1]), abs(skutu[0][2]), abs(skutu[1][2]))
    satirlar = [
        S('kapaksız toplam boy [mm]', 'yanıt key_dimensions', boy),
        # V301/T-ÇAPA-D: STEP'in interpolasyonlu lüle konturu ölçüleri ürünün
        # kontur kapısı sınırıyla (kabul.KONTUR_SINIF_KATSAYISI; ölçülen
        # gerçek aşma katı örnekte 53 nm yarıçap). STL satırları 'CAD'.
        S('kapaksız toplam boy [mm]', 'STEP montaj max x', kutu[1][0], 'CAD_KONTUR_BOY'),
        S('kapaksız toplam boy [mm]', 'STL montaj max x', skutu[1][0], 'CAD'),
        S('kapaklı toplam boy [mm]', 'yanıt key_dimensions (kapaklı)', kapakli),
        S('kapaklı toplam boy [mm]', 'STEP montaj max x − min x', kutu[1][0] - kutu[0][0],
          'CAD_KONTUR_BOY'),
        S('kapaklı toplam boy [mm]', 'STL montaj max x − min x', skutu[1][0] - skutu[0][0], 'CAD'),
        S('en büyük çap [mm]', 'uçuş_aracı.engine_od_m×1000', (v.get('engine_od_m') or 0) * 1000),
        S('en büyük çap [mm]', 'STEP montaj en büyük çap', cap_step, 'CAD_KONTUR_CAP'),
        S('en büyük çap [mm]', 'STL montaj en büyük çap', cap_stl, 'CAD'),
    ]
    _kanit_yaz(mt, 'k3_cad', satirlar)
    kotu = kabul.k3_karsilastir(satirlar)
    assert not kotu, f'{mt}: CAD ⟷ yanıt ölçüleri farklı:\n  ' + '\n  '.join(kotu)


# ===========================================================================
# K6 — uçuş kaynağı: kayıtlı proje ⟷ son hesap
# ===========================================================================
#: Bit-aynı olması gereken araç alanları (brif: kütleler, çap, boy, itki
#: eğrisi, yanma süresi). ``source``/``motor_name``/not metinleri kaynağı
#: anlatır, karşılaştırılmaz (beyanlı).
ARAC_ALANLARI = ('engine_inert_mass', 'propellant_mass', 'engine_od_m',
                 'engine_length_m', 'thrust', 'thrust_curve', 'burn_time')


@pytest.mark.parametrize('mt', MOTORLAR)
def test_k6_ucus_araci_proje_kaynagi_son_hesapla_bit_ayni(client, mt, monkeypatch):
    """Örnek DOSYA kayıtlı proje olarak seçilince uçan araç = sayfanın son
    hesabının aracı. Kırmızıysa ve fark örnek dosyanın taşımadığı alanlardan
    geliyorsa: ÖRNEK TAZELEMESİ BEKLİYOR (ana model, generate_examples);
    kullanıcının KAYDETTİĞİ proje yolu ayrıca kabul_ui K6-UI düğümünde."""
    import shutil
    from tests.test_example_projects import NAMES, EXAMPLES_DIR
    # Depo KOPYASI: HRMA_PROJECTS_DIR depodaki examples/'a yönlendirilirse
    # ürün oraya tazeleme damgası (.examples_refresh.json) yazıyor (ölçüldü
    # 27 Eki) — izlenen dizine yazmamak için kalıcı çalışma dizininde kopya.
    depo = kabul.CALISMA / ('k6-projeler-%d' % os.getpid())
    depo.mkdir(parents=True, exist_ok=True)
    shutil.copy2(EXAMPLES_DIR / (NAMES[mt] + '.hrma'), depo / (NAMES[mt] + '.hrma'))
    monkeypatch.setenv('HRMA_PROJECTS_DIR', str(depo))
    sonuc = _arac(client, mt)
    durum, js, _h, _t = kabul.post(client, '/api/flight-vehicle',
                                   {'source': 'project', 'name': NAMES[mt]})
    assert durum == 200, js
    proje = js['vehicle']
    farklar = [f'{k}: son hesap {json.dumps(sonuc.get(k))[:120]} ⟷ kayıtlı proje '
               f'{json.dumps(proje.get(k))[:120]}'
               for k in ARAC_ALANLARI
               if json.dumps(sonuc.get(k), sort_keys=True) != json.dumps(proje.get(k), sort_keys=True)]
    _kanit_yaz(mt, 'k6', {'son_hesap': {k: sonuc.get(k) for k in ARAC_ALANLARI},
                          'kayitli_proje': {k: proje.get(k) for k in ARAC_ALANLARI}})
    assert not farklar, (f'{mt}: Fırlatma Sahası örnek dosyadan FARKLI motor uçuruyor '
                         '(örnek dosya sayfanın gönderdiği alanları taşımıyorsa: ÖRNEK '
                         'TAZELEMESİ BEKLİYOR):\n  ' + '\n  '.join(farklar))


def test_k3_cad_kontur_olcutu_urun_sinirindan_ve_ters_mutasyonda_kirmizi():
    """V301/T-ÇAPA-D (ana model kararı): STEP kontur ölçüsü ölçütü ürünün kapı
    sabitinden gelir; ölçülen 53 nm aşma geçer, 50 µm'lik çap sapması ve
    11 µm'lik boy sapması KIRMIZI kalır (ters mutasyon)."""
    from hrma.engines.nozzle_design import CONTOUR_ENVELOPE_TOLERANCE_MM
    S = kabul.satir
    assert kabul.kontur_siniri_mm('CAD_KONTUR_CAP') == 2 * CONTOUR_ENVELOPE_TOLERANCE_MM
    assert kabul.kontur_siniri_mm('CAD_KONTUR_BOY') == CONTOUR_ENVELOPE_TOLERANCE_MM
    ref = 90.99999999999999
    assert kabul.esit_mi(ref, S('c', 'STEP', 91.0001064244349, 'CAD_KONTUR_CAP'))
    assert not kabul.esit_mi(ref, S('c', 'STEP', ref + 0.05, 'CAD_KONTUR_CAP'))
    assert not kabul.esit_mi(ref, S('c', 'STEP', ref - 0.05, 'CAD_KONTUR_CAP'))
    boy = 557.087597885417
    assert kabul.esit_mi(boy, S('b', 'STEP', boy + 0.009, 'CAD_KONTUR_BOY'))
    assert not kabul.esit_mi(boy, S('b', 'STEP', boy + 0.011, 'CAD_KONTUR_BOY'))
    # Eski 'CAD' sınıfı aynı aşmayı hâlâ yakalar (sınıf yalnız bu iki ölçüde).
    assert not kabul.esit_mi(ref, S('c', 'STL', 91.0001064244349, 'CAD'))
