"""fea-yuk 2. tur (14 Eki 2026) — kip mekanizması bekçileri için ORTAK ARAÇ.

Karar §28-18 (B) + kart OH-DK-04: yapısal FEA yükü artık izantropik P(x) +
kapalı uç kuvveti. Eski sabit-P_c yükü ıraksakta yapay bir net eksenel
kuvvet (sıvı örnekte −131,7 kN) üretiyor ve iki mesnet kipini (``z_min`` /
``z_max``) YAPAY olarak ayrıştırıyordu. Kip mekanizmalarını (kötümser kipin
yayımlanması, yayımlanan kibin KENDİ yakınsaması, kısıt-yeri duyarlılık
kapısı) sınayan bekçilerin araçları bu ayrışmaya dayanıyordu; doğru yükle
kipler birbirine yaklaştı (örnek araçlarda oran 1,0003-1,018) ve araçlar
kayboldu (fea-yuk 1. tur rapor 'DUR' tablosu).

Mekanizmaların kendisi geçerlidir; yalnız araç değişir. İki araç, ikisi de
ÜRÜNÜN KENDİ yolu (test içi yama YOK):

1. **Ayrışan kip aracı — izantropik yükte** (``ARAC_BIRINCIL_KIP``): köprü
   ``axial_fix`` parametresiyle birincil kibi seçtirir (ürün parametresi). Yeni
   yükte ``z_min`` kipi bu fikstürlerde hafifçe kötümser (ölçüldü,
   docs/scofield/raw/OH/V3/fea-yuk/kanit/tur2/arac_olc.jsonl): birincil
   ``z_max`` verilince yayımlanan kip ``z_min`` olur ve yayımlanan ≠ birincil
   koşulu (kendi yakınsaması ölçülen kip) doğal olarak kurulur. Sıvı 2 kN /
   15 bar / ε 5: 22,9382 ⟷ 22,7678; hibrit 2 kN / 30 bar: 38,4646 ⟷
   38,4509; katı 5 kN / 40 bar: 2,6471 ⟷ 2,5997.

2. **Büyük oranlı kip aracı — γ'sız geri dönüş yolu** (``gamma_suz``): motor
   sözlüğünden ``gamma`` çıkarılınca köprü beyanlı geri dönüşe düşer (sabit
   P_c + kapalı uç kuvveti; ``load_model.distribution ==
   'uniform_pc_fallback'``, ``fallback_reason`` adıyla). Bu ürünün gerçek
   yoludur (γ yayımlamayan motor) ve kısıt-yeri duyarlılık kapısının POZİTİF
   yakasını kurar: katı 5 kN / 40 bar oran 1,2007 (eşik %8,0; 1. tur ölçümü
   kanit/gamma_yok_arac.jsonl, 2. tur yeniden ölçüm kanit/tur2/).

Ters mutasyon (eski sabit P_c yükü, uç kuvveti yok): iki araç da kaybolur
ya da sayısı değişir → bu araçla çevrilen düğümler KIRMIZI
(docs/scofield/raw/OH/V3/fea-yuk/mutasyon.md, 2. tur).
"""
from __future__ import annotations

#: Ayrışan kip aracının birincil kibi (yeni yükte ``z_min`` kötümser kalır,
#: yayımlanan kip bu yüzden birincilden BAŞKA olur).
ARAC_BIRINCIL_KIP = 'z_max'
#: Ayrışan araçta yayımlanması beklenen (kötümser) kip.
ARAC_YAYIMLANAN_KIP = 'z_min'

#: Ürün künyesindeki dağılım adları (``hrma.fea.bridge``'den okunur; burada
#: literal tekrarlanmaz).


def _dagilim_adlari():
    from hrma.fea import bridge
    return (bridge.YUK_DAGILIMI_IZANTROPIK,
            bridge.YUK_DAGILIMI_SABIT_GERI_DONUS)


def gamma_suz(motor: dict) -> dict:
    """Motor sözlüğünün ``gamma``sız kopyası (köprü geri dönüş yoluna düşer).

    Özgün sözlük değişmez (modül kapsamlı fikstürler paylaşılır).
    """
    from hrma.fea import bridge
    kopya = dict(motor)
    assert bridge.YUK_GAMMA_ALANI in kopya, (
        'araç önkoşulu: motor γ yayımlamıyor — geri dönüş aracı anlamsız')
    kopya.pop(bridge.YUK_GAMMA_ALANI)
    return kopya


def _yuk_modeli(sonuc: dict) -> dict:
    """Yük modeli künyesi + kuvvet dengesi önkoşulu.

    Künye yalnız beyandır; çözücünün o yükü GERÇEKTEN uyguladığını mesnet
    eksenel tepkisi ⟷ analitik net kuvvet dengesi kanıtlar (OH-DK-04,
    ``force_balance.holds``). Yük çözücüye ulaşmıyorsa (ör. eski skaler P_c)
    denge tutmaz ve araç önkoşulu KIRMIZI olur.
    """
    lm = sonuc.get('load_model')
    if lm is None:
        lm = (sonuc.get('fea') or {}).get('load_model')
    assert isinstance(lm, dict), 'köprü sonucu yük modeli künyesi taşımıyor'
    fb = lm.get('force_balance') or {}
    assert fb.get('holds') is True, (
        'kuvvet dengesi tutmuyor — çözücü künyedeki yükü uygulamıyor', fb)
    return lm


def izantropik_yukte(sonuc: dict) -> dict:
    """Araç önkoşulu: koşu YENİ yük modelinde (izantropik + kapalı uç)."""
    izan, _ = _dagilim_adlari()
    lm = _yuk_modeli(sonuc)
    assert lm.get('distribution') == izan, lm.get('distribution')
    assert float((lm.get('end_force') or {}).get('force_n') or 0.0) > 0.0, (
        'kapalı uç kuvveti yok — koşu yeni yük modelinde değil')
    return lm


def geri_donus_yukte(sonuc: dict) -> dict:
    """Araç önkoşulu: koşu γ'sız geri dönüşte (sabit P_c + kapalı uç)."""
    from hrma.fea import bridge
    _, geri = _dagilim_adlari()
    lm = _yuk_modeli(sonuc)
    assert lm.get('distribution') == geri, lm.get('distribution')
    assert bridge.YUK_GAMMA_ALANI in str(lm.get('fallback_reason')), lm
    assert float((lm.get('end_force') or {}).get('force_n') or 0.0) > 0.0, (
        'kapalı uç kuvveti yok — koşu yeni yük modelinde değil')
    return lm
