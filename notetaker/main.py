from __future__ import print_function
import os
import sys
import codecs
import datetime
from tempfile import NamedTemporaryFile
import argparse
from subprocess import check_output, call, Popen, TimeoutExpired, CalledProcessError
import pkg_resources
from configparser import ConfigParser
from six import StringIO, u
from pathlib import Path
from contextlib import contextmanager
import traceback
import pdb
from collections import namedtuple, OrderedDict
import difflib

ENCODING = u('utf-8')
NEWLINE = u('\n')
DATE_PREFIX = u("# Journal --- ")
NOTE_HEADER = u("# Note ---")


config_string = pkg_resources.resource_string(__name__, 'config.ini')
config_io = StringIO(config_string.decode(ENCODING))

config_parser = ConfigParser()
config_parser.read_file(config_io)

note_dir = Path(config_parser.get('common', 'note_directory'))
summary_dir = Path(config_parser.get('common', 'summary_directory'))
merge_dir = Path(config_parser.get('common', 'merge_directory'))
tag_marker = config_parser.get('common', 'tag_marker')
propagate_changes_interval = config_parser.getint('common', 'propagate_changes_interval')

# searcher can be any of: grep, ag, ack-grep
searcher = config_parser.get('common', 'searcher')

_searcher_args = {'grep': [], 'ack-grep': ['--nobreak']}
_searcher_args['ack'] = _searcher_args['ack-grep']
_searcher_args['ag'] = _searcher_args['ack-grep']
searcher_args = _searcher_args[searcher]

cfg = dict(
    note_dir=note_dir,
    summary_dir=summary_dir,
    merge_dir=merge_dir,
    tag_marker=tag_marker,
    propagate_changes_interval=propagate_changes_interval,
    searcher=searcher,
    searcher_args=searcher_args
)


if sys.version_info[0] > 2:
    def uwriter(fp):
        return fp
else:
    def uwriter(fp):
        return codecs.getwriter(ENCODING)(fp)


@contextmanager
def pdb_postmortem():
    try:
        yield
    except Exception:
        type, value, tb = sys.exc_info()
        traceback.print_exc()
        pdb.post_mortem(tb)


def set_default_subparser(self, name, args=None):
    """ Default subparser selection.

    Call after setup, just before parse_args()
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
    """ Find all tags present in the notes folder.

    Parameters
    ----------
    prefix : str, optional
        Only tags that begin with prefix will be returned.

    """
    query = cfg['tag_marker']

    searcher_line = [cfg['searcher']]
    searcher_line.extend(cfg['searcher_args'])
    searcher_line.extend(["-r", query, cfg['note_dir']])

    try:
        b_searcher_output = check_output(searcher_line)

    except CalledProcessError as e:
        if e.returncode == 1:
            print("No tags found.")
            return
        else:
            raise e
    searcher_output = b_searcher_output.encode(ENCODING)

    tags = searcher_output.split(NEWLINE)[:-2]
    tags = [line.split(cfg['tag_marker'])[-1].strip() for line in tags]
    tags = [t for t in tags if t.startswith(prefix)]

    return tags


_Note = namedtuple('_Note', 'path text tags'.split())


class Note(_Note):
    @classmethod
    def from_path(cls, path):
        with path.open('r') as f:
            s = f.read()
            return cls.from_string(path, s)

    @classmethod
    def from_string(cls, path, s):
        text, _, tags = s.partition(tag_marker)
        text = text.strip()

        tags = tag_marker + tags
        tags = tags.split(tag_marker)[1:]
        tags = tuple(t.strip() for t in tags if t)

        return Note(path, text, tags)

    def as_string(self, show_tags=False):
        s = [self.text.strip()] + ['']
        if show_tags:
            s.extend([tag_marker + tag for tag in self.tags] + [''])
        return NEWLINE.join(s)

    def save(self, mode='w'):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open(mode=mode) as f:
            f.write(self.text)
            f.write(NEWLINE)
            for tag in self.tags:
                f.write(tag_marker + tag + NEWLINE)


def mtime(path):
    return path.stat().st_mtime


def atime(path):
    return path.stat().st_atime


def extract_notes_from_summary(notes, summary_file):
    new_summary = Path(summary_file.name).read_text()

    # Remove comments.
    new_summary = new_summary.split(NEWLINE)
    new_summary = [l for l in new_summary if not l.startswith(DATE_PREFIX)]
    new_summary = NEWLINE.join(new_summary)

    segments = new_summary.split(NOTE_HEADER)[1:]

    if len(segments) > len(notes):
        raise Exception("Notes were added in the process of editing the summary file.")
    if len(segments) < len(notes):
        raise Exception("Notes were removed in the process of editing the summary file.")

    extracted_notes = type(notes)()

    for (path, note), seg in zip(notes.items(), segments):
        lines = seg.split(NEWLINE)
        lines = lines[1:]
        seg = NEWLINE.join(lines)
        seg = seg.strip()
        if cfg['show_tags']:
            _note = Note.from_string(path, seg)
        else:
            _note = Note(path, seg, note.tags)
        extracted_notes[path] = _note

    return extracted_notes


def propagate_changes(notes, summary_file):
    extracted_notes = extract_notes_from_summary(notes, summary_file)

    for path in notes:
        note = notes[path]
        extracted_note = extracted_notes[path]

        if extracted_note != note:
            # User wrote to the part of the summary file corresponding to ``note``

            note_on_disk = Note.from_path(path)
            if note_on_disk == note:
                # Do not write the edited note to disk if there is a discrepancy between
                # the current note on disk and the note before editing began, as this indicates
                # that the note has been changed by some other means. Once editing is over,
                # edits applied to such a note will be resolved by a merge process.

                _atime, _mtime = atime(path), mtime(path)
                extracted_note.save()
                os.utime(str(path), (_atime, _mtime))

                notes[path] = extracted_note


def perform_diffs(notes, summary_file):
    extracted_notes = extract_notes_from_summary(notes, summary_file)

    for path in notes:
        note = notes[path]
        extracted_note = extracted_notes[path]

        no_change = note == extracted_note

        if no_change:
            continue

        on_disk_note = Note.from_path(path)
        no_interference = on_disk_note == note

        if no_interference:
            continue

        # A merge is necessary

        on_disk_text = on_disk_note.text.splitlines(keepends=True)
        extracted_text = extracted_note.text.splitlines(keepends=True)

        _diff_text = ''.join(difflib.ndiff(on_disk_text, extracted_text))
        diff_text = []
        for line in _diff_text.split('\n'):
            if line.startswith('  '):
                line = line[2:]
            elif any(line.startswith(c) for c in ('? ', '- ', '+ ')):
                line = '&&& ' + line
            elif not line:
                pass
            else:
                raise Exception('NotImplemented')
            diff_text.append(line)
        diff_text = '\n'.join(diff_text)

        new_tags = sorted(set(on_disk_note.tags) | set(extracted_note.tags))
        extracted_note = Note(merge_dir / path.name, diff_text, new_tags)
        extracted_note.save()
        command = "{} {}".format(cfg['viewer'], extracted_note.path).split()
        call(command)
        edited_note = Note.from_path(extracted_note.path)
        edited_note = Note(path, edited_note.text, edited_note.tags)

        _atime, _mtime = atime(path), mtime(path)
        edited_note.save()
        os.utime(str(path), (_atime, _mtime))

        notes[path] = edited_note


def view_notes(paths):
    if not paths:
        print("No matching notes found.")
        return

    if not note_dir.is_dir():
        note_dir.mkdir(parents=True)

    # Sort paths by modification time
    paths = [note_dir / f for f in paths]
    paths = sorted(paths, key=lambda n: mtime(n))

    print("Viewing {n} files.".format(n=len(paths)))
    max_paths = 10
    for p in paths[:max_paths]:
        print(p)
    if len(paths) > max_paths:
        print("...and {} more.".format(len(paths) - max_paths))
    print("")

    if not summary_dir.is_dir():
        summary_dir.mkdir(parents=True)
    else:
        existing_summary_files = [
            summary for summary in summary_dir.iterdir() if summary.is_file()]
        if len(existing_summary_files) > 20:
            for summary in existing_summary_files:
                summary.unlink()

    try:
        # Populate the summary file
        date = datetime.date.fromtimestamp(0.0)
        to_write = []
        original_notes = OrderedDict()
        for path in paths:
            note = Note.from_path(path)
            original_notes[path] = note

            if cfg['show_date']:
                new_date = datetime.datetime.utcfromtimestamp(mtime(path)).date()
                if new_date != date:
                    date_str = new_date.strftime("%Y-%m-%d")
                    to_write.append("{}{}(UTC) {}\n".format(DATE_PREFIX, date_str, "=" * 40))
                    date = new_date

            to_write.append("{} `{}` {}\n".format(NOTE_HEADER, path.name, "-" * 40))
            to_write.append(note.as_string(cfg['show_tags']))

        # Latest version of the notes for which there is (after this function call)
        # agreement between the sumamry file and the on-disk notes.
        notes = original_notes.copy()

        with NamedTemporaryFile(mode='w',
                                dir=str(summary_dir),
                                prefix='notetaker_summary_',
                                suffix='.md',
                                delete=False) as summary_file:
            summary_file.write('\n'.join(to_write))

        summary_path = Path(summary_file.name)

        summary_mod_time = mtime(summary_path)

        command = "{} {}".format(cfg['viewer'], summary_file.name).split()
        editing_process = Popen(command)

        while True:
            finished = True
            try:
                editing_process.wait(propagate_changes_interval)
            except TimeoutExpired:
                finished = False

            new_summary_mod_time = mtime(summary_path)

            if new_summary_mod_time > summary_mod_time:
                summary_mod_time = new_summary_mod_time
                propagate_changes(notes, summary_file)

            if finished:
                break

        perform_diffs(notes, summary_file)

        n_changes = 0
        for path in notes:
            if notes[path] != original_notes[path]:
                print("Changed note {}.".format(path))
                n_changes += 1
        print("Changed {n} note(s).".format(n=n_changes))

    finally:
        try:
            os.remove(summary_file.name)
        except FileNotFoundError:
            pass


def make_note(name, tags):
    date_time_string = str(datetime.datetime.now()).split('.')[0]
    for c in [":", ".", " ", "-"]:
        date_time_string = date_time_string.replace(c, '_')

    name = name or '_'.join(tags)
    note_path = note_dir / "{}_{}.md".format(name, date_time_string)

    call(['vim', str(note_path)])

    try:
        note = Note.from_path(note_path)
        with_tags = Note(note.path, note.text, tags)
        with_tags.save()
        print("Saved as {}".format(note_path))
    except FileNotFoundError:
        print("Note was not written to, so not saved.")


def search_view(args):
    """ Get the files to compose the summary file from by searching. """

    command = [str(s) for s in [searcher, "-R", "-l", args.pattern, note_dir]]

    try:
        b_searcher_output = check_output(command)

    except CalledProcessError as e:
        if e.returncode == 1:
            print("No matching files found.")
            return
        else:
            raise e
    searcher_output = b_searcher_output.decode(ENCODING)
    filenames = searcher_output.split(NEWLINE)[:-1]

    cfg.update(
        show_date=not args.no_date,
        show_tags=args.show_tags,
        viewer=args.viewer,
    )

    view_notes(filenames)


def date_view(args):
    """ Get the files to compose the summary file from using a date range. """

    command = 'find {} -type f -newermt {} -not -newermt {}'.format(note_dir, args.frm, args.to)

    try:
        b_find_output = check_output(command.split())

    except CalledProcessError as e:
        if e.returncode == 1:
            print("No matching files found.")
            return
        else:
            raise e
    find_output = b_find_output.decode(ENCODING)
    filenames = find_output.split(NEWLINE)[:-1]

    cfg.update(
        show_date=not args.no_date,
        show_tags=args.show_tags,
        viewer=args.viewer,
    )

    view_notes(filenames)


def tail_view(args):
    """ Get the files to compose the summary file from. """

    command = 'ls -t1 {}'.format(note_dir)

    try:
        b_sorted_filenames = check_output(command.split())
    except CalledProcessError as e:
        if e.returncode == 1:
            print("No matching files found.")
            return
        else:
            raise e
    sorted_filenames = b_sorted_filenames.decode(ENCODING)

    start = 0 if args.n <= 0 else args.final - args.n

    filenames = sorted_filenames.split(NEWLINE)[:-1]
    filenames = filenames[start:args.final]

    cfg.update(
        show_date=not args.no_date,
        show_tags=args.show_tags,
        viewer=args.viewer,
    )

    view_notes(filenames)


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
        '--pdb', action='store_true', help="If supplied, enter post-mortem debugging on error.")
    parser.add_argument(
        '--show-tags', action='store_true', help="Supply to show tags.")
    parser.add_argument(
        '--viewer', default='vim +/Note\\s---',
        help="The program used to view search results. Defaults to: vim.")
    parser.add_argument(
        '--no-date', default=False, action='store_true',
        help="Supply to hide dates.")

    subparsers = parser.add_subparsers()

    search_parser = subparsers.add_parser(
        'search', help='View notes whose contents match the given pattern.')
    search_parser.add_argument('pattern', type=str)
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
    tail_parser.add_argument('final', nargs='?', type=int, default=1,
                             help="Index of final note to display, counting backwards.")
    tail_parser.add_argument('n', nargs='?', type=int, default=0,
                             help="Number of notes to display, counting forward from final note. "
                                  "If value of 0 is supplied, or argument is not supplied, all notes "
                                  "up to the final note will be displayed.")
    tail_parser.set_defaults(func=tail_view)

    parser.set_default_subparser('search')

    args = parser.parse_args()

    if args.pdb:
        with pdb_postmortem():
            args.func(args)
    else:
        args.func(args)


def make_note_cl():
    parser = argparse.ArgumentParser(description='Make a note.')

    parser.add_argument(
        '--name', type=str, help="Name of the note.")
    parser.add_argument(
        '--pdb', action='store_true', help="If supplied, enter post-mortem debugging on error.")
    parser.add_argument('tags', nargs='*', help="Tags for the note.")
    args = parser.parse_args()

    tags = args.tags or []

    if args.pdb:
        with pdb_postmortem():
            make_note(args.name, tags)
    else:
        make_note(args.name, tags)


if __name__ == "__main__":
    # Calling these makes argcomplete work.
    make_note_cl()
    view_note_cl()
