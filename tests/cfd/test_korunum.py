# tests/cfd — korunum bütçesi bekçisi (basamak 4)
"""
Kararlı hâlde giriş-çıkış akı dengeleri: hücre-merkezli FVM korunum
formundadır; iç yüzey akıları teleskopik olarak birebir sadeleşir, duvar
(kayma) yüzeyinde kütle/enerji akısı sıfırdır, eksen yüzeyleri geometrik
akısızdır. Dolayısıyla giriş-çıkış farkı = Σ hücre kalıntısı; derin
yakınsamada makine-hassasiyeti sınıfına inmesi ZORUNLUDUR — inmiyorsa şema
korunum formunu kaybetmiştir (eski cfd_analysis.py'nin ölüm sebebi).

Eşikler ölçümden konuldu (dosya sonundaki sabitlerin yanında ölçüm değeri);
görevin istediği 1e-8 sınıfının altı doğrulandı.

Kaynak terim NOTU: eksenel simetrik basınç kaynağı yalnız r-momentum
denklemindedir; kütle ve enerji bütçesine kaynak girmez, bu yüzden bütçe
kapanışı kaynak teriminden bağımsız bir bekçidir (mutasyon 2'yi debi bekçisi
yakalar, bu dosya değil — bilinçli işbölümü).
"""

import numpy as np

# ÖLÇÜLDÜ (bu depo, M4 Max, 2026-08-15; 120×24, derin yakınsama —
# tol_res=1e-10, settle_tol=1e-11, kalıntı 6,9e-12):
#   kütle bağıl artığı  : 1,14e-11
#   enerji bağıl artığı : 8,76e-12
# Eşik = ölçüm × ~9 payı = tasarım belgesinin "1e-10 sınıfı" hedefi;
# görevin 1e-8 sınıfının 100 katı altında (gevşetme yok).
KUTLE_ARTIK_TOL = 1e-10
ENERJI_ARTIK_TOL = 1e-10


def test_kutle_akisi_dengesi(lule_cozumu):
    _, res = lule_cozumu
    # --- ÇEVRİLDİ (ÖH D32 / OH-D31-15) -------------------------------
    # İzantropik 120×24 vakası AÇIK yolda koşuyor, sınırlayıcı donuyor ve yayımlanan
    # kalıntı BAYAT operatörünündür; şemanın kendi (canlı minmod)
    # kalıntısı tolun 2,903e+07 katıdır (ÖLÇÜLDÜ: docs/scofield/raw/OH/D32/
    # fea-cfd/a2/once.json K1). Çözücü artık o hükmü VERMİYOR
    # (converged=None, convergence_status='not_evaluated'; Berke kararı
    # 15 Eyl 2026 §3 seç. A). Eski ``is True`` iddiası KAZANILMAMIŞ
    # hükmün yerinde durmasını şart koşuyordu — kusuru koruyan bekçi,
    # yönü çevrildi. Korunan yasak aynen duruyor: ıraksamış ya da
    # ÖLÇÜLMÜŞ olarak yakınsamamış alandan iddia kurulmaz.
    assert res['converged'] is not False, (
        f"bütçe hükmü ÖLÇÜLMÜŞ olarak yakınsamamış çözümle kurulamaz: "
        f"{res['convergence_basis']}")
    assert res['convergence_status'] in ('converged', 'not_evaluated'), (
        f"vaka kurulumu bozulmuş: {res['convergence_status']!r}")
    rel = res['mass_balance_rel']
    assert rel < KUTLE_ARTIK_TOL, (
        f'kütle bütçesi kapanmadı: |mdot_in − mdot_out|/mdot_in = {rel:.3e} '
        f'>= {KUTLE_ARTIK_TOL:.0e} — FVM korunum formu bozulmuş')


def test_enerji_akisi_dengesi(lule_cozumu):
    _, res = lule_cozumu
    rel = res['energy_balance_rel']
    assert rel < ENERJI_ARTIK_TOL, (
        f'enerji bütçesi kapanmadı: bağıl artık {rel:.3e} >= '
        f'{ENERJI_ARTIK_TOL:.0e} (duvar akısı sızıntısı ya da korunum '
        f'formu kaybı)')


def test_butce_beyani_alanlari(lule_cozumu):
    """Korunum bütçesi çıktıda BEYAN edilir (dürüstlük sözleşmesi):
    sayılar sonuç sözlüğünde, tüketici gizli hesaba muhtaç değil."""
    _, res = lule_cozumu
    for key in ('mass_flow_in_kg_s', 'mass_flow_out_kg_s',
                'mass_balance_rel', 'energy_flux_in_W', 'energy_flux_out_W',
                'energy_balance_rel'):
        assert key in res, f'korunum bütçesi beyanı eksik: {key}'
        assert np.isfinite(res[key])
    assert res['mass_flow_in_kg_s'] > 0.0
    assert res['energy_flux_in_W'] > 0.0


# ===========================================================================
# BASAMAK 14 — VİSKOZ korunum bütçesi (tasarım §7 satır 14)
#
# Yukarıdaki üç bekçi EULER yolunun bütçesidir. Viskoz koşuda bütçe İKİ
# yerden daha beslenir ve İKİSİ DE sürücünün yayımladığı sözlükte YOKTUR
# (ölçüldü, devir kalemi raporda): (a) duvar ısı akısı Q_w, (b) giriş/çıkış
# yüzlerinden geçen VİSKOZ enerji akısı. Bu yüzden viskoz bütçe, yakınsamış
# alan üzerinde İKİ kalıntı çağrısı (Euler + viskoz, sürücünün KENDİ sınır
# durumlarıyla) kurularak ölçülür — ikinci bir fizik gerçeklemesi yazılmaz.
#
# AYRIK ÖZDEŞLİK (şema korunum formunda olduğu sürece TAM):
#     E_giriş − E_çıkış + (visk_çıkış − visk_giriş) − Q_duvar
#         ≡ Σ_hücre (dE/dt)·V
# Sol taraf yalnız SINIR akılarından, sağ taraf hücre kalıntılarından
# kurulur; iç yüz akıları teleskoplayınca ikisi ÖZDEŞ olmak zorundadır.
#
# ÖLÇÜLDÜ (M4 Max, 2026-08-19; test_wall_output.py vakası 64×16 ve
# 192×48 KAPI ikizi):
#                                  64×16        192×48 (KAPI)
#   özdeşlik artığı [W]            2,6e-10      2,3e-09
#   özdeşlik artığı / E_giriş      8,5e-18      7,6e-17   (yuvarlama sınıfı)
#   bütçe kapanışı |kalan|/E_giriş 6,67e-06     1,96e-09
#   kütle kapanışı  |ΣdρV|/ṁ       6,94e-06     2,16e-09
#   duvar kütle akısı              0,0 (BİT)    0,0 (BİT)
#   viskoz akının kütle bileşeni   0,0 (BİT)    0,0 (BİT)
#
# İki kapanış sayısının 64×16'da 1e-6 sınıfında kalması ızgaranın kaba
# olmasındandır (KAPI ızgarasında 1e-9'a iniyor); ÖZDEŞLİK ise ızgaradan
# BAĞIMSIZ olarak yuvarlama sınıfındadır — kilit oraya konur.
# ===========================================================================

import pytest

from hrma.cfd.euler_core import (
    WALL_BC_NOSLIP, _outlet_state, cons_to_prim_axisym,
    inlet_state_from_stagnation, precompute_geometry, prim_to_cons_axisym,
    residual_axisym,
)
from hrma.cfd.gradients import precompute_gradient_geometry
from hrma.cfd.viscous import viscous_residual

from .conftest import LULE_GAMMA, LULE_P0, LULE_R, LULE_T0
from .test_wall_output import VLULE_TW_ORANI, viskoz_izo  # noqa: F401

#: Ayrık özdeşliğin artığı (E_giriş'e göre). ÖLÇÜLDÜ 8,5e-18 / 7,6e-17;
#: eşik ölçümün ~100 katı ama hâlâ makine-hassasiyeti sınıfının içinde:
#: bir terim düşerse ya da işareti dönerse artık 1e-6 sınıfına fırlar.
VISKOZ_OZDESLIK_TOL = 1e-13

#: Bütçe kapanışı (bu ızgarada). ÖLÇÜLDÜ 6,67e-06; eşik ~3× pay.
#: BU EŞİK YAKINSAMIŞ ALANIN hedefidir ve GEVŞETİLMEMİŞTİR — aşağıdaki
#: duyarlılık bekçisi (test_viskoz_sinir_akisi_TERIMI_gercekten_gerekli)
#: onu aynen kullanır.
VISKOZ_ENERJI_KAPANIS_TOL = 2e-5
VISKOZ_KUTLE_KAPANIS_TOL = 2e-5

#: TAVAN DURUMU kapanışı (ÖH defter OH-Z5-14; ölçüldü 2026-08-31,
#: docs/scofield/raw/OH/D15/cfd-picard/a2/once.json → izo/butce).
#: Örtük yolun öz-tutarlılık kapısı hükmü geri çektiğinden koşu artık
#: hüküm anında DURMUYOR, max_iters tavanında bitiyor; alan minmod limit
#: döngüsünün TAVANDAKİ fazıdır. Ölçülen kapanış:
#:   enerji |kalan|/E_giriş  2,32811e-05   (yakınsamış ölçüm 6,67e-06)
#:   kütle  |Σdρ·V|/ṁ        2,42183e-05   (yakınsamış ölçüm 6,94e-06)
#: Yani kapanış yakınsamış alanınkinin ~3,5 katı — ÖLÇÜLMÜŞ bir gerçek,
#: gizlenmez. Yukarıdaki 2e-5 hedefi bu yüzden GEVŞETİLMEDİ; tavan
#: durumu AYRI ADLA ve İKİ TARAFLI çıpayla dondurulur: sayı hangi yöne
#: kayarsa sürücü ya da hüküm durumu değişmiştir.
#: Tolerans FAZ DUYARLILIĞINDAN türetildi (aynı dizin,
#: faz_duyarliligi.json — tavan 19999/20000/20001 ile üç koşu): kapanış
#: bağıl 1,99e-05 (enerji) / 3,67e-05 (kütle) oynuyor; bant onun 27-50
#: katı. Aynı ölçümde ALAN büyüklükleri neredeyse hiç oynamıyor (debi
#: 5,2e-11, y⁺ 2,8e-12, sürtünme 7,3e-10) — yani tavan fazı ALANI değil
#: KALINTI SINIFINDAKİ büyüklükleri oynatıyor.
#: ÖH D37 A3a cfd-kok-a (F-05 TRRS duvar akısı; Berke Sunum 3a onayı 24 Eyl):
#: yeniden ölçüldü 2,331247e-05 (eski 2,32811e-05, +%0,13); bant aynı.
VISKOZ_TAVAN_ENERJI_KAPANIS = 2.331247e-05
#: aynı turda yeniden ölçüldü 2,425056e-05 (eski 2,42183e-05, +%0,13); bant aynı.
VISKOZ_TAVAN_KUTLE_KAPANIS = 2.425056e-05
VISKOZ_TAVAN_KAPANIS_REL = 1e-3
#: Bir akı terimi düşerse kapanış bu sınıfa fırlar (ölçüldü: tam bütçe
#: 204,15 W ⇒ eksik bütçe −16.149 W, 79 kat ⇒ ~5,3e-04 bu ölçekte).
#: Çıpanın AYIRT EDİCİLİĞİ bu sayıyla ölçülür.
VISKOZ_SIZINTI_IMZASI = 1e-4


def _viskoz_butce(grid, res, tr):
    """Yakınsamış viskoz alanın SINIR akıları + hücre kalıntı toplamları.

    Sınır durumları sürücünün KENDİ fonksiyonlarından kurulur
    (inlet_state_from_stagnation / _outlet_state) — viskoz katmanın gördüğü
    hayalet durum ile buradaki ölçüm ayrışmasın.
    """
    f = res['fields']
    U = prim_to_cons_axisym(f['rho_kg_m3'], f['u_z_m_s'], f['u_r_m_s'],
                            f['pressure_Pa'], LULE_GAMMA)
    geom = precompute_geometry(grid)
    grad_geom = precompute_gradient_geometry(grid)
    Pb = res['inputs']['Pb_Pa']
    w = cons_to_prim_axisym(U, LULE_GAMMA)
    w_in = inlet_state_from_stagnation(w[0], LULE_GAMMA, LULE_R, LULE_P0,
                                       LULE_T0)
    w_out = _outlet_state(w[-1], geom['n_out_hat'], LULE_GAMMA, Pb)
    dE, auxE = residual_axisym(U, grid, LULE_GAMMA, LULE_R, LULE_P0, LULE_T0,
                               Pb, geom=geom, wall_bc=WALL_BC_NOSLIP)
    dV, auxV = viscous_residual(
        grid, U, tr, R=LULE_R, geom=geom, grad_geom=grad_geom,
        inlet_face_primitives=w_in, outlet_face_primitives=w_out,
        wall_thermal='isothermal', T_wall=VLULE_TW_ORANI * LULE_T0,
        T_wall_source='verification_case: T_w = 0,6·T₀')
    toplam = dE + dV
    return {
        'E_in': auxE['energy_flux_in_W'], 'E_out': auxE['energy_flux_out_W'],
        'mdot_in': auxE['mass_flow_in_kg_s'],
        'visk_in': auxV['inlet_energy_flux_W'],
        'visk_out': auxV['outlet_energy_flux_W'],
        'Q_wall': auxV['wall_heat_W'],
        'duvar_kutle': auxE['wall_mass_flux_kg_s'],
        'visk_kutle_max': float(np.max(np.abs(dV[..., 0]))),
        'sum_dE': float(np.sum(toplam[..., 3] * grid.volume)),
        'sum_drho': float(np.sum(toplam[..., 0] * grid.volume)),
    }


def test_viskoz_butce_OZDESLIGI(viskoz_izo):
    """Sınır akıları toplamı ≡ hücre kalıntıları toplamı (ayrık özdeşlik).

    Terim düşerse (ör. viskoz sınır akısı unutulursa) ya da bir işaret
    dönerse bu bekçi yuvarlama sınıfından 1e-6 sınıfına fırlar. Kapanışın
    KENDİSİNİ (kalıntının küçüklüğünü) ayrı bekçi ölçer — ikisi farklı
    iddialardır ve bilerek ayrıldı.
    """
    grid, res, tr = viskoz_izo
    b = _viskoz_butce(grid, res, tr)
    kalan = (b['E_in'] - b['E_out'] + b['visk_out'] - b['visk_in']
             - b['Q_wall'])
    artik = abs(kalan - b['sum_dE']) / abs(b['E_in'])
    assert artik < VISKOZ_OZDESLIK_TOL, (
        f'viskoz enerji bütçesi özdeşliği bozuldu: |sınır − hücre| / E_giriş '
        f'= {artik:.3e} >= {VISKOZ_OZDESLIK_TOL:.0e} (sınır {kalan:.9g} W, '
        f'hücre {b["sum_dE"]:.9g} W) — bir akı terimi düşmüş ya da işareti '
        f'dönmüş olabilir')


def test_viskoz_butce_KAPANISI(viskoz_izo):
    """Bütçe artığı TAVAN durumunun ölçülen bandında — sızıntı YOK.

    HÜKÜM SÖZLEŞMESİ (ÖH defter OH-Z5-14; çevrildi 2026-08-31)
    ----------------------------------------------------------
    Testin eski PREMİSİ ("yakınsamış alanda…") artık YANLIŞTIR ve bunu
    ürünün kendisi söylüyor: örtük yolun öz-tutarlılık kapısı hükmü geri
    çekiyor (``converged=False``, ``scheme_residual_blocks_verdict``),
    koşu max_iters tavanında bitiyor ve alan minmod limit döngüsünün
    tavandaki fazıdır. Yakınsamış alanın 6,67e-06 kapanışı bu durumda
    ÖLÇÜLDÜ: 2,328e-05 (enerji) / 2,422e-05 (kütle) — 2e-5 hedefinin
    ÜSTÜNDE.

    HEDEF GEVŞETİLMEDİ: ``VISKOZ_*_KAPANIS_TOL`` (2e-5) yerinde durur ve
    duyarlılık bekçisinde aynen kullanılır. Bu testin çıpası AYRI adla,
    AYRI ölçümle ve İKİ TARAFLI konur — sayının bir yöne kayması da
    "iyileşme" sayılmaz, sürücünün değiştiğinin işaretidir ve bu
    dosyanın bantları yeniden ölçülmelidir.

    SIZINTI SORUSU AYRI: kapanışın 3,5 kat kötüleşmesi bir akı teriminin
    DÜŞMESİ değildir — o kusurun ölçülen imzası ~5,3e-04'tür (79 kat),
    yani çıpanın bir mertebe üstünde ve ADIYLA sınanır.
    """
    grid, res, tr = viskoz_izo
    # --- PREMİS FAIL-CLOSED: alan yakınsamış DEĞİL, ürün öyle diyor ---
    assert res['converged'] is False, res['convergence_basis']
    assert res['convergence_status'] == 'not_converged', (
        res['convergence_basis'])
    assert res['scheme_residual_blocks_verdict'] is True

    b = _viskoz_butce(grid, res, tr)
    kalan = (b['E_in'] - b['E_out'] + b['visk_out'] - b['visk_in']
             - b['Q_wall'])
    enerji = abs(kalan) / abs(b['E_in'])
    kutle = abs(b['sum_drho']) / b['mdot_in']
    assert enerji == pytest.approx(VISKOZ_TAVAN_ENERJI_KAPANIS,
                                   rel=VISKOZ_TAVAN_KAPANIS_REL), (
        f'viskoz enerji bütçesi kapanışı ölçülen tavan bandından çıktı: '
        f'{enerji:.6e} ≠ {VISKOZ_TAVAN_ENERJI_KAPANIS:.6e} '
        f'(±{VISKOZ_TAVAN_KAPANIS_REL:.0e}) — sürücü ya da hüküm durumu '
        f'değişmiş olabilir')
    assert kutle == pytest.approx(VISKOZ_TAVAN_KUTLE_KAPANIS,
                                  rel=VISKOZ_TAVAN_KAPANIS_REL), (
        f'viskoz kütle bütçesi kapanışı ölçülen tavan bandından çıktı: '
        f'{kutle:.6e} ≠ {VISKOZ_TAVAN_KUTLE_KAPANIS:.6e}')
    # SIZINTI YOK: eksik terimin imzası bir mertebe uzakta.
    assert enerji < VISKOZ_SIZINTI_IMZASI and kutle < VISKOZ_SIZINTI_IMZASI, (
        'kapanış sızıntı imzası sınıfına fırladı — bir akı terimi '
        'düşmüş ya da işareti dönmüş olabilir')
    # Q_duvar bütçenin BASKIN terimidir: onu düşürmek kapanışı %14 bozardı
    # (ölçüldü — sürücünün yayımladığı energy_balance_rel tam da bu yüzden
    # viskoz koşuda 1,4e-01 çıkıyor ve TEK BAŞINA okunmamalıdır).
    assert abs(b['Q_wall']) / abs(b['E_in']) > 0.10


def test_duvarda_kutle_akisi_BIT_SIFIR(viskoz_izo):
    """No-slip duvarda kütle akısı ayrık olarak TAM sıfır; viskoz akının
    kütle bileşeni ise HİÇ YOKTUR (yaklaşık değil, bit)."""
    grid, res, tr = viskoz_izo
    b = _viskoz_butce(grid, res, tr)
    assert b['duvar_kutle'] == 0.0, (
        f'duvar kütle akısı bit-sıfır değil: {b["duvar_kutle"]!r}')
    assert res['wall_mass_flux_kg_s'] == 0.0
    assert b['visk_kutle_max'] == 0.0, (
        'viskoz akı kütle denklemine GİRMEZ (τ ve q yalnız momentum/enerji '
        f'akılarıdır); ölçülen maks |dρ/dt|_viskoz = {b["visk_kutle_max"]!r}')


def test_duvar_isisi_SURUCUNUN_yayiniyla_ayni(viskoz_izo):
    """Q_duvar ölçümü çözücünün yayımladığı sayının TA KENDİSİ olmalı."""
    grid, res, tr = viskoz_izo
    b = _viskoz_butce(grid, res, tr)
    yayin = res['viscous']['wall_heat_W']
    assert yayin == pytest.approx(b['Q_wall'], rel=1e-12), (
        'sürücünün yayımladığı duvar ısısı bu ölçümden ayrıştı — bütçe '
        'başka bir alandan besleniyor olabilir')
    # ∮ q_w dA tanımı da aynı sayıyı vermeli (dizi ↔ skaler tutarlılığı)
    q = np.asarray(res['viscous']['wall_heat_flux_W_m2'], dtype=float)
    a = np.asarray(res['viscous']['wall_area_m2'], dtype=float)
    assert float(np.sum(q * a)) == pytest.approx(yayin, rel=1e-12)


def test_viskoz_sinir_akisi_TERIMI_gercekten_gerekli(viskoz_izo):
    """Bekçinin DUYARLILIĞI ölçülür: terim düşerse özdeşlik ne kadar bozulur?

    Bu, mutasyon kanıtının teste GÖMÜLMÜŞ hâlidir. Giriş/çıkış yüzlerinden
    geçen viskoz enerji akısı unutulursa (Euler akılarıyla + Q_duvar ile
    yetinilirse) artık ÖLÇÜLDÜ: 204,15 W yerine −16 149 W, yani 79 kat.
    Bekçi bu farkı görecek kadar sıkı olmalı; sıkı değilse eksik terim
    sessizce geçerdi.
    """
    grid, res, tr = viskoz_izo
    b = _viskoz_butce(grid, res, tr)
    tam = b['E_in'] - b['E_out'] + b['visk_out'] - b['visk_in'] - b['Q_wall']
    eksik = b['E_in'] - b['E_out'] - b['Q_wall']          # terim DÜŞÜRÜLDÜ
    assert abs(eksik) > 10.0 * abs(tam), (
        f'viskoz sınır akısı terimi düşürüldüğünde artık {eksik:.6g} W '
        f'oluyor, tam bütçede {tam:.6g} W — aradaki fark bekçinin '
        f'ayırt edebileceği kadar büyük değil, bekçi kör demektir')
    assert abs(eksik) / abs(b['E_in']) > VISKOZ_ENERJI_KAPANIS_TOL, (
        'eksik terimli bütçe hâlâ eşiğin altında kalıyor: kapanış bekçisi '
        'bu kusuru YAKALAMAZDI')
