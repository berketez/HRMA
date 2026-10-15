"""Girdi-çıktı sarsım matrisi: ölü girdi ve uydurma sabit tarayıcısı.

Bu modül tek bir ölçüm yapar ve o ölçümden İKİ ayrı hata sınıfı çıkar:

    her form alanı x her çıktı yaprağı -> değişti mi?

* **Satır hiç değişmiyorsa** o girdi ÖLÜDÜR: kullanıcı değeri giriyor ama
  sonuca hiç girmiyor. (v2.5.2'de sıvının 55 girdisi, v2.6.25'te hibritin
  3 termal alanı, v2.6.26'da katının ~29 alanı bu şekilde bulundu.)
* **Sütun hiçbir girdiyle değişmiyorsa** o çıktı UYDURMA SABİTTİR: hiçbir
  girdiden etkilenmiyor, yani hesaplanmıyor. (``strand_burner_tests: 5``,
  ``dimensional_accuracy_percent: 99.5``, ``$500-800 USD`` bu şekilde
  hayatta kalmıştı — üç ayrı elle süpürmeden.)

Neden bu gerekli: ``tests/test_no_fabrication.py`` 17 BİLİNEN vakayı sabitler.
Vaka listelemek yeni uydurmayı yakalamaz. Bu modül vaka listelemez, tarar.

Kullanım kalıbı testlerde::

    from tests.support import shake
    report = shake.run(shake.HYBRID)
    assert not report.dead_inputs
    assert not report.constant_outputs

Ölçüm koşulları (v2.6.26'da ölçüldü):
- Yanıtlar bit düzeyinde deterministik (aynı istek iki kez -> 0 yaprak fark),
  bu yüzden ``rel_tol=1e-9`` güvenli; tolerans yalnız platform farkı için var.
- Flask ``test_client`` kullanılır, gerçek sunucu AÇILMAZ; tek süreçte koşar
  (paralel süreç SQLite kilit çekişmesi yaratıyordu).
- 195 alanlık tam tarama sıcak önbellekte 53 sn, soğukta 2-5 dk sürüyor.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

HEADERS = {'Host': '127.0.0.1:8080'}


# ---------------------------------------------------------------------------
# Yaprak düzleştirme ve karşılaştırma
# ---------------------------------------------------------------------------

def leaves(obj: Any, path: str = '') -> Iterable[Tuple[str, Any]]:
    """İç içe JSON'u {yol: skaler} çiftlerine düzleştirir."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from leaves(value, f'{path}.{key}')
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            yield from leaves(value, f'{path}[{idx}]')
    else:
        yield path, obj


def differing_paths(before: Dict[str, Any], after: Dict[str, Any],
                    rel_tol: float = 1e-9) -> List[str]:
    """Değişen yaprak yollarını döndürür."""
    changed = []
    for key in set(before) | set(after):
        a, b = before.get(key), after.get(key)
        if (isinstance(a, (int, float)) and isinstance(b, (int, float))
                and not isinstance(a, bool) and not isinstance(b, bool)):
            if math.isnan(a) and math.isnan(b):
                continue
            if not math.isclose(a, b, rel_tol=rel_tol):
                changed.append(key)
        elif a != b:
            changed.append(key)
    return changed


#: Yankı önek -> kanonik önek eşlemesi (v2.6.27 tekilleştirme).
#:
#: /calculate yanıtı üst seviye ``motor`` bloğunu iki yerde daha taşır:
#: ``trajectory.motor_data`` ve ``openrocket.flight_profile.motor_data``.
#: ÖLÇÜLDÜ (P-5 denetiminin "bit-aynı kopya" beyanı, canlı test_client):
#: trajectory.motor_data 1604/1604 yaprakta motor ile eşit; Pc 20→35
#: sarsımında ikisi de AYNI 1286 yaprakta birlikte değişti. Kopya sayım
#: birimini üçe katlıyordu: 372 "sabit yaprak" bayrağının 228'i aynı 114
#: sabitin yankısıydı. Tekilleştirme sayım birimini SABİT başına bire indirir;
#: kopya sözleşmesinin kendisi ayrıca ölçülür (bkz. ``yanki_ayristi``).
#:
#: v2.6.27 (yirmi ikinci parti artçısı) — ÜÇÜNCÜ KOPYA: üst seviye
#: ``.injector_design``. ``app.py`` bu anahtarı ``motor_results
#: ['injector_design']`` ile AYNI nesneden doldurur (results sözlüğü
#: kurulurken), yani kopya tanımı gereği bit-aynıdır. ÖLÇÜLDÜ (canlı
#: test_client, HYBRID_BASE): üst seviye blok 11 yaprak, ``.motor.
#: injector_design`` 11 yaprak; 11/11 bit-aynı, iki yönde de eksik/fazla
#: yaprak YOK. Ürün yanıtı DEĞİŞTİRİLMEDİ (ön yüz üst seviye bloğu
#: okuyabilir) — yalnız sayım birimi tekilleştirildi; bit-aynılık şartı
#: aşağıdaki kopya sözleşmesi geçişiyle her koşuda yeniden ölçülür,
#: ayrışırsa indirgeme kendiliğinden iptal olur.
#: v2.6.27 (yirmi altıncı parti) — ÜÇÜNCÜ KOPYANIN İKİ KARDEŞİ.
#: Bu liste ELLE tutuluyor ve yirmi ikinci parti ``.injector_design``i elle
#: bulup orada durmuştu. Bu turda liste TARANARAK denetlendi: taban yanıtın
#: bütün alt ağaçları imzalanıp (göreli yol -> değer) bit-aynı olanlar
#: eşleştirildi. Tarama, aynı sınıftan iki kopya daha buldu:
#: ``.design_summary`` (24/24 yaprak ``.motor.design_summary`` ile bit-aynı)
#: ve ``.grain_design`` (9/9 yaprak ``.motor.grain_design`` ile bit-aynı).
#: Birlikte-değişme de ÖLÇÜLDÜ (chamber_pressure 20->30, thrust 5000->7500,
#: of_ratio 2,5->3,5): üç sarsımda da kopya ile kanonik AYNI göreli yaprak
#: kümesini değiştirdi (15/15, 14/14, 7/7).
#:
#: DÜRÜSTLÜK NOTU — bu iki girişin SABİT SAYIMINA katkısı SIFIRDIR: iki
#: bloğun da sayısal yapraklarının tamamı canlı, yani indirgenecek sabit
#: yok (ölçüldü). Eklenme sebebi sayım değil SÖZLEŞME KAPSAMI: bu
#: önekler eklendiği an iki blok da ``yanki_ayristi`` denetimine girer,
#: yani üst seviye kopya bir gün bayat/varsayılan veriyle beslenirse
#: (uçuş simülasyonunun eski motor verisiyle beslenmesi sınıfı)
#: ``test_motor_echo_copies_never_diverge`` kırmızıya döner. Kopya
#: kapsanmadıkça o kusur sessizce yaşar.
ECHO_CANONICAL_PREFIXES = (
    ('.trajectory.motor_data', '.motor'),
    ('.openrocket.flight_profile.motor_data', '.motor'),
    ('.injector_design', '.motor.injector_design'),
    ('.design_summary', '.motor.design_summary'),
    ('.grain_design', '.motor.grain_design'),
)

#: BEYAN YANKISI: değeri, kullanıcının GÖNDERDİĞİ sayının birebir kendisi
#: olan yaprak. ``inputs_not_used[i].submitted`` tam olarak budur —
#: ``app.py::_declare_overridden_inputs`` bu alana ``float(data[field])``
#: yazar, yani hesabın değil İSTEĞİN kopyasıdır ("şunu gönderdiniz ama
#: çözücü kendi hesabını kullanıyor" beyanının 'şunu gönderdiniz' yarısı).
#:
#: Neden gerekli: sabit-çıktı taraması sayısal yaprakların hiçbir sarsımda
#: kıpırdamamasını arıyor. Bu yaprak, ilgili alan SARSILMADIĞI sürece
#: kıpırdamaz ve "uydurma sabit" gibi görünür — oysa uydurma değil,
#: kullanıcının kendi sayısıdır. Ölçülen vaka: ``chamber_temperature``
#: hibrit ŞABLONUNDA form alanı olarak yok (yalnız ``HYBRID_BASE`` yükünde
#: var), bu yüzden hiç sarsılmıyor ve ``.inputs_not_used[0].submitted``
#: taban değeri 3000,0'da donuyor.
#:
#: DAR TUTULDU: kardeş ``used_by_model`` alanı BİLEREK kapsam dışı —
#: o çözücünün kendi sonucudur ve sabit kalırsa gerçekten şüphelidir;
#: bekçi onu korumaya devam eder.
#: ÖH D26 / app-api a3 (OH-Z5-02): AYNALANMIŞ KANAL da aynı yaprakdır.
#: ``app.py::_beyanlari_uyari_kanalina_yansit`` aynı beyanı ekrana basılan
#: ``input_warnings`` kanalına kopyalar ve ``params.submitted`` alanına
#: KULLANICININ GÖNDERDİĞİ sayının kendisini yazar. Desen yalnız kanonik
#: yolu tanıdığı için aynası "uydurma sabit" diye sayılıyordu.
#:
#: GEÇİŞ ÖLÇÜMÜ (``a3/z5_yaprak_gecis.json``): ``chamber_temperature``
#: 3000 -> 2600 sarsıldığında ``.input_warnings[0].params.submitted``
#: 3000,0 -> 2600,0 KIPIRDIYOR ve kanonik kardeşiyle (
#: ``.inputs_not_used[0].submitted``) BİREBİR aynı sayıyı taşıyor. Yani
#: yaprak ölü değil; alan sarsılmadığı sürece donması tanımı gereğidir.
#:
#: DAR TUTULDU: yalnız ``params.submitted``. Kardeş ``params.used_by_model``
#: (varsa) çözücünün kendi sonucudur ve KAPSAM DIŞIDIR.
_DECLARATION_ECHO = re.compile(
    r'(\.inputs_not_used\[\d+\]\.submitted'
    r'|\.input_warnings\[\d+\]\.params\.submitted)$')


def is_declaration_echo(path: str) -> bool:
    """Yaprak, kullanıcının gönderdiği sayının beyan yankısı mı?"""
    return bool(_DECLARATION_ECHO.search(path))


def canonical_echo_path(path: str) -> Optional[str]:
    """Yaprak bir yankı öneki altındaysa kanonik karşılığını döndürür.

    Önek eşleşmesi alan SINIRINDA yapılır: '.trajectory.motor_data.X' ve
    '.trajectory.motor_data[...]' indirgenir ama '.trajectory.motor_database'
    gibi bir ad indirgenMEZ (yanlış tekilleştirme sabit saklardı).
    """
    for prefix, canonical in ECHO_CANONICAL_PREFIXES:
        if path.startswith(prefix):
            rest = path[len(prefix):]
            if rest == '' or rest[0] in '.[':
                return canonical + rest
    return None


def _bit_identical(a: Any, b: Any) -> bool:
    """Bit-aynılık: tip AYNI ve değer eşit (NaN çifti eşit sayılır).

    ``==`` yetmez: True == 1 ve 1 == 1.0 doğrudur ama bunlar kopya değil
    tip kaymasıdır — bayat/yeniden-üretilmiş kopyanın tam da bırakacağı iz.
    """
    if type(a) is not type(b):
        return False
    if isinstance(a, float) and math.isnan(a) and math.isnan(b):
        return True
    return a == b


def bit_ayni(a: Any, b: Any) -> bool:
    """``_bit_identical``in KAMUYA açık adı — kopya sözleşmesinin ölçütü.

    v2.6.27 / P10B4-08: ``tools/sabit_siniflandirma.py`` bir ayna yaprağını
    "kopya" sayıp sınıflandırmadan düşürmeden ÖNCE bit-aynılık istiyor.
    Ölçüt burada tanımlıdır ve ikinci kez yazılmaz; araç bu adı çağırır.
    """
    return _bit_identical(a, b)


def is_echo(path: str, field_name: str) -> bool:
    """Bu yaprak, alanın kendi YANKISI mı?

    Bir alanı sarstığınızda çıktıdaki 'girdiğiniz değer şuydu' yankıları
    doğal olarak değişir. Yalnız yankısı değişen alan CANLI SAYILMAZ —
    aksi hâlde her ölü alan kendini canlı gösterirdi.
    Ölçülmüş örnek: ``fuel_orifice_diameter`` yalnız 1 yaprak değiştiriyordu,
    o da ``$.input_warnings[*].params.entered`` yankısıydı.
    """
    echo_markers = ('input_warnings', 'inputs_used', 'unwired_inputs',
                    'design_warnings', 'warnings', 'defaults_applied',
                    'entered', 'requested', 'form_value', 'user_',
                    # v2.6.27: 'inputs_not_used' bloğunun TAMAMI beyandır —
                    # "bu sayıyı gönderdiniz, çözücü kendi hesabını
                    # kullanıyor". Bir alanın TEK etkisi bu beyanı üretmekse
                    # alan modele girmiyor demektir; beyanı 'canlılık' saymak
                    # ölü alanı canlı gösterirdi (yankı sınıfının tanımı).
                    # DİKKAT: 'inputs_used' imi bunu KAPSAMAZ (metin farklı),
                    # bu yüzden ayrıca yazıldı.
                    'inputs_not_used')
    if any(marker in path for marker in echo_markers):
        return True
    return path.endswith('.' + field_name)


# ---------------------------------------------------------------------------
# Sarsım kuralları
# ---------------------------------------------------------------------------

@dataclass
class FieldSpec:
    """Bir form alanının nasıl sarsılacağı.

    ``lo``/``hi``: motorun kabul aralığı. Sarsım bu aralığı AŞMAMALI, yoksa
    motor değeri sessizce reddeder ve alan YALANCI ÖLÜ görünür (ölçülmüş
    örnek: ambient_temp x1.5 = 447 K, [200,350] dışında).

    ``companions``: bu alanın etkili olması için birlikte gönderilmesi
    gereken alanlar (ör. injector_type='pintle' refakat alanları olmadan
    HTTP 400 veriyor).

    ``context``: alanın canlı olduğu bağlam (ör. calculate_trajectory=True,
    grain_type='star'). Koşullu alanlar yalnız kendi bağlamlarında ölçülür.
    """
    name: str
    kind: str = 'number'          # number | choice | bool
    lo: Optional[float] = None
    hi: Optional[float] = None
    options: Tuple[str, ...] = ()
    companions: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    note: str = ''


def perturb(spec: FieldSpec, current: Any) -> Optional[Any]:
    """Alanı BELİRGİN biçimde değiştir; değiştirilemiyorsa None.

    ÖH D17 (bekci-cevirisi a1 — defter OH-D16-09, ikinci yarı). İKİLİ ALAN
    TAHMİN EDİLMEZ. Eski kod ``not bool(current)`` yazıyordu; alan taban
    yükünde YOKSA ``current`` ``None`` olur, çevirme ``True`` üretir ve bu
    çoğu bayrakta ucun ZATEN kullandığı varsayılandır. "Sarsım" hiçbir şeyi
    değiştirmez, çıktı bit-aynı çıkar ve CANLI alan sessizce ÖLÜ ilan
    edilir — uydurma bir sarsım, uydurma bir hüküm.

    Fail-closed: taban değer bilinmiyorsa alan sarsılamaz ve ``run`` bunu
    ``unmeasurable`` olarak ADIYLA bildirir. Hibrit yolunda bu durumu
    ``tests/test_field_wiring_layer_b.py::
    test_sarsilan_her_mantiksal_alan_taban_yukunde_bildirilir`` zaten
    kilitliyordu; katı/sıvı yolunda (``tools/wiring_map.py::measure_page``
    yalnız ``choice`` alanlarını geri dolduruyor) kilit YOKTU. Artık kör
    nokta sessiz değil.
    """
    if spec.kind == 'bool':
        if current is None:
            return None
        return not bool(current)

    if spec.kind == 'choice':
        options = [o for o in spec.options if o != current]
        return options[0] if options else None

    try:
        value = float(current)
    except (TypeError, ValueError):
        value = None

    if value is None or value == 0:
        # 0 çoğu alanda "otomatik" demektir; anlamlı bir sıfırdışı değer gerekir.
        if spec.lo is not None and spec.hi is not None:
            return spec.lo + 0.5 * (spec.hi - spec.lo)
        return None

    for factor in (1.5, 0.5):
        candidate = value * factor
        if spec.lo is not None and candidate < spec.lo:
            continue
        if spec.hi is not None and candidate > spec.hi:
            continue
        return candidate

    # v2.6.26 — DAR BANT KURTARMASI.
    # Çarpımsal adayların ikisi de banda sığmayabilir: sıvı motorun
    # combustion_efficiency alanı 97, bandı [50, 100] — 1.5x=145.5 taşıyor,
    # 0.5x=48.5 altına düşüyor. Eski kod None döndürüp alanı "ölçülemedi"
    # sayıyordu; oysa alan pekâlâ sarsılabilir. Bant içinde, değerden EN UZAK
    # uca gidilir: bu, alanın kendi beyan ettiği sınırdır, uydurma değildir.
    if spec.lo is not None and spec.hi is not None and spec.hi > spec.lo:
        hedef = spec.lo if (value - spec.lo) >= (spec.hi - value) else spec.hi
        if abs(hedef - value) > 1e-9 * max(1.0, abs(value)):
            return hedef
    return None


# ---------------------------------------------------------------------------
# Rapor
# ---------------------------------------------------------------------------

@dataclass
class ShakeReport:
    endpoint: str
    baseline_leaf_count: int
    dead_inputs: List[str] = field(default_factory=list)
    live_inputs: Dict[str, int] = field(default_factory=dict)
    echo_only_inputs: List[str] = field(default_factory=list)
    unmeasurable: Dict[str, str] = field(default_factory=dict)
    constant_outputs: List[str] = field(default_factory=list)
    declared_but_live: List[str] = field(default_factory=list)
    #: v2.6.27 — sabit-çıktı sayımında kanonik yola İNDİRGENEN yankı yaprağı
    #: sayısı (her biri motor.* kanonik yaprağıyla bit-aynı olduğu için
    #: ikinci kez sayılmadı). Sayı rapora yazılır ki tekilleştirmenin ne
    #: kadar iş yaptığı görünür kalsın.
    echo_constant_dedup: int = 0
    #: v2.6.27 — KOPYA SÖZLEŞMESİ İHLALLERİ. Yankı yaprağı kanonik yaprakla
    #: ya tabanda bit-aynı değil, ya kanonik karşılığı hiç yok, ya da sarsım
    #: altında biri değişirken öteki dondu. P-5 denetimi kopyayı "bit-aynı"
    #: diye belgelemişti; bu liste o beyanı ölçüme çevirir. Bekçi testte
    #: SIFIR olmak zorundadır — bayat/varsayılan kopya sınıfını (uçuş
    #: simülasyonunun eski motor verisiyle beslenmesi) sonsuza dek yakalar.
    yanki_ayristi: List[str] = field(default_factory=list)
    #: v2.6.27 — sabit sayımından BEYAN YANKISI olduğu için çıkarılan
    #: yapraklar (bkz. ``is_declaration_echo``). Sayılmıyor ama SAKLANIYOR:
    #: sınıflandırmanın ne yuttuğu görünmeden kalırsa, im genişletmenin en
    #: kolay saklanma yeri olur.
    beyan_yankilari: List[str] = field(default_factory=list)
    #: Taban koşunun DÜZ yaprak sözlüğü (yol -> değer).
    #: v2.6.26 — sabit çıktı yapraklarının SINIFLANDIRILMASI için gerekli:
    #: bir yaprağın "ızgara mı, standart mı, beyanlı mı" olduğuna karar vermek
    #: değerine ve kardeş alanlarına (``*_basis`` / ``*_source`` / ``*_status``)
    #: bakmayı gerektiriyor. Bekçi testleri bu alanı kullanmaz; ölçüm aracı
    #: kullanır.
    baseline_leaves: Dict[str, Any] = field(default_factory=dict)
    #: alan -> o alanı sarsınca değişen çıktı yaprakları (yankılar hariç).
    #: Bekçi testleri yalnız sayıya bakar; bu alan geliştirici bağlama
    #: haritası (tools/wiring_map.py) içindir — "bu sayı nereden geliyor"
    #: sorusunun cevabı burada duran ölçümdür, tahmin değil.
    changed_paths: Dict[str, List[str]] = field(default_factory=dict)
    #: ÖH D17 — SEÇİM KAPSAMI (defter P10B4-06). ``perturb`` bir seçim
    #: alanını TEK alternatifle sarsar. "Canlı" hükmü bu yüzden 1/N
    #: ölçümüne dayanır ve tek başına yayımlanırsa "bütün seçenekler
    #: sınandı" diye okunur. Alan başına ``{'toplam': N, 'denenen': k,
    #: 'denenen_secenek': ...}`` burada ADIYLA durur; kapsam beyanı
    #: hükümle birlikte yayımlanır.
    secim_kapsami: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    #: ÖH D17 — ÜÇÜNCÜ HÂL: "kısmen ölçüldü" (defter P10B4-06). Ölçülen
    #: (P10 B4): hibritte ``fuel_type``ın 11 seçeneğinden 4'ü (``carbon``,
    #: ``al2o3``, ``mixture``, ``custom``) uçtan HTTP 400 dönüyor, buna
    #: rağmen harita alanı düpedüz "canlı" gösteriyordu; ``unmeasurable``
    #: boş, ``dead`` boştu. ``run(probe_all_options=True)`` ile bütün
    #: seçenekler denenir ve 200 vermeyenler alan adı + durum koduyla
    #: buraya yazılır: ``{alan: {'kirik': {secenek: durum}, 'toplam': N}}``.
    #: ÖH D32 GÜNCELLEMESİ (577bb32d · OH-D31-05): ``al2o3`` şablondan
    #: söküldü — yukarıdaki P10 B4 satırı TARİHÎ ölçümdür. Bugünkü nüfus
    #: evren 10, kırık küme {carbon, mixture, custom}; yürürlükteki sayılar
    #: tests/test_d17_bekci_cevirisi_a1.py modül başındaki tek kaynaktadır.
    kismen_olculdu: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f'{self.endpoint}: {len(self.live_inputs)} canli, '
            f'{len(self.dead_inputs)} olu, '
            f'{len(self.echo_only_inputs)} yalniz-yanki, '
            f'{len(self.unmeasurable)} olculemedi, '
            f'{len(self.constant_outputs)} sabit cikti yapragi '
            f'({self.echo_constant_dedup} yanki tekillestirildi, '
            f'{len(self.beyan_yankilari)} beyan yankisi, '
            f'{len(self.yanki_ayristi)} yanki ayristi, '
            f'{len(self.kismen_olculdu)} kismen olculdu)')


# ---------------------------------------------------------------------------
# Çekirdek
# ---------------------------------------------------------------------------

def run(client, endpoint: str, baseline_payload: Dict[str, Any],
        specs: Iterable[FieldSpec],
        declared_unwired: Iterable[str] = (),
        ignore_output_prefixes: Iterable[str] = (),
        probe_all_options: bool = False,
        probe_fields: Iterable[str] = ()) -> ShakeReport:
    """Sarsım matrisini koş.

    ``declared_unwired``: motorun "bu alanı kullanmıyorum" diye BEYAN ettiği
    alanlar. Beyan edilmiş ama gerçekte çıktıyı değiştiren alan
    ``declared_but_live`` listesine düşer — beyan çürümesi bu şekilde
    yakalanır (v2.6.26'da sıvıda throat_diameter'ın 710 yaprak değiştirdiği
    hâlde "kullanılmıyor" diye beyan edildiği böyle bulundu).

    ``ignore_output_prefixes``: sabit olması MEŞRU çıktı yolları (sürüm
    numarası, birim etiketi, sabit metinler). Beyaz liste dar tutulmalı;
    genişletmek uydurmayı gizlemenin en kolay yoludur.

    ``probe_all_options``: seçim alanlarının BÜTÜN seçeneklerini tek tek
    dener (ÖH D17, defter P10B4-06). Kapalıyken (varsayılan) yalnız kapsam
    BEYANI yazılır — hangi seçeneğin denendiği ve kaç seçenekten kaçının
    denendiği ``secim_kapsami``da durur, böylece "canlı" hükmü 1/N ölçümü
    olduğunu saklamaz. Açıkken 200 vermeyen seçenekler ``kismen_olculdu``
    içine adıyla ve durum koduyla yazılır. Süpürme PAHALIDIR (alan başına
    N-1 ek çağrı); ölçüm araçları kendi bütçelerine göre açar.

    ``probe_fields``: süpürmenin ADIYLA açıldığı alanlar (ÖH D20, Fable-D17
    ŞART'ı). ``probe_all_options`` bütçeye sığmadığında bile kırık seçeneği
    BİLİNEN alanlar (ör. hibrit ``fuel_type``) süpürülür; maliyet o alanın
    N-1 çağrısıyla sınırlı kalır. İkisi de kapalıysa yalnız kapsam BEYANI
    yazılır ve harita "canlı (1/N denendi)" der — bu bir gevşetme değil,
    ölçüm gücünün hükümle birlikte yayımlanmasıdır.
    """
    def call(payload):
        resp = client.post(endpoint, json=payload, headers=HEADERS)
        if resp.status_code != 200:
            return None, resp.status_code
        return dict(leaves(resp.get_json())), 200

    baseline, status = call(baseline_payload)
    if baseline is None:
        raise AssertionError(f'{endpoint} taban cagrisi HTTP {status}')

    report = ShakeReport(endpoint=endpoint, baseline_leaf_count=len(baseline),
                         baseline_leaves=dict(baseline))
    declared = set(declared_unwired)
    # ÖH D20 / P10B4-06 (Fable-D17 ŞART'ı): süpürme ADIYLA açılabilir.
    _supurulen = frozenset(probe_fields)
    ignore = tuple(ignore_output_prefixes)
    ever_changed: set = set()
    # ÖH D15 / harita H2 — "KAYBOLDU" ile "AYRIŞTI" AYNI ŞEY DEĞİLDİR.
    # ``differing_paths`` yaprağın YOK OLMASINI da "değişti" sayar (a != b,
    # b yok). Kopya sözleşmesi geçişi ise değişim kümelerinin SİMETRİK
    # olmasını ister; bir alan koca bir bloğu bilerek kaldırıyorsa
    # (``calculate_trajectory=false`` -> ``.trajectory.motor_data.*`` hiç
    # üretilmez) kopya "değişmiş", kanonik ``.motor.*`` ise yerinde kalmış
    # görünür ve sözleşme SAHTE ihlal verir. Ölçüldü: bayrak haritaya
    # bağlandığı anda 8+ ``.trajectory.motor_data.*`` yaprağı "bayat kopya
    # şüphesi" diye işaretlendi — oysa hiçbiri bayat değildi, ilgili blok
    # o koşuda HİÇ YOKTU. Simetri denetimi bu yüzden yalnız İKİ SNAPSHOT'TA
    # DA VAR OLAN yaprakların değişimine bakar; kopyanın DEĞER olarak
    # kanonikten ayrışması (asıl kovaladığımız kusur) aynen yakalanır.
    ever_changed_present: set = set()

    for spec in specs:
        payload = dict(baseline_payload)
        payload.update(spec.context)
        payload.update(spec.companions)

        mevcut = payload.get(spec.name)
        new_value = perturb(spec, mevcut)
        if new_value is None:
            if spec.kind == 'bool' and mevcut is None:
                # ÖH D17 / OH-D16-09: tahmin edilen "çevirme" sahte ölü
                # üretiyordu. Artık ADIYLA ölçülemedi denir.
                report.unmeasurable[spec.name] = (
                    'ikili alan taban yukunde bildirilmemis; carpitma '
                    'ucun varsayilanina esit cikacagi icin olculemez')
            else:
                report.unmeasurable[spec.name] = (
                    'sarsilamadi (aralik/secenek yok)')
            continue

        if spec.kind == 'choice':
            # ÖH D17 / P10B4-06 — kapsam BEYANI hükümle birlikte yayımlanır.
            report.secim_kapsami[spec.name] = {
                'toplam': len(spec.options),
                'denenen': 1,
                'taban_secenek': mevcut,
                'denenen_secenek': new_value,
            }

        # Bağlam değiştiyse tabanı da o bağlamda al (adil karşılaştırma).
        if spec.context or spec.companions:
            context_base, status = call(payload)
            if context_base is None:
                report.unmeasurable[spec.name] = f'baglam tabani HTTP {status}'
                continue
        else:
            context_base = baseline

        payload[spec.name] = new_value
        shaken, status = call(payload)
        if shaken is None:
            report.unmeasurable[spec.name] = f'sarsim HTTP {status}'
            continue

        changed = differing_paths(context_base, shaken)
        ever_changed.update(changed)
        ever_changed_present.update(
            p for p in changed if p in context_base and p in shaken)
        real = [p for p in changed if not is_echo(p, spec.name)]

        if real:
            report.live_inputs[spec.name] = len(real)
            report.changed_paths[spec.name] = sorted(real)
            if spec.name in declared:
                report.declared_but_live.append(spec.name)
        elif changed:
            report.echo_only_inputs.append(spec.name)
        else:
            if spec.name not in declared:
                report.dead_inputs.append(spec.name)

        # ÖH D17 / P10B4-06 — ÜÇÜNCÜ HÂL: kullanıcıya gösterilen seçenek
        # hesabı düşürüyorsa alan "canlı" diye kapatılamaz.
        if ((probe_all_options or spec.name in _supurulen)
                and spec.kind == 'choice' and spec.options):
            kirik = {}
            denenen = 0
            for secenek in spec.options:
                if secenek == mevcut:
                    continue
                deneme = dict(payload)
                deneme[spec.name] = secenek
                _govde, _durum = call(deneme)
                denenen += 1
                if _govde is None:
                    kirik[str(secenek)] = _durum
            report.secim_kapsami[spec.name]['denenen'] = denenen
            if kirik:
                report.kismen_olculdu[spec.name] = {
                    'toplam': len(spec.options),
                    'denenen': denenen,
                    'kirik': kirik,
                }

    # --- Kopya sözleşmesi geçişi (v2.6.27) --------------------------------
    # Yankı öneki altındaki HER yaprak (sayı/metin fark etmez) kanonik
    # karşılığıyla karşılaştırılır. İhlal üç biçimde olabilir:
    #   1. kanonik yaprak yok (kopyada fazladan/artık alan),
    #   2. taban değeri bit-aynı değil (bayat ya da başka kaynaktan kopya),
    #   3. sarsım altında biri değişirken öteki dondu (canlı görünüp
    #      donmuş kopya — değişim kümeleri simetrik olmak zorundadır).
    # Sağlam sözleşme, aşağıdaki sabit sayımında tekilleştirmenin ÖN KOŞULU:
    # ayrışan yaprak indirgenmez, sabitse sabit listesinde ADIYLA kalır.
    _MISSING = object()
    for path, value in baseline.items():
        canon = canonical_echo_path(path)
        if canon is None:
            continue
        canon_value = baseline.get(canon, _MISSING)
        if canon_value is _MISSING or not _bit_identical(value, canon_value):
            report.yanki_ayristi.append(path)
        elif ((path in ever_changed_present)
              != (canon in ever_changed_present)):
            report.yanki_ayristi.append(path)
    ayrisan = set(report.yanki_ayristi)

    # Sütun tarafı: hiçbir sarsımda değişmeyen SAYISAL çıktı yaprakları.
    # Metin/etiket alanları doğal olarak sabittir; yalnız sayılar aranır.
    for path, value in baseline.items():
        if path in ever_changed:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if any(path.startswith(prefix) or prefix in path for prefix in ignore):
            continue
        # Beyan yankısı: değeri kullanıcının GÖNDERDİĞİ sayının kendisi olan
        # yaprak uydurma sabit değildir (bkz. is_declaration_echo). Alan
        # sarsılırsa zaten değişir; sarsılmıyorsa donması tanımı gereğidir.
        if is_declaration_echo(path):
            report.beyan_yankilari.append(path)
            continue
        # Yankı tekilleştirme: sözleşmesi SAĞLAM kopya ikinci kez sayılmaz —
        # kanonik motor.* yaprağı bu döngüde zaten sayılıyor (sözleşme
        # sağlamsa kopya sabitken kanonik de sabittir). Ayrışan kopya
        # İNDİRGENMEZ: hem yanki_ayristi'da hem sabit listesinde görünür.
        if canonical_echo_path(path) is not None and path not in ayrisan:
            report.echo_constant_dedup += 1
            continue
        report.constant_outputs.append(path)

    return report
