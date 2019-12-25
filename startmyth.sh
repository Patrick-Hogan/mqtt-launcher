#!/bin/bash

IPADDR=127.0.0.1
PORT=6546

# Check to see if myth is already running; if it is, just jump to livetv
if ps -efc | grep mythfrontend | grep -vq grep; then
    if ! echo "query location" | nc -w 1 $IPADDR $PORT | grep -q LiveTV; then
        echo "jump livetv" | nc -w 1 $IPADDR $PORT
    fi
    echo "ON"
    exit 0
fi 

# Try to start myth:
mythfrontend --service &> /dev/null &
#echo Done launching mythfrontend.
sleep 2

# Since myth is interactive (won't return an exit code until closed), start it
# in the background and watch the process list to see if it launches. Check for
# up to 5 seconds.
for t in {0..5}; do
    #echo Checking for mythfrontend
    if ps -efc | grep mythfrontend | grep -vq grep; then
        #echo mythfrontend found. Waiting for menu
        for t2 in {0..5}; do
            resp=$(echo "query location" | nc -W 2 -w 5 $IPADDR $PORT)
            if [[ -z $resp ]]; then
                #echo "No response from frontend"
                sleep 1
                continue
            fi
            #echo "Received response: $resp"
            if echo "$resp" | grep -qv LiveTV; then 
                # Receive 2 bytes or wait for up to 5 s:
                #echo "Executing jump command"
                echo "jump livetv" | nc -W 2 -w 5 $IPADDR $PORT > /dev/null
                break
            fi
            sleep 1
        done
        echo ON
        exit 0
    fi 
    sleep 1
done
echo "Offline"

