"""ÖH Dalga-32 · fizik kulvarı a1 bekçileri.

Kalem: **P6B4-03** — "Aynı yanıtta iki karışım süresi". Kalemin üç ayağı var:

  (a) iki zaman ölçeği çevrime aday olarak VERİLMİYORDU
      → D31 fizik a1 (``chug_tau_sensitivity`` çekirdeği) +
        D32 termo-ucus a1 (motor bağlantısı, OH-D31-08) ile kapandı;
  (b) HÜKÜM ölçekten ölçeğe dönüyor
      → D31'de ölçüldü (``verdict_is_tau_sensitive``, monotonluk teoremi);
  (c) **FREKANS 88,16 → 240,02 Hz (2,7×) değişiyor**  ← BU DOSYANIN KONUSU.

(c) açıktı: ``tau_choice_sensitivity`` YALNIZ hükmün τ'ya duyarlılığını
bildiriyordu. Defterin ölçtüğü koşuda iki aday da "unstable" verdiği için
``verdict_is_tau_sensitive`` **False** çıkıyor — oysa yayımlanan
``frequency_hz`` adaylar arasında **90,67 Hz ⟷ 262,39 Hz (2,894×)**.
Tek o bayrağa bakan tüketici, yayımlanan tek frekansı kesinmiş gibi alıp
sönümleme/akustik boşluk tasarımını 2,9× yanlış bir sayıya dayandırır.
Ölçüm: ``docs/scofield/raw/OH/D32/fizik/a1/once_p6b403_frekans.json``
(bandı bildiren alan sayısı **0**) → ``sonra_p6b403_frekans.json`` (**3**).

Monotonluk savının kapsamı: HÜKÜM. Frekansı KAPSAMAZ — bu dosyanın
``test_p6b403c_monotonluk_frekansi_kapsamaz`` bekçisi bunu ölçer.

Her bekçi TERS-MUTASYONLA kanıtlanmıştır:
``docs/scofield/raw/OH/D32/fizik/a1/mutasyon_p6b403c.json``.
"""

import math

import pytest

from hrma.stability.chug import assess_chug, chug_tau_sensitivity


# Defterin ölçtüğü koşu (D31 fizik a1 denetim_kesinti.json ile AYNI girdiler).
J = 0.12
TAU_C_S = 1.5436660091922559e-3
TAU_ATOM_S = 4.489e-3          # enjektörün ikincil parçalanma süresi
TAU_MIX_S = 1.264e-3           # enjektörün karışma kalış süresi


def _defter_kosusu():
    """Defterin koşusunun duyarlılık bloğu (motorun verdiği aday ile)."""
    sonuc = assess_chug(dp_ratio_j=J, tau_s=TAU_ATOM_S, tau_c_s=TAU_C_S,
                        alternative_taus={'mixing_residence_time':
                                          TAU_MIX_S})
    blok = sonuc.get('tau_choice_sensitivity')
    assert blok is not None, 'aday verildi, duyarlılık bloğu konmalıydı'
    return sonuc, blok


# ---------------------------------------------------------------------------
# (c) FREKANS BANDI — kalemin asıl açık ayağı
# ---------------------------------------------------------------------------

def test_p6b403c_frekans_bandi_yayimlanir():
    """Band ÖLÇÜLÜR ve yayımlanır: 90,67 ⟷ 262,39 Hz, 2,894×.

    Kusur buydu: bandı bildiren alan sayısı SIFIRDI.
    """
    _, blok = _defter_kosusu()
    band = blok.get('frequency_hz_span')
    assert band is not None, (
        'iki aday da frekans çözdü; band yayımlanmalı (kusur: alan yoktu)')

    assert band['min_candidate'] == 'selected'
    assert band['max_candidate'] == 'mixing_residence_time'
    # Sayılar defterin mertebesinde (D31 ölçümü: 90,673 ⟷ 262,386 Hz).
    assert band['min_hz'] == pytest.approx(90.6729403242403, rel=1e-9)
    assert band['max_hz'] == pytest.approx(262.3863297453567, rel=1e-9)
    assert band['ratio'] == pytest.approx(2.8937666387246397, rel=1e-9)
    # Defterin "2,7×" iddiası: band en az iki katlık.
    assert band['ratio'] > 2.0
    assert band['unresolved_candidates'] == []
    assert sorted(band['resolved_candidates']) == ['mixing_residence_time',
                                                   'selected']


def test_p6b403c_hukum_duyarsizken_frekans_duyarli_gorulur():
    """KUSURUN ÇEKİRDEĞİ: hüküm bayrağı False iken frekans bayrağı True.

    Bu koşuda iki aday da "unstable" → ``verdict_is_tau_sensitive`` False.
    Tüketici yalnız ona bakarsa 2,894×'lik frekans bandını GÖRMEZ.
    """
    _, blok = _defter_kosusu()
    assert blok['verdict_is_tau_sensitive'] is False, (
        'bu koşunun ayırt ediciliği: hüküm ekseninde duyarlılık YOK')
    assert blok['frequency_is_tau_sensitive'] is True, (
        'frekans ekseninde duyarlılık VAR — kusur tam buydu')
    # Tüketicinin bakacağı TEK bayrak doğruyu söylemeli.
    assert blok['is_tau_sensitive'] is True


def test_p6b403c_monotonluk_frekansi_kapsamaz():
    """Monotonluk savının KAPSAMI ölçülür: hüküm evet, frekans hayır.

    τ büyüdükçe hüküm yalnız "unstable" yönüne gider (D31 teoremi), ama
    frekans τ ile DÜŞER. Yani tek bir "konservatif" seçim frekansı da
    konservatif yapmaz; band bu yüzden ayrı ölçülür.
    """
    # En konservatif aday (hüküm ekseni) = en BÜYÜK τ = atomizasyon.
    _, blok = _defter_kosusu()
    assert blok['most_conservative'] == 'selected'
    adaylar = blok['candidates']
    assert adaylar['selected']['tau_s'] > \
        adaylar['mixing_residence_time']['tau_s']
    # Ama frekansı EN BÜYÜK olan aday, τ'su en KÜÇÜK olandır:
    assert blok['frequency_hz_span']['max_candidate'] == \
        'mixing_residence_time'
    # Yani "en konservatif hüküm" adayı en yüksek frekansı VERMİYOR.
    assert blok['frequency_hz_span']['max_candidate'] != \
        blok['most_conservative']


@pytest.mark.parametrize('j', [0.05, 0.12, 0.30])
def test_p6b403c_frekans_tau_da_monoton_azalan(j):
    """Frekansın τ'da azaldığı ölçülür (bandın yönü tesadüf değil)."""
    taular = [0.8e-3, 1.264e-3, 2.5e-3, 4.489e-3, 8.0e-3]
    blok = chug_tau_sensitivity(j, TAU_C_S, None,
                                {f't{i}': t for i, t in enumerate(taular)})
    assert blok is not None
    frekanslar = [blok['candidates'][f't{i}']['frequency_hz']
                  for i in range(len(taular))]
    if any(f is None for f in frekanslar):
        pytest.skip('bu J değerinde kök çözülmeyen aday var')
    for onceki, sonraki in zip(frekanslar, frekanslar[1:]):
        assert sonraki < onceki, (
            f'τ büyürken frekans düşmeli (J={j}): {frekanslar}')
    # Band, uçları doğru yakalamalı.
    assert blok['frequency_hz_span']['max_candidate'] == 't0'
    assert blok['frequency_hz_span']['min_candidate'] == \
        f't{len(taular) - 1}'


# ---------------------------------------------------------------------------
# FAIL-CLOSED — ölçülmeyen band "duyarsız" diye yayımlanmaz
# ---------------------------------------------------------------------------

def test_p6b403c_olculemeyen_band_false_degil_none():
    """Tek aday çözülürse band YOK; bayrak False DEĞİL None + gerekçe.

    False "ölçtüm, duyarsız" der; burada ölçüm yoktur. Doktrin 1.
    """
    blok = chug_tau_sensitivity(J, TAU_C_S, None, {'yalniz': TAU_ATOM_S})
    assert blok is not None
    assert blok['frequency_hz_span'] is None
    assert blok['frequency_is_tau_sensitive'] is None, (
        'ölçülmeyen eksen False diye yayımlanamaz (sessiz güven)')
    assert blok['is_tau_sensitive'] is None
    gerekce = blok['frequency_span_not_resolved_reason']
    assert isinstance(gerekce, str) and gerekce, 'gerekçe ADIYLA durmalı'
    assert 'not measured' in gerekce.lower()


def test_p6b403c_esit_tau_bandi_duyarsiz_olculur():
    """İki aday AYNI τ ise band ölçülür ve duyarsız çıkar (eşik yok)."""
    blok = chug_tau_sensitivity(J, TAU_C_S, None,
                                {'a': TAU_ATOM_S, 'b': TAU_ATOM_S})
    assert blok is not None
    assert blok['frequency_hz_span']['ratio'] == 1.0
    assert blok['frequency_is_tau_sensitive'] is False
    assert blok['is_tau_sensitive'] is False
    assert blok['frequency_span_not_resolved_reason'] is None


def test_p6b403c_alan_hic_aday_verilmezse_konmaz():
    """Aday verilmezse duyarlılık bloğu HİÇ konmaz (çapa bit-aynı kalır)."""
    sonuc = assess_chug(dp_ratio_j=J, tau_s=TAU_ATOM_S, tau_c_s=TAU_C_S)
    assert 'tau_choice_sensitivity' not in sonuc


# ---------------------------------------------------------------------------
# (d) KIYASSIZ BLOK — ``setdefault('selected', tau)`` fail-open'ı
# ---------------------------------------------------------------------------
#
# Ölçüm: once_p6b403_tekaday.json — çağıranın adaylarının hepsi geçersizken
# blok YİNE yayımlanıyordu (3/3 vaka), üstelik ``most_conservative:
# 'selected'`` diyerek. Hiçbir şey kıyaslanmamıştı. sonra_*: 0/3.

@pytest.mark.parametrize('kotu_aday', [
    {'mixing_residence_time': float('nan')},
    {'mixing_residence_time': -1.0},
    {'mixing_residence_time': 0.0},
    {'mixing_residence_time': None},
    {'a': float('inf'), 'b': 'metin'},
])
def test_p6b403d_kiyassiz_blok_yayimlanmaz(kotu_aday):
    """Geçerli ALTERNATİF kalmadıysa duyarlılık alanı hiç konmaz.

    Kusur: tek başına 'selected' kalan blok ``most_conservative:
    'selected'`` diyerek "seçimimiz en konservatif" diye okunuyordu.
    """
    sonuc = assess_chug(dp_ratio_j=J, tau_s=TAU_ATOM_S, tau_c_s=TAU_C_S,
                        alternative_taus=kotu_aday)
    assert 'tau_choice_sensitivity' not in sonuc, (
        'kıyas yokken "duyarlılık" yayımlanamaz (fail-open)')


def test_p6b403d_gecerli_alternatif_varsa_blok_durur():
    """Kapı yalnız KIYASSIZ bloğu keser; gerçek kıyas geçmeye devam eder."""
    sonuc = assess_chug(dp_ratio_j=J, tau_s=TAU_ATOM_S, tau_c_s=TAU_C_S,
                        alternative_taus={'mixing_residence_time': TAU_MIX_S,
                                          'kotu': float('nan')})
    blok = sonuc.get('tau_choice_sensitivity')
    assert blok is not None, 'geçerli alternatif vardı, blok durmalıydı'
    assert set(blok['candidates']) == {'selected', 'mixing_residence_time'}
    assert 'kotu' not in blok['candidates']


def test_p6b403c_band_sayilari_adaylarla_tutarli():
    """Band, adayların KENDİ frekanslarından gelir — ikinci hesap yok."""
    _, blok = _defter_kosusu()
    band = blok['frequency_hz_span']
    frekanslar = [v['frequency_hz'] for v in blok['candidates'].values()
                  if v['frequency_hz'] is not None]
    assert band['min_hz'] == min(frekanslar)
    assert band['max_hz'] == max(frekanslar)
    assert band['ratio'] == max(frekanslar) / min(frekanslar)
    assert band['min_hz'] == \
        blok['candidates'][band['min_candidate']]['frequency_hz']
    assert band['max_hz'] == \
        blok['candidates'][band['max_candidate']]['frequency_hz']


def test_p6b403c_gecersiz_frekans_banda_girmez():
    """None/NaN/≤0 frekanslı aday banda GİRMEZ, adıyla çözülmeyene yazılır."""
    blok = chug_tau_sensitivity(J, TAU_C_S, None,
                                {'a': TAU_ATOM_S, 'b': TAU_MIX_S})
    assert blok is not None
    band = blok['frequency_hz_span']
    for ad in band['resolved_candidates']:
        f = blok['candidates'][ad]['frequency_hz']
        assert f is not None and math.isfinite(f) and f > 0.0
    for ad in band['unresolved_candidates']:
        f = blok['candidates'][ad]['frequency_hz']
        assert f is None or not math.isfinite(f) or f <= 0.0


def test_p6b403c_basis_metni_kapsami_soyluyor():
    """Künye, monotonluğun frekansı kapsamadığını AÇIKÇA söylemeli."""
    _, blok = _defter_kosusu()
    metin = blok['_basis'].lower()
    assert 'frequency' in metin
    assert 'is_tau_sensitive' in blok['_basis']
    assert 'frequency_hz_span' in blok['_basis']
    band_metni = blok['frequency_hz_span']['_basis'].lower()
    assert 'verdict' in band_metni and 'frequency' in band_metni
