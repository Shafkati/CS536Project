from helper import *
from collections import defaultdict

# Create a parser and add arguments
parser = argparse.ArgumentParser()
parser.add_argument('--files', '-f',
                    help="Rate timeseries output to one plot",
                    required=True,
                    action="store",
                    nargs='+',
                    dest="files")

parser.add_argument('--legend', '-l',
                    help="Legend to use if there are multiple plots.  File names used as default.",
                    action="store",
                    nargs="+",
                    default=None,
                    dest="legend")

parser.add_argument('--out', '-o',
                    help="Output png file for the plot.",
                    default=None, # Will show the plot
                    dest="out")
parser.add_argument('--bwout',
                    help="Output png file for the avg bw plot.",
                    default='avg_bw.png', # Will show the plot
                    dest="bwout")

parser.add_argument('-s', '--summarise',
                    help="Summarise the time series plot (boxplot).  First 10 and last 10 values are ignored.",
                    default=False,
                    dest="summarise",
                    action="store_true")

parser.add_argument('--labels',
                    help="Labels for x-axis if summarising; defaults to file names",
                    required=False,
                    default=[],
                    nargs="+",
                    dest="labels")

parser.add_argument('--xlabel',
                    help="Custom label for x-axis",
                    required=False,
                    default=None,
                    dest="xlabel")

parser.add_argument('--ylabel',
                    help="Custom label for y-axis",
                    required=False,
                    default=None,
                    dest="ylabel")

parser.add_argument('-i',
                    help="Interfaces to plot (regex)",
                    default=".*",
                    dest="pat_iface")

parser.add_argument('--rx',
                    help="Plot receive rates on the interfaces.",
                    default=False,
                    action="store_true",
                    dest="rx")

parser.add_argument('--maxy',
                    help="Max mbps on y-axis..",
                    default=100,
                    action="store",
                    dest="maxy")

parser.add_argument('--n',
                    help="Number of senders on more hop",
                    default=2,
                    action="store",
                    dest="n")

parser.add_argument('--maxx',
                    help="Max sec on x-axis..",
                    default=60,
                    action="store",
                    dest="maxx")

parser.add_argument('--metric',
                    help="Metric for chart spacing.",
                    default='avg',
                    action="store",
                    dest="metric")

parser.add_argument('--miny',
                    help="Min mbps on y-axis..",
                    default=0,
                    action="store",
                    dest="miny")

parser.add_argument('--normalize',
                    help="normalise y-axis",
                    default=False,
                    action="store_true",
                    dest="normalise")

args = parser.parse_args()
print(args)
if args.labels is None:
    args.labels = args.files

pat_iface = re.compile(args.pat_iface)

to_plot=[]
# avg_bw[flow - 0/1, 0: s1-eth1][(curr-start)/10] = list of all the bw/s in
# this time interval
avg_bw = [[[] for x in range(7)] for y in range(2)]


"""Output of bwm-ng csv has the following columns: https://github.com/vgropp/bwm-ng
timestamp;iface_name;bytes_out/s;bytes_in/s;bytes_total/s;bytes_in;bytes_out;packets_out/s;packets_in/s;packets_total/s;packets_in;...
"""

if args.normalise and args.labels == []:
    raise "Labels required if summarising/normalising."
    sys.exit(-1)

bw = list(map(lambda e: int(e.replace('M','')), args.labels))
idx = 0

start_time = 0
offset = 0
offset_diff = 10

def offset_data(data):
    return [x + offset for x in data] + [offset]

'''
Parses the file 'f' and populates the 'rate' map
'''

for f in args.files:
    data = read_list(f)
    rate = defaultdict(list)

    # Changed from 2, 3 to 5, 6
    column = 5 if args.rx else 6
    for row in data:
        row = list(row)
        try:
            ifname = row[1]
        except:
            break

        if start_time == 0:
            start_time = float(row[0])
        if ifname not in ['eth0', 'lo']:
            if ifname not in rate:
                rate[ifname] = []
            try:
                rate[ifname].append(float(row[column]) * 8.0 / (1 << 20))
            except:
                break
            # store the b/w for avg throughput calculation
            if ifname.strip() == 's1-eth1':
                time_offset = float(row[0]) - float(start_time)
                avg_bw[0][int(time_offset//10)].append(float(row[column]) * 8.0 / (1 << 20))
            else:
                time_offset = float(row[0]) - float(start_time)
                avg_bw[1][int(time_offset//10)].append(float(row[column]) * 8.0 / (1 << 20))

    metric = avg
    if args.metric == 'max':
        metric = lambda l: max(l) / 2

    offset_diff = int(metric([metric(row) for key, row in rate.items() if pat_iface.match(key)]) * 1.5) + 1
        
    if args.summarise:
        for k in rate.keys():
            if pat_iface.match(k):
                print(k)
                vals = filter(lambda e: e < 1500, rate[k][10:-10])
                if args.normalise:
                    vals = list(map(lambda e: e / bw[idx], vals))
                    
                    idx += 1
                to_plot.append(vals)
    else:
        # The length of rate[key] is time + 1 (time is defined in the outcast-)
        for k in sorted(rate.keys()):
            if pat_iface.match(k):
                plt.fill(offset_data(rate[k]), label=k, zorder=-1 * offset)
                offset += offset_diff

plt.title("TX rates")
if args.rx:
    plt.title("RX rates")

if args.ylabel:
    plt.ylabel(args.ylabel)
elif args.normalise:
    plt.ylabel("Normalized BW")
else:
    plt.ylabel("Mbps")

plt.grid()

maxy = max([int(args.maxy), offset + offset_diff])
plt.ylim((int(args.miny), int(maxy)))
maxx = int(args.maxx)
plt.xlim((0, maxx))
ax = plt.subplot(111)
box = ax.get_position()
ax.set_position([box.x0, box.y0,
                 box.width * 0.8, box.height])
handles, labels = ax.get_legend_handles_labels()
ax.legend(handles[::-1], labels[::-1], loc="upper left", bbox_to_anchor=(1,1))

if args.summarise:
    plt.boxplot(to_plot)
    plt.xticks(range(1, 1+len(args.files)), args.labels)

if not args.summarise:
    if args.xlabel:
        plt.xlabel(args.xlabel)
    else:
        plt.xlabel("Time")
    if args.legend:
        plt.legend(args.legend, loc="upper left", bbox_to_anchor=(1,1))

if args.out:
    plt.savefig(args.out)
else:
    plt.show()


# plot the avg bandwidth
plt.clf()

# get the mean of all the entries
fig = plt.figure(figsize = (10, 5))
barWidth = 1.75
x_other = [0, 10, 20, 30, 40, 50]
x_h1 = [x + barWidth for x in x_other]
other_bw = [0.0 if len(x) == 0 else (sum(x)/len(x)) for x in avg_bw[1]]
h1_bw = [0.0 if len(x) == 0 else (sum(x)/len(x)) for x in avg_bw[0]]
print(other_bw)
print(h1_bw)
# the last index is for the 60th second, that has sometimes erroneous figures
plt.bar(x_other, other_bw[:-1], color ='r', width = barWidth, edgecolor ='grey', label ='3 hop flow')
plt.bar(x_h1, h1_bw[:-1], color ='b', width = barWidth, edgecolor ='grey', label ='2 hop flow')
plt.xlabel('Time', fontweight ='bold', fontsize = 15)
plt.ylabel('Avg Throughput(mbps)', fontweight ='bold', fontsize = 15)
plt.title('Avg Throughput with  3-Hop flows & 1 2-Hop flow.')
plt.xticks(x_other)
plt.legend()
plt.savefig(args.bwout)
