
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter, FileType
import warnings
import zipfile
import numpy as np

warnings.simplefilter("ignore")

# Parse command line arguments
parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)
parser.add_argument('-i', '--input', type=str)
parser.add_argument('-o', '--output', type=str)
args = parser.parse_args()


def merge_bitstreams(data):
    """Merges together per-channel bitstreams into packed unitsize samples used by sigrok"""
    num_streams = len(data)
    # Convert input data into arrays of individual bits
    bits = [np.unpackbits(np.frombuffer(d, dtype=np.uint8),
                          bitorder='little') for d in data]
    # Then stack them all and pack into all-channels units
    return np.packbits(np.stack(bits, axis=1), axis=-1, bitorder='little').tobytes()


def copy_data(num_probes, num_blocks, dsl, sr):
    # Convert individual per-channel DSL data blocks into sigrok's combined data slices.
    for b in range(num_blocks):
        dsl_data = [dsl.read("L-%d/%d" % (p, b)) for p in range(num_probes)]
        with sr.open("logic-1-%d" % (b+1), "w") as data:
            data.write(merge_bitstreams(dsl_data))


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
            kv = [x.strip() for x in line.split('=')]
            if len(kv) != 2:
                continue
            k, v = kv
            if k == "total probes":
                num_probes = int(v)
            elif k == "total blocks":
                num_blocks = int(v)
            if k.startswith("probe"):
                # DSL uses 0-based probe numbering, sigrok wants 1-based.
                p = int(k[5:])+1
                sr_metadata += ("probe%d=%s\n" % (p, v))
            if k in ["samplerate", "total probes"]:
                sr_metadata += ("%s=%s\n" % (k, v))
    # figure out how many bytes we need to pack all channels.
    unitsize = (num_probes + 7) // 8
    sr_metadata += "unitsize=%d" % unitsize
    with sr.open("metadata", "w") as srm:
        srm.write(sr_metadata.encode('utf-8'))

    print("Found %d probes/%d blocks of data" % (num_probes, num_blocks))
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
