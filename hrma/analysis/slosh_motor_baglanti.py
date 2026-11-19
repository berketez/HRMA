"""3.0.7 ÇALKANTI-MOTOR bağlantısı (KARTLAR K4; CALKANTI_6DOF_TASARIM.md §A.2, §B.1).

Motorun KENDİ sonucundan 6-DOF'un çalkantı tank listesini kurar
(``slosh_tanks``; K2 arayüzü, ``six_dof_slosh.SloshBaglama``):

    [{"tank_id", "x_tank_taban_m", "tablo": SloshTablo,
      "m_t": {"t": [...], "m": [...]}, "zeta_ek": None}]

Tek giriş noktası :func:`slosh_tanklari`. Bu modül sayı ÜRETMEZ; motorun
yayımladığı alanları okur, tutarlılıklarını denetler ve K2'nin beklediği
biçime çevirir. Okunamayan ya da tutmayan alan tankı BAĞLAMAZ ve adlı kodla
söylenir (uydurma kütle, yoğunluk ya da konum yok).

Okunan alanlar (koddan ölçüldü, 16 Kasım 2026;
``docs/scofield/raw/OH/V307/calkanti-motor/alan_olcumu.json``):

SIVI (``/calculate_liquid`` gövdesi)
  * tank geometrisi: UÇUŞ'un tank listesi
    ``flight_vehicle.normalize(...)['propellant_tanks']`` (``diameter_m``,
    ``length_m``, ``volume_m3``; kaynağı ``propellant_tanks.<tank>.
    dimensions`` mm / litre). Motorun boyutlandırma modeli V = π/4·D²·L
    (düz kapaklı dik silindir); hacim bu bağıntıyla tutmazsa tank
    bağlanmaz.
  * yüklenen sıvı: ``propellant_tanks.<tank>.propellant_data.mass``
    (nominal × 1,15 yedek), nominal yanan ``mass_nominal``.
  * yoğunluk: ``propellant_tanks.<tank>.propellant_data.density``.
  * tüketim: pompalanan debiler ``oxidizer_flow`` / ``fuel_flow`` [kg/s]
    (açık çevrimde ``mass_flow_ledger``'ın ``oxidizer_flow_kg_s`` /
    ``fuel_flow_kg_s``'i ile aynı sayı: ana kamara + türbin/gaz jeneratörü;
    tank ikisini de besler). Defter ``open_cycle_closed`` değilse motor
    debi yayımlamaz → tank bağlanmaz. Denetim: ṁ_k·t_yanma = mass_nominal_k.
  * yanma süresi: ``flight_vehicle.motor_flight_thrust(...)['burn_time']``
    (uçuşa giren itkinin TEK kuralı).
  * viskozite (çeper sönümü için, isteğe bağlı): ``detailed_feed_system.
    valve_feedline.<oxidizer|fuel>_line.viscosity_Pa_s`` (+ ``_source``);
    ν = μ/ρ.
HİBRİT (``/calculate`` gövdesi, ``motor`` sarmalı)
  * tank geometrisi: UÇUŞ'un tank listesi (kaynağı ``motor.
    oxidizer_tank_slosh`` ``tank_diameter_m``/``tank_length_m``).
  * yüklenen sıvı: ``motor.oxidizer_tank_slosh.liquid_mass_kg`` (=
    ``oxidizer_liquid_loaded_kg``); yoğunluk ``liquid_density_kg_m3``
    (ateşleme anındaki N₂O doyma yoğunluğu).
  * tüketim: kendinden basınçlı tankta motorun boşalma çözümünün SIVI
    kütlesi serisi ``motor.tank_blowdown.oxidizer_inventory.
    liquid_mass_time_s`` / ``liquid_mass_kg`` (V307/ÇALKANTI-MOTOR ile
    yayımlandı; buharlaşma dahil). Regüle beslemede (boşalma modellenmedi)
    sabit debi ``motor.mdot_ox`` (BEYANLI).
KATI: tank yok → ``UYGULANMAZ`` (kod ``TANK_YOK``), liste boş; 6-DOF bugünkü
  çözümle bit-aynı kalır.

Tankın araçtaki yeri motor ya da UÇUŞ sonucunda YAYIMLANMIYOR (ölçüldü:
``propellant_tanks`` yalnız çap/boy/hacim taşır; 6-DOF ucu bileşen listesini
çözücüye geçirmiyor). Yer ``arac_duzeni`` girdisinden gelir (CALKANTI §B.1);
verilmezse tank ``TANK_ISTASYONU_VERILMEDI`` koduyla bağlanmaz.
"""

from __future__ import annotations

import math
import numbers

from hrma.analysis import flight_vehicle as _fv
from hrma.analysis import six_dof_slosh as _k2
from hrma.analysis import slosh_analysis as _sa
from hrma.analysis import slosh_tablo as _tablo
from hrma.constants import G_0

# ---------------------------------------------------------------------------
# Sabitler — TEK TANIM YERİ
# ---------------------------------------------------------------------------
SONUC_SEMASI = 'hrma.calkanti_motor_baglantisi'
SONUC_SURUMU = 'v307-1'

#: Motorun tank anahtarı → sözleşme tank kimliği (``slosh_tablo.
#: TANK_KIMLIKLERI``). Hibritte N₂O tankı 'n2o'; başka sıvı oksitleyici
#: 'oksitleyici'.
SIVI_TANKLARI = (('oxidizer_tank', 'oksitleyici'), ('fuel_tank', 'yakit'))
HIBRIT_N2O_KIMLIGI = 'n2o'
HIBRIT_OKSITLEYICI_KIMLIGI = 'oksitleyici'

#: Tutarlılık denetimlerinin bağıl payı: kayan nokta artığı, fizik değil.
#: Yeni sayı açılmadı — sözleşme doğrulayıcısının değişmez payı.
TUTARLILIK_BAGIL_TOL = _tablo.DEGISMEZ_BAGIL_TOL

#: Açık çevrim debi defterinin "debi yayımlandı" durumu (sıvı motor
#: ``_mass_flow_ledger_block``).
DEFTER_KAPALI = 'open_cycle_closed'

#: Hibrit boşalma bloğunun "modellendi" durumu ve besleme kipi.
BOSALMA_MODELLENDI = 'modelled'
BOSALMA_KIPI = 'blowdown'

#: ``arac_duzeni`` anahtarları. Yer kaynağı (tam olarak biri):
#:   ``tank_istasyonlari``    {tank_id: x_tank_taban_m} (araç tanımı)
#:   ``ardisik``              {'sira': [tank_id, ...]} burundan kıça; tanklar
#:                            motorun hemen önünde, başları temas hâlinde
#:                            dizilir (UÇUŞ gövde türetme kuralının TEK
#:                            dizilim tanımı: ``flight_vehicle.tank_stack``);
#:                            ``govde_boyu_m`` şart. ``sira`` verilmezse
#:                            ({}) UÇUŞ'un tank listesi sırası (türetilmiş
#:                            gövdenin kendi dizilimi)
#:   ``sivi_km_istasyonlari`` {tank_id: x_km_m} yüklü sıvının kütle merkezi
#:                            (6-DOF bileşen tablosunun itici satırı; §B.1
#:                            ikinci kaynak)
#: Uygunluk denetimi için isteğe bağlı: ``govde_boyu_m``, ``burun_boyu_m``,
#: ``govde_capi_m``, ``motor_boyu_m`` (yoksa UÇUŞ'un ``engine_length_m``i).
YER_KAYNAKLARI = ('tank_istasyonlari', 'ardisik', 'sivi_km_istasyonlari')
ARAC_OLCULERI = ('govde_boyu_m', 'burun_boyu_m', 'govde_capi_m',
                 'motor_boyu_m')

# Sonuç durumları
DURUM_BAGLANDI = 'BAGLANDI'
DURUM_KISMI = 'KISMI'
DURUM_BAGLANMADI = 'BAGLANMADI'
DURUM_UYGULANMAZ = 'UYGULANMAZ'

# Kod sınıfları (BAGLANMADI ve BEYAN K2 ile aynı ad)
SINIF_UYGULANMAZ = 'UYGULANMAZ'
SINIF_BAGLANMADI = _k2.SINIF_BAGLANMADI
SINIF_BEYAN = _k2.SINIF_BEYAN

#: Makine-okur kodlar: (sınıf, gerekçe). Metinlerin TR/EN ekran karşılığı
#: arayüz sözlüğündedir (K5).
KODLAR = {
    'TANK_YOK': (
        SINIF_UYGULANMAZ, 'katı motorda sıvı itici tankı yoktur; çalkantı '
        'uygulanmaz (CALKANTI §B.1)'),
    'TANK_GEOMETRISI_YAYIMLANMADI': (
        SINIF_BAGLANMADI, 'motor sonucu bu tankın çapını ve boyunu '
        'yayımlamıyor (UÇUŞ propellant_tanks); tablo kurulamaz'),
    'TANK_GEOMETRISI_DIK_SILINDIR_DEGIL': (
        SINIF_BAGLANMADI, 'yayımlanan tank hacmi π/4·D²·L bağıntısını '
        'tutmuyor; motorun tankı düz kapaklı dik silindir sayılamaz'),
    'YOGUNLUK_YAYIMLANMADI': (
        SINIF_BAGLANMADI, 'motor bu tankın sıvı yoğunluğunu yayımlamıyor'),
    'YUKLENEN_KUTLE_YAYIMLANMADI': (
        SINIF_BAGLANMADI, 'motor bu tankın yüklenen sıvı kütlesini '
        'yayımlamıyor'),
    'TUKETIM_YAYIMLANMADI': (
        SINIF_BAGLANMADI, 'motor bu tankın tüketimini (debi ya da boşalma '
        'serisi) yayımlamıyor'),
    'DEBI_BUTCESI_TUTARSIZ': (
        SINIF_BAGLANMADI, 'debi × yanma süresi motorun yayımladığı nominal '
        'kütleyi vermiyor ya da yüklenen kütleyi aşıyor'),
    'TUKETIM_SERISI_TUTARSIZ': (
        SINIF_BAGLANMADI, 'boşalma serisi motorun yayımladığı başlangıç '
        'sıvısıyla, yanma süresiyle ya da kendi içinde tutarlı değil'),
    'UCUS_KUTLESIYLE_TUTARSIZ': (
        SINIF_BAGLANMADI, 'tank kütleleri UÇUŞ\'un uçuş kütlesi bütçesiyle '
        '(yüklenen, harcanan, kalan) kapanmıyor'),
    'TANK_HACMI_YETERSIZ': (
        SINIF_BAGLANMADI, 'yüklenen sıvının hacmi tank iç hacmini aşıyor'),
    'TANK_GEOMETRISI_RET': (
        SINIF_BAGLANMADI, 'tank geometri girdisi reddedildi; içe aktarıcının '
        'adlı kodu geometri_girdisi alanında'),
    'TANK_ISTASYONU_VERILMEDI': (
        SINIF_BAGLANMADI, 'tankın araçtaki yeri motor ve uçuş sonucunda '
        'yayımlanmıyor ve girilmedi; uydurma konum yok (CALKANTI §B.1)'),
    'MOTOR_BOYU_YAYIMLANMADI': (
        SINIF_BAGLANMADI, 'ardışık dizilim motor boyunu ister; motor boyu '
        'yayımlanmıyor ve girilmedi'),
    'TANK_ARAC_DISI': (
        SINIF_BAGLANMADI, 'tank araç boyunun dışında (taban > gövde boyu ya '
        'da tepe < 0)'),
    'TANK_BURUN_ICINDE': (
        SINIF_BAGLANMADI, 'tankın tepesi burun konisinin içinde'),
    'TANK_GOVDEDEN_GENIS': (
        SINIF_BAGLANMADI, 'tankın dış çapı (iç çap + 2 × motorun yayımladığı '
        'cidar; cidar yayımlanmamışsa iç çap) gövde dış çapından büyük'),
    'TANKLAR_CAKISIYOR': (
        SINIF_BAGLANMADI, 'iki tank araç ekseninde üst üste biniyor'),
    # --- BEYAN (tank bağlı; varsayım adıyla) ---------------------------
    'TUKETIM_SABIT_DEBI': (
        SINIF_BEYAN, 'kararlı (regüle) besleme: tank sabit debiyle boşalır, '
        'm(t) = m0 − ṁ·t; sıvıda ṁ pompalanan debidir (ana kamara + '
        'türbin/gaz jeneratörü)'),
    'TUKETIM_BOSALMA_COZUMU': (
        SINIF_BEYAN, 'kendinden basınçlı N₂O tankı: sıvı kütlesi motorun '
        'boşalma çözümünden (ullage\'ı doyma basıncında tutan buharlaşma '
        'dahil); buhar çalkantıya girmez'),
    'YOGUNLUK_SABIT': (
        SINIF_BEYAN, 'sıvı yoğunluğu yanma boyunca sabit alındı; doluluk = '
        'm/(ρ·V_iç). Motor bu tank için tek yoğunluk yayımlıyor (sıvı motor: '
        'tank sıcaklığı modeli yok; hibrit regüle besleme: boşalma çözümü '
        'yok) (CALKANTI §A.2)'),
    'YOGUNLUK_BOSALMA_COZUMU': (
        SINIF_BEYAN, 'kendinden basınçlı N₂O tankı: sıvı yoğunluğu motorun '
        'boşalma çözümündeki tank sıcaklığından, adım sınırlarında ρ_l(T); '
        'doluluk = m(t)/(ρ(t)·V_iç) (tank soğudukça sıvı yoğunlaşır)'),
    'YOGUNLUK_SERISI_TUTARSIZ': (
        SINIF_BAGLANMADI, 'motorun yayımladığı sıvı yoğunluğu serisi sıvı '
        'kütlesi serisiyle aynı uzunlukta değil ya da ilk değeri motorun '
        'ateşleme yoğunluğunu vermiyor'),
    'BAFL_SONUMU_UYGULANMADI': (
        SINIF_BEYAN, 'motorun bafl sönümü tam dolulukta tek sayıdır, '
        'doluluğa bağlı değildir; 6-DOF\'a ek sönüm verilmedi (tutucu)'),
    'TANK_ISTASYONU_ARDISIK_DIZILIM': (
        SINIF_BEYAN, 'tanklar motorun hemen önünde, verilen sırayla (sıra '
        'verilmediyse motorun tank listesi sırasıyla: oksitleyici önde) '
        'dizildi; her tank iç boyu + motorun yayımladığı iki baş kalınlığı '
        'kadar yer tutar, komşu başlar temas hâlindedir, tanklar arası bölme '
        'eklenmez (UÇUŞ gövde türetme kuralı, flight_vehicle.tank_stack)'),
    'TANK_ISTASYONU_SIVI_KM_DONUSUMU': (
        SINIF_BEYAN, 'girilen istasyon yüklü sıvının kütle merkezidir; '
        'taban = x_km + z_km(yüklü doluluk) (CALKANTI §B.1 ikinci kaynak)'),
}

#: Kapsam künyesi (çıktıya aynen yazılır).
KUNYE = (
    'Tank listesi motorun kendi sonucundan kuruldu: geometri UÇUŞ tank '
    'listesinden, yüklenen sıvı ve yoğunluk motorun tank bloğundan, '
    'tüketim motorun debisinden (sıvı) ya da boşalma çözümünden (hibrit). '
    'Eşdeğer model tablosu tek girişten (slosh_analysis.esdeger_model_'
    'tablosu). Tankın araçtaki yeri girdidir; motor yayımlamaz.')


class SloshMotorBaglantiHatasi(ValueError):
    """Bağlantı GİRDİSİ reddedildi (``kod`` ve ``alan`` adlı).

    Motor sonucundaki eksik alan hata değil sonuçtur (tank adlı kodla
    bağlanmaz); bu istisna yalnız çağıranın verdiği girdi (motor türü,
    ``arac_duzeni``, ``tank_geometrileri``) bozuksa atılır.
    """

    def __init__(self, mesaj, kod, alan=None):
        super().__init__(f'{alan}: {mesaj}' if alan else mesaj)
        self.kod = kod
        self.alan = alan


def _ret(kod, alan, mesaj):
    raise SloshMotorBaglantiHatasi(mesaj, kod, alan)


# ---------------------------------------------------------------------------
# Küçük yardımcılar
# ---------------------------------------------------------------------------
def _sayi(v):
    """Sonlu gerçek sayı ya da None (bool sayı değildir)."""
    if isinstance(v, bool) or not isinstance(v, numbers.Real):
        return None
    v = float(v)
    return v if math.isfinite(v) else None


def _al(d, *yol):
    for k in yol:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _yakin(a, b):
    return abs(a - b) <= TUTARLILIK_BAGIL_TOL * max(abs(a), abs(b), 1e-300)


def _girdi_sayisi(v, alan, *, pozitif=False):
    if isinstance(v, bool) or not isinstance(v, numbers.Real) \
            or not math.isfinite(float(v)):
        _ret('SAYI_DEGIL', alan, f'sonlu bir sayı olmalı ({v!r})')
    v = float(v)
    if pozitif and not v > 0.0:
        _ret('ARALIK', alan, f'pozitif olmalı ({v!r})')
    return v


# ---------------------------------------------------------------------------
# Motor sonucundan tank adayları
# ---------------------------------------------------------------------------
def _ucus_tanklari(motor_type, sonuc):
    """UÇUŞ'un tank listesi (tek kaynak): anahtar → kayıt (ya da {})."""
    try:
        arac = _fv.normalize(motor_type, sonuc)
    except (TypeError, ValueError):
        return {}, None
    liste = arac.get('propellant_tanks')
    tanklar = {t['key']: t for t in liste} if isinstance(liste, list) else {}
    return tanklar, arac


def _silindir_tanimi(kayit):
    """UÇUŞ tank kaydından düz kapaklı dik silindir; (tanım, sebep)."""
    if not isinstance(kayit, dict):
        return None, 'TANK_GEOMETRISI_YAYIMLANMADI'
    D, L, V = (_sayi(kayit.get('diameter_m')), _sayi(kayit.get('length_m')),
               _sayi(kayit.get('volume_m3')))
    if D is None or L is None or D <= 0.0 or L <= 0.0:
        return None, 'TANK_GEOMETRISI_YAYIMLANMADI'
    if V is not None and not _yakin(V, math.pi / 4.0 * D * D * L):
        return None, 'TANK_GEOMETRISI_DIK_SILINDIR_DEGIL'
    return {'tur': _sa.TANK_TURU_DIK_SILINDIR, 'R_m': D / 2.0, 'H_m': L}, None


def _sivi_adaylari(sonuc, ucus_tanklari, ucus_itki):
    """Sıvı motorun iki tankı: ham okuma (bağlanma kararı sonra)."""
    pt = sonuc.get('propellant_tanks') if isinstance(
        sonuc.get('propellant_tanks'), dict) else {}
    t_b = _sayi(ucus_itki.get('burn_time'))
    defter = sonuc.get('mass_flow_ledger')
    defter_kapali = (not isinstance(defter, dict)
                     or defter.get('status') == DEFTER_KAPALI)
    debiler = {'oxidizer_tank': _sayi(sonuc.get('oxidizer_flow')),
               'fuel_tank': _sayi(sonuc.get('fuel_flow'))}
    hatlar = {'oxidizer_tank': 'oxidizer_line', 'fuel_tank': 'fuel_line'}
    out = []
    for anahtar, tid in SIVI_TANKLARI:
        blok = pt.get(anahtar) if isinstance(pt.get(anahtar), dict) else {}
        pd = blok.get('propellant_data') if isinstance(
            blok.get('propellant_data'), dict) else {}
        aday = {'tank_id': tid, 'motor_anahtari': 'propellant_tanks.' + anahtar,
                'sebep': [], 'beyan': ['YOGUNLUK_SABIT'],
                'sivi_adi': str(blok.get('propellant_type') or tid),
                'ucus_tanki': ucus_tanklari.get(anahtar)}
        tanim, sebep = _silindir_tanimi(ucus_tanklari.get(anahtar))
        if sebep:
            aday['sebep'].append(sebep)
        aday['tank'] = tanim
        aday['tank_kaynagi'] = (
            f'motor tasarımı: propellant_tanks.{anahtar}.dimensions (iç çap '
            've boy; düz kapaklı dik silindir, V = π/4·D²·L)')
        rho = _sayi(pd.get('density'))
        aday['rho'] = rho
        aday['rho_kaynagi'] = (f'propellant_tanks.{anahtar}.propellant_data.'
                               f'density ({pd.get("density_source")})')
        if rho is None or rho <= 0.0:
            aday['sebep'].append('YOGUNLUK_YAYIMLANMADI')
        m0, m_nom = _sayi(pd.get('mass')), _sayi(pd.get('mass_nominal'))
        aday['m0'] = m0
        if m0 is None or m0 <= 0.0 or m_nom is None or m_nom < 0.0:
            aday['sebep'].append('YUKLENEN_KUTLE_YAYIMLANMADI')
        mdot = debiler[anahtar]
        aday['mdot'] = mdot
        if not defter_kapali or mdot is None or mdot <= 0.0 or t_b is None \
                or t_b <= 0.0:
            aday['sebep'].append('TUKETIM_YAYIMLANMADI')
        if not aday['sebep']:
            # Nominal kütle debi × süredir (motorun künyesi); tutmazsa ya da
            # yüklenenden fazla yanıyorsa bütçe kapanmıyor.
            if not _yakin(mdot * t_b, m_nom) or m_nom > m0:
                aday['sebep'].append('DEBI_BUTCESI_TUTARSIZ')
            else:
                aday['m_t'] = {'t': [0.0, t_b], 'm': [m0, m0 - m_nom]}
                aday['beyan'].append('TUKETIM_SABIT_DEBI')
                aday['seri_kaynagi'] = (
                    f'propellant_tanks.{anahtar}.propellant_data.mass − '
                    f'debi × süre ({"oxidizer_flow" if anahtar == "oxidizer_tank" else "fuel_flow"} '
                    f'× flight burn_time = mass_nominal)')
        # Viskozite (isteğe bağlı): motorun besleme hattında kullandığı μ.
        hat = _al(sonuc, 'detailed_feed_system', 'valve_feedline',
                  hatlar[anahtar])
        mu = _sayi(_al(hat, 'viscosity_Pa_s'))
        aday['nu'] = (mu / rho if (mu is not None and mu > 0.0 and rho)
                      else None)
        aday['nu_kaynagi'] = (
            f'ν = μ/ρ; μ = detailed_feed_system.valve_feedline.'
            f'{hatlar[anahtar]}.viscosity_Pa_s ({_al(hat, "viscosity_source")})'
            if aday['nu'] is not None else None)
        baffle = _al(blok, 'slosh', 'baffle')
        aday['motor_bafl_sonumu'] = _sayi(_al(baffle, 'damping_ratio'))
        if aday['motor_bafl_sonumu'] is not None:
            aday['beyan'].append('BAFL_SONUMU_UYGULANMADI')
        aday['f1_hz_motor_1g'] = _sayi(_al(blok, 'slosh', 'f1_hz'))
        ull = _sayi(_al(pt, 'system_summary', 'ullage_fraction'))
        aday['tasarim_dolulugu'] = (1.0 - ull / 100.0
                                    if ull is not None and 0.0 <= ull < 100.0
                                    else None)
        out.append(aday)
    return out


def _hibrit_oksitleyici(eng):
    ad = (_al(eng, 'oxidizer_inlet_state', 'oxidizer')
          or _al(eng, 'combustion_analysis', 'inputs', 'oxidizer_type'))
    return str(ad).lower() if isinstance(ad, str) and ad.strip() else None


def _hibrit_adayi(sonuc, ucus_tanklari, ucus_itki):
    """Hibrit motorun oksitleyici tankı: ham okuma."""
    eng = sonuc.get('motor') if isinstance(sonuc.get('motor'), dict) else sonuc
    ox = _hibrit_oksitleyici(eng)
    tid = HIBRIT_N2O_KIMLIGI if ox == 'n2o' else HIBRIT_OKSITLEYICI_KIMLIGI
    blok = eng.get('oxidizer_tank_slosh') if isinstance(
        eng.get('oxidizer_tank_slosh'), dict) else {}
    aday = {'tank_id': tid, 'motor_anahtari': 'motor.oxidizer_tank_slosh',
            'sebep': [], 'beyan': ['YOGUNLUK_SABIT'],
            'sivi_adi': (ox or 'oxidizer').upper(),
            'ucus_tanki': ucus_tanklari.get('oxidizer_tank')}
    tanim, sebep = _silindir_tanimi(ucus_tanklari.get('oxidizer_tank'))
    if sebep:
        aday['sebep'].append(sebep)
    aday['tank'] = tanim
    aday['tank_kaynagi'] = (
        'motor tasarımı: motor.oxidizer_tank_slosh (tank_diameter_m, '
        'tank_length_m; düz kapaklı dik silindir, V = π/4·D²·L)')
    rho = _sayi(blok.get('liquid_density_kg_m3'))
    aday['rho'] = rho
    aday['rho_kaynagi'] = ('motor.oxidizer_tank_slosh.liquid_density_kg_m3 '
                           '(ateşleme anındaki doyma yoğunluğu)')
    if rho is None or rho <= 0.0:
        aday['sebep'].append('YOGUNLUK_YAYIMLANMADI')
    m0 = _sayi(blok.get('liquid_mass_kg'))
    aday['m0'] = m0
    if m0 is None or m0 <= 0.0:
        aday['sebep'].append('YUKLENEN_KUTLE_YAYIMLANMADI')
    aday['nu'], aday['nu_kaynagi'] = None, None
    aday['motor_bafl_sonumu'] = None
    aday['f1_hz_motor_1g'] = _sayi(_al(blok, 'slosh', 'f1_hz'))
    aday['tasarim_dolulugu'] = _sayi(blok.get('liquid_fill_fraction'))
    t_b = _sayi(ucus_itki.get('burn_time'))
    tb = eng.get('tank_blowdown') if isinstance(
        eng.get('tank_blowdown'), dict) else {}
    envanter = tb.get('oxidizer_inventory') if isinstance(
        tb.get('oxidizer_inventory'), dict) else {}
    if aday['sebep']:
        return aday, envanter
    if (tb.get('status') == BOSALMA_MODELLENDI
            and tb.get('feed_mode') == BOSALMA_KIPI
            and ucus_itki.get('curve_source') == 'motor_blowdown'):
        ts, ms = envanter.get('liquid_mass_time_s'), envanter.get(
            'liquid_mass_kg')
        if not (isinstance(ts, list) and isinstance(ms, list)
                and 2 <= len(ts) == len(ms)
                <= _k2.KUTLE_SERISI_NOKTA_SINIRI):
            aday['sebep'].append('TUKETIM_YAYIMLANMADI')
            return aday, envanter
        t = [_sayi(x) for x in ts]
        m = [_sayi(x) for x in ms]
        m_bas = _sayi(envanter.get('tank_initial_liquid_kg'))
        if (None in t or None in m or m_bas is None
                or t[0] != 0.0 or any(b <= a for a, b in zip(t, t[1:]))
                or min(m) < 0.0 or not _yakin(m[0], m0)
                or not _yakin(m[0], m_bas) or t_b is None
                or t[-1] > t_b * (1.0 + TUTARLILIK_BAGIL_TOL)
                or any(b > a for a, b in zip(m, m[1:]))):
            aday['sebep'].append('TUKETIM_SERISI_TUTARSIZ')
            return aday, envanter
        aday['m_t'] = {'t': t, 'm': m}
        aday['beyan'].append('TUKETIM_BOSALMA_COZUMU')
        aday['seri_kaynagi'] = ('motor.tank_blowdown.oxidizer_inventory.'
                                'liquid_mass_time_s / liquid_mass_kg')
        # V307/ÇALKANTI-KARARLILIK (karar 16 Kas): sıvı yoğunluğu serisi
        # motorun boşalma çözümünden (aynı adım sınırları). Motor seriyi
        # yayımlamıyorsa (alan yok / None) yoğunluk sabit kalır (BEYANLI);
        # yayımlıyor ama tutarsızsa tank bağlanmaz (fail-closed).
        rs = envanter.get('liquid_density_kg_m3')
        if rs is not None:
            r = [_sayi(x) for x in rs] if isinstance(rs, list) else []
            # Doyma modelinin sıvı hâli vermediği kuyruk (None) seriden düşer.
            n_ok = next((i for i, x in enumerate(r)
                         if x is None or x <= 0.0), len(r))
            if len(r) != len(t) or n_ok < 1 or not _yakin(r[0], rho):
                aday['sebep'].append('YOGUNLUK_SERISI_TUTARSIZ')
                return aday, envanter
            aday['rho_t'] = {'t': t[:n_ok], 'rho': r[:n_ok]}
            aday['beyan'] = [b for b in aday['beyan'] if b != 'YOGUNLUK_SABIT']
            aday['beyan'].append('YOGUNLUK_BOSALMA_COZUMU')
            aday['rho_seri_kaynagi'] = (
                'motor.tank_blowdown.oxidizer_inventory.liquid_mass_time_s / '
                'liquid_density_kg_m3')
        return aday, envanter
    # Regüle besleme: sabit ṁ_ox (motorun tasarım çifti), BEYANLI.
    mdot = _sayi(eng.get('mdot_ox'))
    aday['mdot'] = mdot
    if mdot is None or mdot <= 0.0 or t_b is None or t_b <= 0.0:
        aday['sebep'].append('TUKETIM_YAYIMLANMADI')
        return aday, envanter
    m_son = m0 - mdot * t_b
    if m_son < -TUTARLILIK_BAGIL_TOL * m0:
        aday['sebep'].append('DEBI_BUTCESI_TUTARSIZ')
        return aday, envanter
    aday['m_t'] = {'t': [0.0, t_b], 'm': [m0, max(m_son, 0.0)]}
    aday['beyan'].append('TUKETIM_SABIT_DEBI')
    aday['seri_kaynagi'] = 'motor.oxidizer_tank_slosh.liquid_mass_kg − motor.mdot_ox × flight burn_time'
    return aday, envanter


# ---------------------------------------------------------------------------
# Uçuş kütlesi bütçesi (UÇUŞ'un tek kaynağı: motor_flight_thrust + normalize)
# ---------------------------------------------------------------------------
def _sivi_kutle_denetimi(adaylar, arac):
    """Σm0 = UÇUŞ harcanan + yedek kalemi; Σm_son = yedek kalemi."""
    ucus = arac['flight_thrust']
    harcanan = _sayi(ucus.get('propellant_consumed_kg'))
    yedek = sum(_sayi(k.get('mass_kg')) or 0.0
                for k in (arac.get('engine_inert_mass_items') or [])
                if k.get('key') == 'reserve_propellant')
    m0 = sum(a['m0'] for a in adaylar)
    m_son = sum(a['m_t']['m'][-1] for a in adaylar)
    out = {'tank_sivisi_baslangic_kg': m0, 'tank_sivisi_yanma_sonu_kg': m_son,
           'ucus_harcanan_kg': harcanan, 'ucus_yedek_itici_kg': yedek,
           'kural': ('Σ yüklenen = UÇUŞ harcanan (flight_thrust.'
                     'propellant_consumed_kg) + uçan atıl kütlenin yedek itici '
                     'kalemi; Σ yanma sonu = yedek itici kalemi')}
    out['tutarli'] = bool(harcanan is not None
                          and _yakin(m0, harcanan + yedek)
                          and _yakin(m_son, yedek))
    return out


def _hibrit_kutle_denetimi(aday, eng, envanter, arac):
    """Hibrit: ateşlemedeki tank (sıvı + ullage buharı) + dökülen yakıt =
    UÇUŞ yüklenen; boşalmada yanma sonu tank envanteri UÇUŞ'un uçurduğu
    kalanın içinde."""
    ucus = arac['flight_thrust']
    yuklenen = _sayi(ucus.get('propellant_loaded_kg'))
    kalan = _sayi(ucus.get('propellant_residual_kg'))
    ox_yuklu = _sayi(eng.get('oxidizer_mass'))
    yakit_yuklu = _sayi(eng.get('fuel_mass_loaded'))
    buhar0 = _sayi(envanter.get('tank_initial_vapour_kg'))
    tank_son = _sayi(envanter.get('tank_final_kg'))
    bosalma = 'TUKETIM_BOSALMA_COZUMU' in aday['beyan']
    out = {'tank_sivisi_baslangic_kg': aday['m0'],
           'tank_sivisi_yanma_sonu_kg': aday['m_t']['m'][-1],
           'oksitleyici_yuklu_kg': ox_yuklu, 'yakit_yuklu_kg': yakit_yuklu,
           'tank_buhari_baslangic_kg': buhar0,
           'tank_son_envanter_kg': tank_son,
           'ucus_yuklenen_kg': yuklenen, 'ucus_kalan_kg': kalan,
           'kural': ('UÇUŞ yüklenen = yüklü oksitleyici + dökülen yakıt; '
                     'yüklü oksitleyici = tank sıvısı + ullage buharı '
                     '(boşalma) ya da ≥ tank sıvısı (regüle); boşalmada '
                     'yanma sonu tank envanteri ≤ UÇUŞ kalan')}
    ok = (yuklenen is not None and ox_yuklu is not None
          and yakit_yuklu is not None
          and _yakin(yuklenen, ox_yuklu + yakit_yuklu)
          and aday['m0'] <= ox_yuklu * (1.0 + TUTARLILIK_BAGIL_TOL))
    if ok and bosalma:
        ok = (buhar0 is not None and tank_son is not None
              and kalan is not None
              and _yakin(ox_yuklu, aday['m0'] + buhar0)
              and tank_son <= kalan * (1.0 + TUTARLILIK_BAGIL_TOL))
    out['tutarli'] = bool(ok)
    return out


# ---------------------------------------------------------------------------
# Tankın araçtaki yeri
# ---------------------------------------------------------------------------
def _arac_duzeni_kapisi(arac_duzeni, kimlikler):
    """Girdi kapısı: biçim ve kimlik (adlı ret). Döner: (kaynak, veri, ölçüler)."""
    if arac_duzeni is None:
        return None, None, {}
    if not isinstance(arac_duzeni, dict):
        _ret('TIP', 'arac_duzeni', 'sözlük olmalı')
    bilinmeyen = set(arac_duzeni) - set(YER_KAYNAKLARI) - set(ARAC_OLCULERI)
    if bilinmeyen:
        _ret('ALAN_BILINMEYEN', 'arac_duzeni',
             f'bilinmeyen alan {sorted(bilinmeyen)}')
    kaynaklar = [k for k in YER_KAYNAKLARI if k in arac_duzeni]
    if len(kaynaklar) != 1:
        _ret('YER_KAYNAGI', 'arac_duzeni',
             f'tam olarak bir yer kaynağı olmalı {YER_KAYNAKLARI}; '
             f'verilen {kaynaklar}')
    olcu = {}
    for k in ARAC_OLCULERI:
        if arac_duzeni.get(k) is not None:
            olcu[k] = _girdi_sayisi(arac_duzeni[k], 'arac_duzeni.' + k,
                                    pozitif=True)
    kaynak = kaynaklar[0]
    veri = arac_duzeni[kaynak]
    alan = 'arac_duzeni.' + kaynak
    if kaynak == 'ardisik':
        if not isinstance(veri, dict) or not set(veri) <= {'sira'}:
            _ret('TIP', alan, "{'sira': [tank_id, ...]} ya da {} olmalı")
        # V307/UÇUŞ-GÖVDE: sıra verilmezse UÇUŞ'un tank listesi sırası
        # (türetilmiş gövdenin kendi dizilimi; ``kimlikler`` o sıradadır).
        sira = veri['sira'] if 'sira' in veri else list(kimlikler)
        if not isinstance(sira, (list, tuple)) or \
                sorted(map(str, sira)) != sorted(kimlikler) or \
                len(set(sira)) != len(sira):
            _ret('SIRA', alan + '.sira',
                 f'motorun tanklarının ({sorted(kimlikler)}) her biri tam bir '
                 f'kez, burundan kıça sırayla verilmeli ({sira!r})')
        if 'govde_boyu_m' not in olcu:
            _ret('ALAN_EKSIK', 'arac_duzeni.govde_boyu_m',
                 'ardışık dizilim gövde boyunu ister')
        return kaynak, list(sira), olcu
    if not isinstance(veri, dict) or len(veri) > len(_tablo.TANK_KIMLIKLERI):
        _ret('TIP', alan, '{tank_id: x [m]} sözlüğü olmalı')
    temiz = {}
    for tid, x in veri.items():
        if tid not in kimlikler:
            _ret('TANK_KIMLIGI', alan,
                 f'{tid!r} bu motorun tanklarından değil ({sorted(kimlikler)})')
        temiz[tid] = _girdi_sayisi(x, f'{alan}.{tid}')
    return kaynak, temiz, olcu


def _yer_ata(adaylar, kaynak, veri, olcu, motor_boyu):
    """Bağlanabilir adaylara x_tank_taban_m ve kaynağını ata (yerinde)."""
    hazir = [a for a in adaylar if not a['sebep']]
    if kaynak is None:
        for a in hazir:
            a['sebep'].append('TANK_ISTASYONU_VERILMEDI')
        return
    if kaynak == 'tank_istasyonlari':
        for a in hazir:
            if a['tank_id'] in veri:
                a['x_tank_taban_m'] = veri[a['tank_id']]
                a['istasyon_kaynagi'] = 'araç tanımı (girilen tank tabanı)'
            else:
                a['sebep'].append('TANK_ISTASYONU_VERILMEDI')
    elif kaynak == 'sivi_km_istasyonlari':
        for a in hazir:
            if a['tank_id'] not in veri:
                a['sebep'].append('TANK_ISTASYONU_VERILMEDI')
                continue
            # Yer dönüşümü 6-DOF'un t = 0 dolulukuyla (m_t[0]/(ρ·V_iç)) AYNI
            # sayıdan: x_taban + z_km(d0) kullanıcının x_km'sine eşit kalır.
            d0 = a['tablo'].doluluk_kutleden(a['m0'])
            z_km = a['tablo'].ara(d0)['z_km_m']
            a['x_tank_taban_m'] = veri[a['tank_id']] + z_km
            a['istasyon_kaynagi'] = (
                f'yüklü sıvı kütle merkezi x_km = {veri[a["tank_id"]]:g} m + '
                f'z_km = {z_km:g} m')
            a['beyan'].append('TANK_ISTASYONU_SIVI_KM_DONUSUMU')
    else:   # ardisik
        if motor_boyu is None:
            for a in hazir:
                a['sebep'].append('MOTOR_BOYU_YAYIMLANMADI')
            return
        if len(hazir) != len(adaylar):
            # Dizilim bütün tankların boyunu ister; biri okunamadıysa öbürünün
            # yeri de bilinmez.
            for a in hazir:
                a['sebep'].append('TANK_ISTASYONU_VERILMEDI')
            return
        # Dizilim TEK TANIMDAN (flight_vehicle.tank_stack): gövde türetme
        # kuralı gövde boyunu, burası tank yerini aynı işlevden alır. İç boy
        # tablonunkidir (yüklenen geometri motorun silindirinden farklı
        # olabilir); baş kalınlığı UÇUŞ tank kaydından.
        sirali = {a['tank_id']: a for a in adaylar}
        kayitlar = []
        for tid in veri:
            a = sirali[tid]
            kayitlar.append({
                'key': tid, 'length_m': a['tablo'].geometri['H_ic_m'],
                'end_closure_thickness_m': (a.get('ucus_tanki') or {}).get(
                    'end_closure_thickness_m')})
        yigin = _fv.tank_stack(kayitlar, motor_boyu)
        for y in yigin['tanks']:
            a = sirali[y['key']]
            a['x_tank_taban_m'] = olcu['govde_boyu_m'] - y['base_from_tail_m']
            a['istasyon_kaynagi'] = (
                f'ardışık dizilim: gövde boyu {olcu["govde_boyu_m"]:g} m − '
                f'motor boyu {motor_boyu:g} m, sıra {list(veri)}; baş '
                'kalınlıkları motorun tank kabuğundan'
                + (' (bu tankta yayımlanmadı: 0 alındı)'
                   if y['key'] in yigin['shell_not_published'] else ''))
            a['beyan'].append('TANK_ISTASYONU_ARDISIK_DIZILIM')


def _uygunluk(adaylar, olcu):
    """Gövde ölçüsü verildiyse tank araca sığıyor mu; tanklar çakışıyor mu."""
    yerli = [a for a in adaylar if not a['sebep']]
    for a in yerli:
        geo = a['tablo'].geometri
        taban, tepe = a['x_tank_taban_m'], a['x_tank_taban_m'] - geo['H_ic_m']
        L = olcu.get('govde_boyu_m')
        if tepe < 0.0 or (L is not None and taban > L):
            a['sebep'].append('TANK_ARAC_DISI')
        elif olcu.get('burun_boyu_m') is not None and \
                tepe < olcu['burun_boyu_m']:
            a['sebep'].append('TANK_BURUN_ICINDE')
        # Tankın DIŞ çapı: tablo iç çapı + 2 × motorun yayımladığı cidar
        # (gövde türetme kuralıyla aynı tanım; cidar yayımlanmamışsa iç çap).
        cidar = _sayi((a.get('ucus_tanki') or {}).get('wall_thickness_m'))
        if olcu.get('govde_capi_m') is not None and \
                2.0 * geo['R_ref_m'] + 2.0 * (cidar or 0.0) \
                > olcu['govde_capi_m']:
            a['sebep'].append('TANK_GOVDEDEN_GENIS')
    yerli = [a for a in yerli if not a['sebep']]
    for i, a in enumerate(yerli):
        for b in yerli[i + 1:]:
            a0 = a['x_tank_taban_m'] - a['tablo'].geometri['H_ic_m']
            b0 = b['x_tank_taban_m'] - b['tablo'].geometri['H_ic_m']
            if a0 < b['x_tank_taban_m'] and b0 < a['x_tank_taban_m']:
                for t in (a, b):
                    if 'TANKLAR_CAKISIYOR' not in t['sebep']:
                        t['sebep'].append('TANKLAR_CAKISIYOR')


# ---------------------------------------------------------------------------
# Tablo (TEK GİRİŞ: slosh_analysis.esdeger_model_tablosu)
# ---------------------------------------------------------------------------
def _tablo_kur(aday, tank_geometrisi, yontem):
    tank = tank_geometrisi if tank_geometrisi is not None else aday['tank']
    kaynak = (aday['tank_kaynagi'] if tank_geometrisi is None else None)
    sivi = {'ad': aday['sivi_adi'], 'rho_kg_m3': aday['rho'],
            'sigma_N_m': None, 'nu_m2_s': aday['nu']}
    try:
        r = _sa.esdeger_model_tablosu(aday['tank_id'], tank, sivi,
                                      yontem=yontem, kaynak=kaynak)
    except _sa.SloshGirdiHatasi as exc:
        _ret('TANK_GEOMETRISI', f'tank_geometrileri.{aday["tank_id"]}',
             str(exc))
    aday['tablo_yolu'] = r['yol']
    aday['geometri_girdisi'] = r.get('geometri_girdisi')
    aday['oneri_yontem'] = r.get('oneri_yontem')
    aday['satir_durumlari'] = r.get('satir_durumlari')
    if r['tablo'] is None:
        aday['sebep'].append('TANK_GEOMETRISI_RET')
        return
    aday['tablo'] = r['tablo']
    geo = r['tablo'].geometri
    if aday['m0'] / aday['rho'] > geo['V_ic_m3'] * (1.0 + TUTARLILIK_BAGIL_TOL):
        aday['sebep'].append('TANK_HACMI_YETERSIZ')


# ---------------------------------------------------------------------------
# Genel giriş
# ---------------------------------------------------------------------------
def slosh_tanklari(motor_type, motor_sonucu, *, arac_duzeni=None,
                   tank_geometrileri=None,
                   yontem=_sa.YONTEM_SECIMI_OTOMATIK):
    """Motor sonucu + araç düzeni → 6-DOF çalkantı tank listesi.

    Parameters
    ----------
    motor_type : {'liquid', 'hybrid', 'solid'}
    motor_sonucu : dict
        Sayfanın hesap ucunun yanıt gövdesi (``/calculate_liquid``,
        ``/calculate`` — ``motor`` sarmalı kabul —, ``/calculate_solid``).
    arac_duzeni : dict | None
        Tankın araçtaki yeri (modül başındaki ``YER_KAYNAKLARI``) ve isteğe
        bağlı gövde ölçüleri. None: yer bilinmiyor → tanklar bağlanmaz
        (``TANK_ISTASYONU_VERILMEDI``).
    tank_geometrileri : dict | None
        {tank_id: tank tanımı} — ``esdeger_model_tablosu``'nun ``tank``
        girdisi (profil / dosya / içe aktarıcı sonucu; §6.2 tank geometrisi).
        Verilmezse motorun düz kapaklı dik silindiri.
    yontem : str
        ``esdeger_model_tablosu`` yol seçimi.

    Returns
    -------
    dict
        ``durum`` (BAGLANDI / KISMI / BAGLANMADI / UYGULANMAZ), ``sebep``,
        ``slosh_tanks`` (K2 arayüzü; yalnız bağlanan tanklar, ``SloshTablo``
        nesneleriyle), ``tanklar`` (tank başına JSON'a hazır rapor),
        ``kutle_denetimi``, ``kunye``. JSON karşılığı :func:`json_ozeti`.
    """
    mt = motor_type.strip().lower() if isinstance(motor_type, str) else None
    if mt not in ('liquid', 'hybrid', 'solid'):
        _ret('MOTOR_TURU', 'motor_type',
             f"'liquid', 'hybrid' ya da 'solid' olmalı ({motor_type!r})")
    if not isinstance(motor_sonucu, dict):
        _ret('TIP', 'motor_sonucu', 'hesap ucunun yanıt gövdesi (sözlük) olmalı')
    if motor_sonucu.get('error') or motor_sonucu.get('status') == 'error':
        _ret('MOTOR_SONUCU_HATA', 'motor_sonucu',
             'hesap ucu bu motoru hesaplamadı (error)')
    if yontem not in _sa.YONTEM_SECIMLERI:
        _ret('YONTEM', 'yontem', f'{_sa.YONTEM_SECIMLERI} içinden olmalı')
    temel = {'sema': SONUC_SEMASI, 'sema_surumu': SONUC_SURUMU,
             'motor_type': mt, 'kunye': KUNYE, 'kutle_denetimi': None}
    if mt == 'solid':
        if arac_duzeni is not None or tank_geometrileri is not None:
            _ret('TANK_YOK', 'arac_duzeni',
                 'katı motorun sıvı tankı yok; tank yeri ve geometrisi '
                 'verilemez')
        return dict(temel, durum=DURUM_UYGULANMAZ, sebep=['TANK_YOK'],
                    slosh_tanks=[], tanklar=[])

    ucus_tanklari, arac = _ucus_tanklari(mt, motor_sonucu)
    ucus_itki = (arac or {}).get('flight_thrust') or {}
    if mt == 'liquid':
        adaylar = _sivi_adaylari(motor_sonucu, ucus_tanklari, ucus_itki)
        envanter = None
    else:
        aday, envanter = _hibrit_adayi(motor_sonucu, ucus_tanklari, ucus_itki)
        adaylar = [aday]
        eng = (motor_sonucu.get('motor')
               if isinstance(motor_sonucu.get('motor'), dict) else motor_sonucu)
    kimlikler = [a['tank_id'] for a in adaylar]

    # Girdi kapıları (adlı ret) — motor sonucundan bağımsız biçim denetimi.
    kaynak, veri, olcu = _arac_duzeni_kapisi(arac_duzeni, kimlikler)
    if tank_geometrileri is not None:
        if not isinstance(tank_geometrileri, dict):
            _ret('TIP', 'tank_geometrileri', '{tank_id: tank tanımı} olmalı')
        for tid in tank_geometrileri:
            if tid not in kimlikler:
                _ret('TANK_KIMLIGI', 'tank_geometrileri',
                     f'{tid!r} bu motorun tanklarından değil ({kimlikler})')
    # Tablo: yalnız motor alanları okunabilen tankta.
    for a in adaylar:
        if not a['sebep']:
            _tablo_kur(a, (tank_geometrileri or {}).get(a['tank_id']), yontem)

    # Uçuş kütlesi bütçesi (tüketimi kurulan tanklarla).
    serili = [a for a in adaylar if 'm_t' in a and not a['sebep']]
    denetim = None
    if serili and arac is not None:
        if mt == 'liquid' and len(serili) == len(adaylar):
            denetim = _sivi_kutle_denetimi(serili, arac)
        elif mt == 'hybrid':
            denetim = _hibrit_kutle_denetimi(serili[0], eng, envanter or {},
                                             arac)
        if denetim is not None and not denetim['tutarli']:
            for a in serili:
                a['sebep'].append('UCUS_KUTLESIYLE_TUTARSIZ')

    motor_boyu = olcu.get('motor_boyu_m')
    if motor_boyu is None and arac is not None:
        motor_boyu = _sayi(arac.get('engine_length_m'))
    _yer_ata(adaylar, kaynak, veri, olcu, motor_boyu)
    _uygunluk(adaylar, olcu)

    slosh_tanks, tanklar = [], []
    for a in adaylar:
        bagli = not a['sebep']
        if bagli:
            giris = {'tank_id': a['tank_id'],
                     'x_tank_taban_m': a['x_tank_taban_m'],
                     'tablo': a['tablo'], 'm_t': a['m_t'],
                     'zeta_ek': None}
            if a.get('rho_t') is not None:
                # K2 isteğe bağlı alanı (ρ(t)); yoksa anahtar HİÇ konmaz
                # (sıvı motorda tank girişi 3.0.7 K4 biçimiyle aynı kalır).
                giris['rho_t'] = a['rho_t']
            slosh_tanks.append(giris)
        tanklar.append(_tank_raporu(a, bagli))
    n = len(slosh_tanks)
    durum = (DURUM_BAGLANDI if n == len(adaylar) else
             DURUM_KISMI if n else DURUM_BAGLANMADI)
    sebep = []
    for a in adaylar:
        sebep.extend(k for k in a['sebep'] if k not in sebep)
    return dict(temel, durum=durum, sebep=sebep, slosh_tanks=slosh_tanks,
                tanklar=tanklar, kutle_denetimi=denetim)


def _yuklu_doluluk(a):
    """Yüklü doluluk (V307/TEK-TANIM, CI-KIRMIZI K1): motorun tasarım
    doluluğu (sıvıda 1 − ullage, hibritte ``liquid_fill_fraction``) yüklü
    kütlenin m0/(ρ·V_iç) dolulukla tutarlıysa O sayı (ızgara düğümü; motor
    kartının derinliği aynı doluluktan, aynı işlevle), değilse — ör.
    kullanıcının tank geometrisi — m0/(ρ·V_iç). Aynı büyüklüğün iki hesabı
    son basamakta ayrışıp tabloyu düğüm yerine ara değere götürüyordu."""
    tablo = a['tablo']
    d_kutle = tablo.doluluk_kutleden(a['m0'])
    d_tas = a.get('tasarim_dolulugu')
    if d_tas is not None and d_tas > 0.0 and _yakin(d_tas, d_kutle):
        return d_tas
    return d_kutle


def _tank_raporu(a, bagli):
    """Tank raporu (yayımlanacak alanlar; K5).

    V307/UÇUŞ-GÖVDE (K4 DEVİR): ``tablo`` (``SloshTablo`` nesnesi; kurulamadıysa
    None), ``oneri_yontem``, ``satir_durumlari`` ve ``beyan`` 6-DOF'a
    BAĞLANMAYAN tankta da yayımlanır: motor/tank görünümü (K5) tabloyu
    ikinci kez kurmaz, buradan okur. ``tablo`` nesnedir; JSON karşılığını
    :func:`json_ozeti` verir. ``beyan`` tankın o ana kadar kazandığı
    varsayım kodlarıdır (yer kodları yalnız yer atandıysa girer).
    """
    tablo = a.get('tablo')
    geo = tablo.geometri if tablo is not None else None
    r = {'tank_id': a['tank_id'], 'motor_anahtari': a['motor_anahtari'],
         'durum': DURUM_BAGLANDI if bagli else DURUM_BAGLANMADI,
         'sebep': list(a['sebep']),
         'beyan': list(a['beyan']),
         'tablo': tablo,
         'oneri_yontem': a.get('oneri_yontem'),
         'satir_durumlari': a.get('satir_durumlari'),
         'sivi_adi': a['sivi_adi'],
         'rho_kg_m3': a.get('rho'), 'rho_kaynagi': a.get('rho_kaynagi'),
         'rho_t': a.get('rho_t') if bagli else None,
         'rho_seri_kaynagi': a.get('rho_seri_kaynagi'),
         'nu_m2_s': a.get('nu'), 'nu_kaynagi': a.get('nu_kaynagi'),
         'yuklenen_sivi_kg': a.get('m0'),
         'm_t': a.get('m_t'), 'seri_kaynagi': a.get('seri_kaynagi'),
         'tablo_yolu': a.get('tablo_yolu'),
         'geometri': ({'tur': geo['tur'], 'R_ref_m': geo['R_ref_m'],
                       'H_ic_m': geo['H_ic_m'], 'V_ic_m3': geo['V_ic_m3'],
                       'kaynak': geo['kaynak']} if geo else None),
         'geometri_girdisi': a.get('geometri_girdisi'),
         'x_tank_taban_m': a.get('x_tank_taban_m'),
         'istasyon_kaynagi': a.get('istasyon_kaynagi'),
         'motor_bafl_sonumu_tam_doluluk': a.get('motor_bafl_sonumu'),
         'zeta_ek': None,
         'f1_hz_1g': None}
    if tablo is not None and a.get('m0') is not None:
        d0 = _yuklu_doluluk(a)
        s = tablo.ara(d0)
        r['yuklu_doluluk'] = d0
        r['f1_hz_1g'] = {
            'motor': a.get('f1_hz_motor_1g'),
            'tablo': (math.sqrt(s['kappa1_1m'] * G_0) / (2.0 * math.pi)
                      if s.get('kappa1_1m') is not None else None)}
    return r


def json_ozeti(sonuc):
    """:func:`slosh_tanklari` sonucunun JSON'a hazır kopyası (tablo sözlük)."""
    out = {k: v for k, v in sonuc.items()
           if k not in ('slosh_tanks', 'tanklar')}
    out['slosh_tanks'] = [dict(t, tablo=t['tablo'].sozluk())
                          for t in sonuc['slosh_tanks']]
    out['tanklar'] = [dict(t, tablo=(t['tablo'].sozluk()
                                     if t.get('tablo') is not None else None))
                      for t in sonuc['tanklar']]
    return out
