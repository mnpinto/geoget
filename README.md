# GeoGet
> Utility functions to download geo data.


## Install

`pip install geoget`

## How to use

Here is an example of a .bash file to download data from https://ladsweb.modaps.eosdis.nasa.gov/. The email and authentication token (auth) need to be defined in order for the script to work. To create an account and an authentication token visit ladsweb website.
    
```bash
#!/bin/bash -l 
email=""
auth=""
bbox='-10 36 0 44'
product="NPP_VMAES_L1"
collection="5000"
tstart="2017-10-27 00:00:00"
tend='2017-10-27 23:59:59'
path_save="/srv/geoget/data"
bands="Reflectance_M5 Reflectance_M7 Reflectance_M10 Radiance_M12 Radiance_M15 SolarZenithAngle SatelliteZenithAngle"

geoget_ladsweb $product $collection "$tstart" "$tend" "$bbox" $email $auth $path_save "$bands" --repName "GEO" --repPixSize "0.01" --daynight "D"
```

**Note:** Library under development. Examples above were tested in Ubuntu 16.04 LTS.
