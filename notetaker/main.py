import os
import time
import datetime
import string
from tempfile import NamedTemporaryFile
import argparse
import argcomplete
from subprocess import check_output, call, CalledProcessError
import ConfigParser
import pkg_resources
import StringIO

config_string = pkg_resources.resource_string(__name__, 'config.ini')
config_io = StringIO.StringIO(config_string)

config_parser = ConfigParser.SafeConfigParser()
config_parser.readfp(config_io)

note_dir = config_parser.get('common', 'note_directory')
search_results_dir = config_parser.get('common', 'search_directory')
delim = config_parser.get('common', 'delimiter')
tag_marker = config_parser.get('common', 'tag_marker')

# searcher can be any of: grep, ag, ack-grep
searcher = config_parser.get('common', 'searcher')

searcher_args = {'grep': [],
                 'ack-grep': ['--nobreak']}
searcher_args['ack'] = searcher_args['ack-grep']
searcher_args['ag'] = searcher_args['ack-grep']


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
        searcher_output = check_output(searcher_line)

    except CalledProcessError as e:
        if e.returncode == 1:
            print "No tags found."
            return
        else:
            raise e

    tags = searcher_output.split('\n')[:-1]
    tags = [line.split(tag_marker)[-1].strip() for line in tags]
    tags = filter(lambda x: x.startswith(prefix), tags)

    return tags


def view_notes(filenames, show_date, show_tags, viewer):

    if not os.path.isdir(note_dir):
        os.mkdir(note_dir)

    # Sort filenames by modification time
    mod_times = {}
    for filename in filenames:
        mod_time = datetime.datetime.utcfromtimestamp(
            os.path.getmtime(filename))
        mod_times[filename] = mod_time

    filenames.sort(key=lambda f: mod_times[f])

    if not os.path.isdir(search_results_dir):
        os.mkdir(search_results_dir)
    else:
        search_filenames = [
            os.path.join(search_results_dir, f)
            for f in os.listdir(search_results_dir)]

        search_filenames = filter(
            lambda f: os.path.isfile(f), search_filenames)

        if len(search_filenames) > 20:
            for sf in search_filenames:
                os.remove(sf)

    temp_file_args = {'dir': search_results_dir,
                      'suffix': ".md",
                      'delete': False}
    date_prefix = "## Journal: "

    try:
        stripped_contents = []
        orig_contents = []

        # Populate the summary file
        with NamedTemporaryFile(**temp_file_args) as outfile:
            date = datetime.date.fromtimestamp(0.0)

            for filename in filenames:
                with open(filename, 'r') as f:
                    if show_date:
                        mod_time = mod_times[filename]
                        new_date = mod_time.date()

                        if new_date != date:
                            time_str = new_date.strftime("%Y-%m-%d")
                            outfile.write(date_prefix + str(time_str) + '\n')

                            date = new_date

                    outfile.write(delim)
                    outfile.write('\n\n')

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

                    outfile.write('\n\n')

        outfile_mod_time = time.gmtime(os.path.getmtime(outfile.name))
        call([viewer, outfile.name])
        new_outfile_mod_time = time.gmtime(os.path.getmtime(outfile.name))

        # Write edits
        if new_outfile_mod_time > outfile_mod_time:
            with open(outfile.name, 'r') as results:
                text = results.read()

                new_contents = [o.split('\n') for o in text.split(delim)[1:]]
                new_contents = [
                    filter(lambda x: not x.startswith(date_prefix), nc)
                    for nc in new_contents]
                new_contents = ['\n'.join(nc).strip() for nc in new_contents]

                lists = zip(
                    orig_contents, new_contents, filenames, stripped_contents)
                for orig, new, filename, stripped in lists:
                    if new != orig:
                        print "Writing to ", filename
                        atime = os.path.getatime(filename)
                        mtime = os.path.getmtime(filename)

                        with open(filename, 'w') as f:
                            f.write(new)
                            f.write(stripped)

                        os.utime(filename, (atime, mtime))
    finally:
        try:
            os.remove(outfile.name)
        except:
            pass


def make_note(name, tags):
    date_time_string = str(datetime.datetime.now()).split('.')[0]
    date_time_string = reduce(
        lambda y, z: string.replace(y, z, "_"),
        [date_time_string, ":", ".", " ", "-"])

    filename = note_dir + "/" + name + "_" + date_time_string + ".md"
    call(['vim', filename])

    with open(filename, 'a') as f:
        f.write('\n')

        for tag in tags:
            f.write(tag_marker + tag + '\n')


def search_view(args):
    # Get the files to compose the summary file from by searching.
    command = '%s -R -l %s %s' % (searcher, args.pattern, note_dir)
    try:
        searcher_output = check_output(command.split())

    except CalledProcessError as e:
        if e.returncode == 1:
            print "No matching files found."
            return
        else:
            raise e
    filenames = searcher_output.split('\n')[:-1]
    if not filenames:
        print "No matching files found."
        return

    # View the chosen files
    view_notes(
        filenames, show_date=not args.no_date,
        show_tags=args.show_tags, viewer=args.viewer)


def date_view(args):
    # Get the files to compose the summary file from using a date range.
    command = [
        'find', note_dir, '-type', 'f',
        '-newermt', args.frm, '-not', '-newermt', args.to]

    try:
        find_output = check_output(command)

    except CalledProcessError as e:
        if e.returncode == 1:
            print "No matching files found."
            return
        else:
            raise e
    filenames = find_output.split('\n')[:-1]
    if not filenames:
        print "No matching files found."
        return

    # View the chosen files
    view_notes(
        filenames, show_date=not args.no_date,
        show_tags=args.show_tags, viewer=args.viewer)


def tail_view(args):
    # Get the files to compose the summary file from
    command = 'ls -t1 %s' % note_dir

    try:
        sorted_filenames = check_output(command.split())
    except CalledProcessError as e:
        if e.returncode == 1:
            print "No matching files found."
            return
        else:
            raise e
    filenames = sorted_filenames.split('\n')[:-1]
    filenames = filenames[:args.n]
    filenames = [os.path.join(note_dir, fn) for fn in filenames]
    if not filenames:
        print "No matching files found."
        return

    # View the chosen files
    view_notes(
        filenames, show_date=not args.no_date,
        show_tags=args.show_tags, viewer=args.viewer)


def view_note_cl():
    parser = argparse.ArgumentParser(description='View and edit notes.')

    subparsers = parser.add_subparsers()

    search_parser = subparsers.add_parser(
        'search', help='View notes whose contents match the given pattern.')
    arg = search_parser.add_argument('pattern', type=str)
    arg.completer = lambda prefix, **kwargs: get_all_tags(prefix)
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

    parser.add_argument(
        '--show-tags', action='store_true', help="Supply to show tags.")
    parser.add_argument(
        '--viewer', default='vim',
        help="The program used to view search results. Defaults to: vim.")
    parser.add_argument(
        '--no-date', default=False, action='store_true',
        help="Supply to hide dates.")

    argcomplete.autocomplete(parser)

    args = parser.parse_args()
    args.func(args)


def make_note_cl():
    parser = argparse.ArgumentParser(description='Make a note.')

    parser.add_argument(
        '--name', type=str, default="", help="Name of the note.")
    arg = parser.add_argument('tags', nargs='*', help="Tags for the note.")
    arg.completer = lambda prefix, **kwargs: get_all_tags(prefix)

    argcomplete.autocomplete(parser)

    argvals = parser.parse_args()

    tags = [] if argvals.tags is None else argvals.tags
    make_note(argvals.name, tags)

if __name__ == "__main__":

    # Calling these makes argcomplete work.
    make_note_cl()
    view_note_cl()
