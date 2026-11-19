"""3.0.7 ÇALKANTI-ARAYÜZ (KARTLAR K5) — tank çalkantı modelinin ekran ve
araç ekibine aktarım görünümü.

Tasarım: ``docs/tasarim/v307/CALKANTI_6DOF_TASARIM.md`` §A.3 (tek başına
motor/tank görünümü), §A.4 (SP-8009 yükleri), §A.5 (bafl önerisi), §A.6
(aktarım tablosu); ``TANK_GEOMETRI_TASARIM.md`` §F (sözleşme).

Bu modül SAYI ÜRETMEZ; yalnız bileştirir:

* eşdeğer model tablosu yalnız TEK GİRİŞTEN
  (``slosh_analysis.esdeger_model_tablosu``; K6);
* tank kaydı, yüklenen sıvı, yoğunluk, viskozite ve m(t) serisi motorun
  kendi sonucundan, K4 bağlantısıyla
  (``slosh_motor_baglanti.slosh_tanklari``);
* doluluk × g_eff frekans haritası, iki genlik düzeyinde SP-8009 yükleri,
  düz çeper sönümü ve Miles bafl önerisi K1'in işlevlerinden
  (``geff_frekans_haritasi``, ``silindir_yukleri``, ``duz_ceper_sonumu``,
  ``CylindricalTankSlosh.recommend_baffle`` / ``baffle_damping``);
* zaman ekseni sözleşmenin ara değeriyle (``SloshTablo.ara``).

Okunamayan ya da tutmayan büyüklük adlı kodla "hesaplanmadı" olur; yedek
sayı, uydurma konum ya da yaklaşık sonuç yok.

Girdi kapıları (adlı ret, :class:`CalkantiArayuzHatasi`): bilinmeyen alan,
motor türü, g_eff (sonlu, pozitif; tek değer ya da [en küçük, en büyük]),
yöntem, tank geometrisi (tank kimliği, profil nokta sınırı, dosya adı, sha256,
beyan kodu). Motor sonucunun kendisi K4'ün kapılarından geçer.
"""

from __future__ import annotations

import csv
import inspect
import io
import json
import math
import numbers
import re

import numpy as np

from hrma.analysis import slosh_analysis as _sa
from hrma.analysis import slosh_motor_baglanti as _k4
from hrma.analysis import slosh_tablo as _tablo
from hrma.analysis import six_dof_slosh as _k2
from hrma.constants import G_0, MOTOR_TYPES

# ---------------------------------------------------------------------------
# Sabitler — TEK TANIM YERİ
# ---------------------------------------------------------------------------
GORUNUM_SEMASI = 'hrma.calkanti_tank_modeli'
GORUNUM_SURUMU = 'v307-k5-1'
#: Araç ekibine aktarım dosyasının şema kimliği (§A.6). Eşdeğer model
#: tablosu dosyanın içinde sözleşmenin kendi şemasıyla (``slosh_tablo``)
#: durur; bu kimlik zarfı ve zaman eksenini tanıtır.
AKTARIM_SEMASI = 'calkanti_arac_aktarim_tablosu'
AKTARIM_SURUMU = 'v307-k5-1'

#: g_eff aralığı verildiğinde haritanın g_eff nokta sayısı (uçlar dahil,
#: eşit aralıklı). HRMA seçimi: 0,1 g adımlı bir 1–2 g taraması kadar
#: çözünürlük; üst sınır K1'in GEFF_HARITA_NOKTA_SINIRI'dır.
GEFF_ARALIK_NOKTA_SAYISI = 11
assert 2 <= GEFF_ARALIK_NOKTA_SAYISI <= _sa.GEFF_HARITA_NOKTA_SINIRI

#: İstek bloğunun alanları (başka alan reddedilir).
ISTEK_ZORUNLU = ('motor_type',)
ISTEK_ISTEGE_BAGLI = ('motor_sonucu', 'g_eff_m_s2', 'yontem',
                      'tank_geometrileri')
# Motor türleri: TEK KAYNAK ``hrma.constants.MOTOR_TYPES`` (yerel kopya
# yok; test_sabit_tek_kaynak). Üyelik aynı, hata metnindeki sıra merkezin.

#: Yüklenen tank geometrisinin istek içindeki alanları (yükleme ucunun
#: yanıtından gelir; profil sunucuda B.4 kapısından YENİDEN geçer).
YUKLENEN_GEOMETRI_ZORUNLU = ('profil_rz_m',)
YUKLENEN_GEOMETRI_ISTEGE_BAGLI = ('dosya_adi', 'sha256', 'sebep')
DOSYA_ADI_BOY_SINIRI = 255
_SHA256_RE = re.compile(r'^[0-9a-f]{64}$')
_DOSYA_ADI_YASAK_RE = re.compile(r'[\x00-\x1f\x7f/\\]')

#: Motor görünümünde (tank yeri yok) anlamsız olan K4 sebebi: tankın araçtaki
#: yeri 6-DOF panelinde girilir; motor/tank görünümü yer istemez.
SEBEP_YER_YOK = 'TANK_ISTASYONU_VERILMEDI'

#: Bu modülün kendi "hesaplanmadı" kodları (sınıfları: BILGI).
K5_KODLARI = {
    'YUK_BAGINTISI_DIK_SILINDIR_ICIN': (
        'SP-8009 Denk. (4) basınç dağılımı ve Dodge (3.4b)/(3.5) yük '
        'bağıntıları düz tabanlı dik silindir içindir; bu tankın tablosu '
        'silindir kapalı biçiminden değil, yükler hesaplanmadı'),
    'BAFL_BAGINTISI_DIK_SILINDIR_ICIN': (
        'Miles (Dodge 2000 Denk. (2.16)) halka bafl bağıntısı dik silindir '
        'içindir; bafl önerisi hesaplanmadı'),
    'YUKLU_DOLULUK_IZGARA_DISI': (
        'yüklü doluluk tablonun ızgarası dışında ya da o satır RET; bafl '
        'önerisi yüklü dolulukta kurulamadı'),
    'ZAMAN_EKSENI_YOK': (
        'motor bu tankın tüketimini yayımlamıyor ya da tank kaydı tutarsız; '
        'zaman ekseni kurulmadı (sebep tank kodlarında)'),
    'CEPER_SONUMU_TEK_GEFF_ISTER': (
        'düz çeper sönümü g_eff\'e bağlıdır; g_eff aralık verildiğinden '
        'zaman ekseninde ω1 ve çeper sönümü yazılmadı (κ1 g\'den bağımsızdır, '
        'tüketici ω1 = √(κ1·g_eff) ile kendi ivmesinde hesaplar)'),
}

#: Kapsam dışı künyesi (§1, §B.6): K2'nin tek tanımı.
KAPSAM_DISI_KODU = _k2.KAPSAM_DISI_KODU
KAPSAM_DISI_GEREKCE = _k2.KAPSAM_DISI_GEREKCE

#: Eksen kuralı künyesi (§2.1) — aktarım dosyasına yazılır.
EKSEN_KURALI = (
    'Eksen kuralı (CALKANTI §2.1): tank çerçevesinde z tank simetri '
    'ekseni, sıfır tankın en alt iç noktası (itki altında etkin yerçekiminin '
    'gösterdiği uç, araçta kıç tarafı), z buruna doğru pozitif; bütün '
    'konumlar metre. Araç istasyonu x = x_tank_taban − z (burundan, kıça '
    'pozitif); tankın araçtaki yeri motor görünümünde yoktur, 6-DOF '
    'panelinde girilir. Tabloda frekans yerine κ1 = ω1²/g_eff [1/m] '
    'tutulur; ω1 = √(κ1·g_eff).')

#: Zaman ekseni sütunları (sıra = CSV sütun sırası) ve birimleri.
ZAMAN_SUTUNLARI = (
    ('t_s', 's'), ('m_sivi_kg', 'kg'), ('doluluk', '-'), ('h_m', 'm'),
    ('z_km_m', 'm'), ('I_km_donmus_kgm2', 'kg.m2'),
    ('I_eksenel_donmus_kgm2', 'kg.m2'), ('m1_kg', 'kg'), ('m0_kg', 'kg'),
    ('m1_oran', '-'), ('m0_oran', '-'), ('L1_m', 'm'), ('z1_m', 'm'),
    ('z_aski_m', 'm'), ('z0_m', 'm'), ('kappa1_1m', '1/m'),
    ('Gamma1', '-'), ('omega1_rad_s', 'rad/s'), ('f1_hz', 'Hz'),
    ('zeta_ceper', '-'), ('I0_kgm2', 'kg.m2'), ('I0_kaynak', '-'),
    ('durum', '-'), ('sebep', '-'),
)
_ZAMAN_METIN = ('I0_kaynak', 'durum')
CSV_ZAMAN_KIMLIGI = f'# {AKTARIM_SEMASI} {AKTARIM_SURUMU} zaman_ekseni'
CSV_META_ONEKI = _tablo.CSV_META_ONEKI


class CalkantiArayuzHatasi(ValueError):
    """İstek girdisi reddedildi (``kod`` ve ``alan`` adlı; HTTP 400)."""

    def __init__(self, mesaj, kod, alan=None):
        super().__init__(f'{alan}: {mesaj}' if alan else mesaj)
        self.kod = kod
        self.alan = alan

    def kunye(self):
        return {'field': self.alan, 'reason': self.kod, 'message': str(self)}


class MotorSonucuOkunamadi(ValueError):
    """Motor sonucu K4 tarafından okunamadı (biçim; HTTP 422)."""

    def __init__(self, tur):
        super().__init__('the motor result could not be read '
                         f'({tur}); nothing was computed')
        self.kod = 'MOTOR_SONUCU_OKUNAMADI'
        self.alan = 'motor_sonucu'


def _ret(kod, alan, mesaj):
    raise CalkantiArayuzHatasi(mesaj, kod, alan)


def _imza(islev, ad):
    """İmzadaki varsayılan (TEK KAYNAK; uçtaki ``_imza_varsayilani`` ile aynı)."""
    return inspect.signature(islev).parameters[ad].default


# ---------------------------------------------------------------------------
# Girdi kapıları
# ---------------------------------------------------------------------------
def _sonlu_pozitif(v, alan):
    if isinstance(v, (bool, np.bool_)) or not isinstance(v, numbers.Real):
        _ret('SAYI_DEGIL', alan, f'a finite positive number is required '
                                 f'({type(v).__name__} given)')
    v = float(v)
    if not (math.isfinite(v) and v > 0.0):
        _ret('ARALIK_DISI', alan, 'must be finite and > 0')
    return v


def geff_listesi(deger):
    """g_eff girdisi → (değerler, kaynak).

    ``None`` → [G_0] (beyanlı varsayılan); sayı → [g]; [g_min, g_max]
    (g_min < g_max) → eşit aralıklı ``GEFF_ARALIK_NOKTA_SAYISI`` değer.
    """
    if deger is None or deger == '':
        return [float(G_0)], 'varsayilan_g0'
    if isinstance(deger, (list, tuple)):
        if len(deger) != 2:
            _ret('BICIM', 'g_eff_m_s2', 'a range must be [g_min, g_max]')
        lo = _sonlu_pozitif(deger[0], 'g_eff_m_s2[0]')
        hi = _sonlu_pozitif(deger[1], 'g_eff_m_s2[1]')
        if not hi > lo:
            _ret('ARALIK_DISI', 'g_eff_m_s2', 'g_max must be greater than '
                                              'g_min')
        gs = np.linspace(lo, hi, GEFF_ARALIK_NOKTA_SAYISI).tolist()
        gs[0], gs[-1] = lo, hi
        return gs, 'aralik'
    return [_sonlu_pozitif(deger, 'g_eff_m_s2')], 'girdi'


def _geometri_kapisi(tg):
    """``tank_geometrileri`` → K4'ün ``tank_geometrileri`` girdisi."""
    if tg is None:
        return None, {}
    if not isinstance(tg, dict):
        _ret('TIP', 'tank_geometrileri', 'must be {tank_id: geometry}')
    k4, ozet = {}, {}
    for tid, g in tg.items():
        alan = f'tank_geometrileri.{tid}'
        if tid not in _tablo.TANK_KIMLIKLERI:
            _ret('TANK_KIMLIGI', 'tank_geometrileri',
                 f'unknown tank {str(tid)[:32]!r}')
        if not isinstance(g, dict):
            _ret('TIP', alan, 'must be a mapping')
        for k in g:
            if k not in YUKLENEN_GEOMETRI_ZORUNLU and k not in YUKLENEN_GEOMETRI_ISTEGE_BAGLI:
                _ret('ALAN_BILINMEYEN', f'{alan}.{str(k)[:32]}',
                     'unknown field')
        for k in YUKLENEN_GEOMETRI_ZORUNLU:
            if k not in g:
                _ret('ALAN_EKSIK', f'{alan}.{k}', 'required')
        prof = g['profil_rz_m']
        if (not isinstance(prof, list)
                or len(prof) > _tablo.PROFIL_NOKTA_SINIRI):
            _ret('BICIM', f'{alan}.profil_rz_m',
                 f'must be a list of at most {_tablo.PROFIL_NOKTA_SINIRI} '
                 '[r, z] pairs')
        ad = g.get('dosya_adi')
        if ad is not None and (not isinstance(ad, str) or not ad.strip()
                               or len(ad) > DOSYA_ADI_BOY_SINIRI
                               or _DOSYA_ADI_YASAK_RE.search(ad)):
            _ret('BICIM', f'{alan}.dosya_adi', 'must be a plain file name')
        sha = g.get('sha256')
        if sha is not None and (not isinstance(sha, str)
                                or not _SHA256_RE.match(sha)):
            _ret('BICIM', f'{alan}.sha256', 'must be 64 lowercase hex digits')
        sebep = g.get('sebep') or []
        if not isinstance(sebep, list) or any(
                not isinstance(s, str) or s not in _tablo.SEBEP_KODLARI
                or _tablo.SEBEP_KODLARI[s][0] != _tablo.SINIF_BEYAN
                for s in sebep):
            _ret('BICIM', f'{alan}.sebep',
                 'only declaration-class contract codes are accepted')
        kunye = {}
        if ad is not None:
            kunye['dosya_adi'] = ad
        if sha is not None:
            kunye['sha256'] = sha
        k4[tid] = {'tur': _sa.TANK_TURU_GEOMETRI_SONUCU,
                   'sonuc': {'durum': _tablo.durum_birlestir(list(sebep)),
                             'sebep': list(sebep), 'profil_rz_m': prof,
                             'kunye': kunye}}
        ozet[tid] = kunye
    return k4, ozet


def istek_kapisi(istek):
    """``tank_modeli`` istek bloğunu denetler; normalleştirilmiş sözlük."""
    if not isinstance(istek, dict):
        _ret('TIP', 'tank_modeli', 'must be a JSON object')
    for k in istek:
        if k not in ISTEK_ZORUNLU and k not in ISTEK_ISTEGE_BAGLI:
            _ret('ALAN_BILINMEYEN', f'tank_modeli.{str(k)[:32]}',
                 'unknown field')
    for k in ISTEK_ZORUNLU:
        if k not in istek:
            _ret('ALAN_EKSIK', f'tank_modeli.{k}', 'required')
    mt = istek['motor_type']
    if mt not in MOTOR_TYPES:
        _ret('MOTOR_TURU', 'tank_modeli.motor_type',
             f'must be one of {MOTOR_TYPES}')
    yontem = istek.get('yontem') or _sa.YONTEM_SECIMI_OTOMATIK
    if yontem not in _sa.YONTEM_SECIMLERI:
        _ret('YONTEM', 'tank_modeli.yontem',
             f'must be one of {_sa.YONTEM_SECIMLERI}')
    gs, g_kaynak = geff_listesi(istek.get('g_eff_m_s2'))
    tg_k4, tg_ozet = _geometri_kapisi(istek.get('tank_geometrileri'))
    sonuc = istek.get('motor_sonucu')
    if mt == 'solid':
        if tg_k4:
            _ret('TANK_YOK', 'tank_modeli.tank_geometrileri',
                 'a solid motor has no liquid tank')
    elif not isinstance(sonuc, dict):
        _ret('ALAN_EKSIK', 'tank_modeli.motor_sonucu',
             'the motor result of the page is required for a liquid or '
             'hybrid motor')
    return {'motor_type': mt, 'motor_sonucu': sonuc, 'yontem': yontem,
            'g_eff': gs, 'g_eff_kaynagi': g_kaynak,
            'tank_geometrileri': tg_k4, 'geometri_kunyesi': tg_ozet}


# ---------------------------------------------------------------------------
# Görünüm parçaları
# ---------------------------------------------------------------------------
def _silindir_kapali_bicim_mi(tablo):
    return (tablo.geometri['tur'] == _tablo.GEOMETRI_DIK_SILINDIR
            and tablo.yontem == _tablo.YONTEM_KAPALI_BICIM)


def zaman_ekseni(tablo, m_t, g_tek=None, nu=None):
    """Motorun m(t) serisinden zaman ekseni satırları (§A.6).

    Satırlar serinin noktalarıdır; seri parça parça doğrusaldır (6-DOF'un
    ``np.interp`` kuralı, K2) ve doluluğun ızgara düğümlerini kestiği anlar
    eklenir (düğümde satır tablonun kendi değeridir). Her satırın model
    alanları ``SloshTablo.ara`` ile; m1, m0 kütleleri oranlardan; ω1 ve
    düz çeper sönümü yalnız tek g_eff verildiyse (çeper sönümü yalnız düz
    tabanlı dik silindirde ve ν varsa).
    """
    ts = [float(x) for x in m_t['t']]
    ms = [float(x) for x in m_t['m']]
    rho = tablo.sivi['rho_kg_m3']
    V = tablo.geometri['V_ic_m3']
    R = tablo.geometri['R_ref_m']
    silindir = _silindir_kapali_bicim_mi(tablo)
    noktalar = [(t, m, None) for t, m in zip(ts, ms)]
    for (t0, m0), (t1, m1) in zip(zip(ts, ms), zip(ts[1:], ms[1:])):
        if m1 == m0:
            continue
        for d in _tablo.DOLULUK_IZGARASI:
            mk = d * rho * V
            if (m0 - mk) * (m1 - mk) < 0.0:
                noktalar.append((t0 + (mk - m0) * (t1 - t0) / (m1 - m0),
                                 mk, d))
    noktalar.sort(key=lambda p: (p[0], p[2] is None))
    satirlar = []
    for t, m, d_dugum in noktalar:
        if satirlar and t == satirlar[-1]['t_s']:
            continue
        d = d_dugum if d_dugum is not None else tablo.doluluk_kutleden(m)
        s = tablo.ara(d)
        r = {'t_s': t, 'm_sivi_kg': m, 'doluluk': d}
        for k in ('h_m', 'z_km_m', 'I_km_donmus_kgm2',
                  'I_eksenel_donmus_kgm2', 'm1_oran', 'm0_oran', 'L1_m',
                  'z1_m', 'z_aski_m', 'z0_m', 'kappa1_1m', 'Gamma1',
                  'I0_kgm2', 'I0_kaynak'):
            r[k] = s.get(k)
        r['m1_kg'] = None if s.get('m1_oran') is None else s['m1_oran'] * m
        r['m0_kg'] = None if s.get('m0_oran') is None else s['m0_oran'] * m
        r['omega1_rad_s'] = r['f1_hz'] = r['zeta_ceper'] = None
        if g_tek is not None and s.get('kappa1_1m') is not None:
            w = _tablo.omega1(s['kappa1_1m'], g_tek)
            r['omega1_rad_s'] = w
            r['f1_hz'] = w / (2.0 * math.pi)
            if silindir and nu is not None and s.get('h_m'):
                r['zeta_ceper'] = _sa.duz_ceper_sonumu(R, s['h_m'], nu, g_tek)
        r['durum'] = s['durum']
        r['sebep'] = list(s['sebep'])
        satirlar.append(r)
    return satirlar


def yukler(tablo, g):
    """İki genlik düzeyinde SP-8009 yükleri, doluluk ızgarasında (§A.4)."""
    if not _silindir_kapali_bicim_mi(tablo):
        return {'durum': 'HESAPLANMADI',
                'sebep': ['YUK_BAGINTISI_DIK_SILINDIR_ICIN']}
    R = tablo.geometri['R_ref_m']
    rho = tablo.sivi['rho_kg_m3']
    duzeyler = ('dogrusal_sinir', 'kirilma_ust_siniri')
    alanlar = ('eta_ceper_m', 'x1_m', 'F1_N', 'M1_km_Nm',
               'p_dinamik_yuzey_Pa', 'p_taban_Pa')
    out = {'durum': 'HESAPLANDI', 'g_eff_m_s2': g, 'doluluk': [],
           'duzeyler': {d: {a: [] for a in alanlar + ('sebep',)}
                        for d in duzeyler}}
    for s in tablo.satirlar:
        if s['durum'] == _tablo.DURUM_RET:
            continue
        y = _sa.silindir_yukleri(R, s['h_m'], rho, g)
        out['doluluk'].append(s['doluluk'])
        for d in duzeyler:
            for a in alanlar:
                out['duzeyler'][d][a].append(y['duzeyler'][d][a])
            out['duzeyler'][d]['sebep'].append(y['duzeyler'][d]['sebep'])
    return out


def bafl_onerisi(tablo, d0):
    """Yüklü dolulukta tek halka bafl önerisi ve ×2 bandı (§A.5)."""
    if not _silindir_kapali_bicim_mi(tablo):
        return {'durum': 'HESAPLANMADI',
                'sebep': ['BAFL_BAGINTISI_DIK_SILINDIR_ICIN']}
    s = tablo.ara(d0) if d0 is not None else None
    if s is None or s['durum'] == _tablo.DURUM_RET or not s.get('h_m'):
        return {'durum': 'HESAPLANMADI',
                'sebep': ['YUKLU_DOLULUK_IZGARA_DISI']}
    R = tablo.geometri['R_ref_m']
    derinlik = _imza(_sa.CylindricalTankSlosh.analyze, 'baffle_depth_ratio')
    ts = _sa.CylindricalTankSlosh(R, s['h_m'])
    oneri = ts.recommend_baffle(depth_ratio=derinlik)
    out = {'durum': 'HESAPLANDI', 'doluluk': d0, 'h_m': s['h_m'],
           'derinlik_orani': derinlik,
           'derinlik_orani_kaynagi': 'CylindricalTankSlosh.analyze '
                                     '(baffle_depth_ratio varsayılanı)',
           'oneri': oneri, 'degerlendirme': None}
    if oneri['achievable_with_single_baffle'] and \
            oneri['recommended_width_ratio'] > 0.0:
        out['degerlendirme'] = ts.baffle_damping(
            oneri['recommended_width_ratio'], derinlik,
            amplitude_ratio=oneri['amplitude_ratio'])
    return out


#: Motor/tank görünümünün zaman eksenine giren K4 tüketim beyanları. Yer
#: kodları ve 6-DOF'a özgü kodlar (bafl sönümü, ρ(t) serisi) bu görünümün
#: beyanı değildir: görünümün doluluk ekseni ateşleme yoğunluğuyla kurulur
#: (``zaman_ekseni``), o yüzden yoğunluk beyanı burada ``YOGUNLUK_SABIT``tir.
TUKETIM_BEYANLARI = ('TUKETIM_SABIT_DEBI', 'TUKETIM_BOSALMA_COZUMU')


def _tuketim_beyani(r):
    """Motor görünümünde tüketim beyanı: K4'ün tank raporundaki tüketim
    kodu AYNEN (V307/UÇUŞ-GÖVDE: K4 beyanı bağlanmayan tankta da yayımlıyor;
    seri kaynağı metninden yeniden türetme kalktı)."""
    if not r.get('m_t'):
        return []
    return ['YOGUNLUK_SABIT'] + [b for b in (r.get('beyan') or [])
                                 if b in TUKETIM_BEYANLARI]


def _tank_gorunumu(mt, r, istek):
    g_list = istek['g_eff']
    g_tek = g_list[0] if len(g_list) == 1 else None
    sebep = [k for k in r['sebep'] if k != SEBEP_YER_YOK]
    out = {
        'tank_id': r['tank_id'], 'motor_anahtari': r['motor_anahtari'],
        'sivi_adi': r['sivi_adi'], 'rho_kg_m3': r['rho_kg_m3'],
        'rho_kaynagi': r['rho_kaynagi'], 'nu_m2_s': r['nu_m2_s'],
        'nu_kaynagi': r['nu_kaynagi'],
        'yuklenen_sivi_kg': r['yuklenen_sivi_kg'],
        'yuklu_doluluk': r.get('yuklu_doluluk'),
        'f1_hz_1g': r.get('f1_hz_1g'),
        'motor_bafl_sonumu_tam_doluluk':
            r.get('motor_bafl_sonumu_tam_doluluk'),
        'sebep': sebep, 'beyan': [], 'tablo_yolu': r.get('tablo_yolu'),
        'geometri': r.get('geometri'),
        'geometri_girdisi': r.get('geometri_girdisi'),
        'geometri_dosyasi': istek['geometri_kunyesi'].get(r['tank_id']),
        'yontem': None, 'oneri_yontem': None, 'satir_durumlari': None,
        'tablo': None, 'zaman': None, 'frekans_haritasi': None,
        'yukler': None, 'bafl': None,
    }
    # V307/UÇUŞ-GÖVDE (K4 DEVİR kapandı): tablo K4'ün AYNI çağrıda kurduğu
    # nesnedir; ikinci kez kurulmaz (SE yolunda ~2,5 s çift hesaptı).
    tablo = r.get('tablo')
    if tablo is None:
        return out, None
    out['yontem'] = tablo.yontem
    out['oneri_yontem'] = r.get('oneri_yontem')
    out['satir_durumlari'] = r.get('satir_durumlari')
    out['tablo'] = tablo.sozluk()
    out['frekans_haritasi'] = _sa.geff_frekans_haritasi(tablo, g_list)
    out['yukler'] = yukler(tablo, max(g_list))
    out['bafl'] = bafl_onerisi(tablo, out['yuklu_doluluk'])
    if r.get('m_t') and not sebep:
        out['beyan'] = _tuketim_beyani(r)
        zaman = zaman_ekseni(tablo, r['m_t'], g_tek, r['nu_m2_s'])
        out['zaman'] = {
            'kaynak': r.get('seri_kaynagi'),
            'g_eff_m_s2': g_tek,
            'sebep': ([] if g_tek is not None
                      else ['CEPER_SONUMU_TEK_GEFF_ISTER']),
            'satirlar': zaman,
        }
    else:
        out['zaman'] = {'kaynak': None, 'g_eff_m_s2': g_tek,
                        'sebep': ['ZAMAN_EKSENI_YOK'], 'satirlar': []}
    return out, tablo


def tank_modeli(istek_ham):
    """``/api/slosh-analysis`` ``tank_modeli`` bloğu → görünüm sözlüğü.

    Dönüş: ``(gorunum, tablolar)``; ``tablolar`` {tank_id: SloshTablo}
    (dışa aktarım aynı nesnelerden yazılır).
    """
    istek = istek_kapisi(istek_ham)
    mt = istek['motor_type']
    temel = {'sema': GORUNUM_SEMASI, 'sema_surumu': GORUNUM_SURUMU,
             'motor_type': mt, 'g_eff_m_s2': istek['g_eff'],
             'g_eff_kaynagi': istek['g_eff_kaynagi'],
             'yontem_secimi': istek['yontem'],
             'kapsam_disi': {'kod': KAPSAM_DISI_KODU,
                             'gerekce': KAPSAM_DISI_GEREKCE}}
    if mt == 'solid':
        return dict(temel, durum=_k4.DURUM_UYGULANMAZ, sebep=['TANK_YOK'],
                    tanklar=[], kutle_denetimi=None,
                    kunye=[_k4.KODLAR['TANK_YOK'][1]]), {}
    try:
        k4 = _k4.slosh_tanklari(mt, istek['motor_sonucu'],
                                tank_geometrileri=istek['tank_geometrileri'],
                                yontem=istek['yontem'])
    except _k4.SloshMotorBaglantiHatasi:
        raise
    except (TypeError, ValueError, KeyError, AttributeError,
            IndexError) as exc:
        raise MotorSonucuOkunamadi(type(exc).__name__) from None
    tanklar, tablolar = [], {}
    for r in k4['tanklar']:
        g, tablo = _tank_gorunumu(mt, r, istek)
        tanklar.append(g)
        if tablo is not None:
            tablolar[r['tank_id']] = tablo
    hazir = [t for t in tanklar if t['tablo'] is not None]
    durum = ('HESAPLANDI' if len(hazir) == len(tanklar) else
             'KISMI' if hazir else 'HESAPLANMADI')
    sebep = []
    for t in tanklar:
        sebep.extend(k for k in t['sebep'] if k not in sebep)
    return dict(temel, durum=durum, sebep=sebep, tanklar=tanklar,
                kutle_denetimi=k4['kutle_denetimi'],
                kunye=[_k4.KUNYE]), tablolar


# ---------------------------------------------------------------------------
# Dışa aktarım (araç ekibine aktarım tablosu, §A.6)
# ---------------------------------------------------------------------------
DISA_AKTARIM_BICIMLERI = ('json', 'csv_doluluk', 'csv_zaman')


def _aktarim_kunyesi(gorunum, tank):
    k = [f'HRMA {AKTARIM_SEMASI} {AKTARIM_SURUMU}; motor türü '
         f'{gorunum["motor_type"]}; tank {tank["tank_id"]} '
         f'({tank["sivi_adi"]})',
         f'Yöntem: {tank["yontem"]} (yol {tank["tablo_yolu"]})',
         f'Kapsam dışı ({KAPSAM_DISI_KODU}): {KAPSAM_DISI_GEREKCE}',
         EKSEN_KURALI, _k4.KUNYE,
         f'Yoğunluk: {tank["rho_kaynagi"]}']
    if tank.get('nu_kaynagi'):
        k.append(f'Viskozite: {tank["nu_kaynagi"]}')
    z = tank.get('zaman') or {}
    if z.get('kaynak'):
        k.append(f'm(t): {z["kaynak"]}; zaman ekseni serinin noktaları + '
                 'doluluğun ızgara düğümlerini kestiği anlar (seri parça '
                 'parça doğrusal)')
    for kod in tank['beyan']:
        k.append(f'BEYAN {kod}: {_k4.KODLAR[kod][1]}')
    for kod in tank['sebep']:
        gerekce = (_k4.KODLAR.get(kod) or (None, kod))[1]
        k.append(f'SEBEP {kod}: {gerekce}')
    for kod in z.get('sebep') or []:
        k.append(f'NOT {kod}: {K5_KODLARI[kod]}')
    gd = tank.get('geometri_dosyasi')
    if gd:
        k.append('Tank geometrisi dosyası: '
                 f'{gd.get("dosya_adi", "-")} (sha256 {gd.get("sha256", "-")})')
    return k


def _tablo_kunyeli(tablo, ek):
    v = tablo.sozluk()
    v['kunye'] = list(v.get('kunye', [])) + list(ek)
    return _tablo.SloshTablo.sozlukten(v)


def disa_aktarim(gorunum, tablolar, tank_id, bicim):
    """(dosya adı, MIME türü, metin). Dosya sözleşme okuyucusuyla geri
    okunabilir: JSON'daki tablo ``slosh_tablo.dogrula``dan, doluluk CSV'si
    ``slosh_tablo.csv_oku``dan geçer."""
    if bicim not in DISA_AKTARIM_BICIMLERI:
        _ret('BICIM', 'disa_aktarim.bicim',
             f'must be one of {DISA_AKTARIM_BICIMLERI}')
    tank = next((t for t in gorunum['tanklar'] if t['tank_id'] == tank_id),
                None)
    if tank is None or tank_id not in tablolar:
        _ret('TANK_TABLOSU_YOK', 'disa_aktarim.tank_id',
             'no equivalent-model table was computed for this tank')
    kunye = _aktarim_kunyesi(gorunum, tank)
    tablo = _tablo_kunyeli(tablolar[tank_id], kunye)
    ad = f'HRMA_calkanti_{gorunum["motor_type"]}_{tank_id}'
    zaman = tank['zaman'] or {}
    if bicim == 'csv_doluluk':
        return ad + '_doluluk.csv', 'text/csv', _tablo.csv_yaz(tablo)
    if bicim == 'csv_zaman':
        meta = {'sema': AKTARIM_SEMASI, 'sema_surumu': AKTARIM_SURUMU,
                'tank_id': tank_id, 'motor_type': gorunum['motor_type'],
                'g_eff_m_s2': zaman.get('g_eff_m_s2'),
                'birimler': dict(ZAMAN_SUTUNLARI),
                'tablo_kimligi': {k: tablo.sozluk()[k] for k in (
                    'sema', 'sema_surumu', 'yontem', 'geometri', 'sivi')},
                'kunye': kunye}
        tampon = io.StringIO()
        tampon.write(CSV_ZAMAN_KIMLIGI + '\n')
        tampon.write(CSV_META_ONEKI + json.dumps(
            meta, ensure_ascii=False, allow_nan=False) + '\n')
        w = csv.writer(tampon, lineterminator='\n')
        w.writerow([s for s, _ in ZAMAN_SUTUNLARI])
        for r in zaman.get('satirlar') or []:
            satir = []
            for k, _b in ZAMAN_SUTUNLARI:
                v = r.get(k)
                if v is None:
                    satir.append('')
                elif k == 'sebep':
                    satir.append(';'.join(v))
                elif k in _ZAMAN_METIN:
                    satir.append(v)
                else:
                    satir.append(repr(float(v)))
            w.writerow(satir)
        return ad + '_zaman.csv', 'text/csv', tampon.getvalue()
    paket = {
        'sema': AKTARIM_SEMASI, 'sema_surumu': AKTARIM_SURUMU,
        'motor_type': gorunum['motor_type'], 'tank_id': tank_id,
        'kunye': kunye, 'beyan': list(tank['beyan']),
        'sebep': list(tank['sebep']),
        'kapsam_disi': gorunum['kapsam_disi'],
        'esdeger_model_tablosu': tablo.sozluk(),
        'zaman_ekseni': {
            'g_eff_m_s2': zaman.get('g_eff_m_s2'),
            'kaynak': zaman.get('kaynak'),
            'sebep': list(zaman.get('sebep') or []),
            'birimler': dict(ZAMAN_SUTUNLARI),
            'satirlar': zaman.get('satirlar') or [],
        },
    }
    metin = json.dumps(paket, ensure_ascii=False, allow_nan=False, indent=1)
    return ad + '_aktarim.json', 'application/json', metin
