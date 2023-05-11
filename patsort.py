#!/usr/bin/env python
import argparse
import os
import re

def run(files, pattern=None):
    key = None
    filter_func = None

    if pattern:
        key_re = re.compile(pattern)
        filter_func = key_re.search
        def key(path):
            match = filter_func(path)
            if match:
                return match.groups()
            else:
                return (path,)

    for ls_path in files:
        paths = filter(filter_func, os.listdir(ls_path))
        for path in sorted(paths, key=key):
            print(path)

def main(argv=None):
    """
    Sort file list by pattern key.
    """
    # NOTE
    # - motivated to sort a file listing by a pattern.
    # - want to rename the files using enumerated, sorted output.
    # - linux sort command has a key sort option but it only seems to take
    #   positions in the filename string.
    parser = argparse.ArgumentParser(
        description = main.__doc__,
    )
    parser.add_argument(
        'files',
        nargs = '*',
    )
    parser.add_argument(
        '-p', '--pattern',
    )
    args = parser.parse_args(argv)

    if not args.files:
        args.files.append('.')

    run(args.files, args.pattern)

if __name__ == '__main__':
    main()
