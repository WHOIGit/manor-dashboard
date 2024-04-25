"""This Flask application hosts a no-login Nagios Dashboard that periodically updates"""
import os
import pytz
import json
from pprint import pprint
from ast import literal_eval
from collections import defaultdict
from datetime import datetime, timedelta
import requests
from flask import Flask, render_template, make_response
from flask_apscheduler import APScheduler

QUERY_ROOT = 'https://nagios-common.whoi.edu/nagios/cgi-bin/statusjson.cgi'

app = Flask(__name__)
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

DATAFILE = 'servicelist.dict'

# Authentication for QUERY_ROOT
app.config["AUTHFILE"] = os.environ['AUTHFILE']
with open(app.config["AUTHFILE"]) as f:
    app.config["AUTH"] = tuple(f.read().split())

app.config['FLASK_DEBUG'] = 1
app.config['DATA_POLLING_INTERVAL_MINS'] = 2
app.config['PAGE_REFRESH_INTERVAL_MINS'] = 1
app.config['DATA_POLLING_CERTS'] = os.environ['DATA_POLLING_CERTS'] if 'DATA_POLLING_CERTS' in os.environ else False
app.config['CNAME_CSV'] = os.environ['CNAME_CSV'] if 'CNAME_CSV' in os.environ and os.path.isfile(os.environ['CNAME_CSV']) else False

if app.config['FLASK_DEBUG']:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

@scheduler.task('cron', id='periodic-update', minute='*/{}'.format(app.config['DATA_POLLING_INTERVAL_MINS']), max_instances=1)
def update():
    servicelist = collect_data(app.config["AUTH"])
    update_time = datetime.now(pytz.timezone('US/Eastern'))
    update_time = datetime.strftime(update_time,'%Y-%m-%d %H:%M:%S %Z')
    data = dict(servicelist=servicelist,update_time=update_time)
    with open(DATAFILE,'w') as f:
        pprint(data, f)

def collect_data(auth, output=None):
    query_service = '?query=servicelist&hostname=manor.whoi.edu'
    url_service = QUERY_ROOT+query_service
    # fixed verify=False, see https://stackoverflow.com/a/12864892
    r_service = requests.get(url_service, auth=auth, verify=app.config['DATA_POLLING_CERTS'])
    servicelist = r_service.json()
    data = servicelist.pop('data')['servicelist']
    # Output
    if isinstance(output,str) and output.endswith('.json'):
        with open(output, 'w') as f:
            json.dump(data,f,indent=2)
    elif output==print:
        pprint(data)
    return data


def collate_data(data):
    MESSAGE = {2: 'ok', 4: 'warning', 8: 'unknown', 16: 'critical'}
    outdata = []
    for host in data:
        hostname = host.rsplit('.',2)[0] if host != 'www.whoi.edu' else host
        services = []
        bins = dict(ok=[], warning=[], unknown=[], critical=[])
        for service,status in data[host].items():
            msg = MESSAGE[status]
            service_data = dict(name=service, status=status, msg=msg)
            services.append(service_data)
            bins[msg].append(service)

        services.sort(key=lambda d:d['status'],reverse=True)
        host_status = services[0]['status'] # highest status value

        if len(bins['ok'])==len(services):
            host_msg = 'ok'
            host_desc = 'No Critical or Unknown Errors, no Warnings'
        else:
            host_msg = host_desc = ''
            if bins['critical']:
                host_msg = 'critical'
                host_desc = 'Critical Errors: [{}]\n'.format(','.join(bins['critical']))
            if bins['unknown']:
                host_msg = host_msg if host_msg else 'unknown'
                host_desc += 'Unknown Errors: [{}]\n'.format(','.join(bins['unknown']))
            if bins['warning']:
                host_msg = host_msg if host_msg else 'warning'
                host_desc += 'Warnings: [{}]\n'.format(','.join(bins['warning']))
            host_desc = host_desc.strip()

        host_dict = dict(host=host, hostname=hostname, cnames=[], status=host_status, msg=host_msg, description=host_desc, services=services)
        outdata.append(host_dict)

    outdata.sort(key=lambda d: d['status'], reverse=True)
    return outdata

def cname_demux(data):
    host_cnames = defaultdict(list)
    with open(app.config['CNAME_CSV']) as f:
        axfr = f.read().splitlines()
    for line in axfr:
        ip,host,cnames = line.split(',')
        cnames = cnames.split()
        host_cnames[host] = cnames

    for host_dict in data:
        if host_dict['host'] in host_cnames:
            host_dict['cnames'] = host_cnames[host_dict['host']]
    return data

def read_datafile():
    try:
        with open(DATAFILE) as f:
            data = literal_eval(f.read())
        servicelist = data['servicelist']
        update_time = data['update_time']
    except (FileNotFoundError,KeyError):
        update()
        with open(DATAFILE) as f:
            data = literal_eval(f.read())
        servicelist = data['servicelist']
        update_time = data['update_time']
    return servicelist,update_time

@app.route('/')
def index():
    servicelist,update_time = read_datafile()
    data = collate_data(servicelist)
    if app.config['CNAME_CSV']:
        cname_demux(data)
    class_enum = {'critical':'table-danger',
                  'unknown':'table-danger',
                  'warning':'table-warning',
                  'ok':'table-success'}

    status_count = dict(ok=0, critical=0, warning=0, unknown=0, sites=0)
    for host_data in data:
        host_data['class'] = class_enum[host_data['msg']]
        host_data['description'] = host_data['description'].replace('\n','<br>')
        status_count[host_data['msg']] += 1
        status_count['sites'] += len(host_data['cnames'])

    refresh_time = timedelta(minutes=app.config['PAGE_REFRESH_INTERVAL_MINS'])
    context = dict(data=data,
                   update_time=update_time,
                   status_count=status_count, # "Summary: {OK: all} {warnings - none} {critical - 3} {unknown - none}"
                   refresh_seconds=refresh_time.seconds)

    return render_template('index.html', **context)


@app.route('/update')
def update_endpoint():
    update()
    servicelist,update_time = read_datafile()
    response = make_response(update_time, 200)
    response.mimetype = "text/json"
    return response


if __name__ == '__main__':
    app.run()



