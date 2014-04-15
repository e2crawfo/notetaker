import os, time
import tempfile
import argparse
from subprocess import check_output, call

note_dir = '/home/e2crawfo/Dropbox/notes/'
delim = '%NOTE%'

def view_notes(query, write_time=True, tags_only=False):
    output = check_output(["grep", "-R", "-l", query, note_dir])

    filenames = output.split('\n')[:-1]

    with tempfile.NamedTemporaryFile(suffix='.md') as outfile:

        for filename in filenames:
            with open(filename, 'r') as f:
                outfile.write(delim + " ")
                if write_time:
                    mod_time = time.ctime(os.path.getmtime(filename))
                    outfile.write(str(mod_time))

                outfile.write('\n\n')

                outfile.write(f.read())

                outfile.write('\n')

        outfile.seek(0)

        call(['vim', outfile.name])

        text = outfile.read()

        new_contents = [o.split('\n')[2:-1] for o in text.split(delim)[1:]]
        new_contents = ['\n'.join(nc) for nc in new_contents]

        for contents, filename in zip(new_contents, filenames):
            with open(filename, 'w') as f:
                f.write(contents)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Search and edit notes.')
    parser.add_argument('pattern', nargs='*', help="Pattern to search for.")
    argvals = parser.parse_args()

    view_notes(argvals.pattern[0])
