#!/usr/bin/env python3

from CalNES.NES import NES
import sys
import time

def main():
    filename = sys.argv[1]
    DEBUG = True if (len(sys.argv) > 2 and sys.argv[2] == '-d') else False
    n = NES(filename, DEBUG)
    timer = time.time()
    while True:
        n.step()
        cur_time = time.time()
        if cur_time - timer >= 0.16639:
            timer = cur_time
            n.update_display()

main()
