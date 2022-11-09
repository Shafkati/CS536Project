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
    cthroughput = defaultdict(list)
    throughput = defaultdict(int)
    first = True
    start_time = 0
    for l in open(f).xreadlines():
        fields = l.strip().split(' ')
        if len(fields) != 10:
            break
        if fields[1].split(':')[1] != args.port:
            continue
        if fields[3] != '596':
            continue
        sport = int(fields[2].split(':')[1])
        time = float(fields[0])
        if first:
            start_time = time
            first = False
        
        time = time - start_time

        if time >= args.max_time:
            break

        times[sport].append(time)
        cur = throughput[sport] + 1
        throughput[sport] = cur
        if (time == 0):
            ct = 0
        else:
            ct = cur / time
        cthroughput[sport].append(ct)
        c = int(fields[6])
    return times, cthroughput

def compute_fairness(events):
    recent_ct = defaultdict(float)
    times = []
    fairness = []

    for (t,p,c) in events:
        times.append(t)
        recent_ct[p] = c
        f = sum(recent_ct.values())
        f *= f
        f /= len(recent_ct.keys())
        if (f == 0):
            f = 1
        else:
            f /= sum(x * x for x in recent_ct.values())
        fairness.append(f)

    return times, fairness

def plot_fairness(f, ax):
    events = []
    nb_ports = 0

    times, cthroughput = parse_file(f)
    nb_ports = len(cthroughput.keys())
    for port in sorted(cthroughput.keys()):
        t = times[port]
        ct = cthroughput[port]
        events += zip(t, [port]*len(t), ct)

    events.sort()
    times, fairness = compute_fairness(events)
    ax.plot(times, fairness, lw=2, label=basename(f))

parser = argparse.ArgumentParser()
parser.add_argument('-p', '--port', dest="port", default='5001')
parser.add_argument('-f', dest="files", nargs='+', required=True)
parser.add_argument('-o', '--out', dest="out", required=True)
parser.add_argument('-t', '--max_time', dest="max_time", type=float,
                    default=10.0)
args = parser.parse_args()

if __name__ == '__main__':
    m.rc('figure', figsize=(16, 6))
    fig = plt.figure()
    ax = fig.add_subplot(1, 1, 1)

    for f in args.files:
        plot_fairness(f, ax)

    ax.grid(True)

    ax.set_xlabel("seconds")
    ax.set_ylabel("cumulative fairness ratio")
    ax.set_title("Fairness with Respect to Cumulative Throughput")
    ax.legend()
    ax.set_ylim(0, 1.2)

    print 'saving to', args.out
    plt.savefig(args.out)

