
from subprocess import call
import datetime
import argparse
import string

note_dir = '/home/e2crawfo/Dropbox/notes/'
tag_marker = '%tag%'

def make_note(name, tags):
    date_time_string = str(datetime.datetime.now()).split('.')[0]
    date_time_string = reduce(lambda y,z: string.replace(y,z,"_"), [date_time_string,":","."," ","-"])

    filename = note_dir + "/" + name + "_" + date_time_string + ".md"
    call(['vim', filename])

    with open(filename, 'a') as f:
        f.write('\n')

        if tags:
            for tag in tags:
                f.write(tag_marker + tag + '\n')

def main():
    parser = argparse.ArgumentParser(description='Make a note.')
    parser.add_argument('name', nargs='?', default="", help="Name of the note.")
    parser.add_argument('-t', nargs='*', help="Tags for the note.")

    argvals = parser.parse_args()

    make_note(argvals.name, argvals.t)

if __name__ == "__main__":
    main()
