#!/usr/bin/env python3
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter, FileType
import warnings
import zipfile
from io import TextIOWrapper
from typing import IO
import numpy as np
import configparser

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

def repack_analog(offset, div, data: IO[bytes]) -> bytes:
    points = np.frombuffer(data, dtype=np.uint8).astype(np.float32)
    points = (offset - points) / div
    return points.tobytes()

def copy_data(num_probes, num_blocks, dsl: zipfile.ZipFile, sr: zipfile.ZipFile):
    # Convert individual per-channel DSL data blocks into sigrok's combined data slices.
    try:
        # Easiest way to check if a file exists in the archive is just except a
        # KeyError if it's not found.
        dsl.getinfo("L-0/0")
        print(f"Converting DSLogic data")
        for b in range(num_blocks):
            dsl_data = [dsl.read(f"L-{p}/{b}") for p in range(num_probes)]
            with sr.open(f"logic-1-{b + 1}", "w") as data:
                data.write(merge_bitstreams(dsl_data))
        return
    except KeyError:
        pass

def convert_analog(probe, offset, div, num_blocks, dsl: zipfile.ZipFile, sr: zipfile.ZipFile):
    try:
        # Easiest way to check if a file exists in the archive is just except a
        # KeyError if it's not found.
        dsl.getinfo(f"O-{probe}/0")
        print(f"Converting DSCope Oscilloscope data for probe {probe}")
        for b in range(num_blocks):
            dsl_data = dsl.read(f"O-{probe}/{b}")
            with sr.open(f"analog-1-{probe + 1}-{b + 1}", "w") as data:
                data.write(repack_analog(offset, div, dsl_data))
        return
    except KeyError:
        pass

    try:
        # Easiest way to check if a file exists in the archive is just except a
        # KeyError if it's not found.
        # Note: These files are interweaved with adjacent channels.
        print(f"Converting DSCope Data Acquisition data for probe {probe}")
        for b in range(num_blocks):
            dsl_data = dsl.read(f"A-{probe // 2}/{b}")[probe::2]
            with sr.open(f"analog-1-{probe + 1}-{b + 1}", "w") as data:
                data.write(repack_analog(offset, div, dsl_data))
        return
    except KeyError:
        pass

    print(f"Failed to convert analog data for probe: {probe}")

def convert(dsl: zipfile.ZipFile, sr: zipfile.ZipFile):
    num_probes = 0
    num_blocks = 0

    metadata = configparser.ConfigParser(default_section='global')
    metadata['global'] = {
        'sigrok sigrok version':'0.6.0',
    }
    metadata.add_section('device 1')

    with dsl.open("header", mode="r") as dslm:
        config = configparser.ConfigParser()
        config.read_file(TextIOWrapper(dslm, encoding='utf-8'), "header")
        if config['version']['version'] != '3':
            raise ValueError(f"Error: unsupported DSView file version {config['version']['version']}")

        header = config['header']
        num_probes = int(header["total probes"])
        num_blocks = int(header["total blocks"])

        if header['driver'] == "DSLogic":
            print("Detected DSLogic capture data")
            # figure out how many bytes we need to pack all channels.
            unitsize = (num_probes + 7) // 8
            metadata['device 1']['unitsize'] = str(unitsize)
            metadata['device 1']['capturefile'] = 'logic-1'
            metadata['device 1']['total probes'] = str(num_probes)
            for p in range(num_probes):
                metadata['device 1'][f'probe{p}'] = header[f'probe{p}']

            copy_data(num_probes, num_blocks, dsl, sr)
        elif header['driver'] in ["DSCope", "virtual-demo"]:
            print("Detected DSCope analog data")
            metadata['device 1']['samplerate'] = header['samplerate']
            # Reserve 'total analog' before the probe defintions to prevent a invalid format bug in sigrok
            metadata['device 1']['total analog'] = ''

            for p in range(num_probes):
                # ConfigParser trreats indented lines following a property value as multi-line strings.
                # We can use this to extract the probe's properties even though each property is suffixed
                #  with the probe index.
                probe_data = header[f"probe{p}"].split("\n")
                probe_name = probe_data[0]
                probe = {
                    key.strip(): value.strip()
                    for key, _, value in (kv.partition(f'{p} =') for kv in probe_data[1:])
                }
                if probe['enable'] == '0':
                    num_probes -= 1
                    continue

                metadata['device 1'][f'analog{p + 1}'] = probe_name
                convert_analog(p, int(probe['vOffset']), int(probe['vDiv']), num_blocks, dsl, sr)

            metadata['device 1']['total analog'] = str(num_probes)
        else:
            raise ValueError(f"Warning: Unknown DSView device type '{header['driver']}'")

    with sr.open("metadata", "w") as srm:
        metadata.write(TextIOWrapper(srm, encoding='utf-8'))

    print(f"Found {num_probes} probes/{num_blocks} blocks of data")
    return num_probes, num_blocks


def main():
    with zipfile.ZipFile(args.input, mode="r") as dsl:
        with zipfile.ZipFile(args.output, mode="w", compression=zipfile.ZIP_DEFLATED) as sr:
            sr.writestr("version", "2")
            convert(dsl, sr)


if __name__ == "__main__":
    main()
