####################################################
# Sample script that shows how to save result data using json #
####################################################
import json
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen


# You need to enter the real URL and have the server running
CODESPEED_URL = 'http://localhost:8000/'

sample_data = [
    {
        "commitid": "8",
        "project": "MyProject",
        "branch": "default",
        "executable": "myexe O3 64bits",
        "benchmark": "float",
        "environment": "Dual Core",
        "result_value": 2500.0,
        "source": "legacy"
    },
    {
        "commitid": "8",
        "project": "MyProject",
        "branch": "default",
        "executable": "myexe O3 64bits",
        "benchmark": "int",
        "environment": "Dual Core",
        "result_value": 1100,
        "source": "legacy"
    }
]


def add(data):
    response = "None"
    try:
        f = urlopen(
            CODESPEED_URL + 'result/add/json/', urlencode(data).encode('utf-8'))
    except HTTPError as e:
        print(str(e))
        print(e.read().decode())
        return
    response = f.read().decode()
    f.close()
    print("Server (%s) response: %s\n" % (CODESPEED_URL, response))


if __name__ == "__main__":
    data = {'json': json.dumps(sample_data)}
    add(data)
