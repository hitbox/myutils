#!/home/hitbox/venv-ytdlp/bin/python
#!/usr/bin/env python
import argparse
import configparser
import datetime
import math
import os
import subprocess
import sys
import time

from functools import cached_property
from operator import attrgetter
from operator import itemgetter
from operator import xor

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    import rtouch
except ImportError:
    rtouch = None

# special string to indicate ini option is a flag
IS_FLAG_VALUE = ':flag:'

class spec_order:

    def __init__(self, jumps):
        self.jumps = jumps

    def __call__(self, spec):
        try:
            # special jump order or...
            return self.jumps.index(spec.name)
        except ValueError:
            # ...whatever order they're already in
            return math.inf


class DownloadData:

    def __init__(
        self,
        *,
        python_exe,
        specs,
        insert_path = None,
        jump_list = None,
        intervals = None,
    ):
        """
        :param python_exe:
            required path to python exe.
        :param specs:
            list of objects specifying yt-dlp options.
        :param insert_path:
            a string to insert to the front of PATH.
        :param jump_list:
            list of strings overriding the normal order of specs.
        :param intervals:
            list of interval objects with options for yt-dlp to use during a
            given time interval.
        """
        self.python_exe = python_exe
        self.specs = specs
        self.insert_path = insert_path
        if jump_list is None:
            jump_list = []
        self.jump_list = jump_list
        if intervals is None:
            intervals = []
        self.intervals = intervals

    @cached_property
    def env(self):
        env = os.environ.copy()
        if self.insert_path:
            path_list = os.environ['PATH'].split(os.pathsep)
            path_list.insert(0, self.insert_path)
            env['PATH'] = os.pathsep.join(path_list)
        return env

    def iter_enabled_specs(self):
        for spec in self.specs:
            # skip disabled
            if not spec.enabled:
                continue
            # skip no urls and empty batch
            # yt-dlp throws an error message
            if not spec.urls:
                batch = spec.get_batch()
                if not batch or not has_non_empty(batch):
                    continue
            yield spec

    def applicable_interval(self, now):
        for (section_name, interval, remaining) in self.intervals:
            if not interval.match(now):
                continue
            yield (section_name, interval, remaining)


class Spec:

    def __init__(self, *, name, enabled, urls=None, **extra):
        self.name = name
        self.enabled = enabled
        self.urls = urls
        self.extra = extra

    def get_batch(self):
        return self.extra.get('batch')

    def update_kwargs_for_timeout(self, downloads, run_kwargs, extra):
        timeout_seconds = None
        now = datetime.datetime.now()
        matching = list(downloads.applicable_interval(now))
        if len(matching) > 1:
            raise ValueError('Multiple matching intervals.')
        elif len(matching) == 1:
            key, interval, remaining = matching[0]
            # insert timeout args and command in reverse
            timeout_timedelta = interval.duration(now)
            timeout_seconds = timeout_timedelta.total_seconds()
            run_kwargs['timeout'] = timeout_seconds
            extra.update(remaining)

    def cmdargs(self, dlargs, downloads, use_intervals):
        """
        :param dlargs: list of extra command line arguments for yt-dlp
        """
        args = [downloads.python_exe, '-m', 'yt_dlp']
        extra = self.extra.copy()

        run_kwargs = dict(
            env = downloads.env,
        )

        # interval override options
        if use_intervals:
            self.update_kwargs_for_timeout(downloads, run_kwargs, extra)

        # spec's remaining options in place
        add_remaining(args, extra)

        # XXX: possible collisions with config
        # NOTES:
        # - adding --rate, which is common, duplicates but yt-dlp picks up the
        #   last on--the one given on command line
        # - not sure how to eliminate dupes yet
        # - besides it works
        args.extend(dlargs)

        if self.urls:
            # NOTE: should be at end, as arguments to process
            args.append(self.urls)

        return (args, run_kwargs)


class Interval:

    def __init__(self, from_dt, to_dt):
        self.from_dt = from_dt
        self.to_dt = to_dt

    def duration(self, dt):
        to_dt = self.to_dt
        if isinstance(to_dt, datetime.time):
            to_dt = datetime.datetime.combine(dt.date(), to_dt)

        if dt <= to_dt:
            td = to_dt - dt
        else:
            to_dt += datetime.timedelta(days=1)
            next_midnight = datetime.datetime.combine(
                dt.date() + datetime.timedelta(days=1),
                datetime.time()
            )
            td = (next_midnight - dt) + (to_dt - next_midnight)
        return td

    def match(self, dt, print_=False):
        combine = datetime.datetime.combine

        from_dt = self.from_dt
        if isinstance(from_dt, datetime.time):
            from_dt = combine(dt.date(), from_dt)

        to_dt = self.to_dt
        if isinstance(to_dt, datetime.time):
            to_dt = combine(dt.date(), to_dt)

        if from_dt < to_dt:
            return from_dt <= dt <= to_dt
        else:
            return dt >= from_dt or dt <= to_dt


def safepop(section, key, getfunc='get', default=None):
    """
    :param section:
        config section to pop from.
    :param key:
        the key to pop.
    :param getfunc:
        str of one of the get or coercing function from configparser
    """
    # NOTES
    # - we want to pop in a way that resolves to default
    # - configparser doesn't seem to do this
    # - configparser `pop` doesn't seem to resolve
    # - want to pop so that remaing key-values can be used as is
    section_getter = getattr(section, getfunc)
    value = section_getter(key, default)
    try:
        del section[key]
    except KeyError:
        pass
    return value

def resolve_datetime(string):
    strptime = datetime.datetime.strptime
    try:
        return strptime(string, '%H:%M').time()
    except ValueError:
        try:
            return strptime(string, '%Y-%m-%d %H:%M')
        except ValueError:
            raise ValueError('No matching datetime formats.')

def parse_interval(section):
    from_dt = resolve_datetime(section.pop('from'))
    to_dt = resolve_datetime(section.pop('to'))
    # ignore keys because dict() seems to resolve and overwrite, at least, the output key.
    # it grabs the default from the downloads section
    exclude = set(['output'])
    remaining = {key: value for key, value in section.items() if key not in exclude}
    return (section.name, Interval(from_dt, to_dt), remaining)

def parse_spec(section):
    spec = Spec(
        name = section.name,
        enabled = safepop(section, 'enabled', 'getboolean'),
        urls = section.pop('urls', None),
    )
    # add remaining after popping
    spec.extra.update(section)
    return spec

def specs_from_config(cp, keys):
    yield from map(parse_spec, map(cp.__getitem__, keys))

def has_non_empty(path):
    with open(path) as batch_file:
        for line in batch_file:
            line = line.strip()
            if line and not line.startswith('#'):
                # non-empty line that's not a comment
                return True

def is_empty_batch(spec):
    return (
        'batch' in spec
        and
        spec['batch']
        and not has_non_empty(spec['batch'])
    )

def add_remaining(args, data):
    for key, val in data.items():
        if key == 'urls' or val is None:
            continue
        key = f'--{key}'
        if val == IS_FLAG_VALUE:
            args.append(key)
        else:
            args.extend((key, val))

def parse_main(cp, jump_list=None):
    if jump_list is None:
        jump_list = []

    section = cp['downloads']
    assert 'download-archive' in section

    # pop asap to keep resolve/fallthrough from picking up
    python_exe = section.pop('python_exe')
    insert_path = section.pop('insert_path', '')
    keys = section.pop('keys').split()
    assert keys

    # raise for jump keys not existing
    if any(jump_key not in keys for jump_key in jump_list):
        raise ValueError('Key in jump list not found.')

    # insert path to front of PATH
    env = os.environ.copy()
    if insert_path:
        path_list = [insert_path] + os.environ['PATH'].split(os.pathsep)
        env['PATH'] = os.pathsep.join(path_list)

    # parse intervals
    use_intervals = safepop(section, 'use_intervals', 'getboolean')
    interval_keys = safepop(section, 'interval_keys', default='').split()
    if not use_intervals:
        intervals = None
    else:
        interval_sections = [cp[key] for key in interval_keys]
        intervals = list(map(parse_interval, interval_sections))

    # parse download specifications
    specs = sorted(specs_from_config(cp, keys), key=spec_order(jump_list))

    data = DownloadData(
        python_exe = python_exe,
        specs = specs,
        insert_path = insert_path,
        jump_list = jump_list,
        intervals = intervals,
    )
    return data

def run(dlargs, config, jump_list=None, dry=False, use_intervals=True, no_rtouch=False):
    """
    Download the configured urls.

    :param dlargs: extra command line arguments passed on to yt-dlp.
    """
    cp = configparser.ConfigParser(
        default_section = 'downloads',
        interpolation = configparser.ExtendedInterpolation(),
    )
    cp.read(config)
    downloads = parse_main(cp, jump_list)
    use_rtouch = not no_rtouch
    for spec in downloads.iter_enabled_specs():
        args, kwargs = spec.cmdargs(dlargs, downloads, use_intervals)
        if dry:
            print(subprocess.list2cmdline(map(str, args)), end='\n\n')
            continue
        if 'timeout' in kwargs:
            timeout = kwargs['timeout']
            print(f'{timeout=}')
        try:
            completed = subprocess.run(args, **kwargs)
        except subprocess.TimeoutExpired:
            pass
        except KeyboardInterrupt:
            break
        else:
            if use_rtouch and rtouch:
                rtouch.run(root_path=os.getcwd())

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('config', nargs='+')
    parser.add_argument(
        '--jump',
        nargs = '+',
        help = 'TODO',
    )
    parser.add_argument(
        '--dry',
        action = 'store_true',
        help = 'Display each download configuration instead of running.',
    )
    parser.add_argument(
        '--no-intervals',
        action = 'store_true',
        help = 'Disable intervals',
    )
    parser.add_argument(
        '--no-rtouch',
        action = 'store_true',
        help = 'Disable rtouching the top dir.',
    )
    args, dlargs = parser.parse_known_args(argv)
    run(
        dlargs,
        args.config,
        jump_list = args.jump,
        dry = args.dry,
        use_intervals = not args.no_intervals,
        no_rtouch = args.no_rtouch,
    )

if __name__ == '__main__':
    main()
