# -*- coding: utf-8 -*-
import importlib, traceback
try:
 importlib.import_module('_ctypes'); print('OK')
except BaseException:
 traceback.print_exc(); raise
