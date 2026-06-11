import urllib.request; r = urllib.request.urlopen('http://127.0.0.1:5000/'); html = r.read().decode('utf-8'); print(html[:2000])  
