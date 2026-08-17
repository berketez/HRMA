# hrma/stability/bands.py — künyeli QSHOD (A, B) bant tablosu (F2b-3)
"""Katı yakıt QSHOD (A, B) tepki bantları — KÜNYELİ literatür tablosu.

F2a'nın "hazır tablo taşımaz" bekçisinin (test_f2a_hazir_bant_tablosu_tasimaz)
işaret ettiği tablo BUDUR: (A, B) bantları depoda YALNIZ bu modülde yaşar;
``response.py`` mekanizmayı kurar, sayı taşımaz (tasarım belgesi §8.1 karar 3).

TABLO DİSİPLİNİ (bu partide ÖLÇÜLEREK kurulmuştur, 2026-08-17):
    1.  Kaynağı İNDİRİLİP DOĞRULANAMAYAN hiçbir sayı tabloya girmez.
        Doğrulanamayan aile ``MissingBandRecord`` ile BOŞ bırakılır —
        uydurma bant, yanlış banttan beterdir.
    2.  Her dolu kayıt ``response.py``'nin zarf şemasıyla bire birdir:
        ``QSHODBand`` (formülasyon sınıfı + basınç aralığı + sıcaklık aralığı
        + kaynak künyesi) + kayıt-düzeyi güven notu.
    3.  Kaynak bir NOKTA fit yayımlıyorsa bant dejenere aralıktır
        ``(x, x)`` — kaynak vermediği genişlik icat edilmez. Fit'in
        benzersiz OLMADIĞI kaynak beyanları güven notunda taşınır.
    4.  Sıcaklık ayağı ayrı kaynaktan geliyorsa (Perry 1970 alev sıcaklığı)
        künyede AYRI satırla beyan edilir; kaynak karışımı gizlenmez.

DOĞRULANMIŞ KAYNAKLAR (indirildi, sayfa/tablo düzeyinde okundu; md5'ler
künyelerde):
    - Culick & Yang 1990 (AIAA Progress Vol. 143) — depodaki sayısal çapa
      (tests/test_stability_tepki.py Tablo 1'i bağımsız yeniden üretir).
    - NATO RTO AG-AVT-039 (Culick 2006, 664 s.) — Fig. 2.16/2.17 fitleri
      görsel olarak doğrulandı (A-13: A=40, B=1.1; A-35: A=14, B=0.8,
      n=0.49); s. 6-12 formülasyon beyanı; s. 2-31 ve 6-45 fit uyarıları.
    - Perry, E.H., Caltech doktora tezi 1970 — Tablo A (s. 28) görsel
      doğrulandı: A-13/A-35 bağlayıcı, yoğunluk, n ve alev sıcaklıkları.

BULUNAMAYANLAR (arandı; 'kaynak bulunamadı' beyanlı boş):
    - KNDX / KNSU (şeker yakıtları): kamuya açık T-burner ölçümü ya da
      QSHOD (A, B) fiti bulunamadı.
    - Modern AP/HTPB (APCP) ölçülü bandı: Blomshield NAWCWD T-burner
      derlemeleri bu oturumda erişilemedi (DTIC bakımda, dergi kapılı) —
      açık kalem; en yakın sınıf eşlemesi FAMILY_BANDS'te beyanlıdır.
"""

from hrma.analysis.valve_feedline import PSI_PA
from hrma.stability.response import QSHODBand

__all__ = [
    'RECORD_CONFIDENCE_MEDIUM',
    'RECORD_CONFIDENCE_LOW',
    'MISSING_NOT_FOUND',
    'QSHODBandRecord',
    'MissingBandRecord',
    'QSHOD_BAND_RECORDS',
    'FAMILY_BANDS',
    'bands_for_family',
]

# ---------------------------------------------------------------------------
# Kayıt-düzeyi güven sözlüğü (zarf rozetinden AYRI eksen: zarf rozeti
# response.py'de çalışma noktasına bakar; bu eksen KAYNAĞIN kalitesine).
# ---------------------------------------------------------------------------
RECORD_CONFIDENCE_MEDIUM = 'medium'
RECORD_CONFIDENCE_LOW = 'low'
_RECORD_CONFIDENCES = frozenset((RECORD_CONFIDENCE_MEDIUM,
                                 RECORD_CONFIDENCE_LOW))

#: Boş kayıt durumu: arandı ve bulunamadı (taranmamış aile tabloya girmez;
#: yalan 'bulunamadı' beyanı da yasaktır).
MISSING_NOT_FOUND = 'not_found'


class QSHODBandRecord:
    """Dolu tablo satırı: zarflı bant + kayıt-düzeyi güven notu.

    Yapısal sözleşme: ``band`` alanı ``QSHODBand`` OLMAK ZORUNDADIR —
    böylece zarf üstverisi (formülasyon sınıfı, basınç, sıcaklık, kaynak)
    response.py kurucusunda zorlanır; burada ikinci bir şema icat edilmez.
    """

    __slots__ = ('record_id', 'band', 'confidence', 'confidence_note',
                 'retrieved')

    def __init__(self, record_id, band, confidence, confidence_note,
                 retrieved):
        if not isinstance(record_id, str) or not record_id.strip():
            raise ValueError('record_id is mandatory.')
        if not isinstance(band, QSHODBand):
            raise ValueError(
                f'{record_id}: band must be a QSHODBand carrying its full '
                f'validity envelope (got {type(band).__name__}).')
        if confidence not in _RECORD_CONFIDENCES:
            raise ValueError(
                f'{record_id}: confidence must be one of '
                f'{sorted(_RECORD_CONFIDENCES)} (got {confidence!r}).')
        if not isinstance(confidence_note, str) or not confidence_note.strip():
            raise ValueError(
                f'{record_id}: confidence_note is mandatory — a literature '
                f'band without its caveats misleads.')
        if not isinstance(retrieved, str) or not retrieved.strip():
            raise ValueError(
                f'{record_id}: retrieved (verification date) is mandatory.')
        self.record_id = record_id
        self.band = band
        self.confidence = confidence
        self.confidence_note = confidence_note.strip()
        self.retrieved = retrieved.strip()

    def as_dict(self):
        return {
            'record_id': self.record_id,
            'band': self.band.as_dict(),
            'record_confidence': self.confidence,
            'record_confidence_note': self.confidence_note,
            'retrieved': self.retrieved,
        }


class MissingBandRecord:
    """Boş tablo satırı: kaynak bulunamadı BEYANI.

    Yapısal olarak SAYI TAŞIYAMAZ (``__slots__``'ta sayısal alan yok):
    'kaynaksız kayıt yok' kuralı burada sınıf tanımıyla kilitlenir.
    """

    __slots__ = ('record_id', 'status', 'reason')

    def __init__(self, record_id, reason):
        if not isinstance(record_id, str) or not record_id.strip():
            raise ValueError('record_id is mandatory.')
        if not isinstance(reason, str) or len(reason.strip()) < 40:
            raise ValueError(
                f'{record_id}: a missing-band record must declare WHAT was '
                f'searched and WHY the row is empty (got {reason!r}).')
        self.record_id = record_id
        self.status = MISSING_NOT_FOUND
        self.reason = reason.strip()

    def as_dict(self):
        return {
            'record_id': self.record_id,
            'status': self.status,
            'reason': self.reason,
        }


_RETRIEVED = '2026-08-17'

# ---------------------------------------------------------------------------
# TABLO — her sayının yanında künyesi. Basınçlar kaynak psi değerlerinden
# PSI_PA ile çevrilir (tek kaynak: hrma/analysis/valve_feedline.py).
# ---------------------------------------------------------------------------
QSHOD_BAND_RECORDS = {
    # -- Culick & Yang 1990 örnek motoru: depodaki sayısal çapanın kendisi --
    'cy1990_worked_example': QSHODBandRecord(
        record_id='cy1990_worked_example',
        band=QSHODBand(
            a_range=(6.0, 6.0),
            b_range=(0.55, 0.55),
            pressure_exponent_n=0.3,
            formulation_class=(
                'Metallized composite worked-example propellant of Culick & '
                'Yang (1990), Appendix data; NOT a named production '
                'formulation. Aluminized (the example carries particle '
                'damping).'),
            # Örneğin tek çalışma noktası: p̄ = 10,6 MPa, T = 3539 K
            # (dejenere zarf — makale başka nokta yayımlamaz).
            pressure_range_Pa=(1.06e7, 1.06e7),
            temperature_range_K=(3539.0, 3539.0),
            source=(
                "Culick, F.E.C. & Yang, V., 'Prediction of the Stability of "
                "Unsteady Motions in Solid-Propellant Rocket Motors', AIAA "
                'Progress in Astronautics and Aeronautics Vol. 143, 1990, '
                'pp. 719-779, Appendix worked-example motor (A=6.0, B=0.55, '
                'n=0.3 at p=10.6 MPa, T=3539 K). Independently re-derived in '
                "this repository: tests/test_stability_tepki.py reproduces "
                "the paper's Table 1 growth constants to 0.2-2.5%. Source "
                'PDF md5 1fb7c275bb62dc7b607cdf1f25986655 (Stanford AA284A '
                'copy).'),
        ),
        confidence=RECORD_CONFIDENCE_MEDIUM,
        confidence_note=(
            'Model worked example, not a T-burner measurement: the (A, B, n) '
            'triple is the input the paper chose for its demonstration '
            'motor. Its downstream numbers are anchored in-repo (Table 1 '
            'reproduced to 0.2-2.5%), which verifies the TRANSCRIPTION, not '
            'the propellant. The envelope is the single operating point of '
            'the example.'),
        retrieved=_RETRIEVED,
    ),

    # -- A-35: AP / poliüretan (estane) — NWC araştırma yakıtı -------------
    'a35_ap_polyurethane': QSHODBandRecord(
        record_id='a35_ap_polyurethane',
        band=QSHODBand(
            a_range=(14.0, 14.0),
            b_range=(0.8, 0.8),
            # Fig. 2.17'nin kendi fit girdisi ('ALL CURVES ... n = 0.49').
            pressure_exponent_n=0.49,
            formulation_class=(
                'A-35 research propellant (NWC China Lake): AP oxidizer with '
                '25% by mass estane-type polyurethane binder; same oxidizer '
                'particle size distribution as A-13 (AG-AVT-039 p. 6-12). '
                'Unmetallized.'),
            # T-burner veri basınçları: 200-800 psi (Fig. 2.17 lejantı).
            # Kaynak psia/psig ayrımı yazmıyor; nominal psi çevrildi.
            pressure_range_Pa=(200.0 * PSI_PA, 800.0 * PSI_PA),
            # Alev sıcaklığı 2160 K @ 300 psig — Perry 1970 Tablo A.
            temperature_range_K=(2160.0, 2160.0),
            source=(
                "(A, B, n) fit: Culick, F.E.C., 'Unsteady Motions in "
                "Combustion Chambers for Propulsion Systems', NATO RTO "
                'AG-AVT-039, 2006, Fig. 2.17 (p. 2-32: ALL CURVES A=14, '
                'B=0.8, n=0.49; T-burner data at 200/400/600/800 psi) and '
                "p. 6-12 text: 'Denison and Baum's result may represent the "
                "dynamics of A-35 (A=14, B=0.8)'. Primary data: Beckstead, "
                "M.W. & Culick, F.E.C., 'A Comparison of Analysis and "
                "Experiment for Solid Propellant Combustion Instability', "
                'AIAA Journal 9(1), 1971, pp. 147-154. Formulation class: '
                'AG-AVT-039 p. 6-12. Flame temperature envelope: Perry, '
                "E.H., 'Investigations of the T-Burner and Its Role in "
                "Combustion Instability Studies', PhD thesis, Caltech, 1970, "
                'Table A p. 28 (A-35: polyurethane/AP, T_flame = 2160 K at '
                '300 psig; propellants supplied by NWC China Lake). '
                'AG-AVT-039 PDF md5 cf9c70bd56ac2a9903584b82c05a2955; Perry '
                'thesis PDF md5 a7cfda6ac2094098ae9cacc99f689e9b.'),
        ),
        confidence=RECORD_CONFIDENCE_MEDIUM,
        confidence_note=(
            'The compilation itself endorses this fit only conditionally: '
            "Beckstead & Culick's main conclusion was that UNIQUE (A, B) "
            'values could not be obtained for a propellant at a chosen '
            'pressure (AG-AVT-039 p. 2-31), and Fig. 6.8 shows the A-35 '
            'data as a REGION (roughly B 0.7-0.9), not a point. Also note a '
            'measured exponent conflict: the fit carries n=0.49 while Perry '
            '(1970, Table A) measured n=0.0 for A-35 at 300 psig (plateau '
            'burning) — n is strongly pressure-dependent for this '
            'formulation.'),
        retrieved=_RETRIEVED,
    ),

    # -- A-13: AP / PBAN — NWC araştırma yakıtı (deponun 'pban' ailesine
    #    en yakın ölçülmüş sınıf; metal yükü YOK) -------------------------
    'a13_ap_pban': QSHODBandRecord(
        record_id='a13_ap_pban',
        band=QSHODBand(
            a_range=(40.0, 40.0),
            b_range=(1.1, 1.1),
            # Fig. 2.16 n yayımlamaz; n = 0.42 @ 300 psig Perry Tablo A'dan.
            pressure_exponent_n=0.42,
            formulation_class=(
                'A-13 research propellant (NWC China Lake): AP oxidizer with '
                '24% by mass PBAN binder (AG-AVT-039 p. 6-12); unmetallized '
                '(no metal loading reported). NOT the Shuttle-class '
                'aluminized PBAN.'),
            # T-burner veri basınçları: 100-800 psi (Fig. 2.16 lejantı).
            pressure_range_Pa=(100.0 * PSI_PA, 800.0 * PSI_PA),
            # Alev sıcaklığı 2100 K @ 300 psig — Perry 1970 Tablo A.
            temperature_range_K=(2100.0, 2100.0),
            source=(
                '(A, B) fit: NATO RTO AG-AVT-039 (Culick 2006), Fig. 2.16 '
                '(p. 2-31: A=40, B=1.1 QSHOD curve against T-burner data at '
                '100/400/800 psi). Primary data: Beckstead, M.W. & Culick, '
                'F.E.C., AIAA Journal 9(1), 1971, pp. 147-154. Formulation '
                'class: AG-AVT-039 p. 6-12. Pressure exponent and flame '
                'temperature: Perry, E.H., PhD thesis, Caltech, 1970, Table '
                'A p. 28 (A-13: PBAN/AP, n=0.42 and T_flame = 2100 K at 300 '
                'psig). AG-AVT-039 PDF md5 cf9c70bd56ac2a9903584b82c05a2955; '
                'Perry thesis PDF md5 a7cfda6ac2094098ae9cacc99f689e9b.'),
        ),
        confidence=RECORD_CONFIDENCE_LOW,
        confidence_note=(
            'LOW confidence, declared by the source itself: AG-AVT-039 '
            "p. 6-12 states Denison & Baum's (QSHOD) form 'may represent "
            "the dynamics of A-35 ... but not those of A-13', and the "
            'T-burner chart interpretation for A-13 is called "clearly '
            'unsuccessful" (p. 6-45, Fig. 6.20). The A=40, B=1.1 curve of '
            'Fig. 2.16 visibly misses the pressure-split of the data. '
            'Fig. 6.8 places part of the A-13 region at A<0 (outside the '
            'model). Carried because it is the only published QSHOD fit for '
            'an AP/PBAN formulation found; treat as an order-of-magnitude '
            'yardstick, not a property.'),
        retrieved=_RETRIEVED,
    ),

    # -- Şeker yakıtları: BOŞ — kaynak bulunamadı --------------------------
    'kndx': MissingBandRecord(
        record_id='kndx',
        reason=(
            'No published T-burner pressure-coupled response measurement or '
            'QSHOD (A, B) fit for potassium nitrate/dextrose (KNDX) '
            'propellant was found in the sources verified on 2026-08-17: '
            'NATO AG-AVT-039 full text (664 pp., searched), Perry 1970 '
            'Caltech thesis, Nakka experimental-rocketry pages, open web '
            'search (DTIC under maintenance during the session). Amateur '
            'sugar propellants are simply not represented in the T-burner '
            'literature that was reachable. No band is fabricated: an '
            'invented band is worse than an empty row.'),
    ),
    'knsu': MissingBandRecord(
        record_id='knsu',
        reason=(
            'No published T-burner pressure-coupled response measurement or '
            'QSHOD (A, B) fit for potassium nitrate/sucrose (KNSU) '
            'propellant was found in the sources verified on 2026-08-17: '
            'NATO AG-AVT-039 full text (664 pp., searched), Perry 1970 '
            'Caltech thesis, Nakka succhem.html (ballistics and combustion '
            'temperature only — no response data), open web search (DTIC '
            'under maintenance during the session). No band is fabricated: '
            'an invented band is worse than an empty row.'),
    ),
}

# ---------------------------------------------------------------------------
# Depo katalog ailesi -> kayıt eşlemesi. Eşleşme notu ZORUNLU: sınıf
# uyuşmazlığı gizlenmez (karar 3'ün ruhu — 'APCP bandı' gibi geniş sınıf
# yetmez; en yakın sınıf eşlemesi ancak beyanla yayımlanır).
# ---------------------------------------------------------------------------
FAMILY_BANDS = {
    'apcp': {
        'record_ids': ('cy1990_worked_example',),
        'mapping_basis': (
            "NEAREST CLASS, not a match: the repo 'apcp' family is an "
            'aluminized AP/HTPB composite; the only verified band in this '
            'class is the Culick & Yang (1990) metallized-composite worked '
            'example, which is not a named APCP formulation. Measured '
            'AP/HTPB T-burner bands exist in the literature (Blomshield, '
            'NAWCWD compilations) but were not retrievable/verifiable in '
            'this session (DTIC maintenance, paywalled journals) — open '
            'item, row NOT fabricated.'),
    },
    'pban': {
        'record_ids': ('a13_ap_pban',),
        'mapping_basis': (
            "CLASS MISMATCH DECLARED: the repo 'pban' entry is the "
            'Shuttle-class aluminized PBAN (16% Al); the verified band is '
            'for A-13, an UNMETALLIZED AP/24%-PBAN research propellant '
            '(Perry 1970; AG-AVT-039 p. 6-12). Same binder chemistry, '
            'different metal loading — metal particles change both the '
            'response and the damping. See also the record-level LOW '
            'confidence note.'),
    },
    'kndx': {
        'record_ids': (),
        'mapping_basis': (
            'Empty by declaration: no verifiable source found — see '
            "QSHOD_BAND_RECORDS['kndx'].reason."),
    },
    'knsu': {
        'record_ids': (),
        'mapping_basis': (
            'Empty by declaration: no verifiable source found — see '
            "QSHOD_BAND_RECORDS['knsu'].reason."),
    },
}


def bands_for_family(family):
    """Depo katalog ailesi için bant kayıtları + eşleşme beyanı.

    Args:
        family: propellant_database katalog anahtarı ('apcp', 'pban',
            'kndx', 'knsu').

    Returns:
        dict: ``family`` / ``records`` (QSHODBandRecord listesi; boş
        olabilir) / ``missing`` (MissingBandRecord ya da None) /
        ``mapping_basis`` (sınıf eşleşme beyanı).

    Raises:
        ValueError: bilinmeyen aile — sessiz boş dönüş yerine açık hata
        (uydurma varsayılan yasağı).
    """
    if family not in FAMILY_BANDS:
        raise ValueError(
            f'Unknown propellant family {family!r}: no QSHOD band mapping '
            f'is published for it. Known families: '
            f'{sorted(FAMILY_BANDS)}. An empty answer is not fabricated '
            f'for unknown keys.')
    entry = FAMILY_BANDS[family]
    records = [QSHOD_BAND_RECORDS[rid] for rid in entry['record_ids']]
    missing = QSHOD_BAND_RECORDS.get(family)
    if not isinstance(missing, MissingBandRecord):
        missing = None
    return {
        'family': family,
        'records': records,
        'missing': missing,
        'mapping_basis': entry['mapping_basis'],
    }
