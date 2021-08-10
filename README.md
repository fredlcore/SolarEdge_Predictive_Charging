# SolarEdge Predictive Charging
Python script to implement predictive battery charging based on SolCast/DWD forecasts

This tool uses the awesome [solaredge_modbus](https://github.com/nmakel/solaredge_modbus) library to access the SolarEdge inverter data (including the battery's data) together with the solar forecasts from either the Germen Weather Service/DWD (via the likewiese awesome [wetterdienst](https://github.com/earthobservations/wetterdienst) library) as well as optionally the forecasts from [SolCast](https://www.solcast.com) (registration required, free for private use).

## Installation
* Download the repository 
* Install the libraries listed in the import/from section of the script via `pip` (e.g. `pip install isodate` or `pip install wetterdienst`) 

## Configuration
* Choose the capital city closest to you (or one that matches the timezone of your location best) and enter the city's name in the `nearest_city` variable at the beginning. If you leave it empty, you will be prompted with a list of cities to choose from during runtime.
* Choose the DWD station ID closest to you from [this list](https://www.dwd.de/DE/leistungen/klimadatenweltweit/stationsverzeichnis.html) and enter it into the `dwd_station` variable.
* Set `kWp` to your peak production capacity in kWp.
* Set `panel_area` to the square meter area occupied by your modules.
* Set `panel_efficiency` to the module's efficiency according to the datasheet.
* Set `inverter_efficiency` to the inverter's efficiency according to the datasheet.
* `adjustment_factor` acts as a bias regarding the forecast data. It can help adjust the forecast data to fit your individual setup. A value below one starts the charging process earlier, a value above one delays it further.
* `min_battery_level` determines how much battery charge should be maintained even during peak production
* Set `interval_seconds` to the interval you want the script to poll data from the inverter.

### SolCast configuration
Using SolCast is optional, but it could result in higher quality data than the one provided by the DWD. To use it, you have to register your site on their website and then configure the following variables:
* Set `use_solcast` to `True` in order to enable SolCast queries.
* Set `solcast_reporting_interva` to a value greater than zero if you want to report your production data to SolCast to enable them to fine-tune their forecast data for you.
* Set `solcast_api_key` and `solcast_resource_id` to the API key and resource ID respectively which you can get from your SolCast account page.

## Running SolarEdge Predictive Charging
The script takes two arguments: the first one is the IP address of the inverter, the second one is the ModBus/TCP port of the inverter. This is 1502 by default, but might have been set to 502. The person who installed your inverter needs to enable the ModBus/TCP functionality, so make sure this has been done!  
  
You should run the script on a system that runs 24/7, like a NAS, for example. To keep it running even after you sign off from your console, run the program like this:  
`nohup ./solaredge_predictive_charging.py 192.168.1.132 502 &` (of course you have to modify the IP address and the port accordingly)
Output will be logged to a file called `nohup.out` in the same directory. With `tail nohup.out` you can then see the output and statistical data coming up.  
If you want to terminate the script (which has to be done prior to restarting it!), have a look at the output of `ps aux` and then use `kill` or `killall` to terminate the script.  
If you know that everything works fine and you no longer need the output logged to `nohup.out`, you can terminate the program and restart it like this: `nohup ./solaredge_predictive_charging.py 192.168.1.132 502 >/dev/null 2>&1 &`.

## Notes
Currently, the script is written in a way that it will start to export (empty) the battery to the grid in the morning as soon as production is doulbe the household consumption until the battery is down to `min_battery_level`. If the battery level is below that, it will use all PV production not consumed to charge the battery up to this level first.
Exporting to the grid will continue until the predicted solar energy for the rest of the day is lower than what the battery needs. This is adjusted by `adjustment_factor` with which the predicted solar energy is multiplied with. Thus, if you set the value to `0.7`, the predicted solar energy is calculated with 30% less. You'll have to experiment with this a bit; for my setting 0.7 works fine as the battery charging kicks in well after the noon peak but still comfortably charges the battery fully.
