# tests/cfd — gaz taşınım sarmalayıcısının bekçileri (viskoz evre V0)
"""
``hrma/cfd/gas_transport.py`` bir SARMALAYICIDIR: yeni viskozite yasası,
yeni Prandtl tanımı yazmaz. Tasarım belgesi docs/mimari/cfd-viskoz-
tasarimi.md §5.8 bağlayıcıdır:

    - çağıran μ_ref/cp/Pr verdiyse  → μ(T) = μ_ref·(T/T_ref)^n
      (değer T_ref'te KORUNUR, sıcaklık değişimi DEPONUN üs yasasıyla),
    - vermediyse                    → doğrudan ``_get_gas_properties``
      zinciri (hrma/analysis/heat_transfer_analysis.py),
    - her iki durumda k_eff = cp·(μ/Pr + μ_t/Pr_t), Pr = 4γ/(9γ−5).

Bu dosyanın ASIL işi tek-kaynak sözleşmesini ölçmektir: üs (0,6),
ön çarpan (1,184e-7) ve donmuş Prandtl bağıntısı bu modülde YENİDEN
YAZILMAZ; ölçülerek/çağrılarak depodan gelir. Bu yüzden bekçilerin bir
kısmı davranış değil KAYNAK ölçer (AST + depo taraması) — kopya yazıldığı
anda kırmızıya döner.

Depo gerçeği (ÖLÇÜLDÜ, 18 Ağu 2026):
    heat_transfer_analysis.py:283  μ = 1.184e-7·MW^0.5·T^0.6   (tek yer)
    heat_transfer_analysis.py:268  Pr = 4γ/(9γ−5)              (tek yer)
    depoda Sutherland yasası HİÇ YOK (grep boş).
"""

import ast
import math
import re
from pathlib import Path

import numpy as np
import pytest

from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
from hrma.cfd import gas_transport as gt

ROOT = Path(__file__).resolve().parents[2]
KAYNAK_YOLU = ROOT / 'hrma' / 'cfd' / 'gas_transport.py'
KAYNAK_METNI = KAYNAK_YOLU.read_text(encoding='utf-8')
KAYNAK_AGACI = ast.parse(KAYNAK_METNI)

# Testin KENDİ sondaları — modülün kullandıklarından bilerek FARKLI
# (bağımsız ölçüm: modül 1000/2000/4000 K sondalıyorsa test 1500/3000 K
# sondalar; iki ölçüm aynı üssü vermek ZORUNDA).
TEST_SONDA_T1 = 1500.0
TEST_SONDA_T2 = 3000.0
TEST_SONDA_MW = 24.0     # g/mol — depo varsayılanıyla aynı sınıf, sonda


#: Türbülanslı Prandtl'ın depoda arandığı adlar (tek tanım bekçisi).
PR_T_ADLARI = {'PRANDTL_TURBULENT', 'prandtl_turbulent', 'prandtl_t',
               'pr_t', 'Pr_t'}


def _sayisal_sabit(dugum):
    """Düğüm bir sayı literali mi (True/False değil)?"""
    return (isinstance(dugum, ast.Constant)
            and isinstance(dugum.value, (int, float))
            and not isinstance(dugum.value, bool))


def _prt_sayisal_tanimlari(yol):
    """Bir dosyadaki Pr_t = <sayı> TANIMLARI (belge metni ve isim bağlaması hariç).

    Kural: bir Pr_t adına SAYI bağlayan her yer bir tanımdır — atama,
    tür-açıklamalı atama, fonksiyon parametresi varsayılanı ya da çağrı
    argümanı. ``prandtl_turbulent=PRANDTL_TURBULENT`` (isim bağlaması) ve
    belge metnindeki "Pr_t = 0,9" cümlesi tanım DEĞİLDİR — bu yüzden
    metin taraması değil AST kullanılır.
    """
    metin = yol.read_text(encoding='utf-8')
    if not any(ad in metin for ad in PR_T_ADLARI):
        return []          # ucuz ön eleme: adı geçmeyen dosya ayrıştırılmaz
    agac = ast.parse(metin)
    bulgular = []
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.Assign) and _sayisal_sabit(dugum.value):
            bulgular += [h.id for h in dugum.targets
                         if isinstance(h, ast.Name) and h.id in PR_T_ADLARI]
        elif isinstance(dugum, ast.AnnAssign) and _sayisal_sabit(dugum.value):
            if isinstance(dugum.target, ast.Name) and dugum.target.id in PR_T_ADLARI:
                bulgular.append(dugum.target.id)
        elif isinstance(dugum, ast.keyword):
            if dugum.arg in PR_T_ADLARI and _sayisal_sabit(dugum.value):
                bulgular.append(dugum.arg)
        elif isinstance(dugum, ast.arguments):
            konumlu = dugum.posonlyargs + dugum.args
            ciftler = list(zip(konumlu[len(konumlu) - len(dugum.defaults):],
                               dugum.defaults))
            ciftler += list(zip(dugum.kwonlyargs, dugum.kw_defaults))
            for arg, varsayilan in ciftler:
                if arg.arg in PR_T_ADLARI and _sayisal_sabit(varsayilan):
                    bulgular.append(arg.arg)
    return bulgular


def _depo_viskozitesi(T, mw=TEST_SONDA_MW, gamma=1.2):
    """Depo zincirinin ta kendisi (test tarafı, bağımsız çağrı)."""
    props = HeatTransferAnalyzer()._get_gas_properties(
        {'molecular_weight': mw, 'gamma': gamma}, T)
    return float(props['gas_viscosity'])


# ===========================================================================
# 1) Üssün kaynağı: DEPONUN bağıntısı — kopya değil, ÖLÇÜM
# ===========================================================================

def test_ussun_kaynagi_depo_bagintisinin_kendisi():
    """Modülün üssü, testin bağımsız ölçtüğü depo üssüyle AYNI olmalı.

    Mutasyon ısırığı: modüle sabit bir üs (0,6 ya da 0,65) yazılırsa ve
    depo bağıntısı değişirse bu bekçi kırmızıya döner; kopya yazıldığında
    ise 3 numaralı bekçi (literal beyaz listesi) düşer.
    """
    olculen = math.log(_depo_viskozitesi(TEST_SONDA_T2)
                       / _depo_viskozitesi(TEST_SONDA_T1)) \
        / math.log(TEST_SONDA_T2 / TEST_SONDA_T1)

    assert gt.viscosity_exponent() == pytest.approx(olculen, rel=1e-12)
    # Bugünkü depo değeri 0,6'dır (Bartz 1957). Bu satır bir TANIM değil,
    # ölçümün bugünkü sonucunun künyesidir.
    assert gt.viscosity_exponent() == pytest.approx(0.6, rel=1e-12)


def test_us_olcumu_onbelleklenir_ve_temizlenebilir():
    """Sıcak yol depo modülünü her çağrıda ithal etmemeli (önbellek)."""
    gt._repo_power_law.cache_clear()
    ilk = gt.viscosity_exponent()
    bilgi = gt._repo_power_law.cache_info()
    assert bilgi.currsize == 1
    assert gt.viscosity_exponent() == ilk
    assert gt._repo_power_law.cache_info().hits >= 1


# ===========================================================================
# 2+3) Kaynak denetimi: depo zinciri İTHAL EDİLİP ÇAĞRILIYOR, literal yok
# ===========================================================================

def test_modul_depo_zincirini_ithal_edip_cagiriyor():
    """Tek kaynak yapısal olarak kanıtlanır: import + çağrı AST'te var."""
    ithaller = [d.module for d in ast.walk(KAYNAK_AGACI)
                if isinstance(d, ast.ImportFrom) and d.module]
    assert 'hrma.analysis.heat_transfer_analysis' in ithaller, (
        'Sarmalayıcı depo zincirini İTHAL ETMİYOR — yasa yeniden '
        'yazılmış olabilir (tasarım belgesi §5.8 ihlali).')

    cagrilar = {d.func.attr for d in ast.walk(KAYNAK_AGACI)
                if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)}
    assert '_get_gas_properties' in cagrilar, (
        'Depo zinciri çağrılmıyor: μ/cp/Pr yerel olarak hesaplanıyor '
        'olabilir.')


def test_sayisal_literal_beyaz_listesi():
    """Modüldeki HER sayısal literal gerekçeli beyaz listede olmalı.

    Bu, "ikinci viskozite yasası yazma" kuralının mekanik hâlidir: üs
    (0,6), ön çarpan (1,184e-7), MW üssü (0,5) ve donmuş Prandtl'ın
    4/9/5 katsayıları listede YOKTUR — biri yazıldığı an kırmızı.
    """
    izinli_float = {
        0.0,        # sıfır karşılaştırmaları, μ_t varsayılanı
        1.0,        # nötr çarpan, sonda MW'si, oran tabanı
        0.85,       # Pr_t bandının alt ucu (Kays 1994 derlemesi)
        0.9,        # PRANDTL_TURBULENT — TEK yeni model sabiti (künyeli)
        1000.0,     # üs ölçümü sonda sıcaklığı #1 [K]
        2000.0,     # üs ölçümü sonda sıcaklığı #2 [K]
        4000.0,     # üs ölçümü sonda sıcaklığı #3 [K] (sürükleme çaprazı)
        1e-9,       # güç yasası sürükleme toleransı (bağıl)
    }
    izinli_int = {0, 1, 2}   # dizin ve önbellek boyu

    yasak_kopya = {0.6, 1.184e-7, 0.5, 4.0, 9.0, 5.0}

    bulunan_float, bulunan_int = set(), set()
    for dugum in ast.walk(KAYNAK_AGACI):
        if isinstance(dugum, ast.Constant) and not isinstance(dugum.value, bool):
            if isinstance(dugum.value, float):
                bulunan_float.add(dugum.value)
            elif isinstance(dugum.value, int):
                bulunan_int.add(dugum.value)

    assert not (bulunan_float - izinli_float), (
        'Gerekçesiz sayısal literal: '
        f'{sorted(bulunan_float - izinli_float)} — beyaz listeye gerekçesiyle '
        'eklenmedikçe yasak (tek kaynak kuralı).')
    assert not (bulunan_int - izinli_int), (
        f'Gerekçesiz tamsayı literal: {sorted(bulunan_int - izinli_int)}')
    assert not (bulunan_float & yasak_kopya), (
        'Depo bağıntısının katsayısı bu dosyaya KOPYALANMIŞ: '
        f'{sorted(bulunan_float & yasak_kopya)}')


# ===========================================================================
# 4+5) μ_ref yolu: T_ref'te birebir korunum, üs davranışı ölçülü
# ===========================================================================

def test_t_ref_te_birebir_korunum():
    """Çağıranın değeri T_ref'te BİT düzeyinde korunur (approx değil)."""
    mu_ref, T_ref = 8.7654e-05, 2850.0

    assert gt.viscosity_power_law(T_ref, mu_ref, T_ref) == mu_ref

    tasima = gt.resolve_gas_transport(gamma=1.2, T_ref=T_ref, mu_ref=mu_ref,
                                      cp=2100.0, prandtl=0.82)
    assert tasima.viscosity(T_ref) == mu_ref
    assert tasima.mu_ref == mu_ref

    dizi = gt.viscosity_power_law(np.array([T_ref, T_ref]), mu_ref, T_ref)
    assert np.array_equal(dizi, np.array([mu_ref, mu_ref]))


def test_us_davranisi_olculu_ve_dizi_sozlesmesi():
    """μ(2T)/μ(T) = 2^n; dizi biçimi korunur, girdi değişmez."""
    mu_ref, T_ref = 7.0e-05, 1500.0
    n = gt.viscosity_exponent()

    oran = gt.viscosity_power_law(2.0 * T_ref, mu_ref, T_ref) / mu_ref
    assert oran == pytest.approx(2.0 ** n, rel=1e-14)

    T = np.array([[1500.0, 3000.0], [750.0, 6000.0]])
    girdi_kopyasi = T.copy()
    mu = gt.viscosity_power_law(T, mu_ref, T_ref)
    assert mu.shape == T.shape
    assert mu.dtype == np.float64
    assert np.array_equal(T, girdi_kopyasi), 'Girdi dizisi değiştirildi.'
    assert np.all(np.diff(mu.ravel()[np.argsort(T.ravel())]) > 0.0)
    # skaler giren skaler çıkar (V1 akı çekirdeğinin sözleşmesi)
    assert isinstance(gt.viscosity_power_law(1500.0, mu_ref, T_ref), float)


# ===========================================================================
# 6) Depo yolu: zincirin KENDİSİ, yeniden uygulama değil
# ===========================================================================

def test_depo_yolu_zincirle_birebir():
    """μ_ref verilmediğinde μ(T), cp, Pr depo zinciriyle aynı sayılardır."""
    gamma, mw, T_ref = 1.2, 24.0, 3000.0
    tasima = gt.resolve_gas_transport(gamma=gamma, T_ref=T_ref,
                                      molecular_weight=mw)
    analiz = HeatTransferAnalyzer()

    beklenen = analiz._get_gas_properties(
        {'gamma': gamma, 'molecular_weight': mw}, T_ref)
    assert tasima.mu_ref == pytest.approx(beklenen['gas_viscosity'], rel=1e-15)
    assert tasima.cp == pytest.approx(beklenen['gas_cp'], rel=1e-15)
    assert tasima.prandtl == pytest.approx(beklenen['prandtl'], rel=1e-15)

    # T_ref'ten UZAK sıcaklıklarda da zincirin kendisiyle aynı kalmalı:
    # sarmalayıcı ölçülen üsle ölçekliyor, depo bağıntısı saf güç yasası.
    for T in (600.0, 1234.5, 3600.0):
        beklenen_mu = analiz._get_gas_properties(
            {'gamma': gamma, 'molecular_weight': mw}, T)['gas_viscosity']
        assert tasima.viscosity(T) == pytest.approx(beklenen_mu, rel=1e-12)

    # gas_constant yolu MW yoluyla aynı sonucu vermeli (depo türetimi)
    R_ozgul = beklenen['gas_constant']
    ikinci = gt.resolve_gas_transport(gamma=gamma, T_ref=T_ref,
                                      gas_constant=R_ozgul)
    assert ikinci.mu_ref == pytest.approx(tasima.mu_ref, rel=1e-12)


# ===========================================================================
# 7+8) Donmuş Prandtl: el hesabı + sessiz kelepçelemenin reddi
# ===========================================================================

@pytest.mark.parametrize('gamma, el_hesabi', [
    # Pr = 4γ/(9γ−5), el hesabı:
    (1.2, 4.8 / 5.8),            # 4·1,2 = 4,8 ; 9·1,2 − 5 = 5,8
    (1.4, 5.6 / 7.6),            # 4·1,4 = 5,6 ; 9·1,4 − 5 = 7,6
    (1.6, 6.4 / 9.4),            # 4·1,6 = 6,4 ; 9·1,6 − 5 = 9,4
])
def test_donmus_prandtl_el_hesabi(gamma, el_hesabi):
    """Pr bilinen γ'larda el hesabıyla; değer depo tanımından gelir."""
    assert gt.frozen_prandtl(gamma) == pytest.approx(el_hesabi, rel=1e-14)


def test_prandtl_molekul_agirligindan_bagimsiz():
    """Donmuş Pr yalnız γ'nın işlevidir — sonda MW'si sonucu kirletmez."""
    a = gt.resolve_gas_transport(gamma=1.25, T_ref=3000.0,
                                 molecular_weight=12.0).prandtl
    b = gt.resolve_gas_transport(gamma=1.25, T_ref=3000.0,
                                 molecular_weight=48.0).prandtl
    assert a == b == pytest.approx(gt.frozen_prandtl(1.25), rel=1e-15)


@pytest.mark.parametrize('gamma', [1.0, 1.05, 1.7, 2.0])
def test_gamma_bandi_disinda_sessiz_kelepceleme_yok(gamma):
    """Bant dışı γ hiçbir katmanda sessizce kelepçelenmez — ÜÇÜ DE REDDEDER.

    ÇEVRİLDİ (ÖH D21 / termo-ucus a1, P4B1-16). Bu bekçi v2.6.27'ye kadar
    KUSURU KORUYORDU: ilk iddiası depo çağrısının γ'yı SESSİZCE 1,20'ye
    çektiğini ŞART KOŞUYOR ("Depo bu γ için kelepçelemiyor — vaka
    güncellenmeli"), yani sarmalayıcının varlık sebebi olan kusur
    onarılırsa bekçi kırmızıya dönüyordu. Testin kendi künyesi bu güncelleme
    ihtiyacını zaten haber veriyordu.

    ÖLÇÜLDÜ (docs/scofield/raw/OH/D21/termo-ucus/a1/once.json, K1, taban
    35aa279): γ=1,02 ve γ=3,00 girdilerinin İKİSİ de 1,20 dönüyor, üretilen
    uyarı sayısı 0, dönen sözlükte kelepçeyi anan alan yok. Depo artık
    kardeş ``nozzle_flow_1d`` / ``regen_cooling`` ile AYNI hükmü veriyor:
    bant dışı γ reddedilir (``ValueError``), 1,20'ye çekilmez.

    Bekçinin KORUDUĞU şey değişmedi — sarmalayıcı hâlâ reddetmek zorunda;
    değişen, depo katmanının artık kelepçelemek yerine reddediyor olması.
    """
    with pytest.raises(ValueError, match='gamma'):
        HeatTransferAnalyzer()._get_gas_properties(
            {'gamma': gamma, 'molecular_weight': 24.0}, 3000.0)

    with pytest.raises(ValueError, match='gamma'):
        gt.frozen_prandtl(gamma)
    with pytest.raises(ValueError, match='gamma'):
        gt.resolve_gas_transport(gamma=gamma, T_ref=3000.0,
                                 molecular_weight=24.0)


# ===========================================================================
# 9) k_eff kompozisyonu — cebirsel özdeşlik
# ===========================================================================

def test_k_eff_cebirsel_ozdeslik():
    """k_eff = cp(μ/Pr + μ_t/Pr_t): laminer uç + μ_t'de doğrusallık."""
    cp, mu, Pr = 2078.6156545, 7.0750591664e-05, 0.8275862069

    laminer = gt.effective_conductivity(cp, mu, Pr)
    assert laminer == pytest.approx(cp * mu / Pr, rel=1e-15)

    mu_t = 3.5e-04
    tam = gt.effective_conductivity(cp, mu, Pr, mu_t=mu_t)
    assert tam - laminer == pytest.approx(
        cp * mu_t / gt.PRANDTL_TURBULENT, rel=1e-12)

    # μ_t'de doğrusal: iki katı → türbülanslı payın iki katı
    iki_kat = gt.effective_conductivity(cp, mu, Pr, mu_t=2.0 * mu_t)
    assert iki_kat - laminer == pytest.approx(2.0 * (tam - laminer), rel=1e-12)

    # Pr_t varsayılanı sabitin KENDİSİ (ikinci bir varsayılan yok)
    assert gt.effective_conductivity(cp, mu, Pr, mu_t=mu_t,
                                     prandtl_turbulent=gt.PRANDTL_TURBULENT) == tam

    # Dizi yayınlaması: alan hesabının biçimi korunur
    alan = np.full((3, 4), mu)
    assert gt.effective_conductivity(cp, alan, Pr).shape == (3, 4)


# ===========================================================================
# 10) Girdi doğrulama — adlı hatalar, sessiz düzeltme yok
# ===========================================================================

@pytest.mark.parametrize('cagri, ad', [
    (lambda: gt.viscosity_power_law(-300.0, 7e-5, 3000.0), 'temperature'),
    (lambda: gt.viscosity_power_law(0.0, 7e-5, 3000.0), 'temperature'),
    (lambda: gt.viscosity_power_law(np.array([300.0, -1.0]), 7e-5, 3000.0),
     'temperature'),
    (lambda: gt.viscosity_power_law(np.nan, 7e-5, 3000.0), 'temperature'),
    (lambda: gt.viscosity_power_law(3000.0, -7e-5, 3000.0), 'mu_ref'),
    (lambda: gt.viscosity_power_law(3000.0, 7e-5, 0.0), 'T_ref'),
    (lambda: gt.effective_conductivity(-1.0, 7e-5, 0.8), 'cp'),
    (lambda: gt.effective_conductivity(2000.0, -7e-5, 0.8), 'mu'),
    (lambda: gt.effective_conductivity(2000.0, 7e-5, 0.0), 'prandtl'),
    (lambda: gt.effective_conductivity(2000.0, 7e-5, 0.8, mu_t=-1e-5), 'mu_t'),
    (lambda: gt.effective_conductivity(2000.0, 7e-5, 0.8,
                                       prandtl_turbulent=0.0),
     'prandtl_turbulent'),
    (lambda: gt.resolve_gas_transport(gamma=1.2, T_ref=-1.0,
                                      molecular_weight=24.0), 'T_ref'),
])
def test_girdi_dogrulama_adli_hatalar(cagri, ad):
    """Kusurlu girdi ADIYLA reddedilir (NaN/negatif sessizce geçmez)."""
    with pytest.raises(ValueError, match=ad):
        cagri()


def test_depo_zinciri_icin_eksik_girdi_reddedilir():
    """MW/R yoksa depo MW=24'e DÜŞER; sarmalayıcı bunu reddeder.

    Depo varsayılanı ölçülür (kanıt), sonra sarmalayıcının aynı girdide
    eksik alanları ADIYLA saydığı gösterilir — ısı analizi modülünün
    'defaults'tan hüküm üretilmez' desenine uyum.
    """
    dusen = HeatTransferAnalyzer()._get_gas_properties({'gamma': 1.2}, 3000.0)
    assert dusen['molecular_weight'] == 24.0, (
        'Depo artık sessiz MW varsayılanı kullanmıyor — bekçi güncellenmeli.')

    with pytest.raises(ValueError, match='molecular_weight'):
        gt.resolve_gas_transport(gamma=1.2, T_ref=3000.0)

    # μ, cp ve Pr'nin ÜÇÜ de çağırandan gelirse MW hiç gerekmez.
    tasima = gt.resolve_gas_transport(gamma=1.2, T_ref=3000.0, mu_ref=9.0e-05,
                                      cp=2100.0, prandtl=0.82)
    assert tasima.sources['viscosity'] == 'caller'


# ===========================================================================
# 11) Pr_t: TEK yeni model sabiti — tek tanım + künye
# ===========================================================================

def test_prandtl_turbulent_tek_tanim_ve_kunyeli():
    """Pr_t depoda TEK yerde sayı olarak tanımlanır ve künyelidir."""
    tanimlar = {}
    for yol in sorted((ROOT / 'hrma').rglob('*.py')):
        sayi = len(_prt_sayisal_tanimlari(yol))
        if sayi:
            tanimlar[yol.relative_to(ROOT).as_posix()] = sayi
    assert tanimlar == {'hrma/cfd/gas_transport.py': 1}, (
        f'Türbülanslı Prandtl tek tanım noktasında değil: {tanimlar}')
    # Tek tanım gerçekten modül sabitinin kendisi olmalı
    assert re.search(r'^PRANDTL_TURBULENT\s*=\s*0\.90\s*$',
                     KAYNAK_METNI, re.M)

    kunye = gt.PRANDTL_TURBULENT_CITATION
    for alan in ('author', 'title', 'journal', 'year', 'doi', 'note'):
        assert isinstance(kunye.get(alan), str) and kunye[alan].strip(), alan
    assert kunye['doi'] == '10.1115/1.2911398'      # Crossref, 18 Ağu 2026
    assert 'Kays' in kunye['author'] and kunye['year'] == '1994'

    alt, ust = gt.PRANDTL_TURBULENT_BAND
    assert alt < gt.PRANDTL_TURBULENT or alt == gt.PRANDTL_TURBULENT
    assert ust == gt.PRANDTL_TURBULENT     # üst uç = seçilen değer, kopya yok
    assert alt <= gt.PRANDTL_TURBULENT <= ust


# ===========================================================================
# 12) Beyan: hangi sayı nereden geldi
# ===========================================================================

def test_beyan_kaynak_etiketleri():
    """Her büyüklüğün kaynağı ('caller' / 'repo_chain') beyan edilir."""
    karma = gt.resolve_gas_transport(gamma=1.2, T_ref=3000.0,
                                     molecular_weight=24.0, mu_ref=9.0e-05)
    assert karma.sources == {
        'viscosity': 'caller',
        'cp': 'repo_chain',
        'prandtl': 'repo_chain',
        'prandtl_turbulent': 'model_constant',
    }
    assert karma.mu_ref == 9.0e-05          # çağıranın değeri ezilmedi

    beyan = karma.declaration()
    assert beyan['viscosity_law_source'] == gt.VISCOSITY_LAW_SOURCE
    assert 'heat_transfer_analysis' in beyan['viscosity_law_source']
    assert beyan['viscosity_exponent'] == pytest.approx(0.6, rel=1e-12)
    assert beyan['prandtl_turbulent'] == gt.PRANDTL_TURBULENT
    assert beyan['prandtl_turbulent_citation']['doi'] == '10.1115/1.2911398'
    assert beyan['sources'] == karma.sources


# ===========================================================================
# 13) Sürükleme bekçisi: depo yasası güç yasası olmaktan çıkarsa DUR
# ===========================================================================

def test_kaynak_surukleme_bekcisi(monkeypatch):
    """Depo bağıntısı Sutherland'e dönerse ölçüm SESSİZCE uydurmaz, atar."""
    def sahte(self, motor_data, chamber_temperature):
        T = float(chamber_temperature)
        # Sutherland biçimi: saf güç yasası DEĞİL
        return {'gamma': motor_data.get('gamma', 1.2),
                'molecular_weight': 24.0, 'gas_constant': 346.0,
                'gas_cp': 2000.0, 'prandtl': 0.8,
                'gas_viscosity': 1.7e-5 * (T / 273.0) ** 1.5 * 384.0 / (T + 111.0),
                'gas_conductivity': 0.2}

    monkeypatch.setattr(HeatTransferAnalyzer, '_get_gas_properties', sahte)
    gt._repo_power_law.cache_clear()
    try:
        with pytest.raises(gt.GasTransportSourceError, match='güç yasası'):
            gt.viscosity_exponent()
    finally:
        # Sahte yasa geri alınır ve önbellek temizlenir: sonraki bekçiler
        # (ve bu testin son satırı) GERÇEK depoyu ölçmeli.
        monkeypatch.undo()
        gt._repo_power_law.cache_clear()

    assert gt.viscosity_exponent() == pytest.approx(0.6, rel=1e-12)
