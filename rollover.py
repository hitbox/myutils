#!/usr/bin/env python
import argparse
import os
import shutil
import textwrap

def rollover(
    source,
    backup_count = 0,
    keep_source = False,
    exists_func = os.path.exists,
    remove_func = os.remove,
    rename_func = os.rename,
    copy_func = shutil.copy2,
):
    """
    Do file rollover like logging.handlers.RotatingFileHandler.
    """
    if backup_count > 0:
        for i in range(backup_count, 0, -1):
            sfn = f'{source}.{i:d}'
            dfn = f'{source}.{i+1:d}'
            if exists_func(sfn):
                if exists_func(dfn):
                    remove_func(dfn)
                rename_func(sfn, dfn)
        dfn = f'{source}.1'
        if exists_func(dfn):
            remove_func(dfn)
        if keep_source:
            copy_func(source, dfn)
        else:
            rename_func(source, dfn)

def dry_remove(filename):
    print(f'remove {filename}')

def dry_rename(src, dst):
    print(f'rename {src} -> {dst}')

def dry_copy(src, dst):
    print(f'copy {src} -> {dst}')

def main(argv=None):
    """
    File rollover utility
    """
    parser = argparse.ArgumentParser(
        description = main.__doc__,
        prog = 'rollover',
    )
    parser.add_argument('source')
    parser.add_argument('-n', '--dry',
        action = 'store_true',
        help = 'Dry run.'
    )
    parser.add_argument('-k', '--keep',
        action = 'store_true',
        help = 'Keep original source file.'
    )
    # TODO
    # - automatic count plus one for infinite rollover count.
    parser.add_argument('-c', '--count',
        default = 10,
        help = 'Count of rollover backups to keep. Ex.: file.txt.1, file.txt.2,'
            ' ..., file.txt.9 for the default of %(default)s.'
    )
    args = parser.parse_args(argv)
    kwargs = dict(
        backup_count = args.count,
        keep_source = args.keep,
    )
    if args.dry:
        kwargs.update(
            remove_func = dry_remove,
            rename_func = dry_rename,
            copy_func = dry_copy,
        )
    rollover(args.source, **kwargs)

if __name__ == '__main__':
    main()
