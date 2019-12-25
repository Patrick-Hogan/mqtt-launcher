#!/bin/bash

if ps -efc | grep -q 'mythfrontend'; then
    killall mythfrontend
    killall mythfrontend.real
fi

for t in {0..10}; do
    if ps -efc | grep -q 'mythfrontend'; then
        sleep 1 
    else
        echo OFF
    fi
done
