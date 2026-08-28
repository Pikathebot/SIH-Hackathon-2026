# SatQuery AI — Evaluation & Demo Sample Datasets

This directory contains pre-configured, georeferenced satellite rasters in **GeoTIFF (`.tif`)** and **JPEG 2000 (`.jp2`)** formats for testing all core capabilities of **SatQuery AI** (Problem Statement 26167).

---

## 1. Single-Image Optical Datasets (`sample_data/optical/`)

### `optical_port_rotterdam.tif`
- **Format / Sensor**: 3-band True Color GeoTIFF (EPSG:4326 WGS84, 512x512, 16-bit)
- **Features**: Container harbor, deep water channel, quay, container cargo ships, gantry cranes, warehouses.
- **Recommended Test Queries**:
  - *"Detect all shipping vessels, cargo ships, and container cranes in this harbor."* -> *Triggers Object Detection [DET] with bounding boxes.*
  - *"Highlight all deep water bodies and water channels."* -> *Triggers Water Segmentation [SEG] mask.*
  - *"Describe the land use, maritime infrastructure, and docked ships."* -> *Triggers Captioning [CAP].*

### `optical_airbase_runway.tif`
- **Format / Sensor**: 3-band GeoTIFF (EPSG:4326, 512x512)
- **Features**: Desert base, dark asphalt runway with markings, taxiway, tarmac apron with 4 parked aircraft, hangars.
- **Recommended Test Queries**:
  - *"Detect all aircraft, airplanes, and jets parked on the apron."* -> *Triggers Object Detection [DET].*
  - *"What is the primary infrastructure visible on the tarmac?"* -> *Triggers Visual Q&A [VQA].*

### `optical_sentinel2_lake.jp2`
- **Format / Sensor**: 3-band JPEG 2000 GeoJP2 (EPSG:4326, 512x512)
- **Features**: Alpine deep water lake surrounded by dense conifer forest and alpine pastures.
- **Recommended Test Queries**:
  - *"Segment and highlight the water body in this satellite image."* -> *Triggers Water Segmentation [SEG].*
  - *"Describe the surrounding vegetation and natural terrain."* -> *Triggers Scene Captioning [CAP].*

---

## 2. Synthetic Aperture Radar (SAR) Datasets (`sample_data/sar/`)

### `sar_port_rotterdam.tif`
- **Format / Sensor**: 1-band Calibrated SAR Backscatter GeoTIFF (EPSG:4326, 512x512, 16-bit)
- **Features**: Specular low-backscatter dark water, intense double-bounce corner reflection on metal ships/cranes, characteristic speckle noise.
- **Recommended Test Queries**:
  - *"Analyze the radar backscatter intensity and identify high-reflectance metallic objects."* -> *Triggers SAR Single-Image VQA.*

---

## 3. Bi-Temporal Change Detection Pair (`sample_data/bitemporal_change/`)

### `urban_expansion_t1_2021.tif` & `urban_expansion_t2_2024.tif`
- **Format / Sensor**: 2 Spatially Corresponding Optical GeoTIFFs acquired at different timestamps (2021 vs 2024).
- **Scene Changes**:
  - **T1 (2021)**: Rural green agricultural fields, natural river channel, small village.
  - **T2 (2024)**: Major urban expansion — new North-South highway with bridge, large industrial warehouse park in bottom-right, residential expansion.
- **How to Test**:
  1. Attach both `urban_expansion_t1_2021.tif` (Set Date: 2021-06-15) and `urban_expansion_t2_2024.tif` (Set Date: 2024-06-15).
  2. **Query**: *"What changed between these two dates, and where did urban construction occur?"*
  3. **Expected Output**: *Triggers Change Detection [CD], outputs change description, difference heatmap overlay, and enables the interactive Swipe Split Slider in the Report Card!*

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
