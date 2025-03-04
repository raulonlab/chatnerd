#!/bin/bash
input="./questions.txt"
while IFS= read -r line
do
#   command="chatnerd chat '$line'"
#   echo $command
    chatnerd chat "$line"
    sleep 1
done < "$input"
