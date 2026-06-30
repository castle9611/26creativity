# -*- coding: utf-8 -*-
import importlib, traceback
try:
 importlib.import_module('_sqlite3'); print('OK')
except BaseException:
 traceback.print_exc(); raise
