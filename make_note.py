
from subprocess import call
import datetime

note_dir = '/home/e2crawfo/Dropbox/notes/'

def make_note(name):
    date_time_string = str(datetime.datetime.now()).split('.')[0]
    date_time_string = reduce(lambda y,z: string.replace(y,z,"_"), [date_time_string,":","."," ","-"])
    call(['vim', note_dir + "/" + name + "_" + date_time_string + ".md"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Make a note.')
    parser.add_argument('name', nargs='*', help="Name of the note.")
    argvals = parser.parse_args()

    view_notes(argvals.pattern[0])