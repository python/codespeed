#!/usr/bin/env python

import os

from django.utils.crypto import get_random_string

chars = 'abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)'
secret = get_random_string(50, chars)

filename = os.path.join(os.path.dirname(__file__), 'secret_key')
print('Writing secret key to', filename)
with open(filename, 'w') as f:
    f.write(secret)
