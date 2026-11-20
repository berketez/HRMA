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
#: v307-k5-2 (ONARIM-ÇALK, M7-UCUS-13): zaman satırlarında frekans ve çeper
#: sönümü alanları '_sabit_geff' adını taşır; ``zaman.frekans_tanimi``.
GORUNUM_SURUMU = 'v307-k5-2'
#: Araç ekibine aktarım dosyasının şema kimliği (§A.6). Eşdeğer model
#: tablosu dosyanın içinde sözleşmenin kendi şemasıyla (``slosh_tablo``)
#: durur; bu kimlik zarfı ve zaman eksenini tanıtır.
AKTARIM_SEMASI = 'calkanti_arac_aktarim_tablosu'
AKTARIM_SURUMU = 'v307-k5-2'

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
    ('Gamma1', '-'), ('omega1_sabit_geff_rad_s', 'rad/s'),
    ('f1_sabit_geff_hz', 'Hz'), ('zeta_ceper_sabit_geff', '-'),
    ('I0_kgm2', 'kg.m2'), ('I0_kaynak', '-'),
    ('durum', '-'), ('sebep', '-'),
)
_ZAMAN_METIN = ('I0_kaynak', 'durum')
#: 3.0.7 ONARIM-ÇALK (M7-UCUS-13): zaman ekseni doluluğu UÇUŞ zamanına göre
#: verir ama frekans ve çeper sönümü tek, SABİT bir g_eff'tedir (motor
#: görünümünde uçuşun eksenel ivmesi yoktur). ÖLÇÜLDÜ (mühendis turu, örnek
#: hibrit, t = 4,85 s): CSV 'omega1_rad_s' 13,04 (1 g) ⟷ 6-DOF aynı an 30,79
#: rad/s (uçuş ivmesi ~5,6 g): sütun adı bu farkı söylemiyordu. Sütun adları
#: artık '_sabit_geff' taşır ve tanım CSV meta satırında, JSON'da ve ekranda
#: yazılıdır; uçuştaki değer ω1(t) = √(κ1(t)·a_eff(t)) (κ1 sütunu verilir).
FREKANS_TANIMI_KODU = 'FREKANS_SABIT_GEFF'
FREKANS_TANIMI_EN = (
    'omega1_sabit_geff_rad_s, f1_sabit_geff_hz and zeta_ceper_sabit_geff are '
    'evaluated at the single constant g_eff of this table (g_eff_m_s2); the '
    'time axis gives only the fill at flight time. The axial acceleration of '
    'the flight is not part of the motor view: in flight '
    'omega1(t) = sqrt(kappa1_1m(t) * a_eff(t)) with the vehicle\'s axial '
    'acceleration a_eff(t) (the 6-DOF panel uses it).')
FREKANS_TANIMI_TR = (
    'omega1_sabit_geff_rad_s, f1_sabit_geff_hz ve zeta_ceper_sabit_geff bu '
    'tablonun tek, sabit g_eff değerinde (g_eff_m_s2) hesaplanır; zaman '
    'ekseni yalnız doluluğu uçuş zamanına göre verir. Uçuşun eksenel ivmesi '
    'motor görünümünde yoktur: uçuşta omega1(t) = sqrt(kappa1_1m(t) · '
    'a_eff(t)), a_eff(t) aracın eksenel ivmesi (6-DOF paneli bunu kullanır).')
CSV_ZAMAN_KIMLIGI = f'# {AKTARIM_SEMASI} {AKTARIM_SURUMU} zaman_ekseni'
CSV_META_ONEKI = _tablo.CSV_META_ONEKI


# ---------------------------------------------------------------------------
# 3.0.7 ONARIM2-ÇALK-SEKME (M7-CALK-7): aktarım dosyasının dili ve sütun
# sözlüğü. ÖLÇÜLDÜ (mühendis turu): TR künyede İngilizce kapsam cümlesi, EN
# arayüzden indirilen dosyalar TR ile bayt bayt aynı, doluluk CSV'sinde birim
# sözlüğü yok. KARAR (kulvar; araç ekibinin okuyucusu kırılmaz): insan okur
# metin (künye, kapsam dışı gerekçesi, sütun tanımları, dosya adının
# sözcükleri) arayüz dilindedir; makine okur adlar (sütun adları, durum ve
# sebep kodları, şema/sürüm, tank kimliği) iki dilde AYNIDIR. Doluluk
# CSV'sinin meta nesnesi eşdeğer model tablosu sözleşmesinindir
# (``slosh_tablo``; bilinmeyen alan reddedilir), bu yüzden sözlüğü künyede
# bir satırdır; zaman CSV'sinin metasında ve JSON'da ayrıca sözlük alanı.
# ---------------------------------------------------------------------------
AKTARIM_DILLERI = ('tr', 'en')
AKTARIM_DILI_VARSAYILAN = 'tr'
#: 3.0.7 (M7-CALK-7 kalanı; ONARIM2-ÇALK-SEKME devri, ana model 20 Kas):
#: İngilizce aktarımda künye/kaynak satırlarının İngilizcesi. Satırlar motor
#: tanklarının eşdeğer model tablosu üreticisinin
#: (``slosh_analysis.silindir_tablosu``) ve motor bağlamasının
#: (``slosh_motor_baglanti``) Türkçe künyesinden gelir; o dizgeler sözleşme
#: okuyucularında ve tablolarda da durduğu için kaynakta değil EN aktarımda
#: çevrilir (sayısal içerik aynı). Yüklenen geometrinin sonlu eleman / profil
#: tablosu künyesi bu sürümde Türkçe kalır (3.0.8 listesi).
_EN_KUNYE_SATIRLARI = {
    'κ1: Dodge 2000 Denk. (1.40); SP-8009 Tablo I':
        'κ1: Dodge 2000 Eq. (1.40); SP-8009 Table I',
    'm1/m: Dodge 2000 Tablo 3.2 (d = 2R); SP-8009 Tablo I':
        'm1/m: Dodge 2000 Table 3.2 (d = 2R); SP-8009 Table I',
    'z1: SP-8009 Tablo I; Dodge 2000 Tablo 3.2 (askı − L1)':
        'z1: SP-8009 Table I; Dodge 2000 Table 3.2 (hinge point − L1)',
    'L1 = 1/κ1, askı = z1 + L1: Dodge 2000 Tablo 3.2 (errata REV1 madde 28, 29)':
        'L1 = 1/κ1, hinge point = z1 + L1: Dodge 2000 Table 3.2 (errata REV1 items 28, 29)',
    'm0, z0: Dodge 2000 Denk. (3.1), (3.2), birinci modla kesilmiş':
        'm0, z0: Dodge 2000 Eq. (3.1), (3.2), truncated at the first mode',
    'Γ1: CALKANTI_6DOF_TASARIM (A-10); derin tankta Dodge 2000 (2.15) Γ = 0,649':
        'Γ1: CALKANTI_6DOF_TASARIM (A-10); for a deep tank Dodge 2000 (2.15) Γ = 0.649',
    'I0: SP-106 Tablo 6.1 son satırı (yaklaşık); Dodge 2000 Şekil 3.3 ile h/d '
    '0,251–4,503 aralığında ≤ 0,063 fark':
        'I0: SP-106 Table 6.1, last row (approximate); within 0.063 of Dodge 2000 '
        'Fig. 3.3 for h/d 0.251–4.503',
    'ξn: scipy.special.jnp_zeros (Dodge 2000 Denk. (1.41))':
        'ξn: scipy.special.jnp_zeros (Dodge 2000 Eq. (1.41))',
}
_EN_KAYNAK_PARCALARI = (
    ('debi × süre', 'flow × time'),
    ('(ateşleme anındaki doyma yoğunluğu)', '(saturation density at ignition)'),
)


def _en_kunye(satir):
    """EN aktarımda bir künye/kaynak satırının İngilizcesi (bilinmeyen satır
    olduğu gibi döner)."""
    if not isinstance(satir, str):
        return satir
    satir = _EN_KUNYE_SATIRLARI.get(satir, satir)
    for tr, en in _EN_KAYNAK_PARCALARI:
        satir = satir.replace(tr, en)
    return satir
#: K2'nin kapsam dışı gerekçesinin (``six_dof_slosh.KAPSAM_DISI_GEREKCE``,
#: İngilizce, tek tanım) Türkçesi; ekrandaki ``panel.calkanti.sd.kunye``
#: ile aynı anlam.
KAPSAM_DISI_GEREKCE_TR = (
    'Kontrol döngüsü modellenmedi; güdümlü araçta bu bağlaşım asıl risktir '
    've aktarım tablosu araç ekibinin GNC aracı içindir.')
EKSEN_KURALI_EN = (
    'Axis convention (CALKANTI §2.1): in the tank frame z is the tank '
    'symmetry axis, zero at the lowest inner point of the tank (the end the '
    'effective gravity points to under thrust, the aft side in the vehicle), '
    'z positive towards the nose; all positions in metres. Vehicle station '
    'x = x_tank_bottom − z (from the nose, positive aft); the position of '
    'the tank in the vehicle is not part of the motor view, it is entered in '
    'the 6-DOF panel. The table holds κ1 = ω1²/g_eff [1/m] instead of the '
    'frequency; ω1 = √(κ1·g_eff).')
#: K4 künyesinin (``slosh_motor_baglanti.KUNYE``) İngilizcesi.
K4_KUNYE_EN = (
    'The tank list was built from the motor\'s own result: geometry from '
    'the flight tank list, loaded liquid and density from the motor\'s tank '
    'block, consumption from the motor mass flow (liquid) or the blowdown '
    'solution (hybrid). Equivalent-model table from a single entry point '
    '(slosh_analysis.esdeger_model_tablosu). The position of the tank in '
    'the vehicle is an input; the motor does not publish it.')
#: K4 ve K5 kodlarının İngilizce metni: ekrandaki ``panel.calkanti.kod.*``
#: EN metniyle AYNI (bekçi eşitliği sınar; TR metin kodun kendi tablosunda).
KOD_METNI_EN = {
    'TANK_YOK': 'A solid motor has no liquid propellant tank; slosh does not apply.',
    'TANK_GEOMETRISI_YAYIMLANMADI': 'The motor result does not publish the diameter and length of this tank; no table can be built.',
    'TANK_GEOMETRISI_DIK_SILINDIR_DEGIL': "The published tank volume does not satisfy V = π/4·D²·L; the motor's tank cannot be taken as a flat-capped upright cylinder.",
    'YOGUNLUK_YAYIMLANMADI': 'The motor does not publish the liquid density of this tank.',
    'YUKLENEN_KUTLE_YAYIMLANMADI': 'The motor does not publish the liquid mass loaded into this tank.',
    'TUKETIM_YAYIMLANMADI': 'The motor does not publish the consumption of this tank (flow rate or blowdown history); no fill history.',
    'DEBI_BUTCESI_TUTARSIZ': 'Flow rate × burn time does not give the nominal mass the motor publishes, or exceeds the loaded mass.',
    'TUKETIM_SERISI_TUTARSIZ': 'The blowdown history is not consistent with the published initial liquid, the burn time or itself.',
    'UCUS_KUTLESIYLE_TUTARSIZ': 'The tank masses do not close with the flight mass budget (loaded, consumed, remaining).',
    'TANK_HACMI_YETERSIZ': 'The loaded liquid does not fit into this tank geometry (liquid volume larger than the inner volume).',
    'TANK_GEOMETRISI_RET': 'The tank geometry input was rejected; the reason is shown with it.',
    'TANK_ISTASYONU_VERILMEDI': "The tank's place in the vehicle is not published by the motor or the flight model and was not entered; no position is assumed, the tank is not coupled.",
    'MOTOR_BOYU_YAYIMLANMADI': 'The sequential arrangement needs the motor length, which is neither published nor entered.',
    'TANK_ARAC_DISI': 'The tank lies outside the vehicle length.',
    'TANK_BURUN_ICINDE': 'The top of the tank is inside the nose cone.',
    'TANK_GOVDEDEN_GENIS': 'The tank outer diameter (inner diameter + 2 × the wall the engine publishes) is larger than the body diameter.',
    'TANKLAR_CAKISIYOR': 'Two tanks overlap along the vehicle axis.',
    'TUKETIM_SABIT_DEBI': 'Steady (regulated) feed: the tank drains at a constant flow rate, m(t) = m0 − ṁ·t; for a liquid motor ṁ is the pumped flow (main chamber + turbine/gas generator).',
    'TUKETIM_BOSALMA_COZUMU': "Self-pressurised N₂O tank: the liquid mass comes from the motor's blowdown solution (including the boil-off that keeps the ullage at saturation pressure); vapour does not slosh.",
    'YOGUNLUK_SABIT': 'The liquid density is held at its ignition value during the burn; fill = m/(ρ·V_tank).',
    'YOGUNLUK_BOSALMA_COZUMU': 'Self-pressurised N₂O tank: the liquid density follows the tank temperature of the blowdown solution, ρ_l(T) at step boundaries; fill = m(t)/(ρ(t)·V_tank) (the liquid densifies as the tank cools).',
    'YOGUNLUK_SERISI_TUTARSIZ': 'Not coupled: the liquid density series published by the engine does not match the liquid mass series in length, or its first value is not the ignition density.',
    'BAFL_SONUMU_UYGULANMADI': "The motor's baffle damping is a single full-fill number, not fill-dependent; no extra damping is given to the 6-DOF (conservative).",
    'TANK_ISTASYONU_ARDISIK_DIZILIM': 'The tanks are placed directly ahead of the motor in the given order (when none is given: the engine tank list order, oxidizer forward); each tank takes its inner length plus the two end closure thicknesses the engine publishes, neighbouring closures in contact, no inter-tank bay added (the derived airframe rule).',
    'TANK_ISTASYONU_SIVI_KM_DONUSUMU': 'The entered station is the centre of mass of the loaded liquid; tank bottom = x_CG + z_CG(loaded fill).',
    'YUK_BAGINTISI_DIK_SILINDIR_ICIN': "The load relations (NASA SP-8009 Eq. (4); Dodge 2000 Eq. (3.4b), (3.5)) are for an upright flat-bottom cylinder; this tank's table is not the cylinder closed form, so the loads were not computed.",
    'BAFL_BAGINTISI_DIK_SILINDIR_ICIN': 'The Miles ring-baffle relation (Dodge 2000 Eq. (2.16)) is for an upright cylinder; no baffle recommendation was computed.',
    'YUKLU_DOLULUK_IZGARA_DISI': 'The loaded fill is outside the table grid or that row is rejected; the baffle recommendation could not be made at the loaded fill.',
    'ZAMAN_EKSENI_YOK': "The motor does not publish this tank's consumption or the tank record is inconsistent; no time axis was built (reason in the tank codes).",
    'CEPER_SONUMU_TEK_GEFF_ISTER': "An effective axial acceleration range was given, so ω1 and the wall damping are not written in the time table (κ1 is; ω1 = √(κ1·g_eff) at the user's acceleration).",
}
#: Aktarılan sütunların birimi ve tanımı (EN, TR). Birim yazımı zaman
#: CSV'sinin ``birimler`` sözlüğüyle aynı (ASCII: kg.m2, m3, 1/m).
SUTUN_SOZLUGU = {
    't_s': ('s', 'flight time from ignition', 'ateşlemeden itibaren uçuş zamanı'),
    'doluluk': ('-', 'fill fraction V_liquid/V_internal', 'doluluk oranı V_sıvı/V_iç'),
    'h_m': ('m', 'liquid height above the tank bottom (z = 0)', 'tank tabanından (z = 0) sıvı yüksekliği'),
    'V_sivi_m3': ('m3', 'liquid volume', 'sıvı hacmi'),
    'm_sivi_kg': ('kg', 'liquid mass', 'sıvı kütlesi'),
    'z_km_m': ('m', 'liquid centre of mass, z', 'sıvının kütle merkezi, z'),
    'I_km_donmus_kgm2': ('kg.m2', 'transverse moment of inertia of the frozen liquid about its centre of mass', 'donmuş sıvının kütle merkezi etrafındaki enine eylemsizlik momenti'),
    'I_eksenel_donmus_kgm2': ('kg.m2', 'axial moment of inertia of the frozen liquid', 'donmuş sıvının eksenel eylemsizlik momenti'),
    'A_yuzey_m2': ('m2', 'free-surface area', 'serbest yüzey alanı'),
    'R_yuzey_m': ('m', 'free-surface radius', 'serbest yüzey yarıçapı'),
    'kappa1_1m': ('1/m', 'first-mode frequency parameter κ1 = ω1²/g_eff', 'birinci mod frekans parametresi κ1 = ω1²/g_eff'),
    'L1_m': ('m', 'first-mode pendulum length L1 = 1/κ1', 'birinci mod sarkaç boyu L1 = 1/κ1'),
    'm1_oran': ('-', 'first-mode slosh mass / liquid mass', 'birinci mod çalkantı kütlesi / sıvı kütlesi'),
    'm1_kg': ('kg', 'first-mode slosh mass', 'birinci mod çalkantı kütlesi'),
    'z1_m': ('m', 'first-mode slosh mass position, z', 'birinci mod çalkantı kütlesinin konumu, z'),
    'z_aski_m': ('m', 'pendulum hinge position z1 + L1, z', 'sarkaç askı noktası z1 + L1, z'),
    'm0_oran': ('-', 'fixed (non-sloshing) mass / liquid mass', 'sabit (çalkalanmayan) kütle / sıvı kütlesi'),
    'm0_kg': ('kg', 'fixed (non-sloshing) mass', 'sabit (çalkalanmayan) kütle'),
    'z0_m': ('m', 'fixed mass position, z', 'sabit kütlenin konumu, z'),
    'Gamma1': ('-', 'first-mode amplitude factor Γ1: pendulum displacement x1 = Γ1·η (η wall wave amplitude)', 'birinci mod genlik çarpanı Γ1: sarkaç yer değiştirmesi x1 = Γ1·η (η çeper dalga genliği)'),
    'I0_kgm2': ('kg.m2', 'moment of inertia of the fixed mass', 'sabit kütlenin eylemsizlik momenti'),
    'I0_kaynak': ('-', 'source of I0 (code)', 'I0 kaynağı (kod)'),
    'kappa2_1m': ('1/m', 'second-mode frequency parameter κ2 (information only)', 'ikinci mod frekans parametresi κ2 (yalnız bilgi)'),
    'm2_oran': ('-', 'second-mode slosh mass / liquid mass (information only)', 'ikinci mod çalkantı kütlesi / sıvı kütlesi (yalnız bilgi)'),
    'z2_m': ('m', 'second-mode slosh mass position, z (information only)', 'ikinci mod çalkantı kütlesinin konumu, z (yalnız bilgi)'),
    'omega1_sabit_geff_rad_s': ('rad/s', 'first-mode angular frequency at the single constant g_eff of this table', 'tablonun tek, sabit g_eff değerinde birinci mod açısal frekansı'),
    'f1_sabit_geff_hz': ('Hz', 'first-mode frequency at the single constant g_eff of this table', 'tablonun tek, sabit g_eff değerinde birinci mod frekansı'),
    'zeta_ceper_sabit_geff': ('-', 'smooth-wall damping ratio at the single constant g_eff of this table', 'tablonun tek, sabit g_eff değerinde düz çeper sönüm oranı'),
    'durum': ('-', 'row status code (GECERLI valid, BEYANLI declared, RET rejected)', 'satır durum kodu (GECERLI geçerli, BEYANLI beyanlı, RET reddedildi)'),
    'sebep': ('-', 'reason codes of the row, separated by ;', 'satırın sebep kodları, ; ile ayrılmış'),
    'ek': ('-', 'producer-specific diagnostics (JSON)', 'üreticiye özgü tanı alanları (JSON)'),
}
_DOSYA_ADI = {
    'tr': ('HRMA_calkanti', {'json': '_aktarim.json', 'csv_doluluk': '_doluluk.csv',
                             'csv_zaman': '_zaman.csv'}),
    'en': ('HRMA_slosh', {'json': '_handoff.json', 'csv_doluluk': '_fill.csv',
                          'csv_zaman': '_time.csv'}),
}


def _sozluk_alani(sutunlar, dil):
    """{sütun: {'birim', 'tanim'}} — arayüz dilinde tanım."""
    i = 1 if dil == 'en' else 2
    return {c: {'birim': SUTUN_SOZLUGU[c][0], 'tanim': SUTUN_SOZLUGU[c][i]}
            for c in sutunlar}


def _sozluk_satiri(sutunlar, dil):
    bas = ('Columns (unit; definition): ' if dil == 'en'
           else 'Sütunlar (birim; tanım): ')
    return bas + '; '.join(f'{c} [{SUTUN_SOZLUGU[c][0]}] '
                           f'{SUTUN_SOZLUGU[c][1 if dil == "en" else 2]}'
                           for c in sutunlar)


def _kod_metni(kod, dil):
    if dil == 'en':
        return KOD_METNI_EN.get(kod, kod)
    if kod in K5_KODLARI:
        return K5_KODLARI[kod]
    return (_k4.KODLAR.get(kod) or (None, kod))[1]


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
        r['omega1_sabit_geff_rad_s'] = r['f1_sabit_geff_hz'] = None
        r['zeta_ceper_sabit_geff'] = None
        if g_tek is not None and s.get('kappa1_1m') is not None:
            w = _tablo.omega1(s['kappa1_1m'], g_tek)
            r['omega1_sabit_geff_rad_s'] = w
            r['f1_sabit_geff_hz'] = w / (2.0 * math.pi)
            if silindir and nu is not None and s.get('h_m'):
                r['zeta_ceper_sabit_geff'] = _sa.duz_ceper_sonumu(
                    R, s['h_m'], nu, g_tek)
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


#: 3.0.7 ONARIM-ÇALK (M7-CALK-2): bafl önerisinin tasarım genliğinin künyesi.
BAFL_GENLIK_KAYNAGI = (
    'HRMA seçimi: küçük genlikli tasarım noktası η/R = 0,05 '
    '(slosh_analysis._MILES_DEFAULT_AMPLITUDE_RATIO); Miles bağıntısı '
    '(Dodge 2000 Denk. (2.16)) sönümü √(η/R) ile verir')


#: 3.0.7 ONARIM2-ÇALK-SEKME (M7-CALK-16): motor/tank görünümündeki tek halka
#: önerisinin hedef sönümü ``CylindricalTankSlosh.recommend_baffle``
#: varsayılanıdır (HRMA seçimi, kaynaksız). 6-DOF kararlılık taramasının
#: gereken ζ_min'i bu görünümde yoktur; o hedefle öneri 6-DOF panelindedir
#: (ölçüldü, sıvı örnek LOX: 0,01 ⟷ 0,03063).
BAFL_HEDEF_KAYNAGI = 'HRMA_VARSAYILANI_6DOF_ZETA_MIN_DEGIL'


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
           # 3.0.7 ONARIM-ÇALK (M7-CALK-2): Miles sönümü √(η/R) ile
           # değişir; önerinin dayandığı tasarım genliği adıyla yayımlanır
           # (ekranda ve aktarımda; 6-DOF perde önerisiyle aynı dil).
           'tasarim_genligi_eta_R': oneri['amplitude_ratio'],
           'tasarim_genligi_kaynagi': BAFL_GENLIK_KAYNAGI,
           # 3.0.7 ONARIM2-ÇALK-SEKME (M7-CALK-16): hedef sönümün kaynağı
           # adıyla (HRMA varsayılanı; 6-DOF taramasının ζ_min'i DEĞİL).
           'hedef_sonum_kaynagi': BAFL_HEDEF_KAYNAGI,
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
            'frekans_tanimi': _frekans_tanimi(g_tek),
            'sebep': ([] if g_tek is not None
                      else ['CEPER_SONUMU_TEK_GEFF_ISTER']),
            'satirlar': zaman,
        }
    else:
        out['zaman'] = {'kaynak': None, 'g_eff_m_s2': g_tek,
                        'sebep': ['ZAMAN_EKSENI_YOK'], 'satirlar': []}
    return out, tablo


def _frekans_tanimi(g_tek):
    """Zaman ekseninin frekans tanımı (M7-UCUS-13): kod, g_eff, EN + TR."""
    return {'kod': FREKANS_TANIMI_KODU, 'g_eff_m_s2': g_tek,
            'tanim_en': FREKANS_TANIMI_EN, 'tanim_tr': FREKANS_TANIMI_TR}


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


def _aktarim_kunyesi(gorunum, tank, dil=AKTARIM_DILI_VARSAYILAN):
    en = dil == 'en'
    k = [(f'HRMA {AKTARIM_SEMASI} {AKTARIM_SURUMU}; motor type '
          f'{gorunum["motor_type"]}; tank {tank["tank_id"]} '
          f'({tank["sivi_adi"]})') if en else
         (f'HRMA {AKTARIM_SEMASI} {AKTARIM_SURUMU}; motor türü '
          f'{gorunum["motor_type"]}; tank {tank["tank_id"]} '
          f'({tank["sivi_adi"]})'),
         (f'Method: {tank["yontem"]} (path {tank["tablo_yolu"]})' if en
          else f'Yöntem: {tank["yontem"]} (yol {tank["tablo_yolu"]})'),
         (f'Out of scope ({KAPSAM_DISI_KODU}): {KAPSAM_DISI_GEREKCE}' if en
          else f'Kapsam dışı ({KAPSAM_DISI_KODU}): {KAPSAM_DISI_GEREKCE_TR}'),
         EKSEN_KURALI_EN if en else EKSEN_KURALI,
         K4_KUNYE_EN if en else _k4.KUNYE,
         (f'Density: {tank["rho_kaynagi"]}' if en
          else f'Yoğunluk: {tank["rho_kaynagi"]}')]
    if tank.get('nu_kaynagi'):
        k.append(f'Viscosity: {tank["nu_kaynagi"]}' if en
                 else f'Viskozite: {tank["nu_kaynagi"]}')
    z = tank.get('zaman') or {}
    if z.get('kaynak'):
        k.append(f'm(t): {z["kaynak"]}; time axis = the points of the series '
                 '+ the instants at which the fill crosses the grid nodes '
                 '(series piecewise linear)' if en else
                 f'm(t): {z["kaynak"]}; zaman ekseni serinin noktaları + '
                 'doluluğun ızgara düğümlerini kestiği anlar (seri parça '
                 'parça doğrusal)')
    etiket = (('DECLARATION', 'REASON', 'NOTE') if en
              else ('BEYAN', 'SEBEP', 'NOT'))
    for kod in tank['beyan']:
        k.append(f'{etiket[0]} {kod}: {_kod_metni(kod, dil)}')
    for kod in tank['sebep']:
        k.append(f'{etiket[1]} {kod}: {_kod_metni(kod, dil)}')
    for kod in z.get('sebep') or []:
        k.append(f'{etiket[2]} {kod}: {_kod_metni(kod, dil)}')
    b = tank.get('bafl') or {}
    if b.get('durum') == 'HESAPLANDI':
        z = (b.get('oneri') or {}).get('target_damping_ratio')
        k.append((f'Ring-baffle recommendation target damping ζ = {z}: HRMA '
                  'default; it is NOT the ζ_min the 6-DOF stability scan '
                  'requires (the recommendation for that target is in the '
                  '6-DOF panel, Stability — slosh subsection)') if en else
                 (f'Halka perde önerisinin hedef sönümü ζ = '
                  f'{str(z).replace(".", ",")}: HRMA '
                  'varsayılanı; 6-DOF kararlılık taramasının gereken ζ_min '
                  'değeri DEĞİLDİR (o hedefle öneri 6-DOF panelinde, '
                  'Kararlılık — çalkantı alt bölümünde)'))
    gd = tank.get('geometri_dosyasi')
    if gd:
        k.append(('Tank geometry file: ' if en
                  else 'Tank geometrisi dosyası: ')
                 + f'{gd.get("dosya_adi", "-")} (sha256 {gd.get("sha256", "-")})')
    return k


def _tablo_kunyeli(tablo, ek, dil=AKTARIM_DILI_VARSAYILAN):
    v = tablo.sozluk()
    kendi = list(v.get('kunye', []))
    if dil == 'en':
        kendi = [_en_kunye(s) for s in kendi]
    v['kunye'] = kendi + list(ek)
    return _tablo.SloshTablo.sozlukten(v)


def disa_aktarim(gorunum, tablolar, tank_id, bicim,
                 dil=AKTARIM_DILI_VARSAYILAN):
    """(dosya adı, MIME türü, metin). Dosya sözleşme okuyucusuyla geri
    okunabilir: JSON'daki tablo ``slosh_tablo.dogrula``dan, doluluk CSV'si
    ``slosh_tablo.csv_oku``dan geçer."""
    if bicim not in DISA_AKTARIM_BICIMLERI:
        _ret('BICIM', 'disa_aktarim.bicim',
             f'must be one of {DISA_AKTARIM_BICIMLERI}')
    if dil not in AKTARIM_DILLERI:
        _ret('BICIM', 'disa_aktarim.dil', f'must be one of {AKTARIM_DILLERI}')
    tank = next((t for t in gorunum['tanklar'] if t['tank_id'] == tank_id),
                None)
    if tank is None or tank_id not in tablolar:
        _ret('TANK_TABLOSU_YOK', 'disa_aktarim.tank_id',
             'no equivalent-model table was computed for this tank')
    # Tablonun meta nesnesi sözleşmenindir (bilinmeyen alan yok): eşdeğer
    # model tablosunun sütun sözlüğü künyede tek satır (üç biçimde aynı
    # künye; doluluk CSV'si ile JSON'daki tablo aynı kalır).
    kunye = _aktarim_kunyesi(gorunum, tank, dil) + [
        _sozluk_satiri(_tablo.SATIR_SUTUNLARI, dil)]
    if dil == 'en':
        kunye = [_en_kunye(s) for s in kunye]
    on_ek, sonek = _DOSYA_ADI[dil]
    ad = f'{on_ek}_{gorunum["motor_type"]}_{tank_id}'
    zaman = tank['zaman'] or {}
    tablo = _tablo_kunyeli(tablolar[tank_id], kunye, dil)
    if bicim == 'csv_doluluk':
        return ad + sonek[bicim], 'text/csv', _tablo.csv_yaz(tablo)
    zaman_sutunlari = [c for c, _ in ZAMAN_SUTUNLARI]
    if bicim == 'csv_zaman':
        meta = {'sema': AKTARIM_SEMASI, 'sema_surumu': AKTARIM_SURUMU,
                'tank_id': tank_id, 'motor_type': gorunum['motor_type'],
                'g_eff_m_s2': zaman.get('g_eff_m_s2'),
                'frekans_tanimi': _frekans_tanimi(zaman.get('g_eff_m_s2')),
                'birimler': dict(ZAMAN_SUTUNLARI),
                'tanimlar': {c: v['tanim'] for c, v in _sozluk_alani(
                    zaman_sutunlari, dil).items()},
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
        return ad + sonek[bicim], 'text/csv', tampon.getvalue()
    paket = {
        'sema': AKTARIM_SEMASI, 'sema_surumu': AKTARIM_SURUMU,
        'motor_type': gorunum['motor_type'], 'tank_id': tank_id,
        'kunye': kunye, 'beyan': list(tank['beyan']),
        'sebep': list(tank['sebep']),
        'kapsam_disi': dict(gorunum['kapsam_disi'], gerekce=(
            KAPSAM_DISI_GEREKCE if dil == 'en' else KAPSAM_DISI_GEREKCE_TR)),
        'dil': dil,
        'esdeger_model_tablosu': tablo.sozluk(),
        'esdeger_model_sutunlari': _sozluk_alani(_tablo.SATIR_SUTUNLARI, dil),
        # 3.0.7 ONARIM-ÇALK (M7-CALK-2): halka perde önerisi tasarım genliğiyle
        # (aktarımda da; ekranla aynı sayılar).
        'bafl_onerisi': tank.get('bafl'),
        'zaman_ekseni': {
            'g_eff_m_s2': zaman.get('g_eff_m_s2'),
            'frekans_tanimi': _frekans_tanimi(zaman.get('g_eff_m_s2')),
            'kaynak': (_en_kunye(zaman.get('kaynak')) if dil == 'en'
                       else zaman.get('kaynak')),
            'sebep': list(zaman.get('sebep') or []),
            'birimler': dict(ZAMAN_SUTUNLARI),
            'tanimlar': {c: v['tanim'] for c, v in _sozluk_alani(
                zaman_sutunlari, dil).items()},
            'satirlar': zaman.get('satirlar') or [],
        },
    }
    metin = json.dumps(paket, ensure_ascii=False, allow_nan=False, indent=1)
    return ad + sonek['json'], 'application/json', metin
