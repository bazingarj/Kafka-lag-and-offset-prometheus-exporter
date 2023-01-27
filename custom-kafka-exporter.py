# -*- coding: utf-8 -*-

"""
Author: Rahul Juneja
Description: This is a custom prometheus exporter to export kafka consumers group lags and offsets.
"""

import os,subprocess, re
import time
from prometheus_client import start_http_server, Gauge
import asyncio

KAFKA = "{{ Kafka.Servers }}"
IgnoreConsumerGroups = "{{ Kafka.IgnoreConsumerGroups }}".split(",")
WhitelistConsumerGroups = "{{ Kafka.WhitelistConsumerGroups }}".split(",")

class CustomExporter:
    finalList = []
    def __init__(self) -> None:
        self.lags = Gauge("kafka_lag_metric", "", ["consumer_group","topic","partition"])
        self.offsets = Gauge("kafka_offset_metric", "", ["consumer_group","topic","partition"])

    async def run(self, group):
        global KAFKA
        if group == '' or group in IgnoreConsumerGroups:
            return ''
        if len(WhitelistConsumerGroups) > 0  and WhitelistConsumerGroups[0] != '' and group not in WhitelistConsumerGroups:
            return ''
        SCRIPT = '/home/kafka/kafka/bin/./kafka-consumer-groups.sh'
        cmd = ''+SCRIPT+' --bootstrap-server '+KAFKA+' --group '+group+' --describe'
        proc = await asyncio.create_subprocess_shell( cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

        stdout, stderr = await proc.communicate()

        if stdout:
            tmp1 = stdout.decode('utf-8').split("\n")
            skipHeader=False;
            headers = []
            for j in tmp1:
                if j != '':
                    tmp2 = re.sub(' +', ' ', j).split(' ')
                else:
                    continue
                if not skipHeader:
                    headers = tmp2.copy()
                    skipHeader = True
                    continue
                tmp3 = {}
                for i in range(len(tmp2)):
                    tmp3[headers[i]] = tmp2[i]
                self.finalList.append(tmp3)

    async def run_cmds(self, shell_commands):
        for f in asyncio.as_completed([self.run(c) for c in shell_commands]):
            await f

    def getConsumerGroupMetrics(self):
        result = subprocess.run(['/home/kafka/kafka/bin/./kafka-consumer-groups.sh','--bootstrap-server',KAFKA,'--list'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        listGroupsTxt =  result.stdout.decode('utf-8')

        listGroups = listGroupsTxt.split("\n")

        start = 0
        end = len(listGroups)
        step = {{ Kafka.ParallelFetch }}
        for i in range(start, end, step):
            tmp = listGroups[i:i+step]
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete( self.run_cmds( tmp ) )
            loop.close()


    def main(self):
        polling_interval_seconds = int(os.getenv("POLLING_INTERVAL_SECONDS", "{{ Exporter.PollingInterval }}"))
        exporter_port = int(os.getenv("EXPORTER_PORT", "{{ Exporter.Port }}"))
        start_http_server(exporter_port)
        while True:
            self.getConsumerGroupMetrics()
            for m in self.finalList:
                self.offsets.labels(consumer_group=m['GROUP'],topic=m['TOPIC'],partition=m['PARTITION']).set( m['CURRENT-OFFSET'].replace('-', '0') )
                self.lags.labels(consumer_group=m['GROUP'],topic=m['TOPIC'],partition=m['PARTITION']).set( m['LAG'].replace('-', '0') )
            self.finalList = []
            #print('Iteration Complete')
            time.sleep({{ Exporter.GapBetweenFetch }})

if __name__ == "__main__":
    c = CustomExporter()
    c.main()
