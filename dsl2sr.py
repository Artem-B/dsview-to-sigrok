
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter, FileType
import warnings
import zipfile
import numpy as np

warnings.simplefilter("ignore")
 
# Parse command line arguments
parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)
parser.add_argument('-i', '--input', type=str)

# Add an optional argument for the output file,
# open in 'write' mode and and specify encoding
parser.add_argument('-o', '--output', type=str)
args = parser.parse_args()


def merge_bitstreams(data):
    num_streams = len(data)
    bits = [np.unpackbits(np.frombuffer(d, dtype=np.uint8), bitorder='little') for d in data]
    return np.packbits(np.stack(bits, axis = 1), axis = -1, bitorder='little').tobytes()




def copy_data(num_probes, num_blocks, dsl, sr):
    for b in range(num_blocks):
        dsl_data = [dsl.read("L-%d/%d" % (p, b)) for p in range(num_probes)]
        sr_data = merge_bitstreams(dsl_data)
        with sr.open("logic-1-%d" % (b+1), "w") as data:
            data.write(sr_data)

def copy_metadata(dsl, sr):
    num_probes = 0
    num_blocks = 0
    sr_metadata = """
[global]
sigrok sigrok version=0.6.0
[device 1]
total analog=0
capturefile=logic-1
"""
    with dsl.open("header", mode="r") as dslm:
            for line in dslm:
                line = line.decode('utf-8').strip()
                kv = [ x.strip() for x in line.split('=')]
                if len(kv) !=2:
                    continue
                k, v = kv
                if k == "total probes":
                    num_probes = int(v)
                elif k == "total blocks":
                    num_blocks = int(v)
                if k.startswith("probe"):
                    p = int(k[5:])+1
                    sr_metadata += ("probe%d=%s\n" % (p, v))
                if k in ["samplerate", "total probes"]:
                    sr_metadata += ("%s=%s\n" % (k, v))
    unitsize = (num_probes + 7) // 8
    sr_metadata += "unitsize=%d" % unitsize
    with sr.open("metadata", "w") as srm:
        srm.write(sr_metadata.encode('utf-8'))

    print("Found %d probes/%d blocks" %(num_probes, num_blocks))
    return num_probes, num_blocks

def convert(dsl, sr):
    num_probes, num_blocks = copy_metadata(dsl, sr)
    copy_data(num_probes, num_blocks, dsl, sr)
    
def main():
    with zipfile.ZipFile(args.input, mode="r") as dsl:
        with zipfile.ZipFile(args.output, mode="w", compression=zipfile.ZIP_DEFLATED) as sr:
            sr.writestr("version", "2")
            convert(dsl, sr)

if __name__ == "__main__":
    main()