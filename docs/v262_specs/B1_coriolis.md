# B1 — Coriolis 6-DOF spec (ARGE turu çıktısı, kod-teyitli)

## Kod gerçeği (teyit edildi)
- Çerçeve (N,E,U)=(x0,x1,x2): six_dof_trajectory.py:12, :516. Yerçekimi hep (0,0,-g).
- Durum vektörü (13): y=[r(3),v(3),q(4),ω(3)] (:365-369). v=y[3:6] = Coriolis'in v_rel'i.
- İvme = return 2. bloğu = F_i/m (:438). Coriolis fiktif ivme → F_i/m SONRASI eklenir.
- SixDOFTrajectory.__init__ (:226-231) latitude YOK. solve() apojede biter (:459-463 apogee_event).
- local_gravity WGS84 Somigliana (launch_site.py:143-175) → merkezkaç ZATEN içinde.
- OMEGA_EARTH six_dof'a import EDİLMEMİŞ (yalnız launch_site.py:127).

## ⚠️ HANDEDNESS BUGI (en kritik — işaret tüm oyun)
(N,E,U) SOL-elli (N×E=−U), np.cross SAĞ-elli. Naif −2·cross(Ω,v) dik atışta DOĞU verir; fizik BATI. Güvenli kalıp: geçici sağ-elli ENU'ya çevir, hesapla, geri döndür.

```python
# Modül düzeyinde (import edilebilir), _quat_from_elevation_azimuth ile sınıf arasına:
def _coriolis_acceleration(v_neu, cos_lat, sin_lat):
    """a = −2·Ω × v_rel, (N,E,U) çerçevesinde. HANDEDNESS: (N,E,U) sol-elli,
    np.cross sağ-elli → hesap geçici sağ-elli ENU'da (E,N,U) yapılır."""
    vN, vE, vU = float(v_neu[0]), float(v_neu[1]), float(v_neu[2])
    v_enu = np.array([vE, vN, vU])
    omega_enu = OMEGA_EARTH * np.array([0.0, cos_lat, sin_lat])
    a_enu = -2.0 * np.cross(omega_enu, v_enu)
    return np.array([a_enu[1], a_enu[0], a_enu[2]])   # geri (N,E,U)
```
Sabit: `OMEGA_EARTH = 7.292115e-5` — six_dof_trajectory.py:39-42 (G0/R_EARTH yanına), yerel tanım (launch_site ile aynı değer; rule#11 çapraz-referans yorumu).

## Uygulama noktası (_derivatives :422-438)
- Coriolis YALNIZ else (serbest-uçuş) dalında. Ray dalında EKLEME (kısıt karşılar, v≈0).
- v_rel = state `v` (y[3:6]), rüzgâr DEĞİL (u_i=v-wind :385 KULLANMA).
- Taşıma hızı 465 m/s EKLENMEZ (pad'de v=0). Merkezkaç EKLENMEZ (Somigliana).

## latitude_deg plumbing
- __init__ imzası: `latitude_deg=0.0, coriolis=True` ekle. Depola: self.latitude_deg, self._cos_lat, self._sin_lat, self.coriolis (:286 sonrası).
- **coriolis bayrağı ZORUNLU** (izotropi regresyonu için, aşağı bak).
- app.py:1063-1078 → `latitude_deg=float(data.get('latitude_deg',0.0))` (bu satırı ANA entegratör app.py'de yapacak — B1 ajanı app.py'ye DOKUNMAZ).
- launch_site.html body'ye `latitude_deg: la` (A1 ajanı yapacak — B1 DOKUNMAZ).

## ⚠️ KIRILACAK TEST — test_six_dof_trajectory.py:158-186 test_wind_direction_isotropy
Coriolis izotropiyi bozar → drift_e≈drift_n FAIL (lat=0'da bile). ÇÖZÜM: bu testin 3 solver çağrısına (:167-171) `coriolis=False` ekle. Asıl amacı q̇ Hamilton-sırası aero izotropisi, Coriolis'siz korunmalı. (test_stays_vertical_without_wind :97-103 marjı daralır ama geçer — dev teyit etsin, gerekirse coriolis=False.)

## ⚠️ latitude=0 = EKVATOR = MAKSİMUM Coriolis (kapalı DEĞİL). Kapatmak için coriolis=False.

## TDD — YENİ tests/test_six_dof_coriolis.py (import: SixDOFTrajectory, BarrowmanAero, _coriolis_acceleration, OMEGA_EARTH; kanatlı standart araç)
BÜYÜKLÜK FORMÜLÜ: codex'in (4/3) İNİŞ değeri; solve apojede bittiği için doğrusu (2/3)Ω cosφ v0³/g². EN SIKI çapa (sürtünmeden bağımsız): vE(t)=−2Ω cosφ·z(t) kesin → apojede velocity_east[-1]≈−2Ω cosφ·apogee.
- T1 dik atış φ=+45 → position[1][-1]<0 (batı). SERT işaret.
- T2 büyüklük: velocity[1][-1] ≈ -2·Ω·cos(45°)·apogee, rel=0.10.
- T3 kapalı-form (2/3) mertebe bandı 0.4×–2.5× (gevşek).
- T4 iş yapmaz: |dot(a_cor,v)| < 1e-12·(...) makine-hassasiyeti.
- T5 yarıküre sinφ: elevation=45 AZIMUTH=90(Doğu); φ=+45 → position[0][-1]<0 (güney), φ=−45 → >0 (kuzey). İşaret FLIP.
- T6 dik atış İKİ yarıkürede de BATI (cosφ çift, E/W flip ETMEZ).
- T7 ekvator φ=0 dik atış → position[1][-1]<0 (max Coriolis; "lat=0 kapalı" yanılgısını kilitle).
İNİŞ TEST ETME (solve apojede biter).

## Ek: bu dosyada B3 + C1 de yapılabilir (aynı dosya)
- B3: thrust_curve doğrulaması (:257-264) — time boş/tek-nokta → net ValueError (endpoint 400). Şu an IndexError→500.
- C1 perf: _mass_at (:319-322) her türev-değerinde O(N) trapz+2 alloc. __init__'te cumtrapz birikimli impuls önhesapla, _mass_at→np.interp+kısmi segment. ÇIKTI BİT-AYNI (aynı yamuk kuralı). A1 gerçek ~300-nokta eğri bağlanınca değerli.

## NOT_MODELLED + dürüst etiketler (launch_site.py:108-122 — B1 ajanı YAPAR)
- 'coriolis' anahtarını SİL (:113-115). 'earth_rotation' metnini güncelle: taşıma hızı hâlâ modellenmiyor ama "flat-Earth inertial" yanlış → "launch-anchored ROTATING tangent-plane; Coriolis IS integrated; transport velocity out of scope; centrifugal folded into WGS84 gravity".
- i18n_launch_site.js 2 string + launch_site_globe.js 2 yorum + six_dof docstring:11,:27 → ANA ENTEGRATÖR/A2/A1 yapacak (B1 spec olarak teslim eder, dosyaya dokunmaz).

## B1 ajanının YAZACAĞI dosyalar (izole, A2 ile paralel güvenli):
- six_dof_trajectory.py (Coriolis + latitude + B3 + C1 + docstring)
- launch_site.py (NOT_MODELLED)
- tests/test_six_dof_coriolis.py (yeni)
- tests/test_six_dof_trajectory.py (:167-171 coriolis=False)
DOKUNMAYACAĞI (spec olarak teslim): app.py, launch_site.html, i18n_launch_site.js, launch_site_globe.js.
