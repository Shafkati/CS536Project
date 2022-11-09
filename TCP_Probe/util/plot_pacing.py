from helper import *
from collections import defaultdict
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('-p', '--port', dest="port", default='5001')
parser.add_argument('-f', dest="files", nargs='+', required=True)
parser.add_argument('-o', '--out', dest="out", default=None)
args = parser.parse_args()

def first(lst):
    return [e[0] for e in lst]

def second(lst):
    return [e[1] for e in lst]

"""
Sample line:
2.221032535 10.0.0.2:39815 10.0.0.1:5001 32 0x1a2a710c 0x1a2a387c 11 2147483647 14592 85
"""
def parse_file(f):
    times = defaultdict(list)
    cwnd = defaultdict(list)
    srtt = defaultdict(list)
    for l in open(f).xreadlines():
        fields = l.strip().split(' ')
        if len(fields) != 10:
            break
        if fields[2].split(':')[1] != args.port:
            continue
        sport = int(fields[1].split(':')[1])
        times[sport].append(float(fields[0]))
        cwnd[sport].append(int(fields[6]))
        srtt[sport].append(int(fields[-1]))
    return times, cwnd, srtt

added = defaultdict(int)
events = []

def compute_deltas(t):
    return [(t2 - t1) for (t1, t2) in zip(t[:-1], t[1:])]

def compute_rates(t, srtt, cwnd):
    exp_rate, act_rate = [], []
    act_rate = xrange(len(t))
    return exp_rate, act_rate

def plot_snd_rates(fig):
    axRate = fig.add_subplot(4, 1, 1)
    axDelta = fig.add_subplot(4, 1, 2)
    axSrtt = fig.add_subplot(4, 1, 3)
    axCwnd = fig.add_subplot(4, 1, 4)

    for f in args.files:
        times, cwnds, srtt = parse_file(f)
        for port in sorted(cwnds.keys()):
            t = times[port]
            diffs = compute_deltas(t)
            exp_rate, act_rate = compute_rates(t, srtt[port], cwnds[port])

            axDelta.plot(t[1:], diffs)
            axSrtt.plot(t, [s*4 for s in srtt[port]])
            axCwnd.plot(t, cwnds[port])
            #axRate.plot(t, exp_rate)
            axRate.plot(t, act_rate)

    for ax in [axDelta, axSrtt, axCwnd, axRate]:
        ax.set_xlabel("seconds")
        ax.set_ylim(bottom=0)

    axDelta.set_ylim(0, 0.1)
    axDelta.set_ylabel("delta")
    axSrtt.set_ylabel("srtt")
    axCwnd.set_ylabel("cwnd")
    axRate.set_ylabel("packets")

m.rc('figure', figsize=(16, 10))
fig = plt.figure()

plot_snd_rates(fig)


if args.out:
    print 'saving to', args.out
    plt.savefig(args.out)
else:
    plt.show()
