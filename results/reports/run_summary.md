# Analysis Run Summary

- Satellite source: `/Users/korneev/Desktop/water-regime-gis/outputs/reports/kaa_zonal_means.csv`
- Ground source: `/Users/korneev/Desktop/water-regime-gis/data/ground_measurements.csv`
- Prepared satellite rows: 724
- Fields: 55
- Ground merge status: ground_missing
- Matched ground rows: 0
- OPTRAM status: bands_available_parameters_missing
- Model status: ground_missing_or_empty

## Missing Data

- Ground measurements are required for soil moisture, LAI and FCOVER analysis.
- OPTRAM is not generated until the OPTRAM edge/calibration parameters are defined.

## Main Outputs

- `results/data/prepared_satellite_data.csv`
- `results/data/model_dataset.csv`
- `results/data/ground_measurements_template.csv`
- `results/tables/seasonal_summary.csv`
- `results/reports/satellite_quality_report.md`
- `results/reports/model_report.json`
- `results/reports/optram_availability.json`
