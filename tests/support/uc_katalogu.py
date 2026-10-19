"""Merkezî uç-yükü kataloğu — her POST ucu için ÖLÇÜLMÜŞ taban yük.

Neden bu dosya var
------------------
``tools/wiring_map`` ve ``tests/support/shake`` bu kod tabanının en güçlü
ölçüm altyapısı: bir ucu taban yüküyle çağırır, her girdiyi tek tek sarsar ve
"hangi girdi hangi çıktıyı oynatıyor" matrisini çıkarır. Matristen iki hata
sınıfı doğrudan okunur: **ölü girdi** (satır hiç değişmiyor) ve **uydurma
sabit** (sütun hiçbir girdiyle değişmiyor).

Bu altyapı v2.6.27'ye kadar ürünün **3 ucunda** koştu (``/calculate``,
``/calculate_solid``, ``/calculate_liquid``); üründe **80 POST ucu** var.
Kalan 77 ucun ölü-girdi / uydurma-sabit bekçisi YOKTU (kampanya kalemi
P10B4-16). Engelin kökü tek bir eksiklikti ve dört dalga boyunca aynı cümleyle
yazıldı: **ölçüm gövdesi her uç için GEÇERLİ bir taban yük ister ve ağaçta
merkezî bir uç-yükü kataloğu yoktu** — yükler 450 test dosyasına dağılmıştı,
çoğu bilerek GEÇERSİZ (fail-closed sınayan 400/422 yükleri).

Bu dosya o kataloğu tek yere toplar.

Yükler nereden geliyor
----------------------
Elle uydurulmadı, ÖLÇÜLDÜ. İki kaynaktan hasat edildi ve her biri canlı
``test_client`` ile **HTTP 200 verdiği doğrulanarak** kataloğa girdi:

1. ``tests/**`` içindeki ``client.post(yol, json={...})`` çağrılarının AST
   hasadı (literal yükler),
2. hedefli bir pytest koşumunda ``FlaskClient.post`` kaydı (fikstürlerden
   üretilen, literal olmayan yükler).

Kanıt: ``docs/scofield/raw/OH/D23/altyapi/a1/`` (once/sonra JSON + rapor).

Fail-closed sözleşme
--------------------
Katalog ürünün POST uçlarının **tamamını** taşımak zorundadır. Ölçülemeyen uç
sessizce atlanmaz; ADIYLA ve GEREKÇESİYLE bir sınıfa yazılır:

``olculebilir``      taban yükü var, sarsım matrisi koşabilir
``yan_etkili``       çağırmak makinede kalıcı iş yapar (indirme, kurulum,
                     dosya silme/yazma, tarayıcı açma) — ölçüm için çağrılmaz
``dosya_yuklemeli``  gövde multipart dosyadır, JSON sarsımı konusu değil
``govdesiz``         JSON gövdesi yok (sorgu dizgesi/boş gövde) — sarsılacak
                     alan yok
``kataloglanmadi``   HENÜZ geçerli taban yük ölçülemedi (gerekçe ZORUNLU)

``kapsam_raporu()`` katalog ile ``app.url_map`` arasındaki farkı verir;
``tests/test_d23_altyapi_a1.py`` bu farkın BOŞ olmasını kilitler. Yeni bir POST
ucu eklendiğinde bekçi kırmızıya döner ve ucu kataloglamaya zorlar — kapsamın
sessizce çürümesi bu şekilde imkânsızlaşır.
"""

from __future__ import annotations

import copy
import json
import pathlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[2]

#: Geçerli sınıf adları. ``olculebilir`` dışındaki her sınıf GEREKÇE ister.
SINIFLAR: Tuple[str, ...] = (
    'olculebilir', 'yan_etkili', 'dosya_yuklemeli', 'govdesiz',
    'kataloglanmadi',
)

#: Bir ucun 200 verebilmesi için kurulu olması gereken İSTEĞE BAĞLI paketler.
#: Paket yokken uç kendi aile ret kodunu döner (ör. export-step 501
#: ``step_backend_unavailable``); bu ürün davranışıdır, katalog bayatlığı
#: değildir. Ana CI işinde build123d BİLEREK kurulmaz (tests.yml), bu yüzden
#: o uçların canlı taban-yük düğümü ``step-export`` işinde koşar.
ARKA_UCLAR: Tuple[str, ...] = ('build123d',)

#: Sarsım matrisi koşulurken gönderilen başlık (shake.HEADERS ile aynı olmalı;
#: tek kaynak orasıdır, burada yalnız içe aktarılır).
def headers() -> Dict[str, str]:
    from tests.support import shake
    return dict(shake.HEADERS)


@dataclass(frozen=True)
class UcKaydi:
    """Bir POST ucunun katalog kaydı.

    ``yol``        Flask kuralı (``app.url_map`` ile birebir eşleşir).
    ``istek_yolu`` Gerçekte çağrılan yol; değişkenli kurallarda somut örnek
                   (``/api/detailed-cad/<motor_type>`` -> ``.../solid``).
    ``sinif``      ``SINIFLAR`` içinden biri.
    ``gerekce``    ``olculebilir`` değilse ZORUNLU: neden ölçülmüyor.
    ``kaynak``     Yükün nereden ölçüldüğü (dosya:satır ya da üretici adı).
    ``yuk``        Ölçülmüş taban yük (200 döndüğü doğrulanmış).
    ``uretici``    Yük dinamik üretiliyorsa üretici anahtarı; ``yuk`` ile
                   birlikte kullanılmaz (tek kaynak).
    ``arka_uc``    200 için gereken isteğe bağlı paket (``ARKA_UCLAR``);
                   ``None`` = her ortamda 200.
    """
    yol: str
    sinif: str
    gerekce: str = ''
    kaynak: str = ''
    yuk: Optional[Dict[str, Any]] = None
    uretici: Optional[str] = None
    istek_yolu: Optional[str] = None
    #: Sarsımda atlanacak anahtarlar (ör. dosya adı, proje adı gibi kimlikler).
    sarsilmaz: Tuple[str, ...] = ()
    arka_uc: Optional[str] = None

    def __post_init__(self):
        if self.sinif not in SINIFLAR:
            raise ValueError(f'{self.yol}: bilinmeyen sinif {self.sinif!r}')
        if self.arka_uc is not None and self.arka_uc not in ARKA_UCLAR:
            raise ValueError(f'{self.yol}: bilinmeyen arka uc {self.arka_uc!r}')
        if self.sinif == 'olculebilir':
            if self.yuk is None and self.uretici is None:
                raise ValueError(f'{self.yol}: olculebilir kayit yuksuz olamaz')
            if self.yuk is not None and self.uretici is not None:
                raise ValueError(f'{self.yol}: yuk ve uretici birlikte olmaz')
        else:
            if not self.gerekce:
                raise ValueError(f'{self.yol}: {self.sinif} kaydi gerekcesiz '
                                 'olamaz (fail-closed)')

    @property
    def cagri_yolu(self) -> str:
        return self.istek_yolu or self.yol


# ---------------------------------------------------------------------------
# Dinamik yük üreticileri — TEK KAYNAK.
#
# Üç motor sayfasının taban yükü ağaçta ZATEN var; kataloğa kopyalanmaz,
# oradan okunur. Kopyalasaydık iki gerçek olurdu ve biri bayatlardı.
# ---------------------------------------------------------------------------

#: ``/calculate_solid`` ve ``/calculate_liquid`` taban yükünün geldiği örnek
#: projeler (``tools/wiring_map.EXAMPLE_FOR`` ile aynı dosyalar).
ORNEK_PROJE = {
    '/calculate_solid': 'Example Solid KNDX BATES 75mm.hrma',
    '/calculate_liquid': 'Example Liquid LOX-RP1 25kN.hrma',
}


def _ornek_projeden(yol: str) -> Dict[str, Any]:
    ornek = ROOT / 'examples' / ORNEK_PROJE[yol]
    if not ornek.is_file():
        raise FileNotFoundError(f'ornek proje yok: {ornek}')
    with ornek.open(encoding='utf-8') as fh:
        proje = json.load(fh)
    alanlar = dict((proje.get('inputs') or {}).get('fields') or {})
    if not alanlar:
        raise ValueError(f'{ornek} icinde inputs.fields yok')
    return alanlar


def _hibrit_taban() -> Dict[str, Any]:
    # Katman B bekçisinin taban yükü; harita da onu ödünç alıyor.
    import importlib
    mod = importlib.import_module('tests.test_field_wiring_layer_b')
    return dict(mod.HYBRID_BASE)


URETICILER = {
    'hibrit': _hibrit_taban,
    'kati': lambda: _ornek_projeden('/calculate_solid'),
    'sivi': lambda: _ornek_projeden('/calculate_liquid'),
}


# ---------------------------------------------------------------------------
# Katalog API'si
# ---------------------------------------------------------------------------

def kayitlar() -> Dict[str, UcKaydi]:
    """Yol -> kayıt eşlemesi (kopya değil, kayıtlar dondurulmuş)."""
    return dict(KAYITLAR)


def kayit(yol: str) -> UcKaydi:
    try:
        return KAYITLAR[yol]
    except KeyError:
        raise KeyError(f'{yol} katalogda yok — yeni uc kataloglanmali '
                       '(fail-closed: sessiz atlama yok)') from None


def olculebilir_uclar() -> List[str]:
    """Sarsım matrisi koşulabilen uçların yolları (sıralı)."""
    return sorted(y for y, k in KAYITLAR.items() if k.sinif == 'olculebilir')


def sinif_dagilimi() -> Dict[str, int]:
    d: Dict[str, int] = {}
    for k in KAYITLAR.values():
        d[k.sinif] = d.get(k.sinif, 0) + 1
    return dict(sorted(d.items()))


def taban_yuk(yol: str) -> Dict[str, Any]:
    """Ucun ölçülmüş taban yükünün DERİN kopyası.

    Fail-closed: ölçülemeyen sınıflar için sessiz boş sözlük DÖNMEZ, gerekçeli
    hata yükseltir. "Yükü yoksa boş gönder" davranışı ucu yalancı-ölü
    gösterirdi (taban 400 dönerse sarsım da 400 döner ve her alan
    'ölçülemedi' olurdu) — tam olarak bu kalemin kovaladığı sınıf.
    """
    k = kayit(yol)
    if k.sinif != 'olculebilir':
        raise ValueError(f'{yol}: sinif={k.sinif}, taban yuk yok — {k.gerekce}')
    if k.uretici:
        return dict(URETICILER[k.uretici]())
    return copy.deepcopy(k.yuk or {})


def post_uclari(app) -> List[str]:
    """Uygulamanın POST kabul eden uçları (static hariç, sıralı)."""
    uclar = []
    for r in app.url_map.iter_rules():
        if r.endpoint == 'static':
            continue
        if 'POST' in (r.methods or set()):
            uclar.append(str(r.rule))
    return sorted(uclar)


def kapsam_raporu(app) -> Dict[str, Any]:
    """Katalog ile uygulamanın POST uçları arasındaki fark.

    ``eksik``  üründe var, katalogda yok  -> yeni uç kataloglanmalı
    ``fazla``  katalogda var, üründe yok  -> uç kaldırılmış, katalog bayat
    """
    urun = set(post_uclari(app))
    katalog = set(KAYITLAR)
    return {
        'urun_post_sayisi': len(urun),
        'katalog_kayit_sayisi': len(katalog),
        'eksik': sorted(urun - katalog),
        'fazla': sorted(katalog - urun),
        'sinif_dagilimi': sinif_dagilimi(),
        'olculebilir_sayisi': len(olculebilir_uclar()),
    }


def alan_speclari(yol: str):
    """Taban yükten sarsım şartnamelerini (``shake.FieldSpec``) türetir.

    Şablonu olan üç motor sayfasının aksine API uçlarının HTML formu yoktur;
    alan tipi ve bandı taban yükün KENDİ değerinden okunur:

    * ``bool``   -> ikili alan (çevrilir),
    * sayı       -> ``number`` (shake ×1,5 / ×0,5 dener),
    * metin      -> seçenek listesi bilinmediği için sarsılamaz; shake bunu
      ``unmeasurable`` olarak ADIYLA bildirir (sessiz atlama yok),
    * ``dict``/``list`` -> iç anahtarlar bu katmanda sarsılmaz; sayıları
      ``ic_anahtarlar()`` ile BEYAN edilir.
    """
    from tests.support import shake
    yuk = taban_yuk(yol)
    atla = set(kayit(yol).sarsilmaz)
    specs = []
    for ad in sorted(yuk):
        if ad in atla:
            continue
        deger = yuk[ad]
        if isinstance(deger, bool):
            specs.append(shake.FieldSpec(name=ad, kind='bool'))
        elif isinstance(deger, (int, float)):
            specs.append(shake.FieldSpec(name=ad, kind='number'))
        elif isinstance(deger, str):
            specs.append(shake.FieldSpec(name=ad, kind='choice', options=()))
    return specs


def ic_anahtarlar(yol: str) -> Dict[str, int]:
    """Bu katmanda SARSILMAYAN iç (sözlük/dizi) anahtarların sayımı.

    Kapsam beyanı: harita bunu yayımlar ki "ölçüldü" hükmü ölçüm gücünü
    saklamasın. Sıfır değilse o uçta iç anahtarların ölü/uydurma taraması
    henüz YAPILMAMIŞTIR (yapıldı gibi gösterilmez).
    """
    yuk = taban_yuk(yol)
    return {ad: (len(deger) if hasattr(deger, '__len__') else 1)
            for ad, deger in sorted(yuk.items())
            if isinstance(deger, (dict, list))}


# ---------------------------------------------------------------------------
# ÖLÇÜLMÜŞ TABAN YÜKLER
#
# Yüklerin kendisi ``uc_yukleri.json`` içindedir (ölçüm verisi; elle
# yazılmaz, hasat edilir ve 200 verdiği doğrulanır). Sınıflandırma ve
# GEREKÇELER burada, kodda durur — inceleme konusu onlardır.
# ---------------------------------------------------------------------------

YUK_DOSYASI = pathlib.Path(__file__).with_name('uc_yukleri.json')


def _yukleri_oku() -> Dict[str, Dict[str, Any]]:
    with YUK_DOSYASI.open(encoding='utf-8') as fh:
        return json.load(fh)


_YUKLER = _yukleri_oku()


#: Ürünün BÜTÜN POST uçları. Eksiği bekçi kırmızıya döndürür.
KAYITLAR: Dict[str, UcKaydi] = {
    '/analyze_safety': UcKaydi(
        yol='/analyze_safety',
        sinif='olculebilir',
        kaynak='tests/test_wave3_contract.py (canli kayit)',
        yuk=_YUKLER['/analyze_safety'],
    ),
    '/analyze_structural_safety': UcKaydi(
        yol='/analyze_structural_safety',
        sinif='olculebilir',
        kaynak='tests/test_d21_yapisal_sistem_a1.py:391 (AST hasadi)',
        yuk=_YUKLER['/analyze_structural_safety'],
    ),
    '/analyze_thermal_safety': UcKaydi(
        yol='/analyze_thermal_safety',
        sinif='olculebilir',
        kaynak='tests/test_wave3_contract.py (canli kayit)',
        yuk=_YUKLER['/analyze_thermal_safety'],
    ),
    '/api/advanced-analysis': UcKaydi(
        yol='/api/advanced-analysis',
        sinif='olculebilir',
        kaynak='tests/test_d15_fea_viz_a2.py:219 (AST hasadi)',
        yuk=_YUKLER['/api/advanced-analysis'],
    ),
    '/api/advanced-performance-analysis': UcKaydi(
        yol='/api/advanced-performance-analysis',
        sinif='olculebilir',
        kaynak='tests/test_d15_fea_viz_a2.py:586 (AST hasadi)',
        yuk=_YUKLER['/api/advanced-performance-analysis'],
    ),
    '/api/altitude-to-pressure': UcKaydi(
        yol='/api/altitude-to-pressure',
        sinif='olculebilir',
        kaynak='tests/test_export_injection_guard.py:185 (AST hasadi)',
        yuk=_YUKLER['/api/altitude-to-pressure'],
    ),
    '/api/analysis/combustion-stability': UcKaydi(
        yol='/api/analysis/combustion-stability',
        sinif='olculebilir',
        kaynak='tests/test_wave4a_contract.py (canli kayit)',
        yuk=_YUKLER['/api/analysis/combustion-stability'],
    ),
    # OH D30 / app-api-uc a1 · OH-D29-13 (+ P7B1-22): '/api/analysis/
    # thermal-protection' takma yolu SILINDI (urun tarafinda 0 esleme,
    # yanit kardes yolla bit-ayniydi). Kardes yol '/api/thermal-protection'
    # asagida durur ve envanteri o tasir.
    '/api/analysis/wall-profile': UcKaydi(
        yol='/api/analysis/wall-profile',
        sinif='olculebilir',
        kaynak='tests/test_wave4b_contract.py (canli kayit)',
        yuk=_YUKLER['/api/analysis/wall-profile'],
    ),
    '/api/bolted-joint': UcKaydi(
        yol='/api/bolted-joint',
        sinif='olculebilir',
        kaynak='tests/test_wave3_contract.py (canli kayit)',
        yuk=_YUKLER['/api/bolted-joint'],
    ),
    '/api/burn-rate/resolve': UcKaydi(
        yol='/api/burn-rate/resolve',
        sinif='olculebilir',
        kaynak='tests/test_burn_rate_resolve.py:63 (AST hasadi)',
        yuk=_YUKLER['/api/burn-rate/resolve'],
    ),
    '/api/cfd-analysis': UcKaydi(
        yol='/api/cfd-analysis',
        sinif='kataloglanmadi',
        gerekce='uc 501 Not Implemented donduruyor (halef /api/cfd/nozzle); 200 veren taban yuk YOK',
    ),
    '/api/cfd/nozzle': UcKaydi(
        yol='/api/cfd/nozzle',
        sinif='olculebilir',
        kaynak='tests/test_d16_fea_cfd_a1.py (canli kayit)',
        yuk=_YUKLER['/api/cfd/nozzle'],
    ),
    '/api/chemical-species': UcKaydi(
        yol='/api/chemical-species',
        sinif='olculebilir',
        kaynak='tests/test_d21_app_api_a1.py:370 (AST hasadi)',
        yuk=_YUKLER['/api/chemical-species'],
    ),
    '/api/combustion-stability': UcKaydi(
        yol='/api/combustion-stability',
        sinif='olculebilir',
        kaynak='kardes /api/analysis/combustion-stability yuku (200 dogrulandi)',
        yuk=_YUKLER['/api/combustion-stability'],
    ),
    '/api/comparative-analysis': UcKaydi(
        yol='/api/comparative-analysis',
        sinif='olculebilir',
        kaynak='tests/test_wave4a_contract.py (canli kayit)',
        yuk=_YUKLER['/api/comparative-analysis'],
    ),
    '/api/correlation-report': UcKaydi(
        yol='/api/correlation-report',
        sinif='olculebilir',
        kaynak='tests/test_correlation_endpoint.py:48 (AST hasadi)',
        yuk=_YUKLER['/api/correlation-report'],
    ),
    '/api/detailed-cad/<motor_type>': UcKaydi(
        yol='/api/detailed-cad/<motor_type>',
        sinif='olculebilir',
        kaynak='tests/test_z5s_ihracat_kapisi.py (canli kayit)',
        istek_yolu='/api/detailed-cad/liquid',
        yuk=_YUKLER['/api/detailed-cad/<motor_type>'],
    ),
    '/api/export-cad': UcKaydi(
        yol='/api/export-cad',
        sinif='olculebilir',
        kaynak='tests/test_z5s_govde_kapisi.py:242 (AST hasadi)',
        yuk=_YUKLER['/api/export-cad'],
    ),
    '/api/export-chart-pdf': UcKaydi(
        yol='/api/export-chart-pdf',
        sinif='olculebilir',
        kaynak='D23 a1 olcumu (Plotly JSON, 200 dogrulandi)',
        yuk=_YUKLER['/api/export-chart-pdf'],
    ),
    '/api/export-complete-zip': UcKaydi(
        yol='/api/export-complete-zip',
        sinif='olculebilir',
        kaynak='tests/test_d16_ihracat_a1.py (canli kayit)',
        yuk=_YUKLER['/api/export-complete-zip'],
    ),
    '/api/export-drawings-pdf': UcKaydi(
        yol='/api/export-drawings-pdf',
        sinif='olculebilir',
        kaynak='tests/test_faz5_app_export.py:486 (AST hasadi)',
        yuk=_YUKLER['/api/export-drawings-pdf'],
    ),
    '/api/export-dxf': UcKaydi(
        yol='/api/export-dxf',
        sinif='olculebilir',
        kaynak='tests/test_faz5_app_export.py:463 (AST hasadi)',
        yuk=_YUKLER['/api/export-dxf'],
    ),
    '/api/export-eng': UcKaydi(
        yol='/api/export-eng',
        sinif='olculebilir',
        kaynak='tests/test_d16_ihracat_a1.py (canli kayit)',
        yuk=_YUKLER['/api/export-eng'],
    ),
    '/api/export-openrocket': UcKaydi(
        yol='/api/export-openrocket',
        sinif='olculebilir',
        kaynak='tests/test_z5s_ihracat_kapisi.py (canli kayit)',
        yuk=_YUKLER['/api/export-openrocket'],
    ),
    '/api/export-pdf/<report_type>': UcKaydi(
        yol='/api/export-pdf/<report_type>',
        sinif='olculebilir',
        kaynak='tests/test_pdf_analysis.py:216 (AST hasadi)',
        istek_yolu='/api/export-pdf/complete',
        yuk=_YUKLER['/api/export-pdf/<report_type>'],
    ),
    '/api/export-simulation': UcKaydi(
        yol='/api/export-simulation',
        sinif='olculebilir',
        kaynak='tests/test_z5s_ihracat_kapisi.py (canli kayit)',
        yuk=_YUKLER['/api/export-simulation'],
    ),
    '/api/export-step': UcKaydi(
        yol='/api/export-step',
        sinif='olculebilir',
        kaynak='tests/test_faz4_app_export.py (canli kayit)',
        yuk=_YUKLER['/api/export-step'],
        arka_uc='build123d',
    ),
    '/api/export-stl': UcKaydi(
        yol='/api/export-stl',
        sinif='olculebilir',
        kaynak='tests/test_d16_ihracat_a1.py (canli kayit)',
        yuk=_YUKLER['/api/export-stl'],
    ),
    '/api/export-stl-zip': UcKaydi(
        yol='/api/export-stl-zip',
        sinif='olculebilir',
        kaynak='tests/test_faz4_app_export.py (canli kayit)',
        yuk=_YUKLER['/api/export-stl-zip'],
    ),
    '/api/export-xlsx': UcKaydi(
        yol='/api/export-xlsx',
        sinif='olculebilir',
        kaynak='tests/test_export_injection_guard.py:122 (AST hasadi)',
        yuk=_YUKLER['/api/export-xlsx'],
    ),
    '/api/fea/planar-grain': UcKaydi(
        yol='/api/fea/planar-grain',
        sinif='olculebilir',
        kaynak='tests/test_d18_arayuz_a1.py (canli kayit)',
        yuk=_YUKLER['/api/fea/planar-grain'],
    ),
    '/api/fea/structural': UcKaydi(
        yol='/api/fea/structural',
        sinif='olculebilir',
        kaynak='tests/test_d18_arayuz_a1.py (canli kayit, motor_results skalarlara budandi: 274 KB -> 5,3 KB, 200 dogrulandi)',
        yuk=_YUKLER['/api/fea/structural'],
    ),
    '/api/fea/thermal': UcKaydi(
        yol='/api/fea/thermal',
        sinif='kataloglanmadi',
        gerekce='olculdu: kardes /api/fea/structural yuku 422 not_modelled veriyor — uc TERMAL MODELLENMIS bir motor sonucu ister; boyle bir taban yuk bu turda olculemedi',
    ),
    '/api/find-optimum-of': UcKaydi(
        yol='/api/find-optimum-of',
        sinif='olculebilir',
        kaynak='tests/test_d21_app_api_a2.py:303 (AST hasadi)',
        yuk=_YUKLER['/api/find-optimum-of'],
    ),
    '/api/flight-vehicle': UcKaydi(
        yol='/api/flight-vehicle',
        sinif='olculebilir',
        kaynak='tests/test_d20_electron_a1.py:385 (AST hasadi)',
        yuk=_YUKLER['/api/flight-vehicle'],
    ),
    '/api/flow-analysis': UcKaydi(
        yol='/api/flow-analysis',
        sinif='olculebilir',
        kaynak='tests/test_wave4a_contract.py (canli kayit)',
        yuk=_YUKLER['/api/flow-analysis'],
    ),
    '/api/generate-3d': UcKaydi(
        yol='/api/generate-3d',
        sinif='olculebilir',
        kaynak='tests/test_d21_app_api_a2.py (canli kayit)',
        yuk=_YUKLER['/api/generate-3d'],
    ),
    '/api/generate-complete-package': UcKaydi(
        yol='/api/generate-complete-package',
        sinif='olculebilir',
        kaynak='tests/test_z5s_ihracat_kapisi.py:281 (AST hasadi)',
        yuk=_YUKLER['/api/generate-complete-package'],
    ),
    '/api/get-fuel-properties': UcKaydi(
        yol='/api/get-fuel-properties',
        sinif='olculebilir',
        kaynak='tests/test_d21_app_api_a1.py:384 (AST hasadi)',
        yuk=_YUKLER['/api/get-fuel-properties'],
    ),
    '/api/get-propellant-properties': UcKaydi(
        yol='/api/get-propellant-properties',
        sinif='olculebilir',
        kaynak='tests/test_d16_ihracat_a2.py (canli kayit)',
        yuk=_YUKLER['/api/get-propellant-properties'],
    ),
    '/api/gimbal-mount': UcKaydi(
        yol='/api/gimbal-mount',
        sinif='olculebilir',
        kaynak='tests/test_gimbal_baglama.py (canli kayit)',
        yuk=_YUKLER['/api/gimbal-mount'],
    ),
    '/api/import/motor-file': UcKaydi(
        yol='/api/import/motor-file',
        sinif='olculebilir',
        kaynak='tests/test_wave4a_contract.py (canli kayit)',
        yuk=_YUKLER['/api/import/motor-file'],
    ),
    '/api/import/ork': UcKaydi(
        yol='/api/import/ork',
        sinif='olculebilir',
        kaynak='tests/test_d16_ihracat_a2.py (canli kayit)',
        yuk=_YUKLER['/api/import/ork'],
    ),
    '/api/import/step': UcKaydi(
        yol='/api/import/step',
        sinif='dosya_yuklemeli',
        gerekce='gövde multipart STEP dosyasidir (request.files); JSON alan sarsimi konusu degil',
    ),
    '/api/injector-design': UcKaydi(
        yol='/api/injector-design',
        sinif='olculebilir',
        kaynak='tests/test_z5s_ham_500.py (canli kayit)',
        yuk=_YUKLER['/api/injector-design'],
    ),
    '/api/kinetic-analysis': UcKaydi(
        yol='/api/kinetic-analysis',
        sinif='kataloglanmadi',
        gerekce='uc 501 Not Implemented donduruyor (halef /api/kinetic-efficiency); 200 veren taban yuk YOK',
    ),
    '/api/kinetic-efficiency': UcKaydi(
        yol='/api/kinetic-efficiency',
        sinif='olculebilir',
        kaynak='tests/test_wave4a_contract.py (canli kayit)',
        yuk=_YUKLER['/api/kinetic-efficiency'],
    ),
    '/api/launch-site/resolve': UcKaydi(
        yol='/api/launch-site/resolve',
        sinif='olculebilir',
        kaynak='tests/test_d19_termo_ucus_a1.py:180 (AST hasadi)',
        yuk=_YUKLER['/api/launch-site/resolve'],
    ),
    '/api/oxidizer-properties': UcKaydi(
        yol='/api/oxidizer-properties',
        sinif='olculebilir',
        kaynak='tests/test_d16_arayuz_a1.py (canli kayit)',
        yuk=_YUKLER['/api/oxidizer-properties'],
    ),
    '/api/pressurant-sizing': UcKaydi(
        yol='/api/pressurant-sizing',
        sinif='olculebilir',
        kaynak='tests/test_wave4b_contract.py (canli kayit)',
        yuk=_YUKLER['/api/pressurant-sizing'],
    ),
    '/api/pressure-vessel-analysis': UcKaydi(
        yol='/api/pressure-vessel-analysis',
        sinif='olculebilir',
        kaynak='tests/test_wave3_contract.py (canli kayit)',
        yuk=_YUKLER['/api/pressure-vessel-analysis'],
    ),
    '/api/professional-analysis': UcKaydi(
        yol='/api/professional-analysis',
        sinif='kataloglanmadi',
        gerekce='uc 501 Not Implemented donduruyor (halef uclara yonlendirme beyani); 200 veren taban yuk YOK',
    ),
    '/api/projects/delete': UcKaydi(
        yol='/api/projects/delete',
        sinif='yan_etkili',
        gerekce='kayitli projeyi .trash dizinine TASIR (kalici is); sarsim olcumu kullanici verisini oynatir',
    ),
    '/api/projects/save': UcKaydi(
        yol='/api/projects/save',
        sinif='yan_etkili',
        gerekce='kullanicinin proje dizinine DOSYA YAZAR; sarsim matrisi her alan icin yeni bir kayit birakirdi',
    ),
    '/api/quick-geometry': UcKaydi(
        yol='/api/quick-geometry',
        sinif='olculebilir',
        kaynak='tests/test_d21_app_api_a1.py (canli kayit)',
        yuk=_YUKLER['/api/quick-geometry'],
    ),
    '/api/regen-cooling': UcKaydi(
        yol='/api/regen-cooling',
        sinif='olculebilir',
        kaynak='tests/test_wave4b_contract.py (canli kayit)',
        yuk=_YUKLER['/api/regen-cooling'],
    ),
    '/api/regression-analysis': UcKaydi(
        yol='/api/regression-analysis',
        sinif='olculebilir',
        kaynak='tests/test_d22_yapisal_sistem_a1.py:349 (AST hasadi)',
        yuk=_YUKLER['/api/regression-analysis'],
    ),
    '/api/six-dof-analysis': UcKaydi(
        yol='/api/six-dof-analysis',
        sinif='olculebilir',
        kaynak='tests/test_faz5_app_analiz.py (canli kayit)',
        yuk=_YUKLER['/api/six-dof-analysis'],
    ),
    '/api/slosh-analysis': UcKaydi(
        yol='/api/slosh-analysis',
        sinif='olculebilir',
        kaynak='tests/test_wave4b_contract.py (canli kayit)',
        yuk=_YUKLER['/api/slosh-analysis'],
    ),
    '/api/solid-monte-carlo': UcKaydi(
        yol='/api/solid-monte-carlo',
        sinif='olculebilir',
        kaynak='tests/test_d18_app_api_a1.py (canli kayit)',
        yuk=_YUKLER['/api/solid-monte-carlo'],
    ),
    '/api/thermal-protection': UcKaydi(
        yol='/api/thermal-protection',
        sinif='olculebilir',
        kaynak='tests/test_d16_arayuz_a1.py (canli kayit)',
        yuk=_YUKLER['/api/thermal-protection'],
    ),
    '/api/tile/cache/clear': UcKaydi(
        yol='/api/tile/cache/clear',
        sinif='yan_etkili',
        gerekce='disk uzerindeki karo onbellegini SILER; olcum ugruna cagrilmaz',
    ),
    '/api/trajectory-analysis': UcKaydi(
        yol='/api/trajectory-analysis',
        sinif='olculebilir',
        kaynak='tests/test_z5s_ham_500.py (canli kayit)',
        yuk=_YUKLER['/api/trajectory-analysis'],
    ),
    '/api/transient-analysis': UcKaydi(
        yol='/api/transient-analysis',
        sinif='olculebilir',
        kaynak='tests/test_wave3_contract.py (canli kayit)',
        yuk=_YUKLER['/api/transient-analysis'],
    ),
    '/api/uncertainty-analysis': UcKaydi(
        yol='/api/uncertainty-analysis',
        sinif='olculebilir',
        kaynak='tests/test_d15_yapisal_sistem_a1.py:239 (AST hasadi)',
        yuk=_YUKLER['/api/uncertainty-analysis'],
    ),
    '/api/update/download': UcKaydi(
        yol='/api/update/download',
        sinif='yan_etkili',
        gerekce='GitHub uzerinden surum paketi INDIRIR (ag + disk); olcum ugruna cagrilmaz',
    ),
    '/api/update/install': UcKaydi(
        yol='/api/update/install',
        sinif='yan_etkili',
        gerekce='indirilen paketi KURAR ve uygulamayi yeniden baslatir; olcum ugruna cagrilmaz',
    ),
    '/api/update/open-download': UcKaydi(
        yol='/api/update/open-download',
        sinif='yan_etkili',
        gerekce='sunucu makinesinde SISTEM TARAYICISINI acar (webbrowser.open)',
    ),
    '/api/user-guide/open': UcKaydi(
        yol='/api/user-guide/open',
        sinif='govdesiz',
        gerekce='yuk JSON degil sorgu dizgesidir (?lang=tr|en) ve yanit dosya yolu/URL beyanidir; sarsilacak sayisal alan yok',
    ),
    '/api/validate-fuel': UcKaydi(
        yol='/api/validate-fuel',
        sinif='olculebilir',
        kaynak='tests/test_d16_app_api_a2.py:258 (AST hasadi)',
        yuk=_YUKLER['/api/validate-fuel'],
    ),
    '/api/validation/upload-csv': UcKaydi(
        yol='/api/validation/upload-csv',
        sinif='olculebilir',
        kaynak='tests/test_wave4a_contract.py (canli kayit)',
        yuk=_YUKLER['/api/validation/upload-csv'],
    ),
    '/api/water-hammer': UcKaydi(
        yol='/api/water-hammer',
        sinif='olculebilir',
        kaynak='tests/test_wave4b_contract.py (canli kayit)',
        yuk=_YUKLER['/api/water-hammer'],
    ),
    '/calculate': UcKaydi(
        yol='/calculate',
        sinif='olculebilir',
        kaynak='tests/test_field_wiring_layer_b.HYBRID_BASE',
        uretici='hibrit',
    ),
    '/calculate_liquid': UcKaydi(
        yol='/calculate_liquid',
        sinif='olculebilir',
        kaynak='examples/*.hrma (sivi)',
        uretici='sivi',
    ),
    '/calculate_solid': UcKaydi(
        yol='/calculate_solid',
        sinif='olculebilir',
        kaynak='examples/*.hrma (kati)',
        uretici='kati',
    ),
    '/export_liquid_cad': UcKaydi(
        yol='/export_liquid_cad',
        sinif='kataloglanmadi',
        gerekce='olculdu: results tasiyicisi tam bir COZULMUS sivi motor sonucu ister; odunc yukler 422 (CAD ureticileri geometriyi reddediyor)',
    ),
    '/export_solid_motor_cad': UcKaydi(
        yol='/export_solid_motor_cad',
        sinif='kataloglanmadi',
        gerekce='olculdu: results tasiyicisi tam bir COZULMUS kati motor sonucu ister; odunc yukler 422',
    ),
    '/export_tank_cad': UcKaydi(
        yol='/export_tank_cad',
        sinif='olculebilir',
        kaynak='tests/test_z5s_ihracat_kapisi.py (canli kayit)',
        yuk=_YUKLER['/export_tank_cad'],
    ),
    '/parametric-analysis': UcKaydi(
        yol='/parametric-analysis',
        sinif='olculebilir',
        kaynak='tests/test_faz4_app_export.py (canli kayit)',
        yuk=_YUKLER['/parametric-analysis'],
    ),
}
