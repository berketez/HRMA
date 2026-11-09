"""V306/DİL-SIVI bekçileri — sıvı motor sayfasının kullanıcıya görünen dili.

Kilitlenen (kanıt: docs/scofield/raw/OH/V306/dil-sivi/RAPOR.md):

1. Form "?" ipuçları (liquid.html ``.tooltip-text`` + i18n_pages.js EN/TR):
   uç adı / "sent as" kalıbı, ham alan adı (snake_case) ve kaynaksız
   "tipik / typically / genellikle" cümlesi yok.
2. Yörünge yer tutucusu ("Yörünge hesaplanıyor…") çizimden önce kaldırılır
   (M-SIVI-5/16).
3. Güverte kapsam notu başka yazılım önermez (M-SIVI-9: "ANSYS").
4. Parametrik sekme açıklaması çizilen figürü anlatır (M-SIVI-29): O/F /
   oda basıncı taraması ve kaynaksız "optimum aralık" yok.
5. Başka proje açılınca dışa aktarım satırı silinir (M-SIVI-32).
6. Alt sistem kartı etiket sütunu harf harf kırılmaz (NR-20, 9 Kas ek 3/4).
7. Çevirici düğümleri node'da: tank künyesi ham alan adı basmaz (etiket
   sözlükten, makine adı data-liq-field'da); en az 3 anlamlı basamak
   (M-SIVI-7); kanal ölçüsü ekran dilinin ondalığıyla; otojen gerekçesi
   seçicinin adıyla; tanınmayan değer HAM kalır.
8. Sayfanın çevirdiği çözücü dizeleri (imalat süreçleri, tasarım özeti
   başlığı/önerisi, otojen gerekçeleri, kanal mutabakatı) çözücüde hâlâ
   aynı; değişirse sözlük sessizce devreden çıkmasın diye burada düşer.
9. Yayım kapısı TR metninde sayfanın terimi "nozul" ("lüle" değil).
"""
import io
import json
import os
import re
import shutil
import subprocess

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SABLON = os.path.join(KOK, 'hrma', 'templates', 'liquid.html')
SAYFA_SOZLUK = os.path.join(KOK, 'hrma', 'static', 'js', 'i18n_pages.js')
MOTOR = os.path.join(KOK, 'hrma', 'engines', 'liquid_rocket_engine.py')
NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node kurulu değil')


def _oku(yol):
    with io.open(yol, encoding='utf-8') as fh:
        return fh.read()


def _sozluk(onek):
    """{anahtar: [EN, TR]} — dosyadaki iki bloğun sırasıyla."""
    sonuc = {}
    for m in re.finditer(r"^\s*'(%s[^']+)'\s*:\s*'((?:[^'\\]|\\.)*)'\s*,?\s*$"
                         % re.escape(onek), _oku(SAYFA_SOZLUK), re.M):
        sonuc.setdefault(m.group(1), []).append(
            m.group(2).replace("\\'", "'").replace('\\\\', '\\'))
    return sonuc


def _islev(html, imza):
    """Şablondan ``imza`` ile başlayan işlevin GERÇEK gövdesi (süslü sayımı)."""
    i = html.index(imza)
    j = html.index('{', i)
    derin = 0
    for k in range(j, len(html)):
        if html[k] == '{':
            derin += 1
        elif html[k] == '}':
            derin -= 1
            if derin == 0:
                return html[i:k + 1]
    raise AssertionError(imza)


def _node(betik):
    """Betik stdin'den verilir (argv DEĞİL: test_node_cagri_sozlesmesi)."""
    out = subprocess.run([NODE, '-'], input=betik, capture_output=True,
                         text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout)


# Node düzeneği: TR sözlüğüyle T/TF, TR ondalık (virgül).
_TR_DUZENEK = r"""
const SOZ = %s;
function T(k, fb) { return Object.prototype.hasOwnProperty.call(SOZ, k) ? SOZ[k] : fb; }
function TF(k, p, fb) { return String(T(k, fb)).replace(/\{(\w+)\}/g, (w, n) =>
    (p && Object.prototype.hasOwnProperty.call(p, n)) ? String(p[n]) : w); }
function numTxt(v, d) { return Number(v).toFixed(d == null ? 1 : d).replace('.', ','); }
var window = {};
"""


@pytest.fixture(scope='module')
def tr_sozluk():
    return {k: v[1] for k, v in _sozluk('liq.').items() if len(v) == 2}


# ---------------------------------------------------------------------------
# 1. İpuçları
# ---------------------------------------------------------------------------
UC_ADI = re.compile(r'/api/|/calculate|/analyze|olarak gönderilir|olarak gider|'
                    r'\bsent as\b|\bendpoint\b')
ALAN_ADI = re.compile(r'\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b')
TIPIK = re.compile(r'\b(?:Typical|typically|Usually|usually|Tipik|tipik|'
                   r'genellikle|Genellikle)\b')


@pytest.mark.parametrize('desen,ad', [(UC_ADI, 'uç adı / gönderim kalıbı'),
                                      (ALAN_ADI, 'ham alan adı'),
                                      (TIPIK, 'kaynaksız tipik değer')],
                         ids=['uc_adi', 'alan_adi', 'tipik'])
def test_ipuclarinda_yasak_kalip_yok(desen, ad):
    html = _oku(SABLON)
    anahtarlar = sorted(set(re.findall(
        r'class="tooltip-text"[^>]*data-i18n="(liq\.[^"]+)"', html)))
    assert len(anahtarlar) >= 70, len(anahtarlar)
    sozluk = _sozluk('liq.')
    kotu = []
    for k in anahtarlar:
        assert len(sozluk.get(k, [])) == 2, k
        for dil, metin in zip(('en', 'tr'), sozluk[k]):
            bulunan = desen.findall(metin)
            if bulunan:
                kotu.append((k, dil, bulunan[:3]))
    assert not kotu, '%s: %s' % (ad, kotu)


def test_of_bandi_ipucu_tarama_bandini_anlatir():
    """of_min / of_max performans haritasının tarama bandıdır (çözücü
    ``of_scan_min/max``), kararlı yanma sınırı DEĞİL (eski metin yanlıştı)."""
    soz = _sozluk('liq.ui.')
    for k in ('liq.ui.minimum_operational_mixture_ratio_for_stable',
              'liq.ui.maximum_operational_mixture_ratio_before_excessi'):
        en, tr = soz[k]
        assert 'sweep' in en and 'performance map' in en, en
        assert 'tarama' in tr and 'performans haritası' in tr.lower(), tr
        assert 'stable' not in en and 'kararlı' not in tr
    motor = _oku(MOTOR)
    assert re.search(r"^PERF_MAP_MR_SPAN = 0\.45\b", motor, re.M), (
        'tarama bandı varsayılanı değişti; ipucu (× 0,55 / × 1,45) yeniden ölçülmeli')
    assert "'of_min': (0.2, 20.0," in motor and "'of_max': (0.2, 20.0," in motor


# ---------------------------------------------------------------------------
# 2-6. Şablon düğümleri
# ---------------------------------------------------------------------------
def test_yorunge_yer_tutucusu_cizimden_once_kalkar():
    govde = _islev(_oku(SABLON), 'async function computeTrajectory()')
    yt = govde.index("data-liq-traj-placeholder")
    sil = govde.index("querySelectorAll('[data-liq-traj-placeholder]')")
    ciz = govde.index('liquidPlot(div, fig.data, fig.layout)')
    assert yt < sil < ciz


def test_kapsam_notu_baska_yazilim_onermez():
    html = _oku(SABLON)
    soz = _sozluk('liq.msg.')
    for metin in soz['liq.msg.hand_calculation_scope']:
        assert 'ANSYS' not in metin and 'FEA (' not in metin, metin
    i = html.index("adNote.setAttribute('data-i18n', 'liq.msg.hand_calculation_scope')")
    assert 'ANSYS' not in html[i:i + 600]


def test_parametrik_aciklama_cizilen_figuru_anlatir():
    html = _oku(SABLON)
    i = html.index('<div id="single_altitude_content"')
    j = html.index('<div id="altitude_profile_plot"')
    blok = html[i:j]
    for yasak in ('Optimal range', '2.5-2.8', 'Peak markers', 'Mixture Ratio (O/F) - oxidizer',
                  'Blue line', 'Red curve'):
        assert yasak not in blok, yasak
    for k in ('liq.ui.param_isp_line', 'liq.ui.param_thrust_series', 'liq.ui.param_cf_line',
              'liq.ui.param_eff_line', 'liq.ui.param_mach_line'):
        assert 'data-i18n="%s"' % k in blok, k
    soz = _sozluk('liq.')
    # alt sekme adı = çizilen grafiğin başlığı (iki dilde)
    assert soz['liq.ui.single_altitude'] == soz['liq.msg.engine_performance_vs_altitude']
    assert soz['liq.ui.altitude_profile'] == soz['liq.msg.nozzle_parameters_vs_altitude']


def test_proje_degisince_disa_aktarim_satiri_silinir():
    html = _oku(SABLON)
    i = html.index("document.addEventListener('hrma:project-applied', function () {")
    blok = html[i:i + 400]
    assert "getElementById('liquidExportStatus')" in blok
    assert "_liquidExportStatus('')" in blok


def test_etiket_sutunu_harf_harf_kirilmaz():
    html = _oku(SABLON)
    m = re.search(r'\.subsystem-card \.spec-table td:first-child:not\(\[colspan\]\)\s*\{([^}]*)\}', html)
    assert m, 'etiket sütunu kuralı yok'
    assert 'overflow-wrap: normal' in m.group(1) and 'word-break: normal' in m.group(1)


def test_isil_koruma_ham_alan_adi_ekranda_degil():
    sozluk = _sozluk('liq.msg.')
    for metin in sozluk['liq.msg.material_allowable_temperature']:
        assert 'station_march' not in metin
    html = _oku(SABLON)
    govde = _islev(html, 'function displayEngineeringCards(results)')
    assert "solvedSrc = 'thermal_protection.station_march '" not in govde
    assert 'data-liq-source=' in govde
    assert 'ciddiyetAyir' in govde


def test_kapi_metninde_nozul_terimi():
    for k, (en, tr) in _sozluk('liq.gate.').items():
        assert 'lüle' not in tr, (k, tr)


# ---------------------------------------------------------------------------
# 7. Çeviriciler node'da (TR sözlüğüyle)
# ---------------------------------------------------------------------------
@node_gerekli
def test_tank_kunyesi_sozluk_etiketi_ham_ad_yok(tr_sozluk):
    html = _oku(SABLON)
    fn = '\n'.join(_islev(html, imza) for imza in (
        'function _tankEsc(v)', 'function tankKunye(alan, deger)',
        'function tankKriyoSatiri(cs)'))
    betik = (_TR_DUZENEK % json.dumps(tr_sozluk)) + fn + r"""
const sonuc = {
  kisa: tankKunye('safety_factor_source', 'user input (safety factor)'),
  uzun: tankKunye('ullage_fraction_basis', 'TANK_ULLAGE_FRACTION = 0.05 non-liquid ullage volume fraction of the tank; fixed'),
  bilinmeyen: tankKunye('yeni_alan', 'x'),
  kriyo: tankKriyoSatiri({verdict: 'not_required', basis: 'rp1 is stored near ambient temperature'}),
  kriyo_tanimsiz: tankKriyoSatiri({verdict: 'garip'})
};
process.stdout.write(JSON.stringify(sonuc));
"""
    s = _node(betik)
    gorunen = lambda h: re.sub(r'<[^>]*>', ' ', h)
    assert 'Emniyet katsayısının kaynağı: sizin girdiniz (Yapısal Emniyet Katsayısı)' in s['kisa']
    assert 'data-liq-field="safety_factor_source"' in s['kisa']
    assert 'safety_factor_source' not in gorunen(s['kisa'])
    assert s['uzun'].startswith('<details') and '<summary' in s['uzun']
    assert 'Boşluk oranının dayanağı' in s['uzun']
    assert 'ullage_fraction_basis' not in gorunen(s['uzun']).split('TANK_ULLAGE')[0]
    assert 'yeni_alan: x' in gorunen(s['bilinmeyen'])          # tanınmayan: HAM
    assert 'Kriyojenik uygunluk: gerekmiyor' in s['kriyo']
    assert 'cryogenic_suitability' not in gorunen(s['kriyo'])
    assert 'garip' in s['kriyo_tanimsiz']                       # tanınmayan hüküm HAM


@node_gerekli
def test_anlamli_basamak_ve_kanal_olcusu():
    html = _oku(SABLON)
    i = html.index('const LIQ_ANLAMLI_BASAMAK')
    fn = (html[i:html.index('function liqAnlamliTxt', i)]
          + _islev(html, 'function liqAnlamliTxt(v, taban, unit)')
          + '\n' + _islev(html, 'function liqKanalOlcusu(ham)'))
    betik = (_TR_DUZENEK % '{}') + fn + r"""
process.stdout.write(JSON.stringify([
  liqAnlamliTxt(0.512, 0), liqAnlamliTxt(1.03, 0), liqAnlamliTxt(52.3, 0),
  liqAnlamliTxt(834.2, 0), liqAnlamliTxt(0.00118, 1, 'm³'), liqAnlamliTxt(4.8, 1, 'kg'),
  liqAnlamliTxt(0, 0), liqAnlamliTxt(null, 0),
  liqKanalOlcusu('3.0 mm x 2.0 mm'), liqKanalOlcusu('garip'), liqKanalOlcusu(null)]));
"""
    s = _node(betik)
    assert s[:8] == ['0,512', '1,03', '52,3', '834', '0,0012 m³', '4,80 kg', '0', '—'], s
    assert s[8:] == ['3,0 mm × 2,0 mm', 'garip', '—'], s


@node_gerekli
def test_otojen_gerekcesi_secicinin_adiyla(tr_sozluk):
    html = _oku(SABLON)
    fn = _islev(html, 'function liqOtojenGerekce(gerekce)')
    betik = (_TR_DUZENEK % json.dumps(tr_sozluk)) + r"""
function _liqAdi(sel, v) { return ({fuel_type: {rp1: 'RP-1 (Kerosen)'}, oxidizer_type: {lox: 'LOX'}})[sel][v] || v; }
""" + fn + r"""
process.stdout.write(JSON.stringify([
  liqOtojenGerekce("autogenous pressurisation is modelled only for methane/LOX and LH2/LOX; 'rp1/lox' is not supported (the other propellants use stored helium)"),
  liqOtojenGerekce('autogenous pressurisation belongs to turbopump cycles; a pressure-fed system has no pump to tap and uses a separate stored pressurant'),
  liqOtojenGerekce('yeni bir gerekçe')]));
"""
    s = _node(betik)
    assert 'RP-1 (Kerosen) / LOX desteklenmiyor' in s[0] and "'rp1/lox'" not in s[0], s[0]
    assert s[1].startswith('otojen basınçlandırma turbopompalı çevrimlere aittir'), s[1]
    assert s[2] == 'yeni bir gerekçe'


# ---------------------------------------------------------------------------
# 8. Çözücü dizeleri ⟷ sayfa çevirileri
# ---------------------------------------------------------------------------
def test_imalat_surecleri_cozucunun_tablosuyla_ayni():
    from hrma.engines import liquid_rocket_engine as lre
    html = _oku(SABLON)
    govde = _islev(html, 'function displayManufacturingInfo(mfgData)')
    dizeler = set(lre.CHAMBER_PROCESS_BY_COOLING.values()) | {lre.CHAMBER_PROCESS_DEFAULT}
    dizeler |= set(lre.NOZZLE_PROCESS_BY_COOLING.values()) | {lre.NOZZLE_PROCESS_DEFAULT}
    dizeler |= set(lre.INJECTOR_PROCESS_BY_TYPE.values()) | {lre.INJECTOR_PROCESS_DEFAULT}
    eksik = [d for d in sorted(dizeler) if "'%s': T('liq.js.mfg_" % d not in govde]
    assert not eksik, 'çözücünün imalat dizesi sayfada çevrilmiyor: %s' % eksik
    assert lre.MANUFACTURING_COST_STATUS.startswith('not calculated')


def test_cozucunun_cevrilen_cumleleri_degismedi():
    motor = _oku(MOTOR)
    assert "f'Liquid Motor ({self.fuel_type}/{self.oxidizer_type}) - Design Summary'" in motor
    assert ("f'{\"optimised\" if eniyilemeler else \"sized\"} for the given '" in motor
            and "f'T/W={thrust_to_weight:.1f}, Isp(vac)={actual_isp_vac:.0f} s, '" in motor)
    assert "'autogenous pressurisation belongs to turbopump '" in motor
    assert "'autogenous pressurisation is modelled only for methane/LOX '" in motor
    assert "f\"{cooling.get('channel_width_mm', 0):.1f} mm x \"" in motor
    assert "'the design-wall heat flux CANNOT be carried by the '" in motor
    from hrma.engines import liquid_rocket_engine as lre
    assert lre.SAFETY_FACTOR_SOURCE_USER == 'user input (safety factor)'


@node_gerekli
def test_ciddiyet_oneki_iki_kez_basilmaz(tr_sozluk):
    """9 Kas ek 2: 'KRİTİK KRİTİK:' — hükmün kendi öneki etikete taşınır."""
    fn = _islev(_oku(SABLON), 'function liqCiddiyetAyir(metin)')
    betik = (_TR_DUZENEK % json.dumps(tr_sozluk)) + fn + r"""
process.stdout.write(JSON.stringify([
  liqCiddiyetAyir('KR\u0130T\u0130K: tepe sıcak cidar 1400 K'),
  liqCiddiyetAyir('CRITICAL: peak hot-wall temperature 1400 K'),
  liqCiddiyetAyir('UNSAFE: equilibrium wall'),
  liqCiddiyetAyir('öneksiz hüküm')]));
"""
    s = _node(betik)
    assert s[0] == {'etiket': 'KRİTİK', 'govde': 'tepe sıcak cidar 1400 K'}, s[0]
    assert s[1] == {'etiket': 'CRITICAL', 'govde': 'peak hot-wall temperature 1400 K'}, s[1]
    assert s[2]['etiket'] == 'UNSAFE' and s[2]['govde'] == 'equilibrium wall'
    assert s[3] == {'etiket': tr_sozluk['liq.msg.critical_warning_tag'], 'govde': 'öneksiz hüküm'}, s[3]
