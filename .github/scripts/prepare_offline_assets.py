"""Prepare a hash-verified public tokenizer asset before network-denied tests."""
import argparse,hashlib,json,os,pathlib,urllib.request
p=argparse.ArgumentParser();p.add_argument('--cache',required=True);a=p.parse_args()
cache=pathlib.Path(a.cache).resolve();cache.mkdir(parents=True,exist_ok=True)
os.environ['TIKTOKEN_CACHE_DIR']=str(cache)
os.environ['CUSTOM_TIKTOKEN_CACHE_DIR']=str(cache)
url='https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken'
expected='223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7'
target=cache/hashlib.sha1(url.encode()).hexdigest()
if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest()!=expected:
    with urllib.request.urlopen(url,timeout=30) as response:data=response.read()
    assert hashlib.sha256(data).hexdigest()==expected
    target.write_bytes(data)
import tiktoken
tiktoken.get_encoding('cl100k_base')
print(json.dumps({'cache':str(cache),'assets':[{'file':f.name,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in cache.iterdir() if f.is_file()],'model_calls':0}))
