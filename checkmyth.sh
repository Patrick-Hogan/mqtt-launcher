#!/bin/bash

if ps -efc | grep mythfrontend | grep -vq grep; then
    echo ON
else
    echo OFF
fi
