import urllib.request
import os
url = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"
output = "tools/axe.min.js"
print(f"Downloading {url} to {output}...")
urllib.request.urlretrieve(url, output)
print("Done.")
