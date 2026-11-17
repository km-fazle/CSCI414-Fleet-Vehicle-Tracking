# Data

The offline fixture is `data/fixtures/fleet-seed42.json`. It is produced by `simulator/generate.py` with seed 42. Positions come from a linear formula. They are synthetic and are not GPS readings.

`event_time` in that fixture is a fixed clock starting at `2026-11-13T16:00:00Z`, so replaying it later will look stale. The experiment runner does not replay those timestamps. It keeps the same coordinates and stamps each request with the time it is sent. The client and the API share the container clock, so `received_at - event_time` is a same-host delay, not a measurement between two NTP-synchronized machines.

## NYC TLC

The course suggestion is the NYC TLC trip record data: https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page

Those files describe trips, not continuous GPS. `data/import_nyc_tlc.py` can convert a local CSV. If the file has pickup and dropoff coordinates, intermediate points are straight-line interpolation. If it only has zone IDs, pass a zone-centroid JSON file. Every output row is `source_type: nyc_tlc_derived`. The full TLC file is not downloaded into this repo.

The TLC data terms are the city's public dataset terms. Read them before using a file in a report, and cite the file name you actually downloaded.
