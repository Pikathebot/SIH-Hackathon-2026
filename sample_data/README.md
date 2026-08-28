# SatQuery AI — Evaluation & Demo Sample Datasets

This directory contains pre-configured, georeferenced satellite rasters in **GeoTIFF (`.tif`)** and **JPEG 2000 (`.jp2`)** formats for testing all core capabilities of **SatQuery AI** (Problem Statement 26167).

---

## 1. Single-Image Optical Datasets (`sample_data/optical/`)

### `real_sentinel2_austria_tci.tif` ⭐ *Real Satellite Data*
- **Format / Sensor**: Real ESA Sentinel-2 L2A True Color Image (10m resolution, 1024x1024, `EPSG:32631` UTM Zone 31N).
- **Features**: Real Alpine terrain, conifer forests, agricultural fields, rural villages, and river channels.
- **Recommended Test Queries**:
  - *"Describe the land cover, forests, and terrain characteristics in this satellite image."* -> *Triggers Scene Captioning [CAP].*
  - *"Highlight all water bodies, rivers, and streams."* -> *Triggers Water Segmentation [SEG].*

### `optical_sentinel2_lake.jp2` ⭐ *JPEG 2000 Format*
- **Format / Sensor**: 3-band JPEG 2000 GeoJP2 (EPSG:4326, 512x512).
- **Features**: Deep water lake surrounded by dense conifer forest and alpine pastures.
- **Recommended Test Queries**:
  - *"Segment and highlight the water body in this satellite image."* -> *Triggers Water Segmentation [SEG].*

### `optical_port_rotterdam.tif`
- **Format / Sensor**: 3-band True Color GeoTIFF (EPSG:4326 WGS84, 512x512, 16-bit).
- **Features**: Container harbor, deep water channel, quay, container cargo ships, gantry cranes, warehouses.
- **Recommended Test Queries**:
  - *"Detect all shipping vessels, cargo ships, and container cranes in this harbor."* -> *Triggers Object Detection [DET] with bounding boxes.*

### `optical_airbase_runway.tif`
- **Format / Sensor**: 3-band GeoTIFF (EPSG:4326, 512x512).
- **Features**: Desert base, dark asphalt runway with markings, taxiway, tarmac apron with 4 parked aircraft, hangars.
- **Recommended Test Queries**:
  - *"Detect all aircraft, airplanes, and jets parked on the apron."* -> *Triggers Object Detection [DET].*

---

## 2. Synthetic Aperture Radar (SAR) Datasets (`sample_data/sar/`)

### `real_sentinel1_sar_grd_vv.tif` ⭐ *Real Radar Data*
- **Format / Sensor**: Real ESA Sentinel-1 GRD C-band SAR Backscatter (1024x1024 GeoTIFF, VV Polarization).
- **Features**: Real microwave backscatter, dark specular water bodies, bright urban dielectric reflections, speckle patterns.
- **Recommended Test Queries**:
  - *"Analyze the radar backscatter intensity and identify high-reflectance metallic or urban objects."* -> *Triggers SAR Single-Image VQA.*

### `sar_port_rotterdam.tif`
- **Format / Sensor**: 1-band Calibrated SAR Backscatter GeoTIFF (EPSG:4326, 512x512, 16-bit).
- **Features**: Specular low-backscatter dark water, intense double-bounce corner reflection on metal ships/cranes.

---

## 3. Bi-Temporal Change Detection Pairs (`sample_data/bitemporal_change/`)

### `real_sentinel2_change_t1_2022.tif` & `real_sentinel2_change_t2_2024.tif` ⭐ *Real Multi-Year Sentinel-2*
- **Format / Sensor**: Real Sentinel-2 L2A pair acquired over the exact same footprint 2 years apart (August 2022 vs August 2024).
- **How to Test**:
  1. Attach both `real_sentinel2_change_t1_2022.tif` (Date: 2022-08-13) and `real_sentinel2_change_t2_2024.tif` (Date: 2024-08-12).
  2. **Query**: *"What changed between these two dates, and where did vegetation or agricultural change occur?"*
  3. **Expected Output**: *Triggers Change Detection [CD], outputs change description, difference heatmap overlay, and interactive Swipe Split Slider.*

### `urban_expansion_t1_2021.tif` & `urban_expansion_t2_2024.tif`
- **Format / Sensor**: Spatially Corresponding GeoTIFF pair showcasing urban development (new highway, logistics park, and residential expansions).
- **How to Test**:
  1. Attach both images (Dates: 2021-06-15 vs 2024-06-15).
  2. **Query**: *"What changed between these two dates, and where did urban construction occur?"*

---

## 4. Cross-Modal Optical + SAR Fusion Pair (`sample_data/cross_modal_fusion/`)

### `cloudy_optical_scene.tif` & `penetrating_sar_scene.tif`
- **Format / Sensor**: Co-registered Optical and SAR pair of the same maritime area.
  - `cloudy_optical_scene.tif`: Optical image obscured by thick clouds over the harbor.
  - `penetrating_sar_scene.tif`: Co-registered SAR image where microwaves penetrate through the cloud layer to reveal the ships below.
- **How to Test**:
  1. Attach `cloudy_optical_scene.tif` (Modality: Optical) and `penetrating_sar_scene.tif` (Modality: SAR / Radar).
  2. **Query**: *"Use the optical and SAR images together to detect maritime vessels hidden under cloud cover."*
  3. **Expected Output**: *Triggers Multi-Sensor Fusion [FUS], extracts complementary structural SAR features, and produces joint evidence report!*
