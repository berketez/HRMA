"""F2b-3 künyeli tablo bekçileri — QSHOD (A, B) bantları + yakıt termal tablosu.

İki tabloyu birden korur:
    hrma/stability/bands.py         — QSHOD (A, B) bantları (karar 3 zarfı)
    hrma/stability/fuel_thermal.py  — c_p/k + REFERANS SICAKLIK (karar 4)

Bekçi felsefesi: sayılar KAYNAĞA sabitlenir (aşağıdaki beklenen değerler
doğrulanan kaynakların kendi yayımladıklarıdır — sayfa/tablo künyeleriyle);
şema bütünlüğü yapısal kuruculara ek olarak burada da taranır ki gelecekte
kurucular gevşetilirse tablo yine kırmızıya düşsün.

KAYNAK SABİTLERİ (bu dosyada beklenen değerlerin künyesi):
    - Culick & Yang 1990 Ek örneği: A=6,0, B=0,55, n=0,3, p̄=10,6 MPa,
      T=3539 K (tests/test_stability_tepki.py'nin sayısal çapasıyla aynı).
    - AG-AVT-039 Fig. 2.17 (s. 2-32): A-35 için A=14, B=0,8, n=0,49;
      T-burner verisi 200-800 psi. Fig. 2.16 (s. 2-31): A-13 için A=40,
      B=1,1; veri 100-800 psi. (Görsel olarak doğrulandı, 2026-08-17.)
    - Perry 1970 Caltech tezi Tablo A (s. 28): A-13 alev sıcaklığı 2100 K,
      n=0,42 @300 psig; A-35 alev sıcaklığı 2160 K. (Görsel doğrulandı.)
    - Karabeyoglu ve ark. JPP 18(3) 2002 Tablo 2 (s. 616): Wax sıvı faz
      c_p=2,92 kJ/kg-K, k=0,12 W/m-K; dipnot a referans sıcaklık kuralı
      (erime 339,6 K ile kaynama 727,4 K ortalaması = 533,5 K).
"""

import math
import re

import pytest

from hrma.analysis.valve_feedline import PSI_PA
from hrma.stability import bands, fuel_thermal
from hrma.stability.bands import (
    FAMILY_BANDS,
    MissingBandRecord,
    QSHOD_BAND_RECORDS,
    QSHODBandRecord,
    bands_for_family,
)
from hrma.stability.fuel_thermal import (
    FUEL_THERMAL_RECORDS,
    FuelThermalRecord,
    MISSING_NOT_FOUND,
    MISSING_NOT_SEARCHED,
    MissingProperty,
    PHASE_LIQUID,
    ThermalProperty,
    compare_with_propellant_database,
)
from hrma.stability.response import (
    CONFIDENCE_EXTRAPOLATED,
    CONFIDENCE_FIRM,
    QSHODBand,
    qshod_response_band,
)

# Yıl içeren künye deseni: kaynak cümlesi en az bir yayın yılı taşımalı.
_YEAR = re.compile(r'\b(19|20)\d{2}\b')


# ===========================================================================
# 1. Bant tablosu — şema bütünlüğü
# ===========================================================================
def test_bant_kayitlari_bos_degil():
    dolu = [r for r in QSHOD_BAND_RECORDS.values()
            if isinstance(r, QSHODBandRecord)]
    bos = [r for r in QSHOD_BAND_RECORDS.values()
           if isinstance(r, MissingBandRecord)]
    assert len(dolu) >= 3, 'en az üç doğrulanmış bant kaydı bekleniyor'
    assert len(bos) >= 2, 'şeker yakıtlarının boş-beyan kayıtları kayıp'


def test_her_dolu_kayit_zarfi_eksiksiz():
    """Her dolu kayıt: QSHODBand + güven notu + tarih (karar 3 şeması)."""
    for rid, rec in QSHOD_BAND_RECORDS.items():
        if not isinstance(rec, QSHODBandRecord):
            continue
        band = rec.band
        assert isinstance(band, QSHODBand), rid
        assert band.formulation_class.strip(), rid
        assert band.source.strip(), rid
        low, high = band.pressure_range_Pa
        assert 0.0 < low <= high, rid
        t_low, t_high = band.temperature_range_K
        assert 0.0 < t_low <= t_high, rid
        assert rec.confidence_note.strip(), rid
        assert re.fullmatch(r'\d{4}-\d{2}-\d{2}', rec.retrieved), rid


def test_kaynaksiz_sayi_yok():
    """Künye disiplini: her dolu kaydın kaynağı yıl + md5 taşır; boş
    kayıt YAPISAL olarak sayı taşıyamaz (slots)."""
    for rid, rec in QSHOD_BAND_RECORDS.items():
        if isinstance(rec, QSHODBandRecord):
            assert _YEAR.search(rec.band.source), (
                f'{rid}: kaynak künyesi yayın yılı taşımıyor')
            assert 'md5' in rec.band.source, (
                f'{rid}: kaynak künyesi indirilen belgenin md5 kanıtını '
                f'taşımıyor')
        else:
            assert isinstance(rec, MissingBandRecord), rid
            assert not hasattr(rec, 'band'), (
                f'{rid}: boş kayıt sayı alanı taşıyor — yapısal kural '
                f'delinmiş')
            assert len(rec.reason) >= 40, rid
            assert rec.status == bands.MISSING_NOT_FOUND, rid


def test_bos_kayit_beyani_arandigini_soyler():
    """'Bulunamadı' beyanı NE arandığını ve tarihi söylemek zorunda."""
    for rid in ('kndx', 'knsu'):
        rec = QSHOD_BAND_RECORDS[rid]
        assert isinstance(rec, MissingBandRecord), rid
        assert '2026-08-17' in rec.reason, rid
        assert 'AG-AVT-039' in rec.reason, rid


# ===========================================================================
# 2. Bant tablosu — kaynak-sabitli değerler
# ===========================================================================
def test_cy1990_kaydi_kaynak_degerlerinde():
    """Culick & Yang 1990 örneği: depodaki sayısal çapayla bire bir."""
    band = QSHOD_BAND_RECORDS['cy1990_worked_example'].band
    assert band.a_range == (6.0, 6.0)
    assert band.b_range == (0.55, 0.55)
    assert band.pressure_exponent_n == pytest.approx(0.3)
    assert band.pressure_range_Pa == (1.06e7, 1.06e7)
    assert band.temperature_range_K == (3539.0, 3539.0)
    assert 'Culick' in band.source and '1990' in band.source


def test_a35_kaydi_kaynak_degerlerinde():
    """AG-AVT-039 Fig. 2.17 + s. 6-12 + Perry Tablo A değerleri."""
    rec = QSHOD_BAND_RECORDS['a35_ap_polyurethane']
    band = rec.band
    assert band.a_range == (14.0, 14.0)
    assert band.b_range == (0.8, 0.8)
    assert band.pressure_exponent_n == pytest.approx(0.49)
    # Fig. 2.17 lejantı: 200-800 psi (tek psi->Pa kaynağından çevrilir).
    assert band.pressure_range_Pa[0] == pytest.approx(200.0 * PSI_PA)
    assert band.pressure_range_Pa[1] == pytest.approx(800.0 * PSI_PA)
    # Perry 1970 Tablo A: alev sıcaklığı 2160 K @ 300 psig.
    assert band.temperature_range_K == (2160.0, 2160.0)
    assert 'Perry' in band.source and 'Beckstead' in band.source
    # Kaynağın kendi çekincesi güven notunda taşınmalı (fit benzersiz değil
    # + Perry'nin n=0 plato ölçümüyle üstel çelişkisi).
    assert 'UNIQUE' in rec.confidence_note
    assert 'n=0.0' in rec.confidence_note


def test_a13_kaydi_kaynak_degerlerinde_ve_dusuk_guvenli():
    """Fig. 2.16 fiti + Perry n/T; kaynak uyarıları DÜŞÜK güvene bağlanır."""
    rec = QSHOD_BAND_RECORDS['a13_ap_pban']
    band = rec.band
    assert band.a_range == (40.0, 40.0)
    assert band.b_range == (1.1, 1.1)
    assert band.pressure_exponent_n == pytest.approx(0.42)   # Perry Tablo A
    assert band.pressure_range_Pa[0] == pytest.approx(100.0 * PSI_PA)
    assert band.pressure_range_Pa[1] == pytest.approx(800.0 * PSI_PA)
    assert band.temperature_range_K == (2100.0, 2100.0)      # Perry Tablo A
    assert rec.confidence == bands.RECORD_CONFIDENCE_LOW
    assert 'clearly unsuccessful' in rec.confidence_note
    assert 'PBAN' in band.formulation_class


def test_fiziksel_akla_yatkinlik_kaynak_araliklarinda():
    """Kaynakların kendi grafik/metin aralıkları: A (0, 200], B (0, 2].

    Üst sınırlar uydurma değildir: AG-AVT-039 Fig. 6.20'nin A-eğri ailesi
    A=12..200 aralığını, Fig. 6.8 B=0,7..1,4 bölgelerini yayımlar; tablodaki
    her fit bu yayınlanmış zeminin içindedir.
    """
    for rid, rec in QSHOD_BAND_RECORDS.items():
        if not isinstance(rec, QSHODBandRecord):
            continue
        for a in rec.band.a_range:
            assert 0.0 < a <= 200.0, f'{rid}: A={a} kaynak zemini dışında'
        for b in rec.band.b_range:
            assert 0.0 < b <= 2.0, f'{rid}: B={b} kaynak zemini dışında'
        assert 0.0 < rec.band.pressure_exponent_n < 1.0, rid


# ===========================================================================
# 3. Aile eşlemesi — katalogla canlı uyum
# ===========================================================================
def test_aile_indeksi_katalogdaki_katilari_kapsar():
    """Depo kataloğundaki HER katı aile eşleme tablosunda olmalı (canlı)."""
    from hrma.data.propellant_database import PropellantDatabase
    solids = PropellantDatabase().get_propellant_list('solid_propellants')
    assert solids, 'katalog katı listesi boş — ölçüm anlamsız'
    for family in solids:
        assert family in FAMILY_BANDS, (
            f'katalog ailesi {family!r} bant eşlemesinde yok — tablo '
            f'katalogdan koptu')


def test_aile_eslesme_notu_zorunlu_ve_sinif_uyusmazligi_beyanli():
    for family, entry in FAMILY_BANDS.items():
        assert entry['mapping_basis'].strip(), family
    # apcp -> CY örneği YALNIZ 'en yakın sınıf' beyanıyla yayımlanabilir.
    assert 'NEAREST CLASS' in FAMILY_BANDS['apcp']['mapping_basis']
    # pban -> A-13 metal yükü uyuşmazlığı beyanlı.
    assert 'MISMATCH' in FAMILY_BANDS['pban']['mapping_basis']


def test_bilinmeyen_aile_sessizce_bos_donmez():
    with pytest.raises(ValueError, match='Unknown propellant family'):
        bands_for_family('rp1')


def test_aile_erisimi_kayitlari_ve_beyani_birlikte_verir():
    r = bands_for_family('pban')
    assert [rec.record_id for rec in r['records']] == ['a13_ap_pban']
    assert r['missing'] is None
    r = bands_for_family('knsu')
    assert r['records'] == []
    assert isinstance(r['missing'], MissingBandRecord)
    assert 'verdict' not in str(r)  # eşik yolu hükümsüz kalır


# ===========================================================================
# 4. response.py entegrasyonu — zarf rozetleri gerçek kayıtlarla
# ===========================================================================
_A35 = QSHOD_BAND_RECORDS['a35_ap_polyurethane'].band
# Zarf-içi/dışı çağrılarda kullanılan temsili yakıt dinamiği girdileri
# (κ ve ṙ_b bant zarfına girmez; yalnız Ω'yı kurar).
_KAPPA = 1.0e-7
_RB = 0.005


def test_zarf_ici_calisma_noktasi_firm():
    """A-35 zarfının içindeki nokta (3 MPa, 2160 K) FIRM rozeti üretmeli."""
    result = qshod_response_band(
        _A35, 2.0 * math.pi * 500.0, _KAPPA, _RB,
        pressure_Pa=3.0e6, temperature_K=2160.0)
    assert result['confidence'] == CONFIDENCE_FIRM
    assert 'inside the validity envelope' in result['confidence_basis']
    # Dejenere bant: dört köşe aynı -> min == maks.
    assert result['response_real_min'] == pytest.approx(
        result['response_real_max'])


@pytest.mark.parametrize('point,expected_word', [
    ((1.2e7, 2160.0), 'pressure'),      # 12 MPa: veri 1,38-5,52 MPa'nın dışı
    ((3.0e6, 3539.0), 'temperature'),   # CY alev sıcaklığı A-35 zarfı dışı
])
def test_zarf_disi_calisma_noktasi_extrapolated(point, expected_word):
    """Zarf dışı: sonuç gizlenmez, EXTRAPOLATED rozetlenir (karar 3)."""
    result = qshod_response_band(
        _A35, 2.0 * math.pi * 500.0, _KAPPA, _RB,
        pressure_Pa=point[0], temperature_K=point[1])
    assert result['confidence'] == CONFIDENCE_EXTRAPOLATED
    assert expected_word in result['confidence_basis']
    assert result['response_real_min'] is not None


def test_kayit_sozlugu_zarfi_aynen_tasir():
    d = QSHOD_BAND_RECORDS['a13_ap_pban'].as_dict()
    assert d['band']['pressure_range_Pa'] == (
        pytest.approx(100.0 * PSI_PA), pytest.approx(800.0 * PSI_PA))
    assert d['record_confidence'] == bands.RECORD_CONFIDENCE_LOW
    assert d['retrieved'] == '2026-08-17'


# ===========================================================================
# 5. Termal tablo — şema bütünlüğü (karar 4)
# ===========================================================================
def test_termal_tablo_katalogdaki_yakitlari_kapsar():
    """Katalogdaki katı + hibrit yakıt aileleri tabloda olmalı (canlı)."""
    from hrma.data.propellant_database import PropellantDatabase
    db = PropellantDatabase()
    hedef = (db.get_propellant_list('solid_propellants')
             + db.get_propellant_list('hybrid_fuels'))
    assert hedef
    for family in hedef:
        assert family in FUEL_THERMAL_RECORDS, (
            f'katalog yakıtı {family!r} termal tabloda yok')


def test_her_dolu_termal_alan_referans_sicaklikli_ve_kunyeli():
    """KARAR 4: değer varsa referans sıcaklık + alan-düzeyi künye VAR."""
    for family, rec in FUEL_THERMAL_RECORDS.items():
        assert isinstance(rec, FuelThermalRecord), family
        for slot in ('specific_heat', 'thermal_conductivity'):
            field = getattr(rec, slot)
            if isinstance(field, ThermalProperty):
                t_low, t_high = field.reference_temperature_K
                assert 0.0 < t_low <= t_high, (family, slot)
                assert field.reference_basis.strip(), (family, slot)
                assert _YEAR.search(field.source), (family, slot)
                assert field.phase in ('solid', 'liquid'), (family, slot)
            else:
                assert isinstance(field, MissingProperty), (family, slot)
                assert not hasattr(field, 'value'), (
                    f'{family}.{slot}: boş alan sayı taşıyor — yapısal '
                    f'kural delinmiş')
                assert len(field.reason) >= 40, (family, slot)


def test_bulunamadi_ile_taranmadi_ayrimi_durust():
    """'not_found' yalnız arananlarda; taranmayanlar 'not_searched'."""
    searched = ('htpb', 'apcp', 'knsu', 'kndx', 'pban')
    unsearched = ('pe', 'pmma', 'abs')
    for family in searched:
        rec = FUEL_THERMAL_RECORDS[family]
        for slot in ('specific_heat', 'thermal_conductivity'):
            field = getattr(rec, slot)
            if isinstance(field, MissingProperty):
                assert field.status == MISSING_NOT_FOUND, (family, slot)
                assert '2026-08-17' in field.reason, (family, slot)
    for family in unsearched:
        rec = FUEL_THERMAL_RECORDS[family]
        for slot in ('specific_heat', 'thermal_conductivity'):
            field = getattr(rec, slot)
            assert isinstance(field, MissingProperty), (family, slot)
            assert field.status == MISSING_NOT_SEARCHED, (family, slot)


def test_parafin_degerleri_kaynak_tablosunda():
    """JPP 2002 Tablo 2 'Wax' sütunu: SIVI faz, dipnot a referansıyla."""
    rec = FUEL_THERMAL_RECORDS['paraffin']
    cp = rec.specific_heat
    k = rec.thermal_conductivity
    assert isinstance(cp, ThermalProperty) and isinstance(k, ThermalProperty)
    assert cp.value == pytest.approx(2920.0)     # 2,92 kJ/kg-K -> SI
    assert k.value == pytest.approx(0.12)
    assert cp.phase == PHASE_LIQUID and k.phase == PHASE_LIQUID
    # Dipnot a: (339,6 + 727,4)/2 = 533,5 K — kaynağın kendi sayıları.
    assert cp.reference_temperature_K[0] == pytest.approx(533.5)
    assert '339.6' in cp.reference_basis and '727.4' in cp.reference_basis
    assert 'Table 2' in cp.source and 'md5' in cp.source
    # Katı-faz c_p'nin NEDEN taşınmadığı aile notunda beyanlı (karar 4).
    assert 'decision 4' in rec.notes


def test_referans_sicakliksiz_deger_kurulamaz():
    """Karar 4'ün yapısal bekçisi: T_ref'siz ThermalProperty ValueError."""
    with pytest.raises(ValueError, match='reference_temperature_K'):
        ThermalProperty(
            quantity='specific_heat', value=2030.0, phase='solid',
            reference_temperature_K=None,
            reference_basis='x', source='y 2002')


def test_kaynaksiz_deger_kurulamaz():
    with pytest.raises(ValueError, match='mandatory'):
        ThermalProperty(
            quantity='thermal_conductivity', value=0.12, phase='liquid',
            reference_temperature_K=(533.5, 533.5),
            reference_basis='footnote a', source='   ')


def test_bos_alan_sahte_durumla_kurulamaz():
    with pytest.raises(ValueError, match='status'):
        MissingProperty('specific_heat', 'maybe', 'x' * 80)


# ===========================================================================
# 6. Eski tabloyla fark ölçümü (göç KARARI değil, karar GİRDİSİ)
# ===========================================================================
def test_fark_olcumu_canli_ve_eksiksiz():
    rep = compare_with_propellant_database()
    rows = rep['rows']
    assert set(rows) == set(FUEL_THERMAL_RECORDS)
    s = rep['summary']
    # Eski tabloda c_p/k alanları VAR ama hiçbirinde alan-düzeyi künye ya da
    # referans sıcaklık YOK — bu partinin ölçtüğü gerçek boşluk.
    assert s['db_cp_k_fields_present'] >= 10
    assert s['db_cp_k_fields_with_field_level_citation'] == 0
    assert s['db_cp_k_fields_with_reference_temperature'] == 0
    assert s['new_verified_fields'] == 2      # parafin sıvı c_p + k
    assert 'nothing is migrated here' in rep['basis']


def test_fark_olcumu_parafin_faz_riskini_isaretler():
    """Yeni değer SIVI faz; eski tablo faz etiketsiz — risk bayraklı."""
    row = compare_with_propellant_database()['rows']['paraffin']
    assert row['specific_heat_phase_mismatch_risk'] is True
    assert row['thermal_conductivity_phase_mismatch_risk'] is True
    assert row['db_phase_declared'] is False
    assert row['db_reference_temperature_declared'] is False
    # Fark yönü ölçülü: sıvı c_p eski katımsı değerden BÜYÜK (%36,5).
    assert row['specific_heat_delta_rel'] == pytest.approx(0.3645, abs=1e-3)


def test_fark_olcumu_eski_tabloyu_degistirmez():
    """Karşılaştırma salt-okur: DB nesnesi çağrı öncesi/sonrası bit-aynı."""
    from hrma.data.propellant_database import PropellantDatabase
    before = repr(sorted(PropellantDatabase().database['paraffin'].items()))
    compare_with_propellant_database()
    after = repr(sorted(PropellantDatabase().database['paraffin'].items()))
    assert before == after
