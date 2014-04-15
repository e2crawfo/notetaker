import os, time
import tempfile
import argparse
from subprocess import check_output, call, CalledProcessError

note_dir = '/home/e2crawfo/Dropbox/notes/'
delim = '%Note'
tag_marker='%tag%'

def view_notes(query, tags_only, show_date, show_tags):

    if query is None:
        # Show all files in note_dir
        (_, _, filenames) = os.walk(note_dir).next()
        filenames = [os.path.join(note_dir, fn) for fn in filenames]

    else:
        if tags_only:
            query = tag_marker + query

        try:
            grep_output = check_output(["grep", "-R", "-l", query, note_dir])
        except CalledProcessError as e:
            if e.returncode == 1:
                print "No matching files found."
                return
            else:
                raise e

        filenames = grep_output.split('\n')[:-1]

    stripped_contents = []
    orig_contents = []

    # Sort filenames by modification time
    mod_times = {}
    for filename in filenames:
        mod_time = time.gmtime(os.path.getmtime(filename))
        mod_times[filename] = mod_time

    filenames.sort(key=lambda f: mod_times[f])


    with tempfile.NamedTemporaryFile(suffix='.md') as outfile:

        # Populate the summary file
        for filename in filenames:
            with open(filename, 'r') as f:
                outfile.write('*')
                outfile.write(delim)
                if show_date:
                    mod_time = mod_times[filename]
                    time_str = time.strftime("%Y-%m-%d %H:%M:%S", mod_time)
                    outfile.write(" " + str(time_str))
                outfile.write('*')

                outfile.write('\n\n')

                contents = f.read()

                if not show_tags:
                    contents = contents.partition(tag_marker)
                    stripped_contents.append(contents[1] + contents[2])
                    contents = contents[0]
                else:
                    stripped_contents.append("")

                orig_contents.append(contents)
                outfile.write(contents)

                outfile.write('\n\n')


        # Display and edit summary file
        outfile.seek(0)

        try:
            call(['retext', outfile.name])
        except:
            call(['vim', outfile.name])

        # Write edits
        text = outfile.read()

        new_contents = [o.split('\n')[2:-2] for o in text.split(delim)[1:]]
        new_contents = ['\n'.join(nc) for nc in new_contents]
        lists = zip(orig_contents, new_contents, filenames, stripped_contents)

        for orig, new, filename, stripped in lists:
            if new != orig:
                print "Writing to ", filename
                with open(filename, 'w') as f:
                    f.write(new)
                    f.write(stripped)


def main():
    parser = argparse.ArgumentParser(description='Search and edit notes.')
    parser.add_argument('pattern', nargs='?', default=None, help="Pattern to search for.")
    parser.add_argument('-t', action='store_true', help="Supply to search only in tags.")
    parser.add_argument('-s', action='store_true', help="Supply to show tags.")
    parser.add_argument('--hd', default=False, action='store_true', help="Supply to hide dates.")
    argvals = parser.parse_args()
    print "Arguments:", argvals

    view_notes(argvals.pattern, tags_only=argvals.t, show_date=not argvals.hd, show_tags=argvals.s)

if __name__ == "__main__":
	main()

