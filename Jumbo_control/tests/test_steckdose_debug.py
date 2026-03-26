"""Debug: rohe HTTP-Antworten der ALL4076 ausgeben."""
import urllib.request

IP = "192.168.1.215"

def get(url):
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return r.status, r.read().decode("utf-8")
    except Exception as e:
        return None, str(e)

urls = [
    f"http://{IP}/xml",
    f"http://{IP}/xml/",
    f"http://{IP}/xml/?q=0",
    f"http://{IP}/xml?q=0",
    f"http://{IP}/xml/?mode=actor&type=list",
    f"http://{IP}/xml?mode=actor&type=list",
]

for url in urls:
    code, body = get(url)
    print(f"\nURL: {url}")
    print(f"HTTP {code}")
    print(body[:300])
    print("-"*50)
