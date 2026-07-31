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
                    'entered', 'requested', 'form_value', 'user_')
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
    """Alanı BELİRGİN biçimde değiştir; değiştirilemiyorsa None."""
    if spec.kind == 'bool':
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
    #: alan -> o alanı sarsınca değişen çıktı yaprakları (yankılar hariç).
    #: Bekçi testleri yalnız sayıya bakar; bu alan geliştirici bağlama
    #: haritası (tools/wiring_map.py) içindir — "bu sayı nereden geliyor"
    #: sorusunun cevabı burada duran ölçümdür, tahmin değil.
    changed_paths: Dict[str, List[str]] = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f'{self.endpoint}: {len(self.live_inputs)} canli, '
            f'{len(self.dead_inputs)} olu, '
            f'{len(self.echo_only_inputs)} yalniz-yanki, '
            f'{len(self.unmeasurable)} olculemedi, '
            f'{len(self.constant_outputs)} sabit cikti yapragi')


# ---------------------------------------------------------------------------
# Çekirdek
# ---------------------------------------------------------------------------

def run(client, endpoint: str, baseline_payload: Dict[str, Any],
        specs: Iterable[FieldSpec],
        declared_unwired: Iterable[str] = (),
        ignore_output_prefixes: Iterable[str] = ()) -> ShakeReport:
    """Sarsım matrisini koş.

    ``declared_unwired``: motorun "bu alanı kullanmıyorum" diye BEYAN ettiği
    alanlar. Beyan edilmiş ama gerçekte çıktıyı değiştiren alan
    ``declared_but_live`` listesine düşer — beyan çürümesi bu şekilde
    yakalanır (v2.6.26'da sıvıda throat_diameter'ın 710 yaprak değiştirdiği
    hâlde "kullanılmıyor" diye beyan edildiği böyle bulundu).

    ``ignore_output_prefixes``: sabit olması MEŞRU çıktı yolları (sürüm
    numarası, birim etiketi, sabit metinler). Beyaz liste dar tutulmalı;
    genişletmek uydurmayı gizlemenin en kolay yoludur.
    """
    def call(payload):
        resp = client.post(endpoint, json=payload, headers=HEADERS)
        if resp.status_code != 200:
            return None, resp.status_code
        return dict(leaves(resp.get_json())), 200

    baseline, status = call(baseline_payload)
    if baseline is None:
        raise AssertionError(f'{endpoint} taban cagrisi HTTP {status}')

    report = ShakeReport(endpoint=endpoint, baseline_leaf_count=len(baseline))
    declared = set(declared_unwired)
    ignore = tuple(ignore_output_prefixes)
    ever_changed: set = set()

    for spec in specs:
        payload = dict(baseline_payload)
        payload.update(spec.context)
        payload.update(spec.companions)

        new_value = perturb(spec, payload.get(spec.name))
        if new_value is None:
            report.unmeasurable[spec.name] = 'sarsilamadi (aralik/secenek yok)'
            continue

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

    # Sütun tarafı: hiçbir sarsımda değişmeyen SAYISAL çıktı yaprakları.
    # Metin/etiket alanları doğal olarak sabittir; yalnız sayılar aranır.
    for path, value in baseline.items():
        if path in ever_changed:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if any(path.startswith(prefix) or prefix in path for prefix in ignore):
            continue
        report.constant_outputs.append(path)

    return report
