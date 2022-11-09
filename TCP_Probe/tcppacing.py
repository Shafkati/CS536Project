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
from util.monitor import monitor_qlen, monitor_cumulative_throughput
#from util.helper import stdev

#TCP MSS
ADVMSS = 576

LARGE_QUEUE_VALUE = 10000

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
        print(T.colored(s, color))
    else:
        print(T.colored(s, color))


# Parse arguments

parser = ArgumentParser(description="Buffer sizing tests")
parser.add_argument('--bw-net', '-b',
                    dest="bw_net",
                    type=float,
                    action="store",
                    help="Bandwidth of bottleneck link",
                    default=5)

parser.add_argument('--delay-net',
                    dest="delay_net",
                    type=float,
                    help="Delay in milliseconds of net link",
                    default=40)

parser.add_argument('--delay-host',
                    dest="delay_host",
                    type=float,
                    help="Delay in milliseconds of host links",
                    default=5)

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
                    help="Number of sender-receiver pairs",
                    default=1)

parser.add_argument('--nflows',
                    dest="nflows",
                    action="store",
                    type=int,
                    help="Number of flows per sender-receiver pair",
                    default=1)

parser.add_argument('--maxq',
                    dest="maxq",
                    type=int,
                    action="store",
                    help="Max buffer size of bottleneck link buffer",
                    default=25)

parser.add_argument('--cong',
                    dest="cong",
                    help="Congestion control algorithm to use",
                    default="reno")

parser.add_argument('--pacing',
                    action="store_true",
                    help="Enable TCP Pacing")

parser.add_argument('--iperf',
                    dest='iperf',
                    help='Path to custom iperf',
                    required=True)

# Expt parameters
args = parser.parse_args()

CUSTOM_IPERF_PATH = args.iperf
#print(args.iperf)
#assert(os.path.exists(CUSTOM_IPERF_PATH))

if not os.path.exists(args.dir):
    os.makedirs(args.dir)

lg.setLogLevel('info')

clients = []
servers = []

# Topology to be instantiated in Mininet
class StarTopo(Topo):
    "Star topology for Buffer Sizing experiment"

    def __init__(self, n=1, cpu=None, delay_host=None, delay_net=None,
                  bw_net=None, maxq=None, nflows=None):
        # Add default members to class.
        super(StarTopo, self ).__init__()
        self.n = n
        self.cpu = cpu
        self.delay_host = delay_host
        self.delay_net = delay_net
        self.bw_net = bw_net
        self.maxq = maxq
        self.nflows = nflows
        self.create_topology()

    def create_topology(self):
        # the sender bottleneck router
        switch_client = self.addSwitch('s0')
        # the receiver bottleneck router
        switch_server = self.addSwitch('s1')

        #bottleneck link
        #custom tweak to bypass Mininet/netem limitations
        queue_size = self.maxq + (args.delay_net * self.bw_net * 1000) / (8 * ADVMSS)
	    #queue_size = self.maxq
        self.addLink(switch_client, switch_server,
	           bw=self.bw_net, delay=self.delay_net, loss=0, max_queue_size=queue_size)

        # the sender-receiver pairs
        bw = 4 * self.bw_net * self.nflows
        for i in range(self.n):
            client = self.addHost('client%d' % i)
            self.addLink(client, switch_client,
	           bw=bw, delay=self.delay_host, loss=0, max_queue_size=LARGE_QUEUE_VALUE)
            server = self.addHost('server%d' % i)
            self.addLink(switch_server, server,
	           bw=bw, delay=self.delay_host, loss=0, max_queue_size=LARGE_QUEUE_VALUE)

def start_ping(net, src='client0', dst='server0'):
  h1 = net.getNodeByName(src)
  h2 = net.getNodeByName(dst)
  if args.pacing:
      filename = "Pacing.ping"
  else:
      filename = "NewReno.ping"
  cmd = 'ping -i 0.1 %s > %s/%s' % (h2.IP(), args.dir, filename)
  h1.popen(cmd, shell=True)

def stop_ping():
  Popen("killall -9 ping", shell=True).wait()

def start_tcpprobe():
    fn = ''
    if(args.pacing):
        fn = 'Pacing.tcpprobe'
    else:
        fn = 'NewReno.tcpprobe'
    "Install tcp_probe module and dump to file"
    os.system("rmmod tcp_probe 2>/dev/null; modprobe tcp_probe;")
    Popen("cat /proc/net/tcpprobe > %s/%s" %
          (args.dir, fn), shell=True)

def stop_tcpprobe():
    os.system("killall -9 cat; rmmod tcp_probe &>/dev/null;")

def start_qmon(iface, interval_sec=0.1):
    fn = ''
    if(args.pacing):
        fn = 'qlen_mod_%s.txt' % iface
    else:
        fn = 'qlen_%s.txt' % iface
    monitor = Process(target=monitor_qlen,
                      args=(iface, interval_sec, '%s/%s' %
                            (args.dir, fn)))
    monitor.start()
    return monitor

def start_tmon(iface, interval_sec=0.1):
    fn = ''
    if(args.pacing):
        fn = 'Pacing.cthroughput'
    else:
        fn = 'NewReno.cthroughput'
    monitor = Process(target=monitor_cumulative_throughput,
                      args=(iface, interval_sec, '%s/%s' %
                            (args.dir, fn)))
    monitor.start()
    return monitor

# set TCP MSS to ADVMSS
def set_advmss(host):
    print ('setting advmss of host %s to %d' % (host.name, ADVMSS))
    host.cmd('ip route change 10.0.0.0/8 dev %s-eth0 advmss %d' % (host.name, ADVMSS))

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
        print ('.')
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
    rtt = 2 * (args.delay_net + 2 * args.delay_host)
    diff = abs(avgRtt - rtt)
    if((diff / rtt) > 0.1): #rough verification
        print (diff)
        raise Exception('Latency check failed')
    return avgRtt


# verify the latency settings of the topology
def verify_latency(net):
    print ("Verifying latency (avg RTT)...")
    client = net.getNodeByName('client0')
    server = net.getNodeByName('server0')
    #for h in hosts:
        #print "%s <-> server: %sms" % (h.name, do_ping(net, h, server))
    print ("%s <-> %s: %sms" % (client.name, server.name, do_ping(net, client, server)))
    cprint("Latency check passed", "green")

# verify the bandwidth settings of the topology
def verify_bandwidth(net, nb = 0):
    print ("Verifying bandwidth...")
    s = net.getNodeByName('s0')
    c = net.getNodeByName('c0')

    print ("Generating TCP traffic using iperf...")
    server = s.popen("%s -s" % (CUSTOM_IPERF_PATH))
    client = c.popen("%s -c %s -t 100" % (CUSTOM_IPERF_PATH, s.IP()))
    medRate = median(get_rates('s1-eth1'))
    diff = abs(medRate - args.bw_net)
    if((diff / args.bw_net) > 0.1):
        if(nb > 0):
            raise Exception('Bandwidth check failed')
        else:
            cprint("Bandwidth check failed, second try", "red")
            verify_bandwidth(net, nb = 1)
    print ("Host - server bandwidth: %.3fMb/s" % medRate)
    client.kill()
    server.kill()

    cprint("Bandwidth check passed", "green")
    os.system('killall -9 ' + CUSTOM_IPERF_PATH)


# Start iperf on the receiver node
# Note: The output file should be <args.dir>/iperf_server.txt
#       It will be used later in count_connections()

def start_receiver(net):
    for i in xrange(args.n):
        serverName = 'server%d' % i
        server = net.getNodeByName(serverName)
        #no need to specify receiver window size?
        server.popen("%s -s -p %s -i 1 -yc > %s/iperf_server.txt" % (
                CUSTOM_IPERF_PATH, 5001, args.dir), shell=True)


# Start args.nflows flows across the senders in a round-robin fashion

def start_sender(net):
    # Seconds to run iperf; keep this very high
    seconds = 3600
    for i in xrange(args.n):
        serverName = 'server%d' % i
        clientName = 'client%d' % i
        server = net.getNodeByName(serverName)
        client = net.getNodeByName(clientName)
        for i in xrange(args.nflows):
            flow = client.popen("%s -c %s -p %s -t %d -yc -Z %s" % (
                    CUSTOM_IPERF_PATH, server.IP(), 5001, seconds, args.cong))

def main():
    "Create network and run Buffer Sizing experiment"

    start = time()

    # Set TCP/IP kernel options.
    #os.system("sysctl -w net.ipv4.tcp_slow_start_after_idle=0")
    os.system("sysctl -w net.ipv4.tcp_ecn=0")
    os.system("sysctl -w net.ipv4.tcp_frto=0")
    #os.system("sysctl -w net.ipv4.tcp_timestamps=0")

    if(args.pacing):
        os.system("sysctl -w net.ipv4.tcp_pacing=1")
    else:
        os.system("sysctl -w net.ipv4.tcp_pacing=0")

    # Reset to known state
    topo = StarTopo(n=args.n, delay_host='%sms' % args.delay_host,
                    delay_net='%sms' % args.delay_net,
                    bw_net=args.bw_net, maxq=args.maxq, nflows=args.nflows)
    net = Mininet(topo=topo, host=CPULimitedHost, link=TCLink)
    net.start()
    #net.startTerms()
    dumpNodeConnections(net.hosts)
    net.pingAll()

    for c in xrange(args.n):
        clients.append(net.getNodeByName('client%d' % c))
    for s in xrange(args.n):
        servers.append(net.getNodeByName('server%d' % s))
    for s in servers:
        print(s.name)

    for h in (clients + servers):
        set_advmss(h)

    # verify letency and bandwidth of mininet topology
    verify_latency(net)
    #verify_bandwidth(net)

    start_tcpprobe()

    # Start monitoring cumulative throughput
    tmon = start_tmon(iface='s0-eth1')

    cprint("Starting experiment", "green")

    start_receiver(net)
    start_sender(net)
    start_ping(net)

    rtt = 2 * (args.delay_net + 2 * args.delay_host)
    sleep(500 * rtt / 1000)

    # Store output.  It will be parsed by run.sh after the entire
    # sweep is completed.  Do not change this filename!
    #output = "%d %s %.3f\n" % (total_flows, ret, ret * 1500.0)
    #open("%s/result.txt" % args.dir, "w").write(output)

    os.remove("ping.txt")
    # Shut down iperf and ping processes
    os.system('killall -9 ' + CUSTOM_IPERF_PATH)
    stop_ping()

    tmon.terminate()
    net.stop()
    Popen("killall -9 top bwm-ng tcpdump cat mnexec", shell=True).wait()
    stop_tcpprobe()
    end = time()
    cprint("Sweep took %.3f seconds" % (end - start), "yellow")

    # Restore TCP/IP kernel options.
    #os.system("sysctl -w net.ipv4.tcp_slow_start_after_idle=1")
    os.system("sysctl -w net.ipv4.tcp_ecn=1")
    os.system("sysctl -w net.ipv4.tcp_frto=0")
    #os.system("sysctl -w net.ipv4.tcp_timestamps=1")
    os.system("sysctl -w net.ipv4.tcp_pacing=0")

if __name__ == '__main__':
    try:
        main()
    except:
        print("-"*80)
        print("Caught exception.  Cleaning up...")
        print("-"*80)
        import traceback
        traceback.print_exc()
        os.system("killall -9 top bwm-ng tcpdump cat mnexec %s; mn -c" % (
                CUSTOM_IPERF_PATH))
        os.remove("ping.txt")
