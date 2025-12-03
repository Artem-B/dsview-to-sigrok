# dsview-to-sigrok
Convert DSLogic .dsl files into sigrok's .sr format. This only supports converting the captured data and makes no attempt at convering the decoders or markers

## Support

- [X] DSLogic logic analyser files
- [X] DSCope Oscilloscope files
- [X] DSCope Data Aquisition files

## Usage

```bash
./dsl2sr.py -i <input-file.dsl> -o <output-file.sr>
```