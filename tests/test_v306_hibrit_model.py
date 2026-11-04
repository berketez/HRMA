# -*- coding: utf-8 -*-
"""V306/HİBRİT-MODEL — hibrit motor modelinin boyutlandırma bekçileri.

Kaynak bulgular: mühendis turu (docs/scofield/raw/OH/V306/muhendis-turu/
hibrit/BULGULAR.md) ve UÇUŞ-2 devri. Brif:
docs/scofield/raw/OH/V306/ana-model/brif_02kas/HIBRIT_MODEL.md +
brif_03kas/HIBRIT_MODEL.md. Ölçümler:
docs/scofield/raw/OH/V306/hibrit-model/olcum/.

Kalemler:
* **6 (UÇUŞ-2 devri)** — motor TEK çıkış alanı yayımlar (lülenin
  geometrisi); vakum ve irtifa itkisi o alandan ve tasarım ortam
  basıncından türetilir: F_vak = F_tasarım + p_tasarım·A_e.
* **2 (M-HIBRIT-25)** — c* verimi varsayılanı bütün çiftlerde aynı kural:
  çiftin ölçülmüş kayıtlarının ortancası, yoksa beyanlı genel hibrit
  ortancası; ideal c* yalnız kullanıcı 100 girerse.

Beklenen değerler ucun O KOŞUMDAKİ yanıtından ya da kayıtların kendisinden
okunur; ürün sabiti kendini doğrulamaz.
"""

import contextlib
import glob
import io
import json
import pathlib
import re
import statistics
import warnings

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
ORNEK = KOK / 'examples' / 'Example Hybrid N2O-HTPB 3kN.hrma'
KAYITLAR = KOK / 'hrma' / 'data' / 'validation_records' / 'hybrid'
G0 = 9.80665


def _ornek_govde(**ek):
    from tests.support.ornek_alanlari import ornek_alanlari
    f = ornek_alanlari(ORNEK)
    f.pop('motor_name', None)
    f.pop('motor_description', None)
    f['atmospheric_pressure'] = f.pop('single_pressure')
    f.update(ek)
    return {k: v for k, v in f.items() if v is not None}


def _post(uc, govde):
    from hrma.app import app
    app.config['TESTING'] = True
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()), \
            warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with app.test_client() as c:
            r = c.post(uc, json=govde)
    return r.status_code, r.get_json() or {}


@pytest.fixture(scope='module')
def ornek():
    kod, j = _post('/calculate', _ornek_govde())
    assert kod == 200, str(j)[:400]
    return j


# ---------------------------------------------------------------------------
# Kalem 6 — tek çıkış alanı, tasarım ortamında çapa
# ---------------------------------------------------------------------------
def test_tarama_geometrik_alan_ve_tasarim_capasi_ile():
    """Sabit geometride dF/dp_a = −A_e: her satır F + (p_çapa − p)·A_e."""
    from hrma.constants import isa_pressure
    from hrma.engines.combustion_analysis import CombustionAnalyzer
    mdot, v_e, p_e_bar, t_e, r_e = 1.4, 2400.0, 0.9, 1800.0, 320.0
    f_tasarim, a_e, p_capa = 3000.0, 0.0036, 1.0e5
    satirlar, meta = CombustionAnalyzer._fixed_nozzle_altitude_sweep(
        mdot, v_e, p_e_bar, t_e, r_e, [0, 5000, 20000],
        thrust_sea_level=f_tasarim, exit_area_m2=a_e,
        anchor_ambient_pressure_pa=p_capa)
    assert meta['exit_area_m2'] == a_e
    assert meta['anchor_ambient_pressure_pa'] == p_capa
    assert meta['thrust_vacuum_n'] == pytest.approx(
        f_tasarim + p_capa * a_e, rel=1e-12)
    for s in satirlar:
        p_pa = isa_pressure(float(s['altitude']))
        assert s['thrust'] == pytest.approx(
            f_tasarim + (p_capa - p_pa) * a_e, rel=1e-12)


def test_tarama_eski_yol_bit_ayni():
    """Alan/çapa verilmezse eski (süreklilik + ISA) yol değişmez."""
    from hrma.engines.combustion_analysis import CombustionAnalyzer
    arg = (1.4, 2400.0, 0.9, 1800.0, 320.0, [0, 10000])
    s1, m1 = CombustionAnalyzer._fixed_nozzle_altitude_sweep(
        *arg, thrust_sea_level=3000.0)
    assert 'exit_area_source' not in m1
    assert m1['exit_area_m2'] == pytest.approx(
        1.4 * 320.0 * 1800.0 / (0.9e5 * 2400.0), rel=1e-15)


@pytest.mark.parametrize('alan, deger', [
    ('exit_area_m2', 0.0), ('exit_area_m2', float('nan')),
    ('anchor_ambient_pressure_pa', -1.0)])
def test_tarama_gecersiz_alan_adiyla_reddedilir(alan, deger):
    from hrma.engines.combustion_analysis import CombustionAnalyzer
    with pytest.raises(ValueError, match=alan):
        CombustionAnalyzer._fixed_nozzle_altitude_sweep(
            1.4, 2400.0, 0.9, 1800.0, 320.0, [0],
            thrust_sea_level=3000.0, **{alan: deger})


def test_motor_tek_cikis_alani_yayimlar(ornek):
    m = ornek['motor']
    nlm = m['altitude_performance']['nozzle_loss_model']
    # UÇUŞ-2'nin okuduğu alan (flight_vehicle.motor_flight_thrust) lülenin
    # geometrik alanıyla AYNI sayı.
    assert nlm['exit_area_m2'] == m['exit_area']
    assert m['exit_area'] == pytest.approx(
        m['throat_area'] * m['expansion_ratio'], rel=1e-9)
    tat = m['thrust_altitude_analysis']['nozzle_loss_model']
    assert tat['exit_area_m2'] == m['exit_area']


def test_vakum_itkisi_tasarim_ortamindan(ornek):
    m = ornek['motor']
    p_tasarim_pa = m['nozzle_design']['performance']['ambient_pressure'] * 1e5
    nlm = m['altitude_performance']['nozzle_loss_model']
    assert nlm['anchor_ambient_pressure_pa'] == pytest.approx(
        p_tasarim_pa, rel=1e-12)
    f_vak = m['thrust'] + p_tasarim_pa * m['exit_area']
    assert nlm['thrust_vacuum_n'] == pytest.approx(f_vak, rel=1e-12)
    assert m['vacuum_isp'] == pytest.approx(
        f_vak / (m['mdot_total'] * G0), rel=1e-12)
    assert m['thrust_altitude_analysis']['vacuum_thrust'] == pytest.approx(
        f_vak, rel=1e-12)


# ---------------------------------------------------------------------------
# Kalem 2 — c* verimi: bütün çiftlerde aynı kural
# ---------------------------------------------------------------------------
def _kayit_verimi(r):
    m = r.get('measured') or {}
    if m.get('c_star_efficiency') is not None:
        return float(m['c_star_efficiency'])
    if m.get('c_star_efficiency_percent') is not None:
        return float(m['c_star_efficiency_percent']) / 100.0
    return None


def _kayitlar():
    return [json.loads(pathlib.Path(y).read_text(encoding='utf-8'))
            for y in sorted(glob.glob(str(KAYITLAR / '*.json')))]


def _istatistik(degerler):
    return (len(degerler), statistics.median(degerler),
            (min(degerler), max(degerler)),
            round(statistics.stdev(degerler), 4),
            round(statistics.mean(degerler), 4))


def _pencere_gecerli(r):
    """Ölçüm penceresi kuralı (4 Kas): kararı yazılmış ve geçersiz olan
    kayıt varsayılana girmez; kararı olmayan anomali kaydını
    ``test_her_anomali_kaydinin_pencere_karari_var`` yakalar."""
    from hrma.engines.hybrid_rocket_engine import (
        HYBRID_ETA_C_STAR_WINDOW_DECISIONS)
    # Sözlük okuması ``.get(...)`` ile yazılmaz: d18/d24 rota çağrısı
    # tarayıcısı ``X.get(<ifade>)``'yi istemci çağrısı sayıp "çözülemeyen
    # rota çağrısı" tavanını aşıyordu (24 > 23); bu bir rota çağrısı değil.
    kimlik = r['test_id']
    if kimlik not in HYBRID_ETA_C_STAR_WINDOW_DECISIONS:
        return True
    return HYBRID_ETA_C_STAR_WINDOW_DECISIONS[kimlik]['window_valid']


def _anomali_notu_var(r):
    a = r.get('anomaly') or {}
    return bool(a.get('flag')) or bool(str(a.get('note') or '').strip())


@pytest.mark.parametrize('cift', [('lox', 'htpb'), ('lox', 'paraffin'),
                                  ('n2o', 'htpb')])
def test_cift_varsayilani_kayitlardan_yeniden_hesaplanir(cift):
    from hrma.engines.hybrid_rocket_engine import HYBRID_ETA_C_STAR_MEASURED
    k = HYBRID_ETA_C_STAR_MEASURED[cift]
    degerler = [v for r in _kayitlar()
                if any(r['test_id'].startswith(p)
                       for p in k['record_prefixes']) and _pencere_gecerli(r)
                for v in [_kayit_verimi(r)] if v is not None]
    n, ortanca, bant, sigma, ortalama = _istatistik(degerler)
    assert n == k['n_tests']
    assert ortanca == pytest.approx(k['eta_c_star'], abs=1e-12)
    assert bant == pytest.approx(tuple(k['measured_band']), abs=1e-12)
    assert sigma == pytest.approx(k['sample_stdev'], abs=1e-12)
    assert ortalama == pytest.approx(k['mean'], abs=1e-12)


def test_genel_varsayilan_butun_olcumlerden():
    from hrma.engines.hybrid_rocket_engine import HYBRID_ETA_C_STAR_GENERAL
    k = HYBRID_ETA_C_STAR_GENERAL
    degerler = [v for r in _kayitlar()
                if not r.get('synthetic') and _pencere_gecerli(r)
                for v in [_kayit_verimi(r)] if v is not None]
    n, ortanca, bant, sigma, ortalama = _istatistik(degerler)
    assert n == k['n_tests']
    assert ortanca == pytest.approx(k['eta_c_star'], abs=1e-12)
    assert bant == pytest.approx(tuple(k['measured_band']), abs=1e-12)
    assert sigma == pytest.approx(k['sample_stdev'], abs=1e-12)
    assert ortalama == pytest.approx(k['mean'], abs=1e-12)


def test_her_anomali_kaydinin_pencere_karari_var():
    """Ölçülmüş c* verimi + anomali notu taşıyan HER kaydın pencere kararı
    yazılı; karar tablosunda kaydı olmayan ya da veriminden yoksun satır
    yok (yeni anomali kaydı sınıflandırılmadan varsayılana giremez)."""
    from hrma.engines.hybrid_rocket_engine import (
        HYBRID_ETA_C_STAR_WINDOW_DECISIONS)
    anomali = {r['test_id'] for r in _kayitlar()
               if _kayit_verimi(r) is not None and _anomali_notu_var(r)}
    assert anomali == set(HYBRID_ETA_C_STAR_WINDOW_DECISIONS)
    for tid, k in HYBRID_ETA_C_STAR_WINDOW_DECISIONS.items():
        assert isinstance(k['window_valid'], bool), tid
        assert k['label'] and k['reason'] and k['reason_code'], tid


def test_lox_htpb_bes_kaydin_pencere_karari():
    """Ana model kararı (4 Kas): LOX/HTPB'nin 5 kaydı kayıt kayıt."""
    from hrma.engines.hybrid_rocket_engine import (
        HYBRID_ETA_C_STAR_MEASURED, resolve_hybrid_c_star_efficiency)
    k = HYBRID_ETA_C_STAR_MEASURED[('lox', 'htpb')]
    kayitlar = {r['test_id']: r for r in _kayitlar()
                if any(r['test_id'].startswith(p)
                       for p in k['record_prefixes'])}
    assert sorted(kayitlar) == [
        'hyb-hpdp2003-htpb-lox-250k-m1t1', 'hyb-hpdp2003-htpb-lox-250k-m2t1',
        'hyb-hpdp2003-htpb-lox-250k-m2t2', 'hyb-hpdp2003-htpb-lox-250k-m2t3',
        'hyb-sims1998-htpb-lox-hp24-5030']
    gecerli = sorted(t for t, r in kayitlar.items() if _pencere_gecerli(r))
    assert gecerli == ['hyb-hpdp2003-htpb-lox-250k-m2t1',
                       'hyb-hpdp2003-htpb-lox-250k-m2t3',
                       'hyb-sims1998-htpb-lox-hp24-5030']
    c = resolve_hybrid_c_star_efficiency('lox', 'htpb', None)
    assert [d['test_id'] for d in c['excluded_records']] == [
        'hyb-hpdp2003-htpb-lox-250k-m1t1', 'hyb-hpdp2003-htpb-lox-250k-m2t2']
    assert {d['reason_code'] for d in c['excluded_records']} == {
        'window_not_determinable'}
    # Varsayılan ORTANCADIR; ortalama yanında yayımlanır.
    gv = [_kayit_verimi(kayitlar[t]) for t in gecerli]
    assert c['eta_c_star'] == pytest.approx(statistics.median(gv),
                                            abs=1e-12)
    assert c['mean'] == pytest.approx(statistics.mean(gv), abs=5e-5)
    assert 'HPDP 2003 250K M1T1' in c['basis']
    assert 'HPDP 2003 250K M2T2' in c['basis']


def test_lule_erozyonu_alan_duzeltmeli_kayit_dislanmaz():
    """Düşük ama doğru ölçülmüş / düzeltilmiş verim anomali diye
    dışlanmaz: Karabeyoğlu 4F-1A/4F-4/4F-5 (Ek Denk. A7 ORTALAMA lüle
    alanı) ve 4L-12 (tutarsızlık c* terimlerinde değil) girer."""
    from hrma.engines.hybrid_rocket_engine import (
        resolve_hybrid_c_star_efficiency)
    c = resolve_hybrid_c_star_efficiency('lox', 'paraffin', None)
    disla = {d['test_id'] for d in c['excluded_records']}
    for ek in ('t4f-1a', 't4f-4', 't4f-5', 't4l-12'):
        assert 'hyb-karabeyoglu2003-paraffin-gox-' + ek not in disla
    assert disla == {'hyb-karabeyoglu2003-paraffin-gox-' + ek
                     for ek in ('t4l-06', 't4l-07', 't4l-11', 'tst')}


def test_n2o_htpb_dislanan_yok_alan_yayimlanmaz(ornek):
    blok = ornek['motor']['c_star_efficiency']
    assert 'excluded_records' not in blok
    assert blok['mean'] == pytest.approx(0.8885)


@pytest.mark.parametrize('cift', [('lox', 'htpb'), ('n2o', 'paraffin')])
def test_az_gecerli_kayitta_varsayilan_kurulmaz(monkeypatch, cift):
    """Geçerli kayıt pratik kapının altında: varsayılan yok, adlı ret;
    ideal c*'a (η = 1) DÜŞÜLMEZ."""
    import hrma.engines.hybrid_rocket_engine as H
    if cift in H.HYBRID_ETA_C_STAR_MEASURED:
        kayit = dict(H.HYBRID_ETA_C_STAR_MEASURED[cift], n_tests=1)
        monkeypatch.setitem(H.HYBRID_ETA_C_STAR_MEASURED, cift, kayit)
    else:
        monkeypatch.setattr(H, 'HYBRID_ETA_C_STAR_GENERAL',
                            dict(H.HYBRID_ETA_C_STAR_GENERAL, n_tests=1))
    with pytest.raises(H.HybridCStarDefaultUnavailable,
                       match='Enter the c\\* efficiency'):
        H.resolve_hybrid_c_star_efficiency(*cift, None)
    # Kullanıcı değeri her zaman geçer.
    assert H.resolve_hybrid_c_star_efficiency(*cift, 92)['eta_engine'] == \
        pytest.approx(0.92)


def test_az_gecerli_kayit_ucta_adli_422(monkeypatch):
    import hrma.engines.hybrid_rocket_engine as H
    kayit = dict(H.HYBRID_ETA_C_STAR_MEASURED[('lox', 'htpb')], n_tests=1)
    monkeypatch.setitem(H.HYBRID_ETA_C_STAR_MEASURED, ('lox', 'htpb'), kayit)
    govde = _ornek_govde(oxidizer_type='lox', fuel_type='htpb')
    govde.pop('combustion_efficiency', None)
    kod, j = _post('/calculate', govde)
    assert kod == 422, str(j)[:300]
    alan = j['invalid_fields'][0]
    assert alan['field'] == 'combustion_efficiency'
    assert alan['reason'] == 'too_few_valid_measured_firings'


def test_az_gecerli_kayit_ret_cumlesi_turkcede_cevrilir(tmp_path,
                                                        monkeypatch):
    import subprocess
    from tests.test_app_hata_dili import (
        NODE, NODE_DUZENEGI, STATIC_JS, TURKCE_KARAKTER)
    if NODE is None:
        pytest.skip('node yok')
    import hrma.engines.hybrid_rocket_engine as H
    kayit = dict(H.HYBRID_ETA_C_STAR_MEASURED[('lox', 'htpb')], n_tests=1)
    monkeypatch.setitem(H.HYBRID_ETA_C_STAR_MEASURED, ('lox', 'htpb'), kayit)
    with pytest.raises(H.HybridCStarDefaultUnavailable) as hata:
        H.resolve_hybrid_c_star_efficiency('lox', 'htpb', None)
    cumle = str(hata.value)
    duzenek = tmp_path / 'srv.js'
    duzenek.write_text(NODE_DUZENEGI, encoding='utf-8')
    girdi = tmp_path / 'in.json'
    girdi.write_text(json.dumps([cumle]), encoding='utf-8')
    islem = subprocess.run([NODE, str(duzenek), str(STATIC_JS), str(girdi)],
                           capture_output=True, text=True, timeout=120)
    assert islem.returncode == 0, islem.stderr
    sonuc = json.loads(islem.stdout)
    assert sonuc['en'] == [cumle]
    tr = sonuc['tr'][0]
    assert tr != cumle and TURKCE_KARAKTER.search(tr), tr
    assert 'LOX/HTPB için' in tr and 'pratik kapı' in tr


_MANSET = r"""
const fs = require('fs'); const vm = require('vm');
const kaynak = fs.readFileSync(process.argv[2], 'utf8');
const bas = kaynak.indexOf('function headlineBasisBlock(');
const son = kaynak.indexOf('\n}\n', bas);
const motor = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const sb = { JSON, Object, Array, Math, Number, String, isFinite, window: {},
  T: (k, f) => f,
  TF: (k, p, f) => String(f).replace(/\{(\w+)\}/g, (w, n) =>
      (p && n in p) ? String(p[n]) : w) };
vm.createContext(sb);
vm.runInContext(kaynak.slice(bas, son + 3)
  + '\nthis.sonuc = headlineBasisBlock(' + JSON.stringify(motor) + ');', sb);
process.stdout.write(sb.sonuc);
"""


def test_manset_dislanan_kayitlari_adi_ve_gerekcesiyle_yazar(tmp_path):
    import shutil
    import subprocess
    node = shutil.which('node')
    if node is None:
        pytest.skip('node yok')
    from hrma.engines.hybrid_rocket_engine import (
        HYBRID_ETA_C_STAR_WINDOW_DECISIONS, resolve_hybrid_c_star_efficiency)
    c = resolve_hybrid_c_star_efficiency('n2o', 'paraffin', None)
    blok = {k: c[k] for k in ('eta_c_star', 'percent', 'source', 'scope',
                              'n_tests', 'mean', 'measured_band', 'sources',
                              'excluded_records')}
    blok.update(applied=True, c_star_theoretical_m_s=1600.0,
                c_star_delivered_m_s=1600.0 * c['eta_c_star'])
    duzenek = tmp_path / 'm.js'
    duzenek.write_text(_MANSET, encoding='utf-8')
    dosya = tmp_path / 'motor.json'
    dosya.write_text(json.dumps({'c_star_efficiency': blok}),
                     encoding='utf-8')
    islem = subprocess.run(
        [node, str(duzenek), str(KOK / 'hrma' / 'static' / 'js' / 'app.js'),
         str(dosya)], capture_output=True, text=True, timeout=60)
    assert islem.returncode == 0, islem.stderr
    html = islem.stdout
    assert '(mean %.3f)' % c['mean'] in html
    assert '%d firings excluded' % len(c['excluded_records']) in html
    for d in c['excluded_records']:
        assert d['label'] in html
    assert 'HPDP 2003 250K M1T1 (stable window not determinable)' in html
    assert 'Karabeyoglu 2003 4L-11 (burn too short for data reduction)' \
        in html
    # Dışlanan her gerekçe kodunun manşette bir çevirisi var (EN + TR).
    app_js = (KOK / 'hrma' / 'static' / 'js' / 'app.js').read_text(
        encoding='utf-8')
    ortak = (KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js').read_text(
        encoding='utf-8')
    for k in HYBRID_ETA_C_STAR_WINDOW_DECISIONS.values():
        if not k['window_valid']:
            assert k['reason_code'] + ': T(' in app_js, k['reason_code']
    for anahtar in ('cstarExclWindowUnknown', 'cstarExclUnburnedFuel',
                    'cstarExclShortBurn', 'cstarEffExcluded'):
        assert ortak.count("'app.headline.%s'" % anahtar) == 2, anahtar


@pytest.mark.parametrize('ox, fu, kapsam', [
    ('n2o', 'htpb', 'propellant_pair'), ('lox', 'htpb', 'propellant_pair'),
    ('lox', 'paraffin', 'propellant_pair'), ('n2o', 'paraffin',
                                             'all_hybrid_pairs'),
    ('h2o2', 'pe', 'all_hybrid_pairs'), ('lox', 'abs', 'all_hybrid_pairs')])
def test_verilmeyen_verim_her_ciftte_kaynakli(ox, fu, kapsam):
    from hrma.engines.hybrid_rocket_engine import (
        HYBRID_ETA_C_STAR_GENERAL, HYBRID_ETA_C_STAR_MEASURED,
        resolve_hybrid_c_star_efficiency)
    c = resolve_hybrid_c_star_efficiency(ox, fu, None)
    assert c['source'] == 'sourced_default'
    assert c['scope'] == kapsam
    beklenen = (HYBRID_ETA_C_STAR_MEASURED[(ox, fu)]
                if kapsam == 'propellant_pair'
                else HYBRID_ETA_C_STAR_GENERAL)['eta_c_star']
    assert c['eta_engine'] == c['eta_c_star'] == beklenen
    assert c['eta_c_star'] < 1.0


def test_ideal_yalniz_kullanici_isterse():
    from hrma.engines.hybrid_rocket_engine import (
        resolve_hybrid_c_star_efficiency)
    c = resolve_hybrid_c_star_efficiency('lox', 'paraffin', 100)
    assert c['source'] == 'user_input' and c['eta_engine'] == 1.0


def test_ipucu_sayilari_sabitlerle_ayni():
    """'?' ipucundaki yüzdeler ve sayılar tek tanımdan sapmaz (EN + TR)."""
    from hrma.engines.hybrid_rocket_engine import (
        HYBRID_ETA_C_STAR_GENERAL, HYBRID_ETA_C_STAR_MEASURED)
    metin = (KOK / 'hrma' / 'static' / 'js' / 'i18n_advanced.js').read_text(
        encoding='utf-8')
    ipuclari = re.findall(r"'adv\.tip\.combustionEfficiency': '(.*?)',\n",
                          metin)
    assert len(ipuclari) == 2
    en, tr = ipuclari

    def yuzde(x):
        return ('%g' % round(100 * x, 1))

    kayitlar = [HYBRID_ETA_C_STAR_MEASURED[c] for c in (
        ('n2o', 'htpb'), ('lox', 'htpb'), ('lox', 'paraffin'))]
    kayitlar.append(HYBRID_ETA_C_STAR_GENERAL)
    for k in kayitlar:
        assert yuzde(k['eta_c_star']) + ' %' in en, k['eta_c_star']
        assert '%' + yuzde(k['eta_c_star']).replace('.', ',') in tr
        assert str(k['n_tests']) in en and str(k['n_tests']) in tr


def test_ornek_n2o_htpb_degismedi(ornek):
    """N2O/HTPB varsayılanı (0,89) bu kalemde değişmez."""
    blok = ornek['motor']['c_star_efficiency']
    assert blok['eta_c_star'] == pytest.approx(0.89)
    assert blok['scope'] == 'propellant_pair'


# ---------------------------------------------------------------------------
# Kalem 3 — M-HIBRIT-11: astar = gerileme payı + iletim payı (iki rejimde)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('fo', [0.01, 0.0635, 0.2, 1.0, 3.0])
def test_levha_arka_yuz_cozumu_iki_seriyle_ayni(fo):
    """Görüntü (erfc) serisi = Fourier serisi (Carslaw & Jaeger §3.3)."""
    import math
    from hrma.engines.hybrid_rocket_engine import _slab_back_face_rise
    fourier = 1.0 - 4.0 / math.pi * sum(
        (-1) ** n / (2 * n + 1)
        * math.exp(-(2 * n + 1) ** 2 * math.pi ** 2 * fo / 4.0)
        for n in range(4000))
    assert _slab_back_face_rise(fo) == pytest.approx(fourier, abs=1e-9)


def test_iletim_fourier_sayisi_kesri_saglar():
    from hrma.engines.hybrid_rocket_engine import (
        LINER_BACK_FACE_RISE_FRACTION, LINER_CONDUCTION_FOURIER,
        _slab_back_face_rise)
    assert _slab_back_face_rise(LINER_CONDUCTION_FOURIER) == pytest.approx(
        LINER_BACK_FACE_RISE_FRACTION, abs=1e-12)


def _astar(h, t_aw=2700.0, t_b=11.0, r=0.05):
    from hrma.analysis.thermal_protection import ThermalProtectionAnalyzer
    from hrma.engines.hybrid_rocket_engine import (
        LINER_MATERIAL_DEFAULT, hybrid_liner_sizing)
    return hybrid_liner_sizing(
        ThermalProtectionAnalyzer(), q_net_W_m2=h * 1000.0, burn_time_s=t_b,
        material=LINER_MATERIAL_DEFAULT, T_initial_K=293.15,
        h_gas_W_m2K=h, T_recovery_K=t_aw, station_radius_m=r)


def _iletim_mm(t_b):
    from hrma.data.materials_db import get_material
    from hrma.engines.hybrid_rocket_engine import LINER_CONDUCTION_FOURIER
    m = get_material('ablative')
    alfa = m['thermal_conductivity'] / (m['density'] * m['specific_heat'])
    return (alfa * t_b / LINER_CONDUCTION_FOURIER) ** 0.5 * 1e3


def test_net_isinma_yokken_astar_iletimle_boyutlanir():
    s = _astar(200.0)       # düşük h: ablasyon sıcaklığında net ısınma yok
    assert s['recession_regime'] == 'no_net_heating'
    assert s['thickness_status'] == 'sized' and s['model_valid'] is True
    assert s['recession_allowance_mm'] == 0.0
    assert s['required_thickness_mm'] == pytest.approx(_iletim_mm(11.0),
                                                       rel=1e-12)


def test_kararli_ablasyonda_iki_pay_toplanir():
    s = _astar(3000.0)
    assert s['recession_regime'] == 'steady_ablation'
    assert s['required_thickness_mm'] == pytest.approx(
        s['q_star_thickness_mm'] + _iletim_mm(11.0), rel=1e-12)


def test_isi_yuku_artarken_astar_incelmez():
    """Monotonluk: daha sıcak motor daha ince astar almaz (M-HIBRIT-11)."""
    kalinlik = [_astar(h)['required_thickness_mm']
                for h in (100.0, 300.0, 1000.0, 2000.0, 4000.0)]
    assert kalinlik == sorted(kalinlik)


def test_astar_gecidi_kapatirsa_yayimlanmaz():
    s = _astar(200.0, r=0.004)
    assert s['thickness_status'] == 'NOT_MODELLED'
    assert s['required_thickness_mm'] is None
    assert 'station radius' in s['validity_note']


def test_guverte_termal_astar_yolu_ayni_islevi_cagirir():
    kaynak = (KOK / 'hrma' / 'analysis' / 'heat_transfer_analysis.py'
              ).read_text(encoding='utf-8')
    govde = kaynak[kaynak.index('def _apply_chamber_liner'):]
    if '\ndef ' in govde:
        govde = govde[:govde.index('\ndef ')]
    assert 'hybrid_liner_sizing(' in govde
    assert 'ablative_thickness(' not in govde


def test_carmicino_dusuk_basincta_motor_kritik_olmaz():
    """Carmicino 2013 t01 (8,52 bar, gaz N2O / HTPB): eskiden ÇIPLAK
    CİDAR KRİTİK + YAPI UNSAFE."""
    govde = _ornek_govde(chamber_pressure=8.52, of_ratio=3.9,
                         combustion_efficiency=79, oxidizer_phase='gas',
                         thrust=72.7, burn_time=11, total_impulse=799.7,
                         initial_port_diameter=0.0117)
    kod, j = _post('/calculate', govde)
    assert kod == 200, str(j)[:300]
    m = j['motor']
    astar = m['thermal_protection']['chamber_liner']
    assert astar['thickness_status'] == 'sized'
    assert astar['recession_regime'] == 'no_net_heating'
    assert astar['thickness'] == pytest.approx(
        astar['conduction_allowance_mm'], rel=1e-12)
    bolgeler = m['chamber_wall_zones']
    assert bolgeler['all_zones_protected'] is True
    assert not [z for z in bolgeler['zones']
                if z['verdict'] == 'BARE_WALL_CRITICAL']
    assert m['structural_analysis']['safety_analysis']['status'] != 'UNSAFE'


# ---------------------------------------------------------------------------
# Kalem 4 — M-HIBRIT-38: yapısal sekme motorun kasa sıcaklığında, tek hüküm
# ---------------------------------------------------------------------------
def _guverte_govdesi(j, **ek):
    m = j['motor']
    sa = m['structural_analysis']
    ta = sa['thermal_analysis']
    cidar_m = sa['chamber_analysis']['wall_thickness_used_mm'] / 1000.0
    govde = {
        'chamber_pressure': m['chamber_pressure'],
        'chamber_diameter': m['chamber_diameter'],
        'chamber_length': m['chamber_length'],
        'throat_diameter': m['throat_diameter'],
        'chamber_temperature': m['chamber_temperature'],
        'thrust': m['thrust'],
        'wall_thickness': cidar_m,
        'material': m['chamber_material'],
        'safety_factor': m['design_safety_factor_input'],
        'motor_type': 'hybrid',
        'motor_result': {'motor': {'structural_analysis': {
            'safety_analysis': sa['safety_analysis']}}},
        'motor_verdict_inputs': {
            'chamber_pressure': m['chamber_pressure'],
            'chamber_diameter': m['chamber_diameter'],
            'wall_thickness': cidar_m},
        'motor_wall_source': 'sized_by_hrma',
        'motor_wall_temperature': {
            'hot': ta['wall_temperature_inner_K'],
            'cold': ta['wall_temperature_outer_K'],
            'source': ta['wall_temperature_source']},
    }
    govde.update(ek)
    return {k: v for k, v in govde.items() if v is not None}


def test_yapisal_sekme_motorun_kasa_sicakliginda(ornek):
    m = ornek['motor']
    sa_m = m['structural_analysis']
    assert (sa_m['thermal_analysis']['wall_temperature_source']
            == 'hybrid_chamber_zone_protection')
    kod, j = _post('/analyze_structural_safety', _guverte_govdesi(ornek))
    assert kod == 200, str(j)[:300]
    sa = j['structural_analysis']
    assert sa['thermal_analysis']['wall_temperature_source'] == (
        'hybrid_chamber_zone_protection')
    assert sa['thermal_analysis']['wall_temperature_inner_K'] == (
        sa_m['thermal_analysis']['wall_temperature_inner_K'])
    # Aynı cidar, aynı sıcaklık → aynı çember emniyet katsayısı ve aynı
    # kazanılmış kapsam hükmü (iki hüküm yok).
    assert sa['chamber_analysis']['hoop_safety_factor'] == pytest.approx(
        sa_m['chamber_analysis']['hoop_safety_factor'], rel=1e-6)
    s, s_m = sa['safety_analysis'], sa_m['safety_analysis']
    assert s['earned_scope_status'] == s_m['earned_scope_status']
    assert s['module_status'] == s_m['status'] == s['status']


def test_yapisal_sekme_girdi_degisince_motor_sicakligini_benimsemez(ornek):
    govde = _guverte_govdesi(
        ornek, chamber_pressure=ornek['motor']['chamber_pressure'] * 1.2)
    kod, j = _post('/analyze_structural_safety', govde)
    assert kod == 200, str(j)[:300]
    assert j['structural_analysis']['thermal_analysis'][
        'wall_temperature_source'] != 'hybrid_chamber_zone_protection'


def test_yapisal_sekme_kullanici_sicakligi_onceliklidir(ornek):
    govde = _guverte_govdesi(ornek, wall_temperature_hot=600.0,
                             wall_temperature_cold=550.0)
    kod, j = _post('/analyze_structural_safety', govde)
    assert kod == 200, str(j)[:300]
    ta = j['structural_analysis']['thermal_analysis']
    assert ta['wall_temperature_inner_K'] == pytest.approx(600.0)
    assert ta['wall_temperature_source'] != 'hybrid_chamber_zone_protection'


def test_panel_baglami_motor_kasa_sicakligini_tasir(tmp_path, ornek):
    import shutil
    import subprocess
    node = shutil.which('node')
    if node is None:
        pytest.skip('node yok')
    js = KOK / 'hrma' / 'static' / 'js'
    duzenek = tmp_path / 'p.js'
    duzenek.write_text(r"""
const fs = require('fs'); const path = require('path'); const vm = require('vm');
const [jsDir, sonucYolu] = process.argv.slice(2);
function El() { this.children = []; this.style = {}; this.dataset = {}; }
El.prototype.appendChild = function (c) { return c; };
El.prototype.setAttribute = function () {};
El.prototype.querySelectorAll = function () { return []; };
const doc = { head: new El(), body: new El(), readyState: 'complete',
  documentElement: { setAttribute() {}, lang: 'en' },
  createElement: function () { return new El(); },
  querySelector: function () { return null; },
  querySelectorAll: function () { return []; },
  getElementById: function () { return null; }, addEventListener() {} };
const sb = { console: { log() {}, warn() {}, error() {} }, setTimeout,
  clearTimeout, JSON, Math, Number, Array, Object, String, Boolean, RegExp,
  Promise, Date, Error, isFinite, isNaN, parseFloat, parseInt,
  fetch: function () { return Promise.reject(new Error('yok')); },
  document: doc };
sb.window = sb; sb.globalThis = sb; sb.self = sb; sb.localStorage = null;
vm.createContext(sb);
for (const f of ['units_constants.js', 'analysis_dock.js',
                 path.join('panels', 'structural_panel.js')]) {
  vm.runInContext(fs.readFileSync(path.join(jsDir, f), 'utf8'), sb);
}
sb.window.AnalysisDock._setMotorType('hybrid');
const spec = sb.window.AnalysisDock._registry.filter(s => s.id === 'structural')[0];
const r = JSON.parse(fs.readFileSync(sonucYolu, 'utf8'));
spec.fromResults(r);
process.stdout.write(JSON.stringify(spec.contextFromResults(r)));
""", encoding='utf-8')
    dosya = tmp_path / 'r.json'
    dosya.write_text(json.dumps(ornek), encoding='utf-8')
    islem = subprocess.run([node, str(duzenek), str(js), str(dosya)],
                           capture_output=True, text=True, timeout=120)
    assert islem.returncode == 0, islem.stderr[-2000:]
    ctx = json.loads(islem.stdout)
    ta = ornek['motor']['structural_analysis']['thermal_analysis']
    assert ctx['motor_wall_temperature'] == {
        'hot': ta['wall_temperature_inner_K'],
        'cold': ta['wall_temperature_outer_K'],
        'source': 'hybrid_chamber_zone_protection'}


# ---------------------------------------------------------------------------
# Kalem 1 — M-HIBRIT-22: grafit lüle = ek (erozyon) + yapısal gövde
# ---------------------------------------------------------------------------
def test_grafit_luele_ek_ve_govde(ornek):
    from hrma.analysis.structural_analysis import (
        STRUCTURAL_DESIGN_PRESSURE_FACTOR, nozzle_throat_wall_sizing)
    from hrma.analysis.transient_ballistics import ThroatErosionModel
    from hrma.data.materials_db import get_material
    m = ornek['motor']
    assert m['nozzle_material'] == 'graphite'
    geo = m['nozzle_design']['geometry']
    yap = geo['nozzle_construction']
    assert yap['type'] == 'insert_plus_structural_housing'
    ek, gov = yap['insert'], yap['housing']
    assert 'not a pressure shell' in yap['basis']
    # Ek: yanma boyunca toplam boğaz gerilemesi (bant üstü), imalat tabanı.
    hiz = ThroatErosionModel.for_material('graphite').rate_mm_s(
        m['chamber_pressure'])
    assert ek['erosion_recession_mm'] == pytest.approx(
        hiz * ek['burn_time_s'], rel=1e-12)
    assert ek['thickness_mm'] == pytest.approx(
        max(1.0, ek['erosion_recession_mm']), rel=1e-12)
    # Gövde: kamara malzemesi, aynı boğaz kuralı, gövdenin iç yarıçapında.
    assert gov['material_key'] == m['chamber_material']
    r_gov = m['throat_diameter'] / 2.0 + ek['thickness_mm'] / 1000.0
    assert gov['inner_radius_mm'] == pytest.approx(r_gov * 1000.0,
                                                   rel=1e-12)
    kayit = get_material(gov['material_key'])
    boyut = nozzle_throat_wall_sizing(
        m['chamber_pressure'] * 1e5 * STRUCTURAL_DESIGN_PRESSURE_FACTOR,
        r_gov, kayit['yield_strength'], gov['safety_factor_target'],
        m['nozzle_type'])
    from hrma.engines.hybrid_rocket_engine import (
        NOZZLE_HOUSING_SIZING_ROUND_UP_REL as PAY)
    assert gov['thickness_mm'] == pytest.approx(
        max(1.0, boyut['required_throat_thickness_m'] * 1000.0
            * (1.0 + PAY)), rel=1e-12)
    assert geo['wall_thickness'] == pytest.approx(
        ek['thickness_mm'] + gov['thickness_mm'], rel=1e-12)


def test_yapisal_lule_denetimi_govdeyi_dogrular(ornek):
    m = ornek['motor']
    gov = m['nozzle_design']['geometry']['nozzle_construction']['housing']
    na = m['structural_analysis']['nozzle_analysis']
    assert na['material_key'] == gov['material_key']
    assert na['throat_thickness_used_mm'] == pytest.approx(
        gov['thickness_mm'], rel=1e-12)
    assert na['shell_inner_radius_mm'] == pytest.approx(
        gov['inner_radius_mm'], rel=1e-12)
    # Gövde kendi hedefini ALTTAN okumaz (toleranssız: merdiven eşiği
    # 2,0'da 1 ulp altı UNSAFE basar).
    assert na['safety_factor'] >= gov['safety_factor_target']


def test_l5_boyutlanan_govde_hedefin_altinda_okunmaz():
    """Tur L5 (LOX/HTPB, SF 2, grafit): gövde SF'si 1,9999999999999998
    okunup motor yapı hükmü UNSAFE/HIGH'a düşüyordu (taban MARGINAL)."""
    from tests.support.kanit import kanit_gerekli
    # Kanıt kapısı (test_kanit_atlama_kapisi): docs'suz yayın dalında atla,
    # HRMA_KANIT_ZORUNLU=1 iken HATA; okuma yalnız kapıdan geçer.
    yol = kanit_gerekli(
        KOK / 'docs/scofield/raw/OH/V306/muhendis-turu/hibrit/vakalar'
        / 'L5.json')
    d = json.loads(yol.read_text(encoding='utf-8'))
    govde = [r for r in d['istekler'] if r['uc'] == '/calculate'][-1]['govde']
    kod, j = _post('/calculate', govde)
    assert kod == 200, str(j)[:300]
    m = j['motor']
    gov = m['nozzle_design']['geometry']['nozzle_construction']['housing']
    na = m['structural_analysis']['nozzle_analysis']
    assert na['safety_factor'] >= gov['safety_factor_target']
    sa = m['structural_analysis']['safety_analysis']
    assert sa['verdict_safety_factor'] >= gov['safety_factor_target']
    assert (sa['status'], sa['risk_level']) == ('MARGINAL', 'MEDIUM')


def test_cizilen_lule_kutlesi_iki_malzemeyle_tek_sayi(ornek):
    from hrma.analysis.structural_analysis import (
        drawn_nozzle_insert_housing_mass_kg)
    from hrma.engines.nozzle_design import sample_nozzle_inner_contour
    m = ornek['motor']
    geo = m['nozzle_design']['geometry']
    pts, _meta = sample_nozzle_inner_contour(m)
    beklenen = drawn_nozzle_insert_housing_mass_kg(
        pts, geo['nozzle_construction'])
    assert geo['estimated_mass'] == pytest.approx(beklenen, rel=1e-12)
    assert ornek['cad_design']['performance_summary']['mass_breakdown'][
        'nozzle_mass'] == pytest.approx(beklenen, rel=1e-12)


def test_motor_zarfi_kasa_ile_ayni_ve_ana_sayfada(ornek):
    from hrma.analysis.flight_vehicle import normalize
    m = ornek['motor']
    kd = m['design_summary']['key_dimensions']
    ca = m['structural_analysis']['chamber_analysis']
    kasa_mm = ca['diameter'] + 2.0 * ca['wall_thickness_used_mm']
    arac = normalize('hybrid', ornek)
    assert kd['motor_envelope_diameter_mm'] == pytest.approx(
        arac['engine_od_m'] * 1000.0, rel=1e-12)
    # Grafit ek + gövde artık kasanın dışına taşmıyor (örnekte çizilen lüle
    # dış profili kasa dış çapını aşmaz; zarf = kasa).
    assert kd['motor_envelope_diameter_mm'] == pytest.approx(kasa_mm,
                                                            rel=1e-9)


def test_tasarim_raporunda_zarf_satiri():
    kaynak = (KOK / 'hrma' / 'static' / 'js' / 'app.js').read_text(
        encoding='utf-8')
    govde = kaynak[kaynak.index('function designSummarySection('):]
    govde = govde[:govde.index('\n}\n')]
    assert 'dims.motor_envelope_diameter_mm' in govde
    assert "'app.rep.motorEnvelopeDia'" in govde


def test_grafit_disi_lule_eski_tek_parca_yol():
    """C-C / metal lülede iki parçalı yapı kurulmaz (erozyon bandı ya da
    basınç kabuğu beyanı farklı)."""
    from hrma.engines.hybrid_rocket_engine import NOZZLE_INSERT_ONLY_MATERIALS
    assert NOZZLE_INSERT_ONLY_MATERIALS == ('graphite',)


# ---------------------------------------------------------------------------
# Kalem 5 — M-HIBRIT-10: gaz N2O beslemesi
# ---------------------------------------------------------------------------
def test_gaz_faz_kapisi_doyma_altini_kabul_eder():
    from hrma.engines.hybrid_rocket_engine import user_tank_pressure_state
    durum, ret = user_tank_pressure_state(16.0, 8.52, 'n2o', 293.0,
                                          oxidizer_phase='gas')
    assert ret == [] and durum['oxidizer_phase'] == 'gas'
    assert durum['superheat_pressure_margin_bar'] == pytest.approx(
        durum['saturation_pressure_bar'] - 16.0)
    # Sıvı faz aynı basıncı (doyma altı) aynen reddeder.
    _d, ret_s = user_tank_pressure_state(16.0, 8.52, 'n2o', 293.0,
                                         oxidizer_phase='liquid')
    assert [r['reason'] for r in ret_s] == ['below_n2o_saturation_pressure']


def test_gaz_faz_kapisi_doyma_ustunu_adiyla_reddeder():
    from hrma.engines.hybrid_rocket_engine import user_tank_pressure_state
    _d, ret = user_tank_pressure_state(60.0, 20.0, 'n2o', 293.0,
                                       oxidizer_phase='gas')
    assert [r['reason'] for r in ret] == [
        'above_n2o_saturation_pressure_gas_phase']
    assert ret[0]['maximum_bar'] > ret[0]['saturation_pressure_bar']


@pytest.fixture(scope='module')
def carmicino_gaz():
    govde = _ornek_govde(chamber_pressure=8.52, of_ratio=3.9,
                         combustion_efficiency=79, oxidizer_phase='gas',
                         thrust=72.7, burn_time=11, total_impulse=799.7,
                         initial_port_diameter=0.0117,
                         tank_pressure_source='user', tank_pressure=16)
    return _post('/calculate', govde)


def test_carmicino_gaz_n2o_kullanici_basinci_cozulur(carmicino_gaz):
    kod, j = carmicino_gaz
    assert kod == 200, str(j)[:400]
    m = j['motor']
    assert m['oxidizer_inlet_state']['phase'] == 'gas'
    # Yanma gaz girişiyle çözülür; performans yayımlanır.
    assert m['isp'] > 0 and m['c_star_efficiency']['source'] == 'user_input'


def test_gaz_beslemede_sivi_besleme_sayilari_yayimlanmaz(carmicino_gaz):
    kod, j = carmicino_gaz
    assert kod == 200
    m = j['motor']
    assert m['injector_design']['status'] == 'not_analyzed'
    for ad in ('oxidizer_tank_slosh', 'oxidizer_tank_pressure_vessel',
               'tank_blowdown'):
        assert m[ad]['status'] == 'NOT_MODELLED', ad
    kodlar = [w.get('code') for w in m.get('design_warnings') or []
              if isinstance(w, dict)]
    assert 'warn.hybrid.gas_phase_feed_not_modelled' in kodlar


def test_gaz_faz_ret_cumlesi_turkcede_cevrilir(tmp_path):
    """Gaz faz doyma üstü reddi (422) Türkçe arayüzde çevrilir; cümle
    ÜRÜNDEN alınır (kapının kendi metni)."""
    import subprocess
    from tests.test_app_hata_dili import (
        NODE, NODE_DUZENEGI, STATIC_JS, TURKCE_KARAKTER)
    if NODE is None:
        pytest.skip('node yok')
    from hrma.engines.hybrid_rocket_engine import user_tank_pressure_state
    _d, ret = user_tank_pressure_state(60.0, 20.0, 'n2o', 293.0,
                                       oxidizer_phase='gas')
    cumle = ret[0]['message']
    duzenek = tmp_path / 'srv.js'
    duzenek.write_text(NODE_DUZENEGI, encoding='utf-8')
    girdi = tmp_path / 'in.json'
    girdi.write_text(json.dumps([cumle]), encoding='utf-8')
    islem = subprocess.run([NODE, str(duzenek), str(STATIC_JS), str(girdi)],
                           capture_output=True, text=True, timeout=120)
    assert islem.returncode == 0, islem.stderr
    sonuc = json.loads(islem.stdout)
    assert sonuc['en'] == [cumle]
    tr = sonuc['tr'][0]
    assert tr != cumle and TURKCE_KARAKTER.search(tr), tr
    assert 'yoğuşur' in tr and '%2' in tr


def test_korunan_kasada_isil_yapraklar_ozdeslik_ve_kardes_canli(ornek):
    """Kalem 3'ten sonra bütün bölgeler korunduğunda yapısal zincir beyanlı
    izotermal kasayı kullanır: ΔT = 0, ısıl çember gerilmesi 0, dayanım
    tutma 1 TANIM GEREĞİ (tests/test_field_wiring_layer_b.py bu 11 yaprağı
    tam yolla imler). Kilit: özdeşlik YALNIZ bölge modeli devredeyken; canlı
    kardeş (kasa sıcaklığı) ortam sıcaklığı girdisini izler."""
    m = ornek['motor']
    z = m['chamber_wall_zones']
    sa = m['structural_analysis']
    ta, ca = sa['thermal_analysis'], sa['chamber_analysis']
    assert z['all_zones_protected'] is True
    assert ta['wall_temperature_source'] == 'hybrid_chamber_zone_protection'
    assert ta['wall_temperature_inner_K'] == ta['wall_temperature_outer_K'] \
        == z['structural_casing_temperature_K']
    assert ta['wall_delta_T_K'] == 0.0 and ca['thermal_hoop_stress'] == 0.0
    for sen in ca['thermal_scenarios'].values():
        assert sen['delta_T_K'] == 0.0
    # Canlı kardeş: ortam sıcaklığı değişince kasa sıcaklığı onu izler.
    kod, j = _post('/calculate', _ornek_govde(ambient_temp=263.15))
    assert kod == 200, str(j)[:300]
    m2 = j['motor']
    assert m2['chamber_wall_zones']['structural_casing_temperature_K'] == \
        pytest.approx(263.15)
    assert m2['structural_analysis']['thermal_analysis'][
        'wall_temperature_inner_K'] == pytest.approx(263.15)
