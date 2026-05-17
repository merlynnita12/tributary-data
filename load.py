"""
Loader helpers for the Tributary dataset.

After cloning the repo, run this once to decompress transactions.csv.gz
into transactions.csv. The other files are committed uncompressed.

Or, if you'd rather regenerate from scratch with the same seed,
just run `python generate.py` and it'll write all files fresh.
"""

import gzip
import shutil
from pathlib import Path


def decompress_transactions(output_dir='./output'):
    out = Path(output_dir)
    gz_path = out / 'transactions.csv.gz'
    csv_path = out / 'transactions.csv'

    if csv_path.exists():
        print(f"{csv_path} already exists, skipping.")
        return

    if not gz_path.exists():
        print(f"{gz_path} not found. Run generate.py to create the data fresh.")
        return

    print(f"Decompressing {gz_path}...")
    with gzip.open(gz_path, 'rb') as f_in:
        with open(csv_path, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
    print(f"Wrote {csv_path}")


if __name__ == '__main__':
    decompress_transactions()
