# hrma/stability/fuel_thermal.py — künyeli yakıt termal özellik tablosu (F2b-3)
"""Yakıt c_p / k tablosu — alan başına künye + REFERANS SICAKLIK zorunlu.

NEDEN YENİ TABLO (tasarım belgesi §8.1 karar 4):
    Mevcut ``hrma/data/propellant_database.py`` c_p/k değerleri blok-başına
    tek 'source' etiketi taşır ve o etiketler sayı kaynağı DEĞİLDİR (S8
    ölçümü; bu partide yeniden ölçüldü — ör. HTPB bloğu 'NASA SP-8075' der;
    SP-8064/8075 sınıfı monograflar HANGİ özelliklerin ölçüleceğini tanımlar,
    sayı YAYIMLAMAZ — SP-8064 tam metni indirilip OCR'la tarandı, 2026-08-17).
    Bu modül propellant_database'i DEĞİŞTİRMEZ (tüketicileri var; göç F2c/
    sonraki partinin kararı) — farklar ``compare_with_propellant_database``
    ile ÖLÇÜLÜR.

TABLO DİSİPLİNİ:
    1.  Değer ancak İNDİRİLİP DOĞRULANMIŞ kaynakla girer; kaynak alanı boşsa
        değer de yoktur (yapısal: ``MissingProperty``'nin sayı alanı yoktur).
    2.  KARAR 4: tek sayı taşınacaksa referans sıcaklık kaydın PARÇASIDIR.
        Kaynağı sayı yayımlayıp referans sıcaklık BEYAN ETMEYEN alan boş
        bırakılır ve gerekçede o değer 'taşınmadı' diye açıkça anılır
        (ör. parafin katı-faz c_p'si).
    3.  Faz beyanı zorunludur ('solid' | 'liquid'): parafinin doğrulanmış
        değerleri SIVI fazdır; eski tablo faz etiketi taşımaz — karışıklık
        karşılaştırma raporunda işaretlenir.
    4.  'not_found' yalnız GERÇEKTEN arananlar için kullanılır; bu partide
        hiç taranmayan aileler 'not_searched' beyanı taşır (yalan
        'bulunamadı' beyanı da yasaktır).

DOĞRULANAN KAYNAK:
    Karabeyoglu, M.A., Altman, D. & Cantwell, B.J., 'Combustion of
    Liquefying Hybrid Propellants: Part 1, General Theory', Journal of
    Propulsion and Power 18(3), 2002, ss. 610-620 — Tablo 2 (s. 616) görsel
    olarak doğrulandı; PDF md5 c7ecf5b49ce71e4f90194d2ad8ca5b5f (Stanford
    ~cantwell yayın dizininden, 2026-08-17).

ARANIP BULUNAMAYANLAR (gerekçeler kayıtlarda):
    HTPB, APCP, KNDX, KNSU, PBAN — sıcaklık-beyanlı, indirilebilir birincil
    bulunamadı; adaylar (Hanson-Parr & Parr 1999; Blomshield NAWCWD; JSSE
    2026 KNSU makalesi) gerekçelerde açık kalem olarak kayıtlıdır.
"""

import math

__all__ = [
    'PHASE_SOLID',
    'PHASE_LIQUID',
    'MISSING_NOT_FOUND',
    'MISSING_NOT_SEARCHED',
    'ThermalProperty',
    'MissingProperty',
    'FuelThermalRecord',
    'FUEL_THERMAL_RECORDS',
    'compare_with_propellant_database',
]

PHASE_SOLID = 'solid'
PHASE_LIQUID = 'liquid'
_PHASES = frozenset((PHASE_SOLID, PHASE_LIQUID))

#: Alan durumları: arandı-bulunamadı / bu partide taranmadı (dürüst ayrım).
MISSING_NOT_FOUND = 'not_found'
MISSING_NOT_SEARCHED = 'not_searched'
_MISSING_STATUSES = frozenset((MISSING_NOT_FOUND, MISSING_NOT_SEARCHED))

_QUANTITY_UNITS = {
    'specific_heat': 'J_kgK',
    'thermal_conductivity': 'W_mK',
}


class ThermalProperty:
    """Tek doğrulanmış alan: değer + faz + referans sıcaklık + künye.

    Kurucu, KARAR 4'ü şema düzeyinde zorlar: referans sıcaklıksız ya da
    kaynaksız değer KURULAMAZ.
    """

    __slots__ = ('quantity', 'value', 'unit', 'phase',
                 'reference_temperature_K', 'reference_basis', 'source')

    def __init__(self, quantity, value, phase, reference_temperature_K,
                 reference_basis, source):
        if quantity not in _QUANTITY_UNITS:
            raise ValueError(
                f'quantity must be one of {sorted(_QUANTITY_UNITS)} '
                f'(got {quantity!r}).')
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(float(value)) or float(value) <= 0.0):
            raise ValueError(
                f'{quantity}: value must be a positive finite number in SI '
                f'(got {value!r}).')
        if phase not in _PHASES:
            raise ValueError(
                f'{quantity}: phase must be one of {sorted(_PHASES)} '
                f'(got {phase!r}).')
        try:
            t_low, t_high = reference_temperature_K
        except (TypeError, ValueError):
            raise ValueError(
                f'{quantity}: reference_temperature_K must be a (low, high) '
                f'pair in kelvin — a single number without its temperature '
                f'is not published (design doc §8.1 decision 4); got '
                f'{reference_temperature_K!r}.') from None
        t_low, t_high = float(t_low), float(t_high)
        if not (math.isfinite(t_low) and math.isfinite(t_high)
                and 0.0 < t_low <= t_high):
            raise ValueError(
                f'{quantity}: reference_temperature_K must satisfy '
                f'0 < low <= high (got {reference_temperature_K!r}).')
        for name, text in (('reference_basis', reference_basis),
                           ('source', source)):
            if not isinstance(text, str) or not text.strip():
                raise ValueError(
                    f'{quantity}: {name} is mandatory — an uncited or '
                    f'temperature-blind value is not published.')
        self.quantity = quantity
        self.value = float(value)
        self.unit = _QUANTITY_UNITS[quantity]
        self.phase = phase
        self.reference_temperature_K = (t_low, t_high)
        self.reference_basis = reference_basis.strip()
        self.source = source.strip()

    def as_dict(self):
        return {
            'quantity': self.quantity,
            'value': self.value,
            'unit': self.unit,
            'phase': self.phase,
            'reference_temperature_K': self.reference_temperature_K,
            'reference_basis': self.reference_basis,
            'source': self.source,
        }


class MissingProperty:
    """Boş alan beyanı — yapısal olarak SAYI TAŞIYAMAZ (slots'ta yok)."""

    __slots__ = ('quantity', 'status', 'reason')

    def __init__(self, quantity, status, reason):
        if quantity not in _QUANTITY_UNITS:
            raise ValueError(
                f'quantity must be one of {sorted(_QUANTITY_UNITS)} '
                f'(got {quantity!r}).')
        if status not in _MISSING_STATUSES:
            raise ValueError(
                f'{quantity}: status must be one of '
                f'{sorted(_MISSING_STATUSES)} (got {status!r}).')
        if not isinstance(reason, str) or len(reason.strip()) < 40:
            raise ValueError(
                f'{quantity}: a missing field must declare what was (or was '
                f'not) searched and why the field is empty (got {reason!r}).')
        self.quantity = quantity
        self.status = status
        self.reason = reason.strip()

    def as_dict(self):
        return {
            'quantity': self.quantity,
            'status': self.status,
            'reason': self.reason,
        }


class FuelThermalRecord:
    """Aile satırı: c_p alanı + k alanı + aile-düzeyi not."""

    __slots__ = ('family', 'specific_heat', 'thermal_conductivity', 'notes')

    def __init__(self, family, specific_heat, thermal_conductivity,
                 notes=''):
        if not isinstance(family, str) or not family.strip():
            raise ValueError('family is mandatory.')
        for name, field in (('specific_heat', specific_heat),
                            ('thermal_conductivity', thermal_conductivity)):
            if not isinstance(field, (ThermalProperty, MissingProperty)):
                raise ValueError(
                    f'{family}.{name}: field must be a ThermalProperty or a '
                    f'declared MissingProperty (got '
                    f'{type(field).__name__}).')
            if field.quantity != name:
                raise ValueError(
                    f'{family}.{name}: field carries quantity '
                    f'{field.quantity!r} — slot/quantity mismatch.')
        if not isinstance(notes, str):
            raise ValueError(f'{family}: notes must be a string.')
        self.family = family
        self.specific_heat = specific_heat
        self.thermal_conductivity = thermal_conductivity
        self.notes = notes.strip()

    def as_dict(self):
        return {
            'family': self.family,
            'specific_heat': self.specific_heat.as_dict(),
            'thermal_conductivity': self.thermal_conductivity.as_dict(),
            'notes': self.notes,
        }


_JPP2002_SOURCE = (
    "Karabeyoglu, M.A., Altman, D. & Cantwell, B.J., 'Combustion of "
    "Liquefying Hybrid Propellants: Part 1, General Theory', Journal of "
    'Propulsion and Power 18(3), 2002, pp. 610-620, Table 2 (p. 616), '
    "'Wax' column (model wax, MW 432.8 g/mol, melting 339.6 K, boiling "
    '727.4 K). PDF md5 c7ecf5b49ce71e4f90194d2ad8ca5b5f (Stanford '
    '~cantwell publications copy, verified 2026-08-17).')

# Tablo 2 dipnot a: sıvı özellikler erime (339,6 K) ile buharlaşma (727,4 K)
# sıcaklıklarının ORTALAMASINDA değerlendirilir — 533,5 K kaynağın kendi
# sayılarından aritmetiktir.
_JPP2002_TREF = ((339.6 + 727.4) / 2.0, (339.6 + 727.4) / 2.0)
_JPP2002_TREF_BASIS = (
    "Table 2 footnote a: 'Liquid properties other than surface tension are "
    "evaluated at a mean temperature between the melting and vaporization "
    "temperatures.' Mean of the source's own melting (339.6 K) and boiling "
    '(727.4 K) values = 533.5 K; the arithmetic is declared, both bounds '
    'are published in the same table.')

_HANSON_PARR_LEAD = (
    "Primary candidate for a temperature-resolved value: Hanson-Parr, D.M. "
    "& Parr, T.P., 'Thermal properties measurements of solid rocket "
    "propellant oxidizers and binder materials as a function of "
    "temperature', J. Energetic Materials 17(1), 1999, pp. 1-48 — "
    'paywalled; not retrievable this session (2026-08-17), so nothing is '
    'carried from it.')

FUEL_THERMAL_RECORDS = {
    # -- Parafin: JPP 2002 Tablo 2 (görsel doğrulandı) ---------------------
    'paraffin': FuelThermalRecord(
        family='paraffin',
        specific_heat=ThermalProperty(
            quantity='specific_heat',
            value=2920.0,                      # 2.92 kJ/kg-K, sıvı faz
            phase=PHASE_LIQUID,
            reference_temperature_K=_JPP2002_TREF,
            reference_basis=_JPP2002_TREF_BASIS,
            source=_JPP2002_SOURCE,
        ),
        thermal_conductivity=ThermalProperty(
            quantity='thermal_conductivity',
            value=0.12,                        # W/m-K, sıvı faz
            phase=PHASE_LIQUID,
            reference_temperature_K=_JPP2002_TREF,
            reference_basis=_JPP2002_TREF_BASIS,
            source=_JPP2002_SOURCE,
        ),
        notes=(
            'SOLID-phase c_p exists in the same table (2.03 kJ/kg-K, Wax '
            'column) but Table 2 states a reference temperature ONLY for '
            'the liquid-phase rows (footnote a); per design doc §8.1 '
            'decision 4 a number without its temperature is NOT carried — '
            'the solid value is recorded here as a lead, not as data. NOTE '
            "the phase mismatch against hrma/data/propellant_database.py "
            "('paraffin': c_p=2.14 kJ/kg-K, k=0.25 W/m-K, no phase or "
            'temperature stated, block source "Stanford University '
            'Research" — not a retrievable citation).'),
    ),

    # -- HTPB: sıcaklık-beyanlı birincil bulunamadı ------------------------
    'htpb': FuelThermalRecord(
        family='htpb',
        specific_heat=MissingProperty(
            quantity='specific_heat',
            status=MISSING_NOT_FOUND,
            reason=(
                'Searched 2026-08-17; no downloadable primary stating a '
                'reference temperature was verified. Leads NOT carried as '
                'data: Sun et al., Aerospace 10(8):692, 2023 (open access) '
                'Table 1 gives c_p,HTPB = 2900 J/kgK as a model constant '
                'with NO reference temperature; Hu et al. 2016 (Vanderbilt '
                'preprint) Table 1 gives a volumetric heat capacity 1.987 '
                'mJ/mm3K at 296 K with rho=950 kg/m3 (division would be '
                'this session\'s derivation, not a published value). '
                + _HANSON_PARR_LEAD),
        ),
        thermal_conductivity=MissingProperty(
            quantity='thermal_conductivity',
            status=MISSING_NOT_FOUND,
            reason=(
                'Searched 2026-08-17; no downloadable primary stating a '
                'reference temperature was verified. Lead NOT carried: Sun '
                'et al., Aerospace 10(8):692, 2023, Table 1 gives lambda_'
                'HTPB = 0.14 W/mK as a temperature-blind model constant. '
                + _HANSON_PARR_LEAD),
        ),
        notes=(
            "The existing propellant_database 'htpb' block cites 'NASA "
            "SP-8075' for its numbers (c_p=1.8 kJ/kg-K, k=0.2 W/m-K). "
            'MEASURED this batch: the sibling monograph SP-8064 (full scan '
            'OCR-searched) defines WHICH thermal properties to measure and '
            'publishes no propellant numbers; the SP-80xx citation class '
            'cannot be the origin of these values.'),
    ),

    # -- APCP: yakıt-düzeyi (kompozit) doğrulanmış değer bulunamadı --------
    'apcp': FuelThermalRecord(
        family='apcp',
        specific_heat=MissingProperty(
            quantity='specific_heat',
            status=MISSING_NOT_FOUND,
            reason=(
                'Searched 2026-08-17; no propellant-level (composite) '
                'AP/HTPB c_p with a stated reference temperature was '
                'verified. NASA SP-8064 (downloaded, OCR-searched) defines '
                'the measurement, publishes no numbers. Ingredient-level '
                'model constants exist (Sun et al. 2023: c_p,AP = 1602 '
                'J/kgK, temperature-blind) but mixing-rule synthesis of a '
                'propellant value would be fabrication. '
                + _HANSON_PARR_LEAD),
        ),
        thermal_conductivity=MissingProperty(
            quantity='thermal_conductivity',
            status=MISSING_NOT_FOUND,
            reason=(
                'Searched 2026-08-17; no propellant-level AP/HTPB k with a '
                'stated reference temperature was verified. Ingredient '
                'leads (Sun et al. 2023: lambda_AP = 0.21 W/mK, lambda_HTPB '
                '= 0.14 W/mK, temperature-blind) are not composited here. '
                + _HANSON_PARR_LEAD),
        ),
        notes=(
            "The propellant_database 'apcp' block carries no c_p/k at all; "
            'this row measures that the gap is real, not an oversight.'),
    ),

    # -- Şeker yakıtları ---------------------------------------------------
    'knsu': FuelThermalRecord(
        family='knsu',
        specific_heat=MissingProperty(
            quantity='specific_heat',
            status=MISSING_NOT_FOUND,
            reason=(
                'Searched 2026-08-17: Nakka succhem.html (combustion '
                'temperature 1720 K theoretical @1000 psi, ballistics, '
                'density — NO grain c_p); JATM/Redalyc KNSu papers (density '
                'and burning rate only); Valencia et al., J. Space Safety '
                'Eng. 13(1):48-58, 2026 (open access, KNSU multiphysics) '
                'could not be retrieved past the abstract this session — '
                'open lead. No grain specific heat with a reference '
                'temperature was verifiable.'),
        ),
        thermal_conductivity=MissingProperty(
            quantity='thermal_conductivity',
            status=MISSING_NOT_FOUND,
            reason=(
                'Searched 2026-08-17: same source set as the specific-heat '
                'field (Nakka pages, JATM/Redalyc, JSSE 2026 abstract-only) '
                '— no grain thermal conductivity with a reference '
                'temperature was verifiable. TU Delft KNSB (sorbitol) '
                'theses carry thermal data but for a DIFFERENT fuel '
                '(sorbitol, not sucrose) — not transplanted.'),
        ),
        notes=(
            "Nakka's 1720 K theoretical combustion temperature agrees with "
            "the repo's solid engine ('knsu' T_c = 1719 K) — that chain is "
            'consistent; the thermal-property gap is the grain c_p/k.'),
    ),
    'kndx': FuelThermalRecord(
        family='kndx',
        specific_heat=MissingProperty(
            quantity='specific_heat',
            status=MISSING_NOT_FOUND,
            reason=(
                'Searched 2026-08-17 alongside KNSU (same literature pool: '
                'Nakka pages, amateur/university sugar-propellant papers) — '
                'no grain specific heat for KN/dextrose with a reference '
                'temperature was verifiable.'),
        ),
        thermal_conductivity=MissingProperty(
            quantity='thermal_conductivity',
            status=MISSING_NOT_FOUND,
            reason=(
                'Searched 2026-08-17 alongside KNSU — no grain thermal '
                'conductivity for KN/dextrose with a reference temperature '
                'was verifiable.'),
        ),
        notes='',
    ),

    # -- PBAN --------------------------------------------------------------
    'pban': FuelThermalRecord(
        family='pban',
        specific_heat=MissingProperty(
            quantity='specific_heat',
            status=MISSING_NOT_FOUND,
            reason=(
                'Searched 2026-08-17 (AG-AVT-039 full text; Perry 1970 '
                'thesis; open web) — no PBAN-propellant c_p with a '
                'reference temperature was verifiable. Perry 1970 Table A '
                '(p. 28) DOES publish A-13 (AP/24% PBAN) density 1.56 '
                'g/cm3 and gamma 1.28, but no c_p/k.'),
        ),
        thermal_conductivity=MissingProperty(
            quantity='thermal_conductivity',
            status=MISSING_NOT_FOUND,
            reason=(
                'Searched 2026-08-17 (same source set) — no PBAN-propellant '
                'thermal conductivity with a reference temperature was '
                'verifiable.'),
        ),
        notes='',
    ),

    # -- Bu partide TARANMAYANLAR (dürüst etiket: 'bulunamadı' DEĞİL) ------
    'pe': FuelThermalRecord(
        family='pe',
        specific_heat=MissingProperty(
            quantity='specific_heat', status=MISSING_NOT_SEARCHED,
            reason=(
                'Not searched in this batch (F2b-3 scope was HTPB, '
                'paraffin, APCP, KNDX/KNSU per the design decision); '
                'polymer handbook data likely exists — queued, not '
                'claimed missing.')),
        thermal_conductivity=MissingProperty(
            quantity='thermal_conductivity', status=MISSING_NOT_SEARCHED,
            reason=(
                'Not searched in this batch (F2b-3 scope); queued for a '
                'later batch — declared honestly instead of a false '
                "'not found'.")),
        notes='',
    ),
    'pmma': FuelThermalRecord(
        family='pmma',
        specific_heat=MissingProperty(
            quantity='specific_heat', status=MISSING_NOT_SEARCHED,
            reason=(
                'Not searched in this batch (F2b-3 scope was HTPB, '
                'paraffin, APCP, KNDX/KNSU); polymer literature likely has '
                'temperature-resolved data — queued.')),
        thermal_conductivity=MissingProperty(
            quantity='thermal_conductivity', status=MISSING_NOT_SEARCHED,
            reason=(
                'Not searched in this batch (F2b-3 scope); queued for a '
                'later batch — declared honestly instead of a false '
                "'not found'.")),
        notes='',
    ),
    'abs': FuelThermalRecord(
        family='abs',
        specific_heat=MissingProperty(
            quantity='specific_heat', status=MISSING_NOT_SEARCHED,
            reason=(
                'Not searched in this batch (F2b-3 scope was HTPB, '
                'paraffin, APCP, KNDX/KNSU); queued for a later batch.')),
        thermal_conductivity=MissingProperty(
            quantity='thermal_conductivity', status=MISSING_NOT_SEARCHED,
            reason=(
                'Not searched in this batch (F2b-3 scope); queued for a '
                'later batch — declared honestly instead of a false '
                "'not found'.")),
        notes='',
    ),
}


def compare_with_propellant_database():
    """Bu tablo ile mevcut propellant_database c_p/k alanlarının FARK ÖLÇÜMÜ.

    Mevcut tabloyu DEĞİŞTİRMEZ; canlı okur. Rapor, F2c'nin (ya da sonraki
    partinin) 'eski tablo bu tabloya bağlansın mı' kararının veri girdisidir.

    Returns:
        dict: aile başına satır (eski değer / yeni değer ya da boşluk
        beyanı / mutlak-bağıl fark / faz uyuşmazlığı bayrağı) + özet
        sayaçlar + beyan.
    """
    from hrma.data.propellant_database import PropellantDatabase

    db = PropellantDatabase().database
    rows = {}
    unverified_db_fields = 0
    verified_new_fields = 0
    for family, record in FUEL_THERMAL_RECORDS.items():
        entry = db.get(family, {})
        # Eski tablo birimleri (yorum satırlarından ölçüldü): specific_heat
        # kJ/kg-K, thermal_conductivity W/m-K. SI'ya çevrim beyanlıdır.
        old_cp = entry.get('specific_heat')
        old_cp_J_kgK = old_cp * 1000.0 if isinstance(old_cp,
                                                     (int, float)) else None
        old_k = entry.get('thermal_conductivity')
        old_k_W_mK = float(old_k) if isinstance(old_k, (int, float)) else None

        row = {
            'family': family,
            'db_source_label': entry.get('source'),
            'db_specific_heat_J_kgK': old_cp_J_kgK,
            'db_thermal_conductivity_W_mK': old_k_W_mK,
            'db_phase_declared': False,      # eski tablo faz etiketi taşımaz
            'db_reference_temperature_declared': False,  # ve T_ref taşımaz
        }
        for slot, old_si in (('specific_heat', old_cp_J_kgK),
                             ('thermal_conductivity', old_k_W_mK)):
            field = getattr(record, slot)
            if isinstance(field, ThermalProperty):
                verified_new_fields += 1
                row[f'new_{slot}'] = field.as_dict()
                if old_si is not None:
                    delta = field.value - old_si
                    row[f'{slot}_delta_abs'] = delta
                    row[f'{slot}_delta_rel'] = delta / old_si
                    row[f'{slot}_phase_mismatch_risk'] = (
                        field.phase == PHASE_LIQUID)
            else:
                row[f'new_{slot}'] = field.as_dict()
            if old_si is not None:
                # Eski tablodaki HER c_p/k alanı künye/T_ref yönünden
                # doğrulanmamış sayılır (blok-başına etiket, T_ref yok).
                unverified_db_fields += 1
        rows[family] = row

    return {
        'rows': rows,
        'summary': {
            'families_compared': len(rows),
            'db_cp_k_fields_present': unverified_db_fields,
            'db_cp_k_fields_with_field_level_citation': 0,
            'db_cp_k_fields_with_reference_temperature': 0,
            'new_verified_fields': verified_new_fields,
        },
        'basis': (
            'Measured live against hrma/data/propellant_database.py (not a '
            'snapshot). DB units per its inline comments: specific_heat in '
            'kJ/kg-K (converted here to J/kg-K, factor 1000), thermal_'
            'conductivity in W/m-K. Every DB c_p/k field counts as '
            'unverified because the DB carries one block-level source label '
            'per propellant, no field-level citation and no reference '
            'temperature (design doc §8.1 decision 4). This report is the '
            'decision input for whether a later batch wires the old table '
            'to this one; nothing is migrated here.'),
    }
