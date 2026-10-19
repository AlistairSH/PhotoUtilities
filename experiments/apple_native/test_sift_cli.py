"""Native SIFT harness must reject changed pixels and malformed pair identities."""
import argparse
import copy
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',type=Path,required=True)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='native-sift-invalid-') as folder:
        root=Path(folder);pixel=root/'flat.rgba';data=bytes([128,128,128,255])*64*64;pixel.write_bytes(data)
        image={'index':0,'width':64,'height':64,'pixels':str(pixel),'sha256':hashlib.sha256(data).hexdigest()}
        image2=dict(image,index=1)
        base={'images':[image,image2],'pairs':[{'a':0,'b':1,'vision_distance':1.}]}
        invalid=[]
        x=copy.deepcopy(base);x['images'][0]['sha256']='0'*64;invalid.append(x)
        x=copy.deepcopy(base);x['images'][0]['index']=2;invalid.append(x)
        x=copy.deepcopy(base);x['pairs']*=2;invalid.append(x)
        x=copy.deepcopy(base);x['pairs'][0]['b']=2;invalid.append(x)
        x=copy.deepcopy(base);x['pairs'][0]['vision_distance']=-1;invalid.append(x)
        x=copy.deepcopy(base);x['images'][0]['pixels']=str(root/'missing.rgba');invalid.append(x)
        tiny=root/'truncated.rgba';tiny.write_bytes(data[:4])
        x=copy.deepcopy(base);x['images'][0].update(pixels=str(tiny),sha256=hashlib.sha256(data[:4]).hexdigest());invalid.append(x)
        for i,payload in enumerate(invalid):
            manifest=root/f'{i}.json';manifest.write_text(json.dumps(payload))
            process=subprocess.run([str(args.binary.resolve()),str(manifest)],capture_output=True,text=True,timeout=10)
            assert process.returncode!=0 and '"type":"complete"' not in process.stdout,(i,process.stdout)
        assert pixel.read_bytes()==data
    print('Passed seven native harness rejection checks; input bytes unchanged')


if __name__=='__main__': main()
