# A2 — 3D Dünya GIBS uydu karoları + kalıcı önbellek spec (ARGE, canlı-doğrulandı)

## Doğrulanmış GIBS EPSG:4326 grid (WMTSCapabilities.xml, canlı)
- TileWidth=TileHeight=512px, TopLeftCorner=(-180,90), CRS84 (lon/lat WGS84).
- deg/px = 0.5625/2^z, tileSpan(°) = 288/2^z. z≥3 temiz ikiye katlanır; z0-2 düzensiz (kullanma).
- MatrixWidth(z)=360/tileSpan, MatrixHeight(z)=180/tileSpan (z≥3).
- m/px ekvator: z7≈489, z8≈245. Mevcut Blue Marble 4096px≈9784 m/px → z7 ≈20×, z8 ≈40× keskin.

## Katman seçimi (canlı HTTP 200 teyitli)
- **VARSAYILAN: `BlueMarble_ShadedRelief_Bathymetry`** — JPEG, TileMatrixSet 500m, **Dimension YOK (statik)**, z0-7. Bulutsuz, deterministik, tarih derdi yok, dürüstlük etiğine uygun. z7≈489m "bulanık"ı çözer.
- OPSİYONEL toggle: `VIIRS_SNPP_CorrectedReflectance_TrueColor` — 250m, z8, **Dimension:Time gerekir**, bulut riski → varsayılan YAPMA, bulut/tarih dürüstlük uyarısıyla sun.
- Anahtarsız. SupportedCRS=OGC:1.3:CRS84.

## URL şablonu (backend kurar, istemciden URL GELMEZ)
```
GIBS = https://gibs.earthdata.nasa.gov
Statik:  {GIBS}/wmts/epsg4326/best/{layer}/default/{tms}/{z}/{y}/{x}.jpg
Zamanlı: {GIBS}/wmts/epsg4326/best/{layer}/default/{date}/{tms}/{z}/{y}/{x}.jpg
```
**⚠️ WMTS sırası = z/y/x (TileMatrix/TileRow/TileCol) — OSM'nin z/x/y'si DEĞİL. Row (y) önce.** Tek yerde (backend URL kurucu) kilitle.

## Patch mesh (launch_site_globe.js)
- Tetik: camAltitudeM < TEXTURE_NOTE_ALT_M(400km) (getScaleInfo :680-692 mevcut).
- z seçimi: `z=round(log2(62617.5/metersPerPixel))`, clamp(z,4,maxZoom[layer]=7|8). z<4→base yeter, patch yükleme.
- tile→bbox: `lonW=-180+x·tileSpan; lonE=lonW+tileSpan; latN=90-y·tileSpan; latS=latN-tileSpan`. Ters: `tx=floor((lon+180)/tileSpan); ty=floor((90-lat)/tileSpan)`.
- Merkez tile etrafında (2R+1)² blok, **hard cap R≤3** (max 7×7). Tipik R=2.
- **UV: SphereGeometry UV'ye GÜVENME.** Her tile için kendi patch geometrisi (S×S≥8×8 vertex, lonW..lonE × latS..latN). pos=LaunchSiteGlobe.latLonToVec3(lat,lon,GLOBE_R*1.0004) (dışa açık :749); uv=((lon-lonW)/tileSpan,(lat-latS)/tileSpan). v yönü tek tile'da gözle test (ters ise 1-v).
- Yarıçap 1.0004 (base :166 üstünde, sınırlar :226 1.001 altında → z-fighting yok, sınırlar görünür).
- Malzeme MeshPhong + map (headlight tutarlı), colorSpace=SRGBColorSpace + anisotropy (_loadTexture :201-203 gibi).
- Tarih çizgisi: x = ((tx+dx)%MW+MW)%MW. Mahia 177.86°E gerçek vaka. Kutup: y clamp [0,MH); patch küçük → kutup singularity YOK (EPSG:4326'nın Mercator'a karşı kazancı; Esrange 67.9°N/Andøya 69.3°N güvenli).
- JS-tarafı Map anahtar layer:z:x:y; LRU ~128 mesh üstü THREE dispose (GPU bellek). clearFlightPath/dispose patch temizliği.

## Kalıcı önbellek backend (YENİ hrma/analysis/tile_cache.py — launch_site.py'yi şişirme)
Routes (app.py — ANA ENTEGRATÖR ekler, ama mantık tile_cache.py'de):
```
GET  /api/tile/<layer_key>/<int:z>/<int:x>/<int:y>   (time layer: ?date=YYYY-MM-DD)
GET  /api/tile/cache/status   → {bytes,tiles,dir}
POST /api/tile/cache/clear
```
- Cache dizini: `offline_store._user_data_dir()` reuse + `tiles/` alt-dizin (macOS ~/Library/Application Support/HRMA/tiles, Win %APPDATA%/HRMA/tiles). Override HRMA_TILE_CACHE_DIR. **Belgeler/HRMA DEĞİL** (orası .hrma projelerine ayrılmış, projects.py:100-117).
- Disk: tiles/<layer>/[date]/<z>/<x>/<y>.jpg.
- Akış: layer allowlist değilse 404; date regex ^\d{4}-\d{2}-\d{2}$|default; z/x/y aralık; realpath(path).startswith(realpath(root)) değilse 403; HIT→mtime touch+send_file(Cache-Control immutable); MISS→GIBS URL kur→_http_bytes→tmp+atomik rename→send_file; fetch fail→503 {available:false}.
- `_http_bytes` yeni (launch_site.py _http_json:358 binary ikizi, aynı UA, hata→None).
- **Güvenlik:** çıkış host SABİT GIBS_HOST (SSRF yok); layer_key allowlist dict anahtarı (^[a-z0-9_]+$); int-converter + realpath prefix (traversal yok).
- Boyut: TILE_CACHE_MAX_BYTES varsayılan 400MB, LRU (mtime touch, düşük-su %80'e süpür), status/clear uçları.

## Offline (sahte doku YOK)
- JS fetch /api/tile: ok+image/* → texture; aksi → o tile için mesh EKLEME (base o hücrede görünür, kısmi yükleme OK).
- Patch tamamı başarısız → base'de kal + #ls-texnote (launch_site.html:276) göster.
- Attribution: patch aktifken "NASA GIBS — Blue Marble (~500m)"; offline'da mevcut "~9km/detay yok" notu.

## Boyut gerçeği
Tile ~40-50KB. Tek saha z4→z7 ≈100 tile ≈4.5MB. Tek oturum panning ~5-30MB. Aylarca yalnız gezilen bölgeler → onlarca-birkaç yüz MB (400MB cap). Önden dev indirme YOK.

## A2 ajanının YAZACAĞI dosyalar (izole):
- launch_site_globe.js (patch mesh + tile Map/LRU + offline)
- hrma/analysis/tile_cache.py (yeni: _http_bytes + cache + tile matris formülleri + LRU)
DOKUNMAYACAĞI (spec teslim): app.py (routes — ANA ekler), launch_site.html (attribution/cache düğmesi — ANA/A3), i18n_launch_site.js (ANA).
Ayrıca B1'den DEVİR: launch_site_globe.js:20-21,:501 yorumları güncelle (Coriolis modellendi; yer izi teğet-düzlem).
Layer kimliklerini WebFetch ile teyit et (değişebilir bilgi; Claim/Evidence/Date).
