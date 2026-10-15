"""ÖH D32 · termo-ucus a1 bekçileri.

Kalem: **OH-D31-08** (defter P6B4-03 motor bağlantısı) — sıvı motorun chug
çevrimi, AYNI yanıtta yayımlanan İKİNCİ karışım zaman ölçeğini (enjektörün
karışma kalış süresi) duyarlı gecikme ADAYI olarak görmeli; hangi ölçeğin
daha kararsız hüküm verdiği BEYAN EDİLMEZ, ÖLÇÜLÜR.

Kusur (taban dd1dcddc'de ölçüldü, once.json): üç motor ölçeğinde de
``chug_loop`` bloğunda ``tau_choice_sensitivity`` alanı HİÇ yoktu, çünkü
``_chug_loop_block`` ``assess_chug``a ikinci adayı vermiyordu (çekirdek
D31'de hazırdı ve fail-closed olduğu için sessizce hiçbir şey yayımlamıyordu).
Aynı yanıtta iki ölçek yan yana duruyordu (10,313 ⟷ 9,637 ms; 13,886 ⟷
8,336 ms; 8,362 ⟷ 10,057 ms) ve künye "CONSERVATIVE choice" diyordu — 250 kN
koşusunda bu iddia YANLIŞTI: seçilmeyen ölçek DAHA BÜYÜKTÜ.

Kanıt paketi: docs/scofield/raw/OH/D32/termo-ucus/a1/ (once.json, sonra.json,
kanit_hesap.json, mutasyon_oh_d31_08.json, rapor.md).
"""
import math
import os

import pytest

os.environ.setdefault('HRMA_HEADLESS', '1')


# --- ürünün CANLI yolu: /calculate_liquid (ölü kopya ölçülmez) -------------
_YUKLER = {
    # (ad, yük) — a1 ölçümündeki üç ölçek.
    'A3_capa_sivi': {
        'motor_name': 'CAPA-SIVI', 'thrust': 10000.0, 'burn_time': 30.0,
        'chamber_pressure': 30.0, 'mixture_ratio': 2.2,
        'fuel_type': 'rp1', 'oxidizer_type': 'lox',
        'expansion_ratio': 12.0},
    'S2_buyuk_250kN': {
        'motor_name': 'OLCUM-250kN', 'thrust': 250000.0, 'burn_time': 120.0,
        'chamber_pressure': 60.0, 'mixture_ratio': 2.4,
        'fuel_type': 'rp1', 'oxidizer_type': 'lox',
        'expansion_ratio': 16.0},
}

_ONBELLEK = {}


def _bul(d, anahtar):
    """Gövdede ADIYLA geçen ilk düğümün değeri (yoksa None)."""
    if isinstance(d, dict):
        if anahtar in d:
            return d[anahtar]
        for v in d.values():
            bulunan = _bul(v, anahtar)
            if bulunan is not None:
                return bulunan
    elif isinstance(d, list):
        for v in d:
            bulunan = _bul(v, anahtar)
            if bulunan is not None:
                return bulunan
    return None


def _govde(ad):
    """/calculate_liquid yanıtı (koşum başına bir kez)."""
    if ad in _ONBELLEK:
        return _ONBELLEK[ad]
    from hrma.app import app
    app.config['TESTING'] = True
    istemci = app.test_client()
    r = istemci.post('/calculate_liquid', json=_YUKLER[ad])
    assert r.status_code == 200, f'{ad}: durum {r.status_code}'
    _ONBELLEK[ad] = r.get_json()
    return _ONBELLEK[ad]


def _cevrim(ad):
    j = _govde(ad)
    loop = _bul(j, 'chug_loop')
    assert isinstance(loop, dict), f'{ad}: chug_loop yok'
    assert loop.get('status') == 'modelled', (
        f"{ad}: çevrim çözülmedi ({loop.get('status')}) — bu bekçi "
        'çözülen çevrimi ölçer')
    return loop


# ---------------------------------------------------------------------------
# OH-D31-08 · (1) ALAN ÜRÜN YOLUNDA YAYIMLANIR
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('ad', sorted(_YUKLER))
def test_ohd3108_duyarlilik_alani_urun_yolunda_var(ad):
    """Çevrim ikinci ölçeği FİİLEN koşup yayımlamalı (taban: alan hiç yoktu)."""
    loop = _cevrim(ad)
    ts = loop.get('tau_choice_sensitivity')
    assert ts is not None, (
        f'{ad}: tau_choice_sensitivity yayımlanmıyor — motor bağlantısı yok, '
        'aynı yanıttaki ikinci karışım zaman ölçeği çevrime hiç girmiyor '
        '(OH-D31-08).')
    adaylar = ts.get('candidates') or {}
    assert 'mixing_residence_time' in adaylar, (
        f'{ad}: aday listesinde enjektörün karışma kalış süresi yok; '
        f'yalnız {sorted(adaylar)} var.')
    assert 'selected' in adaylar, (
        f'{ad}: çevrimin FİİLEN kullandığı τ aday listesinde yok')
    # Çekirdek her adayı gerçekten koşmuş olmalı: hüküm + frekans dolu.
    for anahtar, aday in adaylar.items():
        assert aday.get('verdict') in ('stable', 'unstable'), (
            f'{ad}/{anahtar}: aday koşulmamış (verdict {aday.get("verdict")})')
        assert aday.get('tau_s') and aday['tau_s'] > 0


# ---------------------------------------------------------------------------
# OH-D31-08 · (2) TEK KAYNAK + BİRİM: aday, yayımlanan ms değerinin kendisidir
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('ad', sorted(_YUKLER))
def test_ohd3108_aday_yayimlanan_degerin_kendisi(ad):
    """Aday τ = ``injection_system.mixing_residence_time`` / 1000, BİREBİR.

    İkinci bir karışma modeli kurulmadığının ölçüsü: aday, enjektör bloğunun
    yayımladığı sayının ta kendisidir (ms → s, tam 1e-3). Burada bağıl fark
    tam 0 beklenir; 0 değilse ya ikinci bir hesap kurulmuş ya birim
    çevrimi bozulmuştur.
    """
    j = _govde(ad)
    loop = _cevrim(ad)
    # ADRES AÇIK: aday listesindeki eşadlı anahtar değil, ENJEKTÖR bloğunun
    # yayımladığı sayı okunur (arama yapılsa çevrimin kendi adayı bulunurdu).
    enjektor = j.get('injection_system')
    assert isinstance(enjektor, dict), f'{ad}: injection_system bloğu yok'
    yayimlanan_ms = enjektor.get('mixing_residence_time')
    assert yayimlanan_ms is not None, f'{ad}: enjektör bloğu süreyi yayımlamıyor'
    aday_s = loop['tau_choice_sensitivity']['candidates'][
        'mixing_residence_time']['tau_s']
    assert aday_s == float(yayimlanan_ms) / 1000.0, (
        f'{ad}: aday {aday_s!r} s ⟷ yayımlanan {yayimlanan_ms!r} ms — '
        'aday yayımlanan değerin kendisi değil (TEK KAYNAK kırık ya da '
        'birim çevrimi bozuk).')
    # 'selected', çevrimin fiilen kullandığı τ olmalı — ikinci bir kopya değil.
    assert (loop['tau_choice_sensitivity']['candidates']['selected']['tau_s']
            == loop['tau_s'])


# ---------------------------------------------------------------------------
# OH-D31-08 · (3) "KONSERVATİF" ARTIK ÖLÇÜLÜR — 250 kN'de İDDİA YANLIŞTI
# ---------------------------------------------------------------------------
def test_ohd3108_buyuk_motorda_secilen_tau_en_konservatif_degil():
    """250 kN koşusunda seçilmeyen ölçek DAHA BÜYÜK; künye bunu söylemeli.

    Ölçüldü (sonra.json, S2_buyuk_250kN): τ_seçili = 8,362 ms ⟷
    τ_karışma = 10,057 ms. Monotonluk gereği (hüküm τ_nötr ile
    karşılaştırmadan gelir, τ_nötr τ'dan bağımsızdır) BÜYÜK τ daha kararsız
    hükmü verir; yani ürünün seçtiği τ bu koşuda yayımlanan ölçeklerin EN
    KONSERVATİFİ DEĞİLDİR. Taban ağacında bu olgu HİÇBİR yerde görünmüyordu
    ve künye koşulsuz "CONSERVATIVE choice" diyordu.
    """
    loop = _cevrim('S2_buyuk_250kN')
    ts = loop['tau_choice_sensitivity']
    adaylar = ts['candidates']
    assert adaylar['mixing_residence_time']['tau_s'] > adaylar['selected']['tau_s'], (
        'ölçüm değişmiş: 250 kN koşusunda karışma kalış süresi artık '
        'atomizasyon süresinden büyük değil — bekçinin dayandığı olgu '
        'kaybolmuş, kalem yeniden ölçülmeli.'
    )
    assert ts['most_conservative'] == 'mixing_residence_time', (
        'en konservatif aday EN BÜYÜK τ olmalı; '
        f"alan {ts['most_conservative']!r} diyor.")


@pytest.mark.parametrize('ad', sorted(_YUKLER))
def test_ohd3108_en_konservatif_en_buyuk_tau_urun_yolunda(ad):
    """``most_conservative`` her koşuda EN BÜYÜK τ'yu göstermeli."""
    ts = _cevrim(ad)['tau_choice_sensitivity']
    adaylar = ts['candidates']
    en_buyuk = max(adaylar, key=lambda a: adaylar[a]['tau_s'])
    assert ts['most_conservative'] == en_buyuk, (
        f'{ad}: en büyük τ {en_buyuk!r} ama alan '
        f"{ts['most_conservative']!r} diyor.")


# ---------------------------------------------------------------------------
# OH-D31-08 · (4) KÜNYE GERÇEĞİ SÖYLER (beyan çözüm değil, ama yalan da olmaz)
# ---------------------------------------------------------------------------
def test_ohd3108_kunye_konservatifligi_kosulsuz_iddia_etmez():
    """``tau_source`` ölçülen alana YÖNLENDİRMELİ, koşulsuz iddia etmemeli."""
    kunye = _cevrim('S2_buyuk_250kN').get('tau_source') or ''
    assert 'tau_choice_sensitivity' in kunye, (
        'künye, konservatifliğin ölçüldüğü alana yönlendirmiyor; '
        '"CONSERVATIVE choice" cümlesi 250 kN koşusunda ölçümle çelişiyor.')
    assert 'conservative' in kunye.lower()


# ---------------------------------------------------------------------------
# OH-D31-08 · (5) FAIL-CLOSED: aday çözülemezse alan HİÇ konmaz
# ---------------------------------------------------------------------------
def _sahte_enjektor(deger):
    """``calculate_injector_design`` yerine geçen sahte çözüm.

    GERÇEK çözücü ÇAĞRILMAZ: çıplak motorda enjektör çözümü (lüle çözümü
    yapılmadığı için) hata verir ve erişimci daha ölçülecek satıra gelmeden
    None döner — o hâlde bu bekçi SAHTE YEŞİL olurdu (ilk yazımda öyleydi,
    M3 ters-mutasyonu yakaladı). Sözlük doğrudan döndürülerek erişimcinin
    fiilen ölçülen satırı (sonluluk/pozitiflik kapısı) koşulur.
    """
    def _sahte(self, cooling=None):
        return {'mixing_residence_time': deger}
    return _sahte


def test_ohd3108_saglam_deger_gecer_bekci_canli():
    """Sağlam değerde aday ÜRETİLİR — bekçinin yolu canlı (hep-None değil)."""
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine

    motor = LiquidRocketEngine(thrust=10000, chamber_pressure=30,
                               mixture_ratio=2.2)
    orij = LiquidRocketEngine.calculate_injector_design
    LiquidRocketEngine.calculate_injector_design = _sahte_enjektor(4.5)
    try:
        assert motor._injector_mixing_residence_time_s() == 4.5 / 1000.0
    finally:
        LiquidRocketEngine.calculate_injector_design = orij


@pytest.mark.parametrize('bozuk', [None, float('nan'), float('inf'), 0.0,
                                   -3.0, 'abc'])
def test_ohd3108_aday_cozulemezse_alan_hic_konmaz(bozuk):
    """Enjektör süresi çözülemezse uydurma aday yayımlanmaz (ÖK doktrini)."""
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine

    motor = LiquidRocketEngine(thrust=10000, chamber_pressure=30,
                               mixture_ratio=2.2)
    orij = LiquidRocketEngine.calculate_injector_design
    LiquidRocketEngine.calculate_injector_design = _sahte_enjektor(bozuk)
    try:
        assert motor._injector_mixing_residence_time_s() is None, (
            f'{bozuk!r} için aday üretildi — sayı uydurulmuş olur')
    finally:
        LiquidRocketEngine.calculate_injector_design = orij


def test_ohd3108_enjektor_cozumu_patlarsa_neden_saklanir():
    """Çözücü hata verirse aday konmaz ama NEDEN adıyla saklanır."""
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine

    motor = LiquidRocketEngine(thrust=10000, chamber_pressure=30,
                               mixture_ratio=2.2)
    orij = LiquidRocketEngine.calculate_injector_design

    def _patlat(self, cooling=None):
        raise RuntimeError('enjektör çözümü bu koşuda kurulamadı')

    LiquidRocketEngine.calculate_injector_design = _patlat
    try:
        assert motor._injector_mixing_residence_time_s() is None
        assert 'RuntimeError' in (
            getattr(motor, '_injector_mixing_tau_error', '') or '')
    finally:
        LiquidRocketEngine.calculate_injector_design = orij


def test_ohd3108_erisim_ozyinelemede_sayi_uydurmaz():
    """Özyineleme kapısı: ikinci girişte aday üretilmez, None döner."""
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine

    motor = LiquidRocketEngine(thrust=10000, chamber_pressure=30,
                               mixture_ratio=2.2)
    motor._injector_mixing_tau_reentry = True
    assert motor._injector_mixing_residence_time_s() is None
    motor._injector_mixing_tau_reentry = False
    deger = motor._injector_mixing_residence_time_s()
    assert deger is None or (math.isfinite(deger) and deger > 0)
