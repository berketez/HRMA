# -*- coding: utf-8 -*-
"""ÖH Dalga-16 · kulvar bekci-cevirisi · aşama 1/1 — bekçi bekçileri.

Bu dosya ÜRÜN davranışını değil, BEKÇİLERİN KENDİSİNİ savunur: bir
muafiyet gerekçesinin doğruluğunu, bir çiziminin delik sayısı kanalını,
kapanmış kalemlerin kalıcı kilidini.

Her iddia, savunduğu kusuru gördüğü TERS MUTASYONLA kırmızıya düştüğü
ölçülerek doğrulanmıştır (kanıt:
``docs/scofield/raw/OH/D16/bekci-cevirisi/a1/mutasyon.json``).

Kalemler: OH-B4-07 (ters-yön muafiyet gerekçelerinin makineyle sınanması),
P14M3-02 (motor kesitindeki delik sayısı kanalı), OH-Z4-02 (Z4 bekçi
borçlarının bir bölümü).
"""

import importlib
import json
import re
from pathlib import Path

import pytest


KOK = Path(__file__).resolve().parent.parent
JS_KOK = KOK / 'hrma' / 'static' / 'js'
TESTS_KOK = KOK / 'tests'


# ===========================================================================
# OH-B4-07 — ters-yön muafiyet GEREKÇELERİ makineyle sınanır
# ===========================================================================
#
# Ölçülen kusur (ÖNCE, `once_ohb407.json`): üç sözleşme dosyasındaki
# TERS_MUAFIYET tablolarında BEŞ satırın gerekçesi BAYAT'tı — gerekçe
# "panel `X` basıyor" derken `X` panelin okuma envanterinde HİÇ yoktu —
# ve BİR satır (alıntılanan `material`) çürütülmüş bir iddiayı canlı
# iddia gibi taşıyordu:
#
#     wave3  transient/mdot_fuel            -> `mdot_total`
#     wave3  vessel/head_margin             -> `head_thickness_selected_mm`
#     wave3  structural/safety_factor_pressure
#                                           -> `safety_factor_analysis.…`
#     wave4b cooling/summary/total_heat_W   -> `total_heat_kW`
#     wave4b feed/slosh/omega1              -> `f1`
#     wave3  safety/structural_safety       -> alıntılanan `material`
#                                              (sınıflandırıcı kusuru)
#
# D18 DÜZELTMESİ (Fable-D16 ŞART, madde 2): bu liste eskiden ALTI bayat
# satır sayıyordu ve iki kalemi yanlıştı. `cooling/ust/channel_area_mm2`
# ÇÜRÜTÜLDÜ — `channel_width`/`channel_height` cooling_panel.js:306-307'de
# FORM ALANI olarak vardır; eski ölçüm yanlış ölçüte (yanıt okuma
# envanteri) bakmıştı. `flow/losses/method` ise bayat değildi, o gün hiç
# SINIFLANDIRILMIYORDU (olumsuz cümle); gerçekten düzeltilen satır
# `flow/losses/friction_loss_fraction`tı (`_source` kısaltması).
#
# Gerekçe bir BEYANDIR; beyan ölçülmüyorsa muafiyet dilekçeye döner.
# Aşağıdaki iddia, gerekçenin kendisini panelin kaynağına karşı sınar.
#
# SINIFLANDIRMA KURALI (bilerek dar ve denetlenebilir): bir gerekçedeki
# ters-tırnaklı ad ancak "panel …" öbeğine YAKIN durduğunda (aynı cümlecik,
# en fazla 40 karakter) ya da "kullanıcıdan gelen girdi" iddiasının içinde
# geçtiğinde PANEL İDDİASI sayılır. Cümleciğin yüklemi olumsuzsa
# (basmıyor/geçmiyor/okumuyor/çizmiyor) iddia TERSİNE çevrilir: ad panelde
# BULUNMAMALIDIR. Bu dar kapsam, gerekçe metnine dil bilgisi dayatmadan
# yanlış kırmızı üretmeden çalışır; kapsam dışında kalan adlar (bekçi
# adları, künye/borç atıfları, çapraz göndermeler) burada sınanmaz.
#
# D18 EKİ (Fable-D16 ŞART, madde 1): sınıflandırıcı yalnız "panel … `X`"
# SIRASINI tanıyordu; Türkçede aynı iddia sıklıkla TERS sırayla yazılır
# ("`X` cümlesi olarak panelde basılıyor"). Ölçüldü (`once_ohb407.json`):
# ters-tırnak + "panel" içeren 15 muafiyet satırı sınıflandırıcıdan HİÇ
# iddia çıkarmıyordu. Ters sıra deseni eklendi (1 satır kazanıldı:
# validation/parsed::units -> `parsed.warnings`) ve kalan 14 KÖR satır
# `KOR_SATIR_BEYANI`nda ADIYLA beyan edildi; beyan edilmemiş yeni kör
# satır artık kırmızıdır (test_ters_tirnakli_panel_satiri_kor_kalmaz).

_AD = r'([A-Za-z_][\w.\']*)'
_PANEL_IDDIA = re.compile(r'panel[^`;.\n]{0,40}`' + _AD + '`')
# Ters sıra: "`X` … panel(de|e) … basıyor / basılıyor / çiziyor / okuyor".
# Sınır olarak `;`, satır sonu ve BAŞKA bir ters tırnak kullanılır; böylece
# desen bir sonraki adın cümleciğine sızmaz.
_PANEL_IDDIA_TERS = re.compile(
    r'`' + _AD + r'`[^`;\n]{0,40}panel(?:de|e)?\b[^`;.\n]{0,40}'
    r'(?:bas[ıi]yor|bas[ıi]l[ıi]yor|çiziyor|okuyor|geçiyor)')
_GIRDI_IDDIA = re.compile(r'girdi[^`;\n]{0,24}`' + _AD + '`')
_GIRDI_EK = re.compile(r'`' + _AD + r'`(?=[/,]\s*`)|(?<=[/,])\s*`' + _AD + '`')
_KULLANICI = re.compile(r'kullanıcı')
_OLUMSUZ = re.compile(r'(basmıyor|geçmiyor|okumuyor|çizmiyor|yayımlamıyor)')
_BEKCI_ADI = re.compile(r'^(test_|Test[A-Z])')

SOZLESME_MODULLERI = (
    'tests.test_wave3_contract',
    'tests.test_wave4a_contract',
    'tests.test_wave4b_contract',
)


def _js_metin(yollar):
    return '\n'.join((JS_KOK / y).read_text(encoding='utf-8') for y in yollar)


def _cumlecik(neden, ad):
    """Adın geçtiği cümleciği ayır (`;` `,` ve satır sonu sınır).

    Virgül de sınırdır: 'panel `wall_profile` bloğunu … geçiriyor, tek tek
    okumuyor' cümlesinde olumsuz yüklem İKİNCİ cümleciğe aittir ve ilk
    cümleciğin olumlu iddiasını çevirmez.
    """
    yer = neden.find('`' + ad + '`')
    if yer < 0:
        return neden
    bas = max(neden.rfind(';', 0, yer), neden.rfind(',', 0, yer),
              neden.rfind('\n', 0, yer)) + 1
    son = min([k for k in (neden.find(';', yer), neden.find(',', yer))
               if k != -1] or [len(neden)])
    return neden[bas:son]


def _panel_iddialari(neden):
    """Gerekçedeki iddiaları çıkar -> {ad: (olumlu_mu, olcut)}.

    `olcut` 'envanter' ise ad panelin OKUDUĞU yanıt alanları arasında,
    'kaynak' ise panel JS METNİNDE aranır. Kullanıcının FORM ALANI olarak
    girdiği bir ad yanıt okuması değildir; onun ölçütü kaynaktır.
    """
    neden = str(neden)
    iddia = {}

    def _ekle(ad, olcut):
        sade = ad.strip("'")
        if _BEKCI_ADI.match(sade):
            return          # bekçi adı — panelde aranmaz
        olumlu = not _OLUMSUZ.search(_cumlecik(neden, ad))
        onceki = iddia.get(sade)
        # Aynı ad iki kez geçerse KAYNAK ölçütü (gevşek olan) kazanır.
        if onceki is None or olcut == 'kaynak':
            iddia[sade] = (olumlu if onceki is None else onceki[0], olcut)

    for ad in set(_PANEL_IDDIA.findall(neden)):
        _ekle(ad, 'envanter')
    for ad in set(_PANEL_IDDIA_TERS.findall(neden)):
        _ekle(ad, 'envanter')
    if _KULLANICI.search(neden):
        for eslesme in _GIRDI_IDDIA.finditer(neden):
            _ekle(eslesme.group(1), 'kaynak')
            kuyruk = neden[eslesme.end():eslesme.end() + 40]
            for ad in re.findall(r'^[/,]\s*`' + _AD + '`', kuyruk):
                _ekle(ad, 'kaynak')
    return iddia


def _panelde_var(ad, envanter, metin, olcut='envanter'):
    if olcut == 'kaynak':
        return ad in metin
    if '.' in ad:
        # Nokta içeren atıf: ya takma ad öneki (`st.`) ya yol
        # (`a.b`). İkisi de metinde ARANIR; yol ayrıca parça parça.
        if ad in metin:
            return True
        return all(p in envanter for p in ad.split('.') if p)
    return ad in envanter


def _muafiyet_satirlari():
    """(modül_kısa, blok, alan, ad, olumlu, envanter, js_metin) satırları."""
    for mod_adi in SOZLESME_MODULLERI:
        m = importlib.import_module(mod_adi)
        kisa = mod_adi.split('.')[-1]
        for blok, (yollar, muafiyet) in m.TERS_MUAFIYET.items():
            if isinstance(yollar, str):
                yollar = (yollar,)
            envanter = m._okuma_envanteri(*yollar)
            metin = _js_metin(yollar)
            for alan, neden in muafiyet.items():
                for ad, (olumlu, olcut) in _panel_iddialari(neden).items():
                    yield (kisa, blok, alan, ad, olumlu, envanter, metin,
                           olcut)


@pytest.fixture(scope='module')
def muafiyet_satirlari():
    return list(_muafiyet_satirlari())


# --- D18 (Fable-D16 ŞART, madde 1): satır-bazlı KAPSAM -----------------
#
# Sınıflandırıcı dar olduğu için ters-tırnak + "panel" içeren bir satır
# hiç iddia üretmeden geçebilir. Bu sessiz geçiş, muafiyeti yeniden
# dilekçeye çevirir. Aşağıdaki beyan, KÖR kalmasına izin verilen 14
# satırı ADIYLA ve GEREKÇE SINIFIYLA sayar; listede olmayan yeni kör
# satır kırmızıdır.
#
# Sınıflar:
#   'olumsuz-atif' : panel cümlesi OLUMSUZ ("panelde geçmiyor/karşılığı
#                    yok") ve ters-tırnaklı ad panel iddiası değil, borç/
#                    kaynak atfıdır — sınanacak bir varlık iddiası yok.
#   'tanim'        : ters-tırnaklı ad alanın KENDİSİ ya da ikizidir;
#                    cümle "panel sayıyı zaten basıyor, ikinci kez
#                    basmak tekrar olurdu" der — varlık iddiası değil.
#   'kosullu'      : ad bir GİRDİ dalıdır ("`X` verilmediyse …"); panel
#                    cümlesi ada değil, türetilen değere bakar.
#   'rota'         : ters-tırnaklı belirteç bir HTTP rotasıdır, yanıt
#                    yaprağı değil; panelin okuma envanterinde aranamaz.
KOR_SATIR_BEYANI = {
    ('test_wave3_contract', 'vessel', 'burst_margin_definition'): 'tanim',
    ('test_wave3_contract', 'vessel', 'burst_margin_vs_required_burst'):
        'tanim',
    ('test_wave3_contract', 'vessel', 'head_thickness_available_mm'):
        'kosullu',
    ('test_wave3_contract', 'protection/ablative', 'T_surface_K'):
        'olumsuz-atif',
    ('test_wave3_contract', 'protection/radiation', 'q_gas_radiation_W_m2'):
        'olumsuz-atif',
    ('test_wave3_contract', 'joint', 'bearing'): 'olumsuz-atif',
    ('test_wave3_contract', 'safety', 'thermal_safety'): 'olumsuz-atif',
    ('test_wave3_contract', 'safety', 'explosive_hazards'): 'olumsuz-atif',
    # ÖH D27 arayuz a4 — ÖLÜ BEYAN SÖKÜLDÜ. Bu satır 'kör satır'
    # (bekçinin sembolü yalnız olumsuz atıfla andığı satır) diye
    # beyan edilmişti; D27 arayuz aşama-2'nin OH-B3-02 onarımı
    # transient erozyon bloğunu panele GERÇEKTEN bastıktan sonra
    # bekçi sembolü olumlu sınıyor, yani satır artık kör DEĞİL.
    # Beyan yerinde kalırsa `test_kor_satir_beyani_curumez` ölü
    # beyan olarak KIRMIZI verir (nitekim verdi).
    ('test_wave3_contract', 'blowdown/tank', 'of_ratio'): 'olumsuz-atif',
    ('test_wave4a_contract', 'flow/regime', 'thresholds_Pa'): 'olumsuz-atif',
    ('test_wave4a_contract', 'flow/kinetic', 'diagnostics'): 'olumsuz-atif',
    ('test_wave4b_contract', 'feed/water_hammer', 'column_separation'):
        'olumsuz-atif',
    ('test_wave4b_contract', 'settings/update', 'asset'): 'rota',
}


def _kor_satirlar():
    """Ters-tırnak + 'panel' içerip HİÇ iddia üretmeyen muafiyet satırları."""
    kor = []
    for mod_adi in SOZLESME_MODULLERI:
        m = importlib.import_module(mod_adi)
        kisa = mod_adi.split('.')[-1]
        for blok, (_yollar, muafiyet) in m.TERS_MUAFIYET.items():
            for alan, neden in muafiyet.items():
                n = str(neden)
                if 'panel' not in n.lower() or '`' not in n:
                    continue
                if _panel_iddialari(n):
                    continue
                kor.append((kisa, blok, alan))
    return kor


class TestOHB407MuafiyetGerekcesiOlculur:
    """Muafiyet gerekçesindeki panel iddiası panelin kaynağına karşı sınanır."""

    def test_olumlu_panel_iddiasi_panelde_karsilanir(self, muafiyet_satirlari):
        """'panel `X` basıyor' diyen gerekçede `X` panelde GEÇMELİ."""
        bayat = [f'{k}::{b}::{a} -> `{ad}` panelde yok ({olcut})'
                 for k, b, a, ad, olumlu, env, metin, olcut
                 in muafiyet_satirlari
                 if olumlu and not _panelde_var(ad, env, metin, olcut)]
        assert not bayat, (
            'BAYAT muafiyet gerekçesi (panel iddiası kaynakta '
            f'karşılanmıyor): {bayat}')

    def test_olumsuz_panel_iddiasi_hala_dogru(self, muafiyet_satirlari):
        """'panel `X` basmıyor' diyen gerekçede `X` panelde GEÇMEMELİ.

        Panel sonradan o alanı basmaya başladıysa muafiyet gereksizdir;
        gerekçe ölü satıra döner ve alanı sessizce affeder.
        """
        cürüyen = [f'{k}::{b}::{a} -> `{ad}` panele inmiş'
                   for k, b, a, ad, olumlu, env, metin, olcut
                   in muafiyet_satirlari
                   if not olumlu and _panelde_var(ad, env, metin, olcut)]
        assert not cürüyen, (
            f'muafiyet gerekçesi ürünün gerisinde kaldı: {cürüyen}')

    def test_gerekce_bekci_adi_aniyorsa_o_bekci_vardir(self):
        """Gerekçe `test_…`/`Test…` diyorsa o bekçi tests/ altında OLMALI."""
        yazi = '\n'.join(
            (TESTS_KOK / f).read_text(encoding='utf-8')
            for f in ('test_wave3_contract.py', 'test_wave4a_contract.py',
                      'test_wave4b_contract.py'))
        eksik = []
        for mod_adi in SOZLESME_MODULLERI:
            m = importlib.import_module(mod_adi)
            for blok, (_yollar, muafiyet) in m.TERS_MUAFIYET.items():
                for alan, neden in muafiyet.items():
                    for ad in re.findall(r'`(test_\w+|Test[A-Z]\w*)`',
                                         str(neden)):
                        if f'def {ad}(' not in yazi and f'class {ad}' not in yazi:
                            eksik.append(f'{blok}::{alan} -> {ad}')
        assert not eksik, (
            f'gerekçe var olmayan bekçiye atıf yapıyor: {eksik}')

    def test_iddia_evreni_bosalmadi(self, muafiyet_satirlari):
        """Sınıflandırıcı sessizce boşalırsa iddia totolojiye döner.

        ÖLÇÜLEN SAYILAR (Fable-D16 ŞART madde 2 uyarınca nihai bekçinin
        kendi ölçümüne çevrildi):

          * D16 tabanında (6fde52b) evren 40 iddiaydı; 5 BAYAT + 1
            ÇÜRÜYEN (alıntılanan `material`) satır vardı.
          * D16 onarımından sonra ana ağaçta evren 39, açık 0.
            (Evrenin 40'tan 39'a düşmesi kusur değil: alıntıdan ters
            tırnaklar kaldırıldı, o sahte iddia evrenden çıktı.)
          * D18'de ters sıra deseni 1 iddia kazandırdı
            (validation/parsed::units -> `parsed.warnings`); evren 40.

        Not: D16 rapor metnindeki "43 iddia (32 karşılanan + 11 açık)"
        o günün ARA sınıflandırıcısının sayısıydı, nihai bekçinin değil;
        bu docstring artık nihai bekçinin ölçtüğü sayıları taşır.
        Taban 30'un altına düşerse süzgeç kırılmıştır, kusur değil.
        """
        assert len(muafiyet_satirlari) >= 30, (
            'panel iddiası evreni beklenmedik biçimde küçüldü: '
            f'{len(muafiyet_satirlari)}')

    def test_ters_sira_iddiasi_da_sinifllandiriliyor(self):
        """"`X` … panelde basılıyor" sırası da PANEL İDDİASI sayılır.

        FA2 (Fable-D16 ŞART madde 1 ölçütü): validation/parsed::units
        gerekçesindeki `parsed.warnings` adı bozulursa bu iddia kırmızıya
        düşmelidir. D16'da o satır sınıflandırıcıya HİÇ görünmüyordu.
        """
        m = importlib.import_module('tests.test_wave4a_contract')
        yollar, muafiyet = m.TERS_MUAFIYET['validation/parsed']
        if isinstance(yollar, str):
            yollar = (yollar,)
        neden = str(muafiyet['units'])
        iddia = _panel_iddialari(neden)
        assert iddia, (
            'ters sıralı panel iddiası sınıflandırılmıyor: ' + neden[:120])
        env = m._okuma_envanteri(*yollar)
        metin = _js_metin(yollar)
        bayat = [ad for ad, (olumlu, olcut) in iddia.items()
                 if olumlu and not _panelde_var(ad, env, metin, olcut)]
        assert not bayat, f'ters sıralı iddia bayat: {bayat}'

    def test_ters_tirnakli_panel_satiri_kor_kalmaz(self):
        """Ters-tırnak + "panel" içeren her satır ya iddia üretir ya beyanlıdır.

        Sınıflandırıcı dar; darlık sessiz muafiyete dönüşmesin diye kör
        satırlar ADIYLA sayılır. Yeni bir kör satır eklenirse (ya da bir
        gerekçe yeniden yazılıp iddiasını kaybederse) bu iddia kırmızıdır.
        """
        kor = _kor_satirlar()
        beyansiz = sorted('::'.join(k) for k in kor
                          if k not in KOR_SATIR_BEYANI)
        assert not beyansiz, (
            'ters-tırnak+panel içeren muafiyet satırı hiç iddia üretmiyor '
            f've KOR_SATIR_BEYANI\'nda da beyan edilmemiş: {beyansiz}')

    def test_kor_satir_beyani_curumez(self):
        """Beyan listesi ürünün gerisinde kalamaz.

        Bir satır sonradan iddia üretmeye başladıysa (ya da tablodan
        kaldırıldıysa) beyanı ölü satıra döner; ölü beyan, ileride
        gerçekten kör kalan bir satırı sessizce affeder.
        """
        kor = set(_kor_satirlar())
        olu = sorted('::'.join(k) for k in KOR_SATIR_BEYANI if k not in kor)
        assert not olu, f'KOR_SATIR_BEYANI ölü satır taşıyor: {olu}'
        assert set(KOR_SATIR_BEYANI.values()) <= {
            'olumsuz-atif', 'tanim', 'kosullu', 'rota'}, (
            'beyan sınıfı sözlük dışı: '
            f'{sorted(set(KOR_SATIR_BEYANI.values()))}')


# ===========================================================================
# P14M3-02 — motor kesitindeki delik sayısı kanalı (kök kusur P8B4-25)
# ===========================================================================
#
# D15/fea-viz(a3) kesitin HOVER metnini kilitledi
# (`test_d15_fea_viz_a3.py::TestP8B425DelikSayisiTekKaynak`). Ölçüldü
# (`once_p14m3_02.json`): kesitin İKİ kanalı daha var ve ikisi de
# bekçisizdi —
#   K4 çizilen orifis İŞARETİ sayısı (3 / 4 / 5 / 9; delik sayısına cevap
#      veriyor), ve
#   K5 kardeş YÜZ görünümünün çizdiği delik sayısı.
# P8B4-25'in özü "aynı sayfada iki çizim iki farklı sayı basıyor"dur;
# asıl kilit, İKİ çizimin AYNI sayıyı demesidir. Aşağıdaki iddialar bu
# çapraz kilidi kurar.

def _kesit_metni(motor):
    from hrma.visualization.visualization import (
        create_improved_motor_cross_section)
    ham = create_improved_motor_cross_section(motor, 'hybrid')
    d = json.loads(ham) if isinstance(ham, str) else ham
    parca = []
    for tr in d.get('data', []):
        for anahtar in ('text', 'hovertext', 'hovertemplate', 'name'):
            v = tr.get(anahtar)
            if isinstance(v, str):
                parca.append(v)
            elif isinstance(v, list):
                parca += [s for s in v if isinstance(s, str)]
    for an in (d.get('layout', {}).get('annotations') or []):
        if isinstance(an.get('text'), str):
            parca.append(an['text'])
    return d, '\n'.join(parca)


def _orifis_isareti(d):
    for tr in d.get('data', []):
        if tr.get('name') == 'Orifices':
            return len(tr.get('y') or ())
    return None


def _yuz_delikleri(n_holes):
    from hrma.visualization.visualization import (
        create_showerhead_with_tooltips)
    ham = create_showerhead_with_tooltips(
        {'n_holes': n_holes, 'hole_diameter': 1.5, 'plate_thickness': 3.0})
    d = json.loads(ham) if isinstance(ham, str) else ham
    return sum(1 for tr in d.get('data', [])
               if str(tr.get('name') or '').startswith('Hole '))


def _motor(n_holes, n_ori=None):
    m = {'chamber_diameter': 100.0, 'chamber_length': 0.3,
         'throat_diameter': 30.0, 'exit_diameter': 60.0,
         'injector': {'n_holes': n_holes},
         'injector_design': {'injector_type': 'showerhead'}}
    if n_ori is not None:
        m['injector_design']['number_of_orifices'] = n_ori
    return m


class TestP14M302KesitDelikKanali:

    @pytest.mark.parametrize('n_holes', [3, 7, 12, 61])
    def test_iki_cizim_ayni_delik_sayisini_der(self, n_holes):
        """Kesit hover'ı ile yüz görünümünün delik sayısı AYNI olmalı.

        P8B4-25'in kökü: aynı koşuda yüz 153, kesit 7 diyordu (21,86x).
        """
        _d, metin = _kesit_metni(_motor(n_holes, n_ori=7))
        assert f'Showerhead pattern: {n_holes} axial orifices' in metin
        assert _yuz_delikleri(n_holes) == n_holes

    def test_isaret_sayisi_delik_sayisina_cevap_verir(self):
        """Çizilen orifis işareti sayısı sabit değildir.

        Ölçüldü: 3 delik -> 3 işaret, 7 -> 4, 61 -> 9. Sabitlenirse
        kesit kullanıcının girdisine görsel olarak kayıtsız kalır.
        """
        isaretler = []
        for n in (3, 7, 61):
            d, _m = _kesit_metni(_motor(n, n_ori=n))
            isaretler.append(_orifis_isareti(d))
        assert None not in isaretler, f'orifis izi yok: {isaretler}'
        assert len(set(isaretler)) >= 2, (
            f'işaret sayısı delik sayısına cevap vermiyor: {isaretler}')
        assert isaretler == sorted(isaretler), (
            f'işaret sayısı delik sayısıyla artmıyor: {isaretler}')

    def test_kesit_sayiyi_kullanicinin_alanindan_alir(self):
        """Hover, hangi alandan okuduğunu ADIYLA söyler."""
        _d, metin = _kesit_metni(_motor(61, n_ori=7))
        satir = [s for s in metin.split('\n') if 'axial orifices' in s]
        assert satir, 'orifis hover satırı yok'
        assert "results['injector'].n_holes" in satir[0], (
            f'kaynak künyesi orifis satırında yok: {satir[0]!r}')


# ===========================================================================
# OH-Z4-02 — Z4 bekçi borçları (kapanan kalemlerin KALICI kilidi)
# ===========================================================================
#
# Borç paketi yedi kalemdi; bu aşamada İKİSİ kilitlendi (ölçüm:
# `once_ohz402.json`). Kalan beşi (manşet-DEĞİŞMELİ süpürmesi, çift-SF
# etiketi/Δ, yalıtımlı-vaka akma-basıncı duyarlılığı, converged kapısı,
# kıyas-beyanı) bu aşamada AÇILMADI — her biri ayrı bir canlı koşum
# gerektiriyor ve bu kulvarın süre bütçesine sığmadı.

# --- (2) wall_thickness_source ÜÇ ROZET ayrımı -----------------------------
#
# P15S1-01/-02'nin yalanı: bir değer GELMİŞ ama okunamamışken künye yine
# "No wall thickness was supplied" diyordu, yani "hiç göndermedin" ile
# "gönderdin ama hesaba girmedi" TEK rozete çöküyordu. Sınıflandırıcı
# `_classify_wall_thickness_gate`te birleştirildi; kilit buydu, bekçisi
# yoktu (mevcut `test_z5i18n_kalan.py` yalnız ÇEVİRİYİ sınıyor).

def _kapi(submitted_m, evaluated_m, durum):
    from hrma import app as appmod
    return appmod._classify_wall_thickness_gate(
        submitted_m, evaluated_m, durum, 'mm')


class TestOHZ402CidarRozetiUcSinif:

    def test_uc_rozet_de_ayri_ayri_atesleniyor(self):
        """Üç sınıf üç AYRI dizge yayımlar.

        Beklenen küme sabitlerden DEĞİL, yayımlanan DİZGELERDEN yazılır:
        rozet adları ürünün dış sözleşmesidir (ihraç/panel/PDF onları
        okuyor) ve sabit yeniden adlandırılarak sessizce çökertilemez.
        Ölçüldü (MUT10): sabitle yazılan sürüm rozet çöküşünü kaçırıyordu.
        """
        from hrma import app as appmod
        rozetler = {
            _kapi(None, 0.0159, appmod.WALL_INPUT_NOT_SUPPLIED)[
                'wall_thickness_source'],
            _kapi(0.0159, 0.0159, appmod.WALL_INPUT_OK)[
                'wall_thickness_source'],
            _kapi(None, 0.0159, appmod.WALL_INPUT_UNREADABLE)[
                'wall_thickness_source'],
        }
        assert rozetler == {'sized_by_hrma', 'user_supplied',
                            'user_value_not_applied'}, (
            f'üç rozetin üçü ayrışmıyor: {sorted(rozetler)}')
        # Sabitler de aynı dizgeleri taşımalı (tek kaynak korunur).
        assert appmod.WALL_GATE_SIZED == 'sized_by_hrma'
        assert appmod.WALL_GATE_USER == 'user_supplied'
        assert appmod.WALL_GATE_NOT_APPLIED == 'user_value_not_applied'

    @pytest.mark.parametrize('durum_adi', [
        'WALL_INPUT_UNREADABLE', 'WALL_INPUT_NOT_POSITIVE',
        'WALL_INPUT_NOT_FINITE'])
    def test_gelen_ama_uygulanmayan_deger_hic_gelmedi_demez(self, durum_adi):
        """P15S1-01'in yalanı: künye "No wall thickness was supplied" diyordu.

        Bir değer GELDİYSE künye bunu söylemelidir; "hiç gelmedi" cümlesi
        yalnız SIZED dalına aittir.
        """
        from hrma import app as appmod
        k = _kapi(None, 0.0159, getattr(appmod, durum_adi))
        assert k['wall_thickness_source'] == appmod.WALL_GATE_NOT_APPLIED
        assert 'No wall thickness was supplied' not in k['message'], (
            f'{durum_adi}: künye değerin hiç gelmediğini iddia ediyor: '
            f'{k["message"][:90]!r}')
        assert 'WAS submitted' in k['message']

    def test_uygulanmayan_deger_dogrulama_saymaz(self):
        """Sadece GERÇEKTEN hesaba giren cidar `is_verification` olur."""
        from hrma import app as appmod
        uygulanmadi = _kapi(0.005, 0.0159, appmod.WALL_INPUT_OK)
        assert uygulanmadi['wall_thickness_source'] == \
            appmod.WALL_GATE_NOT_APPLIED
        assert uygulanmadi['is_verification'] is False
        assert uygulanmadi['withheld_reason'] == \
            'user_wall_thickness_not_applied'
        # ...ve gönderilen/değerlendirilen çifti YAYIMLANIR (beyan değil,
        # kullanıcı iki sayıyı da görebilmeli).
        assert uygulanmadi['submitted_wall_thickness_mm'] == 5.0
        assert uygulanmadi['evaluated_wall_thickness_mm'] == 15.9
        uygulandi = _kapi(0.0159, 0.0159, appmod.WALL_INPUT_OK)
        assert uygulandi['is_verification'] is True
        assert uygulandi['withheld_reason'] is None

    def test_sized_dali_dogrulama_iddia_etmez(self):
        """HRMA kendi cidarını seçtiyse sonuç ÖNERİdir, doğrulama değil."""
        from hrma import app as appmod
        k = _kapi(None, 0.0159, appmod.WALL_INPUT_NOT_SUPPLIED)
        assert k['is_verification'] is False
        assert 'DESIGN PROPOSAL' in k['message']


# --- (7) künye-tanımı (`*_is_tautological_basis`) --------------------------
#
# Z4'te ayrışan iki cümle: "cidarı HRMA seçti" (totoloji BAYRAĞI) ile
# "yayımlanan sayı hedefin geri okunmasıdır" (KESİN ÖLÇÜT). Tüketiciler
# birincisini ikincisi sanıyordu. Künye alanı bu ayrımı yazıyor; bekçisi
# yalnız TEK dizge (`'SHARP definition'`) üzerinden ve tek alan için vardı.
#
# D18 (Fable-D16 ŞART, madde 1+2): D16 bekçisi künyeyi KARAKTER PENCERESİ
# ile ölçüyordu — `kaynak.find(ad)` sonrası 1600 karakter. Ölçüldü
# (`once_ohz402.json`): hazne künyesinden "Use safety_factor_reads_back_
# target for that question." cümlesi silinse bile pencere, HEMEN ALTINDAKİ
# `safety_factor_reads_back_target` ALAN ADINI görüp yeşil kalıyordu; yani
# künyenin kendisi hiç okunmuyordu. Ayrıca yalnız İLK geçen künye
# sınanıyordu: 5 yayım noktasından 2'si (nozul 1477, kapak 1624) hiç
# görülmüyordu. D18'de her iki eksik de AST ile kapatıldı:
#   * künye metni ters-tırnak/pencere değil, SÖZLÜK LİTERALİNİN kendisi
#     olarak ayrıştırılır (`_kunye_literalleri`);
#   * bayrak yayımlayan HER sözlük literali sayılır ve künyesiz olanlar
#     `KUNYE_KAPSAM_BEYANI`nda ADIYLA beyan edilir.


def _sa_agaci():
    kaynak = (KOK / 'hrma' / 'analysis' /
              'structural_analysis.py').read_text(encoding='utf-8')
    import ast
    return ast.parse(kaynak)


def _duz_dizge(dugum):
    """Bitişik/parantezli dizge literalini tek metne indir (yoksa None)."""
    import ast
    if isinstance(dugum, ast.Constant) and isinstance(dugum.value, str):
        return dugum.value
    if isinstance(dugum, ast.JoinedStr):
        return ''.join(p.value for p in dugum.values
                       if isinstance(p, ast.Constant)
                       and isinstance(p.value, str))
    if isinstance(dugum, ast.BinOp):
        sol, sag = _duz_dizge(dugum.left), _duz_dizge(dugum.right)
        if sol is None or sag is None:
            return None
        return sol + sag
    return None


def _sozlukler():
    """Totoloji bayrağı yayımlayan sözlük literalleri -> anahtar kümesi."""
    import ast
    for d in ast.walk(_sa_agaci()):
        if not isinstance(d, ast.Dict):
            continue
        cift = [(k.value, v) for k, v in zip(d.keys, d.values)
                if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        adlar = {a for a, _ in cift}
        if any(a.endswith('_is_tautological') for a in adlar):
            yield d.lineno, adlar, dict(cift)


def _kunye_literalleri():
    """{künye_adı: [(satır, metin), …]} — HER yayım noktası ayrı kayıt."""
    import ast
    bulgu = {}
    for d in ast.walk(_sa_agaci()):
        if not isinstance(d, ast.Dict):
            continue
        for k, v in zip(d.keys, d.values):
            if not (isinstance(k, ast.Constant)
                    and isinstance(k.value, str)
                    and k.value.endswith('_is_tautological_basis')):
                continue
            bulgu.setdefault(k.value, []).append(
                (k.lineno, _duz_dizge(v)))
    return bulgu


# Bayrak yayımlayan ama AYNI literalde künye TAŞIMAYAN noktalar. Ürün
# koduna dokunmak bu kulvarın sahası değil (tests/**), bu yüzden kapsam
# ADIYLA beyan edilir: her satır, o bayrağın okuyucuya hangi künyeyle
# ulaştığını söyler ve kendi literalinde KESİN ÖLÇÜTÜ
# (`safety_factor_reads_back_target`) yayımladığı makineyle sınanır.
# Beyan edilmemiş yeni künyesiz yayım noktası kırmızıdır.
KUNYE_KAPSAM_BEYANI = {
    '_analyze_nozzle_structure': (
        'safety_factor_is_tautological_basis@_analyze_safety_factors',
        'Nozul bloğu bayrağı kendi literalinde künyesiz yayımlıyor; '
        'okuyucuya ulaşan künye toplayıcının istasyon HARİTASI '
        'künyesidir (safety_factor_is_tautological_basis, per-station '
        'map). Blok kendi KESİN ÖLÇÜTÜNÜ (safety_factor_reads_back_'
        'target) aynı literalde yayımlar; AÇIK BORÇ: blok künyesi yok.'),
    '_analyze_end_caps': (
        'safety_factor_is_tautological_basis@_analyze_safety_factors',
        'Kapak bloğu için aynı durum: künye toplayıcının istasyon '
        'haritasındadır, blok kendi kesin ölçütünü yayımlar. '
        'AÇIK BORÇ: blok künyesi yok.'),
}


class TestOHZ402KunyeTanimi:

    def _kaynak(self):
        return (KOK / 'hrma' / 'analysis' /
                'structural_analysis.py').read_text(encoding='utf-8')

    def test_her_totoloji_bayraginin_kunyesi_ve_kesin_olcutu_var(self):
        kaynak = self._kaynak()
        bayrak = set(re.findall(r"'([a-z_]*is_tautological)'", kaynak))
        kunye = set(re.findall(r"'([a-z_]*is_tautological_basis)'", kaynak))
        olcut = set(re.findall(r"'([a-z_]*reads_back_target)'", kaynak))
        assert bayrak, 'totoloji bayrağı hiç bulunamadı — süzgeç kırık'
        eksik_kunye = sorted(b for b in bayrak if b + '_basis' not in kunye)
        assert not eksik_kunye, f'künyesiz totoloji bayrağı: {eksik_kunye}'
        eksik_olcut = sorted(
            b for b in bayrak
            if b.replace('_is_tautological', '_reads_back_target')
            not in olcut)
        assert not eksik_olcut, (
            f'kesin ölçütü olmayan totoloji bayrağı: {eksik_olcut}')

    def test_kunye_metni_hedefe_esitligi_REDDEDIYOR(self):
        """Künye "bayrak, sayı hedefe eşit demek DEĞİLDİR" demeli.

        Z4'ün kökü tam buydu: hibritte bayrak True iken yayımlanan
        katsayı 1,7173, hedef 4,0 idi.

        D18: ölçüm KÜNYE DİZGESİNİN İÇİNDE yapılır (AST), karakter
        penceresinde değil. FC3 (hazne künyesinden "Use safety_factor_
        reads_back_target for that question." silinmesi) eski pencereli
        bekçiden KAÇIYORDU; artık kırmızıdır.
        """
        kunyeler = _kunye_literalleri()
        assert kunyeler, 'künye literali hiç bulunamadı — süzgeç kırık'
        eksik = []
        for ad, kayitlar in sorted(kunyeler.items()):
            for satir, metin in kayitlar:
                yer = f'{ad}@{satir}'
                if metin is None:
                    eksik.append(f'{yer}: künye dizge literali değil')
                    continue
                # (a) saf okumayı AÇIKÇA reddeden bir olumsuzlama.
                if 'does NOT' not in metin and 'is NOT' not in metin:
                    eksik.append(f'{yer}: "does NOT"/"is NOT" yok')
                # (b) okuyucuyu KESİN ÖLÇÜTE ADIYLA yönlendirme.
                if not re.search(r'\w+(?:_reads_back_target|_sized_by_hrma)',
                                 metin):
                    eksik.append(f'{yer}: kesin ölçüte ADIYLA '
                                 'yönlendirmiyor')
        assert not eksik, f'künye tanımı eksik: {eksik}'

    def test_bayrak_yayim_noktalarinin_hepsi_kunyeli_ya_da_beyanli(self):
        """Bayrak yayımlayan HER sözlük literali künyeli ya da beyanlıdır.

        Ölçüldü (`once_ohz402.json`): 5 yayım noktasından 3'ü künyesini
        aynı literalde taşıyor (1289 hazne, 2685 harita, 2698 binding),
        2'si taşımıyor (1477 nozul, 1624 kapak). Eski bekçi yalnız
        ADLARI sayıyordu, yayım noktasını değil — nozul/kapak hiç
        görünmüyordu.

        FC4 ölçütü: haritanın künyesi (2687) kendi literalinden
        koparılırsa bu iddia KIRMIZI olur.
        """
        import ast
        fonk = []
        for d in ast.walk(_sa_agaci()):
            if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fonk.append((d.lineno, d.end_lineno, d.name))

        def _fonk_adi(ln):
            kapsayan = [n for (a, b, n) in fonk if a <= ln <= b]
            return kapsayan[-1] if kapsayan else '<modül>'

        noktalar, kusur = [], []
        for satir, adlar, _cift in _sozlukler():
            for bayrak in sorted(a for a in adlar
                                 if a.endswith('_is_tautological')):
                fa = _fonk_adi(satir)
                noktalar.append((fa, bayrak))
                if bayrak + '_basis' in adlar:
                    continue
                beyan = KUNYE_KAPSAM_BEYANI.get(fa)
                if beyan is None:
                    kusur.append(
                        f'{fa}::{bayrak}@{satir}: künyesiz yayım ve '
                        'KUNYE_KAPSAM_BEYANI\'nda beyan yok')
                    continue
                # Beyanın işaret ettiği künye GERÇEKTEN var olmalı.
                kunye_adi = beyan[0].split('@')[0]
                if kunye_adi not in _kunye_literalleri():
                    kusur.append(f'{fa}: beyan var olmayan künyeye '
                                 f'işaret ediyor ({beyan[0]})')
                # Künyesiz blok KESİN ÖLÇÜTÜ kendi literalinde yayımlamalı.
                olcut = bayrak.replace('_is_tautological',
                                       '_reads_back_target')
                if olcut not in adlar:
                    kusur.append(f'{fa}::{bayrak}@{satir}: ne künye ne '
                                 f'kesin ölçüt ({olcut}) var')
        assert len(noktalar) >= 5, (
            f'yayım noktası evreni küçüldü — süzgeç kırık: {noktalar}')
        assert not kusur, f'künyesiz/beyansız bayrak yayımı: {kusur}'

    def test_kunye_kapsam_beyani_curumez(self):
        """Beyan, künyesini kazanan bir bloğa asılı kalamaz."""
        import ast
        fonk = []
        for d in ast.walk(_sa_agaci()):
            if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fonk.append((d.lineno, d.end_lineno, d.name))
        kunyesiz = set()
        for satir, adlar, _c in _sozlukler():
            kapsayan = [n for (a, b, n) in fonk if a <= satir <= b]
            fa = kapsayan[-1] if kapsayan else '<modül>'
            for bayrak in (a for a in adlar
                           if a.endswith('_is_tautological')):
                if bayrak + '_basis' not in adlar:
                    kunyesiz.add(fa)
        olu = sorted(set(KUNYE_KAPSAM_BEYANI) - kunyesiz)
        assert not olu, (
            f'KUNYE_KAPSAM_BEYANI ölü satır taşıyor (blok artık künyeli '
            f'ya da bayrağı yok): {olu}')
