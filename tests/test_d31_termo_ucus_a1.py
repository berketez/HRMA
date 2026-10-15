# -*- coding: utf-8 -*-
"""ÖH Dalga-31 / termo-ucus a1 bekçileri.

Kalem: **P12bB4-06** (KİLİDİ AÇILAN, Berke 14 Eyl 2026) — soğutucu tarafı
film katsayısı korelasyon yerine SABİT döndürüyordu.

ÖLÇÜLEN KUSUR (``docs/scofield/raw/OH/D31/termo-ucus/a1/once_p12bb406.json``,
taban 9d70e9ed): dört ayrı soğutma kanalı tasarımında (64x2x3 mm su 1 kg/s,
16x6x6 mm su 1 kg/s, aynı dar kanalda 8 kg/s, RP-1 40x3x4 mm 3 kg/s) ürünün
döndürdüğü katsayı 20.000 W/m²K'de SABİT kalıyordu; aynı girdilerde
Dittus-Boelter 6.639,7 - 77.412,6 W/m²K veriyor (11,66x yayılım) ve cidar iç
sıcaklığı dört tasarımda da 1062,03 K çıkıyordu. ``/formulas`` §5.3 ise
okuyucuya ``h = 0,023 (k/D) Re^0,8 Pr^0,4`` kutusunu gösteriyordu.

ONARIM: ``_coolant_side_resolution`` üç yolu da künyeliyor —
``user_supplied`` / ``dittus_boelter`` (kanal girdileri varsa GERÇEK hesap) /
``not_modelled`` (girdiler yoksa beyan edilen tipik bant, eksik alanlar
adıyla). Korelasyon, Nusselt ve geçerlilik zarfı kardeş ``regen_cooling``
modülünün TEK kaynağından ithal edilir.

Kaynaklar: Incropera & DeWitt, "Fundamentals of Heat and Mass Transfer",
6. bs. Eq. 8.60 (Dittus-Boelter) ve Tablo 1.1 (taşınım bantları);
Huzel & Huang, AIAA Vol. 147, Böl. 4 (rejeneratif kanal bandı).
"""
import os
import re

import pytest

from hrma.analysis.heat_transfer_analysis import (
    COOLANT_CHANNEL_REQUIRED_FIELDS,
    COOLANT_SIDE_DECLARED_SOURCE,
    COOLANT_SIDE_DECLARED_TYPICAL,
    HeatTransferAnalyzer,
)
from hrma.analysis.regen_cooling import (
    canonical_coolant_name,
    hydraulic_diameter_rect,
    rp1_properties,
    water_properties,
)

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MOTOR = dict(chamber_pressure=20.0, chamber_temperature=3200.0,
             chamber_diameter=0.15, chamber_length=0.30, burn_time=10.0,
             throat_diameter=0.050, mdot_total=4.0, gamma=1.20,
             molecular_weight=24.0)

KANAL_DAR = dict(n_channels=64, channel_width=2.0e-3, channel_height=3.0e-3,
                 coolant='water', coolant_mdot=1.0, coolant_inlet_temp=300.0)
KANAL_GENIS = dict(n_channels=16, channel_width=6.0e-3, channel_height=6.0e-3,
                   coolant='water', coolant_mdot=1.0, coolant_inlet_temp=300.0)
KANAL_HIZLI = dict(KANAL_DAR, coolant_mdot=8.0)
KANAL_RP1 = dict(n_channels=40, channel_width=3.0e-3, channel_height=4.0e-3,
                 coolant='rp1', coolant_mdot=3.0, coolant_inlet_temp=300.0)

KANALLAR_DORT = (KANAL_DAR, KANAL_GENIS, KANAL_HIZLI, KANAL_RP1)


def _motor(kanal=None):
    md = dict(MOTOR)
    if kanal:
        md.update(kanal)
    return md


def _bagimsiz_dittus_boelter(kanal):
    """Bağımsız ikinci yol: korelasyonu bu dosyada elden kur.

        D_h = 2wh/(w+h);  G = (mdot/N)/(wh);  Re = G D_h/mu
        Pr  = cp mu / k;  Nu = 0,023 Re^0,8 Pr^0,4;  h = Nu k / D_h

    Ürün kodunun yardımcılarını ÇAĞIRMAZ (yalnız özellik tablosunu okur),
    böylece ürünün kendi aritmetiğini kendi kendine doğrulaması engellenir.
    """
    w, h = kanal['channel_width'], kanal['channel_height']
    d_h = 2.0 * w * h / (w + h)
    p = (water_properties(kanal['coolant_inlet_temp'])
         if canonical_coolant_name(kanal['coolant']) == 'water'
         else rp1_properties(kanal['coolant_inlet_temp']))
    g = (kanal['coolant_mdot'] / kanal['n_channels']) / (w * h)
    re = g * d_h / p['viscosity']
    pr = p['cp'] * p['viscosity'] / p['conductivity']
    nu = 0.023 * re ** 0.8 * pr ** 0.4
    return nu * p['conductivity'] / d_h, re, pr


# ---------------------------------------------------------------------------
# 1) Kanal tasarımı sonuca GİRİYOR (kusurun kendisi)
# ---------------------------------------------------------------------------

def test_p12bb406_kanal_tasarimi_katsayiya_giriyor():
    """Dört ayrı kanal tasarımı dört AYRI katsayı vermeli (taban: tek değer)."""
    a = HeatTransferAnalyzer()
    degerler = [a._coolant_side_coefficient(_motor(k), 'regenerative')
                for k in KANALLAR_DORT]
    assert len(set(round(v, 6) for v in degerler)) == 4, (
        'soğutucu tarafı hâlâ kanal tasarımına duyarsız: '
        f'{sorted(round(v, 3) for v in degerler)}')
    # Hiçbiri eski sabit değil.
    assert all(abs(v - COOLANT_SIDE_DECLARED_TYPICAL['regenerative']) > 1.0
               for v in degerler), (
        'kanal girdileri verilmesine rağmen beyan edilen bant dönüyor')


def test_p12bb406_deger_literatur_korelasyonuyla_ayni():
    """Ürünün sayısı, bu dosyada elden kurulan Dittus-Boelter ile aynı olmalı."""
    a = HeatTransferAnalyzer()
    for kanal in KANALLAR_DORT:
        urun = a._coolant_side_coefficient(_motor(kanal), 'regenerative')
        ref, _re, _pr = _bagimsiz_dittus_boelter(kanal)
        assert abs(urun - ref) <= 1e-9 * ref, (
            f'{kanal["coolant"]} kanalında ürün {urun:.6f} != '
            f'bağımsız Dittus-Boelter {ref:.6f}')


def test_p12bb406_kunye_dittus_boelter_ve_kaynak():
    """Künye: yöntem adı, literatür kaynağı, Re/Pr/D_h yayımlanmalı."""
    a = HeatTransferAnalyzer()
    coz = a._coolant_side_resolution(_motor(KANAL_DAR), 'regenerative')
    assert coz['method'] == 'dittus_boelter'
    assert 'Incropera' in coz['source'] and '8.60' in coz['source']
    ayrinti = coz['detail']
    ref, re_ref, pr_ref = _bagimsiz_dittus_boelter(KANAL_DAR)
    assert abs(ayrinti['reynolds_number'] - re_ref) <= 1e-9 * re_ref
    assert abs(ayrinti['prandtl_number'] - pr_ref) <= 1e-9 * pr_ref
    assert abs(ayrinti['hydraulic_diameter_m']
               - hydraulic_diameter_rect(KANAL_DAR['channel_width'],
                                         KANAL_DAR['channel_height'])) < 1e-15
    assert coz['missing_fields'] == []


# ---------------------------------------------------------------------------
# 2) ÖLÇEK YASASI — korelasyonun üslerinin analitik doğrulaması
# ---------------------------------------------------------------------------

def test_p12bb406_olcek_yasasi_debi_ussu_0_8():
    """Sabit geometri/akışkanda h ~ mdot^0,8 (Nu ~ Re^0,8, Re ~ mdot).

    Taban ölçümü (once_p12bb406.json K6): oran 1,0 — yani hiçbir ölçek
    yasası yoktu (bağıl hata %42,6).
    """
    a = HeatTransferAnalyzer()
    h1 = a._coolant_side_coefficient(_motor(KANAL_DAR), 'regenerative')
    h2 = a._coolant_side_coefficient(
        _motor(dict(KANAL_DAR, coolant_mdot=2.0 * KANAL_DAR['coolant_mdot'])),
        'regenerative')
    beklenen = 2.0 ** 0.8
    assert abs(h2 / h1 - beklenen) <= 1e-12 * beklenen, (
        f'debi iki katına çıkınca oran {h2 / h1:.9f}, beklenen {beklenen:.9f}')


def test_p12bb406_olcek_yasasi_kanal_boyu_ussu_eksi_1_8():
    """Kare kanalda, kanal başına debi sabitken h ~ a^(-1,8).

    a kenarlı kare kanal: D_h = a, A = a², G = mdot_kanal/a²,
    Re = mdot_kanal/(a mu) => h = 0,023 k Pr^0,4 (mdot_kanal/mu)^0,8 a^(-1,8).
    """
    a_hta = HeatTransferAnalyzer()
    kucuk = dict(n_channels=1, channel_width=3.0e-3, channel_height=3.0e-3,
                 coolant='water', coolant_mdot=0.05, coolant_inlet_temp=300.0)
    buyuk = dict(kucuk, channel_width=6.0e-3, channel_height=6.0e-3)
    h1 = a_hta._coolant_side_coefficient(_motor(kucuk), 'regenerative')
    h2 = a_hta._coolant_side_coefficient(_motor(buyuk), 'regenerative')
    beklenen = 2.0 ** (-1.8)
    assert abs(h2 / h1 - beklenen) <= 1e-12, (
        f'kanal kenarı iki katına çıkınca oran {h2 / h1:.9f}, '
        f'beklenen {beklenen:.9f}')


# ---------------------------------------------------------------------------
# 3) ÜRÜN YOLU — cidar sıcaklığı kanal tasarımına duyarlı
# ---------------------------------------------------------------------------

def test_p12bb406_cidar_sicakligi_kanal_tasarimina_duyarli():
    """analyze_heat_transfer: dört tasarım dört AYRI cidar sıcaklığı.

    Taban: dördü de 1062,028051837206 K idi (once_p12bb406.json K3).
    """
    a = HeatTransferAnalyzer()
    sicakliklar = []
    for kanal in KANALLAR_DORT:
        r = a.analyze_heat_transfer(_motor(kanal), material='copper',
                                    wall_thickness=0.002, ambient_temp=300.0,
                                    cooling_type='regenerative')
        sicakliklar.append(r['wall_analysis']['inner_temperature'])
    assert len(set(round(t, 6) for t in sicakliklar)) == 4, (
        f'cidar sıcaklığı hâlâ kanaldan bağımsız: {sicakliklar}')
    assert all(abs(t - 1062.028051837206) > 1e-3 for t in sicakliklar), (
        'taban sabitinin ürettiği 1062,03 K hâlâ dönüyor')


def test_p12bb406_eksenel_profil_bogazla_ayni_tek_tanim():
    """Eksenel profil ile boğaz analizi AYNI soğutucu katsayısını okumalı."""
    a = HeatTransferAnalyzer()
    md = _motor(KANAL_GENIS)
    bogaz = a.analyze_heat_transfer(md, material='copper',
                                    wall_thickness=0.002, ambient_temp=300.0,
                                    cooling_type='regenerative')
    eksen = a.analyze_axial_profile(md, n_stations=12, material='copper',
                                    wall_thickness=0.002, ambient_temp=300.0,
                                    cooling_type='regenerative')
    h_bogaz = bogaz['heat_transfer_coefficients']['coolant_side']
    assert bogaz['heat_transfer_coefficients']['coolant_side_method'] == \
        'dittus_boelter'
    # Eksen bloğu künye YAYIMLAMAZ (ters-yön borcu: bu bloğu panel tek tek
    # okumuyor). Aynı tek tanımı okuduğu EŞDEĞERLİKLE ölçülür: kanal
    # girdileriyle kurulan profil, aynı h'nin elle verildiği profille
    # BİT-AYNI olmalı.
    md_elden = _motor()
    md_elden['coolant_side_coefficient'] = h_bogaz
    eksen_elden = a.analyze_axial_profile(
        md_elden, n_stations=12, material='copper', wall_thickness=0.002,
        ambient_temp=300.0, cooling_type='regenerative')
    assert eksen['T_wall_eq'] == eksen_elden['T_wall_eq'], (
        'eksenel profil boğaz analiziyle aynı soğutucu katsayısını okumuyor')
    # ... ve kanal tasarımı değişince eksen de değişmeli (sabit değil).
    eksen_dar = a.analyze_axial_profile(
        _motor(KANAL_DAR), n_stations=12, material='copper',
        wall_thickness=0.002, ambient_temp=300.0,
        cooling_type='regenerative')
    assert eksen_dar['T_wall_eq'] != eksen['T_wall_eq']


def test_p12bb406_sogutma_alani_kunyeli():
    """Gereken soğutma alanı h ile bölünüyor; h'nin kökeni yanında olmalı."""
    a = HeatTransferAnalyzer()
    r = a.analyze_heat_transfer(_motor(KANAL_DAR), material='copper',
                                wall_thickness=0.002, ambient_temp=300.0,
                                cooling_type='regenerative')
    soguma = r['cooling_analysis']
    assert soguma['coolant_side_coefficient_method'] == 'dittus_boelter'
    assert 'Incropera' in soguma['coolant_side_coefficient_source']


# ---------------------------------------------------------------------------
# 4) FAIL-CLOSED — girdisiz hâl KORELASYON DİYE YAYIMLANAMAZ
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('sogutma', sorted(COOLANT_SIDE_DECLARED_TYPICAL))
def test_p12bb406_kanalsiz_hal_not_modelled_kunyeli(sogutma):
    """Kanal girdisi yoksa: beyan edilen bant + 'not_modelled' + eksik alanlar."""
    a = HeatTransferAnalyzer()
    coz = a._coolant_side_resolution(_motor(), sogutma)
    assert coz['method'] == 'not_modelled'
    assert coz['value'] == COOLANT_SIDE_DECLARED_TYPICAL[sogutma]
    assert coz['source'] == COOLANT_SIDE_DECLARED_SOURCE
    assert 'NOT a correlation' in coz['source']
    assert coz['missing_fields'], 'eksik alanlar adıyla söylenmiyor'


def test_p12bb406_kanalsiz_eksik_alanlar_adiyla():
    """Rejeneratifte eksik alan listesi kanal alanlarının TAMAMINI anmalı."""
    a = HeatTransferAnalyzer()
    coz = a._coolant_side_resolution(_motor(), 'regenerative')
    for alan in COOLANT_CHANNEL_REQUIRED_FIELDS:
        assert any(alan in e for e in coz['missing_fields']), (
            f'eksik alan listesi {alan} alanını anmıyor: {coz["missing_fields"]}')


def test_p12bb406_kanalsiz_hal_uc_cikti_kunyeli():
    """Üç yayın noktası da (boğaz, eksen, soğutma) not_modelled demeli."""
    a = HeatTransferAnalyzer()
    md = _motor()
    r = a.analyze_heat_transfer(md, material='copper', wall_thickness=0.002,
                                ambient_temp=300.0,
                                cooling_type='regenerative')
    kats = r['heat_transfer_coefficients']
    assert kats['coolant_side_method'] == 'not_modelled'
    assert kats['coolant_side_missing_fields']
    assert r['cooling_analysis']['coolant_side_coefficient_method'] == \
        'not_modelled'
    # Eksen bloğu künye yayımlamaz (ters-yön sözleşmesi); aynı tek tanımı
    # okuduğu, beyan edilen bandın elle verilmesiyle BİT-AYNI çıkmasıyla
    # ölçülür.
    eksen = a.analyze_axial_profile(md, n_stations=12, material='copper',
                                    wall_thickness=0.002, ambient_temp=300.0,
                                    cooling_type='regenerative')
    md_elden = dict(md)
    md_elden['coolant_side_coefficient'] = \
        COOLANT_SIDE_DECLARED_TYPICAL['regenerative']
    eksen_elden = a.analyze_axial_profile(
        md_elden, n_stations=12, material='copper', wall_thickness=0.002,
        ambient_temp=300.0, cooling_type='regenerative')
    assert eksen['T_wall_eq'] == eksen_elden['T_wall_eq']


def test_p12bb406_kritik_ustu_sogutucu_sayi_uydurmaz():
    """Metan/hidrojen kanalında Dittus-Boelter KOŞTURULMAZ (Jackson gerekir)."""
    a = HeatTransferAnalyzer()
    for akiskan in ('methane', 'LH2'):
        kanal = dict(KANAL_DAR, coolant=akiskan)
        coz = a._coolant_side_resolution(_motor(kanal), 'regenerative')
        assert coz['method'] == 'not_modelled', (
            f'{akiskan} için kritik-üstü akışkana Dittus-Boelter uygulanmış')
        assert any('regen_cooling' in e or 'Jackson' in e
                   for e in coz['missing_fields']), (
            f'{akiskan} reddi doğru çözücüyü adıyla göstermiyor: '
            f'{coz["missing_fields"]}')


def test_p12bb406_bozuk_girdi_sayi_uretmez():
    """Sıfır/negatif/metin kanal girdisi sessizce korelasyona sokulmaz."""
    a = HeatTransferAnalyzer()
    for bozuk in ({'n_channels': 0}, {'channel_width': -1e-3},
                  {'coolant_mdot': 'çok'}, {'channel_height': float('nan')}):
        kanal = dict(KANAL_DAR)
        kanal.update(bozuk)
        coz = a._coolant_side_resolution(_motor(kanal), 'regenerative')
        assert coz['method'] == 'not_modelled', f'{bozuk} girdisi kabul edildi'
        assert coz['missing_fields']


def test_p12bb406_dogal_zorlanmis_kanal_korelasyonuna_girmez():
    """Kanal girdileri verilse bile natural/forced kanal korelasyonu DEĞİLDİR."""
    a = HeatTransferAnalyzer()
    for sogutma in ('natural', 'forced'):
        coz = a._coolant_side_resolution(_motor(KANAL_DAR), sogutma)
        assert coz['method'] == 'not_modelled'
        assert coz['value'] == COOLANT_SIDE_DECLARED_TYPICAL[sogutma]


def test_p12bb406_kullanici_degeri_kunyeli_kazanir():
    """Çağıranın verdiği katsayı aynen döner ve 'user_supplied' künyelenir."""
    a = HeatTransferAnalyzer()
    md = _motor(KANAL_DAR)
    md['coolant_side_coefficient'] = 12345.0
    coz = a._coolant_side_resolution(md, 'regenerative')
    assert coz['value'] == 12345.0
    assert coz['method'] == 'user_supplied'


# ---------------------------------------------------------------------------
# 5) GEÇERLİLİK ZARFI — ihlal gömülmez
# ---------------------------------------------------------------------------

def test_p12bb406_zarf_ihlali_ust_duzeyde_yayimlanir():
    """Re < 1e4 olan kanalda ihlal adıyla yayımlanmalı (taban: Re=7309,94)."""
    a = HeatTransferAnalyzer()
    _h, re_dar, _pr = _bagimsiz_dittus_boelter(KANAL_DAR)
    assert re_dar < 1.0e4, 'ölçüm bayatlamış: dar kanal artık türbülan bantta'
    r = a.analyze_heat_transfer(_motor(KANAL_DAR), material='copper',
                                wall_thickness=0.002, ambient_temp=300.0,
                                cooling_type='regenerative')
    kats = r['heat_transfer_coefficients']
    ihlaller = kats.get('coolant_side_envelope_violations')
    assert ihlaller, 'zarf ihlali yayımlanmıyor'
    assert any('Re' in i for i in ihlaller)
    assert kats['coolant_side_detail']['envelope']['in_envelope'] is False
    assert kats['coolant_side_detail']['envelope']['scatter_pct'] == 25.0


def test_p12bb406_zarf_ici_kanalda_ihlal_yayimlanmaz():
    """Türbülan bantta ihlal listesi hiç yayımlanmamalı (gürültü yok)."""
    a = HeatTransferAnalyzer()
    r = a.analyze_heat_transfer(_motor(KANAL_HIZLI), material='copper',
                                wall_thickness=0.002, ambient_temp=300.0,
                                cooling_type='regenerative')
    kats = r['heat_transfer_coefficients']
    assert 'coolant_side_envelope_violations' not in kats
    assert kats['coolant_side_detail']['envelope']['in_envelope'] is True


# ---------------------------------------------------------------------------
# 6) TEK KAYNAK
# ---------------------------------------------------------------------------

def test_p12bb406_bant_sayilari_tek_kaynakta():
    """25 / 100 / 20000 sayıları modülde yalnız tek tanımda geçmeli."""
    yol = os.path.join(KOK, 'hrma', 'analysis', 'heat_transfer_analysis.py')
    with open(yol, encoding='utf-8') as f:
        metin = f.read()
    # Yorum satırları ölçüme girmez (gerekçe metinleri sayıyı anar).
    kod = '\n'.join(s for s in metin.splitlines()
                    if not s.lstrip().startswith('#'))
    assert kod.count('COOLANT_SIDE_DECLARED_TYPICAL = {') == 1
    for sayi in ('20000.0', '25.0'):
        assert kod.count(sayi) == 1, (
            f'{sayi} kodda {kod.count(sayi)} kez geçiyor — tek kaynak kuralı')
    # Soğutucu-tarafı çözümünün GÖVDESİNDE hiçbir bant sayısı yazılı olmamalı
    # (100.0 modülün başka yerlerinde birim dönüşümü olarak geçiyor, o yüzden
    # sayım değil GÖVDE ölçülür).
    govde = re.search(r'def _coolant_side_coefficient.*?def _mach_from_area_ratio',
                      kod, re.S)
    assert govde, 'soğutucu tarafı gövdesi bulunamadı'
    for sayi in ('20000', '100.0', '25.0'):
        assert sayi not in govde.group(0), (
            f'{sayi} soğutucu tarafı gövdesine geri yazılmış')


def test_p12bb406_korelasyon_kardes_modulden_ithal():
    """Dittus-Boelter ikinci kez YAZILMAZ; regen_cooling'den ithal edilir."""
    yol = os.path.join(KOK, 'hrma', 'analysis', 'heat_transfer_analysis.py')
    with open(yol, encoding='utf-8') as f:
        metin = f.read()
    assert 'from hrma.analysis.regen_cooling import' in metin
    for ad in ('dittus_boelter_nu', 'dittus_boelter_envelope',
               'hydraulic_diameter_rect', 'canonical_coolant_name'):
        assert ad in metin, f'{ad} ithal edilmiyor'
    # Korelasyonun katsayısı bu dosyada YENİDEN HESAPLANMAMALI: sayı yalnız
    # kaynak künyesinin metninde (belgeleme) geçebilir, aritmetikte değil.
    assert not re.search(r'0\.023\s*\*', metin), (
        'Dittus-Boelter katsayısı bu modülde ikinci kez hesaplanıyor')


def test_p12bb406_sogutucu_adi_tek_kuralla_cozulur():
    """Soğutucu eşanlamlıları iki modülde iki ayrı listede tutulmaz."""
    yol = os.path.join(KOK, 'hrma', 'analysis', 'heat_transfer_analysis.py')
    with open(yol, encoding='utf-8') as f:
        metin = f.read()
    assert "'kerosene'" not in metin, (
        'soğutucu eşanlamlı listesi ısı-transferi modülüne kopyalanmış')
    assert canonical_coolant_name('LCH4') == 'methane'
    assert canonical_coolant_name('H2O') == 'water'
    assert canonical_coolant_name('sirke') is None


# ---------------------------------------------------------------------------
# 7) SAYFA ⟷ ÜRÜN (P12bB4-06 şablon ayağının D31 devamı)
# ---------------------------------------------------------------------------

def test_p12bb406_formulas_beyani_urun_sozlesmesini_anlatiyor():
    """/formulas §5.3 notu, ürünün BUGÜNKÜ sözleşmesini anlatmalı."""
    yol = os.path.join(KOK, 'hrma', 'templates', 'formulas.html')
    with open(yol, encoding='utf-8') as f:
        metin = f.read()
    # ÖH D37 taban-onarım: D36 kabuk-elle (d1d81989, OH-K-01..05) HTML
    # taşıyan beyan düğümüne `data-i18n-html` işaretini ekledi (i18n.js
    # onu innerHTML ile yazar); açılış etiketi artık
    # `data-i18n="…" data-i18n-html>`. YALNIZ bu öznitelik isteğe bağlı
    # kabul edilir — desen başka hiçbir şeye gevşemez.
    m = re.search(r'data-i18n="fx\.s5_3\.model_note"(?: data-i18n-html)?>'
                  r'(.*?)</span>', metin, re.S)
    assert m, '§5.3 model farkı beyanı yok'
    beyan = m.group(1)
    assert 'dittus_boelter' in beyan and 'not_modelled' in beyan
    for alan in ('n_channels', 'channel_width', 'coolant_mdot'):
        assert alan in beyan, f'beyan {alan} alanını anmıyor'
    # Eski (artık yanlış) cümle kalmamalı.
    assert 'does <em>not</em> evaluate it' not in beyan, (
        'sayfa hâlâ "çözücü bu bağıntıyı değerlendirmiyor" diyor')


# ---------------------------------------------------------------------------
# 8) P15B2-01 (OH-D30-08 dağıtımı) — yerel değer kapısı merkeze bağlandı
# ---------------------------------------------------------------------------

def test_p15b201_barrel_length_merkez_kapiya_bagli():
    """``RegenCooling._barrel_length_mm`` merkez kapıyı kullanmalı.

    Borç (p15b201_dagitim.json, termo-ucus satırı): yerel DEĞER kapısı
    ``hrma.utils.input_guard`` merkezine bağlı değildi. Eski gövde yalnız
    Python ``bool``unu eliyordu; ``numpy.bool_`` alt sınıf OLMADIĞI için
    ``float(np.True_) == 1.0`` üzerinden 1000,0 mm'lik bir kamara gövdesi
    üretiyordu.
    """
    import numpy as np

    from hrma.analysis.regen_cooling import RegenCooling

    r = RegenCooling(chamber_pressure=30.0e5, chamber_temperature=3200.0,
                     throat_diameter=0.05, expansion_ratio=8.0,
                     coolant='water', coolant_mdot=1.0)
    # Geçerli değer: metre -> milimetre.
    r.motor_data = {'chamber_length': 0.30}
    assert r._barrel_length_mm() == pytest.approx(300.0)
    # Çözülemeyen değerler gövde ÜRETMEZ.
    for kotu in (None, 'çok', float('nan'), float('inf'), 0.0, -0.2,
                 True, np.bool_(True), np.bool_(False)):
        r.motor_data = {'chamber_length': kotu}
        assert r._barrel_length_mm() == 0.0, (
            f'{kotu!r} girdisinden kamara gövdesi uyduruldu')


def test_p15b201_merkez_kapi_ithal_ediliyor():
    """Kapı merkeze BAĞLI: modül ``input_guard``ı ithal etmeli."""
    yol = os.path.join(KOK, 'hrma', 'analysis', 'regen_cooling.py')
    with open(yol, encoding='utf-8') as f:
        metin = f.read()
    assert 'from hrma.utils import input_guard' in metin
    govde = re.search(r'def _barrel_length_mm.*?\n    @', metin, re.S)
    assert govde, '_barrel_length_mm gövdesi bulunamadı'
    assert 'input_guard.finite_positive' in govde.group(0), (
        'kapı hâlâ yerel kuralla çalışıyor'
    )
