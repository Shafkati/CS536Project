#!/bin/bash

# Exit on any failure
set -e

# Check for uninitialized variables
set -o nounset

ctrlc() {
	killall -9 python
	mn -c
	exit
}

trap ctrlc SIGINT

start=`date`
exptid=`date +%b%d-%H:%M`

rootdir=tcppacing-manyflows-$exptid
plotpath=util

num_hosts=5
iface=s0-eth1
#iperf=~/iperf-patched/src/iperf
iperf=/usr/bin/iperf

queue_size=60

for run in 1; do
for flows_per_host in 10; do
	dir=$rootdir/nf$flows_per_host-r$run

	python tcppacing.py --dir $dir -n $num_hosts\
		--nflows $flows_per_host --iperf $iperf --maxq $queue_size -b 10

	python tcppacing.py --dir $dir -n $num_hosts\
		--nflows $flows_per_host --pacing --iperf $iperf --maxq $queue_size -b 10

	#python $plotpath/plot_queue.py -f $dir/qlen_$iface.txt -o $dir/q.png
  python $plotpath/plot_cwnd.py -f $dir/Pacing.tcpprobe $dir/NewReno.tcpprobe -o $dir/cwnd.png
	python $plotpath/plot_cthroughput.py -f $dir/Pacing.cthroughput $dir/NewReno.cthroughput -o $dir/cthroughput.png
  python $plotpath/plot_ping.py -f $dir/Pacing.ping $dir/NewReno.ping -o $dir/rtt.png
	python $plotpath/plot_fairness.py -f $dir/Pacing.tcpprobe $dir/NewReno.tcpprobe -o $dir/fairness.png
done
done

#cat $rootdir/*/result.txt | sort -n -k 1
#python plot-results.py --dir $rootdir -o $rootdir/result.png
echo "Started at" $start
echo "Ended at" `date`
