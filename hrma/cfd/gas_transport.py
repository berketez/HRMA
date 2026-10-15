# hrma/cfd — gaz taşınım özellikleri: DEPO bağıntısına sarmalayıcı (yeni yasa YOK)
"""
Viskoz CFD'nin ihtiyaç duyduğu taşınım büyüklükleri: μ(T), cp, Pr, Pr_t ve
k_eff.

AMAÇ VE SINIR (tasarım belgesi docs/mimari/cfd-viskoz-tasarimi.md §5.8)
----------------------------------------------------------------------
Bu modül bir **sarmalayıcıdır**. Yeni bir viskozite yasası, yeni bir
Prandtl tanımı YAZMAZ:

- Çağıran μ_ref (ve isterse cp, Pr) verdiyse — örneğin yukarı akıştaki bir
  CEA/Cantera çözümünden — o değer **T_ref'te bit düzeyinde korunur**,
  sıcaklık değişimi deponun kendi üs yasasıyla taşınır:
  ``μ(T) = μ_ref · (T/T_ref)^n``.
- Vermediyse büyüklükler doğrudan depo zincirinden okunur:
  ``hrma.analysis.heat_transfer_analysis.HeatTransferAnalyzer.
  _get_gas_properties`` (Bartz 1957: μ = 1,184e-7·MW^0,5·T^0,6;
  Pr = 4γ/(9γ−5), Sutton & Biblarz Denk. 8-23; cp = γR/(γ−1)).

ÜS NEDEN "ÖLÇÜLÜYOR" DA YAZILMIYOR
----------------------------------
n = 0,6 sayısı bu dosyaya KOPYALANMAZ. ``_repo_power_law`` depo zincirini
üç sıcaklıkta sondalar ve üssü log-oranından ölçer:

    n = ln(μ(T₂)/μ(T₁)) / ln(T₂/T₁)

Böylece bağıntının tek tanım noktası ``heat_transfer_analysis.py:283``
olarak kalır; orası değişirse burası kendiliğinden takip eder. Üçüncü
sonda bir **sürükleme bekçisidir**: depo bağıntısı bir gün saf güç yasası
olmaktan çıkarsa (ör. Sutherland) iki ölçüm birbirini tutmaz ve
``GasTransportSourceError`` atılır — sessizce yanlış bir üs uydurulmaz.

Aynı gerekçeyle donmuş Pr da hesaplanmaz, depo zincirinden okunur. Depo
bant dışı γ'yı SESSİZCE 1,20'ye kelepçelediği için sarmalayıcı bunu tespit
edip reddeder (kelepçelenmiş bir γ ile hüküm üretmek, kullanıcının
vermediği bir gaz için sayı yayımlamak olurdu).

TEK YENİ MODEL SABİTİ: Pr_t
---------------------------
``PRANDTL_TURBULENT = 0,90``. Türbülanslı Prandtl sayısı bir MODEL
sabitidir (ölçülen bir malzeme özelliği değil): türbülanslı ısı akısını
türbülanslı momentum akısına bağlayan kapanış varsayımıdır.

- Künye (birincil, deneysel derleme): Kays, W. M., "Turbulent Prandtl
  Number—Where Are We?", *Journal of Heat Transfer* **116**(2), 1994,
  s. 284-295, DOI 10.1115/1.2911398 (Crossref ile doğrulandı, 18 Ağu 2026):
  iki boyutlu türbülanslı sınır tabakası ve tam gelişmiş boru akışı için
  mevcut deneysel Pr_t verisinin eleştirel derlemesi; gazlarda değer
  ~0,85-0,9 bandındadır.
- Seçilen 0,90, sıkıştırılabilir aerodinamik RANS geleneğidir (SA ile
  birlikte yaygın kullanım; Wilcox, *Turbulence Modeling for CFD*, 3. baskı,
  2006, sınır tabakası için Pr_t = 0,9 — kitap, Crossref künyesi yok).
- Bant ``PRANDTL_TURBULENT_BAND`` olarak dışa verilir; k_t'nin bu banttaki
  belirsizliği ~%6'dır ve koşum beyanında görünür. Çağıran isterse kendi
  değerini geçirebilir (varsayılan ezilmez, beyan edilir).

MODELLENMEYEN (dürüstlük)
-------------------------
- μ bağıntısı Bartz 1957 korelasyonudur; tipik yanma gazlarında CEA
  taşınımına göre ~%10-20 bandındadır (depo modülünün kendi beyanı).
- Pr donmuştur: ayrışma/yeniden birleşme (dissociation) ve tür difüzyonu
  modellenmez.
- Pr_t sabittir: duvara yakın Pr_t artışı ve serbest kayma tabakalarındaki
  düşüş modellenmez.

SÖZLEŞME
--------
Saf NumPy, numba yok (V0). Tüm fonksiyonlar saftır: girdi dizisi
değiştirilmez; skaler giren skaler çıkar, dizi giren aynı biçimde dizi
çıkar. Kusurlu girdi ``ValueError`` ile ADIYLA reddedilir (NaN, negatif,
sıfır sessizce geçmez). Depo modülü **tembel** ithal edilir: ``hrma.cfd``
paketini ithal etmek ısı-transferi ağacını yüklemez; üs ölçümü koşu başına
bir kez yapılır ve önbelleklenir.

ÖLÇÜLDÜ (M4 Max, 18 Ağu 2026):
- ``import hrma.cfd`` sonrası ``hrma.analysis.heat_transfer_analysis``
  sys.modules'ta DEĞİL (tembellik sözleşmesi); o ağacın ithali ~0,8 s.
- İlk ``viscosity_exponent()`` çağrısı 0,167 s (ithal + üç sonda),
  sonrakiler 3,2 µs (önbellek).
- ``viscosity_power_law`` 120×24 (2880 hücre) alanda çağrı başına
  0,040 ms — girdi doğrulaması dâhil. V1'in iterasyon başına maliyeti
  bu mertebede kalır; numba gerekmez (V0 kararı).
"""

from dataclasses import dataclass
from functools import lru_cache
import math

import numpy as np

__all__ = [
    'GasTransport',
    'GasTransportSourceError',
    'PRANDTL_TURBULENT',
    'PRANDTL_TURBULENT_BAND',
    'PRANDTL_TURBULENT_CITATION',
    'VISCOSITY_LAW_SOURCE',
    'effective_conductivity',
    'frozen_prandtl',
    'resolve_gas_transport',
    'viscosity_exponent',
    'viscosity_power_law',
]

#: Viskozite/Prandtl/cp bağıntılarının TEK tanım noktası (adres beyanı).
VISCOSITY_LAW_SOURCE = (
    'hrma.analysis.heat_transfer_analysis.HeatTransferAnalyzer.'
    '_get_gas_properties (Bartz 1957: mu = 1,184e-7 * MW^0,5 * T^0,6; '
    'Pr = 4*gamma/(9*gamma-5), Sutton & Biblarz Denk. 8-23)')

#: Türbülanslı Prandtl sayısı — bu aşamanın TEK yeni model sabiti.
PRANDTL_TURBULENT = 0.90

#: Deneysel derlemenin bandı; üst uç seçilen değerin KENDİSİDİR (kopya yok).
PRANDTL_TURBULENT_BAND = (0.85, PRANDTL_TURBULENT)

#: Pr_t künyesi (yalnız dize alanlar: sayısal literal taşımaz).
PRANDTL_TURBULENT_CITATION = {
    'author': 'Kays, W. M.',
    'title': 'Turbulent Prandtl Number—Where Are We?',
    'journal': 'Journal of Heat Transfer',
    'year': '1994',
    'volume': '116(2)',
    'pages': '284-295',
    'doi': '10.1115/1.2911398',
    'verified': 'Crossref, 18 Ağu 2026',
    'note': ('Deneysel derleme gazlarda Pr_t ~ 0,85-0,9 bandını verir; '
             'seçilen 0,90 sıkıştırılabilir RANS geleneğidir (Wilcox, '
             'Turbulence Modeling for CFD, 3. baskı, 2006 — kitap, DOI yok).'),
}

# Üs ölçümünün sondaları. Bunlar FİZİKSEL VARSAYIM DEĞİLDİR: depo
# bağıntısını yoklayan sorgu noktalarıdır. Roket sıcaklık aralığında ve iki
# kat aralıklı seçildi; üçüncüsü sürükleme (güç yasası mı?) çaprazı içindir.
_PROBE_TEMPERATURES_K = (1000.0, 2000.0, 4000.0)

# Sonda molekül ağırlığı [g/mol]: üs MW'den bağımsız olduğundan değeri
# önemsizdir; 1,0 seçilmesi "bu bir sondadır, gaz varsayımı değildir"
# demenin en açık biçimidir.
_PROBE_MOLECULAR_WEIGHT = 1.0

# İki bağımsız ölçümün bağıl uyum toleransı. Depo bağıntısı saf güç yasası
# olduğu sürece fark kayan nokta gürültüsüdür (ÖLÇÜLDÜ: ~1e-16).
_POWER_LAW_DRIFT_TOL = 1e-9


class GasTransportSourceError(ValueError):
    """Depo taşınım bağıntısı beklenen biçimden SÜRÜKLENDİ.

    ``ValueError`` alt sınıfıdır (depo kalıbı): mevcut ``except ValueError``
    dalları davranışlarını korur. Bu hata "sarmalayıcı artık deponun
    yasasını temsil edemiyor" demektir; sessiz bir vekil üretmek yerine
    koşu durur.
    """


# ---------------------------------------------------------------------------
# Girdi doğrulama (adlı, sessiz düzeltme yok)
# ---------------------------------------------------------------------------

def _positive_scalar(name, value):
    """Pozitif sonlu skaler; değilse ``ValueError`` (ad mesajda)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{name} sayısal olmalı — verilen: {value!r}.')
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f'{name} pozitif ve sonlu olmalı — verilen: '
                         f'{value!r}.')
    return number


def _nonnegative_array(name, value):
    """Negatif olmayan sonlu dizi/skaler → (dizi, skaler_miydi)."""
    array = np.asarray(value, dtype=float)
    if not np.all(np.isfinite(array)) or np.any(array < 0.0):
        raise ValueError(f'{name} negatif olmayan ve sonlu olmalı '
                         '(NaN/inf/negatif sessizce geçmez).')
    return array, array.ndim == 0


def _positive_array(name, value):
    """Pozitif sonlu dizi/skaler → (dizi, skaler_miydi)."""
    array = np.asarray(value, dtype=float)
    if not np.all(np.isfinite(array)) or np.any(array <= 0.0):
        raise ValueError(f'{name} pozitif ve sonlu olmalı '
                         '(NaN/inf/sıfır/negatif sessizce geçmez).')
    return array, array.ndim == 0


# ---------------------------------------------------------------------------
# Depo zinciri: tek tanım noktasına tembel bağ
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _repo_analyzer():
    """Depo ısı-transferi çözümleyicisi (tembel ithal, tek örnek)."""
    from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
    return HeatTransferAnalyzer()


def _repo_properties(gamma=None, temperature=None, molecular_weight=None,
                     gas_constant=None):
    """Depo taşınım sözlüğü — γ kelepçelenirse REDDEDER.

    ``_get_gas_properties`` bant dışı γ'yı sessizce 1,20'ye çeker
    (heat_transfer_analysis.py, ``if not (1.05 < gamma < 1.67)``). Bandın
    sayısı buraya kopyalanmaz: çağrının döndürdüğü γ ile istenen γ
    karşılaştırılır — kelepçelendiyse depo bunu kendisi söylemiş olur.
    """
    payload = {}
    if gamma is not None:
        payload['gamma'] = float(gamma)
    if molecular_weight is not None:
        payload['molecular_weight'] = float(molecular_weight)
    if gas_constant is not None:
        payload['gas_constant'] = float(gas_constant)

    properties = _repo_analyzer()._get_gas_properties(payload,
                                                      float(temperature))
    if gamma is not None and float(properties['gamma']) != float(gamma):
        raise ValueError(
            f'gamma={gamma!r} depo taşınım bağıntısının geçerlilik bandının '
            f'dışında: depo onu sessizce {properties["gamma"]!r} değerine '
            'kelepçeliyor. Kelepçelenmiş gamma ile taşınım özelliği '
            'yayımlanmaz — gamma düzeltilmeli.')
    return properties


@lru_cache(maxsize=1)
def _repo_power_law():
    """Depo viskozite bağıntısının ÖLÇÜLEN sıcaklık üssü.

    İki bağımsız log-oran ölçümü alınır; ikisi uyuşmazsa bağıntı artık saf
    güç yasası değildir ve ``GasTransportSourceError`` atılır.
    """
    temperatures = _PROBE_TEMPERATURES_K
    viscosities = []
    for probe_t in temperatures:
        properties = _repo_properties(
            temperature=probe_t, molecular_weight=_PROBE_MOLECULAR_WEIGHT)
        mu = float(properties['gas_viscosity'])
        if not math.isfinite(mu) or mu <= 0.0:
            raise GasTransportSourceError(
                'Depo viskozite zinciri pozitif sonlu değer vermedi '
                f'(T={probe_t} K → {mu!r}); üs ölçülemez.')
        viscosities.append(mu)

    first = (math.log(viscosities[1] / viscosities[0])
             / math.log(temperatures[1] / temperatures[0]))
    second = (math.log(viscosities[2] / viscosities[1])
              / math.log(temperatures[2] / temperatures[1]))
    if abs(first - second) > _POWER_LAW_DRIFT_TOL * max(1.0, abs(first)):
        raise GasTransportSourceError(
            'Depo viskozite bağıntısı artık saf güç yasası değil: iki '
            f'sonda çifti farklı üs veriyor ({first!r} ve {second!r}). '
            f'Kaynak: {VISCOSITY_LAW_SOURCE}. Sarmalayıcı bu bağıntıyı '
            'temsil edemez; ölçeklenmiş bir üs UYDURULMAZ.')
    return first


def viscosity_exponent():
    """Deponun viskozite yasasının sıcaklık üssü n (ölçülen, kopya değil)."""
    return _repo_power_law()


# ---------------------------------------------------------------------------
# Saf fonksiyonlar (V1 viskoz akısının çağıracağı biçim)
# ---------------------------------------------------------------------------

def viscosity_power_law(temperature, mu_ref, T_ref, exponent=None):
    """μ(T) = μ_ref·(T/T_ref)^n — çağıranın değeri T_ref'te bit düzeyinde korunur.

    Args:
        temperature: Sıcaklık [K], skaler ya da herhangi biçimde dizi.
        mu_ref: T_ref'teki dinamik viskozite [Pa·s], pozitif.
        T_ref: Referans sıcaklık [K], pozitif.
        exponent: Üs n. ``None`` ise depodan ÖLÇÜLEN üs kullanılır (sıcak
            yolda ölçüm önbellekli; yine de V1 çekirdeği üssü bir kez alıp
            geçirebilir).

    Returns:
        Dinamik viskozite [Pa·s]; skaler giren skaler alır, dizi giren
        aynı biçimde ``float64`` dizi alır.

    Raises:
        ValueError: Sıcaklık pozitif sonlu değilse, ``mu_ref``/``T_ref``
            pozitif sonlu değilse.
    """
    array, was_scalar = _positive_array('temperature', temperature)
    mu_ref = _positive_scalar('mu_ref', mu_ref)
    T_ref = _positive_scalar('T_ref', T_ref)
    if exponent is None:
        exponent = viscosity_exponent()
    else:
        exponent = float(exponent)
        if not math.isfinite(exponent):
            raise ValueError(f'exponent sonlu olmalı — verilen: {exponent!r}.')

    result = mu_ref * (array / T_ref) ** exponent
    return float(result) if was_scalar else result


def frozen_prandtl(gamma):
    """Donmuş Prandtl sayısı Pr(γ) — DEPO tanımından (kopya değil).

    Args:
        gamma: Özgül ısı oranı γ (deponun geçerlilik bandı içinde).

    Returns:
        Pr = 4γ/(9γ−5) — sayı deponun ``_get_gas_properties`` zincirinden
        gelir; bağıntı bu dosyada yeniden yazılmaz.

    Raises:
        ValueError: γ pozitif sonlu değilse ya da depo onu kelepçeliyorsa.
    """
    gamma = _positive_scalar('gamma', gamma)
    properties = _repo_properties(
        gamma=gamma, temperature=_PROBE_TEMPERATURES_K[0],
        molecular_weight=_PROBE_MOLECULAR_WEIGHT)
    return float(properties['prandtl'])


def effective_conductivity(cp, mu, prandtl, mu_t=0.0,
                           prandtl_turbulent=PRANDTL_TURBULENT):
    """k_eff = cp·(μ/Pr + μ_t/Pr_t) [W/(m·K)].

    Args:
        cp: Özgül ısı [J/(kg·K)], pozitif.
        mu: Laminer dinamik viskozite [Pa·s], pozitif (skaler ya da dizi).
        prandtl: Laminer (donmuş) Prandtl sayısı, pozitif.
        mu_t: Türbülanslı viskozite [Pa·s], negatif olmayan (SA-neg'de
            ν̃ < 0 bölgesinde μ_t = 0 olur; negatif μ_t bir kusurdur).
        prandtl_turbulent: Pr_t; varsayılan ``PRANDTL_TURBULENT``.

    Returns:
        Etkin ısı iletkenliği; ``mu`` ve ``mu_t`` yayınlamasının biçiminde.

    Raises:
        ValueError: Herhangi bir girdi işaret/sonluluk sözleşmesini bozarsa.
    """
    cp = _positive_scalar('cp', cp)
    prandtl = _positive_scalar('prandtl', prandtl)
    prandtl_turbulent = _positive_scalar('prandtl_turbulent',
                                         prandtl_turbulent)
    mu_array, mu_scalar = _positive_array('mu', mu)
    mu_t_array, mu_t_scalar = _nonnegative_array('mu_t', mu_t)

    result = cp * (mu_array / prandtl + mu_t_array / prandtl_turbulent)
    return float(result) if (mu_scalar and mu_t_scalar) else result


# ---------------------------------------------------------------------------
# Çözümlenmiş taşınım durumu (kaynak beyanıyla)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GasTransport:
    """Bir koşunun taşınım referans durumu + her sayının KAYNAĞI.

    Alanlar referans durumdur (T_ref'te değerlendirilmiş); alan hesabı
    ``viscosity``/``conductivity`` ile yapılır. ``sources`` her büyüklüğün
    çağırandan mı (``'caller'``) yoksa depo zincirinden mi (``'repo_chain'``)
    geldiğini söyler; ``declaration()`` bunu koşum beyanına verir.
    """

    gamma: float
    T_ref: float
    mu_ref: float
    cp: float
    prandtl: float
    prandtl_turbulent: float
    viscosity_exponent: float
    sources: dict

    def __post_init__(self):
        """Taşınım durumunun TANIM ALANI — kusurlu değer ADIYLA reddedilir.

        NEDEN VAR (ÖH defter P6B2-08, ölçüldü D23 once.json K10): bu sınıf
        doğrulamasız bir ``frozen`` dataclass'tı ve γ = 1,0 (hatta 0, −1,
        NaN) taşıyan bir örnek KURULABİLİYORDU. γ = 1,0 taşıyan örnek
        ``viscous._check_gas_consistency``e girince cp = γR/(γ−1) SIFIRA
        BÖLÜM üretiyor ve dışarıya ADSIZ bir ``ZeroDivisionError``
        sızıyordu — modülün "kusurlu girdi ValueError ile ADIYLA
        reddedilir" sözleşmesinin dışında. Kapı BURAYA konur ki her
        tüketici aynı korumayı alsın (tek kaynak); ``_check_gas_consistency``
        kendi kapısını ayrıca taşır çünkü oraya BAŞKA yoldan (sahte nesne)
        gelen γ de olabilir.
        """
        for ad, deger, alt in (('gamma', self.gamma, 1.0),
                               ('T_ref', self.T_ref, 0.0),
                               ('mu_ref', self.mu_ref, 0.0),
                               ('cp', self.cp, 0.0),
                               ('prandtl', self.prandtl, 0.0),
                               ('prandtl_turbulent', self.prandtl_turbulent,
                                0.0)):
            try:
                sayi = float(deger)
            except (TypeError, ValueError):
                raise ValueError(
                    f'GasTransport.{ad} sayı olmalı — verilen: {deger!r}.')
            if not math.isfinite(sayi) or sayi <= alt:
                nicin = ('cp = γR/(γ−1) ancak γ > 1 için tanımlıdır '
                         '(γ = 1 izotermal sınır hâli)' if ad == 'gamma'
                         else 'pozitif ve sonlu olmalı')
                raise ValueError(
                    f'GasTransport.{ad} > {alt:g} olmalı ve sonlu olmalı — '
                    f'verilen: {deger!r}. {nicin}. Bu bir GİRDİ kusurudur; '
                    'sessizce kelepçelenmez.')

    def viscosity(self, temperature):
        """μ(T) [Pa·s] — referans durumdan deponun üs yasasıyla."""
        return viscosity_power_law(temperature, self.mu_ref, self.T_ref,
                                   exponent=self.viscosity_exponent)

    def conductivity(self, temperature, mu_t=0.0):
        """k_eff(T, μ_t) [W/(m·K)] — cp·(μ/Pr + μ_t/Pr_t)."""
        return effective_conductivity(
            self.cp, self.viscosity(temperature), self.prandtl, mu_t=mu_t,
            prandtl_turbulent=self.prandtl_turbulent)

    def declaration(self):
        """Koşum beyanı: hangi sayı nereden geldi, hangi sabit künyeli."""
        return {
            'viscosity_law_source': VISCOSITY_LAW_SOURCE,
            'viscosity_exponent': self.viscosity_exponent,
            'viscosity_exponent_source': 'measured_from_repo_chain',
            'T_ref_K': self.T_ref,
            'mu_ref_Pa_s': self.mu_ref,
            'cp_J_per_kgK': self.cp,
            'prandtl': self.prandtl,
            'prandtl_turbulent': self.prandtl_turbulent,
            'prandtl_turbulent_band': PRANDTL_TURBULENT_BAND,
            'prandtl_turbulent_citation': dict(PRANDTL_TURBULENT_CITATION),
            'sources': dict(self.sources),
        }


def resolve_gas_transport(*, gamma, T_ref, molecular_weight=None,
                          gas_constant=None, mu_ref=None, cp=None,
                          prandtl=None, prandtl_turbulent=PRANDTL_TURBULENT):
    """Taşınım referans durumunu çözer: çağıranın değerleri > depo zinciri.

    Args:
        gamma: Özgül ısı oranı γ (deponun bandı içinde olmalı).
        T_ref: Referans sıcaklık [K] — çağıranın verdiği μ_ref/cp/Pr bu
            sıcaklıkta geçerli sayılır; verilmediyse depo zinciri burada
            değerlendirilir.
        molecular_weight: Molekül ağırlığı [g/mol] (depo yolu için).
        gas_constant: Özgül gaz sabiti [J/(kg·K)] (MW yerine geçer).
        mu_ref: T_ref'teki viskozite [Pa·s] (ör. CEA/Cantera'dan).
        cp: Özgül ısı [J/(kg·K)].
        prandtl: Donmuş Prandtl sayısı.
        prandtl_turbulent: Pr_t (varsayılan künyeli model sabiti).

    Returns:
        ``GasTransport``.

    Raises:
        ValueError: γ/T_ref kusurluysa ya da depo yoluna düşülmesi gerekip
            de ``molecular_weight``/``gas_constant`` verilmemişse (depo
            böyle bir durumda sessizce MW = 24 g/mol varsayar; sarmalayıcı
            bu uydurmayı geçirmez).
    """
    gamma = _positive_scalar('gamma', gamma)
    T_ref = _positive_scalar('T_ref', T_ref)
    prandtl_turbulent = _positive_scalar('prandtl_turbulent',
                                         prandtl_turbulent)

    needs_repo_gas = (mu_ref is None) or (cp is None)
    if needs_repo_gas and molecular_weight is None and gas_constant is None:
        missing = 'molecular_weight veya gas_constant'
        raise ValueError(
            f'Taşınım özelliği depo zincirinden türetilecek ama {missing} '
            'verilmedi. Depo bu durumda sessizce MW = 24 g/mol varsayar; '
            'uydurma gaz üstünden viskozite/cp yayımlanmaz. Ya '
            'molecular_weight (ya da gas_constant) verin ya da mu_ref ve '
            'cp değerlerini doğrudan geçirin.')

    properties = _repo_properties(gamma=gamma, temperature=T_ref,
                                  molecular_weight=molecular_weight,
                                  gas_constant=gas_constant)

    sources = {}
    if mu_ref is None:
        mu_ref = float(properties['gas_viscosity'])
        sources['viscosity'] = 'repo_chain'
    else:
        mu_ref = _positive_scalar('mu_ref', mu_ref)
        sources['viscosity'] = 'caller'
    if cp is None:
        cp = float(properties['gas_cp'])
        sources['cp'] = 'repo_chain'
    else:
        cp = _positive_scalar('cp', cp)
        sources['cp'] = 'caller'
    if prandtl is None:
        prandtl = float(properties['prandtl'])
        sources['prandtl'] = 'repo_chain'
    else:
        prandtl = _positive_scalar('prandtl', prandtl)
        sources['prandtl'] = 'caller'
    sources['prandtl_turbulent'] = 'model_constant'

    return GasTransport(gamma=gamma, T_ref=T_ref, mu_ref=mu_ref, cp=cp,
                        prandtl=prandtl,
                        prandtl_turbulent=prandtl_turbulent,
                        viscosity_exponent=viscosity_exponent(),
                        sources=sources)
