# Satellite Data Quality

- Source rows: 4344
- Prepared field-date rows: 724
- Fields: 55
- Duplicate field/date/index rows: 0
- Empty zonal_mean rows: 276
- Rows with many missing values: 46

## Valid Observations

| Index | Valid | Missing | Min | Max |
| --- | ---: | ---: | ---: | ---: |
| NDMI | 678 | 46 | -0.302938342094 | 0.519855439663 |
| NDRE | 678 | 46 | 0.0351087115705 | 0.598146438599 |
| SAVI | 678 | 46 | 0.0366482958198 | 0.738567173481 |
| NDVI | 678 | 46 | 0.0598003342748 | 0.751195371151 |
| NDWI | 678 | 46 | -0.670465409756 | -0.0680447369814 |
| MNDWI | 678 | 46 | -0.422350913286 | -0.0255352649838 |

## Notes

Rows with empty means are preserved; they usually correspond to fully masked cloudy/nodata scenes.
No averaging is performed across different fields.
