# -*- coding: utf-8 -*-
################################################################################
# This script imports PyPy's result data from json files located on the server #
################################################################################
import simplejson
from urllib.request import urlopen
from urllib.error import URLError
import sys
from xml.dom.minidom import parse
from datetime import datetime
import saveresults

URL = 'http://buildbot.pypy.org/benchmark-results/'
START_REV = 186137
END_REV = 200000


speed_url = "http://127.0.0.1:8000/"

# get json filenames
filelist = []
try:
    datasource = urlopen(URL)
    dom = parse(datasource)
    for elem in dom.getElementsByTagName('td'):
        for e in elem.childNodes:
            if len(e.childNodes):
                filename = e.firstChild.toxml()
                if e.tagName == "a" and ".json" in filename:
                    rev_int = int(filename.split(":")[0])
                    if START_REV <= rev_int <= END_REV:
                        filelist.append(filename)
except URLError as e:
    response = "None"
    if hasattr(e, 'reason'):
        response = '\n  We failed to reach ' + URL + '\n'
        response += '  Reason: ' + str(e.reason)
    elif hasattr(e, 'code'):
        response = '\n  The server couldn\'t fulfill the request\n'
        response += '  Error code: ' + str(e)
    print("Results Server (%s) response: %s\n" % (URL, response))
    sys.exit(1)
finally:
    datasource.close()

# read json result and save to speed.pypy.org
skipped = []
for filename in filelist:
    print(f"Reading {filename}...")
    f = urlopen(URL + filename)
    if f.length < 10:
        skipped.append(filename)
        continue
    result = simplejson.load(f)
    f.close()
    revision = result['revision']
    int_options = ""
    options = ""
    if 'options' in result:
        options = result['options']

    host = 'benchmarker'
    if revision and len(revision) >10:
        branch = result['branch']
        if branch in ("default", "main"):
            proj = "PyPy"
            executable = "pypy-c"
            branch = "main"
        elif branch == "py3.9":
            proj = "PyPy3.9"
            executable = "pypy3.9-64"
        elif branch == "py3.10":
            proj = "PyPy3.10"
            executable = "pypy3.10-64"
        elif branch == "py3.11":
            proj = "PyPy3.11"
            executable = "pypy3.11-64"
        else:
            skipped.append(filename)
            continue
        saveresults.save(proj, revision, result['results'], executable,
                         host, speed_url, branch=branch, changed=True)
        saveresults.save(proj, revision, result['results'],
                         executable.replace('-', '-jit-'),
                         host, speed_url, branch=branch, changed=False)
    else:
        savecpython.save('cpython', '100', result['results'], options, 'cpython', host)
print("\nOK")
print("skipped", skipped)
