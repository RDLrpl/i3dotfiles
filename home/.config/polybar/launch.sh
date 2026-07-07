#!/usr/bin/env bash
pkill polybar

sleep 1

echo "---" | tee -a /tmp/polybar.log

if type "xrandr" > /dev/null; then
  for m in $(xrandr --query | grep " connected" | cut -d" " -f1); do
    MONITOR=$m polybar i3 2>&1 | tee -a /tmp/polybar.log &
  done
else
  polybar i3 2>&1 | tee -a /tmp/polybar.log &
fi

disown
