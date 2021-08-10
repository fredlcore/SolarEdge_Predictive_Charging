#!/usr/bin/env python3

nearest_city = "Berlin"		# Enter capital city for timezone and sunrise/sunset detection or leave empty to select during runtime
dwd_station = 10253		# DWD station ID, see https://www.dwd.de/DE/leistungen/klimadatenweltweit/stationsverzeichnis.html for a list
kWp = 5920			# peak production capacity of solar panels
panel_area = 16 * 1 * 1.6	# module area in square meter
panel_efficiency = 0.203	# module efficiency according to data sheet (divide by 100)
inverter_efficiency = 0.98	# inverter efficieny according to datasheet (divide by 100)
adjustment_factor = 0.7		# Adjustment factor
min_battery_level = 20		# minimum battery level to be maintained in percent
interval_seconds = 10		# update interval
use_solcast = True		# Set to False in order to use DWD MOSMIX only, otherwise use DWD MOSMIX as fallback
solcast_reporting_interval = 5	# report interval in minutes
solcast_api_key = ""		# Enter SolCast API key here 
solcast_resource_id = ""		# Enter SolCast Resource ID here

import argparse
import requests
import json
import time
import isodate
import solaredge_modbus
from datetime import datetime
import dateutil
import pytz
#import astral
import astral.location
import astral.geocoder
import astral.sun
from wetterdienst.provider.dwd.forecast import (
    DwdForecastDate,
    DwdMosmixRequest,
    DwdMosmixType,
)

solcast_period = "PT{}M".format(solcast_reporting_interval)
solcast_url = "https://api.solcast.com.au/rooftop_sites/" + solcast_resource_id + "/forecasts?hours=24&format=json&api_key=" + solcast_api_key
solcast_report_url = "https://api.solcast.com.au/rooftop_sites/" + solcast_resource_id + "/measurements?api_key=" + solcast_api_key

factor = 0.278 * panel_area * panel_efficiency * inverter_efficiency

try:
    city = astral.geocoder.lookup(nearest_city, astral.geocoder.database())
except KeyError:
    try:
        print (f"'{nearest_city}' not found in database.")
        input("Hit 'Enter' to print a list and select by number\nor fill in (only!) the city's name in the 'nearest_city' variable\nat the beginning of this script or press CTRL+C to abort.\n
")
    except KeyboardInterrupt as err:
        quit()
    entries = []
    for location in astral.geocoder.all_locations(astral.geocoder.database()):
        c = astral.location.Location(location)
        entry = {'name': c.name, 'region': c.region, 'timezone': c.timezone}
        entries.append(entry)
    sorted_entries = sorted(entries, key=lambda item: (item.get("region"), item.get("name")), reverse=False)
    entry_index = 0
    for entry in sorted_entries:
        print (f"{entry_index}: {entry['region']} ({entry['timezone']}): {entry['name']}")
        entry_index = entry_index + 1
    entry_selected = input("Enter number of city: ")
    try:
        entry = sorted_entries[int(entry_selected)]
    except IndexError:
        print ("Invalid selection, quitting...")
        quit()
    nearest_city = entry['name']
    print (nearest_city)
    city = astral.geocoder.lookup(nearest_city, astral.geocoder.database())

def get_sunshine(avg_consumption):

    solcast_sunshine = 0
    gross_solcast_sunshine = 0
    api_exceeded = False
    current_time = datetime.now().astimezone(pytz.timezone(city.timezone))
    try:
        if (use_solcast == True):
            request = requests.get(solcast_url)
            x_rate_limit = request.headers['x-rate-limit'] 
            x_rate_remaining = request.headers['x-rate-limit-remaining'] 
            x_rate_limit_reset = request.headers['x-rate-limit-reset']
            reset_date = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(x_rate_limit_reset)))
            print (f"Retrieving SolCast data, status {request.status_code}, {x_rate_remaining} of {x_rate_limit} left, resetting on {reset_date}") 
            if (request.status_code != 429):
                contents = json.loads(request.text)
                for item in contents['forecasts']:
                    solcast_time = dateutil.parser.parse(item['period_end']).astimezone(pytz.timezone(city.timezone))
                    solcast_duration = isodate.parse_duration(item['period'])
                    solcast_time = solcast_time - solcast_duration
                    solcast_pv_estimate = item['pv_estimate'] * 1000
                    if (current_time.date() == solcast_time.date() and solcast_pv_estimate > 0):
                        solcast_sunshine = solcast_sunshine + (solcast_pv_estimate / (60 / (solcast_duration.total_seconds() / 60))) - avg_consumption / (60 / (solcast_duration.total_seconds(
) / 60))
                        gross_solcast_sunshine = gross_solcast_sunshine + (solcast_pv_estimate / (60 / (solcast_duration.total_seconds() / 60)))
                        print (solcast_time, ":", item['pv_estimate'])
                print (avg_consumption, solcast_sunshine, gross_solcast_sunshine)
            else:
                print ("API calls exceeded for today, will use DWD values as fallback")
                api_exceeded = True

        request = DwdMosmixRequest(
            parameter=["Rad1h"],
            start_issue=DwdForecastDate.LATEST,  # automatically set if left empty
            mosmix_type=DwdMosmixType.SMALL,
            humanize=False,
            tidy=False,
        )
        stations = request.filter_by_station_id(
            station_id=[dwd_station],
        )
        response = next(stations.values.query())

        print ("Retrieving DWD data...")
        dwd_sunshine = 0
        gross_dwd_sunshine = 0
        for index, row in response.df.iterrows():
            dwd_time = row['date'].astimezone(pytz.timezone(city.timezone))
            current_time = datetime.now().astimezone(pytz.timezone(city.timezone))
            if (current_time.date() == dwd_time.date() and dwd_time.hour >= current_time.hour and row['rad1h'] > 0):
                dwd_sunshine = dwd_sunshine + row['rad1h'] * factor - avg_consumption
                gross_dwd_sunshine = gross_dwd_sunshine + row['rad1h'] * factor
                print (dwd_time,row['rad1h'],row['rad1h'] * factor)
        print (avg_consumption, dwd_sunshine, gross_dwd_sunshine)

        if (use_solcast == True and api_exceeded == False):
            sunshine = solcast_sunshine
        else:
            sunshine = dwd_sunshine

    except Exception as err:
        print (f"Error occurred: {err.args}", flush=True)
        sunshine = 0

    return sunshine

def get_values(inverter):
    values = {}
    values = inverter.read_all()
    meters = inverter.meters()
    batteries = inverter.batteries()
    values["meters"] = {}
    values["batteries"] = {}

    for meter, params in meters.items():
        meter_values = params.read_all()
        values["meters"][meter] = meter_values

    for battery, params in batteries.items():
        battery_values = params.read_all()
        values["batteries"][battery] = battery_values

    return values

if __name__ == "__main__":

    argparser = argparse.ArgumentParser()
    argparser.add_argument("host", type=str, help="Modbus TCP address")
    argparser.add_argument("port", type=int, help="Modbus TCP port")
    argparser.add_argument("--timeout", type=int, default=1, help="Connection timeout")
    argparser.add_argument("--unit", type=int, default=1, help="Modbus device address")
    argparser.add_argument("--json", action="store_true", default=False, help="Output as JSON")
    args = argparser.parse_args()

    inverter = solaredge_modbus.Inverter(
        host=args.host,
        port=args.port,
        timeout=args.timeout,
        unit=args.unit
    )

    values = get_values(inverter)
    batteryCapacity = (values['batteries']['Battery1']['rated_energy'])

    if args.json:
        print(json.dumps(values, indent=4))
    else:
#        print("Power Inverter;Power Meter;Power Battery;Consumption")

        mode = "";
        old_hour = -1
        old_day = 0
        avg_counter = 0
        avg_consumption = 0
        daily_consumption = 0
        avg_production_counter = 0
        avg_production = 0
        pvProductionInterval = 0
        remaining_sunshine = 0
        post_peak = False

        while True:
            start_time = time.time()

            sun_data = astral.sun.sun(city.observer,datetime.now(),tzinfo=city.timezone)
            sunrise_hour = sun_data['sunrise'].hour
            sunset_hour = sun_data['sunset'].hour

            try:
                pvProduction = (values['power_ac'] * (10 ** values['power_ac_scale'])) + (values['batteries']['Battery1']['instantaneous_power'])
                gridImportExport = (values['meters']['Meter1']['power'] * (10 ** values['meters']['Meter1']['power_scale']))
                batteryImportExport = (values['batteries']['Battery1']['instantaneous_power'])
                householdConsumption = (values['power_ac'] * (10 ** values['power_ac_scale'])) - (values['meters']['Meter1']['power'] * (10 ** values['meters']['Meter1']['power_scale']))
                batterySoe = (values['batteries']['Battery1']['soe'])
                batteryNeeded = batteryCapacity - (batteryCapacity * batterySoe / 100)

                if pvProduction < 0:
                    householdConsumption = householdConsumption + abs(pvProduction)
                    pvProduction = 0
                if householdConsumption > 0:
                    daily_consumption = daily_consumption + householdConsumption
                    avg_counter = avg_counter + 1
                    avg_consumption = daily_consumption / avg_counter

                pvProductionInterval = pvProductionInterval + (pvProduction / 1000)
                avg_production_counter = avg_production_counter + 1
                avg_production = pvProductionInterval / avg_production_counter

                hour = datetime.now().time().hour
                day = datetime.now().today().day
                dt_string = datetime.now().strftime("%d.%m.%Y;%H:%M:%S")

                if (hour != old_hour):
                    if (hour >= sunrise_hour and hour <= sunset_hour):
                        remaining_sunshine = get_sunshine(avg_consumption) * adjustment_factor
                    else:
                        remaining_sunshine = 0
                    old_hour = hour
                if (remaining_sunshine < batteryNeeded and hour > sunrise_hour):
                    post_peak = True
                if (day != old_day):
                    avg_consumption = 0
                    daily_consumption = 0
                    avg_counter = 0
                    post_peak = False
                    old_day = day

                print(f"{dt_string};{pvProduction};{avg_production:.4f};{gridImportExport:.1f};{batteryImportExport};{householdConsumption};{avg_consumption:.1f};{batterySoe};{batteryNeeded:.
0f};{remaining_sunshine:.0f};{post_peak};{mode}", flush=True)

                if (avg_production_counter >= ((solcast_reporting_interval * 60) / interval_seconds)):
                    print ("Sending average production to Solcast...")
                    current_time_iso = datetime.now().astimezone(pytz.timezone(city.timezone)).replace(microsecond=0).isoformat()
                    solcast_json = {"measurement": {"period_end": current_time_iso, "period": solcast_period, "total_power": avg_production}}
                    try:
                        solcast_response = requests.post(solcast_report_url, json = solcast_json)
                        print (solcast_response.status_code, solcast_response.reason, solcast_response.text)
                    except Exception as err:
                        print (f"Error occurred: {err.args}", flush=True)
                    avg_production = 0
                    avg_production_counter = 0
                    pvProductionInterval = 0

                inverter.write("storage_control_mode", 4)
                inverter.write("storage_default_mode", 7)
                if pvProduction > (kWp / 3) and batterySoe > min_battery_level and (post_peak == False or batterySoe > 90):
                    mode = "Maximize export"
                    inverter.write("rc_cmd_mode", 4)
                elif pvProduction > (householdConsumption * 2) and batterySoe >= min_battery_level and post_peak == False:
                    mode = "Charge only with excess PV"
                    inverter.write("rc_cmd_mode", 1)
                else:
                    mode = "Maximize self-consumption"
                    inverter.write("rc_cmd_mode", 7)

            except Exception as err:
                print (f"Error occurred: {err.args}", flush=True)

            values = get_values(inverter)
            end_time = time.time()
            time.sleep(abs(interval_seconds - (end_time - start_time)))
