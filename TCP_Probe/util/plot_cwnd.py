from helper import *
from collections import defaultdict
import argparse

def first(lst):
    return map(lambda e: e[0], lst)

def second(lst):
    return map(lambda e: e[1], lst)

"""
Sample line:
2.221032535 10.0.0.2:39815 10.0.0.1:5001 32 0x1a2a710c 0x1a2a387c 11 2147483647 14592 85
"""
def parse_file(f):
    times = defaultdict(list)
    cwnd = defaultdict(list)
    srtt = []
    for l in open(f).xreadlines():
        fields = l.strip().split(' ')
        if len(fields) != 10:
            break
        if fields[2].split(':')[1] != args.port:
            continue
        sport = int(fields[1].split(':')[1])
        times[sport].append(float(fields[0]))

        c = int(fields[6])
        cwnd[sport].append(c)
        srtt.append(int(fields[-1]))
    return times, cwnd

def plot_cwnd(f, ax):
    events = []
    times, cwnds = parse_file(f)
    for port in sorted(cwnds.keys()):
        events.extend((t, port, cwnd)
                      for t, cwnd in zip(times[port], cwnds[port]))
    events.sort()
    ts, cwnds = [], []
    last = defaultdict(int)
    for t, p, cwnd in events:
        last[p] = cwnd
        ts.append(t)
        cwnds.append(sum(last.values()))
    ax.plot(ts, cwnds, label=basename(f))        

parser = argparse.ArgumentParser()
parser.add_argument('-p', '--port', dest="port", default='5001')
parser.add_argument('-f', dest="files", nargs='+', required=True)
parser.add_argument('-o', '--out', dest="out", required=True)
args = parser.parse_args()

if __name__ == '__main__':
    m.rc('figure', figsize=(16, 6))
    fig = plt.figure()
    ax = fig.add_subplot(1, 1, 1)
    ax.set_xlabel("seconds")
    ax.set_ylabel("cwnd packets")
    ax.set_title("TCP congestion window (cwnd) timeseries")
    for f in args.files:
        plot_cwnd(f, ax)
    ax.legend()

    print 'saving to', args.out
    plt.savefig(args.out)
