# tests — PK3 "CFD kalıntı/bütçe SAHİBİ" onarım bekçileri (ÖH Z5S)
"""Yayımlanan kalıntı, bütçe ve bacak hükmü KİMİN operatöründen?

KAPATILAN KUSUR AİLESİ (ÖH defter P6B1-01/-03/-04/-08)
------------------------------------------------------
Kararlı-hâl çözücüsü MUSCL eğimlerini her iterasyonda CANLI hesaplamaz:
açık yolda plato-dondurma, satır-örtük yolda oturma-tetikli KALICI
dondurma ve eğim tazeleme penceresinin ORTASI eğimleri DONUK taşır. O
hâllerde ``residual_history[-1]`` ile nihai bütçe ŞEMANIN değil, yürüyüşün
taşıdığı operatörün sayılarıdır — ürün ise hükmü o sayıdan veriyor,
üstelik hüküm cümlesi aynı yerde "şema minmod" diyordu.

  P6B1-01  Hüküm cümlesi iki AYRI bacak (debi bandı, boğaz Mach bandı)
           için hüküm yazıyor ama ikisini de tek VE'den (``settled_ok``)
           okuyordu: OTURMUŞ bacak da "OTURMADI" ile suçlanıyordu. Ayrıca
           bacakların KENDİ sayıları (``settle_bands``) uca hiç
           taşınmıyordu — cümle istemcide denetlenemiyordu.
  P6B1-03  Sınırlayıcı donduktan sonra yayımlanan kalıntı donmuş
           operatörün; ``converged`` rozeti şemanın alanını temsil
           etmiyordu (ölçüm: 19.770× fark, şema tolun 86,4 katı).
  P6B1-04  Aynı donmuş/bayat operatör nihai KORUNUM BÜTÇESİNİ de
           besliyordu ve künye sayının sahibini söylemiyordu.
  P6B1-08  Dondurma hiç ateşlemeden de aynı şey oluyordu: 25 iterasyonluk
           Picard penceresinin BAYAT kalıntısı hükmü veriyordu (şema tolun
           97,3 katıyken ``converged=True``).

ONARIMIN ŞEKLİ (bu bekçilerin kilitlediği sözleşme)
---------------------------------------------------
  (a) Her bacağın hükmü KENDİ bandından yazılır (``debi_settled`` /
      ``mach_settled``), bantlar uca taşınır.
  (b) Yayımlanan sayının SAHİBİ adıyla beyan edilir
      (``residual_operator``, ``slope_state``) ve AYNI alanın şema (canlı
      minmod) ölçümü YANINDA yayımlanır (``scheme_residual_norm``,
      ``scheme_mass_balance_rel``, ``scheme_energy_balance_rel``).
  (c) Satır-örtük 2. mertebe yolda hüküm bir ÖZ-TUTARLILIK KAPISINDAN
      geçer: eğimler o anın durumundan tazelendikten sonra da eşiğin
      altında değilse hüküm verilmez, iniş sürer (Picard). Kapının İKİ
      ayağı vardır — döngü içindeki break ayağı ve TAVAN ayağı
      (``scheme_residual_blocks_verdict``): koşu iterasyon tavanında
      biterse, yayımlanan sayı eşiğin altında OLSA BİLE hüküm verilmez.
  (d) Açık yol bu kapının DIŞINDADIR ve bunu ADIYLA beyan eder (§11.3
      bit-özdeşlik referansları oradan geçer). Aşağıda bu kapsam sınırı
      da ölçülür: açık yol beyanı susmaz.

MUTASYON KANITI (ters-değiştirmeli; her mutasyon elle uygulandı, kırmızı
ÖLÇÜLDÜ, sonra TERS düzenlemeyle geri alındı — checkout kullanılmadı,
md5 ile bit-özdeşlik doğrulandı). Sayılar aşağıdaki test gövdelerinde,
sağlam md5'ler ve mutant sonuçları
``docs/scofield/raw/OH/Z5S/pk3/mutasyon.json`` içinde.
"""
import contextlib
import io
import math

import numpy as np
import pytest

from hrma.cfd.euler_core import (precompute_geometry, prim_to_cons_axisym,
                                 residual_axisym)
from hrma.cfd.grid_axisym import build_grid_from_wall
from hrma.cfd.steady import solve_steady_axisym

UC = '/api/cfd/nozzle'

#: Lüle gaz durumu — tests/cfd/conftest.py ile aynı sınıf (γ ve R çağırandan
#: gelir, uydurma yedek yoktur).
LULE = dict(P0=4.0e6, T0=3200.0, gamma=1.2, R=350.0, Pb=2.0e3)
L_CONV, L_DIV = 0.12, 0.18
R_ODA, R_BOGAZ, R_CIKIS = 0.040, 0.025, 0.040
NI, NJ = 60, 12

#: Bayat-pencere izolasyonu: hüküm oturma bacağında takılmasın diye
#: ``settle_tol`` gevşek, DONDURMA ateşlemesin diye ``freeze_settle_tol``
#: erişilmez küçüklükte — kalan tek mekanizma bayat eğim penceresidir.
BAYAT = dict(tol_res=1e-6, settle_tol=1e-3, freeze_settle_tol=1e-30)

BACAKLAR = ('mass_flow_in', 'mass_flow_out', 'throat_mach')

#: Tavan ayağı vakası kaç aday tavanla aranır. Aday tavanlar ÖLÇÜMDEN gelir
#: (aşağıdaki ``tavan_vakasi``): sabit bir iterasyon sayısı yazılsaydı lüle
#: ya da çözücü en küçük değişimde vakayı ıskalar ve bekçi sessizce boşa
#: koşardı. Ölçüm gerekçesi: 60×12 MUSCL örtük yolda kapı 20 kez reddedip
#: 1962'de kabul ediyor, aralıkta onlarca aday var (ilk uygun aday 12
#: denemenin çok içinde kalıyor).
TAVAN_ADAY_SINIRI = 12


def _sessiz(fn, *args, **kwargs):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        return fn(*args, **kwargs)


def _duvar_yaricapi(z):
    """Koni-koni lüle duvarı (tests/cfd/conftest ile aynı biçim)."""
    z = np.asarray(z, dtype=float)
    r = np.where(
        z <= L_CONV,
        R_ODA + (R_BOGAZ - R_ODA) * (z / L_CONV),
        R_BOGAZ + (R_CIKIS - R_BOGAZ) * ((z - L_CONV) / L_DIV))
    return r


def _izgara(ni=NI, nj=NJ):
    z = np.linspace(0.0, L_CONV + L_DIV, ni + 1)
    return build_grid_from_wall(z, _duvar_yaricapi(z), nj)


def _sema_kalintisi(sonuc, izgara, second_order=True):
    """Geri dönen ALANIN, ŞEMANIN CANLI minmod operatörüyle L2 kalıntısı.

    Eğim argümanı BİLEREK verilmez (``slopes=None`` → minmod yeniden
    hesaplanır): sorulan soru tam olarak "yayımlanan sayı şemanın kendi
    operatörünün sayısı mı?"dır. Ölçek çözücününkiyle aynı (ρ0·a0/L),
    böylece iki sayı doğrudan karşılaştırılabilir.
    """
    f = sonuc['fields']
    U = prim_to_cons_axisym(f['rho_kg_m3'], f['u_z_m_s'], f['u_r_m_s'],
                            f['pressure_Pa'], LULE['gamma'])
    res, aux = residual_axisym(U, izgara, LULE['gamma'], LULE['R'],
                               LULE['P0'], LULE['T0'], Pb=LULE['Pb'],
                               second_order=second_order,
                               geom=precompute_geometry(izgara))
    vol = izgara.volume
    olcek = ((LULE['P0'] / (LULE['R'] * LULE['T0']))
             * math.sqrt(LULE['gamma'] * LULE['R'] * LULE['T0'])
             / float(izgara.Z[-1, 0] - izgara.Z[0, 0]))
    norm = float(np.sqrt(np.sum(res[..., 0] ** 2 * vol) / np.sum(vol)) / olcek)
    return norm, aux


def _yayim(sonuc):
    return float(np.asarray(sonuc['residual_history'])[-1])


def _yuruyusun_son_kaydi(sonuc):
    """Yürüyüşün SON KAYDI = ``residual_history[iterations - 1]``.

    ÖH D21 / P6B1-09 ONARIMINDAN SONRA gerekli oldu. Onarımdan ÖNCE
    ``residual_history[-1]`` ile bu SAYI AYNIYDI: geçmişe kayıt U
    güncellenmeden ÖNCE düşüyordu, yani son kayıt bir zaman adımı geride
    kalıyordu ve yayımlanan "son kalıntı" DÖNEN ALANIN değildi (ölçüldü:
    açık yolda %5,74, bu vakada 8,634593e-07 ⟷ 9,056662e-07 = %4,89).
    Onarım dönen alanın kalıntısını geçmişin SONUNA koyduğu için iki sayı
    AYRIŞTI; aşağıdaki P6B1-08 vakası ESKİ hüküm ifadesini arıyor ve o
    ifade yürüyüşün son kaydını okuyordu — bu erişimci onu adıyla verir.
    Vakanın kalibrasyonu böylece DEĞİŞMEZ."""
    gecmis = np.asarray(sonuc['residual_history'], dtype=float)
    return float(gecmis[int(sonuc['iterations']) - 1])


# ---------------------------------------------------------------------------
# Vakalar (module kapsamı — her biri bir çözücü koşusu)
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def izgara():
    return _izgara()


@pytest.fixture(scope='module')
def acik(izgara):
    """AÇIK yol tabanı: bu vakada dondurma ateşlemez, operatör CANLIDIR.

    Ölçüm aygıtının çapası da budur — aşağıdaki karşılaştırmalar bu koşuda
    birebir aynı iki sayı üretmezse ölçüm aygıtı bozuk demektir.
    """
    return _sessiz(solve_steady_axisym, izgara, max_iters=30000, **LULE)


@pytest.fixture(scope='module')
def ortuk_donmus(izgara):
    """ÖRTÜK yol: sınırlayıcı 4253. iterasyonda KALICI donuyor (P6B1-03)."""
    return _sessiz(solve_steady_axisym, izgara, max_iters=30000,
                   time_integrator='line_implicit_j', **LULE)


@pytest.fixture(scope='module')
def ortuk_bayat(izgara):
    """ÖRTÜK yol, dondurma ATEŞLEMEDEN: yalnız bayat pencere (P6B1-08)."""
    return _sessiz(solve_steady_axisym, izgara, max_iters=20000,
                   time_integrator='line_implicit_j', **BAYAT, **LULE)


@pytest.fixture(scope='module')
def tavan_vakasi(izgara, ortuk_bayat):
    """ÖRTÜK yol, kapı REDDEDERKEN iterasyon tavanı (P6B1-08 tavan ayağı).

    Tavan SABİT YAZILMAZ, ölçümden seçilir: ``ortuk_bayat`` koşusunun
    kalıntı geçmişinde tolun ALTINA düşmüş ama koşunun DEVAM ettiği
    iterasyonlar aday tavanlardır (o anlarda ya bantlar oturmamıştır ya
    da öz-tutarlılık kapısı reddetmiştir). Adaylar artan sırada denenir
    ve ESKİ hüküm ifadesinin (üç bant oturdu ∧ yayımlanan kalıntı < tol)
    doğru, şema kalıntısının ise eşiğin ÜSTÜNDE olduğu ilk tavan
    seçilir — yani deliğin fiilen açık olduğu en erken an.

    Döner: (sonuc, sema_kalintisi, tol, tavan, deneme_kaydi).
    """
    tol = float(ortuk_bayat['inputs']['tol_res'])
    stol = float(ortuk_bayat['inputs']['settle_tol'])
    gecmis = np.asarray(ortuk_bayat['residual_history'], dtype=float)
    kabul = int(ortuk_bayat['iterations'])
    adaylar = [int(i) + 1 for i in np.nonzero(gecmis[:kabul - 1] < tol)[0]]
    kayit = []
    for tavan in adaylar[:TAVAN_ADAY_SINIRI]:
        r = _sessiz(solve_steady_axisym, izgara, max_iters=tavan,
                    time_integrator='line_implicit_j', **BAYAT, **LULE)
        b = r['settle_bands']
        # ESKİ hüküm ifadesi YÜRÜYÜŞÜN son kaydını okuyordu (P6B1-09
        # onarımından önce residual_history[-1] ile aynı sayıydı).
        eski_ifade = bool(all(b[a] < stol for a in BACAKLAR)
                          and _yuruyusun_son_kaydi(r) < tol)
        sema, _ = _sema_kalintisi(r, izgara)
        red = int(r['picard_selfconsistency_rejections'])
        kayit.append({'tavan': tavan, 'eski_ifade_converged': eski_ifade,
                      'sema_tolun_kati': sema / tol, 'picard_red': red})
        if eski_ifade and sema >= tol and red >= 1:
            return r, sema, tol, tavan, kayit
    pytest.fail(
        'tavan ayağı vakası kurulamadı — öz-tutarlılık kapısının reddettiği '
        've koşunun tavana dayandığı bir an bulunamadı. Bu bir ürün hükmü '
        'DEĞİL, vakanın kaymasıdır: kapı artık hiç reddetmiyor ya da '
        'yayımlanan kalıntı reddedilen anlarda tolun altına düşmüyor '
        'olabilir. Denenen tavanlar: %r' % (kayit,))


# ===========================================================================
# §1 — ÖLÇÜM AYGITININ ÇAPASI (bu olmadan aşağısı okunamaz)
# ===========================================================================

def test_capa_acik_yolda_yayim_semayla_ozdes(acik, izgara):
    """Dondurmayan açık koşuda yayımlanan kalıntı = alanın şema kalıntısı.

    Aşağıdaki bütün ayrışma iddiaları "belki yeniden hesaplama yanlıştır"
    itirazına açıktır; bu çapa aynı yeniden hesaplamanın ürünün KENDİ
    sayısını birebir ürettiğini her koşuda kanıtlar (ölçüldü 2026-08-28:
    9,862447e-09 ↔ 9,862447e-09, oran 1,0000000005×).
    """
    assert acik['limiter_frozen_at_iter'] is None, (
        'açık yol bu vakada dondurmamalıydı — vaka değişmiş, çapa yeniden '
        'kalibre edilmeli')
    sema, _ = _sema_kalintisi(acik, izgara)
    assert sema == pytest.approx(_yayim(acik), rel=1e-9)
    # Ürünün kendi çapraz ölçümü de aynı sayıyı vermeli (uydurma alan yok).
    assert acik['scheme_residual_norm'] == pytest.approx(sema, rel=1e-9)
    assert acik['residual_operator'] == 'scheme_live_minmod'
    assert acik['slope_state']['walk_operator_is_scheme'] is True


def test_capa_sema_alanlari_bagimsiz_olcumdur(ortuk_bayat, izgara):
    """``scheme_residual_norm`` yürüyüşün sayısının kopyası DEĞİL, gerçek
    bir ikinci ölçümdür (sahte gösterge yasağı).

    ÇEVRİLDİ — ÖH D21 / P6B1-09 (gerekçe ZORUNLU, ÖK-05).

    Eski üçüncü bacak ``scheme_residual_norm != residual_history[-1]``
    diyordu ve KUSURU KORUYORDU: iki sayının ayrı çıkmasının tek sebebi
    yayımlanan son kalıntının DÖNEN ALANA ait olmamasıydı (geçmişe kayıt U
    güncellenmeden önce düşüyordu). Onarım o zaman farkını kapatınca —
    yani yayım artık dönen alanın kalıntısı olunca — bu vakada iki sayı
    ÖZDEŞLEŞTİ (9,056662269004216e-07); bacağı olduğu gibi bırakmak
    "yayımlanan sayı bayat KALSIN" demek olurdu.

    Bacağın KORUDUĞU şey (alan kopyalanmış olabilir) kaybolmadı, daha
    GÜÇLÜ hâliyle duruyor: ``scheme_residual_norm``, çözücünün DIŞINDA
    yeniden hesaplanan ``sema`` ile eşitlenir (kopya bir alan bunu
    geçemez). Buna ek olarak şema sayısının yürüyüşün SON KAYDINDAN
    (eski yayım) farklı olduğu sınanır — "alanı yürüyüşten kopyala"
    gerilemesinin gerçek imzası budur.

    Ölçüldü (bu ağaç): yürüyüşün son kaydı 8,634593e-07 ⟷ dönen alan
    9,056662e-07 (%4,89 fark).
    """
    sema, _ = _sema_kalintisi(ortuk_bayat, izgara)
    assert ortuk_bayat['scheme_residual_norm'] == pytest.approx(sema, rel=1e-9)
    assert ortuk_bayat['slope_state']['walk_operator_is_scheme'] is False
    assert ortuk_bayat['scheme_residual_norm'] != _yuruyusun_son_kaydi(
        ortuk_bayat), (
        'şema alanı YÜRÜYÜŞÜN son kaydıyla bit-aynı — çapraz ölçüm '
        'yapılmamış, alan kopyalanmış olabilir')
    # P6B1-09'un kendi sözleşmesi: yayımlanan son kalıntı DÖNEN alanındır.
    assert ortuk_bayat['residual_history_last_is_returned_field'] is True
    assert _yayim(ortuk_bayat) == pytest.approx(
        float(ortuk_bayat['final_residual_of_returned_field']),
        rel=0.0, abs=0.0)


# ===========================================================================
# §2 — P6B1-03 / P6B1-08: HÜKÜM ŞEMANIN KALINTISIYLA DESTEKLENİR
# ===========================================================================

def test_donmus_operator_hukmu_semayla_desteklenir(ortuk_donmus, izgara):
    """P6B1-03: sınırlayıcı donduktan sonra verilen ``converged`` hükmü,
    alanın ŞEMA kalıntısıyla desteklenmelidir.

    Onarım öncesi ölçüm: donma 4253, hüküm 4452'de, yayım 4,369e-11 ↔ şema
    8,638e-07 = tolun 86,4 katı (fark 19.770×). Onarım sonrası (aynı vaka,
    aynı ayar): hüküm 5512'de veriliyor ve şema kalıntısı 8,531e-09 =
    tolun 0,853 katı — hüküm artık HAK EDİLİYOR.
    """
    assert ortuk_donmus['limiter_frozen_at_iter'] is not None, (
        'vaka dondurmuyor — P6B1-03 bekçisi yeniden kalibre edilmeli')
    tol = ortuk_donmus['inputs']['tol_res']
    sema, _ = _sema_kalintisi(ortuk_donmus, izgara)
    assert not ortuk_donmus['converged'] or sema < tol, (
        f"converged=True yayımlandı (kalıntı {_yayim(ortuk_donmus):.4e} < tol "
        f"{tol:g}) ama alanın ŞEMA kalıntısı {sema:.4e} = tolun "
        f"{sema / tol:.4g} katı — hüküm donmuş operatörün sayısından "
        f"veriliyor. Cümle: {ortuk_donmus['convergence_basis']}")
    # Kapı fiilen ÇALIŞMIŞ olmalı: dondurma altında öz-tutarlılık bedavaya
    # gelmez; en az bir Picard reddi beklenir (ölçüldü: 4 red).
    assert ortuk_donmus['picard_selfconsistency_rejections'] >= 1, (
        'öz-tutarlılık kapısı hiç reddetmemiş — donmuş yolda hüküm bedavaya '
        'geliyorsa kapı fiilen kapalıdır')


def test_bayat_pencere_hukmu_semayla_desteklenir(ortuk_bayat, izgara):
    """P6B1-08: dondurma ATEŞLEMEDEN de hüküm bayat sayıya dayanamaz.

    P6B1-03'ten AYRI mekanizma: sınırlayıcı hiç donmuyor, ayrışmayı tek
    başına eğim tazeleme periyodu (25) üretiyor. Onarım öncesi: 1449
    iterasyon, yayım 9,8538e-07 < tol → ``converged=True``, şema
    9,7286e-05 = tolun 97,3 katı. Onarım sonrası: 1962 iterasyon, şema
    9,8068e-07 = tolun 0,981 katı.
    """
    assert ortuk_bayat['limiter_frozen_at_iter'] is None, (
        'bu vakada dondurma ateşledi — P6B1-08 izolasyonu bozuldu')
    assert ortuk_bayat['converged'] is True, (
        'vaka yakınsamıyor — bekçi yeniden kalibre edilmeli')
    tol = ortuk_bayat['inputs']['tol_res']
    sema, _ = _sema_kalintisi(ortuk_bayat, izgara)
    assert sema < tol, (
        f"converged=True yayımlandı (kalıntı {_yayim(ortuk_bayat):.4e} < tol "
        f"{tol:g}) ama alanın ŞEMA kalıntısı {sema:.4e} = tolun "
        f"{sema / tol:.4g} katı — hüküm bayat pencerenin sayısını okudu")
    assert ortuk_bayat['picard_selfconsistency_rejections'] >= 1


def test_tavan_ayagi_hukmu_geri_ceker(tavan_vakasi):
    """KAPININ TAVAN AYAĞI (P6B1-08, bu partide bulunan ikinci delik).

    Döngü içindeki kapı hükmü yalnız ``break`` yolunda koruyordu; koşu
    iterasyon TAVANINDA bittiğinde kapı hiç sorulmuyor ve hüküm tek başına
    ``res_hist[-1]``den veriliyordu. Kapının kendi gerekçesi
    ("ulaşılamazsa max_iters'ta converged=False ile döner — fail-closed")
    kodda KARŞILIKSIZDI.

    ÖLÇÜLDÜ (2026-08-28, betik olcum_tavan_deligi.py):
      tavan 1800: kapı 6 kez reddetti, koşu tavana dayandı, yayım
                  9,6489e-07 < tol 1e-6 → ESKİ ifade converged=TRUE;
                  şema 2,8399e-05 = tolun 28,4 katı
      tavan 1900: kapı 11 red, yayım 9,0183e-07 → eski TRUE; şema
                  8,2155e-06 = tolun 8,216 katı
      tavan 20000 (kontrol): kapı KABUL etti, şema tolun 0,981 katı →
                  hüküm HAK EDİLDİ (bu bekçinin kontrol ayağı yukarıda)

    Bu bekçi vakanın ÜÇ ayağını birden ister: (1) hüküm geri çekildi,
    (2) sebebi makine-okur alanda ADIYLA duruyor, (3) sayılar SİLİNMEDİ.
    Vakanın kurulabildiği (yani deliğin fiilen açık olduğu) ``tavan_vakasi``
    fikstüründe ölçülür; kurulamazsa bekçi kalibrasyon gerekçesiyle kırılır,
    sessizce yeşil kalmaz.
    """
    sonuc, sema, tol, tavan, kayit = tavan_vakasi
    yayim = _yayim(sonuc)
    red = int(sonuc['picard_selfconsistency_rejections'])
    # (1) Hüküm GERİ ÇEKİLDİ — eski ifade burada converged=True derdi.
    assert sonuc['converged'] is False, (
        f'iterasyon tavanında ({tavan}) biten koşu converged=True yayımladı: '
        f'yayımlanan {yayim:.4e} < tol {tol:g} ve üç bant da oturmuş, ama '
        f'şema kalıntısı {sema:.4e} = tolun {sema / tol:.4g} katı ve '
        f'öz-tutarlılık kapısı {red} kez reddetti — hüküm bayat sayıdan '
        f'veriliyor (tavan ayağı yok). Denemeler: {kayit!r}')
    # (2) Sebep ADIYLA, hem makine alanında hem cümlede.
    assert sonuc['scheme_residual_blocks_verdict'] is True
    assert sonuc['slope_state']['blocks_verdict'] is True
    basis = sonuc['convergence_basis']
    assert 'HÜKÜM VERİLMEDİ' in basis and 'öz-tutarlılık' in basis, (
        'hüküm geri çekildi ama cümle sebebi söylemiyor: %s' % basis)
    # (3) Sayılar SİLİNMEDİ (fail-closed hüküm eksiltir, veri eksiltmez).
    # ÇEVRİLDİ — ÖH D21 / P6B1-09: geçmiş artık ``tavan`` yürüyüş kaydı
    # ARTI dönen alanın kalıntısıdır. Veri EKSİLMEDİ, ARTTI; bekçinin
    # koruduğu şey ("hüküm geri çekilirken sayılar silinmesin") aynen
    # duruyor ve daha keskin: bu vakada yürüyüşün son kaydı 9,0254e-07
    # (tolun ALTINDA görünüyordu) iken DÖNEN ALANIN kalıntısı
    # 1,8477e-04 — yani tolun 184,8 katı, 205 KAT büyük. Eski uzunluk
    # iddiası o sayının hiç yayımlanmamasını kilitliyordu.
    assert len(sonuc['residual_history']) == tavan + 1
    assert sonuc['residual_history_last_is_returned_field'] is True
    assert _yuruyusun_son_kaydi(sonuc) < tol, (
        'vaka kaydı: eski hüküm ifadesi yürüyüşün son kaydını tolun '
        'ALTINDA görüyordu — tavan ayağının varlık sebebi budur')
    assert float(sonuc['residual_history'][-1]) >= tol, (
        'dönen alanın kalıntısı tolun altında — P6B1-09 onarımı bu vakada '
        'artık bir şey göstermiyor, vaka yeniden kalibre edilmeli')
    assert sonuc['mass_flow_in_kg_s'] > 0.0
    assert np.all(np.isfinite(sonuc['fields']['pressure_Pa']))
    assert sonuc['scheme_residual_norm'] == pytest.approx(sema, rel=1e-9)


def test_acik_yol_kapsam_disi_ama_susmuyor(acik, izgara):
    """Kapsam sınırı da BEYANLIDIR: açık yol kapının dışındadır ve bunu
    ADIYLA söyler.

    Açık yolun plato-dondurması minmod limit döngüsünün beyanlı
    tedavisidir ve §11.3 bit-özdeşlik referansları (data/cfd_referans)
    o davranışla dondurulmuştur; hüküm ekseni referans yenilemesi ister
    ve bu partide YAPILMADI. Sessizce geçilmesi kabul edilemez — künye
    kapsamı adlandırmak zorundadır.
    """
    kunye = acik['slope_state']['_basis']
    for anahtar in ('Açık yol', 'kapının', 'YAPILMADI'):
        assert anahtar in kunye, (
            f'slope_state künyesi açık yolun kapsam dışılığını beyan '
            f'etmiyor (aranan: {anahtar!r})')
    assert acik['slope_state']['selfconsistency_gate'] is None
    # Kapsam dışı olmak GÖRÜNMEZ olmak değildir: açık yolda da şema
    # ölçümü ve eşik bayrağı yayımlanır.
    assert 'scheme_residual_norm' in acik
    assert acik['scheme_residual_exceeds_tol'] is False


# ===========================================================================
# §3 — P6B1-01: BACAK HÜKMÜ KENDİ BANDINDAN
# ===========================================================================

def test_bacak_hukmu_oturmus_bacagi_suclamaz(izgara):
    """Cümledeki her bacak hükmü, O BACAĞIN kendi bandından gelmeli.

    VAKA KURULUMU: önce erişilemez ``settle_tol`` ile bantlar ölçülür,
    sonra en küçük ve en büyük bandın GEOMETRİK ORTASI eşik olarak verilip
    aynı yörünge yeniden koşulur — böylece en az bir bacak oturmuş, en az
    biri oturmamış olur. Onarım öncesi ölçüm (2026-08-28): settle_tol
    6,844e-04; ``throat_mach`` 5,369e-04 (OTURDU), ``mass_flow_in``
    7,970e-04 ve ``mass_flow_out`` 8,725e-04 (OTURMADI) — ürün cümlesi
    buna rağmen "boğaz Mach bandı OTURMADI" yazıyordu.
    """
    import re

    ortak = dict(max_iters=1000, tol_res=1e-14, **LULE)
    bacaklar = BACAKLAR
    olcum = _sessiz(solve_steady_axisym, izgara, settle_tol=1e-30, **ortak)
    b0 = olcum['settle_bands']
    tol = float(np.sqrt(min(b0[a] for a in bacaklar)
                        * max(b0[a] for a in bacaklar)))
    sonuc = _sessiz(solve_steady_axisym, izgara, settle_tol=tol, **ortak)
    bant = sonuc['settle_bands']
    oturan = {a: bant[a] < tol for a in bacaklar}
    assert any(oturan.values()) and not all(oturan.values()), (
        f'vaka bacakları ayırmıyor (bantlar {bant}, tol {tol:.4e})')

    m = re.search(r'debi bandı \(giriş/çıkış, son \d+ iter\) '
                  r'(OTURDU|OTURMADI), boğaz Mach bandı (OTURDU|OTURMADI)',
                  sonuc['convergence_basis'])
    assert m, ('hüküm cümlesinin bacak biçimi değişmiş: %s'
               % sonuc['convergence_basis'])
    debi_gercek = ('OTURDU' if (oturan['mass_flow_in']
                                and oturan['mass_flow_out']) else 'OTURMADI')
    mach_gercek = 'OTURDU' if oturan['throat_mach'] else 'OTURMADI'
    assert m.group(2) == mach_gercek, (
        f"boğaz Mach bacağı: cümle {m.group(2)}, bandın kendisi "
        f"{bant['throat_mach']:.4e} "
        f"{'<' if oturan['throat_mach'] else '>='} settle_tol {tol:.4e} → "
        f"{mach_gercek}. Cümle: {sonuc['convergence_basis']}")
    assert m.group(1) == debi_gercek, (
        f"debi bacağı: cümle {m.group(1)}, bantlar giriş "
        f"{bant['mass_flow_in']:.4e} / çıkış {bant['mass_flow_out']:.4e}, "
        f"settle_tol {tol:.4e} → {debi_gercek}")


def test_bacak_hukmu_uc_bandin_VEsi_olmaya_devam_eder(izgara):
    """BEYAN bacak bacak ayrıldı ama HÜKÜM hâlâ ÜÇ bandın VE'sidir.

    Onarımın gerilemesi iki yönlüdür: (a) cümle yanlış bacağı suçlar
    (yukarıdaki bekçi), (b) hüküm gevşer ve bir bacak oturmadan
    ``converged=True`` çıkar. Bu bekçi ikinciyi kapatır.
    """
    ortak = dict(max_iters=1000, tol_res=1e-14, **LULE)
    bacaklar = BACAKLAR
    olcum = _sessiz(solve_steady_axisym, izgara, settle_tol=1e-30, **ortak)
    b0 = olcum['settle_bands']
    tol = float(np.sqrt(min(b0[a] for a in bacaklar)
                        * max(b0[a] for a in bacaklar)))
    sonuc = _sessiz(solve_steady_axisym, izgara, settle_tol=tol, **ortak)
    bant = sonuc['settle_bands']
    assert not all(bant[a] < tol for a in bacaklar), (
        'vaka bir bacağı oturtmuyor olmalıydı — kalibrasyon bozuldu')
    assert sonuc['converged'] is False, (
        'bacaklardan biri oturmamışken hüküm verildi — üçlü VE gevşemiş '
        f'(bantlar {bant}, settle_tol {tol:.4e})')


# ===========================================================================
# §4 — UÇ (app.py /api/cfd/nozzle): SAYILAR VE KÜNYE İSTEMCİYE ULAŞIR
# ===========================================================================

@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _kontur():
    from hrma.engines.nozzle_design import sample_nozzle_inner_contour
    pts, _meta = _sessiz(sample_nozzle_inner_contour, {
        'chamber_diameter': 0.050, 'throat_diameter': 0.030,
        'exit_diameter': 0.075,
        'nozzle_angles': {'nozzle_type': 'conical',
                          'convergent_half_angle_deg': 30,
                          'divergent_half_angle_deg': 15},
    })
    return {'points': [[float(z) / 1000.0, float(r) / 1000.0]
                       for z, r in pts]}


@pytest.fixture(scope='module')
def uc_yanit(client):
    r = _sessiz(client.post, UC, json={
        'nozzle_contour': _kontur(), 'P0_Pa': 2.0e6, 'T0_K': 3000.0,
        'gamma': 1.2, 'R_J_per_kgK': 350.0, 'P_ambient_Pa': 20000.0,
    })
    assert r.status_code == 200, r.get_data(as_text=True)[:800]
    return r.get_json()['cfd']


def test_uc_bacak_bantlarini_yayimlar(uc_yanit):
    """P6B1-01 (uç ayağı): cümlenin bacak hükmü uçtaki SAYILARLA
    denetlenebilir olmalı — üç bant + pencere + eşik yanıtta.

    Ölçüldü (onarım öncesi): ``cfd`` bloğunun 30 anahtarı içinde
    ``settle_bands`` YOKTU; istemci "boğaz Mach bandı OTURMADI" cümlesini
    doğrulayamıyordu.
    """
    assert 'settle_bands' in uc_yanit, (
        'uç bacak bantlarını yayımlamıyor (anahtarlar: %s)'
        % sorted(uc_yanit))
    b = uc_yanit['settle_bands']
    for bacak in ('mass_flow_in', 'mass_flow_out', 'throat_mach'):
        assert isinstance(b[bacak], (int, float)), (
            f'settle_bands.{bacak} sayısal olarak yayımlanmıyor: {b[bacak]!r}')
    assert b['window'] == uc_yanit['iterations'] or b['window'] > 0
    assert b['tol'] > 0.0
    # Cümlenin bacak hükmü, YAYIMLANAN bantlarla tutarlı olmalı — uç,
    # çözücünün cümlesini taşırken sayıları başka bir koşudan almıyor.
    import re
    m = re.search(r'debi bandı \(giriş/çıkış, son \d+ iter\) '
                  r'(OTURDU|OTURMADI), boğaz Mach bandı (OTURDU|OTURMADI)',
                  uc_yanit['convergence_basis'])
    assert m, uc_yanit['convergence_basis']
    beklenen_mach = 'OTURDU' if b['throat_mach'] < b['tol'] else 'OTURMADI'
    assert m.group(2) == beklenen_mach, (
        f"uçtaki cümle {m.group(2)} diyor ama yayımlanan boğaz Mach bandı "
        f"{b['throat_mach']:.4e} / tol {b['tol']:.4e} → {beklenen_mach}")


def test_uc_butce_kunyesi_operatoru_adlandirir(uc_yanit):
    """P6B1-04: bütçe künyesi, sayının hangi eğim sisteminden geldiğini
    SÖYLEMELİ; şemanın kendi ölçümü YANINDA durmalı.

    Ölçüldü (onarım öncesi): ``budget._basis`` içinde "dondur"/"donmuş"/
    "eğim"/"slope"/"frozen" geçen tek kelime YOKTU; dondurma yalnız
    ``limiter_frozen_at_iter`` olarak görünüyordu ve hüküm cümlesi aynı
    koşuda "şema minmod" diyordu.
    """
    b = uc_yanit['budget']
    metin = ' '.join(str(v) for v in b.values()).lower()
    anahtarlar = ('dondur', 'donmuş', 'donmus', 'frozen', 'eğim', 'egim',
                  'slope')
    assert any(k in metin for k in anahtarlar), (
        'budget künyesi nihai bütçenin hangi eğim sisteminden ölçüldüğünü '
        'söylemiyor (aranan: %s)' % ', '.join(anahtarlar))
    assert 'slope_state' in b and 'published_operator' in b['slope_state']
    for alan in ('scheme_mass_balance_rel', 'scheme_energy_balance_rel'):
        assert alan in b and isinstance(b[alan], (int, float)), (
            f'şemanın kendi bütçesi yanında yayımlanmıyor: {alan}')


def test_uc_operator_kimligi_ve_hukum_alanlari(uc_yanit):
    """Uç, sayının sahibini ve hüküm kapısının durumunu makine-okur
    biçimde yayımlamalı (künye kazanılır; istemci cümle ayrıştırmaz)."""
    assert uc_yanit['residual_operator'] in (
        'scheme_live_minmod', 'frozen_slopes', 'stale_refresh_window')
    assert isinstance(uc_yanit['scheme_residual_norm'], (int, float))
    assert isinstance(uc_yanit['scheme_residual_exceeds_tol'], bool)
    assert isinstance(uc_yanit['scheme_residual_blocks_verdict'], bool)
    assert isinstance(uc_yanit['picard_selfconsistency_rejections'], int)
    ss = uc_yanit['slope_state']
    assert ss['published_operator'] == uc_yanit['residual_operator']
    assert ss['scheme_residual_norm'] == pytest.approx(
        uc_yanit['scheme_residual_norm'], rel=0, abs=0)
    # Hüküm ile kapı ÇELİŞEMEZ: hüküm verildiyse kapı engellememiştir.
    if uc_yanit['converged']:
        assert uc_yanit['scheme_residual_blocks_verdict'] is False


def test_uc_hukum_cumlesi_operatoru_yaniltmaz(uc_yanit):
    """Hüküm cümlesi, yayımlanan kalıntının sahibini YANLIŞ söyleyemez.

    Onarım öncesi cümle dondurma dalında "şema minmod" diyerek tersini
    ima ediyordu. Artık: operatör canlıysa cümle bunu söyler, değilse
    UYARI yazar ve şemanın kendi sayısını yanına koyar.
    """
    basis = uc_yanit['convergence_basis']
    if uc_yanit['residual_operator'] == 'scheme_live_minmod':
        assert 'ŞEMANIN canlı minmod operatörünündür' in basis
        assert 'UYARI' not in basis
    else:
        assert 'UYARI' in basis and 'ŞEMANIN DEĞİL' in basis
        assert f"{uc_yanit['scheme_residual_norm']:.3e}" in basis, (
            'uyarı cümlesi şemanın kendi sayısını taşımıyor')
    assert f"residual_operator={uc_yanit['residual_operator']}" in basis
