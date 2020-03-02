# GeoGet
> Utility functions to download geo data.


## Install

`pip install geoget`

## How to use

Go to https://ladsweb.modaps.eosdis.nasa.gov/ and create an account and an authentication token. Then create `~/.ladsweb` file with the following format where you should write your email and token (key):
```bash
# To create an account and an authentication token visit ladsweb website.
{
    "url"   : "https://ladsweb.modaps.eosdis.nasa.gov",
    "key"   : "",
    "email" : ""
}
```
    
The following bash script shows an example of how to make a request:

```bash
#!/bin/bash -l 
bbox='-10 36 0 44'
product="NPP_VMAES_L1"
collection="5000"
tstart="2017-10-27 00:00:00"
tend='2017-10-27 23:59:59'
path_save="/srv/geoget/data"
bands="Reflectance_M5 Reflectance_M7 Reflectance_M10 Radiance_M12 Radiance_M15 SolarZenithAngle SatelliteZenithAngle"

geoget_ladsweb $product $collection "$tstart" "$tend" "$bbox" $path_save "$bands" --repName "GEO" --repPixSize "0.01" --daynight "D"
```

In case you need to stop the request (it may take a while until the files are available) you can later call `geoget_order_manager  .` on `path_save` directory and all requests in the log file will continue to be processed.

**Note:** Library under development. Examples above were tested in Ubuntu 16.04 LTS.
