"""
open XQuartz and run: xhost +

python main.py filename.json no (headleass False)
python main.py filename.json (headleass True)
"""
import os
import json
from sys import argv

from services import run


if __name__ == '__main__':
    # remove filename from args
    argv.pop(0)

    filename = argv.pop(0)
    headless = True
    if argv.pop(0) == 'no':
        headless = False

    print(f'run crawler to filename: {filename}, headless: {headless}')

    data = {}
    with open(filename, 'r') as f:
        data = json.loads(f.read())

    run(data, headless)
