from __future__ import print_function
import os
import sys
import time
import codecs
import datetime
import string
from tempfile import NamedTemporaryFile
import argparse
from subprocess import check_output, call, CalledProcessError
import pkg_resources
import io
from six.moves.configparser import SafeConfigParser
from six import StringIO, u

config_string = pkg_resources.resource_string(__name__, 'config.ini')
config_io = StringIO(config_string.decode('utf-8'))

config_parser = SafeConfigParser()
config_parser.readfp(config_io)

note_dir = config_parser.get('common', 'note_directory')
summary_dir = config_parser.get('common', 'summary_directory')
delim = config_parser.get('common', 'delimiter')
tag_marker = config_parser.get('common', 'tag_marker')

# searcher can be any of: grep, ag, ack-grep
searcher = config_parser.get('common', 'searcher')

searcher_args = {'grep': [],
                 'ack-grep': ['--nobreak']}
searcher_args['ack'] = searcher_args['ack-grep']
searcher_args['ag'] = searcher_args['ack-grep']

newline = u('\n')
date_prefix = u("## Journal: ")


if sys.version_info[0] > 2:
    def uwriter(fp):
        return fp
else:
    def uwriter(fp):
        return codecs.getwriter('utf-8')(fp)


def set_default_subparser(self, name, args=None):
    """
    Default subparser selection. Call after setup, just before parse_args()
    Taken from: http://stackoverflow.com/questions/6365601/default-
                sub-command-or-handling-no-sub-command-with-argparse

    Parameters
    ----------
    name: str
        The name of the subparser to call by default.
    args: str
        If set, is the argument list handed to parse_args()

    Tested with 2.7, 3.2, 3.3, 3.4.
    It works with 2.6 assuming argparse is installed.

    """
    subparser_found = False
    for arg in sys.argv[1:]:
        if arg in ['-h', '--help']:  # global help if no subparser
            break
    else:
        for x in self._subparsers._actions:
            if not isinstance(x, argparse._SubParsersAction):
                continue
            for sp_name in x._name_parser_map.keys():
                if sp_name in sys.argv[1:]:
                    subparser_found = True
        if not subparser_found:
            # insert default in first position, this implies no
            # global options without a sub_parsers specified
            if args is None:
                sys.argv.insert(1, name)
            else:
                args.insert(0, name)


argparse.ArgumentParser.set_default_subparser = set_default_subparser


def get_all_tags(prefix=''):
    """
    Find all tags present in the notes folder.

    Parameters
    ----------
    prefix : str, optional
        Only tags that begin with prefix will be returned.

    """
    query = tag_marker

    searcher_line = [searcher]
    searcher_line.extend(searcher_args[searcher])
    searcher_line.extend(["-r", query, note_dir])

    try:
        b_searcher_output = check_output(searcher_line)

    except CalledProcessError as e:
        if e.returncode == 1:
            print("No tags found.")
            return
        else:
            raise e
    searcher_output = b_searcher_output.encode('utf-8')

    tags = searcher_output.split(newline)[:-2]
    tags = [line.split(tag_marker)[-1].strip() for line in tags]
    tags = [t for t in tags if t.startswith(prefix)]

    return tags


def view_notes(filenames, show_date, show_tags, viewer, verbose):

    if not os.path.isdir(note_dir):
        os.mkdir(note_dir)

    # Sort filenames by modification time
    mod_times = {}
    for filename in filenames:
        mod_time = datetime.datetime.utcfromtimestamp(
            os.path.getmtime(filename))
        mod_times[filename] = mod_time

    filenames.sort(key=lambda f: mod_times[f])

    print("Viewing {n} files.".format(n=len(filenames)))

    if verbose > 0:
        for f in filenames:
            print(f)

    if not os.path.isdir(summary_dir):
        os.mkdir(summary_dir)
    else:
        summary_filenames = [
            os.path.join(summary_dir, f)
            for f in os.listdir(summary_dir)]

        summary_filenames = [
            f for f in summary_filenames if os.path.isfile(f)]

        if len(summary_filenames) > 20:
            for sf in summary_filenames:
                os.remove(sf)

    temp_file_args = {'mode': 'w',
                      'dir': summary_dir,
                      'suffix': ".md",
                      'delete': False}

    try:
        stripped_contents = []
        orig_contents = []

        # Populate the summary file
        with uwriter(NamedTemporaryFile(**temp_file_args)) as outfile:
            date = datetime.date.fromtimestamp(0.0)

            for filename in filenames:
                with io.open(filename, 'r') as f:
                    if show_date:
                        mod_time = mod_times[filename]
                        new_date = mod_time.date()

                        if new_date != date:
                            time_str = new_date.strftime("%Y-%m-%d")
                            outfile.write(date_prefix + str(time_str) + newline)

                            date = new_date

                    outfile.write(delim)
                    outfile.write(newline)

                    contents = f.read()

                    if not show_tags:
                        contents = contents.partition(tag_marker)
                        stripped_contents.append(contents[1] + contents[2])
                        contents = contents[0]
                    else:
                        stripped_contents.append("")

                    contents = contents.strip()
                    orig_contents.append(contents)
                    outfile.write(contents)

                    outfile.write(newline + newline)

        outfile_mod_time = time.gmtime(os.path.getmtime(outfile.name))
        call([viewer, outfile.name])
        new_outfile_mod_time = time.gmtime(os.path.getmtime(outfile.name))

        n_writes = 0

        # Write edits
        if new_outfile_mod_time > outfile_mod_time:
            with io.open(outfile.name, 'r') as results:
                text = results.read()

                new_contents = [o.split(newline) for o in text.split(delim)[1:]]
                new_contents = [
                    [n for n in nc if not n.startswith(date_prefix)]
                    for nc in new_contents]
                new_contents = [newline.join(nc).strip() for nc in new_contents]

                lists = zip(
                    orig_contents, new_contents, filenames, stripped_contents)
                for orig, new, filename, stripped in lists:
                    if new != orig:
                        if verbose > 0:
                            print("Writing to " + filename + ".")

                        atime = os.path.getatime(filename)
                        mtime = os.path.getmtime(filename)

                        with io.open(filename, 'w') as f:
                            f.write(new)
                            f.write(stripped)

                        os.utime(filename, (atime, mtime))
                        n_writes += 1

        print("Wrote to {n} files.".format(n=n_writes))

    finally:
        try:
            os.remove(outfile.name)
        except:
            pass


def make_note(name, tags, verbose):
    date_time_string = str(datetime.datetime.now()).split('.')[0]
    for c in [":", ".", " ", "-"]:
        date_time_string = date_time_string.replace(c, '_')

    if name is None:
        name = '_'.join(tags)

    filename = note_dir + "/" + name + "_" + date_time_string + ".md"
    call(['vim', filename])

    with io.open(filename, 'a') as f:
        f.write(newline)

        for tag in tags:
            f.write(tag_marker + tag + newline)

    if verbose > 0:
        print("Saved as {filename}".format(filename=filename))


def search_view(args):
    # Get the files to compose the summary file from by searching.
    command = '%s -R -l %s %s' % (searcher, args.pattern, note_dir)
    try:
        b_searcher_output = check_output(command.split())

    except CalledProcessError as e:
        if e.returncode == 1:
            print("No matching files found.")
            return
        else:
            raise e
    searcher_output = b_searcher_output.decode('utf-8')

    filenames = searcher_output.split(newline)[:-1]
    if not filenames:
        print("No matching files found.")
        return

    # View the chosen files
    view_notes(
        filenames, show_date=not args.no_date,
        show_tags=args.show_tags, viewer=args.viewer,
        verbose=args.verbose)


def date_view(args):
    # Get the files to compose the summary file from using a date range.
    command = [
        'find', note_dir, '-type', 'f',
        '-newermt', args.frm, '-not', '-newermt', args.to]

    try:
        b_find_output = check_output(command)

    except CalledProcessError as e:
        if e.returncode == 1:
            print("No matching files found.")
            return
        else:
            raise e
    find_output = b_find_output.decode('utf-8')

    filenames = find_output.split(newline)[:-1]
    if not filenames:
        print("No matching files found.")
        return

    # View the chosen files
    view_notes(
        filenames, show_date=not args.no_date,
        show_tags=args.show_tags, viewer=args.viewer,
        verbose=args.verbose)


def tail_view(args):
    # Get the files to compose the summary file from
    command = 'ls -t1 %s' % note_dir

    try:
        b_sorted_filenames = check_output(command.split())
    except CalledProcessError as e:
        if e.returncode == 1:
            print("No matching files found.")
            return
        else:
            raise e
    sorted_filenames = b_sorted_filenames.decode('utf-8')

    filenames = sorted_filenames.split(newline)[:-1]
    filenames = filenames[:args.n]
    filenames = [os.path.join(note_dir, fn) for fn in filenames]
    if not filenames:
        print("No matching files found.")
        return

    # View the chosen files
    view_notes(
        filenames, show_date=not args.no_date,
        show_tags=args.show_tags, viewer=args.viewer,
        verbose=args.verbose)


def view_note_cl():
    parser = argparse.ArgumentParser(
        description='View and edit notes. The default value for '
                    'the positional argument is \'search\'. If a value '
                    'for this argument is explicitly supplied, then the '
                    'top-level optional arguments must come before it. If '
                    'a value is not explicitly supplied, then top-level '
                    'optional arguments cannot be supplied.'
                    'Type \'viewnote <command> -h\' to see arguments specific '
                    'to that command.')

    parser.add_argument(
        '--show-tags', action='store_true', help="Supply to show tags.")
    parser.add_argument(
        '--viewer', default='vim',
        help="The program used to view search results. Defaults to: vim.")
    parser.add_argument(
        '--no-date', default=False, action='store_true',
        help="Supply to hide dates.")
    parser.add_argument(
        '-v', '--verbose', action='count', default=0, help="Increase verbosity.")

    subparsers = parser.add_subparsers()

    search_parser = subparsers.add_parser(
        'search', help='View notes whose contents match the given pattern.')
    arg = search_parser.add_argument('pattern', type=str)
    search_parser.set_defaults(func=search_view)

    date_parser = subparsers.add_parser(
        'date', help='View notes whose most recent modification '
                     'time matches the given range of dates. Dates '
                     'are interpreted in the same manner as the `-d` '
                     'option of GNU `date`.')
    date_parser.add_argument(
        '--from', dest='frm', type=str, default='@0',
        help='Start of the date range.')
    date_parser.add_argument(
        '--to', type=str, default='now', help='End of date range.')
    date_parser.set_defaults(func=date_view)

    tail_parser = subparsers.add_parser(
        'tail', help='View most recent ``n`` notes.')
    tail_parser.add_argument('n', nargs='?', type=int, default=1)
    tail_parser.set_defaults(func=tail_view)

    parser.set_default_subparser('search')

    args = parser.parse_args()
    args.func(args)


def make_note_cl():
    parser = argparse.ArgumentParser(description='Make a note.')

    parser.add_argument(
        '--name', type=str, help="Name of the note.")
    parser.add_argument( '--verbose', '-v', action='count', help="Increase verbosity.")
    arg = parser.add_argument('tags', nargs='*', help="Tags for the note.")
    args = parser.parse_args()

    tags = args.tags or []
    make_note(args.name, tags, args.verbose)

if __name__ == "__main__":

    # Calling these makes argcomplete work.
    make_note_cl()
    view_note_cl()
