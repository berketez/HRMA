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

V4 MUTASYON KANITI (parti 40; sağlam sürüm md5
238f3c3f839f90c4a7abfde999426f47 — dosya dört üyeli karşılaştırmayla
büyüdüğünden M1/M2'nin md5'leri artık geçersizdir, ÖLÇÜTLERİ değil):
  M5 "CFD üyesinin ölçütü ters": ``below = tau_div < 0.0`` →
     ``tau_div > 0.0`` (mutant cc36544466da11c0c68e424cee4c4a85)
     → 3 KIRMIZI (41 yeşil): test_BASAMAK13_tam_akan_lulede_CFD_uyesi_
       AYRILMA_YOK_der, test_BASAMAK13_ayrilmali_vakada_dort_uye_AYNI_
       ciktida, test_BASAMAK13_uyeler_arasi_FARK_alani.
  M6 "viskoz yoksa üye sessizce var sayılıyor": ``if not isinstance(
     block, dict):`` → ``if False:`` (mutant c94e6ae89cb7c56fd81a003d35053cf4)
     → 22 KIRMIZI (22 yeşil): sentetik vakaların TAMAMI patlıyor (viskoz
       olmayan sözlükte üye kurulmaya çalışılıyor) + V4 kapıları.
  M7 "düz alanlar ayrı (ikinci) aramadan doluyor" — DEĞERİ AYNI kopya:
     ``out['wall_pressure_margin_min'] = m_sum['margin_min']`` →
     ``float(np.min(p_div)) / threshold``
     (mutant 01afd0aea44e28ad5585c9c5519bec9e)
     → **İLK ÖLÇÜMDE 43/43 YEŞİLDİ: BEKÇİ DELİĞİ ÖLÇÜLDÜ.** Değer aynı
       olduğundan sayısal karşılaştırma (test_duz_alanlar_summerfield_
       UYESININ_ta_kendisi) kopyayı ayırt edemiyordu; kopya yasağının
       konusu değer değil KAYNAK birliğidir (iki hesap zamanla ayrışır).
       Delik test_duz_alanlar_UYENIN_KENDISINDEN_doluyor_YAPISAL ile
       kapatıldı (monkeypatch'li YAPISAL CASUS: üyenin ürettiği sayı
       imza değerleriyle değiştirilir, düz alanların onu İZLEDİĞİ
       ölçülür). Kapanış doğrulandı: aynı mutasyon ŞİMDİ KIRMIZI
       (1 kırmızı / 43 yeşil).
  M9 "üyenin separation_z_m'i z_wall'dan yeniden okunuyor" — İKİNCİ bir
     değeri-aynı kopya (mutant 921ca8a7c2ca3587dcdac9c5828d17c9)
     → yapısal casus KIRMIZI, değer karşılaştıran eski bekçi YEŞİL.
     İki bekçinin AYRI şeyleri ölçtüğünün kanıtı budur.
  Dört mutasyonun her birinden sonra dosya md5
  238f3c3f839f90c4a7abfde999426f47 değerine TERS DEĞİŞTİRMEYLE bit-özdeş
  geri kondu (checkout ile DEĞİL).
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
    # --- ÇEVRİLDİ (ÖH D32 / OH-D31-15) -------------------------------
    # Bu vaka (şoklu 120×24) AÇIK yolda koşar; sınırlayıcı 20895.
    # iterasyonda donar ve yayımlanan kalıntı BAYAT operatörünündür.
    # Şemanın kendi (canlı minmod) kalıntısı 5,5102e-04 = tolun 398,7
    # katıdır (ölçüldü: docs/scofield/raw/OH/D32/fea-cfd/a2/once.json).
    # Çözücü artık o hükmü VERMİYOR (converged=None, convergence_status=
    # 'not_evaluated'; Berke kararı 15 Eyl 2026 §3 seç. A) — eski
    # ``is True`` iddiası tam da KAZANILMAMIŞ hükmün yerinde durmasını
    # şart koşuyordu. Bu testin ÖLÇTÜĞÜ şey ayrılma İSTASYONUdur;
    # korunan yasak aynen duruyor: ıraksamış ya da ÖLÇÜLMÜŞ olarak
    # yakınsamamış bir alan bu karşılaştırmayı geçersiz kılar.
    assert res['converged'] is not False, (
        f"vaka ÖLÇÜLMÜŞ olarak yakınsamadı: {res['convergence_basis']}")
    assert res['convergence_status'] in ('converged', 'not_evaluated'), (
        f"vaka kurulumu bozulmuş: convergence_status="
        f"{res['convergence_status']!r}")
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
    # ÇEVRİLDİ (OH-D31-15): bu vakada çözücü hüküm VERMİYOR (yukarıdaki
    # gerekçe), dolayısıyla köprü de 'firm' diyemez. Etiket üçüncü
    # durumdur ve 'suspect' DEĞİLDİR: alan oturmadığı için değil,
    # oturup oturmadığına BAKILMADIĞI için sağlam sunulmuyor.
    #
    # ÖH D37 A3a cfd-kok-a (OH-DK-12/13; Berke Sunum 3a onayı 24 Eyl): şoklu
    # akışta plato-dondurması kapandı, bu vaka artık canlı operatörle
    # `converged` olabiliyor. Sözleşme iki durumludur ve etiket hükmü İZLER:
    # hüküm verildiyse 'firm', yargılanmadıysa 'not_evaluated'; hiçbir
    # durumda 'suspect' (ölçülmüş yakınsamama) DEĞİL.
    assert a['converged'] in (True, None), a['converged']
    beklenen = 'firm' if a['converged'] is True else 'not_evaluated'
    assert a['judgment_confidence'] == beklenen, a['judgment_confidence']
    assert 'YAKINSAMADI' not in a['judgment_basis'], (
        'yakınsamamış sayılmayan hüküm "yakınsamadı" diye sunuluyor')
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


# ===========================================================================
# V4 — DÖRT ÜYELİ KARŞILAŞTIRMA (tasarım §8.3, doğrulama merdiveni basamak 13)
#
# Ampirik üçlü (Summerfield / Schmucker / Kalt-Badal) AYNI çözümün duvar
# basıncına, dördüncü üye (CFD-τ_w) aynı çözümün duvar kayma gerilmesine
# uygulanır. Viskoz koşu yoksa dördüncü üye UYDURULMAZ.
#
# ÖLÇÜLDÜ (M4 Max, 2026-08-19; test_wall_output.py'nin vakası — conftest
# lülesi 64×16, laminer μ = 0,15 Pa·s, izotermal T_w = 0,6·T₀):
#
#   (a) TAM-AKAN vaka (Pb=None, P_ortam = 101 325 Pa): DÖRT ÜYE DE
#       "ayrılma yok" (unanimous). τ_w min = +19 377 Pa — yanlış pozitif
#       kapısı bu vakadan geçiyor.
#
#   (b) AŞIRI-GENİŞLEMİŞ vaka (Pb = P_ortam = 2,75 MPa; 4342 iterasyonda
#       yakınsıyor, kalıntı 6,6e-11) — ÜYELER ÇELİŞİYOR ve çelişki
#       GİZLENMİYOR:
#         üye            ayrıldı  index  z [m]        pay (margin)
#         summerfield    hayır    —      —            2,2225
#         schmucker      EVET     26     0,1242195    0,6498
#         kalt_badal     hayır    —      —            1,4373
#         cfd_tau_w      EVET     41     0,1945388    −0,0438
#       z_span = 70,32 mm; cfd − schmucker = +70,32 mm; τ_w min = −2280 Pa.
#       OKUMA: bu vakada boğaz statik basıncı (2,26 MPa) ortam basıncının
#       ALTINDADIR, o yüzden Schmucker ıraksak bölgenin İLK istasyonunda
#       ateşliyor (M ≈ 1 — kendi türetim bandının 1,5-4,5 dışı, üye bunu
#       validity_warning ile beyan ediyor). Summerfield ve Kalt-Badal'ın
#       sabit eşikleri (1,10 ve 1,70 MPa) ise duvar basıncının minimumunun
#       (2,44 MPa) altında kaldığı için hiç ateşlemiyor. Ampirik üçlü bu
#       LAMİNER ayrılmayı ıskalıyor; CFD üyesi τ_w'nin işaret değiştirdiği
#       yeri ölçüyor. Dördü de yayımlanıyor.
#
# KAPSAM BEYANI (dürüstlük): CFD üyesi bu partide LAMİNER vakalarla
# doğrulandı. Türbülanslı yol (SA açık lüle koşumu) V3 defterinde AÇIK bir
# kalemdir; şok-sınır tabakası etkileşiminde ayrılma noktasının türbülans
# modeline duyarlılığı BU PARTİDE ÖLÇÜLMEDİ ve üye bunu 'model_dependent'
# güven etiketiyle beyan eder.
# ===========================================================================

from hrma.cfd.separation import (          # noqa: E402  (bölüm sınırı)
    CRITERION_CFD_TAU_W, CRITERION_KALT_BADAL, CRITERION_SCHMUCKER,
    SEPARATION_CRITERIA,
)
from .test_wall_output import (            # noqa: E402
    viskoz_ayrilmali, viskoz_izo,          # noqa: F401 (pytest fikstürleri)
)

#: Ölçülen ayrılmalı vaka değerleri (64×16, Pb = P_ortam = 2,75 MPa).
AYR_BOGAZ_I = 25
AYR_CFD_INDEX = 41
AYR_CFD_Z = 0.19453882
AYR_CFD_Z_ARA = 0.18992527
AYR_SCHMUCKER_INDEX = 26
AYR_SCHMUCKER_Z = 0.12421945
AYR_TAU_MIN = -2280.4
AYR_Z_SPAN = 0.07031937
#: Tam-akan vakada ölçülen en küçük τ_w (pozitif — bağlı akış).
TAM_AKAN_TAU_MIN = 19377.1

#: PLATO KALINTISI (ayrılmalı vaka, tol 1e-8). ÖLÇÜLDÜ iki BAĞIMSIZ
#: koşumda: PK3 ulaşılabilirlik taraması
#: (docs/scofield/raw/OH/Z5S/pk3/ayrilma_ulasilabilirlik.json) 5.000 /
#: 10.000 / 20.000 iterasyon tavanlarında 1,2204e-04 / 1,2168e-04 /
#: 1,2206e-04 — dört katına çıkan bütçe sayıyı BİNDE ÜÇ oynattı; bu
#: dosyanın kendi ölçümü (docs/scofield/raw/OH/D15/cfd-picard/a2/
#: once.json) 1,22057e-04. Yani hedef bu vaka sınıfında ULAŞILAMAZ.
#: Tolerans AYRICA yazılmaz: koşumun kendi yayımladığı plato eşiği
#: (convergence_plateau['rel_tol']) kullanılır — TEK KAYNAK.
AYR_PLATO_KALINTI = 1.22057e-04


def _uye_semasi(uye):
    """Her üyenin taşımak ZORUNDA olduğu ortak anahtarlar."""
    return {'criterion', 'basis_kind', 'available', 'not_available_reason',
            'separated', 'separation_index', 'separation_z_m',
            'separation_z_interp_m', 'separation_wall_pressure_Pa',
            'separated_length_m', 'separated_length_fraction',
            'stations_below_threshold', 'reattachment_suspected',
            'threshold_Pa', 'threshold_min_Pa', 'threshold_max_Pa',
            'margin_min', 'validity_warning', 'reliability',
            'reliability_basis'} <= set(uye)


def test_dort_uye_AYNI_semada_yayimlanir():
    """Dört üye de aynı anahtarları taşır — yan yana okunabilsin diye."""
    res = _sentetik_sonuc(ASIRI_PROFIL)
    res['inputs'] = {'P0_Pa': 5.0e6, 'gamma': 1.2}
    a = assess_separation(res, ASIRI_PA)
    assert tuple(a['criteria']) == SEPARATION_CRITERIA
    for ad in SEPARATION_CRITERIA:
        assert _uye_semasi(a['criteria'][ad]), f'{ad} şeması eksik'
        assert a['criteria'][ad]['criterion'] == ad
    assert 'criteria_spread' in a and 'criteria_basis' in a


def test_duz_alanlar_summerfield_UYESININ_ta_kendisi():
    """Geriye uyum: üst düzey hüküm criteria['summerfield'] ile ÖZDEŞ.

    İki ayrı arama döngüsü yazılsaydı sessizce ayrışabilirlerdi; ölçüt
    aritmetiği tek yerdedir ve bu bekçi onu YAPISAL olarak sabitler.
    """
    res = _sentetik_sonuc(ASIRI_PROFIL)
    a = assess_separation(res, ASIRI_PA)
    m = a['criteria']['summerfield']
    assert a['separated'] is m['separated'] is True
    assert a['separation_index'] == m['separation_index'] \
        == ASIRI_BEKLENEN_INDEX
    assert a['separation_z_m'] == m['separation_z_m'] == ASIRI_BEKLENEN_Z
    assert a['separation_z_interp_m'] == m['separation_z_interp_m']
    assert a['separated_length_m'] == m['separated_length_m']
    assert a['separated_length_fraction'] == m['separated_length_fraction']
    assert a['stations_below_threshold'] == m['stations_below_threshold']
    assert a['wall_pressure_margin_min'] == m['margin_min']
    assert a['reattachment_suspected'] is m['reattachment_suspected']
    assert m['threshold_Pa'] == pytest.approx(ASIRI_ESIK, rel=1e-12)


def test_viskoz_olmayan_cozumde_CFD_uyesi_UYDURULMAZ():
    """Euler koşusunda τ_w yoktur: üye YOK + gerekçe, hüküm ÜRETİLMEZ."""
    res = _sentetik_sonuc(ASIRI_PROFIL)
    a = assess_separation(res, ASIRI_PA)
    cfd = a['criteria'][CRITERION_CFD_TAU_W]
    assert cfd['available'] is False
    assert cfd['separated'] is False
    assert cfd['separation_z_m'] is None
    assert 'VİSKOZ DEĞİL' in cfd['not_available_reason']
    assert CRITERION_CFD_TAU_W in a['criteria_spread']['members_unavailable']
    # viscous=None (viskoz kapalı sürücü çıktısı) de aynı yola gider
    res2 = dict(res, viscous=None)
    assert assess_separation(res2, ASIRI_PA)['criteria'][
        CRITERION_CFD_TAU_W]['available'] is False


def test_P0_yoksa_iki_ampirik_uye_UYDURULMAZ():
    """Schmucker/Kalt-Badal eşikleri P₀ ister; yoksa üye YOK + gerekçe."""
    res = _sentetik_sonuc(ASIRI_PROFIL)          # inputs yankısı YOK
    a = assess_separation(res, ASIRI_PA)
    for ad in (CRITERION_SCHMUCKER, CRITERION_KALT_BADAL):
        uye = a['criteria'][ad]
        assert uye['available'] is False
        assert uye['separated'] is False
        assert 'P0_Pa' in uye['not_available_reason']
    # Summerfield P₀ İSTEMEZ — o üye ayakta kalmalı (kapı fazla geniş değil)
    assert a['criteria']['summerfield']['available'] is True


def test_vakumda_dort_uye_de_hukum_vermez():
    res = _sentetik_sonuc(ASIRI_PROFIL)
    res['inputs'] = {'P0_Pa': 5.0e6, 'gamma': 1.2}
    a = assess_separation(res, 0.0)
    assert a['applicable'] is False
    for ad in SEPARATION_CRITERIA:
        assert a['criteria'][ad]['available'] is False
        assert a['criteria'][ad]['separation_z_m'] is None
    assert a['criteria_spread']['members_separated'] == []


def test_BASAMAK13_tam_akan_lulede_CFD_uyesi_AYRILMA_YOK_der(viskoz_izo):
    """Yanlış pozitif bekçisi: bağlı akışta τ_w her yerde POZİTİF."""
    _, res, _ = viskoz_izo
    a = assess_separation(res, 101325.0)
    cfd = a['criteria'][CRITERION_CFD_TAU_W]
    assert cfd['available'] is True, cfd['not_available_reason']
    assert cfd['separated'] is False
    assert cfd['separation_z_m'] is None
    assert cfd['stations_below_threshold'] == 0
    assert cfd['stations_negative_total'] == 0
    assert cfd['tau_wall_min_Pa'] == pytest.approx(TAM_AKAN_TAU_MIN, rel=1e-3)
    # ÇEVRİLDİ (ÖH D24 fea-cfd a3, defter P6B3-12). Eski satır
    # ``cfd['margin_min'] > 0.0`` idi ve KUSURU KORUYORDU: bu üyenin
    # margin_min'i min(τ)/maks|τ| taşıyordu (kritik değeri 0), ampirik
    # üyelerinki ise p_w/eşik (kritik değeri 1). AYNI anahtarda iki
    # büyüklük vardı ve bu YAPIŞIK koşuda değeri 0,2636'ydı — ampirik
    # üyelerin "1'in altı = ayrıldı" kuralıyla okununca yanlış pozitif.
    # margin_min artık bu üyede TANIMSIZ (eşik τ_w = 0, sıfıra bölme) ve
    # normalize edilmiş kayma KENDİ adıyla yayımlanıyor.
    assert cfd['margin_min'] is None, cfd['margin_basis']
    assert cfd['tau_wall_margin_critical_value'] == 0.0
    assert cfd['tau_wall_min_over_max_abs'] > 0.0
    # DÖRT ÜYE de aynı şeyi söylüyor (ölçüldü) — çelişki yok.
    assert a['criteria_spread']['members_separated'] == []
    assert a['criteria_spread']['unanimous'] is True
    assert a['criteria_spread']['z_span_m'] is None


def test_BASAMAK13_ayrilmali_vakada_dort_uye_AYNI_ciktida(viskoz_ayrilmali):
    """Ayrık çözümün τ_w istasyonu ampirik üçlünün YANINDA yayımlanır.

    HÜKÜM SÖZLEŞMESİ — PLATO (ÖH defter OH-Z5-14; çevrildi 2026-08-31)
    ------------------------------------------------------------------
    Bu test eskiden ``res['converged'] is True`` diyordu. O iddia ürünün
    ARTIK VERMEDİĞİ bir hükümdür ve testi yeşil tutmak KUSURU KORUMAK
    olurdu: örtük yolun öz-tutarlılık kapısı hükmü geri çekiyor — çünkü
    yayımlanan kalıntı DONMUŞ eğim sisteminindir (residual_operator=
    frozen_slopes), şemanın KENDİ (canlı minmod) kalıntısı hedefin
    1,22e+04 katıdır. Dahası kalıntı ölçülen bir bantta DURMUŞTUR;
    ürün bunu ADIYLA söyler: ``convergence_status='plateau'``.

    HEDEF GEVŞETİLMEDİ. Sınanan şey hükmün kendisi değil, hükümsüzlüğün
    CİNSİNİN doğru yayımlanmasıdır: "bütçeyi büyüt" ile "bu vaka
    sınıfında hedef ULAŞILAMAZ" ayrı şeylerdir ve ikincisi ölçülmüştür.

    ALAN DEĞİŞMEDİ (ölçüldü, once.json/ayrilmali): aşağıdaki dondurulmuş
    τ_w sabitleri (index 41, z = 0,19453882, z_ara, τ_min = −2280,4)
    AYNEN geçerlidir — kapı hükmü geri çeker, ALANI değiştirmez.
    ÖLÇÜLDÜ (M4 Max, 2026-08-31, 64×16, Pb = 2,75 MPa, tol 1e-8):
    converged=False, status=plateau, 20000 iterasyon (tavan), yayımlanan
    kalıntı 7,354e-08, şema kalıntısı 1,22057e-04, Picard reddi 9,
    dondurma 2426. iterasyonda, plato penceresi 800 iterasyon / göreli
    yayılım 2,483e-03 (eşik 1e-02).
    """
    _, res, _ = viskoz_ayrilmali
    # --- HÜKÜM: kazanılmadı ve SEBEBİ ADIYLA yayımlandı ---------------
    assert res['converged'] is False, (
        'kapı hükmü geri çekmeliydi; converged=True dönüyorsa ya kapı '
        'söküldü ya da şema kalıntısı hedefin altına indi — ikisi de bu '
        f'dosyanın bantlarını geçersiz kılar: {res["convergence_basis"]}')
    assert res['convergence_status'] == 'plateau', (
        f'hükümsüzlüğün cinsi PLATO olmalıydı: {res["convergence_basis"]}')
    assert res['scheme_residual_blocks_verdict'] is True
    assert res['scheme_residual_exceeds_tol'] is True
    assert res['residual_operator'] == 'frozen_slopes'
    assert res['picard_selfconsistency_rejections'] > 0

    pl = res['convergence_plateau']
    assert pl['detected'] is True and pl['reason']
    # Plato ÜÇ koşulun birlikte sağlanmasıdır — üçü de ayrı sınanır.
    assert pl['window_iterations'] >= pl['probe_every'], 'pencere dar'
    assert len(pl['samples']) == pl['min_samples']
    assert all(v >= pl['target_residual'] for _i, v in pl['samples']), (
        'örneklerden biri hedefin altına inmiş — bu plato değil, iniş')
    assert pl['relative_spread'] < pl['rel_tol']
    # Sayının KENDİSİ dondurulur: PK3 taramasının ulaşılamazlık ölçümüyle
    # aynı bant (tolerans koşumun kendi eşiğinden — kopya sabit yok).
    assert pl['plateau_residual'] == pytest.approx(AYR_PLATO_KALINTI,
                                                   rel=pl['rel_tol'])
    assert pl['target_residual'] == pytest.approx(1e-8, rel=0, abs=0)
    # Beyan metni de ikisini de ADIYLA taşımalı (künyesiz hüküm yok).
    assert ' PLATO:' in res['convergence_basis']
    assert 'HÜKÜM VERİLMEDİ' in res['convergence_basis']

    a = assess_separation(res, LULE_PB_SOK)
    assert a['throat_index'] == AYR_BOGAZ_I

    cfd = a['criteria'][CRITERION_CFD_TAU_W]
    assert cfd['available'] is True and cfd['separated'] is True
    assert cfd['separation_index'] == AYR_CFD_INDEX
    assert cfd['separation_z_m'] == pytest.approx(AYR_CFD_Z, abs=1e-6)
    assert cfd['separation_z_interp_m'] == pytest.approx(AYR_CFD_Z_ARA,
                                                         abs=1e-5)
    assert cfd['tau_wall_min_Pa'] == pytest.approx(AYR_TAU_MIN, rel=1e-3)
    assert cfd['tau_wall_at_separation_Pa'] < 0.0
    # ÇEVRİLDİ (ÖH D24 fea-cfd a3, defter P6B3-12) — yukarıdaki
    # test_BASAMAK13_tam_akan_... ile aynı gerekçe: ayrılma hükmü artık
    # margin_min'den DEĞİL, kendi adıyla yayımlanan normalize kaymadan
    # okunur (kritik değeri 0).
    assert cfd['margin_min'] is None, cfd['margin_basis']
    assert cfd['tau_wall_min_over_max_abs'] < 0.0
    # İşaret DEĞİŞİMİ gerçekten var (tek taraflı negatiflik değil)
    assert cfd['tau_wall_sign_changes_total'] >= 1
    # Alt-hücre kestirimi kuşatan iki istasyonun ARASINDA olmalı
    z = np.asarray(res['viscous']['wall_z_m'], dtype=float)
    assert z[AYR_CFD_INDEX - 1] < cfd['separation_z_interp_m'] \
        <= z[AYR_CFD_INDEX]

    # Ampirik üçlü AYNI çıktıda ve hükümleri ÖLÇÜLDÜĞÜ gibi
    sch = a['criteria'][CRITERION_SCHMUCKER]
    assert sch['available'] is True and sch['separated'] is True
    assert sch['separation_index'] == AYR_SCHMUCKER_INDEX
    assert sch['separation_z_m'] == pytest.approx(AYR_SCHMUCKER_Z, abs=1e-6)
    assert sch['validity_warning'] and 'türetim bandının' in \
        sch['validity_warning'], (
        'Schmucker ıraksak bölgenin ilk istasyonunda (M ≈ 1) ateşledi; '
        'türetim bandı uyarısı BEYAN EDİLMELİ')
    assert a['criteria']['summerfield']['separated'] is False
    assert a['criteria'][CRITERION_KALT_BADAL]['separated'] is False
    assert a['criteria'][CRITERION_KALT_BADAL]['pressure_ratio_npr'] == \
        pytest.approx(4.0e6 / LULE_PB_SOK, rel=1e-12)


def test_BASAMAK13_uyeler_arasi_FARK_alani(viskoz_ayrilmali):
    """Çelişki gizlenmez: fark alanı ölçülen ayrışmayı taşır."""
    _, res, _ = viskoz_ayrilmali
    a = assess_separation(res, LULE_PB_SOK)
    s = a['criteria_spread']
    assert set(s['members_separated']) == {CRITERION_SCHMUCKER,
                                           CRITERION_CFD_TAU_W}
    assert set(s['members_attached']) == {'summerfield', CRITERION_KALT_BADAL}
    assert s['members_unavailable'] == []
    assert s['unanimous'] is False
    assert s['z_span_m'] == pytest.approx(AYR_Z_SPAN, abs=1e-5)
    assert s['cfd_minus_empirical_m'][CRITERION_SCHMUCKER] == pytest.approx(
        AYR_Z_SPAN, abs=1e-5)
    # Ayrılmamış üyelerle fark TANIMSIZDIR — sıfır YAZILMAZ.
    assert s['cfd_minus_empirical_m']['summerfield'] is None
    assert s['cfd_minus_empirical_m'][CRITERION_KALT_BADAL] is None


def test_BASAMAK13_guven_etiketleri_tasiniyor(viskoz_ayrilmali):
    """§8.3 + §13/7: CFD üyesi 'model bağımlı' etiketini TAŞIR."""
    _, res, _ = viskoz_ayrilmali
    a = assess_separation(res, LULE_PB_SOK)
    cfd = a['criteria'][CRITERION_CFD_TAU_W]
    assert cfd['reliability'] == 'model_dependent'
    assert cfd['basis_kind'] == 'computed_wall_shear'
    for parca in ('model bağımlı', 'şok-sınır tabakası', 'yerine GEÇMEZ'):
        assert parca in cfd['reliability_basis'], f'beyan eksik: {parca}'
    for ad in ('summerfield', CRITERION_SCHMUCKER, CRITERION_KALT_BADAL):
        uye = a['criteria'][ad]
        assert uye['reliability'] == 'empirical_correlation'
        assert uye['basis_kind'] == 'empirical_wall_pressure'
    # Eksen kayması ÖLÇÜLÜP yayımlanıyor (yarım hücreden küçük).
    assert 0.0 < cfd['axis_offset_max_m'] < 1.0e-4


def test_CFD_uyesi_uyusmayan_eksende_UYDURMAZ(viskoz_ayrilmali):
    """τ_w dizisi başka bir koşuma aitse üye YOK (sessiz taşıma yasağı)."""
    _, res, _ = viskoz_ayrilmali
    bozuk = dict(res)
    v = dict(res['viscous'])
    v['wall_z_m'] = np.asarray(v['wall_z_m'], dtype=float) + 0.05
    bozuk['viscous'] = v
    cfd = assess_separation(bozuk, LULE_PB_SOK)['criteria'][
        CRITERION_CFD_TAU_W]
    assert cfd['available'] is False
    assert 'aynı istasyonlara ait değil' in cfd['not_available_reason']
    # Iraksamış (sonlu olmayan) τ_w de hüküm üretmez
    bozuk2 = dict(res)
    v2 = dict(res['viscous'])
    tau = np.asarray(v2['wall_shear_Pa'], dtype=float).copy()
    tau[3] = np.nan
    v2['wall_shear_Pa'] = tau
    bozuk2['viscous'] = v2
    assert assess_separation(bozuk2, LULE_PB_SOK)['criteria'][
        CRITERION_CFD_TAU_W]['available'] is False


def test_duz_alanlar_UYENIN_KENDISINDEN_doluyor_YAPISAL(monkeypatch):
    """YAPISAL CASUS: düz alanlar gerçekten `_threshold_member`'dan geliyor.

    NEDEN VAR — ÖLÇÜLEN BEKÇİ DELİĞİ (parti 40, mutasyon M7): düz alanları
    ikinci bir aramadan doldurmak (``float(np.min(p_div)) / threshold``)
    DEĞER OLARAK aynı sonucu verir, bu yüzden sayısal karşılaştırma yapan
    ``test_duz_alanlar_summerfield_UYESININ_ta_kendisi`` mutasyonu YEŞİL
    geçmişti (43/43). Kopyanın yasak olmasının sebebi değer değil KAYNAK
    birliğidir: iki hesap zamanla ayrışır. Bu bekçi kaynağı sınar —
    üyenin ürettiği sayı DEĞİŞTİRİLİR ve düz alanların onu izlediği
    ölçülür.
    """
    gercek = cfd_sep._threshold_member
    imza = {'z': 4242.0, 'margin': -13.5, 'idx': 7, 'len': 1234.0}

    def casus(name, *a, **kw):
        m = gercek(name, *a, **kw)
        if name == 'summerfield':
            m = dict(m, separated=True, separation_index=imza['idx'],
                     separation_z_m=imza['z'], margin_min=imza['margin'],
                     separated_length_m=imza['len'],
                     stations_below_threshold=99)
        return m

    monkeypatch.setattr(cfd_sep, '_threshold_member', casus)
    res = _sentetik_sonuc(ASIRI_PROFIL)
    a = assess_separation(res, ASIRI_PA)
    assert a['separation_z_m'] == imza['z'], (
        'düz separation_z_m üyeden GELMİYOR — ikinci bir arama var')
    assert a['separation_index'] == imza['idx']
    assert a['wall_pressure_margin_min'] == imza['margin'], (
        'düz wall_pressure_margin_min üyeden GELMİYOR — kopya hesap var')
    assert a['separated_length_m'] == imza['len']
    assert a['stations_below_threshold'] == 99
    assert a['separated'] is True
