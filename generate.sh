#!/bin/bash

SECONDS=0
# for i in {1..10}
# do
    for t in {12..42}
    do
        echo "Generate $i/$t"
        python3 generator.py --teams=$t --games=6 --output="./website"
        duration=$SECONDS
        echo "$((duration / 60)) minutes and $((duration % 60)) seconds elapsed."
    done
# done
