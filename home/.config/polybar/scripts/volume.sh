#!/bin/bash

print_volume() {
    VOL_RAW=$(wpctl get-volume @DEFAULT_AUDIO_SINK@)
    MUTED=$(echo "$VOL_RAW" | grep -q "MUTED" && echo "yes" || echo "no")
    VOL=$(echo "$VOL_RAW" | grep -Po '[\d.]+' | awk '{printf "%d", $1*100}')
    [ "$VOL" -gt 100 ] && VOL=100

    if [ "$MUTED" = "yes" ]; then
        echo "%{F#888888}X mut%{F-}"
    else
        echo "%{F#ffffff}V ${VOL}%%{F-}"
    fi
}

print_volume
pactl subscribe 2>/dev/null | grep --line-buffered "sink" | while read -r _; do
    print_volume
done