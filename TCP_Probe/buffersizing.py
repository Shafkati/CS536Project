#!/usr/bin/python

"CS244 Assignment 2: Buffer Sizing"

from mininet.topo import Topo
from mininet.node import CPULimitedHost
from mininet.link import TCLink
from mininet.net import Mininet
from mininet.log import lg
from mininet.util import dumpNodeConnections

import subprocess
from subprocess import Popen, PIPE
from time import sleep, time
from multiprocessing import Process
import termcolor as T
from argparse import ArgumentParser

from math import sqrt
import sys
import os
from util.monitor import monitor_qlen
from util.helper import stdev


# Number of samples to skip for reference util calibration.
CALIBRATION_SKIP = 10

# Number of samples to grab for reference util calibration.
CALIBRATION_SAMPLES = 30

# Set the fraction of the link utilization that the measurement must exceed
# to be considered as having enough buffering.
TARGET_UTIL_FRACTION = 0.98

# Fraction of input bandwidth required to begin the experiment.
# At exactly 100%, the experiment may take awhile to start, or never start,
# because it effectively requires waiting for a measurement or link speed
# limiting error.
START_BW_FRACTION = 0.9

# Number of samples to take in get_rates() before returning.
NSAMPLES = 3

# Time to wait between samples, in seconds, as a float.
SAMPLE_PERIOD_SEC = 1.0

# Time to wait for first sample, in seconds, as a float.
#SAMPLE_WAIT_SEC = 3.0
# change the value to 5, I thought it was safer
SAMPLE_WAIT_SEC = 5.0


def cprint(s, color, cr=True):
    """Print in color
       s: string to print
       color: color to use"""
    if cr:
        print T.colored(s, color)
    else:
        print T.colored(s, color),


# Parse arguments

parser = ArgumentParser(description="Buffer sizing tests")
parser.add_argument('--bw-host', '-B',
                    dest="bw_host",
                    type=float,
                    action="store",
                    help="Bandwidth of host links",
                    required=True)

parser.add_argument('--bw-net', '-b',
                    dest="bw_net",
                    type=float,
                    action="store",
                    help="Bandwidth of network link",
                    required=True)

parser.add_argument('--delay',
                    dest="delay",
                    type=float,
                    help="Delay in milliseconds of host links",
                    default=87)

parser.add_argument('--dir', '-d',
                    dest="dir",
                    action="store",
                    help="Directory to store outputs",
                    default="results",
                    required=True)

parser.add_argument('-n',
                    dest="n",
                    type=int,
                    action="store",
                    help="Number of nodes in star.  Must be >= 3",
                    required=True)

parser.add_argument('--nflows',
                    dest="nflows",
                    action="store",
                    type=int,
                    help="Number of flows per host (for TCP)",
                    required=True)

parser.add_argument('--maxq',
                    dest="maxq",
                    action="store",
                    help="Max buffer size of network interface in packets",
                    default=1000)

parser.add_argument('--cong',
                    dest="cong",
                    help="Congestion control algorithm to use",
                    default="bic")

parser.add_argument('--target',
                    dest="target",
                    help="Target utilisation",
                    type=float,
                    default=TARGET_UTIL_FRACTION)

parser.add_argument('--iperf',
                    dest="iperf",
                    help="Path to custom iperf",
                    required=True)
                    
parser.add_argument('--fast',
                    action="store_true",
                    help="Increase the speed of the experiment, using less conservative values")
                    
parser.add_argument('--acc',
                    action="store_true",
                    help="Increase the accuracy for small number of flows")

parser.add_argument('--mod',
                    action="store_true",
                    help="Enable TCP Pacing")

# Expt parameters
args = parser.parse_args()

CUSTOM_IPERF_PATH = args.iperf
assert(os.path.exists(CUSTOM_IPERF_PATH))

if not os.path.exists(args.dir):
    os.makedirs(args.dir)

lg.setLogLevel('info')

hosts = []

# Topology to be instantiated in Mininet
class StarTopo(Topo):
    "Star topology for Buffer Sizing experiment"

    def __init__(self, n=3, cpu=None, bw_host=None, bw_net=None,
                 delay=None, maxq=None):
        # Add default members to class.
        super(StarTopo, self ).__init__()
        self.n = n
        self.cpu = cpu
        self.bw_host = bw_host
        self.bw_net = bw_net
        self.delay = delay
        self.maxq = maxq
        self.create_topology()

    def create_topology(self):
        # the server
        server = self.addHost('server')
        
        # the switch connecting them
        switch = self.addSwitch('s0')
        
        # switch-server link
        maxq = int((2 * args.delay * self.bw_net) / 0.012)
        self.addLink(switch, server,
	           bw=self.bw_net, delay=0, loss=0, max_queue_size=maxq)
        
        # the hosts, linked to the switch
        for h in xrange(self.n - 1):
            host = self.addHost('h%d' % h)
            self.addLink(host, switch,
                bw=self.bw_host, delay=self.delay, loss=0, max_queue_size=10000)

def start_tcpprobe():
    "Install tcp_probe module and dump to file"
    os.system("rmmod tcp_probe 2>/dev/null; modprobe tcp_probe;")
    Popen("cat /proc/net/tcpprobe > %s/tcp_probe.txt" %
          args.dir, shell=True)

def stop_tcpprobe():
    os.system("killall -9 cat; rmmod tcp_probe &>/dev/null;")

def count_connections():
    "Count current connections in iperf output file"
    out = args.dir + "/iperf_server.txt"
    lines = Popen("grep connected %s | wc -l" % out,
                  shell=True, stdout=PIPE).communicate()[0]
    return int(lines)

def set_q(iface, q):
    "Change queue size limit of interface"
    cmd = ("tc qdisc change dev %s parent 1:1 "
           "handle 10: netem limit %s" % (iface, q))
    #os.system(cmd)
    subprocess.check_output(cmd, shell=True)

def set_speed(iface, spd):
    "Change htb maximum rate for interface"
    cmd = ("tc class change dev %s parent 1:0 classid 1:1 "
           "htb rate %s burst 15k" % (iface, spd))
    os.system(cmd)

def get_txbytes(iface):
    f = open('/proc/net/dev', 'r')
    lines = f.readlines()
    for line in lines:
        if iface in line:
            break
    f.close()
    if not line:
        raise Exception("could not find iface %s in /proc/net/dev:%s" %
                        (iface, lines))

    # Extract TX bytes from:
    #Inter-|   Receive                                                |  Transmit
    # face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    # lo: 6175728   53444    0    0    0     0          0         0  6175728   53444    0    0    0     0       0          0
    return float(line.split()[9])

def get_rates(iface, nsamples=NSAMPLES, period=SAMPLE_PERIOD_SEC,
              wait=SAMPLE_WAIT_SEC):
    """Returns the interface @iface's current utilization in Mb/s.  It
    returns @nsamples samples, and each sample is the average
    utilization measured over @period time.  Before measuring it waits
    for @wait seconds to 'warm up'."""
    # Returning nsamples requires one extra to start the timer.
    nsamples += 1
    last_time = 0
    last_txbytes = 0
    ret = []
    sleep(wait)
    while nsamples:
        nsamples -= 1
        txbytes = get_txbytes(iface)
        now = time()
        elapsed = now - last_time
        #if last_time:
        #    print "elapsed: %0.4f" % (now - last_time)
        last_time = now
        # Get rate in Mbps; correct for elapsed time.
        rate = (txbytes - last_txbytes) * 8.0 / 1e6 / elapsed
        if last_txbytes != 0:
            # Wait for 1 second sample
            ret.append(rate)
        last_txbytes = txbytes
        print '.',
        sys.stdout.flush()
        sleep(period)
    return ret

def avg(s):
    "Compute average of list or string of values"
    if ',' in s:
        lst = [float(f) for f in s.split(',')]
    elif type(s) == str:
        lst = [float(s)]
    elif type(s) == list:
        lst = s
    return sum(lst)/len(lst)

def median(l):
    "Compute median from an unsorted list of values"
    s = sorted(l)
    if len(s) % 2 == 1:
        return s[(len(l) + 1) / 2 - 1]
    else:
        lower = s[len(l) / 2 - 1]
        upper = s[len(l) / 2]
        return float(lower + upper) / 2

def format_floats(lst):
    "Format list of floats to three decimal places"
    return ', '.join(['%.3f' % f for f in lst])

def ok(fraction):
    "Fraction is OK if it is >= args.target"
    return fraction >= args.target

def format_fraction(fraction):
    "Format and colorize fraction"
    if ok(fraction):
        return T.colored('%.3f' % fraction, 'green')
    return T.colored('%.3f' % fraction, 'red', attrs=["bold"])

def do_sweep(iface):
    """Sweep queue length until we hit target utilization.
       We assume a monotonic relationship and use a binary
       search to find a value that yields the desired result"""
    bdp = args.bw_net * 2 * args.delay * 1000.0 / 8.0 / 1500.0
    nflows = args.nflows * (args.n - 1)
    if(nflows == 0):
        nflows = 1
    
    # if we just want to generate a graph fast, then we can anticipate...
    if(args.fast):
        bdp = bdp / sqrt(nflows)
    
    min_q, max_q = 1, int(bdp)

    # Set a higher speed on the bottleneck link in the beginning so
    # flows quickly connect
    set_speed(iface, "2Gbit")

    succeeded = 0
    wait_time = 300
    while wait_time > 0 and succeeded != nflows:
        wait_time -= 1
        succeeded = count_connections()
        print 'Connections %d/%d succeeded\r' % (succeeded, nflows),
        sys.stdout.flush()
        sleep(1)

    monitor = Process(target=monitor_qlen,
                      args=(iface, 0.01, '%s/qlen_%s.txt' %
                            (args.dir, iface)))
    monitor.start()

    if succeeded != nflows:
        print 'Giving up'
        return -1

    # Set the speed back to the bottleneck link speed.
    set_speed(iface, "%.2fMbit" % args.bw_net)
    print "\nSetting q=%d " % max_q,
    sys.stdout.flush()
    set_q(iface, max_q)

    # Wait till link is 100% utilised and train
    reference_rate = 0.0
    while reference_rate <= args.bw_net * START_BW_FRACTION:
        rates = get_rates(iface, nsamples=CALIBRATION_SAMPLES+CALIBRATION_SKIP)
        print "measured calibration rates: %s" % rates
        # Ignore first N; need to ramp up to full speed.
        rates = rates[CALIBRATION_SKIP:]
        reference_rate = median(rates)
        ru_max = max(rates)
        ru_stdev = stdev(rates)
        cprint ("Reference rate median: %.3f max: %.3f stdev: %.3f" %
                (reference_rate, ru_max, ru_stdev), 'blue')
        sys.stdout.flush()
        
        
    while abs(min_q - max_q) >= 2:
        mid = (min_q + max_q) / 2
        print "Trying q=%d  [%d,%d] " % (mid, min_q, max_q),
        sys.stdout.flush()

        # Binary search over queue sizes.
        # (1) Check if a queue size of "mid" achieves required utilization
        #     based on the median value of the measured rate samples.
        # (2) Change values of max_q and min_q accordingly
        #     to continue with the binary search
        
        # we use the median and not the average, in case one of the 
        # measurements was biased by noise
        
        set_q(iface, mid)
        if(args.acc and nflows <= 10):
            # see README for details about this particular case
            ls = sorted(get_rates(iface, nsamples=5, period=5))
            medianRate = avg(ls[1:-1])
        else:
            medianRate = median(get_rates(iface))
        if ok(medianRate / reference_rate): #if buffer was big enough
            max_q = mid
        else:
            min_q = mid

    monitor.terminate()
    print "*** Minq for target: %d" % max_q
    return max_q

# do pings from h1 to h2 and evaluates the avg time it takes
def do_ping(net, h1, h2):
    # the most accurate way to do this is to save the output of ping to 
    # a file and parse it when the process is over
    nbTests = 5;
    proc = h1.popen('ping -q -i 0.1 -c %d' % nbTests,  h2.IP(), '>ping.txt', shell=True)
    proc.wait()
    lines = open('ping.txt').readlines()
    avgRtt = lines[-1].split('=')[1].split('/')[1]
    avgRtt = float(avgRtt)
    rtt = args.delay * 2
    diff = abs(avgRtt - rtt)
    if((diff / rtt) > 0.1): #rough verification
        print diff
        raise Exception('Latency check failed')
    return avgRtt
    

# verify the latency settings of the topology
def verify_latency(net):
    print "Verifying latency (avg RTT)..."
    server = net.getNodeByName('server')
    for h in hosts:
        print "%s <-> server: %sms" % (h.name, do_ping(net, h, server))
    cprint("Latency check passed", "green")

# verify the bandwidth settings of the topology
def verify_bandwidth(net, nb = 0):
    print "Verifying bandwidth..."
    s = net.getNodeByName('server')
    hA = hosts[0]
    hB = hosts[1]

    bw_max = args.bw_host * 1000 * 1000
    
    print "Generating TCP traffic using iperf..."
    server = s.popen("iperf -s")
    client = hA.popen("iperf -c %s -t 100" % (s.IP()))
    medRate = median(get_rates('s0-eth1'))
    diff = abs(medRate - args.bw_net)
    if((diff / args.bw_net) > 0.1):
        if(nb > 0):
            raise Exception('Bandwidth check failed')
        else:
            cprint("Bandwidth check failed, second try", "red")
            verify_bandwidth(net, nb = 1)
    print "Host - server bandwidth: %.3fMb/s" % medRate
    client.kill()
    server.kill()
    
    if(not args.fast):
        print "Generating UDP traffic using iperf..."
        server = hB.popen("iperf -u -s")
        client = hA.popen("iperf -u -c %s -b %fg -t 100" % (hB.IP(), args.bw_host))
        medRate = median(get_rates('s0-eth3'))
        client.kill()
        server.kill()
        print "Host - host bandwidth (informational): %.3fMb/s" % medRate
        
    cprint("Bandwidth check passed", "green")
    os.system('killall -9 iperf')


# Start iperf on the receiver node
# Note: The output file should be <args.dir>/iperf_server.txt
#       It will be used later in count_connections()

def start_receiver(net):
    server = net.getNodeByName('server')
    #no need to specify receiver window size?
    server.popen("%s -s -p %s > %s/iperf_server.txt" % (CUSTOM_IPERF_PATH, 5001, args.dir), shell=True)


# Start args.nflows flows across the senders in a round-robin fashion

def start_senders(net):
    # Seconds to run iperf; keep this very high
    seconds = 3600
    server = net.getNodeByName('server')
    flow = 0;
    if(args.nflows == 0):
        #hosts[0].popen("sudo tcpdump -i h0-eth0 -vvv> %s/tcpdump" % (
                #args.dir), shell=True)
        client = hosts[0].popen("%s -c %s -p %s -t %d -i 1 -yc -Z %s" % (
                CUSTOM_IPERF_PATH, server.IP(), 5001, seconds, args.cong))
        return
    for i in xrange(args.nflows):
        for h in hosts:
            # uncomment the following lines if debugging is needed
            #flow += 1
            #output_file = "flow%d" % flow
            #client = h.popen("%s -c %s -p %s -t %d -i 1 -yc -Z %s > %s/%s" % (
                #CUSTOM_IPERF_PATH, server.IP(), 5001, seconds, args.cong, args.dir, output_file), shell=True)
            client = h.popen("%s -c %s -p %s -t %d -i 1 -yc -Z %s" % (
                CUSTOM_IPERF_PATH, server.IP(), 5001, seconds, args.cong))


# this function is called when the user enables fast mode

def do_it_fast():
    cprint("Fast mode enabled", "red")
    global CALIBRATION_SAMPLES
    CALIBRATION_SAMPLES = 10
    global SAMPLE_WAIT_SEC
    SAMPLE_WAIT_SEC = 3.

def main():
    "Create network and run Buffer Sizing experiment"

    if(args.mod):
        os.system("sysctl -w net.ipv4.tcp_pacing=1")
    else:
        os.system("sysctl -w net.ipv4.tcp_pacing=0")

    start = time()
    # Reset to known state
    topo = StarTopo(n=args.n, bw_host=args.bw_host,
                    delay='%sms' % args.delay,
                    bw_net=args.bw_net, maxq=args.maxq)
    net = Mininet(topo=topo, host=CPULimitedHost, link=TCLink)
    net.start()
    dumpNodeConnections(net.hosts)
    net.pingAll()
    
    if(args.fast):
        do_it_fast()

    # fill the hosts list
    for h in xrange(args.n - 1):
        hosts.append(net.getNodeByName('h%d' % h))
    
    # verify letency and bandwidth of mininet topology
    verify_latency(net)
    verify_bandwidth(net)
    
    start_receiver(net)

    #start_tcpprobe()

    cprint("Starting experiment", "green")

    start_senders(net)

    ret = do_sweep(iface='s0-eth1')
    total_flows = (args.n - 1) * args.nflows
    if(total_flows == 0):
        total_flows = 1

    # Store output.  It will be parsed by run.sh after the entire
    # sweep is completed.  Do not change this filename!
    output = "%d %s %.3f\n" % (total_flows, ret, ret * 1500.0)
    open("%s/result.txt" % args.dir, "w").write(output)
    
    os.remove("ping.txt")
    # Shut down iperf processes
    os.system('killall -9 ' + CUSTOM_IPERF_PATH)
    
    net.stop()
    Popen("killall -9 top bwm-ng tcpdump cat mnexec", shell=True).wait()
    #stop_tcpprobe()
    end = time()
    cprint("Sweep took %.3f seconds" % (end - start), "yellow")

if __name__ == '__main__':
    try:
        main()
    except:
        print "-"*80
        print "Caught exception.  Cleaning up..."
        print "-"*80
        import traceback
        traceback.print_exc()
        os.remove("ping.txt")
        os.system("killall -9 top bwm-ng tcpdump cat mnexec iperf; mn -c")

