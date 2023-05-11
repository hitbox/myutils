#!/usr/bin/env python
import argparse
import datetime
import fnmatch
import os
import re

from operator import attrgetter
from pathlib import Path

def st_mtime(path):
    return path.stat().st_mtime

def walk_files(root, exclude=None):
    """
    :param exclude:
        Called on filename return true to ignore.
    """
    if exclude is None:
        exclude = lambda filename: False
    for dirpath, dirnames, filenames in os.walk(root):
        for filename in filenames:
            if exclude(filename):
                continue
            yield Path(os.path.join(dirpath, filename))

def run(root_path, dry_run=False, exclude=None):
    """
    Update directories of `root_path` mtime to that of its newest file.
    """
    for child_dir in Path(root_path).iterdir():
        if not child_dir.is_dir():
            # skip not a directory
            continue
        file_paths = list(walk_files(child_dir, exclude))
        if not file_paths:
            # skip for no files
            continue
        newest_file = max(file_paths, key=st_mtime)
        if newest_file.stat().st_mtime <= child_dir.stat().st_mtime:
            # skip for newest file is not newer than directory
            continue
        if dry_run:
            print(child_dir)
            print(f'\t{newest_file}')
            print(f'\tParent: {datetime.datetime.fromtimestamp(child_dir.stat().st_mtime)}')
            print(f'\tNewest: {datetime.datetime.fromtimestamp(newest_file.stat().st_mtime)}')
        else:
            # update mtime, keeping atime
            atime = child_dir.stat().st_atime
            newest_mtime = newest_file.stat().st_mtime
            os.utime(child_dir, (atime, newest_mtime))

def root_type(string):
    return Path(string).resolve()

def main(argv=None):
    """
    Update directories to their newest file's datetime.
    """
    parser = argparse.ArgumentParser(
        description = main.__doc__,
    )
    parser.add_argument(
        '--root',
        type = root_type,
        default = '.',
        help = 'Root directory. Default: %(default)s.',
    )
    parser.add_argument(
        '--exclude',
        action = 'append',
        help = 'Exclude filenames matching shell pattern.',
    )
    parser.add_argument(
        '--dry',
        action = 'store_true',
        help = 'Dry run.',
    )
    args = parser.parse_args(argv)

    if args.exclude:
        patterns = '|'.join(map(fnmatch.translate, args.exclude))
        exclude = re.compile(patterns).match
    else:
        exclude = lambda filename: False

    run(args.root, args.dry, exclude)

if __name__ == '__main__':
    main()
