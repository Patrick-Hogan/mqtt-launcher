#!/usr/bin/env python

# Copyright (c) 2014 Jan-Piet Mens <jpmens()gmail.com>
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
# 3. Neither the name of mosquitto nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

__author__    = 'Jan-Piet Mens <jpmens()gmail.com>'
__copyright__ = 'Copyright 2014 Jan-Piet Mens'

import os
import sys
import subprocess
import logging
import logging.config
import paho.mqtt.client as paho   # pip install paho-mqtt
import time
import socket
import string
import yaml
import threading

QOS = 0
DEFAULT_TIMEOUT = 10  # seconds
CONFIG=os.getenv('MQTTLAUNCHERCONFIG', 'launcher.yaml')

try:
    cf = yaml.load(open(CONFIG,'r'), Loader=yaml.FullLoader)
except Exception as e:
    print("Cannot load configuration from file {0}: {1}".format(CONFIG, str(e)))
    sys.exit(2)

if cf.get('log'):
    logging.config.dictConfig(cf['log'])

logger = logging.getLogger(__name__) 
logger.info("Starting")
logger.debug("DEBUG MODE")

def runprog(topic, param=None):

    publish = "%s/report" % topic

    if param is not None and all(c in string.printable for c in param) == False:
        logger.debug("Param for topic %s is not printable; skipping" % (topic))
        return

    if not topic in topics:
        logger.info("Topic %s isn't configured" % topic)
        return

    if param is not None and param in topics[topic]:
        cmd = topics[topic].get(param)
        if cmd.get('arg_template', None):
            args = [arg.replace('{{ value }}', param) for arg in cmd['arg_template']]
        else:
            args = cmd.get('args', [])
    else:
        logger.info("No matching param (%s) for %s" % (param, topic))
        return

    logger.debug("Running t=%s: %s on pid: %d" % (topic, cmd['command'], os.getpid()))

    fullcmd = [cmd['command']]
    if args:
        fullcmd.extend(args)
    logger.debug("Args: %s" % ', '.join(args))

    timeout_sec = cmd.get('timeout', DEFAULT_TIMEOUT)
    proc = subprocess.Popen(fullcmd, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)
    timer = threading.Timer(timeout_sec, proc.kill)

    try:
        timer.start()
        res, err = proc.communicate()
        if res:
            res = res.decode().strip()
        if err:
            err = err.decode().strip()
        logger.debug("Result: %s; stderr: %s" % (str(res), str(err)))
    except Exception as e:
        res = "*****> %s" % str(e)
    finally:
        timer.cancel()

    logger.debug("Publishing: \n\ttopic: %s\n\tpayload: %s\n\tretain: %s" % 
            (publish, res, cmd.get('retain', False)))
    (res, mid) =  mqttc.publish(publish, 
                                res,
                                qos=cmd.get('qos', QOS),
                                retain=cmd.get('retain', False))
    logger.debug("Done running program")

def publish_periodic(topic, param, interval):
    while True:
        runprog(topic, param)
        time.sleep(interval)

def on_message(mosq, userdata, msg):
    logger.debug(msg.topic+" "+str(msg.qos)+" "+str(msg.payload))

    runprog(msg.topic, str(msg.payload.decode()))
    logger.debug("on_message completed")

def on_connect(mosq, userdata, flags, result_code):
    logger.debug("Connected to MQTT broker, subscribing to topics...")
    for topic, cmd in topics.items():
        mqttc.subscribe(topic, cmd.get('qos', QOS))
    mqttc.publish('mqtt-launcher/{0}'.format(cf['mqtt']['clientid']), 
                  payload="Online", 
                  qos=0, 
                  retain=True) 

    for topic, commands in cf['topics'].items(): 
        for name, command in commands.items():
            interval = command.get('interval', 0)
            if interval:
                thread = threading.Thread(target=publish_periodic,
                                          args=(topic, name, interval),
                                          daemon=True)
                thread.start()


def on_disconnect(mosq, userdata, rc):
    logger.debug("OOOOPS! launcher disconnects")
    time.sleep(10)

if __name__ == '__main__':

    userdata = {}
    topics = cf.get('topics')

    if topics is None:
        logger.info("No topic list. Aborting")
        sys.exit(2)

    if cf.get('mqtt') is None:
        logger.error('No mqtt section in config. Aborting.')
        sys.exit(1)

    cf['mqtt'].setdefault('clientid', 'mqtt-launcher-%s' % os.getpid())
    clientid = cf['mqtt'].get('clientid')

    # initialise MQTT broker connection
    mqttc = paho.Client(clientid, clean_session=False)

    mqttc.on_message = on_message
    mqttc.on_connect = on_connect
    mqttc.on_disconnect = on_disconnect

    mqttc.will_set('mqtt-launcher/{0}'.format(clientid), 
                    payload="Offline", 
                    qos=0, 
                    retain=True)

    # Delays will be: 3, 6, 12, 24, 30, 30, ...
    #mqttc.reconnect_delay_set(delay=3, delay_max=30, exponential_backoff=True)

    if cf['mqtt'].get('username') is not None:
        mqttc.username_pw_set(cf['mqtt'].get('username'), cf['mqtt'].get('password'))
    
    if cf['mqtt'].get('tls', False):
        mqttc.tls_set()

    for topic, commands in cf['topics'].items(): 
        for name, command in commands.items():
            if command.get('command') is None:
                logger.error("Unable to configure {0}:{1} command not set"
                            .format(topic, name))

    mqttc.connect(cf['mqtt'].get('broker', 'localhost'), int(cf['mqtt'].get('port', 1883)), 60)

    while True:
        try:
            mqttc.loop_forever()
        except socket.error:
            time.sleep(5)
        except KeyboardInterrupt:
            sys.exit(0)

