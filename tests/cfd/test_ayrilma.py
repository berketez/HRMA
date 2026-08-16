# tests/cfd — CFD duvar basıncı → Summerfield ayrılma hükmü bekçileri (1B)
"""
``hrma.cfd.separation.assess_separation`` sözleşmesi ve hükmü.

İKİ KATMAN
----------
1) Sentetik duvar basıncı profilleri: ölçüt, arama bölgesi (yanlış pozitif
   kapısı), girdi denetimleri ve hüküm/doğrulama ayrımı — çözücü koşmadan.
   Beklenen istasyon ELLE TASARLANIR (profil değerleri seçilirken hangi
   istasyonun eşiği geçtiği bellidir), koddaki ifade tekrar edilmez.
2) GERÇEK çözücü koşusu: conftest.sok_cozumu (aşırı-genişlemiş, iç normal
   şoklu vaka; 120×24) YENİDEN KULLANILIR — süit disiplini gereği ikinci bir
   pahalı koşu açılmaz. Ayrılma istasyonu, testin kendi kurduğu analitik
   beklentiyle (izantropik ses-üstü dalda p_w(z) = k·P_ortam kökü)
   karşılaştırılır. Analitik dalın geçerliliği testin kendi içinde
   doğrulanır: kök, analitik şok konumunun YUKARISINDA olmalıdır.

ÖLÇÜLDÜ (bu depo, M4 Max, 2026-08-16; sok_cozumu ayarları, P_ortam = Pb =
2,75 MPa, k = 0,40 → eşik 1,10 MPa):
  analitik kök z_sep = 0,172415 m; analitik şok z_s = 0,209862 m (kök şokun
    yukarısında — izantropik dal geçerli)
  CFD ilk ayrılmış istasyon: index 68, z = 0,171252 m, p_w = 1,08575 MPa
    (bir önceki istasyon 1,12845 MPa — eşik bu ikisinin arasında)
  |z_CFD − z_analitik| = 1,16 mm  (eksenel hücre 2,5 mm → 0,47 hücre)
  |z_ara değer − z_analitik| = 2,00 mm (0,80 hücre)
  eşik altı istasyon 15/71; min p_w/eşik = 0,588; çıkış p_w = 2,753 MPa
    (şok ardında eşiğin üstüne dönüyor → reattachment_suspected beyanı)
Eşik = ölçüm × ~2,5 payı (2 eksenel hücre).

MUTASYON KANITI (elle uygulandı, kırmızı ÖLÇÜLDÜ, geri alındı; md5'ler
hrma/cfd/separation.py dosyasına ait — sağlam sürüm
ec226285b03883642ef32f144160942a):
  M1 "hüküm ters": ``below = p_div < threshold`` → ``p_div > threshold``
     (mutant md5 de5f7c69e98262c4288ae311d009ba8b)
     → 9 test KIRMIZI (24 yeşil): test_tam_akis_ayrilmaz,
       test_asiri_genisleme_ayrilma_istasyonu,
       test_ayrilma_istasyonu_esigi_gercekten_asiyor,
       test_arama_bolgesi_iraksakla_sinirli,
       test_bogaz_istasyonu_arama_disinda,
       test_bogaz_index_geometriden_turetilir,
       test_gercek_cozum_ayrilma_istasyonu, test_gercek_cozum_beyanlari,
       test_gercek_cozum_dusuk_ortamda_ayrilmaz.
  M2 "k kopyala-sabitle": ``factor = float(SEPARATION_FACTOR_DEFAULT)`` →
     ``factor = 0.40`` (ithal yerine kopya sabit; DEĞER AYNI — hüküm
     sayısal olarak değişmez, bu yüzden ölçüt testleri yeşil kalır)
     (mutant md5 2492f56e65622468f173c7db216a5064)
     → 2 test KIRMIZI (31 yeşil): test_varsayilan_k_ithal_ediliyor
       (monkeypatch'lenen ithal sabit artık hükme geçmiyor),
       test_kaynakta_kopya_sabit_yok (kaynakta çıplak bant sabiti belirdi).
     Bu ikisi olmasa "değeri aynı kopya" sessizce geçerdi — kopya yasağının
     bekçisi ölçüt testleri DEĞİL, bu ikilidir.
  Her iki mutasyondan sonra dosya md5 ec226285b03883642ef32f144160942a
  değerine bit-özdeş geri kondu.
"""

import re
from pathlib import Path

import numpy as np
import pytest
from scipy.optimize import brentq

from hrma.analysis.nozzle_flow_1d import (
    SEPARATION_FACTOR_DEFAULT,
    SEPARATION_FACTOR_MAX,
    SEPARATION_FACTOR_MIN,
)
from hrma.cfd import separation as cfd_sep
from hrma.cfd.separation import assess_separation
from hrma.flow.separation import (
    SUMMERFIELD_FACTOR_DEFAULT,
    summerfield_pressure_ratio,
)

from .conftest import (
    LULE_GAMMA, LULE_L_CONV, LULE_L_DIV, LULE_P0, LULE_PB_SOK,
    LULE_R_THROAT, lule_duvar_yaricapi,
)
from .test_normal_sok import (
    _izantropik_p_orani, _mach_alandan, analitik_sok_konumu,
)

# Eşik ÖLÇÜMDEN: konum farkı 1,16 mm / 2,00 mm ölçüldü, eksenel hücre
# 2,5 mm → 2 hücre payı bırakıldı.
AYRILMA_KONUM_TOL_M = 5.0e-3


# ---------------------------------------------------------------------------
# Sentetik vaka kurucusu (çözücüsüz)
# ---------------------------------------------------------------------------

def _sentetik_sonuc(p_wall, i_throat=4, dz=0.01, converged=True,
                    throat_key=True, r_centers=True):
    """Duvar basıncı profilinden solve_steady_axisym sözleşmesi taklidi.

    Yalnız bu köprünün OKUDUĞU alanlar üretilir (sözleşme yüzeyi dar
    tutuluyor: köprü başka alan okumaya başlarsa bu kurucu kırılır ve
    bağımlılık görünür olur).
    """
    p = np.asarray(p_wall, dtype=float)
    z = np.arange(p.size, dtype=float) * dz
    res = {
        'wall_pressure_Pa': p,
        'wall_pressure_z_m': z,
        'converged': bool(converged),
        'convergence_basis': ('SENTETİK: bu sözlük testin kurduğu profildir, '
                              'çözücü koşmadı.'),
    }
    if throat_key:
        res['throat'] = {'i': int(i_throat)}
    if r_centers:
        # Boğazı i_throat'ta olan yapay yarıçap sütunu (geometrik türetme
        # basamağının bekçisi): duvar sütunu r_centers_m[:, -1].
        r = 0.05 + 0.01 * np.abs(np.arange(p.size) - i_throat)
        res['r_centers_m'] = np.stack([r * 0.5, r], axis=1)
    return res


# Elle tasarlanmış aşırı-genişleme profili: boğaz index 4, ıraksakta
# 7 istasyon. P_ortam = 7,5e5 Pa ve k = 0,40 → eşik TAM 3,0e5 Pa.
# Eşiğin altına ilk düşen istasyon TASARIM GEREĞİ global index 9'dur
# (değeri 2,0e5; bir öncekinin değeri 4,0e5 — eşik ikisinin tam ortasında,
# ara değer z = 0,085 m çıkmalı).
ASIRI_PROFIL = [5.0e6, 4.5e6, 4.0e6, 3.5e6, 3.0e6,      # 0-4 (4 = boğaz)
                1.0e6, 8.0e5, 6.0e5, 4.0e5, 2.0e5, 1.0e5, 5.0e4]  # 5-11
ASIRI_PA = 7.5e5
ASIRI_ESIK = 3.0e5          # = 0,40 × 7,5e5 (elle)
ASIRI_BEKLENEN_INDEX = 9
ASIRI_BEKLENEN_Z = 0.09
ASIRI_BEKLENEN_ARA_Z = 0.085


# ---------------------------------------------------------------------------
# (a) Tam akış: hiçbir istasyon eşiğin altında değil
# ---------------------------------------------------------------------------

def test_tam_akis_ayrilmaz():
    """p_w her yerde k·P_ortam üstündeyse ayrılma YOK ve alanlar boş kalır."""
    res = _sentetik_sonuc(ASIRI_PROFIL)
    # Ortam basıncı 10 kat düşük: eşik 3,0e4 Pa, min p_w 5,0e4 Pa.
    a = assess_separation(res, ASIRI_PA / 10.0)
    assert a['applicable'] is True
    assert a['separated'] is False
    assert a['separation_index'] is None
    assert a['separation_z_m'] is None
    assert a['separated_length_m'] == 0.0
    assert a['stations_below_threshold'] == 0
    assert a['wall_pressure_margin_min'] > 1.0, (
        'ayrılma yokken min p_w eşiğin üstünde olmalı: '
        f"{a['wall_pressure_margin_min']}")
    assert a['reattachment_suspected'] is False


# ---------------------------------------------------------------------------
# (b) Aşırı genişleme: ilk ayrılma istasyonu ve türetilmiş alanlar
# ---------------------------------------------------------------------------

def test_asiri_genisleme_ayrilma_istasyonu():
    """Çıkışa doğru düşen profilde ilk ayrılma istasyonu TASARLANAN yerde."""
    res = _sentetik_sonuc(ASIRI_PROFIL)
    a = assess_separation(res, ASIRI_PA)
    assert a['separated'] is True
    assert a['threshold_Pa'] == pytest.approx(ASIRI_ESIK, rel=1e-12)
    assert a['separation_index'] == ASIRI_BEKLENEN_INDEX, (
        f"ilk ayrılma istasyonu {a['separation_index']}, tasarlanan "
        f'{ASIRI_BEKLENEN_INDEX} (profil elle kuruldu)')
    assert a['separation_z_m'] == pytest.approx(ASIRI_BEKLENEN_Z, abs=1e-12)
    assert a['separation_wall_pressure_Pa'] == pytest.approx(2.0e5)
    assert a['separation_z_interp_m'] == pytest.approx(
        ASIRI_BEKLENEN_ARA_Z, abs=1e-12), (
        'eşik iki istasyonun tam ortasında: ara değer 0,085 m olmalı')
    # Türetilmiş alanlar: yayımlanan z alanlarından geri kurulur (sabit yok)
    beklenen_uzunluk = a['exit_z_m'] - a['separation_z_m']
    assert a['separated_length_m'] == pytest.approx(beklenen_uzunluk)
    assert a['separated_length_fraction'] == pytest.approx(
        beklenen_uzunluk / (a['exit_z_m'] - a['throat_z_m']))
    assert a['stations_below_threshold'] == 3      # index 9, 10, 11
    assert a['stations_in_search_domain'] == 7     # index 5…11
    assert a['reattachment_suspected'] is False
    assert a['criterion'] == 'summerfield'
    assert 'Summerfield' in a['criterion_basis']
    assert '1954' in a['criterion_basis']


def test_ayrilma_istasyonu_esigi_gercekten_asiyor():
    """Bağımsız çapraz: seçilen istasyon eşiğin ALTINDA, bir önceki ÜSTÜNDE."""
    res = _sentetik_sonuc(ASIRI_PROFIL)
    a = assess_separation(res, ASIRI_PA)
    pw = np.asarray(res['wall_pressure_Pa'])
    j = a['separation_index']
    assert pw[j] < a['threshold_Pa']
    assert pw[j - 1] > a['threshold_Pa'], (
        'seçilen istasyon İLK geçiş değil: bir önceki de eşiğin altında')


# ---------------------------------------------------------------------------
# Arama bölgesi: yanlış pozitif kapısı
# ---------------------------------------------------------------------------

def test_arama_bolgesi_iraksakla_sinirli():
    """Yakınsak bölgede eşiğin altında istasyon OLSA BİLE ayrılma yok.

    Ses-altı girişte ölçüt tanımsızdır (modül docstring'i beyanlı). Bu bekçi,
    aramanın tüm diziye yayılması hâlinde kırmızıya döner.
    """
    profil = list(ASIRI_PROFIL)
    profil[2] = 1.0e3            # yakınsak bölgede eşiğin ÇOK altında
    res = _sentetik_sonuc(profil)
    a = assess_separation(res, ASIRI_PA / 10.0)   # ıraksakta hepsi üstte
    assert a['separated'] is False, (
        'yakınsak bölgedeki düşük basınç ayrılma sayıldı — arama bölgesi '
        'ıraksakla sınırlı değil')
    assert 'ıraksak' in a['search_domain_basis']


def test_bogaz_istasyonu_arama_disinda():
    """Boğaz istasyonunun kendisi arama bölgesinde değildir (kesit M ≈ 1)."""
    profil = list(ASIRI_PROFIL)
    profil[4] = 1.0e3            # boğaz istasyonu eşiğin altında
    res = _sentetik_sonuc(profil)
    a = assess_separation(res, ASIRI_PA / 10.0)
    assert a['separated'] is False
    assert a['stations_in_search_domain'] == 7


# ---------------------------------------------------------------------------
# (c) + (d) Girdi denetimleri: uydurma varsayılan yok
# ---------------------------------------------------------------------------

def test_ortam_basinci_zorunlu():
    """P_ambient_Pa eksikse ValueError — varsayılan ortam basıncı UYDURMADIR."""
    res = _sentetik_sonuc(ASIRI_PROFIL)
    with pytest.raises(ValueError, match='P_ambient_Pa zorunludur'):
        assess_separation(res, None)
    with pytest.raises(TypeError):
        assess_separation(res)          # konumsal argüman da zorunlu


def test_ortam_basinci_negatif_reddedilir():
    res = _sentetik_sonuc(ASIRI_PROFIL)
    with pytest.raises(ValueError):
        assess_separation(res, -1.0)


def test_vakumda_hukum_verilmez():
    """P_ortam = 0: ölçüt tanımsız; 'ayrılma yok' demek yerine beyan."""
    res = _sentetik_sonuc(ASIRI_PROFIL)
    a = assess_separation(res, 0.0)
    assert a['applicable'] is False
    assert a['separated'] is False
    assert 'not_applicable_reason' in a
    assert 'Vakum' in a['not_applicable_reason']


@pytest.mark.parametrize('k', [SEPARATION_FACTOR_MIN - 1e-6,
                               SEPARATION_FACTOR_MAX + 1e-6,
                               0.0, 1.0])
def test_faktor_bant_disi_reddedilir(k):
    """k, ithal edilen [MIN, MAX] bandının dışındaysa ValueError."""
    res = _sentetik_sonuc(ASIRI_PROFIL)
    with pytest.raises(ValueError, match='separation_factor'):
        assess_separation(res, ASIRI_PA, separation_factor=k)


def test_faktor_bant_ucunda_kabul():
    """Bandın uçları KABUL (aralık kapalı) — bant daralırsa bu bekçi kırmızı."""
    res = _sentetik_sonuc(ASIRI_PROFIL)
    for k in (SEPARATION_FACTOR_MIN, SEPARATION_FACTOR_MAX):
        a = assess_separation(res, ASIRI_PA, separation_factor=k)
        assert a['separation_factor'] == pytest.approx(k)
        assert a['separation_factor_source'] == 'caller'
        assert a['threshold_Pa'] == pytest.approx(k * ASIRI_PA)


def test_kullanici_faktoru_beyani():
    """k kaynağı (varsayılan mı çağıran mı) hükümde beyanlı."""
    res = _sentetik_sonuc(ASIRI_PROFIL)
    a = assess_separation(res, ASIRI_PA)
    assert a['separation_factor_source'] == 'default'
    assert 'varsayılan' in a['criterion_basis']
    b = assess_separation(res, ASIRI_PA, separation_factor=0.35)
    assert b['separation_factor_source'] == 'caller'
    assert 'çağıranın verdiği' in b['criterion_basis']


# ---------------------------------------------------------------------------
# (e) Hüküm / doğrulama ayrımı
# ---------------------------------------------------------------------------

def test_yakinsamayan_hukum_supheli():
    """converged=False: hüküm gizlenmez ama ŞÜPHELİ işaretlenir."""
    res = _sentetik_sonuc(ASIRI_PROFIL, converged=False)
    a = assess_separation(res, ASIRI_PA)
    assert a['separated'] is True, 'yakınsamayan koşuda sonuç gizlenmemeli'
    assert a['converged'] is False
    assert a['judgment_confidence'] == 'suspect'
    assert 'YAKINSAMADI' in a['judgment_basis']
    assert 'ŞÜPHELİ' in a['judgment_basis']
    assert a['solver_convergence_basis'] == res['convergence_basis']


def test_yakinsayan_hukum_kesin():
    res = _sentetik_sonuc(ASIRI_PROFIL, converged=True)
    a = assess_separation(res, ASIRI_PA)
    assert a['judgment_confidence'] == 'firm'
    assert 'YAKINSAMADI' not in a['judgment_basis']


def test_yakinsama_beyani_olmadan_hukum_yok():
    """'converged' anahtarı yoksa hüküm verilmez (sessiz kabul YASAK)."""
    res = _sentetik_sonuc(ASIRI_PROFIL)
    res.pop('converged')
    with pytest.raises(ValueError, match='converged'):
        assess_separation(res, ASIRI_PA)


# ---------------------------------------------------------------------------
# Sözleşme denetimleri
# ---------------------------------------------------------------------------

def test_duvar_sozlesmesi_yoksa_reddedilir():
    res = _sentetik_sonuc(ASIRI_PROFIL)
    eksik = dict(res)
    eksik.pop('wall_pressure_Pa')
    with pytest.raises(ValueError, match='wall_pressure_Pa'):
        assess_separation(eksik, ASIRI_PA)
    eksik2 = dict(res)
    eksik2.pop('wall_pressure_z_m')
    with pytest.raises(ValueError, match='wall_pressure_z_m'):
        assess_separation(eksik2, ASIRI_PA)


def test_eksen_artan_degilse_reddedilir():
    res = _sentetik_sonuc(ASIRI_PROFIL)
    z = np.asarray(res['wall_pressure_z_m']).copy()
    z[6], z[7] = z[7], z[6]
    res['wall_pressure_z_m'] = z
    with pytest.raises(ValueError, match='kesin artan'):
        assess_separation(res, ASIRI_PA)


def test_uzunluklar_uyusmazsa_reddedilir():
    res = _sentetik_sonuc(ASIRI_PROFIL)
    res['wall_pressure_z_m'] = np.asarray(res['wall_pressure_z_m'])[:-1]
    with pytest.raises(ValueError, match='aynı uzunlukta değil'):
        assess_separation(res, ASIRI_PA)


def test_sonlu_olmayan_basinc_reddedilir():
    profil = list(ASIRI_PROFIL)
    profil[7] = float('nan')
    res = _sentetik_sonuc(profil)
    with pytest.raises(ValueError, match='sonlu'):
        assess_separation(res, ASIRI_PA)


def test_bogaz_index_geometriden_turetilir():
    """throat['i'] yoksa boğaz GEOMETRİDEN türetilir, dayanağı beyanlı."""
    res = _sentetik_sonuc(ASIRI_PROFIL, throat_key=False)
    a = assess_separation(res, ASIRI_PA)
    assert a['throat_index'] == 4
    assert 'GEOMETRİDEN' in a['throat_index_basis']
    assert a['separation_index'] == ASIRI_BEKLENEN_INDEX


def test_bogaz_belirlenemezse_uydurulmaz():
    """Ne throat['i'] ne r_centers_m varsa: ValueError (varsayım YOK)."""
    res = _sentetik_sonuc(ASIRI_PROFIL, throat_key=False, r_centers=False)
    with pytest.raises(ValueError, match='Boğaz'):
        assess_separation(res, ASIRI_PA)


def test_hukum_sonucu_degistirmez():
    """Saf fonksiyon: girdi sözlüğü ve dizileri DEĞİŞMEDEN kalır."""
    res = _sentetik_sonuc(ASIRI_PROFIL)
    pw_once = np.asarray(res['wall_pressure_Pa']).copy()
    anahtar_once = set(res)
    assess_separation(res, ASIRI_PA)
    assert set(res) == anahtar_once
    assert np.array_equal(np.asarray(res['wall_pressure_Pa']), pw_once)


def test_not_modelled_beyani_tasiniyor():
    """Ayrılma + CFD modellenmeyenleri hükümle birlikte yayımlanır."""
    res = _sentetik_sonuc(ASIRI_PROFIL)
    a = assess_separation(res, ASIRI_PA)
    nm = a['not_modelled']
    for anahtar in ('side_loads', 'boundary_layer_state',
                    'separation_resolution', 'viscosity_turbulence'):
        assert anahtar in nm, f'{anahtar} beyanı hükümde yok'


# ---------------------------------------------------------------------------
# Sabitlerin tek kaynağı (kopya yasağı)
# ---------------------------------------------------------------------------

def test_iki_kaynak_ayni_k_degerinde():
    """Depodaki iki Summerfield sabiti ayrışırsa bu bekçi kırmızıya döner."""
    assert SEPARATION_FACTOR_DEFAULT == SUMMERFIELD_FACTOR_DEFAULT, (
        f'nozzle_flow_1d {SEPARATION_FACTOR_DEFAULT} ile flow.separation '
        f'{SUMMERFIELD_FACTOR_DEFAULT} ayrıştı')


def test_bant_iki_kaynakta_ayni():
    """Bant denetimi davranışsal: flow.separation'ın kapısı MIN/MAX ile aynı."""
    assert summerfield_pressure_ratio(SEPARATION_FACTOR_MIN) == pytest.approx(
        SEPARATION_FACTOR_MIN)
    assert summerfield_pressure_ratio(SEPARATION_FACTOR_MAX) == pytest.approx(
        SEPARATION_FACTOR_MAX)
    with pytest.raises(ValueError):
        summerfield_pressure_ratio(SEPARATION_FACTOR_MIN - 1e-6)
    with pytest.raises(ValueError):
        summerfield_pressure_ratio(SEPARATION_FACTOR_MAX + 1e-6)


def test_varsayilan_k_ithal_ediliyor(monkeypatch):
    """Varsayılan k KOPYA değil İTHAL: ithal sabit değişince hüküm değişir."""
    monkeypatch.setattr(cfd_sep, 'SEPARATION_FACTOR_DEFAULT', 0.30)
    res = _sentetik_sonuc(ASIRI_PROFIL)
    a = assess_separation(res, ASIRI_PA)
    assert a['separation_factor'] == pytest.approx(0.30), (
        'ithal sabit değiştirildi ama hüküm eski değeri kullandı — modülde '
        'kopya sabit var')
    assert a['threshold_Pa'] == pytest.approx(0.30 * ASIRI_PA)


def test_kaynakta_kopya_sabit_yok():
    """Modül kaynağında çıplak bant sabiti (0.4 / 0.35 / 0.2 / 0.6) YOK.

    Sayısal bant tek kaynaktan ithal edilir; kopyalanırsa (ithalle aynı değer
    olsa bile) bu bekçi kırmızıya döner.
    """
    kaynak = Path(cfd_sep.__file__).read_text(encoding='utf-8')
    kacaklar = re.findall(r'(?<![\w.])0\.(?:20|2|35|40|4|60|6)(?![\d])',
                          kaynak)
    assert not kacaklar, (
        f'kaynakta çıplak bant sabiti bulundu: {kacaklar} — sabitler '
        f'hrma.analysis.nozzle_flow_1d\'den ithal edilmeli')


# ---------------------------------------------------------------------------
# GERÇEK ÇÖZÜCÜ: aşırı-genişlemiş vaka (conftest.sok_cozumu yeniden kullanım)
# ---------------------------------------------------------------------------

def _analitik_ayrilma_konumu(k, p_ortam):
    """p_w(z) = k·P_ortam kökü, izantropik ses-üstü dalda (testin analitiği).

    Duvar basıncı, alan-Mach terslemesi + izantropik p/p0 ile kurulur
    (test_normal_sok'un yardımcıları YENİDEN KULLANILIR, kopya yok). Kökün
    şokun YUKARISINDA kalması çağıran testte doğrulanır — aşağısında
    izantropik dal geçersizdir.
    """
    a_star = np.pi * LULE_R_THROAT ** 2
    hedef = k * p_ortam

    def fark(z):
        a = float(np.pi * lule_duvar_yaricapi(np.array([z]))[0] ** 2)
        m = _mach_alandan(a / a_star, LULE_GAMMA, supersonic=True)
        return LULE_P0 * _izantropik_p_orani(m, LULE_GAMMA) - hedef

    return float(brentq(fark, LULE_L_CONV + 1e-6,
                        LULE_L_CONV + LULE_L_DIV - 1e-9,
                        xtol=1e-12, maxiter=200))


def test_gercek_cozum_ayrilma_istasyonu(sok_cozumu):
    """CFD ayrılma istasyonu analitik izantropik beklentiyle tutarlı."""
    _, res = sok_cozumu
    assert res['converged'] is True, (
        f"vaka yakınsamadı: {res['convergence_basis']}")
    a = assess_separation(res, LULE_PB_SOK)
    assert a['separated'] is True, (
        'aşırı-genişlemiş vakada ayrılma öngörülmedi: min p_w/eşik = '
        f"{a['wall_pressure_margin_min']:.3f}")
    assert a['threshold_Pa'] == pytest.approx(
        SEPARATION_FACTOR_DEFAULT * LULE_PB_SOK)

    z_ref = _analitik_ayrilma_konumu(SEPARATION_FACTOR_DEFAULT, LULE_PB_SOK)
    z_sok = analitik_sok_konumu(LULE_PB_SOK, LULE_GAMMA)
    assert z_ref < z_sok, (
        f'analitik ayrılma kökü {z_ref:.5f} m şokun ({z_sok:.5f} m) '
        f'aşağısında — izantropik dal geçersiz, vaka kurulumu bozulmuş')

    fark = abs(a['separation_z_m'] - z_ref)
    assert fark < AYRILMA_KONUM_TOL_M, (
        f"ayrılma istasyonu z={a['separation_z_m']:.5f} m, analitik "
        f'{z_ref:.5f} m — fark {fark * 1e3:.2f} mm > '
        f'{AYRILMA_KONUM_TOL_M * 1e3:.1f} mm (ölçüm 1,16 mm; eksenel '
        f'hücre 2,5 mm)')
    fark_ara = abs(a['separation_z_interp_m'] - z_ref)
    assert fark_ara < AYRILMA_KONUM_TOL_M, (
        f"ara değer konumu {a['separation_z_interp_m']:.5f} m, analitik "
        f'{z_ref:.5f} m — fark {fark_ara * 1e3:.2f} mm (ölçüm 2,00 mm)')


def test_gercek_cozum_beyanlari(sok_cozumu):
    """Gerçek koşuda hüküm alanları: kesinlik, bracket, şok ardı geri çıkış."""
    grid, res = sok_cozumu
    a = assess_separation(res, LULE_PB_SOK)
    assert a['judgment_confidence'] == 'firm'
    assert a['converged'] is True
    assert a['solver_convergence_basis'] == res['convergence_basis']

    pw = np.asarray(res['wall_pressure_Pa'])
    zw = np.asarray(res['wall_pressure_z_m'])
    j = a['separation_index']
    assert pw[j] < a['threshold_Pa'] < pw[j - 1], (
        'ayrılma istasyonu eşiği ilk geçen istasyon değil')
    assert a['separation_z_m'] == pytest.approx(float(zw[j]))
    assert a['throat_index'] == res['throat']['i']
    assert 0 < a['stations_below_threshold'] < a['stations_in_search_domain']

    # İç normal şok ardında p_w eşiğin üstüne döner: Euler ayrılmış bölgeyi
    # çözemez, bu geri çıkış YENİDEN YAPIŞMA sayılmaz — beyan aranıyor.
    assert a['reattachment_suspected'] is True
    assert 'şok' in a['reattachment_basis']
    assert float(pw[-1]) > a['threshold_Pa']

    # Ayrılan bölge: ilk mertebe Summerfield işleyişi (istasyondan çıkışa)
    assert a['separated_length_m'] == pytest.approx(
        float(zw[-1]) - float(zw[j]))
    assert 0.0 < a['separated_length_fraction'] < 1.0
    assert a['inputs']['wall_stations'] == grid.ni


def test_gercek_cozum_bogaz_turetmesi(sok_cozumu):
    """Gerçek ızgarada geometrik boğaz türetmesi yayımlanan index'le aynı."""
    _, res = sok_cozumu
    kopya = dict(res)
    kopya.pop('throat')
    a = assess_separation(kopya, LULE_PB_SOK)
    assert a['throat_index'] == res['throat']['i'], (
        f"geometrik türetme {a['throat_index']}, çözücünün beyanı "
        f"{res['throat']['i']}")
    assert 'GEOMETRİDEN' in a['throat_index_basis']


def test_gercek_cozum_dusuk_ortamda_ayrilmaz(sok_cozumu):
    """Aynı alan, deniz seviyesi ortamında: eşik 40 kPa, ayrılma YOK.

    Ölçüt gerçekten ORTAM basıncına bağlı — sabit bir eşik değil.
    """
    _, res = sok_cozumu
    a = assess_separation(res, 1.0e5)
    assert a['separated'] is False
    assert a['wall_pressure_margin_min'] > 1.0
