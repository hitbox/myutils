#!/usr/bin/env python
import argparse
import fnmatch
import os
import re

from datetime import datetime
from operator import attrgetter
from pathlib import Path

no_files = object()

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

def run(root_path, dry_run=False, exclude=None, report=False):
    """
    Update directories of `root_path` mtime to that of its newest file.
    """
    for child_dir in Path(root_path).iterdir():
        if not child_dir.is_dir():
            # skip non-directories
            continue
        # Recursively find the newest file in this child dir of root.
        newest_file = max(walk_files(child_dir, exclude), default=no_files)
        if newest_file is no_files:
            # skip for no files
            continue
        if newest_file.stat().st_mtime <= child_dir.stat().st_mtime:
            # skip for newest file is not newer than directory
            continue
        if report:
            print(child_dir)
            print(f'\t{newest_file}')
            print(f'\tParent: {datetime.fromtimestamp(child_dir.stat().st_mtime)}')
            print(f'\tNewest: {datetime.fromtimestamp(newest_file.stat().st_mtime)}')
        if not dry_run:
            # update mtime, keeping atime
            atime = child_dir.stat().st_atime
            newest_mtime = newest_file.stat().st_mtime
            os.utime(child_dir, (atime, newest_mtime))

def root_type(string):
    return Path(string).resolve()

def argument_parser():
    parser = argparse.ArgumentParser(
        description = main.__doc__,
    )
    parser.add_argument(
        '--root',
        type = root_type,
        default = '.',
        help = 'Root directory. Defaults to current directory.',
    )
    parser.add_argument(
        '--exclude',
        action = 'append',
        help = 'Exclude filenames matching shell pattern.',
    )
    parser.add_argument(
        '--dry',
        action = 'store_true',
        help = 'Dry run. Do not update the directories times.',
    )
    parser.add_argument(
        '--report',
        dest = 'report',
        action = 'store_true',
        default = True,
        help = 'Report updates. Default on.',
    )
    parser.add_argument(
        '--no-report',
        dest = 'report',
        action = 'store_false',
        help = 'Do not report updates.',
    )
    return parser

def exclude_from_args(args):
    if args.exclude:
        patterns = '|'.join(map(fnmatch.translate, args.exclude))
        exclude = re.compile(patterns).match
    else:
        exclude = lambda filename: False

    return exclude

def main(argv=None):
    """
    Update the directories to their newest file's datetime.
    """
    parser = argument_parser()
    args = parser.parse_args(argv)
    exclude = exclude_from_args(args)
    run(args.root, args.dry, exclude, args.report)

if __name__ == '__main__':
    main()
